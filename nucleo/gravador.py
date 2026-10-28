"""Gravação automática de mouse e teclado (F9 para, F10 pausa, ESC descarta).

As chamadas de Tkinter ficam fora daqui: a UI consulta `resultado`/`ativo`
periodicamente. Nenhuma função de interface é chamada de dentro dos
listeners do pynput.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from . import passos
from .projeto import Passo

MODIFICADORES = {"ctrl", "alt", "shift", "win"}
_TECLAS_ESPECIAIS = {
    "enter", "tab", "esc", "space", "backspace", "delete", "insert", "home",
    "end", "page_up", "page_down", "up", "down", "left", "right",
    "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
    "ctrl", "ctrl_l", "ctrl_r", "alt", "alt_l", "alt_r", "shift", "shift_l",
    "shift_r", "cmd", "cmd_l", "cmd_r",
}
_NORMALIZAR = {
    "page_up": "pageup",
    "page_down": "pagedown",
    "cmd": "win",
    "cmd_l": "win",
    "cmd_r": "win",
    "ctrl_l": "ctrl",
    "ctrl_r": "ctrl",
    "alt_l": "alt",
    "alt_r": "alt",
    "shift_l": "shift",
    "shift_r": "shift",
}


@dataclass
class Evento:
    t: float
    tipo: str  # move | press | release | scroll | keydown | keyup
    x: int = 0
    y: int = 0
    botao: str = ""
    dx: int = 0
    dy: int = 0
    tecla: str | None = None  # caractere ou nome especial
    especial: bool = False
    recorte: Any = None
    meta: dict = field(default_factory=dict)


class GravadorEventos:
    def __init__(
        self,
        cfg: Mapping[str, Any],
        salvar_template: Callable[..., str] | None = None,
    ):
        self.cfg = dict(cfg)
        self.salvar_template = salvar_template
        self.ativo = False
        self.pausado = False
        self.descartado = False
        self.erro: str | None = None
        self.resultado: list[Passo] | None = None
        self.titulo_janela = ""
        self._eventos: list[Evento] = []
        self._lock = threading.Lock()
        self._inicio = 0.0
        self._mouse = None
        self._teclado = None
        self._kb = None
        self._mapa: dict[Any, str] = {}
        self._pressionadas: set[str] = set()
        self._mods: set[str] = set()
        self._ultimo_move = (0, 0, 0.0)
        self._avisos: list[str] = []

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    def iniciar(self) -> None:
        from pynput import keyboard, mouse

        self._kb = keyboard
        self.resultado = None
        self.erro = None
        self.descartado = False
        self.pausado = False
        self._eventos = []
        self._pressionadas = set()
        self._mods = set()
        self._ultimo_move = (0, 0, 0.0)
        self._avisos = []
        self._mapa = self._montar_mapa(keyboard)
        self.titulo_janela = _titulo_janela()

        self._inicio = time.monotonic()
        self.ativo = True
        self._mouse = mouse.Listener(
            on_move=self._on_move, on_click=self._on_click, on_scroll=self._on_scroll
        )
        self._teclado = keyboard.Listener(
            on_press=self._on_press, on_release=self._on_release
        )
        self._mouse.start()
        self._teclado.start()

    def _montar_mapa(self, keyboard) -> dict[Any, str]:
        mapa: dict[Any, str] = {}
        for nome in _TECLAS_ESPECIAIS:
            alvo = getattr(keyboard.Key, nome, None)
            if alvo is not None:
                mapa[alvo] = _NORMALIZAR.get(nome, nome)
        return mapa

    def parar(self, descartar: bool = False) -> None:
        if not self.ativo:
            return
        self.ativo = False
        self.descartado = bool(descartar)
        self._encerrar_listeners()
        if descartar:
            self.resultado = None
            return
        try:
            with self._lock:
                eventos = list(self._eventos)
            self.resultado = converter(
                eventos,
                self.cfg,
                titulo=self.titulo_janela,
                salvar_template=self.salvar_template,
                avisos=self._avisos,
            )
        except Exception as exc:  # pragma: no cover - defensivo
            self.erro = f"{type(exc).__name__}: {exc}"
            self.resultado = None

    def _encerrar_listeners(self) -> None:
        for listener in (self._mouse, self._teclado):
            try:
                if listener is not None:
                    listener.stop()
            except Exception:
                pass
        self._mouse = None
        self._teclado = None

    def alternar_pausa(self) -> bool:
        self.pausado = not self.pausado
        return self.pausado

    @property
    def duracao(self) -> float:
        if not self._inicio:
            return 0.0
        return time.monotonic() - self._inicio

    @property
    def total_eventos(self) -> int:
        with self._lock:
            return len(self._eventos)

    # ------------------------------------------------------------------
    # Callbacks (threads do pynput)
    # ------------------------------------------------------------------
    def _registrar(self, evento: Evento) -> None:
        if not self.ativo or self.pausado:
            return
        with self._lock:
            self._eventos.append(evento)

    def _t(self) -> float:
        return time.monotonic() - self._inicio

    def _on_move(self, x, y) -> None:
        if not self.ativo or self.pausado:
            return
        x, y = int(x), int(y)
        ultimo_x, ultimo_y, ultimo_t = self._ultimo_move
        agora = self._t()
        if abs(x - ultimo_x) + abs(y - ultimo_y) < 4 and agora - ultimo_t < 0.1:
            return
        self._ultimo_move = (x, y, agora)
        self._registrar(Evento(agora, "move", x=x, y=y))

    def _on_click(self, x, y, button, pressed) -> None:
        nome = getattr(button, "name", "left")
        recorte = None
        if pressed and self.cfg.get("registrar_recorte"):
            recorte = self._capturar_recorte(int(x), int(y))
        self._registrar(
            Evento(
                self._t(),
                "press" if pressed else "release",
                x=int(x),
                y=int(y),
                botao=nome,
                recorte=recorte,
            )
        )

    def _capturar_recorte(self, x: int, y: int):
        if self.salvar_template is None:
            return None
        try:
            from . import imagens

            largura = max(16, int(self.cfg.get("recorte_largura", 120)))
            altura = max(16, int(self.cfg.get("recorte_altura", 60)))
            tela, ox, oy = imagens.capturar_tela()
            x1 = max(ox, x - largura // 2)
            y1 = max(oy, y - altura // 2)
            x2 = min(ox + tela.width, x + largura // 2)
            y2 = min(oy + tela.height, y + altura // 2)
            img = imagens.recortar(tela, x1, y1, x2, y2, ox, oy)
            return {
                "img": img,
                "dx": x - (x1 + x2) // 2,
                "dy": y - (y1 + y2) // 2,
            }
        except Exception:
            return None

    def _on_scroll(self, x, y, dx, dy) -> None:
        self._registrar(
            Evento(self._t(), "scroll", x=int(x), y=int(y), dx=int(dx), dy=int(dy))
        )

    def _on_press(self, key) -> None:
        if key == self._kb.Key.f9:
            threading.Thread(target=self.parar, daemon=True).start()
            return
        if key == self._kb.Key.esc:
            threading.Thread(
                target=self.parar, kwargs={"descartar": True}, daemon=True
            ).start()
            return
        if key == self._kb.Key.f10:
            self.alternar_pausa()
            return

        nome, especial = self._nome_da_tecla(key)
        if nome is None:
            return
        if nome in self._pressionadas:
            return
        self._pressionadas.add(nome)
        if nome in MODIFICADORES:
            self._mods.add(nome)
            return
        self._registrar(
            Evento(self._t(), "keydown", tecla=nome, especial=especial)
        )

    def _on_release(self, key) -> None:
        nome, _especial = self._nome_da_tecla(key)
        if nome is None:
            return
        self._pressionadas.discard(nome)
        if nome in MODIFICADORES:
            self._mods.discard(nome)
            return
        self._registrar(Evento(self._t(), "keyup", tecla=nome))

    def _nome_da_tecla(self, key) -> tuple[str | None, bool]:
        especial = self._mapa.get(key)
        if especial is not None:
            return especial, True
        char = getattr(key, "char", None)
        if char is not None:
            return str(char), False
        nome = getattr(key, "name", None)
        if nome:
            return str(nome), True
        return None, False


# ----------------------------------------------------------------------
# Conversão de eventos em passos
# ----------------------------------------------------------------------
class _Estado:
    def __init__(self) -> None:
        self.itens: list[tuple[float, float, Passo]] = []
        self.buffer: list[str] = []
        self.buffer_t: float | None = None
        self.mods: set[str] = set()
        self.press: Evento | None = None
        self.pendente: dict | None = None
        self.scroll: dict | None = None
        self.mover_idx: int | None = None


def converter(
    eventos: list[Evento],
    cfg: Mapping[str, Any],
    *,
    titulo: str = "",
    salvar_template: Callable[..., str] | None = None,
    avisos: list[str] | None = None,
) -> list[Passo]:
    """Transforma eventos brutos em passos legíveis.

    Heurísticas:
      * digitação contínua vira um único passo "digitar"
      * backspace dentro da rajada corrige o texto em vez de virar passo
      * Ctrl/Alt/Win + tecla vira "atalho"
      * dois cliques próximos (<0.35s, <6px) viram um duplo clique
      * pressionar, mover e soltar vira "arrastar"
      * scroll consecutivo na mesma posição é acumulado
      * recorte opcional de 120x60 em volta do clique (fallback para coordenada)
    """
    avisos = [] if avisos is None else avisos
    est = _Estado()
    registrar_pausas = bool(cfg.get("registrar_pausas", False))
    pausa_minima = float(cfg.get("pausa_minima_registro", 1.5) or 1.5)

    def emitir(t: float, passo: Passo, t_fim: float | None = None) -> None:
        est.itens.append((t, t_fim if t_fim is not None else t, passo))
        est.mover_idx = None

    def flush_texto() -> None:
        if not est.buffer:
            est.buffer_t = None
            return
        texto = "".join(est.buffer)
        intervalo = float(cfg.get("intervalo_digitacao", 0.08) or 0.08)
        inicio = est.buffer_t or 0.0
        emitir(
            inicio,
            Passo("digitar", passos.criar("digitar", texto=texto)),
            t_fim=inicio + max(0.0, len(texto) - 1) * intervalo,
        )
        est.buffer = []
        est.buffer_t = None

    def _emitir_pendente() -> None:
        if est.pendente is None:
            return
        pend = est.pendente
        est.pendente = None
        recorte = pend.get("recorte")
        if recorte and salvar_template is not None:
            try:
                nome = salvar_template(
                    recorte["img"],
                    (titulo or "clique") + "_clique",
                    meta={
                        "janela": titulo,
                        "regiao": [pend["x"], pend["y"], recorte["img"].width,
                                   recorte["img"].height],
                    },
                )
                params = passos.criar(
                    "imagem_clicar",
                    arquivo=nome,
                    timeout=cfg.get("timeout_imagem", 15),
                    confianca=cfg.get("confianca_imagem", 0.9),
                    tentativas=cfg.get("tentativas_imagem", 2),
                    se_falhar="abortar",
                    offset=[recorte.get("dx", 0), recorte.get("dy", 0)],
                    fallback=[pend["x"], pend["y"]],
                )
                emitir(pend["t"], Passo("imagem_clicar", params))
                return
            except Exception as exc:
                avisos.append(f"Recorte do clique não salvo: {exc}")
        params = passos.criar(
            "clicar", x=pend["x"], y=pend["y"],
            botao=pend["botao"], cliques=pend["cliques"],
        )
        emitir(pend["t"], Passo("clicar", params))

    def flush_pendente(t: float) -> None:
        if est.pendente is None:
            return
        if t - est.pendente["t"] >= 0.35:
            _emitir_pendente()

    def emitir_scroll(dados: dict) -> None:
        emitir(
            dados["t"],
            Passo(
                "rolar",
                passos.criar(
                    "rolar",
                    quantidade=int(dados["quantidade"]),
                    x=dados.get("x"),
                    y=dados.get("y"),
                ),
            ),
        )

    for ev in eventos:
        if ev.tipo == "press":
            flush_pendente(ev.t)
            flush_texto()
            est.press = ev
            continue

        if ev.tipo == "release":
            if est.press is None or est.press.botao != ev.botao:
                continue
            inicio = est.press
            distancia = math.hypot(ev.x - inicio.x, ev.y - inicio.y)
            duracao = max(0.0, ev.t - inicio.t)
            est.press = None
            if distancia > 10 and duracao > 0.12:
                flush_texto()
                _emitir_pendente()
                emitir(
                    inicio.t,
                    Passo(
                        "arrastar",
                        passos.criar(
                            "arrastar",
                            x1=inicio.x,
                            y1=inicio.y,
                            x2=ev.x,
                            y2=ev.y,
                            duracao=round(min(2.0, max(0.3, duracao)), 2),
                            botao=inicio.botao,
                        ),
                    ),
                )
                continue

            if (
                est.pendente is not None
                and est.pendente["botao"] == inicio.botao
                and 0 <= (ev.t - est.pendente["t"]) <= 0.35
                and math.hypot(ev.x - est.pendente["x"], ev.y - est.pendente["y"]) <= 6
            ):
                est.pendente["cliques"] = 2
                _emitir_pendente()
            else:
                _emitir_pendente()
                est.pendente = {
                    "t": inicio.t,
                    "x": ev.x,
                    "y": ev.y,
                    "botao": inicio.botao,
                    "cliques": 1,
                    "recorte": inicio.recorte,
                }
            continue

        if ev.tipo == "scroll":
            flush_texto()
            if (
                est.scroll is not None
                and ev.t - est.scroll["t"] <= 0.3
                and est.scroll.get("x") == ev.x
                and est.scroll.get("y") == ev.y
            ):
                est.scroll["quantidade"] += ev.dy
                est.scroll["t"] = ev.t
            else:
                if est.scroll is not None:
                    emitir_scroll(est.scroll)
                est.scroll = {
                    "t": ev.t,
                    "x": ev.x,
                    "y": ev.y,
                    "quantidade": ev.dy,
                }
            continue

        if ev.tipo == "keydown":
            flush_pendente(ev.t)
            nome = ev.tecla or ""
            if not ev.especial:
                if est.mods & {"ctrl", "alt", "win"}:
                    flush_texto()
                    combinacao = sorted(est.mods, key=_ordem_mod) + [nome.lower()]
                    emitir(ev.t, Passo("atalho", passos.criar("atalho", teclas=combinacao)))
                else:
                    if est.buffer_t is None:
                        est.buffer_t = ev.t
                    est.buffer.append(nome)
                continue

            if nome in MODIFICADORES:
                est.mods.add(nome)
                continue
            if nome == "space":
                if est.buffer_t is None:
                    est.buffer_t = ev.t
                est.buffer.append(" ")
                continue
            if nome == "backspace":
                if est.buffer:
                    est.buffer.pop()
                    if not est.buffer:
                        est.buffer_t = None
                    continue
                flush_texto()
                emitir(ev.t, Passo("tecla", passos.criar("tecla", nome="backspace")))
                continue
            flush_texto()
            emitir(ev.t, Passo("tecla", passos.criar("tecla", nome=nome)))
            continue

        if ev.tipo == "keyup":
            nome = ev.tecla or ""
            if nome in MODIFICADORES:
                est.mods.discard(nome)
            continue

        if ev.tipo == "move":
            if not cfg.get("registrar_movimento") or est.press is not None:
                continue
            if (
                est.mover_idx is not None
                and est.mover_idx == len(est.itens) - 1
                and (ev.t - est.itens[-1][1]) < 1.0
            ):
                t0, _tf, passo = est.itens[-1]
                passo.params["x"] = ev.x
                passo.params["y"] = ev.y
                est.itens[-1] = (t0, ev.t, passo)
            else:
                emitir(
                    ev.t,
                    Passo(
                        "mover",
                        passos.criar(
                            "mover",
                            x=ev.x,
                            y=ev.y,
                            duracao=float(cfg.get("duracao_movimento", 1.2) or 1.2),
                        ),
                    ),
                )
                est.mover_idx = len(est.itens) - 1
            continue

    flush_texto()
    _emitir_pendente()
    if est.scroll is not None:
        emitir_scroll(est.scroll)

    itens = sorted(est.itens, key=lambda item: item[0])
    if not registrar_pausas:
        return [passo for _t, _tf, passo in itens]

    saida: list[Passo] = []
    anterior_fim = None
    for t, t_fim, passo in itens:
        if anterior_fim is not None and t - anterior_fim >= pausa_minima:
            saida.append(
                Passo("pausa", passos.criar("pausa", segundos=round(t - anterior_fim, 1)))
            )
        saida.append(passo)
        anterior_fim = t_fim
    return saida


def _ordem_mod(nome: str) -> int:
    ordem = {"ctrl": 0, "alt": 1, "shift": 2, "win": 3}
    return ordem.get(nome, 9)


def _titulo_janela() -> str:
    try:
        import ctypes

        user32 = ctypes.windll.user32
        handle = user32.GetForegroundWindow()
        tamanho = user32.GetWindowTextLengthW(handle)
        buffer = ctypes.create_unicode_buffer(tamanho + 1)
        user32.GetWindowTextW(handle, buffer, tamanho + 1)
        return buffer.value.strip()
    except Exception:
        return ""
