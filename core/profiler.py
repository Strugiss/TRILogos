# TRILogos — Profiler hardware (B2a, motore interno)
"""Rileva l'hardware disponibile (VRAM/RAM/CPU/disco) per il motore interno
(llama.cpp + Piano risorse): SOLO LETTURA, nessuna scrittura, nessuna
dipendenza nuova. Adattato dal Profiler di ARCA
(9_PROGETTO_ARCA\\Script\\arca\\profiler.py, DESIGN_ARCA §2a) al perimetro
TRILogos: nessun percorso o import verso ARCA.

Regole:
- `rileva()` non solleva MAI eccezioni: un dato mancante resta `None` e il
  motivo finisce in `Profilo.avvisi` (messaggi in italiano, per la UI);
- GPU via `nvidia-smi` (subprocess, finestra nascosta, timeout); se assente o
  in errore: nessuna GPU NVIDIA rilevata, avviso chiaro;
- RAM via `ctypes` (GlobalMemoryStatusEx) e CPU via `os` (+ PowerShell per i
  core fisici, come ARCA) — nessun pacchetto esterno;
- privacy: nessun dato esce dal PC (solo letture locali).
"""
import ctypes
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional

try:
    import psutil  # opzionale, come in ARCA: usato SOLO se gia' presente
except ImportError:
    psutil = None

COMANDO_GPU = "nvidia-smi"
TIMEOUT_GPU = 15
CARTELLA_MODELLI_DEFAULT = os.path.join(
    os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming"),
    "TRILogos", "modelli")


class ErroreProfiler(Exception):
    """Errore di rilevazione di una singola voce (messaggio in italiano)."""


@dataclass
class Profilo:
    """Profilo hardware tipizzato. Ogni campo None = dato non rilevato; il
    motivo e' elencato in `avvisi` (lista, mai None)."""
    gpu_nome: Optional[str] = None
    vram_totale_mib: Optional[int] = None
    vram_libera_mib: Optional[int] = None
    ram_totale_gb: Optional[float] = None
    ram_libera_gb: Optional[float] = None
    cpu_core: Optional[int] = None
    cpu_thread: Optional[int] = None
    disco_libero_gb: Optional[float] = None
    disco_percorso: Optional[str] = None
    avvisi: List[str] = field(default_factory=list)


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def _esegui_comando(argomenti):
    """Esegue un comando locale (finestra nascosta su Windows) e ne ritorna lo
    stdout. Solleva ErroreProfiler con messaggio in italiano se manca, va in
    timeout o fallisce (tecnica ripresa da ARCA)."""
    try:
        esito = subprocess.run(
            argomenti,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_GPU,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except FileNotFoundError:
        raise ErroreProfiler(
            f"comando non trovato: '{argomenti[0]}' non e' installato o non e' nel PATH")
    except subprocess.TimeoutExpired:
        raise ErroreProfiler(
            f"il comando '{argomenti[0]}' non ha risposto entro {TIMEOUT_GPU} secondi")
    if esito.returncode != 0:
        dettaglio = (esito.stderr or esito.stdout or "").strip()
        raise ErroreProfiler(
            f"il comando '{argomenti[0]}' e' fallito (codice {esito.returncode}): {dettaglio}")
    return esito.stdout or ""


def _numero_mib(testo):
    """'8192 MiB' / '8192' / '8.0 GiB'? -> int MiB (ARCA: solo MiB/MB)."""
    return int(float(testo.lower().replace("mib", "").replace("mb", "").strip()))


def _parse_nvidia_smi(testo):
    """Righe 'nome, totale, libera' -> [(nome, totale_mib, libera_mib)].
    Solleva ErroreProfiler se l'output non e' riconoscibile (tecnica ARCA)."""
    gpu = []
    for riga in testo.splitlines():
        riga = riga.strip()
        if not riga:
            continue
        parti = [parte.strip() for parte in riga.split(",")]
        if len(parti) < 3:
            raise ErroreProfiler(f"output di nvidia-smi non riconosciuto: '{riga}'")
        try:
            totale = _numero_mib(parti[-2])
            libera = _numero_mib(parti[-1])
        except ValueError:
            raise ErroreProfiler(f"output di nvidia-smi non riconosciuto: '{riga}'")
        gpu.append((", ".join(parti[:-2]), totale, libera))
    if not gpu:
        raise ErroreProfiler("nvidia-smi non ha restituito alcuna GPU")
    return gpu


def _rileva_gpu():
    """(nome, vram_totale_mib, vram_libera_mib) via nvidia-smi; somma le GPU."""
    testo = _esegui_comando(
        [COMANDO_GPU, "--query-gpu=name,memory.total,memory.free",
         "--format=csv,noheader"])
    gpu = _parse_nvidia_smi(testo)
    nome = " + ".join(voce[0] for voce in gpu)
    totale = sum(voce[1] for voce in gpu)
    libera = sum(voce[2] for voce in gpu)
    return nome, totale, libera


def _rileva_ram():
    """(ram_totale_gb, ram_libera_gb) via ctypes GlobalMemoryStatusEx."""
    try:
        stato = _MEMORYSTATUSEX()
        stato.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stato)):
            raise OSError("GlobalMemoryStatusEx ha restituito 0")
        return (round(stato.ullTotalPhys / 1024 ** 3, 1),
                round(stato.ullAvailPhys / 1024 ** 3, 1))
    except Exception as errore:
        raise ErroreProfiler(f"RAM non leggibile: {errore}")


