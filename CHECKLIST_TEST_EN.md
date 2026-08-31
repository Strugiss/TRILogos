# TRILogos — TEST CHECKLIST (for testers & feedback)
### Try the items in order and report: ✓ works / ✗ problem (with what happened)

## 1. STARTUP
- [ ] `python gui.py` opens the window (4 panels: YOU · LLM · LLM2 · UNANIMOUS ANSWER)
- [ ] The status bar at the bottom shows "● ready" even in a NON-maximized window
- [ ] The dropdowns above LLM and LLM2 show available models (mock, ollama, etc.)

## 2. FULL FLOW
- [ ] Type a question → Enter → everything runs by itself ("● working" spinner visible)
- [ ] Answers appear streaming (token by token), not as blocks
- [ ] LLM formulates for LLM2 · LLM2 replies · debate · summary · unanimous answer in the purple panel
- [ ] At the end: sound + green status "· calls: X/40"
- [ ] Initial load time is acceptable (1–2 min for the 14B model)

## 3. LANGUAGES
- [ ] The 🌐 selector switches interface AND model responses (try EN → IT → 中文)
- [ ] Header labels translate (YOU/UTENTE, UNANIMOUS ANSWER/RISPOSTA UNIVOCA)

## 4. MODELS & CLIENTS
- [ ] Change the model from the dropdown above LLM → channel rebuilds (status: "A → … channel rebuilt")
- [ ] ⚙ Options: shows discovered clients (opencode, ollama, …)
- [ ] Add a manual client (name + base URL) → its models appear in the dropdowns
- [ ] Fallback: pick a non-existent model → the channel falls back to the other one ([fallback] note)

## 5. ATTACHMENTS
- [ ] ＋ ADD: add a text file → "[attachment] name (text, N chars)" appears
- [ ] ＋ ADD: add an image → "[attachment] name (image…)" appears
- [ ] 📁 Folder: pick a folder → supported files load (max 40)
- [ ] The flow uses the attachments (answer citing the documents)

## 6. CROSS-CHECK
- [ ] 🛡 Cross-check without attachments → verifies against the roles (with note)
- [ ] 🛡 Cross-check with attachments → verification with references (e.g. "Section 3.2") and verdict
- [ ] If the answer contains an error (e.g. "low MI" instead of high) → is it flagged?

## 7. TIMELINE & SESSIONS
- [ ] 💾 Save session → JSON + MD files in `sessioni/` and event Tn in `timeline.json`
- [ ] The timeline is readable with the research-timeline schema

## 8. ROLE PROFILES
- [ ] 👥 menu: switch from one profile to another (e.g. Generic → Creative) → roles change (status confirms)
- [ ] New profile in config.json → appears in the menu

## 9. CAP & SAFETY
- [ ] The call counter in the status rises with each call
- [ ] (No need to hit the cap: it triggers after 40 calls)

## FREE FEEDBACK
- What felt awkward or unclear?
- What is missing in your opinion?
- UX/aesthetics suggestions?

Thanks! — N47Lab

