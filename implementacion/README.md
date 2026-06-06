# Proyecto Nariz Electrónica — Pipeline de ML

Pipeline de ML para clasificar mezclas (agua, alcohol etílico, vino y sus
combinaciones) medidas con una nariz electrónica de **4 sensores TGS**.
Procesamiento de señal + clasificación SVM, siguiendo la metodología de
Macias et al., *Sensors* 2013, adaptada al hardware del proyecto.

## Formato de datos

Las grabaciones crudas son los CSV de la carpeta `datasets/` de la raíz del
repositorio (cabecera `data,v20,v11,v02,v00,estado`). Cada CSV es una grabación
continua de una mezcla con tres fases en la columna `estado`:

- `inicio`   : calentamiento del sensor → **se descarta**.
- `base`     : aire limpio → de aquí sale la línea base **R0**.
- `medicion` : respuesta al estímulo → es la **señal** que se caracteriza.

La normalización es el cambio fraccional `(R0 − Rs) / R0`, con R0 estimado de la
fase `base` y Rs la respuesta de la fase `medicion`.

## Arquitectura

El proyecto sigue la estructura **Especificación → Diseño → Desarrollo**:

| Capa | Carpeta | Propósito |
|---|---|---|
| Spec | `spec/contracts/` | Clases `Protocol` — interfaces formales para cada etapa del pipeline |
| Spec | `spec/schemas/` | Modelos Pydantic — validación de datos en los límites del sistema |
| Diseño | `diseño/adr/` | Registros de Decisión de Arquitectura — por qué el sistema está construido así |
| Dev | `src/enose/` | Implementaciones — organizadas por dominio, intercambiables vía Protocols |

## Estructura del Proyecto

```
Electronic Nose Project/
├── datasets/                       # Grabaciones CSV (raíz del repo) — entrada de la Fase 4
│
└── implementacion/
    ├── main.py                     # Punto de entrada del pipeline (CLI)
    ├── requirements.txt
    │
    ├── spec/
    │   ├── contracts/              # Python Protocols (interfaces)
    │   │   ├── processor.py        # SignalProcessorProtocol
    │   │   ├── extractor.py        # HandcraftedExtractorProtocol, SignalExtractorProtocol
    │   │   ├── classifier.py       # ClassifierProtocol
    │   │   └── reporter.py         # ReportGeneratorProtocol
    │   └── schemas/                # Modelos Pydantic (validación en frontera)
    │       ├── sensor_reading.py   # SensorReading — grabación cruda (4 sensores TGS)
    │       ├── feature_vector.py   # FeatureVector — post-extracción
    │       ├── prediction.py       # Prediction — salida del modelo
    │       └── execution_report.py # ExecutionReport — informe de ejecución
    │
    ├── diseño/adr/                 # Registros de Decisión de Arquitectura
    │
    ├── src/enose/                  # Paquete principal
    │   ├── io/reader.py            # Lectura CSV, etiqueta por nombre, split por estado
    │   ├── signal/processor.py     # Savitzky-Golay + normalización por línea base
    │   ├── features/
    │   │   ├── pca.py              # PCAFeatureExtractor
    │   │   ├── perkey_pca.py       # PerKeyPCA (PCA por sensor×ventana en el Pipeline)
    │   │   └── handcrafted.py      # HandcraftedExtractor (max, AUC, slope)
    │   ├── model/trainer.py        # Entrenamiento SVM con GridSearchCV
    │   ├── pipeline/dataset.py     # DatasetGenerator + helpers de carga/validación
    │   ├── report/generator.py     # Informe de ejecución (Markdown + JSON)
    │   ├── config.py               # Configuración tipada (dataclasses frozen)
    │   └── utils.py                # Logging, gráficas, validación
    │
    ├── datos/procesados/           # Generado: dataset maestro, modelos .pkl, visualizaciones
    ├── pruebas/                    # Tests de contrato + unitarios
    ├── documentacion/
    ├── cuadernos/
    └── registros/
```

## Inicio Rápido

```bash
pip install -r requirements.txt

# Solo extracción de características (Fase 4) — recomendado por ahora
python main.py --phase 4

# Pipeline completo (Fase 4 + entrenamiento Fase 5)
python main.py

# Solo entrenamiento del modelo (Fase 5 — requiere dataset y ≥2 grabaciones/clase)
python main.py --phase 5
```

