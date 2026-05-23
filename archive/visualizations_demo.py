"""
===============================================================================
DEMO DE VISUALIZACIONES - NARIZ ELECTRÓNICA
===============================================================================

Este script demuestra las visualizaciones disponibles sin necesidad de ejecutar
el pipeline completo. Útil para familiarizarse con los gráficos antes de usar
el pipeline real.

Uso:
    python visualizations_demo.py

===============================================================================
"""

import numpy as np
import pandas as pd
from pathlib import Path
import sys

# Agregar src al path
sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    plot_signal_processing,
    plot_class_distribution,
    plot_feature_statistics,
    plot_correlation_heatmap,
    create_output_directory,
    setup_logging
)

logger = setup_logging(__name__)


def create_demo_dataset(n_samples: int = 150) -> pd.DataFrame:
    """
    Crea un dataset de demostración con características sintéticas.
    
    Parámetros:
    -----------
    n_samples : int
        Número de muestras a generar
    
    Retorna:
    --------
    pd.DataFrame
        Dataset de demostración
    """
    logger.info(f"Generando dataset de demostración ({n_samples} muestras)...")
    
    np.random.seed(42)
    
    # Generar datos para 3 clases
    data = []
    
    # Clase AQ - valores típicos
    for i in range(n_samples // 3):
        data.append({
            'Nombre_Archivo': f'AQ_Wine{i:02d}.txt',
            'Calidad_Vino': 'AQ',
            'MQ3_1_max': 0.45 + np.random.normal(0, 0.05),
            'MQ3_1_auc': 12.3 + np.random.normal(0, 1),
            'MQ3_1_slope': 0.78 + np.random.normal(0, 0.1),
            'MQ4_1_max': 0.52 + np.random.normal(0, 0.06),
            'MQ4_1_auc': 14.1 + np.random.normal(0, 1.2),
            'MQ4_1_slope': 0.85 + np.random.normal(0, 0.12),
        })
    
    # Clase HQ - valores diferentes
    for i in range(n_samples // 3):
        data.append({
            'Nombre_Archivo': f'HQ_Wine{i:02d}.txt',
            'Calidad_Vino': 'HQ',
            'MQ3_1_max': 0.65 + np.random.normal(0, 0.05),
            'MQ3_1_auc': 18.5 + np.random.normal(0, 1),
            'MQ3_1_slope': 0.95 + np.random.normal(0, 0.1),
            'MQ4_1_max': 0.72 + np.random.normal(0, 0.06),
            'MQ4_1_auc': 20.2 + np.random.normal(0, 1.2),
            'MQ4_1_slope': 1.05 + np.random.normal(0, 0.12),
        })
    
    # Clase LQ - valores intermedios
    for i in range(n_samples - 2 * (n_samples // 3)):
        data.append({
            'Nombre_Archivo': f'LQ_Wine{i:02d}.txt',
            'Calidad_Vino': 'LQ',
            'MQ3_1_max': 0.55 + np.random.normal(0, 0.05),
            'MQ3_1_auc': 15.4 + np.random.normal(0, 1),
            'MQ3_1_slope': 0.87 + np.random.normal(0, 0.1),
            'MQ4_1_max': 0.62 + np.random.normal(0, 0.06),
            'MQ4_1_auc': 17.1 + np.random.normal(0, 1.2),
            'MQ4_1_slope': 0.95 + np.random.normal(0, 0.12),
        })
    
    df = pd.DataFrame(data)
    logger.info(f"✓ Dataset creado: {df.shape[0]} muestras, {df.shape[1]} características")
    
    return df


def demo_signal_visualization():
    """
    Demuestra la visualización de procesamiento de señal.
    """
    logger.info("\n" + "="*70)
    logger.info("DEMO 1: Visualización de Procesamiento de Señal")
    logger.info("="*70)
    
    # Generar señal de demostración
    t = np.linspace(0, 10, 1000)
    # Señal: componente base + sinusoide + ruido
    signal_raw = 100 + 40 * np.sin(2 * np.pi * 0.5 * t) + np.random.normal(0, 8, len(t))
    
    # Simular procesamiento
    from phase_1_3_feature_extraction import SignalProcessor
    processor = SignalProcessor()
    signal_smoothed, signal_normalized = processor.process_signal(signal_raw)
    
    # Crear carpeta de output
    output_dir = create_output_directory(Path("demo_visualizations"))
    
    # Generar gráfica
    plot_signal_processing(
        signal_raw=signal_raw,
        signal_smoothed=signal_smoothed,
        signal_normalized=signal_normalized,
        time_axis=t,
        title="DEMO: Procesamiento de Señal de Sensor",
        output_path=output_dir / "demo_signal_processing.png"
    )
    
    logger.info(f"✓ Gráfica guardada en: demo_visualizations/demo_signal_processing.png")


def demo_dataset_visualizations():
    """
    Demuestra las visualizaciones del dataset.
    """
    logger.info("\n" + "="*70)
    logger.info("DEMO 2: Visualizaciones del Dataset")
    logger.info("="*70)
    
    # Crear dataset de demostración
    df = create_demo_dataset(150)
    
    # Crear carpeta de output
    output_dir = create_output_directory(Path("demo_visualizations"))
    
    # Gráfica 1: Distribución de clases
    logger.info("\nGenerando gráfica de distribución de clases...")
    plot_class_distribution(
        df,
        label_column='Calidad_Vino',
        output_path=output_dir / "demo_class_distribution.png"
    )
    logger.info("✓ class_distribution.png")
    
    # Gráfica 2: Estadísticas de características
    logger.info("Generando gráfica de estadísticas de características...")
    feature_cols = [col for col in df.columns if col.endswith('_max') or col.endswith('_auc')]
    plot_feature_statistics(
        df,
        feature_columns=feature_cols[:6],
        output_path=output_dir / "demo_feature_statistics.png"
    )
    logger.info("✓ feature_statistics.png")
    
    # Gráfica 3: Matriz de correlación
    logger.info("Generando matriz de correlación...")
    plot_correlation_heatmap(
        df,
        output_path=output_dir / "demo_correlation_heatmap.png",
        figsize=(10, 8)
    )
    logger.info("✓ correlation_heatmap.png")


def demo_model_visualizations():
    """
    Demuestra las visualizaciones del modelo.
    """
    import matplotlib.pyplot as plt
    import seaborn as sns
    
    logger.info("\n" + "="*70)
    logger.info("DEMO 3: Visualizaciones del Modelo")
    logger.info("="*70)
    
    output_dir = create_output_directory(Path("demo_visualizations"))
    
    # Crear datos simulados
    y_true = np.array(['AQ', 'HQ', 'LQ', 'AQ', 'HQ', 'LQ', 'AQ', 'HQ', 'LQ', 'AQ',
                       'AQ', 'HQ', 'LQ', 'AQ', 'HQ', 'LQ', 'AQ', 'HQ', 'LQ', 'AQ'])
    y_pred = np.array(['AQ', 'HQ', 'LQ', 'AQ', 'HQ', 'LQ', 'AQ', 'HQ', 'AQ', 'LQ',
                       'AQ', 'HQ', 'LQ', 'LQ', 'HQ', 'LQ', 'AQ', 'HQ', 'LQ', 'AQ'])
    
    # 1. Matriz de confusión
    logger.info("Generando matriz de confusión...")
    from sklearn.metrics import confusion_matrix
    cm = confusion_matrix(y_true, y_pred, labels=['AQ', 'HQ', 'LQ'])
    
    fig, ax = plt.subplots(figsize=(8, 6))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', ax=ax,
               xticklabels=['AQ', 'HQ', 'LQ'],
               yticklabels=['AQ', 'HQ', 'LQ'],
               cbar_kws={'label': 'Cantidad'})
    ax.set_xlabel('Predicción', fontweight='bold')
    ax.set_ylabel('Verdadero', fontweight='bold')
    ax.set_title('DEMO: Matriz de Confusión', fontweight='bold', fontsize=12)
    plt.tight_layout()
    plt.savefig(output_dir / "demo_confusion_matrix.png", dpi=300)
    plt.close()
    logger.info("✓ confusion_matrix.png")
    
    # 2. Comparación de precisiones
    logger.info("Generando comparación de precisiones...")
    acc_train = 0.92
    acc_test = 0.85
    
    fig, ax = plt.subplots(figsize=(8, 5))
    datasets = ['Entrenamiento', 'Prueba']
    accuracies = [acc_train * 100, acc_test * 100]
    colors = ['#2ecc71', '#e74c3c']
    bars = ax.bar(datasets, accuracies, color=colors, edgecolor='black', linewidth=2, alpha=0.8)
    
    for bar, acc in zip(bars, accuracies):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
               f'{acc:.1f}%', ha='center', va='bottom', fontweight='bold', fontsize=11)
    
    ax.set_ylabel('Precisión (%)', fontweight='bold')
    ax.set_title('DEMO: Comparación de Precisión', fontweight='bold', fontsize=12)
    ax.set_ylim([0, 105])
    ax.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / "demo_accuracy_comparison.png", dpi=300)
    plt.close()
    logger.info("✓ accuracy_comparison.png")


def main():
    """
    Ejecuta las demostraciones.
    """
    print("\n" + "="*70)
    print("DEMOSTRACIÓN DE VISUALIZACIONES - NARIZ ELECTRÓNICA".center(70))
    print("="*70 + "\n")
    
    logger.info("Iniciando demostraciones de visualizaciones...\n")
    
    try:
        # Demo 1: Visualización de señal
        demo_signal_visualization()
        
        # Demo 2: Visualizaciones del dataset
        demo_dataset_visualizations()
        
        # Demo 3: Visualizaciones del modelo
        demo_model_visualizations()
        
        logger.info("\n" + "="*70)
        logger.info("✅ DEMOSTRACIONES COMPLETADAS")
        logger.info("="*70)
        logger.info("\nTodas las gráficas se han guardado en: demo_visualizations/")
        logger.info("\nPrueba estas gráficas para familiarizarte con los outputs")
        logger.info("del pipeline completo (python main.py)\n")
        
    except Exception as e:
        logger.error(f"❌ Error en demostración: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
