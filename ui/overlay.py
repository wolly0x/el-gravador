"""Seleção de região na tela (overlay) — devolve coordenadas virtuais."""

from __future__ import annotations

import tkinter as tk
from typing import Callable


def selecionar_regiao(
    root: tk.Misc,
    ao_concluir: Callable[[tuple[int, int, int, int] | None], None],
) -> None:
    """Abre um overlay de seleção. O callback recebe (x, y, largura, altura)."""
    from nucleo.dpi import area_virtual

    ox, oy, largura, altura = area_virtual()

    overlay = tk.Toplevel(root)
    overlay.overrideredirect(True)
    try:
        overlay.attributes("-topmost", True)
    except tk.TclError:
        pass
    try:
        overlay.attributes("-alpha", 0.25)
    except tk.TclError:
        pass
    overlay.geometry(f"{largura}x{altura}+{ox}+{oy}")
    overlay.configure(bg="black", cursor="crosshair")

    canvas = tk.Canvas(overlay, bg="black", highlightthickness=0, cursor="crosshair")
    canvas.pack(fill=tk.BOTH, expand=True)

    canvas.create_text(
        largura // 2,
        36,
        text="Clique e arraste para marcar a região  •  ESC / botão direito cancela",
        fill="#00ff88",
        font=("Segoe UI", 14, "bold"),
    )

    estado = {"x0": None, "y0": None, "rect": None, "texto": None}
    finalizado = {"ok": False}

    def rel(event) -> tuple[int, int]:
        return event.x_root - ox, event.y_root - oy

    def ao_pressionar(event) -> None:
        if event.num == 3:  # botão direito
            finalizar(None)
            return
        estado["x0"], estado["y0"] = event.x_root, event.y_root
        x, y = rel(event)
        if estado["rect"] is not None:
            canvas.delete(estado["rect"])
        estado["rect"] = canvas.create_rectangle(
            x, y, x, y, outline="#ff0055", width=3
        )

    def ao_arrastar(event) -> None:
        if estado["rect"] is None or estado["x0"] is None:
            return
        x0, y0 = estado["x0"] - ox, estado["y0"] - oy
        x, y = rel(event)
        canvas.coords(estado["rect"], x0, y0, x, y)
        largura_sel = abs(event.x_root - estado["x0"])
        altura_sel = abs(event.y_root - estado["y0"])
        if estado["texto"] is None:
            estado["texto"] = canvas.create_text(
                x, max(12, y - 14),
                text="",
                fill="#ffffff",
                font=("Consolas", 11, "bold"),
            )
        canvas.coords(estado["texto"], x + 8, max(12, y - 12))
        canvas.itemconfigure(
            estado["texto"], text=f"{largura_sel}x{altura_sel}"
        )

    def ao_soltar(event) -> None:
        if estado["x0"] is None:
            return
        x1, y1 = estado["x0"], estado["y0"]
        x2, y2 = event.x_root, event.y_root
        esquerda, topo = min(x1, x2), min(y1, y2)
        largura_sel, altura_sel = abs(x2 - x1), abs(y2 - y1)
        if largura_sel < 8 or altura_sel < 8:
            finalizar(None)
            return
        finalizar((esquerda, topo, largura_sel, altura_sel))

    def finalizar(regiao) -> None:
        if finalizado["ok"]:
            return
        finalizado["ok"] = True
        try:
            overlay.destroy()
        except tk.TclError:
            pass
        # espera o overlay sumir antes de qualquer screenshot
        root.after(120, lambda: ao_concluir(regiao))

    canvas.bind("<ButtonPress-1>", ao_pressionar)
    canvas.bind("<B1-Motion>", ao_arrastar)
    canvas.bind("<ButtonRelease-1>", ao_soltar)
    canvas.bind("<ButtonPress-3>", lambda e: finalizar(None))
    overlay.bind("<Escape>", lambda e: finalizar(None))
    try:
        overlay.focus_force()
    except tk.TclError:
        pass
