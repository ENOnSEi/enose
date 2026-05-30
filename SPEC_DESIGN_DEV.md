# Sistema Specification → Design → Development

Este documento explica la metodología de tres capas que estructura todo el código del Electronic Nose Project y cómo trabajar con ella en la práctica.

---

## El problema que resuelve

En un proyecto de ML/señal es fácil acabar con un notebook monolítico donde la lectura de datos, el procesamiento y el entrenamiento están entremezclados. Cuando hay que cambiar algo (el clasificador, la forma de normalizar la señal, el formato de los datos) es difícil saber qué toca y qué puede romperse.

El sistema Spec → Design → Dev separa tres preguntas distintas:

1. **¿Qué tiene que hacer cada componente?** → *Spec*
2. **¿Por qué está diseñado así y no de otra forma?** → *Design*
3. **¿Cómo lo hace concretamente?** → *Dev*

---

## Las tres capas

| Capa | Carpeta | Propósito |
|------|---------|-----------|
| **Spec** | `spec/contracts/` | Protocolos Python (`typing.Protocol`) — interfaces sin implementación |
| **Spec** | `spec/schemas/` | Modelos Pydantic — validación de datos en las fronteras del sistema |
| **Design** | `design/adr/` | Architecture Decision Records — decisiones con contexto y razonamiento |
| **Dev** | `src/enose/` | Implementaciones reales, organizadas por dominio |

---

## Capa 1 — Spec: los contratos

### 1a. Contratos (`spec/contracts/`)

Un contrato es un `typing.Protocol` de Python: declara qué métodos y atributos debe tener un componente, pero no dice cómo implementarlos. Es el equivalente a una interfaz en Java o C#.

**¿Por qué Protocols y no clases abstractas?**  
Con `Protocol` no es necesario heredar de nada. Cualquier clase que tenga los métodos correctos satisface el contrato automáticamente (*structural subtyping* o *duck typing* con verificación estática). Esto hace que el pipeline no dependa de sklearn, ni de ninguna librería concreta.

#### Ejemplo: `spec/contracts/processor.py`

```python
@runtime_checkable
class SignalProcessorProtocol(Protocol):
    sampling_frequency: float

    def smooth_signal(self, signal: np.ndarray) -> np.ndarray: ...
    def normalize_by_baseline(self, signal: np.ndarray) -> np.ndarray: ...
    def process_signal(self, signal: np.ndarray) -> Tuple[np.ndarray, np.ndarray]: ...
    def extract_features(self, signal: np.ndarray) -> Dict[str, float]: ...
    def get_signal_segments(self, signal: np.ndarray) -> Dict[str, np.ndarray]: ...
```

Este archivo responde: *"cualquier procesador de señal en este proyecto debe ser capaz de suavizar, normalizar, extraer características y segmentar"*. No dice nada sobre Savitzky-Golay, ni sobre ventanas temporales, ni sobre R0. Esos son detalles de implementación.

#### Ejemplo: `spec/contracts/extractor.py`

Hay dos contratos diferenciados porque hay dos tipos de extractor con necesidades distintas:

```python
class HandcraftedExtractorProtocol(Protocol):
    # No requiere ajuste previo; las características son deterministas
    def extract(self, normalized_signal: np.ndarray, sensor_name: str) -> Dict[str, float]: ...

class SignalExtractorProtocol(Protocol):
    # Requiere fit() antes de transform() — aprende del dataset
    is_fitted: bool
    def fit(self, all_segments: Dict[str, List[np.ndarray]]) -> None: ...
    def transform(self, segment: np.ndarray, key: str) -> np.ndarray: ...
    def save(self, path: Path) -> None: ...
```

El hecho de separar los dos contratos documenta una decisión de diseño importante: los extractores estadísticos (max, AUC, slope) no tienen estado, pero los extractores basados en PCA sí (necesitan ajustarse primero).

#### Ejemplo: `spec/contracts/classifier.py`

```python
class ClassifierProtocol(Protocol):
    classes_: np.ndarray
    def fit(self, X: np.ndarray, y: np.ndarray) -> "ClassifierProtocol": ...
    def predict(self, X: np.ndarray) -> np.ndarray: ...
    def predict_proba(self, X: np.ndarray) -> np.ndarray: ...
    def score(self, X: np.ndarray, y: np.ndarray) -> float: ...
```

El pipeline de entrenamiento usa `ClassifierProtocol`, no `sklearn.svm.SVC`. Esto significa que se puede sustituir el SVC por un RandomForest o una red neuronal sin tocar el orquestador, siempre que la nueva clase implemente estos cuatro métodos.

---

### 1b. Schemas (`spec/schemas/`)

