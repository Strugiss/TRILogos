# TRILogos — Piano risorse (B2b, motore interno)
"""Trasforma profilo hardware + metadati GGUF + contesto richiesto in un Piano
eseguibile (ngl, KV, thread, mmap, stima tok/s, margini), con le regole
MISURATE di ARCA (DESIGN_ARCA §2b/§3, policy P1-P17) come costanti documentate.
Adattato in sola lettura: nessun import/percorso verso ARCA, nessuna dipendenza.

Regole chiave (fonti ARCA):
- ginocchio 14B contesto-dipendente (P1/A4): ≤0,5k→40 · 0,5-16k→40−0,258·(ctx_k−0,5)
  · 16-32k→36−0,5·(ctx_k−16); mai ≥44 (P2: spill −60%); 48+ OOM (P3);
- piccoli (≤36 layer o ≲4 GB) full-GPU: ngl 99 (P4);
- KV: q8_0 di default da 8k, obbligatoria da 16k (P5/D3: la f16 a 16k sul 14B OOM);
- thread: 12 con offload (P6/D10), plateau 4 full-GPU, mai 24;
- no-mmap default (P7/D4); margine minimo 550 MiB al picco (D1/P8), rischio
  allocazione in blocco WDDM ~1 GiB (P8); stop-rule 90% VRAM (D1); budget RAM
  ~20 GB (P10); un solo modello grande residente (D1/REGOLE);
- stima tok/s per fasce misurate (1,8 / 4,4 / 8,37 GB + punti intermedi, ARCA
  campagna 19/09/2026), correzione formato e decadimento contesto 14B.

Mai crash su metadati mancanti: i dati assenti restano None e il motivo finisce
negli `avvisi` del Piano (stima dichiarata, italiano).
"""
import os
import struct
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# ---- costanti misurate ARCA (DESIGN_ARCA §3, policy P1-P17) ----
MARGINE_MINIMO_MIB = 550          # D1: liberi minimi al picco (ginocchio: 567)
MARGINE_WDDM_MIB = 1536           # P8: alloc ~1 GiB negata con 1566 MiB liberi
RISERVA_VRAM_FRAZIONE = 0.10      # D1: stop-rule 90% VRAM totale
BUDGET_RAM_GB = 20.0              # P10: budget RAM LLM ~20 GB su 32
KV_Q8_DA_TOKEN = 8192             # B2b: q8_0 di default da 8k in su
KV_Q8_OBBLIGATORIA_DA_TOKEN = 16384  # P5/D3: f16 vietata da 16k
THREAD_OFFLOAD = 12               # P6/D10: 14B in offload
THREAD_FULL = 4                   # P6: plateau full-GPU
NGN_VIETATO = 44                  # P2: mai ≥44 (tg 7.46, −60%)
NGN_OOM = 48                      # P3: 48 e 99 → OOM (99 = full, clampato)
MMAP_DEFAULT = False              # P7/D4: no-mmap (load 4 s vs 8 s)
SOGLIA_PICCOLI_LAYER = 36         # A3: piccoli ≲4 GB full
SOGLIA_PICCOLI_GB = 4.0
CAP_BREVE = 40                    # P1: 14B a contesto breve
PENDENZA_FINO_16K = 0.258         # P1/A4
PENDENZA_16_32K = 0.5             # P1/A4
MINIMO_OLTRE_32K = 20             # A4: estrapolazione dichiarata
LAYER_NOTI = {                    # ARCA REGOLE["layer_noti"]
    "deepseek-r1:14b": 48,
    "llama3.2:3b": 28,
    "qwen2.5:3b": 36,
}
PUNTI_TOK_S = (                   # ARCA campagna 19/09/2026 (GB, tok/s)
    (1.8, 89.3),
    (4.4, 42.85),
    (5.071, 39.0),
    (5.825, 35.0),
    (7.542, 27.34),
    (8.37, 18.9),
)
TOLLERANZA_FASCIA = 0.10
PUNTI_CONTESTO_14B = ((512, 18.9), (16384, 17.3), (32768, 14.9))
FATTORI_FORMATO = {"Q8_0": 0.64, "Q6_K": 0.82, "Q5_K_M": 0.91,
                   "Q4_K_M": 1.0, "Q3_K_M": None, "Q2_K": None}
