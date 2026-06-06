# Electronic Nose Project — Pipeline Instructions

## Requisitos previos

```bash
pip install -r requirements.txt
```

Python 3.10+ recomendado.

---

## Estructura de datos esperada

Las grabaciones crudas son los CSV de la carpeta `datasets/` de la **raíz del
repositorio** (no dentro de `implementacion/`):

```
Electronic Nose Project/
  datasets/            ← grabaciones .csv (una por mezcla)
    agua.csv
    alcohol.csv
    vino.csv
    vinoyagua.csv
    vinoagitacionrara.csv
  implementacion/
    datos/procesados/  ← generado automáticamente por el pipeline
```

Cada CSV tiene cabecera `data,v20,v11,v02,v00,estado`. La columna `estado`
marca las fases `inicio` / `base` / `medicion` (ver README).

---

## Ejecución del pipeline

Todos los comandos se ejecutan desde `implementacion/` (donde está `main.py`).

### Solo Fase 4 — Extracción de características (recomendado por ahora)

```bash
python main.py --phase 4
```

Lee los `.csv` de `datasets/`, normaliza cada sensor con su fase `base`, extrae
features de la fase `medicion` y genera `datos/procesados/dataset_maestro.csv`.

### Pipeline completo (Fase 4 + Fase 5)

```bash
python main.py
```

### Solo Fase 5 — Entrenamiento del modelo

```bash
python main.py --phase 5
```

Requiere que `datos/procesados/dataset_maestro.csv` exista y que haya **≥2
grabaciones por clase** (la validación es por grupos; con una sola grabación por
mezcla el split train/test no es posible sin fuga y la fase se detiene avisando).

---

## Salidas generadas

| Archivo | Modo | Descripción |
|---|---|---|
| `datos/procesados/dataset_maestro.csv` | ambos | Dataset maestro con todas las features |
| `datos/procesados/best_model.pkl` | ambos | Pipeline SVM entrenado (incluye PerKeyPCA en modo `pca_signal`) |
| `datos/procesados/training_results.pkl` | ambos | Métricas y resultados del entrenamiento |
| `datos/procesados/visualizations/` | ambos | Distribución de clases, matriz de confusión, precisiones |
| `informes/informe_<timestamp>/` | Fase 5 | Informe de ejecución (Markdown + JSON + PNGs) |
| `registros/enose_project.log` | ambos | Log de ejecución completo |

---

## Configuración

Todos los parámetros están en `src/enose/config.py` como dataclasses tipadas (inmutables):

```python
FEATURE_MODE = 'handcrafted'   # 'handcrafted' (por defecto) | 'pca_signal'

SIGNAL_CONFIG = SignalConfig(
    sampling_frequency=4.0,     # Hz (250 ms entre muestras)
    savgol_window=9,            # Savitzky-Golay (debe ser impar)
    savgol_polyorder=3,
    baseline_seconds=2.0,       # fallback si la grabación no tiene fase 'base'
    time_windows=((0, 5), (5, 15), (15, 40)),   # s desde el inicio de 'medicion'
)

PCA_CONFIG = PCAConfig(explained_variance_threshold=0.95)
ML_CONFIG = MLConfig(n_splits_cv=3, scoring_metric='balanced_accuracy')
```

### Generar más muestras por grabación (ventaneo)

Por defecto cada grabación es una muestra. Para trocear la fase `medicion` en
varias muestras, edita `src/enose/pipeline/dataset.py`:

```python
MEASUREMENT_WINDOWING = (8.0, 0.5)   # ventanas de 8 s con 50% de solape
```

y re-ejecuta la Fase 4.

---

## Ejecución de tests

```bash
# Tests de contrato (Protocol compliance + validación de schemas)
python -m pytest pruebas/contratos/ -v

# Smoke test de imports
python pruebas/unitarias/test_imports.py

# Test de entrenamiento (requiere dataset y ≥2 grabaciones/clase)
python pruebas/unitarias/test_phase5.py
```

---

## Añadir un nuevo extractor de características

1. Implementa `SignalExtractorProtocol` (ver `spec/contracts/extractor.py`)
2. Crea tu clase en `src/enose/features/mi_extractor.py`
3. Añade una rama en `src/enose/pipeline/dataset.py` (`FEATURE_MODE == 'mi_modo'`)
4. Registra el modo en `FEATURE_MODE` de `config.py`
5. Añade tests en `pruebas/contratos/`

---

## Añadir un nuevo sensor

1. Actualiza `SENSOR_MODELS` / `SENSOR_COLUMNS` en `src/enose/config.py`
2. Actualiza `EXPECTED_SENSORS` en `spec/schemas/sensor_reading.py`
3. Asegúrate de que el sketch de Arduino y el `serial-reader` emiten la columna nueva
4. Los tests de schema verificarán la coherencia

---

## Solución de problemas comunes

**`ModuleNotFoundError: No module named 'enose'`**
→ Ejecuta siempre desde `implementacion/`, no desde dentro de `src/`.

**`No hay grabaciones .csv en ...`**
→ Deja los CSV en la carpeta `datasets/` de la raíz del repositorio.

**`FileNotFoundError` / dataset no encontrado en Fase 5**
→ Ejecuta primero la Fase 4 para generar el dataset.

**`Insuficientes grupos por clase para un split por grupos`**
→ Necesitas ≥2 grabaciones de cada mezcla. Graba más CSVs (o activa el ventaneo
   de `medicion` solo aporta muestras, no grupos nuevos: hacen falta grabaciones
   distintas por clase).

**`UnicodeEncodeError` en la consola de Windows**
→ `main.py` ya fuerza UTF-8 en la salida; si lanzas otro script, exporta
   `PYTHONUTF8=1`.

**Errores de importación en VS Code (subrayado rojo)**
→ Verifica que `pyrightconfig.json` incluye `"extraPaths": ["src"]`.
