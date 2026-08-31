# TRILogos — integrazione con research-timeline: ogni sessione diventa un evento tracciato.
"""Genera/aggiorna TRILogos/timeline.json nel formato dello strumento research-timeline
(eventi tipizzati con metrics/evidence/ai_role) — il lavoro del canale entra nello
stesso schema auditabile del laboratorio."""
import json, os, datetime, re

TIMELINE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "timeline.json")


def _leggi():
    try:
        with open(TIMELINE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "project": {"name": "TRILogos", "description": "Dialoghi a tre voci (utente · LLM · LLM2)",
                        "domain": "ai_orchestration"},
            "author": {"name": "N47Lab", "affiliation": "independent", "orcid": None,
                       "background": "without academic degrees", "ai_role": "cognitive_prosthesis"},
            "events": [],
        }


def aggiungi_sessione(nome_sessione, domanda, modelli, lingua, percorso_json, percorso_md,
                      verdetto="", tipo="milestone"):
    """Registra la sessione salvata come evento nella timeline."""
    tl = _leggi()
    numeri = []
    for e in tl.get("events", []):
        m = re.match(r"^T(\d+)$", e.get("id", ""))
        if m:
            numeri.append(int(m.group(1)))
    prossimo = max(numeri, default=-1) + 1
    evento = {
        "id": f"T{prossimo}",
        "type": tipo,
        "date": datetime.date.today().isoformat(),
        "description": f"Dialogo TRILogos: {domanda[:120]}",
        "tags": ["trilogos", "dialogo", "multi_agent"],
        "metrics": {
            "modelli": modelli,
            "lingua": lingua,
            "verdetto": verdetto[:200],
        },
        "evidence": {
            "session_json": percorso_json,
            "session_md": percorso_md,
            "ai_role": "cognitive_prosthesis",
        },
    }
    tl.setdefault("events", []).append(evento)
    with open(TIMELINE, "w", encoding="utf-8") as f:
        json.dump(tl, f, ensure_ascii=False, indent=2)
    return f"T{prossimo}"