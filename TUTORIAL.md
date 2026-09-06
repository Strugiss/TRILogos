# TUTORIAL TRILogos — guida all'uso (italiano)

## Cos'è
Un orchestratore locale che mette **tre LLM a collaborare tramite prompt** sotto la
supervisione dell'utente. La struttura è a quattro voci: **tu · LLM1 · LLM2 · LLM3**.
La terza voce (**LLM3**, il "bimbo" verificatore) presume ogni affermazione sbagliata
finché non è dimostrata: verifica fatti, segni e valori a ogni turno del dibattito e
dà il verdetto finale sulla risposta.

## Il flusso completo (passo per passo)
1. Scrivi una domanda nella barra **SUPERVISORE** e premi **Invio** (o ▶).
2. **A** (LLM1) la analizza e formula la richiesta per B.
3. **B** (LLM2) risponde con la sua analisi.
4. **Dibattito a 3**: A, B e C si scambiano le posizioni — C verifica a ogni turno —
   finché convergono. Soglie di convergenza per voce (proporzione di caratteri uguali
   nei primi 80): **A=0.2, B=0.5, C=0.87**. Se le voci concordano già all'inizio,
   il dibattito viene saltato (**early-exit**).
5. **Sintesi**: A scrive la sintesi finale e divide i compiti (chi fa cosa).
6. **Risposta univoca**: una sola posizione condivisa, approvata da **B+C**.
7. **🛡 Cross-check di C**: il verificatore controlla ogni affermazione della risposta
   contro il contesto (allegati o ruoli di sistema), marca `[SUPPORTATO]`/`[NON SUPPORTATO]`
   e dà il **verdetto**.
8. **💾 Salva sessione**: salva JSON + Markdown e registra l'evento nella timeline (T0, T1, …).

Se il verdetto è **DA_CORREGGERE**, premi **✏️ Correggi**: la risposta viene rigirata
al canale insieme ai punti del verificatore e il cross-check viene ri-eseguito
(max 3 rigiri; azione utente, mai automatica). Se il dibattito non converge, il
finale è marcato `[NON-CONSENSO]` con entrambe le posizioni preservate.

## Le funzioni essenziali
| Bottone | Cosa fa |
|---|---|
| ▶ | Invia la domanda e avvia il flusso completo |
| ⚡ Dibattito | Solo il passo del dibattito a 3 voci |
| ✓ Sintesi | Solo sintesi + risposta univoca |
| ◆ Risposta univoca | Rigenera la risposta consensuale |
| 🛡 Cross-check | Verifica anti-allucinazione con fonti |
| ✏️ Correggi | Rigira la risposta con i punti del verificatore (max 3 rigiri) |
| 💾 Salva | Salva sessione + evento timeline |
| ✖ Svuota | Pulisce canale e allegati |
| ⚙ | Opzioni: clienti (rilevati + aggiunta manuale) |
| 🌐 (menu lingua) | Cambia lingua di interfaccia e risposte dei modelli |
| 👥 (menu profili) | Sceglie il profilo dei ruoli delle voci |

## Il verdetto e cosa significa
- **CONFERMATA**: il verificatore non trova errori: la risposta è confermata dal contesto.
- **DA_CORREGGERE**: il verificatore trova errori: premi **✏️ Correggi** (max 3 rigiri) o rivedi la risposta.
- **NON_CONCLUSO**: il verificatore non riesce né a confermare né a smentire: la risposta resta, ma non è dimostrata dal contesto.

## Modelli
- **Menu a tendina** sopra i riquadri LLM1/LLM2/LLM3: scegli i modelli indipendentemente.
- **Locale** (autonomia, zero chiavi): Ollama, LM Studio, Jan.
- **Cloud** (tramite clienti configurati): opencode, OpenAI, Anthropic, o i clienti
  che aggiungi in ⚙ (chiave = solo nome di variabile d'ambiente, mai in chiaro).
- **Ollama consigliato** (il più leggero): `winget install Ollama.Ollama` (o
  https://ollama.com/download), poi `ollama pull qwen2.5:3b`.
- **Velocità**: i modelli pesanti sono etichettati **"(lento)"** nei menu: il primo
  caricamento richiede 1-2 minuti; ogni risposta 20-60 secondi (CPU). Per prove
  rapide usa un modello piccolo (1.5b/3b).

## Clienti (dalla splash "Pronto all'uso")
All'avvio TRILogos rileva automaticamente i clienti locali e mostra il loro stato:
- **non installato** → istruzioni per l'installer + comando winget;
- **installato ma spento** → avvialo;
- **attivo** → elenca i modelli.

Le chiavi cloud vanno nel file `.env` (ignorato da git), mai in chiaro. Per un
client personalizzato usa il form **"➕ Aggiungi un client personalizzato"**
(nome / base URL / chiave / modelli), con chiave reale o `env:NOME`. opencode è
in lista. Con **"🔄 Riprova connessioni"** ritesti tutto.

## Le prime 4 cose da fare (checklist "✓ Primi passi")
1. **Installa Ollama** (`winget install Ollama.Ollama`).
2. **Scarica un modello** (`ollama pull qwen2.5:3b`).
3. **Connetti le voci** (scegli un modello in ogni menu LLM1/LLM2/LLM3).
4. **Fai la tua prima domanda** (barra SUPERVISORE + Invio).

La checklist si aggiorna da sola a ogni spunta.

## Allegati (dare contesto al canale)
- Premi **📁 Cartella** e seleziona una cartella di documenti, oppure **➕ ADD** per
  file singoli (max 40 file).
- Testo, PDF (estrazione con pypdf; pymupdf opzionale per PDF più difficili) e
  immagini (inviate ai modelli multimodali).
- Il cross-check verifica contro questi allegati (o contro i ruoli se non ci sono).

## Sessioni, timeline e profili
- **💾 Salva**: sessione esportata in JSON + Markdown leggibile.
- **Timeline**: ogni sessione salvata diventa un evento tipizzato (T0, T1, …) in
  `timeline.json`, compatibile con lo schema research-timeline (metriche, evidence,
  ai_role).
- **👥 Profili**: i ruoli delle voci vivono in `config.json` (profili → A/B/C);
  puoi personalizzarli o aggiungere un file `profili_n47lab.json` (non distribuito,
  ignorato da git) con i tuoi profili privati.

## Note tecniche
- **Cap**: 60 chiamate per sessione (configurabile in config.json → canale → max_chiamate).
- **Temperatura per passo** (ricerca 2026): formulazione 0.7, dibattito 0.7,
  sintesi 0.4, univoca 0.4, revisione 0.3, verifica 0.2 — configurabile nel costruttore del canale.
- **Soglie di convergenza per voce**: A=0.2, B=0.5, C=0.87 — configurabili in
  config.json → canale → soglie.
- **7 lingue**: IT · EN · FR · ES · DE · PT · 中文.
- **Timeout rete**: 10 s (connessione) / 120 s (lettura) — configurabili in config.json → rete.
- **Requisiti**: Python 3.9+, `requests>=2.34`, `pypdf>=4.0` (obbligatorio),
  `pymupdf` (opzionale).
- Contatore token nella barra di stato: `token: X in / Y out` + chiamate eseguite.

## Risoluzione problemi
| Problema | Soluzione |
|---|---|
| "Server spento" | Avvia Ollama (o LM Studio / Jan) e premi "🔄 Riprova connessioni" |
| "Modello non trovato" | `ollama pull qwen2.5:3b`, poi riavvia il client |
| Timeout rete | Aumenta i timeout in config.json → rete, o usa un modello locale |

Firmato: N47Lab — 06/09/2026
