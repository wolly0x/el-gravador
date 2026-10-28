import json

import pytest

from nucleo import projeto, passos


def test_roundtrip_arquivo(tmp_path):
    p = projeto.Projeto("cadastro")
    p.adicionar("clicar", x=1, y=2)
    p.adicionar("digitar", texto="ação")
    p.adicionar("bloco_inicio", vezes=3)
    p.adicionar("tecla", nome="enter")
    p.adicionar("bloco_fim")
    p.config["repeticoes"] = 4
    destino = p.salvar(tmp_path / "cadastro.json")

    carregado = projeto.Projeto.carregar(destino)
    assert carregado.nome == "cadastro"
    assert len(carregado) == 5
    assert carregado.passos[1].params["texto"] == "ação"
    assert carregado.repeticao() == 4
    assert carregado.validar() == []
    assert carregado.caminho == destino
    assert carregado.alterado is False


def test_mover_duplicar_remover():
    p = projeto.Projeto()
    for i in range(3):
        p.adicionar("pausa", segundos=i + 1)
    assert p.mover(0, 2)
    assert [x.params["segundos"] for x in p] == [2, 3, 1]
    copia = p.duplicar(0)
    assert copia is not None and len(p) == 4
    assert p.passos[0].id != p.passos[1].id
    removido = p.remover(0)
    assert removido is not None and len(p) == 3


def test_validar_bloco_desbalanceado():
    p = projeto.Projeto()
    p.adicionar("bloco_fim")
    p.adicionar("bloco_inicio", vezes=2)
    problemas = p.validar()
    assert any("sem INÍCIO" in x for x in problemas)
    assert any("sem FIM" in x for x in problemas)


def test_de_dict_completa_parametros_ausentes():
    passo = projeto.Passo.de_dict({"tipo": "imagem_clicar", "params": {"arquivo": "a.png"}})
    assert passo.params["timeout"] == 15
    assert passo.params["arquivo"] == "a.png"
    assert passo.params["tentativas"] == 2


def test_templates_usados_unicos():
    p = projeto.Projeto()
    p.adicionar("imagem_clicar", arquivo="a.png")
    p.adicionar("imagem_esperar", arquivo="a.png")
    p.adicionar("imagem_desaparecer", arquivo="b.png")
    assert p.templates_usados() == ["a.png", "b.png"]


def test_criar_desconhecido():
    with pytest.raises(KeyError):
        passos.criar("nao_existe")
