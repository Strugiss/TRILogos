# TRILogos — dialoghi a tre voci (utente · A · B)
"""Adapter dei modelli: commerciali (OpenAI/Anthropic), locali (Ollama) e Mock per test.
Niente SDK: solo HTTP via `requests`. Le chiavi API si leggono da variabili d'ambiente."""
import os, json, re, base64, mimetypes, threading, time
try:
    import requests
except ImportError:
    raise ImportError("Manca la libreria 'requests': installala con: pip install requests")

# Timeout rete: (connect, read) secondi. Connect 10s per non bloccare la GUI/worker
# su host irraggiungibili; read 120s per completamenti lenti ma vivi.
TIMEOUT_RETE = (10, 120)


def _rete_ok(base, fn):
    """Esegue la chiamata di rete; errori di CONNESSIONE (server spento o
    irraggiungibile) -> RuntimeError in ITALIANO con l'URL del server (senza
    chiavi). Gli HTTPError (401/404) NON sono catturati: restano al
    comportamento attuale (raise_for_status)."""
    try:
        return fn()
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout,
            requests.exceptions.TooManyRedirects) as e:
        raise RuntimeError(
            f"server non raggiungibile: {base} — verifica che il servizio sia avviato") from e


def _int0(v):
    try:
        return max(int(v), 0)
    except (TypeError, ValueError):
        return 0


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


def _estrai_json(testo):
    """B1a: estrae il primo oggetto JSON valido dal testo (gestisce i fence
    ```json e il testo attorno). Ritorna il dict oppure None."""
    t = (testo or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t).strip()
    try:
        d = json.loads(t)
        return d if isinstance(d, dict) else None
    except Exception:
        pass
    i, j = t.find("{"), t.rfind("}")
    if 0 <= i < j:
        try:
            d = json.loads(t[i:j + 1])
            return d if isinstance(d, dict) else None
        except Exception:
            return None
    return None


class ModelloBase:
    """Interfaccia comune: ogni modello risponde a un prompt con un testo."""
    def __init__(self):
        self.ultimo_usage = None
        # B1a: schema JSON per l'output strutturato (None = testo libero).
        self.formato = None
        # FIX annullamento immediato: riferimento alla response HTTP in streaming
        # e flag di annullamento richiesto (chiusura volontaria, MAI fallback).
        self._response_attiva = None
        self._annullato = False

    def annulla(self):
        """Annullamento IMMEDIATO: alza il flag e chiude la response HTTP attiva
        (sblocca iter_lines). Sicuro anche senza nulla da chiudere."""
        self._annullato = True
        r = self._response_attiva
        if r is not None:
            try:
                r.close()
            except Exception:
                pass

    def precarica(self):
        """V6 (warmup): carica il modello in memoria per il primo flusso. No-op
        di default (i modelli cloud non si scaldano). Ritorna il tempo di
        caricamento in secondi, oppure None se non applicabile."""
        return None

    def _post_stream(self, url, **kwargs):
        """POST in streaming eseguita in un thread daemon: il riferimento alla
        response è disponibile appena arriva; se annulla() è richiesto durante
        l'attesa (es. load del modello), solleva SUBITO senza attendere la
        risposta. Il thread residuo termina da solo (risposta o timeout) e non
        blocca la chiusura del processo."""
        esito = {}

        def _lavoro():
            try:
                r = _rete_ok(url, lambda: requests.post(url, stream=True, **kwargs))
                if self._annullato:
                    try:
                        r.close()
                    except Exception:
                        pass
                    return
                esito["r"] = r
            except Exception as e:
                esito["e"] = e

        t = threading.Thread(target=_lavoro, daemon=True)
        t.start()
        while t.is_alive():
            if self._annullato:
                raise RuntimeError("elaborazione annullata dall'utente")
            t.join(0.05)
        if "e" in esito:
            raise esito["e"]
        r = esito.get("r")
        if r is None:
            raise RuntimeError("elaborazione annullata dall'utente")
        if self._annullato:
            try:
                r.close()
            except Exception:
                pass
            raise RuntimeError("elaborazione annullata dall'utente")
        self._response_attiva = r
        return r

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

    def rispondi_json(self, messaggi, schema, tentativi=3):
        """B1a: output strutturato (JSON Schema). Imposta il formato sul modello
        (Ollama: /api/chat con `format`), estrae e valida il JSON; retry fino a
        `tentativi` con log dell'output grezzo sui fallimenti. Ritorna
        (dict|None, output_grezzo): il chiamante decide cosa fare del None."""
        vecchio = getattr(self, "formato", None)
        self.formato = schema
        grezzo = ""
        try:
            for i in range(max(1, tentativi)):
                grezzo = self.rispondi(messaggi) or ""
                dati = _estrai_json(grezzo)
                if dati is not None:
                    return dati, grezzo
                print(f"[json-retry {i + 1}/{tentativi}] output non valido: "
                      f"{grezzo[:300]!r}")
        finally:
            self.formato = vecchio
        return None, grezzo

    def nome(self):
        return self.__class__.__name__


