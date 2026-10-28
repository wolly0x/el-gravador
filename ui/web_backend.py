"""Backend do El Gravador 18 Pro Max para a interface web.

Este processo mantém a janela Tk real escondida e expõe as operações do
gravador por um pequeno servidor HTTP local.  A janela web (PyWebView) roda
em outro processo, no thread principal, e conversa com este backend.

A separação é intencional: o Tkinter e o WebView2 têm loops de eventos
próprios.  Manter o núcleo/Tk neste processo evita bloqueios e preserva o
HUD, o indicador de gravação e a seleção de região que já foram validados.
"""

from __future__ import annotations

import argparse
import base64
import copy
import json
import logging
import os
import queue
import secrets
import sys
import threading
import tkinter as tk
from concurrent.futures import Future
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from nucleo import caminhos, codegen, imagens, legado, logs, passos
from nucleo.config import Config
from nucleo.dpi import habilitar_dpi
from nucleo.projeto import Projeto

LOG = logging.getLogger("elgravador.web")


def _emitir_saida(texto: str) -> None:
    """Escreve no stdout do processo, mesmo em builds windowed do PyInstaller."""
    linha = texto.rstrip("\r\n") + "\n"
    try:
        if sys.stdout is not None:
            sys.stdout.write(linha)
            sys.stdout.flush()
            return
    except Exception:
        pass
    try:
        os.write(1, linha.encode("utf-8", errors="replace"))
    except Exception:
        pass


