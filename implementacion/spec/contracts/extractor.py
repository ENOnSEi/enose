"""
Contratos formales para extractores de características.

HandcraftedExtractorProtocol: extrae estadísticos por ventana (max, AUC, slope).
SignalExtractorProtocol: aprende una proyección (PCA u otra) sobre el conjunto completo
  de muestras y luego transforma cada segmento individualmente.

Para añadir un nuevo extractor (ej: autoencoder, wavelet features), implementa
el protocolo correspondiente sin tocar el pipeline.
"""

from typing import Protocol, runtime_checkable, Dict, List
from pathlib import Path
import numpy as np


@runtime_checkable
class HandcraftedExtractorProtocol(Protocol):
    """
    Extractor de características estadísticas sobre una señal ya procesada.
    No requiere fase de ajuste — las características son deterministas.
    """

    def extract(self, normalized_signal: np.ndarray, sensor_name: str) -> Dict[str, float]:
        """
        Extrae características de una señal normalizada.

        Parámetros
        ----------
        normalized_signal : array de floats, señal post-normalización
        sensor_name       : nombre del sensor (ej: 'v20')

        Retorna
        -------
        dict con claves '{sensor}_{ventana}_{métrica}' → float
        """
        ...


@runtime_checkable
class SignalExtractorProtocol(Protocol):
    """
    Extractor que aprende una proyección sobre el dataset completo (ej: PCA).
    Requiere fit() antes de transform().
    """

    is_fitted: bool

    def fit(self, all_segments: Dict[str, List[np.ndarray]]) -> None:
        """
        Ajusta el extractor sobre todos los segmentos disponibles.

        Parámetros
        ----------
        all_segments : {'{sensor}_{ventana}': [array_muestra_1, array_muestra_2, ...]}
        """
        ...

    def transform(self, segment: np.ndarray, key: str) -> np.ndarray:
        """
        Proyecta un único segmento sobre el espacio aprendido.

        Parámetros
        ----------
        segment : array de floats, segmento de señal normalizada
        key     : clave '{sensor}_{ventana}' para seleccionar el modelo correcto

        Retorna
        -------
        array de scores (PCs u otras proyecciones)
        """
        ...

    def save(self, path: Path) -> None:
        """Persiste el extractor ajustado a disco."""
        ...

    @classmethod
    def load(cls, path: Path) -> "SignalExtractorProtocol":
        """Carga un extractor previamente guardado."""
        ...
