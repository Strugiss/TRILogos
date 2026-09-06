# LabGUI — profilo grafico del laboratorio N47Lab (riusabile per tutti i progetti)
"""Profilo GUI condiviso: tema scuro, layout pulito, colonne colorate, status bar.
Uso nei progetti: from labgui import Finestra, Colonna, Pulsante
Profili: user-friendly, WYSIWYG — tutto ciò che accade appare nella finestra.
Stile ambra TRILogos: poli/pulsanti/bordi #f0b429, angoli arrotondati raggio 12
(lista punti di rounded.py, taglio 3px simmetrico)."""
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont

PALETTE = {
    "sfondo": "#1e1f24",
    "pannello": "#2a2b31",
    "bordo": "#3a3b42",
    "testo": "#e8e9ec",
    "secondario": "#9aa0ab",
    "primario": "#6c8cff",
    "ambra": "#f0b429",
    "ambra_hover": "#f7c948",
    "ambra_disabled": "#4a4d57",
    "ambra_thumb": "#8a6f1e",
    "testo_su_ambra": "#101014",
    "testo_disabled_btn": "#9aa0ab",
    "campo": "#232429",
    "selectbackground": "#f0b429",
    "selectforeground": "#101014",
    "bordo_cornici": "#f0b429",
    "track_scrollbar": "#1a1b1f",
    "blu": "#4d9fff",
    "verde": "#34c77b",
    "viola": "#b07cff",
    "rosso": "#ff5c5c",
    "errore": "#ffb3b3",
}
FONT = ("Segoe UI", 10)
FONT_B = ("Segoe UI", 10, "bold")
FONT_H = ("Segoe UI", 11, "bold")


def _punti_arrotondati(r, w, h):
    """Lista punti ESATTA di rounded.py per il rettangolo arrotondato smooth:
    la B-spline di Tk passa per i punti medi -> taglio reale 3px per lato.
    h-1 e w-1: l'outline inferiore/destro resta dentro il canvas (0..h-1)."""
    r = max(0, min(r, w / 2, h / 2))
    return [0, r, 0, 0, r, 0, w - r, 0, w, 0, w, r, w, h - 1 - r, w, h - 1,
            w - r, h - 1, r, h - 1, 0, h - 1, 0, h - 1 - r]


# Riferimenti globali: le PhotoImage della freccia NON devono mai finire nel GC
# (l'elemento del tema le usa via Tcl; senza riferimento Python verrebbero distrutte).
_IMGS_FRECCE = []


def _crea_freccia(root, sfondo, freccia, lar=21, alt=21):
    """Foto del pulsante freccia del combobox: quadrato ambra con triangolo
    scuro verso il basso (arrowcolor su clam/Windows colora solo il glifo,
    non il FONDO dell'area freccia: per lo sfondo serve un'immagine)."""
    img = tk.PhotoImage(master=root, width=lar, height=alt)
    img.put(sfondo, to=(0, 0, lar, alt))
    cx = lar // 2
    y_cima, y_punta, larga = 8, 14, 9
    for y in range(y_cima, y_punta + 1):
        f = (y - y_cima) / (y_punta - y_cima)
        meta = larga / 2 - (larga / 2 - 0.5) * f
        xl = int(cx - meta + 0.5)
        xr = int(cx + meta + 0.5)
        img.put(freccia, to=(xl, y, xr + 1, y + 1))
    _IMGS_FRECCE.append(img)
    return img


def _configura_combo_ambra(stile, root):
    """Stile 'Ambra.TCombobox': sostituisce l'elemento 'downarrow' con
    un'immagine (fondo ambra #f0b429, freccia scura #101014; hover #f7c948;
    disabled #4a4d57). Idempotente: se l'elemento esiste già non rifà nulla."""
    if "Ambra.downarrow" in stile.element_names():
        return
    img_norm = _crea_freccia(root, PALETTE["ambra"], PALETTE["testo_su_ambra"])
    img_hover = _crea_freccia(root, PALETTE["ambra_hover"], PALETTE["testo_su_ambra"])
    img_dis = _crea_freccia(root, PALETTE["ambra_disabled"], PALETTE["testo_disabled_btn"])
    stile.element_create("Ambra.downarrow", "image", img_norm,
                         ("hover", img_hover), ("active", img_hover),
                         ("disabled", img_dis), border=0)
    stile.layout("Ambra.TCombobox", [
        ("Combobox.field", {"sticky": "nswe", "children": [
            ("Ambra.downarrow", {"side": "right", "sticky": "ns"}),
            ("Combobox.padding", {"sticky": "nswe", "children": [
                ("Combobox.textarea", {"sticky": "nswe"})
            ]}),
        ]}),
    ])


