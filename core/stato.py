# TRILogos — stato runtime locale (flag dell'applicazione)
"""Flag di runtime (primo_flusso_ok, byok_splash) in stato.json nella root del
progetto: file LOCALE e gitignored, mai nel config.json tracciato. Scrittura
atomica (file temporaneo + os.replace); lettura tollerante (dict vuoto se il
file manca o è corrotto). Migrazione una tantum dai vecchi campi di config.json.
Nessun dato esce dal PC."""
import json, os, tempfile

PERCORSO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "stato.json")
CHIAVI_MIGRATE = ("primo_flusso_ok", "byok_splash")


def leggi():
    """Dict dello stato locale; {} se il file manca, è corrotto o non è un dict."""
    try:
        with open(PERCORSO, encoding="utf-8") as f:
            dati = json.load(f)
        return dati if isinstance(dati, dict) else {}
    except Exception:
        return {}


def _salva(dati):
    """Scrittura ATOMICA del dict su stato.json (file temporaneo + os.replace):
    mai un file parziale se il processo muore a metà. True se salvato."""
    tmp = None
    try:
        cartella = os.path.dirname(PERCORSO)
        fd, tmp = tempfile.mkstemp(prefix="stato_", suffix=".tmp", dir=cartella)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(dati, f, ensure_ascii=False, indent=2)
        os.replace(tmp, PERCORSO)
        return True
    except Exception:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass
        return False


def imposta(chiave, valore=True):
    """Imposta UNA chiave dello stato. Lo stato è accessorio: mai crash,
    False se la scrittura non riesce."""
    dati = leggi()
    dati[chiave] = valore
    return _salva(dati)


def migra_da_config(config):
    """Migrazione una tantum: copia in stato.json i flag byok_splash e
    primo_flusso_ok presenti in config.json (vecchio formato) ma non ancora
    nello stato. Il vecchio campo NON viene rimosso da config.json: la
    bonifica del file tracciato è una decisione separata.
    Ritorna True se ha migrato almeno un flag."""
    if not isinstance(config, dict):
        return False
    dati = leggi()
    migrati = False
    for chiave in CHIAVI_MIGRATE:
        if chiave not in dati and chiave in config:
            dati[chiave] = bool(config.get(chiave))
            migrati = True
    if not migrati:
        return False
    return _salva(dati)
