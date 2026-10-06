# TRILogos — test unit del misuratore tok/s (A13)
"""Verifica deterministica di `core\\metro.MisuratoreTok`: finestra mobile,
stima caratteri/3,5, media del passo, dato reale (finalizza), reset, casi
limite (Δt nullo, testo vuoto, valori malformati). Clock iniettivo: nessuna
attesa reale, nessuna rete.

Uso:  python Test/test_metro.py
Esito atteso: 16/16 OK. PRECETTO PRIVACY: nessun dato utente, solo conteggi."""
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.metro import MisuratoreTok, CARATTERI_PER_TOKEN, FINESTRA_S


class ClockFinto:
    """Clock controllato: i test avanzano il tempo a comando."""
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def nuovo(**kw):
    clock = ClockFinto()
    return MisuratoreTok(clock=clock, **kw), clock


# ---------------------------------------------------------------- casi
def caso_01_reset_iniziale():
    m, _ = nuovo()
    assert m.tok_s() is None
    assert m.media() is None
    assert m.media_reale() is False
    assert m.attivo() is False


def caso_02_testo_vuoto_ignorato():
    m, _ = nuovo()
    m.aggiungi("")
    m.aggiungi(None)
    assert m.tok_s() is None
    assert m.media() is None


def caso_03_primo_chunk_zero():
    m, c = nuovo()
    c.t = 1.0
    m.aggiungi("x" * 350)
    assert m.tok_s() == 0.0          # Δt nullo: chunk nello stesso istante
    assert m.media() == 0.0


def caso_04_stima_istantanea():
    m, c = nuovo()
    m.aggiungi("x" * 350)            # t=0
    c.t = 1.0
    m.aggiungi("y" * 350)            # t=1: Δ350 car in 1 s
    assert m.tok_s() == 100.0        # 350/1/3,5


def caso_05_finestra_mobile():
    m, c = nuovo()
    m.aggiungi("a" * 350)            # t=0
    c.t = 1.0; m.aggiungi("a" * 350)
    c.t = 2.0; m.aggiungi("a" * 350)
    c.t = 3.0; m.aggiungi("a" * 350)
    # base = campione al confine (t=1), non quello a t=0 fuori finestra
    assert m.tok_s() == 100.0        # (1050-700)/2/3,5


def caso_06_finestra_vuota():
    m, c = nuovo()
    m.aggiungi("x" * 350)            # t=0
    c.t = 1.0; m.aggiungi("x" * 350)
    c.t = 3.5                        # ultimo chunk a t=1 -> oltre 2 s
    assert m.tok_s() == 0.0
    assert m.attivo() is False


def caso_07_attivo():
    m, c = nuovo()
    assert m.attivo() is False
    m.aggiungi("x" * 350)            # t=0
    c.t = FINESTRA_S                 # esattamente al bordo: ancora in finestra
    assert m.attivo() is True
    c.t = FINESTRA_S + 0.001
    assert m.attivo() is False


def caso_08_media_stimata():
    m, c = nuovo()
    m.aggiungi("x" * 350)            # t=0, inizio passo
    c.t = 2.0
    m.aggiungi("y" * 350)            # t=2
    assert m.media() == 100.0        # 700/2/3,5 (media del passo)
    assert m.tok_s() == 50.0         # istantaneo: 350/2/3,5
    assert m.media_reale() is False


def caso_09_finalizza_reale():
    m, c = nuovo()
    m.aggiungi("x" * 350)
    c.t = 1.0
    m.aggiungi("y" * 350)
    m.finalizza(900, 10.0)           # eval_count reale / durata
    assert m.media() == 90.0
    assert m.media_reale() is True


def caso_10_finalizza_invalida():
    m, c = nuovo()
    m.aggiungi("x" * 350)
    c.t = 1.0
    m.aggiungi("y" * 350)
    for n, s in ((0, 10.0), (None, None), ("abc", "x"), (100, 0), (-5, 10.0)):
        m.finalizza(n, s)
        assert m.media_reale() is False
        assert m.media() == 200.0    # resta la stima del passo: 700/1/3,5


def caso_11_reset_azzera_tutto():
    m, c = nuovo()
    m.aggiungi("x" * 350)
    c.t = 1.0
    m.aggiungi("y" * 350)
    m.finalizza(900, 10.0)
    m.reset()
    assert m.tok_s() is None
    assert m.media() is None
    assert m.media_reale() is False
    c.t = 2.0
    m.aggiungi("z" * 350)            # riparte pulito: primo campione a t=2
    assert m.tok_s() == 0.0


def caso_12_potatura_campioni():
    m, c = nuovo()
    for i in range(100):             # 100 chunk ogni 0,05 s = 5 s
        c.t = i * 0.05
        m.aggiungi("x" * 35)
    # la finestra (2 s) tiene solo i campioni utili (<= ~41 + base)
    assert len(m._campioni) <= 45
    # 35 car / 0,05 s / 3,5 = 200 tok/s
    assert m.tok_s() == 200.0


def caso_13_arrotondamento():
    m, c = nuovo()
    m.aggiungi("x" * 100)            # t=0
    c.t = 1.0
    m.aggiungi("y" * 148)            # Δ148 car in 1 s -> 42,2857... 
    assert m.tok_s() == 42.3         # 1 decimale (42,3)
    assert m.media() == 70.9         # 248/1/3,5 = 70,857... -> 70,9


def caso_14_delta_t_nullo():
    m, c = nuovo()
    c.t = 5.0
    m.aggiungi("x" * 700)
    m.aggiungi("y" * 700)            # stesso istante
    assert m.tok_s() == 0.0
    assert m.media() == 0.0          # nessuna divisione per zero


def caso_15_cpt_custom():
    m, c = nuovo(caratteri_per_token=4.0)
    m.aggiungi("x" * 400)            # t=0
    c.t = 1.0
    m.aggiungi("y" * 400)
    assert m.tok_s() == 100.0        # 400/1/4,0


def caso_16_costanti_documentate():
    assert CARATTERI_PER_TOKEN == 3.5
    assert FINESTRA_S == 2.0


CASI = [
    ("01 reset iniziale", caso_01_reset_iniziale),
    ("02 testo vuoto ignorato", caso_02_testo_vuoto_ignorato),
    ("03 primo chunk zero", caso_03_primo_chunk_zero),
    ("04 stima istantanea", caso_04_stima_istantanea),
    ("05 finestra mobile", caso_05_finestra_mobile),
    ("06 finestra vuota", caso_06_finestra_vuota),
    ("07 attivo", caso_07_attivo),
    ("08 media stimata", caso_08_media_stimata),
    ("09 finalizza reale", caso_09_finalizza_reale),
    ("10 finalizza invalida", caso_10_finalizza_invalida),
    ("11 reset azzera tutto", caso_11_reset_azzera_tutto),
    ("12 potatura campioni", caso_12_potatura_campioni),
    ("13 arrotondamento", caso_13_arrotondamento),
    ("14 delta t nullo", caso_14_delta_t_nullo),
    ("15 cpt custom", caso_15_cpt_custom),
    ("16 costanti documentate", caso_16_costanti_documentate),
]


def main():
    ok = 0
    for nome, fn in CASI:
        try:
            fn()
            ok += 1
            print(f"[OK]   {nome}")
        except Exception as e:
            print(f"[FAIL] {nome}: {e!r}")
    print(f"\n{ok}/{len(CASI)} OK")
    return 0 if ok == len(CASI) else 1


if __name__ == "__main__":
    sys.exit(main())
