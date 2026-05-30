# 📊 Guía de Visualizaciones - Nariz Electrónica

Este documento describe todas las visualizaciones generadas automáticamente por el pipeline.

## 📍 Ubicación de Visualizaciones

Todas las gráficas se guardan en:
```
data/processed/visualizations/
```

## 🎨 Visualizaciones por Fase

### FASE 1-3: Procesamiento de Señal

**Archivo**: `signal_processing_demo.png`

Muestra 3 subgráficas comparando:
1. **Señal Cruda** - Datos originales del sensor (con ruido)
2. **Señal Suavizada** - Después de aplicar media móvil
3. **Señal Normalizada** - Después de normalizar por línea base

**Uso**: Entender el impacto de cada paso del procesamiento

```python
from utils import plot_signal_processing

plot_signal_processing(
    signal_raw=raw_sensor_data,
    signal_smoothed=smoothed_data,
    signal_normalized=normalized_data,
    title="Mi Análisis de Señal",
    output_path="output.png"
)
```

---

### FASE 4: Análisis del Dataset

#### 1. **class_distribution.png**

Muestra la distribución de clases en 2 formatos:
- **Gráfico de barras**: Cantidad de muestras por clase
- **Gráfico de pastel**: Porcentaje de cada clase

**Qué significa**:
- Ayuda a identificar desbalance de clases
- Si el dataset está sesgado hacia una clase, el modelo puede tener sesgo

**Ejemplo de salida**:
```
AQ: 45 muestras (35.2%)
HQ: 38 muestras (29.7%)
LQ: 50 muestras (39.1%)
```

#### 2. **feature_statistics.png**

Histogramas de las 6 características principales con:
- Media aritmética (línea roja punteada)
- Desviación estándar (línea naranja punteada)

**Qué significa**:
- Distribución de cada característica
- Detectar valores atípicos o problemas
- Entender el rango de valores típicos

**Características mostradas**:
- `MQ3_1_max`, `MQ4_1_max`, `MQ6_1_max`
- `MQ3_1_auc`, `MQ4_1_auc`, `MQ6_1_auc`
- ... y más según disponibilidad

---

### FASE 5: Análisis del Modelo

#### 1. **01_confusion_matrix.png**

Matriz de confusión con heatmap (colores azules)

**Cómo interpretarla**:
```
                Predicción
            AQ    HQ    LQ
Real AQ   [10     1     0]    ← Predicciones de AQ
     HQ   [ 2     8     1]    ← Predicciones de HQ
     LQ   [ 0     1     9]    ← Predicciones de LQ
```

**Métricas clave**:
- Diagonal (10, 8, 9): Aciertos
- Fuera diagonal: Errores de clasificación

**Objetivo**: Maximize la diagonal, minimize fuera de diagonal

#### 2. **02_accuracy_comparison.png**

Comparación de barras de precisión:
- **Entrenamiento**: Precisión en datos vistos
- **Prueba**: Precisión en datos nuevos

**Qué significa**:
- Si son muy diferentes → **Overfitting** (memorizado los datos)
- Si son similares → **Buen balance** (generaliza bien)

**Ejemplo**:
```
Entrenamiento: 95.2%
Prueba:        87.5%  ← Un poco de overfitting
```

#### 3. **03_classification_report.png**

Gráfico de barras con 3 métricas por clase:
- **Precisión**: De lo que predijo como X, cuánto fue correcto
- **Recall**: De todas las X reales, cuántas predijo correctamente
- **F1-Score**: Promedio armónico de precisión y recall

**Interpretación**:
- Valores cercanos a 1.0 (100%) = Excelente
- Valores cercanos a 0.0 (0%) = Pobre

**Ejemplo**:
```
AQ:  Precisión=0.91, Recall=0.89, F1=0.90  ← Bueno
HQ:  Precisión=0.85, Recall=0.80, F1=0.82  ← Aceptable
LQ:  Precisión=0.75, Recall=0.82, F1=0.78  ← Necesita mejora
```

#### 4. **04_distribution_comparison.png**

Comparación de 2 gráficos:
- **Izquierda**: Clases reales en datos de prueba
- **Derecha**: Clases predichas por el modelo

**Qué significa**:
- Si son similares → El modelo aprendió bien la distribución
- Si son diferentes → El modelo tiende a predecir unas clases más que otras

---

## 🔍 Cómo Usar las Visualizaciones

