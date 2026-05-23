#!/usr/bin/env python3
"""
Electronic Nose Project - Main Pipeline Entry Point

Runs the full pipeline end-to-end:
  Phase 4: Feature extraction -> master dataset CSV
  Phase 5: SVM training, evaluation, and model export

Usage:
    python main.py                  # Run full pipeline
    python main.py --phase 4        # Feature extraction only
    python main.py --phase 5        # Model training only (requires dataset)
"""

import sys
import argparse
from pathlib import Path

src_dir = Path(__file__).parent / 'src'
sys.path.insert(0, str(src_dir))

from config import PROJECT_ROOT, DATA_RAW_DIR, DATASET_MAESTRO_PATH, DATA_PROCESSED_DIR
from phase_4_dataset_generation import DatasetGenerator
from phase_5_model_training import ModelTrainer


def run_phase4() -> bool:
    print("\n" + "=" * 80)
    print("PHASE 4: Feature Extraction -> Master Dataset".center(80))
    print("=" * 80)
    try:
        generator = DatasetGenerator(data_dir=DATA_RAW_DIR)
        df = generator.generate_dataset(output_path=DATASET_MAESTRO_PATH)
        if df is not None:
            print(f"\nDataset generated: {df.shape[0]} samples x {df.shape[1]} features")
            print(f"Saved to: {DATASET_MAESTRO_PATH}")
            return True
        print("\nERROR: Dataset generation failed")
        return False
    except Exception as e:
        print(f"\nERROR in Phase 4: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_phase5() -> bool:
    print("\n" + "=" * 80)
    print("PHASE 5: SVM Training & Evaluation".center(80))
    print("=" * 80)
    try:
        trainer = ModelTrainer(dataset_path=DATASET_MAESTRO_PATH)
        success = trainer.train()
        if success:
            print(f"\nModel saved to: {DATA_PROCESSED_DIR}")
            return True
        print("\nERROR: Model training failed")
        return False
    except Exception as e:
        print(f"\nERROR in Phase 5: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description="Electronic Nose Pipeline")
    parser.add_argument(
        "--phase", type=int, choices=[4, 5],
        help="Run only phase 4 (dataset) or phase 5 (training). Omit to run both."
    )
    args = parser.parse_args()

    print("=" * 80)
    print("ELECTRONIC NOSE PROJECT - ML PIPELINE".center(80))
    print("=" * 80)
    print(f"\nProject root : {PROJECT_ROOT}")
    print(f"Raw data     : {DATA_RAW_DIR}")
    print(f"Dataset      : {DATASET_MAESTRO_PATH}")
    print(f"Output       : {DATA_PROCESSED_DIR}")

    if args.phase == 4:
        ok = run_phase4()
    elif args.phase == 5:
        ok = run_phase5()
    else:
        ok = run_phase4() and run_phase5()

    if ok:
        print("\n" + "=" * 80)
        print("PIPELINE COMPLETED SUCCESSFULLY".center(80))
        print("=" * 80)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
