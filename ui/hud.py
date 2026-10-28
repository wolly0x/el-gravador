"""HUD flutuante mostrado durante a execução.

A janela principal fica escondida para não cobrir o alvo. Este HUD é a única
forma de o usuário ver em que passo a execução está e quanto falta para a
busca de imagem desistir.

Ele é semitransparente (janela layered) e é posicionado no canto oposto ao
template atual, para não atrapalhar a captura de tela.
"""

from __future__ import annotations

import sys
import tkinter as tk

from nucleo.dpi import area_virtual


class Hud:
    def __init__(self, root: tk.Misc, cfg: dict, fonte: str, tamanho: int, cores: dict):
        self.root = root
        self.cfg = cfg
        self.fonte = fonte
        self.tamanho = tamanho
        self.cores = cores
        self.largura = 480
        self.altura = 92
        self.janela: tk.Toplevel | None = None
        self._texto: tk.Label | None = None

    # ------------------------------------------------------------------
    def mostrar(self, texto: str = "Iniciando…") -> None:
        self.esconder()
        try:
            self.janela = tk.Toplevel(self.root)
            janela = self.janela
            # Cria escondido e só mostra depois de aplicar WS_EX_NOACTIVATE:
            # assim o HUD não rouba o foco de quem está sendo automatizado.
            janela.withdraw()
            janela.overrideredirect(True)
            fundo = self.cores.get("c_surface", "#141419")
            janela.configure(bg=self.cores.get("c_border", "#2c2c34"))
            try:
                janela.attributes("-topmost", True)
            except tk.TclError:
                pass
            try:
                # Layered: o Pillow geralmente não captura janelas layered,
                # e a transparência deixa o HUD menos intrusivo.
                janela.attributes("-alpha", 0.94)
            except tk.TclError:
                pass
            janela.geometry(f"{self.largura}x{self.altura}")

            faixa = tk.Frame(
                janela,
                bg=self.cores.get("c_accent", "#0a84ff"),
                width=4,
            )
            faixa.pack(side=tk.LEFT, fill=tk.Y)

            corpo = tk.Frame(janela, bg=fundo)
            corpo.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=12, pady=8)

            topo = tk.Frame(corpo, bg=fundo)
            topo.pack(fill=tk.X)
            tk.Label(
                topo,
                text="●",
                bg=fundo,
                fg=self.cores.get("c_accent", "#0a84ff"),
                font=(self.fonte, max(7, self.tamanho), "bold"),
            ).pack(side=tk.LEFT, padx=(0, 6))
            tk.Label(
                topo,
                text="El Gravador 18 Pro Max",
                bg=fundo,
                fg=self.cores.get("c_fg", "#ffffff"),
                font=(self.fonte, max(7, self.tamanho), "bold"),
                anchor="w",
            ).pack(side=tk.LEFT)
            tk.Label(
                topo,
                text="executando",
                bg=fundo,
                fg=self.cores.get("c_text_sub", "#a1a1a6"),
                font=(self.fonte, max(6, self.tamanho - 1)),
                anchor="e",
            ).pack(side=tk.RIGHT)

            self._texto = tk.Label(
                corpo,
                text=texto,
                bg=fundo,
                fg=self.cores.get("c_fg", "#ffffff"),
                font=(self.fonte, max(7, self.tamanho)),
                anchor="w",
                justify="left",
                wraplength=self.largura - 46,
            )
            self._texto.pack(fill=tk.X, pady=(4, 1))

            tk.Label(
                corpo,
                text="ESC parar   •   F8 pausar",
                bg=fundo,
                fg=self.cores.get("c_text_sub", "#a1a1a6"),
                font=(self.fonte, max(6, self.tamanho - 1)),
                anchor="w",
            ).pack(fill=tk.X)

            self._posicionar(None)
            self._nao_ativar()
            try:
                janela.deiconify()
                janela.lift()
                janela.update_idletasks()
                self._arredondar()
                # Reaplica depois do deiconify: o Tk pode tentar ativar a
                # janela ao mostrá-la.
                self._nao_ativar()
            except tk.TclError:
                pass
        except Exception:
            self.esconder()

    def reexibir(self) -> None:
        """Reexibe depois que a janela principal é escondida."""
        if self.janela is None:
            return
        try:
            self.janela.deiconify()
            self.janela.lift()
            self._nao_ativar()
        except tk.TclError:
            pass

    def atualizar(self, texto: str) -> None:
        if self._texto is None:
            return
        try:
            self._texto.configure(text=texto)
        except tk.TclError:
            pass

    def posicionar_para(self, regiao: tuple[int, int, int, int] | None) -> None:
        if self.janela is None:
            return
        self._posicionar(regiao)

    @staticmethod
    def _area_monitor(x: int, y: int) -> tuple[int, int, int, int] | None:
        """Área útil do monitor que contém o ponto (Windows)."""
        if sys.platform != "win32":
            return None
        try:
            import ctypes
            from ctypes import wintypes

            class Rect(ctypes.Structure):
                _fields_ = [
                    ("left", wintypes.LONG),
                    ("top", wintypes.LONG),
                    ("right", wintypes.LONG),
                    ("bottom", wintypes.LONG),
                ]

            class MonitorInfo(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("rcMonitor", Rect),
                    ("rcWork", Rect),
                    ("dwFlags", wintypes.DWORD),
                ]

            user32 = ctypes.windll.user32
            user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
            user32.MonitorFromPoint.restype = wintypes.HANDLE
            user32.GetMonitorInfoW.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(MonitorInfo),
            ]
            user32.GetMonitorInfoW.restype = wintypes.BOOL

            ponto = wintypes.POINT(int(x), int(y))
            monitor = user32.MonitorFromPoint(
                ponto, 2  # MONITOR_DEFAULTTONEAREST
            )
            info = MonitorInfo()
            info.cbSize = ctypes.sizeof(MonitorInfo)
            if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                area = info.rcWork
                return (
                    area.left,
                    area.top,
                    area.right - area.left,
                    area.bottom - area.top,
                )
        except Exception:
            pass
        return None

    def _posicionar(self, regiao: tuple[int, int, int, int] | None) -> None:
        if self.janela is None:
            return

        # Prefere o mesmo monitor do template, para o HUD ficar visível.
        area = None
        if regiao:
            rx, ry, rw, rh = regiao
            area = self._area_monitor(int(rx + rw / 2), int(ry + rh / 2))
        if area is None:
            try:
                area = area_virtual()
            except Exception:
                area = (0, 0, 1920, 1080)
        vx, vy, vw, vh = area

        margem = 18
        # Coloca no lado oposto ao template.
        direita = True
        baixo = True
        if regiao:
            rx, ry, rw, rh = regiao
            direita = (rx + rw / 2) < (vx + vw / 2)
            baixo = (ry + rh / 2) < (vy + vh / 2)

        largura = min(self.largura, max(240, vw - margem * 2))
        altura = min(self.altura, max(60, vh - margem * 2))
        x = vx + vw - largura - margem if direita else vx + margem
        y = vy + vh - altura - margem if baixo else vy + margem
        try:
            self.janela.geometry(f"{largura}x{altura}+{int(x)}+{int(y)}")
            self._arredondar()
        except tk.TclError:
            pass

    def _arredondar(self) -> None:
        """Recorta a janela do HUD em um retângulo arredondado (Windows)."""
        if sys.platform != "win32" or self.janela is None:
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
            hwnd = user32.GetParent(self.janela.winfo_id()) or self.janela.winfo_id()
            largura = self.janela.winfo_width()
            altura = self.janela.winfo_height()
            if largura <= 2 or altura <= 2:
                largura = self.largura
                altura = self.altura
            regiao = gdi32.CreateRoundRectRgn(0, 0, largura + 1, altura + 1, 18, 18)
            if regiao:
                if user32.SetWindowRgn(hwnd, regiao, True) == 0:
                    gdi32.DeleteObject(regiao)
        except Exception:
            pass

    def _nao_ativar(self) -> None:
        """Evita que o HUD roube o foco do app que está sendo automatizado."""
        if sys.platform != "win32" or self.janela is None:
            return
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            user32.GetParent.argtypes = [wintypes.HWND]
            user32.GetParent.restype = wintypes.HWND
            user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.GetWindowLongW.restype = ctypes.c_long
            user32.SetWindowLongW.argtypes = [
                wintypes.HWND,
                ctypes.c_int,
                ctypes.c_long,
            ]
            user32.SetWindowLongW.restype = ctypes.c_long
            user32.SetWindowPos.argtypes = [
                wintypes.HWND,
                wintypes.HWND,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                wintypes.UINT,
            ]
            user32.SetWindowPos.restype = wintypes.BOOL

            hwnd = user32.GetParent(self.janela.winfo_id())
            if not hwnd:
                hwnd = self.janela.winfo_id()
            gwl_exstyle = -20
            ws_ex_noactivate = 0x08000000
            ws_ex_toolwindow = 0x00000080
            ws_ex_transparent = 0x00000020  # click-through
            estilo = int(user32.GetWindowLongW(hwnd, gwl_exstyle))
            novo = (
                estilo
                | ws_ex_noactivate
                | ws_ex_toolwindow
                | ws_ex_transparent
            )
            user32.SetWindowLongW(hwnd, gwl_exstyle, ctypes.c_long(novo))
            # SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_FRAMECHANGED
            user32.SetWindowPos(
                hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0020
            )
        except Exception:
            pass

    def esconder(self) -> None:
        if self.janela is not None:
            try:
                self.janela.destroy()
            except tk.TclError:
                pass
        self.janela = None
        self._texto = None
