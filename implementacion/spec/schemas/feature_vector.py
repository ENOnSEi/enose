"""
Schema intermedio del pipeline: vector de características extraídas de una muestra.

Es la frontera entre la capa de extracción y la capa de ML.
Garantiza que el dataset que llega al clasificador tiene estructura válida.
"""

from typing import Dict
from pydantic import BaseModel, field_validator


class FeatureVector(BaseModel):
    """Vector de características de una muestra procesada."""

    filename: str
    substance_label: str
    features: Dict[str, float]  # '{sensor}_{ventana}_{metrica_o_pc}' -> valor

    model_config = {"frozen": True}

    @field_validator("features")
    @classmethod
    def validate_non_empty(cls, v: Dict[str, float]) -> Dict[str, float]:
        if not v:
            raise ValueError("features no puede estar vacío")
        return v

    def to_flat_record(self) -> dict:
        """Convierte a dict plano para construir el DataFrame maestro."""
        return {
            "Nombre_Archivo": self.filename,
            "Calidad_Muestra": self.substance_label,
            **self.features,
        }

    @property
    def n_features(self) -> int:
        return len(self.features)
