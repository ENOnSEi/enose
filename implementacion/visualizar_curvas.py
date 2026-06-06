#!/usr/bin/env python3
"""
Visualización del comportamiento de las curvas de los sensores.

Genera dos figuras en datos/procesados/visualizations/:
  - 01_curvas_crudas.png      : señal cruda de los 4 sensores TGS por grabación,
                                con las fases 'base' y 'medicion' sombreadas.
  - 02_curvas_normalizadas.png: respuesta normalizada (R0 - Rs)/R0 de la fase
                                'medicion', superponiendo todas las mezclas por
                                sensor (así se ve cómo se diferencian las clases).

Uso:
    python visualizar_curvas.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

import matplotlib.pyplot as plt
import numpy as np

from enose.config import (
    BASELINE_STATE, DATA_PROCESSED_DIR, DATA_RAW_DIR, MEASUREMENT_STATE,
    SENSOR_COLUMNS, SENSOR_MODELS, STATE_COLUMN, TIMESTAMP_COLUMN, WARMUP_STATE,
)
from enose.io.reader import (
    extract_substance_label, get_baseline_and_signal, get_files_recursive,
    load_sensor_file,
)
from enose.signal.processor import SignalProcessor

SENSORS = list(SENSOR_COLUMNS["sensors"])
PHASE_COLORS = {WARMUP_STATE: "#dddddd", BASELINE_STATE: "#cfe8ff", MEASUREMENT_STATE: "#ffe0cc"}


def _time_seconds(df_phase) -> np.ndarray:
    """Eje temporal en segundos a partir de la columna de timestamps (ms)."""
    t = df_phase[TIMESTAMP_COLUMN].to_numpy(dtype=float)
    return (t - t[0]) / 1000.0 if len(t) else t


def plot_raw_with_phases(files, out_path: Path) -> None:
    """Una fila por grabación: las 4 señales crudas con las fases sombreadas."""
    n = len(files)
    fig, axes = plt.subplots(n, 1, figsize=(13, 3 * n), squeeze=False)

    for row, fp in enumerate(files):
        ax = axes[row][0]
        df = load_sensor_file(fp)
        label = extract_substance_label(fp.name)
        if df is None:
            continue

        t_all = (df[TIMESTAMP_COLUMN].to_numpy(dtype=float) - df[TIMESTAMP_COLUMN].iloc[0]) / 1000.0

        # Sombrear cada tramo CONTIGUO de fase usando el orden temporal real.
        states = df[STATE_COLUMN].to_numpy()
        seen = set()
        run_start = 0
        for i in range(1, len(states) + 1):
            if i == len(states) or states[i] != states[run_start]:
                state = states[run_start]
                x0, x1 = t_all[run_start], t_all[i - 1]
                ax.axvspan(x0, x1, color=PHASE_COLORS.get(state, "#eeeeee"),
                           alpha=0.6, label=state if state not in seen else None)
                seen.add(state)
                run_start = i

        for sensor in SENSORS:
            ax.plot(t_all, df[sensor].to_numpy(), linewidth=1.3,
                    label=f"{sensor} ({SENSOR_MODELS[sensor]})")

        ax.set_title(f"{label}  ·  {fp.name}", fontweight="bold")
        ax.set_ylabel("Lectura ADC")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8, ncol=2, loc="upper right")
    axes[-1][0].set_xlabel("Tiempo (s)")

    fig.suptitle("Señales crudas por grabación (fases: base / medición)",
                 fontsize=15, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.99))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [OK] {out_path}")


def plot_normalized_by_sensor(files, out_path: Path) -> None:
    """Un subplot por sensor: respuesta normalizada de 'medicion' por mezcla."""
    processor = SignalProcessor()
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    axes = axes.flatten()

    for ax, sensor in zip(axes, SENSORS):
        for fp in files:
            df = load_sensor_file(fp)
            if df is None:
                continue
            pair = get_baseline_and_signal(df, sensor)
            if pair is None:
                continue
            baseline, signal = pair
            _, normalized = processor.process_signal(signal, baseline)
            t = np.arange(len(normalized)) * processor.dt
            ax.plot(t, normalized, linewidth=1.6, label=extract_substance_label(fp.name))

        ax.axhline(0.0, color="black", linewidth=0.8, alpha=0.5)
        ax.set_title(f"{sensor}  ({SENSOR_MODELS[sensor]})", fontweight="bold")
        ax.set_xlabel("Tiempo de medición (s)")
        ax.set_ylabel("Respuesta normalizada (R0 - Rs)/R0")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)

    fig.suptitle("Respuesta normalizada de la fase 'medición' por sensor y mezcla",
                 fontsize=15, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.99))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [OK] {out_path}")


def main() -> int:
    files = get_files_recursive(DATA_RAW_DIR, "*.csv")
    if not files:
        print(f"No hay grabaciones .csv en {DATA_RAW_DIR}")
        return 1

    viz_dir = DATA_PROCESSED_DIR / "visualizations"
    print(f"Grabaciones: {len(files)}  →  {viz_dir}")
    plot_raw_with_phases(files, viz_dir / "01_curvas_crudas.png")
    plot_normalized_by_sensor(files, viz_dir / "02_curvas_normalizadas.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