BPW_FORMATO = {"Q8_0": 8.5, "Q6_K": 6.56, "Q5_K_M": 5.68,
               "Q4_K_M": 4.85, "Q3_K_M": 3.91, "Q2_K": 2.63}
FILE_TYPE_GGUF = {                # general.file_type (llama.cpp) → sigla
    0: "F32", 1: "F16", 2: "Q4_0", 3: "Q4_1", 7: "Q8_0", 8: "Q5_0", 9: "Q5_1",
    10: "Q2_K", 11: "Q3_K_S", 12: "Q3_K_M", 13: "Q3_K_L", 14: "Q4_K_S",
    15: "Q4_K_M", 16: "Q5_K_S", 17: "Q5_K_M", 18: "Q6_K",
}
FORMATI_NOTI = ("Q8_0", "Q6_K", "Q5_K_M", "Q4_K_M", "Q3_K_M", "Q2_K")

# ---- parser GGUF (header minimale, adattato da ARCA profiler.py) ----
_FORMATI_GGUF = {
    0: ("B", 1), 1: ("b", 1), 2: ("H", 2), 3: ("h", 2), 4: ("I", 4),
    5: ("i", 4), 6: ("f", 4), 7: ("?", 1), 10: ("Q", 8), 11: ("q", 8), 12: ("d", 8),
}


class ErrorePiano(Exception):
    """Errore di lettura/parsing (messaggio in italiano)."""


@dataclass
class MetadatiGGUF:
    """Metadati essenziali di un modello GGUF. Ogni campo None = non presente."""
    percorso: str
    nome: str
    dimensione_gb: Optional[float] = None
    n_layer: Optional[int] = None
    n_head_kv: Optional[int] = None
    head_dim: Optional[int] = None
    n_embd: Optional[int] = None
    context_length: Optional[int] = None
    quantizzazione: Optional[str] = None


@dataclass
class Piano:
    """Piano eseguibile per il modello al contesto richiesto."""
    modello: str
    contesto: int
    ngl: int
    kv_tipo: str
    thread: int
    mmap: bool
    stima_tok_s: float
    vram_richiesta_mib: Optional[int] = None
    vram_libera_mib: Optional[int] = None
    margine_residuo_mib: Optional[int] = None
    pesi_ram_gb: Optional[float] = None
    grande: bool = False
    rischio_spill: bool = False
    avvisi: List[str] = field(default_factory=list)


@dataclass
class Esito:
    """Risposta di `puo_stare`: sì/no + motivo + alternative pratiche."""
    ok: bool
    motivo: str
    alternative: List[str] = field(default_factory=list)


def _leggi_valore(file, tipo: int):
    if tipo == 8:
        lunghezza = struct.unpack("<Q", file.read(8))[0]
        return file.read(lunghezza).decode("utf-8", "replace")
    if tipo == 9:
        tipo_elemento = struct.unpack("<I", file.read(4))[0]
        quantita = struct.unpack("<Q", file.read(8))[0]
        _salta_elementi(file, tipo_elemento, quantita)
        return None
    formato = _FORMATI_GGUF.get(tipo)
    if formato is None:
        raise ErrorePiano(f"tipo di valore GGUF non riconosciuto: {tipo}")
    return struct.unpack("<" + formato[0], file.read(formato[1]))[0]


