"""
Tests de contrato para SignalExtractorProtocol (PCAFeatureExtractor).

Verifican que la implementación sigue el contrato definido en
spec/contracts/extractor.py. Para añadir un nuevo extractor, añade
su fixture aquí y hereda de la misma suite.
"""

import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from enose.features.pca import PCAFeatureExtractor
from spec.contracts.extractor import SignalExtractorProtocol


@pytest.fixture
def synthetic_segments():
    """Genera segmentos sintéticos para 2 combinaciones sensor×ventana."""
    rng = np.random.default_rng(0)
    return {
        "MQ3_1_w2-10": [rng.random(148) for _ in range(30)],
        "MQ4_1_w2-10": [rng.random(148) for _ in range(30)],
    }


class TestPCAExtractorContract:

    @pytest.fixture
    def fitted_extractor(self, synthetic_segments):
        ext = PCAFeatureExtractor()
        ext.fit(synthetic_segments)
        return ext

    def test_implements_protocol(self, fitted_extractor):
        assert isinstance(fitted_extractor, SignalExtractorProtocol), (
            "PCAFeatureExtractor no cumple SignalExtractorProtocol"
        )

    def test_is_fitted_after_fit(self, fitted_extractor):
        assert fitted_extractor.is_fitted

    def test_transform_returns_array(self, fitted_extractor, synthetic_segments):
        key = next(iter(synthetic_segments))
        segment = synthetic_segments[key][0]
        result = fitted_extractor.transform(segment, key)
        assert isinstance(result, np.ndarray)
        assert result.ndim == 1

    def test_save_load_roundtrip(self, fitted_extractor, tmp_path, synthetic_segments):
        path = tmp_path / "pca_test.pkl"
        fitted_extractor.save(path)
        loaded = PCAFeatureExtractor.load(path)
        assert loaded.is_fitted

        key = next(iter(synthetic_segments))
        segment = synthetic_segments[key][0]
        original = fitted_extractor.transform(segment, key)
        restored = loaded.transform(segment, key)
        np.testing.assert_array_almost_equal(original, restored)
