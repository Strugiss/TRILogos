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
(max 3 rigiri; azione utente, mai automatica). Se il dibattito non converge, la
zona C mostra sempre la risposta pulita (RISPOSTA + FORMULA per i profili
rigorosi); le posizioni divergenti restano preservate nel verbale.

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
| ✖ Svuota | Pulisce canale e allegati; durante l'elaborazione diventa **⏹ Interrompi** (stesso posto, come Esc) |
| 🔎 Agenti | Apre il pannello della squadra di ricerca (profilo Ricerca) |
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
  che aggiungi in ⚙. Chiavi: cloud → solo il NOME della variabile d'ambiente nel
  `.env`; clienti custom → chiave reale ammessa SOLO nel registro locale
  `clienti.json` (gitignored) oppure `env:NOME`; mai nei file tracciati.
- **Ollama consigliato** (il più leggero): `winget install Ollama.Ollama` (o
  https://ollama.com/download), poi `ollama pull qwen2.5:3b`.
- **Velocità**: i modelli pesanti sono etichettati **"(lento)"** nei menu: il primo
  caricamento richiede 1-2 minuti; ogni risposta 20-60 secondi (CPU). Per prove
  rapide usa un modello piccolo (1.5b/3b).

## Motore interno (llama.cpp)
TRILogos 3.0 può eseguire i modelli GGUF **in casa**, senza clienti esterni:
- **Primo avvio guidato**: la finestra guidata controlla `llama-server` e ti
  accompagna nell'installazione e nel download del modello adatto al tuo hardware.
- **Requisiti**: `winget install ggml.llamacpp` oppure imposta la variabile
  d'ambiente `TRILOGOS_LLAMA_DIR` sulla cartella che contiene `llama-server.exe`.
  Se manca, TRILogos usa senza interruzioni i clienti esterni (Ollama, LM Studio,
  Jan, cloud BYOK).
- **Downloader**: catalogo per fascia hardware (0,5B, 3B, 7B, 14B; vision 3B con
  mmproj), coda multi-selezione, ripresa dei download interrotti (file
  `.parziale`) e verifica **checksum SHA256**.
- **Dove finiscono i modelli**: `%APPDATA%\TRILogos\modelli\` (mai nel progetto).
- **Piano risorse automatico**: il profiler rileva VRAM/RAM/CPU/disco e il piano
  risorse decide ngl/KV/thread/margine per il modello scelto; i server si fermano
  da soli a fine flusso (nessun processo orfano).

## Profilo Ricerca (squadra di agenti)
Con il profilo **Ricerca** (menu 👥) il flusso diventa un progetto di ricerca:
1. **Pianificazione**: A propone la squadra di agenti specializzati (piano JSON
   verificato da B e C).
2. **Esecuzione**: ogni agente produce il suo contributo (pannello **🔎 Agenti**).
3. **Discernimento**: A scrive la risposta finale, B la rivede; A/B/C la valutano
   0-10 e si itera finché il **minimo delle tre voci** raggiunge la **soglia di
   ottimo 8,99/10** (max 3 iterazioni).

La riga **[CONFIDENZA: …]** nella zona C mostra punteggio, soglia, iterazione e
motivo dello stop. Cap dedicato: **200 chiamate** (config.json → ricerca). Il
risultato va in `<cartella progetto>\TRILogos_output\`.

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
- Premi **📁 Progetto** per scegliere la cartella del tuo progetto (il **perimetro
  di scrittura**: lì va il risultato salvato), oppure **➕ ADD** per file singoli:
  le letture sono libere e ADD funziona **anche senza cartella progetto**.
- Cap totale: **max 40 allegati per sessione**.
- Testo, PDF (estrazione con pypdf; pymupdf opzionale per PDF più difficili) e
  immagini (inviate ai modelli multimodali).
- Il cross-check verifica contro questi allegati (o contro i ruoli se non ci sono).
- **💾 Salva**: la sessione va sempre in `sessioni/`; il **risultato** (risposta
  univoca) viene salvato in `<cartella progetto>/TRILogos_output/` con nome univoco
  (mai sovrascritto: `risultato_2.md`, `risultato_3.md`, …). Senza cartella
  progetto compare un avviso informativo ("Per salvare il risultato scegli la
  cartella progetto (📁 Progetto)").

## Sessioni, timeline e profili
- **💾 Salva**: sessione esportata in JSON + Markdown leggibile.
- **Timeline**: ogni sessione salvata diventa un evento tipizzato (T0, T1, …) in
  `timeline.json`, compatibile con lo schema research-timeline (metriche, evidence,
  ai_role).
- **👥 Profili**: i ruoli delle voci vivono in `config.json` (profili → A/B/C);
  puoi personalizzarli o aggiungere un file `profili_locali.json` (non distribuito,
  ignorato da git) con i tuoi profili privati. Il vecchio nome
  `profili_n47lab.json` è ancora letto come fallback (con avviso) ma è deprecato.
- **Author timeline**: chi vuole firmare i propri eventi imposta `config.json →
  timeline.author` (nome, affiliazione, ORCID, background); senza configurazione
  vale l'autore neutro "Utente".

## Note tecniche
- **Cap**: 60 chiamate per sessione (configurabile in config.json → canale → max_chiamate).
- **Temperatura per passo** (ricerca 2026): formulazione 0.7, dibattito 0.7,
  sintesi 0.4, univoca 0.4, revisione 0.3, verifica 0.2 — configurabile nel costruttore del canale.
- **Soglie di convergenza per voce**: A=0.2, B=0.5, C=0.87 — configurabili in
  config.json → canale → soglie. Nel dibattito a tre, dopo ogni turno completo:
  A è confrontata con la posizione di C (soglia A), B e C con quella di A (soglie B/C).
- **7 lingue**: IT · EN · FR · ES · DE · PT · 中文.
- **Timeout rete**: 10 s (connessione) / 120 s (lettura) — configurabili in config.json → rete.
- **Dibattito parallelo**: A+B in parallelo (fallback sequenziale automatico se
  una voce fallisce); limiti token per passo in config.json → canale → limiti_token.
- **Ollama**: `keep_alive` -1 (modello mai scaricato tra i turni), `num_ctx` 8192
  e warmup in background dei modelli lenti — configurabili in config.json → ollama.
- **Cap Ricerca**: 200 chiamate (config.json → ricerca → max_chiamate).
- **Copiabilità**: i riquadri sono in sola selezione; tasto destro per
  Copia / Copia tutto / Seleziona tutto.
- **Requisiti**: Python 3.9+, `requests>=2.34`, `pypdf>=4.0` (obbligatorio),
  `pymupdf` (opzionale); `llama.cpp` (opzionale) per il motore interno.
- Contatore token nella barra di stato: `token: X in / Y out` + chiamate eseguite.

## Risoluzione problemi
| Problema | Soluzione |
|---|---|
| "Server spento" | Avvia Ollama (o LM Studio / Jan) e premi "🔄 Riprova connessioni" |
| "Modello non trovato" | `ollama pull qwen2.5:3b`, poi riavvia il client |
| Timeout rete | Aumenta i timeout in config.json → rete, o usa un modello locale |
| llama.cpp assente | Il motore interno si disattiva: `winget install ggml.llamacpp` o variabile `TRILOGOS_LLAMA_DIR`, oppure usa i clienti esterni |
| Download interrotto | Rilancia il download: riprende dal file `.parziale` (HTTP Range) e verifica il checksum a fine |
| Pulisci HW | Mostra solo proposte con guadagno stimato; nessuna chiusura automatica: seleziona e conferma |

Firmato: N47Lab — 06/10/2026 (TRILogos 3.0 «ARCA Engine»)