def _salta_elementi(file, tipo_elemento: int, quantita: int):
    if tipo_elemento == 8:
        for _ in range(quantita):
            lunghezza = struct.unpack("<Q", file.read(8))[0]
            file.seek(lunghezza, os.SEEK_CUR)
        return
    if tipo_elemento == 9:
        for _ in range(quantita):
            tipo_annidato = struct.unpack("<I", file.read(4))[0]
            quantita_annidata = struct.unpack("<Q", file.read(8))[0]
            _salta_elementi(file, tipo_annidato, quantita_annidata)
        return
    formato = _FORMATI_GGUF.get(tipo_elemento)
    if formato is None:
        raise ErrorePiano(f"tipo di elemento GGUF non riconosciuto: {tipo_elemento}")
    file.seek(formato[1] * quantita, os.SEEK_CUR)


def _metadato(metadati: dict, nome: str):
    suffisso = "." + nome
    for chiave, valore in metadati.items():
        if chiave == nome or chiave.endswith(suffisso):
            return valore
    return None


def leggi_metadati_gguf(percorso) -> MetadatiGGUF:
    """Header minimale di un GGUF (magic, versione 2/3, coppie chiave-valore):
    estrae i metadati necessari al Piano senza dipendenze esterne."""
    percorso = str(percorso)
    nome_file = os.path.basename(percorso)
    try:
        dimensione_gb = round(os.path.getsize(percorso) / 1024 ** 3, 2)
    except OSError as errore:
        raise ErrorePiano(f"impossibile aprire il file '{percorso}': {errore}")
    try:
        with open(percorso, "rb") as file:
            if file.read(4) != b"GGUF":
                raise ErrorePiano(f"file non in formato GGUF: {percorso}")
            versione = struct.unpack("<I", file.read(4))[0]
            if versione not in (2, 3):
                raise ErrorePiano(
                    f"versione GGUF non supportata dal parser minimale: {versione}")
            struct.unpack("<Q", file.read(8))[0]
            n_coppie = struct.unpack("<Q", file.read(8))[0]
            grezzi = {}
            for _ in range(n_coppie):
                lunghezza = struct.unpack("<Q", file.read(8))[0]
                chiave = file.read(lunghezza).decode("utf-8", "replace")
                tipo = struct.unpack("<I", file.read(4))[0]
                grezzi[chiave] = _leggi_valore(file, tipo)
    except ErrorePiano:
        raise
    except struct.error:
        raise ErrorePiano(f"file GGUF danneggiato o incompleto: {percorso}")
    except OSError as errore:
        raise ErrorePiano(f"impossibile leggere '{percorso}': {errore}")
    n_head = _metadato(grezzi, "attention.head_count")
    head_dim = _metadato(grezzi, "attention.key_length")
    n_embd = _metadato(grezzi, "embedding_length")
    if head_dim is None and n_head and n_embd:
        try:
            head_dim = int(n_embd) // int(n_head)
        except (TypeError, ValueError, ZeroDivisionError):
            head_dim = None
    quantizzazione = None
    file_type = _metadato(grezzi, "file_type")
    if file_type is not None:
        quantizzazione = FILE_TYPE_GGUF.get(int(file_type))
    if quantizzazione is None:
        testo = nome_file.upper()
        for formato in FORMATI_NOTI:
            if formato in testo:
                quantizzazione = formato
                break
    return MetadatiGGUF(
        percorso=percorso,
        nome=nome_file,
        dimensione_gb=dimensione_gb,
        n_layer=_metadato(grezzi, "block_count"),
        n_head_kv=_metadato(grezzi, "attention.head_count_kv"),
        head_dim=head_dim,
        n_embd=n_embd,
        context_length=_metadato(grezzi, "context_length"),
        quantizzazione=quantizzazione,
    )


# ---- costi byte (formule uniche ARCA: models.py) ----
def costo_pesi_mib(metadati: MetadatiGGUF) -> Optional[int]:
    """Costo byte dei pesi (MiB) = dimensione del file GGUF (header trascurabile)."""
    if metadati.dimensione_gb is None or metadati.dimensione_gb <= 0:
        return None
    return int(round(metadati.dimensione_gb * 1024))


