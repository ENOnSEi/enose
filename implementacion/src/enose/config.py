"""
Configuración tipada del proyecto.

Usa dataclasses frozen (inmutables) para evitar mutaciones accidentales
en el runtime. Todos los parámetros están en un solo lugar — cambia aquí,
no en los módulos individuales.

Formato de datos
----------------
Los datos crudos son CSV producidos por el `serial-reader` a partir del
Arduino (`analog-reader-arduino/4sensor-basic.ino`). Cada CSV es UNA grabación
continua de una mezcla. Cabecera:

    data,v20,v11,v02,v00,estado

  - data   : timestamp en ms (Arduino millis(), ~250 ms entre muestras → 4 Hz)
  - v20    : sensor TGS2620
  - v11    : sensor TGS2611
  - v02    : sensor TGS2602
  - v00    : sensor TGS2600
  - estado : fase del experimento — 'inicio' (calentamiento, se descarta),
             'base' (línea base / aire limpio → R0) y 'medicion' (respuesta al
             estímulo → señal a caracterizar).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Literal, Tuple


# ---------------------------------------------------------------------------
# Rutas del proyecto
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    # .../implementacion/src/enose/config.py → .../implementacion
    return Path(__file__).parent.parent.parent


PROJECT_ROOT = _project_root()
REPO_ROOT = PROJECT_ROOT.parent                  # raíz del repositorio (Electronic Nose Project)

# Los CSV crudos del serial-reader viven en la carpeta 'datasets/' de la raíz.
DATA_RAW_DIR = REPO_ROOT / "datasets"
DATA_PROCESSED_DIR = PROJECT_ROOT / "datos" / "procesados"
NOTEBOOK_DIR = PROJECT_ROOT / "cuadernos"
LOGS_DIR = PROJECT_ROOT / "registros"
REPORTS_DIR = PROJECT_ROOT / "informes"   # informes de ejecución con timestamp (en .gitignore)

# Crear directorios necesarios al importar (DATA_RAW_DIR se asume existente:
# es la carpeta donde el usuario deposita las grabaciones).
for _d in [DATA_PROCESSED_DIR, NOTEBOOK_DIR, LOGS_DIR, REPORTS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# El dataset maestro (salida de la Fase 4) se guarda junto a los procesados.
DATASET_MAESTRO_PATH = DATA_PROCESSED_DIR / "dataset_maestro.csv"


# ---------------------------------------------------------------------------
# Sensores, fases y sustancias
# ---------------------------------------------------------------------------

# Columnas del CSV crudo.
TIMESTAMP_COLUMN = "data"      # ms desde el arranque del Arduino
STATE_COLUMN = "estado"        # inicio | base | medicion

# Fases del experimento (valores de la columna 'estado').
WARMUP_STATE = "inicio"        # calentamiento del sensor → se descarta
BASELINE_STATE = "base"        # aire limpio → de aquí sale R0
MEASUREMENT_STATE = "medicion"  # respuesta al estímulo → señal a caracterizar

# Sensores TGS. Las claves son los nombres de columna del CSV; el valor, el
# modelo físico (para etiquetas legibles en gráficas y documentación).
SENSOR_MODELS: Dict[str, str] = {
    "v20": "TGS2620",
    "v11": "TGS2611",
    "v02": "TGS2602",
    "v00": "TGS2600",
}

SENSOR_COLUMNS: Dict[str, object] = {
    "timestamp": TIMESTAMP_COLUMN,
    "state": STATE_COLUMN,
    "sensors": list(SENSOR_MODELS.keys()),   # ['v20', 'v11', 'v02', 'v00']
}

SENSOR_RATIO_PAIRS: List[Tuple[str, str]] = [
    ("v20", "v11"),   # alcoholes/solventes vs metano
    ("v00", "v02"),   # contaminantes generales vs VOCs
    ("v20", "v02"),   # etanol vs VOCs
    ("v11", "v00"),   # metano vs contaminantes
]

# Etiqueta de clase por nombre de fichero (sin extensión, en minúsculas).
# El valor describe la mezcla. Para una grabación cuyo nombre no esté aquí, se
# usa el propio nombre del fichero como etiqueta (ver io.reader.extract_substance_label).
SUBSTANCE_LABELS: Dict[str, str] = {
    "agua": "Agua",                       # 100% agua
    "alcohol": "Alcohol",                 # 100% alcohol etílico
    "vino": "Vino",                       # 100% vino (12.5º)
    "vinoyagua": "Vino+Agua",             # 50% vino + 50% agua
    "vinoagitacionrara": "Vino+Alcohol",  # 50% vino + 50% alcohol etílico
}

# Nombres de las columnas no-feature del dataset maestro.
FILENAME_COLUMN = "Nombre_Archivo"
LABEL_COLUMN = "Etiqueta"
# Unidad de agrupación para la validación cruzada (p. ej. "sample_12"). La
# rellena train_from_api.py con el Sample de la API; los CSV legacy no la tienen.
GROUP_COLUMN = "Grupo"
NON_FEATURE_COLUMNS = {FILENAME_COLUMN, LABEL_COLUMN, GROUP_COLUMN}

# Qué se considera "la misma medición" al partir train/test. Todas las filas de
# un mismo grupo caen siempre en el mismo lado del split.
#   'sample'    : grupo = Sample de la API (todas sus reps juntas). Las reps de
#                 una tanda comparten día, deriva y humedad; separarlas entre
#                 train y test infla la accuracy (mide repetibilidad, no
#                 generalización). Es el modo honesto y el por defecto.
#   'recording' : grupo = cada grabación/rep por separado (comportamiento
#                 anterior). Solo para comparar: da una cifra optimista.
# Si el dataset no trae GROUP_COLUMN (CSV legacy), 'sample' cae a 'recording':
# allí cada CSV es a la vez una grabación y una tanda.
GROUP_BY: Literal["sample", "recording"] = "sample"


# ---------------------------------------------------------------------------
# Configuración tipada (dataclasses)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SignalConfig:
    # El Arduino muestrea cada 250 ms → 4 Hz.
    sampling_frequency: float = 4.0
    savgol_window: int = 9           # debe ser impar; ~2 s a 4 Hz
    savgol_polyorder: int = 3
    # Fallback de línea base cuando una grabación no tiene fase 'base':
    # se usan los primeros `baseline_seconds` de la propia señal.
    baseline_seconds: float = 2.0
    # Ventanas temporales (segundos) relativas al inicio de la fase 'medicion'.
    time_windows: Tuple[Tuple[float, float], ...] = (
        (0.0, 5.0),
        (5.0, 15.0),
        (15.0, 40.0),
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
    # 'balanced_accuracy' = media de los recalls por clase: si las mezclas quedan
    # desbalanceadas, la selección de hiperparámetros no ignora las clases pequeñas.
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

# 'handcrafted' : un vector de características por grabación (max, AUC, slope por
#                 ventana). Es el modo por defecto: con una grabación = una muestra
#                 produce features deterministas sin necesidad de ajustar un PCA.
# 'pca_signal'  : serializa los segmentos crudos por (sensor × ventana) y ajusta el
#                 PCA dentro del Pipeline de la Fase 5. Pensado para cuando haya
#                 muchas grabaciones (p. ej. ventaneando la fase 'medicion', ver
#                 pipeline/dataset.py).
FEATURE_MODE: Literal["handcrafted", "pca_signal"] = "handcrafted"

# Clasificador activo en el pipeline de la Fase 5. El paso del Pipeline se llama
# siempre 'clf', así que las rejillas usan el prefijo 'clf__'.
#   'lda' : LinearDiscriminantAnalysis con shrinkage — ganador del harness
#           (compare_models.py) con los datos actuales. Clásico de e-nose/quimiometría
#           para pocas muestras y features colineales.
#   'svm' : SVC (linear/rbf), el modelo anterior.
# Para comparar todos y elegir, usar compare_models.py.
CLASSIFIER: Literal["lda", "svm"] = "lda"

SIGNAL_CONFIG = SignalConfig()
PCA_CONFIG = PCAConfig()
DATA_SPLIT_CONFIG = DataSplitConfig()
ML_CONFIG = MLConfig()
LOGGING_CONFIG = LoggingConfig()
PLOT_CONFIG = PlotConfig()

# Rejillas de hiperparámetros por clasificador (prefijo 'clf__' = paso del Pipeline).
GRID_PARAMS_BY_CLASSIFIER: Dict[str, list] = {
    "lda": [
        {"clf__shrinkage": ["auto", 0.1, 0.3, 0.5, 0.7, 0.9]},
    ],
    "svm": [
        {"clf__kernel": ["linear"], "clf__C": [0.1, 1, 10, 100]},
        {"clf__kernel": ["rbf"], "clf__C": [0.1, 1, 10, 100], "clf__gamma": ["scale", "auto", 0.1, 0.01]},
    ],
}

# Rejilla activa (la que consume el ModelTrainer).
GRID_PARAMS = GRID_PARAMS_BY_CLASSIFIER[CLASSIFIER]


if __name__ == "__main__":
    print(f"Project root : {PROJECT_ROOT}")
    print(f"Raw data dir : {DATA_RAW_DIR}")
    print(f"Feature mode : {FEATURE_MODE}")
    print(f"Sensores     : {SENSOR_COLUMNS['sensors']}  ({SENSOR_MODELS})")
    print(f"Signal config: {SIGNAL_CONFIG}")
    print(f"ML config    : {ML_CONFIG}")
