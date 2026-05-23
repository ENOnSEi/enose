# Scripts de Análisis - Nariz Electrónica

Conjunto de módulos Python bien organizados y comentados para el análisis de datos de sensores químicos.

## 📋 Descripción General

El proyecto está dividido en **5 fases** que van desde la ingesta de datos hasta la predicción con ML:

| Fase | Módulo | Descripción |
|------|--------|-------------|
| **1-3** | `phase_1_3_feature_extraction.py` | Extracción de características de señales de sensores |
| **4** | `phase_4_dataset_generation.py` | Generación automática del dataset maestro |
| **5** | `phase_5_model_training.py` | Entrenamiento y optimización del modelo SVM |
| **Main** | `main.py` | Orquestador del pipeline completo |

## 🏗️ Estructura de Archivos

```
src/
├── config.py                              # Configuración centralizada
├── utils.py                               # Funciones auxiliares reutilizables
├── phase_1_3_feature_extraction.py        # ⭐ Motor de características
├── phase_4_dataset_generation.py          # 📊 Generador de dataset
├── phase_5_model_training.py              # 🧠 Entrenador ML
├── main.py                                # 🚀 Script principal
├── original_EnoseDataAnalysis.py          # Versión original (referencia)
└── README.md                              # Este archivo
```

## 🚀 Uso Rápido

### Opción 1: Ejecutar Pipeline Completo (Recomendado)

```bash
cd src
python main.py
```

Ejecuta automáticamente todas las fases (4 y 5).

### Opción 2: Solo Generar Dataset

```bash
python main.py --phase-4-only
```

Solo crea el archivo `dataset_maestro_vinos.csv`.

### Opción 3: Solo Entrenar Modelo

```bash
python main.py --phase-5-only
```

Entrena el modelo usando un dataset existente.

### Opción 4: Pipeline Personalizado

```bash
# Generar dataset si no existe, luego entrenar
python main.py --skip-phase-4

# Ver más opciones
python main.py --help
```

## 📦 Dependencias

```
pandas>=1.3.0
numpy>=1.20.0
scikit-learn>=1.0.0
matplotlib>=3.4.0
seaborn>=0.11.0
```

**Instalación:**
```bash
pip install -r requirements.txt
```

## 🔍 Detalles de Cada Módulo

### 1️⃣ `config.py` - Configuración Centralizada

Almacena todos los parámetros del proyecto en un solo lugar:

```python
from config import SENSOR_COLUMNS, SIGNAL_PROCESSING_V2, ML_CONFIG, FEATURE_MODE, PCA_CONFIG
```

**Secciones principales:**

| Variable | Descripción |
|---|---|
| `FEATURE_MODE` | `'handcrafted'` o `'pca_signal'` — switch global de modo de extracción |
| `PCA_CONFIG` | Umbral de varianza (0.95), whitening, n_components |
| `SIGNAL_PROCESSING_V2` | Savitzky-Golay, baseline, ventanas temporales |
| `ML_CONFIG` / `GRID_PARAMS` | SVM + GridSearchCV |
| Rutas | `PROJECT_ROOT`, `DATA_RAW_DIR`, `DATA_PROCESSED_DIR`, `DATASET_MAESTRO_PATH` |

### 2️⃣ `utils.py` - Utilidades Reutilizables

Funciones auxiliares de propósito general:

```python
from utils import setup_logging, get_files_recursive, validate_sensor_data

# Logging
logger = setup_logging(__name__)
logger.info("Mensaje informativo")

# Archivos
files = get_files_recursive('data/raw', '*.txt')

# Validación
is_valid, issues = validate_sensor_data(df)
```

**Principales utilidades:**
- `setup_logging()` - Configurar logger
- `validate_file_path()` - Validar archivos
- `get_files_by_pattern()` - Buscar archivos
- `validate_sensor_data()` - Validar datos de sensores

### 3️⃣ `phase_1_3_feature_extraction.py` - Extracción de Características

Motor principal que procesa señales de sensores. Soporta dos modos controlados por `FEATURE_MODE` en `config.py`.

