"""Lista de passos com reordenação por arrastar, duplo clique e teclado."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from nucleo.projeto import Projeto


class ListaPassos(ttk.Frame):
    def __init__(
        self,
        parent,
        *,
        ao_editar: Callable[[int], None],
        ao_mover: Callable[[int, int], None],
        ao_alternar: Callable[[int], None],
        ao_excluir: Callable[[int], None],
        paleta: dict,
        fonte: str,
        tamanho: int,
    ):
        super().__init__(parent)
        self.ao_editar = ao_editar
        self.ao_mover = ao_mover
        self.ao_alternar = ao_alternar
        self.ao_excluir = ao_excluir
        self.paleta = paleta
        self.fonte = fonte
        self.tamanho = tamanho
        self._origem: int | None = None
        self._y_press: int = 0
        self._arrastando = False
        self._projeto: Projeto | None = None

        self.tree = ttk.Treeview(
            self, columns=("num", "tipo", "descricao"), show="headings", selectmode="browse"
        )
        self.tree.heading("num", text="#")
        self.tree.heading("tipo", text="Tipo")
        self.tree.heading("descricao", text="Passo")
        self.tree.column("num", width=40, anchor="center", stretch=False)
        self.tree.column("tipo", width=132, stretch=False)
        self.tree.column("descricao", width=380, stretch=True)

        barra = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=barra.set)
        barra.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.tree.tag_configure("inativo", foreground=paleta.get("c_comment", "#777777"))
        self.tree.tag_configure(
            "atual",
            background=paleta.get("c_accent", "#007aff"),
            foreground=paleta.get("c_on_accent", "#ffffff"),
        )
        self.tree.tag_configure("bloco", foreground=paleta.get("c_orange", "#ff9f0a"))
        self.tree.tag_configure("imagem", foreground=paleta.get("c_cyan", "#007aff"))

        self.tree.bind("<Double-1>", self._duplo_clique)
        self.tree.bind("<Return>", self._duplo_clique)
        self.tree.bind("<Delete>", self._excluir)
        self.tree.bind("<space>", self._alternar)
        self.tree.bind("<ButtonPress-1>", self._pressionar)
        self.tree.bind("<B1-Motion>", self._arrastar)
        self.tree.bind("<ButtonRelease-1>", self._soltar)

    # ------------------------------------------------------------------
    def recarregar(self, projeto: Projeto, indice: int | None = None) -> None:
        self._projeto = projeto
        selecionado = indice if indice is not None else self.selecionado()
        self.tree.delete(*self.tree.get_children())
        for i, passo in enumerate(projeto.passos):
            tags = []
            if not passo.ativo:
                tags.append("inativo")
            if passo.tipo.startswith("imagem_"):
                tags.append("imagem")
            if passo.tipo in ("bloco_inicio", "bloco_fim", "comentario"):
                tags.append("bloco")
            self.tree.insert(
                "",
                "end",
                iid=str(i),
                values=(i + 1, passo.tipo, passo.rotulo),
                tags=tuple(tags),
            )
        if selecionado is not None and 0 <= selecionado < len(projeto.passos):
            self.tree.selection_set(str(selecionado))
            self.tree.focus(str(selecionado))
            self.tree.see(str(selecionado))

    def selecionado(self) -> int | None:
        itens = self.tree.selection()
        if not itens:
            return None
        try:
            return int(itens[0])
        except ValueError:
            return None

    def marcar_atual(self, indice: int | None) -> None:
        for item in self.tree.get_children():
            tags = [t for t in self.tree.item(item, "tags") if t != "atual"]
            if indice is not None and item == str(indice):
                tags.append("atual")
                self.tree.see(item)
            self.tree.item(item, tags=tuple(tags))

    # ------------------------------------------------------------------
    def _duplo_clique(self, _event=None) -> None:
        indice = self.selecionado()
        if indice is not None:
            self.ao_editar(indice)

    def _excluir(self, _event=None) -> None:
        indice = self.selecionado()
        if indice is not None:
            self.ao_excluir(indice)

    def _alternar(self, _event=None) -> None:
        indice = self.selecionado()
        if indice is not None:
            self.ao_alternar(indice)

    def _pressionar(self, event) -> None:
        item = self.tree.identify_row(event.y)
        self._origem = int(item) if item else None
        self._y_press = event.y
        self._arrastando = False

    def _arrastar(self, event) -> None:
        if self._origem is None:
            return
        if abs(event.y - self._y_press) > 6:
            self._arrastando = True
            self.tree.configure(cursor="fleur")
            alvo = self.tree.identify_row(event.y)
            if alvo:
                self.tree.selection_set(alvo)

    def _soltar(self, event) -> None:
        self.tree.configure(cursor="")
        origem, self._origem = self._origem, None
        if not self._arrastando or origem is None:
            return
        self._arrastando = False
        item = self.tree.identify_row(event.y)
        if not item:
            return
        destino = int(item)
        if destino != origem:
            self.ao_mover(origem, destino)
