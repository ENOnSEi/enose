"""
Contrato formal para procesadores de señal.

Cualquier clase que implemente este protocolo puede ser usada como
procesador de señal en el pipeline — sin necesidad de herencia.
Para añadir un nuevo tipo de procesamiento (ej: FFT, wavelet), basta
con implementar estos métodos.
"""

from typing import Optional, Protocol, runtime_checkable, Sequence, Tuple, Dict
import numpy as np


@runtime_checkable
class SignalProcessorProtocol(Protocol):
    """Define la interfaz mínima de un procesador de señal de sensor."""

    sampling_frequency: float

    def smooth_signal(self, signal: np.ndarray) -> np.ndarray:
        """Suaviza la señal cruda para reducir ruido."""
        ...

    def normalize_by_baseline(
        self, signal: np.ndarray, baseline: Optional[Sequence[float]] = None
    ) -> np.ndarray:
        """
        Normaliza por línea base usando cambio fraccional (R0 - Rs) / R0.

        R0 se estima de ``baseline`` (fase 'base' de la grabación) si se aporta;
        en su defecto, de las primeras muestras de la propia señal.
        """
        ...

    def process_signal(
        self, signal: np.ndarray, baseline: Optional[Sequence[float]] = None
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Pipeline completo: suavizado + normalización.
        Retorna (señal_suavizada, señal_normalizada).
        """
        ...

    def extract_features(self, signal: np.ndarray) -> Dict[str, float]:
        """Extrae características estadísticas (max, AUC, slope) por ventana temporal."""
        ...

    def get_signal_segments(self, signal: np.ndarray) -> Dict[str, np.ndarray]:
        """Retorna los segmentos de señal normalizada por ventana (modo PCA)."""
        ...
