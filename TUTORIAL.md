# TUTORIAL TRILogos — guida all'uso (italiano)

## Cos'è
Un orchestratore locale che mette **due LLM a collaborare tramite prompt** sotto la
supervisione dell'utente. La struttura è a tre voci: **tu · LLM · LLM2**.

## Il flusso (come funziona)
1. Scrivi una domanda nella barra in alto e premi **Invio** (o ▶).
2. **LLM** (blu) la analizza e formula la richiesta per **LLM2**.
3. **LLM2** (verde) risponde con la sua analisi.
4. **Dibattito**: si scambiano le posizioni finché convergono (o finisce il budget di turni).
5. **Sintesi e lavori**: LLM scrive la sintesi finale e divide i compiti (chi fa cosa).
6. **Risposta univoca** (riquadro viola): LLM propone la bozza, **LLM2 la approva o la rivede** — il risultato è condiviso.
7. **🛡 Cross-check**: LLM2 verifica ogni affermazione della risposta contro il contesto
   (allegati, o ruoli di sistema) — controlla anche segni e valori — e dà il verdetto.
8. **💾 Salva sessione**: salva JSON + Markdown e registra l'evento nella timeline (T0, T1, …).

## Le funzioni essenziali
| Bottone | Cosa fa |
|---|---|
| Barra + Invio | Avvia il flusso completo (automatico) |
| 📁 Cartella | Carica un'intera cartella (max 40 file supportati) |
| ＋ ADD | Aggiunge singoli file (testo, PDF, immagini) |
| ⚡ Dibattito | Solo il passo del dibattito |
| ✓ Sintesi | Solo sintesi + risposta univoca |
| ◆ Risposta univoca | Rigenera la risposta consensuale |
| 🛡 Cross-check | Verifica anti-allucinazione con fonti |
| 💾 Salva | Salva sessione + evento timeline |
| ✖ Svuota | Pulisce canale e allegati |
| ⚙ | Opzioni: clienti (rilevati + aggiunta manuale) |
| 🌐 (menu lingua) | Cambia lingua di interfaccia e risposte dei modelli |

## Modelli
- **Menu a tendina** sopra i riquadri LLM/LLM2: scegli i modelli indipendentemente.
- **Locale** (autonomia, zero chiavi): Ollama (es. `deepseek-r1:14b`, `qwen2.5:3b`),
  LM Studio, Jan.
- **Cloud** (tramite client configurati): leggiamo la configurazione di opencode e i
  clienti che aggiungi in ⚙ (chiave = solo nome di variabile d'ambiente, mai in chiaro).
- **Velocità**: il primo caricamento del modello 14b richiede 1-2 minuti; poi ogni
  risposta 20-60 secondi (CPU). Per prove rapide usa un modello piccolo (1.5b/3b).

## Allegati (dare contesto al canale)
- Premi **📁 Cartella** e seleziona una cartella di documenti, oppure **＋ ADD** per file singoli.
- Testo e PDF: il contenuto viene iniettato nel contesto. Immagini: inviate ai
  modelli multimodali.
- Il cross-check verifica contro questi allegati (o contro i ruoli se non ci sono).

## Esempio di sessione
```
Domanda: "Quali sono i pro e i contro dell'energia nucleare?"
→ LLM formula per LLM2 → dibattito → sintesi →
→ RISPOSTA UNIVOCA: una posizione condivisa, con i punti di forza e le criticità…
→ CROSS-CHECK: affermazioni supportate dal contesto → RISPOSTA CONFERMATA
```

## Note
- Cap: 40 chiamate per sessione (configurabile in config.json → canale → max_chiamate).
- I ruoli di LLM e LLM2 vivono in `config.json` (profili → A/B): personalizza ogni voce,
  o aggiungi un file `profili_locali.json` (non distribuito) con i tuoi profili privati.
- La timeline generata segue lo schema di un tool di ricerca-timeline standard.

Firmato: N47Lab — 30/08/2026