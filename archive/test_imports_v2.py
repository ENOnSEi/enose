#!/usr/bin/env python3
"""
Script de diagnóstico para verificar imports V2
"""

import sys
from pathlib import Path

# Agregar src al path
src_dir = Path(__file__).parent
sys.path.insert(0, str(src_dir))

print("=" * 70)
print("DIAGNÓSTICO DE IMPORTS - V2".center(70))
print("=" * 70)

# Test 1: Config
print("\n[1/5] Importando config...")
try:
    from config import (
        PROJECT_ROOT, DATA_RAW_DIR, SIGNAL_PROCESSING_V2, 
        ML_CONFIG, GRID_PARAMS
    )
    print("  ✓ config.py OK")
    print(f"    - PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"    - Sampling freq V2: {SIGNAL_PROCESSING_V2['sampling_frequency']} Hz")
except Exception as e:
    print(f"  ✗ ERROR: {e}")
    sys.exit(1)

# Test 2: Utils
print("\n[2/5] Importando utils...")
try:
    from utils import (
        setup_logging, get_files_recursive, extract_substance_label,
        plot_signal_processing, create_output_directory
    )
    print("  ✓ utils.py OK")
except Exception as e:
    print(f"  ✗ ERROR: {e}")
    sys.exit(1)

# Test 3: Phase 1-3 V2
print("\n[3/5] Importando phase_1_3_feature_extractionV2...")
try:
    from phase_1_3_feature_extractionV2 import SignalProcessor, extract_features_from_file
    print("  ✓ phase_1_3_feature_extractionV2.py OK")
    
    # Crear instancia
    processor = SignalProcessor()
    print(f"    - Savgol window: {processor.savgol_window}")
    print(f"    - Baseline samples: {processor.baseline_samples}")
except Exception as e:
    print(f"  ✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Phase 4 V2
print("\n[4/5] Importando phase_4_dataset_generationV2...")
try:
    from phase_4_dataset_generationV2 import DatasetGenerator, load_dataset, validate_dataset
    print("  ✓ phase_4_dataset_generationV2.py OK")
except Exception as e:
    print(f"  ✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: Phase 5 V2
print("\n[5/5] Importando phase_5_model_trainingV2...")
try:
    from phase_5_model_trainingV2 import ModelTrainer
    print("  ✓ phase_5_model_trainingV2.py OK")
except Exception as e:
    print(f"  ✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 70)
print("✓ TODOS LOS IMPORTS OK - V2 LISTA PARA EJECUTAR".center(70))
print("=" * 70)
