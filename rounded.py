# TRILogos — pulsante con angoli arrotondati (canvas, tema scuro del laboratorio)
"""Pulsante rettangolare con angoli arrotondati (raggio 12, curvatura percepibile: taglio 2-3px reali per lato sui 4 angoli, simmetrico).
Sostituisce ttk.Button per le forme cliccabili del layout SENZA cambiarne le dimensioni:
- width in UNITÀ TESTO come ttk.Button (larghezza = measure('0') * width + padding del tema)
- altezza = linespace della font + padding del tema (10,5) -> identica a ttk
- il testo allunga il pulsante solo se più largo del minimo (come ttk.Button)
- hover, stato disabled, configure(text/state/command) come ttk.Button
- si ridisegna automaticamente al resize (pack expand/fill)"""
import tkinter as tk
from tkinter import font as tkfont

try:
    from labgui import PALETTE, FONT_B
except ImportError:
    from LabGUI.labgui import PALETTE, FONT_B

PADX = 10
PADY = 5


class PulsanteRotondo(tk.Canvas):
    def __init__(self, master, testo="", comando=None, width=0, raggio=12,
                 colore=PALETTE["ambra"], colore_hover="#f7c948",
                 colore_disabled="#4a4d57", colore_testo="#101014"):
        font = tkfont.Font(root=master, family="Segoe UI", size=10, weight="bold")
        unita = font.measure("0")
        margine = 2
        if width:
            self._larghezza_min = max(unita * width + 2 * PADX + margine, font.measure(testo) + 2 * PADX + 4)
        else:
            self._larghezza_min = max(font.measure(testo) + 2 * PADX + 4, 99)
        altezza = font.metrics("linespace") + 2 * PADY + margine
        super().__init__(master, width=self._larghezza_min, height=altezza,
                         bg=PALETTE["sfondo"], highlightthickness=0, bd=0, cursor="hand2")
        self._testo = testo
        self._comando = comando
        self._raggio = raggio
        self._colori = {"normal": colore, "hover": colore_hover, "disabled": colore_disabled}
        self._colore_testo = colore_testo
        self._stato = "normal"
        self.bind("<Configure>", lambda e: self._disegna())
        self.bind("<Enter>", self._hover_attiva)
        self.bind("<Leave>", self._hover_disattiva)
        self.bind("<Button-1>", self._clicca)
        self._disegna()

    def _disegna(self):
        self.delete("all")
        lar = self.winfo_width()
        alt = self.winfo_height()
        if lar <= 1 or alt <= 1:
            return
        r = min(self._raggio, alt / 2, lar / 2)
        colore = self._colori[self._stato]
        if r <= 0:
            self.create_rectangle(0, 0, lar, alt, fill=colore, outline="")
        else:
            punti = [0, r, 0, 0, r, 0, lar - r, 0, lar, 0, lar, r, lar, alt - 1 - r, lar, alt - 1,
                     lar - r, alt - 1, r, alt - 1, 0, alt - 1, 0, alt - 1 - r]
            self.create_polygon(punti, smooth=True, fill=colore, outline="")
        testo = self._testo
        font = tkfont.Font(root=self, family="Segoe UI", size=10, weight="bold")
        if font.measure(testo) > lar - 8:
            while testo and font.measure(testo + "…") > lar - 8:
                testo = testo[:-1]
            testo = testo + "…"
        fill_testo = self._colore_testo if self._stato != "disabled" \
            else PALETTE.get("testo_disabled_btn", "#9aa0ab")
        self.create_text(lar / 2, alt / 2, text=testo, fill=fill_testo,
                         font=FONT_B)

    def _hover_attiva(self, evento):
        if self._stato == "normal":
            self._stato = "hover"
            self._disegna()

    def _hover_disattiva(self, evento):
        if self._stato == "hover":
            self._stato = "normal"
            self._disegna()

    def _clicca(self, evento):
        if self._stato in ("normal", "hover") and self._comando is not None:
            self._comando()

    def configure(self, **opzioni):
        if "text" in opzioni:
            self._testo = opzioni.pop("text")
            font = tkfont.Font(root=self, family="Segoe UI", size=10, weight="bold")
            nuova = max(self._larghezza_min, font.measure(self._testo) + 2 * PADX + 4)
            super().configure(width=nuova)
            self._disegna()
        if "command" in opzioni:
            self._comando = opzioni.pop("command")
        if "state" in opzioni:
            self._stato = "disabled" if opzioni.pop("state") == "disabled" else "normal"
            super().configure(cursor="arrow" if self._stato == "disabled" else "hand2")
            self._disegna()
        if opzioni:
            super().configure(**opzioni)