class ModelloOllama(ModelloBase):
    """Modelli locali via Ollama (http://localhost:11434)."""
    def __init__(self, modello, base="http://localhost:11434", temperatura=0.7, timeout=None,
                 keep_alive=None, num_ctx=None):
        super().__init__()
        self.modello = modello
        self.base = base.rstrip("/")
        self.temperatura = temperatura
        # Timeout (connect, read) esplicito; default documentato TIMEOUT_RETE.
        self.timeout = timeout or TIMEOUT_RETE
        # V3: keep_alive per non scaricare il modello (default -1 = mai).
        self.keep_alive = -1 if keep_alive is None else keep_alive
        # FIX CRITICO: contesto di default 8192 (il default del modello R1 è
        # 131072 -> 35 GB e thrashing). Configurabile (config.json -> ollama.num_ctx
        # o override per-voce modelli.<A|B|C>.num_ctx).
        self.num_ctx = 8192 if num_ctx is None else int(num_ctx)
        # V2: limite output per chiamata (impostato dal Canale) e troncamento.
        self.max_tokens = None
        self.ultimo_done_reason = None
        # V6: lock per modello — due warmup concorrenti non duplicano il load.
        self._lock_carico = threading.Lock()

    def rispondi(self, messaggi):
        # B1a: con uno schema attivo usa /api/chat (format = JSON Schema).
        if self.formato:
            return self._rispondi_chat(messaggi)
        prompt = "\n".join(f"{m['ruolo']}: {m['contenuto']}" for m in messaggi)
        self.ultimo_done_reason = None
        self._annullato = False
        options = {"temperature": self.temperatura, "num_ctx": self.num_ctx}
        if self.max_tokens:
            options["num_predict"] = self.max_tokens
        payload = {"model": self.modello, "prompt": prompt,
                   "stream": False, "options": options, "keep_alive": self.keep_alive}
        immagini = _estrae_immagini(messaggi)
        if immagini:
            payload["images"] = [_b64_immagine(p)[0] for p in immagini]
        r = _rete_ok(self.base, lambda: requests.post(
            self.base + "/api/generate",
            json=payload,
            timeout=self.timeout))
        r.raise_for_status()
        d = r.json()
        if not isinstance(d, dict):
            return ""
        if d.get("error"):
            raise RuntimeError(f"errore Ollama: {d['error']}")
        self.ultimo_done_reason = d.get("done_reason")
        if "prompt_eval_count" in d or "eval_count" in d:
            self.ultimo_usage = {"in": _int0(d.get("prompt_eval_count")),
                                 "out": _int0(d.get("eval_count"))}
        return (d.get("response") or "").strip()

    def _rispondi_chat(self, messaggi):
        """B1a: /api/chat con `format` (JSON Schema) per l'output strutturato.
        Stessi num_ctx/keep_alive/limiti delle chiamate normali."""
        self.ultimo_done_reason = None
        self._annullato = False
        options = {"temperature": self.temperatura, "num_ctx": self.num_ctx}
        if self.max_tokens:
            options["num_predict"] = self.max_tokens
        chat = []
        for m in messaggi:
            voce = {"role": m.get("ruolo", "user"), "content": m.get("contenuto", "")}
            immagini = m.get("immagini")
            if immagini:
                voce["images"] = [_b64_immagine(p)[0] for p in immagini]
            chat.append(voce)
        payload = {"model": self.modello, "messages": chat, "stream": False,
                   "options": options, "keep_alive": self.keep_alive,
                   "format": self.formato}
        r = _rete_ok(self.base, lambda: requests.post(
            self.base + "/api/chat", json=payload, timeout=self.timeout))
        r.raise_for_status()
        d = r.json()
        if not isinstance(d, dict):
            return ""
        if d.get("error"):
            raise RuntimeError(f"errore Ollama: {d['error']}")
        self.ultimo_done_reason = d.get("done_reason")
        if "prompt_eval_count" in d or "eval_count" in d:
            self.ultimo_usage = {"in": _int0(d.get("prompt_eval_count")),
                                 "out": _int0(d.get("eval_count"))}
        msg = d.get("message") or {}
        return (msg.get("content") or "").strip()

    def precarica(self):
        """V6 (warmup): carica il modello in memoria con una richiesta minima
        (num_predict: 1) e gli STESSI num_ctx (V7) e keep_alive (V3) delle
        chiamate reali: il modello resta residente e il primo flusso non paga
        il cold start. Lock per modello: due warmup concorrenti non duplicano
        il caricamento. Ritorna il tempo di caricamento in secondi."""
        with self._lock_carico:
            t0 = time.time()
            payload = {"model": self.modello, "prompt": "", "stream": False,
                       "options": {"num_predict": 1, "num_ctx": self.num_ctx},
                       "keep_alive": self.keep_alive}
            r = _rete_ok(self.base, lambda: requests.post(
                self.base + "/api/generate", json=payload, timeout=self.timeout))
            r.raise_for_status()
            d = r.json()
            if isinstance(d, dict) and d.get("error"):
                raise RuntimeError(f"errore warmup Ollama: {d['error']}")
            return round(time.time() - t0, 1)

    def rispondi_stream(self, messaggi, on_chunk):
        prompt = "\n".join(f"{m['ruolo']}: {m['contenuto']}" for m in messaggi)
        self.ultimo_done_reason = None
        self._annullato = False
        options = {"temperature": self.temperatura, "num_ctx": self.num_ctx}
        if self.max_tokens:
            options["num_predict"] = self.max_tokens
        payload = {"model": self.modello, "prompt": prompt,
                   "stream": True, "options": options, "keep_alive": self.keep_alive}
        immagini = _estrae_immagini(messaggi)
        if immagini:
            payload["images"] = [_b64_immagine(p)[0] for p in immagini]
        r = self._post_stream(self.base + "/api/generate", json=payload, timeout=self.timeout)
        try:
            with r:
                r.raise_for_status()
                pezzi = []
                for riga in r.iter_lines():
                    if not riga:
                        continue
                    try:
                        d = json.loads(riga)
                    except Exception:
                        continue
                    if not isinstance(d, dict):
                        continue
                    t = d.get("response", "")
                    if t:
                        on_chunk(t)
                        pezzi.append(t)
                    if d.get("error"):
                        raise RuntimeError(f"errore streaming Ollama: {d['error']}")
                    if d.get("done"):
                        self.ultimo_done_reason = d.get("done_reason")
                        if "prompt_eval_count" in d or "eval_count" in d:
                            self.ultimo_usage = {"in": _int0(d.get("prompt_eval_count")),
                                                 "out": _int0(d.get("eval_count"))}
                        break
        finally:
            self._response_attiva = None
        if self._annullato:
            raise RuntimeError("elaborazione annullata dall'utente")
        return "".join(pezzi).strip()

    def nome(self):
        return f"Ollama:{self.modello}"


