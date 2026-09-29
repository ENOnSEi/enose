"""
Entrenamiento y optimización del modelo SVM (Phase 5).

Implementa ClassifierProtocol de forma indirecta — el pipeline interno
usa sklearn.SVC pero sigue el contrato a través del GridSearchCV wrapper.
Para sustituir el clasificador por otro, solo hay que cambiar los parámetros
de build_pipeline() sin tocar el resto del flujo.
"""

import pickle
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.metrics import (
    accuracy_score, balanced_accuracy_score, classification_report, confusion_matrix,
)
from sklearn.base import clone
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.model_selection import (
    GridSearchCV, StratifiedGroupKFold, cross_val_predict, cross_val_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from enose.config import (
    CLASSIFIER, DATA_PROCESSED_DIR, DATASET_MAESTRO_PATH, FEATURE_MODE, GRID_PARAMS,
    GROUP_BY, LABEL_COLUMN, ML_CONFIG, NON_FEATURE_COLUMNS, PCA_CONFIG,
)
from enose.features.perkey_pca import PerKeyPCA
from enose.pipeline.dataset import derive_groups, load_dataset, validate_dataset
from enose.utils import create_output_directory, print_data_summary, setup_logging

logger = setup_logging(__name__)


class ModelTrainer:
    """
    Entrena y optimiza un SVM para clasificación de sustancias.
    El flujo sigue el método train() que encadena los pasos en orden.
    """

    def __init__(self, dataset_path: Path = DATASET_MAESTRO_PATH) -> None:
        self.dataset_path = Path(dataset_path)
        self.df: Optional[pd.DataFrame] = None
        self.X: Optional[pd.DataFrame] = None
        self.y: Optional[pd.Series] = None
        self.groups = None            # id de grabación por muestra (para split por grupos)
        self.groups_train = None      # ids de grupo del subconjunto de entrenamiento
        self.X_train = self.X_test = self.y_train = self.y_test = None
        self.pipeline: Optional[Pipeline] = None
        self.grid_search: Optional[GridSearchCV] = None
        self.results: Dict = {}
        self.n_groups: int = 0           # nº de grabaciones distintas (para el informe)
        self.split_info: Optional[Dict] = None  # resumen de la división train/test
        # Evaluación sólo-CV (sin holdout separado): se activa cuando la CV anidada
        # no es viable por datos escasos (p. ej. LDA con muchas clases y pocas reps).
        self._cv_only: bool = False
        self._cv_sgkf = None
        self._cv_groups = None

    # ------------------------------------------------------------------
    # Pasos del entrenamiento
    # ------------------------------------------------------------------

    def load_and_validate_data(self) -> bool:
        if not self.dataset_path.exists():
            logger.error(f"Dataset no encontrado: {self.dataset_path}")
            return False
        self.df = load_dataset(self.dataset_path)
        if self.df is None:
            return False
        is_valid, issues = validate_dataset(self.df)
        if not is_valid:
            logger.warning(f"Problemas en dataset: {issues}")
        return True

    def prepare_features(self) -> bool:
        try:
            self.X = self.df.drop(columns=[c for c in NON_FEATURE_COLUMNS if c in self.df.columns])
            self.y = self.df[LABEL_COLUMN]
            self.groups = derive_groups(self.df, GROUP_BY)

            n_groups = pd.Series(self.groups).nunique()
            self.n_groups = int(n_groups)
            logger.info(f"Features: {self.X.shape[1]} | Muestras: {self.X.shape[0]} | "
                        f"Clases: {self.y.nunique()} | Grupos ({GROUP_BY}): {n_groups}")
            if n_groups < self.X.shape[0]:
                logger.info("Se usará validación por grupos: ninguna fila de un mismo grupo "
                            "estará a la vez en train y test.")
            return True
        except Exception as e:
            logger.error(f"Error preparando features: {e}")
            return False

    def _log_insufficient_groups(self) -> None:
        per_class = (
            pd.DataFrame({"y": self.y.to_numpy(), "g": self.groups})
            .drop_duplicates("g").groupby("y")["g"].count()
        )
        short = per_class[per_class < 2]
        logger.error(
            f"Grupos insuficientes con GROUP_BY='{GROUP_BY}': cada clase necesita ≥2 grupos "
            f"distintos para validar sin fuga. Clases con 1 solo grupo: {sorted(short.index.tolist())}."
        )
        if GROUP_BY == "sample":
            logger.error(
                "Solución: medir cada sustancia en ≥2 Samples distintos (idealmente en días "
                "distintos). Con un solo Sample por sustancia no es posible estimar si el modelo "
                "generaliza a otra tanda. Para reproducir la cifra antigua (optimista) usa "
                "GROUP_BY='recording' en config.py."
            )

    def split_data(self, test_size: float = 0.2, random_state: int = 42) -> bool:
        try:
            # nº de grupos distintos por clase: limita en cuántos folds se puede
            # partir manteniendo cada clase representada y los grupos intactos.
            min_groups_per_class = (
                pd.DataFrame({"y": self.y.to_numpy(), "g": self.groups})
                .drop_duplicates("g").groupby("y")["g"].count().min()
            )
            # ~1/test_size folds → primer fold como test, acotado por los grupos disponibles.
            n_splits = min(max(round(1 / test_size), 2), int(min_groups_per_class))
            if n_splits < 2:
                self._log_insufficient_groups()
                return False

            sgkf = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
            train_idx, test_idx = next(sgkf.split(self.X, self.y, self.groups))

            self.X_train, self.X_test = self.X.iloc[train_idx], self.X.iloc[test_idx]
            self.y_train, self.y_test = self.y.iloc[train_idx], self.y.iloc[test_idx]
            self.groups_train = self.groups[train_idx]

            n_test_groups = pd.Series(self.groups[test_idx]).nunique()
            self.split_info = {
                "n_train": int(len(self.X_train)),
                "n_test": int(len(self.X_test)),
                "n_test_groups": int(n_test_groups),
                "test_size_effective": float(len(self.X_test) / len(self.X)) if len(self.X) else 0.0,
            }
            logger.info(f"Split por grupos ({n_splits} folds -> test ~{100/n_splits:.0f}%): "
                        f"Train {len(self.X_train)} muestras / Test {len(self.X_test)} muestras "
                        f"({n_test_groups} grupos en test, disjuntos de train)")
            return True
        except Exception as e:
            logger.error(f"Error dividiendo datos: {e}")
            return False

    def _build_classifier(self):
        """Devuelve el estimador final según CLASSIFIER (config). El paso se
        llama siempre 'clf' en el Pipeline, así que las rejillas usan 'clf__'."""
        if CLASSIFIER == "lda":
            # solver='lsqr' es el que admite shrinkage (regulariza la covarianza,
            # imprescindible con p>n). El shrinkage concreto lo elige GridSearchCV.
            return LinearDiscriminantAnalysis(solver="lsqr")
        if CLASSIFIER == "svm":
            # probability=False: las métricas usan predict() (no predict_proba), y
            # probability=True dispara una CV interna (Platt) costosa e innecesaria.
            return SVC(random_state=42, probability=False)
        raise ValueError(f"CLASSIFIER desconocido: '{CLASSIFIER}'")

    def build_pipeline(self) -> bool:
        try:
            steps = []
            # En modo pca_signal, el PCA por (sensor×ventana) se ajusta DENTRO del
            # pipeline (solo sobre train en cada fold) para evitar data leakage.
            if FEATURE_MODE == "pca_signal":
                steps.append(("pca", PerKeyPCA(PCA_CONFIG)))
            steps.append(("scaler", StandardScaler()))
            steps.append(("clf", self._build_classifier()))

            self.pipeline = Pipeline(steps)
            logger.info(f"Pipeline construido ({CLASSIFIER}): " + " -> ".join(name for name, _ in steps))
            return True
        except Exception as e:
            logger.error(f"Error construyendo pipeline: {e}")
            return False

    def _fit_grid(self, X, y, groups) -> bool:
        """Ajusta un GridSearchCV con CV por grupos sobre (X, y, groups).

        Devuelve True si entrena; False si los folds no son viables (p. ej. un
        clasificador como LDA que exige más muestras que clases por fold).
        """
        groups_per_class = (
            pd.DataFrame({"y": np.asarray(y), "g": groups})
            .drop_duplicates("g").groupby("y")["g"].count().min()
        )
        n_splits = min(ML_CONFIG.n_splits_cv, int(groups_per_class))
        if n_splits < 2:
            return False

        sgkf = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=42)
        gs = GridSearchCV(
            estimator=self.pipeline,
            param_grid=GRID_PARAMS,
            cv=sgkf,
            scoring=ML_CONFIG.scoring_metric,
            n_jobs=ML_CONFIG.n_jobs,
            verbose=ML_CONFIG.verbose,
        )
        logger.info(f"GridSearchCV con {n_splits} folds por grupos — iniciando búsqueda...")
        try:
            gs.fit(X, y, groups=groups)
        except Exception as e:
            logger.warning(f"GridSearchCV no viable con estos folds: {e}")
            return False

        self.grid_search = gs
        self._cv_sgkf = sgkf
        self._cv_groups = groups
        return True

    def optimize_hyperparameters(self) -> bool:
        try:
            # Intento 1: CV anidada sobre el train (deja el holdout para reporte).
            if self._fit_grid(self.X_train, self.y_train, self.groups_train):
                self._cv_only = False
                logger.info("Búsqueda completada (CV anidada con holdout de test)")
                return True

            # Intento 2 (datos escasos): evaluación SÓLO por CV sobre todo el dataset,
            # sin holdout separado. Es la estadística correcta con n pequeño y evita
            # folds con menos muestras que clases. El modelo de producción se reajusta
            # sobre todos los datos.
            logger.warning("CV anidada no viable; evaluando por CV sobre todo el dataset (sin holdout).")
            if self._fit_grid(self.X, self.y, self.groups):
                self._cv_only = True
                logger.info("Búsqueda completada (evaluación sólo-CV, out-of-fold)")
                return True

            self._log_insufficient_groups()
            return False
        except Exception as e:
            logger.error(f"Error en GridSearchCV: {e}", exc_info=True)
            return False

    def evaluate_model(self) -> bool:
        try:
            best = self.grid_search.best_estimator_

            if self._cv_only:
                # Predicciones out-of-fold sobre todo el dataset: cada muestra se
                # predice cuando cae en el fold de test. Sin fuga y estadísticamente
                # honesto con n pequeño. y_true/y_pred cubren todas las muestras.
                est = clone(self.pipeline).set_params(**self.grid_search.best_params_)
                y_true = self.y
                y_pred = cross_val_predict(
                    est, self.X, self.y, cv=self._cv_sgkf,
                    groups=self._cv_groups, n_jobs=ML_CONFIG.n_jobs,
                )
                acc_train = accuracy_score(self.y, best.predict(self.X))
                self.y_test = y_true  # para las visualizaciones (report figure)
                self.split_info = {
                    "n_train": int(len(self.X)),
                    "n_test": int(len(self.X)),
                    "n_test_groups": int(pd.Series(self._cv_groups).nunique()),
                    "test_size_effective": 1.0,
                }
                logger.info("Evaluación out-of-fold sobre todo el dataset (sin holdout separado).")
            else:
                y_true = self.y_test
                y_pred = best.predict(self.X_test)
                acc_train = accuracy_score(self.y_train, best.predict(self.X_train))

            acc_test = accuracy_score(y_true, y_pred)
            bal_acc_test = balanced_accuracy_score(y_true, y_pred)
            cm = confusion_matrix(y_true, y_pred)

            logger.info(f"Mejores params: {self.grid_search.best_params_}")
            logger.info(f"CV score ({ML_CONFIG.scoring_metric}): {self.grid_search.best_score_*100:.2f}%  "
                        f"| Train acc: {acc_train*100:.2f}%  | OOF/Test acc: {acc_test*100:.2f}%  "
                        f"| OOF/Test balanced acc: {bal_acc_test*100:.2f}%")
            logger.info("\n" + classification_report(y_true, y_pred))

            self.results = {
                "best_params": self.grid_search.best_params_,
                "cv_score": self.grid_search.best_score_,
                "cv_scoring_metric": ML_CONFIG.scoring_metric,
                "train_accuracy": acc_train,
                "test_accuracy": acc_test,
                "test_balanced_accuracy": bal_acc_test,
                "classification_report": classification_report(self.y_test, y_pred, output_dict=True),
                "confusion_matrix": cm,
                "y_test": self.y_test.values,
                "y_pred": y_pred,
                "best_model": best,
                "group_by": GROUP_BY,
                **self._grouping_comparison(),
            }
            self._generate_visualizations(best, acc_train, acc_test, cm, y_pred)
            return True
        except Exception as e:
            logger.error(f"Error en evaluación: {e}")
            return False

    def _grouping_comparison(self) -> Dict:
        """CV con los mejores hiperparámetros sobre todo el dataset, dos veces y con
        los mismos folds: agrupando por self.groups (honesta) y con cada fila como su
        propio grupo (reps de una misma tanda repartidas entre train y test). La
        diferencia es cuánto infla la accuracy mezclar reps de la misma tanda."""
        if pd.Series(self.groups).nunique() == len(self.groups):
            return {}  # cada fila ya es su propio grupo: no hay nada que comparar
        try:
            per_class = (
                pd.DataFrame({"y": self.y.to_numpy(), "g": self.groups})
                .drop_duplicates("g").groupby("y")["g"].count().min()
            )
            n_splits = min(ML_CONFIG.n_splits_cv, int(per_class))
            if n_splits < 2:
                return {}
            est = clone(self.pipeline).set_params(**self.grid_search.best_params_)
            cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=42)
            scores = {}
            for key, groups in (("grouped", self.groups), ("per_row", np.arange(len(self.y)))):
                scores[key] = float(np.mean(cross_val_score(
                    est, self.X, self.y, groups=groups, cv=cv,
                    scoring=ML_CONFIG.scoring_metric, n_jobs=ML_CONFIG.n_jobs,
                )))
            inflation = scores["per_row"] - scores["grouped"]
            logger.info(
                f"{ML_CONFIG.scoring_metric} ({n_splits} folds, todo el dataset): "
                f"agrupando por {GROUP_BY} = {scores['grouped']*100:.1f}% | "
                f"por fila (reps mezcladas) = {scores['per_row']*100:.1f}% | "
                f"inflado = {inflation*100:+.1f} pp"
            )
            return {
                "cv_score_grouped": scores["grouped"],
                "cv_score_per_row": scores["per_row"],
                "cv_inflation": inflation,
            }
        except Exception as e:
            logger.warning(f"No se pudo calcular la comparación de agrupaciones: {e}")
            return {}

    def save_model(self, output_dir: Path = DATA_PROCESSED_DIR) -> bool:
        try:
            output_dir = Path(output_dir)
            create_output_directory(output_dir)

            with open(output_dir / "best_model.pkl", "wb") as f:
                pickle.dump(self.grid_search.best_estimator_, f)
            with open(output_dir / "training_results.pkl", "wb") as f:
                pickle.dump(self.results, f)

            logger.info(f"Modelo guardado en: {output_dir / 'best_model.pkl'}")

            if FEATURE_MODE == "pca_signal":
                logger.info("PCA incluido dentro de best_model.pkl (PerKeyPCA en el Pipeline); "
                            "no se requiere pca_transformers.pkl por separado.")
            return True
        except Exception as e:
            logger.error(f"Error guardando modelo: {e}")
            return False

    def generate_report(self) -> bool:
        """
        Genera el informe de ejecución (Markdown + PNGs + report.json) en una
        carpeta con timestamp dentro de informes/. Un fallo aquí NO invalida el
        entrenamiento: el modelo ya está entrenado y guardado.
        """
        try:
            # Import diferido: enose.report es la única zona Dev que toca spec en
            # runtime (ver design/adr/001-informe-automatico-de-ejecucion.md).
            from enose.report import MarkdownReportGenerator, build_execution_report
            from spec.schemas.execution_report import SplitSummary

            split = SplitSummary(**self.split_info) if self.split_info else None
            report = build_execution_report(
                df=self.df,
                results=self.results,
                feature_mode=FEATURE_MODE,
                n_groups=self.n_groups,
                split=split,
            )
            MarkdownReportGenerator().generate(report)
            return True
        except Exception as e:
            logger.warning(f"No se pudo generar el informe de ejecución: {e}")
            return True  # no bloquea el pipeline

    # ------------------------------------------------------------------
    # Orquestador
    # ------------------------------------------------------------------

    def train(self) -> bool:
        steps = [
            ("Cargando datos", self.load_and_validate_data),
            ("Preparando features", self.prepare_features),
            ("Dividiendo datos", self.split_data),
            ("Construyendo pipeline", self.build_pipeline),
            ("Optimizando hiperparámetros", self.optimize_hyperparameters),
            ("Evaluando modelo", self.evaluate_model),
            ("Guardando modelo", self.save_model),
            ("Generando informe", self.generate_report),
        ]
        for name, step in steps:
            logger.info(f">> {name}...")
            if not step():
                logger.error(f"Fallo en: {name}")
                return False
        logger.info("ENTRENAMIENTO COMPLETADO")
        return True

    # ------------------------------------------------------------------
    # Visualizaciones
    # ------------------------------------------------------------------

    def _generate_visualizations(self, best_model, acc_train, acc_test, cm, y_pred) -> None:
        try:
            viz_dir = create_output_directory(DATA_PROCESSED_DIR / "visualizations")

            # Matriz de confusión
            fig, ax = plt.subplots(figsize=(8, 6))
            sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", ax=ax)
            ax.set_xlabel("Predicción", fontweight="bold")
            ax.set_ylabel("Verdadero", fontweight="bold")
            ax.set_title("Matriz de Confusión", fontweight="bold")
            plt.tight_layout()
            plt.savefig(viz_dir / "01_confusion_matrix.png", dpi=300, bbox_inches="tight")
            plt.close()

            # Comparación de precisiones
            fig, ax = plt.subplots(figsize=(8, 5))
            bars = ax.bar(["Entrenamiento", "Prueba"], [acc_train * 100, acc_test * 100],
                          color=["#2ecc71", "#e74c3c"], edgecolor="black", alpha=0.8)
            for bar, acc in zip(bars, [acc_train * 100, acc_test * 100]):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                        f"{acc:.2f}%", ha="center", va="bottom", fontweight="bold")
            ax.set_ylim([0, 105])
            ax.set_title("Precisión: Entrenamiento vs Prueba", fontweight="bold")
            ax.grid(axis="y", alpha=0.3)
            plt.tight_layout()
            plt.savefig(viz_dir / "02_accuracy_comparison.png", dpi=300, bbox_inches="tight")
            plt.close()

            # Reporte de clasificación
            report = classification_report(self.y_test, y_pred, output_dict=True)
            classes = [k for k in report if k not in {"accuracy", "macro avg", "weighted avg"}]
            metrics = ["precision", "recall", "f1-score"]
            x = np.arange(len(classes))
            fig, ax = plt.subplots(figsize=(10, 6))
            for i, metric in enumerate(metrics):
                ax.bar(x + i * 0.25, [report[c].get(metric, 0) for c in classes],
                       0.25, label=metric.capitalize(), alpha=0.8, edgecolor="black")
            ax.set_xticks(x + 0.25)
            ax.set_xticklabels(classes)
            ax.legend()
            ax.set_title("Reporte de Clasificación", fontweight="bold")
            ax.grid(axis="y", alpha=0.3)
            plt.tight_layout()
            plt.savefig(viz_dir / "03_classification_report.png", dpi=300, bbox_inches="tight")
            plt.close()

            # Distribución verdadero vs predicho
            fig, axes = plt.subplots(1, 2, figsize=(12, 5))
            for ax, values, title, color in zip(
                axes,
                [self.y_test, y_pred],
                ["Clases Verdaderas", "Clases Predichas"],
                ["skyblue", "lightcoral"],
            ):
                unique, counts = np.unique(values, return_counts=True)
                ax.bar(unique, counts, color=color, edgecolor="black", alpha=0.8)
                ax.set_title(title, fontweight="bold")
                ax.grid(axis="y", alpha=0.3)
            plt.tight_layout()
            plt.savefig(viz_dir / "04_distribution_comparison.png", dpi=300, bbox_inches="tight")
            plt.close()

            logger.info("Visualizaciones generadas")
        except Exception as e:
            logger.warning(f"Error en visualizaciones: {e}")


def main():
    trainer = ModelTrainer()
    if not trainer.train():
        sys.exit(1)


if __name__ == "__main__":
    main()
