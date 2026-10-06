# TRILogos — squadra di agenti (profilo "Ricerca", B1)
"""Percorso Ricerca: i tre modelli A/B/C pianificano una squadra di agenti
specializzati (piano JSON validato con escape), la eseguono e discernono la
risposta con una soglia di ottimo (default 8,99/10: mai forzare a 10 per
artefatti, mai accontentarsi di 8,98). L'output del progetto va SOLO nella
cartella scelta dall'utente (<cartella>\\TRILogos_output\\), con nomi univoci e
nessuna sovrascrittura (A9 rev. 5). Nessuna duplicazione del motore chiamate:
tutto passa da `Canale.chiama` (B1b: cap, fallback, token, temperatura).

A14b: in `discerni`, se `decision.abilitato` e' true e il modello decisionale
e' disponibile (core\\decisione.py), ogni iterazione riceve in affiancamento
una valutazione "D" (`iterazione["valutatore_d"] = {score, confidence}`). D
informa e NON giudica: la confidenza resta `min(A,B,C)` e la soglia 8,99 non
cambia; la `usage` D e' contata a parte (`EsitoRicerca.usage_decision`), mai
nel Canale/Σ A13. Senza modello o su errore: nessun D, fallback silenzioso.
"""
import json
import os
from dataclasses import dataclass, field

from . import decisione
from . import perimetro
from .canale import VINCOLI_REGISTRO
from .modelli import _estrai_json

SOGLIA_DEFAULT = 8.99
MAX_AGENTI_DEFAULT = 6
MAX_ITERAZIONI_DEFAULT = 3
TEMPERATURA_PIANO = 0.1
TEMPERATURA_AGENTI = 0.4
TEMPERATURA_VALUTAZIONE = 0.1

# B1a: schemi minimi con escape sempre presente (nessuno/sconosciuto/generico).
SCHEMA_PIANO = {
    "type": "object",
    "properties": {
        "obiettivo": {"type": "string"},
        "agenti": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nome": {"type": "string"},
                    "specialita": {"type": "string"},
                    "obiettivo": {"type": "string"},
                    "prompt_sistema": {"type": "string"},
                    "output_atteso": {"type": "string"},
                },
                "required": ["nome", "specialita", "obiettivo",
                             "prompt_sistema", "output_atteso"],
            },
        },
        "note": {"type": "string"},
    },
    "required": ["obiettivo", "agenti", "note"],
}

SCHEMA_VALUTAZIONE = {
    "type": "object",
    "properties": {
        "punteggio": {"type": "number", "minimum": 0, "maximum": 10},
        "motivazione": {"type": "string"},
    },
    "required": ["punteggio", "motivazione"],
}

# A14b: valutatore "D" di affiancamento (decision model locale /v1/systemone).
# 11 livelli 0-10 in italiano (indice = punteggio) per il quesito "score".
LIVELLI_D = (
    "0 — del tutto sbagliata o fuori tema",
    "1 — gravemente insufficiente",
    "2 — molto scarsa, errori gravi",
    "3 — scarsa, errori rilevanti",
    "4 — mediocre, carenze evidenti",
    "5 — appena sufficiente, incerta",
    "6 — sufficiente, ma migliorabile",
    "7 — buona, con limiti minori",
    "8 — molto buona, corretta e completa",
    "9 — ottima: corretta, completa e pertinente",
    "10 — perfetta e non forzata",
)
ISTRUZIONI_D = (
    "Valuta la risposta candidata rispetto al progetto/domanda del supervisore: "
    "correttezza, completezza, pertinenza, assenza di artefatti forzati. "
    "10 = perfetta ma non forzata; non regalare punti."
)
MAX_CHIAMATE_D_DEFAULT = 12


@dataclass
class PianoAgenti:
    obiettivo: str = "sconosciuto"
    agenti: list = field(default_factory=list)
    note: str = "nessuno"

    def to_dict(self):
        return {"obiettivo": self.obiettivo, "agenti": self.agenti, "note": self.note}


