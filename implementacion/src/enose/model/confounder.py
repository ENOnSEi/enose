"""
Test de confusión con el tiempo ("¿aprende el día en vez del olor?").

La fase 'base' es aire limpio: no lleva información de la sustancia. Si un
clasificador entrenado SOLO con features de la base acierta la sustancia por
encima del azar (con validación agrupada, sin fuga entre reps), lo que está
reconociendo es la tanda: deriva, humedad, temperatura, calentamiento... Es
decir, las sustancias se han medido en condiciones distintas y el modelo
"bueno" puede estar aprovechándolo.

El azar se estima con un test de permutación a nivel de grupo: se barajan las
etiquetas entre grupos (Samples), no entre filas, para que cada grupo siga
teniendo una única etiqueta y la permutación respete la estructura de la CV.

Salvedad: la base de las reps ≥2 va tras el cooldown de la misma sustancia y
puede arrastrar restos de olor (carry-over). Para aislar el efecto "día" usar
solo la rep 1 (``first_rep_only``).
"""

from dataclasses import dataclass
from typing import Dict, Optional, Sequence

import numpy as np
import pandas as pd
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.metrics import balanced_accuracy_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from enose.config import ML_CONFIG, SENSOR_COLUMNS, TIMESTAMP_COLUMN
from enose.io.reader import BASELINE_STATE, split_by_state


def baseline_features(df: pd.DataFrame, sensor_cols: Optional[Sequence[str]] = None) -> Optional[Dict[str, float]]:
    """Features crudas (ADC, sin normalizar) de la fase 'base' por sensor:
    mediana, desviación típica y pendiente (u/s con el reloj de la placa).

    Devuelve ``None`` si la grabación no tiene al menos 3 lecturas de base.
    """
    if sensor_cols is None:
        sensor_cols = SENSOR_COLUMNS["sensors"]
    base = split_by_state(df).get(BASELINE_STATE)
    if base is None or len(base) < 3:
        return None

    t = base[TIMESTAMP_COLUMN].to_numpy(dtype=float) / 1000.0 if TIMESTAMP_COLUMN in base else None
    feats: Dict[str, float] = {}
    for sensor in sensor_cols:
        if sensor not in base.columns:
            continue
        y = base[sensor].to_numpy(dtype=float)
        feats[f"{sensor}_base_median"] = float(np.median(y))
        feats[f"{sensor}_base_std"] = float(np.std(y))
        x = t if t is not None and np.ptp(t) > 0 else np.arange(len(y), dtype=float)
        feats[f"{sensor}_base_slope"] = float(np.polyfit(x, y, 1)[0])
    return feats or None


def _estimator() -> Pipeline:
    # Hiperparámetros fijos (sin GridSearch): el objetivo es comparar contra el
    # azar con el mismo estimador, no optimizar.
    return Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")),
    ])


def _n_splits(y: np.ndarray, groups: np.ndarray) -> int:
    per_class = pd.DataFrame({"y": y, "g": groups}).drop_duplicates("g").groupby("y")["g"].count().min()
    return min(ML_CONFIG.n_splits_cv, int(per_class))


def grouped_cv_score(X: np.ndarray, y: np.ndarray, groups: np.ndarray, n_repeats: int = 3) -> float:
    """Balanced accuracy out-of-fold con StratifiedGroupKFold, media de
    ``n_repeats`` particiones distintas (reduce la varianza con n pequeño)."""
    n_splits = _n_splits(y, groups)
    if n_splits < 2:
        raise ValueError("Cada clase necesita ≥2 grupos distintos para la validación agrupada")
    scores = []
    for seed in range(n_repeats):
        cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
        y_pred = np.empty_like(y)
        for tr, te in cv.split(X, y, groups):
            y_pred[te] = _estimator().fit(X[tr], y[tr]).predict(X[te])
        scores.append(balanced_accuracy_score(y, y_pred))
    return float(np.mean(scores))


def permute_by_group(y: np.ndarray, groups: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Baraja las etiquetas entre grupos: cada grupo recibe la etiqueta de otro
    grupo (todas sus filas la misma). Conserva el nº de grupos por clase."""
    uniq, first = np.unique(groups, return_index=True)
    group_labels = y[first]
    mapping = dict(zip(uniq, rng.permutation(group_labels)))
    return np.array([mapping[g] for g in groups], dtype=y.dtype)


@dataclass
class ConfounderResult:
    score: float               # balanced accuracy agrupada con features de base
    chance: float              # 1 / nº de clases
    perm_mean: float           # media de la distribución nula
    perm_p95: float            # percentil 95 de la nula
    p_value: float
    n_permutations: int
    n_rows: int
    n_groups: int
    n_classes: int

    @property
    def confounded(self) -> bool:
        return self.p_value < 0.05

    def as_dict(self) -> Dict:
        return {**self.__dict__, "confounded": self.confounded}


def confounder_test(
    X: np.ndarray, y: np.ndarray, groups: np.ndarray,
    n_permutations: int = 200, n_repeats: int = 3, seed: int = 0,
) -> ConfounderResult:
    X, y, groups = np.asarray(X, dtype=float), np.asarray(y), np.asarray(groups)
    observed = grouped_cv_score(X, y, groups, n_repeats)
    rng = np.random.default_rng(seed)
    null = np.array([
        grouped_cv_score(X, permute_by_group(y, groups, rng), groups, n_repeats)
        for _ in range(n_permutations)
    ])
    return ConfounderResult(
        score=observed,
        chance=1.0 / len(np.unique(y)),
        perm_mean=float(null.mean()),
        perm_p95=float(np.percentile(null, 95)),
        p_value=float((1 + np.sum(null >= observed)) / (n_permutations + 1)),
        n_permutations=n_permutations,
        n_rows=len(y),
        n_groups=len(np.unique(groups)),
        n_classes=len(np.unique(y)),
    )