class RiquadroRotondo(tk.Canvas):
    """Riquadro con angoli arrotondati (raggio 12, lista punti di rounded.py):
    canvas di sfondo + poligono pannello con bordo ambra 1px + frame interno
    (create_window, mai delete('all')). I contenuti vanno in .frame."""
    def __init__(self, master, raggio=12, margine=2, riempimento=None, bordo=None, bg=None):
        riempimento = riempimento or PALETTE["pannello"]
        bordo = bordo or PALETTE["bordo_cornici"]
        super().__init__(master, bg=bg or riempimento, highlightthickness=0, bd=0)
        self._raggio = raggio
        self._margine = margine
        self._riempimento = riempimento
        self._bordo = bordo
        self.frame = tk.Frame(self, bg=riempimento)
        self._item = self.create_window(0, 0, window=self.frame, anchor="nw", tags=("win",))
        self.bind("<Configure>", self._ridisegna)

    def aggiorna_req(self):
        """Allinea la requested size del canvas alla richiesta del frame interno:
        serve ai geometry manager (sticky 'n', colonne compresse a 900×600)."""
        self.update_idletasks()
        super().configure(width=self.frame.winfo_reqwidth(),
                          height=self.frame.winfo_reqheight())

    def _ridisegna(self, evento=None):
        lar, alt = self.winfo_width(), self.winfo_height()
        if lar <= 1 or alt <= 1:
            return
        self.delete("forma")
        punti = _punti_arrotondati(self._raggio, lar, alt)
        self.create_polygon(punti, smooth=True, fill=self._riempimento,
                            outline=self._bordo, width=1, tags=("forma",))
        m = self._margine
        self.coords(self._item, m, m)
        self.itemconfigure(self._item,
                           width=max(10, lar - 2 * m), height=max(10, alt - 2 * m))


class ComboRotonda(tk.Canvas):
    """Cornice arrotondata con combobox ttk interna (create_window, mai
    delete('all')): riquadro pannello + bordo ambra 1px, hover #f7c948,
    disabled #4a4d57. Dropdown NATIVO preservato (.combo).
    API: get/set/current + configure(values/state)."""
    def __init__(self, master, values=(), state="readonly", width=9, bg=None,
                 raggio=12, pad=2):
        super().__init__(master, bg=bg or PALETTE["pannello"], highlightthickness=0, bd=0)
        self._pad = pad
        self._raggio = raggio
        self._stato = state
        self._hover = False
        self.combo = ttk.Combobox(self, values=values, state=state, width=width,
                                  font=("Segoe UI", 9), style="Ambra.TCombobox")
        self._item = self.create_window(0, 0, window=self.combo, anchor="nw", tags=("win",))
        self.update_idletasks()
        super().configure(width=self.combo.winfo_reqwidth() + 2 * pad,
                          height=self.combo.winfo_reqheight() + 2 * pad)
        self.bind("<Configure>", self._ridisegna)
        self.bind("<Enter>", lambda e: self._hover_imposta(True))
        self.bind("<Leave>", lambda e: self._hover_imposta(False))

    def _bordo(self):
        if self._stato == "disabled":
            return PALETTE["ambra_disabled"]
        return PALETTE["ambra_hover"] if self._hover else PALETTE["bordo_cornici"]

    def _hover_imposta(self, attivo):
        self._hover = attivo
        self._ridisegna()

    def _ridisegna(self, evento=None):
        lar, alt = self.winfo_width(), self.winfo_height()
        if lar <= 1 or alt <= 1:
            return
        self.delete("forma")
        punti = _punti_arrotondati(self._raggio, lar, alt)
        self.create_polygon(punti, smooth=True, fill=PALETTE["pannello"],
                            outline=self._bordo(), width=1, tags=("forma",))
        p = self._pad
        self.coords(self._item, p, p)
        self.itemconfigure(self._item,
                           width=max(10, lar - 2 * p), height=max(10, alt - 2 * p))

    def get(self):
        return self.combo.get()

    def set(self, valore):
        self.combo.set(valore)

    def current(self, indice):
        self.combo.current(indice)

    def configure(self, **opzioni):
        if "values" in opzioni:
            self.combo.configure(values=opzioni.pop("values"))
        if "state" in opzioni:
            self._stato = opzioni.pop("state")
            self.combo.configure(state=self._stato)
            self._ridisegna()
        if opzioni:
            super().configure(**opzioni)


