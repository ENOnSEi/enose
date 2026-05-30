#!/usr/bin/env python3
"""
Quick test for Phase 5 (Model Training) using an existing dataset.
Run from the project root: python tests/test_phase5.py
"""

import sys
from pathlib import Path

src_dir = Path(__file__).parent.parent / 'src'
sys.path.insert(0, str(src_dir))

from config import DATASET_MAESTRO_PATH, DATA_PROCESSED_DIR
from phase_5_model_training import ModelTrainer

print("=" * 70)
print("QUICK TEST: PHASE 5 (Model Training)".center(70))
print("=" * 70)

print(f"\nDataset: {DATASET_MAESTRO_PATH}")
print(f"Exists: {DATASET_MAESTRO_PATH.exists()}")

if not DATASET_MAESTRO_PATH.exists():
    print("Dataset not found. Run main.py (Phase 4) first.")
    sys.exit(1)

print("\nStarting training...")

try:
    trainer = ModelTrainer(dataset_path=DATASET_MAESTRO_PATH)
    success = trainer.train()

    if success:
        print(f"\nTraining completed successfully")
        print(f"  Output: {DATA_PROCESSED_DIR}")
        output_files = list(DATA_PROCESSED_DIR.glob("*.png")) + list(DATA_PROCESSED_DIR.glob("*.pkl"))
        if output_files:
            print(f"  Generated files: {len(output_files)}")
            for f in output_files[:5]:
                print(f"    - {f.name}")
    else:
        print("\nError during training")
        sys.exit(1)

except Exception as e:
    print(f"\nERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 70)
print("PHASE 5 TEST COMPLETED".center(70))
print("=" * 70)
