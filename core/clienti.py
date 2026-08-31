# TRILogos — gestione clienti: rileva client locali e provider da opencode,
# permette di aggiungerne di propri. Le chiavi NON si salvano mai in chiaro:
# si riferisce solo il NOME della variabile d'ambiente (o si legge dalla config opencode).
import os, json, re, requests

REGISTRO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "clienti.json")
CONFIG_OPENCODE = os.path.join(os.path.expanduser("~"), ".config", "opencode", "opencode.jsonc")


def _leggi_jsonc(path):
    """Legge un file .jsonc (commenti /* */ e //) come dict."""
    try:
        testo = open(path, encoding="utf-8").read()
    except Exception:
        return None
    testo = re.sub(r'("(?:\\.|[^"\\])*")|/\*.*?\*/', lambda m: m.group(1) or "", testo, flags=re.S)
    testo = re.sub(r'("(?:\\.|[^"\\])*")|//[^\n]*', lambda m: m.group(1) or "", testo)
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
        opts = p.get("options") or {}
        base = opts.get("baseURL", "")
        if not base:
            continue
        modelli = list((p.get("models") or {}).keys()) or [nome]
        clienti.append({"nome": f"opencode:{nome}", "base_url": base,
                        "chiave": "", "modelli": modelli})
    return clienti


def _ollama():
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=4)
        if r.ok:
            modelli = [m["name"] for m in r.json().get("models", []) if m.get("name")]
            if modelli:
                return [{"nome": "ollama", "base_url": "http://localhost:11434/v1",
                         "chiave": "", "modelli": modelli}]
    except Exception:
        pass
    return []


def _compat_openai(porta, nome):
    base = f"http://localhost:{porta}/v1"
    try:
        r = requests.get(base + "/models", timeout=3)
        if r.ok:
            modelli = [m["id"] for m in r.json().get("data", []) if m.get("id")]
            if modelli:
                return [{"nome": nome, "base_url": base, "chiave": "", "modelli": modelli}]
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
    with open(REGISTRO, "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, indent=2)


def rileva_clienti():
    """Tutti i clienti disponibili: opencode + Ollama + compatibili + registro utente."""
    clienti = []
    visti = set()
    for c in _open() + _ollama() + _compat_openai(1234, "lmstudio") + _compat_openai(1337, "jan") + aggiunti():
        chiave = c.get("nome", "")
        if chiave in visti:
            continue
        visti.add(chiave)
        clienti.append(c)
    return clienti


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