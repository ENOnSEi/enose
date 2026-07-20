# Guía de uso — capturar, entrenar, predecir

Instrucciones paso a paso para correr todo el pipeline: desde levantar la API hasta
clasificar una muestra nueva con el modelo entrenado. Para entender *por qué* funciona
cada paso (la teoría), ver
[como_funcionan_las_features_y_el_modelo.md](como_funcionan_las_features_y_el_modelo.md)
y [modelos_de_clasificacion.md](modelos_de_clasificacion.md).

---

## 0. Requisitos previos

- **API arriba** y apuntando a la base de datos correcta (`api/.env` → `DATABASE_URL`).
- **Python con dependencias del pipeline ML** (`pandas`, `numpy`, `scikit-learn`,
  `httpx`, `matplotlib`, `seaborn`). En este proyecto se usa el Python 3.12 del sistema
  (no el `.venv` de `api/`, que es solo para FastAPI):
  ```
  python3.12 script.py ...
  ```
- Todos los scripts del pipeline ML viven en `implementacion/` y se ejecutan desde ahí.

### Levantar la API

```bash
cd api
uvicorn main:app --reload
```

Verifica que responde:
```bash
curl http://127.0.0.1:8000/health
# {"status": "ok"}
```

Swagger interactivo en `http://127.0.0.1:8000/docs`.

> **Nota Neon:** si la BD es Neon (serverless), el primer request tras inactividad
> puede devolver `500` por cold-start. Reintenta — no es un bug del código.

---

## 1. Capturar una sustancia nueva

```bash
curl -X POST "http://127.0.0.1:8000/serial/start?name=Mi+Sustancia&n_repetitions=3"
```

Esto:
1. Conecta con la placa ESP32 (vía `ESP32_WS_URL` en `.env`).
2. Crea un `Sample` y arranca el ciclo `base → medicion → cooldown` automático
   (el Observer decide las transiciones por estabilización de pendiente).
3. Repite `n_repetitions` veces.
4. Se detiene sola al completar todas las repeticiones, o con:
   ```bash
   curl -X POST http://127.0.0.1:8000/serial/stop
   ```

Consulta el estado en vivo:
```bash
curl http://127.0.0.1:8000/serial/status
```

**Lógica forense:** si algún sensor lee 0 (fallo de hardware), la medición se aborta
automáticamente y queda marcada como incompleta.

---

## 2. Ver las mediciones capturadas

Hay 4 formas, de más general a más detallada. Empieza por la 2.1 para saber qué hay,
y baja a la 2.2/2.3 cuando necesites el detalle de una sustancia o repetición concreta.

### 2.1 — Lista de sustancias (samples)

```bash
curl http://127.0.0.1:8000/export/samples
```

```json
[
  {"id": 6, "name": "Don Simon Tinto", "n_repetitions": 3, "completed_repetitions": 3, "started_at": "...", "stopped_at": "..."},
  ...
]
```

Aquí ves **qué sustancias hay y cuántas repeticiones tiene cada una completadas**. El
`id` de este JSON es el `sample_id` — úsalo para filtrar en el resto de comandos
(`--sample-ids`, `?sample_id=`).

### 2.2 — Detalle de una sustancia: aquí está el `measurement_set_id`

```bash
curl "http://127.0.0.1:8000/export/recordings?sample_id=6"
```

Devuelve **un objeto por repetición**, con sus lecturas pivotadas:

```json
[
  {
    "measurement_set_id": 9,
    "sample_id": 6,
    "sample_name": "Don Simon Tinto",
    "repetition_number": 1,
    "is_complete": true,
    "readings": [
      {"data": 0, "v20": 85, "v11": 120, "v02": 45, "v00": 90, "estado": "base"},
      ...
    ]
  },
  { "measurement_set_id": 10, "repetition_number": 2, ... },
  { "measurement_set_id": 11, "repetition_number": 3, ... }
]
```

> **El `measurement_set_id` (campo `measurement_set_id` de cada objeto) es el
> identificador de UNA grabación/repetición concreta.** Es lo que le pasas a
> `predict_from_api.py <ms_id>` para clasificarla (ver paso 6).

Si solo quieres ver los `measurement_set_id` sin todas las lecturas:
```bash
curl -s "http://127.0.0.1:8000/export/recordings?sample_id=6" | python -c \
  "import json,sys; [print(r['measurement_set_id'], 'rep', r['repetition_number']) for r in json.load(sys.stdin)]"
```

Por defecto este endpoint solo trae repeticiones **completas**
(`is_complete: true`). Para ver también las incompletas/abortadas:
```bash
curl "http://127.0.0.1:8000/export/recordings?sample_id=6&only_complete=false"
```

### 2.3 — Una sola repetición por su `measurement_set_id`

```bash
curl "http://127.0.0.1:8000/export/recordings/9"
```

Mismo formato que arriba pero un único objeto — útil cuando ya sabes el `ms_id` que
quieres inspeccionar.

### 2.4 — Swagger interactivo (sin curl)

