"""Importação de scripts antigos (parte*.py) via AST — sem regex frágil."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from . import passos
from .projeto import Passo, Projeto

_CLICKS = {
    "click": (1, "left"),
    "doubleClick": (2, "left"),
    "rightClick": (1, "right"),
    "middleClick": (1, "middle"),
    "tripleClick": (3, "left"),
}
_PREFIXOS = {"pyautogui", "pg", "gui"}


def _lado_do_sidecar(caminho: Path) -> Path:
    return caminho.with_name(caminho.stem + ".elgravador.json")


def importar_script(caminho: str | Path) -> tuple[Projeto, list[str]]:
    origem = Path(caminho)
    avisos: list[str] = []

    sidecar = _lado_do_sidecar(origem)
    if sidecar.exists():
        try:
            projeto = Projeto.carregar(sidecar)
            avisos.append(f'Projeto lido do sidecar "{sidecar.name}".')
            return projeto, avisos
        except Exception as exc:
            avisos.append(f"Sidecar ilegível ({exc}); tentando ler o .py.")

    try:
        fonte = origem.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ValueError(f"Não foi possível ler {origem}: {exc}") from exc

    try:
        arvore = ast.parse(fonte)
    except SyntaxError as exc:
        raise ValueError(f"O arquivo não é um Python válido: {exc}") from exc

    projeto = Projeto(nome=origem.stem)
    bloco = _achar_funcao(arvore, "executar_bloco")
    if bloco is None:
        raise ValueError(
            'Script incompatível: não encontrei "def executar_bloco()".'
        )

    projeto.passos.extend(_converter_corpo(bloco.body, avisos))

    repeticao = _repeticao_do_iniciar(arvore)
    if repeticao is not None:
        projeto.config["repeticoes"] = repeticao

    if not projeto.passos:
        avisos.append("Nenhum passo reconhecido dentro de executar_bloco().")
    return projeto, avisos


# ----------------------------------------------------------------------
def _achar_funcao(arvore: ast.AST, nome: str) -> ast.FunctionDef | None:
    for no in ast.walk(arvore):
        if isinstance(no, ast.FunctionDef) and no.name == nome:
            return no
    return None


def _repeticao_do_iniciar(arvore: ast.AST) -> int | None:
    iniciar = _achar_funcao(arvore, "iniciar")
    if iniciar is None:
        return None
    for no in ast.walk(iniciar):
        if isinstance(no, ast.While) and _eh_true(no.test):
            return 0
        if isinstance(no, ast.For) and isinstance(no.iter, ast.Call):
            limites = _limites_range(no.iter)
            if limites is not None:
                inicio, fim = limites
                return max(1, fim - inicio)
    return None


def _eh_true(no: ast.AST) -> bool:
    return isinstance(no, ast.Constant) and no.value is True


def _constante(no: ast.AST) -> int | None:
    """Avalia inteiros constantes, inclusive expressões como 4 + 1."""
    if isinstance(no, ast.Constant) and isinstance(no.value, int):
        return no.value
    if isinstance(no, ast.UnaryOp) and isinstance(no.op, (ast.USub, ast.UAdd)):
        interno = _constante(no.operand)
        if interno is None:
            return None
        return -interno if isinstance(no.op, ast.USub) else interno
    if isinstance(no, ast.BinOp) and isinstance(
        no.op, (ast.Add, ast.Sub, ast.Mult, ast.FloorDiv, ast.Mod)
    ):
        esquerda = _constante(no.left)
        direita = _constante(no.right)
        if esquerda is None or direita is None:
            return None
        if isinstance(no.op, ast.Add):
            return esquerda + direita
        if isinstance(no.op, ast.Sub):
            return esquerda - direita
        if isinstance(no.op, ast.Mult):
            return esquerda * direita
        if direita == 0:
            return None
        return esquerda // direita if isinstance(no.op, ast.FloorDiv) else esquerda % direita
    return None


def _limites_range(no: ast.Call) -> tuple[int, int] | None:
    if not isinstance(no.func, ast.Name) or no.func.id != "range":
        return None
    valores: list[int] = []
    for arg in no.args:
        valor = _constante(arg)
        if valor is None:
            return None
        valores.append(valor)
    if len(valores) == 1:
        return 0, valores[0]
    if len(valores) >= 2:
        return valores[0], valores[1]
    return None


def _literal(no: ast.AST | None, avisos: list[str]) -> Any:
    if no is None:
        return None
    try:
        return ast.literal_eval(no)
    except Exception:
        avisos.append(f"Argumento não literal ignorado: {ast.dump(no)[:60]}")
        return None


def _chamada(no: ast.stmt) -> tuple[str | None, str | None, ast.Call | None]:
    if not isinstance(no, ast.Expr) or not isinstance(no.value, ast.Call):
        return None, None, None
    chamada = no.value
    func = chamada.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return func.value.id, func.attr, chamada
    if isinstance(func, ast.Attribute):
        return None, func.attr, chamada
    if isinstance(func, ast.Name):
        return None, func.id, chamada
    return None, None, None


def _params(chamada: ast.Call, avisos: list[str]) -> dict[str, Any]:
    valores: dict[str, Any] = {}
    for chave in chamada.keywords:
        if chave.arg:
            valores[chave.arg] = _literal(chave.value, avisos)
    return valores


def _pos(chamada: ast.Call, avisos: list[str]) -> list[Any]:
    return [_literal(arg, avisos) for arg in chamada.args]


def _xy(chamada: ast.Call, avisos: list[str]) -> tuple[int, int] | None:
    pos = _pos(chamada, avisos)
    nomeados = _params(chamada, avisos)
    try:
        if len(pos) >= 2 and pos[0] is not None and pos[1] is not None:
            return int(pos[0]), int(pos[1])
        x = nomeados.get("x", pos[0] if pos else None)
        y = nomeados.get("y", pos[1] if len(pos) > 1 else None)
        if x is not None and y is not None:
            return int(x), int(y)
    except (TypeError, ValueError):
        pass
    return None


# ----------------------------------------------------------------------
def _converter_corpo(corpo: list[ast.stmt], avisos: list[str]) -> list[Passo]:
    lista: list[Passo] = []
    i = 0
    while i < len(corpo):
        no = corpo[i]

        if isinstance(no, ast.For):
            limites = _limites_range(no.iter) if isinstance(no.iter, ast.Call) else None
            if limites is None:
                avisos.append("Laço 'for' não reconhecido; conteúdo importado uma vez.")
                lista.extend(_converter_corpo(no.body, avisos))
                i += 1
                continue
            inicio, fim = limites
            vezes = max(1, fim - inicio)
            lista.append(Passo("bloco_inicio", passos.criar("bloco_inicio", vezes=vezes)))
            lista.extend(_converter_corpo(no.body, avisos))
            lista.append(Passo("bloco_fim", {"vezes": vezes}))
            i += 1
            continue

        if isinstance(no, ast.If):
            avisos.append("Bloco 'if' importado sem a condição (executa sempre).")
            lista.extend(_converter_corpo(no.body, avisos))
            if no.orelse:
                avisos.append("Bloco 'else' foi ignorado.")
            i += 1
            continue

        modulo, nome, chamada = _chamada(no)
        if chamada is None or nome is None:
            i += 1
            continue

        # moveTo + clique -> um único passo de clique
        if nome == "moveTo" and modulo in _PREFIXOS:
            ponto = _xy(chamada, avisos)
            duracao = _params(chamada, avisos).get("duration")
            proximo_modulo, proximo_nome, proxima = (
                _chamada(corpo[i + 1]) if i + 1 < len(corpo) else (None, None, None)
            )
            if (
                proxima is not None
                and proximo_modulo in _PREFIXOS
                and proximo_nome in _CLICKS
            ):
                cliques, botao = _CLICKS[proximo_nome]
                if ponto:
                    lista.append(
                        Passo(
                            "clicar",
                            passos.criar(
                                "clicar",
                                x=ponto[0],
                                y=ponto[1],
                                botao=botao,
                                cliques=cliques,
                                duracao=duracao if duracao else 1.2,
                            ),
                        )
                    )
                i += 2
                continue
            if (
                proxima is not None
                and proximo_modulo in _PREFIXOS
                and proximo_nome == "dragTo"
            ):
                destino = _xy(proxima, avisos)
                if ponto and destino:
                    lista.append(
                        Passo(
                            "arrastar",
                            passos.criar(
                                "arrastar",
                                x1=ponto[0],
                                y1=ponto[1],
                                x2=destino[0],
                                y2=destino[1],
                                duracao=duracao if duracao else 1.2,
                            ),
                        )
                    )
                    i += 2
                    continue
            if ponto:
                lista.append(
                    Passo(
                        "mover",
                        passos.criar(
                            "mover", x=ponto[0], y=ponto[1], duracao=duracao or 1.2
                        ),
                    )
                )
            i += 1
            continue

        if modulo in _PREFIXOS and nome in _CLICKS:
            ponto = _xy(chamada, avisos)
            cliques, botao = _CLICKS[nome]
            if ponto:
                lista.append(
                    Passo(
                        "clicar",
                        passos.criar(
                            "clicar", x=ponto[0], y=ponto[1], botao=botao,
                            cliques=cliques,
                        ),
                    )
                )
            i += 1
            continue

        if modulo in _PREFIXOS and nome == "scroll":
            pos = _pos(chamada, avisos)
            valores = _params(chamada, avisos)
            quantidade = valores.get("clicks", pos[0] if pos else -5)
            try:
                quantidade = int(quantidade)
            except (TypeError, ValueError):
                quantidade = -5
            lista.append(Passo("rolar", passos.criar("rolar", quantidade=quantidade)))
            i += 1
            continue

        if modulo in _PREFIXOS and nome == "hotkey":
            teclas = [str(t).lower() for t in _pos(chamada, avisos) if t is not None]
            if teclas:
                lista.append(Passo("atalho", passos.criar("atalho", teclas=teclas)))
            i += 1
            continue

        if modulo in _PREFIXOS and nome == "press":
            pos = _pos(chamada, avisos)
            if pos and pos[0]:
                repeticoes = _params(chamada, avisos).get("presses", 1)
                try:
                    repeticoes = max(1, int(repeticoes))
                except (TypeError, ValueError):
                    repeticoes = 1
                lista.append(
                    Passo(
                        "tecla",
                        passos.criar(
                            "tecla", nome=str(pos[0]).lower(), repeticoes=repeticoes
                        ),
                    )
                )
            i += 1
            continue

        if modulo in _PREFIXOS and nome in ("write", "typewrite"):
            pos = _pos(chamada, avisos)
            texto = pos[0] if pos else ""
            if texto is not None:
                lista.append(
                    Passo("digitar", passos.criar("digitar", texto=str(texto)))
                )
            i += 1
            continue

        if modulo == "time" and nome == "sleep":
            pos = _pos(chamada, avisos)
            segundos = pos[0] if pos else 1.0
            if isinstance(segundos, (int, float)):
                lista.append(
                    Passo("pausa", passos.criar("pausa", segundos=float(segundos)))
                )
            i += 1
            continue

        if nome == "digitar":
            pos = _pos(chamada, avisos)
            texto = pos[0] if pos else ""
            if texto is not None:
                lista.append(
                    Passo("digitar", passos.criar("digitar", texto=str(texto)))
                )
            i += 1
            continue

        if nome in ("esperar_e_clicar", "esperar_imagem"):
            pos = _pos(chamada, avisos)
            nomeados = _params(chamada, avisos)
            arquivo = pos[0] if pos else nomeados.get("nome")
            if not arquivo:
                avisos.append(f'Passo "{nome}" sem imagem; ignorado.')
                i += 1
                continue

            if nome == "esperar_e_clicar":
                params = passos.criar("imagem_clicar")
                params.update(
                    {
                        "arquivo": str(arquivo),
                        "timeout": nomeados.get("timeout", 15),
                        "confianca": nomeados.get("confidence", 0.9),
                        "duracao": nomeados.get("duration", 1.0),
                    }
                )
                lista.append(Passo("imagem_clicar", params))
            else:
                params = passos.criar("imagem_esperar")
                params.update(
                    {
                        "arquivo": str(arquivo),
                        "timeout": nomeados.get("timeout", 15),
                        "confianca": nomeados.get("confidence", 0.9),
                    }
                )
                lista.append(Passo("imagem_esperar", params))
            i += 1
            continue

        avisos.append(f"Chamada não reconhecida: {modulo + '.' if modulo else ''}{nome}()")
        i += 1

    return lista



def importar_pasta_scripts(pasta: str | Path) -> list[tuple[Path, Projeto | None, list[str]]]:
    """Importa todos os .py de uma pasta, devolvendo (arquivo, projeto, avisos)."""
    resultados = []
    for arquivo in sorted(Path(pasta).glob("*.py")):
        try:
            projeto, avisos = importar_script(arquivo)
            resultados.append((arquivo, projeto, avisos))
        except Exception as exc:
            resultados.append((arquivo, None, [str(exc)]))
    return resultados


def salvar_como_projeto(projeto: Projeto, destino: str | Path) -> Path:
    return projeto.salvar(destino)
