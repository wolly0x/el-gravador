"""Regressão da ponte JavaScript <-> Python do PyWebView.

O pywebview descobre os métodos expostos inspecionando os atributos públicos
do objeto ``js_api``. Qualquer atributo público que seja um objeto (janela,
backend, locks...) acaba serializado pelo motor da janela, gerando enxurradas
de erros do tipo ``maximum recursion depth exceeded`` em ``window.native``.

Por isso, tudo que for interno precisa começar com ``_``. Este teste trava
esse contrato.
"""

from __future__ import annotations

import inspect

from ui.web_app import Api, _geometria_inicial


class BackendFake:
    def __init__(self) -> None:
        self.chamadas: list[tuple[str, dict | None, float | None]] = []

    def requisitar(self, comando, args=None, timeout=None):
        self.chamadas.append((comando, args, timeout))
        return {"ok": True, "comando": comando, "args": args}


def test_api_nao_expoe_atributos_publicos_nao_chamaveis():
    api = Api(BackendFake())  # type: ignore[arg-type]

    publicos = {
        nome: valor
        for nome, valor in vars(api).items()
        if not nome.startswith("_")
    }
    assert publicos == {}, (
        "Atributos públicos em Api são introspeccionados pelo pywebview e "
        f"causam recursão: {sorted(publicos)}"
    )


def test_api_expoe_somente_metodos_publicos_chamaveis():
    api = Api(BackendFake())  # type: ignore[arg-type]

    publicos = {
        nome: valor
        for nome, valor in inspect.getmembers(api)
        if not nome.startswith("_")
    }
    # pywebview recursiona em qualquer atributo público que não seja um
    # método/função — e é nessa recursão que ``native`` estourava a pilha.
    inseguros = {
        nome: valor
        for nome, valor in publicos.items()
        if not (inspect.ismethod(valor) or inspect.isfunction(valor))
    }
    assert inseguros == {}, (
        "Atributos públicos não-função são introspeccionados pelo pywebview: "
        f"{sorted(inseguros)}"
    )

    # A superfície pública é intencionalmente pequena.
    assert set(publicos) >= {"state", "call", "hide_window", "show_window"}


def test_api_nao_tem_properties_publicas():
    """Uma property pública também seria executada na introspecção."""
    publicas = [
        nome
        for nome, valor in vars(Api).items()
        if not nome.startswith("_") and isinstance(valor, property)
    ]
    assert publicas == []


def test_api_state_e_call_delegam_ao_backend():
    backend = BackendFake()
    api = Api(backend)  # type: ignore[arg-type]

    assert api.state() == {"ok": True, "comando": "state", "args": None}
    assert api.call("save_project", {"nome": "x"}) == {
        "ok": True,
        "comando": "save_project",
        "args": {"nome": "x"},
    }
    assert backend.chamadas[0][0] == "state"
    assert backend.chamadas[1] == ("save_project", {"nome": "x"}, 60)


def test_api_janela_sem_window_nao_quebra():
    api = Api(BackendFake())  # type: ignore[arg-type]

    assert api.hide_window() == {"ok": True}
    assert api.show_window() == {"ok": True}
    assert api.cancelar_fechamento() == {"ok": True}
    # Sem janela criada, o fechamento nativo é liberado.
    assert api.ao_fechar() is True


def test_geometria_compacta_fora_do_windows():
    tamanho = _geometria_inicial()
    assert tamanho == {"width": 1140, "height": 740}
