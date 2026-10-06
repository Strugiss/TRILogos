# TRILogos — Runner llama.cpp (B2c, motore interno) + V5 prompt cache
"""Lifecycle di `llama-server` con gli argomenti del Piano (B2b):
- localizzazione eseguibile: TRILOGOS_LLAMA_DIR → PATH → winget → cartella
  locale del progetto (tecnica ripresa da ARCA runner.py, sola lettura);
- avvio con `-m`, `--n-gpu-layers`, `-c`, `--cache-type-k/v q8_0`, `-t`,
  `--no-mmap`, `--host 127.0.0.1 --port`; readiness via `/health` (fallback
  `/v1/models`) con timeout; log del server su FILE (mai in console);
- streaming tramite l'adapter esistente `ModelloOpenAICompat` (nessun nuovo
  client HTTP); metriche (tempo al primo token, tok/s);
- stop pulito: termina SOLO il processo avviato dal runner (zero orfani);
- V5: `--cache-reuse` per il riuso del prefisso KV (se supportato dall'help),
  per ridurre il TTFT sui turni successivi con system prompt fisso.

Sicurezza: il runner non uccide mai processi che non ha avviato; il log resta
sul PC (nessun dato esce). Italiano nei messaggi.
"""
import glob
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional

from .modelli import ModelloOpenAICompat

VARIABILE_DIR = "TRILOGOS_LLAMA_DIR"
NOME_ESEGUIBILE = "llama-server.exe" if os.name == "nt" else "llama-server"
CARTELLA_LOCALE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "llama.cpp")
PORTA_DEFAULT = 8080
TIMEOUT_AVVIO = 180
TIMEOUT_STOP = 10
CACHE_REUSE_DEFAULT = 256
_HELP_TIMEOUT = 30
_HTTP_TIMEOUT = 2

_CACHE_TROVATO = {"percorso": None, "cercato": False}
_CACHE_SUPPORTO = {}


class ErroreRunner(Exception):
    """Errore di localizzazione/avvio/stop (messaggio in italiano)."""


@dataclass
class Metriche:
    """Metriche di una generazione: tempo al primo token, tok/s, token, durata."""
    primo_token_s: Optional[float] = None
    tok_s: Optional[float] = None
    token_totali: int = 0
    durata_s: Optional[float] = None
    completamento: str = ""


@dataclass
class Handle:
    """Server avviato dal runner: processo, endpoint, modello, piano, log."""
    processo: subprocess.Popen
    porta: int
    base_url: str
    modello_id: str
    percorso_modello: str
    piano: object
    log: str
    cache_reuse: Optional[int] = None
    avviato_il: float = field(default_factory=time.time)


def guida_llama_server() -> str:
    """Testo di aiuto in italiano quando llama-server non si trova (fallback)."""
    return (
        "llama-server non e' installato o non e' raggiungibile.\n"
        "Il motore interno non e' disponibile: TRILogos puo' usare i client "
        "esterni (Ollama, LM Studio, Jan, cloud BYOK).\n"
        "Per installare il motore interno:\n"
        "  1) col gestore pacchetti di Windows:  winget install ggml.llamacpp\n"
        "  2) oppure scarica una release Windows di llama.cpp da GitHub "
        "(github.com/ggml-org/llama.cpp/releases), scompattala e imposta la "
        "variabile d'ambiente TRILOGOS_LLAMA_DIR sulla cartella che contiene "
        "llama-server.exe (es. set TRILOGOS_LLAMA_DIR=C:\\llama.cpp)")


def _candidati():
    """Percorsi candidati per llama-server, nell'ordine ARCA: variabile
    d'ambiente → PATH → pacchetto winget → cartella locale del progetto."""
    variabile = os.environ.get(VARIABILE_DIR)
    if variabile:
        yield os.path.join(variabile, NOME_ESEGUIBILE)
    trovato = shutil.which("llama-server")
    if trovato:
        yield trovato
    base = os.environ.get("LOCALAPPDATA")
    if base:
        for cartella in sorted(glob.glob(
                os.path.join(base, "Microsoft", "WinGet", "Packages",
                             "ggml.llamacpp*"))):
            yield os.path.join(cartella, NOME_ESEGUIBILE)
    for cartella in (CARTELLA_LOCALE,
                     os.path.join(CARTELLA_LOCALE, "build", "bin", "Release")):
        yield os.path.join(cartella, NOME_ESEGUIBILE)


