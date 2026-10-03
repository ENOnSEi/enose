"""
¿El modelo aprende "el día" en vez del olor? (Obstáculos de reproducibilidad, punto 9)

Entrena SOLO con features de la fase base (aire limpio) y valida agrupando por
Sample. Si acierta la sustancia claramente por encima del azar (test de
permutación a nivel de Sample), hay confusión con las condiciones de medida.
Como referencia calcula también la cifra con las features de medición.

Usage:
    uv run python confounder_test.py                         # todos los samples
    uv run python confounder_test.py --sample-ids 6 7 8 9
    uv run python confounder_test.py --only-first-rep        # evita carry-over entre reps
    uv run python confounder_test.py --permutations 500
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent / "src"))

from enose.config import DATA_PROCESSED_DIR
from enose.features.handcrafted import HandcraftedExtractor
from enose.io.api import DEFAULT_API, fetch_recordings, recording_to_dataframe, recording_to_features
from enose.model.confounder import baseline_features, confounder_test, grouped_cv_score
from enose.utils import create_output_directory, setup_logging

logger = setup_logging(__name__)


def build_tables(recordings: list[dict], only_first_rep: bool):
    """Devuelve (base_df, signal_df): una fila por MS con 'label', 'group' y features."""
    extractor = HandcraftedExtractor()
    base_rows, signal_rows = [], []
    for rec in recordings:
        if only_first_rep and rec["repetition_number"] != 1:
            continue
        meta = {"label": rec["sample_name"], "group": f"sample_{rec['sample_id']}"}
        base = baseline_features(recording_to_dataframe(rec))
        signal = recording_to_features(rec, extractor)
        if base is None or signal is None:
            logger.warning(f"ms_id={rec['measurement_set_id']}: sin base o sin medición, skip")
            continue
        base_rows.append({**meta, **base})
        signal_rows.append({**meta, **signal})
    return pd.DataFrame(base_rows), pd.DataFrame(signal_rows).fillna(0.0)


def xyg(df: pd.DataFrame):
    return df.drop(columns=["label", "group"]).to_numpy(float), df["label"].to_numpy(), df["group"].to_numpy()


def main():
    parser = argparse.ArgumentParser(description="Test de confusión con el tiempo (features de base)")
    parser.add_argument("--api-url", default=DEFAULT_API)
    parser.add_argument("--sample-ids", type=int, nargs="*", default=None)
    parser.add_argument("--only-first-rep", action="store_true",
                        help="Usa solo la rep 1 de cada Sample (su base no viene de un cooldown de la misma sustancia)")
    parser.add_argument("--permutations", type=int, default=200)
    parser.add_argument("--repeats", type=int, default=3, help="Particiones de CV promediadas")
    args = parser.parse_args()

    recordings = fetch_recordings(args.api_url, args.sample_ids, only_complete=True)
    if not recordings:
        logger.error("No hay grabaciones completas. ¿Está la API levantada?")
        sys.exit(1)

    base_df, signal_df = build_tables(recordings, args.only_first_rep)
    if base_df.empty:
        logger.error("Ninguna grabación con fase base y medición")
        sys.exit(1)

    groups_per_class = base_df.drop_duplicates("group").groupby("label")["group"].count()
    logger.info(f"Grabaciones: {len(base_df)} | Samples por clase: {groups_per_class.to_dict()}")
    if groups_per_class.min() < 2:
        logger.error(f"Clases con un solo Sample: {groups_per_class[groups_per_class < 2].index.tolist()}. "
                     "Excluye esas sustancias (--sample-ids) o mide más Samples.")
        sys.exit(1)

    X, y, g = xyg(base_df)
    logger.info(f"Test de permutación ({args.permutations} perms × {args.repeats} particiones)...")
    res = confounder_test(X, y, g, n_permutations=args.permutations, n_repeats=args.repeats)
    signal_score = grouped_cv_score(*xyg(signal_df), n_repeats=args.repeats)

    logger.info("=" * 70)
    logger.info(f"Balanced accuracy agrupada por Sample ({res.n_classes} clases, {res.n_groups} Samples)")
    logger.info(f"  Azar teórico            : {res.chance*100:5.1f}%")
    logger.info(f"  Azar (permutación) media: {res.perm_mean*100:5.1f}%  | p95: {res.perm_p95*100:5.1f}%")
    logger.info(f"  SOLO BASE (aire limpio) : {res.score*100:5.1f}%  | p = {res.p_value:.3f}")
    logger.info(f"  Features de medición    : {signal_score*100:5.1f}%  (referencia)")
    logger.info("=" * 70)
    if res.confounded:
        logger.warning("CONFUSIÓN PROBABLE: la base (sin olor) predice la sustancia mejor que el azar. "
                       "Las sustancias se han medido en condiciones distintas (día, deriva, humedad...). "
                       "La accuracy del modelo no demuestra que reconozca el olor.")
        if not args.only_first_rep:
            logger.warning("Repite con --only-first-rep para descartar carry-over del cooldown.")
    else:
        logger.info("Sin evidencia de confusión: la base no predice la sustancia mejor que el azar.")

    out = DATA_PROCESSED_DIR / "confounder_test.json"
    create_output_directory(out.parent)
    out.write_text(json.dumps({
        **res.as_dict(),
        "signal_score": signal_score,
        "only_first_rep": args.only_first_rep,
        "sample_ids": sorted(set(base_df["group"])),
    }, indent=2), encoding="utf-8")
    logger.info(f"Guardado en {out}")


if __name__ == "__main__":
    main()
