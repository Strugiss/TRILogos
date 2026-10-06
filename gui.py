# TRILogos — GUI TRIVOICE (barra supervisore + LLM1/LLM2/LLM3), profilo LabGUI
"""Flusso automatico (6 passi): domanda → Invio → A formula e B risponde →
dibattito → sintesi e spartizione → risposta univoca consensuale →
cross-check automatico (verificatore bambino) con verdetto finale.
Layout TRIVOICE: barra SUPERVISORE (84px) + riga 4 riquadri (420px:
pulsanti 200 + LLM1/LLM2/LLM3 325×3) + risposta univoca (284px).
Selettore lingua (7 lingue) per interfaccia e risposte dei modelli."""
import sys, os, json, threading, queue, traceback, time, socket, webbrowser
from urllib.parse import urlparse
import tkinter as tk
from tkinter import ttk
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".opencode", "shared", "LabGUI"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "LabGUI"))
def _carica_env():
    """Carica TRILogos/.env (formato KEY=VALUE, commenti #) in os.environ se non gia' presenti.
    MAI salva chiavi: legge e basta. Serve per attivare i client cloud (BYOK)."""
    import os as _os
    percorso = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".env")
    try:
        with open(percorso, encoding="utf-8") as f:
            for riga in f:
                riga = riga.strip()
                if not riga or riga.startswith("#") or "=" not in riga:
                    continue
                chiave, _, valore = riga.partition("=")
                chiave = chiave.strip()
                if chiave and chiave not in _os.environ:
                    _os.environ[chiave] = valore.strip()
    except Exception:
        pass


_carica_env()


def _errore_import(e):
    r = tk.Tk()
    r.withdraw()
    from tkinter import messagebox
    messagebox.showerror("TRILogos — errore di avvio", str(e))
    sys.exit(1)

from labgui import (Finestra, Colonna, PALETTE, FONT_B, FONT_H, RiquadroRotondo,
                    ComboRotonda, BoxArrotondato, Pill, Tooltip)
from rounded import PulsanteRotondo
try:
    from core.clienti import (rileva_clienti, clienti_base, voci_modelli, aggiunti, salva_aggiunti,
                              aggiungi_cliente, rimuovi_cliente, stato_locale,
                              stato_opencode, trova_client, LOCALI as LOCALI_INFO)
    from core.timeline import aggiungi_sessione
    from core.canale import Canale
    from core import stato as _stato
    from core import perimetro
    from core.modelli import crea_modello, modello_da_voce as _modello_da_voce_core, TIMEOUT_RETE
    from core import motore as _motore
    from core import downloader as _downloader
    from core import profiler as _profiler
    from core import pulizia as _pulizia
    from core.metro import MisuratoreTok
except ImportError as e:
    _errore_import(e)


# ---- etichetta lentezza modelli locali (menu + avvisi: unica fonte di verità) ----
# Suffisso tradotto nelle 7 lingue: il menu mostra l'etichetta nella lingua attiva.
_SUFFISSI_LENTO = {
    "it": " (lento)", "en": " (slow)", "fr": " (lent)", "es": " (lento)",
    "de": " (langsam)", "pt": " (lento)", "zh": " (慢)",
}


def _modello_lento(nome):
    """Regola di lentezza dei modelli locali (Ollama) su CPU, usata sia per
    l'etichetta del menu sia per l'avviso alla partenza del flusso.

    Un modello è LENTO quando il suo nome (es. 'deepseek-r1:14b',
    'llama3.2:70b') contiene un indicatore di peso: la famiglia 'deepseek'
    (reasoning pesante), la variante 'r1', oppure la dimensione in miliardi
    di parametri '14b'/'32b'/'70b' — proxy documentato della dimensione reale
    >= 6GB (non interrogabile offline via API Ollama). I modelli piccoli
    (es. 'qwen2.5:3b', 'llama3.2:3b') non contengono indicatori: non lenti.
    MAI passare la voce del menu ('… (lento) · ollama'): qui arriva il NOME."""
    nome = (nome or "").lower()
    indicatori = ("deepseek", "r1", "14b", "32b", "70b")
    return any(i in nome for i in indicatori)


def _modello_grande(nome):
    """V6 (warmup): modello 'grande' (pesi >= 14B) per la regola ARCA 'un solo
    grande alla volta': indicatori 14b/32b/70b nel nome. MAI passare la voce
    del menu ('… (lento) · ollama'): qui arriva il NOME del modello."""
    nome = (nome or "").lower()
    return any(i in nome for i in ("14b", "32b", "70b"))


def _spoglia_suffisso(nome):
    """Rimuove dalla CODA del nome qualsiasi suffisso di lentezza noto (7 lingue):
    l'etichetta può essere rimasta in una lingua diversa da quella attiva."""
    for suff in _SUFFISSI_LENTO.values():
        if nome.endswith(suff):
            return nome[: -len(suff)]
    return nome


def _opzioni_etichettate(voci, lingua="it"):
    """Aggiunge il suffisso di lentezza NELLA LINGUA ATTIVA alle voci Ollama
    pesanti (regola _modello_lento): 'deepseek-r1:14b · ollama' ->
    'deepseek-r1:14b (slow) · ollama' con lingua 'en'. I modelli piccoli e i
    client NON-Ollama restano invariati. Il parser (modello_da_voce qui sotto)
    rimuove qualsiasi suffisso noto prima di costruire il modello: selezione e
    ricostruzione del canale funzionano in ogni lingua."""
    suffisso = _SUFFISSI_LENTO.get(lingua, _SUFFISSI_LENTO["it"])
    etichettate = []
    for v in voci:
        if v.endswith(" · ollama"):
            nome = v[: -len(" · ollama")]
            if _modello_lento(nome):
                v = nome + suffisso + " · ollama"
        etichettate.append(v)
    return etichettate


def modello_da_voce(voce, clienti=None, timeout=None, keep_alive=None, num_ctx=None):
    """Wrapper di core.modelli.modello_da_voce: rimuove dalla coda del NOME
    qualsiasi etichetta di lentezza nota (7 lingue) prima del parsing, così
    'deepseek-r1:14b (slow) · ollama' costruisce ModelloOllama con modello
    'deepseek-r1:14b'. La voce senza etichetta passa invariata.
    B2e: le voci del motore interno ('Nome (motore)', 7 lingue) costruiscono
    l'adapter ModelloMotore (llama-server) invece dei client esterni.
    `timeout`: tupla (connect, read) per i modelli di rete (None -> default core).
    `keep_alive` (V3) e `num_ctx` (fix critico): solo per Ollama."""
    if voce and _motore.e_voce_motore(voce):
        percorso = _motore.percorso_da_voce(voce)
        if not percorso:
            raise ValueError(f"modello del motore interno non trovato: {voce}")
        return _motore.crea_modello(percorso)
    if voce and " · " in voce:
        nome, client = voce.rsplit(" · ", 1)
        voce = _spoglia_suffisso(nome) + " · " + client
    elif voce:
        voce = _spoglia_suffisso(voce)
    return _modello_da_voce_core(voce, clienti, timeout=timeout,
                                 keep_alive=keep_alive, num_ctx=num_ctx)

VERSIONE = "3.1.0"

def _supporta(fn, nome_param):
    """True se la funzione/metodo accetta il parametro (API Canale estesa, fase 2)."""
    import inspect
    try:
        return nome_param in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


SUPPORTA_C = _supporta(Canale.__init__, "c") or _supporta(Canale.__init__, "modello_c")
SUPPORTA_SOGLIE = _supporta(Canale.__init__, "soglie")
_PARAM_C = "modello_c" if _supporta(Canale.__init__, "modello_c") else "c"


def _discendenti(widget):
    """Tutti i widget discendenti (ricorsivo), per il binding della rotella."""
    risultato = []
    for figlio in widget.winfo_children():
        risultato.append(figlio)
        risultato.extend(_discendenti(figlio))
    return risultato

LINGUE = ["Italiano", "English", "Français", "Español", "Deutsch", "Português", "中文"]
_MAPPA_LINGUE = dict(zip(LINGUE, ["it", "en", "fr", "es", "de", "pt", "zh"]))

BASE = os.path.dirname(os.path.abspath(__file__))


def _avviso_avvio(messaggio):
    """Avviso all'avvio (config/profili illeggibili) con messagebox: root
    temporanea nascosta, distrutta subito. L'avvio NON si blocca e NON crasha."""
    try:
        r = tk.Tk()
        r.withdraw()
        from tkinter import messagebox
        messagebox.showwarning("TRILogos — avviso di avvio", messaggio, parent=r)
        r.destroy()
    except Exception:
        pass


def _config_predefinita():
    """Valori predefiniti con le STESSE chiavi del config.json distribuito
    (profili/modelli/canale/rete): usati SOLO se il file manca o è corrotto."""
    return {
        "profili": {
            "Generico": {
                "A": "Sei l'agente A: analista rigoroso, chiaro e strutturato. Ricevi la domanda del supervisore, la analizzi e la formuli per il collega B.",
                "B": "Sei l'agente B: revisore critico e propositivo. Ricevi la richiesta formulata da A, la analizzi, obietti con rigore e collabori alla spartizione dei lavori.",
            }
        },
        "modelli": {"A": {"tipo": "mock", "modello": None},
                    "B": {"tipo": "mock", "modello": None}},
        "canale": {"max_turni_dibattito": 3, "soglia_convergenza": 0.9,
                   "max_chiamate": 60,
                   "soglie": {"A": 0.2, "B": 0.5, "C": 0.87}},
        "rete": {"timeout_connect": 10, "timeout_read": 120},
    }


def _carica_json(percorso):
    """Legge un file JSON: il dict letto, oppure None se manca/corrotto/non dict."""
    try:
        with open(percorso, encoding="utf-8") as f:
            dati = json.load(f)
        return dati if isinstance(dati, dict) else None
    except Exception:
        return None


CONFIG = _carica_json(os.path.join(BASE, "config.json"))
if CONFIG is None:
    CONFIG = _config_predefinita()
    _avviso_avvio("config.json non leggibile: uso i valori predefiniti. Controlla il file.")
# Profili locali (non distribuiti): nome nuovo preferito, fallback legacy
# profili_n47lab.json con avviso di deprecazione (A10b). Ordine: root poi dev/.
_AVVISO_PROFILI_LEGACY = ""
_PROFILI_CANDIDATI = (
    os.path.join(BASE, "profili_locali.json"),
    os.path.join(BASE, "dev", "profili_locali.json"),
    os.path.join(BASE, "profili_n47lab.json"),
    os.path.join(BASE, "dev", "profili_n47lab.json"),
)
for _cand in _PROFILI_CANDIDATI:
    if not os.path.exists(_cand):
        continue
    _locali = _carica_json(_cand)
    if _locali is None:
        _avviso_avvio(f"{os.path.basename(_cand)} non leggibile: uso solo i profili predefiniti. Controlla il file.")
    elif _locali:
        CONFIG.setdefault("profili", {}).update(_locali)
    if os.path.basename(_cand) == "profili_n47lab.json":
        _AVVISO_PROFILI_LEGACY = ("profili locali: rinomina profili_n47lab.json in profili_locali.json "
                                  "(il vecchio nome sarà rimosso)")
    break

# ---- SPLASH BYOK (primo avvio): clienti locali live + chiavi cloud nel .env ----
CLIENTI_LOCALI = [
    ("Ollama", 11434, "avvia Ollama e scegli un modello"),
    ("LM Studio", 1234, "avvia LM Studio e attiva il server API (porta 1234)"),
    ("Jan", 1337, "installa Jan (jan.ai) e avvia il server (porta 1337)"),
]
CLIENTI_CLOUD = [
    ("OpenAI", "OPENAI_API_KEY", "https://api.openai.com/v1", "https://platform.openai.com/api-keys"),
    ("Anthropic", "ANTHROPIC_API_KEY", "https://api.anthropic.com/v1", "https://console.anthropic.com"),
]
# nomi di default che NON possono diventare client personalizzati (niente doppioni)
NOMI_DEFAULT = {"ollama", "lmstudio", "jan", "openai", "anthropic", "opencode"}
NOMI_ENV = {nome: env for nome, env, _, _ in CLIENTI_CLOUD}


def _server_attivo(porta, timeout=1.0):
    """True se un server risponde sulla porta locale (come Test-NetConnection)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect(("127.0.0.1", porta))
            return True
        except OSError:
            return False


def _scrivi_chiave_env(percorso_env, nome_chiave, valore):
    """Scrive/aggiorna UNA chiave KEY=VALUE nel file .env senza toccare le altre
    (righe commentate e altre variabili restano intatte). Crea il file se manca."""
    righe = []
    if os.path.exists(percorso_env):
        # utf-8-sig: un eventuale BOM UTF-8 iniziale viene rimosso in lettura,
        # così la prima riga matcha e la chiave NON viene duplicata.
        with open(percorso_env, encoding="utf-8-sig") as f:
            righe = f.read().splitlines()
    trovata = False
    for i, riga in enumerate(righe):
        if not riga.strip() or riga.strip().startswith("#"):
            continue
        if riga.partition("=")[0].strip() == nome_chiave:
            righe[i] = f"{nome_chiave}={valore}"
            trovata = True
            break
    if not trovata:
        righe.append(f"{nome_chiave}={valore}")
    with open(percorso_env, "w", encoding="utf-8") as f:
        f.write("\n".join(righe) + "\n")
    return True


def _rimuovi_chiave_env(percorso_env, nome_chiave):
    """Rimuove UNA riga KEY=VALUE dal file .env senza toccare le altre
    (commenti e altre variabili restano intatti). False se la chiave non c'era."""
    if not os.path.exists(percorso_env):
        return False
    with open(percorso_env, encoding="utf-8-sig") as f:
        righe = f.read().splitlines()
    nuove = [r for r in righe
             if r.strip().startswith("#") or r.partition("=")[0].strip() != nome_chiave]
    if len(nuove) == len(righe):
        return False
    with open(percorso_env, "w", encoding="utf-8") as f:
        f.write("\n".join(nuove) + ("\n" if nuove else ""))
    return True


def _porta_base(base_url, default=1234):
    """Porta dalla base URL (es. http://localhost:1234/v1 -> 1234)."""
    try:
        p = urlparse(base_url or "")
        if p.port:
            return p.port
    except ValueError:
        pass
    return default


def _base_e_locale(base_url):
    """True se la base URL punta a un server locale (localhost/127.0.0.1/::1)."""
    try:
        p = urlparse(base_url or "")
    except ValueError:
        return False
    if not p.scheme:
        return False
    return p.hostname in ("localhost", "127.0.0.1", "::1")


def _salva_flag_byok():
    """Salva il flag byok_splash in stato.json (SOLO alla chiusura dello splash,
    se 'Non mostrare più' è spuntata). Il flag non è mai nel codice né nel
    config.json tracciato: vive in core/stato.py (file locale gitignored)."""
    _stato.imposta("byok_splash", True)


def _primo_flusso_ok():
    """True se il flag primo_flusso_ok è attivo in stato.json: la prima domanda
    è stata conclusa con un flusso completo. Rilettura da disco a ogni chiamata."""
    return bool(_stato.leggi().get("primo_flusso_ok"))


def _salva_flag_primo_flusso():
    """Scrive il flag primo_flusso_ok in stato.json SOLO se assente: marca la
    PRIMA conclusione di un flusso completo (nessun altro flag toccato)."""
    if _stato.leggi().get("primo_flusso_ok"):
        return
    _stato.imposta("primo_flusso_ok", True)

TESTI = {
    "it": {
        "titolo": "TRILogos — dialogo a tre voci (supervisore · LLM1 · LLM2 · LLM3)",
        "supervisore": "SUPERVISORE",
        "placeholder": "Scegli la cartella per il tuo progetto e scrivi qui il tuo prompt",
        "invia": "▶ Invia",
        "completo": "▶ Avvia (completo)",
        "dibattito": "💬 Dibattito",
        "sintesi": "📋 Sintesi",
        "univoca": "✍️ Univoca",
        "salva": "💾 Salva",
        "svuota": "🗑 Svuota",
        "interrompi": "⏹ Interrompi",
        "llm1": "LLM1",
        "llm2": "LLM2",
        "llm3": "LLM3",
        "finale": "RISPOSTA UNIVOCA",
        "descr_finale": "il verdetto del canale",
        "pronto": "pronto",
        "lavoro": "in elaborazione …",
        "chiedi_prima": "Scrivi prima una domanda nella barra in alto.",
        "formula": "… sta formulando la richiesta per LLM2 …",
        "pos_a": "[posizione finale]",
        "pos_b": "[posizione finale]",
        "rev_b": "[revisione di LLM2]",
        "sint_ok": "sintesi e risposta univoca …",
        "fine_ok": "risposta univoca condivisa pronta",
        "opzioni": "⚙ Opzioni",
        "cartella": "📁 Progetto",
        "add": "➕ ADD",
        "agenti": "🔎 Agenti",
        "cross": "🛡 Cross-check",
        "correggi": "✏️ Correggi",
        # F4-E: cronometro, header e tooltip localizzati (7 lingue)
        "crono_attesa": "in attesa",
        "crono_passo": "passo",
        "crono_totale": "totale",
        "tt_lingua": "Lingua dell'interfaccia e delle risposte dei modelli",
        "tt_profilo": "Profilo attivo: {v}",
        "tt_modello": "Modello di {n}: {v}\nI modelli '(lento)' su CPU possono richiedere 2-5 minuti per risposta",
        "tt_progetto": "Cartella progetto: {p}",
        "tt_progetto_non": "Cartella progetto: (non scelta)",
        "tt_invia": "Invia la domanda al canale",
        "tt_completo": "Esegue il flusso completo a 6 passi",
        "tt_dibattito": "Esegue solo il dibattito tra le voci",
        "tt_sintesi": "Esegue sintesi, spartizione e risposta univoca",
        "tt_univoca": "Esegue solo la risposta univoca",
        "tt_cross": "Esegue il cross-check del verificatore",
        "tt_correggi": "Corregge la risposta seguendo i punti del verificatore (max 3 giri)",
        "tt_salva": "Salva la sessione in JSON e Markdown",
        "tt_svuota": "Svuota i riquadri e riazzera il canale",
        "tt_cartella": "Sceglie la cartella progetto e carica i file supportati (max 40)",
        "tt_add": "Aggiunge documenti o immagini come allegati",
        "tt_opzioni": "Gestione clienti e modelli",
        "tt_agenti": "Squadra di ricerca: agenti, confidenza e log (profilo Ricerca)",
    },
    "en": {
        "titolo": "TRILogos — three-voice dialogue (supervisor · LLM1 · LLM2 · LLM3)",
        "supervisore": "SUPERVISOR",
        "placeholder": "Choose the folder for your project and write your prompt here",
        "invia": "▶ Send",
        "completo": "▶ Run (full)",
        "dibattito": "💬 Debate",
        "sintesi": "📋 Summary",
        "univoca": "✍️ Unanimous",
        "salva": "💾 Save",
        "svuota": "🗑 Clear",
        "interrompi": "⏹ Stop",
        "llm1": "LLM1",
        "llm2": "LLM2",
        "llm3": "LLM3",
        "finale": "UNANIMOUS ANSWER",
        "descr_finale": "the channel's verdict",
        "pronto": "ready",
        "lavoro": "working …",
        "chiedi_prima": "Type a question in the bar first.",
        "formula": "… formulating the request for LLM2 …",
        "pos_a": "[final position]",
        "pos_b": "[final position]",
        "rev_b": "[LLM2 revision]",
        "sint_ok": "summary and unanimous answer …",
        "fine_ok": "unanimous shared answer ready",
        "opzioni": "⚙ Options",
        "cartella": "📁 Project",
        "add": "➕ ADD",
        "agenti": "🔎 Agents",
        "cross": "🛡 Cross-check",
        "correggi": "✏️ Fix",
        "crono_attesa": "waiting",
        "crono_passo": "step",
        "crono_totale": "total",
        "tt_lingua": "Language of the interface and model responses",
        "tt_profilo": "Active profile: {v}",
        "tt_modello": "Model for {n}: {v}\n'(slow)' models on CPU may take 2-5 minutes per answer",
        "tt_progetto": "Project folder: {p}",
        "tt_progetto_non": "Project folder: (not selected)",
        "tt_invia": "Sends the question to the channel",
        "tt_completo": "Runs the full 6-step flow",
        "tt_dibattito": "Runs only the debate between the voices",
        "tt_sintesi": "Runs summary, work split and unanimous answer",
        "tt_univoca": "Runs only the unanimous answer",
        "tt_cross": "Runs the verifier's cross-check",
        "tt_correggi": "Fixes the answer following the verifier's points (max 3 runs)",
        "tt_salva": "Saves the session as JSON and Markdown",
        "tt_svuota": "Clears the panels and resets the channel",
        "tt_cartella": "Chooses the project folder and loads supported files (max 40)",
        "tt_add": "Adds documents or images as attachments",
        "tt_agenti": "Research team: agents, confidence and log (Ricerca profile)",
        "tt_opzioni": "Manage clients and models",
    },
    "fr": {
        "titolo": "TRILogos — dialogue à trois voix (superviseur · LLM1 · LLM2 · LLM3)",
        "supervisore": "SUPERVISEUR",
        "placeholder": "Choisis le dossier de ton projet et écris ton prompt ici",
        "invia": "▶ Envoyer",
        "completo": "▶ Lancer (complet)",
        "dibattito": "💬 Débat",
        "sintesi": "📋 Synthèse",
        "univoca": "✍️ Unanime",
        "salva": "💾 Sauvegarder",
        "svuota": "🗑 Vider",
        "interrompi": "⏹ Interrompre",
        "llm1": "LLM1",
        "llm2": "LLM2",
        "llm3": "LLM3",
        "finale": "RÉPONSE UNANIME",
        "descr_finale": "le verdict du canal",
        "pronto": "prêt",
        "lavoro": "en cours …",
        "chiedi_prima": "Écrivez d'abord une question dans la barre.",
        "formula": "… formule la demande pour LLM2 …",
        "pos_a": "[position finale]",
        "pos_b": "[position finale]",
        "rev_b": "[révision de LLM2]",
        "sint_ok": "synthèse et réponse unanime …",
        "fine_ok": "réponse unanime partagée prête",
        "opzioni": "⚙ Options",
        "cartella": "📁 Projet",
        "add": "➕ AJOUTER",
        "cross": "🛡 Vérification",
        "correggi": "✏️ Corriger",
        "crono_attesa": "en attente",
        "crono_passo": "étape",
        "crono_totale": "total",
        "tt_lingua": "Langue de l'interface et des réponses des modèles",
        "tt_profilo": "Profil actif : {v}",
        "tt_modello": "Modèle de {n} : {v}\nLes modèles « (lent) » sur CPU peuvent demander 2-5 minutes par réponse",
        "tt_progetto": "Dossier du projet : {p}",
        "tt_progetto_non": "Dossier du projet : (non choisi)",
        "tt_invia": "Envoie la question au canal",
        "tt_completo": "Exécute le flux complet en 6 étapes",
        "tt_dibattito": "Exécute uniquement le débat entre les voix",
        "tt_sintesi": "Exécute synthèse, répartition et réponse unanime",
        "tt_univoca": "Exécute uniquement la réponse unanime",
        "tt_cross": "Exécute la vérification du vérificateur",
        "tt_correggi": "Corrige la réponse selon les points du vérificateur (max 3 tours)",
        "tt_salva": "Enregistre la session en JSON et Markdown",
        "tt_svuota": "Vide les panneaux et réinitialise le canal",
        "tt_cartella": "Choisit le dossier du projet et charge les fichiers pris en charge (max 40)",
        "tt_add": "Ajoute des documents ou images comme pièces jointes",
        "tt_opzioni": "Gestion des clients et des modèles",
    },
    "es": {
        "titolo": "TRILogos — diálogo a tres voces (supervisor · LLM1 · LLM2 · LLM3)",
        "supervisore": "SUPERVISOR",
        "placeholder": "Elige la carpeta para tu proyecto y escribe aquí tu prompt",
        "invia": "▶ Enviar",
        "completo": "▶ Ejecutar (completo)",
        "dibattito": "💬 Debate",
        "sintesi": "📋 Resumen",
        "univoca": "✍️ Unánime",
        "salva": "💾 Guardar",
        "svuota": "🗑 Vaciar",
        "interrompi": "⏹ Interrumpir",
        "llm1": "LLM1",
        "llm2": "LLM2",
        "llm3": "LLM3",
        "finale": "RESPUESTA UNÁNIME",
        "descr_finale": "el veredicto del canal",
        "pronto": "listo",
        "lavoro": "procesando …",
        "chiedi_prima": "Escribe primero una pregunta en la barra.",
        "formula": "… formula la solicitud para LLM2 …",
        "pos_a": "[posición final]",
        "pos_b": "[posición final]",
        "rev_b": "[revisión de LLM2]",
        "sint_ok": "resumen y respuesta unánime …",
        "fine_ok": "respuesta unánime compartida lista",
        "opzioni": "⚙ Opciones",
        "cartella": "📁 Proyecto",
        "add": "➕ AÑADIR",
        "cross": "🛡 Verificación",
        "correggi": "✏️ Corregir",
        "crono_attesa": "en espera",
        "crono_passo": "paso",
        "crono_totale": "total",
        "tt_lingua": "Idioma de la interfaz y de las respuestas de los modelos",
        "tt_profilo": "Perfil activo: {v}",
        "tt_modello": "Modelo de {n}: {v}\nLos modelos '(lento)' en CPU pueden tardar 2-5 minutos por respuesta",
        "tt_progetto": "Carpeta del proyecto: {p}",
        "tt_progetto_non": "Carpeta del proyecto: (no elegida)",
        "tt_invia": "Envía la pregunta al canal",
        "tt_completo": "Ejecuta el flujo completo de 6 pasos",
        "tt_dibattito": "Ejecuta solo el debate entre las voces",
        "tt_sintesi": "Ejecuta resumen, reparto y respuesta unánime",
        "tt_univoca": "Ejecuta solo la respuesta unánime",
        "tt_cross": "Ejecuta la verificación del verificador",
        "tt_correggi": "Corrige la respuesta siguiendo los puntos del verificador (máx. 3 rondas)",
        "tt_salva": "Guarda la sesión en JSON y Markdown",
        "tt_svuota": "Vacía los paneles y reinicia el canal",
        "tt_cartella": "Elige la carpeta del proyecto y carga los archivos admitidos (máx. 40)",
        "tt_add": "Añade documentos o imágenes como adjuntos",
        "tt_opzioni": "Gestión de clientes y modelos",
    },
    "de": {
        "titolo": "TRILogos — Dialog mit drei Stimmen (Betreuer · LLM1 · LLM2 · LLM3)",
        "supervisore": "SUPERVISOR",
        "placeholder": "Wähle den Ordner für dein Projekt und schreibe hier deinen Prompt",
        "invia": "▶ Senden",
        "completo": "▶ Komplett",
        "dibattito": "💬 Debatte",
        "sintesi": "📋 Kurzfassung",
        "univoca": "✍️ Einstimmig",
        "salva": "💾 Speichern",
        "svuota": "🗑 Leeren",
        "interrompi": "⏹ Stoppen",
        "llm1": "LLM1",
        "llm2": "LLM2",
        "llm3": "LLM3",
        "finale": "EINSTIMMIGE ANTWORT",
        "descr_finale": "das Urteil des Kanals",
        "pronto": "bereit",
        "lavoro": "arbeitet …",
        "chiedi_prima": "Schreiben Sie zuerst eine Frage in die Leiste.",
        "formula": "… formuliert die Anfrage für LLM2 …",
        "pos_a": "[Endposition]",
        "pos_b": "[Endposition]",
        "rev_b": "[LLM2-Überarbeitung]",
        "sint_ok": "Zusammenfassung und einstimmige Antwort …",
        "fine_ok": "gemeinsame einstimmige Antwort bereit",
        "opzioni": "⚙ Optionen",
        "cartella": "📁 Projekt",
        "add": "➕ HINZUFÜGEN",
        "cross": "🛡 Prüfung",
        "correggi": "✏️ Korrigieren",
        "crono_attesa": "in Wartestellung",
        "crono_passo": "Schritt",
        "crono_totale": "gesamt",
        "tt_lingua": "Sprache der Oberfläche und der Modellantworten",
        "tt_profilo": "Aktives Profil: {v}",
        "tt_modello": "Modell für {n}: {v}\n'(langsam)'-Modelle auf CPU können 2-5 Minuten pro Antwort brauchen",
        "tt_progetto": "Projektordner: {p}",
        "tt_progetto_non": "Projektordner: (nicht gewählt)",
        "tt_invia": "Sendet die Frage an den Kanal",
        "tt_completo": "Führt den kompletten 6-Schritte-Ablauf aus",
        "tt_dibattito": "Führt nur die Debatte zwischen den Stimmen aus",
        "tt_sintesi": "Führt Zusammenfassung, Aufteilung und einstimmige Antwort aus",
        "tt_univoca": "Führt nur die einstimmige Antwort aus",
        "tt_cross": "Führt den Cross-Check des Prüfers aus",
        "tt_correggi": "Korrigiert die Antwort nach den Punkten des Prüfers (max. 3 Runden)",
        "tt_salva": "Speichert die Sitzung als JSON und Markdown",
        "tt_svuota": "Leert die Felder und setzt den Kanal zurück",
        "tt_cartella": "Wählt den Projektordner und lädt unterstützte Dateien (max. 40)",
        "tt_add": "Fügt Dokumente oder Bilder als Anhänge hinzu",
        "tt_opzioni": "Verwaltung von Clients und Modellen",
    },
    "pt": {
        "titolo": "TRILogos — diálogo a três vozes (supervisor · LLM1 · LLM2 · LLM3)",
        "supervisore": "SUPERVISOR",
        "placeholder": "Escolhe a pasta para o teu projeto e escreve aqui o teu prompt",
        "invia": "▶ Enviar",
        "completo": "▶ Executar (completo)",
        "dibattito": "💬 Debate",
        "sintesi": "📋 Resumo",
        "univoca": "✍️ Unânime",
        "salva": "💾 Salvar",
        "svuota": "🗑 Limpar",
        "interrompi": "⏹ Interromper",
        "llm1": "LLM1",
        "llm2": "LLM2",
        "llm3": "LLM3",
        "finale": "RESPOSTA UNÂNIME",
        "descr_finale": "o veredito do canal",
        "pronto": "pronto",
        "lavoro": "processando …",
        "chiedi_prima": "Escreva primeiro uma pergunta na barra.",
        "formula": "… formula o pedido para LLM2 …",
        "pos_a": "[posição final]",
        "pos_b": "[posição final]",
        "rev_b": "[revisão do LLM2]",
        "sint_ok": "resumo e resposta unânime …",
        "fine_ok": "resposta unânime compartilhada pronta",
        "opzioni": "⚙ Opções",
        "cartella": "📁 Projeto",
        "add": "➕ ADICIONAR",
        "cross": "🛡 Verificação",
        "correggi": "✏️ Corrigir",
        "crono_attesa": "em espera",
        "crono_passo": "passo",
        "crono_totale": "total",
        "tt_lingua": "Idioma da interface e das respostas dos modelos",
        "tt_profilo": "Perfil ativo: {v}",
        "tt_modello": "Modelo de {n}: {v}\nModelos '(lento)' na CPU podem demorar 2-5 minutos por resposta",
        "tt_progetto": "Pasta do projeto: {p}",
        "tt_progetto_non": "Pasta do projeto: (não escolhida)",
        "tt_invia": "Envia a pergunta ao canal",
        "tt_completo": "Executa o fluxo completo de 6 passos",
        "tt_dibattito": "Executa apenas o debate entre as vozes",
        "tt_sintesi": "Executa resumo, divisão e resposta unânime",
        "tt_univoca": "Executa apenas a resposta unânime",
        "tt_cross": "Executa a verificação do verificador",
        "tt_correggi": "Corrige a resposta seguindo os pontos do verificador (máx. 3 rondas)",
        "tt_salva": "Salva a sessão em JSON e Markdown",
        "tt_svuota": "Limpa os painéis e reinicia o canal",
        "tt_cartella": "Escolhe a pasta do projeto e carrega os arquivos suportados (máx. 40)",
        "tt_add": "Adiciona documentos ou imagens como anexos",
        "tt_opzioni": "Gestão de clientes e modelos",
    },
    "zh": {
        "titolo": "TRILogos — 三方对话（主管 · LLM1 · LLM2 · LLM3）",
        "supervisore": "主管",
        "placeholder": "为你的项目选择文件夹，并在此处输入你的提示词",
        "invia": "▶ 发送",
        "completo": "▶ 运行（完整）",
        "dibattito": "💬 辩论",
        "sintesi": "📋 总结",
        "univoca": "✍️ 一致",
        "salva": "💾 保存",
        "svuota": "🗑 清空",
        "interrompi": "⏹ 中断",
        "llm1": "LLM1",
        "llm2": "LLM2",
        "llm3": "LLM3",
        "finale": "一致回答",
        "descr_finale": "频道的最终裁决",
        "pronto": "就绪",
        "lavoro": "处理中 …",
        "chiedi_prima": "请先在顶部输入问题。",
        "formula": "… 正在为 LLM2 拟定请求 …",
        "pos_a": "[最终立场]",
        "pos_b": "[最终立场]",
        "rev_b": "[LLM2 修订]",
        "sint_ok": "总结与一致回答 …",
        "fine_ok": "一致回答已就绪",
        "opzioni": "⚙ 选项",
        "cartella": "📁 项目",
        "add": "➕ 添加",
        "cross": "🛡 核查",
        "correggi": "✏️ 修正",
        "crono_attesa": "等待中",
        "crono_passo": "步骤",
        "crono_totale": "总计",
        "tt_lingua": "界面和模型回复的语言",
        "tt_profilo": "当前配置：{v}",
        "tt_modello": "{n} 的模型：{v}\nCPU 上的“(慢)”模型每次回复可能需要 2-5 分钟",
        "tt_progetto": "项目文件夹：{p}",
        "tt_progetto_non": "项目文件夹：（未选择）",
        "tt_invia": "将问题发送到频道",
        "tt_completo": "运行完整的 6 步流程",
        "tt_dibattito": "仅运行各方之间的辩论",
        "tt_sintesi": "运行总结、分工和一致回答",
        "tt_univoca": "仅运行一致回答",
        "tt_cross": "运行验证者的交叉检查",
        "tt_correggi": "根据验证者的要点修正回答（最多 3 轮）",
        "tt_salva": "将会话保存为 JSON 和 Markdown",
        "tt_svuota": "清空面板并重置频道",
        "tt_cartella": "选择项目文件夹并加载支持的文件（最多 40 个）",
        "tt_add": "添加文档或图片作为附件",
        "tt_opzioni": "管理客户端和模型",
    },
}

