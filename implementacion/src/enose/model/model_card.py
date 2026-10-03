"""
Ficha del modelo (model_card.json) junto a best_model.pkl.

Registra con qué datos, código y configuración se entrenó cada modelo, y sus
métricas, para poder reproducirlo y saber si un .pkl sigue siendo compatible
con el código actual. ``predict_from_api.py`` la comprueba antes de predecir y
solo AVISA si algo no cuadra: nunca bloquea la predicción.
"""

import dataclasses
import hashlib
import json
import platform
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from enose.config import (
    CLASSIFIER, FEATURE_MODE, FILENAME_COLUMN, GRID_PARAMS, GROUP_BY, GROUP_COLUMN,
    LABEL_COLUMN, ML_CONFIG, PCA_CONFIG, PROJECT_ROOT, SENSOR_COLUMNS, SIGNAL_CONFIG,
)

MODEL_CARD_NAME = "model_card.json"
_MS_ID = re.compile(r"_ms(\d+)$")   # Nombre_Archivo de train_from_api: "<sample>_rep<N>_ms<id>"


def card_path_for(model_path: Path) -> Path:
    return Path(model_path).with_name(MODEL_CARD_NAME)


def _git_commit() -> Dict[str, Any]:
    def run(*args: str) -> Optional[str]:
        try:
            out = subprocess.run(["git", *args], cwd=PROJECT_ROOT, capture_output=True,
                                 text=True, timeout=5)
            return out.stdout.strip() if out.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            return None
    status = run("status", "--porcelain")
    return {"commit": run("rev-parse", "HEAD"),
            "dirty": bool(status) if status is not None else None}


def _sha256(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def feature_config() -> Dict[str, Any]:
    """Configuración que determina las features. Si cambia, un modelo antiguo
    recibe features calculadas de otra forma aunque los nombres coincidan."""
    return {
        "feature_mode": FEATURE_MODE,
        "sensors": list(SENSOR_COLUMNS["sensors"]),
        "signal": dataclasses.asdict(SIGNAL_CONFIG),
        "pca": dataclasses.asdict(PCA_CONFIG) if FEATURE_MODE == "pca_signal" else None,
    }


def _to_jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, (np.ndarray, pd.Series)):
        return _to_jsonable(obj.tolist())
    if isinstance(obj, Path):
        return str(obj)
    return obj


def build_model_card(df: pd.DataFrame, dataset_path: Path, feature_names: List[str],
                     results: Dict[str, Any], cv_only: bool) -> Dict[str, Any]:
    import sklearn

    ms_ids = sorted({int(m.group(1)) for name in df.get(FILENAME_COLUMN, pd.Series(dtype=str)).astype(str)
                     if (m := _MS_ID.search(name))})
    metric_keys = ["cv_score", "cv_scoring_metric", "train_accuracy", "test_accuracy",
                   "test_balanced_accuracy", "cv_score_grouped", "cv_score_per_row", "cv_inflation"]
    return _to_jsonable({
        "created_at": datetime.now(timezone.utc).isoformat(),
        "code": _git_commit(),
        "dataset": {
            "path": str(dataset_path),
            "sha256": _sha256(dataset_path),
            "n_rows": int(len(df)),
            "classes": df[LABEL_COLUMN].value_counts().sort_index().to_dict(),
            "n_groups": int(df[GROUP_COLUMN].nunique()) if GROUP_COLUMN in df else None,
            "ms_ids": ms_ids or None,   # None = dataset legacy (CSV), sin ids de la API
        },
        "features": {"n": len(feature_names), "names": list(feature_names), "config": feature_config()},
        "training": {
            "classifier": CLASSIFIER,
            "group_by": GROUP_BY,
            "evaluation": "cv_only (out-of-fold)" if cv_only else "holdout",
            "grid": GRID_PARAMS,
            "ml_config": dataclasses.asdict(ML_CONFIG),
            "best_params": results.get("best_params"),
        },
        "metrics": {k: results[k] for k in metric_keys if k in results},
        "environment": {
            "python": platform.python_version(),
            "sklearn": sklearn.__version__,
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
    })


def save_model_card(card: Dict[str, Any], model_path: Path) -> Path:
    path = card_path_for(model_path)
    path.write_text(json.dumps(card, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def check_model_card(model_path: Path, model: Any = None) -> List[str]:
    """Avisos de compatibilidad entre el modelo guardado y el código actual
    (lista vacía = todo cuadra). No lanza excepciones."""
    path = card_path_for(model_path)
    if not path.exists():
        return [f"El modelo no tiene {MODEL_CARD_NAME} (entrenado antes de que existiera): "
                "no se puede comprobar con qué datos ni con qué configuración se entrenó."]
    try:
        card = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return [f"No se pudo leer {path}: {e}"]

    warnings: List[str] = []
    saved_cfg = card.get("features", {}).get("config")
    current_cfg = _to_jsonable(feature_config())
    if saved_cfg != current_cfg:
        diff = sorted(k for k in set(saved_cfg or {}) | set(current_cfg)
                      if (saved_cfg or {}).get(k) != current_cfg.get(k))
        warnings.append(f"La configuración de features ha cambiado desde el entrenamiento ({', '.join(diff)}): "
                        "las features de ahora no se calculan igual que las de entrenamiento. Reentrena.")
    names = card.get("features", {}).get("names")
    model_names = list(getattr(model, "feature_names_in_", [])) if model is not None else []
    if names and model_names and names != model_names:
        warnings.append(f"{MODEL_CARD_NAME} no corresponde a este .pkl (las features no coinciden).")
    return warnings


def describe_model_card(model_path: Path) -> Optional[str]:
    """Resumen de una línea de la ficha (para el log de la predicción)."""
    try:
        card = json.loads(card_path_for(model_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    commit = (card.get("code", {}).get("commit") or "?")[:8]
    ds, m = card.get("dataset", {}), card.get("metrics", {})
    score = m.get("cv_score_grouped", m.get("cv_score"))
    score_txt = f"{score*100:.1f}%" if isinstance(score, (int, float)) else "?"
    return (f"Modelo entrenado {card.get('created_at', '?')[:19]} (commit {commit}) con "
            f"{ds.get('n_rows', '?')} reps de {len(ds.get('classes') or {})} clases; "
            f"{m.get('cv_scoring_metric', 'score')} agrupado = {score_txt}")
