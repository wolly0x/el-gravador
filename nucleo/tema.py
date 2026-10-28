"""Temas, fontes e escala da interface.

Além das cores históricas (``c_bg``, ``c_current`` ...), cada tema agora
expõe alguns tokens extras usados pelos componentes no estilo Apple Glass.
Os temas antigos continuam funcionando: os tokens que não existem no preset
são derivados automaticamente.
"""

from __future__ import annotations

TEMAS: dict[str, dict[str, str]] = {
    "Dark": {
        "c_bg": "#1a1b26",
        "c_current": "#24283b",
        "c_action": "#2f3549",
        "c_fg": "#c0caf5",
        "c_comment": "#565f89",
        "c_cyan": "#7dcfff",
        "c_green": "#9ece6a",
        "c_orange": "#ff9e64",
        "c_pink": "#bb9af7",
        "c_red": "#f7768e",
    },
    "Light": {
        "c_bg": "#f8f9fa",
        "c_current": "#e9ecef",
        "c_action": "#dee2e6",
        "c_fg": "#212529",
        "c_comment": "#6c757d",
        "c_cyan": "#0d6efd",
        "c_green": "#198754",
        "c_orange": "#fd7e14",
        "c_pink": "#0d6efd",
        "c_red": "#dc3545",
    },
    "Monokai Pro": {
        "c_bg": "#2d2a2e",
        "c_current": "#403e41",
        "c_action": "#524f52",
        "c_fg": "#fcfcfa",
        "c_comment": "#727072",
        "c_cyan": "#78dce8",
        "c_green": "#a9dc76",
        "c_orange": "#fc9867",
        "c_pink": "#ff6188",
        "c_red": "#fc5d7c",
    },
    "Apple Glass": {
        "c_bg": "#F5F5F7",
        "c_current": "#F0F0F4",
        "c_action": "#E8E8ED",
        "c_fg": "#1D1D1F",
        "c_comment": "#63636B",
        "c_cyan": "#0066D6",
        "c_green": "#1E7F3C",
        "c_orange": "#B25E00",
        "c_pink": "#7B3FE4",
        "c_red": "#C6281E",
        # Tokens de superfície / vidro.
        "c_surface": "#FFFFFF",
        "c_surface_alt": "#F0F0F5",
        "c_surface_3": "#E8E8ED",
        "c_border": "#D0D0D8",
        "c_border_strong": "#B9B9C3",
        "c_hover": "#EDEDF2",
        "c_pressed": "#E2E2E8",
        "c_selection": "#E5F0FF",
        "c_shadow": "#D2D2DB",
        "c_accent": "#0066D6",
        "c_accent_hover": "#2F86E8",
        "c_accent_soft": "#E3EFFF",
        "c_on_accent": "#FFFFFF",
        "c_glass": "#FBFBFD",
        "c_glass_border": "#FFFFFF",
        "c_glass_hi": "#FFFFFF",
        "c_track": "#D1D1D6",
        "c_knob": "#FFFFFF",
        "c_toolbar": "#F0F0F4",
        "c_card": "#FFFFFF",
        "c_success": "#1E7F3C",
        "c_warning": "#B25E00",
        "c_danger": "#C6281E",
        "c_text_sub": "#48484D",
        "c_chroma": "#010203",
    },
    "Apple Glass Dark": {
        "c_bg": "#0B0B0F",
        "c_current": "#16161C",
        "c_action": "#22222A",
        "c_fg": "#F5F5F7",
        "c_comment": "#A1A1A6",
        "c_cyan": "#0A84FF",
        "c_green": "#30D158",
        "c_orange": "#FF9F0A",
        "c_pink": "#0A84FF",
        "c_red": "#FF453A",
        "c_surface": "#141419",
        "c_surface_alt": "#1C1C22",
        "c_surface_3": "#26262E",
        "c_border": "#2C2C34",
        "c_border_strong": "#3A3A44",
        "c_hover": "#202028",
        "c_pressed": "#2A2A33",
        "c_selection": "#123A5C",
        "c_shadow": "#050508",
        "c_accent": "#0A84FF",
        "c_accent_hover": "#409CFF",
        "c_accent_soft": "#12283F",
        "c_on_accent": "#FFFFFF",
        "c_glass": "#17171D",
        "c_glass_border": "#2C2C34",
        "c_glass_hi": "#2A2A33",
        "c_track": "#3A3A44",
        "c_knob": "#F5F5F7",
        "c_toolbar": "#121217",
        "c_card": "#141419",
        "c_success": "#30D158",
        "c_warning": "#FF9F0A",
        "c_danger": "#FF453A",
        "c_text_sub": "#A1A1A6",
        "c_chroma": "#010203",
    },
}

