# Electronic Nose Project — Pipeline Instructions

## Requisitos previos

```bash
pip install -r requirements.txt
```

Python 3.10+ recomendado.

---

## Estructura de datos esperada

```
data/
  raw/        ← archivos .txt de sensores organizados por sustancia
    AQ_Wines/
    HQ_Wines/
    LQ_Wines/
    Ethanol/
  processed/  ← generado automáticamente por el pipeline
```

Los archivos de sensor deben estar en `data/raw/` antes de ejecutar la Fase 4.

---

## Ejecución del pipeline

Todos los comandos se ejecutan desde la **raíz del proyecto** (donde está `main.py`).

### Pipeline completo (Fase 4 + Fase 5)

```bash
python main.py
```

### Solo Fase 4 — Extracción de características

```bash
python main.py --phase 4
```

Lee los .txt de `data/raw/`, extrae features y genera `data/raw/dataset_maestro_vinos.csv`.

### Solo Fase 5 — Entrenamiento del modelo

```bash
python main.py --phase 5
```

Requiere que `data/raw/dataset_maestro_vinos.csv` exista (generado por la Fase 4).

---

## Salidas generadas

| Archivo | Modo | Descripción |
|---|---|---|
| `data/raw/dataset_maestro_vinos.csv` | ambos | Dataset maestro con todas las features |
| `data/processed/best_model.pkl` | ambos | Pipeline SVM entrenado (StandardScaler + SVM) |
| `data/processed/training_results.pkl` | ambos | Métricas y resultados del entrenamiento |
| `data/processed/pca_transformers.pkl` | `pca_signal` | Modelos PCA por (sensor × ventana). Necesario para inferencia |
| `data/processed/visualizations/` | ambos | Matriz de confusión, precisiones, reporte de clasificación |
| `logs/enose_project.log` | ambos | Log de ejecución completo |

---

## Configuración

Todos los parámetros están en `src/enose/config.py` como dataclasses tipadas (inmutables):

```python
# Modo de extracción de características
FEATURE_MODE = 'pca_signal'   # 'pca_signal' (recomendado) | 'handcrafted'

# Parámetros de señal
SIGNAL_CONFIG = SignalConfig(
    sampling_frequency=18.5,   # Hz
    savgol_window=15,           # Savitzky-Golay (debe ser impar)
    savgol_polyorder=3,
    baseline_seconds=2.0,
    time_windows=((0, 2), (2, 10), (10, 20)),
)

# PCA
PCA_CONFIG = PCAConfig(explained_variance_threshold=0.95)

# SVM + GridSearch
ML_CONFIG = MLConfig(n_splits_cv=3, scoring_metric='accuracy')
GRID_PARAMS = [...]   # Kernels: linear, rbf | C: [0.1, 1, 10, 100]
```

### Cambiar modo de extracción

Editar una línea en `src/enose/config.py`:

```python
FEATURE_MODE = 'pca_signal'   # PCA por sensor y ventana (recomendado)
FEATURE_MODE = 'handcrafted'  # max, AUC, slope por ventana
```

Luego re-ejecutar la Fase 4 completa.

---

## Ejecución de tests

```bash
# Tests de contrato (Protocol compliance + validación de schemas)
python -m pytest tests/contracts/ -v

# Smoke test de imports
python tests/unit/test_imports.py

# Test de entrenamiento (requiere dataset generado)
python tests/unit/test_phase5.py
```

---

## Añadir un nuevo extractor de características

1. Implementa `SignalExtractorProtocol` (ver `spec/contracts/extractor.py`)
2. Crea tu clase en `src/enose/features/mi_extractor.py`
3. Añade una rama en `src/enose/pipeline/dataset.py` (`FEATURE_MODE == 'mi_modo'`)
4. Registra el modo en `FEATURE_MODE` de `config.py`
5. Añade tests en `tests/contracts/`

---

## Añadir un nuevo sensor

1. Actualiza `SENSOR_COLUMNS` en `src/enose/config.py`
2. Actualiza `EXPECTED_SENSORS` en `spec/schemas/sensor_reading.py`
3. Los tests de schema verificarán automáticamente la coherencia

---

## Solución de problemas comunes

**`ModuleNotFoundError: No module named 'enose'`**
→ Ejecuta siempre desde la raíz del proyecto, no desde dentro de `src/`.

**`FileNotFoundError` en Fase 5**
→ Ejecuta primero la Fase 4 para generar el dataset.

**`pca_transformers.pkl` no encontrado al cargar el modelo**
→ Este archivo se genera en la Fase 4 (modo `pca_signal`). Ejecuta `--phase 4` antes de usar el modelo para inferencia.

**Errores de importación en VS Code (subrayado rojo)**
→ Verifica que `pyrightconfig.json` en la raíz incluye `"extraPaths": ["src"]`.
