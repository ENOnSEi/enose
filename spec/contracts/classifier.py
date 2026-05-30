"""
Contrato formal para clasificadores del pipeline.

El pipeline de entrenamiento y predicción solo depende de este protocolo,
no de sklearn.SVC directamente. Esto permite sustituir el clasificador
(ej: RandomForest, red neuronal, XGBoost) sin cambiar el orquestador.
"""

from typing import Protocol, runtime_checkable, Optional
from pathlib import Path
import numpy as np


@runtime_checkable
class ClassifierProtocol(Protocol):
    """Interfaz mínima para un clasificador entrenado."""

    classes_: np.ndarray

    def fit(self, X: np.ndarray, y: np.ndarray) -> "ClassifierProtocol":
        """Entrena el clasificador."""
        ...

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predice la clase para cada muestra."""
        ...

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        Retorna probabilidades por clase para cada muestra.
        Shape: (n_samples, n_classes).
        """
        ...

    def score(self, X: np.ndarray, y: np.ndarray) -> float:
        """Accuracy media sobre el conjunto dado."""
        ...
