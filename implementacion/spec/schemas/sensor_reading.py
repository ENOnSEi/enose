"""
Schema de entrada del pipeline: una grabación cruda del serial-reader.

Valida automáticamente que los datos sean coherentes antes de que
entren al procesamiento de señal. Esto captura errores en la frontera
del sistema (ingesta de datos) en lugar de dentro del pipeline.

Una grabación contiene las series temporales de los 4 sensores TGS y, por cada
muestra, su fase ('inicio' | 'base' | 'medicion').
"""

from typing import Dict, List
from pydantic import BaseModel, field_validator


# Sensores esperados (columnas del CSV). v20=TGS2620, v11=TGS2611,
# v02=TGS2602, v00=TGS2600.
EXPECTED_SENSORS = {"v20", "v11", "v02", "v00"}
VALID_STATES = {"inicio", "base", "medicion"}


class SensorReading(BaseModel):
    """Representa una grabación completa del serial-reader (un CSV)."""

    filename: str
    substance_label: str
    sensor_data: Dict[str, List[float]]  # sensor_name -> serie temporal
    states: List[str] = []               # fase por muestra ('inicio'/'base'/'medicion')

    model_config = {"frozen": True}

    @field_validator("substance_label")
    @classmethod
    def validate_label(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("substance_label no puede estar vacío")
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
