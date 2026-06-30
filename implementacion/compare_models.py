"""
Harness de comparación de modelos de clasificación.

Corre varios clasificadores sobre el MISMO `dataset_maestro.csv`, con la MISMA
validación que el pipeline (StratifiedGroupKFold agrupando por grabación,
métrica balanced_accuracy), y saca un leaderboard ordenado.

Cada modelo va dentro de un Pipeline(StandardScaler → estimador) y se le da una
pequeña rejilla de hiperparámetros vía GridSearchCV, igual de justo para todos.
Se reporta la balanced_accuracy de CV (media ± std de los folds) — NO un único
split de test, que con pocos datos engaña.

Uso:
    python compare_models.py
    python compare_models.py --dataset ruta/dataset_maestro.csv
    python compare_models.py --cv 3      # nº de folds (se capa por grupos/clase)

Nota metodológica: con pocas muestras, diferencias menores que la std entre
modelos NO son significativas. El leaderboard marca con '~' los que están dentro
de 1 std del mejor: entre esos, elige el más simple (Occam).
"""

import argparse
import re
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.cross_decomposition import PLSRegression
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.decomposition import PCA
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GridSearchCV, StratifiedGroupKFold
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier, NearestCentroid
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelBinarizer, StandardScaler
from sklearn.svm import SVC

sys.path.insert(0, str(Path(__file__).parent / "src"))

from enose.config import (
    DATASET_MAESTRO_PATH, FILENAME_COLUMN, LABEL_COLUMN, NON_FEATURE_COLUMNS,
)

warnings.filterwarnings("ignore")  # silencia convergencia/colinealidad en n pequeño

