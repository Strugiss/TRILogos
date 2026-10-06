# TRILogos — gestione clienti: rileva client locali e provider da opencode,
# permette di aggiungerne di propri. Le chiavi NON si salvano mai in chiaro:
# si riferisce solo il NOME della variabile d'ambiente (o si legge dalla config opencode).
import os, json, re, socket, shutil
from urllib.parse import urlparse
try:
    import requests
except ImportError:
    raise ImportError("Manca la libreria 'requests': installala con: pip install requests")

REGISTRO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "clienti.json")
CONFIG_OPENCODE = os.path.join(os.path.expanduser("~"), ".config", "opencode", "opencode.jsonc")

# ---- clienti locali: metadati per stato installazione (splash) ----
# "comandi": nomi di eseguibili cercati via shutil.which; "percorsi": percorsi
# comuni di installazione desktop (os.path.expandvars risolve %LOCALAPPDATA%).
# winget: ID veri del registro Windows (Ollama.Ollama, ElementLabs.LMStudio,
# Jan.Jan) — "LMStudioLMStudio.LMStudio" e "JanLabs.Jan" NON esistono.
LOCALI = {
    "ollama": {
        "porta": 11434,
        "base_url": "http://localhost:11434/v1",
        "comandi": ["ollama"],
        "percorsi": [],
        "installer": "https://ollama.com/download",
        "winget": "winget install Ollama.Ollama",
        "avvio": "Apri Ollama dal menu Start (resta nella barra delle applicazioni), poi premi Riprova.",
    },
    "lmstudio": {
        "porta": 1234,
        "base_url": "http://localhost:1234/v1",
        "comandi": ["lmstudio"],
        "percorsi": [r"%LOCALAPPDATA%\Programs\LM Studio\LM Studio.exe"],
        "installer": "https://lmstudio.ai",
        "winget": "winget install --id ElementLabs.LMStudio -e",
        "avvio": "Avvia LM Studio e attiva il server API locale (Developer → Start Server), poi premi Riprova.",
    },
    "jan": {
        "porta": 1337,
        "base_url": "http://localhost:1337/v1",
        "comandi": ["jan"],
        "percorsi": [r"%LOCALAPPDATA%\Programs\jan\jan.exe"],
        "installer": "https://jan.ai",
        "winget": "winget install --id Jan.Jan -e",
        "avvio": "Apri Jan e avvia il server locale (porta 1337) dalle impostazioni; premi Riprova.",
    },
}


def _leggi_jsonc(path):
    """Legge un file .jsonc (commenti /* */ e //) come dict, gestendo le virgole trailing."""
    try:
        testo = open(path, encoding="utf-8").read()
    except Exception:
        return None
    testo = re.sub(r'("(?:\\.|[^"\\])*")|/\*.*?\*/', lambda m: m.group(1) or "", testo, flags=re.S)
    testo = re.sub(r'("(?:\\.|[^"\\])*")|//[^\n]*', lambda m: m.group(1) or "", testo)
    testo = re.sub(r',\s*([}\]])', r"\1", testo)
    try:
        return json.loads(testo)
    except Exception:
        return None


def _open():
    """Provider dalla configurazione di opencode (modelli e base URL; MAI chiavi in chiaro)."""
    conf = _leggi_jsonc(CONFIG_OPENCODE)
    if not conf:
        return []
    clienti = []
    disabilitati = set(conf.get("disabled_providers", []) or [])
    for nome, p in (conf.get("provider") or {}).items():
        if nome in disabilitati:
            continue
        if not isinstance(p, dict):
            continue
        opts = p.get("options") or {}
        base = opts.get("baseURL", "")
        if not base:
            continue
        m = p.get("models")
        if isinstance(m, dict):
            modelli = list(m.keys())
        elif isinstance(m, list):
            modelli = [x.get("name", str(x)) if isinstance(x, dict) else str(x) for x in m]
        else:
            modelli = [nome]
        if not modelli:
            modelli = [nome]
        clienti.append({"nome": f"opencode:{nome}", "base_url": base,
                        "chiave": "", "modelli": modelli})
    return clienti