def _core_fisici():
    """Numero di core fisici: psutil se presente, altrimenti PowerShell
    (stessa tecnica di ARCA). None se non determinabile."""
    if psutil is not None:
        return psutil.cpu_count(logical=False)
    testo = _esegui_comando([
        "powershell", "-NoProfile", "-Command",
        "(Get-CimInstance Win32_Processor | Select-Object -First 1 "
        "-ExpandProperty NumberOfCores)"])
    return int(testo.strip())


def _rileva_cpu():
    """(cpu_core, cpu_thread). I thread vengono da os.cpu_count(); i core
    fisici da psutil/PowerShell. Un valore non determinabile resta None."""
    thread = os.cpu_count()
    try:
        core = _core_fisici()
    except (ErroreProfiler, ValueError):
        core = None
    return core, thread


def _cartella_esistente(percorso):
    """Risale dal percorso al primo genitore esistente (per misurare il disco
    anche se la cartella modelli non e' ancora stata creata)."""
    attuale = os.path.abspath(percorso)
    while attuale and not os.path.isdir(attuale):
        genitore = os.path.dirname(attuale)
        if genitore == attuale:
            return None
        attuale = genitore
    return attuale or None


def _rileva_disco(percorso):
    """(disco_libero_gb, percorso_misurato) per la cartella modelli."""
    esistente = _cartella_esistente(percorso)
    if esistente is None:
        raise ErroreProfiler(f"cartella non trovata: {percorso}")
    try:
        libero = shutil.disk_usage(esistente).free / 1024 ** 3
    except OSError as errore:
        raise ErroreProfiler(f"disco non leggibile in '{esistente}': {errore}")
    return round(libero, 1), esistente


def vram_occupata():
    """Processi che usano la GPU (nvidia-smi --query-compute-apps):
    [{nome, pid, mib}] ordinati per memoria; `mib` None se il driver non
    espone la memoria per processo ([N/A] su WDDM). Mai eccezioni: [] se
    nvidia-smi manca o non risponde (B2g: modalita' pulita)."""
    try:
        testo = _esegui_comando(
            [COMANDO_GPU, "--query-compute-apps=pid,process_name,used_memory",
             "--format=csv,noheader"])
    except ErroreProfiler:
        return []
    voci = []
    for riga in testo.splitlines():
        riga = riga.strip()
        if not riga:
            continue
        parti = [parte.strip() for parte in riga.split(",")]
        if len(parti) < 3:
            continue
        try:
            pid = int(parti[0])
        except ValueError:
            continue
        nome = parti[1]
        if "[Insufficient Permissions]" in nome:
            nome = "(permessi insufficienti)"
        else:
            nome = os.path.basename(nome)
        try:
            mib = _numero_mib(parti[2])
        except ValueError:
            mib = None  # [N/A]: il driver non espone la memoria per processo
        voci.append({"nome": nome, "pid": pid, "mib": mib})
    return sorted(voci, key=lambda v: (v["mib"] is None, -(v["mib"] or 0)))


def top_ram(n=10):
    """Principali consumatori di RAM: [{nome, pid, mib}] (PowerShell,
    WorkingSet64). Mai eccezioni: [] se non determinabile (B2g)."""
    try:
        n = max(1, min(int(n), 50))
    except (TypeError, ValueError):
        n = 10
    try:
        testo = _esegui_comando([
            "powershell", "-NoProfile", "-Command",
            f"Get-Process | Sort-Object -Property WorkingSet64 -Descending | "
            f"Select-Object -First {n} | ForEach-Object {{ "
            f"\"$($_.Id)|$($_.ProcessName)|$([math]::Round($_.WorkingSet64/1MB,1))\" }}"])
    except ErroreProfiler:
        return []
    voci = []
    for riga in testo.splitlines():
        parti = riga.strip().split("|")
        if len(parti) != 3:
            continue
        try:
            voci.append({"nome": parti[1], "pid": int(parti[0]),
                         "mib": int(float(parti[2]))})
        except ValueError:
            continue
    return voci


def rileva(percorso_modelli=None):
    """Profilo hardware della macchina (solo lettura). Mai eccezioni: i dati
    mancanti restano None e il motivo finisce in `Profilo.avvisi`.
    `percorso_modelli`: cartella per la misura del disco libero
    (default: %APPDATA%\\TRILogos\\modelli, decisione B2)."""
    profilo = Profilo()
    try:
        profilo.gpu_nome, profilo.vram_totale_mib, profilo.vram_libera_mib = _rileva_gpu()
    except ErroreProfiler as errore:
        profilo.avvisi.append(f"GPU/VRAM non rilevate: {errore}")
    try:
        profilo.ram_totale_gb, profilo.ram_libera_gb = _rileva_ram()
    except ErroreProfiler as errore:
        profilo.avvisi.append(f"RAM non rilevata: {errore}")
    profilo.cpu_core, profilo.cpu_thread = _rileva_cpu()
    if profilo.cpu_core is None:
        profilo.avvisi.append("core fisici non rilevati: psutil assente e PowerShell non ha risposto")
    if profilo.cpu_thread is None:
        profilo.avvisi.append("thread CPU non rilevati: os.cpu_count() ha restituito None")
    cartella = percorso_modelli or CARTELLA_MODELLI_DEFAULT
    try:
        profilo.disco_libero_gb, profilo.disco_percorso = _rileva_disco(cartella)
    except ErroreProfiler as errore:
        profilo.avvisi.append(f"disco non rilevato: {errore}")
    return profilo