def _gravar_pronto(caminho: Path, porta: int, token: str) -> None:
    """Grava o handshake em arquivo para não depender de stdout no .exe."""
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_text(
        json.dumps({"porta": porta, "token": token}, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(temporario, caminho)



class _FakeMessageBox:
    """Evita diálogos nativos do Tk; as mensagens vão para a interface web."""

    def __init__(self, limite: int = 40):
        self.limite = limite
        self.itens: list[dict[str, str]] = []

    def _add(self, nivel: str, titulo: str, texto: str) -> None:
        self.itens.append(
            {"nivel": nivel, "titulo": str(titulo), "texto": str(texto)}
        )
        if len(self.itens) > self.limite:
            del self.itens[: len(self.itens) - self.limite]

    def showinfo(self, titulo, texto, **_kwargs):
        self._add("info", titulo, texto)

    def showwarning(self, titulo, texto, **_kwargs):
        self._add("aviso", titulo, texto)

    def showerror(self, titulo, texto, **_kwargs):
        self._add("erro", titulo, texto)

    def askyesno(self, titulo, texto, **_kwargs):
        self._add("pergunta", titulo, texto)
        return True

    def askyesnocancel(self, titulo, texto, **_kwargs):
        self._add("pergunta", titulo, texto)
        return True


class _FakeFileDialog:
    """Só existe como proteção: a interface web fornece os caminhos."""

    def _erro(self, *_args, **_kwargs):
        raise RuntimeError("Use os diálogos da interface web para escolher arquivos.")

    askopenfilename = _erro
    asksaveasfilename = _erro
    askdirectory = _erro


class _Contexto:
    """Resultado de um comando executado no thread do Tk."""

    def __init__(self):
        self.futuro: Future = Future()
        self.finalizado = False

    def concluir(self, dados: Any = None) -> None:
        if not self.finalizado:
            self.finalizado = True
            self.futuro.set_result({"ok": True, "data": _json_seguro(dados)})

    def falhar(self, mensagem: str) -> None:
        if not self.finalizado:
            self.finalizado = True
            self.futuro.set_result({"ok": False, "erro": str(mensagem)})


def _json_seguro(valor: Any) -> Any:
    if isinstance(valor, Path):
        return str(valor)
    if isinstance(valor, dict):
        return {str(k): _json_seguro(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_json_seguro(v) for v in valor]
    if isinstance(valor, (str, int, float, bool)) or valor is None:
        return valor
    return str(valor)


def _numero(valor: Any, padrao: float = 0.0) -> float:
    try:
        return float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return padrao


def _inteiro(valor: Any, padrao: int = 0) -> int:
    return int(_numero(valor, padrao))


class Backend:
    def __init__(self, root: tk.Tk, cfg: Config, projeto: Projeto | None):
        self.root = root
        self.cfg = cfg
        self.msgbox = _FakeMessageBox()
        self.fila: "queue.Queue[tuple[str, dict, _Contexto]]" = queue.Queue()
        self._status_tipo = "info"
        self._dica: tk.Toplevel | None = None

        # O aplicativo Tk é usado como controlador maduro: gravação,
        # execução, HUD, indicador e captura de região já vivem nele.
        import ui.dialogos as dialogos
        import ui.janela as janela

        janela.messagebox = self.msgbox
        janela.filedialog = _FakeFileDialog()
        janela.simpledialog = _FakeFileDialog()
        dialogos.messagebox = self.msgbox
        dialogos.filedialog = _FakeFileDialog()
        dialogos.simpledialog = _FakeFileDialog()

        self.janela = janela
        self.dialogos = dialogos
        self.app = janela.Aplicativo(root, cfg, projeto)
        self.app._status_original = self.app._status
        self.app._status = self._status
        self._esconder_janela_tk()
        self.root.after(25, self._processar_fila)

    # ------------------------------------------------------------------
    # Thread do Tk
    # ------------------------------------------------------------------
    def _esconder_janela_tk(self) -> None:
        try:
            self.root.withdraw()
        except tk.TclError:
            pass
        # Alguns fluxos do aplicativo chamam deiconify() ao terminar. A
        # janela Tk nunca deve aparecer no produto final.
        self.root.deiconify = lambda: None  # type: ignore[assignment]
        self.root.lift = lambda: None  # type: ignore[assignment]

    def _status(self, texto: str, tipo: str = "info") -> None:
        self._status_tipo = tipo
        try:
            self.app._status_original(texto, tipo)
        except Exception:
            pass

    def _processar_fila(self) -> None:
        while True:
            try:
                comando, argumentos, ctx = self.fila.get_nowait()
            except queue.Empty:
                break
            try:
                resultado = self._executar(comando, argumentos, ctx)
                # Comandos assíncronos (captura de ponto/região) devolvem o
                # próprio Future e concluem quando o usuário termina.
                if resultado is not ctx.futuro and not ctx.finalizado:
                    ctx.concluir(resultado)
            except Exception as exc:  # pragma: no cover - defensivo
                LOG.exception("Erro no comando web %s", comando)
                ctx.falhar(f"{type(exc).__name__}: {exc}")
        try:
            self.root.after(25, self._processar_fila)
        except tk.TclError:
            pass

    def _executar(self, comando: str, args: dict, ctx: _Contexto) -> Any:
        metodo = getattr(self, f"cmd_{comando}", None)
        if metodo is None:
            raise ValueError(f"Comando desconhecido: {comando}")
        return metodo(args or {}, ctx)

    # ------------------------------------------------------------------
    # Mensagens e pequenos auxiliares
    # ------------------------------------------------------------------
    def _dica_tela(self, texto: str) -> None:
        self._fechar_dica()
        try:
            from nucleo.dpi import area_virtual

            vx, vy, vw, _vh = area_virtual()
        except Exception:
            vx = vy = 0
            vw = 1280
        topo = tk.Toplevel(self.root)
        topo.overrideredirect(True)
        topo.configure(bg="#101014")
        try:
            topo.attributes("-topmost", True)
            topo.attributes("-alpha", 0.96)
        except tk.TclError:
            pass
        largura = max(420, min(760, vw - 40))
        topo.geometry(f"{largura}x48+{vx + (vw - largura) // 2}+{vy + 28}")
        tk.Label(
            topo,
            text=texto,
            bg="#101014",
            fg="#F5F5F7",
            font=("Segoe UI", 11, "bold"),
            padx=18,
            pady=12,
        ).pack(fill=tk.BOTH, expand=True)
        self._dica = topo

    def _fechar_dica(self) -> None:
        if self._dica is not None:
            try:
                self._dica.destroy()
            except tk.TclError:
                pass
        self._dica = None

    def _atual(self) -> int | None:
        try:
            for item in self.app.lista.tree.get_children():
                if "atual" in self.app.lista.tree.item(item, "tags"):
                    return self.app.lista.tree.index(item)
        except Exception:
            pass
        return None

    def _snapshot(self) -> dict[str, Any]:
        app = self.app
        projeto = app.projeto

        tipos = {}
        for nome, item in passos.TIPOS.items():
            tipos[nome] = {
                "tipo": nome,
                "titulo": item.titulo,
                "categoria": item.categoria,
                "padrao": copy.deepcopy(item.padrao()),
            }

        itens = []
        for indice, passo in enumerate(projeto.passos):
            meta = passos.TIPOS.get(passo.tipo)
            itens.append(
                {
                    "indice": indice,
                    "id": passo.id,
                    "tipo": passo.tipo,
                    "titulo": meta.titulo if meta else passo.tipo,
                    "categoria": meta.categoria if meta else "outro",
                    "rotulo": passo.rotulo,
                    "params": copy.deepcopy(passo.params),
                    "ativo": bool(passo.ativo),
                }
            )

        rec = app.rec

        return {
            "projeto": {
                "nome": projeto.nome,
                "caminho": str(projeto.caminho) if projeto.caminho else None,
                "alterado": bool(projeto.alterado),
                "repeticoes": projeto.repeticao(),
                "passos": itens,
                "problemas": projeto.validar(),
            },
            "config": copy.deepcopy(self.cfg.dados),
            "paleta": self.cfg.paleta(),
            "fontes": [
                "Segoe UI", "Inter", "Consolas", "Arial", "Calibri",
                "Tahoma", "Verdana", "Courier New", "Microsoft YaHei UI",
            ],
            "tipos": tipos,
            "teclas": list(passos.TECLAS_VALIDAS),
            "status": str(app.lbl_status.cget("text")),
            "status_tipo": self._status_tipo,
            "gravando": bool(app.gravando),
            "executando": bool(app.executando),
            "pausado": bool(
                (rec is not None and rec.pausado) or app.pausar.is_set()
            ),
            "simular": bool(self.cfg.get("simular")),
            "atual": self._atual(),
            "rec": {
                "pausado": bool(rec.pausado) if rec is not None else False,
                "duracao": round(rec.duracao, 1) if rec is not None else 0,
                "eventos": rec.total_eventos if rec is not None else 0,
            },
            "logs": list(app._buffer_log[-500:]),
            "mensagens": list(self.msgbox.itens),
            "pastas": {
                "base": str(caminhos.BASE_DIR),
                "projetos": str(caminhos.PROJETOS_DIR),
                "imagens": str(caminhos.IMAGENS_DIR),
                "logs": str(caminhos.LOGS_DIR),
            },
            "versao": "18 Pro Max",
        }

    # ------------------------------------------------------------------
    # Comandos
    # ------------------------------------------------------------------
    def cmd_state(self, _args: dict, _ctx: _Contexto) -> dict:
        return self._snapshot()

    def cmd_ping(self, _args: dict, _ctx: _Contexto) -> dict:
        return {"mensagem": "pong"}

    def cmd_rename(self, args: dict, _ctx: _Contexto) -> dict:
        nome = str(args.get("nome") or "").strip() or "novo_projeto"
        self.app.projeto.nome = nome
        self.app._marcar_alterado()
        self.app._recarregar()
        self.app._status(f"Projeto renomeado para {nome}.")
        return self._snapshot()

    def cmd_set_repetitions(self, args: dict, _ctx: _Contexto) -> dict:
        valor = max(0, min(100000, _inteiro(args.get("valor"), 1)))
        self.app.projeto.config["repeticoes"] = valor
        self.app._marcar_alterado()
        self.app._recarregar()
        return self._snapshot()

    def cmd_set_simulate(self, args: dict, _ctx: _Contexto) -> dict:
        valor = bool(args.get("valor"))
        self.cfg.set("simular", valor)
        self._salvar_config()
        try:
            self.app.var_simular.set(valor)
        except Exception:
            pass
        return self._snapshot()

    def cmd_set_config(self, args: dict, _ctx: _Contexto) -> dict:
        patch = args.get("patch") or {}
        if not isinstance(patch, dict):
            raise ValueError("Configuração inválida.")
        patch = dict(patch)
        if "escala_web" in patch:
            patch["escala_web"] = max(15, min(22, _inteiro(patch["escala_web"], 15)))
        self.cfg.atualizar(patch)
        self._salvar_config()
        try:
            self.app.var_simular.set(bool(self.cfg.get("simular")))
        except Exception:
            pass
        return self._snapshot()

    def _salvar_config(self) -> None:
        try:
            self.cfg.salvar()
        except Exception as exc:
            LOG.warning("Não foi possível salvar a configuração: %s", exc)

    def cmd_new_project(self, _args: dict, _ctx: _Contexto) -> dict:
        self.app.projeto = Projeto("novo_projeto")
        self.app._desfazer.clear()
        self.app._recarregar()
        self.app._status("Novo projeto criado.")
        return self._snapshot()

    def cmd_open(self, args: dict, _ctx: _Contexto) -> dict:
        caminho = str(args.get("caminho") or "")
        if not caminho:
            raise ValueError("Nenhum arquivo informado.")
        self.app.projeto = Projeto.carregar(caminho)
        self.app._desfazer.clear()
        self.app._recarregar()
        self.app._status(f"Aberto: {caminho}", "ok")
        return self._snapshot()

    def cmd_save(self, _args: dict, _ctx: _Contexto) -> dict:
        if not self.app.projeto.caminho:
            raise ValueError("Escolha um local para salvar o projeto.")
        destino = self.app.projeto.salvar()
        self.app._recarregar()
        self.app._status(f"Salvo em {destino}", "ok")
        return {"caminho": str(destino), "state": self._snapshot()}

    def cmd_save_as(self, args: dict, _ctx: _Contexto) -> dict:
        caminho = str(args.get("caminho") or "")
        if not caminho:
            raise ValueError("Nenhum arquivo informado.")
        destino = self.app.projeto.salvar(caminho)
        self.app._recarregar()
        self.app._status(f"Salvo em {destino}", "ok")
        return {"caminho": str(destino), "state": self._snapshot()}

    def cmd_validate(self, _args: dict, _ctx: _Contexto) -> dict:
        problemas = self.app.projeto.validar()
        ausentes = [
            nome
            for nome in self.app.projeto.templates_usados()
            if not imagens.existe(nome)
        ]
        return {"problemas": problemas, "templates_ausentes": ausentes}

    def cmd_generate(self, args: dict, _ctx: _Contexto) -> dict:
        destino = str(args.get("caminho") or "")
        if not destino:
            raise ValueError("Nenhum destino informado.")
        repeticoes = _inteiro(args.get("repeticoes"), self.app.projeto.repeticao())
        self.app.projeto.config["repeticoes"] = max(0, repeticoes)
        self.app._marcar_alterado()
        info = codegen.exportar(self.app.projeto, destino, self.cfg.dados)
        self.app._log(
            f"[export] {info['script']} "
            f"({len(self.app.projeto.passos)} passos, "
            f"{len(info['templates'])} templates)"
        )
        if info["templates_ausentes"]:
            self.app._log(f"[export] templates ausentes: {info['templates_ausentes']}")
        self.app._status("Script gerado.", "ok")
        return _json_seguro(info)

    def cmd_import_preview(self, args: dict, _ctx: _Contexto) -> dict:
        caminho = str(args.get("caminho") or "")
        if not caminho:
            raise ValueError("Nenhum arquivo informado.")
        importado, avisos = legado.importar_script(caminho)
        return {
            "quantidade": len(importado.passos),
            "avisos": avisos,
            "repeticoes": importado.config.get("repeticoes"),
        }

    def cmd_import_apply(self, args: dict, _ctx: _Contexto) -> dict:
        caminho = str(args.get("caminho") or "")
        if not caminho:
            raise ValueError("Nenhum arquivo informado.")
        importado, avisos = legado.importar_script(caminho)
        substituir = bool(args.get("substituir"))
        self.app._snapshot()
        if substituir:
            self.app.projeto.passos = importado.passos
            if importado.config.get("repeticoes") is not None:
                self.app.projeto.config["repeticoes"] = importado.config["repeticoes"]
        else:
            self.app.projeto.passos.extend(importado.passos)
        self.app._marcar_alterado()
        self.app._recarregar()
        for aviso in avisos:
            self.app._log(f"[import] {aviso}")
        self.app._status(
            f"Importado: {len(importado.passos)} passo(s).", "ok"
        )
        return {
            "quantidade": len(importado.passos),
            "avisos": avisos,
            "state": self._snapshot(),
        }

    def cmd_import_templates(self, args: dict, _ctx: _Contexto) -> dict:
        pasta = str(args.get("pasta") or "")
        if not pasta:
            raise ValueError("Nenhuma pasta informada.")
        novos, iguais = imagens.importar_pasta(pasta)
        self.app._status(
            f"{novos} template(s) importado(s), {iguais} repetido(s).", "ok"
        )
        return {"novos": novos, "iguais": iguais}

    def cmd_add_step(self, args: dict, _ctx: _Contexto) -> dict:
        tipo = str(args.get("tipo") or "")
        if tipo not in passos.TIPOS:
            raise ValueError("Tipo de passo desconhecido.")
        params = args.get("params") or {}
        if not isinstance(params, dict):
            raise ValueError("Parâmetros inválidos.")
        indice = args.get("indice")
        self.app._snapshot()
        if indice is None:
            posicao = len(self.app.projeto.passos)
        else:
            posicao = max(0, min(len(self.app.projeto.passos), _inteiro(indice)))
        self.app.projeto.adicionar(tipo, posicao, **params)
        if tipo == "bloco_inicio":
            self.app.projeto.adicionar("bloco_fim", posicao + 1)
        self.app._marcar_alterado()
        self.app._recarregar(posicao)
        self.app._status(
            f"Passo adicionado: {passos.rotulo(tipo, params)}", "ok"
        )
        return {"indice": posicao, "state": self._snapshot()}

    def cmd_update_step(self, args: dict, _ctx: _Contexto) -> dict:
        indice = _inteiro(args.get("indice"), -1)
        if not (0 <= indice < len(self.app.projeto.passos)):
            raise ValueError("Passo inválido.")
        tipo = str(args.get("tipo") or self.app.projeto.passos[indice].tipo)
        params = args.get("params") or {}
        if tipo not in passos.TIPOS:
            raise ValueError("Tipo de passo desconhecido.")
        if not isinstance(params, dict):
            raise ValueError("Parâmetros inválidos.")
        self.app._snapshot()
        self.app.projeto.substituir(indice, tipo, params)
        self.app._marcar_alterado()
        self.app._recarregar(indice)
        self.app._status("Passo atualizado.", "ok")
        return {"indice": indice, "state": self._snapshot()}

    def cmd_delete_step(self, args: dict, _ctx: _Contexto) -> dict:
        indice = _inteiro(args.get("indice"), -1)
        if not (0 <= indice < len(self.app.projeto.passos)):
            raise ValueError("Passo inválido.")
        self.app.excluir_selecionado(indice)
        return self._snapshot()

    def cmd_duplicate_step(self, args: dict, _ctx: _Contexto) -> dict:
        indice = _inteiro(args.get("indice"), -1)
        if not (0 <= indice < len(self.app.projeto.passos)):
            raise ValueError("Passo inválido.")
        if self.app.projeto.passos[indice].tipo == "bloco_fim":
            raise ValueError("Duplique o INÍCIO do bloco; o FIM é criado junto.")
        self.app.duplicar_selecionado(indice)
        return self._snapshot()

    def cmd_toggle_step(self, args: dict, _ctx: _Contexto) -> dict:
        indice = _inteiro(args.get("indice"), -1)
        if not (0 <= indice < len(self.app.projeto.passos)):
            raise ValueError("Passo inválido.")
        self.app.alternar_passo(indice)
        return self._snapshot()

    def cmd_move_step(self, args: dict, _ctx: _Contexto) -> dict:
        origem = _inteiro(args.get("origem"), -1)
        destino = _inteiro(args.get("destino"), -1)
        self.app.mover_passo(origem, destino)
        return self._snapshot()

    def cmd_undo(self, _args: dict, _ctx: _Contexto) -> dict:
        self.app.desfazer()
        return self._snapshot()

    def cmd_clear_log(self, _args: dict, _ctx: _Contexto) -> dict:
        self.app._limpar_log()
        return {"ok": True}

    def cmd_open_folder(self, args: dict, _ctx: _Contexto) -> dict:
        chave = str(args.get("chave") or "base")
        destinos = {
            "imagens": caminhos.IMAGENS_DIR,
            "projetos": caminhos.PROJETOS_DIR,
            "logs": caminhos.LOGS_DIR,
            "base": caminhos.BASE_DIR,
        }
        destino = destinos.get(chave)
        if destino is None:
            # A interface também abre a pasta de um arquivo gerado/exportado.
            candidato = Path(chave).expanduser()
            if candidato.exists():
                destino = candidato if candidato.is_dir() else candidato.parent
        if destino is None:
            raise ValueError("Pasta não encontrada.")
        self.dialogos.abrir_pasta(destino)
        return {"pasta": str(destino)}

    # ------------------------------------------------------------------
    # Execução
    # ------------------------------------------------------------------
    def cmd_execute(self, args: dict, _ctx: _Contexto) -> dict:
        if self.app.executando or self.app.gravando:
            raise ValueError("Já existe uma execução ou gravação em andamento.")
        if not self.app.projeto.passos:
            raise ValueError("O projeto está vazio.")
        problemas = self.app.projeto.validar()
        if problemas:
            raise ValueError("\n".join(problemas[:12]))
        ausentes = [
            nome
            for nome in self.app.projeto.templates_usados()
            if not imagens.existe(nome)
        ]
        if ausentes:
            raise ValueError(
                "Templates ausentes:\n" + "\n".join(ausentes[:12])
            )
        modo = str(args.get("modo") or "tudo")
        indice = _inteiro(args.get("indice"), -1)
        de, ate, teste = 0, None, False
        if modo == "ate":
            if not (0 <= indice < len(self.app.projeto.passos)):
                raise ValueError("Selecione o último passo.")
            ate = indice
        elif modo == "daqui":
            if not (0 <= indice < len(self.app.projeto.passos)):
                raise ValueError("Selecione o primeiro passo.")
            de = indice
        elif modo == "teste":
            if not (0 <= indice < len(self.app.projeto.passos)):
                raise ValueError("Selecione um passo para testar.")
            de = ate = indice
            teste = True
        simular = bool(self.cfg.get("simular"))
        try:
            self.app.var_simular.set(simular)
        except Exception:
            pass
        self.app._executar(de=de, ate=ate, teste=teste)
        if not self.app.executando:
            raise ValueError("Não foi possível iniciar a execução. Veja as mensagens do aplicativo.")
        return {"simular": simular}

    def cmd_pause_execution(self, _args: dict, _ctx: _Contexto) -> dict:
        self.app.alternar_pausa()
        return self._snapshot()

    def cmd_stop_execution(self, _args: dict, _ctx: _Contexto) -> dict:
        self.app.parar_execucao()
        return self._snapshot()

    # ------------------------------------------------------------------
    # Gravação
    # ------------------------------------------------------------------
    def cmd_start_recording(self, _args: dict, _ctx: _Contexto) -> dict:
        if self.app.executando:
            raise ValueError("Pare a execução antes de gravar.")
        if not self.app.gravando:
            self.app._iniciar_gravacao()
        if not self.app.gravando:
            raise ValueError("Não foi possível iniciar a gravação.")
        return {"gravando": True}

    def cmd_stop_recording(self, _args: dict, _ctx: _Contexto) -> dict:
        if self.app.rec is not None:
            self.app._parar_gravacao()
        return self._snapshot()

    def cmd_pause_recording(self, _args: dict, _ctx: _Contexto) -> dict:
        self.app.pausar_gravacao()
        return {"pausado": bool(self.app.rec.pausado) if self.app.rec else False}

    def cmd_discard_recording(self, _args: dict, _ctx: _Contexto) -> dict:
        self.app.descartar_gravacao()
        return self._snapshot()

    # ------------------------------------------------------------------
    # Capturas
    # ------------------------------------------------------------------
    def cmd_capture_point(self, _args: dict, ctx: _Contexto) -> Any:
        if self.app.executando or self.app.gravando:
            raise ValueError("Pare a execução/gravação antes de capturar.")
        self._dica_tela("Clique no ponto desejado  •  ESC cancela")

        def concluir(ponto):
            self._fechar_dica()
            if ponto is None:
                self.app._status("Captura cancelada.", "aviso")
                ctx.concluir({"ponto": None})
            else:
                self.app._status(f"Ponto capturado: {ponto}", "ok")
                ctx.concluir({"ponto": [int(ponto[0]), int(ponto[1])]})

        self.dialogos.capturar_ponto(self.root, concluir)
        return ctx.futuro  # sinaliza que o comando é assíncrono

    def cmd_capture_region(self, args: dict, ctx: _Contexto) -> Any:
        if self.app.executando or self.app.gravando:
            raise ValueError("Pare a execução/gravação antes de capturar.")
        nome_base = str(args.get("nome") or "regiao").strip() or "regiao"
        self._dica_tela("Arraste para marcar a região  •  ESC cancela")

        def concluir(regiao):
            self._fechar_dica()
            if not regiao:
                self.app._status("Captura cancelada.", "aviso")
                ctx.concluir({"nome": None})
                return
            try:
                x, y, largura, altura = regiao
                tela, ox, oy = imagens.capturar_tela()
                recorte = imagens.recortar(
                    tela, x, y, x + largura, y + altura, ox, oy
                )
                nome = imagens.salvar_template(
                    recorte,
                    nome_base or f"regiao_{largura}x{altura}",
                    meta={"regiao": [x, y, largura, altura]},
                )
            except Exception as exc:
                LOG.exception("Falha ao capturar template")
                self.app._status("Falha ao capturar template.", "erro")
                ctx.concluir({"nome": None, "erro": str(exc)})
                return
            self.app._log(f"[template] salvo: {nome}")
            self.app._status(f"Template salvo: {nome}", "ok")
            ctx.concluir({"nome": nome, "regiao": [x, y, largura, altura]})

        self.janela.selecionar_regiao(self.root, concluir)
        return ctx.futuro

    def cmd_test_template(self, args: dict, _ctx: _Contexto) -> dict:
        nome = str(args.get("nome") or "").strip()
        if not nome:
            raise ValueError("Escolha um template.")
        if not imagens.existe(nome):
            raise ValueError(f'Template "{nome}" não encontrado.')
        confianca = min(1.0, max(0.5, _numero(args.get("confianca"), 0.9)))
        tpl = imagens.carregar(nome)
        tela, ox, oy = imagens.capturar_tela()
        resultado = imagens.localizar_detalhado(
            tela,
            ox,
            oy,
            tpl,
            confianca,
            None,
            bool(self.cfg.get("imagem_cinza", True)),
        )
        diagnostico = imagens.salvar_diagnostico(
            tela,
            tpl,
            resultado,
            nome,
            ox=ox,
            oy=oy,
            confianca=confianca,
            prefixo="diag_teste",
        )
        if resultado.centro is not None:
            texto = (
                f"Encontrada em {resultado.centro}.\n"
                f"Score: {resultado.score:.3f} (confiança {confianca:.2f})."
            )
        else:
            texto = (
                "Não encontrada.\n"
                f"Melhor score: {resultado.melhor_score:.3f} "
                f"(confiança {confianca:.2f})."
            )
            if resultado.melhor_centro is not None:
                texto += f"\nMelhor ponto: {resultado.melhor_centro}."
        if diagnostico:
            texto += f"\n\nDiagnóstico: {diagnostico}"
        self.app._log(f"[teste] {nome}: {texto.replace(chr(10), ' ')}")
        return {
            "nome": nome,
            "encontrada": resultado.centro is not None,
            "centro": list(resultado.centro) if resultado.centro else None,
            "score": resultado.score,
            "melhor_score": resultado.melhor_score,
            "melhor_centro": (
                list(resultado.melhor_centro) if resultado.melhor_centro else None
            ),
            "diagnostico": str(diagnostico) if diagnostico else None,
            "texto": texto,
        }

    # ------------------------------------------------------------------
    # Templates
    # ------------------------------------------------------------------
    def cmd_list_templates(self, _args: dict, _ctx: _Contexto) -> dict:
        itens = []
        for item in imagens.listar():
            itens.append(
                {
                    "nome": item["nome"],
                    "largura": item.get("largura", 0),
                    "altura": item.get("altura", 0),
                    "criado": item.get("criado", ""),
                    "janela": item.get("janela", ""),
                }
            )
        return {"templates": itens}

    def cmd_template_data(self, args: dict, _ctx: _Contexto) -> dict:
        nome = str(args.get("nome") or "")
        arquivo = imagens.caminho(nome)
        if not nome or not arquivo.exists():
            raise ValueError("Template não encontrado.")
        dados = base64.b64encode(arquivo.read_bytes()).decode("ascii")
        return {"nome": nome, "data_url": f"data:image/png;base64,{dados}"}

    def cmd_remove_template(self, args: dict, _ctx: _Contexto) -> dict:
        nome = str(args.get("nome") or "")
        if not nome:
            raise ValueError("Template inválido.")
        removido = imagens.remover(nome)
        self.app._status(
            f"Template removido: {nome}" if removido else "Template não removido.",
            "ok" if removido else "aviso",
        )
        return {"removido": bool(removido)}

    # ------------------------------------------------------------------
    # Encerramento
    # ------------------------------------------------------------------
    def cmd_shutdown(self, _args: dict, ctx: _Contexto) -> Any:
        ctx.concluir({"encerrando": True})
        try:
            self.root.after(120, self.root.destroy)
        except tk.TclError:
            pass
        return ctx.futuro


class _Servidor(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class _Handler(BaseHTTPRequestHandler):
    backend: Backend
    token: str

    def log_message(self, _fmt, *_args):
        return

    def _responder(self, codigo: int, dados: dict) -> None:
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(corpo)
        except OSError:
            pass

    def do_GET(self):
        if self.path == "/health":
            self._responder(200, {"ok": True})
        else:
            self._responder(404, {"ok": False, "erro": "Rota não encontrada."})

    def do_POST(self):
        if self.path != "/api":
            self._responder(404, {"ok": False, "erro": "Rota não encontrada."})
            return
        backend = self.server.backend  # type: ignore[attr-defined]
        token = self.server.token  # type: ignore[attr-defined]
        if self.headers.get("X-Token") != token:
            self._responder(403, {"ok": False, "erro": "Token inválido."})
            return
        try:
            tamanho = int(self.headers.get("Content-Length") or 0)
            if tamanho <= 0 or tamanho > 2_000_000:
                raise ValueError("Corpo inválido.")
            corpo = json.loads(self.rfile.read(tamanho).decode("utf-8"))
            comando = str(corpo.get("comando") or "")
            args = corpo.get("args") or {}
            if not isinstance(args, dict):
                raise ValueError("Argumentos inválidos.")
        except Exception as exc:
            self._responder(400, {"ok": False, "erro": str(exc)})
            return

        ctx = _Contexto()
        backend.fila.put((comando, args, ctx))
        try:
            resultado = ctx.futuro.result(timeout=900)
        except Exception as exc:
            resultado = {"ok": False, "erro": f"Tempo esgotado: {exc}"}
        self._responder(200, resultado)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="El Gravador 18 Pro Max (backend)")
    parser.add_argument("--projeto", type=Path)
    parser.add_argument("--sem-logs", action="store_true")
    parser.add_argument("--ready-file", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    habilitar_dpi()
    caminhos.garantir_dirs()
    cfg = Config()
    cfg.carregar()
    logs.configurar(para_arquivo=not args.sem_logs)

    projeto = None
    if args.projeto:
        try:
            projeto = Projeto.carregar(args.projeto)
        except Exception as exc:
            _emitir_saida(f"ERRO: não foi possível abrir {args.projeto}: {exc}")
            return 2

    root = tk.Tk()
    root.withdraw()
    try:
        backend = Backend(root, cfg, projeto)
    except Exception as exc:
        LOG.exception("Falha ao criar o backend")
        _emitir_saida(f"ERRO: {type(exc).__name__}: {exc}")
        try:
            root.destroy()
        except Exception:
            pass
        return 2

    token = secrets.token_urlsafe(32)
    servidor = _Servidor(("127.0.0.1", 0), _Handler)
    servidor.backend = backend  # type: ignore[attr-defined]
    servidor.token = token  # type: ignore[attr-defined]
    porta = servidor.server_address[1]
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()

    if args.ready_file:
        try:
            _gravar_pronto(args.ready_file, int(porta), token)
        except Exception:
            LOG.exception("Não foi possível gravar o arquivo de handshake")
    _emitir_saida(f"READY {porta} {token}")
    try:
        root.mainloop()
    finally:
        if args.ready_file:
            try:
                args.ready_file.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            servidor.shutdown()
        except Exception:
            pass
        try:
            root.destroy()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