Un schema es un modelo Pydantic que valida los datos que viajan entre componentes. Los schemas viven en los **bordes del sistema**: donde entran datos externos (archivos de sensor), donde se produce una transformación importante (extracción de features), o donde salen resultados (predicción).

La regla es: **validar en la frontera, confiar dentro**. Una vez que un objeto `SensorReading` ha sido construido correctamente, el resto del pipeline no necesita volver a comprobar si los sensores esperados existen o si la etiqueta es válida.

#### Ejemplo: flujo completo de datos a través de schemas

```
Archivo .txt  →  SensorReading  →  FeatureVector  →  Prediction
   (disco)       (entrada)       (procesamiento)     (salida)
```

**`spec/schemas/sensor_reading.py`** — entrada al pipeline:

```python
class SensorReading(BaseModel):
    filename: str
    substance_label: str               # validado: debe ser AQ, HQ, LQ o ETH
    sensor_data: Dict[str, List[float]] # validado: deben existir los 6 sensores MQ
    humidity: List[float] = []
    temperature: List[float] = []

    @field_validator("substance_label")
    def validate_label(cls, v):
        if v not in {"AQ", "HQ", "LQ", "ETH"}:
            raise ValueError(...)
        return v

    @field_validator("sensor_data")
    def validate_sensors(cls, v):
        missing = {"MQ3_1", "MQ4_1", "MQ6_1", "MQ3_2", "MQ4_2", "MQ6_2"} - v.keys()
        if missing:
            raise ValueError(f"Faltan sensores: {missing}")
        return v
```

Si un archivo está mal formado, el error se lanza aquí, no en mitad del cálculo de features.

**`spec/schemas/feature_vector.py`** — frontera entre extracción y ML:

```python
class FeatureVector(BaseModel):
    filename: str
    substance_label: str
    features: Dict[str, float]  # '{sensor}_{ventana}_{metrica_o_pc}' -> valor

    @field_validator("features")
    def validate_non_empty(cls, v):
        if not v:
            raise ValueError("features no puede estar vacío")
        return v

    def to_flat_record(self) -> dict:
        return {"Nombre_Archivo": self.filename, "Calidad_Muestra": self.substance_label, **self.features}
```

Este schema garantiza que lo que llega al clasificador tiene siempre la misma estructura. El método `to_flat_record()` convierte el objeto al formato que necesita el DataFrame de sklearn.

**`spec/schemas/prediction.py`** — salida del pipeline:

```python
class Prediction(BaseModel):
    filename: str
    predicted_class: str              # validado: debe ser AQ, HQ, LQ o ETH
    confidence: Optional[float]       # validado: debe estar en [0, 1]
    class_probabilities: Optional[Dict[str, float]]
```

Si el pipeline se expone como API o se integra con otro sistema, `Prediction` es el contrato de respuesta. Nada que reciba esta clase necesita saber cómo funciona el SVM internamente.

---

## Capa 2 — Design: las decisiones (`design/adr/`)

Un ADR (*Architecture Decision Record*) documenta **una sola decisión de diseño** con tres partes:

- **Contexto**: qué problema existía y qué opciones se consideraron
- **Decisión**: qué se eligió y por qué
- **Consecuencias**: qué se gana y qué se pierde con la elección

Los ADRs no explican código — explican *por qué el código es así*. Son la memoria del proyecto: cuando alguien pregunta "¿por qué usamos PerKeyPCA en lugar de un PCA global?", la respuesta está en un ADR.

#### Ejemplo de ADR: `design/adr/001-per-key-pca.md`

```markdown
# ADR-001: PCA independiente por (sensor × ventana) en lugar de PCA global

## Contexto
En la versión anterior, se ajustaba un único PCA sobre todas las features
concatenadas de todo el dataset (Fase 3 del pipeline original). Esto producía
data leakage: el PCA veía muestras de test durante el ajuste, inflando
artificialmente las métricas de validación cruzada.

Alternativas consideradas:
1. PCA global ajustado solo sobre train
2. PCA independiente por cada clave (sensor × ventana), ajustado dentro del Pipeline de sklearn

## Decisión
Opción 2: PerKeyPCA como TransformerMixin de sklearn.

## Consecuencias
+ El PCA solo ve datos de entrenamiento en cada fold → validación honesta
+ Compatible con Pipeline de sklearn → se reajusta automáticamente en CV
+ Permite comparar varianza explicada por sensor y ventana por separado
- Más modelos PCA a mantener (uno por cada sensor × ventana, no uno solo)
- Requiere que las columnas del DataFrame sigan el patrón 'sensor_ventana__t{idx}'
```

