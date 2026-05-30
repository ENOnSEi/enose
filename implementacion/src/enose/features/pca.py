"""
Extractor de características basado en PCA por combinación (sensor × ventana).

Implementa SignalExtractorProtocol (spec/contracts/extractor.py).
Para sustituirlo por otro método de reducción dimensional (autoencoder, UMAP, etc.),
basta con implementar el protocolo y actualizar FEATURE_MODE en config.py.
"""

import pickle
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from sklearn.decomposition import PCA

from enose.config import PCA_CONFIG, PCAConfig
from enose.utils import setup_logging

logger = setup_logging(__name__)


class PCAFeatureExtractor:
    """
    Ajusta un PCA independiente por cada clave '{sensor}_{ventana}'.
    Implementa SignalExtractorProtocol.
    """

    def __init__(self, config: Optional[PCAConfig] = None) -> None:
        cfg = config or PCA_CONFIG
        self.n_components = cfg.n_components
        self.explained_variance_threshold = cfg.explained_variance_threshold
        self.whiten = cfg.whiten
        self.pca_models: Dict[str, PCA] = {}
        self.segment_lengths: Dict[str, int] = {}
        self.is_fitted = False

    # ------------------------------------------------------------------
    # Protocolo público
    # ------------------------------------------------------------------

    def fit(self, all_segments: Dict[str, List[np.ndarray]]) -> None:
        """
        Ajusta un PCA por clave sobre la colección completa de segmentos.

        Parámetros
        ----------
        all_segments : {'{sensor}_{ventana}': [array_muestra_1, ...]}
        """
        for key, segments in all_segments.items():
            lengths = [len(s) for s in segments]
            fixed_len = max(set(lengths), key=lengths.count)
            self.segment_lengths[key] = fixed_len

            X = np.array([self._pad_truncate(s, fixed_len) for s in segments])
            n_comp = self.n_components if self.n_components is not None else self.explained_variance_threshold
            n_comp = min(n_comp, *X.shape) if isinstance(n_comp, int) else n_comp

            pca = PCA(n_components=n_comp, whiten=self.whiten)
            pca.fit(X)
            self.pca_models[key] = pca

        self.is_fitted = True
        logger.info(f"PCA ajustado: {len(self.pca_models)} modelos")

    def transform(self, segment: np.ndarray, key: str) -> np.ndarray:
        """Proyecta un segmento sobre los PCs del modelo correspondiente."""
        pca = self.pca_models[key]
        padded = self._pad_truncate(segment, self.segment_lengths[key])
        return pca.transform(padded.reshape(1, -1))[0]

    def save(self, path: Path) -> None:
        with open(path, "wb") as f:
            pickle.dump({"pca_models": self.pca_models, "segment_lengths": self.segment_lengths}, f)
        logger.info(f"PCA guardado en: {path}")

    @classmethod
    def load(cls, path: Path, config: Optional[PCAConfig] = None) -> "PCAFeatureExtractor":
        extractor = cls(config)
        with open(path, "rb") as f:
            data = pickle.load(f)
        extractor.pca_models = data["pca_models"]
        extractor.segment_lengths = data["segment_lengths"]
        extractor.is_fitted = True
        return extractor

    # ------------------------------------------------------------------
    # Diagnóstico
    # ------------------------------------------------------------------

    def explained_variance_summary(self) -> Dict[str, np.ndarray]:
        return {key: pca.explained_variance_ratio_ for key, pca in self.pca_models.items()}

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _pad_truncate(self, signal: np.ndarray, length: int) -> np.ndarray:
        if len(signal) >= length:
            return signal[:length]
        pad_value = signal[-1] if len(signal) > 0 else 0.0
        return np.concatenate([signal, np.full(length - len(signal), pad_value)])
