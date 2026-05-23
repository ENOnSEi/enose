#!/usr/bin/env python3
"""
Test rápido de la Fase 5 (Model Training) V2
"""

import sys
from pathlib import Path

# Agregar src al path
src_dir = Path(__file__).parent
sys.path.insert(0, str(src_dir))

from config import DATASET_MAESTRO_PATH, DATA_PROCESSED_DIR
from phase_5_model_trainingV2 import ModelTrainer

print("=" * 70)
print("TEST RÁPIDO: FASE 5 (Model Training) V2".center(70))
print("=" * 70)

print(f"\n📂 Dataset maestro: {DATASET_MAESTRO_PATH}")
print(f"   Existe: {DATASET_MAESTRO_PATH.exists()}")

if not DATASET_MAESTRO_PATH.exists():
    print("✗ Dataset maestro no encontrado")
    sys.exit(1)

print(f"\n🚀 Iniciando entrenamiento...")

try:
    trainer = ModelTrainer(dataset_path=DATASET_MAESTRO_PATH)
    success = trainer.train()
    
    if success:
        print(f"\n✓ Entrenamiento completado exitosamente")
        print(f"  - Output: {DATA_PROCESSED_DIR}")
        output_files = list(DATA_PROCESSED_DIR.glob("*.png")) + list(DATA_PROCESSED_DIR.glob("*.pkl"))
        if output_files:
            print(f"  - Archivos generados: {len(output_files)}")
            for f in output_files[:5]:
                print(f"    • {f.name}")
    else:
        print(f"\n✗ Error al entrenar modelo")
        sys.exit(1)
        
except Exception as e:
    print(f"\n✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 70)
print("✓ TEST FASE 5 COMPLETADO".center(70))
print("=" * 70)
