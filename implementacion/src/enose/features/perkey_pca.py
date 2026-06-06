"""
Transformer PCA por (sensor × ventana) integrable en un Pipeline de sklearn.

A diferencia de PCAFeatureExtractor (que ajustaba el PCA sobre TODO el dataset
en la Fase 4, provocando data leakage hacia el conjunto de test), PerKeyPCA se
ajusta DENTRO del Pipeline de entrenamiento. Así el PCA solo ve los datos de
entrenamiento en cada fold de la validación cruzada y en el split final
train/test, eliminando la fuga de datos.

Entrada esperada (fit/transform): un DataFrame cuyas columnas siguen el patrón
'{sensor}_{ventana}__t{idx}', es decir, las muestras crudas de cada segmento ya
recortadas/rellenadas a longitud fija por la Fase 4 (ver pipeline/dataset.py).
"""

from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.decomposition import PCA

from enose.config import PCA_CONFIG, PCAConfig
from enose.utils import setup_logging

logger = setup_logging(__name__)

# Separador entre la clave '{sensor}_{ventana}' y el índice temporal de la muestra.
SEGMENT_COL_SEP = "__t"


class PerKeyPCA(BaseEstimator, TransformerMixin):
    """
    Ajusta un PCA independiente por cada clave '{sensor}_{ventana}'.

    Compatible con la API de sklearn (fit/transform/clone), por lo que puede
    colocarse como primer paso de un Pipeline y se reajusta automáticamente
    solo sobre los datos de entrenamiento de cada fold.
    """

    def __init__(self, config: Optional[PCAConfig] = None) -> None:
        # sklearn clona los estimadores leyendo los atributos tal cual se reciben
        # en __init__; por eso NO se transforma 'config' aquí.
        self.config = config

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    @staticmethod
    def _key_of(column: str) -> str:
        """'v20_w0-5__t007' -> 'v20_w0-5'."""
        return column.split(SEGMENT_COL_SEP)[0]

    def _resolve_config(self) -> PCAConfig:
        return self.config or PCA_CONFIG

    def _group_columns(self, columns: List[str]) -> Dict[str, List[str]]:
        groups: Dict[str, List[str]] = {}
        for col in columns:
            groups.setdefault(self._key_of(col), []).append(col)
        return groups

    # ------------------------------------------------------------------
    # API sklearn
    # ------------------------------------------------------------------

    def fit(self, X: pd.DataFrame, y=None) -> "PerKeyPCA":
        if not isinstance(X, pd.DataFrame):
            raise TypeError(
                "PerKeyPCA requiere un DataFrame con columnas '{sensor}_{ventana}__t{idx}'."
            )

        cfg = self._resolve_config()
        self.columns_ = list(X.columns)
        self.groups_ = self._group_columns(self.columns_)
        self.pca_models_: Dict[str, PCA] = {}

        n_samples = X.shape[0]
        for key, cols in self.groups_.items():
            block = X[cols].to_numpy()
            n_feat = block.shape[1]

            n_comp = cfg.n_components if cfg.n_components is not None else cfg.explained_variance_threshold
            if isinstance(n_comp, int):
                n_comp = min(n_comp, n_samples, n_feat)
            # Si es un float (umbral de varianza), sklearn elige el nº de componentes.

            pca = PCA(n_components=n_comp, whiten=cfg.whiten)
            pca.fit(block)
            self.pca_models_[key] = pca

        self.is_fitted_ = True
        logger.info(
            f"PerKeyPCA ajustado: {len(self.pca_models_)} modelos "
            f"sobre {n_samples} muestras de entrenamiento"
        )
        return self

    def transform(self, X: pd.DataFrame) -> np.ndarray:
        if not getattr(self, "is_fitted_", False):
            raise RuntimeError("PerKeyPCA no está ajustado. Llama a fit() primero.")

        projections = [self.pca_models_[key].transform(X[cols].to_numpy())
                       for key, cols in self.groups_.items()]
        return np.hstack(projections)

    def get_feature_names_out(self, input_features=None) -> np.ndarray:
        names: List[str] = []
        for key, pca in self.pca_models_.items():
            names.extend(f"{key}_pc{i + 1}" for i in range(pca.n_components_))
        return np.asarray(names, dtype=object)

    # ------------------------------------------------------------------
    # Diagnóstico
    # ------------------------------------------------------------------

    def explained_variance_summary(self) -> Dict[str, np.ndarray]:
        return {key: pca.explained_variance_ratio_ for key, pca in self.pca_models_.items()}
