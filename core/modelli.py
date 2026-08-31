# TRILogos — dialoghi a tre voci (utente · A · B)
"""Adapter dei modelli: commerciali (OpenAI/Anthropic), locali (Ollama) e Mock per test.
Niente SDK: solo HTTP via `requests`. Le chiavi API si leggono da variabili d'ambiente."""
import os, json, time, random, base64, mimetypes
import requests


def _b64_immagine(path):
    with open(path, "rb") as f:
        dati = f.read()
    mime = mimetypes.guess_type(path)[0] or "image/png"
    return base64.b64encode(dati).decode(), mime


def _estrae_immagini(messaggi):
    """Raccoglie i percorsi immagine dal campo 'immagini' dell'ultimo messaggio user."""
    immagini = []
    for m in reversed(messaggi):
        if m.get("immagini"):
            immagini = m["immagini"]
            break
    return immagini

class ModelloBase:
    """Interfaccia comune: ogni modello risponde a un prompt con un testo."""
    def rispondi(self, messaggi):
        """messaggi: lista di dict {'ruolo': system|user|assistant, 'contenuto': str}"""
        raise NotImplementedError

    def rispondi_stream(self, messaggi, on_chunk):
        """Versione streaming: on_chunk(testo_parziale). Fallback: rispondi + un chunk."""
        try:
            testo = self.rispondi(messaggi)
            on_chunk(testo)
            return testo
        except Exception:
            raise

    def nome(self):
        return self.__class__.__name__


class ModelloOllama(ModelloBase):
    """Modelli locali via Ollama (http://localhost:11434)."""
    def __init__(self, modello, base="http://localhost:11434", temperatura=0.7):
        self.modello = modello
        self.base = base
        self.temperatura = temperatura

    def rispondi(self, messaggi):
        prompt = "\n".join(f"{m['ruolo']}: {m['contenuto']}" for m in messaggi)
        payload = {"model": self.modello, "prompt": prompt,
                   "stream": False, "temperature": self.temperatura}
        immagini = _estrae_immagini(messaggi)
        if immagini:
            payload["images"] = [_b64_immagine(p)[0] for p in immagini]
        r = requests.post(
            self.base + "/api/generate",
            json=payload,
            timeout=600)
        r.raise_for_status()
        return r.json()["response"].strip()

    def rispondi_stream(self, messaggi, on_chunk):
        prompt = "\n".join(f"{m['ruolo']}: {m['contenuto']}" for m in messaggi)
        payload = {"model": self.modello, "prompt": prompt,
                   "stream": True, "temperature": self.temperatura}
        immagini = _estrae_immagini(messaggi)
        if immagini:
            payload["images"] = [_b64_immagine(p)[0] for p in immagini]
        with requests.post(self.base + "/api/generate", json=payload, stream=True, timeout=600) as r:
            r.raise_for_status()
            pezzi = []
            for riga in r.iter_lines():
                if not riga:
                    continue
                try:
                    d = json.loads(riga)
                except Exception:
                    continue
                t = d.get("response", "")
                if t:
                    on_chunk(t)
                    pezzi.append(t)
                if d.get("done"):
                    break
        return "".join(pezzi).strip()

    def nome(self):
        return f"Ollama:{self.modello}"


