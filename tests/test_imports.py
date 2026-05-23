#!/usr/bin/env python3
"""
Diagnostic script to verify all module imports work correctly.
Run from the project root: python tests/test_imports.py
"""

import sys
from pathlib import Path

src_dir = Path(__file__).parent.parent / 'src'
sys.path.insert(0, str(src_dir))

print("=" * 70)
print("IMPORT DIAGNOSTICS".center(70))
print("=" * 70)

# Test 1: Config
print("\n[1/5] Importing config...")
try:
    from config import (
        PROJECT_ROOT, DATA_RAW_DIR, SIGNAL_PROCESSING_V2,
        ML_CONFIG, GRID_PARAMS
    )
    print("  OK config.py")
    print(f"    - PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"    - Sampling freq: {SIGNAL_PROCESSING_V2['sampling_frequency']} Hz")
except Exception as e:
    print(f"  ERROR: {e}")
    sys.exit(1)

# Test 2: Utils
print("\n[2/5] Importing utils...")
try:
    from utils import (
        setup_logging, get_files_recursive, extract_substance_label,
        plot_signal_processing, create_output_directory
    )
    print("  OK utils.py")
except Exception as e:
    print(f"  ERROR: {e}")
    sys.exit(1)

# Test 3: Phase 1-3
print("\n[3/5] Importing phase_1_3_feature_extraction...")
try:
    from phase_1_3_feature_extraction import SignalProcessor, extract_features_from_file
    print("  OK phase_1_3_feature_extraction.py")
    processor = SignalProcessor()
    print(f"    - Savgol window: {processor.savgol_window}")
    print(f"    - Baseline samples: {processor.baseline_samples}")
except Exception as e:
    print(f"  ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Phase 4
print("\n[4/5] Importing phase_4_dataset_generation...")
try:
    from phase_4_dataset_generation import DatasetGenerator, load_dataset, validate_dataset
    print("  OK phase_4_dataset_generation.py")
except Exception as e:
    print(f"  ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: Phase 5
print("\n[5/5] Importing phase_5_model_training...")
try:
    from phase_5_model_training import ModelTrainer
    print("  OK phase_5_model_training.py")
except Exception as e:
    print(f"  ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 70)
print("ALL IMPORTS OK - PIPELINE READY".center(70))
print("=" * 70)