# B2e: stringhe del motore interno (IT/EN complete; le altre lingue -> EN).
_MOTORE_TESTI = {
    "it": {
        "motore_tag": "motore",
        "motore_titolo": "Primo avvio — Motore interno",
        "motore_hw": "Hardware rilevato",
        "motore_attesa": "Rilevamento hardware in corso…",
        "motore_proposti": "Modelli consigliati per il tuo hardware",
        "motore_licenza": "Licenza: {l}",
        "motore_scarica": "⬇ Scarica",
        "motore_riprendi": "⬇ Riprendi",
        "motore_annulla": "⏹ Annulla",
        "motore_scaricando": "Download in corso…",
        "motore_interrotto": "Download interrotto: riprenderà da qui",
        "motore_pronto": "Pronto: {n} modello/i nel menu dei modelli",
        "motore_piu_tardi": "Più tardi",
        "motore_apri": "🤖 Avvio guidato motore",
        "motore_stato": "⚙ motore: {n} · {lc}",
        "motore_ok": "llama.cpp ok",
        "motore_assente": "llama.cpp assente",
        "motore_errore": "Errore: {e}",
        "pul_pulsante": "🧹 Pulisci hardware",
        "pul_titolo": "Pulisci hardware — modalità pulita",
        "pul_spiega": "Processi che occupano VRAM/RAM. Seleziona e chiudi con "
                      "conferma: i dati non salvati andranno persi.",
        "pul_nd": "n/d",
        "pul_protetto": "protetto",
        "pul_guadagno": "Guadagno stimato: {mib} MiB",
        "pul_aggiorna": "🔄 Aggiorna",
        "pul_chiudi_sel": "🧹 Chiudi selezionati",
        "pul_annulla": "✖ Annulla",
        "pul_nessuno_sel": "Nessun processo selezionato",
        "pul_nessun_proc": "Nessun processo rilevato",
        "pul_conferma_titolo": "Conferma chiusura",
        "pul_conferma": "Chiudere {n} processi?\nI dati non salvati andranno "
                        "persi.\nL'operazione non è reversibile.",
        "pul_esito": "Chiusi: {n} · non terminano: {k} · protetti: {p}",
        "pul_guadagno_reale": "VRAM libera: {prima} → {dopo} MiB "
                              "(guadagno reale {delta} MiB)",
        "pul_pulsante_breve": "🧹 Pulisci HW",
        "cat_nome": "Nome", "cat_dim": "Dim.", "cat_fascia": "Fascia",
        "cat_input": "Input", "cat_output": "Output", "cat_licenza": "Licenza",
        "cat_scarica_sel": "⬇ Scarica selezionati",
        "cat_annulla_coda": "⏹ Annulla coda",
        "cat_installato": "installato ✓", "cat_in_uso": "in uso",
        "cat_nessuna_sel": "Nessun modello selezionato",
        "cat_coda": "Coda: {i}/{n} · {file}",
        "cat_consigliato": "consigliato",
    },
    "en": {
        "motore_tag": "engine",
        "motore_titolo": "First run — Internal engine",
        "motore_hw": "Detected hardware",
        "motore_attesa": "Detecting hardware…",
        "motore_proposti": "Recommended models for your hardware",
        "motore_licenza": "License: {l}",
        "motore_scarica": "⬇ Download",
        "motore_riprendi": "⬇ Resume",
        "motore_annulla": "⏹ Cancel",
        "motore_scaricando": "Downloading…",
        "motore_interrotto": "Download interrupted: it will resume from here",
        "motore_pronto": "Ready: {n} model(s) in the model menu",
        "motore_piu_tardi": "Later",
        "motore_apri": "🤖 Engine guided setup",
        "motore_stato": "⚙ engine: {n} · {lc}",
        "motore_ok": "llama.cpp ok",
        "motore_assente": "llama.cpp missing",
        "motore_errore": "Error: {e}",
        "pul_pulsante": "🧹 Clean hardware",
        "pul_titolo": "Clean hardware — clean mode",
        "pul_spiega": "Processes using VRAM/RAM. Select and close with "
                      "confirmation: unsaved data will be lost.",
        "pul_nd": "n/a",
        "pul_protetto": "protected",
        "pul_guadagno": "Estimated gain: {mib} MiB",
        "pul_aggiorna": "🔄 Refresh",
        "pul_chiudi_sel": "🧹 Close selected",
        "pul_annulla": "✖ Cancel",
        "pul_nessuno_sel": "No process selected",
        "pul_nessun_proc": "No process detected",
        "pul_conferma_titolo": "Confirm close",
        "pul_conferma": "Close {n} processes?\nUnsaved data will be lost.\n"
                        "This operation cannot be undone.",
        "pul_esito": "Closed: {n} · not terminating: {k} · protected: {p}",
        "pul_guadagno_reale": "Free VRAM: {prima} → {dopo} MiB "
                              "(real gain {delta} MiB)",
        "pul_pulsante_breve": "🧹 Clean HW",
        "cat_nome": "Name", "cat_dim": "Size", "cat_fascia": "Tier",
        "cat_input": "Input", "cat_output": "Output", "cat_licenza": "License",
        "cat_scarica_sel": "⬇ Download selected",
        "cat_annulla_coda": "⏹ Cancel queue",
        "cat_installato": "installed ✓", "cat_in_uso": "in use",
        "cat_nessuna_sel": "No model selected",
        "cat_coda": "Queue: {i}/{n} · {file}",
        "cat_consigliato": "recommended",
    },
}
for _lingua_testi in TESTI:
    TESTI[_lingua_testi].update(_MOTORE_TESTI.get(_lingua_testi, _MOTORE_TESTI["en"]))


def _timeout_rete():
    """Timeout di rete (connect, read) da config.json → rete, validati: due
    interi > 0. Ritorna (tupla, avviso|None): se la sezione è presente ma non
    valida, usa i default TIMEOUT_RETE (10, 120) e restituisce il messaggio di
    avviso da mostrare nello stato. Il core non legge mai la config: i valori
    arrivano ai modelli solo per parametro esplicito."""
    rete = CONFIG.get("rete")
    if rete is None:
        return TIMEOUT_RETE, None
    try:
        c, r = int(rete.get("timeout_connect")), int(rete.get("timeout_read"))
        if c > 0 and r > 0:
            return (c, r), None
    except (TypeError, ValueError, AttributeError):
        pass
    return TIMEOUT_RETE, "config.json → rete non valida: uso i timeout predefiniti (10, 120)"


def _autore_timeline():
    """Author per la timeline da config.json → timeline.author (dict) o None:
    il core applica il default neutro AUTORE_NEUTRO (A10a). Mai dati personali
    hardcoded: chi vuole firma la timeline nel proprio config."""
    autore = (CONFIG.get("timeline") or {}).get("author")
    return autore if isinstance(autore, dict) else None


def _keep_alive_ollama():
    """V3: keep_alive per Ollama da config.json → ollama.keep_alive (default -1)."""
    valore = (CONFIG.get("ollama") or {}).get("keep_alive", -1)
    return valore if valore is not None else -1


def _num_ctx_ollama():
    """FIX CRITICO: contesto per Ollama da config.json → ollama.num_ctx
    (default 8192; il default del modello R1 è 131072 -> 35 GB e thrashing)."""
    try:
        valore = int((CONFIG.get("ollama") or {}).get("num_ctx", 8192))
    except (TypeError, ValueError):
        valore = 8192
    return valore if valore > 0 else 8192


def _kw_modello(cfg, timeout, keep_alive):
    """Kwargs per crea_modello da config: `keep_alive` e `num_ctx` solo per
    Ollama (gli altri adapter non li accettano). `num_ctx` per-voce
    (modelli.<A|B|C>.num_ctx) se presente, altrimenti il globale."""
    kw = dict(modello=cfg.get("modello"), timeout=timeout)
    if cfg.get("tipo") == "ollama":
        kw["keep_alive"] = keep_alive
        try:
            num_ctx = int(cfg.get("num_ctx")) if cfg.get("num_ctx") is not None else None
        except (TypeError, ValueError):
            num_ctx = None
        kw["num_ctx"] = num_ctx if num_ctx and num_ctx > 0 else _num_ctx_ollama()
    return kw


def costruisci_canale(lingua="it", profilo=None, voce_c=None, clienti=None, timeout=None):
    """Canale completo: A e B da config; la terza voce C dalla combo di c_c
    (voce_c + modello_da_voce) se l'API del Canale la supporta; soglie da
    config.json (canale.soglie) se presenti. Fase intermedia (canale senza C):
    comportamento invariato a due voci. `timeout`: (connect, read) per i modelli
    di rete; None -> letto/validato da config.json → rete (helper _timeout_rete).
    V1/V2/V3: dibattito parallelo, limiti token e keep_alive da config.json."""
    m = CONFIG["modelli"]
    timeout = timeout or _timeout_rete()[0]
    keep_alive = _keep_alive_ollama()
    num_ctx = _num_ctx_ollama()
    a = crea_modello(m["A"]["tipo"], **_kw_modello(m["A"], timeout, keep_alive))
    b = crea_modello(m["B"]["tipo"], **_kw_modello(m["B"], timeout, keep_alive))
    profilo = profilo or next(iter(CONFIG["profili"]))
    ruoli = CONFIG["profili"].get(profilo) or next(iter(CONFIG["profili"].values()))
    kwargs = dict(ruolo_a=ruoli["A"], ruolo_b=ruoli["B"],
                  max_turni_dibattito=CONFIG["canale"]["max_turni_dibattito"],
                  soglia_convergenza=CONFIG["canale"]["soglia_convergenza"],
                  lingua=lingua, max_chiamate=CONFIG["canale"].get("max_chiamate", 40),
                  stile=ruoli.get("stile") or "",
                  formato_risposta=ruoli.get("formato_risposta") or "semplice",
                  dibattito_parallelo=CONFIG["canale"].get("dibattito_parallelo", True),
                  limiti_token=CONFIG["canale"].get("limiti_token"))
    if SUPPORTA_C:
        if voce_c:
            c = modello_da_voce(voce_c, clienti, timeout=timeout,
                                keep_alive=keep_alive, num_ctx=num_ctx)
        elif "C" in m:
            c = crea_modello(m["C"]["tipo"], **_kw_modello(m["C"], timeout, keep_alive))
        else:
            c = None
        kwargs[_PARAM_C] = c
        if "C" in ruoli and _supporta(Canale.__init__, "ruolo_c"):
            kwargs["ruolo_c"] = ruoli["C"]
    if CONFIG["canale"].get("soglie") and SUPPORTA_SOGLIE:
        kwargs["soglie"] = CONFIG["canale"]["soglie"]
    return Canale(a, b, **kwargs)


class _RiquadroFinale:
    """Zona C (risposta univoca): header colorato + box, con request compatto
    (il box è a 4 righe richieste: il pannello 284px lo espande a tutto il resto)."""
    def __init__(self, master, polo, colore, descrizione):
        header = tk.Frame(master, bg=PALETTE["pannello"])
        header.pack(fill="x", padx=1, pady=(1, 0))
        self.polo = Pill(header, testo=f"  {polo}  ", colore=colore)
        self.polo.pack(side="left")
        self.lbl_modello = tk.Label(header, text=descrizione, bg=PALETTE["pannello"],
                                    fg=PALETTE["secondario"], font=("Segoe UI", 9))
        self.lbl_modello.pack(side="left", padx=8)
        self.boxwrap = BoxArrotondato(master, altezza_righe=4)
        self.box = self.boxwrap.box
        self.boxwrap.pack(fill="both", expand=True, padx=1, pady=(0, 1))

    def descrizione(self, testo):
        self.lbl_modello.configure(text=testo)

    def scrivi(self, testo):
        self.box.insert("end", testo + "\n\n")
        self.box.see("end")
        self._evidenzia_etichette()

    def _evidenzia_etichette(self):
        """A11 rev. 7: le etichette RISPOSTA:/FORMULA: della zona C sono rese in
        grassetto (tag del tk.Text); nessun widget nuovo, copiabilità invariata."""
        try:
            self.box.tag_configure("etichetta_finale", font=("Consolas", 10, "bold"))
            for etichetta in ("RISPOSTA:", "FORMULA:"):
                pos = "1.0"
                while True:
                    pos = self.box.search(etichetta, pos, stopindex="end")
                    if not pos:
                        break
                    self.box.tag_add("etichetta_finale", pos, f"{pos}+{len(etichetta)}c")
                    pos = f"{pos}+{len(etichetta)}c"
        except tk.TclError:
            pass


PLACEHOLDER_CHIAVE = "incolla qui la chiave"
PLACEHOLDER_SENZA_CHIAVE = "non richiede chiave"


