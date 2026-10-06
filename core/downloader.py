# TRILogos — Downloader modelli (B2d, motore interno)
"""Catalogo per fascia hardware (dal Profiler B2a) + download da URL ufficiali
con progresso, ripresa (HTTP Range) e verifica checksum SHA256.

Regole (Decisioni.md §B2 rev. 2):
- catalogo come dati: nome, parametri, dimensione, URL ufficiale (Hugging Face),
  licenza (testo/link), checksum SHA256; gli URL sono verificabili con HEAD;
- la licenza si mostra PRIMA del download (API `licenza()` per la UI);
- i modelli NON sono ridistribuiti nel pacchetto: si scaricano solo dagli URL
  ufficiali; destinazione default `%APPDATA%\\TRILogos\\modelli\\` (override);
- progresso (byte/totali/percentuale/velocita), ripresa da file `.parziale`,
  checksum a fine download; errori in italiano, mai crash.

Privacy: il downloader contatta SOLO gli URL del catalogo, mai dati utente.
"""
import hashlib
import os
import shutil
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, List, Optional

BLOCCO_BYTE = 1024 * 1024          # 1 MiB per blocco
TIMEOUT_RETE = 60
MARGINE_SPAZIO_BYTE = 64 * 1024 * 1024   # margine disco richiesto (64 MiB)
USER_AGENT = "TRILogos/2.0 (motore interno; download modelli)"
CARTELLA_MODELLI_DEFAULT = os.path.join(
    os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"),
                                              "AppData", "Roaming"),
    "TRILogos", "modelli")


class ErroreDownload(Exception):
    """Errore di download (messaggio in italiano, per la UI)."""


class InterrompiDownload(Exception):
    """Sollevata dal callback di progresso per interrompere: il file .parziale
    resta su disco e la chiamata successiva riprende da lì."""


@dataclass
class Voce:
    """Voce del catalogo: dati puri, nessuna logica. `input`/`output` dichiarano
    le capacita' (testo/immagini/video); `mmproj_*` solo per i modelli vision: il
    proiettore multimodale va scaricato accanto al modello e passato a
    llama-server con `--mmproj`."""
    chiave: str
    nome: str
    parametri: str
    fascia: str
    dimensione_gb: float
    dimensione_byte: int
    url: str
    licenza: str
    licenza_url: str
    sha256: str
    nome_file: str
    input: tuple = ("testo",)
    output: tuple = ("testo",)
    mmproj_url: str = ""
    mmproj_byte: int = 0
    mmproj_sha256: str = ""
    mmproj_file: str = ""


