# TRILogos — test di pulizia delle risposte univoche (A11 rev. 8)
"""Regex di riferimento dei pattern vietati (classi C1-C8 del design A11) su
risposte reali: 0 pattern nei casi normali; per i profili rigorosi verifica la
presenza delle sezioni RISPOSTA: e FORMULA:; controlla l'assenza di blocchi
"Posizione [ABC]" e del vecchio blocco NON-CONSENSO nel corpo.

Uso:
  python Test/test_pulizia.py file <percorso.md|json ...>  -> conta i pattern nei file
  python Test/test_pulizia.py live [N]                     -> N domande reali Ollama (flusso univoca)
  python Test/test_pulizia.py nonconsenso [N]              -> NON-CONSENSO forzato (percorso guidato)
  python Test/test_pulizia.py flusso [turni] [config|veloce] -> flusso completo reale

PRECETTO PRIVACY: stampa SOLO conteggi/indicatori, mai il testo delle risposte."""
import sys, os, json, re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PATTERN = (
    ("C1-domanda-supervisore", r"(?i)la domanda del supervisore"),
    ("C2-posizione", r"(?i)posizione di [abc]\s*:"),
    ("C8-posizione-blocco", r"(?i)\bposizione [abc]\b"),
    ("C8-blocco-nonconsenso", r"(?i)\[non-consenso\] il dibattito non è convergito"),
    ("C2-bozza-verifica", r"(?im)^\s*\[(bozza univoca|verifica univoca)\]"),
    ("C1-collega-b", r"(?i)\bcollega\s+b\b"),
    ("C2-sintesi-spartizione", r"(?i)^\s*(sintesi finale|spartizione dei lavori)\s*:"),
    ("C2-approvo", r"(?i)\bapprovo\b"),
    ("C2-risposta-collega", r"(?i)risposta univoca per il collega"),
    ("C2-ruolo", r"(?i)\bruolo [abc]\s*:"),
    ("C3-preambolo", r"(?i)^\s*(certo|ecco|ciao)[,!]?"),
    ("C3-cortesia", r"(?i)(non esitare a chiedere|spero di esserti stato utile|se hai altre domande)"),
)


def conta(testo):
    """(lista (pattern, n), totale) sui pattern di riferimento."""
    righe = []
    totale = 0
    for nome, pat in PATTERN:
        n = len(re.findall(pat, testo or ""))
        righe.append((nome, n))
        totale += n
    return righe, totale


def sezioni_presenti(testo):
    """(RISPOSTA presente, FORMULA presente) per i profili rigorosi."""
    t = (testo or "").upper()
    return ("RISPOSTA:" in t, "FORMULA:" in t)


def valuta(testo, rigoroso=True):
    """Riepilogo: pattern totali, conteggio Posizione, sezioni (se rigoroso)."""
    righe, tot = conta(testo)
    posizioni = sum(n for nome, n in righe if "posizione" in nome)
    info = {"pattern_totali": tot, "posizioni": posizioni}
    if rigoroso:
        r, f = sezioni_presenti(testo)
        info["risposta"] = r
        info["formula"] = f
    return info


def sezioni_univoca_da_md(percorso):
    """Blocchi '## UNIVOCA' dei file .md di sessione."""
    try:
        with open(percorso, encoding="utf-8") as f:
            testo = f.read()
    except Exception:
        return []
    return [m.group(1) for m in
            re.finditer(r"^## UNIVOCA[^\n]*\n\n(.*?)(?=\n## |\Z)", testo, re.S | re.M)]


def sezioni_univoca_da_json(percorso):
    try:
        with open(percorso, encoding="utf-8") as f:
            dati = json.load(f)
    except Exception:
        return []
    return [p.get("testo", "") for p in dati.get("cronologia", []) if p.get("polo") == "UNIVOCA"]


def modalita_file(percorsi):
    totale = 0
    for p in percorsi:
        sezioni = sezioni_univoca_da_md(p) if p.lower().endswith(".md") else sezioni_univoca_da_json(p)
        for i, s in enumerate(sezioni, 1):
            righe, tot = conta(s)
            totale += tot
            info = valuta(s, rigoroso=False)
            print(f"{os.path.basename(p)} sezione {i}: {tot} pattern vietati "
                  f"(posizioni: {info['posizioni']})")
            for nome, n in righe:
                if n:
                    print(f"   {nome}: {n}")
    print(f"TOTALE pattern vietati: {totale}")
    return totale


def _canale(modelli, rigoroso=True, turni=None):
    """Canale con modelli ('veloce' o 'config') e stile/formato del profilo di
    default dal config.json del progetto."""
    import inspect
    from core.canale import Canale
    from core.modelli import crea_modello
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = json.load(open(os.path.join(base, "config.json"), encoding="utf-8"))
    profilo = next(iter(cfg["profili"].values()))
    if modelli == "config":
        m = cfg["modelli"]
        a = crea_modello(m["A"]["tipo"], modello=m["A"].get("modello"))
        b = crea_modello(m["B"]["tipo"], modello=m["B"].get("modello"))
        c = crea_modello(m["C"]["tipo"], modello=m["C"].get("modello")) if "C" in m else None
    else:
        a = crea_modello("ollama", modello="qwen2.5:3b")
        b = crea_modello("ollama", modello="llama3.2:3b")
        c = crea_modello("ollama", modello="qwen2.5:3b")
    kw = {"stile": profilo.get("stile") or "",
          "formato_risposta": (profilo.get("formato_risposta") or "semplice") if rigoroso else "semplice"}
    sig = inspect.signature(Canale.__init__).parameters
    if "limiti_token" in sig and cfg.get("canale", {}).get("limiti_token"):
        kw["limiti_token"] = cfg["canale"]["limiti_token"]
    if "dibattito_parallelo" in sig:
        kw["dibattito_parallelo"] = cfg["canale"].get("dibattito_parallelo", True)
    if turni is not None and "max_turni_dibattito" in sig:
        kw["max_turni_dibattito"] = turni
    return Canale(a, b, c, **kw)


