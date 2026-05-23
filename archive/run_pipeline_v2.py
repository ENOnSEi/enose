#!/usr/bin/env python3
"""
Script para ejecutar el pipeline completo V2 de una sola vez.
Permite validar que todos los módulos funcionan juntos correctamente.
"""

import sys
from pathlib import Path

# Agregar src al path
src_dir = Path(__file__).parent
sys.path.insert(0, str(src_dir))

from config import PROJECT_ROOT, DATA_RAW_DIR, DATASET_MAESTRO_PATH, DATA_PROCESSED_DIR
from phase_4_dataset_generationV2 import DatasetGenerator
from phase_5_model_trainingV2 import ModelTrainer

print("=" * 80)
print("PIPELINE COMPLETO V2 - NARIZ ELECTRÓNICA".center(80))
print("=" * 80)

print(f"\n📁 Rutas del proyecto:")
print(f"  - Raíz: {PROJECT_ROOT}")
print(f"  - Datos (raw): {DATA_RAW_DIR}")
print(f"  - Dataset maestro: {DATASET_MAESTRO_PATH}")
print(f"  - Datos procesados: {DATA_PROCESSED_DIR}")

# ============================================================================
# FASE 4: Generar Dataset
# ============================================================================
print("\n" + "=" * 80)
print("FASE 4: Generando Dataset Maestro".center(80))
print("=" * 80)

try:
    generator = DatasetGenerator(data_dir=DATA_RAW_DIR)
    df = generator.generate_dataset(output_path=DATASET_MAESTRO_PATH)
    
    if df is not None:
        print(f"\n✓ Dataset generado exitosamente")
        print(f"  - Shape: {df.shape}")
        print(f"  - Columnas: {list(df.columns)[:5]}...")
        print(f"  - Archivo: {DATASET_MAESTRO_PATH}")
    else:
        print("\n✗ Error al generar dataset")
        sys.exit(1)
        
except Exception as e:
    print(f"\n✗ ERROR en Fase 4: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ============================================================================
# FASE 5: Entrenar Modelo
# ============================================================================
print("\n" + "=" * 80)
print("FASE 5: Entrenando Modelo ML".center(80))
print("=" * 80)

try:
    trainer = ModelTrainer(dataset_path=DATASET_MAESTRO_PATH)
    success = trainer.train()
    
    if success:
        print(f"\n✓ Modelo entrenado exitosamente")
        print(f"  - Dataset path: {DATASET_MAESTRO_PATH}")
        print(f"  - Output: {DATA_PROCESSED_DIR}")
    else:
        print("\n✗ Error al entrenar modelo")
        sys.exit(1)
        
except Exception as e:
    print(f"\n✗ ERROR en Fase 5: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 80)
print("✓ PIPELINE V2 COMPLETADO EXITOSAMENTE".center(80))
print("=" * 80)
