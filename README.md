# TRILogos — three-voice dialogue with verified answers

TRILogos is a local orchestrator that lets **three LLMs collaborate through prompts**
under the supervision of a human. The third voice is the **verifier "child"**: it
presumes every claim is wrong until proven, checks facts, signs and values, and
returns a structured verdict (`CONFERMATA` / `DA_CORREGGERE` / `NON_CONCLUSO`).

Flow (6 steps): the user asks **A** (LLM1), which analyzes and formulates the
request; **A**, **B** and **C** debate (C verifies every turn); the channel produces
the synthesis; a **unanimous answer** is approved by B+C; finally **C runs the
cross-check** against the available context and returns the verdict.

**Local or cloud**: works in full autonomy with local models (Ollama, LM Studio,
Jan — no network; Jan needs a placeholder API key, any string, set in the app's
Local API Server), or through existing clients (opencode, OpenAI, Anthropic, or
added by you). Keys are never stored: only environment variable names are
referenced (BYOK).

## Screenshot
_Screenshot coming soon._

## Requirements
- Python 3.9+
- `requests>=2.34`
- `pypdf>=4.0` (**required** — PDF attachment extraction)
- `pymupdf` (optional — improved extraction for harder PDFs)
- Ollama for local models (optional but recommended): `winget install Ollama.Ollama`
  or https://ollama.com/download — then `ollama pull qwen2.5:3b`

## Installation
```bash
git clone <your-repo-url> TRILogos
cd TRILogos
pip install -r requirements.txt
python gui.py          # GUI
python cli.py          # CLI test (mock, no keys)
```
On Windows you can also double-click `AvviaTRILogos.bat`.

## Configuration
- **Splash "Pronto all'uso"**: on startup TRILogos detects your local clients and
  shows their installation status (not installed → installer instructions + winget;
  installed but stopped → start it; active → models). The "✓ Primi passi" checklist
  auto-updates its four ticks (install Ollama / pull a model / connect the voices /
  ask your first question). The key input stays visible, plus a **Disconnetti**
  button and a "🔄 Riprova connessioni" re-test.
- **BYOK**: cloud keys live in `.env` (gitignored), never in clear; custom clients
  can use a real key or `env:NAME`.
- **Clients**: 6 defaults (opencode, ollama, lmstudio, jan, openai, anthropic);
  add your own with the "➕ Aggiungi un client personalizzato" form
  (name / base URL / key / models). opencode is listed and read from its own config.

## Usage
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
not converge, the final answer is marked `[NON-CONSENSO]` and preserves both
positions.

## Features
- **✏️ Correggi**: re-queues the answer with the verifier's points (max 3 reruns).
- **Verdict**: three outcomes (`CONFERMATA` / `DA_CORREGGERE` / `NON_CONCLUSO`).
- **Early-exit debate**: if the voices agree immediately, the debate is skipped.
- **7 languages** (IT · EN · FR · ES · DE · PT · 中文): UI and model responses switch live.
- **Attachments**: text, PDF (pypdf required; pymupdf optional), images, folders —
  up to 40 files.
- **Sessions**: export JSON + readable Markdown, plus a typed timeline
  (research-timeline schema: metrics, evidence, ai_role).
- **Profiles** (👥): role presets for the voices in `config.json`.
- **Step temperatures** (research-backed 2026): formulation 0.7, debate 0.7,
  synthesis 0.4, unanimous 0.4, revision 0.3, verification 0.2 — with per-voice
  convergence thresholds A=0.2 / B=0.5 / C=0.87.
- **Cap**: 60 calls per session (configurable in config.json → canale → max_chiamate).
- **Stopwatch** in the SUPERVISORE pill; live token in/out and call counter in the
  status bar.

## Version
Current version: **2.0.0** (TRIVOICE: three voices). See the
[CHANGELOG](CHANGELOG.md) for the full history.

## License
MIT — see [LICENSE](LICENSE).

TRILogos — N47Lab, 2026.