def trova_llama_server():
    """Percorso di llama-server (cache). Solleva ErroreRunner con la guida se
    assente: il chiamante attiva il fallback sui client esterni."""
    if _CACHE_TROVATO["cercato"]:
        if _CACHE_TROVATO["percorso"] is None:
            raise ErroreRunner(guida_llama_server())
        return _CACHE_TROVATO["percorso"]
    _CACHE_TROVATO["cercato"] = True
    for candidato in _candidati():
        if candidato and os.path.isfile(candidato):
            _CACHE_TROVATO["percorso"] = candidato
            return candidato
    raise ErroreRunner(guida_llama_server())


def _azzera_cache_ricerca():
    """Solo per i test: riabilita la ricerca dell'eseguibile."""
    _CACHE_TROVATO["percorso"] = None
    _CACHE_TROVATO["cercato"] = False


def supporto_opzioni(eseguibile: str) -> dict:
    """Opzioni del server rilevate da `--help` (cache per percorso):
    V5 `cache_reuse`, `slot_save`, `parallel`."""
    if eseguibile in _CACHE_SUPPORTO:
        return _CACHE_SUPPORTO[eseguibile]
    try:
        esito = subprocess.run(
            [eseguibile, "--help"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=_HELP_TIMEOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        testo = (esito.stdout or "") + (esito.stderr or "")
    except (OSError, subprocess.TimeoutExpired):
        testo = ""
    opzioni = {
        "cache_reuse": "--cache-reuse" in testo,
        "slot_save": "--slot-save-path" in testo,
        "parallel": "--parallel" in testo,
        # build recenti: --no-mmap sostituito da --load-mode (none = no-mmap)
        "load_mode": "--load-mode" in testo,
        # modelli vision: proiettore multimodale
        "mmproj": "--mmproj" in testo,
    }
    _CACHE_SUPPORTO[eseguibile] = opzioni
    return opzioni


def comando_server(piano, percorso_modello: str, porta: int = PORTA_DEFAULT,
                   eseguibile: Optional[str] = None,
                   cache_reuse: Optional[int] = None,
                   mmproj: Optional[str] = None) -> List[str]:
    """Argomenti del processo llama-server a partire dal Piano (WYSIWYG):
    ngl, contesto, KV, thread, mmap; host/porta fissi; V5 se richiesto;
    `--mmproj` per i modelli vision (se supportato dalla build)."""
    eseguibile = eseguibile or trova_llama_server()
    comando = [eseguibile, "-m", percorso_modello,
               "--n-gpu-layers", str(int(piano.ngl)),
               "-c", str(int(piano.contesto)),
               "-t", str(int(piano.thread)),
               "--host", "127.0.0.1", "--port", str(int(porta))]
    if piano.kv_tipo == "q8_0":
        comando += ["--cache-type-k", "q8_0", "--cache-type-v", "q8_0"]
    if not piano.mmap:
        if supporto_opzioni(eseguibile).get("load_mode"):
            comando += ["--load-mode", "none"]  # no-mmap (build recenti)
        else:
            comando += ["--no-mmap"]
    if cache_reuse:
        comando += ["--cache-reuse", str(int(cache_reuse))]
    if mmproj and supporto_opzioni(eseguibile).get("mmproj"):
        comando += ["--mmproj", mmproj]
    return comando


def _apri_url(url: str):
    with urllib.request.urlopen(url, timeout=_HTTP_TIMEOUT) as risposta:
        return risposta.status, risposta.read().decode("utf-8", "replace")


def _pronto(porta: int) -> bool:
    for percorso in ("/health", "/v1/models"):
        try:
            stato, _ = _apri_url(f"http://127.0.0.1:{porta}{percorso}")
            if stato == 200:
                return True
        except (urllib.error.URLError, OSError, ValueError):
            continue
    return False


def _modello_id(porta: int) -> str:
    try:
        _, testo = _apri_url(f"http://127.0.0.1:{porta}/v1/models")
        dati = json.loads(testo)
        elenco = dati.get("data") or []
        if elenco:
            return str(elenco[0].get("id") or "model")
    except (urllib.error.URLError, OSError, ValueError):
        pass
    return "model"


def _coda_log(percorso: str, righe: int = 12) -> str:
    try:
        with open(percorso, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-righe:])
    except OSError:
        return "(log non leggibile)"


def _cartella_log() -> str:
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"),
                                                     "AppData", "Roaming")
    cartella = os.path.join(base, "TRILogos", "log")
    os.makedirs(cartella, exist_ok=True)
    return cartella