@dataclass
class EsitoRicerca:
    piano: PianoAgenti = None
    iterazioni: list = field(default_factory=list)
    risposta: str = ""
    punteggio_finale: float = 0.0
    motivo_stop: str = "iterazioni"
    chiamate: int = 0
    token: dict = field(default_factory=dict)
    # A14.3: contabilita' decision model SEPARATA dal Canale/Σ A13.
    decision_chiamate: int = 0
    usage_decision: dict = field(default_factory=lambda: {"in": 0, "out": 0})

    def to_dict(self):
        return {
            "piano": self.piano.to_dict() if self.piano else None,
            "iterazioni": self.iterazioni,
            "risposta": self.risposta,
            "punteggio_finale": self.punteggio_finale,
            "motivo_stop": self.motivo_stop,
            "chiamate": self.chiamate,
            "token": self.token,
            "decision_chiamate": self.decision_chiamate,
            "usage_decision": self.usage_decision,
        }


def _cfg(cfg, chiave, default):
    try:
        v = (cfg or {}).get(chiave)
        return default if v is None else v
    except Exception:
        return default


def _evento(evento, tipo, dati):
    if evento is None:
        return
    try:
        evento(tipo, dati)
    except Exception:
        pass


def _chiama_json(canale, modello, messaggi, schema, passo, tentativi=3):
    """Chiamata JSON strutturata che passa dal motore del canale (B1b): imposta
    lo schema sul modello, chiama con cap/fallback/token/temperatura, estrae e
    valida; retry <=tentativi. Ritorna (dict|None, grezzo)."""
    vecchio = getattr(modello, "formato", None)
    modello.formato = schema
    grezzo = ""
    try:
        for _i in range(max(1, tentativi)):
            grezzo = canale.chiama(modello, messaggi, passo=passo) or ""
            dati = _estrai_json(grezzo)
            if dati is not None:
                return dati, grezzo
    finally:
        modello.formato = vecchio
    return None, grezzo


def _valida_piano(dati, max_agenti):
    """Validazione del piano (formato + limiti): 1 <= agenti <= max_agenti;
    campi obbligatori con escape; mai eccezioni. Ritorna PianoAgenti o None."""
    if not isinstance(dati, dict):
        return None
    agenti = dati.get("agenti")
    if not isinstance(agenti, list) or not agenti:
        return None
    puliti = []
    for ag in agenti:
        if len(puliti) >= max_agenti:
            break
        if not isinstance(ag, dict):
            continue
        nome = str(ag.get("nome") or "nessuno").strip()[:60] or "nessuno"
        puliti.append({
            "nome": nome,
            "specialita": str(ag.get("specialita") or "generico").strip()[:120] or "generico",
            "obiettivo": str(ag.get("obiettivo") or "sconosciuto").strip()[:600] or "sconosciuto",
            "prompt_sistema": str(ag.get("prompt_sistema") or "").strip()[:4000],
            "output_atteso": str(ag.get("output_atteso") or "nessuno").strip()[:300] or "nessuno",
        })
    if not puliti:
        return None
    return PianoAgenti(
        obiettivo=str(dati.get("obiettivo") or "sconosciuto").strip()[:600] or "sconosciuto",
        agenti=puliti,
        note=str(dati.get("note") or "nessuno").strip()[:600] or "nessuno",
    )


def _contesto_utente(domanda, contesto):
    parti = [f"Domanda/progetto del supervisore:\n{domanda}"]
    if contesto:
        parti.append(f"Contesto disponibile (allegati e note):\n{contesto}")
    return "\n\n".join(parti)


