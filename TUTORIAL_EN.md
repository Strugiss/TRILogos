# TRILogos TUTORIAL — user guide (English)

## What it is
A local orchestrator that lets **three LLMs collaborate through prompts** under human
supervision. The structure has four voices: **you · LLM1 · LLM2 · LLM3**.
The third voice (**LLM3**, the verifier "child") presumes every claim is wrong until
proven: it checks facts, signs and values at every turn of the debate and gives the
final verdict on the answer.

## The full flow (step by step)
1. Type a question in the **SUPERVISORE** bar and press **Enter** (or ▶).
2. **A** (LLM1) analyzes it and formulates the request for B.
3. **B** (LLM2) replies with its analysis.
4. **Three-voice debate**: A, B and C exchange positions — C verifies every turn —
   until convergence. Per-voice convergence thresholds (proportion of identical
   characters in the first 80): **A=0.2, B=0.5, C=0.87**. If the voices already agree
   from the start, the debate is skipped (**early-exit**).
5. **Summary**: A writes the final summary and splits the work (who does what).
6. **Unanimous answer**: one shared position, approved by **B+C**.
7. **🛡 C cross-check**: the verifier checks every claim of the answer against the
   context (attachments or system roles), marks `[SUPPORTATO]`/`[NON SUPPORTATO]`,
   and gives the **verdict**.
8. **💾 Save session**: saves JSON + Markdown and registers the event in the timeline (T0, T1, …).

If the verdict is **DA_CORREGGERE**, press **✏️ Correggi**: the answer is re-queued
to the channel together with the verifier's points and the cross-check is re-run
(max 3 reruns; user action, never automatic). If the debate does not converge, the
C panel still shows the clean final answer (RISPOSTA + FORMULA for rigorous
profiles); the divergent positions are preserved in the session report (verbale).

## Essential controls
| Button | What it does |
|---|---|
| ▶ | Sends the question and runs the full flow |
| ⚡ Debate | Runs only the three-voice debate step |
| ✓ Summary | Summary + unanimous answer only |
| ◆ Unanimous answer | Regenerates the consensual answer |
| 🛡 Cross-check | Anti-hallucination verification with sources |
| ✏️ Fix | Re-queues the answer with the verifier's points (max 3 reruns) |
| 💾 Save | Saves session + timeline event |
| ✖ Clear | Clears channel and attachments; while running it becomes **⏹ Interrompi** (same spot, like Esc) |
| 🔎 Agenti | Opens the research-team panel (Ricerca profile) |
| ⚙ | Options: clients (discovered + manual) |
| 🌐 (language menu) | Switches UI and model-response language |
| 👥 (profiles menu) | Chooses the voice-role profile |

## The verdict and what it means
- **CONFERMATA**: the verifier finds no errors: the answer is confirmed by the context.
- **DA_CORREGGERE**: the verifier finds errors: press **✏️ Fix** (max 3 reruns) or revise the answer.
- **NON_CONCLUSO**: the verifier can neither confirm nor refute: the answer stays, but it is not proven by the context.

## Models
- **Dropdowns** above the LLM1/LLM2/LLM3 panels: choose models independently.
- **Local** (autonomous, zero keys): Ollama, LM Studio, Jan.
- **Cloud** (through configured clients): opencode, OpenAI, Anthropic, or any clients
  you add in ⚙. Keys: cloud → environment variable NAME only, stored in `.env`;
  custom clients → a real key is allowed ONLY in the local gitignored registry
  (`clienti.json`), or `env:NAME`; never in tracked files.
