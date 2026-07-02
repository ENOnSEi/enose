# Ejemplo numérico paso a paso: de voltajes a predicción

Walkthrough simplificado de las 4 etapas del pipeline con números de juguete
(2 sensores, 1 ventana temporal, 5 segundos). El modelo real usa 4 sensores × 3
ventanas → 60 features, pero la lógica es exactamente la misma. Para el detalle
completo del pipeline real ver
[como_funcionan_las_features_y_el_modelo.md](como_funcionan_las_features_y_el_modelo.md).

---

## 1. Preprocesamiento: de voltajes a señal normalizada

### Concepto

El sensor entrega una señal sucia: ruido de alta frecuencia y un nivel base que
depende del estado del hardware en ese momento (temperatura, desgaste, drift).
El preprocesamiento hace dos cosas:

1. **Suaviza** con el filtro Savitzky-Golay (regresión polinómica local) — quita
   ruido sin aplanar la altura real del pico.
2. **Normaliza** la señal respecto a su propia línea base en reposo (`R0`), para
   que sea comparable entre sensores y entre sesiones distintas.

```
R_norm = (Rs − R0) / R0
```

`R0` = media de la fase `base` (aire limpio). `Rs` = lectura suavizada en cada
instante de la fase `medicion`.

### Ejemplo numérico

Fase `base`: el sensor v20 lee 100 de media en aire limpio, el v11 lee 50. Esos
son `R0`.

Fase `medicion`: se expone el gas y se aplica la fórmula segundo a segundo.

| Tiempo | Cruda v20 | Normalizada v20 | Cruda v11 | Normalizada v11 |
|--------|-----------|------------------|-----------|------------------|
| 0 s | 100 | (100−100)/100 = **0.0** | 50 | (50−50)/50 = **0.0** |
| 1 s | 300 | (300−100)/100 = **2.0** | 75 | (75−50)/50 = **0.5** |
| 2 s | 500 | (500−100)/100 = **4.0** | 100 | (100−50)/50 = **1.0** |
| 3 s | 600 | (600−100)/100 = **5.0** | 110 | (110−50)/50 = **1.2** |
| 4 s | 600 | (600−100)/100 = **5.0** | 110 | (110−50)/50 = **1.2** |

A partir de aquí solo se trabaja con la columna normalizada — la cruda ya cumplió
su función.

---

## 2. Extracción de estadísticos (modo handcrafted)

### Concepto

El clasificador SVM necesita un **vector de longitud fija**, no una serie
temporal. De cada curva normalizada se extraen 3 números que resumen su forma:

| Métrica | Qué mide | Cómo se calcula |
|---------|----------|------------------|
| `max` | Pico absoluto (magnitud de respuesta) | El valor más alto de la curva |
| `slope` | Cinética de adsorción (qué tan rápido sube) | El salto más abrupto entre dos instantes consecutivos |
| `auc` | Volumen total de reacción | Área bajo la curva (regla del trapecio) |

### Ejemplo numérico — sensor v20

- **Max**: el valor más alto de la columna normalizada → **5.0**
- **Slope**: el salto más abrupto ocurre entre 0 s y 1 s (2.0 − 0.0) → **2.0**
- **AUC** (trapecios de los 4 segundos):

```
(0.0+2.0)/2 + (2.0+4.0)/2 + (4.0+5.0)/2 + (5.0+5.0)/2
  = 1.0 + 3.0 + 4.5 + 5.0 = 13.5
```

→ **AUC = 13.5**

### Mismo cálculo — sensor v11

| Métrica | Valor |
|---------|-------|
| `max` | 1.2 |
| `slope` | 0.5 (salto 0 s→1 s) |
| `auc` | 3.3 |

---

## 3. Ratios: aislar la huella química

### Concepto

Los valores absolutos (`max`, `auc`) fallan si la muestra se acerca o se aleja
del sensor: menos gas llega, y **todo** baja proporcionalmente. El ratio entre
dos sensores divide sus respuestas, **cancelando algebraicamente** la variable
"concentración / distancia". Lo que queda es la proporción pura entre gases —
la huella dactilar química de la sustancia, no de la medición.

### Ejemplo numérico

Dividimos el pico del sensor de alcoholes (v20) entre el del sensor de metano (v11):

```
ratio = max(v20) / max(v11) = 5.0 / 1.2 = 4.17
```

**Prueba de invarianza**: si la copa de vino se aleja y al sensor le llega la
mitad de gas, v20 marcaría 2.5 y v11 marcaría 0.6:

```
ratio = 2.5 / 0.6 = 4.17   ← idéntico
```

La intensidad cambió a la mitad, pero el ratio no se movió. Eso es exactamente
lo que se necesita: una feature que dependa de **qué es** la sustancia, no de
**cuánta** llegó al sensor.

### El vector de características

Con 2 sensores y 1 ventana, el vector de esta grabación es:

```
[max_v20, slope_v20, auc_v20, max_v11, slope_v11, auc_v11, ratio_v20_v11]
  = [5.0,    2.0,      13.5,    1.2,     0.5,       3.3,     4.17]
```

7 números para este ejemplo simplificado. En el modelo real, con 4 sensores y 3
ventanas temporales, el mismo proceso genera **60 números** por grabación.

---

## 4. Clasificación final: pipeline SVM

### Concepto

Las características tienen escalas muy distintas — un `auc` de 13.5 frente a un
`slope` de 0.5. El SVM trabaja con geometría (distancias entre puntos), así que
sin corregir esto la feature de magnitud mayor dominaría por pura escala, no por
relevancia real. Se soluciona estandarizando cada feature a media 0 y desviación
1 (Z-score) antes de entrenar.

```
z = (x − μ) / σ
```

`x` = valor de la feature en esta muestra. `μ`, `σ` = media y desviación
estándar de esa misma feature en el conjunto de entrenamiento.

### Ejemplo numérico

Supongamos que, en el histórico de entrenamiento, la feature `ratio_v20_v11`
tiene media `μ = 3.0` y desviación `σ = 1.0`.

Escalamos nuestro ratio de 4.17:

```
z = (4.17 − 3.0) / 1.0 = 1.17
```

**Inferencia**: el SVM recibe el vector completo ya escalado (todos los valores
rondando entre -3 y +3) y evalúa de qué lado del hiperplano de decisión cae,
para devolver la predicción final — por ejemplo, `"Vino Dummy"`.

---

## Resumen del flujo

```
Voltaje crudo (ruidoso)
   │  Savitzky-Golay + normalización (Rs−R0)/R0
   ▼
Señal normalizada
   │  max, slope, auc por sensor × ventana
   ▼
Estadísticos (36 en el modelo real)
   │  ratios entre pares de sensores por ventana
   ▼
Vector de características (60 en el modelo real)
   │  StandardScaler (Z-score)
   ▼
Vector escalado
   │  SVM (hiperplano de decisión)
   ▼
Predicción: la sustancia
```
