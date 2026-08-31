# LabGUI — profilo grafico del laboratorio N47Lab (riusabile per tutti i progetti)
"""Profilo GUI condiviso: tema scuro, layout pulito, colonne colorate, status bar.
Uso nei progetti: from labgui import Finestra, Colonna, Pulsante
Profili: user-friendly, WYSIWYG — tutto ciò che accade appare nella finestra."""
import tkinter as tk
from tkinter import ttk, scrolledtext

PALETTE = {
    "sfondo": "#1e1f24",
    "pannello": "#2a2b31",
    "bordo": "#3a3b42",
    "testo": "#e8e9ec",
    "secondario": "#9aa0ab",
    "primario": "#6c8cff",
    "ambra": "#f0b429",
    "blu": "#4d9fff",
    "verde": "#34c77b",
    "viola": "#b07cff",
    "rosso": "#ff5c5c",
    "errore": "#ffb3b3",
}
FONT = ("Segoe UI", 10)
FONT_B = ("Segoe UI", 10, "bold")
FONT_H = ("Segoe UI", 11, "bold")


class Colonna(ttk.Frame):
    """Colonna di dialogo colorata: header con polo + area testo WYSIWYG."""
    def __init__(self, master, polo, colore, modello="", larghezza=380, modelli=None, on_change=None):
        super().__init__(master, style="Pannello.TFrame")
        header = tk.Frame(self, bg=PALETTE["pannello"])
        header.pack(fill="x", padx=1, pady=(1, 0))
        tk.Label(header, text=f"  {polo}  ", bg=colore, fg="#101014",
                 font=FONT_B, padx=10, pady=4).pack(side="left")
        if modelli is not None:
            self.combo = ttk.Combobox(header, values=modelli, state="readonly", width=24,
                                      font=("Segoe UI", 9))
            if modello in modelli:
                self.combo.set(modello)
            elif modelli:
                self.combo.current(0)
            self.combo.pack(side="left", padx=8, pady=3)
            self.on_change = on_change
            self.combo.bind("<<ComboboxSelected>>", lambda e: self.on_change(self.combo.get()))
            self.lbl_modello = None
        else:
            self.lbl_modello = tk.Label(header, text=modello, bg=PALETTE["pannello"], fg=PALETTE["secondario"],
                                        font=("Segoe UI", 9))
            self.lbl_modello.pack(side="left", padx=8)
        self.box = scrolledtext.ScrolledText(self, wrap="word", width=32, height=26,
                                             bg="#232429",
                                             fg=PALETTE["testo"], insertbackground=PALETTE["testo"],
                                             font=("Consolas", 10), relief="flat",
                                             highlightthickness=1, highlightbackground=PALETTE["bordo"])
        self.box.pack(fill="both", expand=True, padx=1, pady=(0, 1))
        self.box.configure(state="disabled")

    def descrizione(self, testo):
        if self.lbl_modello is not None:
            self.lbl_modello.configure(text=testo)

    def scrivi(self, testo):
        self.box.configure(state="normal")
        self.box.insert("end", testo + "\n\n")
        self.box.configure(state="disabled")
        self.box.see("end")


class Finestra(tk.Tk):
    """Finestra base con header, area contenuto e status bar."""
    def __init__(self, titolo, larghezza=1200, altezza=720):
        super().__init__()
        self.title(titolo)
        self.geometry(f"{larghezza}x{altezza}")
        self.minsize(900, 560)
        self.configure(bg=PALETTE["sfondo"])
        self._stile = ttk.Style(self)
        try:
            self._stile.theme_use("clam")
        except Exception:
            pass
        self._stile.configure("Pannello.TFrame", background=PALETTE["pannello"])
        self._stile.configure("TButton", font=FONT, padding=(10, 5), background=PALETTE["primario"],
                              foreground="#ffffff", borderwidth=0)
        self._stile.map("TButton", background=[("active", "#7d9bff"), ("disabled", "#4a4d57")])
        self._stile.configure("TEntry", font=FONT, fieldbackground="#232429",
                              foreground=PALETTE["testo"], insertcolor=PALETTE["testo"])
        self._stile.configure("TFrame", background=PALETTE["sfondo"])
        self.est = ttk.Frame(self)
        self.est.pack(fill="x", padx=8, pady=(6, 2))
        ttk.Label(self.est, text=titolo, font=FONT_H, foreground=PALETTE["testo"],
                  background=PALETTE["sfondo"]).pack(side="left")
        self._status = tk.Label(self, text="● pronto", anchor="w", bg=PALETTE["pannello"],
                                fg=PALETTE["secondario"], font=("Segoe UI", 9), padx=10, pady=4)
        self._status.pack(fill="x", side="bottom")
        self.contenuto = ttk.Frame(self)
        self.contenuto.pack(fill="both", expand=True, padx=8, pady=4)

    def stato(self, testo, colore=None):
        self._status.configure(text=testo, fg=colore or PALETTE["secondario"])

    def spinner(self, attivo=True):
        self._status.configure(text="● in elaborazione …" if attivo else "● pronto",
                               fg=PALETTE["ambra"] if attivo else PALETTE["secondario"])

    def bottone(self, padre, testo, comando, primario=False):
        return ttk.Button(padre, text=testo, command=comando)

    def domanda_bar(self, padre, invio_cb):
        bar = ttk.Frame(padre)
        bar.pack(fill="x", padx=8, pady=(6, 2))
        ttk.Label(bar, text="Ask the channel:  ", font=FONT_B,
                  foreground=PALETTE["testo"], background=PALETTE["sfondo"]).pack(side="left")
        entry = ttk.Entry(bar)
        entry.pack(side="left", fill="x", expand=True, padx=4)
        entry.bind("<Return>", lambda e: invio_cb(entry.get()))
        btn = ttk.Button(bar, text="▶ Send", command=lambda: invio_cb(entry.get()))
        btn.pack(side="left")
        return entry


class Registro(Colonna):
    """Colonna di sistema (messaggi del canale)."""
    def __init__(self, master, modello=""):
        super().__init__(master, "SISTEMA", PALETTE["pannello"], modello=modello)