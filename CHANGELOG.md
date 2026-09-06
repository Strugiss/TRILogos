# Changelog

Registro delle versioni di TRILogos — tutte le modifiche rilevanti.

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
