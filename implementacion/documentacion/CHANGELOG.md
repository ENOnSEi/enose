# CHANGELOG — Proyecto Nariz Electrónica

---

## V5 — Validación honesta y limpieza de código heredado (2026-05-30)

### Motivación
Auditoría matemática de las Fases 4 y 5. Se detectaron tres problemas que inflaban
las métricas o duplicaban lógica con riesgo de data leakage.

### Cambios

**Eliminado: código heredado con data leakage**
Los módulos planos en `src/` (anteriores a la migración V4) seguían ajustando el PCA
sobre todo el dataset (train+test) → fuga hacia el test. Se borraron junto con sus
tests y soportes huérfanos (ya reemplazados por el paquete `enose`):
- `src/phase_4_dataset_generation.py`, `src/phase_5_model_training.py`
- `src/phase_1_3_feature_extraction.py`, `src/config.py`, `src/utils.py`
- `pruebas/test_phase5.py`, `pruebas/test_imports.py`

**Métrica de selección: `accuracy` → `balanced_accuracy`**
Las clases están desbalanceadas (LQ=141, HQ=51, AQ=43). `accuracy` premiaba el sesgo
a la clase mayoritaria; `balanced_accuracy` (media de recalls por clase) la sustituye
en `GridSearchCV`. Se reporta además `test_balanced_accuracy` en los resultados.

**Validación consciente de grupos (corrige optimismo del test)**
Cada vino-lote se mide ~11 veces (`{Clase}_Wine{NN}-B{BB}_R{RR}.txt`). Hay solo
**22 vinos independientes** para 235 muestras. El `train_test_split`/`StratifiedKFold`
anteriores repartían réplicas casi idénticas entre train y test → fuga por grupos
(test accuracy artificial del 100%). Se sustituyen por `StratifiedGroupKFold` (split
externo + CV interna), agrupando por vino-lote.
- Resultado honesto: **Test accuracy ≈ 86% / balanced ≈ 79%** (antes 100% por fuga).

**`SVC(probability=False)`** — evita la CV interna de Platt, innecesaria (las métricas
usan `predict()`, no `predict_proba()`).

### Comportamiento
La Fase 4 no cambia. La Fase 5 cambia el esquema de validación (ahora por grupos) y la
métrica de selección; las métricas reportadas son más bajas pero realistas.

---

## V4 — Arquitectura Spec → Design → Dev (2026-05-30)

### Motivación
El pipeline V3 funcionaba correctamente pero tenía una estructura plana en `src/`
que dificultaba añadir nuevos sensores o algoritmos sin modificar múltiples archivos.
Con destino de despliegue en producción, se necesitaba una organización más robusta
con contratos formales entre módulos.

### Cambios

**Nuevo: `spec/` — capa de especificación**
- `spec/contracts/processor.py` — `SignalProcessorProtocol`: define la interfaz de cualquier procesador de señal
- `spec/contracts/extractor.py` — `HandcraftedExtractorProtocol`, `SignalExtractorProtocol`: interfaces de extractores
- `spec/contracts/classifier.py` — `ClassifierProtocol`: interfaz del clasificador
- `spec/schemas/sensor_reading.py` — `SensorReading` (Pydantic): valida archivos de entrada
- `spec/schemas/feature_vector.py` — `FeatureVector` (Pydantic): valida features antes del clasificador
- `spec/schemas/prediction.py` — `Prediction` (Pydantic): valida salidas del modelo

**Nuevo: `design/adr/` — decisiones de arquitectura**
- ADR 001: Arquitectura Spec→Design→Dev
- ADR 002: PCA vs Handcrafted features
- ADR 003: SVM como clasificador

**Refactorizado: `src/` → `src/enose/` — paquete Python propio**

| Antes | Después |
|---|---|
| `src/config.py` | `src/enose/config.py` — dataclasses tipadas (frozen) en lugar de dicts |
| `src/utils.py` | `src/enose/utils.py` |
| `src/phase_1_3_feature_extraction.py` (SignalProcessor) | `src/enose/signal/processor.py` |
| `src/phase_1_3_feature_extraction.py` (PCAFeatureExtractor) | `src/enose/features/pca.py` |
| `src/phase_1_3_feature_extraction.py` (load_sensor_file) | `src/enose/io/reader.py` |
| `src/phase_4_dataset_generation.py` | `src/enose/pipeline/dataset.py` |
| `src/phase_5_model_training.py` | `src/enose/model/trainer.py` |

**Refactorizado: `tests/`**
- `tests/contracts/` — 15 tests que verifican que las implementaciones cumplen sus Protocols
- `tests/unit/test_imports.py` — smoke test del paquete completo
- `tests/unit/test_phase5.py` — test de entrenamiento end-to-end

**Eliminado: `archive/`** — código histórico V1/V2 (preservado en git)

**Actualizado: `main.py`** — apunta a `src/enose/` en lugar de `src/`

**Añadida dependencia: `pydantic`** — validación de schemas en fronteras del sistema

### Comportamiento del pipeline
Sin cambios. Las entradas, salidas y parámetros son idénticos a V3.
Solo cambia la organización interna del código.

### Cómo extender el pipeline (nuevo)
Ver `spec/contracts/extractor.py` y `design/adr/001-spec-design-dev-architecture.md`.

---

## V3 — Extracción de características basada en PCA (2026-05-23)

### Motivación
Implementación del enfoque del paper *Macías et al., Sensors 2013* como alternativa a los estadísticos manuales. En lugar de calcular max/AUC/slope sobre las ventanas, se proyecta cada segmento de señal sobre los componentes principales aprendidos del dataset completo.

### Cambios principales
- `FEATURE_MODE`: `'handcrafted'` | `'pca_signal'` — switch global en `config.py`
- `PCAFeatureExtractor`: ajusta un PCA independiente por (sensor × ventana), con `fit/transform/save/load`
- `DatasetGenerator._generate_pca()`: dos pasadas — recolecta segmentos, ajusta PCA, proyecta
- Guarda `data/processed/pca_transformers.pkl` (necesario para inferencia)

### Salidas nuevas en modo `pca_signal`
- `pca_transformers.pkl` — modelos PCA por combinación sensor×ventana
- Columnas CSV: `{sensor}_{ventana}_pc{n}` (ej: `MQ3_1_w2-10_pc1`)

---

## V2 — Pipeline modularizado con Savitzky-Golay y ventanas temporales

### Cambios principales
- Filtro Savitzky-Golay (reemplaza media móvil de V1) — preserva mejor la forma de los picos
- Segmentación en 3 ventanas temporales: [0-2s] baseline, [2-10s] inyección, [10-20s] limpieza
- Configuración centralizada en `config.py` con parámetros V1 y V2
- Normalización fraccional: (R0 - Rs) / R0

### Resultados validados
- Accuracy en test: **97.87%** (kernel linear, C=0.1)

---

## V1 — Script original (referencia bibliográfica)

Implementación inicial basada directamente en Macías et al., 2013.
Estructura monolítica en un único script. Preservada en git como referencia.