def kv_per_token_mib(metadati: MetadatiGGUF, kv_tipo: str = "q8_0") -> float:
    """KV cache per token (MiB): 2 × n_layer × n_head_kv × head_dim × byte / 1024².
    q8_0 → 1 byte/elemento, f16 → 2. 0.0 se i metadati non bastano."""
    try:
        n_layer = int(metadati.n_layer)
        n_head_kv = int(metadati.n_head_kv)
        head_dim = int(metadati.head_dim)
    except (TypeError, ValueError):
        return 0.0
    if n_layer <= 0 or n_head_kv <= 0 or head_dim <= 0:
        return 0.0
    byte_elemento = 1 if kv_tipo == "q8_0" else 2
    return (2 * n_layer * n_head_kv * head_dim * byte_elemento) / 1024 ** 2


def kv_cache_mib(metadati: MetadatiGGUF, contesto: int, kv_tipo: str = "q8_0") -> int:
    """KV cache totale (MiB) al contesto dato. 0 se non calcolabile."""
    per_token = kv_per_token_mib(metadati, kv_tipo)
    if per_token <= 0 or contesto <= 0:
        return 0
    return int(round(per_token * contesto))


def _layer_stimati(nome: str) -> Optional[int]:
    """Layer noti per nome (ARCA REGOLE.layer_noti): stima dichiarata."""
    chiave = (nome or "").lower()
    for modello, layer in LAYER_NOTI.items():
        if modello in chiave or chiave in modello:
            return layer
    return None


def _e_grande(metadati: MetadatiGGUF, n_layer: Optional[int]) -> bool:
    """Grande = oltre la soglia piccoli (A3): >36 layer oppure >4 GB."""
    if n_layer is not None and n_layer > SOGLIA_PICCOLI_LAYER:
        return True
    dimensione = metadati.dimensione_gb or 0
    return dimensione > SOGLIA_PICCOLI_GB


def ginocchio(metadati: MetadatiGGUF, contesto: int, n_layer: Optional[int] = None):
    """(ngl, avvisi) con la regola A4 misurata: piccoli → 99 (full); 14B
    contesto-dipendente; mai ≥44 (clamp). n_layer None → stima dal nome."""
    avvisi: List[str] = []
    if contesto <= 0:
        raise ValueError(f"contesto non valido: {contesto} token")
    layer = n_layer if n_layer is not None else metadati.n_layer
    if layer is None:
        layer = _layer_stimati(metadati.nome)
        if layer is not None:
            avvisi.append(
                f"n_layer assente nei metadati: uso i layer noti di '{metadati.nome}' ({layer})")
    if (metadati.dimensione_gb or 0) <= SOGLIA_PICCOLI_GB:
        if layer is None:
            avvisi.append(
                "n_layer assente: modello piccolo (≤4 GB), ngl 99 full stimato")
        return 99, avvisi  # full-GPU (P4): llama.cpp clampa a n_layer
    if layer is None:
        return 0, avvisi + [
            "n_layer assente e non stimabile: ngl non determinabile (piano non affidabile)"]
    if layer <= SOGLIA_PICCOLI_LAYER:
        return 99, avvisi
    ctx_k = contesto / 1024.0
    if ctx_k <= 0.5:
        valore = float(CAP_BREVE)
    elif ctx_k <= 16.0:
        valore = CAP_BREVE - PENDENZA_FINO_16K * (ctx_k - 0.5)
    else:
        valore = (CAP_BREVE - PENDENZA_FINO_16K * 15.5
                  - PENDENZA_16_32K * (ctx_k - 16.0))
        if ctx_k > 32.0:
            avvisi.append(
                "non misurato oltre 32k: ngl stimato per estrapolazione della regola A4")
            valore = max(valore, float(MINIMO_OLTRE_32K))
    ngl = max(0, min(int(valore), int(layer)))
    if ngl >= NGN_VIETATO:
        avvisi.append(
            f"ngl {ngl} ridotto a {NGN_VIETATO - 1}: vietato ≥{NGN_VIETATO} (spill −60%)")
        ngl = NGN_VIETATO - 1
    return ngl, avvisi