class SplashByok(tk.Toplevel):
    """Splash BYOK completo: lista completa dei clienti (Ollama, LM Studio, Jan,
    OpenAI, Anthropic, opencode + personalizzati dal registro clienti.json) con
    spunta di stato, stato installazione per i locali, casella chiave SEMPRE
    visibile, 'Disconnetti' per i connessi, consiglio Ollama e form di aggiunta
    custom. Chiavi: cloud nel .env, custom nel registro clienti.json — MAI
    stampate nei messaggi. Non bloccante: ✖ o 'Chiudi' lo chiudono."""
    def __init__(self, master):
        super().__init__(master)
        self.title("TRILogos — Pronto all'uso")
        self.geometry("660x700")
        self.resizable(False, False)
        self.configure(bg=PALETTE["sfondo"])
        self._coda = queue.Queue()
        self._righe = {}
        self._var_non_mostrare = tk.BooleanVar(value=False)
        self._costruisci()
        self._stato_cloud_iniziale()
        self._stato_custom_iniziale()
        self._rileva()
        self.protocol("WM_DELETE_WINDOW", self._chiudi)
        self.after(50, self._sonda)

    # ---- costruzione ----
    def _costruisci(self):
        stile = ttk.Style(self)
        stile.configure("Splash.TEntry", font=("Consolas", 10),
                        fieldbackground=PALETTE["campo"], foreground=PALETTE["testo"],
                        insertcolor=PALETTE["testo"], bordercolor=PALETTE["bordo"],
                        lightcolor=PALETTE["bordo"], darkcolor=PALETTE["bordo"],
                        selectbackground=PALETTE["selectbackground"],
                        selectforeground=PALETTE["selectforeground"])
        stile.configure("SplashPlaceholder.TEntry", font=("Consolas", 10),
                        fieldbackground=PALETTE["campo"], foreground=PALETTE["secondario"],
                        insertcolor=PALETTE["testo"], bordercolor=PALETTE["bordo"],
                        lightcolor=PALETTE["bordo"], darkcolor=PALETTE["bordo"],
                        selectbackground=PALETTE["selectbackground"],
                        selectforeground=PALETTE["selectforeground"])
        stile.configure("SplashDis.TEntry", font=("Consolas", 10),
                        fieldbackground=PALETTE["campo"], foreground=PALETTE["secondario"],
                        insertcolor=PALETTE["secondario"], bordercolor=PALETTE["bordo"],
                        lightcolor=PALETTE["bordo"], darkcolor=PALETTE["bordo"],
                        selectbackground=PALETTE["selectbackground"],
                        selectforeground=PALETTE["selectforeground"])
        header = tk.Frame(self, bg=PALETTE["sfondo"])
        header.pack(fill="x", padx=12, pady=(12, 6))
        Pill(header, testo="  TRILogos  ").pack(side="left")
        tk.Label(header, text="Pronto all'uso — configura i tuoi clienti",
                 bg=PALETTE["sfondo"], fg=PALETTE["ambra"],
                 font=FONT_H).pack(side="left", padx=10)

        # corpo scrollabile (header e fondo restano fissi)
        self._corpo_canvas = tk.Canvas(self, bg=PALETTE["sfondo"],
                                       highlightthickness=0, bd=0)
        self._corpo_sb = ttk.Scrollbar(self._corpo_canvas, orient="vertical",
                                       command=self._corpo_canvas.yview)
        self._corpo_canvas.configure(yscrollcommand=self._corpo_sb.set)
        self._corpo = tk.Frame(self._corpo_canvas, bg=PALETTE["sfondo"])
        self._corpo_item = self._corpo_canvas.create_window(
            (0, 0), window=self._corpo, anchor="nw")
        self._corpo_canvas.bind("<Configure>", self._corpo_resize)
        self._corpo.bind("<Configure>", self._corpo_scroll)
        self._corpo_canvas.bind("<MouseWheel>", self._wheel_corpo)
        self._corpo_sb.pack(side="right", fill="y")
        self._corpo_canvas.pack(fill="both", expand=True)

        self._primi_passi()
        self._consiglio()
        self._clienti_locali()
        self._clienti_cloud()
        self._cliente_opencode()
        self._clienti_custom()
        self._form_custom()

        # esito operazioni (mai il valore della chiave)
        self._lbl_esito = tk.Label(self, text="", bg=PALETTE["sfondo"],
                                   fg=PALETTE["secondario"], font=("Segoe UI", 9),
                                   anchor="w", justify="left")
        self._lbl_esito.pack(fill="x", padx=14, pady=(2, 0))

        # fondo: Riprova connessioni (sinistra) · Non mostrare più · Chiudi (destra)
        fondo = tk.Frame(self, bg=PALETTE["sfondo"])
        fondo.pack(fill="x", padx=12, pady=(6, 10), side="bottom")
        PulsanteRotondo(fondo, testo="🔄 Riprova connessioni",
                        comando=self._rileva).pack(side="left")
        tk.Checkbutton(fondo, text="Non mostrare più", variable=self._var_non_mostrare,
                       bg=PALETTE["sfondo"], fg=PALETTE["testo"],
                       activebackground=PALETTE["sfondo"], activeforeground=PALETTE["testo"],
                       selectcolor=PALETTE["campo"], highlightthickness=0,
                       font=("Segoe UI", 10)).pack(side="left", padx=16)
        PulsanteRotondo(fondo, testo="✖ Chiudi", comando=self._chiudi).pack(side="right")

    def _consiglio(self):
        """Riquadro evidenziato in cima ai clienti LOCALI: il più leggero e migliore."""
        cons = RiquadroRotondo(self._corpo)
        cons.pack(fill="x", padx=12, pady=(6, 3))
        tk.Label(cons.frame, text="⭐ CONSIGLIATO — Ollama",
                 bg=PALETTE["pannello"], fg=PALETTE["ambra"],
                 font=FONT_B).pack(anchor="w", padx=8, pady=(4, 0))
        tk.Label(cons.frame, text="il client locale più leggero e semplice: installalo e scarica il modello base con",
                 bg=PALETTE["pannello"], fg=PALETTE["testo"], font=("Segoe UI", 9),
                 wraplength=590, justify="left").pack(anchor="w", padx=8)
        tk.Label(cons.frame, text="ollama pull qwen2.5:3b", bg=PALETTE["campo"],
                 fg=PALETTE["ambra"], font=("Consolas", 10), padx=8, pady=2).pack(anchor="w", padx=8, pady=2)
        info = LOCALI_INFO["ollama"]
        PulsanteRotondo(cons.frame, testo="🌐 Scarica Ollama", width=14,
                        comando=lambda: webbrowser.open(info["installer"])).pack(side="left", padx=8, pady=(2, 6))
        tk.Label(cons.frame, text=f"oppure in PowerShell:  {info['winget']}",
                 bg=PALETTE["pannello"], fg=PALETTE["secondario"],
                 font=("Consolas", 9)).pack(side="left", padx=8, pady=(2, 6))

    # ---- Primi passi: checklist a 4 voci con spunta automatica ----
    def _primi_passi(self):
        """Riquadro '✓ Primi passi' IN CIMA al corpo scrollabile: 4 voci con
        spunta automatica dallo stato reale (nessuna interazione utente per
        spuntare). Tutte verdi -> si comprime a una sola riga 'tutto pronto!'."""
        riq = RiquadroRotondo(self._corpo)
        riq.pack(fill="x", padx=12, pady=(6, 3))
        f = riq.frame
        self._pp_titolo = tk.Label(f, text="✓ Primi passi", bg=PALETTE["pannello"],
                                   fg=PALETTE["ambra"], font=FONT_B)
        self._pp_titolo.pack(anchor="w", padx=8, pady=(4, 0))
        self._pp_righe = {}
        for chiave, testo in (("ollama", "Installa Ollama"),
                              ("modello", "Scarica un modello"),
                              ("voci", "Connetti le voci"),
                              ("prima_domanda", "Fai la tua prima domanda")):
            riga = tk.Frame(f, bg=PALETTE["pannello"])
            spunta = tk.Label(riga, text="○", bg=PALETTE["pannello"],
                              fg=PALETTE["secondario"], font=("Segoe UI", 11))
            spunta.pack(side="left", padx=(8, 0))
            tk.Label(riga, text=testo, bg=PALETTE["pannello"],
                     fg=PALETTE["testo"], font=("Segoe UI", 9)).pack(side="left", padx=(4, 0))
            sugg = tk.Label(f, text="", bg=PALETTE["pannello"],
                            fg=PALETTE["secondario"], font=("Consolas", 9),
                            wraplength=560, justify="left")
            self._pp_righe[chiave] = {"spunta": spunta, "sugg": sugg, "riga": riga}
        self._pp_stato = tk.Label(f, text="", bg=PALETTE["pannello"],
                                  fg=PALETTE["secondario"], font=("Segoe UI", 8))
        self._aggiorna_primi_passi()

    def _stato_ollama(self):
        """Stato di Ollama (dict di stato_locale) dai risultati già rilevati,
        o con rilevamento diretto se non ancora arrivati (costruzione)."""
        st = getattr(self, "_ultimi_esiti", {}).get("ollama")
        if st is None:
            info = LOCALI_INFO["ollama"]
            st = stato_locale({"nome": "ollama", "base_url": info["base_url"]})
        return st or {}

    def _voci_collegate(self):
        """True se i 3 menu (LLM1/LLM2/LLM3) hanno ciascuno una voce valida:
        non 'mock', non 'nessun modello', non vuota (lettura live delle combo)."""
        master = self.master
        for colonna in (getattr(master, "c_a", None),
                        getattr(master, "c_b", None),
                        getattr(master, "c_c", None)):
            if colonna is None or not hasattr(colonna, "combo"):
                return False
            try:
                voce = (colonna.combo.get() or "").strip()
            except tk.TclError:
                return False
            if not voce or voce == "mock" or voce == "nessun modello":
                return False
        return True

    def _aggiorna_primi_passi(self):
        """Ricalcola le 4 spunte dallo stato reale e ridisegna il riquadro."""
        if not getattr(self, "_pp_righe", None):
            return
        st = self._stato_ollama()
        stati = {
            "ollama": st.get("stato") != "non_installato",
            "modello": st.get("stato") == "attivo" and bool(st.get("modelli")),
            "voci": self._voci_collegate(),
            "prima_domanda": _primo_flusso_ok(),
        }
        tutte = all(stati.values())
        contate = sum(1 for v in stati.values() if v)
        self._pp_titolo.configure(
            text="✓ Primi passi — tutto pronto!" if tutte else "✓ Primi passi")
        suggerimenti = {
            "ollama": "Installa: ollama.com/download  o  winget install Ollama.Ollama",
            "modello": "comando: ollama pull qwen2.5:3b",
            "voci": "",
            "prima_domanda": "",
        }
        for chiave, riga in self._pp_righe.items():
            on = stati[chiave]
            riga["spunta"].configure(text="✓" if on else "○",
                                     fg=PALETTE["verde"] if on else PALETTE["secondario"])
            riga["sugg"].configure(text=suggerimenti[chiave] if not on else "")
        self._pp_stato.configure(text="" if tutte else f"{contate} di 4 completati")
        self._compatta_primi_passi(tutte)

    def _compatta_primi_passi(self, tutte):
        """Tutte verdi -> nasconde le righe dettagliate (resta solo il titolo);
        altrimenti le mostra nell'ordine, con i suggerimenti solo se visibili."""
        for riga in self._pp_righe.values():
            riga["riga"].pack_forget()
            riga["sugg"].pack_forget()
        self._pp_stato.pack_forget()
        if tutte:
            return
        for riga in self._pp_righe.values():
            riga["riga"].pack(fill="x")
            if riga["sugg"].cget("text"):
                riga["sugg"].pack(anchor="w", padx=(26, 8))
        self._pp_stato.pack(anchor="w", padx=8, pady=(0, 4))

    def _clienti_locali(self):
        tk.Label(self._corpo, text="CLIENT LOCALI", bg=PALETTE["sfondo"],
                 fg=PALETTE["ambra"], font=FONT_B).pack(anchor="w", padx=16, pady=(6, 2))
        for chiave in ("ollama", "lmstudio", "jan"):
            info = LOCALI_INFO[chiave]
            self._riquadro_cliente(chiave, info["base_url"], tipo="locale")

    def _clienti_cloud(self):
        tk.Label(self._corpo, text="CLIENT CLOUD", bg=PALETTE["sfondo"],
                 fg=PALETTE["ambra"], font=FONT_B).pack(anchor="w", padx=16, pady=(6, 2))
        tk.Label(self._corpo, text="le chiavi restano solo su questo computer (file .env, mai nel repository)",
                 bg=PALETTE["sfondo"], fg=PALETTE["secondario"],
                 font=("Segoe UI", 9)).pack(anchor="w", padx=16)
        for nome, env, base, link in CLIENTI_CLOUD:
            self._riquadro_cliente(nome, base, tipo="cloud", link=link)

    def _cliente_opencode(self):
        tk.Label(self._corpo, text="OPENCODE", bg=PALETTE["sfondo"],
                 fg=PALETTE["ambra"], font=FONT_B).pack(anchor="w", padx=16, pady=(6, 2))
        self._riquadro_cliente("opencode", "", tipo="opencode")
        self._righe["opencode"]["info"].configure(
            text="configurato in opencode.json (i provider si gestiscono in quel file: TRILogos non lo modifica e non lo aggiunge al registro)")

    def _clienti_custom(self):
        tk.Label(self._corpo, text="CLIENT PERSONALIZZATI", bg=PALETTE["sfondo"],
                 fg=PALETTE["ambra"], font=FONT_B).pack(anchor="w", padx=16, pady=(6, 2))
        self._contenitore_custom = tk.Frame(self._corpo, bg=PALETTE["sfondo"])
        self._contenitore_custom.pack(fill="x")
        self._popola_custom()

    def _popola_custom(self):
        """Ricostruisce i riquadri dei client personalizzati dal registro
        (clienti.json). I nomi di default e 'opencode:*' non compaiono qui."""
        for w in self._contenitore_custom.winfo_children():
            w.destroy()
        for k in [k for k in self._righe if self._righe[k]["tipo"] == "custom"]:
            del self._righe[k]
        custom = [c for c in aggiunti()
                  if c.get("nome") not in NOMI_DEFAULT
                  and not (c.get("nome") or "").startswith("opencode:")]
        if not custom:
            tk.Label(self._contenitore_custom, text="(nessun client personalizzato: aggiungine uno qui sotto)",
                     bg=PALETTE["sfondo"], fg=PALETTE["secondario"],
                     font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=2)
            return
        for c in custom:
            self._riquadro_cliente(c["nome"], c.get("base_url", ""), tipo="custom")

    def _riquadro_cliente(self, nome, base_url, tipo="locale", link=None):
        """Riquadro di UN cliente: spunta + nome + stato + badge (riga 1),
        casella chiave SEMPRE visibile + pulsanti (riga 2), note (riga 3).
        Registra i widget in self._righe[nome] per gli aggiornamenti."""
        riq = RiquadroRotondo(self._corpo)
        riq.pack(fill="x", padx=12, pady=3)
        f = riq.frame
        riga1 = tk.Frame(f, bg=PALETTE["pannello"])
        riga1.pack(fill="x", padx=8, pady=(4, 0))
        dot = tk.Label(riga1, text="●", bg=PALETTE["pannello"],
                       font=("Segoe UI", 12), fg=PALETTE["secondario"])
        dot.pack(side="left")
        tk.Label(riga1, text=nome, bg=PALETTE["pannello"], fg=PALETTE["testo"],
                 font=FONT_B).pack(side="left", padx=6)
        lbl_stato = tk.Label(riga1, text="· Non connesso", bg=PALETTE["pannello"],
                             fg=PALETTE["secondario"], font=("Segoe UI", 9))
        lbl_stato.pack(side="left")
        lbl_badge = tk.Label(riga1, text="", bg=PALETTE["pannello"],
                             font=("Segoe UI", 9, "bold"))
        lbl_badge.pack(side="left", padx=8)
        riga2 = tk.Frame(f, bg=PALETTE["pannello"])
        riga2.pack(fill="x", padx=8, pady=(2, 0))
        riga2.grid_columnconfigure(0, weight=1)
        entry = ttk.Entry(riga2, font=("Consolas", 10), style="Splash.TEntry")
        entry.grid(row=0, column=0, sticky="we")
        btn_salva = None
        btn_dis = None
        btn_link = None
        if tipo in ("locale", "opencode"):
            entry.insert(0, PLACEHOLDER_SENZA_CHIAVE)
            entry.configure(style="SplashDis.TEntry", state="disabled")
        else:
            entry.insert(0, PLACEHOLDER_CHIAVE)
            entry.configure(style="SplashPlaceholder.TEntry")
            entry.bind("<FocusIn>", lambda e, en=entry: self._focus_in_chiave(en))
            entry.bind("<FocusOut>", lambda e, en=entry: self._focus_out_chiave(en))
            btn_salva = PulsanteRotondo(riga2, testo="💾 Salva chiave", width=11,
                                        comando=lambda n=nome: self._salva_chiave_riga(n))
            btn_salva.grid(row=0, column=1, padx=(6, 2))
            btn_dis = PulsanteRotondo(riga2, testo="Disconnetti", width=10,
                                      comando=lambda n=nome: self._disconnetti(n))
            btn_dis.grid(row=0, column=2, padx=(2, 0))
            btn_dis.grid_remove()  # visibile SOLO se il cliente è connesso
            if link:
                btn_link = PulsanteRotondo(riga2, testo="🔗 Link", width=5,
                                           comando=lambda u=link: webbrowser.open(u))
                btn_link.grid(row=0, column=3, padx=(2, 0))
        lbl_info = tk.Label(f, text="", bg=PALETTE["pannello"],
                            fg=PALETTE["secondario"], font=("Segoe UI", 9),
                            wraplength=590, justify="left")
        lbl_info.pack(fill="x", padx=8, pady=(2, 4))
        self._righe[nome] = {"riq": riq, "dot": dot, "stato": lbl_stato,
                             "badge": lbl_badge, "entry": entry,
                             "btn_salva": btn_salva, "btn_dis": btn_dis,
                             "info": lbl_info, "blocco": None,
                             "tipo": tipo, "base_url": base_url}
        return riq

    def _stato_cloud_iniziale(self):
        for nome, env, _, _ in CLIENTI_CLOUD:
            if os.environ.get(env):
                self._set_connesso(nome, True)

    def _stato_custom_iniziale(self):
        for nome, riga in self._righe.items():
            if riga["tipo"] != "custom":
                continue
            trovato = trova_client(aggiunti(), nome)
            if trovato and trovato.get("chiave"):
                self._set_connesso(nome, True)

    # ---- rilevamento asincrono (mai rete esterna: solo porte locali) ----
    def _rileva(self):
        try:
            self._lbl_esito.configure(text="rilevamento connessioni locali …",
                                      fg=PALETTE["secondario"])
        except tk.TclError:
            pass
        threading.Thread(target=self._rileva_thread, daemon=True).start()

    def _rileva_thread(self):
        esiti = {}
        for chiave in ("ollama", "lmstudio", "jan"):
            info = LOCALI_INFO[chiave]
            esiti[chiave] = stato_locale({"nome": chiave, "base_url": info["base_url"]})
        esiti["opencode"] = stato_opencode()
        for c in aggiunti():
            nome = c.get("nome") or ""
            if nome in NOMI_DEFAULT or nome.startswith("opencode:"):
                continue
            if _base_e_locale(c.get("base_url", "")):
                esiti[nome] = {"connesso": _server_attivo(_porta_base(c.get("base_url")), timeout=0.6)}
        self._coda.put(("esiti", esiti))

    def _sonda(self):
        try:
            while True:
                tipo, valore = self._coda.get_nowait()
                if tipo == "esiti":
                    self._mostra_esiti(valore)
        except queue.Empty:
            pass
        except tk.TclError:
            return
        try:
            self.after(50, self._sonda)
        except tk.TclError:
            pass

    def _mostra_esiti(self, esiti):
        for nome in ("ollama", "lmstudio", "jan"):
            st = esiti.get(nome)
            riga = self._righe.get(nome)
            if not st or riga is None:
                continue
            if st["stato"] == "attivo":
                self._set_connesso(nome, True)
                riga["badge"].configure(text="Attivo", fg=PALETTE["verde"])
                modelli = st.get("modelli") or []
                testo = (f"server attivo sulla porta {st['porta']} — modelli: {', '.join(modelli)}"
                         if modelli else f"server attivo sulla porta {st['porta']} (nessun modello rilevato)")
                riga["info"].configure(text=testo, fg=PALETTE["verde"])
            elif st["stato"] == "installato":
                self._set_connesso(nome, False)
                riga["badge"].configure(text="Installato — avvialo", fg=PALETTE["ambra"])
                riga["info"].configure(text=st["avvio"], fg=PALETTE["secondario"])
            else:
                self._set_connesso(nome, False)
                riga["badge"].configure(text="Non installato", fg=PALETTE["rosso"])
                riga["info"].configure(text="Non installato. Due modi:", fg=PALETTE["secondario"])
                self._istruzioni_installazione(riga, st)
        oc = esiti.get("opencode")
        if oc and "opencode" in self._righe:
            self._set_connesso("opencode", oc.get("stato") == "connesso")
        for nome, st in esiti.items():
            riga = self._righe.get(nome)
            if riga is None or riga["tipo"] != "custom":
                continue
            if isinstance(st, dict) and st.get("connesso") is True:
                self._set_connesso(nome, True)
        self._lbl_esito.configure(text="connessioni locali rilevate",
                                  fg=PALETTE["secondario"])
        self._ultimi_esiti = esiti
        self._aggiorna_primi_passi()

    def _istruzioni_installazione(self, riga, st):
        """Due vie di installazione in italiano: installer desktop (link) e
        PowerShell (winget). Il blocco viene ricreato a ogni rilevamento."""
        if riga["blocco"] is not None:
            try:
                riga["blocco"].destroy()
            except tk.TclError:
                pass
        blocco = tk.Frame(riga["riq"].frame, bg=PALETTE["pannello"])
        blocco.pack(fill="x", padx=8, pady=(0, 4))
        PulsanteRotondo(blocco, testo="🌐 Scarica l'installer", width=14,
                        comando=lambda u=st["installer"]: webbrowser.open(u)).pack(side="left", padx=(0, 6))
        tk.Label(blocco, text=f"PowerShell:  {st['winget']}", bg=PALETTE["pannello"],
                 fg=PALETTE["secondario"], font=("Consolas", 9)).pack(side="left")
        riga["blocco"] = blocco

    # ---- stato / spunta ----
    def _set_connesso(self, nome, connesso):
        riga = self._righe.get(nome)
        if riga is None:
            return
        colore = PALETTE["verde"] if connesso else PALETTE["secondario"]
        riga["dot"].configure(fg=colore)
        riga["stato"].configure(text="✓ Connesso" if connesso else "· Non connesso",
                                fg=colore)
        if riga["btn_dis"] is not None:
            if connesso:
                riga["btn_dis"].grid()
            else:
                riga["btn_dis"].grid_remove()

    # ---- casella chiave (sempre visibile: per inserire E sostituire) ----
    def _focus_in_chiave(self, entry):
        if entry.get() == PLACEHOLDER_CHIAVE:
            entry.delete(0, "end")
            entry.configure(style="Splash.TEntry")

    def _focus_out_chiave(self, entry):
        if not entry.get():
            entry.insert(0, PLACEHOLDER_CHIAVE)
            entry.configure(style="SplashPlaceholder.TEntry")

    def _salva_chiave_riga(self, nome):
        """Salva la chiave: .env per i cloud, REGISTRO per i custom (mai nel
        .env). Messaggi di stato senza il valore della chiave."""
        riga = self._righe.get(nome)
        if riga is None:
            return
        valore = riga["entry"].get().strip()
        if not valore or valore == PLACEHOLDER_CHIAVE:
            self._lbl_esito.configure(text="campo vuoto: nessuna chiave salvata",
                                      fg=PALETTE["secondario"])
            return
        if riga["tipo"] == "custom":
            trovato = trova_client(aggiunti(), nome)
            base = riga["base_url"] or (trovato or {}).get("base_url", "http://localhost:1234/v1")
            modelli = (trovato or {}).get("modelli", []) or [nome]
            aggiungi_cliente({"nome": nome, "base_url": base,
                              "chiave": valore, "modelli": modelli})
            self._lbl_esito.configure(text="chiave salvata nel registro clienti (mai nel .env)",
                                      fg=PALETTE["verde"])
        else:
            nome_env = NOMI_ENV.get(nome)
            if not nome_env:
                return
            try:
                _scrivi_chiave_env(os.path.join(BASE, ".env"), nome_env, valore)
            except Exception as e:
                self._lbl_esito.configure(text=f"ERRORE salvataggio: {e}",
                                          fg=PALETTE["errore"])
                return
            os.environ[nome_env] = valore
            self._lbl_esito.configure(text="chiave salvata nel file .env (mai nel repository)",
                                      fg=PALETTE["verde"])
        self._set_connesso(nome, True)
        riga["entry"].configure(style="SplashPlaceholder.TEntry")
        riga["entry"].delete(0, "end")
        riga["entry"].insert(0, PLACEHOLDER_CHIAVE)

    def _disconnetti(self, nome):
        """Rimuove la chiave: dal .env per i cloud, dal registro per i custom.
        Il cliente RESTA nella lista; la spunta torna a 'non connesso'."""
        riga = self._righe.get(nome)
        if riga is None:
            return
        if riga["tipo"] == "custom":
            trovato = trova_client(aggiunti(), nome)
            if trovato:
                aggiungi_cliente({"nome": nome,
                                  "base_url": trovato.get("base_url", riga["base_url"]),
                                  "chiave": "",
                                  "modelli": trovato.get("modelli", [])})
            self._lbl_esito.configure(text=f"chiave di '{nome}' rimossa dal registro clienti",
                                      fg=PALETTE["secondario"])
        else:
            nome_env = NOMI_ENV.get(nome)
            if nome_env:
                try:
                    _rimuovi_chiave_env(os.path.join(BASE, ".env"), nome_env)
                except Exception as e:
                    self._lbl_esito.configure(text=f"ERRORE rimozione: {e}",
                                              fg=PALETTE["errore"])
                    return
                os.environ.pop(nome_env, None)
            self._lbl_esito.configure(text="chiave rimossa dal file .env",
                                      fg=PALETTE["secondario"])
        self._set_connesso(nome, False)

    # ---- form aggiunta client personalizzato ----
    def _form_custom(self):
        riq = RiquadroRotondo(self._corpo)
        riq.pack(fill="x", padx=12, pady=(6, 3))
        f = riq.frame
        tk.Label(f, text="➕ Aggiungi un client personalizzato", bg=PALETTE["pannello"],
                 fg=PALETTE["ambra"], font=FONT_B).pack(anchor="w", padx=8, pady=(4, 2))
        griglia = tk.Frame(f, bg=PALETTE["pannello"])
        griglia.pack(fill="x", padx=8)
        griglia.grid_columnconfigure(1, weight=1)

        def campo(riga, label, default=""):
            tk.Label(griglia, text=label, bg=PALETTE["pannello"], fg=PALETTE["testo"],
                     font=("Segoe UI", 9)).grid(row=riga, column=0, sticky="w", pady=1)
            e = ttk.Entry(griglia, font=("Consolas", 10), style="Splash.TEntry", width=30)
            if default:
                e.insert(0, default)
            e.grid(row=riga, column=1, sticky="we", padx=4, pady=1)
            return e

        self._form_nome = campo(0, "Nome")
        self._form_base = campo(1, "Base URL", "http://localhost:1234/v1")
        self._form_chiave = campo(2, "Chiave (opz.)")
        self._form_modelli = campo(3, "Modelli (csv)")
        PulsanteRotondo(f, testo="＋ Aggiungi", width=10,
                        comando=self._aggiungi_custom).pack(side="left", padx=8, pady=(4, 6))
        tk.Label(f, text="il nuovo client compare subito qui sopra e nei menu di LLM1/LLM2/LLM3",
                 bg=PALETTE["pannello"], fg=PALETTE["secondario"],
                 font=("Segoe UI", 9)).pack(side="left", padx=4, pady=(4, 6))

    def _aggiungi_custom(self):
        nome = self._form_nome.get().strip()
        if not nome:
            self._lbl_esito.configure(text="nome obbligatorio: nessun client aggiunto",
                                      fg=PALETTE["secondario"])
            return
        if nome in NOMI_DEFAULT or nome.startswith("opencode:"):
            self._lbl_esito.configure(text=f"'{nome}' è già un client di default: usa un altro nome",
                                      fg=PALETTE["errore"])
            return
        modelli = [m.strip() for m in self._form_modelli.get().split(",") if m.strip()]
        aggiungi_cliente({"nome": nome,
                          "base_url": self._form_base.get().strip() or "http://localhost:1234/v1",
                          "chiave": self._form_chiave.get().strip(),
                          "modelli": modelli})
        self._popola_custom()
        self._form_nome.delete(0, "end")
        self._form_chiave.delete(0, "end")
        self._form_modelli.delete(0, "end")
        self._lbl_esito.configure(text=f"client '{nome}' aggiunto al registro · presente nei menu",
                                  fg=PALETTE["verde"])
        agg = getattr(self.master, "_aggiorna_menu_clienti", None)
        if agg:
            try:
                agg()
            except Exception:
                pass

    # ---- scroll del corpo ----
    def _corpo_scroll(self, e=None):
        self._corpo_canvas.configure(scrollregion=(
            0, 0, self._corpo.winfo_reqwidth(), self._corpo.winfo_reqheight()))
        for w in _discendenti(self._corpo):
            if w is not self._corpo_canvas:
                w.bind("<MouseWheel>", self._wheel_corpo)

    def _corpo_resize(self, e=None):
        lar = self._corpo_canvas.winfo_width()
        if lar < 10:
            return
        self._corpo_canvas.itemconfigure(self._corpo_item, width=max(10, lar - 4))

    def _wheel_corpo(self, e):
        self._corpo_canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")
        return "break"

    def _chiudi(self):
        if self._var_non_mostrare.get():
            _salva_flag_byok()
        self.destroy()


