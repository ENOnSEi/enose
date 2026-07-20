"""
Fetch recordings from the API, extract features, build dataset_maestro.csv, and train.

Usage:
    uv run python train_from_api.py                          # all complete samples
    uv run python train_from_api.py --sample-ids 6 7 8       # specific samples
    uv run python train_from_api.py --api-url http://host:8000
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

# Add src to path so enose is importable
sys.path.insert(0, str(Path(__file__).parent / "src"))

from enose.config import (
    DATASET_MAESTRO_PATH, FILENAME_COLUMN, LABEL_COLUMN, DATA_PROCESSED_DIR,
)
from enose.features.handcrafted import HandcraftedExtractor
from enose.io.api import DEFAULT_API, fetch_recordings, recording_to_features
from enose.utils import create_output_directory, setup_logging

logger = setup_logging(__name__)


def build_dataset(recordings: list[dict]) -> pd.DataFrame:
    extractor = HandcraftedExtractor()
    rows = []

    for rec in recordings:
        ms_id = rec["measurement_set_id"]
        sample_name = rec["sample_name"]
        rep = rec["repetition_number"]

        # extracción única y compartida con la inferencia (enose.io.api)
        features = recording_to_features(rec, extractor)
        if features is None:
            logger.warning(f"ms_id={ms_id} ({sample_name} rep{rep}): sin fase medicion, skip")
            continue

        row = {
            FILENAME_COLUMN: f"{sample_name}_rep{rep}_ms{ms_id}",
            LABEL_COLUMN: sample_name,
            **features,
        }
        rows.append(row)
        logger.info(f"  ms_id={ms_id} {sample_name} rep{rep}: {len(features)} features")

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    feature_cols = [c for c in df.columns if c not in {FILENAME_COLUMN, LABEL_COLUMN}]
    df[feature_cols] = df[feature_cols].fillna(0.0)
    return df


def main():
    parser = argparse.ArgumentParser(description="Train from API data")
    parser.add_argument("--api-url", default=DEFAULT_API)
    parser.add_argument("--sample-ids", type=int, nargs="*", default=None,
                        help="Sample IDs to include (default: all)")
    parser.add_argument("--dataset-only", action="store_true",
                        help="Only generate dataset_maestro.csv, don't train")
    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("FETCH & TRAIN FROM API")
    logger.info("=" * 70)

    logger.info(f"Fetching from {args.api_url}...")
    recordings = fetch_recordings(args.api_url, args.sample_ids)
    logger.info(f"Recordings fetched: {len(recordings)}")

    if not recordings:
        logger.error("No recordings found. Is the API running?")
        sys.exit(1)

    logger.info("Extracting features...")
    df = build_dataset(recordings)

    if df.empty:
        logger.error("No features extracted from any recording")
        sys.exit(1)

    create_output_directory(DATASET_MAESTRO_PATH.parent)
    df.to_csv(DATASET_MAESTRO_PATH, index=False)
    logger.info(f"Dataset: {df.shape[0]} samples × {df.shape[1]} columns")
    logger.info(f"Classes: {df[LABEL_COLUMN].value_counts().to_dict()}")
    logger.info(f"Saved to: {DATASET_MAESTRO_PATH}")

    if args.dataset_only:
        logger.info("--dataset-only: skipping training")
        return

    logger.info("=" * 70)
    logger.info("TRAINING")
    logger.info("=" * 70)

    from enose.model.trainer import ModelTrainer
    trainer = ModelTrainer()
    if not trainer.train():
        sys.exit(1)


if __name__ == "__main__":
    main()
