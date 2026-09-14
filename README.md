# TRILogos — Tre voci che dibattono, una risposta verificata (by N47Lab)

Orchestratore open source per LLM: dibattito a tre voci + verdetto di verifica.

[![Licenza: MIT](https://img.shields.io/badge/licenza-MIT-brightgreen?style=flat-square)](LICENSE)
[![Versione](https://img.shields.io/badge/versione-2.0.0-f0b429?style=flat-square)](https://github.com/Strugiss/TRILogos/releases)
[![Test](https://img.shields.io/badge/test-277%20PASS-brightgreen?style=flat-square)]()
[![Piattaforma](https://img.shields.io/badge/Windows-10%2F11-0078D6?style=flat-square&logo=windows&logoColor=white)]()
[![BYOK](https://img.shields.io/badge/BYOK-local%20%2F%20cloud-8957e5?style=flat-square)]()

![TRILogos v2.0.0 — interfaccia con il flusso a tre voci](https://n47lab.altervista.org/triviumcad/immagini/TRILogos_v2.0.0_screenshot.png)

## Il problema, la soluzione

Un solo LLM può sbagliare con sicurezza: nessuno controlla, e l'errore arriva all'utente senza avvisaglie. **TRILogos** mette tre modelli a lavorare insieme sotto la supervisione umana: **A** propone, **B** analizza, **C** verifica ogni affermazione a temperatura 0.2 (logica pura). Il risultato è una risposta univoca approvata, accompagnata da un verdetto onesto — `CONFERMATA`, `DA_CORREGGERE` o `NON_CONCLUSO`. Funziona in locale (Ollama, LM Studio, Jan) o col cloud: le chiavi restano le tue (BYOK), mai in chiaro. L'obiettivo non è promettere risposte perfette, ma rendere visibile il processo di verifica.

## Come funziona — il flusso in 6 passi

![Flusso di orchestrazione a tre voci](https://n47lab.altervista.org/trilogos/immagini/trilogos_flusso_3voci.png)

1. **Domanda** — il quesito entra nel "filo d'accordo" e viene inoltrato a tutte le voci
2. **A formula** — la prima voce produce la risposta iniziale
3. **Dibattito A/B/C** — tre turni: B obietta e propone alternative, C verifica ogni affermazione a temperatura 0.2
4. **Sintesi** — convergenza sulle soglie per voce: A 0.2, B 0.5, C 0.87
5. **Risposta univoca** — approvata da B e C in un riquadro dedicato
6. **Cross-check** — C esegue il controllo finale ed emette il verdetto

Se il verdetto è `DA_CORREGGERE`, premi **✏️ Correggi** (max 3 rigiri, mai automatico) e il dibattito riparte con le correzioni indicate.

## Funzionalità

| Funzionalità | Dettagli |
|---|---|
| ⭐ **Tre voci + verificatore C** | A propone, B analizza, C verifica con logica pura a temperatura 0.2; la soglia più severa (0.87) è quella del verificatore |
| ⭐ **Verdetto onesto** | `CONFERMATA` / `DA_CORREGGERE` / `NON_CONCLUSO` con metriche deterministiche; se il dibattito non converge, la risposta è marcata `[NON-CONSENSO]` |
| ⭐ **BYOK — Bring Your Own Key** | Modelli locali (Ollama, LM Studio, Jan) o cloud (OpenAI, Anthropic, clienti personalizzati). Le chiavi vivono nel tuo `.env` locale: mai in chiaro, mai mostrate |
| **7 lingue** | Interfaccia e risposte dei modelli: IT · EN · FR · ES · DE · PT · 中文, cambio a caldo |
| **277 test automatici** | Suite su GUI, canale, modelli e clienti (277 PASS) |
| **Allegati** | Testo, PDF (pypdf; pymupdf opzionale), immagini e cartelle — fino a 40 file |
| **Sessioni** | Export JSON + Markdown leggibile + timeline tipizzata (schema research-timeline: metriche, evidence, ai_role) |
| **Profili** | Preset di ruolo per le voci in `config.json` |
| **Temperature per fase** | Formulazione 0.7, dibattito 0.7, sintesi 0.4, unanime 0.4, revisione 0.3, verifica 0.2 |
| **Early-exit** | Se le voci sono già d'accordo all'inizio, il dibattito viene saltato |
| **Cap chiamate** | 60 chiamate per sessione (configurabile in `config.json`) |
| **Cruscotto** | Cronometro nel pill SUPERVISORE, token in/out e contatore chiamate nella status bar |

## Installazione

### Windows (installer pronto)

1. Scarica **TRILogos_Setup_v2.0.0.exe**: [download diretto](https://n47lab.altervista.org/triviumcad/file/TRILogos_Setup_v2.0.0.exe) (anche dalla [pagina del sito](https://n47lab.altervista.org/trilogos/))
2. Esegui l'installer e avvia **TRILogos**
3. Collega le voci: modelli locali rilevati automaticamente (Ollama, LM Studio, Jan) o chiavi cloud nel `.env` (BYOK)

### Da sorgente

Richiede **Python 3.9+**.

```bash
git clone https://github.com/Strugiss/TRILogos
cd TRILogos
pip install -r requirements.txt
python gui.py     # GUI
python cli.py     # CLI di test (mock, senza chiavi)
```

Su Windows puoi anche fare doppio clic su `AvviaTRILogos.bat`. Per i modelli locali: `winget install Ollama.Ollama` (oppure https://ollama.com/download), poi `ollama pull qwen2.5:3b`.

## Quick Start

1. **Avvia TRILogos**: lo splash "Pronto all'uso" rileva i client installati e la checklist "Primi passi" si spunta da sola (Ollama / modello / voci / prima domanda)
2. **Scegli le voci**: client locale (Ollama, LM Studio, Jan) o cloud via BYOK; puoi aggiungere client personalizzati con nome, base URL, chiave e modelli
3. **Fai la domanda**: segui il flusso a 6 passi e leggi la risposta univoca con il verdetto di C

## Struttura del repository

```
TRILogos/
├── gui.py             # interfaccia grafica (Tkinter)
├── cli.py             # CLI di test (mock, senza chiavi)
├── rounded.py         # widget arrotondati (stile N47Lab)
├── core/
│   ├── canale.py      # flusso a 6 passi, dibattito, soglie, verdetto
│   ├── clienti.py     # client locali/cloud, BYOK, rilevamento
│   ├── modelli.py     # rilevamento e gestione modelli
│   └── timeline.py    # timeline tipizzata delle sessioni
├── LabGUI/            # profilo grafico condiviso N47Lab
├── config.json        # voci, soglie, temperature, cap
├── requirements.txt   # dipendenze
└── pyproject.toml     # packaging
```

## Link

- **Sito N47Lab**: https://n47lab.altervista.org/
- **TRILogos — sito dedicato**: https://n47lab.altervista.org/trilogos/
- **Download**: https://n47lab.altervista.org/triviumcad/file/TRILogos_Setup_v2.0.0.exe
- **Guide**: [TUTORIAL.md](TUTORIAL.md) · [TUTORIAL_EN.md](TUTORIAL_EN.md) · [CHANGELOG.md](CHANGELOG.md)

## Licenza

MIT — vedi [LICENSE](LICENSE). © 2026 N47Lab (Alessandro Tulli).

## Contatti

**N47Lab** — laboratorio di ricerca e sviluppo software.
Sito: https://n47lab.altervista.org/ · GitHub: [@Strugiss](https://github.com/Strugiss)