# Cores históricas: continuam sendo as únicas exibidas no seletor de cores
# da tela de configurações, para não transformar a paleta em uma parede de
# quadradinhos.
CORES = tuple(TEMAS["Dark"].keys())

_TEMAS_APPLE = ("Apple Glass", "Apple Glass Dark")


# ----------------------------------------------------------------------
# Utilidades de cor
# ----------------------------------------------------------------------
def _rgb(cor: str) -> tuple[int, int, int]:
    cor = cor.lstrip("#")
    if len(cor) == 3:
        cor = "".join(c * 2 for c in cor)
    return int(cor[0:2], 16), int(cor[2:4], 16), int(cor[4:6], 16)


def _hex(r: float, g: float, b: float) -> str:
    return "#%02x%02x%02x" % (
        max(0, min(255, int(round(r)))),
        max(0, min(255, int(round(g)))),
        max(0, min(255, int(round(b)))),
    )


def misturar(a: str, b: str, fator: float) -> str:
    """Mistura ``a`` com ``b``; 0 = a, 1 = b."""
    fator = max(0.0, min(1.0, float(fator)))
    ar, ag, ab = _rgb(a)
    br, bg, bb = _rgb(b)
    return _hex(
        ar + (br - ar) * fator,
        ag + (bg - ag) * fator,
        ab + (bb - ab) * fator,
    )


def luminancia(cor: str) -> float:
    r, g, b = _rgb(cor)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def contraste(cor: str) -> str:
    """Texto legível sobre a cor informada."""
    return "#101014" if luminancia(cor) > 0.58 else "#FFFFFF"


def _completar(base: dict[str, str]) -> dict[str, str]:
    """Deriva tokens novos para os temas antigos."""
    b = dict(base)
    escuro = luminancia(b.get("c_bg", "#000000")) < 0.5
    b.setdefault("c_surface", b.get("c_current", b["c_bg"]))
    b.setdefault("c_surface_alt", b.get("c_action", b["c_current"]))
    b.setdefault("c_surface_3", misturar(b["c_surface"], b["c_fg"], 0.10))
    b.setdefault("c_border", misturar(b["c_bg"], b["c_fg"], 0.18))
    b.setdefault("c_border_strong", misturar(b["c_bg"], b["c_fg"], 0.32))
    b.setdefault("c_hover", misturar(b["c_surface"], b["c_fg"], 0.09))
    b.setdefault("c_pressed", misturar(b["c_surface"], b["c_fg"], 0.16))
    b.setdefault("c_selection", misturar(b["c_bg"], b.get("c_cyan", b["c_fg"]), 0.18))
    b.setdefault("c_shadow", misturar(b["c_bg"], "#000000", 0.24))
    b.setdefault("c_accent", b.get("c_cyan", b["c_fg"]))
    b.setdefault("c_accent_hover", misturar(b["c_accent"], "#FFFFFF", 0.16))
    b.setdefault("c_accent_soft", misturar(b["c_bg"], b["c_accent"], 0.16))
    b.setdefault("c_on_accent", contraste(b["c_accent"]))
    b.setdefault("c_glass", b["c_surface"])
    b.setdefault("c_glass_border", b["c_border"])
    b.setdefault("c_glass_hi", misturar(b["c_surface"], "#FFFFFF", 0.28))
    b.setdefault("c_track", misturar(b["c_bg"], b["c_fg"], 0.22))
    b.setdefault("c_knob", "#FFFFFF" if escuro else "#FFFFFF")
    b.setdefault("c_toolbar", b.get("c_current", b["c_bg"]))
    b.setdefault("c_card", b["c_surface"])
    b.setdefault("c_success", b.get("c_green", b["c_fg"]))
    b.setdefault("c_warning", b.get("c_orange", b["c_fg"]))
    b.setdefault("c_danger", b.get("c_red", b["c_fg"]))
    b.setdefault("c_text_sub", b.get("c_comment", b["c_fg"]))
    b.setdefault("c_chroma", "#010203")
    return b


def paleta(nome: str, customizadas: dict[str, str] | None = None) -> dict[str, str]:
    """Cores do tema, permitindo sobrescritas do usuário."""
    base = _completar(dict(TEMAS.get(nome, TEMAS["Dark"])))
    if customizadas:
        for chave, valor in customizadas.items():
            if chave in base and isinstance(valor, str) and valor.startswith("#"):
                base[chave] = valor
    return base


def eh_apple(nome: str) -> bool:
    return nome in _TEMAS_APPLE


def fonte(cfg: dict) -> str:
    return str(cfg.get("fonte", "Segoe UI"))


def tamanho(cfg: dict) -> int:
    base = int(cfg.get("tamanho_fonte", 9))
    zoom = float(cfg.get("fator_zoom", 1.0))
    return max(6, int(round(base * zoom)))
