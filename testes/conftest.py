import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


@pytest.fixture()
def imagens_tmp(tmp_path, monkeypatch):
    """Redireciona a pasta de templates para um tmp_path."""
    from nucleo import caminhos

    pasta = tmp_path / "imagens_templates"
    pasta.mkdir()
    monkeypatch.setattr(caminhos, "IMAGENS_DIR", pasta)
    monkeypatch.setattr(caminhos, "MANIFESTO", pasta / "manifest.json")
    from nucleo import imagens

    imagens.limpar_cache()
    return pasta