def _ollama():
    try:
        # timeout 2s: i probe girano in thread, il valore ridotto è solo igiene
        # (avvio rapido con server spenti); vedi A3 del design.
        r = requests.get("http://localhost:11434/api/tags", timeout=2)
        if r.ok:
            modelli = [m["name"] for m in r.json().get("models", []) if m.get("name")]
            if modelli:
                return [{"nome": "ollama", "base_url": "http://localhost:11434/v1",
                         "chiave": "", "modelli": modelli}]
    except Exception:
        pass
    return []


def _compat_openai(porta, nome, chiave_fittizia=""):
    base = f"http://localhost:{porta}/v1"
    headers = {}
    if chiave_fittizia:
        headers["Authorization"] = f"Bearer {chiave_fittizia}"
    try:
        # timeout 1.5s: come _ollama, il probe gira fuori dal thread UI (A3).
        r = requests.get(base + "/models", timeout=1.5, headers=headers)
        if r.ok:
            modelli = [m["id"] for m in r.json().get("data", []) if m.get("id")]
            if modelli:
                return [{"nome": nome, "base_url": base,
                         "chiave": chiave_fittizia, "modelli": modelli}]
    except Exception:
        pass
    return []


def aggiunti():
    try:
        with open(REGISTRO, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def salva_aggiunti(lista):
    """Salva il registro SANIFICANDO le chiavi: mai un valore reale (es. sk-...),
    solo NOMI di variabili d'ambiente validi; valori non validi -> chiave vuota.
    Le chiavi 'env:NOME' restano valide se NOME è un identifier <= 64."""
    pulita = []
    for c in lista:
        c = dict(c)
        chiave = c.get("chiave", "") or ""
        if not isinstance(chiave, str):
            c["chiave"] = ""
            chiave = ""
        if chiave:
            resto = chiave[4:] if chiave.startswith("env:") else chiave
            if not resto.isidentifier() or len(resto) > 64:
                c["chiave"] = ""
        pulita.append(c)
    with open(REGISTRO, "w", encoding="utf-8") as f:
        json.dump(pulita, f, ensure_ascii=False, indent=2)


def aggiungi_cliente(dati):
    """Aggiunge o aggiorna un cliente nel registro clienti.json mantenendo il
    formato esistente {nome, base_url, chiave, modelli}. Usata da ⚙ Opzioni e
    dallo splash (aggiunta + salvataggio chiave custom). Per i clienti CUSTOM
    la chiave può essere un valore reale: resta nel registro, MAI nel .env,
    MAI stampata nei messaggi. Ritorna True se salvato.

    GUARDIA ANTI-OPENCODE (livello CORE, oltre alla guardia UI di gui.py):
    il nome 'opencode' (normalizzato: spazi rimossi, maiuscole irrilevanti)
    è riservato alla configurazione dell'assistente e NON può essere aggiunto
    come cliente: viene sollevato ValueError in italiano. Gli altri nomi
    seguono il comportamento invariato."""
    lista = aggiunti()
    nome = (dati.get("nome") or "").strip()
    if not nome:
        return False
    if nome.strip().lower() == "opencode":
        raise ValueError("'opencode' è riservato alla configurazione dell'assistente: "
                         "non può essere aggiunto come client")
    base = (dati.get("base_url") or "").strip() or "http://localhost:1234/v1"
    modelli = dati.get("modelli") or []
    if isinstance(modelli, str):
        modelli = [m.strip() for m in modelli.split(",") if m.strip()]
    modelli = [str(m).strip() for m in modelli if str(m).strip()] or [nome]
    voce = {"nome": nome, "base_url": base,
            "chiave": (dati.get("chiave") or "").strip(),
            "modelli": modelli}
    for i, c in enumerate(lista):
        if c.get("nome") == nome:
            lista[i] = voce
            break
    else:
        lista.append(voce)
    with open(REGISTRO, "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, indent=2)
    return True


def rimuovi_cliente(nome):
    """Rimuove un cliente dal registro. Le chiavi delle voci rimanenti NON
    vengono sanificate (nessuna perdita di chiavi custom reali)."""
    lista = [c for c in aggiunti() if c.get("nome") != nome]
    with open(REGISTRO, "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, indent=2)


def stato_opencode():
    """Stato della configurazione opencode (file opencode.jsonc dell'utente):
    'connesso' se ci sono provider configurati (base URL presente). opencode
    non viene MAI scritto nel registro clienti.json."""
    p = _open()
    return {"stato": "connesso" if p else "non_connesso",
            "provider": p}


def _binario_trovato(info):
    for c in info.get("comandi", []):
        if shutil.which(c):
            return True
    for p in info.get("percorsi", []):
        if p and os.path.isfile(os.path.expandvars(p)):
            return True
    return False


def _porta_da_base(base_url, default):
    try:
        p = urlparse(base_url or "")
        if p.port:
            return p.port
    except ValueError:
        pass
    return default


def _porta_aperta(porta, timeout=0.6):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(("127.0.0.1", porta))
            return True
    except OSError:
        return False


def stato_locale(cliente):
    """Stato tipizzato di un client locale (ollama/lmstudio/jan):
    - 'attivo':         porta risponde (modelli rilevati se disponibili);
    - 'installato':     binario trovato ma porta chiusa (avvialo);
    - 'non_installato': binario non trovato (istruzioni di installazione).
    Ritorna {'stato', 'porta', 'modelli', 'installer', 'winget', 'avvio'}."""
    nome = (cliente.get("nome") or "").lower()
    info = LOCALI.get(nome)
    if not info:
        return {"stato": "sconosciuto", "porta": None, "modelli": [],
                "installer": "", "winget": "", "avvio": ""}
    porta = _porta_da_base(cliente.get("base_url"), info["porta"])
    attivo = _porta_aperta(porta)
    modelli = []
    if attivo:
        if nome == "ollama":
            r = _ollama()
            modelli = r[0].get("modelli", []) if r else []
        elif nome == "lmstudio":
            r = _compat_openai(porta, "lmstudio", chiave_fittizia="lm-studio") \
                or _compat_openai(porta, "lmstudio")
            modelli = r[0].get("modelli", []) if r else []
        elif nome == "jan":
            r = _compat_openai(porta, "jan", chiave_fittizia="jan-local-key") \
                or _compat_openai(porta, "jan")
            modelli = r[0].get("modelli", []) if r else []
    if attivo:
        stato = "attivo"
    elif _binario_trovato(info):
        stato = "installato"
    else:
        stato = "non_installato"
    return {"stato": stato, "porta": porta, "modelli": modelli,
            "installer": info["installer"], "winget": info["winget"],
            "avvio": info["avvio"]}


def _e_locale(base_url):
    """True se la base URL punta a un server locale (localhost, 127.0.0.1 o ::1).
    Senza schema (es. '127.0.0.1:11434') NON è locale: urlparse non lo riconosce."""
    try:
        p = urlparse(base_url or "")
    except ValueError:
        return False
    if not p.scheme:
        return False
    return p.hostname in ("localhost", "127.0.0.1", "::1")


def _componi(ollama, lm, jan, filtra_locali):
    """Composizione UNICA della lista clienti (condivisa da rileva_clienti e
    clienti_base), nell'ordine: opencode -> ollama -> openai -> anthropic ->
    lmstudio -> jan -> registro utente. `filtra_locali=True` (rilevamento con
    rete): i clienti locali sono filtrati sui modelli reali di Ollama e quelli
    rimasti senza modelli vengono saltati; `filtra_locali=False` (base, senza
    rete): i clienti passano interi, senza filtri."""
    clienti = []
    visti = set()

    def aggiungi(c):
        nome = c.get("nome", "")
        if nome in visti:
            return
        visti.add(nome)
        clienti.append(c)

    reali = set(ollama[0].get("modelli", [])) if ollama else set()

    for c in _open():
        c = dict(c)
        if filtra_locali and _e_locale(c.get("base_url", "")):
            c["modelli"] = [m for m in c.get("modelli", []) if m in reali]
            if not c["modelli"]:
                continue
        aggiungi(c)

    if ollama:
        aggiungi(ollama[0])
    else:
        aggiungi({"nome": "ollama", "base_url": "http://localhost:11434/v1",
                  "chiave": "", "modelli": []})

    aggiungi({"nome": "openai", "base_url": "https://api.openai.com/v1",
              "chiave": "OPENAI_API_KEY",
              "modelli": ["gpt-4o-mini", "gpt-4o"]})
    aggiungi({"nome": "anthropic", "base_url": "https://api.anthropic.com/v1",
              "chiave": "ANTHROPIC_API_KEY",
              "modelli": ["claude-3-5-sonnet-latest"]})

    if lm:
        aggiungi(lm[0])
    else:
        aggiungi({"nome": "lmstudio", "base_url": "http://localhost:1234/v1",
                  "chiave": "lm-studio", "modelli": ["lm-studio-model"]})

    if jan:
        aggiungi(jan[0])
    else:
        aggiungi({"nome": "jan", "base_url": "http://localhost:1337/v1",
                  "chiave": "jan-local-key", "modelli": ["jan-model"]})

    for c in aggiunti():
        c = dict(c)
        if filtra_locali and _e_locale(c.get("base_url", "")):
            c["modelli"] = [m for m in c.get("modelli", []) if m in reali]
            if not c["modelli"]:
                continue
        aggiungi(c)
    return clienti


def rileva_clienti():
    """Tutti i clienti disponibili, nell'ordine: opencode -> ollama -> openai ->
    anthropic -> lmstudio -> jan -> registro utente. Esegue i probe di rete
    (Ollama/LM Studio/Jan): per l'avvio rapido della GUI usare clienti_base()
    e chiamare questa in un thread.

    I clienti di default sono SEMPRE presenti:
      - ollama:    modelli reali se il server risponde, altrimenti NESSUN modello;
      - openai:    base https://api.openai.com/v1, chiave = NOME env
                   OPENAI_API_KEY, modelli ['gpt-4o-mini', 'gpt-4o'];
      - anthropic: base https://api.anthropic.com/v1, chiave = NOME env
                   ANTHROPIC_API_KEY, modelli ['claude-3-5-sonnet-latest'];
      - lmstudio:  base http://localhost:1234/v1, chiave 'lm-studio', modelli
                   ['lm-studio-model'] se il server non risponde, altrimenti i reali;
      - jan:       base http://localhost:1337/v1, chiave 'jan-local-key', modelli
                   ['jan-model'] se il server non risponde, altrimenti i reali.
    La chiave resta SEMPRE il NOME della variabile d'ambiente (o la chiave
    fittizia per lmstudio/jan), MAI il valore.

    I provider LOCALI (base localhost/127.0.0.1) da opencode/registro vengono
    filtrati sui modelli reali di Ollama: le voci inesistenti sono rimosse e un
    cliente locale rimasto senza modelli viene saltato. Il cloud NON è filtrato.
    La composizione è condivisa con clienti_base() (helper _componi)."""
    ollama = _ollama()
    lm = _compat_openai(1234, "lmstudio", chiave_fittizia="lm-studio") \
        or _compat_openai(1234, "lmstudio")
    jan = _compat_openai(1337, "jan", chiave_fittizia="jan-local-key") \
        or _compat_openai(1337, "jan")
    return _componi(ollama, lm, jan, filtra_locali=True)


def clienti_base():
    """Clienti di default e del registro SENZA rete (avvio GUI immediato):
    ollama senza modelli, openai/anthropic/lmstudio/jan coi default, registro
    utente invariato (il filtro sui modelli reali richiede la rete e resta a
    rileva_clienti). Stessa composizione tramite _componi."""
    return _componi(None, None, None, filtra_locali=False)


def voci_modelli(clienti, con_mock=True):
    """Voci per i menu a tendina: 'modello · client'."""
    voci = ["mock"] if con_mock else []
    for c in clienti:
        for m in c.get("modelli", []):
            voci.append(f"{m} · {c['nome']}")
    return voci


def trova_client(clienti, nome):
    for c in clienti:
        if c.get("nome") == nome:
            return c
    return None