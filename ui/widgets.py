"""Pequenos componentes visuais usados pelo tema Apple Glass.

O Tkinter não consegue arredondar bordas de widgets nativos nem aplicar blur
por widget. Estes componentes desenham o fundo em um Canvas e colocam o
conteúdo real por cima, criando o efeito de vidro/cartão sem depender de
bibliotecas de UI externas.
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import font as tkfont
from typing import Any, Callable

from nucleo import tema as tema_mod


# ----------------------------------------------------------------------
# Geometria
# ----------------------------------------------------------------------
def _pontos_arredondados(
    x1: float, y1: float, x2: float, y2: float, r: float
) -> list[float]:
    r = max(0.0, min(r, (x2 - x1) / 2.0, (y2 - y1) / 2.0))
    return [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]


def _fundo(pai, paleta: dict, padrao: str | None = None) -> str:
    if padrao:
        return padrao
    try:
        cor = pai.cget("bg")
        if isinstance(cor, str) and cor:
            return cor
    except Exception:
        pass
    return paleta.get("c_bg", "#000000")


def _luminancia(cor: str) -> float:
    return tema_mod.luminancia(cor)


def aplicar_borda_windows(janela, escuro: bool = True) -> None:
    """Ativa cantos arredondados e barra de título escura no Windows 11.

    Em Windows 10 ou em versões antigas do DWM as chamadas simplesmente
    falham e são ignoradas; a janela continua com a barra nativa normal.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.GetParent.argtypes = [wintypes.HWND]
        user32.GetParent.restype = wintypes.HWND
        hwnd = user32.GetParent(janela.winfo_id()) or janela.winfo_id()
        dwm = ctypes.windll.dwmapi
        dwm.DwmSetWindowAttribute.argtypes = [
            wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
        ]
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long
        valor = ctypes.c_int(1 if escuro else 0)
        try:
            resultado = dwm.DwmSetWindowAttribute(
                hwnd, 20, ctypes.byref(valor), ctypes.sizeof(valor)
            )
            if resultado != 0:
                # Windows 10 usa o atributo 19 em vez do 20.
                dwm.DwmSetWindowAttribute(
                    hwnd, 19, ctypes.byref(valor), ctypes.sizeof(valor)
                )
        except Exception:
            pass
        try:
            canto = ctypes.c_int(2)  # DWMWCP_ROUND
            dwm.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(canto), ctypes.sizeof(canto)
            )
        except Exception:
            pass
    except Exception:
        pass


