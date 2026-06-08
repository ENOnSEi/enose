"""Calibración offline del SignalAnalyzer con grabaciones reales de datasets/.

Reproduce, sin placa ni BD, qué decidiría el analizador sobre cada CSV:
  - diagnóstico de pendiente por sensor (pico de subida vs. meseta final),
    en counts ADC/s y en %R0/s (relativo a la línea base),
  - barrido de umbrales: a qué segundo de la medición dispararía el `stop`.

Sirve para elegir OBSERVER_SLOPE_THRESHOLD con datos en vez de a ojo, y para ver
si conviene un umbral absoluto (counts/s) o relativo (%R0/s).

Uso:
    python tools/calibrate.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # api/

from app.services.analyzer import (  # noqa: E402
    ChannelState,
    Policy,
    SignalAnalyzer,
    _slope_per_second,
)

DATASETS = Path(__file__).resolve().parents[2] / "datasets"

# columna CSV -> nombre de sensor (orden del Arduino)
COLS = {"v20": "tgs2620", "v11": "tgs2611", "v02": "tgs2602", "v00": "tgs2600"}

WINDOW_SECONDS = 4.0
HYSTERESIS = 0.15
CONFIRM_SECONDS = 1.0
MIN_MEDICION = 30.0
THRESHOLDS = [5, 8, 10, 15, 20, 30]  # counts/s a barrer

# grabaciones que NO sirven para fijar el umbral (con motivo)
EXCLUIDAS = {
    "vinoagitacionrara.csv": "agitación manual irregular (artefacto, no del sensor)",
}


def load(path: Path):
    """Devuelve (rows, base_rows, medicion_rows). Cada row = (ms, {sensor: val})."""
    rows, base, medicion = [], [], []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            ms = int(r["data"])
            vals = {COLS[c]: int(r[c]) for c in COLS}
            rows.append((ms, vals))
            if r["estado"] == "base":
                base.append((ms, vals))
            elif r["estado"] == "medicion":
                medicion.append((ms, vals))
    return rows, base, medicion


def r0_por_sensor(base) -> dict[str, float]:
    """R0 = media de la fase base por sensor (mitad final, ya asentada)."""
    if not base:
        return {}
    tail = base[len(base) // 2 :]
    out = {}
    for name in COLS.values():
        vals = [v[name] for _, v in tail]
        out[name] = sum(vals) / len(vals) if vals else 1.0
    return out


def diagnostico_pendientes(medicion, r0):
    """Por sensor: pico |pendiente| y |pendiente| de la meseta final (u/s y %R0/s)."""
    t0 = medicion[0][0]
    diag = {}
    for name in COLS.values():
        pts = [((ms - t0) / 1000.0, v[name]) for ms, v in medicion]
        peak = 0.0
        last = 0.0
        for i in range(len(pts)):
            t_now = pts[i][0]
            window = [(t, y) for t, y in pts[: i + 1] if t >= t_now - WINDOW_SECONDS]
            s = _slope_per_second(window)
            if s is None:
                continue
            peak = max(peak, abs(s))
            last = abs(s)  # se queda con el último válido = meseta final
        base_val = max(r0.get(name, 1.0), 1.0)
        diag[name] = {
            "peak": peak,
            "last": last,
            "peak_rel": 100 * peak / base_val,
            "last_rel": 100 * last / base_val,
        }
    return diag


def stop_para_umbral(medicion, threshold) -> float | None:
    """Segundo (relativo a inicio de medición) en que el analizador confirma
    ESTABILIZADO por primera vez. None si nunca."""
    an = SignalAnalyzer(
        window_seconds=WINDOW_SECONDS,
        slope_threshold=threshold,
        hysteresis=HYSTERESIS,
        confirm_seconds=CONFIRM_SECONDS,
        policy=Policy.ALL,
    )
    an.reset()
    t0 = medicion[0][0]
    feed = []
    for ms, vals in medicion:
        feed.append((ms, vals))
        res = an.update(feed)
        if res.transition is ChannelState.ESTABILIZADO:
            return (ms - t0) / 1000.0
    return None


def fmt(x, none="—", width=6):
    return none.rjust(width) if x is None else f"{x:{width}.1f}"


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # consola Windows cp1252
    files = sorted(DATASETS.glob("*.csv"))
    for path in files:
        rows, base, medicion = load(path)
        excluida = EXCLUIDAS.get(path.name)
        if not medicion:
            print(f"\n### {path.name}: sin fase medicion, se omite")
            continue

        dur = (medicion[-1][0] - medicion[0][0]) / 1000.0
        dts = [medicion[i + 1][0] - medicion[i][0] for i in range(len(medicion) - 1)]
        dt = median(dts) / 1000.0 if dts else 0.0
        r0 = r0_por_sensor(base)

        print("\n" + "=" * 78)
        tag = f"  [EXCLUIDA: {excluida}]" if excluida else ""
        nobase = "  [SIN BASE → R0 no fiable]" if not base else ""
        print(f"{path.name}{tag}{nobase}")
        print(f"  medicion: {len(medicion)} muestras, {dur:.0f}s, dt≈{dt*1000:.0f}ms")

        diag = diagnostico_pendientes(medicion, r0)
        print(f"  {'sensor':10} {'R0':>6} {'pico u/s':>9} {'mes u/s':>8} "
              f"{'pico %R0/s':>11} {'mes %R0/s':>10}")
        for name, d in diag.items():
            print(f"  {name:10} {r0.get(name, 0):6.0f} {d['peak']:9.1f} "
                  f"{d['last']:8.1f} {d['peak_rel']:11.1f} {d['last_rel']:10.2f}")

        print(f"  {'umbral u/s':>10} -> stop@s (con gate {MIN_MEDICION:.0f}s):")
        line = "   "
        for thr in THRESHOLDS:
            t = stop_para_umbral(medicion, thr)
            # gate: el stop real exige >= MIN_MEDICION; si estabiliza antes, el
            # efectivo es ~MIN (seguirá estable hasta cumplirlo)
            eff = None if t is None else (t if t >= MIN_MEDICION else MIN_MEDICION)
            line += f"{thr:>3}:{fmt(t,width=5)}/{fmt(eff,width=5)}  "
        print(line)
    print("\n(stop@s = primer ESTABILIZADO; segundo nº = efectivo con gate de 30s)")


if __name__ == "__main__":
    main()
