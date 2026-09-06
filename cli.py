# TRILogos — CLI di test
"""Uso:
  python cli.py                    -> dialogo di prova con modelli Mock (nessuna chiave)
  python cli.py --a ollama --b mock --modello-a llama3
  python cli.py --a openai --b anthropic
Configura le chiavi API come variabili d'ambiente (OPENAI_API_KEY, ANTHROPIC_API_KEY)."""
import sys, os, argparse, json
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.modelli import crea_modello
from core.canale import Canale
from core.timeline import aggiungi_sessione

def main():
    p = argparse.ArgumentParser(description="TRILogos — dialogo a tre voci")
    p.add_argument("--a", default="mock", help="tipo modello A: mock|ollama|openai|anthropic|openaicompat")
    p.add_argument("--b", default="mock", help="tipo modello B")
    p.add_argument("--modello-a", default=None, help="nome modello A (per ollama/openai/anthropic)")
    p.add_argument("--modello-b", default=None, help="nome modello B")
    p.add_argument("--ruolo-a", default="Sei l'agente A: analista rigoroso che formula le richieste per il collega B.")
    p.add_argument("--ruolo-b", default="Sei l'agente B: revisore critico e propositivo.")
    p.add_argument("--turni", type=int, default=None, help="max turni di dibattito (default: 3, da config)")
    p.add_argument("--domanda", default="Qual è la relazione tra memoria di fase e cristallo di tempo discreto pretermale?")
    args = p.parse_args()

    try:
        a = crea_modello(args.a, modello=args.modello_a or "llama3.2") if args.a != "mock" else crea_modello("mock", nome="A")
        b = crea_modello(args.b, modello=args.modello_b or "llama3.2") if args.b != "mock" else crea_modello("mock", nome="B")

        try:
            _cfg = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"), encoding="utf-8"))
            _turni_default = _cfg.get("canale", {}).get("max_turni_dibattito", 3)
            _soglia_default = _cfg.get("canale", {}).get("soglia_convergenza", 0.9)
            _cap_default = _cfg.get("canale", {}).get("max_chiamate", 40)
        except Exception:
            _turni_default, _soglia_default, _cap_default = 3, 0.9, 40
        turni = args.turni if args.turni is not None else _turni_default

        canale = Canale(a, b, ruolo_a=args.ruolo_a, ruolo_b=args.ruolo_b,
                        max_turni_dibattito=turni, soglia_convergenza=_soglia_default,
                        max_chiamate=_cap_default)
    except Exception as e:
        print(f"ERRORE di avvio: {e}")
        sys.exit(1)

    print("=" * 70)
    print(f"TRILogos — A: {a.nome()} · B: {b.nome()}")
    print(f"Domanda del supervisore: {args.domanda}")
    print("=" * 70)

    try:
        print("\n[1/6] UTENTE → A (formulazione per B)")
        contesto = canale.domanda_utente(args.domanda)
        print(f"\n--- A formula ---\n{contesto['a_formula']}")
        print(f"\n--- B risponde ---\n{contesto['b_risposta']}")

        print("\n[2/6] DIBATTITO A ↔ B")
        dibattito = canale.dibattito(contesto)
        print(f"\n--- Posizione finale di A ---\n{dibattito['ultimo_a']}")
        print(f"\n--- Posizione finale di B ---\n{dibattito['ultimo_b']}")
        if dibattito["early_exit"]:
            print("\n(early-exit: A e B concordavano già, dibattito saltato)")

        print("\n[3/6] SPARTIZIONE DEI LAVORI")
        sintesi = canale.spartisci_lavori(contesto, dibattito)
        print(f"\n--- Sintesi finale (A) ---\n{sintesi}")

        print("\n[4/6] RISPOSTA UNIVOCA CONSENSUALE")
        finale, revisione = canale.risposta_univoca(contesto, dibattito, sintesi)
        print(f"\n--- Risposta finale ---\n{finale}")
        print(f"\n--- Revisione di B ---\n{revisione}")

        print("\n[6/6] CROSS-CHECK (verificatore bambino)")
        esito = canale.cross_check(contesto, finale)
        print(f"\n--- VERDETTO: {esito['verdetto']} ---\n{esito['testo']}")
        print(f"metriche: {esito['metriche']}")

        print("\nSALVATAGGIO")
        j, md = canale.salva()
        nome = os.path.splitext(os.path.basename(j))[0]
        aggiungi_sessione(nome, args.domanda, [a.nome(), b.nome()], "it",
                          j, md, verdetto=esito["verdetto"])
        print(f"Sessione salvata:\n  JSON: {j}\n  Markdown: {md}")
    except Exception as e:
        print(f"\nERRORE durante il dialogo: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()