# Cómo funciona el PCA y el modelo — guía del proceso completo

Este documento explica, paso a paso y con el "por qué" de cada decisión, cómo el pipeline transforma las curvas crudas de los sensores en una predicción de calidad de vino.

---

## El problema: de señal temporal a vector de longitud fija

Cada vez que el array de sensores huele una muestra de vino, cada uno de los 6 sensores genera una **curva de resistencia eléctrica en el tiempo** (≈20 segundos, muestreados a 18.5 Hz → ~370 puntos).

```
Resistencia
    │       ╭──╮
    │      ╱    ╲
    │─────╱      ╲──────  ← sensor MQ3_1 durante una medición
    └──────────────────── tiempo (20 s)
```

El clasificador (SVM) necesita vectores de **longitud fija y comparable**. No puede comer series temporales de longitud variable directamente. Por eso existe la cadena de procesamiento.

---

## Fase 4: de señal cruda a segmentos listos para PCA

### Paso 1 — Suavizado (Savitzky-Golay)

El filtro reduce el ruido de alta frecuencia preservando la forma del pico. Sin él, los PCs del PCA capturarían ruido en vez de información real.

```
Señal cruda (ruidosa)  →  Savitzky-Golay (ventana=15, orden=3)  →  Señal suavizada
```

### Paso 2 — Normalización por línea base

La resistencia absoluta varía entre sesiones, temperaturas y dispositivos. Para que las muestras sean comparables:

```
R_normalizada = (R0 - Rs) / R0
```

donde `R0` es la media de los primeros 2 segundos (línea base, antes de oler el vino) y `Rs` es la resistencia en cada instante. El resultado es una señal que parte de 0, sube durante la exposición al vino y puede interpretarse como "cambio relativo respecto al estado en reposo".

### Paso 3 — Segmentación en ventanas temporales

La señal normalizada se divide en 3 ventanas fijas:

| Ventana | Intervalo | Qué captura |
|---------|-----------|-------------|
| `w0-2`  | 0–2 s     | Respuesta inicial, primer contacto con el volátil |
| `w2-10` | 2–10 s    | Respuesta principal, máxima concentración |
| `w10-20`| 10–20 s   | Saturación / estabilización del sensor |

Con 6 sensores × 3 ventanas = **18 combinaciones (sensor × ventana)**. Cada una tiene su propia dinámica y aporta información complementaria.

### Paso 4 — Serialización de segmentos crudos

Cada segmento (un array de ~37 a ~185 puntos según la ventana) se guarda en el CSV como columnas `{sensor}_{ventana}__t000`, `{sensor}_{ventana}__t001`, …, una columna por muestra temporal.

El PCA **no se aplica en este paso**. Esto es importante: si el PCA se ajustara sobre todos los datos aquí (antes del split train/test), el test set contaminaría el modelo → _data leakage_.

---

## Fase 5: PCA + escalado + SVM dentro del Pipeline

A partir del CSV con los segmentos crudos, todo ocurre dentro de un **Pipeline de sklearn** que garantiza que nada se ajusta sobre el test set.

```
DataFrame con segmentos crudos
         │
         ▼
  [1] PerKeyPCA            ← ajusta 18 PCAs, uno por (sensor × ventana)
         │
         ▼
  [2] StandardScaler       ← normaliza cada componente principal a media=0, std=1
         │
         ▼
  [3] SVM (kernel RBF)     ← clasifica en AQ / HQ / LQ
         │
         ▼
    Predicción
```

El Pipeline garantiza que cuando se hace validación cruzada (GridSearchCV), cada fold reajusta los pasos 1 y 2 **solo sobre los datos de entrenamiento de ese fold** y evalúa sobre el de validación sin haber "visto" esos datos. Así la métrica de CV es honesta.

---

## ¿Qué hace el PCA exactamente aquí?

### La idea general

El segmento de la ventana `w2-10` del sensor MQ3_1 tiene ~148 puntos. En el dataset hay 235 muestras. PCA toma esas 235 curvas de 148 dimensiones y busca las **direcciones de máxima variación**.

Dicho de otra forma: entre todos los vinos probados, ¿en qué instantes temporales se diferencian más las curvas de ese sensor? Esos instantes son los que más "votan" en las primeras componentes principales (PCs).

```
235 muestras × 148 dimensiones  →  PCA  →  235 muestras × k dimensiones
                                            (k << 148, captura 95% varianza)
```

### Por qué un PCA por (sensor × ventana) y no uno global

Cada combinación tiene su propia escala temporal y su propio patrón de variación. Mezclarlas en un único PCA global "confundiría" al algoritmo: la ventana de 2 s (37 puntos) y la de 10 s (185 puntos) tienen estadísticas totalmente distintas. Separar el PCA por clave mantiene esa estructura física.

### Qué significa cada componente principal (PC)

El PC1 es la dirección de máxima varianza: si proyectamos cada muestra sobre él, obtenemos el número que más separa los vinos entre sí. El PC2 captura la segunda mayor fuente de variación, ortogonal a la primera, y así sucesivamente.

```
PC1: 60% de la varianza → diferencia principal entre vinos
PC2: 20% de la varianza → segunda diferencia
PC3:  8% de la varianza → tercera diferencia
...hasta llegar al 95% acumulado
```

Los PCs no tienen nombre físico concreto (no son "la concentración de etanol" ni "la pendiente del pico") — son combinaciones lineales de las muestras temporales. Su valor está en que concentran la información discriminativa en muy pocas dimensiones.

