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
    accuracy_score, classification_report, confusion_matrix,
)
from sklearn.model_selection import GridSearchCV, StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from enose.config import (
    DATA_PROCESSED_DIR, DATASET_MAESTRO_PATH, FEATURE_MODE,
    GRID_PARAMS, ML_CONFIG, PCA_CONFIG,
)
from enose.features.perkey_pca import PerKeyPCA
from enose.pipeline.dataset import load_dataset, validate_dataset
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
        self.X_train = self.X_test = self.y_train = self.y_test = None
        self.pipeline: Optional[Pipeline] = None
        self.grid_search: Optional[GridSearchCV] = None
        self.results: Dict = {}

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
            exclude = {"Nombre_Archivo", "Ruta_Completa", "Calidad_Vino"}
            self.X = self.df.drop(columns=[c for c in exclude if c in self.df.columns])
            self.y = self.df["Calidad_Vino"]
            logger.info(f"Features: {self.X.shape[1]} | Muestras: {self.X.shape[0]} | Clases: {self.y.nunique()}")
            return True
        except Exception as e:
            logger.error(f"Error preparando features: {e}")
            return False

    def split_data(self, test_size: float = 0.2, random_state: int = 42) -> bool:
        try:
            self.X_train, self.X_test, self.y_train, self.y_test = train_test_split(
                self.X, self.y, test_size=test_size, random_state=random_state, stratify=self.y
            )
            logger.info(f"Train: {len(self.X_train)} | Test: {len(self.X_test)}")
            return True
        except Exception as e:
            logger.error(f"Error dividiendo datos: {e}")
            return False

    def build_pipeline(self) -> bool:
        try:
            steps = []
            # En modo pca_signal, el PCA por (sensor×ventana) se ajusta DENTRO del
            # pipeline (solo sobre train en cada fold) para evitar data leakage.
            if FEATURE_MODE == "pca_signal":
                steps.append(("pca", PerKeyPCA(PCA_CONFIG)))
            steps.append(("scaler", StandardScaler()))
            steps.append(("svm", SVC(random_state=42, probability=True)))

            self.pipeline = Pipeline(steps)
            logger.info("Pipeline construido: " + " -> ".join(name for name, _ in steps))
            return True
        except Exception as e:
            logger.error(f"Error construyendo pipeline: {e}")
            return False

    def optimize_hyperparameters(self) -> bool:
        try:
            min_class = self.y_train.value_counts().min()
            n_splits = min(ML_CONFIG.n_splits_cv, min_class)
            if n_splits < 2:
                logger.error("Clase minoritaria insuficiente para CV (mínimo 2 muestras)")
                return False

            skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
            self.grid_search = GridSearchCV(
                estimator=self.pipeline,
                param_grid=GRID_PARAMS,
                cv=skf,
                scoring=ML_CONFIG.scoring_metric,
                n_jobs=ML_CONFIG.n_jobs,
                verbose=ML_CONFIG.verbose,
            )
            logger.info(f"GridSearchCV con {n_splits} folds — iniciando búsqueda...")
            self.grid_search.fit(self.X_train, self.y_train)
            logger.info("Búsqueda completada")
            return True
        except Exception as e:
            logger.error(f"Error en GridSearchCV: {e}", exc_info=True)
            return False

    def evaluate_model(self) -> bool:
        try:
            best = self.grid_search.best_estimator_
            y_pred = best.predict(self.X_test)
            acc_train = accuracy_score(self.y_train, best.predict(self.X_train))
            acc_test = accuracy_score(self.y_test, y_pred)
            cm = confusion_matrix(self.y_test, y_pred)

            logger.info(f"Mejores params: {self.grid_search.best_params_}")
            logger.info(f"CV score: {self.grid_search.best_score_*100:.2f}%  "
                        f"| Train: {acc_train*100:.2f}%  | Test: {acc_test*100:.2f}%")
            logger.info("\n" + classification_report(self.y_test, y_pred))

            self.results = {
                "best_params": self.grid_search.best_params_,
                "cv_score": self.grid_search.best_score_,
                "train_accuracy": acc_train,
                "test_accuracy": acc_test,
                "classification_report": classification_report(self.y_test, y_pred, output_dict=True),
                "confusion_matrix": cm,
                "y_test": self.y_test.values,
                "y_pred": y_pred,
                "best_model": best,
            }
            self._generate_visualizations(best, acc_train, acc_test, cm, y_pred)
            return True
        except Exception as e:
            logger.error(f"Error en evaluación: {e}")
            return False

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
