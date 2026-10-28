"""Configuração da interface: escala, tema fixo e migração."""

import json

import pytest

from nucleo.config import Config


def _carregar(caminho, dados=None):
    if dados is not None:
        caminho.write_text(json.dumps(dados), encoding="utf-8")
    cfg = Config(caminho)
    cfg.carregar()
    return cfg


def test_escala_web_padrao(tmp_path):
    cfg = _carregar(tmp_path / "config.json")
    assert cfg.get("escala_web") == 15


def test_escala_web_migra_config_antigo(tmp_path):
    cfg = _carregar(
        tmp_path / "config.json",
        {"tema": "Apple Glass", "tamanho_fonte": 15, "fator_zoom": 0.7},
    )
    # O Tk continua com seus valores; a interface web ganha uma escala própria.
    assert cfg.get("tamanho_fonte") == 15
    assert cfg.get("fator_zoom") == 0.7
    assert cfg.get("escala_web") == 15


@pytest.mark.parametrize(
    "valor, esperado",
    [(5, 15), (14, 15), (15, 15), (18, 18), (22, 22), (99, 22), ("x", 15), (None, 15)],
)
def test_escala_web_limites(tmp_path, valor, esperado):
    cfg = _carregar(tmp_path / "config.json", {"escala_web": valor})
    assert cfg.get("escala_web") == esperado


def test_escala_web_persiste(tmp_path):
    caminho = tmp_path / "config.json"
    cfg = _carregar(caminho, {"escala_web": 18})
    cfg.set("tema", "Apple Glass Dark")
    cfg.salvar()

    recarregado = _carregar(caminho)
    assert recarregado.get("escala_web") == 18
    # Tema fixo: qualquer valor antigo é ignorado na leitura.
    assert recarregado.get("tema") == "Apple Glass"


def test_tema_e_cores_antigos_sao_ignorados(tmp_path):
    cfg = _carregar(
        tmp_path / "config.json",
        {
            "tema": "Monokai Pro",
            "cores_custom": {"c_bg": "#000000"},
            "topmost": True,
        },
    )
    assert cfg.get("tema") == "Apple Glass"
    assert cfg.get("cores_custom") == {}
    # A chave removida não é mais lida nem repassada para a interface.
    assert "topmost" not in cfg.dados
