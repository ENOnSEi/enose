#!/usr/bin/env python3
"""
Test de entrenamiento completo (Phase 5) sobre el dataset existente.
Ejecutar: python tests/unit/test_phase5.py
Requiere: haber generado el dataset con main.py --phase 4
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from enose.config import DATA_PROCESSED_DIR, DATASET_MAESTRO_PATH
from enose.model.trainer import ModelTrainer

print("=" * 70)
print("QUICK TEST: Phase 5 — Model Training".center(70))
print("=" * 70)
print(f"\nDataset: {DATASET_MAESTRO_PATH}")
print(f"Existe:  {DATASET_MAESTRO_PATH.exists()}")

if not DATASET_MAESTRO_PATH.exists():
    # skip (no sys.exit): un exit al importar tumba la recogida de toda la suite
    pytest.skip("Dataset no encontrado. Ejecuta: python main.py --phase 4",
                allow_module_level=True)


def test_model_training():
    trainer = ModelTrainer(dataset_path=DATASET_MAESTRO_PATH)
    success = trainer.train()
    assert success, "ModelTrainer.train() retornó False"

    # Verificar artefactos generados
    assert (DATA_PROCESSED_DIR / "best_model.pkl").exists()
    assert (DATA_PROCESSED_DIR / "training_results.pkl").exists()
    print(f"\n  [OK] Modelo guardado en {DATA_PROCESSED_DIR}")


if __name__ == "__main__":
    try:
        test_model_training()
        print("\n" + "=" * 70)
        print("PHASE 5 TEST COMPLETED".center(70))
        print("=" * 70)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)
