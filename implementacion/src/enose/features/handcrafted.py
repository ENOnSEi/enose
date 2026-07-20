"""
Extractor de características estadísticas (handcrafted).

Implementa HandcraftedExtractorProtocol (spec/contracts/extractor.py).
Calcula max, AUC y slope por ventana temporal sobre la señal normalizada.
No requiere fase de ajuste — las características son deterministas.
"""

from typing import Dict, Optional, Sequence

import numpy as np
import pandas as pd

from enose.config import SENSOR_COLUMNS, SENSOR_RATIO_PAIRS, SignalConfig
from enose.io.reader import get_baseline_and_signal
from enose.signal.processor import SignalProcessor
from enose.utils import setup_logging

logger = setup_logging(__name__)


class HandcraftedExtractor:
    """
    Wrapper sobre SignalProcessor para el modo handcrafted.
    Implementa HandcraftedExtractorProtocol.
    """

    def __init__(self, config: Optional[SignalConfig] = None) -> None:
        self._processor = SignalProcessor(config)

    def extract(self, normalized_signal: np.ndarray, sensor_name: str) -> Dict[str, float]:
        """
        Extrae max, AUC y slope por ventana temporal.
        Las claves resultantes tienen formato '{sensor}_{ventana}_{métrica}'.
        """
        raw_features = self._processor.extract_features(normalized_signal)
        return {f"{sensor_name}_{k}": v for k, v in raw_features.items()}

    def extract_ratios(
        self, normalized_signals: Dict[str, np.ndarray],
        ratio_pairs: Optional[Sequence] = None,
    ) -> Dict[str, float]:
        """
        Calcula ratios entre pares de sensores por ventana temporal.

        Los ratios cancelan la intensidad global y capturan la composición
        relativa del gas — la "huella química" de la sustancia.
        """
        if ratio_pairs is None:
            ratio_pairs = SENSOR_RATIO_PAIRS

        features: Dict[str, float] = {}
        for s_a, s_b in ratio_pairs:
            if s_a not in normalized_signals or s_b not in normalized_signals:
                continue
            sig_a = normalized_signals[s_a]
            sig_b = normalized_signals[s_b]
            min_len = min(len(sig_a), len(sig_b))
            if min_len == 0:
                continue

            for start_sec, end_sec in self._processor.time_windows:
                freq = self._processor.sampling_frequency
                total_sec = min_len / freq
                if start_sec >= total_sec:
                    continue
                i0 = max(0, min(int(start_sec * freq), min_len - 1))
                i1 = max(0, min(int(end_sec * freq), min_len))
                seg_a = sig_a[i0:i1]
                seg_b = sig_b[i0:i1]
                if len(seg_a) == 0:
                    continue

                max_a = float(np.max(np.abs(seg_a)))
                max_b = float(np.max(np.abs(seg_b)))
                auc_a = float(np.trapezoid(np.abs(seg_a), dx=1.0 / freq))
                auc_b = float(np.trapezoid(np.abs(seg_b), dx=1.0 / freq))

                label = f"w{int(start_sec)}-{int(end_sec)}"
                tag = f"r_{s_a}_{s_b}_{label}"
                features[f"{tag}_max"] = max_a / (max_b + 1e-10)
                features[f"{tag}_auc"] = auc_a / (auc_b + 1e-10)

        return features

    def extract_from_file_data(self, df: pd.DataFrame, sensor_cols=None) -> Dict[str, float]:
        """
        Extrae características de todos los sensores en una grabación.

        Entrada: DataFrame crudo de la grabación CSV (columnas data, v20, v11,
        v02, v00, estado). Por cada sensor se toma R0 de la fase 'base' y la
        respuesta de la fase 'medicion'.
        """
        if sensor_cols is None:
            sensor_cols = SENSOR_COLUMNS["sensors"]

        result: Dict[str, float] = {}
        normalized_signals: Dict[str, np.ndarray] = {}
        for sensor in sensor_cols:
            pair = get_baseline_and_signal(df, sensor)
            if pair is None:
                continue
            baseline, signal = pair
            _, normalized = self._processor.process_signal(signal, baseline)
            result.update(self.extract(normalized, sensor))
            normalized_signals[sensor] = normalized

        result.update(self.extract_ratios(normalized_signals))
        return result
