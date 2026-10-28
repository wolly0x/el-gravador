"""Janela principal do El Gravador 18 Pro Max."""

from __future__ import annotations

import logging
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from nucleo import caminhos, codegen, imagens, legado, logs, passos, tema
from nucleo.backend import BackendReal
from nucleo.config import Config
from nucleo.executor import Executor, Relatorio
from nucleo.gravador import GravadorEventos
from nucleo.projeto import Passo, Projeto

from . import dialogos
from .config_view import ConfigView
from .hud import Hud
from .lista_passos import ListaPassos
from .overlay import selecionar_regiao
from .widgets import (
    BotaoVidro,
    Cartao,
    EntradaVidro,
    SegmentedControl,
    Switch,
    aplicar_borda_windows,
    arredondar_janela,
)

LOG = logging.getLogger("elgravador")


class _HandlerFila(logging.Handler):
    def __init__(self, fila: "queue.Queue[str]"):
        super().__init__()
        self.fila = fila

    def emit(self, record):
        try:
            self.fila.put(self.format(record))
        except Exception:
            pass


class Aplicativo:
    def __init__(self, root: tk.Tk, cfg: Config, projeto: Projeto | None = None):
        self.root = root
        self.cfg = cfg
        self.projeto = projeto or Projeto("novo_projeto")
        self.fila: "queue.Queue[tuple]" = queue.Queue()
        self.fila_log: "queue.Queue[str]" = queue.Queue()
        self.parar = threading.Event()
        self.pausar = threading.Event()
        self.executando = False
        self.gravando = False
        self.rec: GravadorEventos | None = None
        self._indicador: tk.Toplevel | None = None
        self._indicador_texto: tk.Label | None = None
        self._hud: Hud | None = None
        self._hotkeys = None
        self._desfazer: list[list[Passo]] = []
        self._timer_salvar: str | None = None
        self._timer_visual: str | None = None
        self._timer_config: str | None = None
        self._fechando = False
        self._buffer_log: list[str] = []
        self._ultima_regiao: tuple[int, int, int, int] | None = None
        self._botoes_edicao: list[tk.Button] = []
        self._botoes_exec: list[tk.Button] = []
        self._botoes_rec: list[tk.Button] = []

        self._configurar_log()
        self._construir()
        self._aplicar_estilos()
        self._recarregar()
        self._atualizar_botoes()
        self.root.protocol("WM_DELETE_WINDOW", self.fechar)
        self.root.after(120, self._poll)
        self._status("Pronto.")

    # ==================================================================
    # Construção da interface
    # ==================================================================
    @property
    def cores(self) -> dict:
        return self.cfg.paleta()

    @property
    def fonte(self) -> str:
        return str(self.cfg.get("fonte", "Segoe UI"))

    @property
    def tamanho(self) -> int:
        return max(
            7,
            int(round(self.cfg.get("tamanho_fonte", 9) * self.cfg.get("fator_zoom", 1.0))),
        )

    def _configurar_log(self) -> None:
        try:
            handler = _HandlerFila(self.fila_log)
            handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
            logs.LOGGER.addHandler(handler)
        except Exception:
            pass

    def _construir(self) -> None:
        cores = self.cores
        self.root.configure(bg=cores["c_bg"])
        self.root.title(self._titulo())

        self._botoes_edicao = []
        self._botoes_exec = []
        self._botoes_rec = []
        self._aba_atual = 0

        self._construir_menu()

        principal = tk.Frame(self.root, bg=cores["c_bg"])
        principal.pack(fill=tk.BOTH, expand=True)

        self._topbar(principal)
        # A barra de status é reservada antes do corpo expansível para não
        # ser engolida pela área central no pack do Tk.
        self._barra_status(principal)
        self._corpo(principal)

    def _titulo(self) -> str:
        estrela = " *" if self.projeto.alterado else ""
        return f"El Gravador 18 Pro Max — {self.projeto.nome}{estrela}"

    def _construir_menu(self) -> None:
        """Menu de contexto do botão "⋯" (sem a barra nativa do Windows)."""
        cores = self.cores
        opcoes = dict(
            tearoff=0,
            bg=cores["c_surface"],
            fg=cores["c_fg"],
            activebackground=cores["c_accent"],
            activeforeground=cores["c_on_accent"],
            selectcolor=cores["c_accent"],
            bd=0,
        )
        barra = tk.Menu(self.root, **opcoes)

        arquivo = tk.Menu(barra, **opcoes)
        arquivo.add_command(label="Novo projeto", accelerator="Ctrl+N", command=self.novo_projeto)
        arquivo.add_command(label="Abrir…", accelerator="Ctrl+O", command=self.abrir_projeto)
        arquivo.add_separator()
        arquivo.add_command(label="Salvar", accelerator="Ctrl+S", command=self.salvar)
        arquivo.add_command(
            label="Salvar como…", accelerator="Ctrl+Shift+S", command=self.salvar_como
        )
        arquivo.add_separator()
        arquivo.add_command(
            label="Gerar script .py…", accelerator="Ctrl+G", command=self.gerar_script
        )
        arquivo.add_command(label="Importar script antigo…", command=self.importar_legado)
        arquivo.add_command(
            label="Importar pasta de templates…", command=self.importar_templates
        )
        arquivo.add_separator()
        arquivo.add_command(label="Sair", command=self.fechar)
        barra.add_cascade(label="Arquivo", menu=arquivo)

        editar = tk.Menu(barra, **opcoes)
        editar.add_command(label="Desfazer", accelerator="Ctrl+Z", command=self.desfazer)
        editar.add_command(label="Editar passo", accelerator="Enter", command=self.editar_selecionado)
        editar.add_command(label="Duplicar passo", command=self.duplicar_selecionado)
        editar.add_command(label="Excluir passo", accelerator="Del", command=self.excluir_selecionado)
        barra.add_cascade(label="Editar", menu=editar)

        executar = tk.Menu(barra, **opcoes)
        executar.add_command(
            label="Executar tudo", accelerator="Ctrl+R", command=self.executar_tudo
        )
        executar.add_command(label="Executar daqui em diante", command=self.executar_daqui)
        executar.add_command(label="Executar até o selecionado", command=self.executar_ate)
        executar.add_command(label="Testar apenas o selecionado", command=self.testar_selecionado)
        executar.add_separator()
        executar.add_command(label="Pausar / retomar", accelerator="F8", command=self.alternar_pausa)
        executar.add_command(label="Parar", accelerator="Esc", command=self.parar_execucao)
        barra.add_cascade(label="Executar", menu=executar)

        gravar = tk.Menu(barra, **opcoes)
        gravar.add_command(
            label="Gravar / parar (F9)", accelerator="F9", command=self.alternar_gravacao
        )
        gravar.add_command(label="Descartar gravação atual", command=self.descartar_gravacao)
        barra.add_cascade(label="Gravar", menu=gravar)

        ajuda = tk.Menu(barra, **opcoes)
        ajuda.add_command(label="Atalhos e dicas", command=self.mostrar_ajuda)
        ajuda.add_command(label="Sobre", command=self.mostrar_sobre)
        barra.add_cascade(label="Ajuda", menu=ajuda)

        # Não usamos a barra nativa; o menu é aberto pelo botão "⋯".
        self._menu = barra

    def _mostrar_menu(self, _event=None) -> None:
        try:
            botao = self._menu_botao
            x = botao.winfo_rootx()
            y = botao.winfo_rooty() + botao.winfo_height() + 4
            self._menu.tk_popup(x, y)
        except (tk.TclError, AttributeError):
            pass
        finally:
            try:
                self._menu.grab_release()
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    def _botao(
        self, pai, texto, comando, cor=None, largura=None, destaque=False,
        fundo=None, compacto=False,
    ) -> BotaoVidro:
        cores = self.cores
        return BotaoVidro(
            pai,
            texto=texto,
            comando=comando,
            paleta=cores,
            fonte=self.fonte,
            tamanho=max(7, self.tamanho - (1 if compacto else 0)),
            cor=cor or cores["c_surface_alt"],
            largura=largura,
            altura=28 if compacto else 30,
            raio=9,
            destaque=destaque,
            fundo=fundo,
        )

    def _topbar(self, pai) -> None:
        cores = self.cores
        quadro = tk.Frame(pai, bg=cores["c_toolbar"])
        quadro.pack(fill=tk.X)

        # Controles da direita (o label central fica com o espaço restante).
        self.btn_menu = self._botao(
            quadro, "⋯", self._mostrar_menu, cores["c_surface_alt"],
            largura=4, fundo=cores["c_toolbar"], compacto=True,
        )
        self.btn_menu.pack(side=tk.RIGHT, padx=(4, 12), pady=8)
        self._menu_botao = self.btn_menu

        self.btn_topo_executar = self._botao(
            quadro, "▶  Executar", self.executar_tudo, cores["c_accent"],
            destaque=True, fundo=cores["c_toolbar"],
        )
        self.btn_topo_executar.pack(side=tk.RIGHT, padx=(4, 4), pady=8)

        self._frame_rec = tk.Frame(quadro, bg=cores["c_toolbar"])
        self._frame_rec.pack(side=tk.RIGHT, padx=(0, 4), pady=8)
        self.btn_pausar_rec = self._botao(
            self._frame_rec, "Ⅱ Pausar", self.pausar_gravacao,
            cores["c_surface_alt"], fundo=cores["c_toolbar"], compacto=True,
        )
        self.btn_pausar_rec.pack()
        self._frame_rec.pack_forget()
        self._botoes_rec.append(self.btn_pausar_rec)

        self.btn_gravar = self._botao(
            quadro, "●  Gravar", self.alternar_gravacao, cores["c_red"],
            destaque=True, fundo=cores["c_toolbar"],
        )
        self.btn_gravar.pack(side=tk.RIGHT, padx=(4, 4), pady=8)
        self._botoes_rec.append(self.btn_gravar)

        self.var_simular = tk.BooleanVar(value=bool(self.cfg.get("simular")))
        self._switch_simular = Switch(
            quadro,
            paleta=cores,
            var=self.var_simular,
            comando=self._alternar_simulacao,
            texto="Simular",
            fonte=self.fonte,
            tamanho=self.tamanho,
            fundo=cores["c_toolbar"],
            largura=34,
            altura=18,
        )
        self._switch_simular.pack(side=tk.RIGHT, padx=(8, 8), pady=8)

        self.lbl_gravacao = tk.Label(
            quadro,
            text="Pronto para gravar.",
            bg=cores["c_toolbar"],
            fg=cores["c_text_sub"],
            font=(self.fonte, max(7, self.tamanho - 1)),
            anchor="w",
        )
        self.lbl_gravacao.pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 8), pady=8
        )

        # Projeto e identidade.
        projeto = tk.Frame(quadro, bg=cores["c_toolbar"])
        projeto.pack(side=tk.LEFT, padx=(0, 12), pady=8)
        tk.Label(
            projeto,
            text="PROJETO",
            bg=cores["c_toolbar"],
            fg=cores["c_comment"],
            font=(self.fonte, max(6, self.tamanho - 2), "bold"),
            anchor="w",
        ).pack(anchor="w", pady=(0, 2))
        self.var_nome = tk.StringVar(value=self.projeto.nome)
        entrada = EntradaVidro(
            projeto,
            paleta=cores,
            fonte=self.fonte,
            tamanho=max(7, self.tamanho),
            var=self.var_nome,
            largura=18,
            altura=28,
            fundo=cores["c_toolbar"],
        )
        entrada.pack(anchor="w")
        entrada.bind("<FocusOut>", lambda _e: self._renomear())
        entrada.bind("<Return>", lambda _e: self._renomear())

        marca = tk.Frame(quadro, bg=cores["c_toolbar"])
        marca.pack(side=tk.LEFT, padx=(14, 12), pady=8)
        logo = tk.Canvas(
            marca, width=30, height=30, bg=cores["c_toolbar"],
            highlightthickness=0, bd=0,
        )
        logo.pack(side=tk.LEFT, padx=(0, 9))
        logo.create_oval(2, 2, 28, 28, fill=cores["c_accent"], outline="")
        logo.create_text(
            15, 15, text="E", fill=cores["c_on_accent"],
            font=(self.fonte, max(10, self.tamanho + 2), "bold"),
        )
        titulo = tk.Frame(marca, bg=cores["c_toolbar"])
        titulo.pack(side=tk.LEFT)
        tk.Label(
            titulo,
            text="El Gravador",
            bg=cores["c_toolbar"],
            fg=cores["c_fg"],
            font=(self.fonte, max(8, self.tamanho + 1), "bold"),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            titulo,
            text="18 Pro Max",
            bg=cores["c_toolbar"],
            fg=cores["c_text_sub"],
            font=(self.fonte, max(6, self.tamanho - 2)),
            anchor="w",
        ).pack(anchor="w")

        # Reposiciona a faixa esquerda na ordem marca → projeto → status.
        for widget in (self.lbl_gravacao, projeto, marca):
            widget.pack_forget()
        marca.pack(side=tk.LEFT, padx=(14, 12), pady=8)
        projeto.pack(side=tk.LEFT, padx=(0, 12), pady=8)
        self.lbl_gravacao.pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 8), pady=8
        )

        tk.Frame(pai, bg=cores["c_border"], height=1).pack(fill=tk.X)

    def _corpo(self, pai) -> None:
        cores = self.cores
        self.abas = SegmentedControl(
            pai,
            ["Fluxo", "Configurações", "Log"],
            paleta=cores,
            fonte=self.fonte,
            tamanho=max(7, self.tamanho),
            ao_mudar=self._mostrar_aba,
            fundo=cores["c_bg"],
        )
        self.abas.pack(anchor="w", padx=14, pady=(9, 0))

        self.quadro_abas = tk.Frame(pai, bg=cores["c_bg"])
        self.quadro_abas.pack(
            fill=tk.BOTH, expand=True, padx=10, pady=(6, 0)
        )
        self.quadro_abas.grid_rowconfigure(0, weight=1)
        self.quadro_abas.grid_columnconfigure(0, weight=1)

        self.paginas: list[tk.Frame] = []
        for _ in range(3):
            pagina = tk.Frame(self.quadro_abas, bg=cores["c_bg"])
            pagina.grid(row=0, column=0, sticky="nsew")
            self.paginas.append(pagina)

        self._aba_fluxo(self.paginas[0])
        self.config_view = ConfigView(
            self.paginas[1],
            self.cfg,
            ao_aplicar=self._config_alterada,
            ao_importar_templates=self.importar_templates,
            ao_abrir_pasta=self._abrir_pasta,
        )
        self.config_view.pack(fill=tk.BOTH, expand=True)
        self._aba_log(self.paginas[2])
        self._mostrar_aba(0, notificar=False)

    def _mostrar_aba(self, indice: int, notificar: bool = True) -> None:
        if not getattr(self, "paginas", None):
            return
        indice = max(0, min(int(indice), len(self.paginas) - 1))
        self._aba_atual = indice
        try:
            self.paginas[indice].tkraise()
        except (tk.TclError, IndexError):
            pass
        try:
            self.abas.selecionar(indice, notificar=False)
        except (tk.TclError, AttributeError):
            pass

    # ------------------------------------------------------------------
    def _aba_fluxo(self, pai) -> None:
        cores = self.cores
        painel = tk.PanedWindow(
            pai,
            orient=tk.HORIZONTAL,
            sashwidth=10,
            bg=cores["c_bg"],
            bd=0,
            relief="flat",
        )
        painel.pack(fill=tk.BOTH, expand=True)

        esquerda = Cartao(
            painel,
            paleta=cores,
            fundo=cores["c_bg"],
            bg=cores["c_surface"],
            raio=16,
            padding=10,
            sombra=True,
            expandir=True,
        )
        direita = Cartao(
            painel,
            paleta=cores,
            fundo=cores["c_bg"],
            bg=cores["c_surface"],
            raio=16,
            padding=10,
            sombra=True,
            expandir=True,
        )
        painel.add(esquerda, stretch="always", minsize=430)
        painel.add(direita, stretch="never", minsize=300)

        self.lista = ListaPassos(
            esquerda.conteudo,
            ao_editar=self.editar_selecionado,
            ao_mover=self.mover_passo,
            ao_alternar=self.alternar_passo,
            ao_excluir=self.excluir_selecionado,
            paleta=cores,
            fonte=self.fonte,
            tamanho=self.tamanho,
        )

        barra_lista = tk.Frame(esquerda.conteudo, bg=cores["c_surface"])
        for texto, comando in (
            ("Editar", self.editar_selecionado),
            ("Duplicar", self.duplicar_selecionado),
            ("Excluir", self.excluir_selecionado),
            ("Subir", lambda: self.mover_relativo(-1)),
            ("Descer", lambda: self.mover_relativo(1)),
            ("Ativar/desativar", self.alternar_passo),
            ("Desfazer", self.desfazer),
        ):
            botao = self._botao(
                barra_lista, texto, comando, cores["c_surface_alt"],
                fundo=cores["c_surface"], compacto=True,
            )
            botao.pack(side=tk.LEFT, padx=(0, 4))
            self._botoes_edicao.append(botao)

        dica = tk.Label(
            esquerda.conteudo,
            text="Arraste para reordenar  •  duplo clique edita  •  Espaço ativa  •  Delete exclui",
            bg=cores["c_surface"],
            fg=cores["c_text_sub"],
            font=(self.fonte, max(6, self.tamanho - 2)),
            anchor="w",
        )

        # Reserva o rodapé da lista antes de dar o espaço restante à árvore.
        dica.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))
        barra_lista.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        self.lista.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self._painel_direito(direita.conteudo)

    def _painel_direito(self, pai) -> None:
        cores = self.cores

        def titulo_secao(texto: str, cor: str, pady=(8, 5)) -> None:
            tk.Label(
                pai,
                text=texto,
                bg=cores["c_surface"],
                fg=cor,
                font=(self.fonte, max(8, self.tamanho + 1), "bold"),
                anchor="w",
            ).pack(fill=tk.X, padx=2, pady=pady)

        def separador() -> None:
            tk.Frame(pai, bg=cores["c_border"], height=1).pack(
                fill=tk.X, padx=2, pady=8
            )

        titulo_secao("Adicionar passo", cores["c_accent"], pady=(2, 5))
        grade = tk.Frame(pai, bg=cores["c_surface"])
        grade.pack(fill=tk.X)
        grade.columnconfigure(0, weight=1)
        grade.columnconfigure(1, weight=1)

        acoes = [
            ("Capturar clique", self.capturar_clique),
            ("Duplo clique", self.capturar_duplo),
            ("Clique direito", self.capturar_direito),
            ("Mover para…", self.capturar_mover),
            ("Arrastar…", self.capturar_arrastar),
            ("Rolar…", lambda: self.novo_passo("rolar")),
            ("Digitar…", lambda: self.novo_passo("digitar")),
            ("Atalho…", lambda: self.novo_passo("atalho")),
            ("Tecla…", lambda: self.novo_passo("tecla")),
            ("Pausa…", lambda: self.novo_passo("pausa")),
            ("Imagem + clique", self.capturar_imagem_clique),
            ("Esperar imagem", self.capturar_imagem_esperar),
            ("Esperar sumir…", lambda: self.novo_passo("imagem_desaparecer")),
            ("Bloco repetidor…", lambda: self.novo_passo("bloco_inicio")),
            ("Comentário…", lambda: self.novo_passo("comentario")),
        ]
        for i, (texto, comando) in enumerate(acoes):
            botao = self._botao(
                grade, texto, comando, cores["c_surface_alt"],
                fundo=cores["c_surface"], compacto=True,
            )
            botao.grid(
                row=i // 2,
                column=i % 2,
                sticky="ew",
                padx=2,
                pady=2,
            )
            self._botoes_edicao.append(botao)

        separador()
        titulo_secao("Executar", cores["c_success"], pady=(0, 5))

        grade_exec = tk.Frame(pai, bg=cores["c_surface"])
        grade_exec.pack(fill=tk.X)
        grade_exec.columnconfigure(0, weight=1)
        grade_exec.columnconfigure(1, weight=1)
        botoes_exec = [
            ("▶  Tudo", self.executar_tudo),
            ("Até aqui", self.executar_ate),
            ("Daqui", self.executar_daqui),
            ("Testar passo", self.testar_selecionado),
        ]
        for i, (texto, comando) in enumerate(botoes_exec):
            botao = self._botao(
                grade_exec, texto, comando,
                cores["c_accent"] if i == 0 else cores["c_surface_alt"],
                destaque=(i == 0), fundo=cores["c_surface"], compacto=True,
            )
            botao.grid(
                row=i // 2, column=i % 2, sticky="ew",
                padx=2, pady=2,
            )
            self._botoes_exec.append(botao)

        linha = tk.Frame(pai, bg=cores["c_surface"])
        linha.pack(fill=tk.X, pady=(4, 2))
        self.btn_pausar = self._botao(
            linha, "Ⅱ  Pausar", self.alternar_pausa, cores["c_warning"],
            fundo=cores["c_surface"], compacto=True,
        )
        self.btn_pausar.configure(fg=tema.contraste(cores["c_warning"]))
        self.btn_pausar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        self.btn_parar = self._botao(
            linha, "■  Parar", self.parar_execucao, cores["c_danger"],
            fundo=cores["c_surface"], compacto=True,
        )
        self.btn_parar.configure(fg=tema.contraste(cores["c_danger"]))
        self.btn_parar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))
        self._botoes_exec.extend([self.btn_pausar, self.btn_parar])

        linha_rep = tk.Frame(pai, bg=cores["c_surface"])
        linha_rep.pack(fill=tk.X, pady=(4, 0))
        tk.Label(
            linha_rep,
            text="Repetições (0 = ∞):",
            bg=cores["c_surface"],
            fg=cores["c_text_sub"],
            font=(self.fonte, max(7, self.tamanho - 1)),
        ).pack(side=tk.LEFT)
        self.var_repeticoes = tk.StringVar(value=str(self.projeto.repeticao()))
        spin = tk.Spinbox(
            linha_rep,
            from_=0,
            to=99999,
            textvariable=self.var_repeticoes,
            width=6,
            bg=cores["c_surface_alt"],
            fg=cores["c_fg"],
            insertbackground=cores["c_fg"],
            buttonbackground=cores["c_surface_3"],
            relief="flat",
            highlightthickness=0,
            bd=0,
            font=(self.fonte, max(7, self.tamanho)),
            command=self._aplicar_repeticoes,
        )
        spin.pack(side=tk.RIGHT, padx=(6, 0))
        spin.bind("<FocusOut>", self._aplicar_repeticoes)
        spin.bind("<Return>", self._aplicar_repeticoes)

    def _aba_log(self, pai) -> None:
        cores = self.cores
        cartao = Cartao(
            pai,
            paleta=cores,
            fundo=cores["c_bg"],
            bg=cores["c_surface"],
            raio=16,
            padding=10,
            sombra=True,
            expandir=True,
        )
        cartao.pack(fill=tk.BOTH, expand=True)
        quadro = cartao.conteudo

        self.texto_log = tk.Text(
            quadro,
            bg=cores["c_surface"],
            fg=cores["c_fg"],
            insertbackground=cores["c_fg"],
            relief="flat",
            bd=0,
            highlightthickness=0,
            wrap="word",
            font=("Consolas", max(7, self.tamanho - 1)),
            state=tk.DISABLED,
            padx=8,
            pady=8,
        )
        barra = ttk.Scrollbar(quadro, orient="vertical", command=self.texto_log.yview)
        self.texto_log.configure(yscrollcommand=barra.set)
        self.texto_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        barra.pack(side=tk.RIGHT, fill=tk.Y)
        if self._buffer_log:
            self.texto_log.configure(state=tk.NORMAL)
            self.texto_log.insert(tk.END, "\n".join(self._buffer_log[-2000:]) + "\n")
            self.texto_log.configure(state=tk.DISABLED)
        self.texto_log.see(tk.END)

        botoes = tk.Frame(quadro, bg=cores["c_surface"])
        botoes.pack(fill=tk.X, pady=(8, 0))
        self._botao(
            botoes, "Limpar log", self._limpar_log, cores["c_surface_alt"],
            fundo=cores["c_surface"], compacto=True,
        ).pack(side=tk.LEFT)
        self._botao(
            botoes, "Abrir pasta de logs", lambda: self._abrir_pasta("logs"),
            cores["c_surface_alt"], fundo=cores["c_surface"], compacto=True,
        ).pack(side=tk.LEFT, padx=6)

        # O rodapé precisa ser reservado antes do texto para não ser
        # "engolido" pelo widget que expande.
        for widget in (self.texto_log, barra, botoes):
            widget.pack_forget()
        botoes.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        barra.pack(side=tk.RIGHT, fill=tk.Y)
        self.texto_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def _barra_status(self, pai) -> None:
        cores = self.cores
        quadro = tk.Frame(pai, bg=cores["c_toolbar"])
        quadro.pack(fill=tk.X, side=tk.BOTTOM)

        self.lbl_status = tk.Label(
            quadro,
            text="Pronto.",
            bg=cores["c_toolbar"],
            fg=cores["c_fg"],
            font=(self.fonte, max(7, self.tamanho - 1)),
            anchor="w",
        )
        self.progresso = ttk.Progressbar(
            quadro, mode="indeterminate", length=120, style="Glass.Horizontal.TProgressbar"
        )

        self.lbl_contagem = tk.Label(
            quadro,
            text="",
            bg=cores["c_toolbar"],
            fg=cores["c_text_sub"],
            font=(self.fonte, max(7, self.tamanho - 1)),
        )

        # Reserva os elementos da direita antes do label expansível.
        self.lbl_contagem.pack(side=tk.RIGHT, padx=10)
        self.progresso.pack(side=tk.RIGHT, padx=10, pady=5)
        self.lbl_status.pack(side=tk.LEFT, padx=14, pady=5, fill=tk.X, expand=True)

    # ------------------------------------------------------------------
    def _aplicar_estilos(self) -> None:
        cores = self.cores
        estilo = ttk.Style(self.root)
        try:
            estilo.theme_use("clam")
        except tk.TclError:
            pass
        base = (self.fonte, self.tamanho)
        estilo.configure("TFrame", background=cores["c_bg"])
        estilo.configure("Config.TFrame", background=cores["c_bg"])
        estilo.configure(
            "TLabel", background=cores["c_bg"], foreground=cores["c_fg"], font=base
        )
        estilo.configure(
            "Treeview",
            background=cores["c_surface"],
            fieldbackground=cores["c_surface"],
            foreground=cores["c_fg"],
            rowheight=max(27, int(self.tamanho * 2.6)),
            font=base,
            borderwidth=0,
            relief="flat",
        )
        estilo.configure(
            "Treeview.Heading",
            background=cores["c_surface_alt"],
            foreground=cores["c_text_sub"],
            font=(self.fonte, max(7, self.tamanho), "bold"),
            relief="flat",
            padding=(8, 6),
        )
        estilo.map(
            "Treeview.Heading",
            background=[("active", cores["c_surface_3"])],
        )
        estilo.map(
            "Treeview",
            background=[("selected", cores["c_selection"])],
            foreground=[("selected", cores["c_fg"])],
        )
        estilo.configure(
            "TScrollbar",
            background=cores["c_surface_3"],
            troughcolor=cores["c_surface"],
            bordercolor=cores["c_surface"],
            arrowcolor=cores["c_text_sub"],
            borderwidth=0,
            arrowsize=8,
        )
        estilo.map(
            "TScrollbar",
            background=[("active", cores["c_border_strong"])],
        )
        estilo.configure(
            "Glass.Horizontal.TProgressbar",
            background=cores["c_accent"],
            troughcolor=cores["c_surface_3"],
            borderwidth=0,
            thickness=5,
        )
        estilo.configure(
            "TProgressbar",
            background=cores["c_accent"],
            troughcolor=cores["c_surface_3"],
            borderwidth=0,
        )
        estilo.configure(
            "TCombobox",
            fieldbackground=cores["c_surface_alt"],
            background=cores["c_surface_alt"],
            foreground=cores["c_fg"],
            arrowcolor=cores["c_text_sub"],
            bordercolor=cores["c_border"],
            lightcolor=cores["c_border"],
            darkcolor=cores["c_border"],
            padding=(7, 4),
        )
        estilo.map(
            "TCombobox",
            fieldbackground=[
                ("readonly", cores["c_surface_alt"]),
                ("active", cores["c_surface_3"]),
            ],
            foreground=[("readonly", cores["c_fg"])],
            bordercolor=[("focus", cores["c_accent"])],
        )
        self.root.option_add("*TCombobox*Listbox.background", cores["c_surface"])
        self.root.option_add("*TCombobox*Listbox.foreground", cores["c_fg"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", cores["c_accent"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", cores["c_on_accent"])
        aplicar_borda_windows(
            self.root, tema.luminancia(cores["c_bg"]) < 0.5
        )

    # ==================================================================
    # Estado e recarregamento
    # ==================================================================
    def _recarregar(self, indice: int | None = None) -> None:
        self.lista.recarregar(self.projeto, indice)
        self.lbl_contagem.configure(
            text=f"{len(self.projeto)} passo(s)  •  {self.projeto.repeticao()}x"
        )
        if hasattr(self, "var_repeticoes"):
            self.var_repeticoes.set(str(self.projeto.repeticao()))
        if hasattr(self, "var_nome"):
            self.var_nome.set(self.projeto.nome)
        self.root.title(self._titulo())

    def _aplicar_repeticoes(self, _event=None) -> None:
        try:
            valor = max(0, int(float(self.var_repeticoes.get().replace(",", "."))))
        except (TypeError, ValueError):
            valor = self.projeto.repeticao()
        self.projeto.config["repeticoes"] = valor
        self.var_repeticoes.set(str(valor))
        self._marcar_alterado()
        self.lbl_contagem.configure(
            text=f"{len(self.projeto)} passo(s)  •  {valor}x"
        )

    def _status(self, texto: str, tipo: str = "info") -> None:
        cores = self.cores
        cor = {
            "info": cores["c_fg"],
            "ok": cores["c_green"],
            "aviso": cores["c_orange"],
            "erro": cores["c_red"],
        }.get(tipo, cores["c_fg"])
        try:
            self.lbl_status.configure(text=texto, fg=cor)
        except tk.TclError:
            pass

    def _log(self, texto: str) -> None:
        self._buffer_log.append(texto)
        if len(self._buffer_log) > 5000:
            del self._buffer_log[:2000]
        try:
            if self.texto_log is not None and self.texto_log.winfo_exists():
                self.texto_log.configure(state=tk.NORMAL)
                self.texto_log.insert(tk.END, texto + "\n")
                self.texto_log.see(tk.END)
                self.texto_log.configure(state=tk.DISABLED)
        except (tk.TclError, AttributeError):
            pass

    def _limpar_log(self) -> None:
        self._buffer_log.clear()
        try:
            self.texto_log.configure(state=tk.NORMAL)
            self.texto_log.delete("1.0", tk.END)
            self.texto_log.configure(state=tk.DISABLED)
        except (tk.TclError, AttributeError):
            pass

    def _atualizar_botoes(self) -> None:
        ocupado = self.executando or self.gravando
        estado = tk.DISABLED if ocupado else tk.NORMAL
        for botao in self._botoes_edicao:
            try:
                botao.configure(state=estado)
            except tk.TclError:
                pass
        for botao in self._botoes_exec:
            try:
                botao.configure(state=tk.DISABLED if self.gravando else tk.NORMAL)
            except tk.TclError:
                pass
        cor_gravar = self.cores["c_orange"] if self.gravando else self.cores["c_red"]
        self.btn_gravar.configure(
            state=tk.DISABLED if self.executando else tk.NORMAL,
            text="■  Parar gravação" if self.gravando else "●  Gravar",
            bg=cor_gravar,
            fg=tema.contraste(cor_gravar),
        )
        self.btn_topo_executar.configure(
            state=tk.DISABLED if ocupado else tk.NORMAL,
            text="■  Parando…" if self.executando else "▶  Executar",
        )
        try:
            if self.gravando:
                self._frame_rec.pack(
                    side=tk.RIGHT, padx=(0, 4), pady=8,
                    before=self.btn_gravar,
                )
            else:
                self._frame_rec.pack_forget()
        except tk.TclError:
            pass
        self.btn_pausar_rec.configure(
            state=tk.NORMAL if self.gravando else tk.DISABLED
        )
        if not self.executando:
            self.btn_parar.configure(state=tk.DISABLED)
            self.btn_pausar.configure(state=tk.DISABLED)
        else:
            self.btn_parar.configure(state=tk.NORMAL)
            self.btn_pausar.configure(state=tk.NORMAL)
        if self.executando:
            self.progresso.start(60)
        else:
            try:
                self.progresso.stop()
            except tk.TclError:
                pass

    def _marcar_alterado(self) -> None:
        self.projeto.alterado = True
        self.root.title(self._titulo())
        if self._timer_salvar:
            try:
                self.root.after_cancel(self._timer_salvar)
            except tk.TclError:
                pass
        self._timer_salvar = self.root.after(900, self._salvar_automatico)

    def _salvar_automatico(self) -> None:
        self._timer_salvar = None
        if not self.projeto.caminho:
            nome = imagens.slug(self.projeto.nome or "projeto")
            destino = caminhos.PROJETOS_DIR / f"{nome}.json"
        else:
            destino = self.projeto.caminho
        try:
            self.projeto.salvar(destino)
            if hasattr(self, "var_nome"):
                self.var_nome.set(self.projeto.nome)
            self.root.title(self._titulo())
        except Exception as exc:
            self._log(f"[autosave] falhou: {exc}")

    def _snapshot(self) -> None:
        self._desfazer.append([p.copiar(novo_id=False) for p in self.projeto.passos])
        if len(self._desfazer) > 40:
            self._desfazer.pop(0)

    def desfazer(self) -> None:
        if not self._desfazer:
            self._status("Nada para desfazer.", "aviso")
            return
        passos_antigos = self._desfazer.pop()
        self.projeto.passos = passos_antigos
        self._marcar_alterado()
        self._recarregar()
        self._status("Última alteração desfeita.")

    # ==================================================================
    # Projeto
    # ==================================================================
    def _renomear(self) -> None:
        novo = self.var_nome.get().strip() or "novo_projeto"
        if novo != self.projeto.nome:
            self.projeto.nome = novo
            self._marcar_alterado()

    def _talvez_salvar(self) -> bool:
        if not self.projeto.alterado:
            return True
        resposta = messagebox.askyesnocancel(
            "Salvar alterações?",
            f"O projeto \"{self.projeto.nome}\" foi alterado. Deseja salvar?",
            parent=self.root,
        )
        if resposta is None:
            return False
        if resposta:
            return self.salvar()
        return True

    def novo_projeto(self) -> None:
        if not self._talvez_salvar():
            return
        self.projeto = Projeto("novo_projeto")
        self._desfazer.clear()
        self._recarregar()
        self._status("Novo projeto criado.")

    def abrir_projeto(self) -> None:
        if not self._talvez_salvar():
            return
        caminho = filedialog.askopenfilename(
            title="Abrir projeto",
            initialdir=str(caminhos.PROJETOS_DIR),
            filetypes=[("Projeto El Gravador", "*.json"), ("Todos", "*.*")],
            parent=self.root,
        )
        if not caminho:
            return
        try:
            self.projeto = Projeto.carregar(caminho)
        except Exception as exc:
            messagebox.showerror("Abrir projeto", str(exc), parent=self.root)
            return
        self.var_nome.set(self.projeto.nome)
        self._desfazer.clear()
        self._recarregar()
        self._status(f"Aberto: {caminho}", "ok")

    def salvar(self) -> bool:
        if not self.projeto.caminho:
            return self.salvar_como()
        try:
            self.projeto.salvar()
        except Exception as exc:
            messagebox.showerror("Salvar", str(exc), parent=self.root)
            return False
        self.root.title(self._titulo())
        self._status(f"Salvo em {self.projeto.caminho}", "ok")
        return True

    def salvar_como(self) -> bool:
        caminho = filedialog.asksaveasfilename(
            title="Salvar projeto como",
            initialdir=str(caminhos.PROJETOS_DIR),
            initialfile=f"{imagens.slug(self.projeto.nome)}.json",
            defaultextension=".json",
            filetypes=[("Projeto El Gravador", "*.json")],
            parent=self.root,
        )
        if not caminho:
            return False
        try:
            self.projeto.salvar(caminho)
        except Exception as exc:
            messagebox.showerror("Salvar", str(exc), parent=self.root)
            return False
        self.var_nome.set(self.projeto.nome)
        self._recarregar()
        self._status(f"Salvo em {caminho}", "ok")
        return True

    def gerar_script(self) -> None:
        if not self.projeto.passos:
            messagebox.showinfo("Gerar script", "Adicione pelo menos um passo.", parent=self.root)
            return
        problemas = self.projeto.validar()
        if problemas:
            texto = "\n".join(problemas[:10])
            if not messagebox.askyesno(
                "Problemas encontrados",
                f"O projeto tem problemas:\n\n{texto}\n\nGerar mesmo assim?",
                parent=self.root,
            ):
                return
        ausentes = [t for t in self.projeto.templates_usados() if not imagens.existe(t)]
        if ausentes:
            if not messagebox.askyesno(
                "Templates ausentes",
                "Estas imagens não estão na pasta de templates:\n\n"
                + "\n".join(ausentes[:10])
                + "\n\nO script vai falhar se elas não existirem na outra máquina. Continuar?",
                parent=self.root,
            ):
                return

        repeticoes = simpledialog.askinteger(
            "Repetições",
            "Quantas vezes o fluxo deve repetir?\n(0 = infinito)",
            initialvalue=self.projeto.repeticao(),
            minvalue=0,
            maxvalue=100000,
            parent=self.root,
        )
        if repeticoes is None:
            return
        self.projeto.config["repeticoes"] = int(repeticoes)

        destino = filedialog.asksaveasfilename(
            title="Salvar script gerado",
            initialdir=str(caminhos.PROJETOS_DIR),
            initialfile=f"{imagens.slug(self.projeto.nome)}.py",
            defaultextension=".py",
            filetypes=[("Script Python", "*.py")],
            parent=self.root,
        )
        if not destino:
            return

        try:
            info = codegen.exportar(self.projeto, destino, self.cfg.dados)
        except Exception as exc:
            messagebox.showerror("Gerar script", str(exc), parent=self.root)
            return
        self._log(
            f"[export] {info['script']} "
            f"({len(self.projeto.passos)} passos, {len(info['templates'])} templates)"
        )
        if info["templates_ausentes"]:
            self._log(f"[export] templates ausentes: {info['templates_ausentes']}")
        messagebox.showinfo(
            "Script gerado",
            f"Script criado em:\n{info['script']}\n\n"
            f"Templates copiados: {len(info['templates'])}\n"
            f"Pasta de imagens: {Path(destino).parent / 'imagens_templates'}\n\n"
            "O script gerado sempre executa de verdade (o modo simular vale só "
            "dentro do gravador).\n\n"
            "Para executar: python " + Path(destino).name,
            parent=self.root,
        )
        self._status("Script gerado.", "ok")

    def importar_legado(self) -> None:
        caminho = filedialog.askopenfilename(
            title="Importar script antigo",
            initialdir="/media/sf_PROJETOS/projeto_004",
            filetypes=[("Script Python", "*.py"), ("Todos", "*.*")],
            parent=self.root,
        )
        if not caminho:
            return
        try:
            importado, avisos = legado.importar_script(caminho)
        except Exception as exc:
            messagebox.showerror("Importar script", str(exc), parent=self.root)
            return
        if not importado.passos:
            messagebox.showinfo(
                "Importar script",
                "Nenhum passo reconhecido no arquivo.",
                parent=self.root,
            )
            return
        substituir = messagebox.askyesnocancel(
            "Importar script",
            f"{len(importado.passos)} passo(s) reconhecido(s).\n\n"
            "Sim = substituir o fluxo atual\nNão = acrescentar ao final\n"
            "Cancelar = desistir",
            parent=self.root,
        )
        if substituir is None:
            return
        self._snapshot()
        if substituir:
            self.projeto.passos = importado.passos
            if importado.config.get("repeticoes") is not None:
                self.projeto.config["repeticoes"] = importado.config["repeticoes"]
        else:
            self.projeto.passos.extend(importado.passos)
        self._marcar_alterado()
        self._recarregar()
        for aviso in avisos:
            self._log(f"[import] {aviso}")
        self._status(
            f"Importado: {len(importado.passos)} passo(s).", "ok"
        )
        if avisos:
            messagebox.showinfo(
                "Importar script",
                "Importado com avisos:\n\n" + "\n".join(avisos[:12]),
                parent=self.root,
            )

    def importar_templates(self) -> None:
        pasta = filedialog.askdirectory(
            title="Pasta com templates PNG (ex.: do gravador antigo)",
            parent=self.root,
        )
        if not pasta:
            return
        try:
            novos, iguais = imagens.importar_pasta(pasta)
        except Exception as exc:
            messagebox.showerror("Importar templates", str(exc), parent=self.root)
            return
        self._status(f"{novos} template(s) importado(s), {iguais} repetido(s).", "ok")
        messagebox.showinfo(
            "Importar templates",
            f"{novos} template(s) importado(s).\n{iguais} já existiam (idênticos).",
            parent=self.root,
        )

    # ==================================================================
    # Edição
    # ==================================================================
    def _indice_insercao(self) -> int:
        selecionado = self.lista.selecionado()
        if selecionado is None:
            return len(self.projeto.passos)
        return selecionado + 1

    def _inserir(self, tipo: str, params: dict) -> None:
        self._snapshot()
        posicao = self._indice_insercao()
        self.projeto.adicionar(tipo, posicao, **params)
        if tipo == "bloco_inicio":
            self.projeto.adicionar("bloco_fim", posicao + 1)
        self._marcar_alterado()
        self._recarregar(posicao)
        self._status(f"Passo adicionado: {passos.rotulo(tipo, params)}", "ok")

    def novo_passo(self, tipo: str) -> None:
        base = Passo(tipo=tipo, params=passos.criar(tipo))
        resultado = dialogos.editar_passo(
            self.root,
            base,
            self.cfg.dados,
            capturar_ponto_cb=self.capturar_ponto,
            capturar_regiao_cb=self.capturar_template_regiao,
        )
        if resultado:
            tipo_novo, params = resultado
            self._inserir(tipo_novo, params)

    def editar_selecionado(self, indice: int | None = None) -> None:
        indice = self.lista.selecionado() if indice is None else indice
        if indice is None:
            self._status("Selecione um passo para editar.", "aviso")
            return
        atual = self.projeto.passos[indice]
        resultado = dialogos.editar_passo(
            self.root,
            atual,
            self.cfg.dados,
            capturar_ponto_cb=self.capturar_ponto,
            capturar_regiao_cb=self.capturar_template_regiao,
        )
        if not resultado:
            return
        tipo, params = resultado
        self._snapshot()
        self.projeto.substituir(indice, tipo, params)
        self._marcar_alterado()
        self._recarregar(indice)
        self._status("Passo atualizado.", "ok")

    def duplicar_selecionado(self, indice: int | None = None) -> None:
        indice = self.lista.selecionado() if indice is None else indice
        if indice is None:
            self._status("Selecione um passo para duplicar.", "aviso")
            return
        passo = self.projeto.passos[indice]
        if passo.tipo == "bloco_fim":
            self._status(
                "Duplique o INÍCIO do bloco: o FIM é criado junto.", "aviso"
            )
            return
        self._snapshot()
        self.projeto.duplicar(indice)
        if passo.tipo == "bloco_inicio":
            self.projeto.adicionar("bloco_fim", indice + 2)
        self._marcar_alterado()
        self._recarregar(indice + 1)

    def excluir_selecionado(self, indice: int | None = None) -> None:
        indice = self.lista.selecionado() if indice is None else indice
        if indice is None:
            return
        self._snapshot()
        self.projeto.remover(indice)
        self._marcar_alterado()
        self._recarregar(min(indice, len(self.projeto.passos) - 1))
        self._status("Passo removido.")

    def alternar_passo(self, indice: int | None = None) -> None:
        indice = self.lista.selecionado() if indice is None else indice
        if indice is None:
            return
        self._snapshot()
        self.projeto.alternar_ativo(indice)
        self._marcar_alterado()
        self._recarregar(indice)

    def mover_passo(self, origem: int, destino: int) -> None:
        self._snapshot()
        if self.projeto.mover(origem, destino):
            self._marcar_alterado()
            self._recarregar(destino)

    def mover_relativo(self, delta: int) -> None:
        indice = self.lista.selecionado()
        if indice is None:
            return
        self.mover_passo(indice, indice + delta)

    # ------------------------------------------------------------------
    # Capturas
    # ------------------------------------------------------------------
    def capturar_ponto(self, janelas: list, ao_ponto) -> None:
        def aplicar(ponto):
            try:
                for janela in janelas:
                    if janela.winfo_exists():
                        janela.deiconify()
                self.root.deiconify()
                self.root.lift()
            except tk.TclError:
                pass
            if ponto is None:
                self._status("Captura cancelada.", "aviso")
            ao_ponto(ponto)

        extras = [j for j in janelas if j is not self.root]
        for janela in extras:
            try:
                janela.withdraw()
            except tk.TclError:
                pass
        dialogos.capturar_ponto(self.root, aplicar, extras=extras)

    def capturar_template_regiao(self, janelas: list, ao_nome) -> None:
        for janela in janelas:
            try:
                janela.withdraw()
            except tk.TclError:
                pass
        try:
            self.root.withdraw()
        except tk.TclError:
            pass

        def restaurar():
            try:
                self.root.deiconify()
                self.root.lift()
                for janela in janelas:
                    if janela.winfo_exists():
                        janela.deiconify()
                        janela.lift()
                        try:
                            janela.grab_set()
                        except tk.TclError:
                            pass
            except tk.TclError:
                pass

        def apos(regiao):
            self._ultima_regiao = regiao
            if not regiao:
                restaurar()
                ao_nome(None)
                return
            x, y, largura, altura = regiao
            # O screenshot precisa ser tirado com as janelas do app ainda ocultas.
            try:
                tela, ox, oy = imagens.capturar_tela()
                recorte = imagens.recortar(
                    tela, x, y, x + largura, y + altura, ox, oy
                )
            except Exception as exc:
                restaurar()
                messagebox.showerror("Capturar template", str(exc), parent=self.root)
                ao_nome(None)
                return
            restaurar()
            nome_base = simpledialog.askstring(
                "Nome do template",
                "Nome para reconhecer esta imagem:",
                initialvalue=f"regiao_{largura}x{altura}",
                parent=self.root,
            )
            if not nome_base:
                ao_nome(None)
                return
            try:
                nome = imagens.salvar_template(
                    recorte, nome_base, meta={"regiao": [x, y, largura, altura]}
                )
            except Exception as exc:
                messagebox.showerror("Capturar template", str(exc), parent=self.root)
                ao_nome(None)
                return
            self._log(f"[template] salvo: {nome}")
            self._status(f"Template salvo: {nome}", "ok")
            ao_nome(nome)

        selecionar_regiao(self.root, apos)

    def capturar_clique(self) -> None:
        def aplicar(ponto):
            if ponto:
                self._inserir(
                    "clicar", passos.criar("clicar", x=ponto[0], y=ponto[1])
                )

        self.capturar_ponto([], aplicar)

    def capturar_duplo(self) -> None:
        def aplicar(ponto):
            if ponto:
                self._inserir(
                    "clicar",
                    passos.criar(
                        "clicar", x=ponto[0], y=ponto[1], cliques=2
                    ),
                )

        self.capturar_ponto([], aplicar)

    def capturar_direito(self) -> None:
        def aplicar(ponto):
            if ponto:
                self._inserir(
                    "clicar",
                    passos.criar(
                        "clicar", x=ponto[0], y=ponto[1], botao="right"
                    ),
                )

        self.capturar_ponto([], aplicar)

    def capturar_mover(self) -> None:
        def aplicar(ponto):
            if ponto:
                self._inserir(
                    "mover", passos.criar("mover", x=ponto[0], y=ponto[1])
                )

        self.capturar_ponto([], aplicar)

    def capturar_arrastar(self) -> None:
        def segundo(origem):
            if not origem:
                return

            def destino(ponto):
                if not ponto:
                    return
                self._inserir(
                    "arrastar",
                    passos.criar(
                        "arrastar",
                        x1=origem[0],
                        y1=origem[1],
                        x2=ponto[0],
                        y2=ponto[1],
                    ),
                )

            self.capturar_ponto([], destino)

        self.capturar_ponto([], segundo)

    def _capturar_regiao_para_passo(self, tipo: str) -> None:
        def ao_nome(nome):
            if not nome:
                return
            params = passos.criar(tipo)
            params["arquivo"] = str(nome)
            regiao = self._ultima_regiao
            if tipo == "imagem_clicar" and regiao:
                x, y, largura, altura = regiao
                params["fallback"] = [x + largura // 2, y + altura // 2]
            self._inserir(tipo, params)

        self.capturar_template_regiao([], ao_nome)

    def capturar_imagem_clique(self) -> None:
        self._capturar_regiao_para_passo("imagem_clicar")

    def capturar_imagem_esperar(self) -> None:
        self._capturar_regiao_para_passo("imagem_esperar")

    # ==================================================================
    # Execução
    # ==================================================================
    def _alternar_simulacao(self) -> None:
        self.cfg.set("simular", bool(self.var_simular.get()))
        self._config_alterada(visual=False)

    def executar_tudo(self) -> None:
        self._executar()

    def executar_ate(self) -> None:
        indice = self.lista.selecionado()
        if indice is None:
            self._status("Selecione o último passo a executar.", "aviso")
            return
        self._executar(de=0, ate=indice)

    def executar_daqui(self) -> None:
        indice = self.lista.selecionado()
        if indice is None:
            self._status("Selecione o primeiro passo.", "aviso")
            return
        self._executar(de=indice)

    def testar_selecionado(self) -> None:
        indice = self.lista.selecionado()
        if indice is None:
            self._status("Selecione um passo para testar.", "aviso")
            return
        # Testar também esconde a janela: senão o próprio app cobre o alvo.
        self._executar(de=indice, ate=indice, teste=True)

    def _executar(
        self, de: int = 0, ate: int | None = None, teste: bool = False
    ) -> None:
        if self.executando or self.gravando:
            return
        if not self.projeto.passos:
            messagebox.showinfo("Executar", "O projeto está vazio.", parent=self.root)
            return
        problemas = self.projeto.validar()
        if problemas:
            messagebox.showwarning(
                "Problemas no fluxo",
                "\n".join(problemas[:12]),
                parent=self.root,
            )
            return
        ausentes = [t for t in self.projeto.templates_usados() if not imagens.existe(t)]
        if ausentes:
            messagebox.showwarning(
                "Templates ausentes",
                "Estas imagens não foram encontradas e os passos que as usam vão falhar:\n\n"
                + "\n".join(ausentes[:12]),
                parent=self.root,
            )
            return
        if self.var_simular.get():
            self.cfg.set("simular", True)

        self.parar = threading.Event()
        self.pausar = threading.Event()
        self.executando = True
        simular = bool(self.var_simular.get())
        self._atualizar_botoes()
        self._status("Executando… ESC para parar, F8 para pausar.", "ok")
        self._iniciar_hotkeys()

        try:
            backend = BackendReal(failsafe=bool(self.cfg.get("failsafe_ativo")))
        except Exception as exc:
            self.executando = False
            self._atualizar_botoes()
            self._parar_hotkeys()
            messagebox.showerror(
                "pyautogui ausente",
                "Não foi possível iniciar o controle de mouse/teclado:\n\n"
                f"{exc}\n\nInstale com: pip install pyautogui pynput pillow "
                "opencv-python-headless",
                parent=self.root,
            )
            return

        executor = Executor(
            self.projeto,
            backend,
            self.cfg.dados,
            imagens=imagens,
            parar=self.parar,
            pausar=self.pausar,
            ao_passo=lambda i, _p: self.fila.put(("passo", i)),
            # O log do executor chega pela fila do logging (evita duplicar).
            ao_log=None,
            ao_status=lambda texto: self.fila.put(("hud", texto)),
            simular=simular,
        )

        repeticoes = self.projeto.repeticao() if (de == 0 and ate is None) else 1

        def trabalho():
            # A janela fica escondida durante a execução; qualquer erro
            # inesperado precisa terminar com um ("fim") para reexibi-la.
            relatorio = Relatorio()
            try:
                relatorio = executor.rodar(de, ate)
                feitas = 1
                while (
                    repeticoes == 0 or feitas < repeticoes
                ) and not relatorio.cancelado and not relatorio.erro:
                    if self.parar.is_set():
                        relatorio.cancelado = True
                        break
                    if repeticoes == 0:
                        self.fila.put(
                            (
                                "log",
                                f"[repetição] volta {feitas} concluída; "
                                "recomeçando…",
                            )
                        )
                    relatorio = executor.rodar(de, ate)
                    feitas += 1
            except Exception as exc:
                LOG.exception("Erro inesperado na thread de execução")
                relatorio = Relatorio(erro=f"Erro inesperado: {exc}")
            finally:
                self.fila.put(("fim", relatorio))

        def iniciar_execucao():
            if not self.executando:
                return
            if self._hud is not None:
                self._hud.reexibir()
            else:
                self._mostrar_hud()
            threading.Thread(target=trabalho, daemon=True).start()

        def esconder_e_iniciar():
            if not self.executando:
                return
            # Mesmo padrão do indicador de gravação: cria o Toplevel antes de
            # esconder a janela e reexibe depois. Criar só depois também
            # funciona, mas assim o HUD nunca fica "preso" ao root escondido.
            self._mostrar_hud()
            try:
                self.root.withdraw()
            except tk.TclError:
                pass
            self.root.after(250, iniciar_execucao)

        def contagem(restante: int):
            if not self.executando:
                return
            if self.parar.is_set():
                self.fila.put(("log", "Execução cancelada antes de iniciar."))
                self.fila.put(("fim", Relatorio(cancelado=True)))
                return
            if restante > 0:
                self._status(f"Iniciando em {restante}s…", "aviso")
                self.fila.put(("log", f"Iniciando em {restante}s…"))
                self.root.after(1000, lambda: contagem(restante - 1))
                return
            esconder_e_iniciar()

        if simular:
            threading.Thread(target=trabalho, daemon=True).start()
            return

        try:
            espera = max(0, int(self.cfg.get("tempo_inicio", 0)))
        except (TypeError, ValueError):
            espera = 0
        if teste:
            # Dá tempo de o usuário tirar o mouse de cima do alvo.
            espera = max(2, espera)
            LOG.info("Modo teste: escondendo a janela para capturar a tela real.")
        else:
            LOG.info("Executando com a janela escondida.")
        contagem(espera)

    def _mostrar_hud(self) -> None:
        self._esconder_hud()
        try:
            self._hud = Hud(
                self.root, self.cfg.dados, self.fonte, self.tamanho, self.cores
            )
            self._hud.mostrar("Preparando…")
        except Exception:
            LOG.exception("Falha ao criar o HUD de execução")
            self._hud = None

    def _esconder_hud(self) -> None:
        if self._hud is not None:
            try:
                self._hud.esconder()
            except Exception:
                pass
        self._hud = None

    def _posicionar_hud(self, indice: int) -> None:
        if self._hud is None:
            return
        regiao = None
        try:
            passo = self.projeto.passos[indice]
            if passo.tipo.startswith("imagem_"):
                regiao = imagens.regiao_template(
                    str(passo.params.get("arquivo", ""))
                )
        except (IndexError, TypeError):
            pass
        self._hud.posicionar_para(regiao)

    def _iniciar_hotkeys(self) -> None:
        try:
            from pynput import keyboard
        except ImportError:
            return

        def ao_pressionar(key):
            try:
                if key == keyboard.Key.esc:
                    self.parar.set()
                elif key == keyboard.Key.f8:
                    self._alternar_pausa_thread()
            except Exception:
                pass

        try:
            ouvinte = keyboard.Listener(on_press=ao_pressionar)
            ouvinte.daemon = True
            ouvinte.start()
            self._hotkeys = ouvinte
        except Exception:
            self._hotkeys = None

    def _parar_hotkeys(self) -> None:
        if self._hotkeys is not None:
            try:
                self._hotkeys.stop()
            except Exception:
                pass
            self._hotkeys = None

    def _alternar_pausa_thread(self) -> None:
        if self.pausar.is_set():
            self.pausar.clear()
        else:
            self.pausar.set()

    def alternar_pausa(self) -> None:
        if not self.executando:
            return
        if self.pausar.is_set():
            self.pausar.clear()
            self._status("Execução retomada.", "ok")
            self.btn_pausar.configure(text="Pausar (F8)")
        else:
            self.pausar.set()
            self._status("Execução pausada. F8 para retomar.", "aviso")
            self.btn_pausar.configure(text="Retomar (F8)")

    def parar_execucao(self) -> None:
        if self.executando:
            self.parar.set()
            self._status("Parando…", "aviso")

    def _fim_execucao(self, relatorio: Relatorio) -> None:
        self.executando = False
        self._parar_hotkeys()
        self._esconder_hud()
        self.lista.marcar_atual(None)
        try:
            self.root.deiconify()
        except tk.TclError:
            pass
        self._atualizar_botoes()
        self.btn_pausar.configure(text="Pausar (F8)")
        if relatorio.cancelado:
            self._status(relatorio.resumo(), "aviso")
        elif relatorio.erro:
            self._status(relatorio.resumo(), "erro")
            detalhe = ""
            if relatorio.screenshot_erro:
                detalhe = f"\n\nScreenshot: {relatorio.screenshot_erro}"
            messagebox.showerror(
                "Falha na execução",
                relatorio.resumo() + detalhe,
                parent=self.root,
            )
        else:
            self._status(relatorio.resumo(), "ok")

    # ==================================================================
    # Gravação
    # ==================================================================
    def alternar_gravacao(self) -> None:
        if self.executando:
            return
        try:
            if self.root.grab_current() is not None:
                return
        except tk.TclError:
            pass
        if self.gravando or (self.rec is not None and self.rec.ativo):
            self._parar_gravacao()
        else:
            self._iniciar_gravacao()

    def _iniciar_gravacao(self) -> None:
        if self.gravando:
            return
        self._salvar_automatico()
        self.rec = GravadorEventos(
            self.cfg.dados,
            salvar_template=imagens.salvar_template
            if self.cfg.get("registrar_recorte")
            else None,
        )
        try:
            self.rec.iniciar()
        except Exception as exc:
            self.rec = None
            messagebox.showerror(
                "Gravação",
                "Não foi possível iniciar a gravação.\n\n"
                f"{exc}\n\nInstale: pip install pynput pillow",
                parent=self.root,
            )
            return
        self.gravando = True
        self._atualizar_botoes()
        self._mostrar_indicador()
        self._status("Gravando… F9 para parar, F10 pausa, ESC descarta.", "aviso")
        try:
            self.root.withdraw()
        except tk.TclError:
            pass
        self.root.after(200, self._reerguer_indicador)

    def _reerguer_indicador(self) -> None:
        if not self.gravando or self._indicador is None:
            return
        try:
            self._indicador.deiconify()
            self._indicador.lift()
            self._indicador.attributes("-topmost", True)
        except tk.TclError:
            pass

    def _parar_gravacao(self, descartar: bool = False) -> None:
        if self.rec is None:
            return
        self.rec.parar(descartar=descartar)
        if not self.rec.ativo and self.rec.resultado is not None:
            self._processar_gravacao()

    def descartar_gravacao(self) -> None:
        if self.rec is not None:
            self._parar_gravacao(descartar=True)

    def pausar_gravacao(self) -> None:
        if self.rec is None or not self.rec.ativo:
            return
        pausado = self.rec.alternar_pausa()
        self.btn_pausar_rec.configure(
            text="▶  Retomar" if pausado else "Ⅱ  Pausar"
        )
        self._atualizar_indicador()

    def _mostrar_indicador(self) -> None:
        cores = self.cores
        if self._indicador is not None:
            try:
                self._indicador.destroy()
            except tk.TclError:
                pass
        try:
            from nucleo.dpi import area_virtual

            vx, vy, vw, vh = area_virtual()
        except Exception:
            vx = vy = 0
            vw, vh = 1920, 1080
        largura, altura = 560, 46
        topo = tk.Toplevel(self.root)
        topo.overrideredirect(True)
        topo.configure(bg=cores["c_surface"])
        try:
            topo.attributes("-topmost", True)
            topo.attributes("-alpha", 0.97)
        except tk.TclError:
            pass
        topo.geometry(f"{largura}x{altura}+{vx + vw - largura - 24}+{vy + vh - altura - 60}")
        self._indicador_faixa = tk.Frame(topo, bg=cores["c_danger"], width=4)
        self._indicador_faixa.pack(side=tk.LEFT, fill=tk.Y)
        tk.Frame(topo, bg=cores["c_border"], height=1).pack(
            fill=tk.X, side=tk.BOTTOM
        )
        self._indicador_texto = tk.Label(
            topo,
            text="● GRAVANDO   F9 parar  •  F10 pausar  •  ESC descartar",
            bg=cores["c_surface"],
            fg=cores["c_fg"],
            font=(self.fonte, max(8, self.tamanho + 1), "bold"),
        )
        self._indicador_texto.pack(expand=True, fill=tk.BOTH, padx=12)
        try:
            topo.lift()
            topo.update_idletasks()
            arredondar_janela(topo, 16)
        except tk.TclError:
            pass
        self._indicador = topo

    def _atualizar_indicador(self) -> None:
        if self._indicador is None or self._indicador_texto is None:
            return
        try:
            if not self._indicador.winfo_exists():
                return
        except tk.TclError:
            return
        cores = self.cores
        if self.rec is None:
            return
        if self.rec.pausado:
            cor = cores["c_warning"]
            texto = (
                f"Ⅱ  PAUSADO  {self.rec.duracao:5.1f}s   F10 retomar  •  F9 parar"
            )
        else:
            cor = cores["c_danger"]
            texto = (
                f"●  GRAVANDO  {self.rec.duracao:5.1f}s  •  "
                f"{self.rec.total_eventos} eventos   F9 parar  •  F10 pausar"
            )
        try:
            self._indicador.configure(bg=cores["c_surface"])
            self._indicador_texto.configure(text=texto, bg=cores["c_surface"])
            self._indicador_faixa.configure(bg=cor)
        except (tk.TclError, AttributeError):
            pass

    def _esconder_indicador(self) -> None:
        if self._indicador is not None:
            try:
                self._indicador.destroy()
            except tk.TclError:
                pass
        self._indicador = None
        self._indicador_texto = None

    def _checar_gravacao(self) -> None:
        rec = self.rec
        if rec is None:
            return
        if rec.ativo:
            self.lbl_gravacao.configure(
                text=(
                    "Ⅱ  Pausado — F10 retoma"
                    if rec.pausado
                    else f"●  Gravando {rec.duracao:5.1f}s  •  "
                         "F9 para, F10 pausa, ESC descarta"
                ),
                fg=self.cores["c_warning"] if rec.pausado else self.cores["c_danger"],
            )
            self._atualizar_indicador()
            return
        if rec.resultado is None and rec.erro is None and not rec.descartado:
            return  # ainda convertendo
        self._processar_gravacao()

    def _processar_gravacao(self) -> None:
        rec = self.rec
        self.rec = None
        self.gravando = False
        self._esconder_indicador()
        try:
            self.root.deiconify()
            self.root.lift()
        except tk.TclError:
            pass
        self.btn_pausar_rec.configure(text="Ⅱ  Pausar")
        self.lbl_gravacao.configure(
            text="Pronto para gravar.",
            fg=self.cores["c_text_sub"],
        )
        self._atualizar_botoes()
        if rec is None:
            return
        if rec.erro:
            self._status("Falha ao converter a gravação.", "erro")
            messagebox.showerror(
                "Gravação", f"Não foi possível converter os eventos:\n\n{rec.erro}",
                parent=self.root,
            )
            return
        if rec.descartado:
            self._status("Gravação descartada.", "aviso")
            return
        novos = rec.resultado or []
        if not novos:
            self._status("Nenhum evento registrado.", "aviso")
            return
        self._snapshot()
        posicao = self._indice_insercao()
        for deslocamento, passo in enumerate(novos):
            self.projeto.passos.insert(posicao + deslocamento, passo)
        self._marcar_alterado()
        self._recarregar(posicao)
        self._status(f"{len(novos)} passo(s) gravado(s).", "ok")
        for aviso in rec._avisos:
            self._log(f"[gravação] {aviso}")

    # ==================================================================
    # Configuração
    # ==================================================================
    def _config_alterada(self, visual: bool = True) -> None:
        if self._timer_config:
            try:
                self.root.after_cancel(self._timer_config)
            except tk.TclError:
                pass
        self._timer_config = self.root.after(400, self._salvar_config)
        if visual:
            if self.executando or self.gravando:
                return
            if self._timer_visual:
                try:
                    self.root.after_cancel(self._timer_visual)
                except tk.TclError:
                    pass
            self._timer_visual = self.root.after(350, self._reconstruir_visual)

    def _salvar_config(self) -> None:
        self._timer_config = None
        try:
            self.cfg.salvar()
        except Exception as exc:
            self._log(f"[config] falha ao salvar: {exc}")

    def _reconstruir_visual(self) -> None:
        self._timer_visual = None
        if self.executando or self.gravando:
            return
        aba_atual = getattr(self, "_aba_atual", 0)
        for filho in self.root.winfo_children():
            if isinstance(filho, tk.Toplevel) and filho is not self._indicador:
                continue
            try:
                filho.destroy()
            except tk.TclError:
                pass
        self._construir()
        self._aplicar_estilos()
        self._mostrar_aba(aba_atual, notificar=False)
        self._recarregar()
        self._atualizar_botoes()

    def _abrir_pasta(self, chave: str) -> None:
        destino = {
            "imagens": caminhos.IMAGENS_DIR,
            "projetos": caminhos.PROJETOS_DIR,
            "logs": caminhos.LOGS_DIR,
            "base": caminhos.BASE_DIR,
        }.get(chave, caminhos.BASE_DIR)
        try:
            destino.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        dialogos.abrir_pasta(destino)

    # ==================================================================
    # Loop de eventos
    # ==================================================================
    def _poll(self) -> None:
        try:
            while True:
                tipo, dados = self.fila.get_nowait()
                try:
                    if tipo == "passo":
                        indice_passo = int(dados)
                        self.lista.marcar_atual(indice_passo)
                        self._posicionar_hud(indice_passo)
                    elif tipo == "hud":
                        if self._hud is not None:
                            self._hud.atualizar(str(dados))
                    elif tipo == "log":
                        self._log(str(dados))
                    elif tipo == "fim":
                        self._fim_execucao(dados)
                except Exception:
                    LOG.exception("Erro ao processar evento da fila (%s)", tipo)
        except queue.Empty:
            pass

        try:
            while True:
                self._log(self.fila_log.get_nowait())
        except queue.Empty:
            pass

        self._checar_gravacao()

        try:
            self.root.after(120, self._poll)
        except tk.TclError:
            pass

    # ==================================================================
    # Atalhos e fechamento
    # ==================================================================
    def _foco_editavel(self) -> bool:
        foco = self.root.focus_get()
        return isinstance(foco, (tk.Entry, tk.Text, ttk.Entry, ttk.Combobox, tk.Spinbox))

    def _ligar_atalhos(self) -> None:
        def atalho(sequencia, funcao, permitir_edicao=False):
            def wrapper(event=None):
                try:
                    if self.root.grab_current() is not None:
                        return None
                except tk.TclError:
                    pass
                if not permitir_edicao and self._foco_editavel():
                    return None
                funcao()
                return "break"

            self.root.bind_all(sequencia, wrapper)

        atalho("<Control-n>", self.novo_projeto)
        atalho("<Control-o>", self.abrir_projeto)
        atalho("<Control-s>", self.salvar)
        atalho("<Control-Shift-S>", self.salvar_como)
        atalho("<Control-g>", self.gerar_script)
        atalho("<Control-z>", self.desfazer)
        atalho("<Control-r>", self.executar_tudo)
        atalho("<F9>", self.alternar_gravacao)
        atalho("<F8>", self.alternar_pausa)
        atalho("<Escape>", self.parar_execucao)
        self.root.bind_all(
            "<Control-plus>", lambda _e: self._mudar_zoom(0.1), add="+"
        )
        self.root.bind_all(
            "<Control-minus>", lambda _e: self._mudar_zoom(-0.1), add="+"
        )

    def _mudar_zoom(self, delta: float) -> None:
        atual = float(self.cfg.get("fator_zoom", 1.0))
        novo = round(max(0.6, min(2.0, atual + delta)), 2)
        if novo != atual:
            self.cfg.set("fator_zoom", novo)
            self._config_alterada(visual=True)

    def mostrar_ajuda(self) -> None:
        messagebox.showinfo(
            "Atalhos e dicas",
            "Gravação\n"
            "  F9  — iniciar/parar a gravação\n"
            "  F10 — pausar/retomar a gravação\n"
            "  ESC — descartar a gravação em andamento\n\n"
            "Execução\n"
            "  Ctrl+R — executar tudo\n"
            "  F8 — pausar/retomar\n"
            "  ESC — parar\n\n"
            "Edição\n"
            "  Ctrl+Z — desfazer\n"
            "  Ctrl+S — salvar\n"
            "  Ctrl+G — gerar .py\n"
            "  Duplo clique — editar passo\n"
            "  Espaço — ativar/desativar passo\n"
            "  Delete — excluir passo\n\n"
            "Dicas\n"
            "  • Use passos de imagem em vez de coordenadas fixas quando a janela "
            "pode mudar de lugar.\n"
            "  • A confiança 0.90 costuma ser um bom equilíbrio.\n"
            "  • Use blocos para repetir trechos sem duplicar passos.\n"
            "  • O script gerado é autocontido: leve o .py e a pasta "
            "imagens_templates juntos.",
            parent=self.root,
        )

    def mostrar_sobre(self) -> None:
        messagebox.showinfo(
            "Sobre",
            "El Gravador 18 Pro Max\n\n"
            "Gravador e executor de automação de mouse, teclado e imagens.\n"
            "Projeto modular com núcleo independente da interface.\n\n"
            f"Python: {os.sys.version.split()[0]}\n"
            f"Pasta: {caminhos.BASE_DIR}\n"
            f"Projetos: {len(self.projeto.passos)} passo(s)",
            parent=self.root,
        )

    def fechar(self) -> None:
        if self.executando:
            if not self._fechando:
                if not messagebox.askyesno(
                    "Sair",
                    "Uma execução está em andamento. Parar e sair?",
                    parent=self.root,
                ):
                    return
                self._fechando = True
            self.parar.set()
            self.root.after(300, self.fechar)
            return
        if self.gravando or self.rec is not None:
            self._parar_gravacao(descartar=True)
        if not self._talvez_salvar():
            return
        self._parar_hotkeys()
        self._esconder_indicador()
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def iniciar(cfg: Config, projeto: Projeto | None = None) -> None:
    root = tk.Tk()
    try:
        escala = max(1.0, min(1.6, root.winfo_fpixels("1i") / 96.0))
    except tk.TclError:
        escala = 1.0
    largura = min(int(1080 * escala), max(900, root.winfo_screenwidth() - 120))
    altura = min(int(720 * escala), max(600, root.winfo_screenheight() - 120))
    root.geometry(f"{largura}x{altura}")
    root.minsize(int(920 * min(escala, 1.2)), int(620 * min(escala, 1.2)))
    app = Aplicativo(root, cfg, projeto)
    for aviso in getattr(cfg, "avisos", []):
        app._log(f"[config] {aviso}")
    app._ligar_atalhos()
    root.mainloop()
