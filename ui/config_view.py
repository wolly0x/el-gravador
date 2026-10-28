"""Aba de configurações (rolável), ligada diretamente ao Config."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from nucleo import imagens
from nucleo.config import Config
from .widgets import BotaoVidro, Cartao, Switch

CHAVES_VISUAIS = {
    "fonte",
    "tamanho_fonte",
    "fator_zoom",
}


class ConfigView(ttk.Frame):
    def __init__(
        self,
        parent,
        cfg: Config,
        ao_aplicar: Callable[[bool], None],
        ao_importar_templates: Callable[[], None] | None = None,
        ao_abrir_pasta: Callable[[str], None] | None = None,
    ):
        super().__init__(parent)
        self.cfg = cfg
        self.ao_aplicar = ao_aplicar
        self.ao_importar_templates = ao_importar_templates
        self.ao_abrir_pasta = ao_abrir_pasta
        self._construir()

    # ------------------------------------------------------------------
    @property
    def paleta(self) -> dict:
        return self.cfg.paleta()

    @property
    def fonte(self) -> str:
        return str(self.cfg.get("fonte", "Segoe UI"))

    @property
    def tamanho(self) -> int:
        return max(
            7, int(round(self.cfg.get("tamanho_fonte", 9) * self.cfg.get("fator_zoom", 1.0)))
        )

    def reconstruir(self) -> None:
        for filho in self.winfo_children():
            filho.destroy()
        self._construir()

    # ------------------------------------------------------------------
    def _construir(self) -> None:
        cores = self.paleta
        self.configure(style="Config.TFrame")

        canvas = tk.Canvas(
            self, bg=cores["c_bg"], highlightthickness=0, bd=0
        )
        barra = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=barra.set)
        # A barra é reservada antes do canvas expansível.
        barra.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        interno = tk.Frame(canvas, bg=cores["c_bg"])
        janela = canvas.create_window((0, 0), window=interno, anchor="nw")
        interno.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfigure(janela, width=e.width),
        )

        def rolar(event):
            numero = getattr(event, "num", 0)
            if numero == 4:
                passo = -1
            elif numero == 5:
                passo = 1
            else:
                delta = getattr(event, "delta", 0)
                if not delta:
                    return "break"
                passo = -1 if delta > 0 else 1
            canvas.yview_scroll(passo, "units")
            return "break"

        self._corpo = interno

        self._secao_aparencia()
        self._secao_tempos()
        self._secao_imagens()
        self._secao_gravacao()
        self._secao_diagnostico()

        # Liga a roda em toda a área rolável, inclusive sobre cartões e
        # rótulos. Evita o bind_all global, que continuava ativo ao sair da aba.
        def ligar_roda(widget) -> None:
            if isinstance(widget, (tk.Scale, tk.Spinbox, ttk.Combobox, ttk.Scrollbar)):
                return
            for sequencia in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                widget.bind(sequencia, rolar, add="+")
            for filho in widget.winfo_children():
                ligar_roda(filho)

        ligar_roda(canvas)

    # ------------------------------------------------------------------
    def _secao(self, titulo: str) -> tk.Frame:
        cores = self.paleta
        cartao = Cartao(
            self._corpo,
            paleta=cores,
            fundo=cores["c_bg"],
            bg=cores["c_surface"],
            raio=14,
            padding=12,
            sombra=True,
            altura_auto=True,
        )
        cartao.pack(fill=tk.X, padx=14, pady=(12, 0))
        caixa = cartao.conteudo
        tk.Label(
            caixa,
            text=titulo,
            bg=cores["c_surface"],
            fg=cores["c_accent"],
            font=(self.fonte, max(8, self.tamanho + 1), "bold"),
            anchor="w",
        ).pack(fill=tk.X, padx=2, pady=(0, 6))
        grade = tk.Frame(caixa, bg=cores["c_surface"])
        grade.pack(fill=tk.X)
        grade.columnconfigure(1, weight=1)
        return grade

    def _rotulo(self, pai, texto: str, linha: int) -> None:
        tk.Label(
            pai,
            text=texto,
            bg=self.paleta["c_surface"],
            fg=self.paleta["c_fg"],
            font=(self.fonte, self.tamanho),
            anchor="w",
        ).grid(row=linha, column=0, sticky="w", pady=3, padx=(0, 12))

    def _check(self, pai, texto: str, var: tk.BooleanVar, comando, linha: int) -> None:
        Switch(
            pai,
            paleta=self.paleta,
            var=var,
            comando=comando,
            texto=texto,
            fonte=self.fonte,
            tamanho=self.tamanho,
            fundo=self.paleta["c_surface"],
            largura=36,
            altura=20,
        ).grid(row=linha, column=0, columnspan=2, sticky="w", pady=2)

    def _definir(self, chave: str, valor) -> None:
        self.cfg.set(chave, valor)
        self.ao_aplicar(chave in CHAVES_VISUAIS)

    # ------------------------------------------------------------------
    def _secao_aparencia(self) -> None:
        grade = self._secao("Aparência")
        linha = 0

        self._rotulo(grade, "Fonte:", linha)
        combo_fonte = ttk.Combobox(
            grade,
            values=[
                "Segoe UI", "Inter", "Arial", "Calibri", "Verdana",
            ],
            width=18,
        )
        combo_fonte.set(self.fonte)
        combo_fonte.grid(row=linha, column=1, sticky="w")
        combo_fonte.bind(
            "<<ComboboxSelected>>", lambda _e: self._definir("fonte", combo_fonte.get())
        )
        linha += 1

        self._rotulo(grade, "Tamanho da fonte:", linha)
        self._spin(grade, "tamanho_fonte", 6, 30, 1, linha, inteiro=True)
        linha += 1

        self._rotulo(grade, "Zoom da interface:", linha)
        self._escala(grade, "fator_zoom", 0.6, 2.0, 0.05, linha)
        linha += 1

    # ------------------------------------------------------------------
    def _secao_tempos(self) -> None:
        grade = self._secao("Velocidade e fluidez")
        linha = 0
        self._rotulo(grade, "Duração do movimento do mouse (s):", linha)
        self._escala(grade, "duracao_movimento", 0.0, 3.0, 0.1, linha)
        linha += 1
        self._rotulo(grade, "Duração ao mover até uma imagem (s):", linha)
        self._escala(grade, "duracao_movimento_imagem", 0.0, 3.0, 0.1, linha)
        linha += 1
        self._rotulo(grade, "Pausa entre ações (s):", linha)
        self._escala(grade, "pausa_entre_acoes", 0.0, 2.0, 0.05, linha)
        linha += 1

        var_var = tk.BooleanVar(value=bool(self.cfg.get("pausa_entre_acoes_variavel")))
        self._check(
            grade, "Variar a pausa (parece mais humano)", var_var,
            lambda: self._definir("pausa_entre_acoes_variavel", var_var.get()), linha,
        )
        linha += 1

        self._rotulo(grade, "Intervalo entre letras (s):", linha)
        self._escala(grade, "intervalo_digitacao", 0.0, 0.5, 0.01, linha)
        linha += 1

        var_dig = tk.BooleanVar(value=bool(self.cfg.get("intervalo_digitacao_variavel")))
        self._check(
            grade, "Variar a digitação", var_dig,
            lambda: self._definir("intervalo_digitacao_variavel", var_dig.get()), linha,
        )
        linha += 1

        self._rotulo(grade, "Contagem antes de iniciar (s):", linha)
        self._spin(grade, "tempo_inicio", 0, 30, 1, linha, inteiro=True)
        linha += 1

        var_failsafe = tk.BooleanVar(value=bool(self.cfg.get("failsafe_ativo")))
        self._check(
            grade, "Parar tudo se o mouse for ao canto superior esquerdo (failsafe)",
            var_failsafe,
            lambda: self._definir("failsafe_ativo", var_failsafe.get()), linha,
        )
        linha += 1

    # ------------------------------------------------------------------
    def _secao_imagens(self) -> None:
        grade = self._secao("Busca por imagem")
        linha = 0
        self._rotulo(grade, "Tempo máximo por tentativa (s):", linha)
        self._spin(grade, "timeout_imagem", 0.5, 120, 0.5, linha, inteiro=False)
        linha += 1
        self._rotulo(grade, "Confiança mínima (0.5 a 1.0):", linha)
        self._escala(grade, "confianca_imagem", 0.5, 1.0, 0.01, linha)
        linha += 1
        self._rotulo(grade, "Tentativas:", linha)
        self._spin(grade, "tentativas_imagem", 1, 10, 1, linha, inteiro=True)
        linha += 1

        self._rotulo(grade, "Quando uma imagem não aparecer:", linha)
        combo = ttk.Combobox(
            grade,
            values=["abortar", "continuar"],
            state="readonly",
            width=14,
        )
        combo.set(str(self.cfg.get("ao_falhar")))
        combo.grid(row=linha, column=1, sticky="w")
        combo.bind(
            "<<ComboboxSelected>>", lambda _e: self._definir("ao_falhar", combo.get())
        )
        linha += 1

        var_cinza = tk.BooleanVar(value=bool(self.cfg.get("imagem_cinza")))
        self._check(
            grade, "Comparar em escala de cinza (mais rápido e tolerante a cor)",
            var_cinza,
            lambda: self._definir("imagem_cinza", var_cinza.get()), linha,
        )
        linha += 1

    # ------------------------------------------------------------------
    def _secao_gravacao(self) -> None:
        grade = self._secao("Gravação automática (F9)")
        linha = 0
        for chave, texto in (
            ("registrar_movimento", "Registrar movimentos livres do mouse"),
            ("registrar_recorte", "Criar template de imagem em cada clique"),
            ("registrar_pausas", "Inserir pausas onde você demorou"),
        ):
            var = tk.BooleanVar(value=bool(self.cfg.get(chave)))
            self._check(
                grade, texto, var,
                lambda c=chave, v=var: self._definir(c, v.get()), linha,
            )
            linha += 1

        self._rotulo(grade, "Tamanho do recorte automático:", linha)
        quadro = tk.Frame(grade, bg=self.paleta["c_surface"])
        quadro.grid(row=linha, column=1, sticky="w")
        self._spin(quadro, "recorte_largura", 24, 600, 10, 0, inteiro=True, lado=tk.LEFT)
        tk.Label(
            quadro, text="x", bg=self.paleta["c_surface"], fg=self.paleta["c_comment"]
        ).pack(side=tk.LEFT, padx=4)
        self._spin(quadro, "recorte_altura", 24, 600, 10, 0, inteiro=True, lado=tk.LEFT)
        linha += 1

        self._rotulo(grade, "Pausa mínima registrada (s):", linha)
        self._spin(grade, "pausa_minima_registro", 0.3, 30, 0.1, linha, inteiro=False)
        linha += 1
        tk.Label(
            grade,
            text="Dica: com recorte automático desligado, os cliques viram coordenadas "
                 "fixas. Ligado, cada clique vira um passo de imagem com coordenada de reserva.",
            bg=self.paleta["c_surface"],
            fg=self.paleta["c_comment"],
            font=(self.fonte, max(7, self.tamanho - 1), "italic"),
            wraplength=620,
            justify="left",
        ).grid(row=linha, column=0, columnspan=2, sticky="w", pady=(4, 0))
        linha += 1

    # ------------------------------------------------------------------
    def _secao_diagnostico(self) -> None:
        grade = self._secao("Diagnóstico")
        linha = 0
        estado = imagens.disponivel()
        import importlib.util

        modulos = {}
        for nome in ("pyautogui", "pynput"):
            try:
                modulos[nome] = (
                    "instalado"
                    if importlib.util.find_spec(nome) is not None
                    else "FALTANDO"
                )
            except Exception:
                modulos[nome] = "FALTANDO"
        texto = (
            f"Pillow: {'OK' if estado['pillow'] else 'FALTANDO'}   |   "
            f"numpy: {'OK' if estado['numpy'] else 'FALTANDO'}   |   "
            f"OpenCV: {'OK' if estado['opencv'] else 'FALTANDO (busca por imagem exige)'}\n"
            f"pyautogui: {modulos['pyautogui']}   |   pynput: {modulos['pynput']}"
        )
        tk.Label(
            grade,
            text=texto,
            bg=self.paleta["c_surface"],
            fg=self.paleta["c_fg"] if estado["opencv"] else self.paleta["c_orange"],
            font=(self.fonte, self.tamanho),
            justify="left",
        ).grid(row=linha, column=0, columnspan=2, sticky="w", pady=(0, 8))
        linha += 1

        botoes = tk.Frame(grade, bg=self.paleta["c_surface"])
        botoes.grid(row=linha, column=0, columnspan=2, sticky="w")
        for texto_botao, destino in (
            ("Abrir templates", "imagens"),
            ("Abrir projetos", "projetos"),
            ("Abrir logs", "logs"),
        ):
            BotaoVidro(
                botoes,
                texto=texto_botao,
                comando=lambda d=destino: self.ao_abrir_pasta(d) if self.ao_abrir_pasta else None,
                paleta=self.paleta,
                fonte=self.fonte,
                tamanho=max(7, self.tamanho - 1),
                cor=self.paleta["c_surface_alt"],
                fundo=self.paleta["c_surface"],
                altura=26,
                padding=9,
            ).pack(side=tk.LEFT, padx=(0, 6))
        if self.ao_importar_templates:
            BotaoVidro(
                botoes,
                texto="Importar templates…",
                comando=self.ao_importar_templates,
                paleta=self.paleta,
                fonte=self.fonte,
                tamanho=max(7, self.tamanho - 1),
                cor=self.paleta["c_accent"],
                destaque=True,
                fundo=self.paleta["c_surface"],
                altura=26,
                padding=10,
            ).pack(side=tk.LEFT, padx=(8, 0))
        linha += 1

    # ------------------------------------------------------------------
    # Controles
    # ------------------------------------------------------------------
    def _spin(
        self, pai, chave: str, minimo, maximo, passo, linha: int,
        inteiro: bool = True, lado=None,
    ) -> tk.Spinbox:
        var = tk.StringVar(value=_formatar(self.cfg.get(chave)))
        widget = tk.Spinbox(
            pai,
            from_=minimo,
            to=maximo,
            increment=passo,
            textvariable=var,
            width=8,
            bg=self.paleta["c_surface_alt"],
            fg=self.paleta["c_fg"],
            insertbackground=self.paleta["c_fg"],
            buttonbackground=self.paleta["c_surface_3"],
            relief="flat",
            highlightthickness=0,
            bd=0,
            font=(self.fonte, self.tamanho),
            command=lambda: self._aplicar_spin(chave, var, inteiro),
        )

        def commit(_event=None):
            self._aplicar_spin(chave, var, inteiro)

        widget.bind("<FocusOut>", commit)
        widget.bind("<Return>", commit)
        if lado is not None:
            widget.pack(side=lado)
        else:
            widget.grid(row=linha, column=1, sticky="w")
        return widget

    def _aplicar_spin(self, chave: str, var: tk.StringVar, inteiro: bool) -> None:
        try:
            valor = int(float(var.get().replace(",", "."))) if inteiro else float(
                var.get().replace(",", ".")
            )
        except (TypeError, ValueError):
            return
        self._definir(chave, valor)

    def _escala(self, pai, chave: str, minimo, maximo, passo, linha: int) -> None:
        var = tk.DoubleVar(value=float(self.cfg.get(chave)))
        quadro = tk.Frame(pai, bg=self.paleta["c_surface"])
        quadro.grid(row=linha, column=1, sticky="ew", pady=2)
        quadro.columnconfigure(0, weight=1)
        valor = tk.StringVar(value=_formatar(var.get()))

        def mudar(novo):
            var.set(float(novo))
            valor.set(_formatar(float(novo)))
            self._definir(chave, float(novo))

        escala = tk.Scale(
            quadro,
            from_=minimo,
            to=maximo,
            resolution=passo,
            orient=tk.HORIZONTAL,
            variable=var,
            showvalue=False,
            command=mudar,
            bg=self.paleta["c_surface"],
            fg=self.paleta["c_fg"],
            troughcolor=self.paleta["c_surface_3"],
            activebackground=self.paleta["c_accent"],
            highlightthickness=0,
            bd=0,
            sliderrelief="flat",
            length=260,
        )
        escala.grid(row=0, column=0, sticky="ew")
        tk.Label(
            quadro,
            textvariable=valor,
            width=6,
            anchor="e",
            bg=self.paleta["c_surface"],
            fg=self.paleta["c_accent"],
            font=(self.fonte, self.tamanho),
        ).grid(row=0, column=1, sticky="e", padx=(6, 0))


def _formatar(valor) -> str:
    if isinstance(valor, float):
        texto = f"{valor:.2f}".rstrip("0").rstrip(".")
        return texto or "0"
    return str(valor)