- **Ollama recommended** (the lightest): `winget install Ollama.Ollama` (or
  https://ollama.com/download), then `ollama pull qwen2.5:3b`.
- **Speed**: heavy models are labeled **"(slow)"** in the menus: first load takes
  1–2 minutes; each answer then takes 20–60 seconds (CPU). For quick tests use a
  small model (1.5B/3B).

## Built-in engine (llama.cpp)
TRILogos 3.0 can run GGUF models **on your machine**, with no external clients:
- **First-run wizard**: the guided window checks for `llama-server` and helps you
  install it and download the model that fits your hardware.
- **Requirements**: `winget install ggml.llamacpp`, or set the
  `TRILOGOS_LLAMA_DIR` environment variable to the folder containing
  `llama-server.exe`. If missing, TRILogos seamlessly uses external clients
  (Ollama, LM Studio, Jan, cloud BYOK).
- **Downloader**: catalog by hardware tier (0.5B, 3B, 7B, 14B; 3B vision with
  mmproj), multi-selection queue, resume of interrupted downloads (`.parziale`
  file) and **SHA256 checksum** verification.
- **Where models live**: `%APPDATA%\TRILogos\modelli\` (never in the project).
- **Automatic resource plan**: the profiler reads VRAM/RAM/CPU/disk and the
  resource plan decides ngl/KV/thread/margins for the chosen model; servers stop
  by themselves at the end of the flow (no orphan processes).

## Research profile (agent team)
With the **Ricerca** profile (👥 menu) the flow becomes a research project:
1. **Planning**: A proposes the team of specialized agents (JSON plan verified by
   B and C).
2. **Execution**: each agent produces its contribution (🔎 Agenti panel).
3. **Discernment**: A writes the final answer, B revises it; A/B/C score it 0-10
   and iterate until the **minimum across the three voices** reaches the **optimum
   threshold 8,99/10** (max 3 iterations).

The **[CONFIDENZA: …]** line in panel C shows score, threshold, iteration and stop
reason. Dedicated cap: **200 calls** (config.json → ricerca). The result goes to
`<project folder>\TRILogos_output\`.

## Clients (from the "Ready to use" splash)
On startup TRILogos detects your local clients and shows their status:
- **not installed** → installer instructions + winget command;
- **installed but stopped** → start it;
- **active** → lists the models.

Cloud keys go in the `.env` file (gitignored), never in clear. For a custom client
use the **"➕ Add a custom client"** form (name / base URL / key / models), with a
real key or `env:NAME`. opencode is in the list. **"🔄 Retry connections"** re-tests
everything.

## The first 4 things to do ("✓ Getting started" checklist)
1. **Install Ollama** (`winget install Ollama.Ollama`).
2. **Pull a model** (`ollama pull qwen2.5:3b`).
3. **Connect the voices** (pick a model in each LLM1/LLM2/LLM3 menu).
4. **Ask your first question** (SUPERVISORE bar + Enter).

The checklist updates itself with every tick.

## Attachments (feeding context to the channel)
- Press **📁 Project** to choose your project folder (the **write perimeter**: the
  saved result goes there), or **➕ ADD** for single files: reads are free and ADD
  works **even without a project folder**.
- Total cap: **max 40 attachments per session**.
- Text, PDF (extraction with pypdf; pymupdf optional for harder PDFs) and images
  (sent to multimodal models).
- The cross-check verifies against these attachments (or against the roles if none).
- **💾 Save**: the session always goes to `sessioni/`; the **result** (unanimous
  answer) is saved to `<project folder>/TRILogos_output/` with a unique name
  (never overwritten: `risultato_2.md`, `risultato_3.md`, …). Without a project
  folder an informational notice appears ("Per salvare il risultato scegli la
  cartella progetto (📁 Progetto)").

## Sessions, timeline and profiles
- **💾 Save**: session exported as JSON + readable Markdown.
- **Timeline**: every saved session becomes a typed event (T0, T1, …) in
  `timeline.json`, compatible with the research-timeline schema (metrics, evidence,
  ai_role).
- **👥 Profiles**: the voice roles live in `config.json` (profiles → A/B/C); you can
  customize them or add a `profili_locali.json` file (not distributed, gitignored)
  with your private profiles. The old name `profili_n47lab.json` is still read as a
  fallback (with a warning) but is deprecated.
- **Timeline author**: to sign your own events set `config.json → timeline.author`
  (name, affiliation, ORCID, background); without configuration the neutral author
  "Utente" is used.

## Technical notes
- **Cap**: 60 calls per session (configurable in config.json → canale → max_chiamate).
- **Step temperature** (research 2026): formulation 0.7, debate 0.7, synthesis 0.4,
  unanimous 0.4, revision 0.3, verification 0.2 — configurable in the channel constructor.
- **Per-voice convergence thresholds**: A=0.2, B=0.5, C=0.87 — configurable in
  config.json → canale → soglie.
- **7 languages**: IT · EN · FR · ES · DE · PT · 中文.
- **Network timeouts**: 10 s (connect) / 120 s (read) — configurable in config.json → rete.
- **Parallel debate**: A+B run in parallel (automatic sequential fallback if one
  voice fails); per-step token limits in config.json → canale → limiti_token.
- **Ollama**: `keep_alive` -1 (model never unloaded between turns), `num_ctx` 8192
  and background warmup for slow models — configurable in config.json → ollama.
- **Research cap**: 200 calls (config.json → ricerca → max_chiamate).
- **Copyable results**: panels are selection-only; right-click for
  Copy / Copy all / Select all.
- **Requirements**: Python 3.9+, `requests>=2.34`, `pypdf>=4.0` (required),
  `pymupdf` (optional); `llama.cpp` (optional) for the built-in engine.
- Token counter in the status bar: `token: X in / Y out` + calls executed.

## Troubleshooting
| Problem | Solution |
|---|---|
| "Server stopped" | Start Ollama (or LM Studio / Jan) and press "🔄 Retry connections" |
| "Model not found" | `ollama pull qwen2.5:3b`, then restart the client |
| Network timeout | Increase the timeouts in config.json → rete, or use a local model |
| llama.cpp missing | The built-in engine stays off: `winget install ggml.llamacpp` or `TRILOGOS_LLAMA_DIR`, or use external clients |
| Download interrupted | Re-run the download: it resumes from the `.parziale` file (HTTP Range) and verifies the checksum at the end |
| Pulisci HW | Only proposals with an estimated gain; no automatic closing: select and confirm |

N47Lab — 2026-10-06 (TRILogos 3.0 «ARCA Engine»)
