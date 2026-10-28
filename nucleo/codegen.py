"""Geração do script Python autocontido (com runtime embutido)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from . import imagens, passos
from .projeto import Projeto

_RUNTIME = '''# -*- coding: utf-8 -*-
"""
__TITULO__

Gerado por El Gravador 18 Pro Max em __GERADO__
Passos: __PASSOS__  |  Repetições: __REPETICOES_TXT__

Atalhos durante a execução:
    ESC  -> cancelar
    F8   -> pausar / retomar

Não edite o bloco "runtime" abaixo se for regerar pelo gravador.
"""

import os
import random
import re
import sys
import time
import threading

import pyautogui
from pynput import keyboard

try:
    from PIL import ImageGrab
    _TEM_PIL = True
except ImportError:
    _TEM_PIL = False

try:
    import cv2
    import numpy as np
    _TEM_CV2 = True
except ImportError:
    _TEM_CV2 = False


pyautogui.PAUSE = 0
pyautogui.FAILSAFE = __FAILSAFE__

IMAGENS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'imagens_templates')

_parar = threading.Event()
_pausado = threading.Event()


class ExecucaoCancelada(Exception):
    """Pedido de parada pelo usuário."""


class PassoFalhou(Exception):
    """Falha que deve interromper o script."""


# ----------------------------------------------------------------------
# Controle
# ----------------------------------------------------------------------
def escutar_teclado(key):
    if key == keyboard.Key.esc:
        _parar.set()
    elif key == keyboard.Key.f8:
        if _pausado.is_set():
            _pausado.clear()
            print('\\n[>] RETOMADO')
        else:
            _pausado.set()
            print('\\n[||] PAUSADO')


def checar_pausa():
    while _pausado.is_set():
        time.sleep(0.1)
    if _parar.is_set():
        raise ExecucaoCancelada()


def dormir(segundos):
    """Pausa interrompível por ESC/F8."""
    final = time.monotonic() + max(0.0, float(segundos))
    while True:
        checar_pausa()
        restante = final - time.monotonic()
        if restante <= 0:
            return
        time.sleep(min(0.05, restante))


def _pausa_entre_acoes():
    base = __PAUSA_ACOES__
    if base <= 0:
        return
    if __PAUSA_VARIAVEL__:
        dormir(random.uniform(base * 0.6, base * 1.5))
    else:
        dormir(base)


_ALIAS_TECLAS = {'return': 'enter', 'escape': 'esc', 'del': 'delete',
                 'pgup': 'pageup', 'pgdn': 'pagedown', 'windows': 'win',
                 'print_screen': 'printscreen', 'prtsc': 'printscreen'}
_TOKENS_TEXTO = set('enter tab esc space backspace delete insert home end '
                    'pageup pagedown up down left right ctrl alt shift win '
                    'printscreen apps'.split())
_TOKENS_TEXTO.update('f%d' % i for i in range(1, 13))
_TOKENS_TEXTO.update('abcdefghijklmnopqrstuvwxyz0123456789')
_TOKENS_TEXTO.update(_ALIAS_TECLAS)


def _dividir_texto(texto):
    texto = str(texto)
    partes = []
    posicao = 0
    for achado in re.finditer(r'\\{([A-Za-z0-9_]+)\\}', texto):
        nome = achado.group(1).lower()
        if nome not in _TOKENS_TEXTO:
            continue
        if achado.start() > posicao:
            partes.append(('texto', texto[posicao:achado.start()]))
        partes.append(('tecla', _ALIAS_TECLAS.get(nome, nome)))
        posicao = achado.end()
    if posicao < len(texto):
        partes.append(('texto', texto[posicao:]))
    return partes


def digitar(texto, intervalo=None):
    checar_pausa()
    base = __INTERVALO_DIG__ if intervalo is None else float(intervalo)
    variavel = __DIG_VARIAVEL__
    controlador = None
    for tipo_parte, valor in _dividir_texto(texto):
        if tipo_parte == 'tecla':
            checar_pausa()
            pyautogui.press(valor)
            if base > 0:
                dormir(base)
            continue
        for posicao, letra in enumerate(valor):
            checar_pausa()
            try:
                pyautogui.write(letra)
            except Exception:
                if controlador is None:
                    from pynput.keyboard import Controller
                    controlador = Controller()
                controlador.type(letra)
            if variavel:
                delay = random.uniform(base * 0.7, base * 1.3)
            else:
                delay = base
            if delay > 0:
                dormir(delay)
            if variavel and letra in ' .,;:!?':
                dormir(random.uniform(0.04, 0.12))
            if variavel and letra == ' ' and posicao > 0 and posicao % 60 == 0:
                dormir(random.uniform(0.2, 0.5))


# ----------------------------------------------------------------------
# Imagens
# ----------------------------------------------------------------------
def _area_virtual():
    if sys.platform != 'win32':
        return 0, 0
    try:
        import ctypes
        gsm = ctypes.windll.user32.GetSystemMetrics
        return int(gsm(76)), int(gsm(77))
    except Exception:
        return 0, 0


def _capturar_tela():
    if not _TEM_PIL:
        raise PassoFalhou('Pillow não instalado (pip install pillow)')
    if sys.platform == 'win32':
        try:
            tela = ImageGrab.grab(all_screens=True)
        except TypeError:
            tela = ImageGrab.grab()
    else:
        tela = ImageGrab.grab()
        return tela.convert('RGB'), 0, 0
    ox, oy = _area_virtual()
    return tela.convert('RGB'), ox, oy


def _carregar_template(nome):
    from PIL import Image
    caminho = nome if os.path.isabs(nome) else os.path.join(IMAGENS_DIR, nome)
    if not os.path.exists(caminho):
        raise PassoFalhou('Imagem não encontrada: %s' % caminho)
    with Image.open(caminho) as img:
        return img.convert('RGB')


def _localizar(tela, ox, oy, template, confianca):
    if not _TEM_CV2:
        raise PassoFalhou(
            'Busca por imagem exige OpenCV (pip install opencv-python-headless)'
        )
    alvo = np.asarray(tela, dtype=np.uint8)
    agulha = np.asarray(template, dtype=np.uint8)
    if __CINZA__:
        alvo = cv2.cvtColor(alvo, cv2.COLOR_RGB2GRAY)
        agulha = cv2.cvtColor(agulha, cv2.COLOR_RGB2GRAY)
    resultado = cv2.matchTemplate(alvo, agulha, cv2.TM_CCOEFF_NORMED)
    _minimo, maximo, _minloc, maxloc = cv2.minMaxLoc(resultado)
    if maximo >= float(confianca):
        return (
            ox + maxloc[0] + template.width // 2,
            oy + maxloc[1] + template.height // 2,
        )
    return None


def esperar_imagem(nome, timeout=15, confidence=0.9, tentativas=2):
    template = _carregar_template(nome)
    for tentativa in range(1, max(1, int(tentativas)) + 1):
        final = time.monotonic() + float(timeout)
        print('[..] procurando "%s" (tentativa %d)' % (nome, tentativa))
        while time.monotonic() < final:
            checar_pausa()
            tela, ox, oy = _capturar_tela()
            achado = _localizar(tela, ox, oy, template, confidence)
            if achado is not None:
                print('[ok] "%s" encontrada em (%d, %d)'
                      % (nome, achado[0], achado[1]))
                return achado
            dormir(0.25)
    print('[!] "%s" não apareceu' % nome)
    return None


def esperar_imagem_desaparecer(nome, timeout=15, confidence=0.9, tentativas=2,
                               obrigatorio=True):
    template = _carregar_template(nome)
    for tentativa in range(1, max(1, int(tentativas)) + 1):
        final = time.monotonic() + float(timeout)
        while time.monotonic() < final:
            checar_pausa()
            tela, ox, oy = _capturar_tela()
            if _localizar(tela, ox, oy, template, confidence) is None:
                print('[ok] "%s" desapareceu' % nome)
                return True
            dormir(0.25)
    if obrigatorio:
        raise PassoFalhou('Imagem "%s" continua na tela' % nome)
    print('[!] "%s" continua na tela (seguindo em frente)' % nome)
    return False


def esperar_imagem_obrigatoria(nome, timeout=15, confidence=0.9, tentativas=2,
                               obrigatorio=True):
    alvo = esperar_imagem(nome, timeout=timeout, confidence=confidence,
                          tentativas=tentativas)
    if alvo is None:
        if obrigatorio:
            raise PassoFalhou('Imagem "%s" não apareceu em %.0fs'
                              % (nome, float(timeout)))
        print('[!] "%s" não apareceu (seguindo em frente)' % nome)
    return alvo


def esperar_e_clicar(nome, timeout=15, confidence=0.9, duration=1.0,
                     offset=(0, 0), cliques=1, botao='left',
                     tentativas=2, obrigatorio=True, fallback=None):
    alvo = esperar_imagem(nome, timeout=timeout, confidence=confidence,
                          tentativas=tentativas)
    if alvo is None:
        if fallback is not None:
            print('[!] "%s" não apareceu; usando coordenada reserva %s'
                  % (nome, fallback))
            x, y = int(fallback[0]), int(fallback[1])
        elif obrigatorio:
            raise PassoFalhou('Imagem "%s" não encontrada em %.0fs'
                              % (nome, float(timeout)))
        else:
            print('[!] "%s" não apareceu (seguindo em frente)' % nome)
            return False
    else:
        x, y = alvo
    x += int(offset[0])
    y += int(offset[1])
    pyautogui.moveTo(x, y, duration=float(duration),
                     tween=pyautogui.easeInOutQuad)
    pyautogui.click(clicks=max(1, int(cliques)), interval=0.05, button=botao)
    return True


# ----------------------------------------------------------------------
# Fluxo gravado
# ----------------------------------------------------------------------
def executar_bloco():
__CORPO__

# ----------------------------------------------------------------------
# Entrada
# ----------------------------------------------------------------------
def _habilitar_dpi():
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def iniciar():
    _habilitar_dpi()
    print('=' * 56)
    print('  __TITULO__')
    print('  Gerado por El Gravador 18 Pro Max')
    print('  [ESC] parar  |  [F8] pausar/retomar')
    print('=' * 56)
    print('Iniciando em __TEMPO_INICIO__ segundos...')
    time.sleep(__TEMPO_INICIO__)

    ouvinte = keyboard.Listener(on_press=escutar_teclado)
    ouvinte.daemon = True
    ouvinte.start()

__LOOP__

    print('\\nConcluído com sucesso!')


if __name__ == '__main__':
    try:
        iniciar()
    except ExecucaoCancelada:
        print('\\n[!] Execução CANCELADA pelo usuário.')
    except PassoFalhou as exc:
        print('\\n[!] FALHA: %s' % exc)
        sys.exit(1)
    except KeyboardInterrupt:
        print('\\n[!] Interrompido pelo teclado.')
        sys.exit(1)
'''


def _literal(valor: Any) -> str:
    if isinstance(valor, bool):
        return "True" if valor else "False"
    if isinstance(valor, (int, float)):
        return repr(valor)
    return repr(str(valor))


def gerar_codigo(projeto: Projeto, cfg: Mapping[str, Any]) -> str:
    ctx = passos.Contexto(
        timeout_imagem=float(cfg.get("timeout_imagem", 15)),
        confianca_imagem=float(cfg.get("confianca_imagem", 0.9)),
        tentativas_imagem=max(1, int(cfg.get("tentativas_imagem", 2))),
    )

    corpo: list[str] = []
    nivel = 1
    aberto = 0

    def escrever(linha: str) -> None:
        corpo.append("    " * nivel + linha)

    for indice, passo in enumerate(projeto.passos):
        if not passo.ativo:
            escrever(f"# Passo {indice + 1} (desativado): {passo.rotulo}")
            continue
        if passo.tipo == "bloco_inicio":
            vezes = max(1, int(passo.params.get("vezes", 1)))
            nota = str(passo.params.get("nota") or "").strip()
            escrever(f"# Bloco repetido {vezes}x" + (f" — {nota}" if nota else ""))
            escrever(f"for _ in range({vezes}):")
            nivel += 1
            aberto += 1
            continue
        if passo.tipo == "bloco_fim":
            if aberto > 0:
                nivel = max(1, nivel - 1)
                aberto -= 1
            else:
                escrever("# FIM de bloco sem INÍCIO (ignorado)")
            continue

        if passo.tipo != "comentario":
            escrever(f"# Passo {indice + 1}: {passo.rotulo}")
        escrever("checar_pausa()")
        for linha in passos.emitir(passo.tipo, passo.params, ctx):
            escrever(linha)
        escrever("_pausa_entre_acoes()")

    if not corpo:
        corpo.append("    pass")
    while aberto > 0:
        nivel = max(1, nivel - 1)
        aberto -= 1
    # Um bloco vazio precisa de "pass".
    corpo = _preencher_blocos_vazios(corpo)

    repeticoes = projeto.repeticao()
    if repeticoes == 0:
        loop = (
            "    i = 1\n"
            "    while True:\n"
            "        print('-- Loop %d (infinito) --' % i)\n"
            "        executar_bloco()\n"
            "        i += 1"
        )
        rep_txt = "infinita"
    else:
        loop = (
            f"    for i in range(1, {repeticoes} + 1):\n"
            f"        print('-- Repetição %d de {repeticoes} --' % i)\n"
            "        executar_bloco()"
        )
        rep_txt = f"{repeticoes}x"

    runtime = (
        _RUNTIME.replace("__TITULO__", projeto.nome or "Script El Gravador")
        .replace("__GERADO__", datetime.now().strftime("%d/%m/%Y %H:%M"))
        .replace("__PASSOS__", str(len(projeto.passos)))
        .replace("__REPETICOES_TXT__", rep_txt)
        .replace("__CORPO__", "\n".join(corpo))
        .replace("__LOOP__", loop)
        .replace("__TEMPO_INICIO__", str(int(cfg.get("tempo_inicio", 3))))
        .replace("__FAILSAFE__", _literal(bool(cfg.get("failsafe_ativo", True))))
        .replace("__INTERVALO_DIG__", _literal(float(cfg.get("intervalo_digitacao", 0.08))))
        .replace("__DIG_VARIAVEL__", _literal(bool(cfg.get("intervalo_digitacao_variavel", True))))
        .replace("__PAUSA_ACOES__", _literal(float(cfg.get("pausa_entre_acoes", 0.3))))
        .replace("__PAUSA_VARIAVEL__", _literal(bool(cfg.get("pausa_entre_acoes_variavel", True))))
        .replace("__CINZA__", _literal(bool(cfg.get("imagem_cinza", True))))
    )
    return runtime


def _preencher_blocos_vazios(corpo: list[str]) -> list[str]:
    """Adiciona 'pass' quando um 'for' não tem corpo."""
    resultado: list[str] = []
    for i, linha in enumerate(corpo):
        resultado.append(linha)
        if linha.strip().startswith("for ") and linha.rstrip().endswith(":"):
            proxima = corpo[i + 1] if i + 1 < len(corpo) else ""
            atual_indent = len(linha) - len(linha.lstrip())
            prox_indent = len(proxima) - len(proxima.lstrip()) if proxima.strip() else -1
            if not proxima.strip() or prox_indent <= atual_indent:
                resultado.append("    " * (atual_indent // 4 + 1) + "pass")
    return resultado


def exportar(
    projeto: Projeto,
    destino: str | Path,
    cfg: Mapping[str, Any],
    copiar_imagens: bool = True,
) -> dict[str, Any]:
    """Escreve o .py, o sidecar do projeto e copia os templates usados."""
    caminho = Path(destino)
    if caminho.suffix.lower() != ".py":
        caminho = caminho.with_suffix(".py")
    caminho.parent.mkdir(parents=True, exist_ok=True)

    codigo = gerar_codigo(projeto, cfg)
    caminho.write_text(codigo, encoding="utf-8")

    sidecar = caminho.with_name(caminho.stem + ".elgravador.json")
    try:
        sidecar.write_text(
            json.dumps(projeto.para_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        sidecar = None  # type: ignore[assignment]

    ausentes: list[str] = []
    if copiar_imagens:
        usados = projeto.templates_usados()
        if usados:
            ausentes = imagens.copiar_usados(usados, caminho.parent)

    return {
        "script": caminho,
        "sidecar": sidecar,
        "templates_ausentes": ausentes,
        "templates": projeto.templates_usados(),
    }
