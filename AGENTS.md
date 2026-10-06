# AGENTS.md — TRILogos (N47Lab)

## Cos'è
TRILogos — orchestratore locale a tre voci (A · B · C) con risposta verificata: dibattito → sintesi → risposta univoca → cross-check → verdetto (CONFERMATA / DA_CORREGGERE / NON_CONCLUSO). Versione corrente: 3.0.0 (ARCA Engine).

## Vincoli non negoziabili
- **VINCOLO PRODOTTO (N47, 04/10/2026)**: TRILogos è un'applicazione **per gli utenti generici**, non sviluppata intorno a N47. Niente personalizzazioni, dati o contesti personali hardcoded; ogni contenuto specifico (contesti di progetto, profili) è caricato dall'utente (ADD / profili). Il branding N47Lab come autore/produttore resta legittimo.
- **PRECETTO PRIVACY**: prompt, domande, sessioni e timeline dell'utente restano SOLO sul PC — mai nel repository pubblico, nelle release, nelle relazioni o in rete, né per errore. Esclusioni git già attive: `.env`, `sessioni/*`, `timeline.json`, `clienti.json`, `stato.json`, `profili_locali.json`, `profili_n47lab.json` (legacy), `dev/`, `Documenti/`, `Immagini/`, `Backup/`, log.
- **CHIAVI**: cloud → solo il NOME della variabile d'ambiente nel `.env`; clienti custom → chiave reale ammessa SOLO nel registro locale `clienti.json` (gitignored) oppure `env:NOME`; mai nei file tracciati.
- **PRECETTO ORDINE**: ogni file nel proprio contenitore (`Documenti/`, `Immagini/`, `Test/`, `Backup/`, …); nessun file orfano; niente duplicati.
- **PROCESSO_RELEASE** (F0–F10) per ogni rilascio; standard visivo del laboratorio (`LabGUI`) per la UI; misure e verifiche su disco, mai memoria.

## Struttura
- `core/` — logica (13 moduli): `canale.py` (flusso 6 passi), `modelli.py` (adapter), `clienti.py` (rilevamento clienti), `timeline.py` (eventi research-timeline), `agenti.py` (squadra Ricerca), `motore.py` + `profiler.py` + `piano.py` + `runner_llama.py` + `downloader.py` (motore interno llama.cpp), `pulizia.py` (modalità pulita), `perimetro.py` (perimetro cartella progetto), `stato.py` (flag runtime)
- `gui.py` — UI Tk (TRIVOICE + Ricerca) · `LabGUI/` — widget condivisi · `rounded.py` — pulsanti
- `cli.py` — test da terminale · `Test/` — test locali (incluso `test_pulizia.py`) · `dev/` — script E2E (locale, gitignored)
- `Documenti/` — checklist e design (locale, gitignored) · `sessioni/` — dati utente (MAI pubblicati)
- `config.json` — profili e modelli · `.env` — chiavi BYOK (gitignored)
- `%APPDATA%\TRILogos\modelli\` — modelli del motore interno (fuori dal repo, mai pubblicati)

## Comandi (da `4_PROGETTO_TRILogos\`)
| Azione | Comando |
|--------|---------|
| GUI | `python gui.py` |
| CLI | `python cli.py` |
| Test pulizia | `python Test\test_pulizia.py file <...> \| live [N] \| nonconsenso [N] \| flusso [turni] [config\|veloce]` |
| Avvio Windows | `AvviaTRILogos.bat` |

Motore interno (opzionale): richiede `llama-server` — `winget install ggml.llamacpp`
oppure `TRILOGOS_LLAMA_DIR` sulla cartella che contiene `llama-server.exe`.