### ¿Cuántos PCs se usan?

El parámetro `explained_variance_threshold = 0.95` en `config.py` hace que sklearn elija automáticamente el número mínimo de PCs que explican el 95% de la varianza de cada (sensor × ventana). En la práctica esto suele ser 2–5 PCs por clave, frente a los 37–185 puntos originales.

---

## El clasificador: SVM con kernel RBF

### Por qué SVM

Con datasets pequeños (235 muestras, 3 clases), el SVM con kernel RBF funciona bien porque:
- Maximiza el margen de separación entre clases (robusto a overfitting)
- El kernel RBF proyecta implícitamente los datos a un espacio de dimensión infinita, lo que permite separar clases que no son linealmente separables en el espacio de PCs

### Los hiperparámetros que se optimizan

El GridSearchCV busca los mejores valores de:

| Parámetro | Efecto |
|-----------|--------|
| `C` | Penalización por errores de clasificación. Alto → ajuste fino (riesgo overfitting), bajo → margen amplio (más general) |
| `gamma` | Radio de influencia de cada muestra en el kernel RBF. Alto → fronteras muy locales, bajo → fronteras suaves |

El grid actual prueba las combinaciones de `C ∈ {0.1, 1, 10, 100}` y `gamma ∈ {scale, auto, 0.1, 0.01}` con validación cruzada de 3 folds **por grupos** (`StratifiedGroupKFold`, ver abajo). La métrica que decide el mejor modelo es **`balanced_accuracy`** (media de los recalls por clase), no `accuracy`, porque las clases están desbalanceadas (LQ=141, HQ=51, AQ=43) y `accuracy` premiaría el sesgo a la clase mayoritaria.

### Por qué StandardScaler entre PCA y SVM

El SVM con kernel RBF es sensible a la escala de las features. Aunque todos los PCs tienen unidades comparables, su magnitud varía. El StandardScaler los lleva todos a media=0, std=1 antes de pasarlos al SVM, asegurando que ninguna componente domine por su escala y no por su información.

---

## Validación por grupos: por qué el test no es 100 %

Cada vino-lote no se mide una sola vez, sino **~11 veces** (réplicas, sufijo `_R01`, `_R02`, … en el nombre de archivo). Aunque hay 235 mediciones, en realidad solo existen **22 vinos independientes**.

Si se hace un split aleatorio normal, las réplicas casi idénticas del mismo vino acaban repartidas entre train y test. El modelo entonces "reconoce" en el test vinos que ya vio en train → memoriza en vez de generalizar, y la accuracy de test sube de forma artificial (llegaba al **100 %**).

La solución es agrupar por vino-lote (`StratifiedGroupKFold`): el identificador de grupo se obtiene del nombre de archivo quitando el sufijo `_R{RR}`, y se garantiza que **ningún vino aparezca a la vez en train y test**, ni en el split externo ni en los folds de la CV. Con esto la métrica refleja la capacidad real de clasificar **vinos nuevos**:

```
Test accuracy ≈ 86 %   |   balanced accuracy ≈ 79 %
```

Es más baja que el 100 % anterior, pero es la cifra honesta. Bajar de un 100 % "falso" a un 86 % real **no es empeorar**: es dejar de engañarse.

---

## Inferencia: clasificar un vino nuevo

Para predecir la calidad de una nueva muestra con el modelo entrenado:

1. Medir los 6 sensores durante ~20 segundos → 6 series temporales
2. Aplicar suavizado Savitzky-Golay y normalización por línea base (mismo proceso que en entrenamiento)
3. Segmentar en las 3 ventanas temporales → 18 segmentos
4. Recortar/rellenar cada segmento a la longitud fija aprendida en entrenamiento
5. Construir una fila con columnas `{sensor}_{ventana}__t{idx}`
6. Pasar la fila a `best_model.pkl` — el Pipeline (PerKeyPCA + StandardScaler + SVM) hace el resto

```python
import pickle, pandas as pd
model = pickle.load(open("datos/procesados/best_model.pkl", "rb"))
pred = model.predict(nueva_fila_df)   # → ['HQ']
```

> El SVM se entrena con `probability=False` (las métricas usan `predict`, no probabilidades),
> así que `predict_proba` no está disponible. Si necesitas probabilidades, pon
> `probability=True` en `build_pipeline()` y reentrena.

El PCA, el escalado y la clasificación viajan todos dentro del mismo objeto Pipeline — **no se necesita ningún archivo auxiliar** (el antiguo `pca_transformers.pkl` ya no existe).

---

## Resumen visual del flujo completo

```
Archivos .txt (sensores MQ × 20 s)
         │
         │  Fase 4
         ├─ Suavizado Savitzky-Golay
         ├─ Normalización (R0 - Rs) / R0
         ├─ Segmentación en 3 ventanas × 6 sensores = 18 segmentos
         └─ CSV con segmentos crudos (columnas {sensor}_{ventana}__t{idx})
         │
         │  Fase 5 (split por grupos; PCA/scaler solo sobre train de cada fold)
         ├─ PerKeyPCA: 18 PCAs independientes → vector de ~50 features
         ├─ StandardScaler: media=0, std=1
         └─ SVM RBF: GridSearchCV 3-fold StratifiedGroupKFold (balanced_accuracy) → best_model.pkl
         │
         ▼
  Predicción: AQ / HQ / LQ  (test honesto ≈ 86 % acc / 79 % balanced)
```
