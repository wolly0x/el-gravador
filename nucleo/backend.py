"""Camada de entrada/saída: pyautogui real ou backend falso (testes/simulação)."""

from __future__ import annotations

from typing import Protocol


class Backend(Protocol):
    def mover(self, x: int, y: int, duracao: float) -> None: ...
    def clicar(self, botao: str = "left", cliques: int = 1) -> None: ...
    def clicar_em(
        self, x: int, y: int, botao: str = "left", cliques: int = 1, duracao: float = 0.0
    ) -> None: ...
    def arrastar(
        self, x1: int, y1: int, x2: int, y2: int, duracao: float, botao: str = "left"
    ) -> None: ...
    def rolar(self, quantidade: int) -> None: ...
    def tecla(self, nome: str, repeticoes: int = 1) -> None: ...
    def atalho(self, teclas: list[str]) -> None: ...
    def escrever(self, caractere: str) -> None: ...
    def posicao(self) -> tuple[int, int]: ...


class BackendReal:
    """pyautogui com fallback de digitação via pynput (acentos)."""

    def __init__(self, failsafe: bool = True):
        import pyautogui

        self.pg = pyautogui
        self.pg.PAUSE = 0
        self.pg.FAILSAFE = bool(failsafe)
        self._controlador = None
        self._controlador_tentado = False

    # ------------------------------------------------------------------
    def _ctrl(self):
        if not self._controlador_tentado:
            self._controlador_tentado = True
            try:
                from pynput.keyboard import Controller

                self._controlador = Controller()
            except Exception:
                self._controlador = None
        return self._controlador

    def mover(self, x: int, y: int, duracao: float = 0.0) -> None:
        if duracao and duracao > 0:
            self.pg.moveTo(
                int(x), int(y), duration=float(duracao), tween=self.pg.easeInOutQuad
            )
        else:
            self.pg.moveTo(int(x), int(y))

    def clicar(self, botao: str = "left", cliques: int = 1) -> None:
        self.pg.click(clicks=max(1, int(cliques)), interval=0.05, button=botao)

    def clicar_em(
        self,
        x: int,
        y: int,
        botao: str = "left",
        cliques: int = 1,
        duracao: float = 0.0,
    ) -> None:
        self.mover(x, y, duracao)
        self.clicar(botao, cliques)

    def arrastar(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duracao: float = 1.0,
        botao: str = "left",
    ) -> None:
        self.pg.moveTo(int(x1), int(y1))
        self.pg.dragTo(
            int(x2), int(y2), duration=float(duracao), button=botao
        )

    def rolar(self, quantidade: int) -> None:
        self.pg.scroll(int(quantidade))

    def tecla(self, nome: str, repeticoes: int = 1) -> None:
        self.pg.press(nome, presses=max(1, int(repeticoes)), interval=0.05)

    def atalho(self, teclas: list[str]) -> None:
        if teclas:
            self.pg.hotkey(*teclas)

    def escrever(self, caractere: str) -> None:
        try:
            self.pg.write(caractere)
        except Exception:
            controlador = self._ctrl()
            if controlador is not None:
                try:
                    controlador.type(caractere)
                except Exception:
                    pass

    def posicao(self) -> tuple[int, int]:
        ponto = self.pg.position()
        return int(ponto.x), int(ponto.y)


class BackendFake:
    """Registra as chamadas sem tocar no mouse/teclado."""

    def __init__(self) -> None:
        self.chamadas: list[tuple] = []

    def mover(self, x, y, duracao=0.0):
        self.chamadas.append(("mover", int(x), int(y), float(duracao)))

    def clicar(self, botao="left", cliques=1):
        self.chamadas.append(("clicar", botao, int(cliques)))

    def clicar_em(self, x, y, botao="left", cliques=1, duracao=0.0):
        self.chamadas.append(("clicar_em", int(x), int(y), botao, int(cliques)))

    def arrastar(self, x1, y1, x2, y2, duracao=1.0, botao="left"):
        self.chamadas.append(
            ("arrastar", int(x1), int(y1), int(x2), int(y2), float(duracao), botao)
        )

    def rolar(self, quantidade):
        self.chamadas.append(("rolar", int(quantidade)))

    def tecla(self, nome, repeticoes=1):
        self.chamadas.append(("tecla", str(nome), int(repeticoes)))

    def atalho(self, teclas):
        self.chamadas.append(("atalho", tuple(teclas)))

    def escrever(self, caractere):
        self.chamadas.append(("escrever", caractere))

    def posicao(self):
        return (0, 0)

    # conveniências para testes
    def tipos(self) -> list[str]:
        return [chamada[0] for chamada in self.chamadas]

    def texto_digitado(self) -> str:
        return "".join(
            chamada[1] for chamada in self.chamadas if chamada[0] == "escrever"
        )