class ModelloOpenAI(ModelloBase):
    """API commerciale OpenAI (chat completions)."""
    def __init__(self, modello="gpt-4o-mini", chiave=None, temperatura=0.7):
        self.modello = modello
        self.chiave = chiave or os.environ.get("OPENAI_API_KEY", "")
        self.temperatura = temperatura

    def rispondi(self, messaggi):
        m = [{"role": x["ruolo"], "content": x["contenuto"]} for x in messaggi]
        immagini = _estrae_immagini(messaggi)
        if immagini:
            contenuto = [{"type": "text", "text": m[-1]["content"]}]
            for p in immagini:
                b, mime = _b64_immagine(p)
                contenuto.append({"type": "image_url",
                                  "image_url": {"url": f"data:{mime};base64,{b}"}})
            m[-1]["content"] = contenuto
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.chiave}"},
            json={"model": self.modello, "messages": m,
                  "temperature": self.temperatura}, timeout=600)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    def rispondi_stream(self, messaggi, on_chunk):
        m = [{"role": x["ruolo"], "content": x["contenuto"]} for x in messaggi]
        immagini = _estrae_immagini(messaggi)
        if immagini:
            contenuto = [{"type": "text", "text": m[-1]["content"]}]
            for p in immagini:
                b, mime = _b64_immagine(p)
                contenuto.append({"type": "image_url",
                                  "image_url": {"url": f"data:{mime};base64,{b}"}})
            m[-1]["content"] = contenuto
        with requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.chiave}"},
                json={"model": self.modello, "messages": m,
                      "temperature": self.temperatura, "stream": True},
                stream=True, timeout=600) as r:
            r.raise_for_status()
            pezzi = []
            for riga in r.iter_lines():
                if not riga or riga.startswith(b":"):
                    continue
                try:
                    d = json.loads(riga[6:] if riga.startswith(b"data:") else riga)
                except Exception:
                    continue
                scelta = d.get("choices") or []
                if scelta and scelta[0].get("delta", {}).get("content"):
                    t = scelta[0]["delta"]["content"]
                    on_chunk(t)
                    pezzi.append(t)
                if d.get("choices") and d["choices"][0].get("finish_reason"):
                    break
        return "".join(pezzi).strip()

    def nome(self):
        return f"OpenAI:{self.modello}"


class ModelloAnthropic(ModelloBase):
    """API commerciale Anthropic (Claude)."""
    def __init__(self, modello="claude-3-5-sonnet-latest", chiave=None, temperatura=0.7):
        self.modello = modello
        self.chiave = chiave or os.environ.get("ANTHROPIC_API_KEY", "")
        self.temperatura = temperatura

    def rispondi(self, messaggi):
        m = [{"role": x["ruolo"], "content": x["contenuto"]} for x in messaggi]
        immagini = _estrae_immagini(messaggi)
        if immagini:
            contenuto = [{"type": "text", "text": m[-1]["content"]}]
            for p in immagini:
                b, mime = _b64_immagine(p)
                contenuto.append({"type": "image", "source": {"type": "base64",
                                                               "media_type": mime, "data": b}})
            m[-1]["content"] = contenuto
        system = "\n".join(x["content"] for x in m if x["role"] == "system")
        parti = []
        for x in m:
            if x["role"] == "system":
                continue
            testo = x["content"]
            if isinstance(testo, list):
                testi = [p.get("text", "") for p in testo if isinstance(p, dict) and p.get("type") == "text"]
                testo = " ".join(t for t in testi if t)
            parti.append(f"{'Assistente' if x['role']=='assistant' else 'Utente'}: {testo}")
        user = "\n\n".join(parti)
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": self.chiave, "anthropic-version": "2023-06-01"},
            json={"model": self.modello, "max_tokens": 2048,
                  "temperature": self.temperatura,
                  "system": system, "messages": [{"role": "user", "content": user}]},
            timeout=600)
        r.raise_for_status()
        return r.json()["content"][0]["text"].strip()

    def nome(self):
        return f"Anthropic:{self.modello}"


class ModelloOpenAICompat(ModelloBase):
    """Client generico compatibile OpenAI (LM Studio, Jan, llama.cpp, qualsiasi base_url)."""
    def __init__(self, modello, base_url="http://localhost:1234/v1", chiave="", temperatura=0.7):
        self.modello = modello
        self.base_url = base_url.rstrip("/")
        self.chiave = chiave
        self.temperatura = temperatura

    def rispondi(self, messaggi):
        m = [{"role": x["ruolo"], "content": x["contenuto"]} for x in messaggi]
        immagini = _estrae_immagini(messaggi)
        if immagini:
            contenuto = [{"type": "text", "text": m[-1]["content"]}]
            for p in immagini:
                b, mime = _b64_immagine(p)
                contenuto.append({"type": "image_url",
                                  "image_url": {"url": f"data:{mime};base64,{b}"}})
            m[-1]["content"] = contenuto
        headers = {"Content-Type": "application/json"}
        if self.chiave:
            headers["Authorization"] = f"Bearer {self.chiave}"
        r = requests.post(self.base_url + "/chat/completions",
                          headers=headers,
                          json={"model": self.modello, "messages": m,
                                "temperature": self.temperatura}, timeout=600)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    def nome(self):
        return f"{self.modello}"