def _porta_libera(preferita: int = PORTA_DEFAULT) -> int:
    """Prima porta libera da `preferita` in su (esclusi gli handle attivi)."""
    usate = {h.porta for h in _RUNNER.handles.values() if h.processo.poll() is None}
    for porta in range(int(preferita), int(preferita) + 20):
        if porta in usate:
            continue
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", porta))
            return porta
        except OSError:
            continue
    raise ErroreRunner(
        f"nessuna porta libera per llama-server ({preferita}-{int(preferita) + 19})")


def avvia(piano, percorso_modello: str, porta: int = None,
          cache_reuse="auto", timeout_avvio: int = TIMEOUT_AVVIO,
          mmproj: Optional[str] = None) -> Handle:
    """Avvia llama-server col Piano dato e attende la readiness.
    Un solo server PER MODELLO (percorso): se esiste un handle attivo per lo
    stesso modello viene riusato senza ricaricare. `porta=None` -> prima porta
    libera (8080+). Se il piano e' di un modello GRANDE, gli altri handle
    grandi vengono fermati prima (regola ARCA: un solo grande residente).
    `cache_reuse`: "auto" (V5 abilitata se supportata), None (disabilitata),
    oppure un intero (chunk minimo)."""
    if not os.path.isfile(percorso_modello):
        raise ErroreRunner(f"modello non trovato: {percorso_modello}")
    if piano.contesto <= 0:
        raise ErroreRunner(f"contesto non valido: {piano.contesto}")
    percorso = os.path.abspath(percorso_modello)
    esistente = _RUNNER.handles.get(percorso)
    if esistente is not None and esistente.processo.poll() is None and \
            (porta is None or int(porta) == esistente.porta):
        return esistente  # riuso: nessun doppio caricamento
    if esistente is not None:
        stop(esistente)
    if getattr(piano, "grande", False):
        for altro in list(_RUNNER.handles.values()):
            if getattr(altro.piano, "grande", False) and altro.processo.poll() is None:
                stop(altro)
    if porta is None:
        porta = _porta_libera()
    eseguibile = trova_llama_server()
    opzioni = supporto_opzioni(eseguibile)
    if cache_reuse == "auto":
        cache_reuse = CACHE_REUSE_DEFAULT if opzioni["cache_reuse"] else None
    elif cache_reuse and not opzioni["cache_reuse"]:
        raise ErroreRunner(
            "--cache-reuse richiesto ma non supportato da questo llama-server (V5)")
    comando = comando_server(piano, percorso_modello, porta, eseguibile,
                             cache_reuse, mmproj)
    percorso_log = os.path.join(_cartella_log(), f"llama-server-{int(porta)}.log")
    try:
        log_file = open(percorso_log, "w", encoding="utf-8")
    except OSError as errore:
        raise ErroreRunner(f"impossibile creare il log '{percorso_log}': {errore}")
    try:
        processo = subprocess.Popen(
            comando, stdout=log_file, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, creationflags=(
                subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0))
    except OSError as errore:
        log_file.close()
        raise ErroreRunner(f"avvio di llama-server fallito: {errore}")
    handle = Handle(processo=processo, porta=int(porta),
                    base_url=f"http://127.0.0.1:{int(porta)}",
                    modello_id="", percorso_modello=percorso,
                    piano=piano, log=percorso_log, cache_reuse=cache_reuse)
    scadenza = time.time() + timeout_avvio
    while time.time() < scadenza:
        if processo.poll() is not None:
            log_file.close()
            raise ErroreRunner(
                f"llama-server e' terminato durante l'avvio (codice {processo.returncode}):\n"
                + _coda_log(percorso_log))
        if _pronto(int(porta)):
            handle.modello_id = _modello_id(int(porta))
            _RUNNER.handles[percorso] = handle
            log_file.close()
            return handle
        time.sleep(0.5)
    stop(handle)
    log_file.close()
    raise ErroreRunner(
        f"llama-server non pronto entro {timeout_avvio} s sulla porta {porta}:\n"
        + _coda_log(percorso_log))


