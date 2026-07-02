"""
Procesador de señal de sensor.

Implementa SignalProcessorProtocol (spec/contracts/processor.py):
  - Suavizado Savitzky-Golay
  - Normalización por línea base (Rs - R0) / R0, donde R0 sale de la fase 'base'
    de la grabación (aire limpio) y Rs es la lectura ADC de la fase 'medicion'.
  - Extracción de características por ventana temporal (modo handcrafted)
  - Segmentación de señal normalizada por ventana (modo PCA)
"""

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.signal import savgol_filter

from enose.config import SIGNAL_CONFIG, SignalConfig
from enose.utils import setup_logging

logger = setup_logging(__name__)


class SignalProcessor:
    """
    Procesador de señal para los sensores TGS de la nariz electrónica.

    Conforme a SignalProcessorProtocol — se puede sustituir por cualquier
    clase que implemente el mismo protocolo sin tocar el pipeline.
    """

    def __init__(self, config: Optional[SignalConfig] = None) -> None:
        cfg = config or SIGNAL_CONFIG
        self.sampling_frequency = cfg.sampling_frequency
        self.savgol_window = cfg.savgol_window if cfg.savgol_window % 2 != 0 else cfg.savgol_window + 1
        self.savgol_polyorder = cfg.savgol_polyorder
        self.baseline_seconds = cfg.baseline_seconds
        self.time_windows: List[Tuple[float, float]] = list(cfg.time_windows)

        self.dt = 1.0 / self.sampling_frequency
        self.baseline_samples = int(self.baseline_seconds * self.sampling_frequency)

    # ------------------------------------------------------------------
    # Protocolo público
    # ------------------------------------------------------------------

    def smooth_signal(self, signal: np.ndarray) -> np.ndarray:
        signal = np.asarray(signal, dtype=float)
        if len(signal) < self.savgol_window or len(signal) <= self.savgol_polyorder:
            logger.warning("Señal demasiado corta para Savitzky-Golay. Devolviendo original.")
            return signal
        return savgol_filter(signal, window_length=self.savgol_window, polyorder=self.savgol_polyorder)

    def normalize_by_baseline(
        self, signal: np.ndarray, baseline: Optional[Sequence[float]] = None
    ) -> np.ndarray:
        """
        Normalización fraccional: (Rs - R0) / R0.

        R0 (lectura ADC en aire limpio) se estima como:
          - la media de ``baseline`` (fase 'base' de la grabación), si se aporta;
          - si no, la media de las primeras ``baseline_samples`` muestras de la
            propia señal (fallback para grabaciones sin fase 'base').
        """
        signal = np.asarray(signal, dtype=float)
        if baseline is not None and len(baseline) > 0:
            R0 = float(np.mean(np.asarray(baseline, dtype=float)))
        else:
            n = len(signal) if len(signal) < self.baseline_samples else self.baseline_samples
            n = max(n, 1)
            R0 = float(np.mean(signal[:n]))

        if R0 == 0:
            logger.warning("R0 = 0. Usando Z-score como normalización de respaldo.")
            return (signal - np.mean(signal)) / (np.std(signal) + 1e-10)
        return (signal - R0) / R0

    def process_signal(
        self, signal: np.ndarray, baseline: Optional[Sequence[float]] = None
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Retorna (señal_suavizada, señal_normalizada)."""
        smoothed = self.smooth_signal(signal)
        normalized = self.normalize_by_baseline(smoothed, baseline)
        return smoothed, normalized

    def extract_features(self, signal: np.ndarray) -> Dict[str, float]:
        """Extrae max, AUC y slope por cada ventana temporal (modo handcrafted)."""
        signal = np.asarray(signal, dtype=float)
        features: Dict[str, float] = {}
        total_sec = len(signal) * self.dt

        for start_sec, end_sec in self.time_windows:
            if start_sec >= total_sec:
                continue
            start = max(0, min(int(start_sec * self.sampling_frequency), len(signal) - 1))
            end = max(0, min(int(end_sec * self.sampling_frequency), len(signal)))
            seg = signal[start:end]
            if len(seg) == 0:
                continue

            label = f"w{int(start_sec)}-{int(end_sec)}"
            features[f"{label}_max"] = float(np.max(seg))
            features[f"{label}_auc"] = float(np.trapezoid(seg, dx=self.dt))
            features[f"{label}_slope"] = float(np.max(np.abs(np.diff(seg) / self.dt))) if len(seg) > 1 else 0.0

        return features

    def get_signal_segments(self, signal: np.ndarray) -> Dict[str, np.ndarray]:
        """Retorna los arrays de señal por ventana (modo PCA)."""
        signal = np.asarray(signal, dtype=float)
        segments: Dict[str, np.ndarray] = {}
        total_sec = len(signal) * self.dt

        for start_sec, end_sec in self.time_windows:
            if start_sec >= total_sec:
                continue
            start = max(0, min(int(start_sec * self.sampling_frequency), len(signal) - 1))
            end = max(0, min(int(end_sec * self.sampling_frequency), len(signal)))
            seg = signal[start:end]
            if len(seg) > 0:
                segments[f"w{int(start_sec)}-{int(end_sec)}"] = seg

        return segments
