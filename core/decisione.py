# TRILogos — decision model locali di Ollama (A14, /v1/systemone)
"""Decision model di Ollama (endpoint `/v1/systemone`, Ollama 0.35+): client
HTTP tipizzato e PURO (nessun tkinter). Invia uno `state` e una mappa di
`questions` e riceve `answers` con score/scelta/noul, legend, probabilities,
confidence e `usage`.

PRECETTO PRIVACY: si parla SOLO con l'endpoint locale (`localhost`/`127.0.0.1`);
un host diverso viene rifiutato con errore in italiano. I dati non escono dal PC.

Contratti reali verificati su Ollama 0.35.1 con `tev1:4b` (2026-10-06):
- richiesta: `{model, state, questions: {nome: {type, instructions, criteria}},
  keep_alive}` con:
    - type "score":  criteria = array di descrizioni (indice = punteggio 0..N-1);
    - type "choice": criteria = mappa opzione -> descrizione (o null);
    - type "noul":   criteria = {"true": descrizione, "false": descrizione}.
- risposta: `{model, answers: {nome: {...}}, usage: {input_tokens, output_tokens}}`
  con:
    - score:  {type, score, legend, probabilities, confidence}
    - choice: {type, choice, probabilities, confidence}
    - noul:   {type, noul}
- `state` <= 64 KiB (superamento -> errore chiaro); retry <= 3 per le chiamate
  temporaneamente fallite; errori definitivi (400/404) con messaggio italiano.

API tipizzata (A14a):
    punteggio(modello, state, istruzioni, livelli) -> {score, confidence,
        probabilities, legend}                  (quesito "score" 0..N-1)
    scelta(modello, state, istruzioni, opzioni) -> {choice, probabilities,
        confidence}                             (quesito "choice")
    si_no(modello, state, istruzioni, descrizioni=None) -> {noul}
                                                (quesito "noul")
    valuta(state, quesiti, modello, ...)        -> {nome: RispostaDecisione}
        (API completa: include la `usage` di ogni risposta)
    disponibile(modello, ...)                   -> bool (check via /api/tags)

Contabilità separata (A14.3): la `usage` (in/out) vive DENTRO ogni
RispostaDecisione (normalizzata con la tolleranza `_int0`, A6.2); NON passa dal
Canale e NON entra nella Σ token A13 del flusso standard.

Config (config.json, sezione "decision", A14c):
    {"abilitato": false, "modello": "nimble", "timeout": 120}
- `abilitato`: false = percorso Ricerca identico a oggi (nessuna chiamata D);
  true = 1 valutazione D per iterazione (solo se il modello e' disponibile).
- `modello`: default "nimble" (Apache-2.0; per i test locali usare "tev1:4b").
- `timeout`: secondi per chiamata (default 120).
Opzionali: `endpoint` (default ENDPOINT_DEFAULT), `keep_alive` (default -1),
`tentativi` (default 3), `max_chiamate` (default 12, letto da core\\agenti.py).
"""
from dataclasses import dataclass, field
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    raise ImportError("Manca la libreria 'requests': installala con: pip install requests")

ENDPOINT_DEFAULT = "http://127.0.0.1:11434/v1/systemone"
KEEP_ALIVE_DEFAULT = -1
TIMEOUT_DEFAULT = 120
TENTATIVI_DEFAULT = 3
TIMEOUT_PROBE_DEFAULT = 3
MAX_STATE_BYTE = 64 * 1024

# Host ammessi: il decision model resta su questo PC (PRECETTO PRIVACY).
HOST_LOCALI = ("localhost", "127.0.0.1")


class DecisioneError(Exception):
    """Errore dei decision model: sempre in italiano, mai eccezioni di rete grezze."""


def _int0(v):
    """Intero non negativo robusto (stessa tolleranza AN-2 di modelli/canale)."""
    try:
        return max(int(v), 0)
    except (TypeError, ValueError):
        return 0


