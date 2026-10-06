# Changelog

Registro delle versioni di TRILogos — tutte le modifiche rilevanti.

## [3.0.0] - 2026-10-06 — TRILogos 3.0 «ARCA Engine»

### Migliorie eclatanti
- **Motore interno "ARCA Engine"**: TRILogos esegue i modelli GGUF in casa, senza
  clienti esterni — Profiler hardware (VRAM/RAM/CPU/disco, sola lettura), Piano
  risorse (ngl/KV/thread/margine/budget RAM, dalle regole misurate ARCA), runner
  `llama-server` (localizzazione eseguibile, readiness, streaming, stop pulito
  senza orfani) e downloader modelli con **catalogo per fascia hardware**
  (0,5B/3B/7B/14B + **vision con mmproj**), **coda multi-selezione**,
  **checksum SHA256** e **ripresa** dai file `.parziale`; modelli in
  `%APPDATA%\TRILogos\modelli\`.
- **Primo avvio guidato**: finestra guidata del motore (installazione llama.cpp
  + download del modello adatto all'hardware rilevato); se il motore non è
  disponibile, **fallback sui clienti esterni** (Ollama, LM Studio, Jan, cloud
  BYOK) senza interrompere l'utente.
- **Modalità pulita "🧹 Pulisci hardware"**: analisi VRAM/RAM per processo con
  guadagno stimato, selezione a checkbox e conferma esplicita; MAI chiusure
  automatiche, mai kill forzato, whitelist di sistema e blacklist python/TRILogos.
- **Profilo "Ricerca" con squadra di agenti**: A/B/C pianificano la squadra
  (piano JSON type-safe), la eseguono e discernono la risposta con **soglia di
  ottimo 8,99/10** sul **minimo delle tre voci** (max 3 iterazioni, cap dedicato
  200 chiamate); pannello **🔎 Agenti** e riga **[CONFIDENZA: …]** nella zona C.
- **Velocizzazione (misure reali)**: flusso completo da **784 s → 504 s**,
  dibattito **−44,7%** — dibattito A+B **parallelo**, **limiti token per passo**,
  **keep_alive** (modello mai scaricato tra i turni), preset **Veloce**,
  **warmup** in background, **num_ctx 8192**.
- **Risposta univoca pulita**: sezioni **RISPOSTA + FORMULA** per i profili
  rigorosi e zona C **sempre pulita** — anche nel NON-CONSENSO, senza blocchi
  "Posizione" né meta-testo.
- **Perimetro cartella progetto**: i risultati si scrivono SOLO in
  `<cartella progetto>\TRILogos_output\`, con **nomi univoci** mai sovrascritti;
  ADD e letture restano liberi (anche senza cartella progetto).

### Migliorie rilevanti
- **Pulsante contestuale ⏹ Interrompi** (7 lingue): durante l'elaborazione
  "Svuota" diventa "Interrompi" (stesso posto, equivalente a Esc); torna "Svuota"
  a fine lavoro.
- **Risultati copiabili**: riquadri in sola selezione con menu tasto destro
  (Copia / Copia tutto / Seleziona tutto).
- **Status bar composta**: messaggio di stato + cronometro (passo/totale), 📁
  progetto e **🧹 Pulisci HW** sempre visibile.
- **13° pulsante 🔎 Agenti**: pannello della squadra di ricerca, attivo anche
  durante l'elaborazione.
- **Avvio GUI asincrono**: la finestra appare subito; il rilevamento dei clienti
  avviene in background (solo porte locali, mai rete esterna).
- **stato.json**: flag runtime (primo_flusso_ok, byok_splash) fuori dal
  config.json tracciato; scrittura atomica, file gitignored.
- **Timeout configurabili** (config.json → rete): 10 s connessione / 120 s lettura.
- **Author timeline neutro**: default "Utente" in config.json → timeline.author.
- **profili_locali.json con fallback**: il legacy `profili_n47lab.json` resta
  letto (con avviso) come deprecato.
- **`Test\test_pulizia.py`**: test di pulizia delle risposte (modalità file,
  live, nonconsenso, flusso) pubblicato nel repo.
- **`AGENTS.md`**: guida per gli agenti di sviluppo, pubblicata nel repo.

### Fix
- Bordo dei widget LabGUI corretto (resize e clipping).
- Pill viola eliminata (palette uniforme).
- Etichetta "(lento)" localizzata nelle 7 lingue.
- CLI: avanzamento [1/6]…[6/6] leggibile.
- pymupdf dichiarato opzionale (requirements + estrazione PDF).
- Cap allegati 40 coerente tra codice, README e help.
- Soglia A operativa nel dibattito a tre (AN-1).
- Usage malformato delle voci senza fallback (AN-2).
- D3: zona C pulita a nuovo avvio (nessun residuo del flusso precedente).
- Layout zona A/status: allineamento ricalcolato.
- Fix A1–A12 dell'audit documentazione.

## [2.0.0] - 2026-09-06

### Migliorie eclatanti
- **Terza voce TRIVOICE**: il dibattito passa da 2 a 3 LLM — LLM3 è il verificatore
  "bimbo" che presume ogni affermazione sbagliata finché non è dimostrata, nel giro
  del dibattito (temperature 0.2). Soglie di convergenza per voce (proporzione di
  caratteri uguali nei primi 80): A=0.2, B=0.5, C=0.87. Temperature per passo:
  formulazione 0.7, dibattito 0.7, sintesi 0.4, univoca 0.4, revisione 0.3,
  verifica 0.2.
- **✏️ Correggi**: quando il verdetto è DA_CORREGGERE, l'utente può rigirare la
  risposta al canale con i punti del verificatore (azione utente, mai automatica);
  ri-esegue il cross-check, max 3 rigiri.
- **Splash "TRILogos — Pronto all'uso"**: rilevamento automatico dei clienti locali
  con stato di installazione (non installato → istruzioni installer + winget;
  installato-spento → avvialo; attivo → modelli), consiglio "Ollama — il più leggero"
  (`winget install Ollama.Ollama`, `ollama pull qwen2.5:3b`) e checklist "✓ Primi
  passi" con 4 spunte auto-aggiornanti (Installa Ollama / Scarica un modello /
  Connetti le voci / Fai la tua prima domanda).
- **BYOK**: chiavi cloud solo nel `.env` (gitignored), mai in chiaro; clienti
  personalizzati con chiave reale o `env:NOME`.
- **Clienti personalizzati end-to-end**: form "➕ Aggiungi un client personalizzato"
  (nome/base URL/chiave/modelli) e pulsante "🔄 Riprova connessioni".
- **Layout TRIVOICE al pixel**: barra SUPERVISORE 84px, 4 riquadri (colonna pulsanti
  + LLM1/LLM2/LLM3), risposta univoca 142px — misure verificate.
- **Icona ufficiale** `icona_trilogos.ico` (due volti + formula PASM).

### Migliorie rilevanti
- **Cronometro** nel pill SUPERVISORE.
- **6 clienti di default**: opencode, ollama, lmstudio, jan, openai, anthropic.
- **Etichetta "(lento)"** sui modelli pesanti nei menu.
- **Stile ambra** uniforme (dettagli #f0b429, hover #f7c948, angoli arrotondati 12).
- **Timeline potenziata**: sessioni come eventi tipizzati compatibili con lo schema
  research-timeline (metriche, evidence, ai_role).
- **Anti-iniezione allegati**: contenuti degli allegati neutralizzati come contesto.
- **Cap 60 chiamate** per sessione (configurabile in config.json → canale → max_chiamate).
- **Timeout rete** (10 s connessione / 120 s lettura) configurabili in config.json → rete.

### Fix
- Click sui pulsanti con stato hover: i pulsanti "morti" che ingoiavano il click
  ora rispondono al percorso reale (hover → click).
- Coda UI robusta: nessuna perdita di aggiornamenti sui riquadri di dialogo.
- Errori di rete in italiano, senza eccezioni grezze a schermo.
- Timeout di rete gestiti esplicitamente (10/120).
- Fallback a 3 voci quando una voce fallisce (cap onorato a ogni passo).
- Guardia anti-opencode: il nome 'opencode' è riservato alla configurazione
  dell'assistente, non ai clienti personalizzati.
- Harness di test ampliato: copre la sequenza completa degli eventi reali
  (Enter → hover → click), non solo l'evento finale simulato.

TRILogos — N47Lab, 2026.