CATALOGO = (
    Voce(chiave="0.5b",
         nome="Qwen2.5-0.5B-Instruct Q4_K_M",
         parametri="0.5B · Q4_K_M",
         fascia="prova / hardware minimo (qualsiasi GPU o solo CPU)",
         dimensione_gb=0.49, dimensione_byte=491400032,
         url="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf",
         licenza="Apache License 2.0",
         licenza_url="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF",
         sha256="74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db",
         nome_file="qwen2.5-0.5b-instruct-q4_k_m.gguf",
         input=("testo",), output=("testo",)),
    Voce(chiave="3b",
         nome="Qwen2.5-3B-Instruct Q4_K_M",
         parametri="3B · Q4_K_M",
         fascia="solo CPU / GPU piccola",
         dimensione_gb=2.10, dimensione_byte=2104932768,
         url="https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf",
         licenza="Qwen Research License",
         licenza_url="https://huggingface.co/Qwen/Qwen2.5-3B-Instruct/blob/main/LICENSE",
         sha256="626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d",
         nome_file="qwen2.5-3b-instruct-q4_k_m.gguf",
         input=("testo",), output=("testo",)),
    Voce(chiave="7b",
         nome="Qwen2.5-7B-Instruct Q4_K_M",
         parametri="7B · Q4_K_M",
         fascia="~8 GB VRAM",
         dimensione_gb=4.68, dimensione_byte=4683074240,
         url="https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf",
         licenza="Apache License 2.0",
         licenza_url="https://huggingface.co/Qwen/Qwen2.5-7B-Instruct",
         sha256="65b8fcd92af6b4fefa935c625d1ac27ea29dcb6ee14589c55a8f115ceaaa1423",
         nome_file="Qwen2.5-7B-Instruct-Q4_K_M.gguf",
         input=("testo",), output=("testo",)),
    Voce(chiave="14b",
         nome="DeepSeek-R1-Distill-Qwen-14B Q4_K_M",
         parametri="14B · Q4_K_M",
         fascia="~12 GB VRAM",
         dimensione_gb=8.99, dimensione_byte=8988109984,
         url="https://huggingface.co/unsloth/DeepSeek-R1-Distill-Qwen-14B-GGUF/resolve/main/DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf",
         licenza="Apache License 2.0 (repo unsloth; modello originale MIT)",
         licenza_url="https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-14B",
         sha256="67a7933cf2ad596a393c8e13b30bc4da2d50b283e250b78554aed18817eca31c",
         nome_file="DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf",
         input=("testo",), output=("testo",)),
    Voce(chiave="vision3b",
         nome="Qwen2.5-VL-3B-Instruct Q4_K_M (vision)",
         parametri="3B · Q4_K_M + mmproj Q8_0",
         fascia="~8 GB VRAM · input immagini",
         dimensione_gb=1.93, dimensione_byte=1929901056,
         url="https://huggingface.co/ggml-org/Qwen2.5-VL-3B-Instruct-GGUF/resolve/main/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf",
         licenza="Apache License 2.0",
         licenza_url="https://huggingface.co/ggml-org/Qwen2.5-VL-3B-Instruct-GGUF",
         sha256="d02fe9b69ad8cadbbd228e387667af66612c44bed29ffc8eb1e7caf9ac486c12",
         nome_file="Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf",
         input=("testo", "immagini"), output=("testo",),
         mmproj_url="https://huggingface.co/ggml-org/Qwen2.5-VL-3B-Instruct-GGUF/resolve/main/mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf",
         mmproj_byte=844757728,
         mmproj_sha256="980c9b2f78c04e6cff93d277ada09e768394f112d75db3b4e9dea8a69f9fb904",
         mmproj_file="mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf"),
    Voce(chiave="27b",
         nome="Qwen3.8-27B Q4_K_M",
         parametri="27B · Q4_K_M",
         fascia="offload (~19 GB) · ideale ≥16 GB VRAM",
         dimensione_gb=18.97, dimensione_byte=18973870528,
         url="https://huggingface.co/ggml-org/Qwen3.8-27B-GGUF/resolve/main/Qwen3.8-27B-Q4_K_M.gguf",
         licenza="Apache License 2.0",
         licenza_url="https://huggingface.co/ggml-org/Qwen3.8-27B-GGUF",
         sha256="c600de0300ae8a0eb3a6c0b8b5561b8b96f16bd2c863c2a66c42de29d391a747",
         nome_file="Qwen3.8-27B-Q4_K_M.gguf",
         input=("testo", "immagini", "video"), output=("testo",)),
)


def catalogo() -> List[Voce]:
    """Tutte le voci del catalogo (copie leggere, dati puri)."""
    return list(CATALOGO)


def voce(chiave: str) -> Voce:
    """Voce per chiave ('0.5b', '3b', '7b', '14b')."""
    for v in CATALOGO:
        if v.chiave == chiave:
            return v
    raise ErroreDownload(f"voce di catalogo sconosciuta: '{chiave}'")


def per_fascia(profilo) -> List[Voce]:
    """Voci consigliate per la fascia hardware rilevata dal Profiler (B2a):
    ~8 GB VRAM → 7B Q4; ~12 GB VRAM → 14B Q4; solo CPU → 3B.
    La voce 'prova' (0.5B) è sempre disponibile nel catalogo."""
    vram = int(getattr(profilo, "vram_totale_mib", 0) or 0)
    if vram >= 11000:
        return [voce("14b")]
    if vram >= 7000:
        return [voce("7b")]
    return [voce("3b")]


