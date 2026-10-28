"""Consciência de DPI e geometria do monitor virtual (Windows).

Sem isto, em telas com escala 125%/150% a coordenada capturada não é a
coordenada clicada — o motivo clássico de "cliquei no lugar certo no app
e o script clicou 20% deslocado".
"""

from __future__ import annotations

import sys

_habilitado = False


def habilitar_dpi() -> str:
    """Chama SetProcessDpiAwareness ANTES de criar qualquer janela."""
    global _habilitado
    if _habilitado:
        return "já habilitado"
    _habilitado = True
    if sys.platform != "win32":
        return "ignorado (não é Windows)"
    try:
        import ctypes

        try:
            # PROCESS_PER_MONITOR_DPI_AWARE = 2
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            return "per-monitor"
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
                return "system-aware"
            except Exception as exc:  # pragma: no cover - só Windows
                return f"falhou: {exc}"
    except Exception as exc:  # pragma: no cover
        return f"falhou: {exc}"


def area_virtual() -> tuple[int, int, int, int]:
    """(x, y, largura, altura) da área virtual de todos os monitores."""
    if sys.platform == "win32":
        try:
            import ctypes

            gsm = ctypes.windll.user32.GetSystemMetrics
            x = gsm(76)  # SM_XVIRTUALSCREEN
            y = gsm(77)  # SM_YVIRTUALSCREEN
            w = gsm(78)  # SM_CXVIRTUALSCREEN
            h = gsm(79)  # SM_CYVIRTUALSCREEN
            if w > 0 and h > 0:
                return int(x), int(y), int(w), int(h)
        except Exception:
            pass
    try:
        from PIL import ImageGrab

        img = ImageGrab.grab()
        return 0, 0, img.width, img.height
    except Exception:
        return 0, 0, 1920, 1080
