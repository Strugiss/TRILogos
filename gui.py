# TRILogos — GUI a tre colonne, profilo LabGUI (user-friendly, WYSIWYG)
"""Flusso automatico: domanda → Invio → A formula per LLM2 → dibattito →
sintesi → risposta univoca consensuale. Selettore lingua (IT/EN) per
interfaccia e risposte dei modelli."""
import sys, os, json, threading
import tkinter as tk
from tkinter import ttk
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "LabGUI"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".opencode", "shared", "LabGUI"))
from labgui import Finestra, Colonna, PALETTE
from core.modelli import crea_modello, modelli_disponibili, modello_da_voce
from core.clienti import rileva_clienti, voci_modelli, aggiunti, salva_aggiunti
from core.timeline import aggiungi_sessione
from core.canale import Canale

VERSIONE = "1.0.0"

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG = json.load(open(os.path.join(BASE, "config.json"), encoding="utf-8"))
_PROFILI_LOCALI = os.path.join(BASE, "profili_n47lab.json")
if os.path.exists(_PROFILI_LOCALI):
    _locali = json.load(open(_PROFILI_LOCALI, encoding="utf-8"))
    CONFIG.setdefault("profili", {}).update(_locali)

TESTI = {
    "it": {
        "titolo": "TRILogos — dialogo a tre voci (utente · LLM · LLM2)",
        "barra": "Domanda al canale:",
        "invia": "▶ Invia",
        "completo": "▶ Avvia (completo)",
        "dibattito": "⚡ Dibattito LLM↔LLM2",
        "sintesi": "✓ Sintesi e lavori",
        "univoca": "◆ Risposta univoca",
        "salva": "💾 Salva sessione",
        "svuota": "✖ Svuota canale",
        "utente": "UTENTE",
        "a": "LLM",
        "b": "LLM2",
        "finale": "RISPOSTA UNIVOCA",
        "descr_utente": "il supervisore",
        "descr_finale": "il verdetto del canale",
        "pronto": "pronto",
        "lavoro": "in elaborazione …",
        "chiedi_prima": "Scrivi prima una domanda nella barra in alto.",
        "formula": "… sta formulando la richiesta per LLM2 …",
        "pos_a": "[posizione finale]",
        "pos_b": "[posizione finale]",
        "rev_b": "[revisione di LLM2]",
        "sint_ok": "sintesi e risposta univoca …",
        "fine_ok": "risposta univoca condivisa pronta",
        "opzioni": "⚙ Opzioni",
        "cartella": "📁 Cartella",
        "add": "＋ ADD",
        "cross": "🛡 Cross-check",
    },
    "en": {
        "titolo": "TRILogos — three-voice dialogue (user · LLM · LLM2)",
        "barra": "Ask the channel:",
        "invia": "▶ Send",
        "completo": "▶ Run (full)",
        "dibattito": "⚡ Debate LLM↔LLM2",
        "sintesi": "✓ Summary & tasks",
        "univoca": "◆ Unanimous answer",
        "salva": "💾 Save session",
        "svuota": "✖ Clear channel",
        "utente": "YOU",
        "a": "LLM",
        "b": "LLM2",
        "finale": "UNANIMOUS ANSWER",
        "descr_utente": "the supervisor",
        "descr_finale": "the channel's verdict",
        "pronto": "ready",
        "lavoro": "working …",
        "chiedi_prima": "Type a question in the bar first.",
        "formula": "… formulating the request for LLM2 …",
        "pos_a": "[final position]",
        "pos_b": "[final position]",
        "rev_b": "[LLM2 revision]",
        "sint_ok": "summary and unanimous answer …",
        "fine_ok": "unanimous shared answer ready",
        "opzioni": "⚙ Options",
        "cartella": "📁 Folder",
        "add": "＋ ADD",
        "cross": "🛡 Cross-check",
    },
    "fr": {
        "titolo": "TRILogos — dialogue à trois voix (utilisateur · LLM · LLM2)",
        "barra": "Question au canal :",
        "invia": "▶ Envoyer",
        "completo": "▶ Lancer (complet)",
        "dibattito": "⚡ Débat LLM↔LLM2",
        "sintesi": "✓ Synthèse et tâches",
        "univoca": "◆ Réponse unanime",
        "salva": "💾 Sauvegarder",
        "svuota": "✖ Vider",
        "utente": "VOUS",
        "a": "LLM",
        "b": "LLM2",
        "finale": "RÉPONSE UNANIME",
        "descr_utente": "le superviseur",
        "descr_finale": "le verdict du canal",
        "pronto": "prêt",
        "lavoro": "en cours …",
        "chiedi_prima": "Écrivez d'abord une question dans la barre.",
        "formula": "… formule la demande pour LLM2 …",
        "pos_a": "[position finale]",
        "pos_b": "[position finale]",
        "rev_b": "[révision de LLM2]",
        "sint_ok": "synthèse et réponse unanime …",
        "fine_ok": "réponse unanime partagée prête",
        "opzioni": "⚙ Options",
        "cartella": "📁 Dossier",
        "add": "＋ AJOUTER",
        "cross": "🛡 Vérification",
    },
    "es": {
        "titolo": "TRILogos — diálogo a tres voces (usuario · LLM · LLM2)",
        "barra": "Pregunta al canal:",
        "invia": "▶ Enviar",
        "completo": "▶ Ejecutar (completo)",
        "dibattito": "⚡ Debate LLM↔LLM2",
        "sintesi": "✓ Resumen y tareas",
        "univoca": "◆ Respuesta unánime",
        "salva": "💾 Guardar",
        "svuota": "✖ Vaciar",
        "utente": "USTED",
        "a": "LLM",
        "b": "LLM2",
        "finale": "RESPUESTA UNÁNIME",
        "descr_utente": "el supervisor",
        "descr_finale": "el veredicto del canal",
        "pronto": "listo",
        "lavoro": "procesando …",
        "chiedi_prima": "Escribe primero una pregunta en la barra.",
        "formula": "… formula la solicitud para LLM2 …",
        "pos_a": "[posición final]",
        "pos_b": "[posición final]",
        "rev_b": "[revisión de LLM2]",
        "sint_ok": "resumen y respuesta unánime …",
        "fine_ok": "respuesta unánime compartida lista",
        "opzioni": "⚙ Opciones",
        "cartella": "📁 Carpeta",
        "add": "＋ AÑADIR",
        "cross": "🛡 Verificación",
    },
    "de": {
        "titolo": "TRILogos — Dialog mit drei Stimmen (Nutzer · LLM · LLM2)",
        "barra": "Frage an den Kanal:",
        "invia": "▶ Senden",
        "completo": "▶ Starten (vollständig)",
        "dibattito": "⚡ Debatte LLM↔LLM2",
        "sintesi": "✓ Zusammenfassung & Aufgaben",
        "univoca": "◆ Einstimmige Antwort",
        "salva": "💾 Speichern",
        "svuota": "✖ Leeren",
        "utente": "NUTZER",
        "a": "LLM",
        "b": "LLM2",
        "finale": "EINSTIMMIGE ANTWORT",
        "descr_utente": "der Betreuer",
        "descr_finale": "das Urteil des Kanals",
        "pronto": "bereit",
        "lavoro": "arbeitet …",
        "chiedi_prima": "Schreiben Sie zuerst eine Frage in die Leiste.",
        "formula": "… formuliert die Anfrage für LLM2 …",
        "pos_a": "[Endposition]",
        "pos_b": "[Endposition]",
        "rev_b": "[LLM2-Überarbeitung]",
        "sint_ok": "Zusammenfassung und einstimmige Antwort …",
        "fine_ok": "gemeinsame einstimmige Antwort bereit",
        "opzioni": "⚙ Optionen",
        "cartella": "📁 Ordner",
        "add": "＋ HINZUFÜGEN",
        "cross": "🛡 Prüfung",
    },
    "pt": {
        "titolo": "TRILogos — diálogo a três vozes (usuário · LLM · LLM2)",
        "barra": "Pergunta ao canal:",
        "invia": "▶ Enviar",
        "completo": "▶ Executar (completo)",
        "dibattito": "⚡ Debate LLM↔LLM2",
        "sintesi": "✓ Resumo e tarefas",
        "univoca": "◆ Resposta unânime",
        "salva": "💾 Salvar",
        "svuota": "✖ Limpar",
        "utente": "VOCÊ",
        "a": "LLM",
        "b": "LLM2",
        "finale": "RESPOSTA UNÂNIME",
        "descr_utente": "o supervisor",
        "descr_finale": "o veredito do canal",
        "pronto": "pronto",
        "lavoro": "processando …",
        "chiedi_prima": "Escreva primeiro uma pergunta na barra.",
        "formula": "… formula o pedido para LLM2 …",
        "pos_a": "[posição final]",
        "pos_b": "[posição final]",
        "rev_b": "[revisão do LLM2]",
        "sint_ok": "resumo e resposta unânime …",
        "fine_ok": "resposta unânime compartilhada pronta",
        "opzioni": "⚙ Opções",
        "cartella": "📁 Pasta",
        "add": "＋ ADICIONAR",
        "cross": "🛡 Verificação",
    },
    "zh": {
        "titolo": "TRILogos — 三方对话（用户 · LLM · LLM2）",
        "barra": "向频道提问：",
        "invia": "▶ 发送",
        "completo": "▶ 运行（完整）",
        "dibattito": "⚡ 辩论 LLM↔LLM2",
        "sintesi": "✓ 总结与分工",
        "univoca": "◆ 一致回答",
        "salva": "💾 保存会话",
        "svuota": "✖ 清空",
        "utente": "用户",
        "a": "LLM",
        "b": "LLM2",
        "finale": "一致回答",
        "descr_utente": "主管",
        "descr_finale": "频道的最终裁决",
        "pronto": "就绪",
        "lavoro": "处理中 …",
        "chiedi_prima": "请先在顶部输入问题。",
        "formula": "… 正在为 LLM2 拟定请求 …",
        "pos_a": "[最终立场]",
        "pos_b": "[最终立场]",
        "rev_b": "[LLM2 修订]",
        "sint_ok": "总结与一致回答 …",
        "fine_ok": "一致回答已就绪",
        "opzioni": "⚙ 选项",
        "cartella": "📁 文件夹",
        "add": "＋ 添加",
        "cross": "🛡 核查",
    },
}


