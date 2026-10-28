from nucleo import gravador
from nucleo.gravador import Evento, converter

CFG = {
    "registrar_movimento": False,
    "registrar_recorte": False,
    "registrar_pausas": False,
    "pausa_minima_registro": 1.5,
    "intervalo_digitacao": 0.08,
    "timeout_imagem": 12,
    "confianca_imagem": 0.9,
    "tentativas_imagem": 2,
}


def _press(t, x=100, y=100, botao="left", recorte=None):
    return Evento(t, "press", x=x, y=y, botao=botao, recorte=recorte)


def _release(t, x=100, y=100, botao="left"):
    return Evento(t, "release", x=x, y=y, botao=botao)


def test_clique_simples():
    passos = converter([_press(0.0), _release(0.05)], CFG)
    assert len(passos) == 1
    assert passos[0].tipo == "clicar"
    assert passos[0].params["x"] == 100
    assert passos[0].params["cliques"] == 1


def test_duplo_clique():
    eventos = [
        _press(0.0), _release(0.05),
        _press(0.10), _release(0.15),
    ]
    passos = converter(eventos, CFG)
    assert len(passos) == 1
    assert passos[0].params["cliques"] == 2


def test_cliques_separados():
    eventos = [_press(0.0), _release(0.05), _press(1.0), _release(1.05)]
    passos = converter(eventos, CFG)
    assert len(passos) == 2
    assert all(p.params["cliques"] == 1 for p in passos)


def test_drag():
    eventos = [
        _press(0.0, 10, 10),
        Evento(0.2, "move", x=50, y=50),
        _release(0.5, 120, 90),
    ]
    passos = converter(eventos, CFG)
    assert len(passos) == 1
    assert passos[0].tipo == "arrastar"
    assert passos[0].params["x1"] == 10
    assert passos[0].params["x2"] == 120


def test_digitacao_agrupada():
    eventos = [
        Evento(0.0, "keydown", tecla="o"),
        Evento(0.1, "keydown", tecla="l"),
        Evento(0.2, "keydown", tecla="a"),
    ]
    passos = converter(eventos, CFG)
    assert len(passos) == 1
    assert passos[0].tipo == "digitar"
    assert passos[0].params["texto"] == "ola"


def test_backspace_corrige_texto():
    eventos = [
        Evento(0.0, "keydown", tecla="o"),
        Evento(0.1, "keydown", tecla="l"),
        Evento(0.2, "keydown", tecla="a"),
        Evento(0.3, "keydown", tecla="backspace", especial=True),
        Evento(0.4, "keydown", tecla="x"),
    ]
    passos = converter(eventos, CFG)
    assert len(passos) == 1
    assert passos[0].params["texto"] == "olx"


def test_ctrl_c_vira_atalho():
    eventos = [
        Evento(0.0, "keydown", tecla="ctrl", especial=True),
        Evento(0.1, "keydown", tecla="c"),
        Evento(0.2, "keyup", tecla="c"),
        Evento(0.3, "keyup", tecla="ctrl", especial=True),
    ]
    passos = converter(eventos, CFG)
    assert len(passos) == 1
    assert passos[0].tipo == "atalho"
    assert passos[0].params["teclas"] == ["ctrl", "c"]


def test_enter_vira_tecla():
    eventos = [Evento(0.0, "keydown", tecla="enter", especial=True)]
    passos = converter(eventos, CFG)
    assert passos[0].tipo == "tecla"
    assert passos[0].params["nome"] == "enter"


def test_scroll_acumulado():
    eventos = [
        Evento(0.0, "scroll", x=5, y=5, dy=1),
        Evento(0.1, "scroll", x=5, y=5, dy=1),
        Evento(0.2, "scroll", x=5, y=5, dy=1),
    ]
    passos = converter(eventos, CFG)
    assert len(passos) == 1
    assert passos[0].tipo == "rolar"
    assert passos[0].params["quantidade"] == 3


def test_recorte_vira_imagem_com_fallback():
    chamadas = []

    def salvar(img, nome_base, meta=None):
        chamadas.append((img, nome_base, meta))
        return "recorte.png"

    from types import SimpleNamespace

    falsa = SimpleNamespace(width=120, height=60)
    eventos = [
        _press(0.0, recorte={"img": falsa, "dx": 2, "dy": -3}),
        _release(0.05),
    ]
    passos = converter(eventos, CFG, titulo="Cadastro", salvar_template=salvar)
    assert len(passos) == 1
    assert passos[0].tipo == "imagem_clicar"
    assert passos[0].params["arquivo"] == "recorte.png"
    assert passos[0].params["fallback"] == [100, 100]
    assert passos[0].params["offset"] == [2, -3]
    assert chamadas[0][1].startswith("Cadastro")


def test_pausas_opcionais():
    cfg = dict(CFG, registrar_pausas=True)
    eventos = [_press(0.0), _release(0.05), _press(3.0), _release(3.05)]
    passos = converter(eventos, cfg)
    assert [p.tipo for p in passos] == ["clicar", "pausa", "clicar"]
    assert passos[1].params["segundos"] == 3.0


def test_movimento_opcional():
    cfg = dict(CFG, registrar_movimento=True)
    eventos = [
        Evento(0.0, "move", x=10, y=10),
        Evento(0.2, "move", x=80, y=40),
        Evento(0.4, "move", x=150, y=90),
    ]
    passos = converter(eventos, cfg)
    assert len(passos) == 1
    assert passos[0].tipo == "mover"
    assert (passos[0].params["x"], passos[0].params["y"]) == (150, 90)


def test_eventos_mantem_ordem_cronologica():
    eventos = [
        _press(2.0), _release(2.05),
        _press(0.0), _release(0.05),
        Evento(1.0, "keydown", tecla="a"),
    ]
    passos = converter(eventos, CFG)
    assert [p.tipo for p in passos] == ["clicar", "digitar", "clicar"]