def licenza(v) -> str:
    """Testo di licenza da mostrare PRIMA del download (API per la UI)."""
    return (f"Modello: {v.nome}\nParametri: {v.parametri}\n"
            f"Input: {', '.join(v.input)} · Output: {', '.join(v.output)}\n"
            f"Licenza: {v.licenza}\nLicenza (link): {v.licenza_url}\n"
            f"Dimensione: {v.dimensione_gb:.2f} GB"
            + (f" (+ mmproj {v.mmproj_byte / 1024 ** 3:.2f} GB)" if v.mmproj_url else "")
            + f"\nURL ufficiale: {v.url}\nSHA256: {v.sha256}\n"
            "Il modello non e' incluso nel pacchetto: viene scaricato solo "
            "dall'URL ufficiale, con verifica del checksum.")


def nome_file_sanificato(nome: str) -> str:
    """Nome file senza separatori o caratteri non validi (Windows): spazi e
    caratteri stranieri -> '_'; conserva lettere, cifre, punto, trattino."""
    nome = os.path.basename((nome or "").strip())
    puliti = []
    for carattere in nome:
        if carattere.isalnum() or carattere in "._-":
            puliti.append(carattere)
        else:
            puliti.append("_")
    risultato = "".join(puliti).strip("._")
    return risultato or "modello.gguf"


def _progresso(callback, fase, byte, totale, t0, byte_iniziali=0, nota="", file=""):
    if callback is None:
        return
    trascorso = max(1e-6, time.time() - t0)
    velocita = (byte - byte_iniziali) / trascorso / (1024 * 1024)
    callback({
        "fase": fase,
        "byte": byte,
        "totale": totale,
        "percentuale": round(100.0 * byte / totale, 1) if totale else None,
        "velocita_mb_s": round(velocita, 2),
        "ripresa_da": byte_iniziali,
        "nota": nota,
        "file": file,
    })


def _sha256_file(percorso: str) -> str:
    h = hashlib.sha256()
    with open(percorso, "rb") as f:
        for blocco in iter(lambda: f.read(BLOCCO_BYTE), b""):
            h.update(blocco)
    return h.hexdigest()


def _apri(url: str, range_da: int = 0, timeout: int = TIMEOUT_RETE):
    richiesta = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    if range_da > 0:
        richiesta.add_header("Range", f"bytes={range_da}-")
    return urllib.request.urlopen(richiesta, timeout=timeout)