```
http://127.0.0.1:8000/docs
```

Prueba cualquiera de los endpoints anteriores desde el navegador con botones
"Try it out". Útil si no quieres usar la terminal.

### 2.5 — Gráficamente (curvas por sensor, no JSON)

```bash
cd implementacion
python visualize_from_api.py --sample-ids 6
```

Genera en `datos/visualizations/` las curvas crudas y normalizadas de las 3
repeticiones superpuestas, comparativas entre sustancias, etc. Ver detalle de cada
gráfica en el propio script.

---

## 3. Revisar repetibilidad antes de entrenar (opcional pero recomendado)

Detecta repeticiones que se desvían mucho del resto **dentro de cada sample** (posible
fallo de medición vs. variación real). No borra nada — solo marca para que lo revises:

```bash
python check_repeatability.py --sample-ids 6 7 8 9 10 11 12 13
```

Si una rep sale marcada (`<-- REVISAR`):
1. Mira las "features que más se desvían" — te dice qué sensor/ventana es la causa.
2. Inspecciona la curva cruda de esa rep:
   ```bash
   python visualize_from_api.py --sample-ids <id>
   ```
   y mira `01_raw_<sustancia>.png` / `02_norm_<sustancia>.png`.
3. Si hay causa técnica clara (saturación, base inestable, corte prematuro) → considera
   remedir esa repetición. Si no hay causa clara → es variación real, consérvala.

Ver el razonamiento completo en la cabecera de
[`check_repeatability.py`](../check_repeatability.py).

Opciones:
| Flag | Qué hace |
|---|---|
| `--sample-ids 6 7 8` | Solo esos samples (si se omite, analiza todos) |
| `--threshold 2.5` | Sube el umbral de marcado (default `2.0`, más alto = más laxo) |
| `--api-url http://host:8000` | Apunta a otra instancia de la API |

---

## 4. Entrenar el modelo

```bash
python train_from_api.py --sample-ids 6 7 8 9 10 11 12 13 15 16 17
```

Esto:
1. Hace fetch de cada sample vía `GET /export/recordings` (pivota sensores, descarta
   `cooldown`).
2. Extrae las 60 features (36 estadísticos + 24 ratios) por grabación —
   [`enose.io.api.recording_to_features`](../src/enose/io/api.py), el mismo código que
   usa la inferencia.
3. Genera `datos/procesados/dataset_maestro.csv`.
4. Entrena con el clasificador activo (`CLASSIFIER` en
   [`src/enose/config.py`](../src/enose/config.py) — hoy `lda`), con
   `GridSearchCV` + `StratifiedGroupKFold` agrupando por grabación.
5. Guarda `datos/procesados/best_model.pkl` + `training_results.pkl` + visualizaciones
   + informe en `informes/`.

Opciones:
| Flag | Qué hace |
|---|---|
| `--sample-ids 6 7 8` | Solo esos samples (si se omite, usa todos los completos) |
| `--dataset-only` | Solo genera el CSV, no entrena (útil para inspeccionar features) |
| `--api-url http://host:8000` | Apunta a otra instancia de la API |

**Si entrenando con muchas clases y pocas reps falla el GridSearchCV anidado** (p. ej.
LDA exige más muestras que clases por fold), el trainer cae automáticamente a
evaluación **out-of-fold sobre todo el dataset** (sin holdout separado) — verás un aviso
en el log. Es el comportamiento esperado con datos escasos, no un error.

---

## 5. Comparar modelos (opcional, recomendado tras cada sesión nueva)

```bash
python compare_models.py
```

Corre 12 clasificadores con la misma validación (mismo `StratifiedGroupKFold`, misma
métrica `balanced_accuracy`) y saca un leaderboard. Te dice si conviene cambiar el
`CLASSIFIER` activo. Detalle de cada modelo, fortalezas/debilidades y cuándo usar cada
uno en [modelos_de_clasificacion.md](modelos_de_clasificacion.md).

```bash
python compare_models.py --dataset datos/procesados/dataset_maestro.csv --cv 3
```

Si gana un modelo distinto al activo, cámbialo en `CLASSIFIER` (`src/enose/config.py`)
y repite el paso 4.

---

## 6. Predecir una muestra nueva (inferencia)

Esto cierra el loop: medir algo **cuya sustancia no conoces** y que el modelo te diga
qué es.

> **Importante:** el modelo solo puede predecir clases que conoce del training. Si
> mides una sustancia que **no estaba en `--sample-ids` del último entrenamiento**, la
> clasificará como la más parecida de las que conoce (que puede ser incorrecta). Señal
> de alerta: scores de `decision_function` mucho más altos de lo habitual — el modelo
> está extrapolando lejos de su espacio. Solución: añade la sustancia al training y
> reentrena.

### Paso 1 — Captúrala (con 3 repeticiones, recomendado)

```bash
curl -X POST "http://127.0.0.1:8000/serial/start?name=Muestra+Desconocida&n_repetitions=3"
```