def scegli_kv(kv: str, contesto: int):
    """(kv_tipo, avvisi): auto → q8_0 da 8k (B2b); f16 richiesta a ≥16k →
    q8_0 obbligatoria (P5/D3)."""
    if kv == "auto":
        return ("q8_0" if contesto >= KV_Q8_DA_TOKEN else "f16"), []
    if kv == "q8_0":
        return "q8_0", []
    if kv == "f16":
        if contesto >= KV_Q8_OBBLIGATORIA_DA_TOKEN:
            return "q8_0", [
                "KV f16 non disponibile a questo contesto: uso q8_0 "
                "(da 16k la f16 esaurisce la VRAM al ginocchio — P5)"]
        return "f16", []
    raise ValueError(f"tipo KV non riconosciuto: '{kv}' (attesi: auto, q8_0, f16)")


def _interpola(punti: Tuple[Tuple[float, float], ...], x: float) -> float:
    if x <= punti[0][0]:
        return punti[0][1]
    for (x1, y1), (x2, y2) in zip(punti, punti[1:]):
        if x <= x2:
            return y1 + (y2 - y1) * (x - x1) / (x2 - x1)
    return punti[-1][1]


def _base_tok_s(dimensione_gb: float):
    """(tok/s, calibrato): fascia misurata (tolleranza 10%) o interpolazione."""
    for gb, valore in PUNTI_TOK_S:
        if abs(dimensione_gb - gb) <= TOLLERANZA_FASCIA * gb:
            return float(valore), True
    if dimensione_gb < PUNTI_TOK_S[0][0]:
        return float(PUNTI_TOK_S[0][1]), False
    if dimensione_gb > PUNTI_TOK_S[-1][0]:
        return float(PUNTI_TOK_S[-1][1]), False
    return round(_interpola(tuple(PUNTI_TOK_S), dimensione_gb), 2), True


def _fattore_contesto(contesto: int) -> float:
    punti = PUNTI_CONTESTO_14B
    return _interpola(punti, contesto) / punti[0][1]


def stima_tok_s(metadati: MetadatiGGUF, contesto: int, grande: bool):
    """(tok/s, avvisi): fasce misurate ARCA (1,8/4,4/8,37 GB), correzione
    formato e decadimento contesto sul grande."""
    avvisi: List[str] = []
    dimensione = metadati.dimensione_gb
    formato = metadati.quantizzazione
    fattore = FATTORI_FORMATO.get(formato) if formato is not None else None
    if formato is not None and fattore is None and formato in FORMATI_NOTI:
        avvisi.append(
            f"{formato} non misurato nella campagna del 19/09/2026: "
            "stima base senza correzione di formato")
    if dimensione is not None and dimensione > 0:
        dimensione_stima = dimensione
        if fattore is not None and fattore != 1.0:
            bpw = BPW_FORMATO.get(formato)
            if bpw:
                dimensione_stima = dimensione * BPW_FORMATO["Q4_K_M"] / bpw
        base, calibrato = _base_tok_s(dimensione_stima)
        if not calibrato:
            avvisi.append(
                f"stima non calibrata per questo modello: {dimensione_stima:.2f} GB "
                "fuori dalle fasce misurate (~1,8-8,4 GB)")
    else:
        base = float(PUNTI_TOK_S[-1][1]) if grande else float(PUNTI_TOK_S[0][1])
        avvisi.append("stima non calibrata per questo modello: dimensione dei pesi non nota")
    if fattore is not None:
        base *= fattore
    if grande:
        base *= _fattore_contesto(contesto)
    return round(base, 2), avvisi


