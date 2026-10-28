import ast
from pathlib import Path

import pytest

from nucleo import legado

LEGADO_DIR = Path("/media/sf_PROJETOS/projeto_004/AUTOMACAO_EL_GRAVADOR/parte1.py")


def test_importa_script_real():
    if not LEGADO_DIR.exists():
        pytest.skip("script de exemplo não disponível")
    p, avisos = legado.importar_script(LEGADO_DIR)
    assert len(p) > 10
    tipos = [passo.tipo for passo in p]
    assert "imagem_clicar" in tipos
    assert "digitar" in tipos
    assert "tecla" in tipos
    assert tipos.count("imagem_clicar") > 5
    # O loop do script antigo vai para config, sem multiplicar passos.
    assert p.repeticao() == 1
    total = len(p)
    p2, _ = legado.importar_script(LEGADO_DIR)
    assert len(p2) == total
    assert all(passo.tipo in __import__("nucleo.passos", fromlist=["TIPOS"]).TIPOS for passo in p)


def test_importa_loop_como_bloco(tmp_path):
    fonte = '''
import time, pyautogui

def executar_bloco():
    for i in range(3):
        pyautogui.moveTo(10, 20, duration=1.0)
        pyautogui.click()
        digitar('oi')
    pyautogui.press('enter')

def iniciar():
    time.sleep(2)
    for i in range(1, 4 + 1):
        executar_bloco()
'''
    arquivo = tmp_path / "loop.py"
    arquivo.write_text(fonte, encoding="utf-8")
    p, avisos = legado.importar_script(arquivo)
    assert [x.tipo for x in p] == [
        "bloco_inicio", "clicar", "digitar", "bloco_fim", "tecla",
    ]
    assert p.passos[0].params["vezes"] == 3
    assert p.repeticao() == 4
    assert p.validar() == []


def test_importa_infinito(tmp_path):
    fonte = '''
def executar_bloco():
    digitar('x')

def iniciar():
    while True:
        executar_bloco()
'''
    arquivo = tmp_path / "inf.py"
    arquivo.write_text(fonte, encoding="utf-8")
    p, _ = legado.importar_script(arquivo)
    assert p.repeticao() == 0


def test_sidecar_tem_prioridade(tmp_path):
    from nucleo import projeto

    p = projeto.Projeto("origem")
    p.adicionar("pausa", segundos=2)
    script = tmp_path / "x.py"
    script.write_text("def executar_bloco():\n    pass\n", encoding="utf-8")
    side = tmp_path / "x.elgravador.json"
    side.write_text(__import__("json").dumps(p.para_dict()), encoding="utf-8")
    lido, avisos = legado.importar_script(script)
    assert len(lido) == 1
    assert "sidecar" in avisos[0]


def test_script_incompativel(tmp_path):
    arquivo = tmp_path / "nada.py"
    arquivo.write_text("print('oi')", encoding="utf-8")
    with pytest.raises(ValueError):
        legado.importar_script(arquivo)


def test_python_invalido(tmp_path):
    arquivo = tmp_path / "invalido.py"
    arquivo.write_text("def (:", encoding="utf-8")
    with pytest.raises(ValueError):
        legado.importar_script(arquivo)


def test_importa_pyautogui_write(tmp_path):
    fonte = """
import pyautogui

def executar_bloco():
    pyautogui.write("ola mundo")
    pyautogui.typewrite("linha 2")
"""
    arquivo = tmp_path / "write.py"
    arquivo.write_text(fonte, encoding="utf-8")
    p, avisos = legado.importar_script(arquivo)
    assert [x.tipo for x in p] == ["digitar", "digitar"]
    assert p.passos[0].params["texto"] == "ola mundo"
    assert p.passos[1].params["texto"] == "linha 2"
    assert avisos == []
