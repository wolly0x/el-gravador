"""Diálogos de edição de passo, escolha de template e avisos."""

from __future__ import annotations

import logging
import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Callable

from nucleo import imagens as imagens_mod
from nucleo import passos
from nucleo.tema import luminancia, paleta as montar_paleta
from .widgets import BotaoVidro, EntradaVidro, Switch, aplicar_borda_windows

LOG = logging.getLogger("elgravador")


class BaseDialogo(tk.Toplevel):
    def __init__(self, pai, titulo: str, cfg: dict):
        super().__init__(pai)
        self.paleta = montar_paleta(cfg.get("tema", "Apple Glass"), cfg.get("cores_custom") or {})
        self.cfg = cfg
        self.fonte = cfg.get("fonte", "Segoe UI")
        self.tamanho = max(7, int(cfg.get("tamanho_fonte", 9) * cfg.get("fator_zoom", 1.0)))
        self.resultado: Any = None
        self.title(titulo)
        self.configure(bg=self.paleta["c_bg"])
        self.transient(pai.winfo_toplevel() if hasattr(pai, "winfo_toplevel") else pai)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.cancelar)
        self.bind("<Escape>", lambda _e: self.cancelar())
        self.corpo = tk.Frame(
            self,
            bg=self.paleta["c_surface"],
            highlightthickness=1,
            highlightbackground=self.paleta["c_border"],
            bd=0,
        )
        self.corpo.pack(fill=tk.BOTH, expand=True, padx=14, pady=(14, 8))

    # ------------------------------------------------------------------
    def rotulo(self, texto: str, linha: int, coluna: int = 0) -> tk.Label:
        lbl = tk.Label(
            self.corpo,
            text=texto,
            bg=self.paleta["c_surface"],
            fg=self.paleta["c_fg"],
            font=(self.fonte, self.tamanho),
            anchor="w",
        )
        lbl.grid(row=linha, column=coluna, sticky="w", pady=3, padx=(0, 8))
        return lbl

    def dica(self, texto: str, linha: int, colunas: int = 2) -> None:
        tk.Label(
            self.corpo,
            text=texto,
            bg=self.paleta["c_surface"],
            fg=self.paleta["c_comment"],
            font=(self.fonte, max(7, self.tamanho - 1), "italic"),
            anchor="w",
            justify="left",
            wraplength=520,
        ).grid(row=linha, column=0, columnspan=colunas, sticky="w", pady=(4, 0))

    def entrada(self, valor: Any = "", largura: int = 12) -> EntradaVidro:
        var = tk.StringVar(value=str(valor))
        widget = EntradaVidro(
            self.corpo,
            paleta=self.paleta,
            fonte=self.fonte,
            tamanho=self.tamanho,
            var=var,
            largura=largura,
            altura=30,
            fundo=self.paleta["c_surface"],
        )
        widget.var = var  # type: ignore[attr-defined]
        return widget

    def combo(self, valores: list, valor: Any, largura: int = 24) -> ttk.Combobox:
        var = tk.StringVar(value=str(valor))
        widget = ttk.Combobox(
            self.corpo, values=[str(v) for v in valores], textvariable=var,
            state="readonly", width=largura,
        )
        widget.var = var  # type: ignore[attr-defined]
        return widget

    def caixa(self, texto: str, valor: bool, linha: int) -> tk.BooleanVar:
        var = tk.BooleanVar(value=bool(valor))
        Switch(
            self.corpo,
            paleta=self.paleta,
            var=var,
            texto=texto,
            fonte=self.fonte,
            tamanho=self.tamanho,
            fundo=self.paleta["c_surface"],
            largura=36,
            altura=20,
        ).grid(row=linha, column=0, columnspan=2, sticky="w", pady=2)
        return var

    def botao(self, parent, texto: str, comando, cor=None, largura: int = 12) -> BotaoVidro:
        return BotaoVidro(
            parent,
            texto=texto,
            comando=comando,
            paleta=self.paleta,
            fonte=self.fonte,
            tamanho=self.tamanho,
            cor=cor or self.paleta["c_surface_alt"],
            largura=largura,
            altura=30,
            raio=9,
            destaque=bool(cor and cor in {
                self.paleta["c_accent"], self.paleta["c_green"],
                self.paleta["c_red"], self.paleta["c_orange"],
            }),
        )

    def rodape(self, ao_confirmar: Callable[[], None]) -> None:
        barra = tk.Frame(self, bg=self.paleta["c_bg"])
        # Reserva o rodapé antes de devolver o corpo expansível ao pack.
        self.corpo.pack_forget()
        barra.pack(side=tk.BOTTOM, fill=tk.X, padx=14, pady=(0, 12))
        self.corpo.pack(fill=tk.BOTH, expand=True, padx=14, pady=(14, 8))
        self.botao(
            barra, "Confirmar", ao_confirmar, self.paleta["c_accent"]
        ).pack(side=tk.RIGHT)
        self.botao(
            barra, "Cancelar", self.cancelar, self.paleta["c_surface_alt"]
        ).pack(side=tk.RIGHT, padx=(0, 6))

        def enter(_event=None):
            if isinstance(self.focus_get(), tk.Text):
                return None
            ao_confirmar()
            return "break"

        self.bind("<Return>", enter)
        self.bind("<Control-Return>", lambda _e: ao_confirmar())

    def cancelar(self) -> None:
        self.resultado = None
        self.destroy()

    def exibir(self):
        self.update_idletasks()
        try:
            pai = self.master.winfo_toplevel()
            x = pai.winfo_rootx() + max(0, (pai.winfo_width() - self.winfo_width()) // 2)
            y = pai.winfo_rooty() + max(0, (pai.winfo_height() - self.winfo_height()) // 2)
            self.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass
        aplicar_borda_windows(self, luminancia(self.paleta["c_bg"]) < 0.5)
        self.grab_set()
        self.wait_window(self)
        return self.resultado


# ----------------------------------------------------------------------
# Ponto e região
# ----------------------------------------------------------------------
def capturar_ponto(
    janela: tk.Misc,
    ao_ponto: Callable[[tuple[int, int] | None], None],
    mensagem: str = "Clique no ponto desejado (ESC ou botão direito cancela)",
    extras: list | None = None,
) -> None:
    """Esconde a janela, captura um clique globalmente e devolve via callback."""
    import threading

    try:
        from pynput import keyboard, mouse
    except ImportError:
        messagebox.showerror(
            "pynput ausente",
            "Instale pynput para capturar cliques na tela:\n\npip install pynput",
            parent=janela,
        )
        ao_ponto(None)
        return

    estado: dict[str, Any] = {}
    pronto = threading.Event()
    extras = extras or []

    janela.withdraw()
    for extra in extras:
        try:
            extra.withdraw()
        except tk.TclError:
            pass
    janela.update_idletasks()
    try:
        janela.master.iconify()
    except Exception:
        pass

    def ao_clicar(x, y, button, pressed):
        if not pressed:
            return
        if button == mouse.Button.left:
            estado["ponto"] = (int(x), int(y))
            pronto.set()
            return False
        if button == mouse.Button.right:
            pronto.set()
            return False
        return None

    def ao_teclar(key):
        if key == keyboard.Key.esc:
            pronto.set()
            return False
        return None

    ouvinte_mouse = mouse.Listener(on_click=ao_clicar)
    ouvinte_teclado = keyboard.Listener(on_press=ao_teclar)
    ouvinte_mouse.start()
    ouvinte_teclado.start()

    def verificar():
        if not pronto.is_set():
            janela.after(60, verificar)
            return
        try:
            ouvinte_mouse.stop()
            ouvinte_teclado.stop()
        except Exception:
            pass
        try:
            janela.master.deiconify()
        except Exception:
            pass
        janela.deiconify()
        for extra in extras:
            try:
                if extra.winfo_exists():
                    extra.deiconify()
                    extra.lift()
                    extra.grab_set()
            except tk.TclError:
                pass
        ao_ponto(estado.get("ponto"))

    janela.after(60, verificar)


# ----------------------------------------------------------------------
# Escolha de template
# ----------------------------------------------------------------------
def escolher_template(pai, cfg: dict, inicial: str | None = None) -> str | None:
    dialogo = BaseDialogo(pai, "Templates de imagem", cfg)
    dialogo.geometry("700x420")

    lista = tk.Listbox(
        dialogo.corpo,
        bg=dialogo.paleta["c_surface_alt"],
        fg=dialogo.paleta["c_fg"],
        selectbackground=dialogo.paleta["c_accent"],
        selectforeground=dialogo.paleta["c_on_accent"],
        font=(dialogo.fonte, dialogo.tamanho),
        exportselection=False,
        width=34,
        relief=tk.FLAT,
        bd=0,
        highlightthickness=1,
        highlightbackground=dialogo.paleta["c_border"],
        activestyle="none",
    )
    lista.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
    dialogo.corpo.rowconfigure(0, weight=1)
    dialogo.corpo.columnconfigure(0, weight=1)

    previa = tk.Label(
        dialogo.corpo,
        text="(prévia)",
        bg=dialogo.paleta["c_surface_alt"],
        fg=dialogo.paleta["c_comment"],
        width=38,
        height=14,
    )
    previa.grid(row=0, column=1, sticky="nsew")
    referencia = {"imagem": None}

    itens = imagens_mod.listar()
    for item in itens:
        lista.insert(
            tk.END,
            f"{item['nome']}  ({item['largura']}x{item['altura']})",
        )
    if inicial:
        for i, item in enumerate(itens):
            if item["nome"] == inicial:
                lista.selection_set(i)
                lista.see(i)
                break

    def atualizar_previa(_event=None) -> None:
        selecao = lista.curselection()
        previa.configure(image="", text="(sem seleção)")
        referencia["imagem"] = None
        if not selecao:
            return
        item = itens[selecao[0]]
        try:
            from PIL import Image, ImageTk

            with Image.open(item["caminho"]) as img:
                copia = img.convert("RGB")
            copia.thumbnail((360, 260))
            foto = ImageTk.PhotoImage(copia)
            referencia["imagem"] = foto
            previa.configure(image=foto, text="")
        except Exception as exc:
            previa.configure(text=f"Sem prévia:\n{exc}")

    lista.bind("<<ListboxSelect>>", atualizar_previa)

    def usar() -> None:
        selecao = lista.curselection()
        if not selecao:
            messagebox.showinfo("Template", "Escolha um template.", parent=dialogo)
            return
        dialogo.resultado = itens[selecao[0]]["nome"]
        dialogo.destroy()

    def remover() -> None:
        selecao = lista.curselection()
        if not selecao:
            return
        item = itens[selecao[0]]
        if not messagebox.askyesno(
            "Remover template",
            f'Remover "{item["nome"]}"? Os passos que o usam vão falhar.',
            parent=dialogo,
        ):
            return
        imagens_mod.remover(item["nome"])
        dialogo.resultado = None
        dialogo.destroy()

    def importar() -> None:
        pasta = filedialog.askdirectory(
            title="Pasta com templates PNG (ex.: do gravador antigo)", parent=dialogo
        )
        if not pasta:
            return
        try:
            novos, iguais = imagens_mod.importar_pasta(pasta)
        except Exception as exc:
            messagebox.showerror("Importar", str(exc), parent=dialogo)
            return
        messagebox.showinfo(
            "Importar",
            f"{novos} template(s) importado(s), {iguais} já existiam.",
            parent=dialogo,
        )
        dialogo.destroy()
        dialogo.resultado = None

    barra = tk.Frame(dialogo.corpo, bg=dialogo.paleta["c_surface"])
    barra.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
    dialogo.botao(barra, "Importar pasta", importar, dialogo.paleta["c_surface_alt"]).pack(
        side=tk.LEFT
    )
    dialogo.botao(barra, "Remover", remover, dialogo.paleta["c_red"]).pack(
        side=tk.LEFT, padx=6
    )
    dialogo.botao(barra, "Usar selecionado", usar, dialogo.paleta["c_accent"], 16).pack(
        side=tk.RIGHT
    )
    dialogo.botao(barra, "Cancelar", dialogo.cancelar, dialogo.paleta["c_surface_alt"]).pack(
        side=tk.RIGHT, padx=6
    )
    lista.bind("<Double-1>", lambda _e: usar())
    if itens:
        lista.selection_set(0)
        atualizar_previa()
    return dialogo.exibir()


# ----------------------------------------------------------------------
# Editores por tipo
# ----------------------------------------------------------------------
def _num(texto: Any, padrao: float = 0.0, inteiro: bool = True):
    try:
        valor = float(str(texto).replace(",", "."))
    except (TypeError, ValueError):
        return padrao
    return int(valor) if inteiro else valor


def _parse_atalho(texto: str) -> list[str]:
    partes = [p.strip().lower() for p in texto.replace("+", ",").split(",")]
    return [p for p in partes if p]


def editar_passo(
    pai,
    passo,
    cfg: dict,
    *,
    capturar_ponto_cb: Callable | None = None,
    capturar_regiao_cb: Callable | None = None,
) -> tuple[str, dict] | None:
    tipo = passo.tipo
    params = dict(passo.params)
    dialogo = BaseDialogo(pai, f"Editar: {passos.rotulo(tipo, params)}", cfg)

    def finalizar() -> None:
        try:
            if tipo == "clicar":
                params.update(
                    {
                        "x": _num(x.var.get()),
                        "y": _num(y.var.get()),
                        "botao": botao.var.get(),
                        "cliques": max(1, _num(cliques.var.get(), 1)),
                        "duracao": max(0.0, _num(duracao.var.get(), 1.2, False)),
                    }
                )
            elif tipo == "mover":
                params.update(
                    {
                        "x": _num(x.var.get()),
                        "y": _num(y.var.get()),
                        "duracao": max(0.0, _num(duracao.var.get(), 1.2, False)),
                    }
                )
            elif tipo == "arrastar":
                params.update(
                    {
                        "x1": _num(x1.var.get()),
                        "y1": _num(y1.var.get()),
                        "x2": _num(x2.var.get()),
                        "y2": _num(y2.var.get()),
                        "duracao": max(0.0, _num(duracao.var.get(), 1.2, False)),
                        "botao": botao.var.get(),
                    }
                )
            elif tipo == "rolar":
                params.update(
                    {
                        "quantidade": _num(quantidade.var.get(), -5),
                        "x": _num(x.var.get()) if mover_antes.get() else None,
                        "y": _num(y.var.get()) if mover_antes.get() else None,
                    }
                )
            elif tipo == "digitar":
                texto = caixa_texto.get("1.0", "end-1c")
                params["texto"] = texto
                intervalo_txt = intervalo.var.get().strip()
                params["intervalo"] = (
                    max(0.0, _num(intervalo_txt, 0.08, False))
                    if intervalo_txt
                    else None
                )
            elif tipo == "atalho":
                teclas = _parse_atalho(atalho.var.get())
                if not teclas:
                    messagebox.showerror(
                        "Atalho", "Informe pelo menos uma tecla.", parent=dialogo
                    )
                    return
                params["teclas"] = teclas
            elif tipo == "tecla":
                params.update(
                    {
                        "nome": tecla.var.get(),
                        "repeticoes": max(1, _num(repeticoes.var.get(), 1)),
                    }
                )
            elif tipo == "pausa":
                params["segundos"] = max(0.0, _num(segundos.var.get(), 1.0, False))
            elif tipo == "bloco_inicio":
                params.update(
                    {
                        "vezes": max(1, _num(vezes.var.get(), 2)),
                        "nota": nota.var.get().strip(),
                    }
                )
            elif tipo == "comentario":
                params["texto"] = caixa_texto.get("1.0", "end-1c")
            elif tipo.startswith("imagem_"):
                nome = template.get().strip()
                if not nome:
                    messagebox.showerror(
                        "Imagem", "Escolha ou capture um template.", parent=dialogo
                    )
                    return
                params.update(
                    {
                        "arquivo": nome,
                        "timeout": max(0.1, _num(timeout.var.get(), 15, False)),
                        "confianca": min(
                            1.0, max(0.5, _num(confianca.var.get(), 0.9, False))
                        ),
                        "tentativas": max(1, _num(tentativas.var.get(), 2)),
                        "se_falhar": falhar.var.get(),
                    }
                )
                if tipo == "imagem_clicar":
                    params.update(
                        {
                            "duracao": max(0.0, _num(duracao.var.get(), 1.0, False)),
                            "offset": [
                                _num(offset_x.var.get()),
                                _num(offset_y.var.get()),
                            ],
                            "cliques": max(1, _num(cliques.var.get(), 1)),
                            "botao": botao.var.get(),
                            "fallback": (
                                [_num(fallback_x.var.get()), _num(fallback_y.var.get())]
                                if usar_fallback.get()
                                else None
                            ),
                        }
                    )
        except Exception as exc:
            messagebox.showerror("Valores inválidos", str(exc), parent=dialogo)
            return
        dialogo.resultado = (tipo, params)
        dialogo.destroy()

    # ------------------------------------------------------------------
    linha = 0
    if tipo in ("clicar", "mover"):
        dialogo.rotulo("Posição X:", linha)
        x = dialogo.entrada(params.get("x", 0), 10)
        x.grid(row=linha, column=1, sticky="w")
        dialogo.rotulo("Posição Y:", linha, 2)
        y = dialogo.entrada(params.get("y", 0), 10)
        y.grid(row=linha, column=3, sticky="w")
        linha += 1
        dialogo.rotulo("Duração do movimento (s):", linha)
        duracao = dialogo.entrada(params.get("duracao", 1.2), 10)
        duracao.grid(row=linha, column=1, sticky="w")
        linha += 1
        if tipo == "clicar":
            dialogo.rotulo("Botão:", linha)
            botao = dialogo.combo(["left", "right", "middle"], params.get("botao", "left"), 10)
            botao.grid(row=linha, column=1, sticky="w")
            dialogo.rotulo("Cliques:", linha, 2)
            cliques = dialogo.entrada(params.get("cliques", 1), 6)
            cliques.grid(row=linha, column=3, sticky="w")
            linha += 1
        if capturar_ponto_cb:
            dialogo.botao(
                dialogo.corpo, "Capturar ponto na tela",
                lambda: capturar_ponto_cb(
                    [dialogo],
                    lambda p: (x.var.set(str(p[0])), y.var.set(str(p[1]))) if p else None,
                ),
                dialogo.paleta["c_cyan"], 24,
            ).grid(row=linha, column=0, columnspan=4, sticky="w", pady=(8, 0))

    elif tipo == "arrastar":
        dialogo.rotulo("Origem X:", linha)
        x1 = dialogo.entrada(params.get("x1", 0), 9)
        x1.grid(row=linha, column=1, sticky="w")
        dialogo.rotulo("Origem Y:", linha, 2)
        y1 = dialogo.entrada(params.get("y1", 0), 9)
        y1.grid(row=linha, column=3, sticky="w")
        linha += 1
        dialogo.rotulo("Destino X:", linha)
        x2 = dialogo.entrada(params.get("x2", 0), 9)
        x2.grid(row=linha, column=1, sticky="w")
        dialogo.rotulo("Destino Y:", linha, 2)
        y2 = dialogo.entrada(params.get("y2", 0), 9)
        y2.grid(row=linha, column=3, sticky="w")
        linha += 1
        dialogo.rotulo("Duração (s):", linha)
        duracao = dialogo.entrada(params.get("duracao", 1.2), 9)
        duracao.grid(row=linha, column=1, sticky="w")
        dialogo.rotulo("Botão:", linha, 2)
        botao = dialogo.combo(["left", "right", "middle"], params.get("botao", "left"), 9)
        botao.grid(row=linha, column=3, sticky="w")
        linha += 1

    elif tipo == "rolar":
        dialogo.rotulo("Quantidade (+ cima / - baixo):", linha)
        quantidade = dialogo.entrada(params.get("quantidade", -5), 8)
        quantidade.grid(row=linha, column=1, sticky="w")
        linha += 1
        mover_antes = dialogo.caixa(
            "Posicionar o cursor antes de rolar", params.get("x") is not None, linha
        )
        linha += 1
        dialogo.rotulo("X:", linha)
        x = dialogo.entrada(params.get("x") or 0, 9)
        x.grid(row=linha, column=1, sticky="w")
        dialogo.rotulo("Y:", linha, 2)
        y = dialogo.entrada(params.get("y") or 0, 9)
        y.grid(row=linha, column=3, sticky="w")
        linha += 1

    elif tipo in ("digitar", "comentario"):
        dialogo.rotulo("Texto:", linha)
        linha += 1
        caixa_texto = tk.Text(
            dialogo.corpo,
            width=62,
            height=7 if tipo == "digitar" else 4,
            bg=dialogo.paleta["c_surface_alt"],
            fg=dialogo.paleta["c_fg"],
            insertbackground=dialogo.paleta["c_fg"],
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=dialogo.paleta["c_border"],
            wrap="word",
            font=(dialogo.fonte, dialogo.tamanho),
            padx=6,
            pady=5,
        )
        caixa_texto.grid(row=linha, column=0, columnspan=4, sticky="ew")
        caixa_texto.insert("1.0", params.get("texto", ""))
        caixa_texto.focus_set()
        linha += 1
        if tipo == "digitar":
            dialogo.rotulo("Intervalo entre letras (vazio = padrão):", linha)
            intervalo = dialogo.entrada(
                "" if params.get("intervalo") is None else params.get("intervalo"), 10
            )
            intervalo.grid(row=linha, column=1, sticky="w")
            linha += 1
            dialogo.dica(
                "Use {ENTER}, {TAB} ou {F5} no texto para pressionar teclas especiais.",
                linha, 4,
            )
            linha += 1

    elif tipo == "atalho":
        dialogo.rotulo("Teclas (ex.: ctrl+c ou ctrl, shift, s):", linha)
        atalho = dialogo.entrada("+".join(params.get("teclas") or []), 30)
        atalho.grid(row=linha, column=1, columnspan=3, sticky="w")
        linha += 1
        dialogo.dica(
            "Modificadores: ctrl, alt, shift, win. Teclas: letras, números, f1..f12, "
            "enter, tab, esc, setas.",
            linha, 4,
        )
        linha += 1

    elif tipo == "tecla":
        dialogo.rotulo("Tecla:", linha)
        tecla = dialogo.combo(passos.TECLAS_VALIDAS, params.get("nome", "enter"), 16)
        tecla.grid(row=linha, column=1, sticky="w")
        dialogo.rotulo("Repetições:", linha, 2)
        repeticoes = dialogo.entrada(params.get("repeticoes", 1), 6)
        repeticoes.grid(row=linha, column=3, sticky="w")
        linha += 1

    elif tipo == "pausa":
        dialogo.rotulo("Segundos:", linha)
        segundos = dialogo.entrada(params.get("segundos", 1.0), 10)
        segundos.grid(row=linha, column=1, sticky="w")
        linha += 1

    elif tipo == "bloco_inicio":
        dialogo.rotulo("Repetir quantas vezes:", linha)
        vezes = dialogo.entrada(params.get("vezes", 2), 8)
        vezes.grid(row=linha, column=1, sticky="w")
        linha += 1
        dialogo.rotulo("Nota (opcional):", linha)
        nota = dialogo.entrada(params.get("nota", ""), 30)
        nota.grid(row=linha, column=1, columnspan=3, sticky="w")
        linha += 1
        dialogo.dica("O bloco vai do passo seguinte até o passo 'FIM do bloco'.", linha, 4)
        linha += 1

    elif tipo.startswith("imagem_"):
        dialogo.rotulo("Template:", linha)
        template = tk.StringVar(value=params.get("arquivo", ""))
        seletor = tk.Frame(dialogo.corpo, bg=dialogo.paleta["c_surface"])
        seletor.grid(row=linha, column=1, columnspan=3, sticky="w")
        EntradaVidro(
            seletor,
            paleta=dialogo.paleta,
            fonte=dialogo.fonte,
            tamanho=dialogo.tamanho,
            var=template,
            largura=34,
            altura=30,
            fundo=dialogo.paleta["c_surface"],
        ).pack(side=tk.LEFT)
        dialogo.botao(
            seletor, "Escolher",
            lambda: _escolher_no_seletor(template, dialogo),
            dialogo.paleta["c_surface_alt"], 10,
        ).pack(side=tk.LEFT, padx=4)
        if capturar_regiao_cb:
            dialogo.botao(
                seletor, "Capturar",
                lambda: capturar_regiao_cb(
                    [dialogo], lambda nome: template.set(nome or template.get())
                ),
                dialogo.paleta["c_accent"], 10,
            ).pack(side=tk.LEFT)
        linha += 1
        dialogo.rotulo("Timeout (s):", linha)
        timeout = dialogo.entrada(params.get("timeout", 15), 8)
        timeout.grid(row=linha, column=1, sticky="w")
        dialogo.rotulo("Confiança:", linha, 2)
        confianca = dialogo.entrada(params.get("confianca", 0.9), 8)
        confianca.grid(row=linha, column=3, sticky="w")
        linha += 1
        dialogo.rotulo("Tentativas:", linha)
        tentativas = dialogo.entrada(params.get("tentativas", 2), 8)
        tentativas.grid(row=linha, column=1, sticky="w")
        dialogo.rotulo("Se falhar:", linha, 2)
        falhar = dialogo.combo(["abortar", "continuar"], params.get("se_falhar", "abortar"), 12)
        falhar.grid(row=linha, column=3, sticky="w")
        linha += 1

        def testar_imagem_agora() -> None:
            """Confere o template contra a tela real, com o app escondido."""
            nome = template.get().strip()
            if not nome:
                messagebox.showwarning(
                    "Testar imagem", "Escolha ou capture um template.", parent=dialogo
                )
                return
            if not imagens_mod.existe(nome):
                messagebox.showerror(
                    "Testar imagem",
                    f'Template "{nome}" não encontrado em '
                    f"{imagens_mod.caminho(nome).parent}.",
                    parent=dialogo,
                )
                return

            try:
                conf = float(str(confianca.var.get()).replace(",", "."))
            except (TypeError, ValueError):
                conf = 0.9
            conf = min(1.0, max(0.5, conf))
            try:
                tpl = imagens_mod.carregar(nome)
            except Exception as exc:
                messagebox.showerror("Testar imagem", str(exc), parent=dialogo)
                return

            raiz = dialogo.master.winfo_toplevel()
            try:
                dialogo.grab_release()
            except tk.TclError:
                pass
            dialogo.withdraw()
            try:
                raiz.withdraw()
            except tk.TclError:
                pass

            def capturar() -> None:
                if not dialogo.winfo_exists():
                    # Diálogo fechado durante a espera: não deixe o app sumido.
                    try:
                        raiz.deiconify()
                    except tk.TclError:
                        pass
                    return
                try:
                    tela, ox, oy = imagens_mod.capturar_tela()
                    resultado = imagens_mod.localizar_detalhado(
                        tela,
                        ox,
                        oy,
                        tpl,
                        conf,
                        None,
                        bool(dialogo.cfg.get("imagem_cinza", True)),
                    )
                    diagnostico = imagens_mod.salvar_diagnostico(
                        tela,
                        tpl,
                        resultado,
                        nome,
                        ox=ox,
                        oy=oy,
                        confianca=conf,
                        prefixo="diag_teste",
                    )
                except Exception as exc:
                    try:
                        raiz.deiconify()
                        dialogo.deiconify()
                        dialogo.grab_set()
                    except tk.TclError:
                        pass
                    messagebox.showerror("Testar imagem", str(exc), parent=dialogo)
                    return

                try:
                    raiz.deiconify()
                    raiz.lift()
                except tk.TclError:
                    pass
                try:
                    dialogo.deiconify()
                    dialogo.lift()
                    dialogo.grab_set()
                except tk.TclError:
                    pass

                if resultado.centro is not None:
                    texto = (
                        f"Encontrada em {resultado.centro}.\n"
                        f"Score: {resultado.score:.3f} "
                        f"(confiança {conf:.2f})."
                    )
                else:
                    texto = (
                        "Não encontrada.\n"
                        f"Melhor score: {resultado.melhor_score:.3f} "
                        f"(confiança {conf:.2f})."
                    )
                    if resultado.melhor_centro is not None:
                        texto += f"\nMelhor ponto: {resultado.melhor_centro}."
                if diagnostico:
                    texto += f"\n\nDiagnóstico: {diagnostico}"
                LOG.info(
                    "Teste de imagem %s: %s", nome, texto.replace("\n", " ")
                )
                messagebox.showinfo(
                    "Testar imagem agora", texto, parent=dialogo
                )

            dialogo.after(400, capturar)

        dialogo.botao(
            dialogo.corpo,
            "Testar imagem agora (esconde o app)",
            testar_imagem_agora,
            dialogo.paleta["c_green"],
            40,
        ).grid(row=linha, column=0, columnspan=4, sticky="w", pady=(8, 0))
        linha += 1
        dialogo.dica(
            "A janela do app é escondida por cerca de meio segundo para o "
            "teste enxergar a tela real. O resultado mostra o melhor score e "
            "salva um PNG em logs/.",
            linha,
            4,
        )
        linha += 1

        if tipo == "imagem_clicar":
            dialogo.rotulo("Offset X:", linha)
            offset_x = dialogo.entrada((params.get("offset") or [0, 0])[0], 8)
            offset_x.grid(row=linha, column=1, sticky="w")
            dialogo.rotulo("Offset Y:", linha, 2)
            offset_y = dialogo.entrada((params.get("offset") or [0, 0])[1], 8)
            offset_y.grid(row=linha, column=3, sticky="w")
            linha += 1
            dialogo.rotulo("Duração (s):", linha)
            duracao = dialogo.entrada(params.get("duracao", 1.0), 8)
            duracao.grid(row=linha, column=1, sticky="w")
            dialogo.rotulo("Cliques:", linha, 2)
            cliques = dialogo.entrada(params.get("cliques", 1), 8)
            cliques.grid(row=linha, column=3, sticky="w")
            linha += 1
            dialogo.rotulo("Botão:", linha)
            botao = dialogo.combo(["left", "right", "middle"], params.get("botao", "left"), 12)
            botao.grid(row=linha, column=1, sticky="w")
            linha += 1
            usar_fallback = dialogo.caixa(
                "Se a imagem não aparecer, clicar nesta coordenada reserva",
                params.get("fallback") is not None,
                linha,
            )
            linha += 1
            dialogo.rotulo("Reserva X:", linha)
            fallback_x = dialogo.entrada((params.get("fallback") or [0, 0])[0], 8)
            fallback_x.grid(row=linha, column=1, sticky="w")
            dialogo.rotulo("Reserva Y:", linha, 2)
            fallback_y = dialogo.entrada((params.get("fallback") or [0, 0])[1], 8)
            fallback_y.grid(row=linha, column=3, sticky="w")
            linha += 1
            dialogo.dica(
                "O offset desloca o clique em relação ao centro da imagem. "
                "A coordenada reserva é usada quando o template não é encontrado.",
                linha, 4,
            )
            linha += 1
        else:
            dialogo.dica(
                "Confiança abaixo de 1.0 usa OpenCV. Timeout é por tentativa.",
                linha, 4,
            )
            linha += 1

    elif tipo == "bloco_fim":
        tk.Label(
            dialogo.corpo,
            text="Este passo apenas fecha o bloco aberto mais recente.",
            bg=dialogo.paleta["c_surface"],
            fg=dialogo.paleta["c_fg"],
            font=(dialogo.fonte, dialogo.tamanho),
        ).grid(row=linha, column=0, columnspan=4, sticky="w")
        linha += 1

    else:
        tk.Label(
            dialogo.corpo,
            text=f"Tipo sem editor dedicado: {tipo}",
            bg=dialogo.paleta["c_surface"],
            fg=dialogo.paleta["c_comment"],
        ).grid(row=linha, column=0, columnspan=4, sticky="w")
        linha += 1

    dialogo.rodape(finalizar)
    return dialogo.exibir()


def _escolher_no_seletor(var: tk.StringVar, dialogo) -> None:
    nome = escolher_template(dialogo, dialogo.cfg, var.get() or None)
    if nome:
        var.set(nome)


# ----------------------------------------------------------------------
# Texto multi-linha (usado para digitar)
# ----------------------------------------------------------------------
def perguntar_texto(pai, cfg: dict, titulo: str, inicial: str = "") -> str | None:
    dialogo = BaseDialogo(pai, titulo, cfg)
    caixa = tk.Text(
        dialogo.corpo,
        width=62,
        height=8,
        bg=dialogo.paleta["c_surface_alt"],
        fg=dialogo.paleta["c_fg"],
        insertbackground=dialogo.paleta["c_fg"],
        relief="flat",
        bd=0,
        highlightthickness=1,
        highlightbackground=dialogo.paleta["c_border"],
        wrap="word",
        font=(dialogo.fonte, dialogo.tamanho),
        padx=6,
        pady=5,
    )
    caixa.pack(fill=tk.BOTH, expand=True)
    caixa.insert("1.0", inicial)
    caixa.focus_set()

    def confirmar() -> None:
        dialogo.resultado = caixa.get("1.0", "end-1c")
        dialogo.destroy()

    dialogo.bind("<Control-Return>", lambda _e: confirmar())
    dialogo.rodape(confirmar)
    return dialogo.exibir()


def perguntar_nome(pai, titulo: str, inicial: str = "") -> str | None:
    return simpledialog.askstring(titulo, "Nome:", initialvalue=inicial, parent=pai)


def abrir_pasta(caminho) -> None:
    try:
        if os.name == "nt":
            os.startfile(str(caminho))  # type: ignore[attr-defined]
        else:
            import subprocess

            subprocess.Popen(["xdg-open", str(caminho)])
    except Exception:
        pass