class FinestraAvvioGuidato(tk.Toplevel):
    """B2e — Primo avvio guidato del motore interno (non bloccante).
    Passi: (a) rileva hardware (Profiler B2a); (b) propone i modelli per fascia
    (downloader.per_fascia + 0.5B) con nome, dimensione e licenza; (c) scarica
    con progresso (byte/totali/%, velocita'; Annulla -> parziale conservato per
    la ripresa); (d) pronto: i modelli compaiono nei menu. Chiudibile in ogni
    momento con 'Più tardi'; un download in corso viene annullato (parziale
    conservato). Stringhe nella lingua attiva della finestra principale."""

    def __init__(self, master, cartella=None):
        super().__init__(master)
        self.app = master
        self._cartella = cartella or _motore.cartella_modelli()
        self._annulla = False
        self._voce_in_corso = None
        self._righe = {}
        self._check_catalogo = {}
        self._coda_attiva = False
        self._annulla_coda = False
        self._profilo = None
        self.title("TRILogos — " + self._t("motore_titolo"))
        self.geometry("700x640")
        self.configure(bg=PALETTE["sfondo"])
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self._chiudi)
        self._costruisci()
        threading.Thread(target=self._lavoro_hw, daemon=True).start()

    def _t(self, chiave):
        return TESTI[self.app.lingua][chiave]

    # ---- costruzione ----
    def _costruisci(self):
        header = tk.Frame(self, bg=PALETTE["sfondo"])
        header.pack(fill="x", padx=12, pady=(12, 4))
        Pill(header, testo="  TRILogos  ").pack(side="left")
        tk.Label(header, text=self._t("motore_titolo"), bg=PALETTE["sfondo"],
                 fg=PALETTE["ambra"], font=FONT_H).pack(side="left", padx=10)
        self._lbl_hw = tk.Label(self, text=self._t("motore_attesa"), bg=PALETTE["sfondo"],
                                fg=PALETTE["secondario"], font=("Segoe UI", 10),
                                anchor="w", justify="left")
        self._lbl_hw.pack(fill="x", padx=14, pady=(2, 6))
        # B2g: modalita' pulita PRIMA delle proposte modelli (proposta + misura)
        barra_pul = tk.Frame(self, bg=PALETTE["sfondo"])
        barra_pul.pack(fill="x", padx=14, pady=(0, 4))
        PulsanteRotondo(barra_pul, testo=self._t("pul_pulsante"),
                        comando=self._apri_pulizia).pack(side="left")
        self._lbl_pul = tk.Label(barra_pul, text="", bg=PALETTE["sfondo"],
                                 fg=PALETTE["verde"], font=("Segoe UI", 9))
        self._lbl_pul.pack(side="left", padx=8)
        tk.Label(self, text=self._t("motore_proposti"), bg=PALETTE["sfondo"],
                 fg=PALETTE["testo"], font=FONT_B, anchor="w").pack(fill="x", padx=14)
        self._corpo = tk.Frame(self, bg=PALETTE["sfondo"])
        self._corpo.pack(fill="both", expand=True, padx=14, pady=4)
        # download: stato + barra + annulla
        self._lbl_prog = tk.Label(self, text="", bg=PALETTE["sfondo"],
                                  fg=PALETTE["ambra"], font=("Consolas", 9),
                                  anchor="w", justify="left")
        self._lbl_prog.pack(fill="x", padx=14)
        self._barra = tk.Canvas(self, height=14, bg=PALETTE["campo"],
                                highlightthickness=0, bd=0)
        self._barra.pack(fill="x", padx=14, pady=(2, 4))
        self._barra_pieno = self._barra.create_rectangle(
            0, 0, 0, 14, fill=PALETTE["ambra"], outline="")
        self._lbl_pronto = tk.Label(self, text="", bg=PALETTE["sfondo"],
                                    fg=PALETTE["verde"], font=("Segoe UI", 10, "bold"),
                                    anchor="w", justify="left")
        self._lbl_pronto.pack(fill="x", padx=14)
        fondo = tk.Frame(self, bg=PALETTE["sfondo"])
        fondo.pack(fill="x", padx=12, pady=(6, 10), side="bottom")
        self._btn_coda = PulsanteRotondo(fondo, testo=self._t("cat_scarica_sel"),
                                         comando=self._avvia_coda)
        self._btn_coda.pack(side="left")
        self._btn_annulla_coda = PulsanteRotondo(fondo, testo=self._t("cat_annulla_coda"),
                                                 comando=self._ferma_coda)
        self._btn_annulla_coda.pack(side="left", padx=8)
        self._btn_annulla_coda.pack_forget()
        PulsanteRotondo(fondo, testo=self._t("motore_piu_tardi"),
                        comando=self._chiudi).pack(side="right")

    def _lavoro_hw(self):
        """Profiler in background: mai bloccare la UI."""
        try:
            profilo = _profiler.rileva()
        except Exception as e:
            self.app._ui(self._mostra_errore, str(e))
            return
        self.app._ui(self._mostra_hw, profilo)

    def _mostra_hw(self, profilo):
        parti = []
        if profilo.gpu_nome:
            parti.append(f"{profilo.gpu_nome} · {profilo.vram_totale_mib} MiB VRAM "
                         f"({profilo.vram_libera_mib} liberi)")
        else:
            parti.append("GPU: nessuna (solo CPU)")
        parti.append(f"RAM {profilo.ram_totale_gb} GB ({profilo.ram_libera_gb} liberi)")
        parti.append(f"CPU {profilo.cpu_core} core / {profilo.cpu_thread} thread")
        testo = self._t("motore_hw") + ": " + " · ".join(parti)
        if profilo.avvisi:
            testo += "\n" + " · ".join(profilo.avvisi)
        self._lbl_hw.configure(text=testo)
        self._proponi(profilo)

    def _apri_pulizia(self):
        """B2g: apre la modalita' pulita; a fine pulizia aggiorna hardware,
        guadagno reale e proposte modelli (ricalcolo per_fascia)."""
        FinestraPulizia(self.app, al_termine=self._pulizia_fatta)

    def _pulizia_fatta(self, profilo):
        """Callback a fine pulizia: profilo ri-rilevato dal Profiler."""
        self._mostra_hw(profilo)
        if getattr(profilo, "vram_libera_mib", None) is not None:
            self._lbl_pul.configure(
                text=f"{profilo.vram_libera_mib} MiB VRAM liberi")

    def _proponi(self, profilo):
        """B2d/B2e rev.: catalogo con checkbox multi-selezione e colonne
        nome/dimensione/fascia/input/output/licenza; stato installato
        persistente e badge 'in uso'. La spunta serve SOLO al download:
        l'attivazione resta nei menu A/B/C."""
        self._profilo = profilo
        for figlio in self._corpo.winfo_children():
            figlio.destroy()
        self._check_catalogo.clear()
        self._righe.clear()
        try:
            consigliate = {v.chiave for v in _downloader.per_fascia(profilo)}
            voci = list(_downloader.catalogo())
        except Exception as e:
            self._mostra_errore(str(e))
            return
        larghezze = (26, 9, 18, 12, 8, 16)
        intest = tk.Frame(self._corpo, bg=PALETTE["sfondo"])
        intest.pack(fill="x")
        for testo, larghezza in zip(
                (self._t("cat_nome"), self._t("cat_dim"), self._t("cat_fascia"),
                 self._t("cat_input"), self._t("cat_output"), self._t("cat_licenza")),
                larghezze):
            tk.Label(intest, text=testo, bg=PALETTE["sfondo"],
                     fg=PALETTE["secondario"], font=("Segoe UI", 8, "bold"),
                     width=larghezza, anchor="w").pack(side="left")
        for v in voci:
            riga = tk.Frame(self._corpo, bg=PALETTE["pannello"])
            riga.pack(fill="x", pady=1)
            installato = self._installato(v)
            var = tk.BooleanVar(value=False)
            casella = tk.Checkbutton(
                riga, text="", variable=var,
                state="disabled" if installato else "normal",
                bg=PALETTE["pannello"], activebackground=PALETTE["pannello"],
                selectcolor=PALETTE["campo"], highlightthickness=0)
            casella.pack(side="left", padx=2)
            self._check_catalogo[v.chiave] = var
            nome = v.nome + (" ★" if v.chiave in consigliate else "")
            dim = f"{v.dimensione_gb:.2f} GB" + (" +mmproj" if v.mmproj_url else "")
            for testo, larghezza in zip(
                    (nome, dim, v.fascia, ", ".join(v.input), ", ".join(v.output),
                     v.licenza), larghezze):
                tk.Label(riga, text=testo, bg=PALETTE["pannello"], fg=PALETTE["testo"],
                         font=("Segoe UI", 8), width=larghezza,
                         anchor="w").pack(side="left")
            stato = tk.Label(riga, text="", bg=PALETTE["pannello"],
                             font=("Segoe UI", 8, "bold"))
            stato.pack(side="left", padx=2)
            if installato:
                stato.configure(text=self._t("cat_installato"), fg=PALETTE["verde"])
            if self._in_uso(v):
                prefisso = (stato.cget("text") + " · ") if stato.cget("text") else ""
                stato.configure(text=prefisso + self._t("cat_in_uso"),
                                fg=PALETTE["ambra"])
            self._righe[v.chiave] = riga

    def _installato(self, v):
        """Installato persistente: file completo per dimensione (+ mmproj per i
        vision). Veloce: nessun checksum di GB a ogni apertura."""
        percorso = os.path.join(self._cartella,
                                _downloader.nome_file_sanificato(v.nome_file))
        if not (os.path.isfile(percorso)
                and os.path.getsize(percorso) == v.dimensione_byte):
            return False
        if v.mmproj_url:
            mmproj = os.path.join(self._cartella,
                                  _downloader.nome_file_sanificato(v.mmproj_file))
            if not (os.path.isfile(mmproj)
                    and os.path.getsize(mmproj) == v.mmproj_byte):
                return False
        return True

    def _in_uso(self, v):
        """Badge 'in uso': il file è selezionato in A/B/C del canale."""
        percorso = os.path.join(self._cartella,
                                _downloader.nome_file_sanificato(v.nome_file))
        for polo in ("A", "B", "C"):
            modello = getattr(self.app.canale, polo, None)
            if isinstance(modello, _motore.ModelloMotore) \
                    and modello.percorso == percorso:
                return True
        return False

    # ---- coda di download (uno alla volta, parziali conservati) ----
    def _avvia_coda(self):
        if self._coda_attiva:
            return
        scelte = []
        for chiave, var in self._check_catalogo.items():
            if not var.get():
                continue
            try:
                v = _downloader.voce(chiave)
            except _downloader.ErroreDownload:
                continue
            if not self._installato(v):
                scelte.append(v)
        if not scelte:
            self._lbl_prog.configure(text=self._t("cat_nessuna_sel"))
            return
        self._coda_attiva = True
        self._annulla_coda = False
        self._btn_annulla_coda.pack(side="left", padx=8)
        threading.Thread(target=self._lavoro_coda, args=(scelte,),
                         daemon=True).start()

    def _lavoro_coda(self, voci):
        totale = len(voci)
        for indice, v in enumerate(voci, start=1):
            self.app._ui(self._coda_voce, indice, totale, v)
            try:
                _downloader.scarica(v, self._cartella, self._callback_progresso)
            except _downloader.InterrompiDownload:
                self.app._ui(self._coda_interrotta)
                return
            except Exception as e:
                self.app._ui(self._coda_errore, str(e))
                return
        self.app._ui(self._coda_fine)

    def _callback_progresso(self, campione):
        if self._annulla_coda:
            raise _downloader.InterrompiDownload()
        self.app._ui(self._mostra_progresso, campione)

    def _coda_voce(self, indice, totale, v):
        self._lbl_prog.configure(
            text=self._t("cat_coda").format(i=indice, n=totale, file=v.nome_file))

    def _mostra_progresso(self, campione):
        if campione["fase"] == "verifica":
            self._lbl_prog.configure(text="verifica checksum…")
            return
        if campione["fase"] == "completato":
            return
        mb = campione["byte"] / 1e6
        tot = (campione["totale"] or 0) / 1e6
        perc = campione["percentuale"] or 0
        nome_file = campione.get("file") or ""
        self._lbl_prog.configure(
            text=f"{nome_file} · {mb:.1f}/{tot:.1f} MB · {perc:.1f}% · "
                 f"{campione['velocita_mb_s']:.1f} MB/s")
        lar = max(1, self._barra.winfo_width())
        self._barra.coords(self._barra_pieno, 0, 0, int(lar * perc / 100), 14)

    def _ferma_coda(self):
        self._annulla_coda = True
        self._lbl_prog.configure(text=self._t("motore_interrotto"))

    def _coda_interrotta(self):
        self._coda_attiva = False
        self._btn_annulla_coda.pack_forget()
        self._lbl_prog.configure(text=self._t("motore_interrotto"))
        if self._profilo is not None:
            self._proponi(self._profilo)

    def _coda_errore(self, messaggio):
        self._coda_attiva = False
        self._btn_annulla_coda.pack_forget()
        self._lbl_prog.configure(text=self._t("motore_errore").format(e=messaggio))

    def _coda_fine(self):
        self._coda_attiva = False
        self._btn_annulla_coda.pack_forget()
        self._barra.coords(self._barra_pieno, 0, 0, self._barra.winfo_width(), 14)
        self.app._aggiorna_voci_modelli()
        n = len(_motore.modelli_locali())
        self._lbl_pronto.configure(text=self._t("motore_pronto").format(n=n))
        if self._profilo is not None:
            self._proponi(self._profilo)

    def _mostra_errore(self, messaggio):
        self._lbl_prog.configure(text=self._t("motore_errore").format(e=messaggio))

    def _chiudi(self):
        if self._coda_attiva:
            self._annulla_coda = True  # il parziale resta per la ripresa
        self.destroy()


class FinestraPulizia(tk.Toplevel):
    """B2g — Modalita' pulita "🧹 Pulisci hardware": processi che occupano
    VRAM/RAM con guadagno stimato, selezione a checkbox, conferma esplicita
    ("i dati non salvati andranno persi"), chiusura gentile dei soli PID
    selezionati, ri-misura del guadagno reale e ricalcolo delle proposte.
    Mai chiusura automatica; i processi protetti (sistema/python) non sono
    selezionabili."""

    def __init__(self, master, al_termine=None):
        super().__init__(master)
        self.app = master
        self.al_termine = al_termine
        self._checkbox = {}   # pid -> BooleanVar
        self._voci = {}       # pid -> voce
        self.title("TRILogos — " + TESTI[master.lingua]["pul_titolo"])
        self.geometry("720x620")
        self.configure(bg=PALETTE["sfondo"])
        self.transient(master)
        self._costruisci()
        self._aggiorna()

    def _t(self, chiave):
        return TESTI[self.app.lingua][chiave]

    def _costruisci(self):
        header = tk.Frame(self, bg=PALETTE["sfondo"])
        header.pack(fill="x", padx=12, pady=(12, 2))
        Pill(header, testo="  TRILogos  ").pack(side="left")
        tk.Label(header, text=self._t("pul_titolo"), bg=PALETTE["sfondo"],
                 fg=PALETTE["ambra"], font=FONT_H).pack(side="left", padx=10)
        tk.Label(self, text=self._t("pul_spiega"), bg=PALETTE["sfondo"],
                 fg=PALETTE["secondario"], font=("Segoe UI", 9),
                 anchor="w", justify="left", wraplength=680).pack(fill="x", padx=14)
        # P1-B (collaudo B2rev): lista processi in canvas scrollabile, cosi' i
        # pulsanti inferiori restano sempre raggiungibili con molte righe.
        self._canvas_corpo = tk.Canvas(self, bg=PALETTE["sfondo"],
                                       highlightthickness=0)
        self._sb_corpo = tk.Scrollbar(self, orient="vertical",
                                      command=self._canvas_corpo.yview)
        self._canvas_corpo.configure(yscrollcommand=self._sb_corpo.set)
        self._sb_corpo.pack(side="right", fill="y", padx=(0, 4))
        self._canvas_corpo.pack(side="top", fill="both", expand=True,
                                padx=(14, 0), pady=6)
        self._corpo = tk.Frame(self._canvas_corpo, bg=PALETTE["sfondo"])
        self._win_corpo = self._canvas_corpo.create_window(
            (0, 0), window=self._corpo, anchor="nw")
        self._corpo.bind(
            "<Configure>",
            lambda e: self._canvas_corpo.configure(
                scrollregion=self._canvas_corpo.bbox("all")))
        self._canvas_corpo.bind(
            "<Configure>",
            lambda e: self._canvas_corpo.itemconfigure(
                self._win_corpo, width=e.width))
        self._canvas_corpo.bind(
            "<MouseWheel>",
            lambda e: self._canvas_corpo.yview_scroll(
                -1 if e.delta > 0 else 1, "units"))
        self._lbl_guadagno = tk.Label(self, text="", bg=PALETTE["sfondo"],
                                      fg=PALETTE["ambra"], font=FONT_B, anchor="w")
        self._lbl_guadagno.pack(fill="x", padx=14)
        self._lbl_esito = tk.Label(self, text="", bg=PALETTE["sfondo"],
                                   fg=PALETTE["verde"], font=("Segoe UI", 9),
                                   anchor="w", justify="left", wraplength=680)
        self._lbl_esito.pack(fill="x", padx=14)
        self._lbl_reale = tk.Label(self, text="", bg=PALETTE["sfondo"],
                                   fg=PALETTE["ambra"], font=FONT_B,
                                   anchor="w", justify="left", wraplength=680)
        self._lbl_reale.pack(fill="x", padx=14)
        fondo = tk.Frame(self, bg=PALETTE["sfondo"])
        fondo.pack(fill="x", padx=12, pady=(6, 10), side="bottom")
        PulsanteRotondo(fondo, testo=self._t("pul_aggiorna"),
                        comando=self._aggiorna).pack(side="left")
        PulsanteRotondo(fondo, testo=self._t("pul_chiudi_sel"),
                        comando=self._chiudi_selezionati).pack(side="left", padx=8)
        PulsanteRotondo(fondo, testo=self._t("pul_annulla"),
                        comando=self.destroy).pack(side="right")

    # ---- analisi ----
    def _aggiorna(self):
        for figlio in self._corpo.winfo_children():
            figlio.destroy()
        self._checkbox.clear()
        self._voci.clear()
        self._lbl_esito.configure(text="")
        self._lbl_reale.configure(text="")
        threading.Thread(target=self._lavoro_analizza, daemon=True).start()

    def _lavoro_analizza(self):
        dati = _pulizia.analizza()
        self.app._ui(self._mostra, dati)

    def _mostra(self, dati):
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        if not dati["processi"]:
            tk.Label(self._corpo, text=self._t("pul_nessun_proc"),
                     bg=PALETTE["sfondo"], fg=PALETTE["secondario"],
                     font=("Segoe UI", 9)).pack(anchor="w")
            return
        for voce in dati["processi"]:
            self._voci[voce["pid"]] = voce
            riga = tk.Frame(self._corpo, bg=PALETTE["pannello"])
            riga.pack(fill="x", pady=1)
            var = tk.BooleanVar(value=False)
            if voce["protetto"]:
                casella = tk.Checkbutton(
                    riga, text="", variable=var, state="disabled",
                    bg=PALETTE["pannello"], activebackground=PALETTE["pannello"],
                    selectcolor=PALETTE["campo"], highlightthickness=0)
            else:
                casella = tk.Checkbutton(
                    riga, text="", variable=var, command=self._aggiorna_guadagno,
                    bg=PALETTE["pannello"], activebackground=PALETTE["pannello"],
                    selectcolor=PALETTE["campo"], highlightthickness=0)
            casella.pack(side="left", padx=4)
            self._checkbox[voce["pid"]] = var
            vram = (f"{voce['vram_mib']} MiB" if voce["vram_mib"] is not None
                    else self._t("pul_nd"))
            ram = (f"{voce['ram_mib']} MiB" if voce["ram_mib"] is not None
                   else self._t("pul_nd"))
            testo = (f"{voce['nome']} (PID {voce['pid']}) · VRAM {vram} · RAM {ram}")
            if voce["protetto"]:
                testo += f" · {self._t('pul_protetto')}: {voce['motivo']}"
            lbl = tk.Label(riga, text=testo, bg=PALETTE["pannello"], fg=PALETTE["testo"],
                           font=("Segoe UI", 9), anchor="w", justify="left")
            lbl.pack(side="left", fill="x", expand=True, padx=6, pady=3)
            # P4-3: la rotella sopra le righe deve scorrere la lista
            for w in (riga, casella, lbl):
                w.bind("<MouseWheel>", self._wheel_corpo)
        self._aggiorna_guadagno()

    def _wheel_corpo(self, e):
        """P4-3: scroll della lista processi con la rotella."""
        self._canvas_corpo.yview_scroll(-1 if e.delta > 0 else 1, "units")
        return "break"

    def _aggiorna_guadagno(self):
        totale = 0
        for pid, var in self._checkbox.items():
            voce = self._voci.get(pid)
            if var.get() and voce is not None:
                totale += voce["guadagno_mib"]
        self._lbl_guadagno.configure(
            text=self._t("pul_guadagno").format(mib=totale))

    # ---- chiusura con conferma ----
    def _chiudi_selezionati(self):
        selezionati = [pid for pid, var in self._checkbox.items()
                       if var.get() and not self._voci.get(pid, {}).get("protetto")]
        if not selezionati:
            self._lbl_esito.configure(text=self._t("pul_nessuno_sel"))
            return
        from tkinter import messagebox
        conferma = messagebox.askyesno(
            self._t("pul_conferma_titolo"),
            self._t("pul_conferma").format(n=len(selezionati)),
            parent=self)
        if not conferma:
            return  # annulla: nessuna chiusura
        self._lbl_esito.configure(text="…")
        threading.Thread(target=self._lavoro_chiudi, args=(selezionati,),
                         daemon=True).start()

    def _lavoro_chiudi(self, pid_list):
        prima = _profiler.rileva()
        esiti = _pulizia.chiudi(pid_list)
        time.sleep(1.0)  # il driver aggiorna la VRAM dopo la chiusura
        profilo = _profiler.rileva()
        self.app._ui(self._dopo_chiusura, esiti, prima, profilo)

    def _dopo_chiusura(self, esiti, prima, profilo):
        chiusi = sum(1 for e in esiti if e["esito"] == "chiuso")
        non_term = sum(1 for e in esiti if e["esito"] == "non termina")
        protetti = sum(1 for e in esiti if e["esito"] == "protetto")
        self._aggiorna()  # ricarica la lista (reset sincrono delle label)
        self._lbl_esito.configure(
            text=self._t("pul_esito").format(n=chiusi, k=non_term, p=protetti))
        if prima.vram_libera_mib is not None and profilo.vram_libera_mib is not None:
            delta = profilo.vram_libera_mib - prima.vram_libera_mib
            self._lbl_reale.configure(
                text=self._t("pul_guadagno_reale").format(
                    prima=prima.vram_libera_mib, dopo=profilo.vram_libera_mib,
                    delta=delta))
        if self.al_termine is not None:
            try:
                self.al_termine(profilo)
            except Exception:
                pass


