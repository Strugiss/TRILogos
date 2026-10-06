# TRILogos — integrazione con research-timeline: ogni sessione diventa un evento tracciato.
"""Genera/aggiorna TRILogos/timeline.json nel formato dello strumento research-timeline
(eventi tipizzati con metrics/evidence/ai_role) — il lavoro del canale entra nello
stesso schema auditabile del laboratorio."""
import json, os, datetime, re

TIMELINE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "timeline.json")

# Author di default NEUTRO (A10a): nessun dato personale nel distribuito.
# Chi vuole firmare la propria timeline lo configura in config.json → timeline.author.
AUTORE_NEUTRO = {
    "name": "Utente",
    "affiliation": "",
    "orcid": "",
    "background": "",
    "ai_role": "cognitive_prosthesis",
}


def _leggi(autore=None):
    """Timeline esistente; se manca o è corrotta ne crea una nuova con l'autore
    passato (None -> default neutro AUTORE_NEUTRO). L'author di una timeline
    già esistente non viene mai riscritto."""
    autore = autore if isinstance(autore, dict) else dict(AUTORE_NEUTRO)
    try:
        with open(TIMELINE, encoding="utf-8") as f:
            tl = json.load(f)
        if isinstance(tl, dict):
            return tl
    except Exception:
        pass
    return {
        "project": {"name": "TRILogos", "description": "Dialoghi a tre voci (utente · LLM · LLM2)",
                    "domain": "ai_orchestration"},
        "author": autore,
        "events": [],
    }


def aggiungi_sessione(nome_sessione, domanda, modelli, lingua, percorso_json, percorso_md,
                      verdetto="", tipo="milestone", autore=None):
    """Registra la sessione salvata come evento nella timeline.
    `autore`: dict da config.json → timeline.author (il core non legge la config);
    None -> default neutro AUTORE_NEUTRO. Vale solo per una timeline nuova:
    l'author di una timeline esistente non viene riscritto."""
    tl = _leggi(autore)
    numeri = []
    for e in tl.get("events", []):
        m = re.match(r"^T(\d+)$", str(e.get("id", "") or ""))
        if m:
            numeri.append(int(m.group(1)))
    prossimo = max(numeri, default=-1) + 1
    evento = {
        "id": f"T{prossimo}",
        "type": tipo,
        "date": datetime.date.today().isoformat(),
        "description": f"Dialogo TRILogos: {nome_sessione or ''} — {(domanda or '')[:120]}",
        "tags": ["trilogos", "dialogo", "multi_agent"],
        "metrics": {
            "modelli": ", ".join(modelli) if isinstance(modelli, list) else str(modelli or ""),
            "lingua": lingua,
            "verdetto": (verdetto or "")[:200],
        },
        "evidence": {
            "session_json": os.path.relpath(percorso_json, os.path.dirname(TIMELINE)),
            "session_md": os.path.relpath(percorso_md, os.path.dirname(TIMELINE)),
            "ai_role": "cognitive_prosthesis",
            "data_links": [os.path.relpath(percorso_json, os.path.dirname(TIMELINE))],
            "code_links": [],
        },
    }
    tl.setdefault("events", []).append(evento)
    with open(TIMELINE, "w", encoding="utf-8") as f:
        json.dump(tl, f, ensure_ascii=False, indent=2)
    return f"T{prossimo}"