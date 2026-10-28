import threading

import pytest

from nucleo import executor, projeto


CFG = {
    "duracao_movimento": 0.0,
    "duracao_movimento_imagem": 0.0,
    "pausa_entre_acoes": 0.0,
    "pausa_entre_acoes_variavel": False,
    "intervalo_digitacao": 0.0,
    "intervalo_digitacao_variavel": False,
    "timeout_imagem": 0.2,
    "confianca_imagem": 0.9,
    "tentativas_imagem": 1,
    "ao_falhar": "abortar",
    "imagem_cinza": True,
    "simular": False,
}


class ImagensFake:
    def __init__(self, achados=None, existentes=None):
        self.achados = achados or {}
        self.existentes = existentes if existentes is not None else {"ok.png"}

    def existe(self, nome):
        return nome in self.existentes

    def carregar(self, nome):
        return nome

    def localizar(self, tela, ox, oy, template, confianca, regiao, cinza):
        return self.achados.get(template)

    def capturar_tela(self):
        return object(), 0, 0


class ImagensFakeScore(ImagensFake):
    def __init__(self, score=0.4, centro=(1, 2)):
        super().__init__({})
        self.score = score
        self.centro = centro

    def localizar_detalhado(self, tela, ox, oy, template, confianca, regiao, cinza):
        from nucleo import imagens

        return imagens.ResultadoBusca(
            centro=None,
            score=self.score,
            melhor_score=self.score,
            melhor_centro=self.centro,
        )


def _backend():
    from nucleo.backend import BackendFake

    return BackendFake()


def _rodar(p, cfg=None, imagens=None, **kwargs):
    faixa = {k: v for k, v in kwargs.items() if k in ("de", "ate")}
    construtor = {k: v for k, v in kwargs.items() if k not in ("de", "ate")}
    backend = _backend()
    ex = executor.Executor(
        p,
        backend,
        cfg or CFG,
        imagens=imagens or ImagensFake(),
        dormir_entre_acoes=False,
        **construtor,
    )
    relatorio = ex.rodar(**faixa)
    return relatorio, backend


def test_sequencia_simples():
    p = projeto.Projeto()
    p.adicionar("clicar", x=1, y=2, duracao=0)
    p.adicionar("digitar", texto="ab")
    p.adicionar("tecla", nome="enter")
    rel, backend = _rodar(p)
    assert rel.ok and rel.executados == 3
    assert backend.tipos() == ["clicar_em", "escrever", "escrever", "tecla"]
    assert backend.texto_digitado() == "ab"


def test_bloco_repetido():
    p = projeto.Projeto()
    p.adicionar("bloco_inicio", vezes=3)
    p.adicionar("tecla", nome="tab")
    p.adicionar("bloco_fim")
    rel, backend = _rodar(p)
    assert rel.ok
    assert backend.chamadas.count(("tecla", "tab", 1)) == 3
    assert rel.executados == 3


def test_blocos_aninhados():
    p = projeto.Projeto()
    p.adicionar("bloco_inicio", vezes=2)
    p.adicionar("bloco_inicio", vezes=2)
    p.adicionar("tecla", nome="a")
    p.adicionar("bloco_fim")
    p.adicionar("bloco_fim")
    rel, backend = _rodar(p)
    assert rel.ok
    assert backend.chamadas.count(("tecla", "a", 1)) == 4


def test_passo_desativado_e_ignorado():
    p = projeto.Projeto()
    p.adicionar("tecla", nome="a")
    p.adicionar("tecla", nome="b")
    p.passos[0].ativo = False
    rel, backend = _rodar(p)
    assert rel.ok
    assert backend.chamadas == [("tecla", "b", 1)]


def test_faixa_de_ate():
    p = projeto.Projeto()
    for nome in "abcd":
        p.adicionar("tecla", nome=nome)
    rel, backend = _rodar(p, de=1, ate=2)
    assert rel.ok and rel.executados == 2
    assert [c[1] for c in backend.chamadas] == ["b", "c"]


def test_imagem_encontrada_clica_com_offset():
    p = projeto.Projeto()
    p.adicionar("imagem_clicar", arquivo="ok.png", offset=[5, -2], duracao=0, timeout=0.05, tentativas=1)
    rel, backend = _rodar(p, imagens=ImagensFake({"ok.png": (100, 200)}))
    assert rel.ok
    assert backend.chamadas == [("clicar_em", 105, 198, "left", 1)]


