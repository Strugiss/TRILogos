# TRILogos TUTORIAL — user guide (English)

## What it is
A local orchestrator that lets **two LLMs collaborate through prompts** under human
supervision. The structure has three voices: **you · LLM · LLM2**.

## The flow (how it works)
1. Type a question in the top bar and press **Enter** (or ▶).
2. **LLM** (blue) analyzes it and formulates the request for **LLM2**.
3. **LLM2** (green) replies with its analysis.
4. **Debate**: they exchange positions until convergence (or the turn budget runs out).
5. **Summary & tasks**: LLM writes the final summary and splits the work (who does what).
6. **Unanimous answer** (purple panel): LLM proposes the draft, **LLM2 approves or
   revises it** — the result is shared.
7. **🛡 Cross-check**: LLM2 verifies every claim of the answer against the context
   (attachments, or system roles) — it also checks signs and values — and gives a verdict.
8. **💾 Save session**: saves JSON + Markdown and registers the event in the timeline (T0, T1, …).

## Essential controls
| Button | What it does |
|---|---|
| Top bar + Enter | Runs the full flow (automatic) |
| 📁 Folder | Loads an entire folder (up to 40 supported files) |
| ＋ ADD | Adds single files (text, PDF, images) |
| ⚡ Debate | Runs only the debate step |
| ✓ Summary | Summary + unanimous answer only |
| ◆ Unanimous answer | Regenerates the consensual answer |
| 🛡 Cross-check | Anti-hallucination verification with sources |
| 💾 Save | Saves session + timeline event |
| ✖ Clear | Clears channel and attachments |
| ⚙ | Options: clients (discovered + manual) |
| 🌐 (language menu) | Switches UI and model-response language |

## Models
- **Dropdowns** above the LLM/LLM2 panels: choose models independently.
- **Local** (autonomous, zero keys): Ollama (e.g. `deepseek-r1:14b`, `qwen2.5:3b`),
  LM Studio, Jan.
- **Cloud** (through configured clients): we read the opencode configuration and any
  clients you add in ⚙ (key = environment variable name only, never stored in clear).
- **Speed**: first load of a 14B model takes 1–2 minutes; each answer then takes
  20–60 seconds (CPU). For quick tests use a small model (1.5B/3B).

## Attachments (feeding context to the channel)
- Press **📁 Folder** and pick a documents folder, or **＋ ADD** for single files.
- Text and PDF: content is injected into the context. Images: sent to multimodal models.
- The cross-check verifies against these attachments (or against the roles if none).

## Example session
```
Question: "What are the pros and cons of nuclear energy?"
→ LLM formulates for LLM2 → debate → summary →
→ UNANIMOUS ANSWER: a shared position, with strengths and weaknesses…
→ CROSS-CHECK: claims supported by the context → ANSWER CONFIRMED
```

## Notes
- Call cap: 40 per session (configurable in config.json → canale → max_chiamate).
- The roles of LLM and LLM2 live in `config.json` (profiles → A/B): customize each voice,
  or add a `profili_locali.json` file (not distributed) with your private profiles.
- The generated timeline follows a standard research-timeline schema.

N47Lab — 2026-08-30