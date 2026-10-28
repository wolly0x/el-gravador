"""Log em arquivo + memória, compartilhado pela UI e pelo executor."""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

from . import caminhos

LOGGER = logging.getLogger("elgravador")
_configurado = False


def configurar(nivel: int = logging.INFO, para_arquivo: bool = True) -> Path | None:
    """Configura o logger uma única vez. Devolve o caminho do arquivo."""
    global _configurado
    caminho: Path | None = None
    if _configurado:
        return caminhos.LOGS_DIR / f"elgravador_{datetime.now():%Y-%m-%d}.log"
    _configurado = True
    LOGGER.setLevel(nivel)
    LOGGER.propagate = False

    formato = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formato)
    LOGGER.addHandler(console)

    if para_arquivo:
        try:
            caminhos.LOGS_DIR.mkdir(parents=True, exist_ok=True)
            caminho = caminhos.LOGS_DIR / f"elgravador_{datetime.now():%Y-%m-%d}.log"
            arquivo = logging.FileHandler(caminho, encoding="utf-8")
            arquivo.setFormatter(formato)
            LOGGER.addHandler(arquivo)
        except Exception as exc:  # pragma: no cover
            LOGGER.warning("Não foi possível abrir o arquivo de log: %s", exc)
    return caminho


def log(texto: str, nivel: int = logging.INFO) -> None:
    LOGGER.log(nivel, texto)