def pianifica(profilo, metadati: MetadatiGGUF, contesto_richiesto: int,
              kv: str = "auto") -> Piano:
    """Piano per il modello al contesto richiesto secondo le regole ARCA.
    `profilo`: `core.profiler.Profilo` (B2a). Mai crash su metadati mancanti:
    i dati assenti restano None e il motivo è negli `avvisi`."""
    avvisi: List[str] = []
    if contesto_richiesto <= 0:
        raise ValueError(f"contesto non valido: {contesto_richiesto} token")
    n_layer = metadati.n_layer
    grande = _e_grande(metadati, n_layer)
    kv_tipo, avvisi_kv = scegli_kv(kv, contesto_richiesto)
    avvisi.extend(avvisi_kv)
    ngl, avvisi_gin = ginocchio(metadati, contesto_richiesto)
    avvisi.extend(avvisi_gin)
    if n_layer is None and ngl > 0:
        n_layer = _layer_stimati(metadati.nome)
    ngl_eff = min(ngl, n_layer) if n_layer else ngl
    # thread: 12 in offload (P6/D10), 4 full-GPU, mai 24; clamp ai thread reali
    full = bool(n_layer) and ngl_eff >= n_layer
    thread = THREAD_FULL if full else THREAD_OFFLOAD
    if profilo.cpu_thread:
        thread = min(thread, int(profilo.cpu_thread))
    # costi byte
    pesi_mib = costo_pesi_mib(metadati)
    pesi_vram_mib = None
    pesi_ram_gb = None
    if pesi_mib is not None and n_layer:
        quota = min(max(0, ngl_eff), n_layer) / float(n_layer)
        pesi_vram_mib = int(round(pesi_mib * quota))
        pesi_ram_gb = round((pesi_mib - pesi_vram_mib) / 1024, 2)
    kv_mib = kv_cache_mib(metadati, contesto_richiesto, kv_tipo)
    vram_richiesta = (pesi_vram_mib + kv_mib) if pesi_vram_mib is not None else None
    # margini e rischio (D1/P8)
    vram_libera = profilo.vram_libera_mib
    margine_residuo = None
    rischio_spill = False
    if vram_richiesta is not None and vram_libera:
        margine_residuo = int(vram_libera - vram_richiesta)
        if margine_residuo < MARGINE_MINIMO_MIB:
            rischio_spill = True
            avvisi.append(
                f"margine insufficiente: ~{vram_richiesta} MiB richiesti su "
                f"{vram_libera} liberi (margine minimo {MARGINE_MINIMO_MIB} MiB): "
                "rischio spill")
        elif margine_residuo < MARGINE_WDDM_MIB:
            rischio_spill = True
            avvisi.append(
                f"piano al limite: margine residuo {margine_residuo} MiB, sotto i "
                f"{MARGINE_WDDM_MIB} MiB consigliati (P8: allocazione in blocco WDDM "
                "~1 GiB può essere negata): rischio spill")
    if vram_richiesta is not None and profilo.vram_totale_mib:
        tetto = int(profilo.vram_totale_mib * (1.0 - RISERVA_VRAM_FRAZIONE))
        if vram_richiesta > tetto:
            avvisi.append(
                f"stop-rule 90% VRAM: picco ~{vram_richiesta} MiB oltre il tetto "
                f"{tetto} MiB (90% di {profilo.vram_totale_mib} MiB)")
    if pesi_ram_gb is not None and pesi_ram_gb > BUDGET_RAM_GB:
        avvisi.append(
            f"budget RAM: pesi in RAM {pesi_ram_gb} GB oltre il budget ~{BUDGET_RAM_GB} GB (P10)")
    if grande:
        avvisi.append(
            "regola ARCA: un solo modello grande residente — scarica il precedente prima del load")
    stima, avvisi_stima = stima_tok_s(metadati, contesto_richiesto, grande)
    avvisi.extend(avvisi_stima)
    return Piano(
        modello=metadati.nome,
        contesto=contesto_richiesto,
        ngl=ngl,
        kv_tipo=kv_tipo,
        thread=thread,
        mmap=MMAP_DEFAULT,
        stima_tok_s=stima,
        vram_richiesta_mib=vram_richiesta,
        vram_libera_mib=vram_libera,
        margine_residuo_mib=margine_residuo,
        pesi_ram_gb=pesi_ram_gb,
        grande=grande,
        rischio_spill=rischio_spill,
        avvisi=avvisi,
    )


