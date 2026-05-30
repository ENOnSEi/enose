# Proyecto Nariz Electrónica

Pipeline de ML para clasificación de calidad de vino mediante una nariz electrónica (6 sensores quimioresistivos MQ).
Implementa procesamiento de señal y clasificación SVM siguiendo Macias et al., *Sensors* 2013.

## Arquitectura

El proyecto sigue la estructura **Especificación → Diseño → Desarrollo**:

| Capa | Carpeta | Propósito |
|---|---|---|
| Spec | `spec/contracts/` | Clases `Protocol` de Python — interfaces formales para cada etapa del pipeline |
| Spec | `spec/schemas/` | Modelos Pydantic — validación de datos en los límites del sistema |
| Diseño | `diseño/adr/` | Registros de Decisión de Arquitectura — por qué el sistema está construido así |
| Dev | `src/enose/` | Implementaciones — organizadas por dominio, intercambiables via Protocols |

## Estructura del Proyecto

```
Electronic Nose Project/
├── main.py                        # Punto de entrada del pipeline (CLI)
├── requirements.txt
├── pyrightconfig.json
├── pytest.ini
│
├── spec/
│   ├── contracts/                 # Python Protocols (interfaces)
│   │   ├── processor.py           # SignalProcessorProtocol
│   │   ├── extractor.py           # HandcraftedExtractorProtocol, SignalExtractorProtocol
│   │   └── classifier.py          # ClassifierProtocol
│   └── schemas/                   # Modelos Pydantic (validación en frontera)
│       ├── sensor_reading.py      # SensorReading — entrada cruda
│       ├── feature_vector.py      # FeatureVector — post-extracción
│       └── prediction.py          # Prediction — salida del modelo
│
├── diseño/
│   └── adr/                       # Registros de Decisión de Arquitectura
│       ├── 001-spec-design-dev-architecture.md
│       ├── 002-pca-vs-handcrafted-features.md
│       └── 003-svm-classifier.md
│
├── src/enose/                     # Paquete principal
│   ├── io/reader.py               # Lectura de ficheros de sensores, extracción de etiquetas
│   ├── signal/processor.py        # Suavizado Savitzky-Golay + normalización
│   ├── features/
│   │   ├── pca.py                 # PCAFeatureExtractor
│   │   └── handcrafted.py         # HandcraftedExtractor (máximo, AUC, pendiente)
│   ├── model/trainer.py           # Entrenamiento SVM con GridSearchCV
│   ├── pipeline/dataset.py        # DatasetGenerator + helpers de carga/validación
│   ├── config.py                  # Configuración tipada (dataclasses frozen)
│   └── utils.py                   # Logging, gráficas, validación
│
├── datos/
│   ├── brutos/                    # Ficheros .txt de sensores + CSV maestro
│   │   ├── AQ_Wines/
│   │   ├── HQ_Wines/
│   │   ├── LQ_Wines/
│   │   └── Ethanol/
│   └── procesados/                # Generado: ficheros .pkl del modelo, visualizaciones
│
├── pruebas/
│   ├── contratos/                 # Tests de contrato (verifican cumplimiento de Protocols)
│   │   ├── test_processor_contract.py
│   │   ├── test_extractor_contract.py
│   │   └── test_schemas.py
│   └── unitarias/
│       ├── test_imports.py        # Test de humo de imports
│       └── test_phase5.py         # Test de entrenamiento end-to-end
│
├── documentacion/
│   ├── CHANGELOG.md
│   └── modules_reference.md
├── cuadernos/
└── registros/
```

## Inicio Rápido

```bash
pip install -r requirements.txt

# Pipeline completo (extracción de características + entrenamiento)
python main.py

# Solo extracción de características (Fase 4)
python main.py --phase 4

# Solo entrenamiento del modelo (Fase 5 — requiere dataset)
python main.py --phase 5
```

## Visión General del Pipeline

```
Fase 4: Extracción de Características
  io/reader.py        → carga ficheros .txt de sensores
  signal/processor.py → Savitzky-Golay + normalización de línea base
  signal/processor.py → segmentación por (sensor × ventana)     [modo pca_signal]
  features/handcrafted.py → máximo, AUC, pendiente por ventana  [modo handcrafted]
  pipeline/dataset.py → agregación → dataset_maestro_vinos.csv
                        (en pca_signal serializa segmentos crudos; el PCA se ajusta en Fase 5)

Fase 5: Entrenamiento del Modelo
  pipeline/dataset.py → carga + validación CSV + split por grupos (vino-lote)
  model/trainer.py    → PerKeyPCA → StandardScaler → SVM
                        GridSearchCV + StratifiedGroupKFold (balanced_accuracy) → best_model.pkl
```

> **Sin data leakage:** en modo `pca_signal` el PCA (`PerKeyPCA`) se ajusta **dentro** del
> Pipeline, solo sobre el train de cada fold. Además la validación es **por grupos**: ninguna
> réplica del mismo vino-lote aparece a la vez en train y test (ver ADR 002 y CHANGELOG V5).

## Modos de Extracción de Características

Controlado por `FEATURE_MODE` en `src/enose/config.py`:

| Modo | Descripción | Características/muestra | Artefactos necesarios para inferencia |
|---|---|---|---|
| `pca_signal` (por defecto) | PCA sobre curvas de señal por (sensor × ventana), ajustado dentro del Pipeline | ~15–20 (95% var) | `best_model.pkl` únicamente (el PCA va embebido) |
| `handcrafted` | Máximo, AUC, pendiente por ventana | 54 fijas | `best_model.pkl` únicamente |

## Salidas

| Fichero | Descripción |
|---|---|
| `datos/brutos/dataset_maestro_vinos.csv` | Dataset maestro |
| `datos/procesados/best_model.pkl` | Pipeline entrenado completo (PerKeyPCA + StandardScaler + SVM) |
| `datos/procesados/training_results.pkl` | Métricas y resultados de evaluación |
| `datos/procesados/visualizaciones/` | Matriz de confusión, gráficas de precisión, informe de clasificación |

## Configuración

Todos los parámetros están en `src/enose/config.py` como dataclasses tipados y frozen:

```python
# Modo de extracción de características
FEATURE_MODE = 'pca_signal'   # o 'handcrafted'

# Procesamiento de señal
SIGNAL_CONFIG = SignalConfig(
    sampling_frequency=18.5,
    savgol_window=15,
    baseline_seconds=2.0,
    time_windows=((0, 2), (2, 10), (10, 20)),
)

# PCA
PCA_CONFIG = PCAConfig(explained_variance_threshold=0.95)

# SVM
ML_CONFIG = MLConfig(n_splits_cv=3, scoring_metric='balanced_accuracy')
```

## Extender el Pipeline

La capa Spec define los contratos. Para añadir un nuevo extractor de características:

1. Implementar `SignalExtractorProtocol` (ver `spec/contracts/extractor.py`)
2. Añadir la clase en `src/enose/features/`
3. Conectarla en `src/enose/pipeline/dataset.py`
4. Añadir tests de contrato en `pruebas/contratos/`

No hay que modificar ningún otro fichero.

## Ejecutar Pruebas

```bash
# Tests de contrato (cumplimiento de Protocols + validación de esquemas)
python -m pytest pruebas/contratos/ -v

# Test de humo de imports
python pruebas/unitarias/test_imports.py

# Test de entrenamiento completo (requiere dataset)
python pruebas/unitarias/test_phase5.py
```

## Referencia

Macias, M. M. et al. "Electronic Nose for Wine Discrimination." *Sensors* 13.5 (2013): 5528–5543.
