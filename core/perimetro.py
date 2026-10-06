# TRILogos — perimetro della cartella progetto (vincolo esclusivo di SCRITTURA)
"""Unica fonte di verità per la cartella progetto scelta dall'utente: è il
perimetro delle SCRITTURE (risultati/output del progetto, rev. 5); le letture
degli allegati sono libere. La radice è salvata in stato.json (chiave
`cartella_progetto`). Regola unica: un percorso è accettato SOLO se il suo
percorso reale (symlink e `..` risolti) è uguale alla radice o un suo discendente.
Mai cancellazioni o sovrascritture silenziose: i nomi dei nuovi file passano da
`nome_univoco`. Nessun dato esce dal PC."""
import os
from pathlib import Path

from . import stato as _stato

CHIAVE = "cartella_progetto"


class FuoriPerimetroError(Exception):
    """Percorso rifiutato: non è dentro la cartella progetto (o manca il perimetro)."""


def _radice():
    """Path risolta della radice, o None se assente/non più valida su disco."""
    p = _stato.leggi().get(CHIAVE)
    if not p or not isinstance(p, str):
        return None
    try:
        radice = Path(p).resolve()
    except (OSError, ValueError):
        return None
    return radice if radice.is_dir() else None


def _e_dentro(p, radice):
    """Confronto robusto (case Windows): True se p è la radice o un discendente.
    commonpath solleva ValueError su drive diversi -> fuori."""
    try:
        return os.path.commonpath([os.path.normcase(str(p)),
                                   os.path.normcase(str(radice))]) == os.path.normcase(str(radice))
    except ValueError:
        return False


def leggi():
    """Percorso della cartella progetto (stringa risolta) se esiste ancora su
    disco; None se assente, non valido o non più esistente."""
    r = _radice()
    return str(r) if r is not None else None


def imposta(percorso):
    """Valida una directory esistente, la salva come perimetro e ritorna il
    percorso risolto. Solleva ValueError (italiano) se non è una directory."""
    try:
        r = Path(percorso).resolve()
    except (OSError, ValueError) as e:
        raise ValueError(f"percorso non valido: {percorso}") from e
    if not r.is_dir():
        raise ValueError(f"non è una cartella esistente: {percorso}")
    _stato.imposta(CHIAVE, str(r))
    return str(r)


def nome():
    """Nome della cartella progetto per la UI ('' se non scelta)."""
    r = _radice()
    return r.name if r is not None else ""


def dentro(percorso):
    """True se il percorso REALE (symlink e `..` risolti) è dentro il perimetro.
    Senza perimetro attivo: sempre False."""
    r = _radice()
    if r is None:
        return False
    try:
        p = Path(percorso).resolve()
    except (OSError, ValueError):
        return False
    return _e_dentro(p, r)


def risolvi(relativo):
    """Costruisce e valida il percorso di un file dentro il perimetro.
    `relativo` può essere un nome o un percorso relativo (costruito sulla radice)
    oppure un percorso assoluto (ammesso solo se dentro la radice). Solleva
    FuoriPerimetroError con messaggio in italiano se manca il perimetro o se il
    percorso reale esce dalla radice (path traversal, symlink, drive diversi).
    La sanificazione dei nomi proposti dagli agenti è a monte (B1)."""
    r = _radice()
    if r is None:
        raise FuoriPerimetroError("nessuna cartella progetto scelta (usa 📁 Progetto)")
    try:
        p = Path(relativo)
        p = p.resolve() if p.is_absolute() else (r / p).resolve()
    except (OSError, ValueError) as e:
        raise FuoriPerimetroError(f"percorso non valido: {relativo}") from e
    if not _e_dentro(p, r):
        raise FuoriPerimetroError(f"percorso fuori dalla cartella progetto: {relativo}")
    return str(p)


def nome_univoco(relativo, nome):
    """Percorso LIBERO dentro il perimetro per un nuovo file: se il file esiste
    già, aggiunge il suffisso numerico _2, _3, … (MAI overwrite, MAI
    cancellazioni). `relativo` è la sottocartella di destinazione (deve esistere:
    la crea il chiamante); `nome` è il nome file proposto (per gli agenti va
    sanificato a monte: qui vale solo il basename, mai un percorso). Ritorna il
    percorso assoluto di un file ancora inesistente."""
    base = risolvi(relativo)
    if not os.path.isdir(base):
        raise FuoriPerimetroError(f"cartella di destinazione non valida: {relativo}")
    nome = os.path.basename(str(nome).replace("\\", "/").rstrip("/"))
    if not nome:
        raise FuoriPerimetroError("nome file mancante")
    stem, ext = os.path.splitext(nome)
    candidato = os.path.join(base, nome)
    suffisso = 2
    while os.path.exists(candidato):
        candidato = os.path.join(base, f"{stem}_{suffisso}{ext}")
        suffisso += 1
    return candidato