def test_imagem_ausente_aborta():
    p = projeto.Projeto()
    p.adicionar("imagem_clicar", arquivo="ok.png", timeout=0.05, tentativas=1)
    p.adicionar("tecla", nome="a")
    rel, backend = _rodar(p, imagens=ImagensFake({}))
    assert not rel.ok
    assert rel.falha_indice == 0
    assert backend.chamadas == []


def test_imagem_ausente_com_fallback():
    p = projeto.Projeto()
    p.adicionar("imagem_clicar", arquivo="ok.png", fallback=[7, 8], duracao=0, timeout=0.05, tentativas=1)
    rel, backend = _rodar(p, imagens=ImagensFake({}))
    assert rel.ok
    assert backend.chamadas == [("clicar_em", 7, 8, "left", 1)]


def test_imagem_ausente_continuar():
    p = projeto.Projeto()
    p.adicionar("imagem_esperar", arquivo="ok.png", se_falhar="continuar", timeout=0.05, tentativas=1)
    p.adicionar("tecla", nome="a")
    rel, backend = _rodar(p, imagens=ImagensFake({}))
    assert rel.ok
    assert backend.chamadas == [("tecla", "a", 1)]


def test_imagem_esperar_sucesso_loga():
    p = projeto.Projeto()
    p.adicionar("imagem_esperar", arquivo="ok.png", timeout=0.1, tentativas=1)
    p.adicionar("tecla", nome="a")
    rel, backend = _rodar(p, imagens=ImagensFake({"ok.png": (10, 20)}))
    assert rel.ok
    assert backend.chamadas == [("tecla", "a", 1)]
    assert any("encontrada em (10, 20)" in e for e in rel.eventos)


def test_imagem_esperar_loga_melhor_score():
    p = projeto.Projeto()
    p.adicionar("imagem_esperar", arquivo="ok.png", timeout=0.05, tentativas=1)
    rel, _ = _rodar(p, imagens=ImagensFakeScore(score=0.42, centro=(7, 8)))
    assert not rel.ok
    assert "melhor score 0.42" in (rel.erro or "")
    assert any("Melhor score" in e for e in rel.eventos)


def test_arquivo_de_imagem_inexistente():
    p = projeto.Projeto()
    p.adicionar("imagem_clicar", arquivo="nao_existe.png")
    rel, _ = _rodar(p, imagens=ImagensFake({}, existentes=set()))
    assert not rel.ok
    assert "não existe" in (rel.erro or "")


def test_cancelamento_antes_de_rodar():
    p = projeto.Projeto()
    p.adicionar("tecla", nome="a")
    parar = threading.Event()
    parar.set()
    rel, backend = _rodar(p, parar=parar)
    assert rel.cancelado and not rel.ok
    assert backend.chamadas == []


def test_simulacao_nao_toca_backend():
    p = projeto.Projeto()
    p.adicionar("clicar", x=1, y=2, duracao=0)
    p.adicionar("digitar", texto="abc")
    rel, backend = _rodar(p, simular=True)
    assert rel.ok
    assert backend.chamadas == []


def test_projeto_vazio():
    rel, _ = _rodar(projeto.Projeto())
    assert not rel.ok and "nenhum passo" in (rel.erro or "")


def test_falha_em_um_passo_registra_indice():
    p = projeto.Projeto()
    p.adicionar("tecla", nome="a")
    p.adicionar("tecla", nome="b")
    p.passos[1].tipo = "tipo_inexistente"
    rel, _ = _rodar(p)
    assert not rel.ok and rel.falha_indice == 1
    assert "#2" in rel.resumo()


def test_digitar_com_tokens_de_tecla():
    p = projeto.Projeto()
    p.adicionar("digitar", texto="a{ENTER}b")
    rel, backend = _rodar(p)
    assert rel.ok
    digitacao = [c for c in backend.chamadas if c[0] in ("escrever", "tecla")]
    assert digitacao == [
        ("escrever", "a"),
        ("tecla", "enter", 1),
        ("escrever", "b"),
    ]
