"""
Extractor de características estadísticas (handcrafted).

Implementa HandcraftedExtractorProtocol (spec/contracts/extractor.py).
Calcula max, AUC y slope por ventana temporal sobre la señal normalizada.
No requiere fase de ajuste — las características son deterministas.
"""

from typing import Dict, Optional

import numpy as np

from enose.config import SENSOR_COLUMNS, SignalConfig
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

    def extract_from_file_data(self, df, sensor_cols=None) -> Dict[str, float]:
        """
        Extrae características de todos los sensores en un DataFrame de sensor.
        Entrada: DataFrame crudo del archivo .txt.
        """
        if sensor_cols is None:
            sensor_cols = SENSOR_COLUMNS["sensors"]

        result: Dict[str, float] = {}
        for sensor in sensor_cols:
            if sensor not in df.columns:
                continue
            raw = df[sensor].values
            _, normalized = self._processor.process_signal(raw)
            features = self.extract(normalized, sensor)
            result.update(features)
        return result
