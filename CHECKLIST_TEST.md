# TRILogos — CHECKLIST DI TEST (per tester e feedback)
### Prova i punti in ordine e riporta: ✓ funziona / ✗ problema (con cosa è successo)

## 1. AVVIO
- [ ] `python gui.py` apre la finestra (4 riquadri: UTENTE · LLM · LLM2 · RISPOSTA UNIVOCA)
- [ ] La status bar in basso mostra "● pronto" anche in finestra NON a tutto schermo
- [ ] I menu sopra LLM e LLM2 mostrano i modelli disponibili (mock, ollama, ecc.)

## 2. FLUSSO COMPLETO
- [ ] Scrivi una domanda → Invio → parte tutto da solo (spinner "● in elaborazione" visibile)
- [ ] Il testo delle risposte appare a flusso (streaming), non a blocchi
- [ ] A formula per LLM2 · LLM2 risponde · dibattito · sintesi · risposta univoca nel riquadro viola
- [ ] A fine flusso: suono + stato verde "· chiamate: X/40"
- [ ] Il tempo di caricamento iniziale è accettabile (1-2 min per il 14b)

## 3. LINGUE
- [ ] Il selettore 🌐 cambia interfaccia E risposte dei modelli (prova IT → EN → 中文)
- [ ] Le etichette degli header (UTENTE/YOU, RISPOSTA UNIVOCA/UNANIMOUS ANSWER) si traducono

## 4. MODELLI E CLIENTI
- [ ] Cambia modello dal menu sopra LLM → il canale si ricostruisce (status: "A → … canale ricostruito")
- [ ] ⚙ Opzioni: mostra i clienti rilevati (opencode, ollama, …)
- [ ] Aggiungi un client manuale (nome + base URL) → i suoi modelli compaiono nei menu
- [ ] Fallback: scegli un modello inesistente → il canale ripiega sull'altro (nota [fallback])

## 5. ALLEGATI
- [ ] ＋ ADD: aggiungi un file di testo → appare "[allegato] nome (testo, N caratteri)"
- [ ] ＋ ADD: aggiungi un'immagine → appare "[allegato] nome (immagine…)"
- [ ] 📁 Cartella: seleziona una cartella → carica i file supportati (max 40)
- [ ] Il flusso usa gli allegati (risposta che cita i documenti)

## 6. CROSS-CHECK
- [ ] 🛡 Cross-check senza allegati → verifica contro i ruoli (con nota)
- [ ] 🛡 Cross-check con allegati → verifica con riferimenti (es. "Punto 3.2") e verdetto
- [ ] Se la risposta contiene un errore (es. "MI bassa" invece di alta) → segnalato?

## 7. TIMELINE E SESSIONI
- [ ] 💾 Salva sessione → file JSON + MD in `sessioni/` e evento Tn in `timeline.json`
- [ ] La timeline è leggibile con lo schema research-timeline

## 8. PROFILI RUOLI
- [ ] Menu 👥: cambia da un profilo all'altro (es. Generico → Creativo) → i ruoli cambiano (status conferma)
- [ ] Nuovo profilo in config.json → compare nel menu

## 9. CAP E SICUREZZA
- [ ] Il contatore in status sale con ogni chiamata
- [ ] (Non serve provare il cap: si raggiunge dopo 40 chiamate)

## FEEDBACK LIBERO
- Cosa hai trovato scomodo o poco chiaro?
- Cosa manca secondo te?
- Suggerimenti di UX/estetica?

Grazie! — N47Lab
