# Modules Reference — enose package

Referencia completa de las clases y funciones del paquete `src/enose/`.

---

## Estructura del paquete

```
src/enose/
├── config.py          # Configuración tipada (dataclasses)
├── utils.py           # Logging, validación, visualización
├── io/
│   └── reader.py      # Ingesta de archivos de sensor
├── signal/
│   └── processor.py   # Procesamiento de señal (SignalProcessor)
├── features/
│   ├── perkey_pca.py  # PerKeyPCA — transformer sklearn (pipeline activo)
│   ├── pca.py         # PCAFeatureExtractor — cumple SignalExtractorProtocol
│   └── handcrafted.py # HandcraftedExtractor
├── model/
│   └── trainer.py     # ModelTrainer
└── pipeline/
    └── dataset.py     # DatasetGenerator + helpers
```

---

## `enose.config`

Configuración centralizada como dataclasses frozen (inmutables).

### Dataclasses

```python
@dataclass(frozen=True)
class SignalConfig:
    sampling_frequency: float = 4.0    # Hz (250 ms entre muestras)
    savgol_window: int = 9             # debe ser impar
    savgol_polyorder: int = 3
    baseline_seconds: float = 2.0      # fallback si no hay fase 'base'
    time_windows: tuple = ((0,5), (5,15), (15,40))   # s desde el inicio de 'medicion'

@dataclass(frozen=True)
class PCAConfig:
    n_components: int | None = None
    explained_variance_threshold: float = 0.95
    whiten: bool = False

@dataclass(frozen=True)
class MLConfig:
    model_type: str = 'SVM'
    n_splits_cv: int = 3
    scoring_metric: str = 'balanced_accuracy'
    n_jobs: int = -1
```

### Constantes activas

```python
FEATURE_MODE: Literal['handcrafted', 'pca_signal'] = 'handcrafted'
SIGNAL_CONFIG = SignalConfig()
PCA_CONFIG    = PCAConfig()
ML_CONFIG     = MLConfig()
GRID_PARAMS   = [...]   # BASE | GRID_PARAMS_REDUCED | GRID_PARAMS_EXTENDED
```

### Rutas

```python
PROJECT_ROOT         # .../implementacion
REPO_ROOT            # raíz del repositorio
DATA_RAW_DIR         # <repo>/datasets/  (grabaciones .csv)
DATA_PROCESSED_DIR   # datos/procesados/
DATASET_MAESTRO_PATH # datos/procesados/dataset_maestro.csv
```

---

## `enose.io.reader`

### `load_sensor_file(file_path: Path) -> Optional[pd.DataFrame]`

Carga una grabación CSV (cabecera `data,v20,v11,v02,v00,estado`).
Retorna `None` si el archivo no existe o le faltan columnas esperadas.

### `get_files_recursive(directory, pattern='*.csv') -> List[Path]`

Busca grabaciones recursivamente. Ejemplo: `get_files_recursive(DATA_RAW_DIR, "*.csv")`.

### `extract_substance_label(filename: str) -> Optional[str]`

Deriva la etiqueta de mezcla del nombre del fichero (coincidencia exacta del
nombre sin extensión contra `SUBSTANCE_LABELS`; si no está, usa el propio nombre).

```python
extract_substance_label("vino.csv")              # → 'Vino'
extract_substance_label("vinoyagua.csv")         # → 'Vino+Agua'
extract_substance_label("vinoagitacionrara.csv") # → 'Vino+Alcohol'
extract_substance_label("mezcla_nueva.csv")      # → 'mezcla_nueva' (fallback)
```

### `get_baseline_and_signal(df, sensor) -> Optional[tuple]`

Devuelve `(baseline, signal)` para un sensor: valores de la fase `base` (R0) y
de la fase `medicion` (respuesta). `None` si no hay fase `medicion`.

---

## `enose.signal.processor.SignalProcessor`

Implementa `SignalProcessorProtocol`. Parámetros configurables via `SignalConfig`.

```python
processor = SignalProcessor()                    # usa SIGNAL_CONFIG por defecto
processor = SignalProcessor(config=my_config)   # config personalizada
```

### Métodos

```python
smooth_signal(signal: np.ndarray) -> np.ndarray
# Suavizado Savitzky-Golay. Preserva la forma de los picos.

normalize_by_baseline(signal, baseline=None) -> np.ndarray
# Normalización fraccional: (R0 - Rs) / R0
# R0 = media de `baseline` (fase 'base'); si no se aporta, primeras muestras

process_signal(signal, baseline=None) -> Tuple[np.ndarray, np.ndarray]
# Retorna (señal_suavizada, señal_normalizada)

extract_features(signal: np.ndarray) -> Dict[str, float]
# Extrae {max, auc, slope} por cada ventana temporal.
# Claves: 'w{start}-{end}_max', 'w{start}-{end}_auc', 'w{start}-{end}_slope'

get_signal_segments(signal: np.ndarray) -> Dict[str, np.ndarray]
# Retorna el array de señal por ventana (para modo PCA).
# Claves: 'w{start}-{end}'
```

---

## `enose.features.perkey_pca.PerKeyPCA` ← **pipeline activo**

Transformer sklearn (`BaseEstimator` + `TransformerMixin`) que ajusta un PCA independiente por cada clave `{sensor}_{ventana}`. Se coloca como primer paso del Pipeline de la Fase 5 y se reajusta solo sobre los datos de entrenamiento en cada fold de la CV — sin data leakage.

```python
from enose.features.perkey_pca import PerKeyPCA
from enose.config import PCAConfig

transformer = PerKeyPCA()                         # usa PCA_CONFIG por defecto
transformer = PerKeyPCA(config=PCAConfig(explained_variance_threshold=0.90))
```