def _vincoli_piano(max_agenti):
    return (
        "Pianifica la squadra di agenti specializzati necessaria per il progetto. "
        f"Da 1 a {max_agenti} agenti; scegli SOLO quelli necessari (esempi indicativi, "
        "mai un elenco chiuso: programmatore, decodificatore, calcolatore, verificatore, "
        "documentarista...). Per ogni agente: nome breve, specialita', obiettivo, "
        "prompt_sistema (descrizione operativa e professionale del suo modo di lavorare, "
        "senza formule di auto-presentazione) e output_atteso. "
        "Se un campo manca usa esattamente \"nessuno\"/\"sconosciuto\"/\"generico\". "
        "Rispondi SOLO con l'oggetto JSON secondo lo schema, senza altro testo; "
        "non menzionare il processo e usa un registro professionale."
    )


def pianifica(canale, domanda, contesto="", cfg=None, evento=None):
    """Pianificazione (A propone JSON -> B rivede JSON -> C verifica fattibilita').
    Ritorna PianoAgenti validato oppure None se il formato non e' ottenibile."""
    canale.temperature["ricerca_piano"] = float(_cfg(cfg, "temperatura_piano", TEMPERATURA_PIANO))
    canale.temperature["ricerca_esecuzione"] = float(_cfg(cfg, "temperatura_agenti", TEMPERATURA_AGENTI))
    canale.temperature["ricerca_valutazione"] = float(_cfg(cfg, "temperatura_valutazione", TEMPERATURA_VALUTAZIONE))
    # Limite risposta della ricerca piu' ampio del flusso standard (V2).
    try:
        canale.limiti_token["univoca"] = int(_cfg(cfg, "limite_risposta", 700))
    except Exception:
        pass
    max_agenti = int(_cfg(cfg, "max_agenti", MAX_AGENTI_DEFAULT))
    base = _contesto_utente(domanda, contesto)

    _evento(evento, "fase", {"nome": "pianificazione"})
    dati_a, _g = _chiama_json(canale, canale.A, [
        {"ruolo": "system", "contenuto": canale.ruolo_a + "\n\n" + VINCOLI_REGISTRO},
        {"ruolo": "user", "contenuto": base + "\n\n" + _vincoli_piano(max_agenti)},
    ], SCHEMA_PIANO, "ricerca_piano", tentativi=3)
    piano = _valida_piano(dati_a, max_agenti)
    if piano is None:
        _evento(evento, "piano", {"esito": "formato non valido"})
        return None

    dati_b, _g = _chiama_json(canale, canale.B, [
        {"ruolo": "system", "contenuto": canale.ruolo_b + "\n\n" + VINCOLI_REGISTRO},
        {"ruolo": "user", "contenuto": base + "\n\nPiano proposto da A (JSON):\n"
            + json.dumps(piano.to_dict(), ensure_ascii=False)
            + "\n\nObietta e integra con rigore, poi restituisci il piano MIGLIORATO "
            "nello stesso formato JSON (schema identico). " + _vincoli_piano(max_agenti)},
    ], SCHEMA_PIANO, "ricerca_piano", tentativi=2)
    piano_b = _valida_piano(dati_b, max_agenti)
    if piano_b is not None:
        piano = piano_b

    if canale.C is not None:
        verifica = canale.chiama(canale.C, [
            {"ruolo": "system", "contenuto": canale.ruolo_c + "\n\n" + VINCOLI_REGISTRO},
            {"ruolo": "user", "contenuto": base + "\n\nPiano finale (JSON):\n"
                + json.dumps(piano.to_dict(), ensure_ascii=False)
                + "\n\nVerifica la fattibilita' e la coerenza del piano con il progetto. "
                "Rispondi conciso: OK oppure elenca i problemi."},
        ], passo="ricerca_piano")
        _evento(evento, "piano", {"esito": "verificato", "verifica": (verifica or "")[:300]})

    _evento(evento, "piano", {"esito": "pronto", "n_agenti": len(piano.agenti),
                              "piano": piano.to_dict()})
    return piano