Anota el `sample_id` de la respuesta. Espera a que termine (consulta
`GET /serial/status` hasta `running: false`).

> Con `n_repetitions=1` también funciona, pero 3 reps dan una predicción más robusta
> gracias al soft vote (ver paso 3).

### Paso 2 — Averigua los measurement_set_ids

`/serial/start` no devuelve los `measurement_set_id` directamente — consúltalos como
se explica en el paso 2.2 de esta guía:

```bash
curl "http://127.0.0.1:8000/export/recordings?sample_id=<sample_id>"
```

Verás un objeto por repetición, cada uno con su `measurement_set_id`. Para una
predicción agregada (recomendada) no necesitas copiarlos — basta el `sample_id`.

### Paso 3 — Clasifica

**Opción A — Sample completo con soft vote (RECOMENDADO):**

Agrega las N reps promediando sus scores antes de decidir. Una rep ruidosa baja un
poco sus scores pero no veta la predicción — más robusto que votar 3 veces por separado.

```bash
python predict_from_api.py --sample-id <sample_id>
```

Salida:
```
==============================================================
  Sample 22  ('Muestra Desconocida')  — 3 rep(s) validas
==============================================================
  >> PREDICCION AGREGADA (soft vote): Estrella Galicia

  Predicciones individuales por rep:
    rep1: Estrella Galicia  <--
    rep2: Estrella Galicia  <--
    rep3: Estrella Galicia  <--

  Ranking (media de decision_function entre reps):
    1.  +110.945  Estrella Galicia  <--
    2.   +83.795  san miguel cerveza 2
    3.   +54.403  skol cerveza
    4.   +38.253  Don Simon Tinto
    5.   +34.215  1906
```

**Opción B — Una repetición suelta (diagnóstico):**

```bash
python predict_from_api.py --ms-id <measurement_set_id>
```

Útil para inspeccionar rep a rep, pero para producción usa siempre la opción A.

### Cómo interpretar la salida

- **Predicciones individuales**: si las 3 coinciden, el modelo está seguro. Si
  divergen (p. ej. 2 vs 1), revisa la rep discrepante con `visualize_from_api.py`.
- **Ranking de scores**: la diferencia entre el 1º y el 2º importa más que el valor
  absoluto. Salto grande (2×+) → seguro. Salto pequeño → revisar.
- **Scores muy altos** (>3× lo habitual): la sustancia probablemente no está en el
  training — ver aviso al inicio de esta sección.

Opciones:
| Flag | Qué hace |
|---|---|
| `--sample-id X` | Agrega todas las reps del sample X con soft vote |
| `--ms-id X` | Clasifica una sola repetición |
| `--api-url http://host:8000` | Apunta a otra instancia de la API |
| `--model ruta/best_model.pkl` | Usa un modelo distinto al de `datos/procesados/` |

---

## 7. Visualizar (diagnóstico, opcional)

```bash
python visualize_from_api.py --sample-ids 6 7 8
```

Genera en `datos/visualizations/`: señal cruda y normalizada por sustancia (3 reps
superpuestas), comparativa de todas las sustancias, box plots de features, heatmap,
proyección PCA, varianza explicada, repetibilidad (CV%), perfil de respuesta por
sensor, matriz de correlación. Detalle de cada gráfica en el propio script.

---

## Flujo resumen

```
1. POST /serial/start (capturar)
        │
2. GET /export/samples (ver qué hay)
        │
3. check_repeatability.py (detectar reps sospechosas → revisar manualmente)
        │
4. train_from_api.py (fetch → features → dataset_maestro.csv → entrena → best_model.pkl)
        │
5. compare_models.py (¿sigue ganando el clasificador activo? si no, cambia CLASSIFIER y vuelve a 4)
        │
6. Muestra nueva: POST /serial/start (n_repetitions=3) → predict_from_api.py --sample-id <id>  (soft vote de las 3 reps)
```

---

## Problemas comunes

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| `500` en `/export/recordings` | Cold-start de Neon (BD serverless) | Reintenta |
| `ModuleNotFoundError: numpy` | Estás usando el `.venv` de `api/` en vez del Python del sistema | Usa `python3.12` directamente |
| `Modelo no encontrado` en `predict_from_api.py` | No has entrenado todavía | Corre `train_from_api.py` primero |
| `GridSearchCV no viable con estos folds` (warning) | Pocas reps para el nº de clases con el clasificador actual | Normal con datos escasos; el trainer cae a evaluación out-of-fold automáticamente |
| Predicción incorrecta con scores muy altos (10×+) | La sustancia medida no está en el training | Añádela a `--sample-ids` y reentrena |
| `UnicodeEncodeError` al imprimir `→`/`±` en consola Windows | La consola usa `cp1252` | Antepón `PYTHONIOENCODING=utf-8` al comando |
| Dataset vacío / `No hay recordings` | La API no tiene datos para esos `sample_id`, o `only_complete` los está filtrando | Revisa `GET /export/samples`, prueba `only_complete=false` |
