# TRILogos — Motore interno (B2e): modelli locali + adapter per il flusso
"""Collega i moduli del motore interno (Profiler B2a, Piano B2b, Runner B2c,
Downloader B2d) alla GUI:
- `modelli_locali()`: elenco dei GGUF scaricati in `%APPDATA%\\TRILogos\\modelli\\`;
- voci del menu etichettate nella lingua attiva (es. "Qwen2.5-7B (motore)");
- `ModelloMotore`: adapter del flusso — al primo uso avvia `llama-server` col
  Piano calcolato (profilo reale + metadati GGUF) e streamma via il runner;
  `annulla()` chiude lo stream in corso; un solo server per processo.

Nessuna dipendenza nuova; nessun percorso esterno; il modulo non tocca i file
dei modelli (sola lettura, a parte i download gestiti dal downloader).
"""
import os
import time

from . import downloader
from . import piano as _piano
from . import profiler
from . import runner_llama
from .modelli import ModelloBase, ModelloOpenAICompat

PORTA_DEFAULT = 8080
CONTESTO_DEFAULT = 4096
TAG_MOTORE = {"it": "motore", "en": "engine", "fr": "moteur", "es": "motor",
              "de": "Motor", "pt": "motor", "zh": "引擎"}


def cartella_modelli() -> str:
    """Cartella dei modelli del motore interno (decisione B2)."""
    return downloader.CARTELLA_MODELLI_DEFAULT


def modelli_locali(cartella: str = None):
    """[(percorso, nome_file)] dei GGUF presenti (esclude i .parziale)."""
    cartella = cartella or cartella_modelli()
    trovati = []
    if os.path.isdir(cartella):
        for nome in sorted(os.listdir(cartella)):
            if nome.lower().endswith(".gguf"):
                percorso = os.path.join(cartella, nome)
                if os.path.isfile(percorso):
                    trovati.append((percorso, nome))
    return trovati


def nome_voce(percorso: str, tag: str = "motore") -> str:
    """Voce del menu per un modello del motore: 'NomeSenzaEstensione (tag)'."""
    base = os.path.basename(percorso)
    if base.lower().endswith(".gguf"):
        base = base[:-5]
    return f"{base} ({tag})"


def e_voce_motore(voce: str) -> bool:
    """True se la voce del menu appartiene al motore interno (qualsiasi lingua)."""
    if not voce:
        return False
    return any(voce.endswith(f" ({tag})") for tag in TAG_MOTORE.values())


def percorso_da_voce(voce: str, cartella: str = None):
    """Percorso del GGUF corrispondente a una voce del menu, o None."""
    if not e_voce_motore(voce):
        return None
    base = voce.rsplit(" (", 1)[0]
    for percorso, _nome in modelli_locali(cartella):
        if os.path.basename(percorso)[:-5] == base:
            return percorso
    return None


def llama_disponibile() -> bool:
    """True se llama-server e' localizzabile (motore pronto)."""
    try:
        runner_llama.trova_llama_server()
        return True
    except Exception:
        return False


