"""Janela PyWebView + ponte para o processo de backend Tk.

O processo principal roda o loop do WebView2 no thread principal (exigência
do pywebview).  O backend, em outro processo, mantém o Tk escondido e expõe
as operações por HTTP em 127.0.0.1, sempre protegido por um token aleatório.
"""

from __future__ import annotations

import json
import os
import queue
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from nucleo import caminhos

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "ui_web" / "index.html"
MAIN = ROOT / "main.py"


def _slug(nome: str) -> str:
    nome = str(nome or "projeto").strip().lower()
    nome = re.sub(r"[^a-z0-9._-]+", "_", nome, flags=re.UNICODE)
    return nome.strip("._-") or "projeto"


def _geometria_inicial() -> dict[str, int]:
    """Janela compacta e centralizada na área útil da tela.

    O padrão é 1140x740, sem ocupar a tela inteira. Em telas pequenas
    encolhe até o mínimo usável (1020x680). Em outros sistemas mantém o
    mesmo tamanho-base para não depender de APIs nativas.
    """
    largura, altura = 1140, 740
    if sys.platform != "win32":
        return {"width": largura, "height": altura}

    x = y = 0
    try:
        import ctypes
        from ctypes import wintypes

        class _Rect(ctypes.Structure):
            _fields_ = [
                ("left", wintypes.LONG),
                ("top", wintypes.LONG),
                ("right", wintypes.LONG),
                ("bottom", wintypes.LONG),
            ]

        area = _Rect()
        # SPI_GETWORKAREA = 48 (desconta a barra de tarefas)
        if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(area), 0):
            disp_w = max(1, int(area.right - area.left))
            disp_h = max(1, int(area.bottom - area.top))
            x, y = int(area.left), int(area.top)
            # Deixa uma margem confortável e nunca abre em tela cheia.
            largura = min(1140, max(1020, disp_w - 120))
            altura = min(740, max(680, disp_h - 120))
            x += max(0, (disp_w - largura) // 2)
            y += max(0, (disp_h - altura) // 2)
    except Exception:
        pass
    return {"width": largura, "height": altura, "x": x, "y": y}


class BackendProcess:
    def __init__(self, projeto: Path | None = None, sem_logs: bool = False):
        self.proc: subprocess.Popen[str] | None = None
        self.porta: int | None = None
        self.token: str | None = None
        self._linhas: "queue.Queue[str]" = queue.Queue()
        self._saida: list[str] = []
        self._parar = threading.Event()
        self._pronto = False
        self._ready_path: Path | None = (
            Path(tempfile.gettempdir())
            / f"elgravador2_{os.getpid()}_{secrets.token_hex(6)}.json"
        )

        if getattr(sys, "frozen", False):
            comando = [sys.executable, "--backend"]
        else:
            comando = [sys.executable, str(MAIN), "--backend"]
        comando.extend(["--ready-file", str(self._ready_path)])
        if projeto:
            comando.extend(["--projeto", str(projeto)])
        if sem_logs:
            comando.append("--sem-logs")

        env = dict(os.environ)
        env.setdefault("PYTHONUNBUFFERED", "1")
        self.proc = subprocess.Popen(
            comando,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
        )
        if self.proc.stdout is not None:
            threading.Thread(target=self._ler_saida, daemon=True).start()
        self._aguardar_pronto()

    def _ler_saida(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        for linha in self.proc.stdout:
            linha = linha.rstrip("\r\n")
            self._saida.append(linha)
            if len(self._saida) > 200:
                del self._saida[:100]
            if not self._pronto:
                self._linhas.put(linha)
        self._parar.set()

    def _ler_pronto(self) -> bool:
        caminho = self._ready_path
        if caminho is None:
            return False
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
            porta = int(dados["porta"])
            token = str(dados["token"])
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return False
        if not token:
            return False
        self.porta = porta
        self.token = token
        self._pronto = True
        try:
            caminho.unlink(missing_ok=True)
        except OSError:
            pass
        return True

    def _aguardar_pronto(self) -> None:
        limite = time.monotonic() + 25
        while time.monotonic() < limite:
            if self._ler_pronto():
                return
            try:
                linha = self._linhas.get(timeout=0.1)
            except queue.Empty:
                if self.proc is not None and self.proc.poll() is not None:
                    # O processo pode ter gravado o arquivo e encerrado em
                    # seguida; tenta uma última leitura antes de desistir.
                    if self._ler_pronto():
                        return
                    break
                continue
            if linha.startswith("READY "):
                partes = linha.split()
                if len(partes) >= 3:
                    self.porta = int(partes[1])
                    self.token = partes[2]
                    self._pronto = True
                    return
            if linha.startswith("ERRO"):
                break
        restante = "\n".join(self._saida[-12:])
        self.parar(forcar=True)
        raise RuntimeError(
            "Não foi possível iniciar o processo de automação.\n"
            + (restante or "O backend encerrou sem detalhes.")
        )

    @property
    def url(self) -> str:
        if self.porta is None:
            raise RuntimeError("Backend não iniciado.")
        return f"http://127.0.0.1:{self.porta}/api"

    def requisitar(
        self, comando: str, args: dict | None = None, timeout: float = 60
    ) -> dict[str, Any]:
        if self.token is None:
            return {"ok": False, "erro": "Backend não iniciado."}
        corpo = json.dumps(
            {"comando": comando, "args": args or {}}, ensure_ascii=False
        ).encode("utf-8")
        pedido = urllib.request.Request(
            self.url,
            data=corpo,
            method="POST",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-Token": self.token,
            },
        )
        try:
            with urllib.request.urlopen(pedido, timeout=timeout) as resposta:
                dados = json.loads(resposta.read().decode("utf-8"))
            return dados if isinstance(dados, dict) else {
                "ok": False,
                "erro": "Resposta inválida do backend.",
            }
        except urllib.error.URLError as exc:
            return {"ok": False, "erro": f"Backend indisponível: {exc}"}
        except Exception as exc:
            return {"ok": False, "erro": f"{type(exc).__name__}: {exc}"}

    def parar(self, forcar: bool = False) -> None:
        if self.proc is None:
            return
        if self.proc.poll() is None:
            if not forcar:
                try:
                    self.requisitar("stop_execution", timeout=2)
                    self.requisitar("stop_recording", timeout=4)
                    self.requisitar("shutdown", timeout=2)
                except Exception:
                    pass
                try:
                    self.proc.wait(timeout=2.5)
                except subprocess.TimeoutExpired:
                    pass
            if self.proc.poll() is None:
                try:
                    self.proc.terminate()
                    self.proc.wait(timeout=1.5)
                except Exception:
                    try:
                        self.proc.kill()
                    except Exception:
                        pass
        self.proc = None
        if self._ready_path is not None:
            try:
                self._ready_path.unlink(missing_ok=True)
            except OSError:
                pass


class Api:
    def __init__(self, backend: BackendProcess):
        self._backend = backend
        self._window = None
        self._oculta = False
        self._lock = threading.RLock()
        self._fechar_autorizado = False
        self._fechar_pendente = False

    # ------------------------------------------------------------------
    # Ponte básica
    # ------------------------------------------------------------------
    def state(self) -> dict:
        return self._backend.requisitar("state", timeout=12)

    def call(self, comando: str, args: dict | None = None, timeout: float = 60) -> dict:
        return self._backend.requisitar(comando, args, timeout=timeout)

    def backend_command(self, comando: str, args: dict | None = None) -> dict:
        return self.call(comando, args)

    # ------------------------------------------------------------------
    # Janela
    # ------------------------------------------------------------------
    def _hide(self) -> None:
        with self._lock:
            if self._window is None or self._oculta:
                return
            try:
                self._window.hide()
                self._oculta = True
            except Exception:
                pass

    def _show(self) -> None:
        with self._lock:
            if self._window is None:
                return
            try:
                self._window.show()
                self._window.restore()
            except Exception:
                try:
                    self._window.show()
                except Exception:
                    pass
            self._oculta = False

    def hide_window(self) -> dict:
        self._hide()
        return {"ok": True}

    def show_window(self) -> dict:
        self._show()
        return {"ok": True}

    def quit_app(self) -> dict:
        self._fechar_autorizado = True
        self._show()
        try:
            self.call("stop_execution", timeout=2)
            self.call("stop_recording", timeout=3)
            self.call("shutdown", timeout=2)
        except Exception:
            pass
        if self._window is not None:
            try:
                self._window.destroy()
            except Exception:
                pass
        return {"ok": True}

    def cancelar_fechamento(self) -> dict:
        """Cancela um pedido de fechamento iniciado pelo botão X."""
        self._fechar_pendente = False
        self._fechar_autorizado = False
        return {"ok": True}

    def ao_fechar(self) -> bool:
        """Pergunta ao JavaScript se há alterações antes de fechar a janela.

        O evento ``closing`` do PyWebView é síncrono. Cancelamos o fechamento
        nativo e deixamos a interface web executar o mesmo fluxo usado pelo
        menu Sair (salvar/descartar/cancelar). Se a página ainda não estiver
        pronta, permite o fechamento normal.
        """
        if self._fechar_autorizado:
            return True
        if self._fechar_pendente:
            return False
        if self._window is None:
            return True
        self._fechar_pendente = True
        try:
            pronto = self._window.evaluate_js(
                "typeof window.__elgravadorSolicitarFechamento === 'function'"
            )
            if not pronto:
                self._fechar_pendente = False
                return True
            self._window.evaluate_js("window.__elgravadorSolicitarFechamento()")
        except Exception:
            self._fechar_pendente = False
            return True
        return False

    # ------------------------------------------------------------------
    # Diálogos nativos
    # ------------------------------------------------------------------
    def _dialogo(
        self, tipo: int, *, diretorio: str = "", nome: str = "", tipos=()
    ) -> str | None:
        if self._window is None:
            return None
        try:
            resultado = self._window.create_file_dialog(
                tipo,
                directory=diretorio,
                allow_multiple=False,
                save_filename=nome,
                file_types=tipos,
            )
        except Exception:
            return None
        if not resultado:
            return None
        if isinstance(resultado, (list, tuple)):
            return str(resultado[0]) if resultado else None
        return str(resultado)

    def open_project_dialog(self) -> dict:
        import webview

        caminho = self._dialogo(
            webview.FileDialog.OPEN,
            diretorio=str(caminhos.PROJETOS_DIR),
            tipos=("Projeto El Gravador (*.json)", "Todos (*.*)"),
        )
        return {"caminho": caminho}

    def save_project_dialog(self, nome: str = "projeto") -> dict:
        import webview

        caminho = self._dialogo(
            webview.FileDialog.SAVE,
            diretorio=str(caminhos.PROJETOS_DIR),
            nome=f"{_slug(nome)}.json",
            tipos=("Projeto El Gravador (*.json)",),
        )
        return {"caminho": caminho}

    def open_script_dialog(self) -> dict:
        import webview

        caminho = self._dialogo(
            webview.FileDialog.OPEN,
            diretorio=str(caminhos.BASE_DIR.parent),
            tipos=("Script Python (*.py)", "Todos (*.*)"),
        )
        return {"caminho": caminho}

    def save_script_dialog(self, nome: str = "automacao") -> dict:
        import webview

        caminho = self._dialogo(
            webview.FileDialog.SAVE,
            diretorio=str(caminhos.PROJETOS_DIR),
            nome=f"{_slug(nome)}.py",
            tipos=("Script Python (*.py)",),
        )
        return {"caminho": caminho}

    def folder_dialog(self, titulo: str = "Escolher pasta") -> dict:
        import webview

        caminho = self._dialogo(
            webview.FileDialog.FOLDER,
            diretorio=str(caminhos.PROJETOS_DIR),
        )
        return {"caminho": caminho, "titulo": titulo}

    # ------------------------------------------------------------------
    # Capturas
    # ------------------------------------------------------------------
    def capture_point(self) -> dict:
        self._hide()
        try:
            time.sleep(0.25)
            return self.call("capture_point", timeout=900)
        finally:
            self._show()

    def capture_region(self, nome: str = "regiao") -> dict:
        self._hide()
        try:
            time.sleep(0.3)
            return self.call("capture_region", {"nome": nome}, timeout=900)
        finally:
            self._show()

    def test_template(self, nome: str, confianca: float = 0.9) -> dict:
        self._hide()
        try:
            time.sleep(0.35)
            return self.call(
                "test_template", {"nome": nome, "confianca": confianca}, timeout=120
            )
        finally:
            self._show()

    # ------------------------------------------------------------------
    # Gravação / execução
    # ------------------------------------------------------------------
    def start_recording(self) -> dict:
        resposta = self.call("start_recording", timeout=30)
        if resposta.get("ok"):
            self._hide()
            threading.Thread(target=self._acompanhar_gravacao, daemon=True).start()
        return resposta

    def start_execution(self, modo: str = "tudo", indice: int | None = None) -> dict:
        resposta = self.call(
            "execute",
            {"modo": modo, "indice": indice if indice is not None else -1},
            timeout=30,
        )
        if resposta.get("ok"):
            dados = resposta.get("data") or {}
            if not dados.get("simular"):
                # Esconde imediatamente: a contagem regressiva e o HUD nativo
                # já são exibidos pelo processo Tk durante a execução.
                self._hide()
                threading.Thread(
                    target=self._acompanhar_execucao,
                    daemon=True,
                ).start()
        return resposta

    def _acompanhar_gravacao(self) -> None:
        while True:
            time.sleep(0.35)
            resposta = self.state()
            if not resposta.get("ok"):
                break
            estado = resposta.get("data") or {}
            if not estado.get("gravando"):
                break
        self._show()

    def _acompanhar_execucao(self) -> None:
        while True:
            time.sleep(0.3)
            resposta = self.state()
            if not resposta.get("ok"):
                break
            estado = resposta.get("data") or {}
            if not estado.get("executando"):
                break
        self._show()


def iniciar(cfg, projeto=None, sem_logs: bool = False) -> None:
    try:
        import webview
    except ImportError as exc:  # pragma: no cover - depende da instalação
        raise RuntimeError(
            "PyWebView não está instalado. Instale com: pip install pywebview"
        ) from exc

    if not INDEX.exists():
        raise RuntimeError(f"Interface web não encontrada em {INDEX}")

    backend = BackendProcess(
        Path(projeto.caminho) if projeto and projeto.caminho else None,
        sem_logs=sem_logs,
    )
    api = Api(backend)
    try:
        try:
            fundo = cfg.paleta().get("c_bg", "#0B0B0F")
        except Exception:
            fundo = "#0B0B0F"
        window = webview.create_window(
            "El Gravador 18 Pro Max",
            str(INDEX),
            js_api=api,
            **(_geometria_inicial()),
            min_size=(1020, 680),
            resizable=True,
            background_color=fundo,
            text_select=True,
        )
        api._window = window
        try:
            window.events.closing += api.ao_fechar
        except Exception:
            pass
        try:
            webview.start(http_server=True, debug=False)
        finally:
            backend.parar()
    finally:
        backend.parar()