class ModelloOpenAI(ModelloBase):
    """API commerciale OpenAI (chat completions)."""
    def __init__(self, modello="gpt-4o-mini", chiave=None, temperatura=0.7, timeout=None):
        self.ultimo_usage = None
        self.modello = modello
        self.chiave = chiave or os.environ.get("OPENAI_API_KEY", "")
        self.temperatura = temperatura
        self.timeout = timeout or TIMEOUT_RETE
        # V2: limite output per chiamata (impostato dal Canale) e troncamento.
        self.max_tokens = None
        self.ultimo_done_reason = None

    def rispondi(self, messaggi):
        self.ultimo_usage = None
        self.ultimo_done_reason = None
        self._annullato = False
        if not self.chiave:
            raise RuntimeError("chiave mancante: imposta OPENAI_API_KEY come variabile d'ambiente")
        m = [{"role": x["ruolo"], "content": x["contenuto"]} for x in messaggi]
        immagini = _estrae_immagini(messaggi)
        if immagini:
            contenuto = [{"type": "text", "text": m[-1]["content"]}]
            for p in immagini:
                b, mime = _b64_immagine(p)
                contenuto.append({"type": "image_url",
                                  "image_url": {"url": f"data:{mime};base64,{b}"}})
            m[-1]["content"] = contenuto
        corpo = {"model": self.modello, "messages": m,
                 "temperature": self.temperatura}
        if self.max_tokens:
            corpo["max_tokens"] = self.max_tokens
        r = _rete_ok("https://api.openai.com", lambda: requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.chiave}"},
            json=corpo, timeout=self.timeout))
        r.raise_for_status()
        d = r.json()
        if not isinstance(d, dict):
            return ""
        if d.get("error"):
            raise RuntimeError(f"errore OpenAI: {d['error']}")
        u = d.get("usage")
        if u:
            self.ultimo_usage = {"in": _int0(u.get("prompt_tokens")),
                                 "out": _int0(u.get("completion_tokens"))}
        scelte = d.get("choices") or []
        if not scelte:
            raise RuntimeError("OpenAI: risposta senza scelte")
        self.ultimo_done_reason = scelte[0].get("finish_reason")
        contenuto = (scelte[0].get("message") or {}).get("content")
        return (contenuto or "").strip()

    def rispondi_stream(self, messaggi, on_chunk):
        self.ultimo_usage = None
        self.ultimo_done_reason = None
        self._annullato = False
        if not self.chiave:
            raise RuntimeError("chiave mancante: imposta OPENAI_API_KEY come variabile d'ambiente")
        m = [{"role": x["ruolo"], "content": x["contenuto"]} for x in messaggi]
        immagini = _estrae_immagini(messaggi)
        if immagini:
            contenuto = [{"type": "text", "text": m[-1]["content"]}]
            for p in immagini:
                b, mime = _b64_immagine(p)
                contenuto.append({"type": "image_url",
                                  "image_url": {"url": f"data:{mime};base64,{b}"}})
            m[-1]["content"] = contenuto
        corpo = {"model": self.modello, "messages": m,
                 "temperature": self.temperatura, "stream": True,
                 "stream_options": {"include_usage": True}}
        if self.max_tokens:
            corpo["max_tokens"] = self.max_tokens
        r = self._post_stream("https://api.openai.com/v1/chat/completions",
                              headers={"Authorization": f"Bearer {self.chiave}"},
                              json=corpo, timeout=self.timeout)
        try:
            with r:
                r.raise_for_status()
                pezzi = []
                for riga in r.iter_lines():
                    if not riga:
                        continue
                    if riga.startswith(b":"):
                        continue
                    riga_testo = riga[6:] if riga.startswith(b"data:") else riga
                    if riga_testo.strip() == b"[DONE]":
                        break
                    try:
                        d = json.loads(riga_testo)
                    except Exception:
                        continue
                    if not isinstance(d, dict):
                        continue
                    if d.get("error"):
                        raise RuntimeError(f"errore streaming OpenAI: {d['error']}")
                    scelta = d.get("choices") or []
                    if scelta and scelta[0].get("delta", {}).get("content"):
                        t = scelta[0]["delta"]["content"]
                        on_chunk(t)
                        pezzi.append(t)
                    if scelta and scelta[0].get("finish_reason"):
                        self.ultimo_done_reason = scelta[0]["finish_reason"]
                    u = d.get("usage")
                    if u:
                        self.ultimo_usage = {"in": _int0(u.get("prompt_tokens")),
                                             "out": _int0(u.get("completion_tokens"))}
                    if d.get("choices") and d["choices"][0].get("finish_reason"):
                        if self.ultimo_usage is not None:
                            break
        finally:
            self._response_attiva = None
        if self._annullato:
            raise RuntimeError("elaborazione annullata dall'utente")
        return "".join(pezzi).strip()

    def nome(self):
        return f"OpenAI:{self.modello}"