def _token_nome(nome: str):
    """Token alfanumerici significativi di un nome file modello (per associare
    un mmproj al modello giusto nella stessa cartella)."""
    base = (nome or "").lower()
    for suffisso in (".gguf", ".mmproj"):
        if base.endswith(suffisso):
            base = base[: -len(suffisso)]
    scarti = {"gguf", "mmproj", "q2", "q3", "q4", "q5", "q6", "q8", "f16", "k",
              "m", "s", "l", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9"}
    token = []
    for parte in base.replace("_", "-").replace(".", "-").split("-"):
        parte = parte.strip()
        if len(parte) >= 2 and parte not in scarti:
            token.append(parte)
    return set(token)


def trova_mmproj(percorso: str):
    """Percorso del proiettore multimodale (mmproj) associato al modello:
    stessa cartella, nome simile (almeno 3 token in comune), altrimenti None.
    I modelli vision senza mmproj non ricevono il flag --mmproj."""
    percorso = os.path.abspath(percorso)
    cartella = os.path.dirname(percorso)
    if not os.path.isdir(cartella):
        return None
    token_modello = _token_nome(os.path.basename(percorso))
    migliore, punteggio = None, 0
    for nome in sorted(os.listdir(cartella)):
        if "mmproj" not in nome.lower() or not nome.lower().endswith(".gguf"):
            continue
        comuni = len(token_modello & _token_nome(nome))
        if comuni > punteggio:
            migliore, punteggio = os.path.join(cartella, nome), comuni
    return migliore if punteggio >= 3 else None


def ferma_tutti() -> int:
    """Stop pulito di TUTTI i server motore (fine flusso / chiusura app)."""
    return runner_llama.ferma_tutti()


def ferma_server_non_usati(canale=None) -> int:
    """Stop dei server dei modelli del motore NON più presenti nel canale."""
    percorsi = []
    if canale is not None:
        for polo in ("A", "B", "C"):
            modello = getattr(canale, polo, None)
            if isinstance(modello, ModelloMotore):
                percorsi.append(modello.percorso)
    return runner_llama.ferma_non_usati(percorsi)


def crea_modello(percorso: str, porta: int = None,
                 contesto: int = CONTESTO_DEFAULT) -> "ModelloMotore":
    """Adapter del motore interno per il percorso GGUF dato.
    `porta=None` -> il runner sceglie la prima porta libera (8080+)."""
    return ModelloMotore(percorso, porta=porta, contesto=contesto)


class ModelloMotore(ModelloBase):
    """Adapter del flusso per un GGUF del motore interno.

    Al primo uso: metadati GGUF + profilo reale -> Piano (B2b) -> avvio del
    server (B2c). Lo streaming riusa `ModelloOpenAICompat` verso il server.
    `annulla()` (dal canale) chiude lo stream in corso; il server resta attivo
    per i turni successivi (keep-alive del processo, stop a fine sessione o
    cambio modello)."""

    def __init__(self, percorso: str, porta: int = None,
                 contesto: int = CONTESTO_DEFAULT):
        super().__init__()
        self.percorso = os.path.abspath(percorso)
        self.porta = int(porta) if porta else None  # None -> prima porta libera
        self.contesto = int(contesto)
        # V2: il Canale imposta temperatura e max_tokens per ogni passo; il
        # troncamento e i token vengono riportati dal compat (come gli altri).
        self.temperatura = 0.7
        self.max_tokens = None
        self.ultimo_done_reason = None
        self._metadati = None
        self._piano_corrente = None
        self._handle = None
        self._compat = None
        self._mmproj = None

    def nome(self):
        return nome_voce(self.percorso)

    def _piano(self):
        if self._piano_corrente is None:
            self._metadati = _piano.leggi_metadati_gguf(self.percorso)
            profilo = profiler.rileva()
            self._piano_corrente = _piano.pianifica(profilo, self._metadati,
                                                     self.contesto)
        return self._piano_corrente

    def _assicura_server(self):
        """Avvia (o riusa) il server per questo modello: un solo server per
        modello, mai duplicati (il runner riusa l'handle attivo). Per i modelli
        vision associa il mmproj (--mmproj) se presente nella cartella."""
        if self._handle is not None and runner_llama.attivo() \
                and self._handle.processo.poll() is None \
                and self._handle.percorso_modello == self.percorso:
            return self._handle
        self._handle = runner_llama.avvia(self._piano(), self.percorso,
                                          porta=self.porta, mmproj=self._mmproj())
        return self._handle

    def _mmproj(self):
        if self._mmproj is None:
            self._mmproj = trova_mmproj(self.percorso) or ""
        return self._mmproj or None

    def precarica(self):
        """V6/warmup: avvia il server e ritorna il tempo di avvio in secondi."""
        t0 = time.time()
        self._assicura_server()
        return round(time.time() - t0, 1)

    def rispondi(self, messaggi):
        pezzi = []
        return self.rispondi_stream(messaggi, pezzi.append)

    def rispondi_stream(self, messaggi, on_chunk):
        handle = self._assicura_server()
        compat = ModelloOpenAICompat(
            modello=handle.modello_id or "model",
            base_url=f"{handle.base_url}/v1",
            temperatura=getattr(self, "temperatura", 0.7))
        # V2: limite token del passo impostato dal Canale
        compat.max_tokens = getattr(self, "max_tokens", None)
        self._compat = compat
        try:
            testo = compat.rispondi_stream(messaggi, on_chunk)
        finally:
            self.ultimo_usage = compat.ultimo_usage
            self.ultimo_done_reason = compat.ultimo_done_reason
            self._compat = None
        return testo

    def annulla(self):
        """Annulla lo stream in corso (il server resta attivo)."""
        self._annullato = True
        if self._compat is not None:
            try:
                self._compat.annulla()
            except Exception:
                pass

    def ferma_server(self):
        """Stop pulito del server avviato per questo modello."""
        if self._handle is not None:
            runner_llama.stop(self._handle)
            self._handle = None
