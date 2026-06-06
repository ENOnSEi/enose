#!/usr/bin/env python3
"""
Verifica que todos los módulos del paquete enose importan correctamente.
Ejecutar: python tests/unit/test_imports.py  o  pytest tests/unit/test_imports.py
"""

import sys
from pathlib import Path

_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_root / "src"))
sys.path.insert(0, str(_root))

print("=" * 70)
print("IMPORT DIAGNOSTICS — enose package".center(70))
print("=" * 70)


def test_config_import():
    from enose.config import (
        PROJECT_ROOT, DATA_RAW_DIR, DATASET_MAESTRO_PATH,
        SIGNAL_CONFIG, ML_CONFIG, FEATURE_MODE,
    )
    assert PROJECT_ROOT.exists()
    assert SIGNAL_CONFIG.sampling_frequency == 4.0
    print(f"  [OK] enose.config — FEATURE_MODE={FEATURE_MODE}")


def test_utils_import():
    from enose.utils import setup_logging, validate_sensor_data, create_output_directory
    print("  [OK] enose.utils")


def test_io_import():
    from enose.io.reader import load_sensor_file, get_files_recursive, extract_substance_label
    assert extract_substance_label("vino.csv") == "Vino"
    assert extract_substance_label("vinoyagua.csv") == "Vino+Agua"
    assert extract_substance_label("vinoagitacionrara.csv") == "Vino+Alcohol"
    assert extract_substance_label("mezcla_nueva.csv") == "mezcla_nueva"  # fallback
    print("  [OK] enose.io.reader")


def test_signal_import():
    from enose.signal.processor import SignalProcessor
    p = SignalProcessor()
    assert p.sampling_frequency == 4.0
    assert p.savgol_window % 2 != 0
    print(f"  [OK] enose.signal.processor — window={p.savgol_window}")


def test_features_import():
    from enose.features.pca import PCAFeatureExtractor
    from enose.features.handcrafted import HandcraftedExtractor
    pca = PCAFeatureExtractor()
    assert not pca.is_fitted
    print("  [OK] enose.features.pca + handcrafted")


def test_pipeline_import():
    from enose.pipeline.dataset import DatasetGenerator, load_dataset, validate_dataset
    print("  [OK] enose.pipeline.dataset")


def test_model_import():
    from enose.model.trainer import ModelTrainer
    print("  [OK] enose.model.trainer")


def test_spec_import():
    from spec.contracts import SignalProcessorProtocol, SignalExtractorProtocol, ClassifierProtocol
    from spec.schemas import SensorReading, FeatureVector, Prediction
    print("  [OK] spec.contracts + spec.schemas")


if __name__ == "__main__":
    tests = [
        test_config_import,
        test_utils_import,
        test_io_import,
        test_signal_import,
        test_features_import,
        test_pipeline_import,
        test_model_import,
        test_spec_import,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"  [ERROR] {t.__name__}: {e}")
            import traceback; traceback.print_exc()
            failed += 1

    print("\n" + "=" * 70)
    if failed == 0:
        print("ALL IMPORTS OK — PIPELINE READY".center(70))
    else:
        print(f"{failed} test(s) FAILED".center(70))
        sys.exit(1)
    print("=" * 70)
