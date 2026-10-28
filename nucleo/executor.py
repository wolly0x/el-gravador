"""Executor único: roda o projeto no app e é espelhado pelo script gerado."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from . import caminhos, imagens as imagens_padrao, passos
from .projeto import Passo, Projeto

LOG = logging.getLogger("elgravador")


class ExecucaoCancelada(Exception):
    """Pedido de parada (ESC / botão Parar)."""


class PassoFalhou(Exception):
    def __init__(self, indice: int, mensagem: str):
        super().__init__(mensagem)
        self.indice = indice
        self.mensagem = mensagem


@dataclass
class BuscaImagem:
    """Resultado de uma espera por imagem, com dados para diagnóstico."""

    centro: tuple[int, int] | None = None
    score: float = 0.0
    melhor_score: float = 0.0
    melhor_centro: tuple[int, int] | None = None
    segundos: float = 0.0
    diagnostico: Path | None = None


@dataclass
class Relatorio:
    inicio: datetime = field(default_factory=datetime.now)
    fim: datetime | None = None
    total: int = 0
    executados: int = 0
    ok: bool = False
    cancelado: bool = False
    falha_indice: int | None = None
    erro: str | None = None
    eventos: list[str] = field(default_factory=list)
    screenshot_erro: Path | None = None

    @property
    def duracao(self) -> float:
        final = self.fim or datetime.now()
        return (final - self.inicio).total_seconds()

    def resumo(self) -> str:
        if self.cancelado:
            return f"Cancelado após {self.executados} passo(s) em {self.duracao:.1f}s."
        if self.erro:
            numero = (self.falha_indice or 0) + 1
            return f"Falhou no passo #{numero}: {self.erro}"
        return f"Concluído: {self.executados}/{self.total} passos em {self.duracao:.1f}s."


class Executor:
    """Executa uma faixa de passos, respeitando blocos de repetição."""

    def __init__(
        self,
        projeto: Projeto,
        backend,
        cfg: Mapping[str, Any],
        *,
        imagens=None,
        parar=None,
        pausar=None,
        ao_passo: Callable[[int, Passo], None] | None = None,
        ao_log: Callable[[str], None] | None = None,
        ao_status: Callable[[str], None] | None = None,
        simular: bool | None = None,
        dormir_entre_acoes: bool = True,
    ):
        import threading

        self.projeto = projeto
        self.backend = backend
        self.cfg = dict(cfg)
        self.imagens = imagens or imagens_padrao
        self.parar = parar or threading.Event()
        self.pausar = pausar or threading.Event()
        self.ao_passo = ao_passo
        self.ao_log = ao_log
        self.ao_status = ao_status
        self.simular = bool(self.cfg.get("simular", False) if simular is None else simular)
        self.dormir_entre_acoes = dormir_entre_acoes
        self.relatorio = Relatorio()

        self.duracao_movimento = _f(self.cfg.get("duracao_movimento"), 1.2)
        self.duracao_movimento_imagem = _f(
            self.cfg.get("duracao_movimento_imagem"), 1.0
        )
        self.pausa_entre_acoes = _f(self.cfg.get("pausa_entre_acoes"), 0.3)
        self.pausa_variavel = bool(self.cfg.get("pausa_entre_acoes_variavel", True))
        self.intervalo_digitacao = _f(self.cfg.get("intervalo_digitacao"), 0.08)
        self.digitacao_variavel = bool(self.cfg.get("intervalo_digitacao_variavel", True))
        self.timeout_imagem = _f(self.cfg.get("timeout_imagem"), 15.0)
        self.confianca_imagem = _f(self.cfg.get("confianca_imagem"), 0.9)
        self.tentativas_imagem = max(1, int(_f(self.cfg.get("tentativas_imagem"), 2)))
        self.ao_falhar = str(self.cfg.get("ao_falhar", "abortar"))
        self.cinza = bool(self.cfg.get("imagem_cinza", True))

    # ------------------------------------------------------------------
    # Controle
    # ------------------------------------------------------------------
    def _checar(self) -> None:
        if self.parar.is_set():
            raise ExecucaoCancelada()
        while self.pausar.is_set():
            if self.parar.is_set():
                raise ExecucaoCancelada()
            time.sleep(0.05)

    def _log(self, texto: str, nivel: int = logging.INFO) -> None:
        LOG.log(nivel, texto)
        self.relatorio.eventos.append(texto)
        if self.ao_log:
            try:
                self.ao_log(texto)
            except Exception:
                pass

    def _status(self, texto: str) -> None:
        """Atualização curta para o HUD (não vai para o log)."""
        if self.ao_status:
            try:
                self.ao_status(texto)
            except Exception:
                pass

    def _dormir(self, segundos: float) -> None:
        final = time.monotonic() + max(0.0, float(segundos))
        while True:
            self._checar()
            restante = final - time.monotonic()
            if restante <= 0:
                return
            time.sleep(min(0.05, restante))

    # ------------------------------------------------------------------
    # Execução
    # ------------------------------------------------------------------
    def rodar(self, de: int = 0, ate: int | None = None) -> Relatorio:
        self.relatorio = Relatorio()
        total = len(self.projeto.passos)
        if total == 0:
            self.relatorio.erro = "O projeto não tem nenhum passo."
            self.relatorio.fim = datetime.now()
            return self.relatorio
        de = max(0, min(int(de), total - 1))
        fim = total - 1 if ate is None else max(de, min(int(ate), total - 1))
        self.relatorio.total = fim - de + 1

        pilha: list[dict[str, int]] = []
        indice = de
        try:
            while indice <= fim:
                passo = self.projeto.passos[indice]
                if not passo.ativo:
                    indice += 1
                    continue
                if passo.tipo == "bloco_inicio":
                    vezes = max(1, int(_f(passo.params.get("vezes"), 1)))
                    pilha.append({"inicio": indice, "feitos": 0, "vezes": vezes})
                    indice += 1
                    continue
                if passo.tipo == "bloco_fim":
                    if pilha:
                        atual = pilha[-1]
                        atual["feitos"] += 1
                        if atual["feitos"] < atual["vezes"]:
                            indice = atual["inicio"] + 1
                            continue
                        pilha.pop()
                    indice += 1
                    continue

                self._checar()
                if self.ao_passo:
                    try:
                        self.ao_passo(indice, passo)
                    except Exception:
                        pass
                self._log(f"Passo #{indice + 1}: {passo.rotulo}")
                self._status(
                    f"Passo #{indice + 1}/{len(self.projeto.passos)} — {passo.rotulo}"
                )
                try:
                    self._executar(indice, passo)
                except ExecucaoCancelada:
                    raise
                except PassoFalhou as exc:
                    if self.ao_falhar == "continuar":
                        self._log(
                            f"Passo #{indice + 1} falhou e foi ignorado: {exc.mensagem}",
                            logging.WARNING,
                        )
                        indice += 1
                        continue
                    raise
                self.relatorio.executados += 1
                if self.dormir_entre_acoes:
                    self._pausa_humana()
                indice += 1
            self.relatorio.ok = True
        except ExecucaoCancelada:
            self.relatorio.cancelado = True
            self._log("Execução cancelada pelo usuário.")
        except PassoFalhou as exc:
            self.relatorio.falha_indice = exc.indice
            self.relatorio.erro = exc.mensagem
            self.relatorio.screenshot_erro = self._capturar_erro(exc)
        except Exception as exc:  # rede de segurança
            LOG.exception("Erro inesperado no executor")
            self.relatorio.erro = f"Erro inesperado: {exc}"
            self.relatorio.screenshot_erro = self._capturar_erro(exc)
        finally:
            self.relatorio.fim = datetime.now()
        return self.relatorio

    def _pausa_humana(self) -> None:
        base = self.pausa_entre_acoes
        if base <= 0:
            return
        if self.pausa_variavel:
            self._dormir(random.uniform(base * 0.6, base * 1.5))
        else:
            self._dormir(base)

    def _capturar_erro(self, exc: Exception) -> Path | None:
        if self.simular:
            return None
        try:
            caminhos.LOGS_DIR.mkdir(parents=True, exist_ok=True)
            destino = caminhos.LOGS_DIR / f"erro_{datetime.now():%Y%m%d_%H%M%S}.png"
            tela, _ox, _oy = self.imagens.capturar_tela()
            tela.save(destino)
            self._log(f"Screenshot da falha salvo em {destino}", logging.ERROR)
            return destino
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Despacho por tipo
    # ------------------------------------------------------------------
    def _executar(self, indice: int, passo: Passo) -> None:
        metodo = getattr(self, f"_p_{passo.tipo}", None)
        if metodo is None:
            raise PassoFalhou(indice, f"Tipo de passo não suportado: {passo.tipo}")
        try:
            metodo(indice, passo.params)
        except ExecucaoCancelada:
            raise
        except PassoFalhou:
            raise
        except Exception as exc:
            raise PassoFalhou(indice, f"{type(exc).__name__}: {exc}") from exc

    def _p_comentario(self, indice: int, p: dict) -> None:
        self._log(f"# {p.get('texto', '')}")

    def _p_clicar(self, indice: int, p: dict) -> None:
        x, y = int(_f(p.get("x"))), int(_f(p.get("y")))
        if self.simular:
            self._log(f"[simulado] clicaria em ({x}, {y})")
            return
        self.backend.clicar_em(
            x,
            y,
            botao=str(p.get("botao", "left")),
            cliques=max(1, int(_f(p.get("cliques"), 1))),
            duracao=_f(p.get("duracao"), self.duracao_movimento),
        )

    def _p_mover(self, indice: int, p: dict) -> None:
        x, y = int(_f(p.get("x"))), int(_f(p.get("y")))
        if self.simular:
            self._log(f"[simulado] moveria para ({x}, {y})")
            return
        self.backend.mover(x, y, _f(p.get("duracao"), self.duracao_movimento))

    def _p_arrastar(self, indice: int, p: dict) -> None:
        x1, y1 = int(_f(p.get("x1"))), int(_f(p.get("y1")))
        x2, y2 = int(_f(p.get("x2"))), int(_f(p.get("y2")))
        if self.simular:
            self._log(f"[simulado] arrastaria ({x1}, {y1}) -> ({x2}, {y2})")
            return
        self.backend.arrastar(
            x1,
            y1,
            x2,
            y2,
            _f(p.get("duracao"), self.duracao_movimento),
            str(p.get("botao", "left")),
        )

    def _p_rolar(self, indice: int, p: dict) -> None:
        quantidade = int(_f(p.get("quantidade"), -5))
        if self.simular:
            self._log(f"[simulado] rolaria {quantidade}")
            return
        if p.get("x") is not None and p.get("y") is not None:
            self.backend.mover(int(p["x"]), int(p["y"]), 0)
            self._dormir(0.1)
        self.backend.rolar(quantidade)

    def _p_digitar(self, indice: int, p: dict) -> None:
        texto = str(p.get("texto", ""))
        intervalo = p.get("intervalo")
        base = self.intervalo_digitacao if intervalo is None else _f(
            intervalo, self.intervalo_digitacao
        )
        if self.simular:
            self._log(f"[simulado] digitaria {texto!r}")
            return
        for tipo_parte, valor in passos.dividir_texto(texto):
            if tipo_parte == "tecla":
                self._checar()
                self.backend.tecla(valor)
                if base > 0:
                    self._dormir(base)
                continue
            for posicao, letra in enumerate(valor):
                self._checar()
                self.backend.escrever(letra)
                if self.digitacao_variavel:
                    delay = random.uniform(base * 0.7, base * 1.3)
                else:
                    delay = base
                if delay > 0:
                    self._dormir(delay)
                if self.digitacao_variavel and letra in " .,;:!?":
                    self._dormir(random.uniform(0.04, 0.12))
                if (
                    self.digitacao_variavel
                    and letra == " "
                    and posicao > 0
                    and posicao % 60 == 0
                ):
                    self._dormir(random.uniform(0.2, 0.5))

    def _p_atalho(self, indice: int, p: dict) -> None:
        teclas = [str(t) for t in (p.get("teclas") or []) if str(t).strip()]
        if not teclas:
            raise PassoFalhou(indice, "Atalho sem teclas")
        if self.simular:
            self._log(f"[simulado] atalho {'+'.join(teclas)}")
            return
        self.backend.atalho(teclas)

    def _p_tecla(self, indice: int, p: dict) -> None:
        nome = str(p.get("nome", "enter"))
        repeticoes = max(1, int(_f(p.get("repeticoes"), 1)))
        if self.simular:
            self._log(f"[simulado] tecla {nome} x{repeticoes}")
            return
        self.backend.tecla(nome, repeticoes)

    def _p_pausa(self, indice: int, p: dict) -> None:
        self._dormir(_f(p.get("segundos"), 1.0))

    # ------------------------------------------------------------------
    # Imagens
    # ------------------------------------------------------------------
    def _p_imagem_clicar(self, indice: int, p: dict) -> None:
        nome = str(p.get("arquivo", ""))
        busca = self._aguardar_imagem(indice, p, clicar=True)
        if busca.centro is None:
            fallback = p.get("fallback")
            if fallback and len(fallback) >= 2:
                x, y = int(fallback[0]), int(fallback[1])
                self._log(
                    f'Imagem "{nome}" não apareceu; usando coordenada reserva '
                    f"({x}, {y})" + self._detalhe_busca(busca),
                    logging.WARNING,
                )
                if not self.simular:
                    self.backend.clicar_em(
                        x,
                        y,
                        botao=str(p.get("botao", "left")),
                        cliques=max(1, int(_f(p.get("cliques"), 1))),
                        duracao=_f(p.get("duracao"), self.duracao_movimento_imagem),
                    )
                return
            self._falha_ou_ignora(
                indice,
                f'Imagem "{nome}" não encontrada' + self._detalhe_busca(busca),
                p,
            )
            return

        x, y = busca.centro
        dx, dy = _offset(p.get("offset"))
        x, y = x + dx, y + dy
        self._log(
            f'Imagem "{nome}" encontrada em ({x}, {y}) — '
            f"score {busca.score:.2f}, {busca.segundos:.1f}s"
        )
        if self.simular:
            return
        self.backend.clicar_em(
            x,
            y,
            botao=str(p.get("botao", "left")),
            cliques=max(1, int(_f(p.get("cliques"), 1))),
            duracao=_f(p.get("duracao"), self.duracao_movimento_imagem),
        )

    def _p_imagem_esperar(self, indice: int, p: dict) -> None:
        nome = str(p.get("arquivo", "?"))
        busca = self._aguardar_imagem(indice, p, clicar=False)
        if busca.centro is None:
            self._falha_ou_ignora(
                indice,
                f'Imagem "{nome}" não apareceu' + self._detalhe_busca(busca),
                p,
            )
            return
        # Antes não havia log de sucesso: a espera ficava "muda" e parecia
        # travada mesmo quando encontrava o template.
        self._log(
            f'Imagem "{nome}" encontrada em {busca.centro} — '
            f"score {busca.score:.2f}, {busca.segundos:.1f}s"
        )

    def _p_imagem_desaparecer(self, indice: int, p: dict) -> None:
        nome = str(p.get("arquivo", ""))
        timeout = _f(p.get("timeout"), self.timeout_imagem)
        confianca = _f(p.get("confianca"), self.confianca_imagem)
        tentativas = max(1, int(_f(p.get("tentativas"), self.tentativas_imagem)))
        if not self.imagens.existe(nome):
            self._falha_ou_ignora(indice, f'Imagem "{nome}" não existe', p)
            return
        template = self.imagens.carregar(nome)
        for tentativa in range(1, tentativas + 1):
            final = time.monotonic() + timeout
            self._log(
                f'Aguardando "{nome}" desaparecer (até {timeout:.0f}s, '
                f"tentativa {tentativa}/{tentativas})"
            )
            self._status(
                f'Aguardando "{nome}" desaparecer — até {timeout:.0f}s '
                f"(tentativa {tentativa}/{tentativas})"
            )
            while time.monotonic() < final:
                self._checar()
                if self.simular:
                    self._log("[simulado] considera que desapareceu")
                    return
                tela, ox, oy = self.imagens.capturar_tela()
                if self.imagens.localizar(
                    tela, ox, oy, template, confianca, None, self.cinza
                ) is None:
                    self._log(f'"{nome}" desapareceu.')
                    self._status(f'✓ "{nome}" desapareceu')
                    return
                self._dormir(0.25)
        self._falha_ou_ignora(indice, f'Imagem "{nome}" continua na tela', p)

    def _localizar_detalhado(self, tela, ox, oy, template, confianca):
        """Compatível com imagens antigas/fakes que só têm localizar()."""
        funcao = getattr(self.imagens, "localizar_detalhado", None)
        if funcao is not None:
            resultado = funcao(
                tela, ox, oy, template, confianca, None, self.cinza
            )
            if hasattr(resultado, "centro") and hasattr(
                resultado, "melhor_score"
            ):
                return resultado
            centro = resultado if isinstance(resultado, tuple) else None
            score = 1.0 if centro else 0.0
            return imagens_padrao.ResultadoBusca(
                centro=centro,
                score=score,
                melhor_score=score,
                melhor_centro=centro,
            )

        centro = self.imagens.localizar(
            tela, ox, oy, template, confianca, None, self.cinza
        )
        score = 1.0 if centro is not None else 0.0
        return imagens_padrao.ResultadoBusca(
            centro=centro,
            score=score,
            melhor_score=score,
            melhor_centro=centro,
        )

    @staticmethod
    def _detalhe_busca(busca: BuscaImagem) -> str:
        detalhe = ""
        if busca.melhor_score > 0:
            detalhe += f" (melhor score {busca.melhor_score:.2f})"
        if busca.diagnostico:
            detalhe += f"; diagnóstico: {busca.diagnostico}"
        return detalhe

    def _aguardar_imagem(
        self, indice: int, p: dict, clicar: bool
    ) -> BuscaImagem:
        nome = str(p.get("arquivo", ""))
        if not nome:
            raise PassoFalhou(indice, "Passo de imagem sem arquivo definido")
        if not self.imagens.existe(nome):
            raise PassoFalhou(
                indice,
                f'Imagem "{nome}" não existe em {caminhos.IMAGENS_DIR}',
            )
        timeout = _f(p.get("timeout"), self.timeout_imagem)
        confianca = _f(p.get("confianca"), self.confianca_imagem)
        tentativas = max(1, int(_f(p.get("tentativas"), self.tentativas_imagem)))
        if self.simular:
            self._log(f'[simulado] esperaria "{nome}"')
            return BuscaImagem(
                centro=(0, 0),
                score=1.0,
                melhor_score=1.0,
                melhor_centro=(0, 0),
            )

        template = self.imagens.carregar(nome)
        inicio = time.monotonic()
        melhor_score = 0.0
        melhor_centro: tuple[int, int] | None = None
        ultima_tela = None
        ultimo_ox = ultimo_oy = 0
        ultimo_status = 0.0

        for tentativa in range(1, tentativas + 1):
            final = time.monotonic() + timeout
            self._log(
                f'Procurando "{nome}" por até {timeout:.0f}s '
                f"(confiança {confianca:.2f}, tentativa {tentativa}/{tentativas})"
            )
            while time.monotonic() < final:
                self._checar()
                tela, ox, oy = self.imagens.capturar_tela()
                ultima_tela, ultimo_ox, ultimo_oy = tela, ox, oy
                resultado = self._localizar_detalhado(
                    tela, ox, oy, template, confianca
                )
                if resultado.melhor_score > melhor_score:
                    melhor_score = float(resultado.melhor_score)
                    melhor_centro = resultado.melhor_centro
                if resultado.centro is not None:
                    segundos = time.monotonic() - inicio
                    self._status(
                        f'✓ "{nome}" encontrada em {resultado.centro} '
                        f"— {segundos:.1f}s"
                    )
                    return BuscaImagem(
                        centro=resultado.centro,
                        score=float(resultado.score),
                        melhor_score=melhor_score,
                        melhor_centro=melhor_centro,
                        segundos=segundos,
                    )

                agora = time.monotonic()
                if agora - ultimo_status >= 0.4:
                    self._status(
                        f'Procurando "{nome}" — {agora - inicio:.1f}s/'
                        f"{timeout:.0f}s (tentativa {tentativa}/{tentativas})"
                    )
                    ultimo_status = agora
                self._dormir(0.25)

        segundos = time.monotonic() - inicio
        busca = BuscaImagem(
            centro=None,
            score=0.0,
            melhor_score=melhor_score,
            melhor_centro=melhor_centro,
            segundos=segundos,
        )
        if melhor_score > 0:
            self._log(
                f'Melhor score para "{nome}": {melhor_score:.3f} '
                f"(confiança exigida {confianca:.2f}) em {melhor_centro}",
                logging.WARNING,
            )
        self._status(
            f'✗ "{nome}" não encontrada — melhor score {melhor_score:.2f}'
        )

        salvar = getattr(self.imagens, "salvar_diagnostico", None)
        if ultima_tela is not None and salvar is not None:
            try:
                diagnostico = salvar(
                    ultima_tela,
                    template,
                    imagens_padrao.ResultadoBusca(
                        centro=None,
                        score=0.0,
                        melhor_score=melhor_score,
                        melhor_centro=melhor_centro,
                    ),
                    nome,
                    ox=ultimo_ox,
                    oy=ultimo_oy,
                    confianca=confianca,
                )
                busca.diagnostico = diagnostico
                if diagnostico:
                    self._log(
                        f"Diagnóstico da busca salvo em {diagnostico}",
                        logging.WARNING,
                    )
            except Exception as exc:
                self._log(
                    f"Não foi possível salvar o diagnóstico da busca: {exc}",
                    logging.WARNING,
                )
        return busca

    def _falha_ou_ignora(self, indice: int, mensagem: str, p: dict) -> None:
        if str(p.get("se_falhar", self.ao_falhar)) == "continuar":
            self._log(mensagem + " (continuando)", logging.WARNING)
            return
        raise PassoFalhou(indice, mensagem)


def _f(valor: Any, padrao: float = 0.0) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return float(padrao)


def _offset(valor: Any) -> tuple[int, int]:
    try:
        return int(valor[0]), int(valor[1])
    except (TypeError, ValueError, IndexError):
        return 0, 0


def executar(
    projeto: Projeto,
    backend,
    cfg: Mapping[str, Any],
    **kwargs,
) -> Relatorio:
    """Atalho de conveniência."""
    return Executor(projeto, backend, cfg, **kwargs).rodar()
