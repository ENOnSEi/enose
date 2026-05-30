"""
Schema del informe de ejecución del pipeline.

Es la frontera entre el pipeline (Fase 4 + Fase 5) y la capa de reporting.
Captura toda la información de una ejecución — metadata, datos del dataset,
resultados del modelo y conclusiones — en una estructura validada que cualquier
generador de informes (Markdown, HTML, ...) puede consumir.

Al ser un modelo Pydantic, también se serializa a JSON sin esfuerzo, lo que
permite comparar ejecuciones distintas del historial de informes.
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, field_validator


class DatasetSummary(BaseModel):
    """Resumen de la Fase 4 (generación del dataset)."""

    feature_mode: str                       # 'handcrafted' | 'pca_signal'
    n_samples: int
    n_features: int
    n_groups: int                           # nº de vinos-lote distintos (para split por grupos)
    class_distribution: Dict[str, int]      # clase -> nº de muestras
    sensors: List[str] = []


class SplitSummary(BaseModel):
    """Resumen de la división train/test por grupos."""

    n_train: int
    n_test: int
    n_test_groups: int                      # vinos en test, disjuntos de train
    test_size_effective: float              # proporción real de test


class ModelResults(BaseModel):
    """Resumen de la Fase 5 (entrenamiento y evaluación)."""

    best_params: Dict[str, object]
    cv_score: float
    cv_scoring_metric: str
    train_accuracy: float
    test_accuracy: float
    test_balanced_accuracy: float
    classification_report: Dict[str, object]
    confusion_matrix: List[List[int]]
    class_labels: List[str]

    @field_validator("train_accuracy", "test_accuracy", "test_balanced_accuracy", "cv_score")
    @classmethod
    def validate_ratio(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"métrica fuera de [0, 1]: {v}")
        return v


class ExecutionReport(BaseModel):
    """
    Informe completo de una ejecución del pipeline.

    Reúne metadata reproducible (fecha, commit, rama), el resumen del dataset,
    la división de datos, los resultados del modelo y conclusiones automáticas.
    """

    timestamp: datetime
    git_commit: Optional[str] = None
    git_branch: Optional[str] = None

    dataset: DatasetSummary
    split: Optional[SplitSummary] = None
    model: ModelResults
    conclusions: List[str] = []

    model_config = {"frozen": True}

    @property
    def slug(self) -> str:
        """Identificador del informe basado en la fecha-hora: 'informe_2026-05-31_14-30-05'."""
        return f"informe_{self.timestamp:%Y-%m-%d_%H-%M-%S}"

    @property
    def overfitting_gap(self) -> float:
        """Diferencia train - test accuracy (indicador de sobreajuste)."""
        return self.model.train_accuracy - self.model.test_accuracy