### Formato de entrada esperado

Un `pd.DataFrame` con columnas `{sensor}_{ventana}__t{idx}` (generadas por la Fase 4):

```
v20_w0-5__t000, v20_w0-5__t001, ..., v11_w5-15__t000, ...
```

### Flujo sklearn

```python
from sklearn.pipeline import Pipeline

pipe = Pipeline([
    ("pca",    PerKeyPCA()),
    ("scaler", StandardScaler()),
    ("svm",    SVC()),
])
pipe.fit(X_train, y_train)   # PCA ajustado solo sobre X_train
pipe.predict(X_test)         # PCA transforma X_test sin haberlo visto
```

### Diagnóstico

```python
transformer.fit(X_train)
summary = transformer.explained_variance_summary()  # {key: np.ndarray de ratios}
names   = transformer.get_feature_names_out()       # ['v20_w0-5_pc1', ...]
```

---

## `enose.features.pca.PCAFeatureExtractor`

Implementa `SignalExtractorProtocol`. Se mantiene para los tests de contrato pero **ya no participa en el pipeline activo** (sustituido por `PerKeyPCA`). Su API sigue siendo válida.

```python
extractor = PCAFeatureExtractor()
extractor.fit(all_segments)   # {'{sensor}_{ventana}': [array, ...]}
scores = extractor.transform(segment, key='v20_w5-15')
summary = extractor.explained_variance_summary()
```

---

## `enose.features.handcrafted.HandcraftedExtractor`

Implementa `HandcraftedExtractorProtocol`. No requiere fase de ajuste.

```python
extractor = HandcraftedExtractor()

# Por señal individual
features = extractor.extract(normalized_signal, sensor_name='v20')
# → {'v20_w0-5_max': ..., 'v20_w5-15_auc': ..., ...}

# Por grabación completa (toma R0 de 'base' y señal de 'medicion' por sensor)
features = extractor.extract_from_file_data(df_raw)
# → dict con todas las features de todos los sensores
```

---

## `enose.pipeline.dataset.DatasetGenerator`

Orquesta la generación del dataset maestro.

```python
gen = DatasetGenerator(data_dir=DATA_RAW_DIR)
df = gen.generate_dataset(output_path=DATASET_MAESTRO_PATH)
```

Detecta automáticamente el modo (`FEATURE_MODE`) y ejecuta la estrategia correspondiente:
- `handcrafted`: una pasada, extrae estadísticos directamente (max, AUC, slope por ventana)
- `pca_signal`: dos pasadas — calcula longitudes fijas de segmento, serializa los segmentos crudos como columnas `{sensor}_{ventana}__t{idx}`. El PCA se ajusta más tarde en la Fase 5 (dentro del Pipeline, solo sobre train).

### Funciones auxiliares

```python
validate_dataset(df) -> Tuple[bool, List[str]]
# Verifica columnas requeridas, features suficientes, ausencia de NaN

load_dataset(path) -> Optional[pd.DataFrame]
# Carga y valida un CSV de dataset
```

---

## `enose.model.trainer.ModelTrainer`

Entrenamiento end-to-end del modelo SVM.

```python
trainer = ModelTrainer(dataset_path=DATASET_MAESTRO_PATH)
success = trainer.train()   # ejecuta todos los pasos en secuencia
```

### Pasos internos

```python
trainer.load_and_validate_data()   # carga el CSV
trainer.prepare_features()          # separa X e y, deriva grupos (grabación)
trainer.split_data()                # split por grupos (StratifiedGroupKFold)
trainer.build_pipeline()            # [PerKeyPCA ->] StandardScaler -> SVC
trainer.optimize_hyperparameters()  # GridSearchCV + StratifiedGroupKFold (con groups)
trainer.evaluate_model()            # métricas + visualizaciones
trainer.save_model()                # best_model.pkl + training_results.pkl
```

### Resultados

```python
trainer.results = {
    'best_params': {...},
    'cv_score': float,
    'cv_scoring_metric': str,          # 'balanced_accuracy'
    'train_accuracy': float,
    'test_accuracy': float,
    'test_balanced_accuracy': float,   # honesto con clases desbalanceadas
    'classification_report': {...},
    'confusion_matrix': np.ndarray,
    'y_test': np.ndarray,
    'y_pred': np.ndarray,
    'best_model': sklearn.Pipeline,
}
```

---

## Spec — Contratos y Schemas

### Protocols (`spec/contracts/`)

Los Protocols definen qué métodos debe implementar cada tipo de componente.
Se verifican con `isinstance(obj, Protocol)` gracias a `@runtime_checkable`.

```python
from spec.contracts import (
    SignalProcessorProtocol,
    HandcraftedExtractorProtocol,
    SignalExtractorProtocol,
    ClassifierProtocol,
)

assert isinstance(SignalProcessor(), SignalProcessorProtocol)       # True
assert isinstance(PCAFeatureExtractor(), SignalExtractorProtocol)   # True (tras fit)
```

### Schemas (`spec/schemas/`)

Los schemas Pydantic validan datos en las fronteras del sistema.

```python
from spec.schemas import SensorReading, FeatureVector, Prediction

# Valida al construir — lanza ValueError si los datos son inválidos
reading = SensorReading(
    filename="vino.csv",
    substance_label="Vino",        # no puede estar vacío
    sensor_data={sensor: values for sensor in EXPECTED_SENSORS},  # v20, v11, v02, v00
)

fv = FeatureVector(
    filename="vino.csv",
    substance_label="Vino",
    features={"v20_w0-5_max": 0.42, ...},  # no puede estar vacío
)

pred = Prediction(
    filename="vino.csv",
    predicted_class="Vino",   # no puede estar vacío
    confidence=0.95,          # debe estar en [0, 1]
)
```
