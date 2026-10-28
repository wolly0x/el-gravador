from nucleo import passos


def test_dividir_texto_tokens():
    assert passos.dividir_texto("oi{ENTER}!") == [
        ("texto", "oi"),
        ("tecla", "enter"),
        ("texto", "!"),
    ]
    assert passos.dividir_texto("{enter}{TAB}") == [
        ("tecla", "enter"),
        ("tecla", "tab"),
    ]
    assert passos.dividir_texto("{F5}") == [("tecla", "f5")]


def test_dividir_texto_mantem_chaves_desconhecidas():
    assert passos.dividir_texto("a{foo}b") == [("texto", "a{foo}b")]
    assert passos.dividir_texto("{{ENTER}}") == [
        ("texto", "{"),
        ("tecla", "enter"),
        ("texto", "}"),
    ]
    assert passos.dividir_texto("") == []


def test_dividir_texto_aliases():
    assert passos.dividir_texto("{escape}") == [("tecla", "esc")]
    assert passos.dividir_texto("{Return}") == [("tecla", "enter")]
    assert passos.dividir_texto("{pgdn}") == [("tecla", "pagedown")]
