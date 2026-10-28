"""Configuração persistida (JSON) com migração do app antigo."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from . import caminhos, tema

VERSAO = 1

PADROES: dict[str, Any] = {
    "versao": VERSAO,
    # aparência (tema fixo no Apple Glass; sem customização de cores)
    "tema": "Apple Glass",
    "fonte": "Segoe UI",
    "tamanho_fonte": 9,
    "fator_zoom": 1.0,
    "escala_web": 15,
    "cores_custom": {},
    # tempo
    "duracao_movimento": 1.2,
    "duracao_movimento_imagem": 1.0,
    "pausa_comandos": 0.3,
    "tempo_inicio": 3,
    # segurança
    "failsafe_ativo": True,
    "ao_falhar": "abortar",  # abortar | continuar
    # busca por imagem
    "timeout_imagem": 15,
    "confianca_imagem": 0.9,
    "tentativas_imagem": 2,
    "imagem_cinza": True,
    # digitação / fluidez
    "intervalo_digitacao": 0.08,
    "intervalo_digitacao_variavel": True,
    "pausa_entre_acoes": 0.3,
    "pausa_entre_acoes_variavel": True,
    # gravação automática
    "registrar_movimento": False,
    "registrar_recorte": False,
    "recorte_largura": 120,
    "recorte_altura": 60,
    "registrar_pausas": False,
    "pausa_minima_registro": 1.5,
    # execução
    "repeticoes": 1,
    "simular": False,
}

# Chaves do config.json antigo que têm equivalente direto.
_MAPA_ANTIGO = {
    "fonte": "fonte",
    "tamanho_fonte": "tamanho_fonte",
    "fator_zoom": "fator_zoom",
    "duracao_movimento": "duracao_movimento",
    "duracao_movimento_imagem": "duracao_movimento_imagem",
    "pausa_comandos": "pausa_comandos",
    "tempo_inicio": "tempo_inicio",
    "failsafe_ativo": "failsafe_ativo",
    "timeout_imagem": "timeout_imagem",
    "confianca_imagem": "confianca_imagem",
    "intervalo_digitacao": "intervalo_digitacao",
    "intervalo_digitacao_variavel": "intervalo_digitacao_variavel",
    "pausa_entre_acoes": "pausa_entre_acoes",
    "pausa_entre_acoes_variavel": "pausa_entre_acoes_variavel",
}


def _salvar_atomico(caminho: Path, dados: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(caminho.parent), prefix=".cfg_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=4, ensure_ascii=False)
        os.replace(tmp, caminho)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class Config:
    """Acesso simples a um dicionário de configuração com persistência."""

    def __init__(self, caminho: Path | str | None = None):
        self.caminho = Path(caminho) if caminho else caminhos.CONFIG_FILE
        self.dados: dict[str, Any] = dict(PADROES)
        self.avisos: list[str] = []

    # ------------------------------------------------------------------
    def get(self, chave: str, padrao: Any = None) -> Any:
        return self.dados.get(chave, PADROES.get(chave, padrao))

    def set(self, chave: str, valor: Any) -> None:
        self.dados[chave] = valor

    def __getitem__(self, chave: str) -> Any:
        return self.get(chave)

    def __setitem__(self, chave: str, valor: Any) -> None:
        self.set(chave, valor)

    def atualizar(self, valores: dict[str, Any]) -> None:
        self.dados.update(valores)

    def paleta(self) -> dict[str, str]:
        return tema.paleta(self.get("tema"), self.get("cores_custom") or {})

    # ------------------------------------------------------------------
    def carregar(self) -> None:
        origem = self.caminho
        if not origem.exists():
            origem = self._procurar_legado()
            if origem is None:
                return
        try:
            with open(origem, "r", encoding="utf-8") as f:
                bruto = json.load(f)
        except Exception as exc:
            self.avisos.append(f"Configuração ilegível ({exc}); usando padrões.")
            return
        if not isinstance(bruto, dict):
            self.avisos.append("Configuração inválida; usando padrões.")
            return
        self._migrar(bruto)
        if origem != self.caminho:
            self.avisos.append(
                f"Configuração importada do app antigo: {origem}"
            )
            try:
                self.salvar()
            except OSError:
                pass

    def _procurar_legado(self) -> Path | None:
        """Procura o config.json do gravador antigo ao lado deste projeto."""
        if self.caminho != caminhos.CONFIG_FILE:
            return None
        candidatos = [
            caminhos.BASE_DIR / "config_antigo.json",
            caminhos.BASE_DIR.parent / "AUTOMACAO_EL_GRAVADOR" / "config.json",
        ]
        for candidato in candidatos:
            if not candidato.exists():
                continue
            try:
                with open(candidato, "r", encoding="utf-8") as f:
                    dados = json.load(f)
            except Exception:
                continue
            if isinstance(dados, dict) and (
                "tema" in dados or "confianca_imagem" in dados or "failsafe_ativo" in dados
            ):
                return candidato
        return None

    def _migrar(self, bruto: dict) -> None:
        for chave in PADROES:
            if chave in bruto:
                self.dados[chave] = bruto[chave]

        for antigo, novo in _MAPA_ANTIGO.items():
            if antigo in bruto and antigo not in PADROES:
                self.dados[novo] = bruto[antigo]
            elif antigo in bruto and novo not in bruto:
                self.dados[novo] = bruto[antigo]

        # O tema é fixo no Apple Glass e não aceita mais cores personalizadas.
        # Configurações antigas são ignoradas na leitura e limpas ao salvar.
        self.dados["tema"] = "Apple Glass"
        self.dados["cores_custom"] = {}

        # Sanidade dos valores
        self.dados["fator_zoom"] = _faixa(self.dados.get("fator_zoom"), 0.6, 2.0, 1.0)
        # Escala real da interface web (px do root). Independente do Tk,
        # que continua usando tamanho_fonte/fator_zoom.
        self.dados["escala_web"] = int(
            _faixa(self.dados.get("escala_web"), 15, 22, 15)
        )
        self.dados["confianca_imagem"] = _faixa(
            self.dados.get("confianca_imagem"), 0.5, 1.0, 0.9
        )
        try:
            self.dados["tentativas_imagem"] = max(
                1, int(self.dados.get("tentativas_imagem", 2))
            )
        except (TypeError, ValueError):
            self.dados["tentativas_imagem"] = 2
        if self.dados.get("ao_falhar") not in ("abortar", "continuar"):
            self.dados["ao_falhar"] = "abortar"
        self.dados["versao"] = VERSAO

    # ------------------------------------------------------------------
    def salvar(self) -> None:
        _salvar_atomico(self.caminho, self.dados)


def _faixa(valor: Any, minimo: float, maximo: float, padrao: float) -> float:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return padrao
    return max(minimo, min(maximo, numero))
