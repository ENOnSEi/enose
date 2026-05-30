"""
Schema de salida del pipeline: predicción del clasificador para una muestra.

Punto de entrada de cara a producción: si el pipeline se expone vía API
o se integra con otro sistema, este schema es el contrato de respuesta.
"""

from typing import Dict, Optional
from pydantic import BaseModel, field_validator


VALID_LABELS = {"AQ", "HQ", "LQ", "ETH"}


class Prediction(BaseModel):
    """Predicción del clasificador para una muestra de sensor."""

    filename: str
    predicted_class: str
    confidence: Optional[float] = None           # probabilidad de la clase predicha
    class_probabilities: Optional[Dict[str, float]] = None  # proba por clase

    model_config = {"frozen": True}

    @field_validator("predicted_class")
    @classmethod
    def validate_class(cls, v: str) -> str:
        if v not in VALID_LABELS:
            raise ValueError(f"predicted_class debe ser uno de {VALID_LABELS}, recibido: '{v}'")
        return v

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence debe estar en [0, 1], recibido: {v}")
        return v
