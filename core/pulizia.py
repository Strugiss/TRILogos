# TRILogos — Modalità pulita "🧹 Pulisci hardware" (B2g)
"""Proposta + misura, MAI chiusura automatica (DESIGN_ARCA §2b, decisione D7).

- `analizza()`: processi che occupano VRAM (nvidia-smi compute-apps) e i
  principali consumatori di RAM (PowerShell), con il guadagno stimato;
- `chiudi(pid_list)`: `terminate()` gentile sui SOLI PID selezionati e
  confermati dall'utente; attesa e verifica; se un processo non termina entro
  il timeout si segnala, senza mai forzare (niente kill se evitabile);
- whitelist di sistema (Esplora risorse, desktop, servizi Windows, sicurezza/
  antivirus) e blacklist (processo corrente, TRILogos/python): mai chiudibili;
- log in italiano su `%APPDATA%\\TRILogos\\log\\pulizia.log` (solo PID/nome/
  esito: nessun dato utente).

Nota WDDM: su questa GPU `nvidia-smi --query-compute-apps` non espone la
memoria per processo ([N/A]); in quel caso `mib` resta None e il guadagno
stimato conta solo i valori noti — il guadagno REALE è misurato dal Profiler
(VRAM libera PRIMA/DOPO).
"""
import os
import subprocess
import time
from datetime import datetime

from . import profiler

try:
    import psutil  # opzionale: terminate() gentile, come in ARCA
except ImportError:
    psutil = None

ATTESA_CHIUSURA_S = 5.0
PASSO_POLL_S = 0.25
LOG_PULIZIA = os.path.join(
    os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"),
                                              "AppData", "Roaming"),
    "TRILogos", "log", "pulizia.log")

# Whitelist di sistema: MAI chiudibili (Esplora risorse, desktop, servizi, sicurezza)
PROTETTI_SISTEMA = {
    "system", "registry", "memory compression", "secure system",
    "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe", "services.exe",
    "lsass.exe", "svchost.exe", "dwm.exe", "explorer.exe", "sihost.exe",
    "fontdrvhost.exe", "audiodg.exe", "spoolsv.exe", "taskhostw.exe",
    "startmenuexperiencehost.exe", "shellexperiencehost.exe", "searchhost.exe",
    "textinputhost.exe", "runtimebroker.exe", "ctfmon.exe", "systemsettings.exe",
    "applicationframehost.exe", "shellhost.exe", "widgetboard.exe",
    "securityhealthservice.exe", "securityhealthsystray.exe", "msmpeng.exe",
    "nissrv.exe", "mpcmdrun.exe", "windefend.exe",
    "nvcontainer.exe", "nvdisplay.container.exe", "nvidia-smi.exe",
}
PROTETTI_ANTIVIRUS = ("avast", "avg", "eset", "kaspersky", "mcafee", "norton",
                      "bitdefender", "sophos", "trend micro", "malwarebytes",
                      "defender", "windows security")
# Blacklist: processo corrente, TRILogos e qualunque python (mai chiudibili)
PROTETTI_PROCESSO = {"python.exe", "pythonw.exe", "py.exe", "pyw.exe"}


def _protetto(pid, nome):
    """(protetto, motivo): whitelist sistema + antivirus + processo corrente."""
    nome_b = (nome or "").lower()
    try:
        if int(pid) == os.getpid():
            return True, "processo corrente (TRILogos)"
    except (TypeError, ValueError):
        return True, "PID non valido"
    if nome_b in PROTETTI_PROCESSO:
        return True, "python/TRILogos: mai chiudibile"
    if nome_b in PROTETTI_SISTEMA:
        return True, "processo di sistema"
    if any(prefisso in nome_b for prefisso in PROTETTI_ANTIVIRUS):
        return True, "sicurezza/antivirus"
    return False, ""