def arredondar_janela(janela, raio: int = 18) -> None:
    """Recorta uma janela sem moldura em um retângulo arredondado no Windows."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        user32.GetParent.argtypes = [wintypes.HWND]
        user32.GetParent.restype = wintypes.HWND
        gdi32.CreateRoundRectRgn.argtypes = [
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int,
        ]
        gdi32.CreateRoundRectRgn.restype = wintypes.HRGN
        user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
        user32.SetWindowRgn.restype = ctypes.c_int
        gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        gdi32.DeleteObject.restype = wintypes.BOOL
        hwnd = user32.GetParent(janela.winfo_id()) or janela.winfo_id()
        largura = max(1, janela.winfo_width())
        altura = max(1, janela.winfo_height())
        regiao = gdi32.CreateRoundRectRgn(0, 0, largura + 1, altura + 1, raio, raio)
        if regiao and user32.SetWindowRgn(hwnd, regiao, True) == 0:
            gdi32.DeleteObject(regiao)
    except Exception:
        pass


# ----------------------------------------------------------------------
# Botão arredondado
# ----------------------------------------------------------------------
class BotaoVidro(tk.Canvas):
    """Botão desenhado em Canvas, com estados hover/pressed/disabled."""

    def __init__(
        self,
        pai,
        texto: str = "",
        comando: Callable | None = None,
        *,
        paleta: dict,
        fonte: str = "Segoe UI",
        tamanho: int = 9,
        cor: str | None = None,
        fg: str | None = None,
        largura: int | None = None,
        altura: int = 30,
        raio: int | None = None,
        destaque: bool = False,
        fundo: str | None = None,
        alinhamento: str = "center",
        padding: int = 12,
        estado: str = tk.NORMAL,
    ):
        self.paleta = paleta
        self.fonte = fonte
        self.tamanho = tamanho
        self._texto = texto
        self._comando = comando
        self._cor_base = cor or paleta.get("c_surface_alt", "#eeeeee")
        self._fg_base = fg or (
            tema_mod.contraste(self._cor_base) if destaque else paleta.get("c_fg", "#111111")
        )
        self._destaque = destaque
        self._alinhamento = alinhamento
        self._padding = padding
        self._raio = raio
        self._estado = estado
        self._hover = False
        self._pressionado = False
        self._fundo = _fundo(pai, paleta, fundo)
        self._req_altura = max(20, int(altura))

        fnt = tkfont.Font(family=fonte, size=tamanho, weight="bold" if destaque else "normal")
        largura_texto = fnt.measure(texto) if texto else 0
        if largura:
            largura_px = max(int(largura) * 7, largura_texto + padding * 2)
            self._largura_fixa = True
        else:
            largura_px = max(48, largura_texto + padding * 2)
            self._largura_fixa = False
        self._req_largura = largura_px

        super().__init__(
            pai,
            bg=self._fundo,
            width=largura_px,
            height=self._req_altura,
            bd=0,
            highlightthickness=0,
            takefocus=0,
            cursor="hand2" if estado != tk.DISABLED else "arrow",
        )

        self.bind("<Configure>", lambda _e: self._redesenhar())
        self.bind("<Enter>", self._entrar)
        self.bind("<Leave>", self._sair)
        self.bind("<ButtonPress-1>", self._pressionar)
        self.bind("<ButtonRelease-1>", self._soltar)
        self.after_idle(self._redesenhar)

    # ------------------------------------------------------------------
    @property
    def _cor_atual(self) -> str:
        if self._estado == tk.DISABLED:
            return self.paleta.get("c_surface_alt", self._cor_base)
        if self._pressionado:
            return tema_mod.misturar(self._cor_base, "#000000", 0.12)
        if self._hover:
            if _luminancia(self._cor_base) < 0.45:
                return tema_mod.misturar(self._cor_base, "#FFFFFF", 0.10)
            return tema_mod.misturar(self._cor_base, "#000000", 0.05)
        return self._cor_base

    @property
    def _fg_atual(self) -> str:
        if self._estado == tk.DISABLED:
            return self.paleta.get("c_comment", "#888888")
        return self._fg_base

    def _redesenhar(self) -> None:
        try:
            w = max(1, self.winfo_width())
            h = max(1, self.winfo_height())
            if w <= 2:
                w = self._req_largura
            if h <= 2:
                h = self._req_altura
            self.delete("all")
            r = self._raio if self._raio is not None else min(10, h // 2)
            x1, y1, x2, y2 = 1.0, 1.0, w - 1.0, h - 1.0
            pontos = _pontos_arredondados(x1, y1, x2, y2, r)
            self.create_polygon(
                pontos, smooth=True, splinesteps=24,
                fill=self._cor_atual, outline="", width=0,
            )
            borda = self.paleta.get("c_border", "#cccccc")
            if self._destaque and self._estado != tk.DISABLED:
                borda = tema_mod.misturar(self._cor_base, "#FFFFFF", 0.35)
            self.create_polygon(
                pontos, smooth=True, splinesteps=24,
                fill="", outline=borda, width=1,
            )
            if self._estado != tk.DISABLED:
                self.create_line(
                    x1 + r, y1 + 1.0, x2 - r, y1 + 1.0,
                    fill=tema_mod.misturar(self._cor_atual, "#FFFFFF", 0.28),
                    width=1,
                )
            if self._texto:
                if self._alinhamento == "w":
                    x = self._padding
                    anchor = "w"
                else:
                    x = w / 2
                    anchor = "center"
                self.create_text(
                    x, h / 2,
                    text=self._texto,
                    fill=self._fg_atual,
                    anchor=anchor,
                    font=(self.fonte, self.tamanho, "bold" if self._destaque else "normal"),
                )
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    def _entrar(self, _event=None) -> None:
        if self._estado == tk.DISABLED:
            return
        self._hover = True
        self._redesenhar()

    def _sair(self, _event=None) -> None:
        self._hover = False
        self._pressionado = False
        self._redesenhar()

    def _pressionar(self, _event=None) -> None:
        if self._estado == tk.DISABLED:
            return
        self._pressionado = True
        self._redesenhar()

    def _soltar(self, event=None) -> None:
        if self._estado == tk.DISABLED:
            return
        dentro = True
        if event is not None:
            dentro = 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()
        self._pressionado = False
        self._redesenhar()
        if dentro and self._comando is not None:
            try:
                self._comando()
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    def invoke(self) -> None:
        if self._estado != tk.DISABLED and self._comando is not None:
            self._comando()

    def configure(self, cnf: Any = None, **kw: Any) -> None:
        atualizou = False
        if isinstance(cnf, dict):
            kw = {**cnf, **kw}
        elif cnf is not None:
            return super().configure(cnf)
        if "state" in kw:
            self._estado = kw.pop("state")
            try:
                super().configure(cursor="arrow" if self._estado == tk.DISABLED else "hand2")
            except tk.TclError:
                pass
            atualizou = True
        if "text" in kw:
            self._texto = str(kw.pop("text"))
            if not getattr(self, "_largura_fixa", False):
                fnt = tkfont.Font(
                    family=self.fonte, size=self.tamanho,
                    weight="bold" if self._destaque else "normal",
                )
                self._req_largura = max(48, fnt.measure(self._texto) + self._padding * 2)
                try:
                    super().configure(width=self._req_largura)
                except tk.TclError:
                    pass
            atualizou = True
        if "bg" in kw:
            self._cor_base = kw.pop("bg")
            atualizou = True
        elif "background" in kw:
            self._cor_base = kw.pop("background")
            atualizou = True
        if "fg" in kw:
            self._fg_base = kw.pop("fg")
            atualizou = True
        elif "foreground" in kw:
            self._fg_base = kw.pop("foreground")
            atualizou = True
        if "command" in kw:
            self._comando = kw.pop("command")
        if "width" in kw:
            try:
                self._req_largura = max(1, int(kw.pop("width")))
            except (TypeError, ValueError):
                kw.pop("width", None)
        if "height" in kw:
            try:
                self._req_altura = max(1, int(kw.pop("height")))
            except (TypeError, ValueError):
                kw.pop("height", None)
        if kw:
            super().configure(**kw)
        if atualizou or not kw:
            self._redesenhar()

    config = configure


# ----------------------------------------------------------------------
# Entrada de texto com moldura arredondada
# ----------------------------------------------------------------------
class EntradaVidro(tk.Frame):
    def __init__(
        self,
        pai,
        *,
        paleta: dict,
        fonte: str = "Segoe UI",
        tamanho: int = 9,
        valor: str = "",
        largura: int = 12,
        fundo: str | None = None,
        var: tk.StringVar | None = None,
        altura: int = 30,
    ):
        self.paleta = paleta
        self._fundo = _fundo(pai, paleta, fundo)
        self._altura = max(24, altura)
        super().__init__(pai, bg=self._fundo, highlightthickness=0, bd=0)
        self.var = var or tk.StringVar(value=str(valor))
        self.canvas = tk.Canvas(
            self, bg=self._fundo, highlightthickness=0, bd=0,
            height=self._altura, width=max(60, int(largura) * 7),
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.entry = tk.Entry(
            self.canvas,
            textvariable=self.var,
            bg=paleta.get("c_surface_alt", "#ffffff"),
            fg=paleta.get("c_fg", "#111111"),
            insertbackground=paleta.get("c_fg", "#111111"),
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
            font=(fonte, tamanho),
        )
        self._win = self.canvas.create_window(
            9, self._altura // 2,
            window=self.entry, anchor="w",
            width=max(20, self.canvas.winfo_reqwidth() - 18),
        )
        self.canvas.bind("<Configure>", self._reconfigurar)
        self.entry.bind("<FocusIn>", lambda _e: self._redesenhar(True))
        self.entry.bind("<FocusOut>", lambda _e: self._redesenhar(False))
        self.after_idle(self._reconfigurar)

    def _reconfigurar(self, _event=None) -> None:
        try:
            w = self.canvas.winfo_width()
            h = self.canvas.winfo_height()
            if w <= 2:
                w = self.canvas.winfo_reqwidth()
            if h <= 2:
                h = self._altura
            self.canvas.coords(self._win, 9, h // 2)
            self.canvas.itemconfigure(self._win, width=max(20, w - 18))
            self._redesenhar(bool(self.entry.focus_get() is self.entry))
        except tk.TclError:
            pass

    def _redesenhar(self, focado: bool = False) -> None:
        try:
            w = max(1, self.canvas.winfo_width())
            h = max(1, self.canvas.winfo_height())
            self.canvas.delete("fundo")
            pontos = _pontos_arredondados(1, 1, w - 1, h - 1, min(9, h // 2))
            self.canvas.create_polygon(
                pontos, smooth=True, splinesteps=24,
                fill=self.paleta.get("c_surface_alt", "#ffffff"),
                outline=self.paleta.get("c_accent", "#007aff") if focado
                else self.paleta.get("c_border", "#cccccc"),
                width=1, tags="fundo",
            )
            self.canvas.tag_lower("fundo")
        except tk.TclError:
            pass

    def get(self) -> str:
        return self.var.get()

    def set(self, valor: Any) -> None:
        self.var.set(str(valor))

    def bind(self, sequencia: str, func=None, add: str | None = None):
        return self.entry.bind(sequencia, func, add) if func is not None else self.entry.bind(sequencia)

    def focus_set(self) -> None:
        self.entry.focus_set()

    def configure(self, cnf: Any = None, **kw: Any) -> None:
        if "state" in kw:
            self.entry.configure(state=kw.pop("state"))
        if kw:
            super().configure(**kw)

    config = configure


# ----------------------------------------------------------------------
# Switch
# ----------------------------------------------------------------------
class Switch(tk.Frame):
    def __init__(
        self,
        pai,
        *,
        paleta: dict,
        var: tk.BooleanVar,
        comando: Callable | None = None,
        texto: str | None = None,
        fonte: str = "Segoe UI",
        tamanho: int = 9,
        fundo: str | None = None,
        largura: int = 38,
        altura: int = 22,
        estado: str = tk.NORMAL,
    ):
        self.paleta = paleta
        self.var = var
        self.comando = comando
        self._estado = estado
        self._fundo = _fundo(pai, paleta, fundo)
        self._largura = max(30, largura)
        self._altura = max(18, altura)
        super().__init__(pai, bg=self._fundo, highlightthickness=0, bd=0)
        self._label = None
        if texto:
            self._label = tk.Label(
                self,
                text=texto,
                bg=self._fundo,
                fg=paleta.get("c_fg", "#111111"),
                font=(fonte, tamanho),
                anchor="w",
                cursor="hand2" if estado != tk.DISABLED else "arrow",
            )
            self._label.pack(side=tk.LEFT, padx=(0, 10))
            self._label.bind("<Button-1>", self._alternar)
        self.canvas = tk.Canvas(
            self, bg=self._fundo, width=self._largura + 8,
            height=self._altura + 8, bd=0, highlightthickness=0,
            cursor="hand2" if estado != tk.DISABLED else "arrow",
        )
        self.canvas.pack(side=tk.LEFT)
        self.canvas.bind("<Button-1>", self._alternar)
        try:
            self._trace = self.var.trace_add("write", lambda *_a: self._desenhar())
        except Exception:
            self._trace = None
        self.after_idle(self._desenhar)

    def _alternar(self, _event=None) -> None:
        if self._estado == tk.DISABLED:
            return
        self.var.set(not bool(self.var.get()))
        if self.comando is not None:
            try:
                self.comando()
            except tk.TclError:
                pass

    def _desenhar(self) -> None:
        try:
            self.canvas.delete("all")
            w, h = self._largura, self._altura
            ativo = bool(self.var.get())
            trilha = (
                self.paleta.get("c_accent", "#007aff") if ativo
                else self.paleta.get("c_track", "#cccccc")
            )
            if self._estado == tk.DISABLED:
                trilha = self.paleta.get("c_surface_3", trilha)
            pontos = _pontos_arredondados(4, 4, 4 + w, 4 + h, h / 2)
            self.canvas.create_polygon(
                pontos, smooth=True, splinesteps=24, fill=trilha, outline="",
            )
            raio = h / 2 - 3
            cx = 4 + h / 2 + (w - h) if ativo else 4 + h / 2
            cy = 4 + h / 2
            self.canvas.create_oval(
                cx - raio, cy - raio, cx + raio, cy + raio,
                fill=self.paleta.get("c_knob", "#ffffff"), outline="",
            )
        except tk.TclError:
            pass

    def configure(self, cnf: Any = None, **kw: Any) -> None:
        if "state" in kw:
            self._estado = kw.pop("state")
            try:
                self.canvas.configure(cursor="arrow" if self._estado == tk.DISABLED else "hand2")
                if self._label:
                    self._label.configure(cursor="arrow" if self._estado == tk.DISABLED else "hand2")
            except tk.TclError:
                pass
            self._desenhar()
        if kw:
            super().configure(**kw)

    config = configure

    def get(self) -> bool:
        return bool(self.var.get())

    def set(self, valor: Any) -> None:
        self.var.set(bool(valor))


# ----------------------------------------------------------------------
# Segmented control
# ----------------------------------------------------------------------
class SegmentedControl(tk.Frame):
    def __init__(
        self,
        pai,
        itens: list[str],
        *,
        paleta: dict,
        fonte: str = "Segoe UI",
        tamanho: int = 9,
        ao_mudar: Callable[[int], None] | None = None,
        fundo: str | None = None,
    ):
        self.paleta = paleta
        self.fonte = fonte
        self.tamanho = tamanho
        self.ao_mudar = ao_mudar
        self._fundo = _fundo(pai, paleta, fundo)
        self._selecionado = 0
        super().__init__(pai, bg=self._fundo, highlightthickness=0, bd=0)
        self._caixa = tk.Frame(self, bg=self._fundo)
        self._caixa.pack()
        self.botoes: list[BotaoVidro] = []
        for i, texto in enumerate(itens):
            botao = BotaoVidro(
                self._caixa,
                texto=texto,
                comando=lambda idx=i: self.selecionar(idx),
                paleta=paleta,
                fonte=fonte,
                tamanho=tamanho,
                altura=28,
                raio=8,
                padding=14,
                fundo=self._fundo,
                cor=paleta.get("c_surface_alt", "#eeeeee"),
                fg=paleta.get("c_fg", "#111111"),
            )
            botao.pack(side=tk.LEFT, padx=1, pady=2)
            self.botoes.append(botao)
        self.selecionar(0, notificar=False)

    def selecionar(self, indice: int, notificar: bool = True) -> None:
        if not self.botoes:
            return
        indice = max(0, min(indice, len(self.botoes) - 1))
        self._selecionado = indice
        for i, botao in enumerate(self.botoes):
            if i == indice:
                botao.configure(
                    bg=self.paleta.get("c_surface", "#ffffff"),
                    fg=self.paleta.get("c_accent", "#007aff"),
                )
            else:
                botao.configure(
                    bg=self.paleta.get("c_surface_alt", "#eeeeee"),
                    fg=self.paleta.get("c_comment", "#666666"),
                )
        if notificar and self.ao_mudar is not None:
            self.ao_mudar(indice)

    def index(self) -> int:
        return self._selecionado

    def select(self, indice: int) -> None:
        self.selecionar(indice)


# ----------------------------------------------------------------------
# Cartão de vidro
# ----------------------------------------------------------------------
class Cartao(tk.Frame):
    """Frame com fundo arredondado, borda e sombra simulada."""

    def __init__(
        self,
        pai,
        *,
        paleta: dict,
        fundo: str | None = None,
        bg: str | None = None,
        raio: int = 16,
        padding: int = 12,
        sombra: bool = True,
        expandir: bool = False,
        altura_auto: bool = False,
    ):
        self.paleta = paleta
        self._fundo = _fundo(pai, paleta, fundo)
        self._bg = bg or paleta.get("c_surface", "#ffffff")
        self.raio = raio
        self.padding = padding
        self.sombra = sombra
        self.expandir = expandir
        self.altura_auto = altura_auto
        self._altura_calculada = 0
        super().__init__(pai, bg=self._fundo, highlightthickness=0, bd=0)
        self.canvas = tk.Canvas(self, bg=self._fundo, highlightthickness=0, bd=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.conteudo = tk.Frame(self.canvas, bg=self._bg)
        self._win = self.canvas.create_window(
            padding, padding, window=self.conteudo, anchor="nw",
        )
        self.canvas.bind("<Configure>", self._reconfigurar)
        self.conteudo.bind("<Configure>", self._conteudo_alterado)
        self.after_idle(self._reconfigurar)
        if self.altura_auto:
            self.after_idle(self._conteudo_alterado)

    def _conteudo_alterado(self, _event=None) -> None:
        if not self.altura_auto:
            return
        try:
            h = max(1, self.conteudo.winfo_reqheight() + self.padding * 2)
            if h != self._altura_calculada:
                self._altura_calculada = h
                self.canvas.configure(height=h)
                self._desenhar()
        except tk.TclError:
            pass

    def _reconfigurar(self, _event=None) -> None:
        try:
            w = self.canvas.winfo_width()
            h = self.canvas.winfo_height()
            if w <= 2:
                w = self.canvas.winfo_reqwidth()
            if h <= 2:
                h = self.canvas.winfo_reqheight()
            self.canvas.coords(self._win, self.padding, self.padding)
            self.canvas.itemconfigure(self._win, width=max(20, w - self.padding * 2))
            if self.expandir:
                self.canvas.itemconfigure(self._win, height=max(20, h - self.padding * 2))
            self._desenhar()
        except tk.TclError:
            pass

    def _desenhar(self) -> None:
        try:
            w = max(2, self.canvas.winfo_width())
            h = max(2, self.canvas.winfo_height())
            if self.altura_auto and self._altura_calculada:
                h = max(h, self._altura_calculada)
            self.canvas.delete("vidro")
            if self.sombra:
                cor_sombra = tema_mod.misturar(
                    self._fundo, self.paleta.get("c_shadow", "#000000"), 0.55
                )
                pontos_sombra = _pontos_arredondados(
                    3, 4, w - 3, h - 1, self.raio
                )
                self.canvas.create_polygon(
                    pontos_sombra, smooth=True, splinesteps=24,
                    fill=cor_sombra, outline="", tags="vidro",
                )
            pontos = _pontos_arredondados(1, 1, w - 3, h - 3, self.raio)
            self.canvas.create_polygon(
                pontos, smooth=True, splinesteps=24,
                fill=self._bg,
                outline=self.paleta.get("c_glass_border", self.paleta.get("c_border", "#cccccc")),
                width=1, tags="vidro",
            )
            # Realce especular no topo.
            self.canvas.create_line(
                1 + self.raio, 2,
                w - 3 - self.raio, 2,
                fill=tema_mod.misturar(self._bg, "#FFFFFF", 0.42),
                width=1, tags="vidro",
            )
            self.canvas.tag_lower("vidro")
        except tk.TclError:
            pass
