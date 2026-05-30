"""
Tests de contrato para SignalProcessorProtocol.

Verifican que cualquier implementación de SignalProcessorProtocol
cumple la interfaz definida en spec/contracts/processor.py.
Añade nuevas implementaciones de procesador aquí y hereda de TestSignalProcessorContract.
"""

import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from enose.signal.processor import SignalProcessor
from spec.contracts.processor import SignalProcessorProtocol


class TestSignalProcessorContract:
    """Suite de contrato — reutilizable para cualquier implementación."""

    @pytest.fixture
    def processor(self):
        return SignalProcessor()

    @pytest.fixture
    def sample_signal(self) -> np.ndarray:
        rng = np.random.default_rng(42)
        return rng.random(370).astype(np.float64) * 10 + 150

    def test_implements_protocol(self, processor):
        assert isinstance(processor, SignalProcessorProtocol), (
            "SignalProcessor no cumple SignalProcessorProtocol"
        )

    def test_smooth_signal_preserves_length(self, processor, sample_signal):
        smoothed = processor.smooth_signal(sample_signal)
        assert len(smoothed) == len(sample_signal)

    def test_normalize_output_is_finite(self, processor, sample_signal):
        normalized = processor.normalize_by_baseline(sample_signal)
        assert np.all(np.isfinite(normalized)), "normalize_by_baseline produjo NaN o inf"

    def test_process_signal_returns_two_arrays(self, processor, sample_signal):
        smoothed, normalized = processor.process_signal(sample_signal)
        assert len(smoothed) == len(sample_signal)
        assert len(normalized) == len(sample_signal)

    def test_extract_features_returns_dict_of_floats(self, processor, sample_signal):
        _, normalized = processor.process_signal(sample_signal)
        features = processor.extract_features(normalized)
        assert isinstance(features, dict)
        assert len(features) > 0
        assert all(isinstance(v, float) for v in features.values())

    def test_get_signal_segments_non_empty(self, processor, sample_signal):
        _, normalized = processor.process_signal(sample_signal)
        segments = processor.get_signal_segments(normalized)
        assert isinstance(segments, dict)
        assert len(segments) > 0
        assert all(isinstance(v, np.ndarray) for v in segments.values())
