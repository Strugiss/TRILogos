# TRILogos — three-voice dialogue with verified answers

[![Licenza: MIT](https://img.shields.io/badge/licenza-MIT-brightgreen?style=flat-square)](LICENSE)
[![Versione](https://img.shields.io/badge/versione-3.0.0-f0b429?style=flat-square)](https://github.com/Strugiss/TRILogos/releases)
[![Test](https://img.shields.io/badge/test-PASS-brightgreen?style=flat-square)]()
[![Piattaforma](https://img.shields.io/badge/Windows-10%2F11-0078D6?style=flat-square&logo=windows&logoColor=white)]()
[![BYOK](https://img.shields.io/badge/BYOK-local%20%2F%20cloud-8957e5?style=flat-square)]()

![TRILogos — user interface with the verified-answer flow](https://n47lab.altervista.org/triviumcad/immagini/TRILogos_v2.0.0_screenshot.png)

TRILogos is a local orchestrator that lets **three LLMs collaborate through prompts**
under the supervision of a human. The third voice is the **verifier "child"**: it
presumes every claim is wrong until proven, checks facts, signs and values, and
returns a structured verdict (`CONFERMATA` / `DA_CORREGGERE` / `NON_CONCLUSO`).

Flow (6 steps): the user asks **A** (LLM1), which analyzes and formulates the
request; **A**, **B** and **C** debate (C verifies every turn); the channel produces
the synthesis; a **unanimous answer** is approved by B+C; finally **C runs the
cross-check** against the available context and returns the verdict.

**Built-in engine — primary path (ARCA Engine)**: TRILogos 3.0 ships its own
local engine on top of **llama.cpp** — hardware profiler, resource plan, model
downloader with a hardware-tier catalog, vision support (mmproj). Models live in
`%APPDATA%\TRILogos\modelli\`. **External clients (optional)**: Ollama, LM Studio,
Jan (no network; Jan needs a placeholder API key, any string, set in the app's
Local API Server), or through existing clients (opencode, OpenAI, Anthropic, or
added by you). Keys are never stored: only environment variable names are
referenced (BYOK).

## Requirements
- Python 3.9+
- `requests>=2.34`
- `pypdf>=4.0` (**required** — PDF attachment extraction)
- `pymupdf` (optional — improved extraction for harder PDFs)
- `llama.cpp` for the built-in engine (optional): `winget install ggml.llamacpp`
  or set `TRILOGOS_LLAMA_DIR` to the folder containing `llama-server.exe`
- Models for the built-in engine are stored in `%APPDATA%\TRILogos\modelli\`
  (downloaded by the app; not distributed with the package)
- Ollama for external local models (optional): `winget install Ollama.Ollama`
  or https://ollama.com/download — then `ollama pull qwen2.5:3b`

## Installation
```bash
git clone https://github.com/Strugiss/TRILogos TRILogos
cd TRILogos
pip install -r requirements.txt
python gui.py          # GUI
python cli.py          # CLI test (mock, no keys)
```
On Windows you can also double-click `AvviaTRILogos.bat`.

Previous version: **2.0.0** installer — [download](https://n47lab.altervista.org/triviumcad/file/TRILogos_Setup_v2.0.0.exe).

## Configuration
- **First-run wizard (built-in engine)**: on first launch the guided window checks
  for `llama-server` and helps you install it and download the model that fits
  your hardware (catalog by tier); if the engine is not available, TRILogos
  transparently falls back to external clients.
- **Splash "Pronto all'uso"**: on startup TRILogos detects your local clients and
  shows their installation status (not installed → installer instructions + winget;
  installed but stopped → start it; active → models). The "✓ Primi passi" checklist
  auto-updates its four ticks (install Ollama / pull a model / connect the voices /
  ask your first question). The key input stays visible, plus a **Disconnetti**
  button and a "🔄 Riprova connessioni" re-test.
- **BYOK**: cloud keys live in `.env` (gitignored), never in clear; custom clients
  can use a real key (stored only in the local gitignored registry `clienti.json`)
  or `env:NAME`.
- **Clients**: 6 defaults (opencode, ollama, lmstudio, jan, openai, anthropic);
  add your own with the "➕ Aggiungi un client personalizzato" form
  (name / base URL / key / models). opencode is listed and read from its own config.

## Usage

![Three-voice orchestration flow](https://n47lab.altervista.org/trilogos/immagini/trilogos_flusso_3voci.png)

Flow (6 steps):
1. **A analyzes**: the first voice (LLM1) receives your question, analyzes it and
   formulates the request for B.
2. **A/B/C debate**: the three voices exchange positions (C verifies every turn)
   until convergence — or **early-exit** if they already agree from the start.
3. **Synthesis**: the channel summarizes and splits the work (who does what).
4. **Unanimous answer**: one shared answer, approved by **B+C**.
5. **C cross-check**: the verifier checks every claim against the context
   (attachments or system roles), marks `[SUPPORTATO]`/`[NON SUPPORTATO]`, and
   returns the verdict.
6. **Verdict**: `CONFERMATA` / `DA_CORREGGERE` / `NON_CONCLUSO` with deterministic
   metrics.

If the verdict is `DA_CORREGGERE`, press **✏️ Correggi** (user action, never
automatic, max 3 reruns; each rerun re-runs the cross-check). If the debate does
not converge, the C panel still shows the clean final answer (RISPOSTA +
FORMULA for rigorous profiles); the divergent positions are preserved in the
session report (verbale).

**Research mode**: with the "Ricerca" profile (🔎 Agenti panel) A/B/C plan a team
of specialized agents (type-safe JSON plan), execute it and discern the answer;
the `[CONFIDENZA: …]` line reports the minimum score across the three voices
(optimum threshold 8,99/10, up to 3 iterations, dedicated cap 200 calls).
**⏹ Interrompi**: while a flow is running, ✖ Svuota becomes **Interrompi** (same
spot, equivalent to Esc); it goes back to Svuota when the flow ends.

## Features
- **Built-in engine (ARCA Engine)**: llama.cpp runner with hardware profiler +
  resource plan (ngl/KV/thread/margins), model downloader with tier catalog,
  vision (mmproj), multi-selection queue, SHA256 checksum and resume.
- **🧹 Pulisci hardware**: clean mode — shows processes and estimated gain, and
  closes only what you select and confirm (never on its own, no forced kills).
- **🔎 Ricerca (agents)**: research profile with agent team, `[CONFIDENZA]` line
  (optimum threshold 8,99/10, minimum across voices), dedicated cap 200 calls.
- **Speed-ups (measured)**: parallel A+B debate, per-step token limits, Ollama
  keep_alive, Veloce preset, background warmup, num_ctx 8192 — full flow from
  784 s to 504 s, debate −44.7%.
- **Project perimeter**: results are written only to
  `<project folder>\TRILogos_output\` with unique names; ADD and reads stay free.
- **Copyable results**: selection + right-click menu (Copy / Copy all / Select all).
- **⏹ Interrompi**: contextual stop button (Svuota → Interrompi) in all 7 languages.
- **✏️ Correggi**: re-queues the answer with the verifier's points (max 3 reruns).
- **Verdict**: three outcomes (`CONFERMATA` / `DA_CORREGGERE` / `NON_CONCLUSO`).
- **Early-exit debate**: if the voices agree immediately, the debate is skipped.
- **7 languages** (IT · EN · FR · ES · DE · PT · 中文): UI and model responses switch live.
- **Attachments**: text, PDF (pypdf required; pymupdf optional), images, folders —
  up to 40 attachments per session (total; ADD is always available: reads are free
  and work without a project folder).
- **Sessions**: export JSON + readable Markdown, plus a typed timeline
  (research-timeline schema: metrics, evidence, ai_role; author configurable in
  `config.json → timeline.author`, neutral default). The unanimous result is saved
  into `<project folder>/TRILogos_output/` (📁 Project) with unique names — never
  overwritten.
- **Profiles** (👥): role presets for the voices in `config.json`; local profiles in
  `profili_locali.json` (gitignored; legacy `profili_n47lab.json` still read with a
  deprecation warning).
- **Step temperatures** (research-backed 2026): formulation 0.7, debate 0.7,
  synthesis 0.4, unanimous 0.4, revision 0.3, verification 0.2 — with per-voice
  convergence thresholds A=0.2 / B=0.5 / C=0.87.
- **Cap**: 60 calls per session (configurable in config.json → canale → max_chiamate).
- **Stopwatch** in the SUPERVISORE pill; live token in/out and call counter in the
  status bar.

## Version
Current version: **3.0.0** (ARCA Engine). See the
[CHANGELOG](CHANGELOG.md) for the full history.

## Links
- **N47Lab website**: https://n47lab.altervista.org/
- **TRILogos dedicated site**: https://n47lab.altervista.org/trilogos/
- **Guides**: [TUTORIAL.md](TUTORIAL.md) · [TUTORIAL_EN.md](TUTORIAL_EN.md) · [CHANGELOG.md](CHANGELOG.md)

## License
MIT — see [LICENSE](LICENSE).

TRILogos — N47Lab, 2026.