WINDOW_SUFFIX = re.compile(r"#w\d+$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# PLS-DA: PLSRegression sobre etiquetas one-hot + argmax (no viene en sklearn)
# ---------------------------------------------------------------------------

class PLSDA(BaseEstimator, ClassifierMixin):
    """Partial Least Squares Discriminant Analysis. El estándar quimiométrico
    para discriminar bebidas: maneja p≫n y features colineales por construcción."""

    def __init__(self, n_components: int = 2):
        self.n_components = n_components

    def fit(self, X, y):
        X = np.asarray(X, dtype=float)
        self._lb = LabelBinarizer()
        Y = self._lb.fit_transform(y)
        if Y.shape[1] == 1:  # binario → 2 columnas
            Y = np.hstack([1 - Y, Y])
        self.classes_ = self._lb.classes_
        nc = max(1, min(self.n_components, X.shape[1], X.shape[0] - 1))
        self._pls = PLSRegression(n_components=nc)
        self._pls.fit(X, Y)
        return self

    def predict(self, X):
        Yhat = self._pls.predict(np.asarray(X, dtype=float))
        return self.classes_[np.argmax(Yhat, axis=1)]


# ---------------------------------------------------------------------------
# Catálogo de modelos: (nombre, estimador, grid, tier)
# ---------------------------------------------------------------------------

def build_catalog() -> list[tuple]:
    return [
        # Tier 1 — encajan en pocas muestras + features colineales
        ("PLS-DA", PLSDA(), {"clf__n_components": [2, 3, 5, 8]}, 1),
        ("LDA-shrinkage",
         LinearDiscriminantAnalysis(solver="lsqr"),
         {"clf__shrinkage": ["auto", 0.1, 0.5]}, 1),
        ("LogReg-L2",
         LogisticRegression(penalty="l2", max_iter=5000),
         {"clf__C": [0.1, 1, 10]}, 1),
        ("LogReg-L1",
         LogisticRegression(penalty="l1", solver="saga", max_iter=10000),
         {"clf__C": [0.1, 1, 10]}, 1),
        ("SVM-linear", SVC(kernel="linear"), {"clf__C": [0.1, 1, 10, 100]}, 1),
        ("SVM-RBF", SVC(kernel="rbf"),
         {"clf__C": [1, 10, 100], "clf__gamma": ["scale", "auto", 0.01]}, 1),
        # Tier 2 — baselines
        ("kNN", KNeighborsClassifier(), {"clf__n_neighbors": [1, 3, 5]}, 2),
        ("kNN+PCA",
         Pipeline([("pca", PCA(n_components=6)), ("knn", KNeighborsClassifier())]),
         {"clf__knn__n_neighbors": [1, 3, 5]}, 2),
        ("NaiveBayes", GaussianNB(), {}, 2),
        ("NearestCentroid", NearestCentroid(), {}, 2),
        # Tier 3 — hambrientos de datos (ganarán cuando crezca el dataset)
        ("RandomForest",
         RandomForestClassifier(random_state=42),
         {"clf__n_estimators": [300], "clf__max_depth": [None, 5]}, 3),
        ("HistGradientBoosting",
         HistGradientBoostingClassifier(random_state=42),
         {"clf__max_depth": [None, 3], "clf__learning_rate": [0.1]}, 3),
    ]


# ---------------------------------------------------------------------------
# Carga de datos y grupos
# ---------------------------------------------------------------------------

def load_xy_groups(dataset_path: Path):
    df = pd.read_csv(dataset_path)
    feature_cols = [c for c in df.columns if c not in NON_FEATURE_COLUMNS]
    X = df[feature_cols].fillna(0.0)
    y = df[LABEL_COLUMN]
    if FILENAME_COLUMN in df.columns:
        groups = df[FILENAME_COLUMN].apply(lambda n: WINDOW_SUFFIX.sub("", str(n))).to_numpy()
    else:
        groups = np.arange(len(df))
    return X, y, groups


def n_splits_for(y, groups, requested: int) -> int:
    min_groups_per_class = (
        pd.DataFrame({"y": np.asarray(y), "g": groups})
        .drop_duplicates("g").groupby("y")["g"].count().min()
    )
    return min(max(requested, 2), int(min_groups_per_class))


# ---------------------------------------------------------------------------
# Evaluación
# ---------------------------------------------------------------------------

def evaluate(name, estimator, grid, X, y, groups, cv) -> dict:
    pipe = Pipeline([("scaler", StandardScaler()), ("clf", estimator)])
    gs = GridSearchCV(pipe, grid or {}, cv=cv, scoring="balanced_accuracy", n_jobs=-1)
    gs.fit(X, y, groups=groups)
    std = float(gs.cv_results_["std_test_score"][gs.best_index_])
    return {
        "name": name,
        "score": float(gs.best_score_),
        "std": std,
        "params": {k.replace("clf__", ""): v for k, v in gs.best_params_.items()},
    }


def main():
    parser = argparse.ArgumentParser(description="Compara modelos de clasificación")
    parser.add_argument("--dataset", default=str(DATASET_MAESTRO_PATH))
    parser.add_argument("--cv", type=int, default=3, help="nº de folds (se capa por grupos/clase)")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(f"No existe el dataset: {dataset_path}\nGenera primero con train_from_api.py")
        sys.exit(1)

    X, y, groups = load_xy_groups(dataset_path)
    n_splits = n_splits_for(y, groups, args.cv)
    n_groups = pd.Series(groups).nunique()

    print("=" * 64)
    print("  COMPARACIÓN DE MODELOS")
    print("=" * 64)
    print(f"  Dataset : {dataset_path.name}")
    print(f"  Muestras: {len(X)}  |  Features: {X.shape[1]}  |  Clases: {y.nunique()}")
    print(f"  Grupos (grabaciones): {n_groups}  |  CV: {n_splits}-fold StratifiedGroupKFold")
    print(f"  Métrica : balanced_accuracy (media ± std de los folds)")
    print("=" * 64)

    if n_splits < 2:
        print("  Grupos insuficientes por clase para CV por grupos (se requieren ≥2).")
        sys.exit(1)

    cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=42)

    results = []
    for name, estimator, grid, tier in build_catalog():
        try:
            r = evaluate(name, estimator, grid, X, y, groups, cv)
            r["tier"] = tier
            results.append(r)
            print(f"  ok  {name:22} {r['score']*100:5.1f}% ± {r['std']*100:4.1f}")
        except Exception as e:
            print(f"  XX  {name:22} fallo: {e}")

    if not results:
        sys.exit(1)

    results.sort(key=lambda r: r["score"], reverse=True)
    best = results[0]
    threshold = best["score"] - best["std"]  # dentro de 1 std del mejor

    print("\n" + "=" * 64)
    print("  LEADERBOARD  (ordenado por balanced_accuracy de CV)")
    print("=" * 64)
    print(f"  {'#':>2}  {'modelo':22} {'bal_acc':>9}  {'tier':>4}   params")
    print("  " + "-" * 60)
    for i, r in enumerate(results, 1):
        within = "~" if r["score"] >= threshold else " "
        params = ", ".join(f"{k}={v}" for k, v in r["params"].items()) or "—"
        print(f" {within}{i:>2}  {r['name']:22} {r['score']*100:5.1f}±{r['std']*100:3.0f}%  T{r['tier']}   {params}")

    print("\n  '~' = dentro de 1 std del mejor -> estadisticamente empatados.")
    print(f"  Mejor: {best['name']} ({best['score']*100:.1f}%). Entre los '~', elige el mas simple.")
    print("=" * 64)


if __name__ == "__main__":
    main()
