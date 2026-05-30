"""
Configuración tipada del proyecto.

Usa dataclasses frozen (inmutables) para evitar mutaciones accidentales
en el runtime. Todos los parámetros están en un solo lugar — cambia aquí,
no en los módulos individuales.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Literal, Tuple


# ---------------------------------------------------------------------------
# Rutas del proyecto
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    return Path(__file__).parent.parent.parent


PROJECT_ROOT = _project_root()
DATA_RAW_DIR = PROJECT_ROOT / "datos" / "brutos"
DATA_PROCESSED_DIR = PROJECT_ROOT / "datos" / "procesados"
NOTEBOOK_DIR = PROJECT_ROOT / "cuadernos"
LOGS_DIR = PROJECT_ROOT / "registros"

# Crear directorios necesarios al importar
for _d in [DATA_RAW_DIR, DATA_PROCESSED_DIR, NOTEBOOK_DIR, LOGS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

DATASET_MAESTRO_PATH = DATA_RAW_DIR / "dataset_maestro_vinos.csv"


# ---------------------------------------------------------------------------
# Sensores y sustancias
# ---------------------------------------------------------------------------

SENSOR_COLUMNS: Dict[str, object] = {
    "humidity": "Humedad_%",
    "temperature": "Temperatura_C",
    "sensors": ["MQ3_1", "MQ4_1", "MQ6_1", "MQ3_2", "MQ4_2", "MQ6_2"],
}

SUBSTANCE_LABELS: Dict[str, str] = {
    "AQ_WINE": "AQ",
    "HQ_WINE": "HQ",
    "LQ_WINE": "LQ",
    "ETHANOL": "ETH",
}


# ---------------------------------------------------------------------------
# Configuración tipada (dataclasses)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SignalConfig:
    sampling_frequency: float = 18.5
    savgol_window: int = 15          # debe ser impar
    savgol_polyorder: int = 3
    baseline_seconds: float = 2.0
    time_windows: Tuple[Tuple[float, float], ...] = (
        (0.0, 2.0),
        (2.0, 10.0),
        (10.0, 20.0),
    )


@dataclass(frozen=True)
class PCAConfig:
    n_components: int | None = None
    explained_variance_threshold: float = 0.95
    whiten: bool = False


@dataclass(frozen=True)
class DataSplitConfig:
    test_size: float = 0.2
    random_state: int = 42
    stratified: bool = True


@dataclass(frozen=True)
class MLConfig:
    model_type: str = "SVM"
    n_splits_cv: int = 3
    # Clases desbalanceadas (LQ domina, ETH es minoritaria): 'accuracy' premiaría
    # el sesgo a la clase mayoritaria. 'balanced_accuracy' = media de los recalls
    # por clase, así la selección de hiperparámetros no ignora las clases pequeñas.
    scoring_metric: str = "balanced_accuracy"
    n_jobs: int = -1
    verbose: int = 1


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_file: Path = LOGS_DIR / "enose_project.log"


@dataclass(frozen=True)
class PlotConfig:
    style: str = "seaborn-v0_8-darkgrid"
    figsize: Tuple[int, int] = (12, 8)
    dpi: int = 300
    save_format: str = "png"


# ---------------------------------------------------------------------------
# Configuración activa del pipeline
# ---------------------------------------------------------------------------

FEATURE_MODE: Literal["handcrafted", "pca_signal"] = "pca_signal"

SIGNAL_CONFIG = SignalConfig()
PCA_CONFIG = PCAConfig()
DATA_SPLIT_CONFIG = DataSplitConfig()
ML_CONFIG = MLConfig()
LOGGING_CONFIG = LoggingConfig()
PLOT_CONFIG = PlotConfig()

# Grid search para SVM
GRID_PARAMS = [
    {"svm__kernel": ["linear"], "svm__C": [0.1, 1, 10, 100]},
    {"svm__kernel": ["rbf"], "svm__C": [0.1, 1, 10, 100], "svm__gamma": ["scale", "auto", 0.1, 0.01]},
]

GRID_PARAMS_REDUCED = [
    {"svm__kernel": ["linear"], "svm__C": [1, 10]},
    {"svm__kernel": ["rbf"], "svm__C": [1, 10], "svm__gamma": ["scale", "auto"]},
]

GRID_PARAMS_EXTENDED = [
    {"svm__kernel": ["linear"], "svm__C": [0.01, 0.1, 1, 10, 100, 1000]},
    {"svm__kernel": ["rbf"], "svm__C": [0.01, 0.1, 1, 10, 100, 1000], "svm__gamma": ["scale", "auto", 0.001, 0.01, 0.1, 1]},
]


if __name__ == "__main__":
    print(f"Project root : {PROJECT_ROOT}")
    print(f"Feature mode : {FEATURE_MODE}")
    print(f"Signal config: {SIGNAL_CONFIG}")
    print(f"ML config    : {ML_CONFIG}")