**Modo `handcrafted` (V2):**
```python
from phase_1_3_feature_extraction import SignalProcessor, extract_features_from_file

processor = SignalProcessor()
smoothed, normalized = processor.process_signal(signal)
features = processor.extract_features(normalized)
# {'w2-10_max': 0.45, 'w2-10_auc': 12.3, 'w2-10_slope': 0.98, ...}

features = extract_features_from_file(file_path, substance_label='AQ')
```

**Modo `pca_signal` (V3):**
```python
from phase_1_3_feature_extraction import SignalProcessor, PCAFeatureExtractor, extract_segments_from_file

processor = SignalProcessor()
segments = processor.get_signal_segments(normalized)
# {'w0-2': array([...]), 'w2-10': array([...]), 'w10-20': array([...])}

# PCAFeatureExtractor — se ajusta en Phase 4 sobre el dataset completo
extractor = PCAFeatureExtractor()          # o PCAFeatureExtractor.load(path)
extractor.fit(all_segments_by_key)         # un PCA por (sensor, ventana)
pc_scores = extractor.transform(seg, key) # proyección sobre PCs
extractor.save(path)                       # → pca_transformers.pkl
```

**Clases y funciones principales:**

| Nombre | Tipo | Descripción |
|---|---|---|
| `SignalProcessor` | clase | Suavizado Savitzky-Golay + normalización ΔR/R₀ + segmentación |
| `PCAFeatureExtractor` | clase | PCA por (sensor×ventana): fit/transform/save/load |
| `extract_features_from_file` | función | Modo handcrafted: archivo → dict de estadísticos |
| `extract_segments_from_file` | función | Modo PCA: archivo → dict de arrays de señal |

### 4️⃣ `phase_4_dataset_generation.py` - Generación del Dataset

Genera automáticamente el dataset maestro. El comportamiento varía según `FEATURE_MODE`.

```python
from phase_4_dataset_generation import DatasetGenerator, load_dataset

generator = DatasetGenerator(data_dir='data/raw')
df_maestro = generator.generate_dataset()

df = load_dataset('data/raw/dataset_maestro_vinos.csv')
```

**Flujo según modo:**

| `FEATURE_MODE` | Pasadas | Salidas |
|---|---|---|
| `'handcrafted'` | 1 — extrae estadísticos por archivo | CSV con columnas `{sensor}_{ventana}_{max\|auc\|slope}` |
| `'pca_signal'` | 2 — recolecta segmentos → ajusta PCA → proyecta | CSV con columnas `{sensor}_{ventana}_pc{n}` + `pca_transformers.pkl` |

En modo PCA, `pca_transformers.pkl` se guarda en `data/processed/` y es necesario para inferencia futura junto al modelo.

### 5️⃣ `phase_5_model_training.py` - Entrenamiento ML

Entrena modelo SVM con búsqueda de hiperparámetros.

```python
from phase_5_model_training import ModelTrainer

# Crear y entrenar modelo
trainer = ModelTrainer()
success = trainer.train()

# Acceder a resultados
print(trainer.results['best_params'])
print(f"Precisión: {trainer.results['test_accuracy']:.2%}")
```

**Modelo:**
- **Algoritmo**: Support Vector Machine (SVM)
- **Preprocesamiento**: StandardScaler
- **Optimización**: GridSearchCV
- **Validación**: StratifiedKFold

**Hiperparámetros optimizados:**
- Kernel: linear, rbf
- C: 0.1, 1, 10, 100
- Gamma: scale, auto, 0.1, 0.01

## 📊 Salidas del Pipeline

Después de ejecutar `main.py`, se generan:

```
data/
├── raw/
│   ├── dataset_maestro_vinos.csv      ← Generado en FASE 4
│   ├── AQ_Wines/
│   ├── HQ_Wines/
│   ├── LQ_Wines/
│   └── Ethanol/
└── processed/
    ├── best_model.pkl                 ← Generado en FASE 5
    ├── training_results.pkl           ← Generado en FASE 5
    └── visualizations/                ← Nueva carpeta con gráficas
        ├── 01_confusion_matrix.png
        ├── 02_accuracy_comparison.png
        ├── 03_classification_report.png
        ├── 04_distribution_comparison.png
        ├── class_distribution.png
        ├── feature_statistics.png
        └── signal_processing_demo.png
```

## 📈 Visualizaciones Generadas