def stop(handle: Handle) -> bool:
    """Stop pulito: termina SOLO il processo avviato dal runner (terminate,
    attesa, kill di riserva). Idempotente. True se il processo e' chiuso."""
    if handle is None:
        return True
    processo = handle.processo
    if processo.poll() is None:
        try:
            processo.terminate()
            processo.wait(timeout=TIMEOUT_STOP)
        except subprocess.TimeoutExpired:
            processo.kill()
            try:
                processo.wait(timeout=TIMEOUT_STOP)
            except subprocess.TimeoutExpired:
                return False
        except OSError:
            return processo.poll() is not None
    for percorso, h in list(_RUNNER.handles.items()):
        if h is handle:
            del _RUNNER.handles[percorso]
    return processo.poll() is not None


def ferma_tutti() -> int:
    """Stop di TUTTI i server avviati dal runner (fine flusso / chiusura).
    Ritorna il numero di server fermati."""
    fermati = 0
    for handle in list(_RUNNER.handles.values()):
        if stop(handle):
            fermati += 1
    return fermati


def ferma_non_usati(percorsi) -> int:
    """Stop dei server dei modelli NON più usati (cambio modello)."""
    usati = {os.path.abspath(p) for p in percorsi}
    fermati = 0
    for percorso, handle in list(_RUNNER.handles.items()):
        if percorso not in usati and stop(handle):
            fermati += 1
    return fermati
    if getattr(_RUNNER, "handle", None) is handle:
        _RUNNER.handle = None
    return processo.poll() is not None


def attivo() -> bool:
    """True se almeno un server avviato dal runner e' in esecuzione."""
    return any(h.processo.poll() is None for h in _RUNNER.handles.values())


def server_attivi():
    """[(percorso, porta)] dei server attivi (per lo stato motore)."""
    return [(p, h.porta) for p, h in _RUNNER.handles.items()
            if h.processo.poll() is None]


def stream(handle: Handle, messaggi, on_chunk, temperatura: float = 0.7):
    """Streaming via ModelloOpenAICompat verso il server del runner.
    Ritorna (testo, Metriche): tempo al primo token, tok/s, token, durata."""
    modello = ModelloOpenAICompat(
        modello=handle.modello_id or "model",
        base_url=f"{handle.base_url}/v1", temperatura=temperatura)
    metriche = Metriche()
    t0 = time.time()

    def _callback(pezzo):
        if metriche.primo_token_s is None:
            metriche.primo_token_s = time.time() - t0
        metriche.token_totali += 1
        on_chunk(pezzo)

    testo = modello.rispondi_stream(messaggi, _callback)
    metriche.durata_s = round(time.time() - t0, 2)
    usage = getattr(modello, "ultimo_usage", None)
    if usage and usage.get("out"):
        metriche.token_totali = int(usage["out"])
    metriche.completamento = getattr(modello, "ultimo_done_reason", "") or ""
    if metriche.durata_s and metriche.token_totali:
        metriche.tok_s = round(metriche.token_totali / metriche.durata_s, 2)
    return testo, metriche


class _Runner:
    """Stato del runner: un handle per modello (percorso), mai duplicati."""
    def __init__(self):
        self.handles = {}


_RUNNER = _Runner()