def costruisci_canale(lingua="it", profilo=None):
    m = CONFIG["modelli"]
    a = crea_modello(m["A"]["tipo"], modello=m["A"].get("modello"))
    b = crea_modello(m["B"]["tipo"], modello=m["B"].get("modello"))
    profilo = profilo or next(iter(CONFIG["profili"]))
    ruoli = CONFIG["profili"].get(profilo) or next(iter(CONFIG["profili"].values()))
    return Canale(a, b,
                  ruolo_a=ruoli["A"],
                  ruolo_b=ruoli["B"],
                  max_turni_dibattito=CONFIG["canale"]["max_turni_dibattito"],
                  soglia_convergenza=CONFIG["canale"]["soglia_convergenza"],
                  lingua=lingua,
                  max_chiamate=CONFIG["canale"].get("max_chiamate", 40))


class TrilogoApp(Finestra):
    def __init__(self):
        super().__init__(f"{TESTI['it']['titolo']}  ·  v{VERSIONE}")
        self.lingua = "it"
        self.opzioni = modelli_disponibili()
        self.clienti = rileva_clienti()
        self.opzioni = voci_modelli(self.clienti)
        self.canale = costruisci_canale(self.lingua)
        self.dibattito_risultato = None
        self._busy = False
        self._costruisci()
        self._applica_lingua()

    def _inizia_lavoro(self):
        if self._busy:
            return False
        self._busy = True
        for chiave in ("completo", "dibattito", "sintesi", "univoca", "cross"):
            self.bottoni[chiave].configure(state="disabled")
        self.spinner(True)
        self.update_idletasks()
        return True

    def _fine_lavoro(self):
        self._busy = False
        for chiave in ("completo", "dibattito", "sintesi", "univoca", "cross"):
            self.bottoni[chiave].configure(state="normal")
        self.spinner(False)

    def _costruisci(self):
        # barra domanda + selettore lingua
        bar = ttk.Frame(self.contenuto)
        bar.pack(fill="x", padx=8, pady=(6, 2))
        self.lbl_barra = ttk.Label(bar, font=("Segoe UI", 10, "bold"),
                                   foreground=PALETTE["testo"], background=PALETTE["sfondo"])
        self.lbl_barra.pack(side="left")
        self.domanda = ttk.Entry(bar)
        self.domanda.pack(side="left", fill="x", expand=True, padx=4)
        self.domanda.bind("<Return>", lambda e: self._completo())
        self.btn_invia = ttk.Button(bar, command=lambda: self._completo())
        self.btn_invia.pack(side="left")
        ttk.Label(bar, text="  🌐", background=PALETTE["sfondo"]).pack(side="left", padx=(8, 2))
        self.combo_lingua = ttk.Combobox(bar, values=["Italiano", "English", "Français", "Español", "Deutsch", "Português", "中文"], state="readonly", width=9)
        self.combo_lingua.current(0)
        self.combo_lingua.bind("<<ComboboxSelected>>", lambda e: self._cambia_lingua())
        self.combo_lingua.pack(side="left")
        ttk.Label(bar, text="  👥", background=PALETTE["sfondo"]).pack(side="left", padx=(6, 2))
        self.combo_profilo = ttk.Combobox(bar, values=list(CONFIG["profili"].keys()), state="readonly", width=9)
        self.combo_profilo.set(next(iter(CONFIG["profili"])))
        self.combo_profilo.bind("<<ComboboxSelected>>", lambda e: self._cambia_profilo())
        self.combo_profilo.pack(side="left")

        # bottoni, allineati a larghezza uniforme
        riga = ttk.Frame(self.contenuto)
        riga.pack(fill="x", padx=2, pady=2)
        self.bottoni = {}
        for chiave in ("completo", "dibattito", "sintesi", "univoca", "salva", "svuota"):
            b = ttk.Button(riga, width=22)
            b.pack(side="left", padx=2, expand=True, fill="x")
            self.bottoni[chiave] = b
        self.bottoni["completo"].configure(command=self._completo)
        self.bottoni["dibattito"].configure(command=self._dibattito)
        self.bottoni["sintesi"].configure(command=self._sintesi)
        self.bottoni["univoca"].configure(command=self._univoca)
        self.bottoni["salva"].configure(command=self._salva)
        self.bottoni["svuota"].configure(command=self._svuota)
        self.bottoni["cartella"] = ttk.Button(riga, width=11, command=self._add_cartella)
        self.bottoni["cartella"].pack(side="left", padx=2)
        self.bottoni["add"] = ttk.Button(riga, width=8, command=self._add_files)
        self.bottoni["add"].pack(side="left", padx=2)
        self.bottoni["cross"] = ttk.Button(riga, width=14, command=self._cross_check)
        self.bottoni["cross"].pack(side="left", padx=2)
        ttk.Button(riga, text="⚙", width=3, command=self._opzioni).pack(side="left", padx=2)

        # colonne
        colonne = ttk.Frame(self.contenuto)
        colonne.pack(fill="both", expand=True, padx=2, pady=2)
        for i in range(3):
            colonne.grid_columnconfigure(i, weight=1)
        colonne.grid_rowconfigure(0, weight=1)
        colonne.grid_rowconfigure(1, weight=1)
        self.c_utente = Colonna(colonne, "UTENTE", PALETTE["ambra"], "il supervisore")
        self.c_utente.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self.c_a = Colonna(colonne, "LLM", PALETTE["blu"],
                           modelli=self.opzioni, on_change=lambda v: self._cambia_modello("A", v))
        self.c_a.grid(row=0, column=1, sticky="nsew", padx=2, pady=2)
        self.c_b = Colonna(colonne, "LLM2", PALETTE["verde"],
                           modelli=self.opzioni, on_change=lambda v: self._cambia_modello("B", v))
        self.c_b.grid(row=0, column=2, sticky="nsew", padx=2, pady=2)
        self.c_a.combo.set(self._voce_canale(self.canale.A))
        self.c_b.combo.set(self._voce_canale(self.canale.B))
        self.c_finale = Colonna(colonne, "RISPOSTA UNIVOCA", PALETTE["viola"], "il verdetto del canale")
        self.c_finale.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=2, pady=2)

    # ---- lingua ----
    def _cambia_profilo(self):
        nome = self.combo_profilo.get()
        ruoli = CONFIG["profili"].get(nome)
        if ruoli:
            self.canale.ruolo_a = ruoli["A"]
            self.canale.ruolo_b = ruoli["B"]
            self.stato(f"profilo ruoli: {nome}")

    def _cambia_lingua(self):
        mappa = {"Italiano": "it", "English": "en", "Français": "fr", "Español": "es",
                 "Deutsch": "de", "Português": "pt", "中文": "zh"}
        self.lingua = mappa.get(self.combo_lingua.get(), "en")
        self.canale.lingua = self.lingua
        self._applica_lingua()

    def _applica_lingua(self):
        t = TESTI[self.lingua]
        self.title(f"{t['titolo']}  ·  v{VERSIONE}")
        self.lbl_barra.configure(text=t["barra"])
        self.btn_invia.configure(text=t["invia"])
        for chiave in ("completo", "dibattito", "sintesi", "univoca", "salva", "svuota",
                       "cartella", "add", "cross"):
            self.bottoni[chiave].configure(text=t[chiave])
        self.c_utente.descrizione(t["descr_utente"])
        self.c_finale.descrizione(t["descr_finale"])
        self.c_utente.box.configure(state="normal")
        self.c_a.box.configure(state="normal")
        self.c_b.box.configure(state="normal")
        self.c_finale.box.configure(state="normal")
        # headers
        for c, nome in ((self.c_utente, t["utente"]), (self.c_a, t["a"]),
                        (self.c_b, t["b"]), (self.c_finale, t["finale"])):
            c.box.delete("1.0", "end")
            c.box.configure(state="disabled")
        self.stato(t["pronto"])

    # ---- azioni ----
    def _completo(self):
        domanda = self.domanda.get().strip()
        if not domanda:
            self.c_finale.scrivi(TESTI[self.lingua]["chiedi_prima"])
            return
        if not self._inizia_lavoro():
            return
        self.domanda.delete(0, "end")
        threading.Thread(target=self._l_completo, args=(domanda,), daemon=True).start()

    def _aggiorna(self, testo, colore=None):
        self.stato(f"{testo} · chiamate: {self.canale.chiamate}/{self.canale.max_chiamate}", colore)

    def _l_completo(self, domanda):
        t = TESTI[self.lingua]
        try:
            self.c_utente.scrivi(domanda)
            self.c_a.scrivi(t["formula"])
            self.update_idletasks()
            contesto = self.canale.domanda_utente(domanda, on_chunk=lambda x: self._flusso(self.c_a, x))
            self.c_a.scrivi(contesto["a_formula"])
            self.c_b.scrivi(contesto["b_risposta"])
            self.stato(t["lavoro"])
            self.update_idletasks()
            self.dibattito_risultato = self.canale.dibattito(contesto, on_chunk=lambda x: self._flusso(self.c_a, x))
            self.c_a.scrivi(t["pos_a"] + "\n" + self.dibattito_risultato["ultimo_a"])
            self.c_b.scrivi(t["pos_b"] + "\n" + self.dibattito_risultato["ultimo_b"])
            self._aggiorna(t["sint_ok"])
            sintesi = self.canale.spartisci_lavori(contesto, self.dibattito_risultato,
                                                   on_chunk=lambda x: self._flusso(self.c_a, x))
            self.c_a.scrivi("[SINTESI FINALE E LAVORI]\n" + sintesi)
            finale, revisione = self.canale.risposta_univoca(contesto, self.dibattito_risultato, sintesi,
                                                             on_chunk=lambda x: self._flusso(self.c_finale, x))
            self.c_b.scrivi(t["rev_b"] + "\n" + revisione)
            self.c_finale.scrivi(finale)
            self._aggiorna(t["fine_ok"], PALETTE["verde"])
            self.bell()
        except Exception as e:
            self.c_finale.scrivi(f"ERRORE: {e}")
        finally:
            self._fine_lavoro()

    def _flusso(self, colonna, pezzo):
        """Scrittura incrementale (streaming) nella colonna, senza bloccare la GUI."""
        colonna.box.configure(state="normal")
        colonna.box.insert("end", pezzo)
        colonna.box.see("end")
        colonna.box.configure(state="disabled")
        self.update_idletasks()
        self.update()

    def _cross_check(self):
        if not self._inizia_lavoro():
            return
        threading.Thread(target=self._l_cross, daemon=True).start()

    def _l_cross(self):
        t = TESTI[self.lingua]
        try:
            finale = self.c_finale.box.get("1.0", "end").strip()
            contesto = {"domanda": self._ultimo("UTENTE") or self._ultimo("YOU")}
            if not finale or finale.startswith("ERRORE"):
                self.c_finale.scrivi("Nessuna risposta univoca da verificare: esegui prima il flusso.")
                return
            self.c_finale.scrivi("\n[🛡 CROSS-CHECK in corso …]")
            verdetto = self.canale.cross_check(contesto, finale,
                                               on_chunk=lambda x: self._flusso(self.c_finale, x))
            self.c_finale.scrivi("[VERDETTO CROSS-CHECK]\n" + verdetto)
            self.stato("cross-check completato")
        except Exception as e:
            self.c_finale.scrivi(f"ERRORE cross-check: {e}")
        finally:
            self._fine_lavoro()

    def _dibattito(self):
        if not self._inizia_lavoro():
            return
        threading.Thread(target=self._l_dibattito, daemon=True).start()

    def _l_dibattito(self):
        t = TESTI[self.lingua]
        try:
            contesto = {"a_formula": self._ultimo("A"), "b_risposta": self._ultimo("B"),
                        "domanda": self._ultimo("UTENTE") or self._ultimo("YOU")}
            self.dibattito_risultato = self.canale.dibattito(contesto)
            self.c_a.scrivi(t["pos_a"] + "\n" + self.dibattito_risultato["ultimo_a"])
            self.c_b.scrivi(t["pos_b"] + "\n" + self.dibattito_risultato["ultimo_b"])
        except Exception as e:
            self.c_finale.scrivi(f"ERRORE: {e}")
        finally:
            self._fine_lavoro()

    def _sintesi(self):
        if not self._inizia_lavoro():
            return
        threading.Thread(target=self._l_sintesi, daemon=True).start()

    def _l_sintesi(self):
        t = TESTI[self.lingua]
        try:
            contesto = {"a_formula": self._ultimo("A"), "b_risposta": self._ultimo("B"),
                        "domanda": self._ultimo("UTENTE") or self._ultimo("YOU")}
            dibattito = self.dibattito_risultato or {"ultimo_a": contesto["a_formula"],
                                                     "ultimo_b": contesto["b_risposta"]}
            sintesi = self.canale.spartisci_lavori(contesto, dibattito)
            self.c_a.scrivi("[SINTESI FINALE E LAVORI]\n" + sintesi)
            self.stato(t["sint_ok"])
            finale, revisione = self.canale.risposta_univoca(contesto, dibattito, sintesi)
            self.c_b.scrivi(t["rev_b"] + "\n" + revisione)
            self.c_finale.scrivi(finale)
            self.stato(t["fine_ok"])
        except Exception as e:
            self.c_finale.scrivi(f"ERRORE: {e}")
        finally:
            self._fine_lavoro()

    def _univoca(self):
        if not self._inizia_lavoro():
            return
        threading.Thread(target=self._l_univoca, daemon=True).start()

    def _l_univoca(self, contesto=None, dibattito=None, sintesi=None):
        t = TESTI[self.lingua]
        try:
            contesto = contesto or {"a_formula": self._ultimo("A"), "b_risposta": self._ultimo("B"),
                                    "domanda": self._ultimo("UTENTE") or self._ultimo("YOU")}
            dibattito = dibattito or (self.dibattito_risultato or {"ultimo_a": contesto["a_formula"],
                                                                   "ultimo_b": contesto["b_risposta"]})
            sintesi = sintesi or self._ultimo("A") or contesto["a_formula"]
            finale, revisione = self.canale.risposta_univoca(contesto, dibattito, sintesi)
            self.c_b.scrivi(t["rev_b"] + "\n" + revisione)
            self.c_finale.scrivi(finale)
            self.stato(t["fine_ok"])
        except Exception as e:
            self.c_finale.scrivi(f"ERRORE: {e}")
        finally:
            self._fine_lavoro()

    def _salva(self):
        try:
            j, md = self.canale.salva()
            nome = os.path.splitext(os.path.basename(j))[0]
            domanda = self._ultimo("UTENTE") or self._ultimo("YOU")
            finale = self.c_finale.box.get("1.0", "end").strip()
            tid = aggiungi_sessione(nome, domanda,
                                    [self.canale.A.nome(), self.canale.B.nome()],
                                    self.lingua, j, md, verdetto=finale)
            self.stato(f"salvata: {md} · timeline evento {tid}")
        except Exception as e:
            self.c_finale.scrivi(f"ERRORE salvataggio: {e}")

    def _svuota(self):
        for c in (self.c_utente, self.c_a, self.c_b, self.c_finale):
            c.box.configure(state="normal")
            c.box.delete("1.0", "end")
            c.box.configure(state="disabled")
        self.canale.allegati = []
        self.dibattito_risultato = None

    def _voce_canale(self, modello):
        """Ritrova la voce del menu corrispondente al modello attivo del canale."""
        nome = modello.nome()
        for tipo, suffisso in (("Ollama:", "ollama"), ("OpenAI:", "openai"), ("Anthropic:", "anthropic")):
            if nome.startswith(tipo):
                m = nome.split(":", 1)[1]
                for v in self.opzioni:
                    if v == f"{m} · {suffisso}":
                        return v
        if nome.startswith("Mock"):
            return "mock"
        return self.opzioni[0] if self.opzioni else "mock"

    def _add_cartella(self):
        """Seleziona una cartella intera: carica tutti i file supportati (max 40)."""
        from tkinter import filedialog
        cartella = filedialog.askdirectory(title="Cartella — carica tutti i documenti/immagini")
        if not cartella:
            return
        supportati = [".txt", ".md", ".csv", ".py", ".json", ".log", ".tex", ".html",
                      ".yml", ".yaml", ".ini", ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif"]
        file_trovati = []
        for radice, _, nomi in os.walk(cartella):
            for n in nomi:
                if os.path.splitext(n)[1].lower() in supportati:
                    file_trovati.append(os.path.join(radice, n))
            if len(file_trovati) >= 40:
                break
        file_trovati = file_trovati[:40]
        if not file_trovati:
            self.c_utente.scrivi("[cartella] nessun file supportato trovato")
            return
        esiti = self.canale.aggiungi_file(file_trovati)
        for e in esiti:
            self.c_utente.scrivi(f"[cartella] {e}")
        self.stato(f"cartella caricata ({len(esiti)} file)")

    def _add_files(self):
        """Selezione file (testo, PDF, immagini) da dare in pasto al canale."""
        from tkinter import filedialog
        percorsi = filedialog.askopenfilenames(
            title="ADD — seleziona documenti o immagini",
            filetypes=[("Documenti e immagini", "*.txt *.md *.csv *.py *.json *.log *.tex *.html *.pdf *.png *.jpg *.jpeg *.webp *.gif"),
                       ("Tutti i file", "*.*")])
        if not percorsi:
            return
        esiti = self.canale.aggiungi_file(list(percorsi))
        for e in esiti:
            self.c_utente.scrivi(f"[allegato] {e}")
        self.stato(f"{len(esiti)} allegato/i aggiunto/i al canale")

    def _opzioni(self):
        """Finestra Opzioni: gestione completa dei clienti (aggiungi, modifica modelli, elimina, preset)."""
        fin = tk.Toplevel(self)
        fin.title("TRILogos — Opzioni / Clients")
        fin.geometry("620x520")
        fin.configure(bg=PALETTE["sfondo"])
        fin.transient(self)

        lista = tk.Text(fin, height=7, bg="#232429", fg=PALETTE["testo"], relief="flat",
                        highlightthickness=1, highlightbackground=PALETTE["bordo"], font=("Consolas", 9))
        lista.pack(fill="x", padx=8, pady=6)
        self._aggiorna_lista_clienti(lista)
        lista.configure(state="disabled")

        # selezione client esistente
        sel_bar = ttk.Frame(fin)
        sel_bar.pack(fill="x", padx=8)
        ttk.Label(sel_bar, text="Client selezionato:").pack(side="left")
        combo_clienti = ttk.Combobox(sel_bar, values=[c["nome"] for c in self.clienti],
                                     state="readonly", width=24)
        if self.clienti:
            combo_clienti.current(0)
        combo_clienti.pack(side="left", padx=4)
        e_modello_nuovo = ttk.Entry(sel_bar, width=20)
        e_modello_nuovo.pack(side="left", padx=4)
        ttk.Button(sel_bar, text="＋ Modello", width=10,
                   command=lambda: self._op_aggiungi_modello(fin, combo_clienti, e_modello_nuovo, lista)).pack(side="left", padx=2)
        ttk.Button(sel_bar, text="🗑 Elimina", width=9,
                   command=lambda: self._op_elimina_client(fin, combo_clienti, lista)).pack(side="left", padx=2)

        form = ttk.Frame(fin)
        form.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Label(form, text="Nuovo client:").grid(row=0, column=0, sticky="w")
        e_nome = ttk.Entry(form, width=18)
        e_nome.grid(row=0, column=1, sticky="we", padx=2)
        ttk.Label(form, text="base URL").grid(row=0, column=2, sticky="e")
        e_base = ttk.Entry(form, width=30)
        e_base.grid(row=0, column=3, sticky="we", padx=2)
        ttk.Label(form, text="chiave (nome env)").grid(row=1, column=0, sticky="w")
        e_chiave = ttk.Entry(form, width=18)
        e_chiave.grid(row=1, column=1, sticky="we", padx=2)
        ttk.Label(form, text="modelli (csv)").grid(row=1, column=2, sticky="e")
        e_modelli = ttk.Entry(form, width=30)
        e_modelli.grid(row=1, column=3, sticky="we", padx=2)
        form.columnconfigure(3, weight=1)

        def aggiungi():
            nome = e_nome.get().strip()
            if not nome:
                return
            chiave = e_chiave.get().strip()
            if chiave and (not chiave.isidentifier() or len(chiave) > 64):
                self.c_utente.scrivi(
                    f"[opzioni] chiave non valida: usa il NOME della variabile d'ambiente "
                    f"(es. OPENAI_API_KEY), mai il valore.")
                return
            modelli = [m.strip() for m in e_modelli.get().split(",") if m.strip()]
            lista_nuova = aggiunti()
            lista_nuova.append({"nome": nome, "base_url": e_base.get().strip() or "http://localhost:1234/v1",
                                "chiave": chiave, "modelli": modelli or [nome]})
            salva_aggiunti(lista_nuova)
            self._ricarica_clienti(lista, combo_clienti)
            self.stato(f"client '{nome}' aggiunto · modelli nei menu")
            fin.destroy()

        ttk.Button(fin, text="＋ Aggiungi client", command=aggiungi).pack(side="left", padx=8, pady=8)
        ttk.Button(fin, text="⚡ OpenAI", command=lambda: self._op_preset(fin, lista, combo_clienti,
                    "openai", "https://api.openai.com/v1", "OPENAI_API_KEY",
                    ["gpt-4o-mini", "gpt-4o"])).pack(side="left", padx=2)
        ttk.Button(fin, text="⚡ Anthropic", command=lambda: self._op_preset(fin, lista, combo_clienti,
                    "anthropic", "https://api.anthropic.com/v1", "ANTHROPIC_API_KEY",
                    ["claude-3-5-sonnet-latest"])).pack(side="left", padx=2)
        ttk.Button(fin, text="⚡ Ollama", command=lambda: self._op_preset(fin, lista, combo_clienti,
                    "ollama", "http://localhost:11434/v1", "", [])).pack(side="left", padx=2)
        ttk.Button(fin, text="✖ Chiudi", command=fin.destroy).pack(side="right", padx=8, pady=8)
        ttk.Label(fin, text="I modelli dei client compaiono nei menu di LLM e LLM2. Le chiavi: solo nomi di variabili d'ambiente.",
                  background=PALETTE["sfondo"], foreground=PALETTE["secondario"]).pack(side="bottom", pady=4)

    def _aggiorna_lista_clienti(self, lista):
        lista.configure(state="normal")
        lista.delete("1.0", "end")
        lista.insert("1.0", "CLIENTI (modelli tra parentesi)\n" + "\n".join(
            f"- {c['nome']} ({', '.join(c.get('modelli', []))}) · {c.get('base_url', '')}"
            for c in self.clienti) or "  (nessuno)")
        lista.configure(state="disabled")

    def _ricarica_clienti(self, lista, combo_clienti):
        self.clienti = rileva_clienti()
        self.opzioni = voci_modelli(self.clienti)
        self.c_a.combo.configure(values=self.opzioni)
        self.c_b.combo.configure(values=self.opzioni)
        combo_clienti.configure(values=[c["nome"] for c in self.clienti])
        if self.clienti:
            combo_clienti.current(0)
        self._aggiorna_lista_clienti(lista)

    def _op_aggiungi_modello(self, fin, combo_clienti, e_modello, lista):
        nome_client = combo_clienti.get()
        modello = e_modello.get().strip()
        if not nome_client or not modello:
            return
        lista_nuova = aggiunti()
        for c in lista_nuova:
            if c["nome"] == nome_client:
                c.setdefault("modelli", [])
                if modello not in c["modelli"]:
                    c["modelli"].append(modello)
        salva_aggiunti(lista_nuova)
        self._ricarica_clienti(lista, combo_clienti)
        self.stato(f"modello '{modello}' aggiunto a {nome_client}")

    def _op_elimina_client(self, fin, combo_clienti, lista):
        nome_client = combo_clienti.get()
        if not nome_client:
            return
        lista_nuova = [c for c in aggiunti() if c["nome"] != nome_client]
        salva_aggiunti(lista_nuova)
        self._ricarica_clienti(lista, combo_clienti)
        self.stato(f"client '{nome_client}' eliminato")

    def _op_preset(self, fin, lista, combo_clienti, nome, base, chiave_env, modelli):
        if any(c["nome"] == nome for c in self.clienti):
            self.stato(f"client '{nome}' già presente")
            return
        lista_nuova = aggiunti()
        lista_nuova.append({"nome": nome, "base_url": base, "chiave": chiave_env,
                            "modelli": modelli})
        salva_aggiunti(lista_nuova)
        self._ricarica_clienti(lista, combo_clienti)
        self.stato(f"client '{nome}' aggiunto (chiave da env {chiave_env})")

    def _cambia_modello(self, polo, voce):
        """Cambia il modello di LLM o LLM2 al volo: ricostruisce il canale."""
        try:
            nuovo = modello_da_voce(voce, self.clienti)
            altro_polo = "B" if polo == "A" else "A"
            voce_altro = self.c_b.combo.get() if altro_polo == "B" else self.c_a.combo.get()
            altro = modello_da_voce(voce_altro, self.clienti)
            m = CONFIG["modelli"]
            a = nuovo if polo == "A" else altro
            b = nuovo if polo == "B" else altro
            self.canale = Canale(a, b,
                                 ruolo_a=CONFIG["ruoli"]["A"],
                                 ruolo_b=CONFIG["ruoli"]["B"],
                                 max_turni_dibattito=CONFIG["canale"]["max_turni_dibattito"],
                                 soglia_convergenza=CONFIG["canale"]["soglia_convergenza"],
                                 lingua=self.lingua)
            self.dibattito_risultato = None
            self._svuota()
            self.stato(f"{polo} → {nuovo.nome()} · canale ricostruito")
        except Exception as e:
            self.stato(f"ERRORE cambio modello: {e}")

    def _ultimo(self, polo):
        for passo in reversed(self.canale.cronologia):
            if passo["polo"] == polo:
                return passo["testo"]
        return ""


if __name__ == "__main__":
    app = TrilogoApp()
    app.mainloop()