El pipeline genera automáticamente múltiples gráficas en `data/processed/visualizations/`:

### FASE 4: Análisis del Dataset
- **class_distribution.png** - Distribución de clases (barras y pastel)
- **feature_statistics.png** - Histogramas de características principales
- **signal_processing_demo.png** - Demostración de suavizado y normalización

### FASE 5: Análisis del Modelo
- **01_confusion_matrix.png** - Matriz de confusión con heatmap
- **02_accuracy_comparison.png** - Precisión en entrenamiento vs prueba
- **03_classification_report.png** - Precisión, recall y f1-score por clase
- **04_distribution_comparison.png** - Clases verdaderas vs predichas

### Usar Visualizaciones en tu Código

```python
from utils import plot_signal_processing, plot_class_distribution, plot_feature_statistics

# Visualizar procesamiento de una señal
plot_signal_processing(
    signal_raw=raw_data,
    signal_smoothed=smoothed_data,
    signal_normalized=normalized_data,
    output_path='mi_grafica.png'
)

# Visualizar distribución de clases
plot_class_distribution(df, output_path='clases.png')

# Estadísticas de características
plot_feature_statistics(df, output_path='features.png')
```

## 📝 Logging

Todos los módulos generan logs detallados:

```
2026-05-23 10:30:45,123 - phase_4_dataset_generation - INFO - Buscando archivos de sensores...
2026-05-23 10:30:46,456 - phase_4_dataset_generation - INFO - ✓ Se encontraron 145 archivos
2026-05-23 10:30:50,789 - phase_4_dataset_generation - INFO - ✓ Dataset guardado exitosamente
```

Los logs también se guardan en: `enose_project.log`

## 🔧 Personalización

### Cambiar Parámetros

Edita `config.py`:

```python
# Cambiar frecuencia de muestreo
SIGNAL_PROCESSING['sampling_frequency'] = 20.0

# Cambiar número de folds en CV
ML_CONFIG['n_splits_cv'] = 5

# Agregar hiperparámetros
GRID_PARAMS.append({
    'svm__kernel': ['sigmoid'],
    'svm__C': [0.5, 5, 50]
})
```

### Usar Datos Diferentes

```python
from phase_4_dataset_generation import DatasetGenerator

# Buscar en directorio diferente
generator = DatasetGenerator(data_dir='otra/ruta/datos')
df = generator.generate_dataset(output_path='salida.csv')
```

## ⚠️ Troubleshooting

### "No se encontraron archivos .txt"
- Verifica que los archivos estén en `data/raw/`
- Revisa que los archivos tengan extensión `.txt`
- Busca archivos recursivamente en subdirectorios

### "Dataset vacío después de procesamiento"
- Verifica que los archivos tengan formato correcto
- Revisa los logs para mensajes de error específicos
- Prueba manualmente: `python phase_1_3_feature_extraction.py`

### "No hay suficientes muestras para validación cruzada"
- Reduce `n_splits_cv` en `config.py`
- Usa más datos o cambia `test_size`

## 📚 Referencias

### Documentación de Módulos

Cada módulo tiene docstrings detallados:

```python
from phase_1_3_feature_extraction import SignalProcessor
help(SignalProcessor.process_signal)
```

### Ejemplo Completo

```python
from phase_4_dataset_generation import DatasetGenerator, load_dataset
from phase_5_model_training import ModelTrainer

# 1. Generar dataset
generator = DatasetGenerator()
df = generator.generate_dataset()
print(f"Dataset: {df.shape[0]} muestras, {df.shape[1]} características")

# 2. Entrenar modelo
trainer = ModelTrainer()
trainer.train()

# 3. Acceder a resultados
print(f"Mejores parámetros: {trainer.results['best_params']}")
print(f"Precisión: {trainer.results['test_accuracy']:.2%}")
```

## 🤝 Contribuciones

Para mejorar o extender el código:

1. Mantén el formato de comentarios
2. Actualiza docstrings
3. Agrega parámetros a `config.py`
4. Usa logging en lugar de `print()`

## 📄 Licencia

Proyecto académico - Nariz Electrónica

---

**Última actualización**: Mayo 2026  
**Versión**: 2.0 (Refactorizado y modularizado)