def puo_stare(piano: Piano, profilo, grande_residente: bool = False) -> Esito:
    """Ammissibilità del piano sulle risorse attuali: sì | no + motivo +
    alternative pratiche. Regole: mai ≥44 (P2), 48+ OOM (P3), stop-rule 90%
    (D1), margine minimo 550 MiB (D1), budget RAM ~20 GB (P10), un solo
    modello grande residente."""
    alternative: List[str] = []
    if piano.ngl >= NGN_OOM:
        return Esito(False,
                     f"ngl {piano.ngl}: limite di load ARCA (P3: 48 e 99 → OOM)",
                     ["usa il ginocchio contesto-dipendente (≤43)",
                      "riduci il contesto richiesto"])
    if piano.ngl >= NGN_VIETATO:
        return Esito(False,
                     f"ngl {piano.ngl}: soglia spill ARCA (P2: a 44 tg 7.46, −60%)",
                     ["riduci ngl sotto 44 (ginocchio contesto-dipendente)"])
    if grande_residente and piano.grande:
        return Esito(False,
                     "un solo modello grande residente (ARCA D1): ne è già attivo uno",
                     ["scarica il modello grande precedente prima del load",
                      "usa un modello piccolo (≲4 GB) per questa voce"])
    libera = profilo.vram_libera_mib
    totale = profilo.vram_totale_mib
    richiesta = piano.vram_richiesta_mib
    if richiesta is not None and not libera:
        return Esito(True,
                     "VRAM non rilevata: piano non verificabile (ammissibile con riserva)")
    if richiesta is not None and libera:
        if richiesta > libera - MARGINE_MINIMO_MIB:
            alternative = ["KV q8_0 (se non già attiva)", "riduci il contesto",
                           "riduci ngl", "libera VRAM (chiudi app che la occupano)"]
            if richiesta > libera:
                return Esito(False,
                             f"VRAM insufficiente: il piano richiede ~{richiesta} MiB, "
                             f"liberi {libera}", alternative)
            return Esito(False,
                         f"margine insufficiente: ~{richiesta} MiB + {MARGINE_MINIMO_MIB} "
                         f"di margine su {libera} liberi (D1/P8): rischio spill",
                         alternative)
    if richiesta is not None and totale:
        tetto = int(totale * (1.0 - RISERVA_VRAM_FRAZIONE))
        if richiesta > tetto:
            return Esito(False,
                         f"stop-rule 90% VRAM: picco ~{richiesta} MiB oltre il tetto "
                         f"{tetto} MiB",
                         ["riduci contesto o ngl", "KV q8_0"])
    if piano.pesi_ram_gb is not None and piano.pesi_ram_gb > BUDGET_RAM_GB:
        return Esito(False,
                     f"budget RAM: pesi in RAM {piano.pesi_ram_gb} GB oltre ~{BUDGET_RAM_GB} GB (P10)",
                     ["aumenta ngl (più layer in VRAM)", "usa un modello più piccolo"])
    if richiesta is None:
        return Esito(True,
                     "metadati insufficienti per il bilancio byte: piano non verificabile "
                     "contro la VRAM (avviso)")
    if piano.margine_residuo_mib is not None and piano.margine_residuo_mib < MARGINE_WDDM_MIB:
        return Esito(True,
                     f"ammissibile con rischio WDDM: margine residuo "
                     f"{piano.margine_residuo_mib} MiB (< {MARGINE_WDDM_MIB} MiB, P8)",
                     ["verifica con una sessione reale"])
    return Esito(True, f"piano ammissibile: margine residuo {piano.margine_residuo_mib} MiB")
