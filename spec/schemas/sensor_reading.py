"""
Schema de entrada del pipeline: una lectura cruda de un archivo de sensor.

Valida automáticamente que los datos sean coherentes antes de que
entren al procesamiento de señal. Esto captura errores en la frontera
del sistema (ingesta de datos) en lugar de dentro del pipeline.
"""

from typing import Dict, List
from pydantic import BaseModel, field_validator


VALID_LABELS = {"AQ", "HQ", "LQ", "ETH"}
EXPECTED_SENSORS = {"MQ3_1", "MQ4_1", "MQ6_1", "MQ3_2", "MQ4_2", "MQ6_2"}


class SensorReading(BaseModel):
    """Representa la lectura completa de un archivo de sensor (.txt)."""

    filename: str
    substance_label: str
    sensor_data: Dict[str, List[float]]  # sensor_name -> serie temporal
    humidity: List[float] = []
    temperature: List[float] = []

    model_config = {"frozen": True}

    @field_validator("substance_label")
    @classmethod
    def validate_label(cls, v: str) -> str:
        if v not in VALID_LABELS:
            raise ValueError(f"substance_label debe ser uno de {VALID_LABELS}, recibido: '{v}'")
        return v

    @field_validator("sensor_data")
    @classmethod
    def validate_sensors(cls, v: Dict[str, List[float]]) -> Dict[str, List[float]]:
        missing = EXPECTED_SENSORS - v.keys()
        if missing:
            raise ValueError(f"Faltan sensores en sensor_data: {missing}")
        return v

    @property
    def n_samples(self) -> int:
        first_key = next(iter(self.sensor_data))
        return len(self.sensor_data[first_key])
