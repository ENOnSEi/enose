"""
===============================================================================
FASE 5: ENTRENAMIENTO DEL MODELO ML CON GRID SEARCH (VERSIÓN 2)
===============================================================================

Este módulo implementa el entrenamiento y optimización del modelo SVM.

Novedades V2:
- Cálculo dinámico y seguro de `k_folds` para evitar fallos críticos
- Adaptación implícita al nuevo volumen de características (escalabilidad)

===============================================================================
"""

import pandas as pd
import numpy as np
import pickle
from pathlib import Path
from typing import Tuple, Dict, Optional
import sys
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.model_selection import StratifiedKFold, GridSearchCV, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.metrics import (
    classification_report, confusion_matrix, accuracy_score,
    precision_recall_fscore_support
)

# Importaciones correctas (mismo nivel)
from utils import setup_logging, create_output_directory, print_data_summary
from phase_4_dataset_generation import load_dataset, validate_dataset
from config import DATASET_MAESTRO_PATH, DATA_PROCESSED_DIR, ML_CONFIG, GRID_PARAMS, FEATURE_MODE

logger = setup_logging(__name__)


class ModelTrainer:
    """
    Entrena y optimiza modelos SVM para clasificación de sustancias.
    """
    
    def __init__(self, dataset_path: Path = DATASET_MAESTRO_PATH):
        self.dataset_path = Path(dataset_path)
        self.df = None
        self.X = None
        self.y = None
        self.X_train = None
        self.X_test = None
        self.y_train = None
        self.y_test = None
        self.pipeline = None
        self.grid_search = None
        self.results = {}
    
    def load_and_validate_data(self) -> bool:
        logger.info(f"Cargando dataset desde: {self.dataset_path}")
        
        if not self.dataset_path.exists():
            logger.error(f"Archivo no encontrado: {self.dataset_path}")
            return False
        
        try:
            self.df = load_dataset(self.dataset_path)
            
            if self.df is None:
                logger.error("No se pudo cargar el dataset")
                return False
            
            is_valid, issues = validate_dataset(self.df)
            if not is_valid:
                logger.warning(f"Problemas en dataset: {issues}")
            
            logger.info(" Dataset cargado y validado")
            return True
            
        except Exception as e:
            logger.error(f"Error al cargar dataset: {e}")
            return False
    
    def prepare_features(self) -> bool:
        try:
            logger.info("Preparando características...")
            exclude_cols = ['Nombre_Archivo', 'Ruta_Completa', 'Calidad_Vino']
            self.X = self.df.drop(columns=[col for col in exclude_cols if col in self.df.columns])
            self.y = self.df['Calidad_Vino']
            
            logger.info(f"Características: {self.X.shape[1]}")
            logger.info(f"Muestras: {self.X.shape[0]}")
            logger.info(f"Clases: {self.y.nunique()}")
            logger.info(f"Distribución de clases:\n{self.y.value_counts()}")
            
            return True
        except Exception as e:
            logger.error(f"Error al preparar características: {e}")
            return False
    
    def split_data(self, test_size: float = 0.2, random_state: int = 42) -> bool:
        try:
            logger.info(f"\nDividiendo datos (train={1-test_size:.0%}, test={test_size:.0%})...")
            
            self.X_train, self.X_test, self.y_train, self.y_test = train_test_split(
                self.X, self.y,
                test_size=test_size,
                random_state=random_state,
                stratify=self.y
            )
            
            logger.info(f"Entrenamiento: {len(self.X_train)} muestras")
            logger.info(f"Prueba: {len(self.X_test)} muestras")
            logger.info(f"Distribución entrenamiento:\n{self.y_train.value_counts()}")
            logger.info(f"Distribución prueba:\n{self.y_test.value_counts()}")
            
            return True
        except Exception as e:
            logger.error(f"Error al dividir datos: {e}")
            return False
    
    def build_pipeline(self) -> bool:
        try:
            logger.info("Construyendo pipeline...")
            self.pipeline = Pipeline([
                ('scaler', StandardScaler()),
                ('svm', SVC(random_state=42, probability=True))
            ])
            logger.info(" Pipeline construido: StandardScaler + SVM")
            return True
        except Exception as e:
            logger.error(f"Error al construir pipeline: {e}")
            return False
    
    def optimize_hyperparameters(self) -> bool:
        try:
            logger.info("\n" + "="*70)
            logger.info("FASE 5: Optimización de Hiperparámetros (GridSearchCV)")
            logger.info("="*70)
            
            # --- V2: Ajuste dinámico y seguro del K-Fold ---
            min_class_count = self.y_train.value_counts().min()
            target_splits = ML_CONFIG.get('n_splits_cv', 3) # Usa 3 por defecto si falla la key
            
            n_splits = min(target_splits, min_class_count)
            
            if n_splits < 2:
                logger.error("[ERROR] No hay suficientes muestras en la clase minoritaria del set de entrenamiento para realizar validacion cruzada. Se requieren al menos 2.")
                return False
                
            skf = StratifiedKFold(
                n_splits=n_splits,
                shuffle=True,
                random_state=42
            )
            
            logger.info(f"Validación cruzada: {n_splits} folds (calculado dinámicamente)")
            logger.info(f"Espacio de búsqueda: {len(GRID_PARAMS)} configuraciones base")
            
            total_combinations = sum(
                np.prod([len(v) if isinstance(v, list) else 1 for v in params.values()])
                for params in GRID_PARAMS
            )
            logger.info(f"Total de combinaciones a probar: {total_combinations}")
            
            self.grid_search = GridSearchCV(
                estimator=self.pipeline,
                param_grid=GRID_PARAMS,
                cv=skf,
                scoring=ML_CONFIG.get('scoring_metric', 'accuracy'),
                n_jobs=ML_CONFIG.get('n_jobs', -1),
                verbose=ML_CONFIG.get('verbose', 1)
            )
            
            logger.info("\nIniciando búsqueda... (esto puede tomar un tiempo)")
            self.grid_search.fit(self.X_train, self.y_train)
            
            logger.info("\n Búsqueda completada")
            return True
            
        except Exception as e:
            logger.error(f"Error en optimización de hiperparámetros: {e}", exc_info=True)
            return False
    
    def evaluate_model(self) -> bool:
        try:
            logger.info("\n" + "="*70)
            logger.info("EVALUACIÓN DEL MODELO")
            logger.info("="*70)
            
            best_model = self.grid_search.best_estimator_
            
            y_pred_train = best_model.predict(self.X_train)
            y_pred_test = best_model.predict(self.X_test)
            
            acc_train = accuracy_score(self.y_train, y_pred_train)
            acc_test = accuracy_score(self.y_test, y_pred_test)
            
            logger.info(f"\nMejores Hiperparámetros:")
            for param, value in self.grid_search.best_params_.items():
                logger.info(f"  {param}: {value}")
            
            logger.info(f"\nPrecisión Media en Validación Cruzada: {self.grid_search.best_score_*100:.2f}%")
            logger.info(f"Precisión en Entrenamiento: {acc_train*100:.2f}%")
            logger.info(f"Precisión en Prueba: {acc_test*100:.2f}%")
            
            logger.info("\nReporte de Clasificación (datos de prueba):")
            logger.info("\n" + classification_report(self.y_test, y_pred_test))
            
            logger.info("\nMatriz de Confusión (datos de prueba):")
            cm = confusion_matrix(self.y_test, y_pred_test)
            cm_df = pd.DataFrame(
                cm,
                index=[f"Real_{clase}" for clase in best_model.classes_],
                columns=[f"Pred_{clase}" for clase in best_model.classes_]
            )
            logger.info("\n" + str(cm_df))
            
            self.results = {
                'best_params': self.grid_search.best_params_,
                'cv_score': self.grid_search.best_score_,
                'train_accuracy': acc_train,
                'test_accuracy': acc_test,
                'classification_report': classification_report(self.y_test, y_pred_test, output_dict=True),
                'confusion_matrix': cm,
                'y_test': self.y_test.values,
                'y_pred': y_pred_test,
                'best_model': best_model
            }
            
            logger.info("\nGenerando visualizaciones...")
            self._generate_visualizations(best_model, acc_train, acc_test, cm)
            
            return True
            
        except Exception as e:
            logger.error(f"Error en evaluación: {e}")
            return False
    
    def _generate_visualizations(self, best_model, acc_train: float, acc_test: float, cm: np.ndarray) -> None:
        try:
            viz_dir = create_output_directory(DATA_PROCESSED_DIR / "visualizations")
            
            # 1. Matriz de Confusión
            fig, ax = plt.subplots(figsize=(8, 6))
            sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', ax=ax, cbar_kws={'label': 'Cantidad'})
            ax.set_xlabel('Predicción', fontweight='bold')
            ax.set_ylabel('Verdadero', fontweight='bold')
            ax.set_title('Matriz de Confusión - Datos de Prueba', fontweight='bold', fontsize=12)
            plt.tight_layout()
            plt.savefig(viz_dir / "01_confusion_matrix.png", dpi=300, bbox_inches='tight')
            plt.close()
            logger.info(" Matriz de confusión")
            
            # 2. Comparación de Precisiones
            fig, ax = plt.subplots(figsize=(8, 5))
            datasets = ['Entrenamiento', 'Prueba']
            accuracies = [acc_train * 100, acc_test * 100]
            colors = ['#2ecc71', '#e74c3c']
            bars = ax.bar(datasets, accuracies, color=colors, edgecolor='black', linewidth=2, alpha=0.8)
            
            for bar, acc in zip(bars, accuracies):
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                        f'{acc:.2f}%', ha='center', va='bottom', fontweight='bold', fontsize=11)
            
            ax.set_ylabel('Precisión (%)', fontweight='bold', fontsize=11)
            ax.set_title('Comparación de Precisión: Entrenamiento vs Prueba', fontweight='bold', fontsize=12)
            ax.set_ylim([0, 105])
            ax.grid(axis='y', alpha=0.3)
            plt.tight_layout()
            plt.savefig(viz_dir / "02_accuracy_comparison.png", dpi=300, bbox_inches='tight')
            plt.close()
            logger.info(" Comparación de precisiones")
            
            # 3. Reporte de clasificación
            report_dict = classification_report(self.y_test, self.results['y_pred'], output_dict=True)
            fig, ax = plt.subplots(figsize=(10, 6))
            classes = [k for k in report_dict.keys() if k not in ['accuracy', 'macro avg', 'weighted avg']]
            metrics = ['precision', 'recall', 'f1-score']
            
            x = np.arange(len(classes))
            width = 0.25
            
            for i, metric in enumerate(metrics):
                values = [report_dict[cls].get(metric, 0) for cls in classes]
                ax.bar(x + i*width, values, width, label=metric.capitalize(), alpha=0.8, edgecolor='black')
            
            ax.set_xlabel('Clase', fontweight='bold', fontsize=11)
            ax.set_ylabel('Puntuación', fontweight='bold', fontsize=11)
            ax.set_title('Reporte de Clasificación por Métrica', fontweight='bold', fontsize=12)
            ax.set_xticks(x + width)
            ax.set_xticklabels(classes)
            ax.legend()
            ax.grid(axis='y', alpha=0.3)
            plt.tight_layout()
            plt.savefig(viz_dir / "03_classification_report.png", dpi=300, bbox_inches='tight')
            plt.close()
            logger.info(" Reporte de clasificación")
            
            # 4. Distribución
            fig, axes = plt.subplots(1, 2, figsize=(12, 5))
            
            unique_true, counts_true = np.unique(self.y_test, return_counts=True)
            axes[0].bar(unique_true, counts_true, color='skyblue', edgecolor='black', alpha=0.8)
            axes[0].set_xlabel('Clase', fontweight='bold')
            axes[0].set_ylabel('Cantidad', fontweight='bold')
            axes[0].set_title('Distribución de Clases - Verdaderas', fontweight='bold')
            axes[0].grid(axis='y', alpha=0.3)
            
            unique_pred, counts_pred = np.unique(self.results['y_pred'], return_counts=True)
            axes[1].bar(unique_pred, counts_pred, color='lightcoral', edgecolor='black', alpha=0.8)
            axes[1].set_xlabel('Clase', fontweight='bold')
            axes[1].set_ylabel('Cantidad', fontweight='bold')
            axes[1].set_title('Distribución de Clases - Predichas', fontweight='bold')
            axes[1].grid(axis='y', alpha=0.3)
            
            plt.tight_layout()
            plt.savefig(viz_dir / "04_distribution_comparison.png", dpi=300, bbox_inches='tight')
            plt.close()
            logger.info("  Distribución de predicciones")
            
            logger.info(" Todas las visualizaciones generadas exitosamente")
            
        except Exception as e:
            logger.warning(f"Error al generar visualizaciones: {e}")
    
    def save_model(self, output_dir: Path = DATA_PROCESSED_DIR) -> bool:
        try:
            output_dir = Path(output_dir)
            create_output_directory(output_dir)
            
            model_path = output_dir / "best_model.pkl"
            results_path = output_dir / "training_results.pkl"
            
            with open(model_path, 'wb') as f:
                pickle.dump(self.grid_search.best_estimator_, f)
            logger.info(f" Modelo guardado en: {model_path}")

            with open(results_path, 'wb') as f:
                pickle.dump(self.results, f)
            logger.info(f" Resultados guardados en: {results_path}")

            if FEATURE_MODE == 'pca_signal':
                pca_path = DATA_PROCESSED_DIR / "pca_transformers.pkl"
                if pca_path.exists():
                    logger.info(f" PCA transformers (generados en Fase 4): {pca_path}")
                else:
                    logger.warning("FEATURE_MODE='pca_signal' pero no se encontró pca_transformers.pkl. "
                                   "Ejecuta primero la Fase 4.")

            return True
            
        except Exception as e:
            logger.error(f"Error al guardar modelo: {e}")
            return False
    
    def train(self) -> bool:
        logger.info("\n" + "="*70)
        logger.info("INICIANDO PIPELINE DE ENTRENAMIENTO")
        logger.info("="*70 + "\n")
        
        steps = [
            ("Cargando datos", self.load_and_validate_data),
            ("Preparando características", self.prepare_features),
            ("Dividiendo datos", self.split_data),
            ("Construyendo pipeline", self.build_pipeline),
            ("Optimizando hiperparámetros", self.optimize_hyperparameters),
            ("Evaluando modelo", self.evaluate_model),
            ("Guardando modelo", self.save_model)
        ]
        
        for step_name, step_func in steps:
            logger.info(f"\n>> {step_name}...")
            if not step_func():
                logger.error(f"[ERROR] Error en: {step_name}")
                return False
            logger.info(f" {step_name} completado")
        
        logger.info("\n" + "="*70)
        logger.info("[OK] ENTRENAMIENTO COMPLETADO EXITOSAMENTE")
        logger.info("="*70 + "\n")
        
        return True

def main():
    try:
        trainer = ModelTrainer()
        success = trainer.train()
        
        if success:
            logger.info("[OK] Pipeline completado exitosamente")
        else:
            logger.error("[ERROR] Error en el entrenamiento")
            sys.exit(1)

    except Exception as e:
        logger.error(f"[ERROR] Error inesperado: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()