# TRILogos — A13: misuratore dei token al secondo (stima dai chunk di testo)
"""Modulo PURO (nessuna dipendenza da tkinter): il thread di streaming lo
alimenta con i pezzi di testo (`aggiungi`), il thread UI lo legge per la status
bar (`tok_s`, `media`). Thread-safe: lock interno su ogni operazione.

Stima documentata (Decisioni §A13, punto 2): `token_stimati = caratteri / 3,5`
(italiano, range atteso 3-4). L'istantaneo usa una finestra mobile di ~2 s
(campioni `(t, caratteri_cumulati)`); la media del passo si calcola dall'inizio
del passo e, a fine chiamata, `finalizza(eval_count, secondi)` la sostituisce
col valore REALE quando l'usage del modello è disponibile. Il conteggio per
chunk è O(1) (solo `len`), la finestra pota i campioni vecchi in modo
ammortizzato O(1): nessun costo misurabile sullo streaming."""
import threading
import time
from collections import deque

# Costante unica documentata (A13): stima caratteri-per-token per l'italiano.
CARATTERI_PER_TOKEN = 3.5
# Ampiezza della finestra mobile dell'istantaneo (secondi).
FINESTRA_S = 2.0


class MisuratoreTok:
    """Contatore tok/s a finestra mobile, con media del passo e dato reale.

    Uso tipico:
        m = MisuratoreTok()
        m.reset()                      # a inizio passo/flusso
        m.aggiungi(chunk)              # per ogni chunk (anche da thread)
        m.tok_s()                      # istantaneo (None mai / 0.0 finestra vuota)
        m.finalizza(eval_count, dt)    # a fine chiamata, se l'usage c'e'
        m.media()                      # media del passo (reale o stimata)
    """

    def __init__(self, caratteri_per_token=None, finestra_s=None, clock=None):
        self._cpt = float(caratteri_per_token or CARATTERI_PER_TOKEN)
        self._finestra = float(finestra_s if finestra_s is not None else FINESTRA_S)
        # clock iniettabile: i test usano un clock finto, in produzione time.monotonic.
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self.reset()

    # ---- alimentazione (thread di streaming) ----
    def aggiungi(self, testo):
        """Registra un chunk di testo: conteggio O(1) e campione (t, cumulato).
        Testo vuoto/None: ignorato (nessun campione)."""
        n = len(testo or "")
        if n <= 0:
            return
        now = self._clock()
        with self._lock:
            self._car_passo += n
            self._campioni.append((now, self._car_passo))
            self._ultimo = now
            if self._inizio is None:
                self._inizio = now
            # Pota i campioni fuori finestra tenendo il primo al confine: è la
            # base per il Δ dell'istantaneo (mai perdere l'ultimo campione
            # immediatamente precedente alla finestra).
            limite = now - self._finestra
            while len(self._campioni) > 1 and self._campioni[1][0] <= limite:
                self._campioni.popleft()

    # ---- lettura (thread UI) ----
    def tok_s(self):
        """Stima istantanea (finestra mobile ~2 s), 1 decimale.
        None = nessun chunk ricevuto dal reset; 0.0 = finestra vuota (nessun
        chunk recente) o Δt nullo (chunk nello stesso istante)."""
        with self._lock:
            if self._ultimo is None:
                return None
            now = self._clock()
            if now - self._ultimo > self._finestra:
                return 0.0
            t0, c0 = self._base(now)
            t1, c1 = self._ultimo, self._car_passo
            dt = t1 - t0
            if dt <= 1e-9:
                return 0.0
            return round((c1 - c0) / dt / self._cpt, 1)

    def media(self):
        """Media del passo, 1 decimale: il valore reale se `finalizza` l'ha
        impostato, altrimenti la stima caratteri/tempo dall'inizio del passo.
        None = passo senza chunk."""
        with self._lock:
            if self._reale is not None:
                return round(self._reale, 1)
            if self._inizio is None or self._ultimo is None:
                return None
            dt = self._ultimo - self._inizio
            if dt <= 1e-9:
                return 0.0
            return round(self._car_passo / dt / self._cpt, 1)

    def media_reale(self):
        """True se la media del passo poggia sull'usage reale (eval_count)."""
        with self._lock:
            return self._reale is not None

    def attivo(self):
        """True se l'ultimo chunk è dentro la finestra: il refresh può
        continuare a campionare (per mostrare 0,0 a finestra vuota)."""
        with self._lock:
            if self._ultimo is None:
                return False
            return (self._clock() - self._ultimo) <= self._finestra

    def token_stimati(self):
        """Stima dei token del passo corrente (`car_passo / caratteri_per_token`),
        frazionaria e thread-safe: usata dal totale di sessione Σ (A13 rev. 17.1,
        base congelata + stima). Unico posto della costante insieme a `aggiungi`."""
        with self._lock:
            return self._car_passo / self._cpt

    def finalizza(self, eval_count, secondi):
        """Media reale del passo (eval_count / secondi) se entrambi positivi;
        altrimenti la media resta quella stimata. Valori malformati = ignorati."""
        try:
            n = int(eval_count)
        except (TypeError, ValueError):
            n = 0
        try:
            s = float(secondi)
        except (TypeError, ValueError):
            s = 0.0
        with self._lock:
            self._reale = (n / s) if (n > 0 and s > 0) else None

    def reset(self):
        """Azzera campioni, conteggi e media reale: nuovo passo/flusso."""
        with self._lock:
            self._campioni = deque()
            self._car_passo = 0
            self._inizio = None
            self._ultimo = None
            self._reale = None

    # ---- interno (chiamato con il lock già acquisito) ----
    def _base(self, now):
        """Campione di base della finestra: l'ultimo con t <= now-finestra;
        se nessuno è più vecchio, il primo disponibile."""
        limite = now - self._finestra
        base = None
        for campione in self._campioni:
            if campione[0] <= limite:
                base = campione
            else:
                break
        return base if base is not None else self._campioni[0]
