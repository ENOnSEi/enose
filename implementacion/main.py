#!/usr/bin/env python3
"""
Electronic Nose Project - Pipeline Entry Point

Usage:
    python main.py                  # Fases 4 + 5
    python main.py --phase 4        # Solo extracción de características
    python main.py --phase 5        # Solo entrenamiento (requiere dataset)
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from enose.config import DATA_PROCESSED_DIR, DATA_RAW_DIR, DATASET_MAESTRO_PATH, PROJECT_ROOT
from enose.pipeline.dataset import DatasetGenerator
from enose.model.trainer import ModelTrainer


def run_phase4() -> bool:
    print("\n" + "=" * 80)
    print("PHASE 4: Feature Extraction → Master Dataset".center(80))
    print("=" * 80)
    try:
        df = DatasetGenerator(data_dir=DATA_RAW_DIR).generate_dataset(output_path=DATASET_MAESTRO_PATH)
        if df is not None:
            print(f"\nDataset: {df.shape[0]} muestras × {df.shape[1]} características")
            print(f"Guardado en: {DATASET_MAESTRO_PATH}")
            return True
        print("\nERROR: Generación de dataset fallida")
        return False
    except Exception as e:
        print(f"\nERROR en Fase 4: {e}")
        import traceback; traceback.print_exc()
        return False


def run_phase5() -> bool:
    print("\n" + "=" * 80)
    print("PHASE 5: SVM Training & Evaluation".center(80))
    print("=" * 80)
    try:
        ok = ModelTrainer(dataset_path=DATASET_MAESTRO_PATH).train()
        if ok:
            print(f"\nModelo guardado en: {DATA_PROCESSED_DIR}")
            return True
        print("\nERROR: Entrenamiento fallido")
        return False
    except Exception as e:
        print(f"\nERROR en Fase 5: {e}")
        import traceback; traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description="Electronic Nose Pipeline")
    parser.add_argument("--phase", type=int, choices=[4, 5],
                        help="Fase a ejecutar (omitir = ambas)")
    args = parser.parse_args()

    print("=" * 80)
    print("ELECTRONIC NOSE PROJECT — ML PIPELINE".center(80))
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


if __name__ == "__main__":
    main()