def _numero(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _usage_normalizzato(usage):
    """`usage` di /v1/systemone -> {"in", "out"} con tolleranza _int0."""
    if not isinstance(usage, dict):
        return {"in": 0, "out": 0}
    return {"in": _int0(usage.get("input_tokens")), "out": _int0(usage.get("output_tokens"))}


def _controlla_endpoint(endpoint):
    """Solo endpoint locali (PRECETTO PRIVACY): host non locale -> errore."""
    try:
        p = urlparse(str(endpoint))
    except Exception:
        p = None
    if p is None or p.scheme not in ("http", "https") or not p.hostname:
        raise DecisioneError(
            f"endpoint decisionale non valido: {endpoint!r} "
            f"(atteso un URL http://127.0.0.1:11434/v1/systemone)")
    if p.hostname not in HOST_LOCALI:
        raise DecisioneError(
            f"endpoint decisionale non locale rifiutato: {p.hostname} — i decision "
            "model girano solo su questo PC (localhost/127.0.0.1)")
    return p


def _base_ollama(endpoint):
    """Base http://host:porta ricavata dall'endpoint del decision model."""
    p = _controlla_endpoint(endpoint)
    porta = f":{p.port}" if p.port else ""
    return f"{p.scheme}://{p.hostname}{porta}"


def _dettaglio_errore(r):
    """Testo dell'errore JSON di Ollama, se presente (senza eccezioni)."""
    try:
        d = r.json()
        if isinstance(d, dict) and d.get("error"):
            return str(d["error"])[:300]
    except Exception:
        pass
    return (r.text or "").strip()[:300]


@dataclass
class Quesito:
    """Una domanda per il decision model."""
    nome: str
    tipo: str                  # "score" | "choice" | "noul"
    istruzioni: str
    criteri: object = None     # score: [descrizioni]; choice: {opzione: desc|null}; noul: {"true","false"}

    def payload(self):
        tipo = (self.tipo or "").strip().lower()
        if tipo not in ("score", "choice", "noul"):
            raise DecisioneError(f"tipo di quesito non valido: {self.tipo!r} (score|choice|noul)")
        return {"type": tipo, "instructions": self.istruzioni or "", "criteria": self.criteri}


@dataclass
class RispostaDecisione:
    """Risposta di un singolo quesito, con `usage` normalizzata."""
    nome: str = ""
    tipo: str = ""
    score: float = None
    scelta: str = ""
    noul: float = None
    legend: dict = field(default_factory=dict)
    probabilities: dict = field(default_factory=dict)
    confidence: float = None
    usage: dict = field(default_factory=lambda: {"in": 0, "out": 0})


def _normalizza_quesiti(quesiti):
    """Accetta {nome: Quesito} oppure [Quesito, ...]: ritorna (coppie, payload)."""
    if isinstance(quesiti, dict):
        coppie = list(quesiti.items())
    else:
        coppie = []
        for q in (quesiti or []):
            if not isinstance(q, Quesito):
                raise DecisioneError("quesito non valido: atteso Quesito(nome, tipo, istruzioni, criteri)")
            coppie.append((q.nome, q))
    if not coppie:
        raise DecisioneError("nessun quesito decisionale fornito")
    payload = {}
    for nome, q in coppie:
        if not str(nome or "").strip() or not isinstance(q, Quesito):
            raise DecisioneError("quesito non valido: nome mancante o oggetto non Quesito")
        payload[str(nome)] = q.payload()
    return coppie, payload


def _post(url, payload, timeout, tentativi, modello):
    """POST con retry <= tentativi sugli errori temporanei; errori definitivi
    (400/404) subito in italiano. Ritorna il dict della risposta."""
    ultimo = None
    for _tentativo in range(max(1, int(tentativi))):
        try:
            r = requests.post(url, json=payload, timeout=timeout)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            ultimo = DecisioneError(
                f"server decisionale non raggiungibile: {url} — verifica che Ollama sia avviato")
            continue
        except Exception as e:
            ultimo = DecisioneError(f"errore di rete verso il server decisionale: {e}")
            continue
        if r.status_code == 200:
            try:
                dati = r.json()
            except ValueError:
                ultimo = DecisioneError("risposta decisionale non in formato JSON")
                continue
            if not isinstance(dati, dict):
                ultimo = DecisioneError("risposta decisionale di tipo inatteso (atteso oggetto JSON)")
                continue
            return dati
        dettaglio = _dettaglio_errore(r)
        if r.status_code == 404:
            if "not found" in dettaglio.lower() and "model" in dettaglio.lower():
                raise DecisioneError(
                    f"modello decisionale '{modello}' non disponibile: esegui "
                    f"`ollama pull {modello}`; il flusso prosegue senza valutatore D")
            raise DecisioneError(
                f"endpoint decisionale non trovato ({url}): serve Ollama 0.35+ "
                f"con /v1/systemone ({dettaglio or '404'})")
        if 400 <= r.status_code < 500:
            raise DecisioneError(f"errore decisionale ({r.status_code}): {dettaglio or 'richiesta rifiutata'}")
        # 5xx: errore temporaneo del server -> retry
        ultimo = DecisioneError(f"errore del server decisionale ({r.status_code}): {dettaglio or 'riprova'}")
    raise ultimo or DecisioneError("chiamata decisionale non riuscita")


def valuta(state, quesiti, modello, endpoint=None, timeout=None, keep_alive=None, tentativi=None):
    """Chiama /v1/systemone con `state` e i `quesiti`.

    `quesiti`: {nome: Quesito} oppure [Quesito, ...]. Ritorna
    {nome: RispostaDecisione} (con `usage` normalizzata). Solleva
    DecisioneError (italiano) su state >64 KiB, endpoint non locale, modello
    assente, payload rifiutato o errore definitivo dopo i retry."""
    nome_modello = str(modello or "").strip()
    if not nome_modello:
        raise DecisioneError("modello decisionale non indicato (sezione 'decision' di config.json)")
    testo = state if isinstance(state, str) else str(state or "")
    if len(testo.encode("utf-8")) > MAX_STATE_BYTE:
        raise DecisioneError(
            f"state troppo grande per il decision model: {len(testo.encode('utf-8'))} byte "
            f"(limite {MAX_STATE_BYTE}) — riduci domanda/risposta candidata")
    url = str(endpoint or ENDPOINT_DEFAULT).strip() or ENDPOINT_DEFAULT
    _controlla_endpoint(url)
    coppie, domande = _normalizza_quesiti(quesiti)
    try:
        timeout_s = float(timeout) if timeout is not None else TIMEOUT_DEFAULT
    except (TypeError, ValueError):
        timeout_s = TIMEOUT_DEFAULT
    try:
        tentativi_n = int(tentativi) if tentativi is not None else TENTATIVI_DEFAULT
    except (TypeError, ValueError):
        tentativi_n = TENTATIVI_DEFAULT
    ka = KEEP_ALIVE_DEFAULT if keep_alive is None else keep_alive
    payload = {"model": nome_modello, "state": testo, "questions": domande, "keep_alive": ka}
    dati = _post(url, payload, timeout_s, tentativi_n, nome_modello)

    answers = dati.get("answers")
    if not isinstance(answers, dict):
        raise DecisioneError("risposta decisionale senza 'answers'")
    usage = _usage_normalizzato(dati.get("usage"))
    risposte = {}
    for nome, q in coppie:
        a = answers.get(nome)
        if not isinstance(a, dict):
            raise DecisioneError(f"risposta mancante per il quesito '{nome}'")
        r = RispostaDecisione(nome=nome, tipo=str(a.get("type") or (q.tipo or "")).lower(),
                              usage=dict(usage))
        if r.tipo == "score":
            r.score = _numero(a.get("score"))
            r.legend = a.get("legend") if isinstance(a.get("legend"), dict) else {}
            r.probabilities = a.get("probabilities") if isinstance(a.get("probabilities"), dict) else {}
            r.confidence = _numero(a.get("confidence"))
        elif r.tipo == "choice":
            r.scelta = str(a.get("choice") or "")
            r.probabilities = a.get("probabilities") if isinstance(a.get("probabilities"), dict) else {}
            r.confidence = _numero(a.get("confidence"))
        elif r.tipo == "noul":
            r.noul = _numero(a.get("noul"))
        else:
            raise DecisioneError(f"tipo di risposta decisionale non riconosciuto: {r.tipo!r}")
        risposte[nome] = r
    return risposte


def punteggio(modello, state, istruzioni, livelli, **opzioni):
    """Quesito "score" 0..N-1 (`livelli` = descrizioni in italiano, indice = punteggio).
    Ritorna {score, confidence, probabilities, legend}; per la `usage` usa valuta()."""
    descrizioni = [str(x) for x in (livelli or [])]
    if len(descrizioni) < 2:
        raise DecisioneError("servono almeno 2 livelli per un quesito 'score' (0..N-1)")
    risposte = valuta(state, [Quesito("merito", "score", istruzioni, descrizioni)], modello, **opzioni)
    r = risposte["merito"]
    return {"score": r.score, "confidence": r.confidence,
            "probabilities": r.probabilities, "legend": r.legend}


def scelta(modello, state, istruzioni, opzioni, **extra):
    """Quesito "choice" (decisione tra `opzioni`: lista di voci o mappa voce->descrizione).
    Ritorna {choice, probabilities, confidence}."""
    if isinstance(opzioni, dict):
        criteri = dict(opzioni)
    else:
        voci = [str(x) for x in (opzioni or [])]
        if len(voci) < 2:
            raise DecisioneError("servono almeno 2 opzioni per un quesito 'choice'")
        criteri = {v: None for v in voci}
    risposte = valuta(state, [Quesito("scelta", "choice", istruzioni, criteri)], modello, **extra)
    r = risposte["scelta"]
    return {"choice": r.scelta, "probabilities": r.probabilities, "confidence": r.confidence}


def si_no(modello, state, istruzioni, descrizioni=None, **extra):
    """Quesito "noul" (esito binario 0..1). `descrizioni` può essere
    {"true": ..., "false": ...} oppure (descrizione_vera, descrizione_falsa).
    Ritorna {noul}."""
    if isinstance(descrizioni, dict):
        criteri = dict(descrizioni)
    elif isinstance(descrizioni, (tuple, list)) and len(descrizioni) == 2:
        criteri = {"true": str(descrizioni[0]), "false": str(descrizioni[1])}
    else:
        criteri = {"true": "vero", "false": "falso"}
    risposte = valuta(state, [Quesito("esito", "noul", istruzioni, criteri)], modello, **extra)
    return {"noul": risposte["esito"].noul}


def disponibile(modello, endpoint=None, timeout=TIMEOUT_PROBE_DEFAULT):
    """True se `modello` compare in /api/tags del server Ollama locale.
    Probe breve e silenzioso: qualunque errore -> False (fallback totale)."""
    nome = str(modello or "").strip()
    if not nome:
        return False
    try:
        url = _base_ollama(endpoint or ENDPOINT_DEFAULT) + "/api/tags"
        r = requests.get(url, timeout=timeout)
        if r.status_code != 200:
            return False
        dati = r.json()
    except Exception:
        return False
    if not isinstance(dati, dict):
        return False
    for m in (dati.get("models") or []):
        n = str((m or {}).get("name") or "")
        if n == nome or n == nome + ":latest":
            return True
    return False
