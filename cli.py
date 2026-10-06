# TRILogos — CLI di test
"""Uso:
  python cli.py                    -> dialogo di prova con modelli Mock (nessuna chiave)
  python cli.py --a ollama --b mock --modello-a llama3
  python cli.py --a openai --b anthropic
Configura le chiavi API come variabili d'ambiente (OPENAI_API_KEY, ANTHROPIC_API_KEY).

Mappa dei 6 passi stampati:
  [1/6] formulazione (domanda + A formula + B risponde)   [4/6] risposta univoca
  [2/6] dibattito                                         [5/6] cross-check
  [3/6] spartizione dei lavori                            [6/6] salvataggio
La CLI di prova usa DUE voci (A · B): il Canale supporta la terza voce C,
usata dalla GUI; qui il verificatore del cross-check è B."""
import sys, os, argparse, json, inspect
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.modelli import crea_modello
from core.canale import Canale
from core.timeline import aggiungi_sessione

def main():
    p = argparse.ArgumentParser(description="TRILogos — CLI di prova (canale a due voci A · B)")
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
        # Config letta PRIMA dei modelli: i timeout di rete (config.json → rete)
        # arrivano ai modelli per parametro esplicito (il core non legge la config).
        try:
            _cfg = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"), encoding="utf-8"))
            _turni_default = _cfg.get("canale", {}).get("max_turni_dibattito", 3)
            _soglia_default = _cfg.get("canale", {}).get("soglia_convergenza", 0.9)
            _cap_default = _cfg.get("canale", {}).get("max_chiamate", 40)
            _rete = _cfg.get("rete") or {}
            _timeout = (int(_rete.get("timeout_connect", 10)), int(_rete.get("timeout_read", 120)))
            if _timeout[0] <= 0 or _timeout[1] <= 0:
                _timeout = (10, 120)
            _autore = (_cfg.get("timeline") or {}).get("author") if isinstance(_cfg, dict) else None
            # V2/V3: limiti output per passo e keep_alive Ollama dal config
            _limiti = _cfg.get("canale", {}).get("limiti_token") if isinstance(_cfg, dict) else None
            _keep = (_cfg.get("ollama") or {}).get("keep_alive", -1) if isinstance(_cfg, dict) else -1
            try:
                _num_ctx = int((_cfg.get("ollama") or {}).get("num_ctx", 8192))
            except (TypeError, ValueError):
                _num_ctx = 8192
            if _num_ctx <= 0:
                _num_ctx = 8192
        except Exception:
            _turni_default, _soglia_default, _cap_default = 3, 0.9, 40
            _timeout = (10, 120)
            _autore = None
            _limiti = None
            _keep = -1
            _num_ctx = 8192

        def _kw_modello(tipo, nome):
            kw = {"modello": nome, "timeout": _timeout}
            if tipo == "ollama":
                kw["keep_alive"] = _keep
                kw["num_ctx"] = _num_ctx
            return kw

        a = crea_modello(args.a, **_kw_modello(args.a, args.modello_a or "llama3.2")) if args.a != "mock" else crea_modello("mock", nome="A")
        b = crea_modello(args.b, **_kw_modello(args.b, args.modello_b or "llama3.2")) if args.b != "mock" else crea_modello("mock", nome="B")
        turni = args.turni if args.turni is not None else _turni_default

        _canale_extra = {}
        if "limiti_token" in inspect.signature(Canale.__init__).parameters and _limiti:
            _canale_extra["limiti_token"] = _limiti
        canale = Canale(a, b, ruolo_a=args.ruolo_a, ruolo_b=args.ruolo_b,
                        max_turni_dibattito=turni, soglia_convergenza=_soglia_default,
                        max_chiamate=_cap_default, **_canale_extra)
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

        print("\n[5/6] CROSS-CHECK (verificatore bambino)")
        esito = canale.cross_check(contesto, finale)
        print(f"\n--- VERDETTO: {esito['verdetto']} ---\n{esito['testo']}")
        print(f"metriche: {esito['metriche']}")

        print("\n[6/6] SALVATAGGIO")
        j, md = canale.salva()
        nome = os.path.splitext(os.path.basename(j))[0]
        aggiungi_sessione(nome, args.domanda, [a.nome(), b.nome()], "it",
                          j, md, verdetto=esito["verdetto"], autore=_autore)
        print(f"Sessione salvata:\n  JSON: {j}\n  Markdown: {md}")
    except Exception as e:
        print(f"\nERRORE durante il dialogo: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()