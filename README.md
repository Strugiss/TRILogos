# TRILogos — three-voice dialogue (user · LLM · LLM2)

TRILogos is a local orchestrator that lets **two LLMs collaborate through prompts**
under the supervision of a human. Flow: the user asks **LLM**, which formulates the
request for **LLM2**; a reciprocal debate follows; the two analyze each other and
split the work; finally the channel produces a **unanimous answer** (LLM proposes,
LLM2 approves or revises) verified by a **cross-check** against the context.

**Local or cloud**: works in full autonomy with local models (Ollama, LM Studio,
Jan, llama.cpp — no network, no keys), or through existing clients (read from the
opencode configuration, or added by you). Keys are never stored: only environment
variable names are referenced.

## Features
- **Three-voice pipeline**: user → LLM → LLM2 → debate → reciprocal analysis →
  task split → unanimous answer (consensual) → cross-check.
- **7 languages** (IT · EN · FR · ES · DE · PT · 中文): UI and model responses switch live.
- **Model dropdowns** per panel (LLM / LLM2 independent), models auto-discovered
  from Ollama + opencode config + your custom clients (⚙ Options window).
- **Attachments**: 📁 folder (up to 40 supported files) or ＋ ADD single files —
  text, PDF (text extracted), images (sent to multimodal models).
- **Streaming**: responses appear token by token.
- **Cross-check (anti-hallucination)**: LLM2 verifies every claim of the unanimous
  answer against the attached context (or the system roles), checking signs and
  values, with verdict: CONFIRMED or NEEDS CORRECTION.
- **Turn/call cap**: configurable (default 40 calls) — no budget surprises.
- **Session export**: JSON + readable Markdown.
- **Timeline integration**: every saved session becomes a typed event (T0, T1, …)
  in `timeline.json`, compatible with the research-timeline schema (metrics,
  evidence, ai_role) — the channel's work enters the same auditable trail as the lab.
- **Shared GUI profile**: built on LabGUI (`.opencode/shared/LabGUI`), reusable by
  future projects.

## Quick start
```bash
cd TRILogos
python gui.py          # GUI
python cli.py          # CLI test (mock, no keys)
python cli.py --a ollama --b ollama --modello-a deepseek-r1:14b --modello-b deepseek-r1:14b
```
- Ensure an Ollama server is running with your models (`ollama list`).
- First load of a large model takes 1–2 minutes; then each answer streams.
- For fast testing use a small model (e.g. `ollama pull qwen2.5:3b`) and select it
  from the dropdowns.
- On Windows, double-click `AvviaTRILogos.bat` (or `python gui.py`).

## Structure
```
TRILogos/
├── gui.py            GUI (LabGUI profile)
├── cli.py            CLI for tests
├── config.json       roles (project context), models, language, caps
├── clienti.json      your custom clients (never keys: only env names)
├── timeline.json     session events (research-timeline schema)
├── core/
│   ├── canale.py     the three-voice pipeline
│   ├── modelli.py    adapters: Ollama · OpenAI · Anthropic · OpenAI-compatible · Mock
│   ├── clienti.py    client discovery (opencode config, local, custom)
│   └── timeline.py   research-timeline integration
└── sessioni/         saved sessions (JSON + MD)
```

## Scientific basis
Multi-agent debate improves answer quality (Du et al. 2023, *Improving Factuality
and Reasoning through Multiagent Debate*; NeurIPS 2024 framework analyses; ICLR
2025 benchmark reviews). Key lesson applied: diversity matters — LLM and LLM2 play
different roles and can be different models.

## Feedback & testing — we need YOU
TRILogos is young and we want it to grow with real users. **Your feedback is
essential** — please test it and tell us what works, what breaks, and what you'd
add.

- **Test checklist**: see `CHECKLIST_TEST_EN.md` (and `CHECKLIST_TEST.md` in Italian)
- **How to give feedback**: open an issue on this repository with:
  - what you tried (checklist item number),
  - what happened (✓ worked / ✗ problem, with the message you saw),
  - any suggestion (UX, features, languages, aesthetics).
- We are especially interested in: new languages, model compatibility, attachment
  formats, debate quality, and anything that feels awkward.

Every report makes the tool better — thank you!

## Licenses & third-party services
- TRILogos is released under the MIT License (see LICENSE).
- All code and documentation are original; the multi-agent debate concept is
  published scientific literature (cited above), and this implementation is
  independent.
- Models are provided by third-party services (Ollama, OpenAI, Anthropic, or any
  OpenAI-compatible client you configure): their use is subject to their own
  terms and licenses. TRILogos is a client: it does not redistribute models or
  any third-party content. API keys are never stored — only environment variable
  names are referenced.

TRILogos — N47Lab, 2026.