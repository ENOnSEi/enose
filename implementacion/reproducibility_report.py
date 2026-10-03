"""
Informe de reproducibilidad (Obstáculos de reproducibilidad, punto 8).

Por sustancia y sensor: CV dentro del Sample (repetibilidad), CV entre Samples
(reproducibilidad entre tandas), ICC de tanda y tendencia rep1 → repN. Por
sensor: CV de R0 entre Samples. Definiciones en enose/report/reproducibility.py.

Usage:
    uv run python reproducibility_report.py
    uv run python reproducibility_report.py --sample-ids 6 7 8 9
    uv run python reproducibility_report.py --scale delta     # ADC en vez de (Rs−R0)/R0
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent / "src"))

from enose.config import DATA_PROCESSED_DIR
from enose.io.api import DEFAULT_API, fetch_recordings, recording_to_dataframe
from enose.report.reproducibility import r0_stats, rep_responses, reproducibility_stats
from enose.utils import create_output_directory, setup_logging

logger = setup_logging(__name__)
OUT_DIR = DATA_PROCESSED_DIR / "reproducibilidad"


def build_responses(recordings: list[dict]) -> pd.DataFrame:
    rows = []
    for rec in recordings:
        for sensor, vals in rep_responses(recording_to_dataframe(rec)).items():
            rows.append({"ms_id": rec["measurement_set_id"], "sample_id": rec["sample_id"],
                         "label": rec["sample_name"], "rep": rec["repetition_number"],
                         "sensor": sensor, **vals})
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description="Informe de reproducibilidad")
    parser.add_argument("--api-url", default=DEFAULT_API)
    parser.add_argument("--sample-ids", type=int, nargs="*", default=None)
    parser.add_argument("--scale", choices=["frac", "delta"], default="frac",
                        help="frac = (Rs−R0)/R0 (defecto) | delta = Rs−R0 en ADC")
    args = parser.parse_args()

    recordings = fetch_recordings(args.api_url, args.sample_ids, only_complete=True)
    if not recordings:
        logger.error("No hay grabaciones completas. ¿Está la API levantada?")
        sys.exit(1)

    responses = build_responses(recordings)
    if responses.empty:
        logger.error("Ninguna grabación con fase base y medición")
        sys.exit(1)

    stats = reproducibility_stats(responses, args.scale)
    r0 = r0_stats(responses)

    pd.set_option("display.width", 160)
    pd.set_option("display.max_rows", 200)
    fmt = {c: "{:.1%}".format for c in ("cv_intra", "cv_inter", "r0_cv")}
    fmt.update(icc_batch="{:.2f}".format, trend_pct_per_rep="{:+.1f}%".format)
    logger.info(f"Escala: {args.scale} | {responses['ms_id'].nunique()} reps, "
                f"{responses['sample_id'].nunique()} Samples, {responses['label'].nunique()} sustancias")
    print("\nPor sustancia y sensor\n" + stats.to_string(index=False, formatters=fmt))
    print("\nR0 entre Samples (rep 1)\n" + r0.to_string(index=False, formatters=fmt))

    # Lectura rápida de los resultados
    valid = stats.dropna(subset=["cv_intra", "cv_inter"])
    if not valid.empty:
        ratio = (valid["cv_inter"] / valid["cv_intra"]).median()
        print(f"\nMediana de CV entre Samples / CV dentro del Sample: {ratio:.1f}×"
              + ("  → la variación entre tandas domina: efecto tanda/día" if ratio > 2 else ""))
    icc = stats["icc_batch"].dropna()
    if not icc.empty:
        print(f"ICC de tanda mediano: {icc.median():.2f}"
              + ("  → más de la mitad de la varianza se explica por la tanda" if icc.median() > 0.5 else ""))
    if stats["n_samples"].max() < 2:
        print("Aviso: ninguna sustancia tiene ≥2 Samples; CV entre Samples e ICC no se pueden calcular.")

    create_output_directory(OUT_DIR)
    responses.to_csv(OUT_DIR / "respuestas_por_rep.csv", index=False)
    stats.to_csv(OUT_DIR / f"reproducibilidad_{args.scale}.csv", index=False)
    r0.to_csv(OUT_DIR / "r0_entre_samples.csv", index=False)
    (OUT_DIR / f"resumen_{args.scale}.json").write_text(json.dumps({
        "scale": args.scale,
        "sample_ids": sorted(int(s) for s in responses["sample_id"].unique()),
        "stats": stats.to_dict(orient="records"),
        "r0": r0.to_dict(orient="records"),
    }, indent=2, default=float), encoding="utf-8")
    logger.info(f"Guardado en {OUT_DIR}")


if __name__ == "__main__":
    main()