def esegui(canale, piano, domanda, contesto="", cfg=None, evento=None):
    """Esecuzione degli agenti: N chiamate, system = prompt_sistema dell'agente.
    Esecutore v1: il modello della voce A (design B1)."""
    base = _contesto_utente(domanda, contesto)
    risultati = []
    for i, ag in enumerate(piano.agenti, 1):
        _evento(evento, "agente", {"indice": i, "nome": ag["nome"],
                                   "specialita": ag["specialita"], "stato": "in corso"})
        testo = canale.chiama(canale.A, [
            {"ruolo": "system", "contenuto": (ag["prompt_sistema"] or
                "Assolvi il compito assegnato con rigore e chiarezza.") + "\n\n" + VINCOLI_REGISTRO},
            {"ruolo": "user", "contenuto": base
                + f"\n\nObiettivo del tuo lavoro:\n{ag['obiettivo']}"
                + f"\n\nOutput atteso:\n{ag['output_atteso']}"},
        ], passo="ricerca_esecuzione") or ""
        risultati.append({"nome": ag["nome"], "specialita": ag["specialita"], "testo": testo})
        _evento(evento, "agente", {"indice": i, "nome": ag["nome"], "stato": "completato",
                                   "esito": testo[:200]})
    return risultati


def _blocco_risultati(risultati):
    parti = []
    for r in risultati:
        parti.append(f"[AGENTE: {r['nome']} — {r['specialita']}]\n{r['testo']}")
    return "\n\n---\n\n".join(parti)


def _e_approvo(testo):
    """Approvazione secca di B tollerante alla punteggiatura e a testo residuo
    dopo la prima riga: 'APPROVO', 'approvo.', 'APPROVO.\\n### …' -> True;
    una revisione vera (che riscrive la risposta) -> False."""
    prima = ""
    for riga in (testo or "").splitlines():
        if riga.strip():
            prima = riga
            break
    return prima.strip().lower().rstrip(".! ").strip() == "approvo"


def _valuta(canale, voce, modello, candidato, domanda, cfg):
    dati, _g = _chiama_json(canale, modello, [
        {"ruolo": "system", "contenuto": (
            "Valuta con severità la risposta assegnando un punteggio 0-10 "
            "rispetto a: correttezza, completezza, pertinenza al progetto, "
            "assenza di artefatti forzati. 10 = perfetta ma non forzata; "
            "non regalare punti. Rispondi SOLO col JSON dello schema, "
            "senza menzionare il processo.")},
        {"ruolo": "user", "contenuto": (
            f"Progetto/domanda:\n{domanda}\n\nRisposta candidata:\n{candidato}")},
    ], SCHEMA_VALUTAZIONE, "ricerca_valutazione", tentativi=2)
    if dati is None:
        return {"voce": voce, "punteggio": 0.0,
                "motivazione": "valutazione non disponibile (formato non valido)"}
    try:
        p = float(dati.get("punteggio", 0))
    except (TypeError, ValueError):
        p = 0.0
    return {"voce": voce, "punteggio": max(0.0, min(10.0, p)),
            "motivazione": str(dati.get("motivazione") or "")[:400]}


def _config_decision(cfg):
    """A14c: sezione "decision" del config. Usa la cfg passata se contiene
    "decision" (dict), altrimenti legge config.json del progetto; fallback {}
    (decision spenti) senza mai sollevare."""
    if isinstance(cfg, dict) and isinstance(cfg.get("decision"), dict):
        return cfg["decision"]
    percorso = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
    try:
        with open(percorso, encoding="utf-8") as f:
            dati = json.load(f)
        sezione = dati.get("decision")
        return sezione if isinstance(sezione, dict) else {}
    except Exception:
        return {}


