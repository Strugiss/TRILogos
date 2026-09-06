# TRILogos — GUI TRIVOICE (barra supervisore + LLM1/LLM2/LLM3), profilo LabGUI
"""Flusso automatico (6 passi): domanda → Invio → A formula e B risponde →
dibattito → sintesi e spartizione → risposta univoca consensuale →
cross-check automatico (verificatore bambino) con verdetto finale.
Layout TRIVOICE: barra SUPERVISORE (84px) + riga 4 riquadri (420px:
pulsanti 200 + LLM1/LLM2/LLM3 325×3) + risposta univoca (142px).
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

from labgui import Finestra, Colonna, PALETTE, FONT_B, FONT_H, RiquadroRotondo, ComboRotonda, BoxArrotondato, Pill
from rounded import PulsanteRotondo
try:
    from core.clienti import (rileva_clienti, voci_modelli, aggiunti, salva_aggiunti,
                              aggiungi_cliente, rimuovi_cliente, stato_locale,
                              stato_opencode, trova_client, LOCALI as LOCALI_INFO)
    from core.timeline import aggiungi_sessione
    from core.canale import Canale
    from core.modelli import crea_modello, modello_da_voce as _modello_da_voce_core
except ImportError as e:
    _errore_import(e)


# ---- etichetta lentezza modelli locali (menu + avvisi: unica fonte di verità) ----
_SUFFISSO_LENTO = " (lento)"


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


def _opzioni_etichettate(voci):
    """Aggiunge ' (lento)' alle voci Ollama pesanti (regola _modello_lento):
    'deepseek-r1:14b · ollama' -> 'deepseek-r1:14b (lento) · ollama'.
    I modelli piccoli e i client NON-Ollama restano invariati. Il parser
    (modello_da_voce qui sotto) rimuove l'etichetta prima di costruire il
    modello: selezione e ricostruzione del canale funzionano in entrambi i casi."""
    etichettate = []
    for v in voci:
        if v.endswith(" · ollama"):
            nome = v[: -len(" · ollama")]
            if _modello_lento(nome):
                v = nome + _SUFFISSO_LENTO + " · ollama"
        etichettate.append(v)
    return etichettate


def modello_da_voce(voce, clienti=None):
    """Wrapper di core.modelli.modello_da_voce: rimuove l'etichetta
    informativa ' (lento)' dal NOME della voce prima del parsing, così
    'deepseek-r1:14b (lento) · ollama' costruisce ModelloOllama con modello
    'deepseek-r1:14b'. La voce senza etichetta passa invariata."""
    if voce and " · " in voce:
        nome, client = voce.rsplit(" · ", 1)
        if nome.endswith(_SUFFISSO_LENTO):
            voce = nome[: -len(_SUFFISSO_LENTO)] + " · " + client
    elif voce and voce.endswith(_SUFFISSO_LENTO):
        voce = voce[: -len(_SUFFISSO_LENTO)]
    return _modello_da_voce_core(voce, clienti)

VERSIONE = "2.0.0"

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
_PROFILI_LOCALI = os.path.join(BASE, "profili_n47lab.json")
if not os.path.exists(_PROFILI_LOCALI):
    _PROFILI_LOCALI = os.path.join(BASE, "dev", "profili_n47lab.json")
if os.path.exists(_PROFILI_LOCALI):
    _locali = _carica_json(_PROFILI_LOCALI)
    if _locali is None:
        _avviso_avvio("profili_n47lab.json non leggibile: uso solo i profili predefiniti. Controlla il file.")
    elif _locali:
        CONFIG.setdefault("profili", {}).update(_locali)

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
    """Salva il flag byok_splash:true in config.json (SOLO alla chiusura dello
    splash, se 'Non mostrare più' è spuntata). Il flag non è mai nel codice."""
    percorso = os.path.join(BASE, "config.json")
    try:
        with open(percorso, encoding="utf-8") as f:
            dati = json.load(f)
        dati["byok_splash"] = True
        with open(percorso, "w", encoding="utf-8") as f:
            json.dump(dati, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _leggi_config():
    """Rilegge config.json da disco (flag runtime: byok_splash, primo_flusso_ok).
    Mai fidarsi della CONFIG in memoria (scritta una sola volta all'import)."""
    percorso = os.path.join(BASE, "config.json")
    try:
        with open(percorso, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _primo_flusso_ok():
    """True se il flag primo_flusso_ok è true in config.json: la prima domanda
    è stata conclusa con un flusso completo. Rilettura da disco a ogni chiamata."""
    return bool(_leggi_config().get("primo_flusso_ok"))


def _salva_flag_primo_flusso():
    """Scrive il flag primo_flusso_ok:true in config.json SOLO se assente: marca
    la PRIMA conclusione di un flusso completo (nessun altro flag toccato)."""
    percorso = os.path.join(BASE, "config.json")
    try:
        with open(percorso, encoding="utf-8") as f:
            dati = json.load(f)
        if dati.get("primo_flusso_ok"):
            return
        dati["primo_flusso_ok"] = True
        with open(percorso, "w", encoding="utf-8") as f:
            json.dump(dati, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

TESTI = {
    "it": {
        "titolo": "TRILogos — dialogo a tre voci (supervisore · LLM1 · LLM2 · LLM3)",
        "supervisore": "SUPERVISORE",
        "placeholder": "Scrivi la domanda e premi Invio o ▶",
        "invia": "▶ Invia",
        "completo": "▶ Avvia (completo)",
        "dibattito": "💬 Dibattito",
        "sintesi": "📋 Sintesi",
        "univoca": "✍️ Univoca",
        "salva": "💾 Salva",
        "svuota": "🗑 Svuota",
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
        "cartella": "📁 Cartella",
        "add": "➕ ADD",
        "cross": "🛡 Cross-check",
        "correggi": "✏️ Correggi",
    },
    "en": {
        "titolo": "TRILogos — three-voice dialogue (supervisor · LLM1 · LLM2 · LLM3)",
        "supervisore": "SUPERVISOR",
        "placeholder": "Type your question and press Enter or ▶",
        "invia": "▶ Send",
        "completo": "▶ Run (full)",
        "dibattito": "💬 Debate",
        "sintesi": "📋 Summary",
        "univoca": "✍️ Unanimous",
        "salva": "💾 Save",
        "svuota": "🗑 Clear",
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
        "cartella": "📁 Folder",
        "add": "➕ ADD",
        "cross": "🛡 Cross-check",
        "correggi": "✏️ Fix",
    },
    "fr": {
        "titolo": "TRILogos — dialogue à trois voix (superviseur · LLM1 · LLM2 · LLM3)",
        "supervisore": "SUPERVISEUR",
        "placeholder": "Écrivez la question et appuyez sur Entrée ou ▶",
        "invia": "▶ Envoyer",
        "completo": "▶ Lancer (complet)",
        "dibattito": "💬 Débat",
        "sintesi": "📋 Synthèse",
        "univoca": "✍️ Unanime",
        "salva": "💾 Sauvegarder",
        "svuota": "🗑 Vider",
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
        "cartella": "📁 Dossier",
        "add": "➕ AJOUTER",
        "cross": "🛡 Vérification",
        "correggi": "✏️ Corriger",
    },
    "es": {
        "titolo": "TRILogos — diálogo a tres voces (supervisor · LLM1 · LLM2 · LLM3)",
        "supervisore": "SUPERVISOR",
        "placeholder": "Escribe la pregunta y pulsa Intro o ▶",
        "invia": "▶ Enviar",
        "completo": "▶ Ejecutar (completo)",
        "dibattito": "💬 Debate",
        "sintesi": "📋 Resumen",
        "univoca": "✍️ Unánime",
        "salva": "💾 Guardar",
        "svuota": "🗑 Vaciar",
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
        "cartella": "📁 Carpeta",
        "add": "➕ AÑADIR",
        "cross": "🛡 Verificación",
        "correggi": "✏️ Corregir",
    },
    "de": {
        "titolo": "TRILogos — Dialog mit drei Stimmen (Betreuer · LLM1 · LLM2 · LLM3)",
        "supervisore": "SUPERVISOR",
        "placeholder": "Frage eingeben und Enter oder ▶ drücken",
        "invia": "▶ Senden",
        "completo": "▶ Komplett",
        "dibattito": "💬 Debatte",
        "sintesi": "📋 Kurzfassung",
        "univoca": "✍️ Einstimmig",
        "salva": "💾 Speichern",
        "svuota": "🗑 Leeren",
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
        "cartella": "📁 Ordner",
        "add": "➕ HINZUFÜGEN",
        "cross": "🛡 Prüfung",
        "correggi": "✏️ Korrigieren",
    },
    "pt": {
        "titolo": "TRILogos — diálogo a três vozes (supervisor · LLM1 · LLM2 · LLM3)",
        "supervisore": "SUPERVISOR",
        "placeholder": "Escreva a pergunta e pressione Enter ou ▶",
        "invia": "▶ Enviar",
        "completo": "▶ Executar (completo)",
        "dibattito": "💬 Debate",
        "sintesi": "📋 Resumo",
        "univoca": "✍️ Unânime",
        "salva": "💾 Salvar",
        "svuota": "🗑 Limpar",
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
        "cartella": "📁 Pasta",
        "add": "➕ ADICIONAR",
        "cross": "🛡 Verificação",
        "correggi": "✏️ Corrigir",
    },
    "zh": {
        "titolo": "TRILogos — 三方对话（主管 · LLM1 · LLM2 · LLM3）",
        "supervisore": "主管",
        "placeholder": "输入问题并按回车或 ▶",
        "invia": "▶ 发送",
        "completo": "▶ 运行（完整）",
        "dibattito": "💬 辩论",
        "sintesi": "📋 总结",
        "univoca": "✍️ 一致",
        "salva": "💾 保存",
        "svuota": "🗑 清空",
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
        "cartella": "📁 文件夹",
        "add": "➕ 添加",
        "cross": "🛡 核查",
        "correggi": "✏️ 修正",
    },
}


def costruisci_canale(lingua="it", profilo=None, voce_c=None, clienti=None):
    """Canale completo: A e B da config; la terza voce C dalla combo di c_c
    (voce_c + modello_da_voce) se l'API del Canale la supporta; soglie da
    config.json (canale.soglie) se presenti. Fase intermedia (canale senza C):
    comportamento invariato a due voci."""
    m = CONFIG["modelli"]
    a = crea_modello(m["A"]["tipo"], modello=m["A"].get("modello"))
    b = crea_modello(m["B"]["tipo"], modello=m["B"].get("modello"))
    profilo = profilo or next(iter(CONFIG["profili"]))
    ruoli = CONFIG["profili"].get(profilo) or next(iter(CONFIG["profili"].values()))
    kwargs = dict(ruolo_a=ruoli["A"], ruolo_b=ruoli["B"],
                  max_turni_dibattito=CONFIG["canale"]["max_turni_dibattito"],
                  soglia_convergenza=CONFIG["canale"]["soglia_convergenza"],
                  lingua=lingua, max_chiamate=CONFIG["canale"].get("max_chiamate", 40))
    if SUPPORTA_C:
        if voce_c:
            c = modello_da_voce(voce_c, clienti)
        elif "C" in m:
            c = crea_modello(m["C"]["tipo"], modello=m["C"].get("modello"))
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
    (il box è a 4 righe richieste: il pannello 142px lo espande a tutto il resto)."""
    def __init__(self, master, polo, colore, descrizione):
        header = tk.Frame(master, bg=PALETTE["pannello"])
        header.pack(fill="x", padx=1, pady=(1, 0))
        self.polo = Pill(header, testo=f"  {polo}  ")
        self.polo.pack(side="left")
        self.lbl_modello = tk.Label(header, text=descrizione, bg=PALETTE["pannello"],
                                    fg=PALETTE["secondario"], font=("Segoe UI", 9))
        self.lbl_modello.pack(side="left", padx=8)
        self.boxwrap = BoxArrotondato(master, altezza_righe=4)
        self.box = self.boxwrap.box
        self.boxwrap.pack(fill="both", expand=True, padx=1, pady=(0, 1))
        self.box.configure(state="disabled")

    def descrizione(self, testo):
        self.lbl_modello.configure(text=testo)

    def scrivi(self, testo):
        self.box.configure(state="normal")
        self.box.insert("end", testo + "\n\n")
        self.box.configure(state="disabled")
        self.box.see("end")


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


class TrilogoApp(Finestra):
    def __init__(self):
        super().__init__(f"{TESTI['it']['titolo']}  ·  v{VERSIONE}")
        self.lingua = "it"
        self._ultima_domanda = ""
        self.clienti = rileva_clienti()
        self.opzioni = _opzioni_etichettate(voci_modelli(self.clienti))
        self.canale = costruisci_canale(self.lingua,
                                        voce_c=self.opzioni[0] if self.opzioni else None,
                                        clienti=self.clienti)
        self.dibattito_risultato = None
        self._busy = False
        self._messaggio_finale = None
        self.ultimo_verdetto = ""
        self.ultimo_finale = ""
        self.ultimo_punti = ""
        self._rigiri = 0
        self._profilo_attivo = next(iter(CONFIG["profili"]))
        self._chiusa = False
        self._crono = {"passo": None, "durata": None, "totale": None}
        self._costruisci()
        try:
            _percorso_ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icona_trilogos.ico")
            self.iconbitmap(bitmap=_percorso_ico)
            self.iconbitmap(default=_percorso_ico)
        except Exception:
            pass
        self._coda_ui = queue.Queue()
        self.after(50, self._sonda_ui)
        self._applica_lingua()
        self.spinner = self._spinner_localizzato
        self.bind("<Escape>", lambda e: self._annulla())
        self.protocol("WM_DELETE_WINDOW", self._chiusura)
        # SPLASH BYOK al primo avvio (flag byok_splash assente in config.json):
        # Toplevel non bloccante, la finestra principale resta operativa.
        # NESSUN focus_force né topmost: il Toplevel appare sopra la principale
        # da solo, senza rubare il focus ai click dell'utente (e ai test GUI).
        self._splash = SplashByok(self) if not CONFIG.get("byok_splash") else None

    def _spinner_localizzato(self, attivo=True):
        testo = "● in elaborazione …" if attivo else TESTI[self.lingua]["pronto"]
        self._status.configure(text=testo, fg=PALETTE["ambra"] if attivo else PALETTE["secondario"])

    def _annulla(self):
        if self._busy:
            self.canale.annulla = True
            self.stato("⏹ annullamento in corso …")

    def _chiusura(self):
        if self._busy:
            from tkinter import messagebox
            if messagebox.askyesno("TRILogos", "Elaborazione in corso: interrompere e chiudere?"):
                self.canale.annulla = True
                self._chiusa = True
                self.destroy()
            return
        self._chiusa = True
        self.destroy()

    def _inizia_lavoro(self):
        if self._busy:
            return False
        self.canale.annulla = False
        self._busy = True
        for chiave in self.bottoni:
            self.bottoni[chiave].configure(state="disabled")
        self.spinner(True)
        self.update_idletasks()
        return True

    def _fine_lavoro(self):
        if self._chiusa:
            return
        self._busy = False
        for chiave in self.bottoni:
            self.bottoni[chiave].configure(state="normal")
        if self._messaggio_finale:
            self.stato(self._messaggio_finale)
            self._messaggio_finale = None
        else:
            self.spinner(False)

    def _costruisci(self):
        # LAYOUT TRIVOICE: zona A (barra SUPERVISORE 84px) + zona B (riga 4 riquadri 420px)
        # + zona C (risposta univoca 142px); totali: 84 + 420 + 142 + 12 (pady) = 658.
        # Dimensioni esatte via minsize delle righe/colonne (i frame con figli
        # non possono forzare la propria size: la richiesta resta quella dei figli).
        self.contenuto.grid_columnconfigure(0, weight=1)
        self.contenuto.grid_rowconfigure(0, weight=0, minsize=88)   # cella 88 = 84 + pady 4
        self.contenuto.grid_rowconfigure(1, weight=1)
        self.contenuto.grid_rowconfigure(2, weight=0, minsize=146)  # cella 146 = 142 + pady 4
        self.contenuto.bind("<Configure>", self._adatta_quadri)

        # ZONA A — barra SUPERVISORE (84px, full width, senza pulsanti)
        self._zona_a = RiquadroRotondo(self.contenuto, bg=PALETTE["sfondo"])
        self._zona_a.grid(row=0, column=0, sticky="nsew", pady=2)
        self.lbl_supervisore = Pill(self._zona_a.frame, testo="  SUPERVISORE  ")
        self.lbl_supervisore.pack(fill="x")
        self._zona_a.frame.bind("<Configure>", self._riadatta_pill)
        self._bw_supervisore = BoxArrotondato(self._zona_a.frame, altezza_righe=3, editabile=True)
        self.supervisore = self._bw_supervisore.box
        self._bw_supervisore.pack(fill="both", expand=True, padx=2, pady=(0, 2))

        self.supervisore.bind("<Return>", self._invio_supervisore)
        self.supervisore.bind("<FocusIn>", self._focus_supervisore)
        self.supervisore.bind("<FocusOut>", self._blur_supervisore)
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
        # (900×600: ~291px disponibili vs ~434px richiesti). A 1200×720 layout
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
        self.bottoni = {}
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
                                   ("opzioni", 10, self._opzioni)):
            b = PulsanteRotondo(self._quadro_interno, width=w, comando=comando)
            b.pack(fill="x", padx=6, pady=1)
            self.bottoni[chiave] = b

        # rotella del mouse sul quadro: scroll verticale del canvas (i figli del
        # frame interno sono canvas/combobox: l'evento non risale da solo)
        self._quadro_interno.bind("<Configure>", self._aggiorna_scroll_quadro)
        self._quadro_canvas.bind("<Configure>", self._allarga_quadro)
        self._quadro_canvas.bind("<MouseWheel>", self._wheel_quadro)
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

        # ZONA C — risposta univoca (142px, full width)
        self._zona_c = RiquadroRotondo(self.contenuto, bg=PALETTE["sfondo"])
        self._zona_c.grid(row=2, column=0, sticky="nsew", pady=2)
        self.c_finale = _RiquadroFinale(self._zona_c.frame, "RISPOSTA UNIVOCA", PALETTE["viola"],
                                        "il verdetto del canale")
        self._lbl_polo = {c: c.polo for c in (self.c_a, self.c_b, self.c_c)}
        self._lbl_polo[self.c_finale] = self.c_finale.polo
        for riquadro in (self._zona_a, self._zona_b, self._quadro,
                         self._wr_a, self._wr_b, self._wr_c, self._zona_c):
            riquadro.aggiorna_req()

    def _adatta_quadri(self, e=None):
        """Regola i minsize della riga dei riquadri: 415px (zona B reale = alt−238,
        contenuto 653px: 84 + 415 + 142 + 12); sotto soglia i riquadri LLM si
        comprimono (nessun 1x1) e il quadro pulsanti diventa scrollabile."""
        lar = self.contenuto.winfo_width()
        alt = self.contenuto.winfo_height()
        if lar < 10 or alt < 10:
            return
        if not getattr(self, "_zona_b", None):
            return
        riga_b = alt - 238  # 84 + 142 + 12 (pady delle 3 zone); tolleranza bordi finestra
        ok = lar >= 1180 and riga_b >= 415
        self._zona_b.frame.grid_rowconfigure(0, weight=1, minsize=415 if ok else 0)
        for i in (1, 2, 3):
            self._zona_b.frame.grid_columnconfigure(i, weight=1, minsize=320 if ok else 0)
        # quadro pulsanti: sempre nsew (a 900×600 resta dentro la zona B, non
        # esonda più sotto la zona C). A 1200×720 (ok) niente scrollbar e canvas
        # all'altezza del contenuto (layout invariato); sotto soglia il canvas
        # si limita allo spazio reale e la scrollbar verticale appare.
        self._quadro.grid_configure(sticky="nsew")
        if ok:
            self._quadro_canvas.itemconfigure(self._quadro_item_sb, state="hidden")
            self._quadro_canvas.configure(height=self._quadro_interno.winfo_reqheight())
        else:
            self._quadro_canvas.itemconfigure(self._quadro_item_sb, state="normal")
            self._quadro_canvas.configure(height=max(riga_b, 120))

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
        visibile (a 1200×720 niente scroll: layout invariato)."""
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
        if ruoli:
            self._profilo_attivo = nome
            self.canale.ruolo_a = ruoli["A"]
            self.canale.ruolo_b = ruoli["B"]
            self.stato(f"profilo ruoli: {nome}")

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
        self._titolo_supervisore = t["supervisore"]
        self._reset_cronometro()
        for chiave in ("invia", "completo", "dibattito", "sintesi", "univoca", "cross",
                       "correggi", "salva", "svuota", "cartella", "add", "opzioni"):
            self.bottoni[chiave].configure(text=t[chiave])
        self.c_finale.descrizione(t["descr_finale"])
        # headers tradotti (nessuna cancellazione: il contenuto delle colonne si conserva)
        for c, nome in ((self.c_a, t["llm1"]), (self.c_b, t["llm2"]),
                        (self.c_c, t["llm3"]), (self.c_finale, t["finale"])):
            self._lbl_polo[c].configure(text=f"  {nome}  ")
        for box in (self.c_a.box, self.c_b.box, self.c_c.box, self.c_finale.box):
            box.configure(state="disabled")
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

    def _blur_supervisore(self, e=None):
        if not self.supervisore.get("1.0", "end").strip():
            self._metti_placeholder()

    def _invio_supervisore(self, e=None):
        """<Return> invia la domanda; <Shift+Return> lascia il newline di default."""
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
        L'input corrente (testo NON marcato ▶) viene convertito in riga ▶: niente duplicati."""
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
        self.supervisore.insert("end", testo)
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
        if not self._inizia_lavoro():
            self.stato("elaborazione in corso: attendi o premi Esc")
            return
        # avviso informativo (NON bloccante): modelli locali pesanti su CPU
        # possono impiegare 2-5 minuti per risposta; il flusso parte comunque.
        lenti = self._lenti_attivi()
        if lenti:
            for n, colonna in lenti:
                colonna.scrivi(f"⚠ modello lento su CPU: attesa stimata 2-5 min per risposta ({n})")
            nomi = ", ".join(n for n, _ in lenti)
            self.stato(f"⚠ modello lento su CPU: attesa stimata 2-5 min per risposta ({nomi})")
        self._ultima_domanda = domanda
        self._supervisore_appendi("▶ " + " ".join(domanda.split()))
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

    def _componi_pill(self, passo=None, durata=None, totale=None):
        """Testo del pill SUPERVISORE: il cronometro è SEMPRE visibile. La stringa
        completa viene accorciata (passo troncato, poi solo durata+totale) se non
        entra nella larghezza reale della barra A (misura font vs canvas)."""
        titolo = getattr(self, "_titolo_supervisore", "SUPERVISORE")
        if passo is None:
            return f"  {titolo}  ·  ⏱ 0.0s · in attesa"
        if durata is None:
            return f"  {titolo}  ·  ⏱ {passo}"
        pieno = f"  {titolo}  ·  ⏱ {passo} · passo {durata:.1f}s · totale {totale:.1f}s"
        breve = f"  {titolo}  ·  ⏱ {passo[:12].rstrip()}… · passo {durata:.1f}s · tot {totale:.1f}s"
        minimo = f"  {titolo}  ·  ⏱ passo {durata:.1f}s · tot {totale:.1f}s"
        for cand in (pieno, breve, minimo):
            if self._pill_ci_sta(cand):
                return cand
        return minimo

    def _pill_ci_sta(self, testo):
        """True se il testo entra nel canvas del pill (barra A full-width, margine
        per i bordi arrotondati); finestra non ancora materializzata -> True."""
        try:
            lar = self.lbl_supervisore.winfo_width()
            if lar < 10:
                lar = self._zona_a.frame.winfo_width()
            if lar < 10:
                return True
            return self.lbl_supervisore._font.measure(testo) <= lar - 32
        except tk.TclError:
            return True

    def _reset_cronometro(self):
        """Cronometro a riposo nel pill ('⏱ 0.0s · in attesa'): avvio dell'app e
        cambio lingua (l'etichetta SUPERVISORE resta, il tempo si ripristina)."""
        self._crono = {"passo": None, "durata": None, "totale": None}
        self.lbl_supervisore.configure(text=self._componi_pill())

    def _disegna_cronometro(self):
        """Scrive nel pill l'ultimo stato del cronometro. La composizione del testo
        (misura font, troncamento) gira SUL MAIN THREAD: tk non è thread-safe e
        winfo_width/measure dal worker sollevano RuntimeError (main loop)."""
        c = self._crono

        def _aggiorna():
            testo = self._componi_pill(c["passo"], c["durata"], c["totale"])
            self.lbl_supervisore.configure(text=testo)

        self._ui(_aggiorna)

    def _riadatta_pill(self, e=None):
        """Resize della barra A: ricalcola il testo del pill (troncamento a misura)."""
        try:
            if getattr(self, "_crono", None) is not None:
                self._disegna_cronometro()
        except tk.TclError:
            pass

    def _tempo(self, passo, durata=None, totale=None):
        """Cronometro SEMPRE visibile nel rettangolo arancione del pill SUPERVISORE:
        a riposo '⏱ 0.0s · in attesa'; durante il flusso passo/durata/totale;
        a fine flusso il totale finale resta visibile (nessun reset qui)."""
        self._crono = {"passo": passo, "durata": durata, "totale": totale}
        self._disegna_cronometro()

    def _scrivi_errore(self, e):
        if self._chiusa:
            return
        testo = "⏹ elaborazione annullata" if self.canale.annulla else f"ERRORE: {e}"
        try:
            self.c_finale.scrivi(testo)
        except tk.TclError:
            pass

    def _l_completo(self, domanda):
        t = TESTI[self.lingua]
        try:
            t0 = time.time()
            t_passo = t0
            def _passo(nome, finito=False):
                nonlocal t_passo
                ora = time.time()
                if finito:
                    durata = ora - t_passo
                    self._tempo(nome, durata, ora - t0)
                    t_passo = ora
                else:
                    self._tempo(nome + " (in corso)", None, ora - t0)
            self._tempo("formulazione…", 0.0, 0.0)
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
            self._ui(self.bell)
            _salva_flag_primo_flusso()
        except Exception as e:
            self._ui(self._scrivi_errore, e)
        finally:
            self._ui(self._fine_lavoro)

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
        Le operazioni tkinter girano SOLO sul main thread (via _ui)."""
        if threading.current_thread() is not threading.main_thread():
            self._ui(self._flusso, colonna, pezzo)
            return
        colonna.box.configure(state="normal")
        colonna.box.insert("end", pezzo)
        colonna.box.see("end")
        colonna.box.configure(state="disabled")

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
            self._ui(self.c_finale.scrivi, self._riga_verdetto(risultato) + "\n" + risultato["testo"])
            self.ultimo_finale = finale
            self.ultimo_punti = risultato["testo"]
            self.ultimo_verdetto = risultato["verdetto"]
            self._messaggio_finale = "cross-check completato"
            self._ui(self.stato, "cross-check completato")
        except Exception as e:
            self._ui(self._scrivi_errore, e)

    def _riga_verdetto(self, risultato):
        """Riga [VERDETTO: … · metriche] in formato unico (cross-check e Correggi)."""
        met = risultato["metriche"]
        return (f"[VERDETTO: {risultato['verdetto']} · supportate {met['affermazioni_supportate']} "
                f"| non supportate {met['affermazioni_non_supportate']} | parole {met['parole_risposta']}]")

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
        try:
            j, md = self.canale.salva()
            nome = os.path.splitext(os.path.basename(j))[0]
            domanda = getattr(self, "_ultima_domanda", "") or self._ultimo("UTENTE")
            modelli = [self.canale.A.nome(), self.canale.B.nome()]
            c_terzo = getattr(self.canale, "C", None)
            if c_terzo is not None:
                modelli.append(c_terzo.nome())
            tid = aggiungi_sessione(nome, domanda, modelli, self.lingua, j, md,
                                    verdetto=getattr(self, "ultimo_verdetto", "") or "non verificata")
            self.stato(f"salvata: {md} · timeline evento {tid}")
        except Exception as e:
            self.c_finale.scrivi(f"ERRORE salvataggio: {e}")

    def _svuota(self):
        for c in (self.c_a, self.c_b, self.c_c, self.c_finale):
            c.box.configure(state="normal")
            c.box.delete("1.0", "end")
            c.box.configure(state="disabled")
        self._metti_placeholder()
        self.canale.allegati = []
        self.canale.cronologia = []
        self.canale.chiamate = 0
        self.canale.token_totali = {"in": 0, "out": 0}
        self.ultimo_verdetto = ""
        self.ultimo_finale = ""
        self.ultimo_punti = ""
        self._rigiri = 0
        self.dibattito_risultato = None

    def _voce_canale(self, modello):
        """Ritrova la voce del menu corrispondente al modello attivo del canale."""
        nome = modello.nome()
        for tipo, suffisso in (("Ollama:", "ollama"), ("OpenAI:", "openai"), ("Anthropic:", "anthropic")):
            if nome.startswith(tipo):
                m = nome.split(":", 1)[1]
                for v in self.opzioni:
                    if v.replace(_SUFFISSO_LENTO, "") == f"{m} · {suffisso}":
                        return v
        if nome.startswith("Mock"):
            return "mock"
        for v in self.opzioni:
            if v.startswith(nome + " · "):
                return v
        return self.opzioni[0] if self.opzioni else "mock"

    def _add_cartella(self):
        """Seleziona una cartella intera: carica tutti i file supportati (max 40)."""
        from tkinter import filedialog
        cartella = filedialog.askdirectory(title="Cartella — carica tutti i documenti/immagini")
        if not cartella:
            return
        supportati = [".txt", ".md", ".csv", ".py", ".json", ".log", ".tex", ".html",
                      ".yml", ".yaml", ".ini", ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"]
        file_trovati = []
        for radice, _, nomi in os.walk(cartella):
            for n in nomi:
                if os.path.splitext(n)[1].lower() in supportati:
                    file_trovati.append(os.path.join(radice, n))
            if len(file_trovati) >= 40:
                break
        file_trovati = file_trovati[:40]
        if not file_trovati:
            self._supervisore_appendi("[cartella] nessun file supportato trovato")
            return
        esiti = self.canale.aggiungi_file(file_trovati)
        for e in esiti:
            self._supervisore_appendi(f"[cartella] {e}")
        self.stato(f"cartella caricata ({len(esiti)} file)")

    def _add_files(self):
        """Selezione file (testo, PDF, immagini) da dare in pasto al canale."""
        from tkinter import filedialog
        percorsi = filedialog.askopenfilenames(
            title="ADD — seleziona documenti o immagini",
            filetypes=[("Documenti e immagini", "*.txt *.md *.csv *.py *.json *.log *.tex *.html *.pdf *.png *.jpg *.jpeg *.webp *.gif"),
                       ("Tutti i file", "*.*")])
        if not percorsi:
            return
        esiti = self.canale.aggiungi_file(list(percorsi))
        for e in esiti:
            self._supervisore_appendi(f"[allegato] {e}")
        self.stato(f"{len(esiti)} allegato/i aggiunto/i al canale")

    def _opzioni(self):
        """Finestra Opzioni: gestione completa dei clienti (aggiungi, modifica modelli, elimina, preset)."""
        fin = tk.Toplevel(self)
        fin.title("TRILogos — Opzioni / Clienti")
        fin.geometry("620x520")
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
                                     width=24, bg=PALETTE["sfondo"])
        if self.clienti:
            combo_clienti.current(0)
        combo_clienti.pack(side="left", padx=4)
        e_modello_nuovo = ttk.Entry(sel_bar, width=20)
        e_modello_nuovo.pack(side="left", padx=4)
        PulsanteRotondo(sel_bar, testo="＋ Modello", width=10,
                   comando=lambda: self._op_aggiungi_modello(fin, combo_clienti, e_modello_nuovo, lista)).pack(side="left", padx=2)
        PulsanteRotondo(sel_bar, testo="🗑 Elimina", width=9,
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
        PulsanteRotondo(fin, testo="✖ Chiudi", comando=fin.destroy).pack(side="right", padx=8, pady=8)
        PulsanteRotondo(fin, testo="🔑 API Key", width=9,
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
        self._aggiorna_menu_clienti()
        combo_clienti.configure(values=[c["nome"] for c in self.clienti])
        if self.clienti:
            combo_clienti.current(0)
        self._aggiorna_lista_clienti(lista)

    def _aggiorna_menu_clienti(self):
        """Rileva di nuovo i clienti e aggiorna i menu di LLM1/LLM2/LLM3 (dopo
        l'aggiunta di un client dallo splash o da Opzioni). La selezione
        corrente resta intatta (solo i values della combo cambiano)."""
        self.clienti = rileva_clienti()
        self.opzioni = _opzioni_etichettate(voci_modelli(self.clienti))
        for combo in (self.c_a.combo, self.c_b.combo, self.c_c.combo):
            combo.configure(values=self.opzioni)

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
                self._ui(self.c_finale.scrivi, self._riga_verdetto(esito_cross))
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
            nuovo = modello_da_voce(voce, self.clienti)
            if polo == "C":
                a = modello_da_voce(self.c_a.combo.get(), self.clienti)
                b = modello_da_voce(self.c_b.combo.get(), self.clienti)
                c = nuovo
            else:
                altro_polo = "B" if polo == "A" else "A"
                voce_altro = self.c_b.combo.get() if altro_polo == "B" else self.c_a.combo.get()
                altro = modello_da_voce(voce_altro, self.clienti)
                a = nuovo if polo == "A" else altro
                b = nuovo if polo == "B" else altro
                c = modello_da_voce(self.c_c.combo.get(), self.clienti) if SUPPORTA_C else None
            nome_profilo = self.combo_profilo.get() or next(iter(CONFIG["profili"]))
            ruoli = CONFIG["profili"].get(nome_profilo) or next(iter(CONFIG["profili"].values()))
            kwargs = dict(ruolo_a=ruoli["A"], ruolo_b=ruoli["B"],
                          max_turni_dibattito=CONFIG["canale"]["max_turni_dibattito"],
                          soglia_convergenza=CONFIG["canale"]["soglia_convergenza"],
                          max_chiamate=CONFIG["canale"].get("max_chiamate", 40),
                          lingua=self.lingua)
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