class FinestraAgenti(tk.Toplevel):
    """B3 — Squadra di ricerca: agenti creati, confidenza per iterazione e log.
    Testi readonly selezionabili e copiabili (requisito A8); aggiornamenti in
    tempo reale via evento() chiamato dal main thread (coda UI)."""

    def __init__(self, master):
        super().__init__(master)
        self.app = master
        self.title("TRILogos — Squadra di ricerca")
        self.geometry("620x520")
        self.configure(bg=PALETTE["sfondo"])
        self.transient(master)
        header = tk.Frame(self, bg=PALETTE["sfondo"])
        header.pack(fill="x", padx=12, pady=(12, 2))
        Pill(header, testo="  TRILogos  ").pack(side="left")
        tk.Label(header, text="Squadra di ricerca", bg=PALETTE["sfondo"],
                 fg=PALETTE["ambra"], font=FONT_H).pack(side="left", padx=10)
        self._aree = {}
        self._area("Agenti", 6)
        self._area("Confidenza", 5)
        self._area("Log", 7)
        self._scrivi(self._aree["Log"],
                     "Nessuna ricerca in corso. Attiva il profilo Ricerca e premi "
                     "▶ Avvia (completo): qui vedrai agenti, confidenza e log in "
                     "tempo reale.")
        fondo = tk.Frame(self, bg=PALETTE["sfondo"])
        fondo.pack(fill="x", padx=12, pady=(6, 10), side="bottom")
        PulsanteRotondo(fondo, testo="✖ Chiudi", comando=self.destroy).pack(side="right")

    def _area(self, titolo, righe):
        tk.Label(self, text=titolo, bg=PALETTE["sfondo"], fg=PALETTE["secondario"],
                 font=FONT_B, anchor="w").pack(fill="x", padx=14, pady=(6, 0))
        t = tk.Text(self, height=righe, bg=PALETTE["campo"], fg=PALETTE["testo"],
                    wrap="word", font=("Consolas", 9), relief="flat",
                    insertwidth=0, highlightthickness=0)
        t.pack(fill="both", expand=True, padx=14)
        t.bind("<Key>", lambda e: "break")  # sola lettura: digitazione bloccata
        menu = tk.Menu(t, tearoff=0)
        menu.add_command(label="Copia", command=lambda: self._copia(t))
        menu.add_command(label="Seleziona tutto",
                         command=lambda: (t.tag_add("sel", "1.0", "end"),
                                          t.focus_set()))
        t.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))
        self._aree[titolo] = t
        return t

    def _copia(self, t):
        try:
            testo = t.get("sel.first", "sel.last")
        except tk.TclError:
            testo = t.get("1.0", "end")
        try:
            self.clipboard_clear()
            self.clipboard_append(testo)
        except tk.TclError:
            pass

    def _scrivi(self, area, testo):
        try:
            area.insert("end", testo + "\n")
            area.see("end")
        except tk.TclError:
            pass

    def pulisci(self):
        """P4-5: svuota le tre aree (chiamata da Svuota)."""
        for area in self._aree.values():
            try:
                area.delete("1.0", "end")
            except tk.TclError:
                pass

    def evento(self, tipo, dati):
        """Aggiornamenti in tempo reale (main thread)."""
        if tipo == "piano" and dati.get("piano"):
            for ag in dati["piano"].get("agenti", []):
                self._scrivi(self._aree["Agenti"],
                             f"• {ag.get('nome')} — {ag.get('specialita')}: "
                             f"{ag.get('obiettivo')}")
        elif tipo == "agente":
            self._scrivi(self._aree["Log"],
                         f"[{dati.get('stato')}] {dati.get('nome')} "
                         f"{dati.get('esito', '')}")
        elif tipo == "iterazione":
            vals = " · ".join(f"{v['voce']}:{v['punteggio']:.2f}"
                              for v in dati.get("valutazioni", []))
            self._scrivi(self._aree["Confidenza"],
                         f"Iterazione {dati.get('numero')}: confidenza "
                         f"{dati.get('confidenza', 0):.2f}/10 ({vals})")
        elif tipo == "fase":
            self._scrivi(self._aree["Log"], f"— {dati.get('nome')} —")
        elif tipo == "avviso":
            self._scrivi(self._aree["Log"], f"⚠ {dati.get('testo', '')}")
        elif tipo == "salvato":
            self._scrivi(self._aree["Log"], f"salvato: {dati.get('percorso', '')}")


# A13 — contatore tok/s: intervallo di refresh (2 Hz, un solo after pendente).
_TOK_INTERVALLO = 0.5


