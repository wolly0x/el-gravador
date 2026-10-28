"""Tipos de passo: rótulo para a UI e emissão de código para o script gerado.

Cada tipo vive em um único lugar. Para criar um tipo novo basta registrar
um `TipoPasso` aqui (e implementar `_p_<tipo>` no executor).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

TECLAS_VALIDAS = [
    "enter", "tab", "esc", "space", "backspace", "delete", "insert",
    "home", "end", "pageup", "pagedown", "up", "down", "left", "right",
    "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
    "ctrl", "alt", "shift", "win", "printscreen", "apps",
]
for _letra in "abcdefghijklmnopqrstuvwxyz0123456789":
    TECLAS_VALIDAS.append(_letra)

# Nomes amigáveis aceitos dentro de { } no texto digitado.
ALIAS_TECLAS = {
    "return": "enter",
    "escape": "esc",
    "del": "delete",
    "pgup": "pageup",
    "pgdn": "pagedown",
    "windows": "win",
    "print_screen": "printscreen",
    "prtsc": "printscreen",
}
_TOKENS_TEXTO = set(TECLAS_VALIDAS) | set(ALIAS_TECLAS)
_PADRAO_TOKEN = re.compile(r"\{([A-Za-z0-9_]+)\}")


def dividir_texto(texto: str) -> list[tuple[str, str]]:
    """Divide o texto em partes digitáveis e teclas especiais.

    ``"oi{ENTER}!"`` -> ``[("texto", "oi"), ("tecla", "enter"), ("texto", "!")]``.
    Chaves não reconhecidas permanecem como texto literal.
    """
    texto = str(texto)
    partes: list[tuple[str, str]] = []
    posicao = 0
    for achado in _PADRAO_TOKEN.finditer(texto):
        nome = achado.group(1).lower()
        if nome not in _TOKENS_TEXTO:
            continue
        if achado.start() > posicao:
            partes.append(("texto", texto[posicao:achado.start()]))
        partes.append(("tecla", ALIAS_TECLAS.get(nome, nome)))
        posicao = achado.end()
    if posicao < len(texto):
        partes.append(("texto", texto[posicao:]))
    return partes


@dataclass(frozen=True)
class Contexto:
    """Valores fixos usados na geração de código."""

    timeout_imagem: float = 15
    confianca_imagem: float = 0.9
    tentativas_imagem: int = 2


@dataclass(frozen=True)
class TipoPasso:
    nome: str
    titulo: str
    rotulo: Callable[[dict], str]
    emitir: Callable[[dict, Contexto], list[str]]
    padrao: Callable[[], dict] = field(default=lambda: {})
    categoria: str = "ação"


# ----------------------------------------------------------------------
# Helpers de emissão
# ----------------------------------------------------------------------
def _num(valor: Any, padrao: float = 0.0) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return padrao


def _seg(valor: Any, padrao: float = 1.0) -> str:
    """Número formatado sem casas decimais desnecessárias."""
    numero = _num(valor, padrao)
    texto = f"{numero:.3f}".rstrip("0").rstrip(".")
    return texto or "0"


def _coords(params: dict) -> tuple[int, int]:
    return int(_num(params.get("x"))), int(_num(params.get("y")))


# ----------------------------------------------------------------------
# Rótulos
# ----------------------------------------------------------------------
def _rotulo_clicar(p: dict) -> str:
    x, y = _coords(p)
    cliques = int(_num(p.get("cliques"), 1))
    botao = p.get("botao", "left")
    if botao == "right":
        acao = "Clique direito"
    elif cliques >= 2:
        acao = "Duplo clique"
    else:
        acao = "Clicar"
    return f"{acao} em ({x}, {y})"


def _rotulo_mover(p: dict) -> str:
    x, y = _coords(p)
    return f"Mover cursor para ({x}, {y})"


def _rotulo_arrastar(p: dict) -> str:
    x1, y1 = int(_num(p.get("x1"))), int(_num(p.get("y1")))
    x2, y2 = int(_num(p.get("x2"))), int(_num(p.get("y2")))
    return f"Arrastar de ({x1}, {y1}) até ({x2}, {y2})"


def _rotulo_rolar(p: dict) -> str:
    q = int(_num(p.get("quantidade"), -5))
    direcao = "para cima" if q > 0 else ("para baixo" if q < 0 else "nenhuma")
    if p.get("x") is not None and p.get("y") is not None:
        return f"Rolar {direcao} ({abs(q)}x) em ({int(p['x'])}, {int(p['y'])})"
    return f"Rolar {direcao} ({abs(q)}x)"


def _rotulo_digitar(p: dict) -> str:
    texto = str(p.get("texto", ""))
    resumo = texto.replace("\n", " ").replace("\r", " ")
    if len(resumo) > 42:
        resumo = resumo[:42] + "…"
    return f'Digitar texto: "{resumo}"'


def _rotulo_atalho(p: dict) -> str:
    teclas = p.get("teclas") or []
    return "Atalho: " + "+".join(str(t) for t in teclas)


def _rotulo_tecla(p: dict) -> str:
    nome = p.get("nome", "enter")
    rep = int(_num(p.get("repeticoes"), 1))
    sufixo = f" ({rep}x)" if rep > 1 else ""
    return f"Pressionar tecla [{str(nome).upper()}]{sufixo}"


def _rotulo_pausa(p: dict) -> str:
    return f"Pausar por {_seg(p.get('segundos'), 1.0)}s"


def _rotulo_img_clicar(p: dict) -> str:
    alvo = p.get("offset") or [0, 0]
    extra = f" offset ({alvo[0]}, {alvo[1]})" if alvo != [0, 0] else ""
    return f'Aguardar imagem "{p.get("arquivo", "?")}" e clicar{extra}'


def _rotulo_img_esperar(p: dict) -> str:
    return f'Aguardar imagem "{p.get("arquivo", "?")}" aparecer'


def _rotulo_img_desaparecer(p: dict) -> str:
    return f'Aguardar imagem "{p.get("arquivo", "?")}" desaparecer'


def _rotulo_bloco_ini(p: dict) -> str:
    vezes = int(_num(p.get("vezes"), 1))
    nota = str(p.get("nota") or "").strip()
    base = f"INÍCIO do bloco repetido {vezes}x"
    return f"{base} — {nota}" if nota else base


def _rotulo_comentario(p: dict) -> str:
    texto = str(p.get("texto", "")).replace("\n", " ")
    return f"# {texto[:60]}"


# ----------------------------------------------------------------------
# Emissores de código
# ----------------------------------------------------------------------
def _emitir_clicar(p: dict, ctx: Contexto) -> list[str]:
    x, y = _coords(p)
    dur = _seg(p.get("duracao"), 1.2)
    cliques = max(1, int(_num(p.get("cliques"), 1)))
    botao = p.get("botao", "left")
    intervalo = 0.05
    return [
        f"pyautogui.moveTo({x}, {y}, duration={dur}, tween=pyautogui.easeInOutQuad)",
        f"pyautogui.click(clicks={cliques}, interval={intervalo}, button={botao!r})",
    ]


def _emitir_mover(p: dict, ctx: Contexto) -> list[str]:
    x, y = _coords(p)
    return [f"pyautogui.moveTo({x}, {y}, duration={_seg(p.get('duracao'), 1.2)}, "
            f"tween=pyautogui.easeInOutQuad)"]


def _emitir_arrastar(p: dict, ctx: Contexto) -> list[str]:
    x1, y1 = int(_num(p.get("x1"))), int(_num(p.get("y1")))
    x2, y2 = int(_num(p.get("x2"))), int(_num(p.get("y2")))
    dur = _seg(p.get("duracao"), 1.2)
    botao = p.get("botao", "left")
    return [
        f"pyautogui.moveTo({x1}, {y1})",
        f"pyautogui.dragTo({x2}, {y2}, duration={dur}, button={botao!r})",
    ]


def _emitir_rolar(p: dict, ctx: Contexto) -> list[str]:
    linhas = []
    if p.get("x") is not None and p.get("y") is not None:
        linhas.append(f"pyautogui.moveTo({int(p['x'])}, {int(p['y'])})")
    linhas.append(f"pyautogui.scroll({int(_num(p.get('quantidade'), -5))})")
    return linhas


def _emitir_digitar(p: dict, ctx: Contexto) -> list[str]:
    texto = repr(str(p.get("texto", "")))
    intervalo = p.get("intervalo")
    if intervalo is None:
        return [f"digitar({texto})"]
    return [f"digitar({texto}, intervalo={_seg(intervalo, 0.08)})"]


def _emitir_atalho(p: dict, ctx: Contexto) -> list[str]:
    teclas = ", ".join(repr(str(t)) for t in (p.get("teclas") or []))
    return [f"pyautogui.hotkey({teclas})"]


def _emitir_tecla(p: dict, ctx: Contexto) -> list[str]:
    nome = repr(str(p.get("nome", "enter")))
    rep = max(1, int(_num(p.get("repeticoes"), 1)))
    if rep > 1:
        return [f"pyautogui.press({nome}, presses={rep}, interval=0.05)"]
    return [f"pyautogui.press({nome})"]


def _emitir_pausa(p: dict, ctx: Contexto) -> list[str]:
    return [f"dormir({_seg(p.get('segundos'), 1.0)})"]


def _emitir_img_clicar(p: dict, ctx: Contexto) -> list[str]:
    offset = p.get("offset") or [0, 0]
    obrigatorio = p.get("se_falhar", "abortar") != "continuar"
    argumentos = [
        repr(str(p.get("arquivo", ""))),
        f"timeout={_seg(p.get('timeout'), ctx.timeout_imagem)}",
        f"confidence={_seg(p.get('confianca'), ctx.confianca_imagem)}",
        f"duration={_seg(p.get('duracao'), 1.0)}",
        f"offset=({int(_num(offset[0]))}, {int(_num(offset[1]))})",
        f"cliques={max(1, int(_num(p.get('cliques'), 1)))}",
        f"botao={p.get('botao', 'left')!r}",
        f"tentativas={max(1, int(_num(p.get('tentativas'), ctx.tentativas_imagem)))}",
        f"obrigatorio={obrigatorio!r}",
    ]
    fallback = p.get("fallback")
    if fallback:
        argumentos.append(f"fallback=({int(_num(fallback[0]))}, {int(_num(fallback[1]))})")
    return [f"esperar_e_clicar({', '.join(argumentos)})"]


def _emitir_img_esperar(p: dict, ctx: Contexto) -> list[str]:
    obrigatorio = p.get("se_falhar", "abortar") != "continuar"
    return [
        "esperar_imagem_obrigatoria("
        f"{p.get('arquivo', '')!r}, "
        f"timeout={_seg(p.get('timeout'), ctx.timeout_imagem)}, "
        f"confidence={_seg(p.get('confianca'), ctx.confianca_imagem)}, "
        f"tentativas={max(1, int(_num(p.get('tentativas'), ctx.tentativas_imagem)))}, "
        f"obrigatorio={obrigatorio!r}"
        ")"
    ]


def _emitir_img_desaparecer(p: dict, ctx: Contexto) -> list[str]:
    obrigatorio = p.get("se_falhar", "abortar") != "continuar"
    return [
        "esperar_imagem_desaparecer("
        f"{p.get('arquivo', '')!r}, "
        f"timeout={_seg(p.get('timeout'), ctx.timeout_imagem)}, "
        f"confidence={_seg(p.get('confianca'), ctx.confianca_imagem)}, "
        f"tentativas={max(1, int(_num(p.get('tentativas'), ctx.tentativas_imagem)))}, "
        f"obrigatorio={obrigatorio!r}"
        ")"
    ]


def _emitir_vazio(p: dict, ctx: Contexto) -> list[str]:
    return []


def _emitir_comentario(p: dict, ctx: Contexto) -> list[str]:
    texto = str(p.get("texto", "")).replace("\r", "").replace("\n", " ")
    return [f"# {texto}"]


# ----------------------------------------------------------------------
# Categorias usadas pela UI
# ----------------------------------------------------------------------
def _padrao_clicar() -> dict:
    return {"x": 0, "y": 0, "botao": "left", "cliques": 1, "duracao": 1.2}


def _padrao_img(arquivo: str = "", clicar: bool = True) -> dict:
    base = {
        "arquivo": arquivo,
        "timeout": 15,
        "confianca": 0.9,
        "tentativas": 2,
        "se_falhar": "abortar",
    }
    if clicar:
        base.update({"duracao": 1.0, "offset": [0, 0], "cliques": 1,
                     "botao": "left", "fallback": None})
    return base


TIPOS: dict[str, TipoPasso] = {
    "clicar": TipoPasso("clicar", "Clique", _rotulo_clicar, _emitir_clicar, _padrao_clicar),
    "mover": TipoPasso(
        "mover", "Movimento", _rotulo_mover, _emitir_mover,
        lambda: {"x": 0, "y": 0, "duracao": 1.2},
    ),
    "arrastar": TipoPasso(
        "arrastar", "Arrastar", _rotulo_arrastar, _emitir_arrastar,
        lambda: {"x1": 0, "y1": 0, "x2": 0, "y2": 0, "duracao": 1.2, "botao": "left"},
    ),
    "rolar": TipoPasso(
        "rolar", "Rolagem", _rotulo_rolar, _emitir_rolar,
        lambda: {"quantidade": -5, "x": None, "y": None},
    ),
    "digitar": TipoPasso(
        "digitar", "Texto", _rotulo_digitar, _emitir_digitar,
        lambda: {"texto": "", "intervalo": None},
    ),
    "atalho": TipoPasso(
        "atalho", "Atalho", _rotulo_atalho, _emitir_atalho,
        lambda: {"teclas": ["ctrl", "c"]},
    ),
    "tecla": TipoPasso(
        "tecla", "Tecla", _rotulo_tecla, _emitir_tecla,
        lambda: {"nome": "enter", "repeticoes": 1},
    ),
    "pausa": TipoPasso(
        "pausa", "Pausa", _rotulo_pausa, _emitir_pausa,
        lambda: {"segundos": 1.0},
    ),
    "imagem_clicar": TipoPasso(
        "imagem_clicar", "Imagem + clique", _rotulo_img_clicar, _emitir_img_clicar,
        lambda: _padrao_img(clicar=True), categoria="imagem",
    ),
    "imagem_esperar": TipoPasso(
        "imagem_esperar", "Esperar imagem", _rotulo_img_esperar, _emitir_img_esperar,
        lambda: _padrao_img(clicar=False), categoria="imagem",
    ),
    "imagem_desaparecer": TipoPasso(
        "imagem_desaparecer", "Esperar sumir", _rotulo_img_desaparecer,
        _emitir_img_desaparecer,
        lambda: _padrao_img(clicar=False), categoria="imagem",
    ),
    "bloco_inicio": TipoPasso(
        "bloco_inicio", "Início de bloco", _rotulo_bloco_ini, _emitir_vazio,
        lambda: {"vezes": 2, "nota": ""}, categoria="estrutura",
    ),
    "bloco_fim": TipoPasso(
        "bloco_fim", "Fim de bloco", lambda p: "FIM do bloco",
        _emitir_vazio, lambda: {}, categoria="estrutura",
    ),
    "comentario": TipoPasso(
        "comentario", "Comentário", _rotulo_comentario, _emitir_comentario,
        lambda: {"texto": ""}, categoria="estrutura",
    ),
}


def criar(tipo: str, **params: Any) -> dict:
    """Cria o dicionário de parâmetros de um passo, com os padrões do tipo."""
    if tipo not in TIPOS:
        raise KeyError(f"Tipo de passo desconhecido: {tipo}")
    base = TIPOS[tipo].padrao()
    base.update(params)
    return base


def rotulo(tipo: str, params: dict) -> str:
    item = TIPOS.get(tipo)
    if item is None:
        return f"Passo desconhecido: {tipo}"
    try:
        return item.rotulo(params)
    except Exception:
        return f"{tipo}: {params}"


def emitir(tipo: str, params: dict, ctx: Contexto) -> list[str]:
    item = TIPOS.get(tipo)
    if item is None:
        raise KeyError(f"Tipo de passo desconhecido: {tipo}")
    return item.emitir(params, ctx)