class ModelloMock(ModelloBase):
    """Modello fittizio per test senza chiavi: risponde in modo deterministico."""
    def __init__(self, nome="Mock", voce="l'eco"):
        self.nome_mock = nome
        self.voce = voce

    def rispondi(self, messaggi):
        ultimo = messaggi[-1]["contenuto"]
        h = sum(ord(c) for c in ultimo)
        frasi = [
            f"[{self.nome_mock}] Ho ricevuto: «{ultimo[:120]}…». Analisi: il nucleo della richiesta è coerente; propongo di verificare i passaggi 1-2 prima di procedere.",
            f"[{self.nome_mock}] Sul messaggio «{ultimo[:100]}…»: concordo sull'impostazione; aggiungerei un controllo incrociato e una sintesi finale in due righe.",
            f"[{self.nome_mock}] Noto un punto da chiarire in «{ultimo[:100]}…»: la parte centrale va esplicitata meglio; propongo di dividerci il lavoro: tu la parte formale, io la verifica.",
        ]
        return frasi[h % len(frasi)]

    def nome(self):
        return f"Mock:{self.nome_mock}"


def crea_modello(tipo, **kwargs):
    """Factory: tipo in {mock, ollama, openai, anthropic, openaicompat}."""
    cls = {"mock": ModelloMock, "ollama": ModelloOllama,
           "openai": ModelloOpenAI, "anthropic": ModelloAnthropic,
           "openaicompat": ModelloOpenAICompat}.get(tipo)
    if cls is None:
        raise ValueError(f"Tipo sconosciuto: {tipo}")
    if tipo == "mock":
        return ModelloMock(**{k: v for k, v in kwargs.items() if k in ("nome", "voce")})
    return cls(**kwargs)


def modello_da_voce(voce, clienti=None):
    """Converte una voce del menu ('modello · client') in un'istanza Modello."""
    from .clienti import trova_client
    clienti = clienti or []
    if voce == "mock" or not voce:
        return crea_modello("mock")
    if " · " in voce:
        nome, client = voce.rsplit(" · ", 1)
    else:
        nome, client = voce, "ollama"
    if client == "ollama":
        return crea_modello("ollama", modello=nome)
    if client == "openai":
        return crea_modello("openai", modello=nome)
    if client == "anthropic":
        return crea_modello("anthropic", modello=nome)
    c = trova_client(clienti, client)
    if c:
        chiave = ""
        if c.get("chiave", "").startswith("env:"):
            chiave = os.environ.get(c["chiave"][4:], "")
        elif c.get("chiave"):
            chiave = c["chiave"]
        return crea_modello("openaicompat", modello=nome,
                            base_url=c.get("base_url", "http://localhost:11434/v1"),
                            chiave=chiave)
    return crea_modello("ollama", modello=nome)


def modelli_disponibili():
    """Elenco modelli per i menu a tendina: Ollama locali (API) + preset commerciali + mock."""
    opzioni = ["mock"]
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        if r.ok:
            for m in r.json().get("models", []):
                nome = m.get("name", "")
                if nome:
                    opzioni.append(f"{nome} · ollama")
    except Exception:
        pass
    for nome in ("gpt-4o-mini", "gpt-4o", "gpt-4.1"):
        opzioni.append(f"{nome} · openai")
    for nome in ("claude-3-5-sonnet-latest", "claude-3-7-sonnet-latest"):
        opzioni.append(f"{nome} · anthropic")
    return opzioni