class TrilogoApp(Finestra):
    def __init__(self):
        # Finestra 1200×862: +142px in altezza per la zona C doppia (284px).
        super().__init__(f"{TESTI['it']['titolo']}  ·  v{VERSIONE}",
                         larghezza=1200, altezza=862)
        # Riferimento all'header interno (label est di LabGUI) per la lingua (F4-E)
        self._lbl_titolo_est = None
        for _w in self.est.winfo_children():
            if isinstance(_w, ttk.Label):
                self._lbl_titolo_est = _w
                break
        # Migrazione una tantum dei flag runtime da config.json a stato.json
        # (file locale gitignored): PRIMA di leggere splash e primo flusso.
        _stato.migra_da_config(CONFIG)
        self.lingua = "it"
        self._ultima_domanda = ""
        # Clienti BASE senza rete: la prima finestra appare subito; il
        # rilevamento completo gira in un thread e aggiorna i menu a fine probe.
        self.clienti = clienti_base()
        self.opzioni = self._voci_menu()
        # Voce C dalla config (voce_c=None): mai "mock" implicito all'avvio.
        _timeout, _avviso_timeout = _timeout_rete()
        self.canale = costruisci_canale(self.lingua, voce_c=None,
                                        clienti=self.clienti, timeout=_timeout)
        self.dibattito_risultato = None
        self._busy = False
        self._messaggio_finale = None
        self.ultimo_verdetto = ""
        self.ultimo_finale = ""
        self.ultimo_punti = ""
        self._rigiri = 0
        self._profilo_attivo = next(iter(CONFIG["profili"]))
        self._preset_attivo = False
        # A12: True mentre "Svuota" è mostrato come "Interrompi" (elaborazione)
        self._interrompi_attivo = False
        self._chiusa = False
        # V6: warmup in background dei soli modelli lenti (uno grande alla volta).
        self._warmup = {}           # nome modello -> "in_corso"|"pronto"|"fallito"
        self._warmup_thread = None  # thread del warmup attivo (attesa del flusso)
        # Status bar COMPOSTA (F5-A): messaggio di stato + cronometro. Il
        # cronometro vive qui: la banda SUPERVISORE è stata rimossa dalla zona A.
        self._stato_testo = ""
        self._stato_colore = PALETTE["secondario"]
        self._crono = {"passo": None, "durata": None, "totale": None}
        # A13: contatore tok/s (modulo puro core\metro.py; la UI è toccata solo
        # sul main thread, il worker alimenta il metro via _flusso).
        self._metro = MisuratoreTok()
        self._tok_lock = threading.Lock()
        self._tok_after_id = None        # id dell'after di refresh pendente
        self._tok_after_pendente = False
        self._tok_ultimo_refresh = 0.0
        self._tok_fine_passo = False     # True tra fine passo e il successivo
        self._tok_out0 = 0               # token out a inizio passo (delta usage)
        # A13 rev. 17.1: base congelata del totale di sessione Σ (in+out reali
        # catturati a inizio passo; la stima del passo in corso si somma sopra).
        self._tok_sigma_base = 0
        self._costruisci()
        if _avviso_timeout:
            self.stato(_avviso_timeout)
        try:
            _percorso_ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icona_trilogos.ico")
            self.iconbitmap(bitmap=_percorso_ico)
            self.iconbitmap(default=_percorso_ico)
        except Exception:
            pass
        self._coda_ui = queue.Queue()
        self.after(50, self._sonda_ui)
        self._applica_lingua()
        if _AVVISO_PROFILI_LEGACY:
            self.stato(_AVVISO_PROFILI_LEGACY)
        self._init_perimetro()
        self.spinner = self._spinner_localizzato
        self.bind("<Escape>", lambda e: self._annulla())
        self.protocol("WM_DELETE_WINDOW", self._chiusura)
        # SPLASH BYOK al primo avvio (flag byok_splash assente in stato.json):
        # Toplevel non bloccante, la finestra principale resta operativa.
        # NESSUN focus_force né topmost: il Toplevel appare sopra la principale
        # da solo, senza rubare il focus ai click dell'utente (e ai test GUI).
        self._splash = SplashByok(self) if not _stato.leggi().get("byok_splash") else None
        # Rilevamento clienti in background: a fine probe il risultato torna sul
        # main thread via coda UI (_applica_clienti_rilevati), mai tk da thread
        # non-main; errore -> messaggio di stato, mai crash.
        threading.Thread(target=self._rileva_clienti_bg, daemon=True).start()
        # V6: warmup automatico all'avvio (dopo il primo render; non blocca la UI).
        self.after(300, self._avvia_warmup)
        # B2e: primo avvio guidato se il motore interno non ha modelli.
        self.after(800, self._avvio_guidato_se_serve)

    def _rileva_clienti_bg(self):
        """Probe dei clienti (rete) FUORI dal thread UI: la finestra è già
        visibile e reattiva. Il risultato (o l'errore) viene accodato sul main
        thread con _ui."""
        try:
            clienti = rileva_clienti()
        except Exception as e:
            self._ui(self.stato, f"rilevamento clienti non riuscito: {e}")
            return
        self._ui(self._applica_clienti, clienti)

    def _applica_clienti(self, clienti):
        """Aggiorna clienti/opzioni, i values delle tre combo e riallinea le
        selezioni al canale (fonte di verità) via _voce_canale: un eventuale
        cambio modello dell'utente è preservato. Gira sul main thread (via _ui)."""
        self.clienti = clienti
        self.opzioni = self._voci_menu()
        for combo in (self.c_a.combo, self.c_b.combo, self.c_c.combo):
            combo.configure(values=self.opzioni)
        self.c_a.combo.set(self._voce_canale(self.canale.A))
        self.c_b.combo.set(self._voce_canale(self.canale.B))
        c_terzo = getattr(self.canale, "C", None)
        if c_terzo is not None:
            self.c_c.combo.set(self._voce_canale(c_terzo))

    def _spinner_localizzato(self, attivo=True):
        """Spinner localizzato: passa dal metodo stato() COMPOSTO, così il
        cronometro resta visibile nella status bar anche durante l'attesa."""
        self.stato("in elaborazione …" if attivo else TESTI[self.lingua]["pronto"],
                   PALETTE["ambra"] if attivo else None)

    def stato(self, testo, colore=None):
        """Status bar COMPOSTA (F5-A): messaggio di stato e cronometro condividono
        la stessa riga in basso ('messaggio · ⏱ passo · passo Xs · totale Ys').
        Sovrascrive Finestra.stato: ogni scrittura ricompone la riga intera."""
        self._stato_testo = testo
        self._stato_colore = colore or PALETTE["secondario"]
        self._aggiorna_status()

    def _aggiorna_status(self):
        """Ricompone la status bar. Gira sul main thread (o via _ui dai worker):
        tk non è thread-safe."""
        crono = self._componi_crono()
        testo = f"{self._stato_testo}  ·  {crono}" if self._stato_testo else crono
        tok = self._componi_tok()
        if tok:
            testo += f"  ·  {tok}"
        try:
            self._status.configure(text=testo, fg=self._stato_colore)
        except tk.TclError:
            pass
        # P1-A (collaudo F4): il configure del Label padre perde il paint dei
        # figli place(): riposizionali a ogni scrittura di stato (ri-place
        # immediato = restano sempre visibili, nessun lampeggio).
        self._riposiziona_status()

    def _componi_crono(self):
        """Testo del cronometro per la status bar, NELLA LINGUA ATTIVA (F4-E):
        a riposo '⏱ 0.0s · in attesa'; in corso '⏱ passo'; a passo finito
        '⏱ passo · passo Xs · totale Ys'. Nessun troncamento."""
        c = self._crono
        t = TESTI[self.lingua]
        if c.get("passo") is None:
            return f"⏱ 0.0s · {t['crono_attesa']}"
        if c.get("durata") is None:
            return f"⏱ {c['passo']}"
        return (f"⏱ {c['passo']} · {t['crono_passo']} {c['durata']:.1f}s"
                f" · {t['crono_totale']} {c['totale']:.1f}s")

    def _aggiorna_perimetro_ui(self):
        """Segmento DESTRO della status bar (A9): cartella progetto fissa +
        (B2e) stato del motore interno: '📁 progetto: X · ⚙ motore: N · llama.cpp ok'."""
        nome = perimetro.nome()
        testo = f"📁 progetto: {nome}" if nome else "📁 progetto: (non scelta)"
        testo += f"  ·  {self._stato_motore()}"
        try:
            self._lbl_perimetro.configure(text=testo)
        except tk.TclError:
            pass

    def _riposiziona_status(self):
        """P1-A (collaudo B2rev): forza il ridisegno dei widget place() della
        status bar (cartella progetto + Pulisci HW) quando la barra ottiene la
        larghezza reale: al primo render possono non disegnarsi."""
        for w, x in ((self._lbl_perimetro, -104), (self._btn_pul_status, -6)):
            try:
                w.place_configure(relx=1.0, rely=1.0, anchor="se", x=x, y=-4)
                w.lift()
            except tk.TclError:
                pass

    def _stato_motore(self):
        """B2e: indicatore del motore interno per la status bar."""
        n = len(_motore.modelli_locali())
        lc = (TESTI[self.lingua]["motore_ok"] if _motore.llama_disponibile()
              else TESTI[self.lingua]["motore_assente"])
        return TESTI[self.lingua]["motore_stato"].format(n=n, lc=lc)

    def _voci_menu(self):
        """Voci dei menu modelli: client esterni (con etichetta di lentezza) +
        (B2e) modelli del motore interno, nella lingua attiva."""
        voci = _opzioni_etichettate(voci_modelli(self.clienti), self.lingua)
        tag = TESTI[self.lingua]["motore_tag"]
        voci += [_motore.nome_voce(percorso, tag)
                 for percorso, _nome in _motore.modelli_locali()]
        return voci

    def _aggiorna_voci_modelli(self):
        """B2e: ricalcola le voci e le applica alle tre combo (dopo un download)."""
        self.opzioni = self._voci_menu()
        for combo in (self.c_a.combo, self.c_b.combo, self.c_c.combo):
            try:
                combo.configure(values=self.opzioni)
            except tk.TclError:
                pass
        self._aggiorna_perimetro_ui()

    def _avvio_guidato_se_serve(self):
        """B2e: mostra la guidata all'avvio quando il motore interno non ha
        modelli (non blocca la UI; una sola finestra per volta)."""
        if self._chiusa:
            return
        if _motore.modelli_locali():
            return
        self._apri_avvio_guidato()

    def _apri_avvio_guidato(self):
        """B2e: apre (o riporta in primo piano) la finestra guidata del motore."""
        guidata = getattr(self, "_guidata", None)
        if guidata is not None:
            try:
                if guidata.winfo_exists():
                    guidata.lift()
                    return
            except tk.TclError:
                pass
        self._guidata = FinestraAvvioGuidato(self)

    def _apri_pulizia_hw(self):
        """B2g: modalita' pulita anche da Opzioni/status bar; a fine pulizia
        aggiorna stato motore e status bar (nessun ricalcolo proposte)."""
        fin = getattr(self, "_pulizia_fin", None)
        if fin is not None:
            try:
                if fin.winfo_exists():
                    fin.lift()
                    return
            except tk.TclError:
                pass
        self._pulizia_fin = FinestraPulizia(
            self, al_termine=lambda profilo: self._aggiorna_perimetro_ui())

    def _garanzia_motore(self):
        """B2f: se il canale usa voci del motore interno ma llama.cpp non è
        disponibile o un modello è sparito, avvisa e riporta il canale ai
        client esterni (nessuna rottura del flusso). True se il canale è ok."""
        voci = []
        for polo in ("A", "B", "C"):
            modello = getattr(self.canale, polo, None)
            if isinstance(modello, _motore.ModelloMotore):
                voci.append((polo, modello))
        if not voci:
            return True
        problemi = []
        if not _motore.llama_disponibile():
            problemi.append("llama.cpp assente")
        for polo, modello in voci:
            if not os.path.isfile(modello.percorso):
                problemi.append(f"{polo}: modello mancante "
                                f"({os.path.basename(modello.percorso)})")
        if not problemi:
            return True
        avviso = ("⚠ motore interno non disponibile (" + "; ".join(problemi)
                  + "): il flusso usa i client esterni")
        self.stato(avviso)
        self._ricostruisci_canale_esterno(avviso)
        return False

    def _ricostruisci_canale_esterno(self, avviso=""):
        """B2f: canale dai modelli di config (client esterni), profilo/lingua
        invariati; l'avviso resta visibile in zona C."""
        try:
            self.canale = costruisci_canale(
                self.lingua, profilo=self._profilo_attivo, voce_c=None,
                clienti=self.clienti, timeout=_timeout_rete()[0])
        except Exception as e:
            self.stato(f"ERRORE fallback client esterni: {e}")
            return
        self.dibattito_risultato = None
        self._svuota()
        self.c_a.combo.set(self._voce_canale(self.canale.A))
        self.c_b.combo.set(self._voce_canale(self.canale.B))
        c_terzo = getattr(self.canale, "C", None)
        if c_terzo is not None:
            self.c_c.combo.set(self._voce_canale(c_terzo))
        if avviso:
            self.c_finale.scrivi(avviso)

    def _tooltip_progetto(self):
        """Testo del tooltip del pulsante 📁 (localizzato, F4-E): percorso completo."""
        t = TESTI[self.lingua]
        percorso = perimetro.leggi()
        return t["tt_progetto"].format(p=percorso) if percorso else t["tt_progetto_non"]

    def _init_perimetro(self):
        """All'avvio: avvisa se la cartella salvata non esiste più e aggiorna il
        segmento destro della status bar."""
        salvata = _stato.leggi().get(perimetro.CHIAVE)
        if salvata and perimetro.leggi() is None:
            self.stato("⚠ cartella progetto non più esistente: scegline una con 📁 Progetto")
        self._aggiorna_perimetro_ui()

    def _annulla(self):
        if self._busy:
            # FIX: annullamento immediato (chiude anche le response HTTP in attesa)
            self.canale.annulla_tutto()
            self.stato("⏹ annullamento in corso …")

    def _chiusura(self):
        if self._busy:
            from tkinter import messagebox
            if messagebox.askyesno("TRILogos", "Elaborazione in corso: interrompere e chiudere?"):
                self.canale.annulla_tutto()
                _motore.ferma_tutti()  # B2f: nessun llama-server orfano
                self._chiusa = True
                self.destroy()
            return
        _motore.ferma_tutti()  # B2f: stop pulito dei server motore
        self._chiusa = True
        self.destroy()

    def _inizia_lavoro(self):
        if self._busy:
            return False
        self.canale.annulla = False
        self._busy = True
        # A13: nuovo flusso -> metro azzerato, segmento tok/s da '⚡ …'
        self._tok_reset()
        for chiave in self.bottoni:
            # B3 rev. (N47): "agenti" resta attivo durante la ricerca: il
            # pannello serve proprio mentre gli agenti lavorano.
            if chiave == "agenti":
                continue
            self.bottoni[chiave].configure(state="disabled")
        # A12: "Svuota" diventa "Interrompi" (stesso posto/larghezza, resta
        # attivo; comando identico a Esc). A fine lavoro torna "Svuota".
        self._interrompi_attivo = True
        self.bottoni["svuota"].configure(text=TESTI[self.lingua]["interrompi"],
                                         command=self._annulla, state="normal")
        self.spinner(True)
        self.update_idletasks()
        return True

    def _fine_lavoro(self):
        if self._chiusa:
            return
        # B2f: stop pulito dei server motore a fine flusso (VRAM/RAM liberate)
        try:
            _motore.ferma_tutti()
        except Exception:
            pass
        self._busy = False
        # A13: fine lavoro (o annullo) -> il segmento tok/s sparisce.
        self._tok_reset()
        for chiave in self.bottoni:
            self.bottoni[chiave].configure(state="normal")
        # A12: il pulsante contestuale torna "Svuota" (testo e comando originali)
        if getattr(self, "_interrompi_attivo", False):
            self._interrompi_attivo = False
            self.bottoni["svuota"].configure(text=TESTI[self.lingua]["svuota"],
                                             command=self._svuota)
        if self.canale.annulla:
            # F4-E: dopo un annullo (Esc) il cronometro torna a riposo
            self.canale.annulla = False
            self._reset_cronometro()
        if self._messaggio_finale:
            self.stato(self._messaggio_finale)
            self._messaggio_finale = None
        else:
            self.spinner(False)

    def _costruisci(self):
        # LAYOUT TRIVOICE: zona A (barra SUPERVISORE 84px) + zona B (riga 4 riquadri 420px)
        # + zona C (risposta univoca 284px); totali: 84 + 420 + 284 + 12 (pady) = 800.
        # Dimensioni esatte via minsize delle righe/colonne (i frame con figli
        # non possono forzare la propria size: la richiesta resta quella dei figli).
        self.contenuto.grid_columnconfigure(0, weight=1)
        self.contenuto.grid_rowconfigure(0, weight=0, minsize=88)   # cella 88 = 84 + pady 4
        self.contenuto.grid_rowconfigure(1, weight=1)
        self.contenuto.grid_rowconfigure(2, weight=0, minsize=288)  # cella 288 = 284 + pady 4
        self.contenuto.bind("<Configure>", self._adatta_quadri)

        # ZONA A — barra SUPERVISORE (84px, full width, senza pulsanti):
        # banda/pill rimossa (F5-A), il campo di input occupa TUTTO lo spazio;
        # cronometro e stato del flusso vivono nella status bar in basso.
        self._zona_a = RiquadroRotondo(self.contenuto, bg=PALETTE["sfondo"])
        self._zona_a.grid(row=0, column=0, sticky="nsew", pady=2)
        self._bw_supervisore = BoxArrotondato(self._zona_a.frame, altezza_righe=3, editabile=True)
        self.supervisore = self._bw_supervisore.box
        self._bw_supervisore.pack(fill="both", expand=True, padx=2, pady=2)

        self.supervisore.bind("<Return>", self._invio_supervisore)
        self.supervisore.bind("<FocusIn>", self._focus_supervisore)
        self.supervisore.bind("<FocusOut>", self._blur_supervisore)
        # N47 06/10/2026 (fix Svuota): al primo tasto o incolla il placeholder
        # sparisce PRIMA dell'inserimento (il binding del widget precede quello
        # di classe): la nuova domanda non si mescola mai al placeholder.
        self.supervisore.bind("<KeyPress>", self._primotasto_supervisore)
        self.supervisore.bind("<<Paste>>", self._primotasto_supervisore)
        self._metti_placeholder()

        # ZONA B — riga dei 4 riquadri (420px): GRID a 6 colonne (weight 0,1,1,1)
        self._zona_b = RiquadroRotondo(self.contenuto, bg=PALETTE["sfondo"])
        self._zona_b.grid(row=1, column=0, sticky="nsew", pady=2)
        self._zona_b.frame.grid_rowconfigure(0, weight=1, minsize=420)
        # celle: col0 203 (200 + padx 3), LLM 327 (325 + padx 2): totale 1184 esatto
        self._zona_b.frame.grid_columnconfigure(0, weight=0, minsize=223)
        for i in (1, 2, 3):
            self._zona_b.frame.grid_columnconfigure(i, weight=1, minsize=320)

        # Riquadro 1 — PULSANTI (200px): riga combo LINGUA+PROFILO affiancate,
        # 12 pulsanti in ordine (Correggi dopo Cross-check, prima di Salva).
        # Il contenuto vive su un canvas con scrollbar verticale SOVRAPPOSTA
        # (pattern di BoxArrotondato): visibile SOLO quando la zona B è compressa
        # (900×600: ~291px disponibili vs ~434px richiesti). A 1200×862 layout
        # invariato (200×415, nessuna scrollbar).
        self._quadro = RiquadroRotondo(self._zona_b.frame)
        self._quadro.grid(row=0, column=0, sticky="nsew", padx=(1, 2))
        self._quadro_canvas = tk.Canvas(self._quadro.frame, bg=PALETTE["pannello"],
                                        highlightthickness=0, bd=0, width=196, height=434)
        self._quadro_sb = ttk.Scrollbar(self._quadro_canvas, orient="vertical",
                                        command=self._quadro_canvas.yview)
        self._quadro_canvas.configure(yscrollcommand=self._quadro_sb.set)
        self._larghezza_sb = max(14, self._quadro_sb.winfo_reqwidth())
        self._quadro_interno = tk.Frame(self._quadro_canvas, bg=PALETTE["pannello"])
        self._quadro_item = self._quadro_canvas.create_window(
            (0, 0), window=self._quadro_interno, anchor="nw")
        self._quadro_item_sb = self._quadro_canvas.create_window(
            (0, 0), window=self._quadro_sb, anchor="ne")
        self._quadro_canvas.pack(fill="both", expand=True)
        riga_combo = tk.Frame(self._quadro_interno, bg=PALETTE["pannello"])
        riga_combo.pack(fill="x", padx=2, pady=1)
        self.combo_lingua = ComboRotonda(riga_combo, values=LINGUE, width=5)
        self.combo_lingua.current(0)
        self.combo_lingua.combo.bind("<<ComboboxSelected>>", lambda e: self._cambia_lingua())
        self.combo_lingua.pack(side="left", fill="x", expand=True, padx=(0, 1))
        self.combo_profilo = ComboRotonda(riga_combo,
                                          values=list(CONFIG["profili"].keys()), width=5)
        self.combo_profilo.set(next(iter(CONFIG["profili"])))
        self.combo_profilo.combo.bind("<<ComboboxSelected>>", lambda e: self._cambia_profilo())
        self.combo_profilo.pack(side="left", fill="x", expand=True, padx=(1, 0))
        # tooltip (A5) localizzati (F4-E): seguono la lingua attiva
        Tooltip(self.combo_lingua, lambda: TESTI[self.lingua]["tt_lingua"])
        Tooltip(self.combo_profilo,
                lambda: TESTI[self.lingua]["tt_profilo"].format(v=self.combo_profilo.get()))
        self.bottoni = {}
        self._tooltips = {}
        for chiave, w, comando in (("invia", 9, self._completo),
                                   ("completo", 15, self._completo),
                                   ("dibattito", 9, self._dibattito),
                                   ("sintesi", 9, self._sintesi),
                                   ("univoca", 9, self._univoca),
                                   ("cross", 11, self._cross_check),
                                   ("correggi", 11, self._correggi),
                                   ("salva", 9, self._salva),
                                   ("svuota", 9, self._svuota),
                                   ("cartella", 11, self._add_cartella),
                                   ("add", 8, self._add_files),
                                   ("opzioni", 10, self._opzioni),
                                   ("agenti", 10, self._apri_agenti)):
            b = PulsanteRotondo(self._quadro_interno, width=w, comando=comando)
            b.pack(fill="x", padx=6, pady=1)
            self.bottoni[chiave] = b
            self._tooltips[chiave] = Tooltip(
                b, lambda k=chiave: TESTI[self.lingua].get(
                    "tt_" + k, TESTI["en"].get("tt_" + k, "")))
        # Tooltip del pulsante Progetto: percorso completo (dinamico, A9)
        self._tooltips["cartella"].testo = self._tooltip_progetto

        # rotella del mouse sul quadro: scroll verticale del canvas (i figli del
        # frame interno sono canvas/combobox: l'evento non risale da solo)
        self._quadro_interno.bind("<Configure>", self._aggiorna_scroll_quadro)
        self._quadro_canvas.bind("<Configure>", self._allarga_quadro)
        self._quadro_canvas.bind("<MouseWheel>", self._wheel_quadro)
        # P4-1: ricalcolo dopo il primo layout (con 13 pulsanti serve la scrollbar)
        self.after(400, self._adatta_quadri)
        for w in _discendenti(self._quadro_interno):
            w.bind("<MouseWheel>", self._wheel_quadro)

        # Riquadri 2-4 — LLM1/LLM2/LLM3 (325px ciascuno, Colonna LabGUI dentro wrapper)
        self._wr_a = RiquadroRotondo(self._zona_b.frame)
        self._wr_b = RiquadroRotondo(self._zona_b.frame)
        self._wr_c = RiquadroRotondo(self._zona_b.frame)
        self._wr_a.grid(row=0, column=1, sticky="nsew", padx=(0, 2))
        self._wr_b.grid(row=0, column=2, sticky="nsew", padx=(0, 2))
        self._wr_c.grid(row=0, column=3, sticky="nsew", padx=(0, 2))
        self.c_a = Colonna(self._wr_a.frame, "LLM1", PALETTE["blu"], modelli=self.opzioni,
                           on_change=lambda v: self._cambia_modello("A", v), altezza_box=4)
        self.c_b = Colonna(self._wr_b.frame, "LLM2", PALETTE["verde"], modelli=self.opzioni,
                           on_change=lambda v: self._cambia_modello("B", v), altezza_box=4)
        self.c_c = Colonna(self._wr_c.frame, "LLM3", PALETTE["viola"], modelli=self.opzioni,
                           on_change=lambda v: self._cambia_modello("C", v), altezza_box=4)
        self.c_a.pack(fill="both", expand=True)
        self.c_b.pack(fill="both", expand=True)
        self.c_c.pack(fill="both", expand=True)
        self.c_a.combo.set(self._voce_canale(self.canale.A))
        self.c_b.combo.set(self._voce_canale(self.canale.B))
        c_terzo = getattr(self.canale, "C", None)
        if c_terzo is not None:
            self.c_c.combo.set(self._voce_canale(c_terzo))
        # tooltip (A5) sulle combo modello: valore corrente + nota lentezza (localizzati)
        for colonna, nome in ((self.c_a, "LLM1"), (self.c_b, "LLM2"), (self.c_c, "LLM3")):
            Tooltip(colonna.combo,
                    lambda n=nome, col=colonna: TESTI[self.lingua]["tt_modello"].format(
                        n=n, v=col.combo.get()))

        # ZONA C — risposta univoca (284px, full width)
        self._zona_c = RiquadroRotondo(self.contenuto, bg=PALETTE["sfondo"])
        self._zona_c.grid(row=2, column=0, sticky="nsew", pady=2)
        self.c_finale = _RiquadroFinale(self._zona_c.frame, "RISPOSTA UNIVOCA", PALETTE["viola"],
                                        "il verdetto del canale")
        self._lbl_polo = {c: c.polo for c in (self.c_a, self.c_b, self.c_c)}
        self._lbl_polo[self.c_finale] = self.c_finale.polo
        for riquadro in (self._zona_a, self._zona_b, self._quadro,
                         self._wr_a, self._wr_b, self._wr_c, self._zona_c):
            riquadro.aggiorna_req()
        # Status bar a DUE segmenti (A9): a destra la cartella progetto (fissa).
        # P1-A (collaudo F4, fix definitivo): i figli place() del Label di stato
        # NON vengono disegnati da Tk su Windows. I due widget vivono quindi come
        # figli della FINESTRA (root), ancorati in basso a destra dentro la barra.
        self._lbl_perimetro = tk.Label(self, text="", bg=PALETTE["pannello"],
                                       fg=PALETTE["secondario"], font=("Segoe UI", 9), padx=6)
        self._lbl_perimetro.place(relx=1.0, rely=1.0, anchor="se", x=-104, y=-4)
        # B2g rev.: pulsante compatto "🧹 Pulisci HW" sempre visibile in status bar
        self._btn_pul_status = tk.Label(
            self, text=TESTI[self.lingua]["pul_pulsante_breve"],
            bg=PALETTE["pannello"], fg=PALETTE["ambra"],
            font=("Segoe UI", 8, "bold"), cursor="hand2", padx=4)
        self._btn_pul_status.place(relx=1.0, rely=1.0, anchor="se", x=-6, y=-4)
        self._btn_pul_status.bind("<Button-1>", lambda e: self._apri_pulizia_hw())
        self._aggiorna_perimetro_ui()
        # riposizionamento (finestra ridimensionata / primo render)
        self.bind("<Configure>", lambda e: self._riposiziona_status(), add="+")
        self.after_idle(self._riposiziona_status)
        self.after(250, self._riposiziona_status)

    def _adatta_quadri(self, e=None):
        """Regola i minsize della riga dei riquadri: 415px (zona B reale = alt−380,
        contenuto 795px: 84 + 415 + 284 + 12); sotto soglia i riquadri LLM si
        comprimono (nessun 1x1) e il quadro pulsanti diventa scrollabile."""
        lar = self.contenuto.winfo_width()
        alt = self.contenuto.winfo_height()
        if lar < 10 or alt < 10:
            return
        if not getattr(self, "_zona_b", None):
            return
        riga_b = alt - 380  # 84 + 284 + 12 (pady delle 3 zone); tolleranza bordi finestra
        ok = lar >= 1180 and riga_b >= 415
        self._zona_b.frame.grid_rowconfigure(0, weight=1, minsize=415 if ok else 0)
        for i in (1, 2, 3):
            self._zona_b.frame.grid_columnconfigure(i, weight=1, minsize=320 if ok else 0)
        # quadro pulsanti: sempre nsew (a 900×600 resta dentro la zona B, non
        # esonda più sotto la zona C). A 1200×862 (ok) niente scrollbar e canvas
        # all'altezza del contenuto (layout invariato); sotto soglia il canvas
        # si limita allo spazio reale e la scrollbar verticale appare.
        self._quadro.grid_configure(sticky="nsew")
        # P4-1 (collaudo F4): con 13 pulsanti il contenuto eccede i 415px anche
        # a finestra piena: la scrollbar va mostrata quando la richiesta supera
        # lo spazio reale (non solo sotto soglia finestra).
        richiesta = self._quadro_interno.winfo_reqheight()
        if ok and richiesta <= riga_b:
            self._quadro_canvas.itemconfigure(self._quadro_item_sb, state="hidden")
            self._quadro_canvas.configure(height=richiesta)
        else:
            self._quadro_canvas.itemconfigure(self._quadro_item_sb, state="normal")
            self._quadro_canvas.configure(height=max(riga_b, 120))
            # P4-1 residuo: restringe il frame interno ora che la scrollbar è
            # mappata (evita la sovrapposizione traccia/pulsanti).
            self.after(30, self._allarga_quadro)

    # ---- scroll verticale del quadro pulsanti (solo quando lo spazio manca) ----
    def _aggiorna_scroll_quadro(self, e=None):
        """Scrollregion del canvas: la richiesta del frame interno (contenuto)."""
        self._quadro_canvas.configure(scrollregion=(
            0, 0, self._quadro_interno.winfo_reqwidth(),
            self._quadro_interno.winfo_reqheight()))

    def _allarga_quadro(self, e=None):
        """Allarga il window del frame interno alla larghezza utile del canvas
        (scrollbar sovrapposta al bordo destro, come BoxArrotondato)."""
        lar = self._quadro_canvas.winfo_width()
        alt = self._quadro_canvas.winfo_height()
        if lar < 10 or alt < 10:
            return
        sb = self._larghezza_sb if self._quadro_sb.winfo_ismapped() else 0
        self._quadro_canvas.itemconfigure(self._quadro_item, width=max(10, lar - sb))
        self._quadro_canvas.coords(self._quadro_item_sb, lar - 2, 2)
        self._quadro_canvas.itemconfigure(self._quadro_item_sb,
                                          height=max(10, alt - 4))

    def _wheel_quadro(self, e):
        """Rotella sul quadro pulsanti: scroll verticale SOLO se la scrollbar è
        visibile (a 1200×862 niente scroll: layout invariato)."""
        if not self._quadro_sb.winfo_ismapped():
            return "break"
        self._quadro_canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")
        return "break"

    # ---- lingua ----
    def _cambia_profilo(self):
        if self._busy:
            self.combo_profilo.set(getattr(self, "_profilo_attivo", next(iter(CONFIG["profili"]))))
            self.stato("operazione in corso: cambio profilo ignorato")
            return
        nome = self.combo_profilo.get()
        ruoli = CONFIG["profili"].get(nome)
        if not ruoli:
            return
        self._profilo_attivo = nome
        self.canale.ruolo_a = ruoli["A"]
        self.canale.ruolo_b = ruoli["B"]
        # A11: stile e formato del profilo si aggiornano subito
        self.canale.stile = (ruoli.get("stile") or "").strip()
        self.canale.formato_risposta = ruoli.get("formato_risposta") or "semplice"
        # V4: preset "Veloce" — modelli piccoli + max_turni_dibattito dedicati:
        # ricostruzione del canale. I profili senza `modelli` restano solo-ruoli.
        preset = ruoli.get("modelli")
        if preset:
            try:
                _timeout = _timeout_rete()[0]
                _ka = _keep_alive_ollama()
                _nc = _num_ctx_ollama()
                a = modello_da_voce(preset.get("A"), self.clienti, timeout=_timeout, keep_alive=_ka, num_ctx=_nc)
                b = modello_da_voce(preset.get("B"), self.clienti, timeout=_timeout, keep_alive=_ka, num_ctx=_nc)
                c = (modello_da_voce(preset.get("C"), self.clienti, timeout=_timeout, keep_alive=_ka, num_ctx=_nc)
                     if preset.get("C") else None)
                kwargs = dict(ruolo_a=ruoli["A"], ruolo_b=ruoli["B"],
                              max_turni_dibattito=ruoli.get("max_turni_dibattito",
                                                            CONFIG["canale"]["max_turni_dibattito"]),
                              soglia_convergenza=CONFIG["canale"]["soglia_convergenza"],
                              lingua=self.lingua,
                              max_chiamate=CONFIG["canale"].get("max_chiamate", 40),
                              stile=ruoli.get("stile") or "",
                              formato_risposta=ruoli.get("formato_risposta") or "semplice",
                              dibattito_parallelo=CONFIG["canale"].get("dibattito_parallelo", True),
                              limiti_token=CONFIG["canale"].get("limiti_token"))
                if SUPPORTA_C:
                    kwargs[_PARAM_C] = c
                    if "C" in ruoli and _supporta(Canale.__init__, "ruolo_c"):
                        kwargs["ruolo_c"] = ruoli["C"]
                if CONFIG["canale"].get("soglie") and SUPPORTA_SOGLIE:
                    kwargs["soglie"] = CONFIG["canale"]["soglie"]
                self.canale = Canale(a, b, **kwargs)
                self.dibattito_risultato = None
                self._svuota()
                self.c_a.combo.set(self._voce_canale(self.canale.A))
                self.c_b.combo.set(self._voce_canale(self.canale.B))
                c_terzo = getattr(self.canale, "C", None)
                if c_terzo is not None:
                    self.c_c.combo.set(self._voce_canale(c_terzo))
                self._preset_attivo = True
                _motore.ferma_server_non_usati(self.canale)
                self._avvia_warmup()
            except Exception as e:
                self.stato(f"ERRORE preset '{nome}': {e}")
                return
        elif getattr(self, "_preset_attivo", False):
            # Uscita dal preset: ripristina i turni standard del config (i modelli
            # restano quelli mostrati nei menu: WYSIWYG).
            self.canale.max_turni = CONFIG["canale"]["max_turni_dibattito"]
            self._preset_attivo = False
        self.stato(f"profilo ruoli: {nome}" + (" (preset Veloce)" if preset else ""))

    def _cambia_lingua(self):
        if self._busy:
            indietro = [k for k, v in _MAPPA_LINGUE.items() if v == self.lingua]
            self.combo_lingua.set(indietro[0] if indietro else "Italiano")
            self.stato("operazione in corso: cambio lingua ignorato")
            return
        self.lingua = _MAPPA_LINGUE.get(self.combo_lingua.get(), "en")
        self.canale.lingua = self.lingua
        self._applica_lingua()

    def _applica_lingua(self):
        t = TESTI[self.lingua]
        self.title(f"{t['titolo']}  ·  v{VERSIONE}")
        if self._lbl_titolo_est is not None:
            # F4-E: anche l'header interno segue la lingua (non solo il titolo)
            self._lbl_titolo_est.configure(text=f"{t['titolo']}  ·  v{VERSIONE}")
        self._reset_cronometro()
        # Menu modelli rigenerati NELLA LINGUA ATTIVA (suffisso di lentezza
        # tradotto) e selezioni riallineate al canale (fonte di verità).
        self.opzioni = self._voci_menu()
        for combo in (self.c_a.combo, self.c_b.combo, self.c_c.combo):
            combo.configure(values=self.opzioni)
        self.c_a.combo.set(self._voce_canale(self.canale.A))
        self.c_b.combo.set(self._voce_canale(self.canale.B))
        c_terzo = getattr(self.canale, "C", None)
        if c_terzo is not None:
            self.c_c.combo.set(self._voce_canale(c_terzo))
        for chiave in ("invia", "completo", "dibattito", "sintesi", "univoca", "cross",
                       "correggi", "salva", "svuota", "cartella", "add", "opzioni",
                       "agenti"):
            if chiave == "svuota" and getattr(self, "_interrompi_attivo", False):
                continue  # A12: durante l'elaborazione resta "Interrompi"
            self.bottoni[chiave].configure(
                text=t.get(chiave, TESTI["en"].get(chiave, chiave)))
        # B2g rev.: pulsante compatto in status bar (lingua attiva)
        try:
            self._btn_pul_status.configure(text=t["pul_pulsante_breve"])
        except (tk.TclError, AttributeError):
            pass
        self.c_finale.descrizione(t["descr_finale"])
        # headers tradotti (nessuna cancellazione: il contenuto delle colonne si conserva)
        for c, nome in ((self.c_a, t["llm1"]), (self.c_b, t["llm2"]),
                        (self.c_c, t["llm3"]), (self.c_finale, t["finale"])):
            self._lbl_polo[c].configure(text=f"  {nome}  ")
        if self._e_placeholder():
            self._metti_placeholder()
        else:
            for ph in TESTI.values():
                if self.supervisore.get("1.0", "end").strip() == ph["placeholder"]:
                    self._metti_placeholder()
                    break
        self.stato(t["pronto"])

    # ---- supervisore (barra A) ----
    def _metti_placeholder(self):
        self.supervisore.delete("1.0", "end")
        self.supervisore.insert("1.0", TESTI[self.lingua]["placeholder"])
        self.supervisore.tag_add("ph", "1.0", "end")
        self.supervisore.tag_configure("ph", foreground=PALETTE["secondario"])

    def _e_placeholder(self):
        return self.supervisore.get("1.0", "end").strip() == TESTI[self.lingua]["placeholder"]

    def _focus_supervisore(self, e=None):
        if self._e_placeholder():
            self.supervisore.delete("1.0", "end")

    def _primotasto_supervisore(self, e=None):
        """Fix N47 06/10/2026: prima digitazione (o incolla) col placeholder
        visibile -> il placeholder viene cancellato PRIMA che il testo venga
        inserito. Serve quando il FocusIn non scatta (il campo ha già il focus
        del sistema, es. dopo Svuota o dopo un flusso): senza, il testo si
        mescolava al placeholder e la domanda partiva corrotta. Ritorna None:
        il binding di classe Text prosegue con l'inserimento del carattere."""
        if self._e_placeholder():
            self.supervisore.delete("1.0", "end")
        return None

    def _blur_supervisore(self, e=None):
        if not self.supervisore.get("1.0", "end").strip():
            self._metti_placeholder()

    def _invio_supervisore(self, e=None):
        """<Return> invia la domanda; <Shift+Return> inserisce il newline.
        F4-E: <Return> matcha anche Shift+Return in Tk -> check del modificatore."""
        if e is not None and (e.state & 0x1):  # Shift premuto: newline di default
            return None
        self._completo()
        return "break"

    def _testo_supervisore(self):
        """La domanda corrente = il blocco NON marcato (dopo l'ultimo '▶' dello storico).
        Il placeholder (in QUALSIASI lingua) viene rimosso se presente."""
        testo = self.supervisore.get("1.0", "end").strip()
        for ph in TESTI.values():
            if ph["placeholder"] in testo:
                testo = testo.replace(ph["placeholder"], "").strip()
                break
        if not testo:
            return ""
        righe = testo.split("\n")
        ultimo = -1
        for i, r in enumerate(righe):
            if r.startswith("▶"):
                ultimo = i
        return "\n".join(righe[ultimo + 1:]).strip()

    def _supervisore_appendi(self, testo):
        """Appende una riga allo storico del supervisore (una domanda per riga).
        F4-E: il nuovo messaggio va SEMPRE su una riga propria (separatore \n
        prima e riga libera dopo), così la nuova domanda digitata è riconosciuta
        da _testo_supervisore; l'input corrente non marcato viene convertito in
        riga ▶ (niente duplicati)."""
        testo_campo = self.supervisore.get("1.0", "end").strip()
        if self._e_placeholder():
            self.supervisore.delete("1.0", "end")
        elif testo_campo:
            righe = testo_campo.split("\n")
            ultimo = -1
            for i, r in enumerate(righe):
                if r.startswith("▶"):
                    ultimo = i
            if ultimo >= 0 and ultimo < len(righe) - 1:
                self.supervisore.delete("1.0", "end")
                self.supervisore.insert("1.0", "\n".join(righe[:ultimo + 1]))
            else:
                self.supervisore.delete("1.0", "end")
        contenuto = self.supervisore.get("1.0", "end-1c")
        if contenuto and not contenuto.endswith("\n"):
            self.supervisore.insert("end", "\n")
        self.supervisore.insert("end", testo + "\n")
        self.supervisore.see("end")

    def _lenti_attivi(self):
        """Modelli lenti (regola _modello_lento) attivi nel canale (A/B/C),
        con la colonna corrispondente: serve all'avviso di attesa alla partenza."""
        attivi = []
        for m, colonna in ((self.canale.A, self.c_a), (self.canale.B, self.c_b),
                           (getattr(self.canale, "C", None), self.c_c)):
            if m is None:
                continue
            nome = m.nome()
            nome_modello = nome.split(":", 1)[1] if nome.startswith("Ollama:") else nome
            if _modello_lento(nome_modello):
                attivi.append((nome_modello, colonna))
        return attivi

    # ---- azioni ----
    def _completo(self):
        domanda = self._testo_supervisore()
        if self._busy:
            self.stato("elaborazione in corso: attendi o premi Esc")
            return
        if not domanda:
            self.c_finale.scrivi(TESTI[self.lingua]["chiedi_prima"])
            self.stato("Scrivi prima una domanda nella barra in alto")
            return
        self._garanzia_motore()  # B2f: fallback ai client esterni se serve
        if not self._inizia_lavoro():
            self.stato("elaborazione in corso: attendi o premi Esc")
            return
        # avviso informativo (NON bloccante): modelli locali pesanti su CPU
        # possono impiegare 2-5 minuti per risposta; il flusso parte comunque.
        lenti = self._lenti_attivi()
        if lenti:
            for n, colonna in lenti:
                colonna.scrivi(f"⚠ modello lento su CPU: attesa stimata 2-5 min per risposta ({n})")
        self._ultima_domanda = domanda
        self._supervisore_appendi("▶ " + " ".join(domanda.split()))
        if getattr(self, "_profilo_attivo", "") == "Ricerca":
            # B1e: percorso Ricerca (pianificazione agenti -> esecuzione -> discernimento)
            threading.Thread(target=self._l_ricerca, args=(domanda,), daemon=True).start()
            return
        threading.Thread(target=self._l_completo, args=(domanda,), daemon=True).start()

    def _aggiorna(self, testo, colore=None):
        tok = self.canale.token_totali
        messaggio = f"{testo} · chiamate: {self.canale.chiamate}/{self.canale.max_chiamate} · token: {tok['in']} in / {tok['out']} out"
        if colore:
            self._messaggio_finale = messaggio
        self.stato(messaggio, colore)

    def _ui(self, fn, *args):
        """Esegue fn sul MAIN thread (Tk non è thread-safe). Dal worker:
        accoda in una coda thread-safe; il main loop (polling after) esegue in FIFO.
        Mai chiamate tk direttamente da thread non-main (RuntimeError o deadlock)."""
        if threading.current_thread() is threading.main_thread():
            return fn(*args)
        self._coda_ui.put((fn, args))

    def _ui_val(self, fn, *args):
        """Esegue fn sul MAIN thread e NE RESTITUISCE il valore (letture GUI dal
        worker). L'eccezione di fn viene propagata al chiamante."""
        if threading.current_thread() is threading.main_thread():
            return fn(*args)
        q = queue.Queue()

        def _esegui():
            try:
                q.put(("ok", fn(*args)))
            except BaseException as e:
                q.put(("err", e))

        self._coda_ui.put((_esegui, ()))
        stato, valore = q.get()
        if stato == "err":
            raise valore
        return valore

    def _sonda_ui(self):
        """Polling della coda UI: esegue sul main thread le fn accodate dai worker.
        ROBUSTA: un'eccezione di fn va in stderr con traceback e il polling continua;
        solo un tk.TclError da finestra distrutta termina il loop. Il rischeduling
        after(50) avviene SEMPRE (anche dopo un'eccezione della fn)."""
        while True:
            try:
                fn, args = self._coda_ui.get_nowait()
            except queue.Empty:
                break
            try:
                fn(*args)
            except tk.TclError:
                try:
                    self.after(50, self._sonda_ui)
                    return
                except tk.TclError:
                    return
            except Exception:
                traceback.print_exc()
        try:
            self.after(50, self._sonda_ui)
        except tk.TclError:
            pass

    def _reset_cronometro(self):
        """Cronometro a riposo ('⏱ 0.0s · in attesa'): avvio dell'app e cambio
        lingua. Il testo vive nella status bar composta (F5-A)."""
        self._crono = {"passo": None, "durata": None, "totale": None}
        self._aggiorna_status()

    def _disegna_cronometro(self):
        """Aggiorna la status bar con l'ultimo stato del cronometro. La scrittura
        gira SUL MAIN THREAD: tk non è thread-safe (via _ui dai worker)."""
        self._ui(self._aggiorna_status)

    def _tempo(self, passo, durata=None, totale=None):
        """Cronometro SEMPRE visibile nella status bar: a riposo '⏱ 0.0s · in
        attesa'; durante il flusso passo/durata/totale; a fine flusso il totale
        finale resta visibile (nessun reset qui)."""
        self._crono = {"passo": passo, "durata": durata, "totale": totale}
        self._disegna_cronometro()

    # ---- A13: contatore tok/s in tempo reale (status bar composta) ----
    def _componi_tok(self):
        """Segmento '⚡ <n> tok/s' della status bar (solo durante l'elaborazione;
        a riposo il segmento non compare). Formato italiano con virgola; '⚡ …'
        prima del primo chunk; '0,0' a finestra vuota; '≈' davanti alla media
        stimata (senza usage reale). In coda il totale di sessione Σ (A13
        rev. 17.1) se > 0: '⚡ 42,3 tok/s · Σ 12.345'."""
        if not self._busy:
            return ""
        if self._tok_fine_passo:
            valore = self._metro.media()
            if valore is None:
                segmento = "⚡ …"
            else:
                prefisso = "" if self._metro.media_reale() else "≈"
                segmento = f"⚡ {prefisso}{self._num_it(valore)} tok/s"
        else:
            istantaneo = self._metro.tok_s()
            if istantaneo is None:
                segmento = "⚡ …"
            else:
                segmento = f"⚡ {self._num_it(istantaneo)} tok/s"
        sigma = self._componi_sigma()
        return f"{segmento} · Σ {sigma}" if sigma else segmento

    @staticmethod
    def _num_it(valore):
        """1 decimale, virgola italiana (stile A13, come il cronometro)."""
        return f"{valore:.1f}".replace(".", ",")

    @staticmethod
    def _num_migliaia(valore):
        """Intero con separatore migliaia italiano (punto), senza `locale` di
        sistema (A13 rev. 17.1): 12345 -> '12.345'."""
        return f"{int(round(valore)):,}".replace(",", ".")

    def _token_reali(self):
        """Reali in+out accumulati da `Canale.token_totali` (A13 rev. 17.1)."""
        tok = self.canale.token_totali
        return tok.get("in", 0) + tok.get("out", 0)

    def _componi_sigma(self):
        """Σ di sessione (A13 rev. 17.1): '' se <= 0 (segmento assente a inizio
        flusso/riposo). Schema a base congelata: durante il passo
        Σ = base (reali in+out) + stima del passo in corso; a passo chiuso
        Σ = reali correnti di `token_totali` (l'usage del passo è già
        contabilizzato dal Canale: nessun doppio conteggio)."""
        if self._tok_fine_passo:
            somma = self._token_reali()
        else:
            somma = self._tok_sigma_base + self._metro.token_stimati()
        intero = int(round(somma))
        if intero <= 0:
            return ""
        return self._num_migliaia(intero)

    def _tok_alimenta(self, pezzo):
        """A13: alimenta il metro (dal thread di streaming, O(1)) e pianifica
        il refresh: aggiornamento immediato se sono passati >=500 ms, altrimenti
        un singolo after(500-Delta) via coda UI. Mai un timer accumulato."""
        if not pezzo:
            return
        self._metro.aggiungi(pezzo)
        if not self._busy:
            return
        with self._tok_lock:
            if self._tok_after_pendente:
                return
            ora = time.monotonic()
            delta = ora - self._tok_ultimo_refresh
            if delta >= _TOK_INTERVALLO:
                self._tok_ultimo_refresh = ora
                self._ui(self._aggiorna_status)
            else:
                self._tok_after_pendente = True
                self._ui(self._tok_after, _TOK_INTERVALLO - delta)

    def _tok_after(self, ritardo):
        """A13 (main thread): programma il tick di refresh; un solo after vivo."""
        if self._chiusa or self._tok_after_id is not None:
            return
        try:
            self._tok_after_id = self.after(
                max(1, int(round(ritardo * 1000))), self._tok_tick)
        except tk.TclError:
            pass

    def _tok_tick(self):
        """A13 (main thread): aggiorna la status; se la finestra ha ancora
        attivita' riprogramma un tick (cosi' a finestra vuota arriva '0,0'),
        altrimenti si ferma (il prossimo chunk riattiva il refresh)."""
        self._tok_after_id = None
        if self._chiusa:
            return
        riprogramma = False
        if self._busy:
            self._aggiorna_status()
            with self._tok_lock:
                self._tok_ultimo_refresh = time.monotonic()
                if self._metro.attivo():
                    riprogramma = True
                else:
                    self._tok_after_pendente = False
        else:
            with self._tok_lock:
                self._tok_after_pendente = False
        if riprogramma:
            try:
                self._tok_after_id = self.after(int(_TOK_INTERVALLO * 1000),
                                                self._tok_tick)
            except tk.TclError:
                pass

    def _tok_reset(self):
        """A13: reset a inizio flusso/fine lavoro/annullamento: metro azzerato,
        after annullato, segmento assente. Gira sul main thread."""
        self._metro.reset()
        self._tok_fine_passo = False
        self._tok_out0 = self.canale.token_totali.get("out", 0)
        # A13 rev. 17.1: la base Σ segue i reali correnti: a inizio flusso il Σ
        # di sessione prosegue; a fine lavoro/annullo il valore resta in memoria.
        self._tok_sigma_base = self._token_reali()
        with self._tok_lock:
            self._tok_ultimo_refresh = 0.0
            self._tok_after_pendente = False
        if self._tok_after_id is not None:
            try:
                self.after_cancel(self._tok_after_id)
            except tk.TclError:
                pass
            self._tok_after_id = None

    def _tok_inizio_passo(self):
        """A13 (main thread, via coda UI): nuovo passo -> il segmento riparte
        da '⚡ …' e il delta usage conta da qui."""
        self._metro.reset()
        self._tok_fine_passo = False
        self._tok_out0 = self.canale.token_totali.get("out", 0)
        self._tok_sigma_base = self._token_reali()   # A13 rev. 17.1: base Σ
        with self._tok_lock:
            self._tok_ultimo_refresh = 0.0
        self._aggiorna_status()

    def _tok_finalizza_passo(self, durata):
        """A13 (main thread, via coda UI): a fine passo la media usa l'usage
        reale (eval_count) se disponibile, altrimenti resta la stima; il
        segmento resta visibile finche' non parte il passo successivo."""
        delta = self.canale.token_totali.get("out", 0) - self._tok_out0
        if delta > 0:
            self._metro.finalizza(delta, durata)
        self._tok_fine_passo = True
        self._aggiorna_status()

    def _scrivi_errore(self, e):
        if self._chiusa:
            return
        testo = "⏹ elaborazione annullata" if self.canale.annulla else f"ERRORE: {e}"
        try:
            self.c_finale.scrivi(testo)
        except tk.TclError:
            pass

    # ---- V6: warmup modelli (preload in background) ----
    def _avvia_warmup(self):
        """V6: preload in background dei soli modelli lenti selezionati, al
        massimo UNO grande alla volta (regola ARCA: se c'è un 14B, prima lui).
        Gli altri lenti restano on-demand (nota in status). Non blocca la UI:
        il caricamento gira in un thread daemon; l'esito torna via coda UI."""
        if self._chiusa:
            return
        if self._warmup_thread is not None and self._warmup_thread.is_alive():
            return  # un warmup è già in corso: mai due caricamenti insieme
        candidati = []
        for polo, modello in (("A", self.canale.A), ("B", self.canale.B),
                              ("C", getattr(self.canale, "C", None))):
            if modello is None:
                continue
            if isinstance(modello, _motore.ModelloMotore):
                # B2f: anche i modelli del motore lenti si scaldano (avvio server)
                breve = os.path.basename(modello.percorso)[:-5]
                if not _modello_lento(breve) or breve in self._warmup:
                    continue
                candidati.append((polo, modello, breve))
                continue
            nome = modello.nome()
            if not nome.startswith("Ollama:"):
                continue  # i modelli cloud non si scaldano
            breve = nome.split(":", 1)[1]
            if not _modello_lento(breve) or breve in self._warmup:
                continue
            candidati.append((polo, modello, breve))
        if not candidati:
            return
        grandi = [c for c in candidati if _modello_grande(c[2])]
        polo, modello, breve = grandi[0] if grandi else candidati[0]
        altri = [b for _, _, b in candidati if b != breve]
        self._warmup[breve] = "in_corso"
        msg = f"⏳ caricamento {polo} ({breve})…"
        if altri:
            msg += f" · {', '.join(altri)} on-demand"
        self.stato(msg)
        self._warmup_thread = threading.Thread(
            target=self._l_warmup, args=(modello, polo, breve), daemon=True)
        self._warmup_thread.start()

    def _l_warmup(self, modello, polo, breve):
        """Thread del warmup (V6): precarica il modello e riporta l'esito in
        status bar sul main thread (via coda UI). Errori -> "fallito", mai crash."""
        try:
            dt = modello.precarica()
            if dt is None:
                self._warmup.pop(breve, None)
                return
            self._warmup[breve] = "pronto"
            self._ui(self.stato, f"{polo} pronto ({dt:.1f} s)")
        except Exception:
            self._warmup[breve] = "fallito"
            self._ui(self.stato, f"⚠ {polo} ({breve}): caricamento fallito")

    def _attendi_warmup(self):
        """V6: se un warmup è in corso, il flusso attende che finisca (stesso
        load, nessuna richiesta duplicata). Chiamata dal thread del flusso."""
        t = self._warmup_thread
        if t is not None and t.is_alive():
            self._ui(self.stato, "⏳ attendo il caricamento del modello…")
            t.join()

    def _l_completo(self, domanda):
        t = TESTI[self.lingua]
        try:
            # V6: mai due caricamenti insieme — se il warmup è in corso, attende.
            self._attendi_warmup()
            t0 = time.time()
            t_passo = t0
            def _passo(nome, finito=False):
                nonlocal t_passo
                ora = time.time()
                if finito:
                    durata = ora - t_passo
                    self._tempo(nome, durata, ora - t0)
                    # A13: media del passo con l'usage reale (eval_count) se c'è
                    self._ui(self._tok_finalizza_passo, durata)
                    t_passo = ora
                else:
                    self._tempo(nome + " (in corso)", None, ora - t0)
                    # A13: nuovo passo -> reset del segmento tok/s ('⚡ …')
                    self._ui(self._tok_inizio_passo)
            self._tempo("formulazione…", 0.0, 0.0)
            self._ui(self._tok_inizio_passo)
            self._ui(self.c_a.scrivi, t["formula"])
            contesto = self.canale.domanda_utente(domanda,
                                              on_chunk=lambda x: self._flusso(self.c_a, x),
                                              on_chunk_b=lambda x: self._flusso(self.c_b, x),
                                              **self._opzioni_c(self.canale.domanda_utente))
            _passo("formulazione", finito=True)
            self._ui(self.spinner, True)
            _passo("dibattito")
            self.dibattito_risultato = self.canale.dibattito(contesto,
                                                             on_chunk=lambda x: self._flusso(self.c_a, x),
                                                             on_chunk_b=lambda x: self._flusso(self.c_b, x),
                                                             **self._opzioni_c(self.canale.dibattito))
            _passo("dibattito", finito=True)
            self._ui(self._aggiorna, t["sint_ok"])
            _passo("sintesi")
            sintesi = self.canale.spartisci_lavori(contesto, self.dibattito_risultato,
                                                   on_chunk=lambda x: self._flusso(self.c_a, x))
            self._ui(self.c_a.scrivi, "[SINTESI FINALE E LAVORI]\n" + sintesi)
            _passo("risposta univoca")
            finale, revisione = self.canale.risposta_univoca(contesto, self.dibattito_risultato, sintesi,
                                                              **self._opzioni_c(self.canale.risposta_univoca))
            _passo("risposta univoca", finito=True)
            self.ultimo_finale = finale
            self._ui(self.c_finale.scrivi, finale)
            self._ui(self.c_b.scrivi, t["rev_b"] + "\n" + revisione)
            self._ui(self._aggiorna, t["fine_ok"], PALETTE["verde"])
            _passo("cross-check")
            self._esegui_cross(contesto)
            _passo("cross-check", finito=True)
            # V2: avviso visibile se qualche risposta è stata troncata dal cap token
            if getattr(self.canale, "troncamenti", 0):
                self._ui(self.stato,
                         f"⚠ {self.canale.troncamenti} risposta/e troncata/e dal limite token")
            self._ui(self.bell)
            _salva_flag_primo_flusso()
        except Exception as e:
            self._ui(self._scrivi_errore, e)
        finally:
            self._ui(self._fine_lavoro)

    # ---- B1e/B3: percorso Ricerca e pannello agenti ----
    def _contesto_allegati(self):
        """B1e: contesto testuale dagli allegati del canale (per gli agenti)."""
        parti = []
        for a in getattr(self.canale, "allegati", []):
            if a.get("tipo") == "testo":
                parti.append(f"[ALLEGATO: {a.get('nome', '?')}]\n"
                             f"{a.get('contenuto', '')[:4000]}")
            else:
                parti.append(f"[ALLEGATO: {a.get('nome', '?')}] (immagine)")
        return "\n\n---\n\n".join(parti)[:12000]

    def _evento_ricerca(self, tipo, dati):
        """B1e: eventi della ricerca verso il pannello agenti (main thread)."""
        try:
            fin = getattr(self, "_agenti_fin", None)
            if fin is not None and fin.winfo_exists():
                fin.evento(tipo, dati)
        except tk.TclError:
            pass
        if tipo == "fase" and dati.get("nome"):
            self.stato(f"🔎 {dati['nome']}…")

    def _l_ricerca(self, domanda):
        """B1e: percorso Ricerca in worker: pianifica -> esegui -> discerni ->
        cross-check -> salvataggio nel perimetro (A9 rev. 5)."""
        from core import agenti as _agenti
        try:
            self._attendi_warmup()
            # D3 (collaudo F4): nuova ricerca -> zona C pulita
            self._ui(self.c_finale.box.delete, "1.0", "end")
            # B3 rev. (N47): il pannello agenti si apre da solo all'avvio della
            # ricerca e il messaggio guida sparisce (serve solo a riposo).
            self._ui(self._apri_agenti)
            self._ui(self._pulisci_agenti)
            cfg = CONFIG.get("ricerca") or {}
            self.canale.max_chiamate = int(cfg.get("max_chiamate", 200))
            evento = lambda tipo, dati: self._ui(self._evento_ricerca, tipo, dati)
            self._ui(self.stato, "🔎 pianificazione agenti…")
            piano = _agenti.pianifica(self.canale, domanda,
                                      contesto=self._contesto_allegati(),
                                      cfg=cfg, evento=evento)
            if piano is None:
                self._ui(self.c_finale.scrivi,
                         "Ricerca: il piano agenti non è stato prodotto in formato "
                         "valido (riprova o usa un modello più grande per il piano).")
                return
            self._ui(self.c_a.scrivi, "[PIANO AGENTI]\n" + "\n".join(
                f"- {a['nome']} ({a['specialita']}): {a['obiettivo']}"
                for a in piano.agenti))
            self._ui(self.stato, f"🔎 esecuzione di {len(piano.agenti)} agenti…")
            risultati = _agenti.esegui(self.canale, piano, domanda,
                                       contesto=self._contesto_allegati(),
                                       cfg=cfg, evento=evento)
            for r in risultati:
                self._ui(self.c_b.scrivi, f"[{r['nome']}]\n{r['testo']}\n")
            self._ui(self.stato, "🔎 discernimento…")
            esito = _agenti.discerni(self.canale, domanda, piano, risultati,
                                     cfg=cfg, evento=evento)
            self.ultimo_finale = esito.risposta
            self._ui(self.c_finale.scrivi, esito.risposta)
            self._ui(self.stato, "🔎 cross-check…")
            self.dibattito_risultato = {"convergito": True}
            self._esegui_cross({"domanda": domanda})
            self._ui(self.c_finale.scrivi, self._riga_confidenza(esito, cfg))
            percorso = _agenti.salva_output(esito, evento=evento)
            if percorso:
                msg = f"risultato salvato: {os.path.basename(percorso)}"
            else:
                msg = ("risultato in GUI (per salvarlo scegli la cartella "
                       "progetto con 📁 Progetto)")
            # P4-2 (collaudo F4): mostrato DOPO la coda del cross-check, senza
            # essere sovrascritto da "cross-check completato".
            self._ui(lambda m=msg: self.after(600, lambda: self.stato(m)))
            self._ui(self.bell)
            _salva_flag_primo_flusso()
        except Exception as e:
            self._ui(self._scrivi_errore, e)
        finally:
            self._ui(self._fine_lavoro)

    def _riga_confidenza(self, esito, cfg):
        """B3: riga [CONFIDENZA: …] in formato italiano (virgola decimale)."""
        soglia = float((cfg or {}).get("soglia_ottimo", 8.99))
        n = len(esito.iterazioni) if esito.iterazioni else 0
        punteggio = f"{esito.punteggio_finale:.2f}".replace(".", ",")
        soglia_s = f"{soglia:.2f}".replace(".", ",")
        return (f"[CONFIDENZA: {punteggio}/10 · soglia {soglia_s} · iterazione {n}"
                f" · stop: {esito.motivo_stop}]")

    def _apri_agenti(self):
        """B3: apre il pannello 'Squadra di ricerca' (avvisa se il profilo non è Ricerca)."""
        try:
            fin = getattr(self, "_agenti_fin", None)
            if fin is not None and fin.winfo_exists():
                fin.lift()
                return
        except tk.TclError:
            pass
        self._agenti_fin = FinestraAgenti(self)
        try:
            self._agenti_fin.lift()
        except tk.TclError:
            pass
        if getattr(self, "_profilo_attivo", "") != "Ricerca":
            self._agenti_fin.evento("avviso", {
                "testo": "Attiva il profilo Ricerca per usare la squadra di agenti."})

    def _pulisci_agenti(self):
        """B3 rev. (N47): all'avvio di una ricerca il pannello si azzera
        (il messaggio guida 'Nessuna ricerca in corso' sparisce)."""
        fin = getattr(self, "_agenti_fin", None)
        try:
            if fin is not None and fin.winfo_exists():
                fin.pulisci()
        except tk.TclError:
            pass

    def _opzioni_c(self, fn):
        """kwargs extra per la terza voce C: on_chunk_c in streaming verso c_c.
        Solo se il canale è stato esteso (attributo C presente E firma del metodo
        con on_chunk_c): altrimenti {} -> comportamento a due voci invariato."""
        if getattr(self.canale, "C", None) is None or not _supporta(fn, "on_chunk_c"):
            return {}
        return {"on_chunk_c": lambda x: self._flusso(self.c_c, x)}

    def _contesto_step(self):
        """Contesto dei flussi parziali: A/B dallo storico + terza voce C
        (c_risposta dall'ultimo passo di C, ultimo_c dal dibattito se presente)."""
        contesto = {"a_formula": self._ultimo("A"), "b_risposta": self._ultimo("B"),
                    "domanda": getattr(self, "_ultima_domanda", "") or self._ultimo("UTENTE")}
        c_risposta = self._ultimo("C")
        if c_risposta:
            contesto["c_risposta"] = c_risposta
        if isinstance(self.dibattito_risultato, dict) and self.dibattito_risultato.get("ultimo_c"):
            contesto["ultimo_c"] = self.dibattito_risultato["ultimo_c"]
        return contesto

    def _flusso(self, colonna, pezzo):
        """Scrittura incrementale (streaming) nella colonna, senza bloccare la GUI.
        Le operazioni tkinter girano SOLO sul main thread (via _ui). Nessun toggle
        di state: i box di output sono in sola lettura selezionabile permanente,
        così la selezione dell'utente non viene cancellata durante lo streaming."""
        if threading.current_thread() is not threading.main_thread():
            # A13: il chunk è contato QUI (thread di streaming, O(1)); la
            # scrittura tk resta sul main thread via coda UI.
            self._tok_alimenta(pezzo)
            self._ui(self._flusso, colonna, pezzo)
            return
        colonna.box.insert("end", pezzo)
        colonna.box.see("end")

    def _cross_check(self):
        if not self._inizia_lavoro():
            return
        threading.Thread(target=self._l_cross, daemon=True).start()

    def _esegui_cross(self, contesto):
        """Cross-check (passo 6): legge la risposta univoca dalla colonna finale
        (via _ui_val se chiamato dal worker), la sottopone al verificatore bambino
        (chiamata di rete NEL WORKER) e scrive verdetto+metriche via _ui.
        try/except interno: errore -> _scrivi_errore via _ui, mai propagato.
        Usato sia dal pulsante autonomo sia dalla chiusura del flusso completo."""
        try:
            finale = getattr(self, "ultimo_finale", "") or ""
            if not finale or finale.startswith("ERRORE"):
                self.ultimo_verdetto = ""
                self.ultimo_finale = ""
                self.ultimo_punti = ""
                self._ui(self.c_finale.scrivi, "Nessuna risposta univoca da verificare: esegui prima il flusso.")
                return
            self._ui(self.c_finale.scrivi, "\n[🛡 CROSS-CHECK in corso …]")
            risultato = self.canale.cross_check(contesto, finale)
            self._ui(self.c_finale.scrivi,
                     self._riga_verdetto(risultato, self._non_convergente()) + "\n" + risultato["testo"])
            # A11.2: la VERSIONE PULITA di C sostituisce la risposta finale se CONFERMATA
            versione_pulita = risultato.get("versione_pulita") or ""
            if risultato["verdetto"] == "CONFERMATA" and versione_pulita:
                self.ultimo_finale = versione_pulita
                self._ui(self.c_finale.scrivi, "[RISPOSTA FINALE PULITA]\n" + versione_pulita)
            else:
                self.ultimo_finale = finale
            self.ultimo_punti = risultato["testo"]
            self.ultimo_verdetto = risultato["verdetto"]
            self._messaggio_finale = "cross-check completato"
            self._ui(self.stato, "cross-check completato")
        except Exception as e:
            self._ui(self._scrivi_errore, e)

    def _riga_verdetto(self, risultato, non_convergente=False):
        """Riga [VERDETTO: … · metriche · pulizia · nota] in formato unico
        (A11 rev. 8): la nota 'non convergente' compare solo se il dibattito non
        è convergito, MAI nel corpo della risposta."""
        met = risultato["metriche"]
        nota = " | nota: non convergente" if non_convergente else ""
        return (f"[VERDETTO: {risultato['verdetto']} · supportate {met['affermazioni_supportate']} "
                f"| non supportate {met['affermazioni_non_supportate']} | parole {met['parole_risposta']} "
                f"| pulizia: {met.get('pulizia', '?')}{nota}]")

    def _non_convergente(self):
        """True se l'ultimo dibattito registrato non è convergito (A11 rev. 8)."""
        d = self.dibattito_risultato
        return isinstance(d, dict) and not d.get("convergito", True)

    def _l_cross(self):
        t = TESTI[self.lingua]
        try:
            contesto = self._contesto_step()
            self._esegui_cross(contesto)
        except Exception as e:
            self._ui(self._scrivi_errore, e)
        finally:
            self._ui(self._fine_lavoro)

    def _dibattito(self):
        if not self._inizia_lavoro():
            self.stato("elaborazione in corso: attendi o premi Esc")
            return
        threading.Thread(target=self._l_dibattito, daemon=True).start()

    def _l_dibattito(self):
        t = TESTI[self.lingua]
        try:
            contesto = self._contesto_step()
            self.dibattito_risultato = self.canale.dibattito(contesto,
                                                             **self._opzioni_c(self.canale.dibattito))
            self._ui(self.c_a.scrivi, t["pos_a"] + "\n" + self.dibattito_risultato["ultimo_a"])
            self._ui(self.c_b.scrivi, t["pos_b"] + "\n" + self.dibattito_risultato["ultimo_b"])
            if isinstance(self.dibattito_risultato, dict) and self.dibattito_risultato.get("ultimo_c"):
                self._ui(self.c_c.scrivi, self.dibattito_risultato["ultimo_c"])
        except Exception as e:
            self._ui(self._scrivi_errore, e)
        finally:
            self._ui(self._fine_lavoro)

    def _sintesi(self):
        if not self._inizia_lavoro():
            return
        threading.Thread(target=self._l_sintesi, daemon=True).start()

    def _l_sintesi(self):
        t = TESTI[self.lingua]
        try:
            contesto = self._contesto_step()
            dibattito = self.dibattito_risultato or {"ultimo_a": contesto["a_formula"],
                                                     "ultimo_b": contesto["b_risposta"]}
            sintesi = self.canale.spartisci_lavori(contesto, dibattito)
            self._ui(self.c_a.scrivi, "[SINTESI FINALE E LAVORI]\n" + sintesi)
            self._ui(self.stato, t["sint_ok"])
            finale, revisione = self.canale.risposta_univoca(contesto, dibattito, sintesi,
                                                             **self._opzioni_c(self.canale.risposta_univoca))
            self._ui(self.c_b.scrivi, t["rev_b"] + "\n" + revisione)
            self._ui(self.c_finale.scrivi, finale)
            self._ui(self.stato, t["fine_ok"])
        except Exception as e:
            self._ui(self._scrivi_errore, e)
        finally:
            self._ui(self._fine_lavoro)

    def _univoca(self):
        if not self._inizia_lavoro():
            self.stato("elaborazione in corso: attendi o premi Esc")
            return
        threading.Thread(target=self._l_univoca, daemon=True).start()

    def _l_univoca(self):
        t = TESTI[self.lingua]
        try:
            contesto = self._contesto_step()
            dibattito = self.dibattito_risultato or {"ultimo_a": contesto["a_formula"],
                                                     "ultimo_b": contesto["b_risposta"]}
            sintesi = self._ultimo("A") or contesto["a_formula"]
            finale, revisione = self.canale.risposta_univoca(contesto, dibattito, sintesi,
                                                             **self._opzioni_c(self.canale.risposta_univoca))
            self._ui(self.c_b.scrivi, t["rev_b"] + "\n" + revisione)
            self._ui(self.c_finale.scrivi, finale)
            self._ui(self.stato, t["fine_ok"])
        except Exception as e:
            self._ui(self._scrivi_errore, e)
        finally:
            self._ui(self._fine_lavoro)

    def _salva(self):
        """💾 Salva: sessione in sessioni/ (proprietà dell'app, come oggi) e, se
        la cartella progetto è scelta, il RISULTATO in <cartella progetto>/TRILogos_output/
        (A9c, nome univoco: mai overwrite). Senza cartella: avviso informativo,
        nessun blocco della lettura/dialogo (rev. 5)."""
        try:
            j, md = self.canale.salva()
            nome = os.path.splitext(os.path.basename(j))[0]
            domanda = getattr(self, "_ultima_domanda", "") or self._ultimo("UTENTE")
            modelli = [self.canale.A.nome(), self.canale.B.nome()]
            c_terzo = getattr(self.canale, "C", None)
            if c_terzo is not None:
                modelli.append(c_terzo.nome())
            tid = aggiungi_sessione(nome, domanda, modelli, self.lingua, j, md,
                                    verdetto=getattr(self, "ultimo_verdetto", "") or "non verificata",
                                    autore=_autore_timeline())
            messaggio = f"salvata: {md} · timeline evento {tid}"
            if perimetro.leggi() is None:
                from tkinter import messagebox
                messagebox.showinfo(
                    "TRILogos — salva risultato",
                    "Per salvare il risultato scegli la cartella progetto (📁 Progetto).\n"
                    "La sessione è stata salvata in sessioni/.",
                    parent=self)
            else:
                percorso = self._salva_risultato(domanda, modelli)
                if percorso:
                    messaggio += f" · risultato: {os.path.basename(percorso)}"
            self.stato(messaggio)
        except Exception as e:
            self.c_finale.scrivi(f"ERRORE salvataggio: {e}")

    def _salva_risultato(self, domanda, modelli):
        """A9c: salva la risposta univoca in <cartella progetto>/TRILogos_output/
        con nome univoco (mai overwrite: _2, _3, …). Ritorna il percorso scritto,
        o None se non c'è un risultato da salvare."""
        finale = getattr(self, "ultimo_finale", "") or ""
        if not finale:
            return None
        out_dir = perimetro.risolvi("TRILogos_output")
        os.makedirs(out_dir, exist_ok=True)
        percorso = perimetro.nome_univoco("TRILogos_output", "risultato.md")
        verdetto = getattr(self, "ultimo_verdetto", "") or "non verificata"
        with open(percorso, "x", encoding="utf-8") as f:
            f.write("# TRILogos — risultato\n\n")
            f.write(f"- Data: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"- Domanda: {domanda}\n")
            f.write(f"- Modelli: {', '.join(modelli)}\n")
            f.write(f"- Verdetto: {verdetto}\n\n")
            f.write("## Risposta univoca\n\n")
            f.write(finale.rstrip() + "\n")
        return percorso

    def _svuota(self):
        for c in (self.c_a, self.c_b, self.c_c, self.c_finale):
            c.box.delete("1.0", "end")
        self._metti_placeholder()
        # N47 06/10/2026 (fix Svuota): il campo e' PRONTO per la nuova domanda.
        # Se il focus era su un altro widget (es. la combo profilo/modello),
        # i tasti andavano persi e la domanda non partiva piu': Svuota riporta
        # il focus nel supervisore. Se il focus era gia' nel campo e il
        # placeholder resta visibile, lo rimuove il primo tasto (bind KeyPress).
        try:
            self.supervisore.focus_set()
        except tk.TclError:
            pass
        self.canale.allegati = []
        self.canale.cronologia = []
        self.canale.chiamate = 0
        self.canale.token_totali = {"in": 0, "out": 0}
        # A13 rev. 17.1: Svuota/nuova sessione azzera il totale di sessione Σ
        # (a riposo il segmento non compare comunque: _busy e' False).
        self._tok_sigma_base = 0
        self.ultimo_verdetto = ""
        self.ultimo_finale = ""
        self.ultimo_punti = ""
        self._rigiri = 0
        self.dibattito_risultato = None
        # P4-5 (collaudo F4): svuota anche il pannello Squadra di ricerca
        try:
            fin = getattr(self, "_agenti_fin", None)
            if fin is not None and fin.winfo_exists():
                fin.pulisci()
        except tk.TclError:
            pass
        self._reset_cronometro()  # F4-E: Svuota/cambio modello azzerano il cronometro

    def _voce_canale(self, modello):
        """Ritrova la voce del menu corrispondente al modello attivo del canale.
        Se il modello è noto (Ollama/OpenAI/Anthropic) ma la sua voce NON è nei
        menu (es. server spento), restituisce comunque la voce composta: la combo
        mostra ciò che il canale usa davvero (WYSIWYG). Il fallback 'mock'/prima
        voce resta SOLO per i modelli ignoti (es. Mock)."""
        nome = modello.nome()
        # P2-A (collaudo B2rev): le voci del motore interno ("<nome> (motore)")
        # non devono cadere nel fallback alla prima voce (che può essere un
        # modello Ollama "(lento)"): match per percorso del modello.
        if isinstance(modello, _motore.ModelloMotore):
            for v in self.opzioni:
                try:
                    if (_motore.e_voce_motore(v)
                            and _motore.percorso_da_voce(v) == modello.percorso):
                        return v
                except Exception:
                    continue
        for tipo, suffisso in (("Ollama:", "ollama"), ("OpenAI:", "openai"), ("Anthropic:", "anthropic")):
            if nome.startswith(tipo):
                m = nome.split(":", 1)[1]
                for v in self.opzioni:
                    # F4-E: il suffisso di lentezza va spogliato dal solo NOME
                    # (parte prima di " · "), non dall'intera voce.
                    if " · " in v:
                        nome_v, client_v = v.rsplit(" · ", 1)
                        if client_v == suffisso and _spoglia_suffisso(nome_v) == m:
                            return v
                return f"{m} · {suffisso}"
        if nome.startswith("Mock"):
            return "mock"
        for v in self.opzioni:
            if v.startswith(nome + " · "):
                return v
        return self.opzioni[0] if self.opzioni else "mock"

    def _add_cartella(self):
        """📁 Progetto: sceglie la cartella progetto (perimetro esclusivo, A9) e
        carica i file supportati (max 40, cap totale del core)."""
        from tkinter import filedialog
        cartella = filedialog.askdirectory(title="Cartella progetto — carica tutti i documenti/immagini")
        if not cartella:
            return
        try:
            radice = perimetro.imposta(cartella)
        except ValueError as e:
            self.stato(f"cartella progetto non valida: {e}")
            return
        self._aggiorna_perimetro_ui()
        supportati = [".txt", ".md", ".csv", ".py", ".json", ".log", ".tex", ".html",
                      ".yml", ".yaml", ".ini", ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"]
        file_trovati = []
        for radice_cartella, _, nomi in os.walk(radice):
            for n in nomi:
                if os.path.splitext(n)[1].lower() in supportati:
                    file_trovati.append(os.path.join(radice_cartella, n))
            if len(file_trovati) >= 40:
                break
        file_trovati = file_trovati[:40]
        if not file_trovati:
            self._supervisore_appendi("[progetto] nessun file supportato trovato")
            self.stato(f"progetto: {perimetro.nome()} · nessun file supportato")
            return
        esiti = self.canale.aggiungi_file(file_trovati)
        for e in esiti:
            self._supervisore_appendi(f"[progetto] {e}")
        self.stato(f"progetto: {perimetro.nome()} · caricati {len(esiti)} file")

    def _add_files(self):
        """➕ ADD (rev. 5): le LETTURE sono libere — il pulsante funziona anche
        senza cartella progetto (caso d'uso: far leggere i file per un sunto).
        Se il perimetro è scelto, i file fuori perimetro sono ignorati con avviso;
        il cap di 40 allegati è sempre segnalato. Nessun blocco preventivo."""
        from tkinter import filedialog, messagebox
        percorsi = filedialog.askopenfilenames(
            title="ADD — seleziona documenti o immagini",
            filetypes=[("Documenti e immagini", "*.txt *.md *.csv *.py *.json *.log *.tex *.html *.pdf *.png *.jpg *.jpeg *.webp *.gif"),
                       ("Tutti i file", "*.*")])
        if not percorsi:
            return
        if perimetro.leggi() is None:
            dentro, fuori = list(percorsi), []  # letture libere: nessun vincolo
        else:
            dentro = [p for p in percorsi if perimetro.dentro(p)]
            fuori = [p for p in percorsi if p not in dentro]
        esiti = self.canale.aggiungi_file(dentro) if dentro else []
        rifiutati = [e for e in esiti if "cap di" in e]
        for e in esiti:
            self._supervisore_appendi(f"[allegato] {e}")
        avvisi = []
        if fuori:
            avvisi.append("Ignorati (fuori dalla cartella progetto):\n" +
                          "\n".join(f"• {os.path.basename(p)}" for p in fuori))
        if rifiutati:
            avvisi.append("Non aggiunti (cap di 40 allegati raggiunto):\n" +
                          "\n".join(f"• {r}" for r in rifiutati))
        if avvisi:
            messagebox.showwarning("TRILogos — allegati", "\n\n".join(avvisi), parent=self)
        if esiti:
            self.stato(f"{len(esiti)} allegato/i aggiunto/i al canale")
        else:
            self.stato("Nessun file aggiunto al canale")

    def _opzioni(self):
        """Finestra Opzioni: gestione completa dei clienti (aggiungi, modifica modelli, elimina, preset)."""
        fin = tk.Toplevel(self)
        fin.title("TRILogos — Opzioni / Clienti")
        fin.geometry("720x560")
        fin.configure(bg=PALETTE["sfondo"])
        fin.transient(self)

        lista = tk.Text(fin, height=7, bg="#232429", fg=PALETTE["testo"], relief="flat",
                        highlightthickness=1, highlightbackground=PALETTE["bordo"],
                        font=("Consolas", 9), selectbackground=PALETTE["selectbackground"],
                        selectforeground=PALETTE["selectforeground"])
        lista.pack(fill="x", padx=8, pady=6)
        self._aggiorna_lista_clienti(lista)
        lista.configure(state="disabled")

        # selezione client esistente
        sel_bar = ttk.Frame(fin)
        sel_bar.pack(fill="x", padx=8)
        ttk.Label(sel_bar, text="Cliente selezionato:").pack(side="left")
        combo_clienti = ComboRotonda(sel_bar, values=[c["nome"] for c in self.clienti],
                                     width=18, bg=PALETTE["sfondo"])
        if self.clienti:
            combo_clienti.current(0)
        combo_clienti.pack(side="left", padx=4)
        e_modello_nuovo = ttk.Entry(sel_bar, width=14)
        e_modello_nuovo.pack(side="left", padx=4)
        PulsanteRotondo(sel_bar, testo="＋ Modello", width=11,
                   comando=lambda: self._op_aggiungi_modello(fin, combo_clienti, e_modello_nuovo, lista)).pack(side="left", padx=2)
        PulsanteRotondo(sel_bar, testo="🗑 Elimina", width=11,
                   comando=lambda: self._op_elimina_client(fin, combo_clienti, lista)).pack(side="left", padx=2)

        form = ttk.Frame(fin)
        form.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Label(form, text="Nuovo cliente:").grid(row=0, column=0, sticky="w")
        e_nome = ttk.Entry(form, width=18)
        e_nome.grid(row=0, column=1, sticky="we", padx=2)
        ttk.Label(form, text="base URL").grid(row=0, column=2, sticky="e")
        e_base = ttk.Entry(form, width=30)
        e_base.grid(row=0, column=3, sticky="we", padx=2)
        ttk.Label(form, text="chiave (nome env)").grid(row=1, column=0, sticky="w")
        e_chiave = ttk.Entry(form, width=18)
        e_chiave.grid(row=1, column=1, sticky="we", padx=2)
        ttk.Label(form, text="modelli (csv)").grid(row=1, column=2, sticky="e")
        e_modelli = ttk.Entry(form, width=30)
        e_modelli.grid(row=1, column=3, sticky="we", padx=2)
        form.columnconfigure(3, weight=1)

        def aggiungi():
            nome = e_nome.get().strip()
            if not nome:
                return
            chiave = e_chiave.get().strip()
            if chiave and (not chiave.isidentifier() or len(chiave) > 64):
                self._supervisore_appendi(
                    f"[opzioni] chiave non valida: usa il NOME della variabile d'ambiente "
                    f"(es. OPENAI_API_KEY), mai il valore.")
                return
            modelli = [m.strip() for m in e_modelli.get().split(",") if m.strip()]
            aggiungi_cliente({"nome": nome,
                              "base_url": e_base.get().strip() or "http://localhost:1234/v1",
                              "chiave": chiave, "modelli": modelli or [nome]})
            self._ricarica_clienti(lista, combo_clienti)
            self.stato(f"client '{nome}' aggiunto · modelli nei menu")
            fin.destroy()

        PulsanteRotondo(fin, testo="＋ Aggiungi cliente", comando=aggiungi).pack(side="left", padx=8, pady=8)
        PulsanteRotondo(fin, testo="⚡ OpenAI",
                    comando=lambda: self._op_preset(fin, lista, combo_clienti,
                    "openai", "https://api.openai.com/v1", "OPENAI_API_KEY",
                    ["gpt-4o-mini", "gpt-4o"])).pack(side="left", padx=2)
        PulsanteRotondo(fin, testo="⚡ Anthropic",
                    comando=lambda: self._op_preset(fin, lista, combo_clienti,
                    "anthropic", "https://api.anthropic.com/v1", "ANTHROPIC_API_KEY",
                    ["claude-3-5-sonnet-latest"])).pack(side="left", padx=2)
        PulsanteRotondo(fin, testo="⚡ Ollama",
                    comando=lambda: self._op_preset(fin, lista, combo_clienti,
                    "ollama", "http://localhost:11434/v1", "", [])).pack(side="left", padx=2)
        PulsanteRotondo(fin, testo=TESTI[self.lingua]["motore_apri"],
                    comando=self._apri_avvio_guidato).pack(side="left", padx=8, pady=8)
        PulsanteRotondo(fin, testo=TESTI[self.lingua]["pul_pulsante"],
                    comando=self._apri_pulizia_hw).pack(side="left", padx=2, pady=8)
        PulsanteRotondo(fin, testo="✖ Chiudi", comando=fin.destroy).pack(side="right", padx=8, pady=8)
        PulsanteRotondo(fin, testo="🔑 API Key", width=12,
                    comando=lambda: self._op_istruzioni_chiavi(fin)).pack(side="right", padx=2, pady=8)
        ttk.Label(fin, text="I modelli dei client compaiono nei menu di LLM1, LLM2 e LLM3. Le chiavi: solo nomi di variabili d'ambiente.",
                  background=PALETTE["sfondo"], foreground=PALETTE["secondario"]).pack(side="bottom", pady=4)

    def _aggiorna_lista_clienti(self, lista):
        lista.configure(state="normal")
        lista.delete("1.0", "end")
        lista.insert("1.0", "CLIENTI (modelli tra parentesi)\n" + "\n".join(
            f"- {c['nome']} ({', '.join(c.get('modelli', []))}) · {c.get('base_url', '')}"
            for c in self.clienti) or "  (nessuno)")
        lista.configure(state="disabled")

    def _ricarica_clienti(self, lista, combo_clienti):
        """Ricarica i clienti in BACKGROUND (F4-E): il probe di rete non blocca
        più la UI (prima ~5 s con i server spenti). A fine corsa aggiorna menu,
        combo e lista della finestra Opzioni (se ancora aperta)."""
        def _lavoro():
            try:
                clienti = rileva_clienti()
            except Exception:
                return
            self._ui(self._applica_ricarica_opzioni, clienti, lista, combo_clienti)
        threading.Thread(target=_lavoro, daemon=True).start()

    def _applica_ricarica_opzioni(self, clienti, lista, combo_clienti):
        """Aggiorna i menu e la finestra Opzioni (se ancora aperta)."""
        self._applica_clienti(clienti)
        try:
            if not lista.winfo_exists():
                return
            combo_clienti.configure(values=[c["nome"] for c in self.clienti])
            if self.clienti:
                combo_clienti.current(0)
            self._aggiorna_lista_clienti(lista)
        except tk.TclError:
            pass

    def _aggiorna_menu_clienti(self):
        """Rileva i clienti in BACKGROUND (F4-E: niente blocco UI) e aggiorna i
        menu di LLM1/LLM2/LLM3 (usata dallo splash dopo l'aggiunta di un client)."""
        def _lavoro():
            try:
                clienti = rileva_clienti()
            except Exception:
                return
            self._ui(self._applica_clienti, clienti)
        threading.Thread(target=_lavoro, daemon=True).start()

    def _cambia_modello_terzo(self, voce):
        """LLM3 in fase intermedia (canale senza C): la combo è attiva ma la
        logica del terzo modello arriva nella fase successiva (sezione 7 di
        LAYOUT_TRIVOICE.md) — nessuna ricostruzione del canale."""
        self.stato(f"LLM3: '{voce}' selezionato — la logica del terzo LLM arriva nella fase successiva")

    def _correggi(self):
        """✏️ Correggi: se il verdetto è DA_CORREGGERE, rigira finale+punti del
        verificatore al canale (max 3 rigiri). Azione UTENTE, mai automatica."""
        if not (self.ultimo_verdetto == "DA_CORREGGERE" and self.ultimo_finale and self.ultimo_punti):
            self.c_finale.scrivi("Nessuna correzione da fare: il verdetto non è DA_CORREGGERE")
            return
        if not self._inizia_lavoro():
            return
        self._rigiri = 0
        threading.Thread(target=self._l_corregge, daemon=True).start()

    def _l_corregge(self):
        """Rigiri di correzione: canale.correggi(finale, punti, domanda) →
        nuovo finale in c_finale, revisione in c_b, esito cross in c_c;
        verdetto aggiornato in c_finale. Stop a CONFERMATA o a 3 rigiri."""
        try:
            correggi = getattr(self.canale, "correggi", None)
            if correggi is None:
                raise RuntimeError("canale.correggi non disponibile: la terza voce non è ancora attiva")
            domanda = getattr(self, "_ultima_domanda", "") or self._ultimo("UTENTE")
            while self._rigiri < 3:
                self._rigiri += 1
                nuovo_finale, revisione, esito_cross = correggi(
                    self.ultimo_finale, self.ultimo_punti, domanda,
                    on_chunk=lambda x: self._flusso(self.c_a, x),
                    **self._opzioni_c(correggi))
                self.ultimo_finale = nuovo_finale
                self.ultimo_punti = esito_cross["testo"]
                self.ultimo_verdetto = esito_cross["verdetto"]
                self._ui(self.c_finale.scrivi, nuovo_finale)
                if revisione:
                    self._ui(self.c_b.scrivi, revisione)
                self._ui(self.c_c.scrivi, esito_cross["testo"])
                self._ui(self.c_finale.scrivi, self._riga_verdetto(esito_cross, self._non_convergente()))
                if self.ultimo_verdetto != "DA_CORREGGERE":
                    break
            if self._rigiri >= 3 and self.ultimo_verdetto == "DA_CORREGGERE":
                self._ui(self.c_finale.scrivi, "limite di 3 correzioni raggiunto")
        except Exception as e:
            self._ui(self._scrivi_errore, e)
        finally:
            self._ui(self._fine_lavoro)

    def _op_aggiungi_modello(self, fin, combo_clienti, e_modello, lista):
        nome_client = combo_clienti.get()
        modello = e_modello.get().strip()
        if not nome_client or not modello:
            return
        # via aggiungi_cliente: le chiavi (anche custom reali) NON vengono perse
        c = trova_client(aggiunti(), nome_client)
        if c is None:
            return
        modelli = list(c.get("modelli", []))
        if modello not in modelli:
            modelli.append(modello)
        aggiungi_cliente({"nome": nome_client, "base_url": c.get("base_url", ""),
                          "chiave": c.get("chiave", ""), "modelli": modelli})
        self._ricarica_clienti(lista, combo_clienti)
        self.stato(f"modello '{modello}' aggiunto a {nome_client}")

    def _op_elimina_client(self, fin, combo_clienti, lista):
        nome_client = combo_clienti.get()
        if not nome_client:
            return
        rimuovi_cliente(nome_client)
        self._ricarica_clienti(lista, combo_clienti)
        self.stato(f"client '{nome_client}' eliminato")

    def _op_istruzioni_chiavi(self, fin):
        """Istruzioni BYOK: come attivare i client cloud (chiavi MAI salvate da TRILogos)."""
        from tkinter import Toplevel, Text
        win = Toplevel(fin)
        win.title("TRILogos — API Key (BYOK)")
        win.geometry("560x300")
        win.configure(bg=PALETTE["sfondo"])
        testo = (
            "Le chiavi sono PERSONALI (BYOK): ogni utente usa le proprie.\n\n"
            "1. OpenAI: crea la chiave su platform.openai.com e impostala come\n"
            "   variabile d'ambiente OPENAI_API_KEY (o nel file .env del progetto).\n"
            "2. Anthropic: console.anthropic.com → ANTHROPIC_API_KEY.\n"
            "3. In alternativa crea/usa il file TRILogos/.env con:\n"
            "   OPENAI_API_KEY=sk-...\n"
            "   ANTHROPIC_API_KEY=sk-ant-...\n"
            "   (il file .env è gitignored: le chiavi non finiscono nel repository)\n\n"
            "TRILogos NON salva MAI le chiavi: le legge solo dalla variabile d'ambiente\n"
            "o dal file .env al momento dell'uso. I client LOCALI (Ollama, LM Studio,\n"
            "Jan) non richiedono chiavi: basta avviare il rispettivo server.\n"
        )
        txt = Text(win, bg=PALETTE["campo"], fg=PALETTE["testo"], font=("Consolas", 9),
                   relief="flat", padx=8, pady=8, wrap="word")
        txt.insert("1.0", testo)
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True, padx=8, pady=8)
        PulsanteRotondo(win, testo="✖ Chiudi", comando=win.destroy).pack(side="right", padx=8, pady=4)

    def _op_preset(self, fin, lista, combo_clienti, nome, base, chiave_env, modelli):
        if any(c["nome"] == nome for c in self.clienti):
            self.stato(f"client '{nome}' già presente")
            return
        aggiungi_cliente({"nome": nome, "base_url": base,
                          "chiave": chiave_env, "modelli": modelli})
        self._ricarica_clienti(lista, combo_clienti)
        self.stato(f"client '{nome}' aggiunto (chiave da env {chiave_env})")

    def _cambia_modello(self, polo, voce):
        """Cambia il modello di LLM1/LLM2/LLM3 al volo: ricostruisce il canale.
        Polo C: ricostruisce come A/B se l'API del canale supporta la terza voce;
        nella fase intermedia (canale senza C) mantiene il comportamento attuale
        (messaggio di stato, nessuna ricostruzione)."""
        if polo == "C" and not SUPPORTA_C:
            self._cambia_modello_terzo(voce)
            return
        colonna = {"A": self.c_a, "B": self.c_b, "C": self.c_c}.get(polo)
        if self._busy:
            self.stato("operazione in corso: cambio modello ignorato")
            colonna.combo.set(self._voce_canale(getattr(self.canale, polo)))
            return
        try:
            _timeout = _timeout_rete()[0]
            _ka = _keep_alive_ollama()
            _nc = _num_ctx_ollama()
            nuovo = modello_da_voce(voce, self.clienti, timeout=_timeout, keep_alive=_ka, num_ctx=_nc)
            if polo == "C":
                a = modello_da_voce(self.c_a.combo.get(), self.clienti, timeout=_timeout, keep_alive=_ka, num_ctx=_nc)
                b = modello_da_voce(self.c_b.combo.get(), self.clienti, timeout=_timeout, keep_alive=_ka, num_ctx=_nc)
                c = nuovo
            else:
                altro_polo = "B" if polo == "A" else "A"
                voce_altro = self.c_b.combo.get() if altro_polo == "B" else self.c_a.combo.get()
                altro = modello_da_voce(voce_altro, self.clienti, timeout=_timeout, keep_alive=_ka, num_ctx=_nc)
                a = nuovo if polo == "A" else altro
                b = nuovo if polo == "B" else altro
                c = (modello_da_voce(self.c_c.combo.get(), self.clienti, timeout=_timeout, keep_alive=_ka, num_ctx=_nc)
                     if SUPPORTA_C else None)
            nome_profilo = self.combo_profilo.get() or next(iter(CONFIG["profili"]))
            ruoli = CONFIG["profili"].get(nome_profilo) or next(iter(CONFIG["profili"].values()))
            kwargs = dict(ruolo_a=ruoli["A"], ruolo_b=ruoli["B"],
                          max_turni_dibattito=CONFIG["canale"]["max_turni_dibattito"],
                          soglia_convergenza=CONFIG["canale"]["soglia_convergenza"],
                          max_chiamate=CONFIG["canale"].get("max_chiamate", 40),
                          lingua=self.lingua,
                          stile=ruoli.get("stile") or "",
                          formato_risposta=ruoli.get("formato_risposta") or "semplice",
                          dibattito_parallelo=CONFIG["canale"].get("dibattito_parallelo", True),
                          limiti_token=CONFIG["canale"].get("limiti_token"))
            if SUPPORTA_C:
                kwargs[_PARAM_C] = c
                if "C" in ruoli and _supporta(Canale.__init__, "ruolo_c"):
                    kwargs["ruolo_c"] = ruoli["C"]
            if CONFIG["canale"].get("soglie") and SUPPORTA_SOGLIE:
                kwargs["soglie"] = CONFIG["canale"]["soglie"]
            self.canale = Canale(a, b, **kwargs)
            self.dibattito_risultato = None
            self._svuota()
            self.stato(f"{polo} → {nuovo.nome()} · canale ricostruito")
            _motore.ferma_server_non_usati(self.canale)
            self._avvia_warmup()
        except Exception as e:
            self.stato(f"ERRORE cambio modello: {e}")

    def _ultimo(self, polo):
        for passo in reversed(self.canale.cronologia):
            if passo["polo"] == polo:
                return passo["testo"]
        return ""


if __name__ == "__main__":
    app = TrilogoApp()
    app.mainloop()