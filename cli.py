# TRILogos — CLI di test (Fase 1: core senza GUI)
"""Uso:
  python cli.py                    -> dialogo di prova con modelli Mock (nessuna chiave)
  python cli.py --a ollama --b mock --modello-a llama3
  python cli.py --a openai --b anthropic
Configura le chiavi API come variabili d'ambiente (OPENAI_API_KEY, ANTHROPIC_API_KEY)."""
import sys, os, argparse
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.modelli import crea_modello
from core.canale import Canale

def main():
    p = argparse.ArgumentParser(description="TRILogos — dialogo a tre voci")
    p.add_argument("--a", default="mock", help="tipo modello A: mock|ollama|openai|anthropic")
    p.add_argument("--b", default="mock", help="tipo modello B")
    p.add_argument("--modello-a", default=None, help="nome modello A (per ollama/openai/anthropic)")
    p.add_argument("--modello-b", default=None, help="nome modello B")
    p.add_argument("--ruolo-a", default="Sei l'agente A: analista rigoroso che formula le richieste per il collega B.")
    p.add_argument("--ruolo-b", default="Sei l'agente B: revisore critico e propositivo.")
    p.add_argument("--turni", type=int, default=4, help="max turni di dibattito")
    p.add_argument("--domanda", default="Qual è la relazione tra memoria di fase e cristallo di tempo discreto pretermale?")
    args = p.parse_args()

    a = crea_modello(args.a, modello=args.modello_a or "llama3.2") if args.a != "mock" else crea_modello("mock", nome="A")
    b = crea_modello(args.b, modello=args.modello_b or "llama3.2") if args.b != "mock" else crea_modello("mock", nome="B")

    canale = Canale(a, b, ruolo_a=args.ruolo_a, ruolo_b=args.ruolo_b, max_turni_dibattito=args.turni)

    print("=" * 70)
    print(f"TRILogos — A: {a.nome()} · B: {b.nome()}")
    print(f"Domanda del supervisore: {args.domanda}")
    print("=" * 70)

    print("\n[1/4] UTENTE → A (formulazione per B)")
    contesto = canale.domanda_utente(args.domanda)
    print(f"\n--- A formula ---\n{contesto['a_formula']}")
    print(f"\n--- B risponde ---\n{contesto['b_risposta']}")

    print("\n[2/4] DIBATTITO A ↔ B")
    dibattito = canale.dibattito(contesto)
    print(f"\n--- Posizione finale di A ---\n{dibattito['ultimo_a']}")
    print(f"\n--- Posizione finale di B ---\n{dibattito['ultimo_b']}")

    print("\n[3/4] ANALISI RECIPROCA")
    b_valuta_a = b.rispondi([{"ruolo": "system", "contenuto": args.ruolo_b},
                             {"ruolo": "user", "contenuto": f"Valuta in 2 righe il lavoro di A:\n{dibattito['ultimo_a']}"}])
    a_valuta_b = a.rispondi([{"ruolo": "system", "contenuto": args.ruolo_a},
                             {"ruolo": "user", "contenuto": f"Valuta in 2 righe il lavoro di B:\n{dibattito['ultimo_b']}"}])
    canale._registra("A", a_valuta_b)
    canale._registra("B", b_valuta_a)
    print(f"\n--- B su A ---\n{b_valuta_a}")
    print(f"\n--- A su B ---\n{a_valuta_b}")

    print("\n[4/4] SPARTIZIONE DEI LAVORI")
    sintesi = canale.spartisci_lavori(contesto, dibattito)
    print(f"\n--- Sintesi finale (A) ---\n{sintesi}")

    j, md = canale.salva()
    print(f"\nSessione salvata:\n  JSON: {j}\n  Markdown: {md}")

if __name__ == "__main__":
    main()