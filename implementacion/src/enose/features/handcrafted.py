"""
Extractor de características estadísticas (handcrafted).

Implementa HandcraftedExtractorProtocol (spec/contracts/extractor.py).
Calcula max, AUC y slope por ventana temporal sobre la señal normalizada.
No requiere fase de ajuste — las características son deterministas.
"""

from typing import Dict, Optional, Sequence

import numpy as np
import pandas as pd

from enose.config import SENSOR_COLUMNS, SignalConfig
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
        for sensor in sensor_cols:
            pair = get_baseline_and_signal(df, sensor)
            if pair is None:
                continue
            baseline, signal = pair
            _, normalized = self._processor.process_signal(signal, baseline)
            result.update(self.extract(normalized, sensor))
        return result