### 1. Verificar Calidad del Dataset
```
Revisar: class_distribution.png y feature_statistics.png
✓ ¿Está bien balanceado el dataset?
✓ ¿Hay valores atípicos extremos?
✓ ¿Las características tienen sentido?
```

### 2. Entender el Procesamiento
```
Revisar: signal_processing_demo.png
✓ ¿El suavizado elimina ruido sin perder señal?
✓ ¿La normalización es adecuada?
```

### 3. Evaluar el Modelo
```
Revisar: 01_confusion_matrix.png + 02_accuracy_comparison.png
✓ ¿Qué clases tiene más dificultad?
✓ ¿Hay overfitting?
✓ ¿El modelo es útil para producción?
```

### 4. Optimizar el Modelo
```
Revisar: 03_classification_report.png
✓ ¿Qué clases tienen peor desempeño?
✓ ¿Por dónde empezar las mejoras?
```

---

## 💡 Tips y Trucos

### Si la matriz de confusión muestra errores consistentes
```python
# Revisar qué muestras se clasifican mal
bad_predictions = df[df['label_real'] != df['label_predicho']]
print(bad_predictions)  # Analizar patrones
```

### Si el modelo tiene bajo recall en una clase
```python
# Ajustar el threshold de predicción en config.py
# o rebalancear el dataset
from sklearn.utils.class_weight import compute_class_weight
```

### Si hay overfitting
```python
# En config.py, intentar:
- Aumentar C (regularización menor)
- Cambiar kernel (linear en lugar de rbf)
- Aumentar regularización
```

---

## 📊 Interpretar Números Comunes

### Precision/Recall/F1-Score

| F1-Score | Interpretación |
|----------|----------------|
| 0.90-1.0 | Excelente |
| 0.80-0.89 | Bueno |
| 0.70-0.79 | Aceptable |
| 0.60-0.69 | Pobre |
| < 0.60 | Muy pobre |

### Accuracy

| Precisión | Interpretación |
|-----------|----------------|
| 95%+ | Excelente (cuidado con overfitting) |
| 85-95% | Muy bueno |
| 75-85% | Bueno |
| 65-75% | Aceptable |
| < 65% | Pobre, necesita mejoras |

---

## 🛠️ Generar Visualizaciones Personalizadas

### Crear tu propia gráfica

```python
from utils import (
    plot_signal_processing,
    plot_class_distribution,
    plot_feature_statistics,
    plot_correlation_heatmap
)
from pathlib import Path
import pandas as pd

# Cargar datos
df = pd.read_csv('data/raw/dataset_maestro_vinos.csv')

# Generar múltiples visualizaciones
plot_class_distribution(df, output_path='clases.png')
plot_feature_statistics(df, output_path='features.png')
plot_correlation_heatmap(df, output_path='correlacion.png')
```

### Visualizar datos específicos

```python
import matplotlib.pyplot as plt

# Graficar una característica específica por clase
for clase in df['Calidad_Vino'].unique():
    data = df[df['Calidad_Vino'] == clase]['MQ3_1_max']
    plt.hist(data, alpha=0.5, label=clase)

plt.legend()
plt.savefig('mi_grafica.png')
```

---

## 📱 Exportar Visualizaciones

### Cambiar formato

En `config.py`:
```python
PLOT_CONFIG = {
    'save_format': 'pdf'  # en lugar de 'png'
}
```

Formatos soportados: `png`, `pdf`, `jpg`, `svg`

### Cambiar resolución

```python
# En las funciones de plot, ajustar dpi:
plt.savefig(path, dpi=300)  # Alta resolución
plt.savefig(path, dpi=100)  # Baja resolución
```

---

## 🐛 Solucionar Problemas de Visualización

### "ModuleNotFoundError: No module named 'matplotlib'"
```bash
pip install matplotlib seaborn
```

### "Las gráficas no se guardan"
```python
# Verificar que exista el directorio
from pathlib import Path
Path('data/processed/visualizations').mkdir(parents=True, exist_ok=True)
```

### "Las gráficas se ven cortadas"
```python
# Agregar en config.py:
PLOT_CONFIG = {
    'figsize': (14, 8)  # Más grande
}
```

---

## 📚 Referencias

- [Matplotlib documentation](https://matplotlib.org/)
- [Seaborn gallery](https://seaborn.pydata.org/examples.html)
- [Scikit-learn metrics](https://scikit-learn.org/stable/modules/model_evaluation.html)

---

**Última actualización**: Mayo 2026  
**Versión**: 2.0 con visualizaciones completas