def _opzioni_decision(dec):
    """A14c: opzioni opzionali (endpoint, timeout, keep_alive, tentativi) per
    core.decisione.valuta; assenti -> default del modulo."""
    opzioni = {}
    if dec.get("endpoint"):
        opzioni["endpoint"] = str(dec["endpoint"])
    if dec.get("timeout") is not None:
        opzioni["timeout"] = dec["timeout"]
    if dec.get("keep_alive") is not None:
        opzioni["keep_alive"] = dec["keep_alive"]
    if dec.get("tentativi") is not None:
        opzioni["tentativi"] = dec["tentativi"]
    return opzioni


def _valuta_d(dec, modello_d, domanda, candidato):
    """A14b: 1 valutazione "D" (score 0..10, 11 livelli) su domanda+candidato.
    Ritorna RispostaDecisione con score numerico, oppure None: qualunque errore
    e' assorbito qui (fallback silenzioso, nessuna regressione del flusso)."""
    try:
        state = (f"Progetto/domanda del supervisore:\n{domanda}\n\n"
                 f"Risposta candidata:\n{candidato}")
        risposte = decisione.valuta(
            state,
            [decisione.Quesito("merito", "score", ISTRUZIONI_D, list(LIVELLI_D))],
            modello_d, **_opzioni_decision(dec))
        r = risposte.get("merito")
        if r is None or r.score is None:
            return None
        return r
    except Exception:
        return None


def discerni(canale, domanda, piano, risultati, cfg=None, evento=None):
    """Discernimento: A sintetizza, B rivede; A/B/C valutano (0-10); confidenza =
    minimo delle tre voci; stop quando confidenza >= soglia - 1e-9 (default 8,99).
    Mai forzare: se la soglia non si raggiunge, si dichiara il punteggio reale.
    A14b: se abilitato e disponibile, ogni iterazione riceve anche la voce "D"
    (decision model locale) in `iterazione["valutatore_d"]`, a solo scopo di
    affiancamento: confidenza e soglia restano quelle di A/B/C."""
    soglia = float(_cfg(cfg, "soglia_ottimo", SOGLIA_DEFAULT))
    max_it = int(_cfg(cfg, "max_iterazioni", MAX_ITERAZIONI_DEFAULT))
    # A14b: attivazione del valutatore D (decision.abilitato + modello presente).
    dec = _config_decision(cfg)
    usa_d = bool(dec.get("abilitato"))
    modello_d = str(dec.get("modello") or "").strip()
    if usa_d and modello_d:
        usa_d = decisione.disponibile(modello_d, endpoint=(dec.get("endpoint") or None))
    else:
        usa_d = False
    try:
        max_chiamate_d = int(dec.get("max_chiamate", MAX_CHIAMATE_D_DEFAULT))
    except (TypeError, ValueError):
        max_chiamate_d = MAX_CHIAMATE_D_DEFAULT
    chiamate_d = 0
    usage_d = {"in": 0, "out": 0}
    blocco = _blocco_risultati(risultati)
    iterazioni = []
    candidato = ""
    confidenza = 0.0
    motivo = "iterazioni"

    for n in range(1, max_it + 1):
        feedback = ""
        if iterazioni:
            feedback = ("\n\nValutazioni dell'iterazione precedente (da superare):\n"
                        + "\n".join(f"- {v['voce']}: {v['punteggio']:.2f}/10 — {v['motivazione']}"
                                    for v in iterazioni[-1]["valutazioni"]))
        _evento(evento, "fase", {"nome": "discernimento", "iterazione": n})
        candidato = canale.chiama(canale.A, [
            {"ruolo": "system", "contenuto": canale.ruolo_a + "\n\n" + VINCOLI_REGISTRO},
            {"ruolo": "user", "contenuto": (
                f"Progetto/domanda del supervisore:\n{domanda}\n\n"
                f"Risultati degli agenti:\n{blocco}\n\n"
                "Scrivi la RISPOSTA finale del canale basandoti sui risultati degli "
                "agenti, formulata con il rigore del tuo profilo. "
                "VIETATO: ripetere o parafrasare il prompt/obiettivo/output atteso, "
                "usare titoli o sezioni tipo 'Obiettivo del tuo lavoro', citare gli "
                "agenti o il processo, preamboli e cortesie. "
                "Scrivi SOLO la risposta finale, in italiano, senza altro testo."
                + feedback)},
        ], passo="univoca") or ""
        revisione = canale.chiama(canale.B, [
            {"ruolo": "system", "contenuto": canale.ruolo_b + "\n\n" + VINCOLI_REGISTRO},
            {"ruolo": "user", "contenuto": (
                f"Progetto/domanda del supervisore:\n{domanda}\n\n"
                f"Risposta proposta da A:\n{candidato}\n\n"
                "Se la approvi rispondi esattamente: APPROVO. Altrimenti riscrivila "
                "(testo unico, nessun meta-testo) migliorandola.")},
        ], passo="revisione") or ""
        if not _e_approvo(revisione):
            candidato = revisione

        valutazioni = [
            _valuta(canale, "A", canale.A, candidato, domanda, cfg),
            _valuta(canale, "B", canale.B, candidato, domanda, cfg),
            _valuta(canale, "C", canale.C or canale.B, candidato, domanda, cfg),
        ]
        confidenza = min(v["punteggio"] for v in valutazioni)
        voce = {"numero": n, "valutazioni": valutazioni,
                "confidenza": confidenza, "candidato": candidato}
        # A14b: valutatore D di affiancamento (non incide su confidenza/soglia).
        if usa_d and chiamate_d < max_chiamate_d:
            d = _valuta_d(dec, modello_d, domanda, candidato)
            if d is not None:
                chiamate_d += 1
                usage_d["in"] += d.usage.get("in", 0)
                usage_d["out"] += d.usage.get("out", 0)
                voce["valutatore_d"] = {"score": d.score, "confidence": d.confidence}
        iterazioni.append(voce)
        _evento(evento, "iterazione", voce)
        if confidenza >= soglia - 1e-9:
            motivo = "soglia"
            break

    return EsitoRicerca(
        piano=piano, iterazioni=iterazioni, risposta=candidato,
        punteggio_finale=confidenza, motivo_stop=motivo,
        chiamate=canale.chiamate, token=dict(canale.token_totali),
        decision_chiamate=chiamate_d, usage_decision=usage_d)


