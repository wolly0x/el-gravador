import json

import pytest
from PIL import Image

from nucleo import imagens


def _imagem(cor="white", tamanho=(100, 80)):
    return Image.new("RGB", tamanho, cor)


def test_salvar_e_listar(imagens_tmp):
    nome = imagens.salvar_template(_imagem("red"), "botao salvar")
    assert nome.startswith("botao_salvar_")
    assert nome.endswith(".png")
    assert (imagens_tmp / nome).exists()
    itens = imagens.listar()
    assert [i["nome"] for i in itens] == [nome]
    assert imagens.existe(nome)
    manifesto = json.loads((imagens_tmp / "manifest.json").read_text(encoding="utf-8"))
    assert manifesto["templates"][nome]["largura"] == 100


def test_dedupe_por_hash(imagens_tmp):
    a = imagens.salvar_template(_imagem("red"), "um")
    b = imagens.salvar_template(_imagem("red"), "dois")
    assert a == b
    assert len(imagens.listar()) == 1


def test_nomes_diferentes_para_imagens_diferentes(imagens_tmp):
    a = imagens.salvar_template(_imagem("red"), "x")
    b = imagens.salvar_template(_imagem("blue"), "x")
    assert a != b


def test_remover_e_orfaos(imagens_tmp):
    a = imagens.salvar_template(_imagem("red"), "a")
    b = imagens.salvar_template(_imagem("blue"), "b")
    assert imagens.orfaos([a]) == [b]
    assert imagens.remover(b)
    assert not imagens.existe(b)
    assert imagens.orfaos([a]) == []


def test_importar_pasta_dedupe(imagens_tmp, tmp_path):
    origem = tmp_path / "antigos"
    origem.mkdir()
    _imagem("green").save(origem / "template_1.png")
    _imagem("black").save(origem / "template_2.png")
    novos, iguais = imagens.importar_pasta(origem)
    assert (novos, iguais) == (2, 0)
    novos, iguais = imagens.importar_pasta(origem)
    assert (novos, iguais) == (0, 2)
    assert len(imagens.listar()) == 2


def test_copiar_usados(imagens_tmp, tmp_path):
    a = imagens.salvar_template(_imagem("red"), "a")
    destino = tmp_path / "saida"
    ausentes = imagens.copiar_usados([a, "nao_existe.png"], destino)
    assert ausentes == ["nao_existe.png"]
    assert (destino / "imagens_templates" / a).exists()
    assert (destino / "imagens_templates" / "manifest.json").exists()


def test_localizar_exato_sem_cv2():
    tela = _imagem("white", (100, 80))
    for x in range(30, 35):
        for y in range(40, 45):
            tela.putpixel((x, y), (255, 0, 0))
    template = tela.crop((30, 40, 35, 45))
    centro = imagens.localizar(tela, 0, 0, template, 1.0)
    assert centro == (32, 42)


def test_localizar_nao_encontrado():
    tela = _imagem("white")
    template = _imagem("black", (5, 5))
    assert imagens.localizar(tela, 0, 0, template, 1.0) is None


def test_localizar_detalhado_exato_sem_cv2():
    tela = _imagem("white", (100, 80))
    for x in range(30, 35):
        for y in range(40, 45):
            tela.putpixel((x, y), (255, 0, 0))
    template = tela.crop((30, 40, 35, 45))
    resultado = imagens.localizar_detalhado(tela, 0, 0, template, 1.0)
    assert resultado.centro == (32, 42)
    assert resultado.score == 1.0
    assert resultado.melhor_score == 1.0


def test_regiao_template(imagens_tmp):
    nome = imagens.salvar_template(
        _imagem("red"), "x", meta={"regiao": [10, 20, 30, 40]}
    )
    assert imagens.regiao_template(nome) == (10, 20, 30, 40)
    assert imagens.regiao_template("nao_existe.png") is None


def test_salvar_diagnostico(imagens_tmp, tmp_path, monkeypatch):
    from nucleo import caminhos

    logs = tmp_path / "logs"
    monkeypatch.setattr(caminhos, "LOGS_DIR", logs)
    tela = _imagem("white", (100, 80))
    template = _imagem("black", (5, 5))
    resultado = imagens.localizar_detalhado(tela, 0, 0, template, 1.0)
    caminho = imagens.salvar_diagnostico(tela, template, resultado, "teste.png")
    assert caminho is not None
    assert caminho.exists()
    assert caminho.name.startswith("diag_teste_")


def test_localizar_offset_de_origem():
    tela = _imagem("white", (100, 80))
    for x in range(10, 15):
        for y in range(10, 15):
            tela.putpixel((x, y), (0, 0, 255))
    template = tela.crop((10, 10, 15, 15))
    # tela capturada com origem virtual (-20, -30)
    centro = imagens.localizar(tela, -20, -30, template, 1.0)
    assert centro == (-20 + 12, -30 + 12)


def test_recortar_validacao():
    tela = _imagem("white", (100, 80))
    assert imagens.recortar(tela, 10, 10, 20, 20).size == (10, 10)
    with pytest.raises(imagens.ErroImagem):
        imagens.recortar(tela, 500, 500, 600, 600)


def test_carregar_cache(imagens_tmp):
    nome = imagens.salvar_template(_imagem("red"), "c")
    primeira = imagens.carregar(nome)
    segunda = imagens.carregar(nome)
    assert primeira is segunda
    imagens.limpar_cache()


def test_slug():
    assert imagens.slug("Botão Salvar (ação)") == "botao_salvar_acao"
    assert imagens.slug("") == "template"