def verifica_url(v, timeout: int = 30):
    """HEAD dell'URL ufficiale: (ok, descrizione). 200/302/307 = raggiungibile."""
    richiesta = urllib.request.Request(v.url, method="HEAD",
                                       headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(richiesta, timeout=timeout) as risposta:
            if risposta.status in (200, 302, 307):
                return True, f"HTTP {risposta.status}"
            return False, f"HTTP {risposta.status}"
    except urllib.error.HTTPError as errore:
        return False, f"HTTP {errore.code}"
    except (urllib.error.URLError, OSError) as errore:
        return False, f"errore di rete: {errore}"


def _scarica_file(url, sha256, nome_file, byte_attesi, cartella,
                  progresso_callback=None, timeout=TIMEOUT_RETE, etichetta=""):
    """Scarica UN file con progresso, ripresa HTTP Range e checksum SHA256
    (se noto). Ritorna il percorso del file completo."""
    try:
        os.makedirs(cartella, exist_ok=True)
    except OSError as errore:
        raise ErroreDownload(f"impossibile creare la cartella '{cartella}': {errore}")
    destinazione = os.path.join(cartella, nome_file_sanificato(nome_file))
    parziale = destinazione + ".parziale"
    t0 = time.time()
    # gia' completo e verificato?
    if os.path.isfile(destinazione) and not os.path.isfile(parziale):
        if sha256 and _sha256_file(destinazione).lower() == sha256.lower():
            _progresso(progresso_callback, "completato", os.path.getsize(destinazione),
                       os.path.getsize(destinazione), t0,
                       nota="gia' presente e verificato", file=etichetta)
            return destinazione
        try:
            os.remove(destinazione)
        except OSError as errore:
            raise ErroreDownload(f"file esistente non valido e non rimovibile: {errore}")
    inizio = os.path.getsize(parziale) if os.path.isfile(parziale) else 0
    try:
        risposta = _apri(url, inizio, timeout)
    except urllib.error.HTTPError as errore:
        if errore.code == 404:
            raise ErroreDownload(f"file non trovato (HTTP 404): {url}")
        if errore.code == 416 and inizio > 0:
            os.remove(parziale)
            raise ErroreDownload("intervallo non valido: il file parziale era "
                                 "piu' grande del previsto, riprova il download")
        raise ErroreDownload(f"errore del server (HTTP {errore.code}) per {url}")
    except (urllib.error.URLError, OSError) as errore:
        raise ErroreDownload(f"errore di rete: {errore} — controlla la connessione "
                             "e riprova")
    try:
        with risposta:
            stato = risposta.status
            if inizio > 0 and stato == 200:
                inizio = 0  # server senza Range: si riparte da capo
            lunghezza = int(risposta.headers.get("Content-Length") or 0)
            totale = (inizio + lunghezza) if lunghezza else int(byte_attesi or 0)
            da_scaricare = max(0, totale - inizio)
            libero = shutil.disk_usage(cartella).free
            if libero < da_scaricare + MARGINE_SPAZIO_BYTE:
                raise ErroreDownload(
                    f"spazio insufficiente in '{cartella}': servono "
                    f"{da_scaricare / 1024 ** 3:.2f} GB (+ margine), liberi "
                    f"{libero / 1024 ** 3:.2f} GB")
            _progresso(progresso_callback, "download", inizio, totale, t0,
                       inizio, nota="ripresa" if inizio else "avvio", file=etichetta)
            modalita = "ab" if inizio > 0 else "wb"
            scaricati = inizio
            with open(parziale, modalita) as file:
                while True:
                    blocco = risposta.read(BLOCCO_BYTE)
                    if not blocco:
                        break
                    file.write(blocco)
                    scaricati += len(blocco)
                    _progresso(progresso_callback, "download", scaricati, totale,
                               t0, inizio, file=etichetta)
    except InterrompiDownload:
        raise  # il .parziale resta su disco: la prossima chiamata riprende
    except (urllib.error.URLError, OSError) as errore:
        raise ErroreDownload(f"errore durante il download: {errore} — il file "
                             "parziale e' conservato: riprova per riprendere")
    if sha256:
        _progresso(progresso_callback, "verifica", os.path.getsize(parziale),
                   totale, t0, inizio, file=etichetta)
        if _sha256_file(parziale).lower() != sha256.lower():
            try:
                os.remove(parziale)
            except OSError:
                pass
            raise ErroreDownload("checksum SHA256 non corrispondente: download "
                                 "corrotto o incompleto, riprova")
    os.replace(parziale, destinazione)
    _progresso(progresso_callback, "completato", os.path.getsize(destinazione),
               os.path.getsize(destinazione), t0, inizio, file=etichetta)
    return destinazione


def scarica(v, cartella: Optional[str] = None,
            progresso_callback: Optional[Callable] = None,
            timeout: int = TIMEOUT_RETE) -> str:
    """Scarica la voce nella cartella (default `%APPDATA%\\TRILogos\\modelli\\`).
    Per i modelli VISION scarica anche il proiettore multimodale (`mmproj`).
    - progresso: callback(dict) con fase/byte/totale/percentuale/velocita/file;
      se il callback solleva `InterrompiDownload`, il download si ferma e il
      file `.parziale` resta per la ripresa;
    - ripresa: se `.parziale` esiste si usa HTTP Range; se il server non lo
      supporta (200) si riparte da capo;
    - checksum: SHA256 verificato a fine download (se noto); mismatch ->
      errore e parziale rimosso;
    - ritorna il percorso del modello (file principale)."""
    cartella = cartella or CARTELLA_MODELLI_DEFAULT
    percorso = _scarica_file(v.url, v.sha256, v.nome_file, v.dimensione_byte,
                             cartella, progresso_callback, timeout,
                             etichetta=v.nome_file)
    if v.mmproj_url and v.mmproj_file:
        _scarica_file(v.mmproj_url, v.mmproj_sha256, v.mmproj_file,
                      v.mmproj_byte, cartella, progresso_callback, timeout,
                      etichetta=v.mmproj_file)
    return percorso
