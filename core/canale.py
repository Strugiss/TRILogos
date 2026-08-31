# TRILogos — il canale di dialogo a tre (utente · A · B)
"""Flusso: l'utente domanda ad A → A formula per B → dibattito reciproco →
analisi reciproca → spartizione dei lavori. L'utente resta nel giro tra i passi."""
import json, datetime, os, re

SESSIONI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sessioni")
TESTO_EXT = {".txt", ".md", ".csv", ".py", ".json", ".log", ".tex", ".html", ".yml", ".yaml", ".ini"}
IMMAGINE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
MAX_CARATTERI_ALLEGATO = 20000


def _testo_da_pdf(path):
    try:
        from pypdf import PdfReader
        return "\n".join(p.extract_text() or "" for p in PdfReader(path).pages)
    except Exception:
        try:
            import fitz
            doc = fitz.open(path)
            return "\n".join(pg.get_text() for pg in doc)
        except Exception:
            return None


class Canale:
    def __init__(self, modello_a, modello_b, ruolo_a="You are agent A: a rigorous analyst.",
                 ruolo_b="You are agent B: a critical, constructive reviewer.",
                 max_turni_dibattito=4, soglia_convergenza=0.9, lingua="it", max_chiamate=40):
        self.A = modello_a
        self.B = modello_b
        self.ruolo_a = ruolo_a
        self.ruolo_b = ruolo_b
        self.max_turni = max_turni_dibattito
        self.soglia = soglia_convergenza
        self.lingua = lingua
        self.max_chiamate = max_chiamate
        self.chiamate = 0
        self.cronologia = []
        self.allegati = []

    def _chiama(self, modello, messaggi, on_chunk=None, backup=True):
        self.chiamate += 1
        if self.chiamate > self.max_chiamate:
            raise RuntimeError(f"cap di {self.max_chiamate} chiamate raggiunto: salva la sessione o riavvia")
        try:
            if on_chunk is not None:
                return modello.rispondi_stream(messaggi, on_chunk)
            return modello.rispondi(messaggi)
        except Exception as e_primo:
            if not backup:
                raise
            altro = self.B if modello is self.A else self.A
            self.chiamate += 1
            if self.chiamate > self.max_chiamate:
                raise RuntimeError(f"cap di {self.max_chiamate} chiamate raggiunto: salva la sessione o riavvia")
            self._registra("SISTEMA", f"[fallback] {modello.nome()} non risponde ({e_primo}); uso {altro.nome()}")
            try:
                if on_chunk is not None:
                    return altro.rispondi_stream(messaggi, on_chunk)
                return altro.rispondi(messaggi)
            except Exception as e_secondo:
                raise RuntimeError(f"entrambi i modelli falliti: {e_primo} | {e_secondo}")

    def aggiungi_file(self, percorsi):
        """Classifica i file allegati: testo (contenuto letto), PDF (testo estratto),
        immagini (percorso per modelli multimodali)."""
        aggiunti = []
        for p in percorsi:
            ext = os.path.splitext(p)[1].lower()
            nome = os.path.basename(p)
            if not os.path.exists(p):
                aggiunti.append(f"{nome} (file non trovato)")
                continue
            if ext in TESTO_EXT:
                try:
                    with open(p, encoding="utf-8", errors="ignore") as f:
                        testo = f.read()[:MAX_CARATTERI_ALLEGATO]
                    if not testo.strip():
                        aggiunti.append(f"{nome} (testo vuoto, ignorato)")
                        continue
                    self.allegati.append({"tipo": "testo", "nome": nome, "contenuto": testo})
                    aggiunti.append(f"{nome} (testo, {len(testo)} caratteri)")
                except Exception as e:
                    aggiunti.append(f"{nome} (ERRORE lettura: {e})")
            elif ext == ".pdf":
                testo = _testo_da_pdf(p)
                if testo and testo.strip():
                    self.allegati.append({"tipo": "testo", "nome": nome,
                                          "contenuto": testo[:MAX_CARATTERI_ALLEGATO]})
                    aggiunti.append(f"{nome} (PDF, {len(testo[:MAX_CARATTERI_ALLEGATO])} caratteri)")
                else:
                    aggiunti.append(f"{nome} (PDF: estrazione testo non riuscita)")
            elif ext in IMMAGINE_EXT:
                self.allegati.append({"tipo": "immagine", "nome": nome, "percorso": p})
                aggiunti.append(f"{nome} (immagine, per modelli multimodali)")
            else:
                aggiunti.append(f"{nome} (tipo non supportato)")
        return aggiunti

    def _messaggi_allegati(self):
        """Messaggi di contesto dagli allegati: testo iniettato, immagini collegate."""
        blocchi = []
        immagini = []
        for a in self.allegati:
            if a["tipo"] == "testo":
                blocchi.append(f"[ALLEGATO: {a['nome']}]\n{a['contenuto']}")
            else:
                immagini.append(a["percorso"])
        msg = []
        if blocchi:
            msg.append({"ruolo": "user",
                        "contenuto": "Contesto allegato dal supervisore (usalo se pertinente):\n\n"
                                     + "\n\n---\n\n".join(blocchi)})
        if immagini:
            msg.append({"ruolo": "user", "contenuto": "Immagini allegate dal supervisore:",
                        "immagini": immagini})
        return msg

    def _con_lingua(self, messaggi):
        istruzioni = {
            "it": "Rispondi sempre in italiano.",
            "en": "Always respond in English.",
            "fr": "Réponds toujours en français.",
            "es": "Responde siempre en español.",
            "de": "Antworte immer auf Deutsch.",
            "pt": "Responda sempre em português.",
            "zh": "始终用中文回答。",
        }
        return self._messaggi_allegati() + messaggi + [{"ruolo": "user", "contenuto": istruzioni.get(self.lingua, istruzioni["en"])}]

    def _registra(self, polo, testo):
        self.cronologia.append({"polo": polo, "testo": testo, "ora": datetime.datetime.now().isoformat(timespec="seconds")})

    def _simili(self, a, b, soglia=None):
        soglia = soglia or self.soglia
        if not a or not b:
            return False
        return abs(len(a) - len(b)) / max(len(a), len(b)) < (1 - soglia) and a[:80] == b[:80]

    def domanda_utente(self, domanda, on_chunk=None):
        """Passo 1: l'utente domanda ad A. Passo 2: A formula per B."""
        self._registra("UTENTE", domanda)
        a1 = self._chiama(self.A, self._con_lingua([
            {"ruolo": "system", "contenuto": self.ruolo_a},
            {"ruolo": "user", "contenuto": f"Domanda del supervisore:\n{domanda}\n\nAnalizzala e formula la richiesta per il collega B."}]), on_chunk)
        self._registra("A", a1)
        b1 = self._chiama(self.B, self._con_lingua([
            {"ruolo": "system", "contenuto": self.ruolo_b},
            {"ruolo": "user", "contenuto": f"Richiesta formulata da A:\n{a1}\n\nRispondi con la tua analisi."}]), on_chunk)
        self._registra("B", b1)
        return {"domanda": domanda, "a_formula": a1, "b_risposta": b1}

    def dibattito(self, contesto, on_chunk=None):
        """Passo 3: scambio reciproco A↔B finché converge o finisce il budget."""
        ultimo_a = contesto["a_formula"]
        ultimo_b = contesto["b_risposta"]
        for turno in range(1, self.max_turni + 1):
            nuova_a = self._chiama(self.A, self._con_lingua([
                {"ruolo": "system", "contenuto": self.ruolo_a},
                {"ruolo": "user", "contenuto": f"Reagisci alla posizione di B:\n{ultimo_b}\n\nSei d'accordo? Obietta o integra in modo conciso."}]), on_chunk)
            self._registra("A", nuova_a)
            ultimo_a = nuova_a
            if self._simili(nuova_a, ultimo_b):
                print(f"  [convergenza A al turno {turno}]")
                break
            nuova_b = self._chiama(self.B, self._con_lingua([
                {"ruolo": "system", "contenuto": self.ruolo_b},
                {"ruolo": "user", "contenuto": f"Reagisci alla posizione di A:\n{ultimo_a}\n\nConferma o correggi in modo conciso."}]), on_chunk)
            self._registra("B", nuova_b)
            ultimo_b = nuova_b
            if self._simili(nuova_b, ultimo_a):
                print(f"  [convergenza B al turno {turno}]")
                break
        return {"ultimo_a": ultimo_a, "ultimo_b": ultimo_b}

    def spartisci_lavori(self, contesto, dibattito, on_chunk=None):
        """Passo 4: A divide i compiti tra sé e B alla luce del dibattito."""
        sintesi = self._chiama(self.A, self._con_lingua([
            {"ruolo": "system", "contenuto": self.ruolo_a},
            {"ruolo": "user", "contenuto":
                f"Domanda: {contesto['domanda']}\n"
                f"Tua formulazione: {contesto['a_formula']}\n"
                f"Posizione di B: {dibattito['ultimo_b']}\n\n"
                "Scrivi la SINTESI FINALE e la SPARTIZIONE DEI LAVORI: chi fa cosa, in 3-5 righe."}]), on_chunk)
        self._registra("A", sintesi)
        return sintesi

    def cross_check(self, contesto, finale, on_chunk=None):
        """Passo 6: verifica della risposta univoca contro il contesto disponibile
        (allegati se presenti, altrimenti i ruoli di sistema che contengono i fatti del progetto)."""
        if self.allegati:
            blocchi = []
            for a in self.allegati:
                if a["tipo"] == "testo":
                    blocchi.append(f"[{a['nome']}]\n{a.get('contenuto', '')}")
                else:
                    blocchi.append(f"[{a['nome']}] (immagine allegata)")
            contesto_verifica = "Contesto allegato:\n" + "\n---\n".join(blocchi)
            nota = "verifica contro gli ALLEGATI"
        else:
            contesto_verifica = ("Nessun allegato: verifica contro i RUOLI DI SISTEMA, che contengono "
                                "il contesto del progetto (fatti dichiarati):\nRUOLO A:\n" + self.ruolo_a +
                                "\n\nRUOLO B:\n" + self.ruolo_b)
            nota = "verifica contro i RUOLI (nessun allegato caricato)"
        verdetto = self._chiama(self.B, self._con_lingua([
            {"ruolo": "system", "contenuto": self.ruolo_b},
            {"ruolo": "user", "contenuto":
                f"Risposta univoca del canale da verificare:\n{finale}\n\n"
                f"Contesto di riferimento ({nota}):\n{contesto_verifica}\n\n"
                "Verifica OGNI affermazione della risposta contro il contesto di riferimento. "
                "Elenca: (1) affermazioni supportate, (2) affermazioni NON supportate o inventate "
                "(controlla anche i SEGNI e i VALORI: alta vs bassa, soglie, numeri — se nessuna "
                "discrepanza, scrivi TUTTE SUPPORTATE), (3) verdetto finale: RISPOSTA CONFERMATA o DA CORREGGERE."}]), on_chunk)
        self._registra("VERIFICA", verdetto)
        return verdetto

    def risposta_univoca(self, contesto, dibattito, sintesi, on_chunk=None):
        """Passo 5: risposta univoca CONSENSUALE — A propone, B rivede e approva."""
        bozza = self._chiama(self.A, self._con_lingua([
            {"ruolo": "system", "contenuto": self.ruolo_a},
            {"ruolo": "user", "contenuto":
                f"Domanda del supervisore: {contesto['domanda']}\n"
                f"Tua formulazione: {contesto['a_formula']}\n"
                f"Posizione di B: {dibattito['ultimo_b']}\n"
                f"Sintesi e spartizione: {sintesi}\n\n"
                "Scrivi la BOZZA della risposta univoca del canale: un testo unico, chiaro, "
                "senza ruoli, massimo 6 righe, che tenga conto del dibattito."}]), on_chunk)
        self._registra("A", f"[bozza univoca]\n{bozza}")
        revisione = self._chiama(self.B, self._con_lingua([
            {"ruolo": "system", "contenuto": self.ruolo_b},
            {"ruolo": "user", "contenuto":
                f"Bozza di risposta univoca proposta da A:\n{bozza}\n\n"
                "Se la approvi, rispondi esattamente: APPROVO. Altrimenti rivedila in un testo "
                "unico, massimo 6 righe, che rappresenti il consenso di entrambi."}]), on_chunk)
        finale = bozza if self._approvata(revisione) else revisione
        self._registra("UNIVOCA", finale + ("  (approvata da B)" if self._approvata(revisione) else "  (revisionata da B)"))
        return finale, revisione

    @staticmethod
    def _approvata(revisione):
        r = (revisione or "").strip().lower()
        if r == "approvo" or r.startswith("approvo"):
            return not r.startswith("non ")
        return False

    def salva(self, nome=None):
        os.makedirs(SESSIONI, exist_ok=True)
        if nome is None:
            nome = datetime.datetime.now().strftime("sessione_%Y%m%d_%H%M%S")
        nome = re.sub(r"[^A-Za-z0-9_-]", "_", nome)
        dati = {"modelli": {"A": self.A.nome(), "B": self.B.nome()},
                "ruoli": {"A": self.ruolo_a, "B": self.ruolo_b},
                "cronologia": self.cronologia}
        percorso = os.path.join(SESSIONI, nome + ".json")
        with open(percorso, "w", encoding="utf-8") as f:
            json.dump(dati, f, ensure_ascii=False, indent=2)
        percorso_md = os.path.join(SESSIONI, nome + ".md")
        with open(percorso_md, "w", encoding="utf-8") as f:
            f.write(f"# Sessione TRILogos — {nome}\n\nA: {self.A.nome()} · B: {self.B.nome()}\n\n")
            for passo in self.cronologia:
                f.write(f"## {passo['polo']} ({passo['ora']})\n\n{passo['testo']}\n\n")
        return percorso, percorso_md