def analizza():
    """{processi: [{pid, nome, vram_mib, ram_mib, guadagno_mib, protetto,
    motivo}], guadagno_stimato_mib}. Mai eccezioni: liste vuote se i dati
    non sono rilevabili."""
    voci = {}
    for voce_vram in profiler.vram_occupata():
        voce = voci.setdefault(voce_vram["pid"], {
            "pid": voce_vram["pid"], "nome": voce_vram["nome"],
            "vram_mib": None, "ram_mib": None})
        if voce_vram["mib"] is not None:
            voce["vram_mib"] = (voce["vram_mib"] or 0) + voce_vram["mib"]
    for voce_ram in profiler.top_ram(15):
        voce = voci.setdefault(voce_ram["pid"], {
            "pid": voce_ram["pid"], "nome": voce_ram["nome"],
            "vram_mib": None, "ram_mib": None})
        if voce["ram_mib"] is None or voce_ram["mib"] > voce["ram_mib"]:
            voce["ram_mib"] = voce_ram["mib"]
    processi = []
    for voce in voci.values():
        protetto, motivo = _protetto(voce["pid"], voce["nome"])
        voce["protetto"] = protetto
        voce["motivo"] = motivo
        voce["guadagno_mib"] = (voce["vram_mib"] or 0) + (voce["ram_mib"] or 0)
        processi.append(voce)
    processi.sort(key=lambda v: (v["protetto"], -v["guadagno_mib"]))
    guadagno = sum(v["guadagno_mib"] for v in processi if not v["protetto"])
    return {"processi": processi, "guadagno_stimato_mib": guadagno}


def _nome_processo(pid):
    """Nome del processo per PID (tasklist). '?' se non determinabile."""
    try:
        esito = subprocess.run(
            ["tasklist", "/FI", f"PID eq {int(pid)}", "/NH", "/FO", "CSV"],
            capture_output=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        testo = (esito.stdout or b"").decode(errors="replace")
        for riga in testo.splitlines():
            parti = [p.strip('"') for p in riga.split('","')]
            if len(parti) >= 1 and parti[0] and not parti[0].startswith("INFO"):
                return parti[0]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "?"


def _vivo(pid):
    """True se il processo esiste ancora."""
    try:
        esito = subprocess.run(
            ["tasklist", "/FI", f"PID eq {int(pid)}", "/NH"],
            capture_output=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        testo = (esito.stdout or b"").decode(errors="replace")
        return str(int(pid)) in testo
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return True  # nel dubbio: non dichiarare chiuso


def _termina_gentile(pid):
    """Chiusura gentile: psutil.terminate() se disponibile, altrimenti
    taskkill SENZA /F (richiesta di chiusura, mai kill forzato)."""
    if psutil is not None:
        try:
            psutil.Process(int(pid)).terminate()
            return
        except Exception:
            pass
    try:
        subprocess.run(["taskkill", "/PID", str(int(pid))],
                       capture_output=True, timeout=15,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _attendi_chiusura(pid, timeout):
    scadenza = time.time() + timeout
    while time.time() < scadenza:
        if not _vivo(pid):
            return True
        time.sleep(PASSO_POLL_S)
    return not _vivo(pid)


def _log(esiti):
    """Log in italiano (solo PID/nome/esito). Mai eccezioni."""
    try:
        os.makedirs(os.path.dirname(LOG_PULIZIA), exist_ok=True)
        with open(LOG_PULIZIA, "a", encoding="utf-8") as f:
            for e in esiti:
                f.write(f"{datetime.now().isoformat(timespec='seconds')} | "
                        f"pid {e['pid']} | {e.get('nome', '?')} | {e['esito']}"
                        f"{(' | ' + e['motivo']) if e.get('motivo') else ''}\n")
    except OSError:
        pass


def chiudi(pid_list):
    """Chiude i SOLI PID indicati (già selezionati e confermati dall'utente).
    Ritorna [{pid, nome, esito, motivo?}]: esito in chiuso / non termina /
    protetto / non trovato. Mai kill forzato."""
    esiti = []
    for pid in pid_list:
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            continue
        nome = _nome_processo(pid)
        protetto, motivo = _protetto(pid, nome)
        if protetto:
            esiti.append({"pid": pid, "nome": nome, "esito": "protetto",
                          "motivo": motivo})
            continue
        if not _vivo(pid):
            esiti.append({"pid": pid, "nome": nome, "esito": "non trovato"})
            continue
        _termina_gentile(pid)
        if _attendi_chiusura(pid, ATTESA_CHIUSURA_S):
            esiti.append({"pid": pid, "nome": nome, "esito": "chiuso"})
        else:
            esiti.append({"pid": pid, "nome": nome, "esito": "non termina",
                          "motivo": f"non risponde entro {ATTESA_CHIUSURA_S:.0f}s: "
                                    "nessun kill forzato"})
    _log(esiti)
    return esiti