class ModelloAnthropic(ModelloBase):
    """API commerciale Anthropic (Claude)."""
    def __init__(self, modello="claude-3-5-sonnet-latest", chiave=None, temperatura=0.7, timeout=None):
        self.ultimo_usage = None
        self.modello = modello
        self.chiave = chiave or os.environ.get("ANTHROPIC_API_KEY", "")
        self.temperatura = temperatura
        self.timeout = timeout or TIMEOUT_RETE
        # V2: limite output per chiamata (impostato dal Canale) e troncamento.
        self.max_tokens = None
        self.ultimo_done_reason = None

    def rispondi(self, messaggi):
        self.ultimo_usage = None
        self.ultimo_done_reason = None
        self._annullato = False
        if not self.chiave:
            raise RuntimeError("chiave mancante: imposta ANTHROPIC_API_KEY come variabile d'ambiente")
        m = [{"role": x["ruolo"], "content": x["contenuto"]} for x in messaggi]
        immagini = _estrae_immagini(messaggi)
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
        contenuto_messaggio = [{"type": "text", "text": user}]
        for p in immagini:
            b, mime = _b64_immagine(p)
            contenuto_messaggio.append({"type": "image", "source": {"type": "base64",
                                                                    "media_type": mime, "data": b}})
        r = _rete_ok("https://api.anthropic.com", lambda: requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": self.chiave, "anthropic-version": "2023-06-01"},
            json={"model": self.modello, "max_tokens": self.max_tokens or 2048,
                  "temperature": self.temperatura,
                  "system": system, "messages": [{"role": "user", "content": contenuto_messaggio}]},
            timeout=self.timeout))
        r.raise_for_status()
        d = r.json()
        if not isinstance(d, dict):
            return ""
        if d.get("error"):
            raise RuntimeError(f"errore Anthropic: {d['error']}")
        self.ultimo_done_reason = d.get("stop_reason")
        u = d.get("usage")
        if u:
            self.ultimo_usage = {"in": _int0(u.get("input_tokens")),
                                 "out": _int0(u.get("output_tokens"))}
        contenuti = d.get("content") or []
        if not contenuti:
            raise RuntimeError("Anthropic: risposta senza contenuto")
        for blocco in contenuti:
            if isinstance(blocco, dict) and blocco.get("type") == "text" and blocco.get("text"):
                return blocco["text"].strip()
        return ""

    def nome(self):
        return f"Anthropic:{self.modello}"