class BoxArrotondato(tk.Canvas):
    """Box di testo con 4 angoli arrotondati: canvas + poligono campo #232429
    con bordo ambra 1px + tk.Text (create_window) + scrollbar ttk accorciata
    6px in basso (angolo basso-destra libero). API del Text in .box."""
    def __init__(self, master, larghezza_ch=32, altezza_righe=4, bg=None, editabile=False):
        super().__init__(master, bg=bg or PALETTE["pannello"], highlightthickness=0, bd=0)
        self.box = tk.Text(self, wrap="word", width=larghezza_ch, height=altezza_righe,
                           bg=PALETTE["campo"], fg=PALETTE["testo"],
                           insertbackground=PALETTE["testo"], font=("Consolas", 10),
                           relief="flat", bd=0, highlightthickness=0,
                           selectbackground=PALETTE["selectbackground"],
                           selectforeground=PALETTE["selectforeground"])
        if not editabile:
            self.box.configure(state="disabled")
        self._scrollbar = ttk.Scrollbar(self, orient="vertical")
        self.box.configure(yscrollcommand=self._scrollbar.set)
        self._scrollbar.configure(command=self.box.yview)
        self._item = self.create_window(0, 0, window=self.box, anchor="nw", tags=("win",))
        self._item_sb = self.create_window(0, 0, window=self._scrollbar, anchor="nw",
                                           tags=("win",))
        self.update_idletasks()
        self._larghezza_sb = max(14, self._scrollbar.winfo_reqwidth())
        super().configure(width=self.box.winfo_reqwidth() + self._larghezza_sb + 8,
                          height=self.box.winfo_reqheight() + 4)
        self.bind("<Configure>", self._ridisegna)

    def _ridisegna(self, evento=None):
        lar, alt = self.winfo_width(), self.winfo_height()
        if lar <= 1 or alt <= 1:
            return
        self.delete("forma")
        punti = _punti_arrotondati(12, lar, alt)
        self.create_polygon(punti, smooth=True, fill=PALETTE["campo"],
                            outline=PALETTE["bordo_cornici"], width=1, tags=("forma",))
        m = 2
        sb = self._larghezza_sb
        self.coords(self._item, m, m)
        self.itemconfigure(self._item,
                           width=max(10, lar - 2 * m - sb - 2),
                           height=max(10, alt - 2 * m))
        self.coords(self._item_sb, lar - m - sb, m)
        self.itemconfigure(self._item_sb,
                           width=sb, height=max(10, alt - 2 * m - 6))


class Pill(tk.Canvas):
    """Etichetta a pillola: canvas + poligono ambra (lista punti di rounded.py)
    + testo scuro #101014 (contrasto 10.18:1 su #f0b429). configure(text=...)."""
    def __init__(self, master, testo="", colore=None, colore_testo=None, raggio=12,
                 padx=10, pady=4, bg=None):
        colore = colore or PALETTE["ambra"]
        colore_testo = colore_testo or PALETTE["testo_su_ambra"]
        self._testo = testo
        self._colore = colore
        self._colore_testo = colore_testo
        self._raggio = raggio
        self._padx = padx
        self._pady = pady
        self._font = tkfont.Font(root=master, family="Segoe UI", size=10, weight="bold")
        altezza = self._font.metrics("linespace") + 2 * pady + 4
        larghezza = self._font.measure(testo) + 2 * padx + 4
        super().__init__(master, width=larghezza, height=altezza,
                         bg=bg or PALETTE["pannello"], highlightthickness=0, bd=0)
        self.bind("<Configure>", self._disegna)

    def _disegna(self, evento=None):
        lar, alt = self.winfo_width(), self.winfo_height()
        if lar <= 1 or alt <= 1:
            return
        self.delete("all")
        punti = _punti_arrotondati(self._raggio, lar, alt)
        self.create_polygon(punti, smooth=True, fill=self._colore, outline="")
        self.create_text(lar / 2, alt / 2, text=self._testo, fill=self._colore_testo,
                         font=self._font)

    def configure(self, **opzioni):
        if "text" in opzioni:
            self._testo = opzioni.pop("text")
            self._disegna()
        if opzioni:
            super().configure(**opzioni)


