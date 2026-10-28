#!/usr/bin/env python3
"""Ponto de entrada do El Gravador 18 Pro Max.

A consciência de DPI precisa ser habilitada antes de qualquer janela Tk ou
importação do pyautogui; por isso ela é a primeira coisa executada.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from nucleo.dpi import habilitar_dpi

habilitar_dpi()

from nucleo import caminhos, config, legado, logs  # noqa: E402
from nucleo.projeto import Projeto  # noqa: E402

LOG = logs.LOGGER


def _importar_scripts(origem: Path) -> int:
    importados = 0
    if origem.is_dir():
        resultados = legado.importar_pasta_scripts(origem)
    else:
        try:
            projeto, avisos = legado.importar_script(origem)
            resultados = [(origem, projeto, avisos)]
        except Exception as exc:
            print(f"[erro] {origem}: {exc}")
            return 0

    for arquivo, projeto, avisos in resultados:
        if projeto is None:
            print(f"[erro] {arquivo}: {'; '.join(avisos)}")
            continue
        destino = caminhos.PROJETOS_DIR / f"{arquivo.stem}.json"
        try:
            projeto.salvar(destino)
        except Exception as exc:
            print(f"[erro] ao salvar {destino}: {exc}")
            continue
        importados += 1
        print(f"[ok] {arquivo.name} -> {destino} ({len(projeto.passos)} passos)")
        for aviso in avisos:
            print(f"      aviso: {aviso}")
    return importados


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="El Gravador 18 Pro Max",
        description="Gravador e executor de automação (mouse, teclado e imagens).",
    )
    parser.add_argument(
        "-p", "--projeto", type=Path, help="Abrir um projeto .json ao iniciar"
    )
    parser.add_argument(
        "-i",
        "--importar",
        type=Path,
        help="Importar um script antigo (.py) ou uma pasta de scripts e sair",
    )
    parser.add_argument(
        "-t",
        "--templates",
        type=Path,
        help="Importar templates PNG de uma pasta e sair",
    )
    parser.add_argument(
        "--sem-logs",
        action="store_true",
        help="Não gravar o log em arquivo",
    )
    parser.add_argument(
        "--tk",
        action="store_true",
        help="Usar a interface Tk clássica em vez da interface web",
    )
    parser.add_argument(
        "--backend",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--ready-file",
        type=Path,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)

    if args.backend:
        # Processo interno iniciado pela interface web. Ele mantém o Tk
        # escondido e expõe o núcleo de automação via HTTP local.
        from ui.web_backend import main as backend_main

        backend_args: list[str] = []
        if args.projeto:
            backend_args.extend(["--projeto", str(args.projeto)])
        if args.sem_logs:
            backend_args.append("--sem-logs")
        if args.ready_file:
            backend_args.extend(["--ready-file", str(args.ready_file)])
        return backend_main(backend_args)

    caminhos.garantir_dirs()
    cfg = config.Config()
    cfg.carregar()
    logs.configurar(para_arquivo=not args.sem_logs)
    for aviso in cfg.avisos:
        LOG.warning(aviso)

    if args.templates:
        from nucleo import imagens

        try:
            novos, iguais = imagens.importar_pasta(args.templates)
        except Exception as exc:
            print(f"[erro] importar templates: {exc}")
            return 2
        print(f"[ok] {novos} template(s) importado(s), {iguais} repetido(s).")
        return 0

    if args.importar:
        quantidade = _importar_scripts(args.importar)
        print(f"\n{quantidade} projeto(s) criado(s) em {caminhos.PROJETOS_DIR}")
        return 0 if quantidade else 1

    projeto = None
    if args.projeto:
        try:
            projeto = Projeto.carregar(args.projeto)
        except Exception as exc:
            print(f"[erro] não foi possível abrir {args.projeto}: {exc}")
            return 2

    if args.tk:
        try:
            from ui.janela import iniciar
        except ImportError as exc:
            print(
                "Falha ao abrir a interface Tk. Verifique se o Tkinter está instalado.\n"
                f"Detalhe: {exc}"
            )
            return 2
        try:
            iniciar(cfg, projeto)
        except Exception:
            LOG.exception("Erro fatal na interface Tk")
            raise
        return 0

    try:
        from ui.web_app import iniciar
    except ImportError as exc:
        print(
            "Falha ao abrir a interface web. Verifique se o PyWebView está instalado.\n"
            "Instale com: pip install pywebview\n"
            f"Detalhe: {exc}"
        )
        return 2

    try:
        iniciar(cfg, projeto, sem_logs=args.sem_logs)
    except RuntimeError as exc:
        print(f"\n[interface web] {exc}")
        if "PyWebView" in str(exc) or "pywebview" in str(exc).lower():
            print("Dica: instale as dependências com: pip install -r requirements.txt")
        return 2
    except Exception:
        LOG.exception("Erro fatal na interface web")
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