class ModelloOpenAICompat(ModelloBase):
    """Client generico compatibile OpenAI (LM Studio, Jan, llama.cpp, qualsiasi base_url)."""
    def __init__(self, modello, base_url="http://localhost:1234/v1", chiave="", temperatura=0.7, timeout=None):
        self.ultimo_usage = None
        self.modello = modello
        base_url = base_url.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url += "/v1"
        self.base_url = base_url
        self.chiave = chiave
        self.temperatura = temperatura
        self.timeout = timeout or TIMEOUT_RETE
        # V2: limite output per chiamata (impostato dal Canale) e troncamento.
        self.max_tokens = None
        self.ultimo_done_reason = None

    def rispondi(self, messaggi):
        self.ultimo_usage = None
        self.ultimo_done_reason = None
        self._annullato = False
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
        corpo = {"model": self.modello, "messages": m,
                 "temperature": self.temperatura}
        if self.max_tokens:
            corpo["max_tokens"] = self.max_tokens
        r = _rete_ok(self.base_url, lambda: requests.post(
            self.base_url + "/chat/completions",
            headers=headers,
            json=corpo, timeout=self.timeout))
        r.raise_for_status()
        d = r.json()
        if not isinstance(d, dict):
            return ""
        if d.get("error"):
            raise RuntimeError(f"errore client compatibile: {d['error']}")
        u = d.get("usage")
        if u:
            self.ultimo_usage = {"in": _int0(u.get("prompt_tokens")),
                                 "out": _int0(u.get("completion_tokens"))}
        scelte = d.get("choices") or []
        if not scelte:
            raise RuntimeError("Compat: risposta senza scelte")
        self.ultimo_done_reason = scelte[0].get("finish_reason")
        contenuto = (scelte[0].get("message") or {}).get("content")
        return (contenuto or "").strip()

    def rispondi_stream(self, messaggi, on_chunk):
        """Streaming compatibile OpenAI (SSE), annullabile come gli altri adapter."""
        self.ultimo_usage = None
        self.ultimo_done_reason = None
        self._annullato = False
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
        corpo = {"model": self.modello, "messages": m,
                 "temperature": self.temperatura, "stream": True}
        if self.max_tokens:
            corpo["max_tokens"] = self.max_tokens
        r = self._post_stream(self.base_url + "/chat/completions", headers=headers,
                              json=corpo, timeout=self.timeout)
        try:
            with r:
                r.raise_for_status()
                pezzi = []
                for riga in r.iter_lines():
                    if not riga:
                        continue
                    if riga.startswith(b":"):
                        continue
                    riga_testo = riga[6:] if riga.startswith(b"data:") else riga
                    if riga_testo.strip() == b"[DONE]":
                        break
                    try:
                        d = json.loads(riga_testo)
                    except Exception:
                        continue
                    if not isinstance(d, dict):
                        continue
                    if d.get("error"):
                        raise RuntimeError(f"errore streaming compat: {d['error']}")
                    scelta = d.get("choices") or []
                    if scelta and scelta[0].get("delta", {}).get("content"):
                        t = scelta[0]["delta"]["content"]
                        on_chunk(t)
                        pezzi.append(t)
                    if scelta and scelta[0].get("finish_reason"):
                        self.ultimo_done_reason = scelta[0]["finish_reason"]
                    u = d.get("usage")
                    if u:
                        self.ultimo_usage = {"in": _int0(u.get("prompt_tokens")),
                                             "out": _int0(u.get("completion_tokens"))}
        finally:
            self._response_attiva = None
        if self._annullato:
            raise RuntimeError("elaborazione annullata dall'utente")
        return "".join(pezzi).strip()

    def nome(self):
        return f"{self.modello}"