def salva_output(esito, evento=None):
    """Salva il risultato della ricerca in <cartella progetto>\\TRILogos_output\\
    (A9 rev. 5): nome univoco, mai sovrascritture; senza cartella -> None (il
    risultato resta in GUI). Ritorna il percorso scritto o None."""
    radice = perimetro.leggi()
    if not radice:
        return None
    out_dir = perimetro.risolvi("TRILogos_output")
    os.makedirs(out_dir, exist_ok=True)
    percorso = perimetro.nome_univoco("TRILogos_output", "risultato.md")
    righe = ["# Risultato ricerca — TRILogos", ""]
    if esito.piano:
        righe += [f"**Obiettivo:** {esito.piano.obiettivo}", ""]
        righe += ["## Squadra di agenti", ""]
        for ag in esito.piano.agenti:
            righe.append(f"- **{ag['nome']}** — {ag['specialita']}: {ag['obiettivo']}")
        righe.append("")
    for it in esito.iterazioni:
        righe.append(f"## Iterazione {it['numero']} — confidenza {it['confidenza']:.2f}/10")
        for v in it["valutazioni"]:
            righe.append(f"- {v['voce']}: {v['punteggio']:.2f}/10 — {v['motivazione']}")
        righe.append("")
    righe += [f"**Punteggio finale:** {esito.punteggio_finale:.2f}/10 "
              f"(stop: {esito.motivo_stop})", "", "## Risposta", "", esito.risposta, ""]
    with open(percorso, "w", encoding="utf-8") as f:
        f.write("\n".join(righe))
    _evento(evento, "salvato", {"percorso": percorso})
    return percorso
