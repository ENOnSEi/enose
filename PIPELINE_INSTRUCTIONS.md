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
  raw/        ← archivos CSV de sensores por muestra
  processed/  ← generado automáticamente por el pipeline
```

Los archivos CSV de mediciones deben estar en `data/raw/` antes de ejecutar la Fase 4.

---

## Ejecución del pipeline

Todos los comandos se ejecutan desde la **raíz del proyecto** (donde está `main.py`).

### Pipeline completo (Fase 4 + Fase 5)

```bash
python main.py
```

Ejecuta extracción de características y luego entrenamiento del modelo en secuencia.

### Solo Fase 4 — Extracción de características

```bash
python main.py --phase 4
```

Lee los CSV de `data/raw/`, extrae features y genera `data/raw/dataset_maestro_vinos.csv`.

### Solo Fase 5 — Entrenamiento del modelo

```bash
python main.py --phase 5
```

Requiere que `data/raw/dataset_maestro_vinos.csv` exista (generado por la Fase 4).
Entrena un SVM con GridSearch y guarda el modelo en `data/processed/`.

---

## Salidas generadas

| Archivo | Modo | Descripción |
|---|---|---|
| `data/raw/dataset_maestro_vinos.csv` | ambos | Dataset master con todas las features |
| `data/processed/best_model.pkl` | ambos | Pipeline SVM entrenado (StandardScaler + SVM) |
| `data/processed/training_results.pkl` | ambos | Métricas y resultados del entrenamiento |
| `data/processed/pca_transformers.pkl` | `pca_signal` | 18 modelos PCA (6 sensores × 3 ventanas). Necesario junto al modelo para inferencia |
| `data/processed/visualizations/` | ambos | Gráficas de distribución, matriz de confusión, etc. |
| `logs/enose_project.log` | ambos | Log de ejecución |

---

## Configuración

Todos los parámetros del pipeline están centralizados en [src/config.py](src/config.py):

- `FEATURE_MODE` — `'pca_signal'` (V3, por defecto) o `'handcrafted'` (V2)
- `PCA_CONFIG` — umbral de varianza explicada, whitening, n_components
- `SIGNAL_PROCESSING_V2` — frecuencia de muestreo, Savitzky-Golay, baseline, ventanas temporales
- `ML_CONFIG` / `GRID_PARAMS` — hiperparámetros del SVM y GridSearch
- `DATA_SPLIT` — proporciones train/val/test

### Cambiar de modo de extracción

Editar una línea en `src/config.py`:

```python
FEATURE_MODE = 'pca_signal'   # V3: PCA por sensor y ventana (recomendado)
FEATURE_MODE = 'handcrafted'  # V2: max, AUC, slope por ventana
```

Para ver el resumen de configuración actual:

```bash
python src/config.py
```

---

## Ejecución de tests

```bash
python -m pytest tests/
```

---

## Solución de problemas comunes

**`ModuleNotFoundError: No module named 'config'`**
→ Ejecuta siempre desde la raíz del proyecto, no desde dentro de `src/`.

**`FileNotFoundError` en Fase 5**
→ Ejecuta primero la Fase 4 para generar el dataset.

**Errores de importación en VS Code (subrayado rojo)**
→ Normal si falta `pyrightconfig.json` en la raíz. Ya incluido en este proyecto.