class ModelloMock(ModelloBase):
    """Modello fittizio per test senza chiavi: risponde in modo deterministico."""
    def __init__(self, nome="Mock", voce="l'eco"):
        super().__init__()
        self.nome_mock = nome
        self.voce = voce

    def rispondi(self, messaggi):
        if not messaggi:
            return f"[{self.nome_mock}] (nessun messaggio ricevuto)"
        ultimo = messaggi[-1].get("contenuto", "") or ""
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


def modello_da_voce(voce, clienti=None, timeout=None, keep_alive=None, num_ctx=None):
    """Converte una voce del menu ('modello · client') in un'istanza Modello.

    Chiavi dei clienti custom (registro clienti.json):
      - prefisso 'env:NOME'  -> risolta dalla variabile d'ambiente NOME;
      - qualsiasi altro valore (es. 'sk-...' dal form dello splash) -> usato
        LETTERALMENTE come chiave, senza risoluzioni fallite su os.environ.

    `timeout`: tupla (connect, read) passata ai modelli di rete; None -> default
    TIMEOUT_RETE. `keep_alive` (V3) e `num_ctx` (fix critico contesto): solo per
    i modelli Ollama; None -> keep_alive -1, num_ctx 8192. Il core non legge
    config.json: i valori arrivano dal chiamante."""
    from .clienti import trova_client
    clienti = clienti or []
    if voce == "mock" or not voce:
        return crea_modello("mock")
    if " · " in voce:
        nome, client = voce.rsplit(" · ", 1)
    else:
        nome, client = voce, "ollama"
    if client == "ollama":
        return crea_modello("ollama", modello=nome, timeout=timeout,
                            keep_alive=keep_alive, num_ctx=num_ctx)
    if client == "openai":
        return crea_modello("openai", modello=nome, timeout=timeout)
    if client == "anthropic":
        return crea_modello("anthropic", modello=nome, timeout=timeout)
    c = trova_client(clienti, client)
    if c:
        chiave = ""
        val = c.get("chiave", "") or ""
        if val.startswith("env:"):
            chiave = os.environ.get(val[4:], "")
        else:
            chiave = val
        return crea_modello("openaicompat", modello=nome,
                            base_url=c.get("base_url", "http://localhost:11434/v1"),
                            chiave=chiave, timeout=timeout)
    return crea_modello("ollama", modello=nome, timeout=timeout,
                        keep_alive=keep_alive, num_ctx=num_ctx)