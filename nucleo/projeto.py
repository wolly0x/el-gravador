"""Modelo de dados: Passo e Projeto (persistência em JSON)."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from . import passos

VERSAO = 1


def _novo_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class Passo:
    tipo: str
    params: dict[str, Any] = field(default_factory=dict)
    ativo: bool = True
    id: str = field(default_factory=_novo_id)

    def para_dict(self) -> dict:
        return {
            "id": self.id,
            "tipo": self.tipo,
            "params": self.params,
            "ativo": self.ativo,
        }

    @classmethod
    def de_dict(cls, dados: dict) -> "Passo":
        tipo = str(dados.get("tipo", ""))
        params = dados.get("params")
        if not isinstance(params, dict):
            params = {}
        # Completa chaves ausentes com os padrões do tipo (upgrade suave).
        if tipo in passos.TIPOS:
            base = passos.TIPOS[tipo].padrao()
            base.update(params)
            params = base
        return cls(
            tipo=tipo,
            params=params,
            ativo=bool(dados.get("ativo", True)),
            id=str(dados.get("id") or _novo_id()),
        )

    @property
    def rotulo(self) -> str:
        return passos.rotulo(self.tipo, self.params)

    def copiar(self, novo_id: bool = True) -> "Passo":
        return Passo(
            tipo=self.tipo,
            params=json.loads(json.dumps(self.params, ensure_ascii=False)),
            ativo=self.ativo,
            id=_novo_id() if novo_id else self.id,
        )


class Projeto:
    def __init__(self, nome: str = "novo_projeto"):
        self.nome = nome
        self.passos: list[Passo] = []
        self.config: dict[str, Any] = {}
        self.caminho: Path | None = None
        self.alterado = False

    # ------------------------------------------------------------------
    # Persistência
    # ------------------------------------------------------------------
    def para_dict(self) -> dict:
        return {
            "versao": VERSAO,
            "nome": self.nome,
            "salvo_em": datetime.now().isoformat(timespec="seconds"),
            "config": self.config,
            "passos": [p.para_dict() for p in self.passos],
        }

    @classmethod
    def de_dict(cls, dados: dict, nome: str | None = None) -> "Projeto":
        projeto = cls(nome=nome or str(dados.get("nome") or "projeto"))
        projeto.config = dict(dados.get("config") or {})
        itens = dados.get("passos")
        if isinstance(itens, list):
            for item in itens:
                if isinstance(item, dict):
                    projeto.passos.append(Passo.de_dict(item))
        return projeto

    def salvar(self, caminho: Path | str | None = None) -> Path:
        destino = Path(caminho) if caminho else self.caminho
        if destino is None:
            raise ValueError("Nenhum caminho de projeto definido")
        destino = destino.with_suffix(".json")
        destino.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(destino.parent), prefix=".proj_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.para_dict(), f, indent=2, ensure_ascii=False)
            os.replace(tmp, destino)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        self.caminho = destino
        if not self.nome or self.nome == "novo_projeto":
            self.nome = destino.stem
        self.alterado = False
        return destino

    @classmethod
    def carregar(cls, caminho: Path | str) -> "Projeto":
        origem = Path(caminho)
        with open(origem, "r", encoding="utf-8") as f:
            dados = json.load(f)
        if isinstance(dados, list):
            dados = {"passos": dados}
        if not isinstance(dados, dict):
            raise ValueError("Arquivo de projeto inválido")
        projeto = cls.de_dict(dados, nome=origem.stem)
        projeto.caminho = origem
        projeto.alterado = False
        return projeto

    # ------------------------------------------------------------------
    # Edição
    # ------------------------------------------------------------------
    def adicionar(self, tipo: str, posicao: int | None = None, **params: Any) -> Passo:
        passo = Passo(tipo=tipo, params=passos.criar(tipo, **params))
        self.inserir(passo, posicao)
        return passo

    def inserir(self, passo: Passo, posicao: int | None = None) -> int:
        if posicao is None or posicao < 0 or posicao > len(self.passos):
            posicao = len(self.passos)
        self.passos.insert(posicao, passo)
        self.alterado = True
        return posicao

    def remover(self, indice: int) -> Passo | None:
        if 0 <= indice < len(self.passos):
            self.alterado = True
            return self.passos.pop(indice)
        return None

    def remover_ultimo(self) -> Passo | None:
        return self.remover(len(self.passos) - 1)

    def mover(self, origem: int, destino: int) -> bool:
        if not (0 <= origem < len(self.passos)):
            return False
        destino = max(0, min(len(self.passos) - 1, destino))
        if origem == destino:
            return False
        passo = self.passos.pop(origem)
        self.passos.insert(destino, passo)
        self.alterado = True
        return True

    def duplicar(self, indice: int) -> Passo | None:
        if not (0 <= indice < len(self.passos)):
            return None
        copia = self.passos[indice].copiar()
        self.passos.insert(indice + 1, copia)
        self.alterado = True
        return copia

    def alternar_ativo(self, indice: int) -> None:
        if 0 <= indice < len(self.passos):
            self.passos[indice].ativo = not self.passos[indice].ativo
            self.alterado = True

    def limpar(self) -> None:
        self.passos.clear()
        self.alterado = True

    def substituir(self, indice: int, tipo: str, params: dict) -> None:
        if 0 <= indice < len(self.passos):
            base = passos.criar(tipo)
            base.update(params)
            self.passos[indice].tipo = tipo
            self.passos[indice].params = base
            self.alterado = True

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self.passos)

    def __iter__(self) -> Iterator[Passo]:
        return iter(self.passos)

    def templates_usados(self) -> list[str]:
        usados: list[str] = []
        for passo in self.passos:
            if passo.tipo.startswith("imagem_"):
                nome = passo.params.get("arquivo")
                if nome and nome not in usados:
                    usados.append(str(nome))
        return usados

    def repeticao(self) -> int:
        try:
            return max(0, int(self.config.get("repeticoes", 1)))
        except (TypeError, ValueError):
            return 1

    def validar(self) -> list[str]:
        """Problemas que impedem uma execução confiável."""
        problemas: list[str] = []
        pilha: list[int] = []
        for indice, passo in enumerate(self.passos):
            numero = indice + 1
            if passo.tipo not in passos.TIPOS:
                problemas.append(f"Passo #{numero}: tipo desconhecido '{passo.tipo}'")
                continue
            if passo.tipo == "bloco_inicio":
                pilha.append(numero)
            elif passo.tipo == "bloco_fim":
                if not pilha:
                    problemas.append(f"Passo #{numero}: FIM de bloco sem INÍCIO")
                else:
                    pilha.pop()
            elif passo.tipo == "digitar" and not str(passo.params.get("texto", "")):
                problemas.append(f"Passo #{numero}: texto vazio")
            elif passo.tipo.startswith("imagem_") and not passo.params.get("arquivo"):
                problemas.append(f"Passo #{numero}: imagem não definida")
        if pilha:
            problemas.append(f"Bloco aberto no passo #{pilha[-1]} sem FIM")
        return problemas
