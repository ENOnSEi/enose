"""
===============================================================================
CONFIGURACIÓN GLOBAL DEL PROYECTO - NARIZ ELECTRÓNICA (MEJORADA)
===============================================================================

Configuración centralizada y reproducible para todas las fases del pipeline.
Permite ajustar fácilmente parámetros sin modificar el código.

VENTAJAS:
- Rutas dinámicas (se ajustan automáticamente)
- Soporta V1 (original) y V2 (mejorada) simultáneamente
- Configuración modular por versión
- Fácil de cambiar hiperparámetros
- Validación automática de rutas

===============================================================================
"""

from pathlib import Path
from typing import Dict, List

# ============================================================================
# CONFIGURACIÓN DE RUTAS (Dinámicas)
# ============================================================================

def get_project_root() -> Path:
    """Obtiene la ruta raíz del proyecto dinámicamente."""
    return Path(__file__).parent.parent

PROJECT_ROOT = get_project_root()
DATA_RAW_DIR = PROJECT_ROOT / "datos" / "brutos"
DATA_PROCESSED_DIR = PROJECT_ROOT / "datos" / "procesados"
NOTEBOOK_DIR = PROJECT_ROOT / "cuadernos"
SRC_DIR = PROJECT_ROOT / "src"

# Crear directorios si no existen
LOGS_DIR = PROJECT_ROOT / 'registros'
for directory in [DATA_RAW_DIR, DATA_PROCESSED_DIR, NOTEBOOK_DIR, LOGS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Archivos principales
DATASET_MAESTRO_PATH = DATA_RAW_DIR / "dataset_maestro_vinos.csv"
DATASET_PROCESSED_PATH = DATA_PROCESSED_DIR / "dataset_maestro_vinos_processed.csv"

# ============================================================================
# CONFIGURACIÓN DE SENSORES
# ============================================================================

SENSOR_COLUMNS = {
    'humidity': 'Humedad_%',
    'temperature': 'Temperatura_C',
    'sensors': ['MQ3_1', 'MQ4_1', 'MQ6_1', 'MQ3_2', 'MQ4_2', 'MQ6_2']
}

SUBSTANCE_LABELS: Dict[str, str] = {
    'AQ_WINE': 'AQ',      # Vino de baja calidad
    'HQ_WINE': 'HQ',      # Vino de alta calidad
    'LQ_WINE': 'LQ',      # Vino de calidad media
    'ETHANOL': 'ETH'      # Etanol (sustancia de control)
}

# ============================================================================
# CONFIGURACIÓN DE PROCESAMIENTO - V1 (Original)
# ============================================================================

SIGNAL_PROCESSING = {
    'sampling_frequency': 18.5,      # Hz
    'smoothing_window': 9,           # Puntos para media móvil
    'baseline_seconds': 2.0,         # Segundos iniciales como línea base
    'interpolation_method': 'linear'
}

# ============================================================================
# CONFIGURACIÓN DE PROCESAMIENTO - V2 (Mejorada - MODIFICABLE)
# ============================================================================

SIGNAL_PROCESSING_V2 = {
    'sampling_frequency': 18.5,      # Hz - MODIFICABLE
    'savgol_window': 15,             # Debe ser impar - MODIFICABLE
    'savgol_polyorder': 3,           # Orden polinómio - MODIFICABLE
    'baseline_seconds': 2.0,         # Segundos - MODIFICABLE
    'time_windows': [
        (0.0, 2.0),      # Ventana 1: Línea base
        (2.0, 10.0),     # Ventana 2: Inyección
        (10.0, 20.0)     # Ventana 3: Limpieza
    ],
    'use_windowed_features': True    # Características por ventana
}

# ============================================================================
# CONFIGURACIÓN DE EXTRACCIÓN DE CARACTERÍSTICAS
# ============================================================================

FEATURE_EXTRACTION = {
    'methods': ['max', 'auc', 'slope'],
    'apply_normalization': True,
    'apply_standardization': False,
}

# ============================================================================
# CONFIGURACIÓN DE EXTRACCIÓN DE CARACTERÍSTICAS - V3
# ============================================================================

FEATURE_MODE = 'pca_signal'  # 'handcrafted' | 'pca_signal'

PCA_CONFIG = {
    'n_components': None,                   # None → usar explained_variance_threshold
    'explained_variance_threshold': 0.95,   # Varianza acumulada mínima a retener
    'whiten': False,                        # Normaliza varianza de cada componente
}

# ============================================================================
# CONFIGURACIÓN DE VALIDACIÓN Y DIVISIÓN DE DATOS
# ============================================================================

DATA_SPLIT = {
    'test_size': 0.2,
    'validation_size': 0.1,
    'random_state': 42,
    'stratified': True
}

# ============================================================================
# CONFIGURACIÓN DE MODELO ML (SVM con GridSearch)
# ============================================================================

ML_CONFIG = {
    'model_type': 'SVM',
    'n_splits_cv': 3,               # MODIFICABLE - Folds en CV
    'scoring_metric': 'accuracy',   # MODIFICABLE
    'n_jobs': -1,
    'verbose': 1
}

# Configuración Base - COMPLETAMENTE MODIFICABLE
GRID_PARAMS = [
    {
        'svm__kernel': ['linear'],
        'svm__C': [0.1, 1, 10, 100]
    },
    {
        'svm__kernel': ['rbf'],
        'svm__C': [0.1, 1, 10, 100],
        'svm__gamma': ['scale', 'auto', 0.1, 0.01]
    }
]

# Configuración Reducida (más rápido)
GRID_PARAMS_REDUCED = [
    {
        'svm__kernel': ['linear'],
        'svm__C': [1, 10]
    },
    {
        'svm__kernel': ['rbf'],
        'svm__C': [1, 10],
        'svm__gamma': ['scale', 'auto']
    }
]

# Configuración Extendida (más exhaustiva)
GRID_PARAMS_EXTENDED = [
    {
        'svm__kernel': ['linear'],
        'svm__C': [0.01, 0.1, 1, 10, 100, 1000]
    },
    {
        'svm__kernel': ['rbf'],
        'svm__C': [0.01, 0.1, 1, 10, 100, 1000],
        'svm__gamma': ['scale', 'auto', 0.001, 0.01, 0.1, 1]
    }
]

# ============================================================================
# CONFIGURACIÓN DE LOGGING
# ============================================================================

LOGGING_CONFIG = {
    'level': 'INFO',
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'log_file': PROJECT_ROOT / 'registros' / 'enose_project.log'
}

# ============================================================================
# CONFIGURACIÓN DE VISUALIZACIÓN
# ============================================================================

PLOT_CONFIG = {
    'style': 'seaborn-v0_8-darkgrid',
    'figsize': (12, 8),
    'dpi': 300,
    'save_format': 'png'
}

# ============================================================================
# HELPERS PARA CONFIGURACIÓN DINÁMICA
# ============================================================================

def get_config_for_version(version: str = 'v1') -> Dict:
    """
    Retorna la configuración de procesamiento según la versión.
    
    Parámetros:
    -----------
    version : str
        'v1' o 'v2'
    
    Retorna:
    --------
    dict
        Configuración de procesamiento
    """
    if version.lower() == 'v2':
        return SIGNAL_PROCESSING_V2
    else:
        return SIGNAL_PROCESSING


def print_config_summary() -> None:
    """Imprime un resumen de la configuración actual."""
    print("\n" + "="*70)
    print("RESUMEN DE CONFIGURACIÓN".center(70))
    print("="*70)
    print(f"\nRuta del proyecto: {PROJECT_ROOT}")
    print(f"Datos (raw): {DATA_RAW_DIR}")
    print(f"Datos (procesados): {DATA_PROCESSED_DIR}")
    print(f"\nFreq. muestreo: {SIGNAL_PROCESSING['sampling_frequency']} Hz")
    print(f"Folds CV: {ML_CONFIG['n_splits_cv']}")
    print(f"Kernels SVM: {[p['svm__kernel'] for p in GRID_PARAMS]}")
    print("="*70 + "\n")


if __name__ == '__main__':
    print_config_summary()
    print(f"\nPaths verificadas:")
    print(f"  [OK] DATA_RAW_DIR: {DATA_RAW_DIR.exists()}")
    print(f"  [OK] DATA_PROCESSED_DIR: {DATA_PROCESSED_DIR.exists()}")
    print(f"  [OK] PROJECT_ROOT: {PROJECT_ROOT.exists()}")
