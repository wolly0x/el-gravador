"""Caminhos padrão do aplicativo (compatível com PyInstaller)."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def base_dir() -> Path:
    """Pasta do executável (frozen) ou a raiz do projeto (código fonte)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = base_dir()
CONFIG_FILE = BASE_DIR / "config.json"
IMAGENS_DIR = BASE_DIR / "imagens_templates"
MANIFESTO = IMAGENS_DIR / "manifest.json"
PROJETOS_DIR = BASE_DIR / "projetos"
LOGS_DIR = BASE_DIR / "logs"

PASTAS = (IMAGENS_DIR, PROJETOS_DIR, LOGS_DIR)


def garantir_dirs() -> None:
    for pasta in PASTAS:
        pasta.mkdir(parents=True, exist_ok=True)


def relativo(caminho: os.PathLike | str) -> str:
    """Tenta devolver um caminho relativo à BASE_DIR; senão, absoluto."""
    p = Path(caminho)
    try:
        return str(p.resolve().relative_to(BASE_DIR))
    except ValueError:
        return str(p)
