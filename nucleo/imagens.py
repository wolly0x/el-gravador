"""Captura de tela e biblioteca de templates de imagem.

Ponto único de captura: tudo (recorte, busca e clique) usa coordenadas
virtuais, então funciona com múltiplos monitores e com DPI awareness.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from . import caminhos

EXT = ".png"


class ErroImagem(RuntimeError):
    pass


@dataclass
class ResultadoBusca:
    """Resultado detalhado de uma busca por template."""

    centro: tuple[int, int] | None = None
    score: float = 0.0
    melhor_score: float = 0.0
    melhor_centro: tuple[int, int] | None = None


# ----------------------------------------------------------------------
# Manifesto
# ----------------------------------------------------------------------
def _manifesto_vazio() -> dict:
    return {"versao": 1, "templates": {}}


def carregar_manifesto() -> dict:
    caminho = caminhos.MANIFESTO
    if not caminho.exists():
        return _manifesto_vazio()
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
        if not isinstance(dados, dict) or not isinstance(dados.get("templates"), dict):
            return _manifesto_vazio()
        return dados
    except Exception:
        return _manifesto_vazio()


def _salvar_manifesto(dados: dict) -> None:
    caminhos.IMAGENS_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(caminhos.IMAGENS_DIR), prefix=".manifest_", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=2, ensure_ascii=False)
        os.replace(tmp, caminhos.MANIFESTO)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _hash_arquivo(caminho: Path) -> str:
    digest = hashlib.sha1()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(65536), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _hash_imagem(img) -> str:
    import io

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return hashlib.sha1(buffer.getvalue()).hexdigest()


# ----------------------------------------------------------------------
# Nomes e consultas
# ----------------------------------------------------------------------
def slug(texto: str, limite: int = 36) -> str:
    base = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_").lower()
    return (base or "template")[:limite]


def caminho(nome: str) -> Path:
    p = Path(nome)
    if p.is_absolute():
        return p
    return caminhos.IMAGENS_DIR / nome


def existe(nome: str) -> bool:
    return bool(nome) and caminho(nome).exists()


def regiao_template(nome: str) -> tuple[int, int, int, int] | None:
    """Região da tela onde o template foi capturado, se registrada."""
    if not nome:
        return None
    info = carregar_manifesto().get("templates", {}).get(Path(nome).name) or {}
    regiao = info.get("regiao")
    if not isinstance(regiao, (list, tuple)) or len(regiao) < 4:
        return None
    try:
        return (int(regiao[0]), int(regiao[1]), int(regiao[2]), int(regiao[3]))
    except (TypeError, ValueError):
        return None


def listar() -> list[dict[str, Any]]:
    """Templates disponíveis, do mais novo para o mais antigo."""
    caminhos.IMAGENS_DIR.mkdir(parents=True, exist_ok=True)
    manifesto = carregar_manifesto()["templates"]
    itens: list[dict[str, Any]] = []
    for arquivo in sorted(caminhos.IMAGENS_DIR.glob("*" + EXT)):
        if arquivo.name.startswith("."):
            continue
        info = manifesto.get(arquivo.name, {})
        itens.append(
            {
                "nome": arquivo.name,
                "caminho": arquivo,
                "criado": info.get("criado", ""),
                "largura": info.get("largura", 0),
                "altura": info.get("altura", 0),
                "janela": info.get("janela", ""),
                "mtime": arquivo.stat().st_mtime,
            }
        )
    itens.sort(key=lambda item: item["mtime"], reverse=True)
    return itens


_cache: dict[str, tuple[float, Any]] = {}


def carregar(nome: str):
    """Abre (com cache) o template como imagem PIL."""
    from PIL import Image

    arquivo = caminho(nome)
    if not arquivo.exists():
        raise ErroImagem(f'Imagem "{nome}" não encontrada em {arquivo.parent}')
    chave = str(arquivo)
    mtime = arquivo.stat().st_mtime
    em_cache = _cache.get(chave)
    if em_cache and em_cache[0] == mtime:
        return em_cache[1]
    with Image.open(arquivo) as img:
        imagem = img.convert("RGB")
    _cache[chave] = (mtime, imagem)
    return imagem


def limpar_cache() -> None:
    _cache.clear()


# ----------------------------------------------------------------------
# Criação / remoção
# ----------------------------------------------------------------------
def salvar_template(
    img,
    nome_base: str = "template",
    meta: dict[str, Any] | None = None,
) -> str:
    """Salva o recorte com nome legível. Reaproveita se for idêntico."""
    caminhos.IMAGENS_DIR.mkdir(parents=True, exist_ok=True)
    digest = _hash_imagem(img)
    manifesto = carregar_manifesto()

    for nome, info in manifesto["templates"].items():
        if info.get("hash") == digest and (caminhos.IMAGENS_DIR / nome).exists():
            return nome

    base = slug(nome_base)
    nome = f"{base}_{datetime.now():%Y%m%d_%H%M%S}{EXT}"
    arquivo = caminhos.IMAGENS_DIR / nome
    contador = 2
    while arquivo.exists():
        nome = f"{base}_{datetime.now():%Y%m%d_%H%M%S}_{contador}{EXT}"
        arquivo = caminhos.IMAGENS_DIR / nome
        contador += 1

    img.save(arquivo, format="PNG")
    registro = {
        "hash": digest,
        "criado": datetime.now().isoformat(timespec="seconds"),
        "largura": img.width,
        "altura": img.height,
    }
    if meta:
        registro.update({k: v for k, v in meta.items() if v is not None})
    manifesto["templates"][nome] = registro
    _salvar_manifesto(manifesto)
    _cache.pop(str(arquivo), None)
    return nome


def registrar(nome: str, **meta: Any) -> None:
    """Registra um template que já existe no disco (ex.: importado)."""
    arquivo = caminho(nome)
    if not arquivo.exists():
        return
    manifesto = carregar_manifesto()
    from PIL import Image

    with Image.open(arquivo) as img:
        largura, altura = img.size
    registro = manifesto["templates"].get(nome, {})
    registro.update(
        {
            "hash": _hash_arquivo(arquivo),
            "largura": largura,
            "altura": altura,
            "criado": registro.get("criado") or datetime.now().isoformat(timespec="seconds"),
            **{k: v for k, v in meta.items() if v is not None},
        }
    )
    manifesto["templates"][nome] = registro
    _salvar_manifesto(manifesto)


def remover(nome: str) -> bool:
    arquivo = caminho(nome)
    manifesto = carregar_manifesto()
    removido = False
    try:
        if arquivo.exists():
            arquivo.unlink()
            removido = True
    except OSError:
        return False
    if manifesto["templates"].pop(nome, None) is not None:
        _salvar_manifesto(manifesto)
    _cache.pop(str(arquivo), None)
    return removido


def orfaos(usados: list[str] | set[str]) -> list[str]:
    usados = set(usados)
    return [item["nome"] for item in listar() if item["nome"] not in usados]


def importar_pasta(origem: str | Path) -> tuple[int, int]:
    """Copia PNGs de outra pasta (ex.: o app antigo). Devolve (novos, iguais)."""
    pasta = Path(origem)
    if not pasta.is_dir():
        raise NotADirectoryError(str(pasta))
    caminhos.IMAGENS_DIR.mkdir(parents=True, exist_ok=True)
    manifesto = carregar_manifesto()
    hashes = {info.get("hash") for info in manifesto["templates"].values()}
    novos = iguais = 0
    for arquivo in sorted(pasta.glob("*.png")):
        digest = _hash_arquivo(arquivo)
        if digest in hashes:
            iguais += 1
            continue
        destino = caminhos.IMAGENS_DIR / arquivo.name
        contador = 2
        while destino.exists():
            destino = caminhos.IMAGENS_DIR / f"{arquivo.stem}_{contador}{EXT}"
            contador += 1
        shutil.copy2(arquivo, destino)
        from PIL import Image

        with Image.open(destino) as img:
            largura, altura = img.size
        manifesto["templates"][destino.name] = {
            "hash": digest,
            "criado": datetime.now().isoformat(timespec="seconds"),
            "largura": largura,
            "altura": altura,
            "importado": str(arquivo),
        }
        hashes.add(digest)
        novos += 1
    if novos:
        _salvar_manifesto(manifesto)
    return novos, iguais


def copiar_usados(usados: list[str], destino: str | Path) -> list[str]:
    """Copia os templates usados para <destino>/imagens_templates."""
    pasta_destino = Path(destino) / "imagens_templates"
    pasta_destino.mkdir(parents=True, exist_ok=True)
    ausentes: list[str] = []
    manifesto = carregar_manifesto()
    copiados = 0
    for nome in usados:
        origem = caminho(nome)
        if not origem.exists():
            ausentes.append(nome)
            continue
        alvo = pasta_destino / origem.name
        try:
            if origem.resolve() != alvo.resolve():
                shutil.copy2(origem, alvo)
                manifesto["templates"].setdefault(origem.name, {
                    "hash": _hash_arquivo(origem),
                    "criado": datetime.now().isoformat(timespec="seconds"),
                })
                copiados += 1
        except OSError:
            ausentes.append(nome)
    if copiados:
        try:
            with open(pasta_destino / "manifest.json", "w", encoding="utf-8") as f:
                json.dump(manifesto, f, indent=2, ensure_ascii=False)
        except OSError:
            pass
    return ausentes


# ----------------------------------------------------------------------
# Captura
# ----------------------------------------------------------------------
def capturar_tela():
    """Devolve (imagem PIL RGB, offset_x, offset_y) da área virtual."""
    try:
        from PIL import ImageGrab
    except ImportError as exc:  # pragma: no cover
        raise ErroImagem("Pillow não instalado (pip install pillow)") from exc

    if sys.platform == "win32":
        try:
            img = ImageGrab.grab(all_screens=True)
        except TypeError:  # Pillow muito antigo
            img = ImageGrab.grab()
        except Exception as exc:  # pragma: no cover
            raise ErroImagem(f"Falha ao capturar a tela: {exc}") from exc
    else:
        img = ImageGrab.grab()
        return img.convert("RGB"), 0, 0

    from .dpi import area_virtual

    x, y, _w, _h = area_virtual()
    return img.convert("RGB"), x, y


def recortar(img, x1: int, y1: int, x2: int, y2: int, ox: int = 0, oy: int = 0):
    """Recorta usando coordenadas virtuais (x1..x2, y1..y2)."""
    esquerda, direita = sorted((int(x1), int(x2)))
    topo, fundo = sorted((int(y1), int(y2)))
    esquerda, topo = max(0, esquerda - ox), max(0, topo - oy)
    direita = min(img.width, direita - ox)
    fundo = min(img.height, fundo - oy)
    if direita <= esquerda or fundo <= topo:
        raise ErroImagem("Região de recorte inválida (fora da tela?)")
    return img.crop((esquerda, topo, direita, fundo))


# ----------------------------------------------------------------------
# Busca
# ----------------------------------------------------------------------
def _numpy():
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover
        raise ErroImagem(
            "numpy é necessário para a busca por imagem (pip install numpy)"
        ) from exc
    return np


def _open_cv():
    try:
        import cv2
    except ImportError:
        return None
    return cv2


def localizar_detalhado(
    tela,
    ox: int,
    oy: int,
    template,
    confianca: float = 0.9,
    regiao: tuple[int, int, int, int] | None = None,
    cinza: bool = True,
) -> ResultadoBusca:
    """Como localizar(), mas devolve também o melhor score e o melhor ponto.

    O score é sempre preenchido (inclusive quando fica abaixo da confiança),
    para que o app consiga mostrar "melhor score 0.62" em vez de só falhar.
    """
    np = _numpy()
    if template.width > tela.width or template.height > tela.height:
        raise ErroImagem(
            f'Template {template.width}x{template.height} é maior que a tela '
            f'{tela.width}x{tela.height}'
        )

    area = tela
    ax, ay = ox, oy
    if regiao:
        rx, ry, rw, rh = regiao
        try:
            area = recortar(tela, rx, ry, rx + rw, ry + rh, ox, oy)
        except ErroImagem:
            return ResultadoBusca()
        ax, ay = int(rx), int(ry)

    cv2 = _open_cv()
    if cv2 is not None:
        alvo = np.asarray(area, dtype=np.uint8)
        agulha = np.asarray(template, dtype=np.uint8)
        if cinza:
            alvo = cv2.cvtColor(alvo, cv2.COLOR_RGB2GRAY)
            agulha = cv2.cvtColor(agulha, cv2.COLOR_RGB2GRAY)
        try:
            resultado = cv2.matchTemplate(alvo, agulha, cv2.TM_CCOEFF_NORMED)
            _minimo, maximo, _minloc, maxloc = cv2.minMaxLoc(resultado)
        except Exception as exc:
            raise ErroImagem(f"Falha ao comparar imagens: {exc}") from exc

        score = float(maximo) if math.isfinite(float(maximo)) else 0.0
        if not math.isfinite(score):
            score = 0.0
        melhor_centro = (
            ax + int(maxloc[0]) + template.width // 2,
            ay + int(maxloc[1]) + template.height // 2,
        )
        if score >= float(confianca):
            return ResultadoBusca(
                centro=melhor_centro,
                score=score,
                melhor_score=score,
                melhor_centro=melhor_centro,
            )
        return ResultadoBusca(
            centro=None,
            score=score,
            melhor_score=score,
            melhor_centro=melhor_centro,
        )

    # Sem OpenCV: só comparação exata.
    if float(confianca) < 0.999:
        raise ErroImagem(
            "Busca com confiança < 1.0 exige OpenCV. "
            "Instale com: pip install opencv-python-headless"
        )

    from numpy.lib.stride_tricks import sliding_window_view

    alvo = np.asarray(area.convert("RGB"), dtype=np.uint8)
    agulha = np.asarray(template.convert("RGB"), dtype=np.uint8)
    if alvo.shape[0] * alvo.shape[1] > 60_000_000:
        raise ErroImagem("Tela grande demais para busca exata sem OpenCV")
    janelas = sliding_window_view(alvo, agulha.shape[:2], axis=(0, 1))
    agulha_t = np.transpose(agulha, (2, 0, 1))
    iguais = np.all(janelas == agulha_t[None, None, :, :, :], axis=(2, 3, 4))
    posicoes = np.argwhere(iguais)
    if posicoes.size == 0:
        return ResultadoBusca()
    y, x = posicoes[0]
    centro = (
        ax + int(x) + template.width // 2,
        ay + int(y) + template.height // 2,
    )
    return ResultadoBusca(
        centro=centro,
        score=1.0,
        melhor_score=1.0,
        melhor_centro=centro,
    )


def localizar(
    tela,
    ox: int,
    oy: int,
    template,
    confianca: float = 0.9,
    regiao: tuple[int, int, int, int] | None = None,
    cinza: bool = True,
) -> tuple[int, int] | None:
    """Centro do template na tela, em coordenadas virtuais. None se não achou."""
    return localizar_detalhado(
        tela, ox, oy, template, confianca, regiao, cinza
    ).centro


def salvar_diagnostico(
    tela,
    template,
    resultado: ResultadoBusca,
    nome: str,
    *,
    ox: int = 0,
    oy: int = 0,
    confianca: float = 0.9,
    prefixo: str = "diag",
) -> Path | None:
    """Salva um PNG da tela com o melhor ponto encontrado e o score.

    Serve para responder "o que a busca estava vendo?" quando um template
    não é encontrado. Devolve o caminho salvo (ou None se não deu).
    """
    try:
        from PIL import ImageDraw

        caminhos.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        base = slug(Path(nome).stem, 40)
        destino = caminhos.LOGS_DIR / (
            f"{prefixo}_{base}_{datetime.now():%Y%m%d_%H%M%S}.png"
        )

        imagem = tela.convert("RGB").copy()
        desenho = ImageDraw.Draw(imagem)

        centro = resultado.melhor_centro
        if centro is not None:
            px = int(centro[0]) - int(ox)
            py = int(centro[1]) - int(oy)
            largura, altura = template.width, template.height
            esquerda = max(0, px - largura // 2)
            topo = max(0, py - altura // 2)
            direita = min(imagem.width - 1, esquerda + largura)
            fundo = min(imagem.height - 1, topo + altura)
            cor = (
                (0, 220, 120)
                if resultado.centro is not None
                else (255, 40, 80)
            )
            desenho.rectangle(
                (esquerda, topo, direita, fundo), outline=cor, width=3
            )
            desenho.line((px - 10, py, px + 10, py), fill=cor, width=2)
            desenho.line((px, py - 10, px, py + 10), fill=cor, width=2)

        texto = (
            f"{Path(nome).name}  |  score {resultado.melhor_score:.3f}"
            f" / confianca {float(confianca):.2f}"
        )
        caixa = desenho.textbbox((10, 8), texto)
        desenho.rectangle(
            (6, 4, caixa[2] + 8, caixa[3] + 6), fill=(0, 0, 0)
        )
        desenho.text((10, 8), texto, fill=(255, 255, 255))
        imagem.save(destino, format="PNG")

        # Mantém só os últimos 20 diagnósticos.
        antigos = sorted(
            caminhos.LOGS_DIR.glob("diag_*.png"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for velho in antigos[20:]:
            try:
                velho.unlink()
            except OSError:
                pass
        return destino
    except Exception:
        return None


def disponivel() -> dict[str, bool]:
    """Diagnóstico mostrado na UI."""
    estado = {"pillow": False, "numpy": False, "opencv": False}
    try:
        import PIL  # noqa: F401

        estado["pillow"] = True
    except ImportError:
        pass
    try:
        import numpy  # noqa: F401

        estado["numpy"] = True
    except ImportError:
        pass
    estado["opencv"] = _open_cv() is not None
    return estado