class Colonna(ttk.Frame):
    """Colonna di dialogo: header con polo Pill ambra + combo modello + box
    arrotondato. self.polo esposto (fix struttura per la ritraduzione lingue)."""
    def __init__(self, master, polo, colore, modello="", larghezza=380, modelli=None,
                 on_change=None, altezza_box=26):
        super().__init__(master, style="Pannello.TFrame")
        header = tk.Frame(self, bg=PALETTE["pannello"])
        header.pack(fill="x", padx=1, pady=(1, 0))
        self.polo = Pill(header, testo=f"  {polo}  ")
        self.polo.pack(side="left")
        if modelli is not None:
            self.combo = ComboRotonda(header, values=modelli, width=24)
            if modello in modelli:
                self.combo.set(modello)
            elif modelli:
                self.combo.current(0)
            # combo a tutta larghezza del header (dopo il polo): i menu dei
            # modelli non vengono troncati, la colonna resta 335/325px.
            self.combo.pack(side="left", fill="x", expand=True, padx=6, pady=3)
            self.on_change = on_change
            self.combo.combo.bind("<<ComboboxSelected>>",
                                  lambda e: self.on_change(self.combo.get()))
            self.lbl_modello = None
        else:
            self.lbl_modello = tk.Label(header, text=modello, bg=PALETTE["pannello"],
                                        fg=PALETTE["secondario"], font=("Segoe UI", 9))
            self.lbl_modello.pack(side="left", padx=8)
        self.boxwrap = BoxArrotondato(self, altezza_righe=altezza_box)
        self.box = self.boxwrap.box
        self.boxwrap.pack(fill="both", expand=True, padx=1, pady=(0, 1))

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
        self._stile.configure("TFrame", background=PALETTE["sfondo"])
        self._stile.configure("TLabel", font=FONT, background=PALETTE["sfondo"],
                              foreground=PALETTE["testo"])
        self._stile.configure("TEntry", font=FONT, fieldbackground=PALETTE["campo"],
                              foreground=PALETTE["testo"], insertcolor=PALETTE["testo"],
                              selectbackground=PALETTE["selectbackground"],
                              selectforeground=PALETTE["selectforeground"],
                              bordercolor=PALETTE["pannello"],
                              lightcolor=PALETTE["pannello"], darkcolor=PALETTE["pannello"])
        self._stile.configure("TCombobox", font=("Segoe UI", 9), padding=(8, 3),
                              fieldbackground=PALETTE["campo"],
                              foreground=PALETTE["testo"], arrowcolor=PALETTE["ambra"],
                              bordercolor=PALETTE["pannello"],
                              lightcolor=PALETTE["pannello"], darkcolor=PALETTE["pannello"],
                              selectbackground=PALETTE["selectbackground"],
                              selectforeground=PALETTE["selectforeground"],
                              insertcolor=PALETTE["testo"])
        self._stile.map("TCombobox",
                        fieldbackground=[("readonly", PALETTE["campo"])],
                        foreground=[("readonly", PALETTE["testo"])],
                        arrowcolor=[("readonly", PALETTE["ambra"]),
                                    ("active", PALETTE["ambra_hover"])],
                        bordercolor=[("readonly", PALETTE["pannello"])])
        _configura_combo_ambra(self._stile, self)
        self._stile.configure("Vertical.TScrollbar", background=PALETTE["ambra_thumb"],
                              troughcolor=PALETTE["track_scrollbar"],
                              bordercolor=PALETTE["track_scrollbar"],
                              arrowcolor=PALETTE["secondario"],
                              lightcolor=PALETTE["ambra_thumb"],
                              darkcolor=PALETTE["ambra_thumb"])
        self._stile.map("Vertical.TScrollbar",
                        background=[("active", PALETTE["ambra"]),
                                    ("pressed", PALETTE["ambra"])])
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