> **Sobre entrenar (Fase 5):** el entrenamiento usa validación **por grupos**
> (cada grabación es un grupo), de modo que ninguna ventana de una misma
> grabación cae a la vez en train y test. Con una sola grabación por mezcla no
> es posible dividir train/test sin fuga, así que la Fase 5 avisará y se
> detendrá hasta que haya **≥2 grabaciones por clase**.

## Visión General del Pipeline

```
Fase 4: Extracción de Características
  io/reader.py        → carga las grabaciones .csv de datasets/
  io/reader.py        → separa fase 'base' (R0) y 'medicion' (señal) por sensor
  signal/processor.py → Savitzky-Golay + normalización (R0 - Rs)/R0
  features/handcrafted.py → max, AUC, slope por ventana            [modo handcrafted]
  signal/processor.py → segmentación por (sensor × ventana)        [modo pca_signal]
  pipeline/dataset.py → agregación → datos/procesados/dataset_maestro.csv

Fase 5: Entrenamiento del Modelo
  pipeline/dataset.py → carga + validación CSV + split por grupos (grabación)
  model/trainer.py    → [PerKeyPCA] → StandardScaler → SVM
                        GridSearchCV + StratifiedGroupKFold (balanced_accuracy) → best_model.pkl
```

## Modos de Extracción de Características

Controlado por `FEATURE_MODE` en `src/enose/config.py`:

| Modo | Descripción | Muestras |
|---|---|---|
| `handcrafted` (por defecto) | Max, AUC, slope por (sensor × ventana) | Una grabación = una muestra |
| `pca_signal` | PCA sobre las curvas por (sensor × ventana), ajustado dentro del Pipeline | Pensado para muchas muestras (p. ej. ventaneando `medicion`) |

### Una grabación = una muestra (y cómo generar más)

Por defecto cada CSV produce **una** muestra. Para aumentar el número de
muestras por grabación se puede **ventanear** la fase `medicion`: pon
`MEASUREMENT_WINDOWING = (longitud_seg, solapamiento)` en
`src/enose/pipeline/dataset.py` (p. ej. `(8.0, 0.5)`) y re-ejecuta la Fase 4.
Todas las ventanas de una misma grabación comparten grupo, así que no hay fuga.

## Configuración

Todos los parámetros están en `src/enose/config.py` como dataclasses tipadas y frozen:

```python
FEATURE_MODE = 'handcrafted'   # o 'pca_signal'

SIGNAL_CONFIG = SignalConfig(
    sampling_frequency=4.0,             # 250 ms entre muestras
    savgol_window=9,                    # impar
    baseline_seconds=2.0,               # fallback si la grabación no tiene fase 'base'
    time_windows=((0, 5), (5, 15), (15, 40)),   # segundos desde el inicio de 'medicion'
)

PCA_CONFIG = PCAConfig(explained_variance_threshold=0.95)
ML_CONFIG = MLConfig(n_splits_cv=3, scoring_metric='balanced_accuracy')
```

### Añadir una mezcla nueva

1. Graba el CSV con el `serial-reader` y déjalo en `datasets/`.
2. (Opcional) Añade su nombre a `SUBSTANCE_LABELS` en `config.py` para darle una
   etiqueta legible; si no, se usa el nombre del fichero como etiqueta.

## Salidas

| Fichero | Descripción |
|---|---|
| `datos/procesados/dataset_maestro.csv` | Dataset maestro |
| `datos/procesados/best_model.pkl` | Pipeline entrenado completo |
| `datos/procesados/training_results.pkl` | Métricas y resultados de evaluación |
| `datos/procesados/visualizations/` | Gráficas de distribución y evaluación |
| `informes/informe_<timestamp>/` | Informe de ejecución (Markdown + JSON + PNGs) |

## Ejecutar Pruebas

```bash
# Tests de contrato (cumplimiento de Protocols + validación de esquemas)
python -m pytest pruebas/contratos/ -v

# Test de humo de imports
python pruebas/unitarias/test_imports.py

# Test de entrenamiento completo (requiere dataset y ≥2 grabaciones/clase)
python pruebas/unitarias/test_phase5.py
```

## Referencia

Macias, M. M. et al. "Electronic Nose for Wine Discrimination." *Sensors* 13.5 (2013): 5528–5543.