def modalita_live(n=3):
    """N domande reali: flusso univoca+cross (come il passo 5-6), profilo rigoroso."""
    domande = ["Quanto fa 2+2? Rispondi in una riga.",
               "Qual è la capitale della Francia? Rispondi in una riga.",
               "Quanti giorni ha una settimana? Rispondi in una riga."][:n]
    canale = _canale("veloce", rigoroso=True)
    totale = 0
    for i, domanda in enumerate(domande, 1):
        contesto = {"domanda": domanda, "a_formula": domanda}
        dibattito = {"ultimo_a": "Risposta breve.", "ultimo_b": "Risposta breve.",
                     "convergito": True}
        finale, _ = canale.risposta_univoca(contesto, dibattito, "Risposta diretta in una riga.")
        esito = canale.cross_check(contesto, finale)
        testo = finale
        if esito["verdetto"] == "CONFERMATA" and esito.get("versione_pulita"):
            testo = esito["versione_pulita"]
        info = valuta(testo, rigoroso=True)
        totale += info["pattern_totali"]
        print(f"domanda {i}: {info['pattern_totali']} pattern vietati "
              f"(RISPOSTA {info['risposta']}, FORMULA {info['formula']}, "
              f"verdetto {esito['verdetto']}, pulizia {esito['metriche'].get('pulizia', '?')})")
    print(f"TOTALE pattern vietati: {totale}")
    return totale


def modalita_nonconsenso(n=1):
    """NON-CONSENSO forzato (convergito=False): la zona C resta RISPOSTA+FORMULA,
    senza blocchi Posizione/meta-testo (percorso guidato rev. 8)."""
    canale = _canale("veloce", rigoroso=True)
    totale = 0
    for i in range(1, n + 1):
        contesto = {"domanda": "Qual è il miglior linguaggio di programmazione e perché?",
                    "a_formula": "Analisi delle alternative."}
        dibattito = {"ultimo_a": "Preferisco Python per la leggibilità.",
                     "ultimo_b": "Preferisco C per le prestazioni.",
                     "ultimo_c": "Dipende dal contesto d'uso.",
                     "convergito": False}
        finale, _ = canale.risposta_univoca(contesto, dibattito, "Sintesi delle posizioni.")
        info = valuta(finale, rigoroso=True)
        totale += info["pattern_totali"]
        print(f"non-consenso {i}: {info['pattern_totali']} pattern vietati, "
              f"posizioni: {info['posizioni']} (RISPOSTA {info['risposta']}, FORMULA {info['formula']})")
    print(f"TOTALE pattern vietati: {totale}")
    return totale


def modalita_flusso(turni=None, modelli="veloce"):
    """Flusso completo reale a 3 voci; valuta la zona C (risposta finale)."""
    canale = _canale(modelli, rigoroso=True, turni=turni)
    domanda = "Quanti lumen esprime il sole?"
    noop = lambda x: None
    contesto = canale.domanda_utente(domanda, on_chunk=noop, on_chunk_b=noop, on_chunk_c=noop)
    dib = canale.dibattito(contesto, on_chunk=noop, on_chunk_b=noop, on_chunk_c=noop)
    sintesi = canale.spartisci_lavori(contesto, dib, on_chunk=noop)
    finale, _ = canale.risposta_univoca(contesto, dib, sintesi,
                                        on_chunk=noop, on_chunk_rev=noop, on_chunk_c=noop)
    esito = canale.cross_check(contesto, finale, on_chunk=noop)
    testo = finale
    if esito["verdetto"] == "CONFERMATA" and esito.get("versione_pulita"):
        testo = esito["versione_pulita"]
    info = valuta(testo, rigoroso=True)
    print(f"flusso: convergito={dib.get('convergito')} turni={canale.max_turni} "
          f"verdetto={esito['verdetto']} {info}")
    return info["pattern_totali"]


def main():
    args = sys.argv[1:]
    if not args or args[0] == "file":
        percorsi = args[1:]
        if not percorsi:
            print("uso: python Test/test_pulizia.py file <file.md|json...>")
            sys.exit(2)
        totale = modalita_file(percorsi)
    elif args[0] == "live":
        totale = modalita_live(int(args[1]) if len(args) > 1 else 3)
    elif args[0] == "nonconsenso":
        totale = modalita_nonconsenso(int(args[1]) if len(args) > 1 else 1)
    elif args[0] == "flusso":
        turni = int(args[1]) if len(args) > 1 else None
        modelli = args[2] if len(args) > 2 else "veloce"
        totale = modalita_flusso(turni, modelli)
    else:
        print("uso: python Test/test_pulizia.py file <...> | live [N] | nonconsenso [N] | flusso [turni] [config|veloce]")
        sys.exit(2)
    sys.exit(0 if totale == 0 else 1)


if __name__ == "__main__":
    main()