---

## Capa 3 — Dev: las implementaciones (`src/enose/`)

Las implementaciones son el código que realmente ejecuta el trabajo. Cada clase de `src/enose/` implementa uno o más contratos de `spec/contracts/` sin necesidad de declararlo explícitamente.

#### Ejemplo: `SignalProcessor` implementa `SignalProcessorProtocol`

```python
# src/enose/signal/processor.py

class SignalProcessor:
    """
    Conforme a SignalProcessorProtocol — se puede sustituir por cualquier
    clase que implemente el mismo protocolo sin tocar el pipeline.
    """
    def __init__(self, config: Optional[SignalConfig] = None) -> None:
        cfg = config or SIGNAL_CONFIG
        self.sampling_frequency = cfg.sampling_frequency
        self.savgol_window = ...
        self.baseline_seconds = ...

    def smooth_signal(self, signal: np.ndarray) -> np.ndarray:
        return savgol_filter(signal, window_length=self.savgol_window, ...)

    def normalize_by_baseline(self, signal: np.ndarray) -> np.ndarray:
        R0 = np.mean(signal[:self.baseline_samples])
        return (R0 - signal) / R0
```

La implementación elige Savitzky-Golay para suavizar y normalización fraccional `(R0 - Rs) / R0`. Esas son decisiones de esta capa. El contrato solo exige que exista `smooth_signal` y `normalize_by_baseline` con las firmas correctas.

#### Ejemplo: `PerKeyPCA` implementa `SignalExtractorProtocol`

```python
# src/enose/features/perkey_pca.py

class PerKeyPCA(BaseEstimator, TransformerMixin):
    """Ajusta un PCA independiente por cada clave '{sensor}_{ventana}'."""

    def fit(self, X: pd.DataFrame, y=None) -> "PerKeyPCA":
        for key, cols in self.groups_.items():
            block = X[cols].to_numpy()
            pca = PCA(n_components=n_comp, whiten=cfg.whiten)
            pca.fit(block)
            self.pca_models_[key] = pca
        return self

    def transform(self, X: pd.DataFrame) -> np.ndarray:
        projections = [self.pca_models_[key].transform(X[cols].to_numpy())
                       for key, cols in self.groups_.items()]
        return np.hstack(projections)
```

`PerKeyPCA` hereda de `BaseEstimator` y `TransformerMixin` de sklearn para ser compatible con `Pipeline`. Eso es un detalle de implementación que no aparece en el contrato.

---

## Cómo trabajar con este sistema

### Al añadir un nuevo componente

1. **Empieza por Spec**: ¿qué métodos necesita tener este componente? Escríbelos en un `Protocol` en `spec/contracts/`. Si el componente produce o consume datos en una frontera del sistema, define su schema en `spec/schemas/`.

2. **Registra la decisión en Design** (si hay algo no obvio): ¿por qué este diseño y no otro? Crea un ADR en `design/adr/`.

3. **Implementa en Dev**: escribe la clase concreta en `src/enose/`. No tiene que heredar del Protocol, pero debe tener los métodos correctos.

### Al sustituir un componente existente

Por ejemplo, sustituir `SVC` por `RandomForestClassifier`:

1. Comprueba `spec/contracts/classifier.py`: ¿tiene `RandomForestClassifier` los métodos `fit`, `predict`, `predict_proba` y `score` con la misma firma? Sí → es compatible.
2. Sustituye en el orquestador (`src/enose/model/trainer.py`). El pipeline no cambia.
3. Opcionalmente, documenta la razón en un ADR.

### Al modificar el formato de datos

Si el formato de `SensorReading` o `FeatureVector` cambia (por ejemplo, añadir un nuevo sensor), el schema de Pydantic lo capturará en tiempo de construcción y el error aparecerá en la frontera, no dentro del pipeline.

---

## Resumen visual

```
spec/contracts/processor.py          spec/schemas/sensor_reading.py
        │                                       │
        │  define la interfaz                   │  valida los datos de entrada
        ▼                                       ▼
src/enose/signal/processor.py  ◄──────  Archivo .txt del sensor
  (implementa smooth, normalize,
   extract_features, ...)
        │
        │  produce
        ▼
spec/schemas/feature_vector.py       design/adr/001-per-key-pca.md
        │                                       │
        │  valida el vector                     │  explica por qué PerKeyPCA
        ▼                                       ▼
src/enose/features/perkey_pca.py  ◄──── decisión documentada
  (implementa fit/transform
   dentro del Pipeline de sklearn)
        │
        │  produce
        ▼
spec/schemas/prediction.py
  (contrato de salida: predicted_class, confidence, ...)
```
