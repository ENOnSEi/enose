# CLAUDE.md

Guía para Claude Code en este repo. Objetivo: no tener que volver a recorrer el proyecto. Si algo de aquí contradice al código, manda el código — y actualiza este fichero.

## Qué es

Nariz electrónica con **4 sensores de gas TGS (Figaro)**: `tgs2620` (col. `v20`), `tgs2611` (`v11`), `tgs2602` (`v02`), `tgs2600` (`v00`). Una ESP32-S3 lee los ADC y conmuta dos relés (aire limpio / muestra). Una API FastAPI captura las lecturas en Postgres, un *observer* automatiza el ciclo base→medición→cooldown, y un pipeline offline de ML clasifica sustancias. Repo GitHub: `ENOnSEi/enose`, rama `main`, flujo con PRs. Docs y comentarios mayoritariamente en español.

| Carpeta | Estado | Qué es |
|---|---|---|
| `api/` | **activo** | Backend FastAPI (Python ≥3.13, `uv`). Adquisición, observer, export, estadísticas, PCA, outliers |
| `esp32s3/` | **activo** | Firmware PlatformIO (`src/main.cpp`, MQTT). `websockets-read.ino` = firmware WS legacy, solo referencia |
| `implementacion/` | activo | Pipeline ML offline (features handcrafted + LDA/SVM). Lee CSVs de `datasets/` o la API vía `/export/recordings` |
| `datasets/` | datos | 6 CSV legacy: agua, alcohol, caldo_gambas, vino, vinoyagua, vinoagitacionrara (=vino+alcohol) |
| `mosquitto/` | infra | Config del broker (anónimo, puerto 1883) |
| `analog-reader-arduino/`, `serial-reader/` | **legacy** | Arduino por serie a 4 Hz + grabador CSV. No tocar salvo petición |
| raíz | | `Makefile`, `compose.yml` (podman), `SPEC_DESIGN_DEV.md`, `README.md` |

Ficheros ruido en raíz (ignorar): `package.json`/`package-lock.json` (instalan claude-code), `skills-lock.json`, `.claude/AhorrarTokensClaude.md` (reglas de estilo del usuario: respuestas cortas, Edit en vez de Write, no releer, soluciones mínimas, paralelizar tool calls).

## Comandos (desde la raíz, vía Makefile)

```bash
make up / up-build / down / down-v / logs   # stack podman: db (postgres:16) + mosquitto + api
make api-dev        # uv --directory api run uvicorn main:app --reload
make api-test       # uv run python tests/test_analyzer.py  (sin BD ni placa)
make api-calibrate  # uv run python tools/calibrate.py (umbral de pendiente vs datasets/)
make esp-build / esp-upload / esp-monitor   # pio run -d esp32s3
make mqtt-ping / mqtt-readings / mqtt-commands / mqtt-fake-reading   # requiere mosquitto-clients
make run-start NAME=x N=3 MIN=30 / run-stop / run-status              # curl a la API
```

El usuario está en **Windows** (PowerShell + Git Bash); `make`, `podman` y `mosquitto_*` pueden no estar disponibles → usar los comandos equivalentes (`uv --directory api ...`). Swagger: `http://localhost:8000/docs`. CLI interactivo: `python api/cli.py`. Debug en VS Code: `.vscode/launch.json` (rutas de venv estilo Linux).

ML: `cd implementacion && pip install -r requirements.txt && python main.py [--phase 4|5]`; tests `pytest` (testpaths=`pruebas`).

## API (`api/`)

### Arranque (`main.py` lifespan)
1. `create_all` (SQLModel) → `sync_schema_with_alembic` (`app/db/migrations_sync.py`): compara la revisión de la BD con el head de `migrations/versions/` y hace upgrade/downgrade automático; si no hay `alembic_version`, intenta upgrade y si falla hace `stamp head`. Pensado para cambiar de rama sin romper la BD.
2. Siembra `sensor` desde `SENSOR_NAMES` → `sensor_cache {name: id}` (solo sensores con `retired_at IS NULL`).
3. Lanza dos tareas permanentes: `_drain_to_db` y `Observer.run()`. Nada mide hasta `POST /serial/start`.

### Transporte con la placa
`app/services/board.py` es una fachada: `BOARD_TRANSPORT=mqtt` (por defecto, `board_mqtt.py`, paho-mqtt) o `ws` (`board_ws.py`, legacy, conecta a `ESP32_WS_URL`). Interfaz común thread-safe: `start(sensor_names)`, `stop()`, `set_estado(e)`, `get_status()`, `drain()`. El cliente MQTT solo se conecta al hacer `start` y se desconecta en `stop`.

Protocolo (idéntico en WS y MQTT):
- ESP32 → `enose/readings`: `{"type":"reading","arduino_ms":N,"values":{"tgs2620":N,"tgs2611":N,"tgs2602":N,"tgs2600":N}}` cada 200 ms (5 Hz).
- API → `enose/commands`: `{"type":"command","estado":"base|medicion|cooldown"}` o `{"type":"command","action":"stop"}`.
- Las lecturas se emparejan **por nombre**, nunca por posición. Si falta algún sensor de `SENSOR_NAMES`, la lectura se descarta. El `estado` guardado es el que la API cree tener (`_estado`), no el que manda la placa.

### Flujo de datos
```
ESP32 ─MQTT─► board_mqtt._handle_message ─► Queue(maxsize 2000)
  ─► _drain_to_db (cada 0.5 s): INSERT Reading + ReadingValue
        · cualquier valor == 0 ⇒ board.stop() + cierra MS y Sample (fallo de sensor)
        · copia is_stable y has_risen (por sensor) desde measurement_state
  ─► Postgres ─► Observer (cada OBSERVER_POLL_INTERVAL) lee las últimas FETCH_LIMIT lecturas
        ─► SignalAnalyzer ─► board.set_estado()/stop()
```

### Estado compartido (singletons de módulo, sin DI)
- `board_mqtt`/`board_ws`: conexión, cola, `_estado`, `_running`.
- `measurement_state`: `sample_id`, `n_repetitions`, `ms_id` actual, `min_medicion_seconds`, `is_stable`, `sensor_risen`. Lo escribe el router en `/start` y el observer; lo leen drain y observer. `clear()` lo resetea.

### Observer (`app/services/observer.py`)
Máquina: `start_base → waiting_base → measuring → cooldown → start_base`.
- `start_base`: rep += 1; crea MeasurementSet (la rep 1 la crea el router); `set_estado("base")`; `reset(require_rise=False)`.
- `waiting_base`: ventana por `ms_id`; si estable → `medicion`, `reset(require_rise=True)`.
- `measuring`: para cuando la señal lleva **estable de forma continua** ≥ `min_medicion_seconds` (`stable_since`; cualquier inestabilidad lo resetea). Cierra MS (espera hasta 10 s a que se vacíe la cola), `completed_repetitions += 1`. Si era la última rep: cierra Sample y `board.stop()`; si no → `cooldown`.
- `cooldown`: ventana por `sample_id` + `estado='cooldown'`; al estabilizar → siguiente rep. No hay cooldown tras la última.
- Si `running` pasa a False (stop manual o fallo) resetea todo.
- Sin timeouts: si base o medición no estabilizan, espera indefinidamente (pendiente, ver `api/CONTEXT.md`).

### SignalAnalyzer (`app/services/analyzer.py`)
FSM por canal, sin dependencias de BD. Pendiente por mínimos cuadrados (u/s) sobre los últimos `OBSERVER_WINDOW_SECONDS` de tiempo de señal (`arduino_ms`, no reloj de pared). Histéresis: `lower = thr·(1−h)`, `upper = thr·(1+h)` sobre `|pendiente|`. Debounce `OBSERVER_CONFIRM_SECONDS`. Latch `require_rise`: en medición un canal no puede estabilizarse sin haber superado antes `upper` (`has_risen`). Combinación multi-sensor con `OBSERVER_POLICY` = `all|any|majority`. Umbral 7.5 u/s calibrado contra `datasets/` (meseta máx ~5.3, subida mínima ~9.7; rango factible ~6.2–8.4). Recalibrar si cambian sensores o se añaden grabaciones.

### Esquema de BD (SQLModel, Postgres, asyncpg)
```
Sample 1─< MeasurementSet 1─< Reading 1─< ReadingValue >─1 Sensor
Sample 1─< Reading   (Reading.sample_id; cooldown tiene measurement_set_id NULL)
```
- `sample`: `name` (repetible), `n_repetitions` (1–10), `completed_repetitions` (solo lo incrementa el observer al cerrar una rep de forma natural), `started_at`, `stopped_at`, `outlier_detection` (JSONB, NULL = nunca etiquetado).
- `measurementset`: `sample_id`, `repetition_number` (1-based), `started_at`, `stopped_at` (NULL ⇒ incompleto, descartar), `outlier_sensors int[]` (ids de sensor marcados outlier).
- `reading`: `sample_id`, `measurement_set_id`, `arduino_ms` (bigint), `estado` (`base|medicion|cooldown`), `is_stable`, `captured_at`.
- `readingvalue`: PK (`reading_id`, `sensor_id`), `value` int, `has_risen`.
- `sensor`: `name` único, `created_at`, `retired_at`. El cableado (pines ADC) vive **solo** en el firmware.
- "Sample completo de verdad" = `completed_repetitions == n_repetitions AND stopped_at IS NOT NULL` (un `/serial/stop` manual también pone `stopped_at` en el MS en curso).

Migraciones Alembic (`api/migrations/versions/`): `0553fd37cd2d` (sensor: quita `pin`, añade `created_at`/`retired_at`) → `6c0cde90f026` (measurementset.`outlier_sensors`) → `a3f1c9e2b7d4` (sample.`outlier_detection`). Una BD migrada por una rama más nueva sigue funcionando con código antiguo (columna nullable ignorada), pero el arranque avisa y no sincroniza. Al cambiar un modelo: crear migración con `uv run alembic revision --autogenerate -m "..."` desde `api/` (el arranque las aplica solo).

### Endpoints
| Router | Endpoint | Qué hace |
|---|---|---|
| serial | `GET /serial/status` | estado de conexión/cola |
| | `POST /serial/start?name&n_repetitions(1-10)&min_medicion_seconds(30)` | crea Sample + MS rep 1, arranca placa. 400 si ya corre |
| | `POST /serial/stop` | para placa; en background espera cola y cierra MS/Sample |
| | `PUT /serial/estado/{base\|medicion\|cooldown}` | forzar estado — **solo pruebas** |
| sensors | `POST /sensors/{name}/rename {archive_as}` | sustitución física: archiva la fila (retired_at) y crea una nueva con el nombre original |
| export | `GET /export/samples?name&only_fully_complete` | lista (búsqueda parcial ilike por nombre) |
| | `GET /export/samples/{id}` | detalle + MS |
| | `GET /export/recordings?sample_id&only_complete` · `/export/recordings/{ms_id}` | MS pivotados a filas `data,v20,v11,v02,v00,estado,is_stable` (sin cooldown). Lo consume el ML |
| | `GET /export/readings?sample_ids&ms_ids&only_complete&estado&is_stable&has_risen&subtract_base` | export filtrado por reglas de negocio |
| | `GET /export/stable-means[/chart]?sample_ids&is_stable&subtract_base` | media por sensor de la medición por MS (JSON o PNG) |
| | `GET /export/pca[/chart]?sample_ids(≥2)&min_repetitions(3)&is_stable&subtract_base` | PCA 2D: observación = muestra, variable = sensor × posición ordinal de rep. Usa los **últimos** `min_repetitions` MS completos **sin outliers**; excluye muestras con menos (en `excluded_samples`) |
| stats | `GET /measurement-sets/{id}/stats` · `GET /samples/{id}/stats` | min/max/media por fase, delta, diagnóstico (SNR, pendiente estimada, duración de transición) |
| | `POST /samples/{id}/detect-outliers?iqr_factor(1.5)&min_reps(5)&force(false)` | Tukey (Q1−k·IQR, Q3+k·IQR) sobre delta estable (medición−base) por sensor; persiste en `outlier_sensors` y método/parámetros/fecha en `sample.outlier_detection` (JSONB). 400 si hay menos de `min_reps` MS completos o si ya está etiquetado y no se pasa `force=true` |
| charts | `GET /measurement-sets/{id}/chart` | PNG curva de una rep: fases, tramos `is_stable`, fin de medición; `relative` (resta base), `include_cooldown` |
| | `GET /samples/{id}/chart` | PNG reps superpuestas por sensor, alineadas al inicio de medición y relativas a base; outlier rojo, incompleta gris |
| | `GET /export/drift/chart?sample_ids&name&reps=first\|all` | PNG R0 (base estable) por Sample cronológico, franjas por día, color = sustancia |
| | `GET /export/fingerprint/chart?sample_ids&normalize` | PNG radar (medición−base)/base medio por sustancia (+ cada Sample en fino) |
| | `GET /health` | |

### Config (`app/core/config.py`, pydantic-settings, lee `api/.env`)
Ver `api/.env.example`. Claves: `DATABASE_URL` (debe ser `postgresql+asyncpg://…`; para Neon `?ssl=require`, **no** `sslmode`), `BOARD_TRANSPORT`, `ESP32_WS_URL`, `MQTT_*` (topics `enose/readings`, `enose/commands`), `SENSOR_NAMES`, `OBSERVER_*` (WINDOW 4.0, THRESHOLD 7.5, HYSTERESIS 0.15, CONFIRM 1.0, POLICY all, FETCH_LIMIT 300, POLL 1.0, MIN_MEDICION 30.0). En compose, `DATABASE_URL`/`MQTT_BROKER_HOST` se sobrescriben con los nombres de servicio (`db`, `mosquitto`). `api/.env` no existe en local ahora mismo.

### Glosario / reglas de dominio
`api/CONTEXT.md` es la fuente de verdad del dominio (Base, Medicion, Sample, MeasurementSet, Cooldown, validez tras crash, sustitución de sensor). Más teoría en `api/docs/` (matemática del analizador, patrón observer, teoría de e-nose). El criterio de stop es **30 s de estabilidad continua** (CONTEXT.md y api/README.md ya lo reflejan).

## Firmware ESP32-S3 (`esp32s3/`)
PlatformIO, `env:esp32-s3-devkitc-1`, lib `PubSubClient`. `include/secrets.h` (gitignored, copiar de `secrets.h.example`): WiFi + IP del broker. Relés: `medicionRelayPin=14` (HIGH en medición), `idleRelayPin=13` (HIGH en el resto). ADC 12 bits. **Pines de sensor aún placeholders (`TODO`: 1, 2, 4, 5)**. El parseo de comandos es por `indexOf` de strings, no JSON real.

## Pipeline ML (`implementacion/`)
Arquitectura Spec → Design → Dev (`SPEC_DESIGN_DEV.md`): `spec/contracts/` (Protocols), `spec/schemas/` (Pydantic), `diseño/adr/` + `design/adr/` (ADRs), `src/enose/` (implementación). Scripts añaden `src` a `sys.path`.
- Entrada legacy: CSV `data,v20,v11,v02,v00,estado` con fases `inicio` (descartar) / `base` (R0) / `medicion`. Etiqueta = nombre de fichero (`SUBSTANCE_LABELS` en `config.py`).
- Señal: Savitzky-Golay (ventana 9, orden 3) + normalización fraccional `(Rs − R0)/R0` sobre el ADC crudo (no sobre la resistencia real). Ventanas temporales desde el inicio de medición: 0–5, 5–15, 15–40 s. `sampling_frequency=4.0` (heredado del Arduino a 4 Hz; la ESP32 va a 5 Hz — tenerlo en cuenta).
- Features handcrafted: max, AUC, slope por sensor×ventana + ratios entre pares (`SENSOR_RATIO_PAIRS`) → ~60 features. Modo alternativo `FEATURE_MODE='pca_signal'` (PerKeyPCA).
- Clasificador activo: `CLASSIFIER='lda'` (LDA con shrinkage, ganó en `compare_models.py`); `svm` disponible. `StandardScaler → clf`, GridSearchCV + StratifiedGroupKFold, métrica `balanced_accuracy`. Grupo de CV según `GROUP_BY` (`config.py`): `'sample'` (defecto; columna `Grupo`=`sample_<id>` que escribe `train_from_api.py`, todas las reps de un Sample en el mismo lado del split) o `'recording'` (una rep = un grupo, cifra optimista). CSV legacy sin `Grupo` caen a `'recording'`. Lógica común en `pipeline/dataset.py::derive_groups`. El trainer reporta `cv_score_grouped` vs `cv_score_per_row` (`cv_inflation`) y falla con mensaje explicativo si una clase tiene un solo Sample → necesita ≥2 Samples por clase.
- Desde la API (camino actual): `train_from_api.py [--sample-ids …]`, `predict_from_api.py --ms-id N | --sample-id N` (soft vote entre reps), `visualize_from_api.py`, `check_repeatability.py` (reps sospechosas por distancia en z-score), `reproducibility_report.py [--scale frac|delta]` (CV dentro/entre Samples, ICC de tanda, tendencia rep1→repN, CV de R0; lógica en `enose/report/reproducibility.py`, salida en `datos/procesados/reproducibilidad/`), `confounder_test.py [--only-first-rep]` (entrena solo con features de la fase base y test de permutación por Sample: si acierta por encima del azar, el modelo aprende el día y no el olor; lógica en `enose/model/confounder.py`, salida `confounder_test.json`). Punto único de extracción: `enose/io/api.py::recording_to_features` (mismo código en train e inferencia). Default API `http://127.0.0.1:8000`.
- Salidas en `implementacion/datos/procesados/` (gitignored): `dataset_maestro.csv`, `best_model.pkl`, `model_card.json` (datos, ms_ids, hash, commit, config de features, métricas; `enose/model/model_card.py`), gráficas. `predict_from_api.py` lee la ficha y solo avisa si la config de features ha cambiado o falta.
- Bug conocido: `predict_from_api.py --sample-id` falla con modelos de 2 clases (`get_scores` descarta el `decision_function` escalar del caso binario). Informes en `informes/`, logs en `registros/`.

## Trampas conocidas
- `DATABASE_URL` es obligatoria (sin default en `config.py`): sin `api/.env` la API no arranca. La antigua URL de Neon con contraseña sigue en el historial de git (desde `d9e5a2c`) → hay que rotarla en Neon.
- El export mapea nombre de sensor → columna `v20/v11/v02/v00` con un dict fijo (`_SENSOR_NAME_TO_COL` en `routers/export.py`); un sensor con otro nombre (p. ej. uno archivado) no aparece. `SENSOR_ID_TO_COL` allí no se usa.
- `routers/measurement_sets.py` y `routers/charts.py` importan helpers privados de `routers/export.py` (`_compute_stable_means`, `_get_sensor_map`, `_fetch_means_by_estado`, `_SENSOR_COLORS`).
- `schemas/reading.py::SensorReadingOut` es legacy (columnas fijas v20…).
- Lecturas con cualquier valor 0 abortan la medición entera.
- En `_drain_to_db`, sensores de la lectura no presentes en `sensor_cache` se ignoran silenciosamente.
- `POST /sensors/{name}/rename` **requiere reiniciar la API**: `sensor_cache` se construye una vez en el lifespan, así que hasta reiniciar las lecturas nuevas se guardan con el `sensor_id` archivado (el docstring dice lo contrario). Las lecturas del sensor archivado salen a 0 en los exports.
- `/export/readings?estado=cooldown` devuelve listas vacías: las lecturas de cooldown tienen `measurement_set_id` NULL y el endpoint selecciona por MS.
- Stats (`/measurement-sets/{id}/stats`): min/max/media son de los **últimos 5 s** de cada fase; `slope_estimate` = delta/5 (no es una pendiente medida); `transition_duration_s` = duración de la **base** (primera lectura base → primera de medición).

## Reproducibilidad: estado y siguientes pasos (actualizado 2026-10-03)
Línea de trabajo abierta. Al retomarla, leer esto primero.

**Documentos locales** (raíz del repo, todos en `.gitignore`, no están en GitHub; se pasan al equipo a mano):
- `Obstáculos Reproducibilidad.odt`: **plan maestro**, 24 puntos con prioridad, estado (resuelto/parcial/pendiente/bloqueado), qué se hizo y cómo. Mantenerlo al día cuando se cierre un punto (se edita reescribiendo `content.xml`; LibreOffice sirve para validar/convertir).
- `Apuntes ENose.pdf` (funcional, foco en análisis y decisiones) y `Guía API ENose.pdf` (uso de cada endpoint). Generadores en `notas/generadores/` (ver su `LEEME.md`). Si cambia un endpoint o el análisis, regenerarlos.

**Rama** `reproducibilidad-quick-wins` (subida; PR a `main` pendiente). Commits: `0598363` (puntos 23, 19, 9), `808f271` (8, 17, 7 parcial, 21) y el de gráficos (`routers/charts.py`). El usuario hace los commits él mismo: darle comandos `git add` + mensaje.

**Hecho:** 9 confounder test · 8 informe de reproducibilidad · 17 model card · 7 outliers configurables + `sample.outlier_detection` (falta la escala Rs/R0) · 19 credenciales fuera del código (contraseña de Neon **sin rotar**: el usuario decidió seguir con la antigua de momento) · 21 docs · 23 test_phase5 · gráficos nuevos (curva de rep, reps superpuestas, deriva de R0, huella radar).

**Pendiente crítico, en orden:**
1. Ejecutar `confounder_test.py` (con y sin `--only-first-rep`) y `reproducibility_report.py` con los datos reales de Neon, y anotar el resultado en el `.odt`. **Aún no se ha hecho**: es la línea base para medir mejoras.
2. Protocolo y campaña (puntos 12–15): procedimiento escrito, muestra de referencia por sesión, orden aleatorio, ≥5 sesiones en días distintos. No es código; es lo que de verdad demuestra reproducibilidad.
3. Esquema eléctrico de la placa → fórmula de Rs (punto 3) y pines reales del firmware (20). Bloqueado: hace falta que el equipo lo aporte.
4. 4 Hz frente a 5 Hz y R0 por mediana de base estable (puntos 4 y 5). Cambian features → reentrenar; hacerlo tras el punto 1 para comparar.
5. Sesión, catálogo de sustancias, temperatura/humedad, `Sample.config` (puntos 1, 2, 11, 16). Requieren decisiones del equipo (ya se les ha planteado por WhatsApp).
6. Recalibrar `OBSERVER_SLOPE_THRESHOLD` con datos de la ESP32 (se calibró con el Arduino).
7. Menores: rotar contraseña de Neon, bug 24 (predict con 2 clases), bug del rename de sensor (no está en el `.odt`; candidato a punto 25), PCA por repetición (punto 6), corrección de deriva (10), uv en el ML (18), export sin columnas fijas (22).

**Entorno:** `api/.env` existe y apunta a **Neon** (credencial antigua, formato asyncpg). Neon estaba en la revisión `6c0cde90f026` con 77 Samples el 2026-10-03; el primer arranque de la API desde esta rama aplica `a3f1c9e2b7d4` (columna nueva, compatible con `main`). No aplicar migraciones en Neon sin que el usuario lo decida.

**Cómo probar sin tocar Neon:** Postgres desechable con `pgserver` (solo tiene wheels hasta Python 3.12: `uv run --no-project --python 3.12 --with pgserver python -c "import pgserver; print(pgserver.get_server(r'<dir>', cleanup_mode=None).get_uri())"`), y ejecutar la API o los scripts con `DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:<puerto>/postgres`. Pararlo con el `pg_ctl.exe` del paquete (`-D <dir> stop`). Tests del ML: `uv run --no-project --python 3.13 --with-requirements requirements.txt --with pytest python -m pytest` desde `implementacion/` (55 tests).

## Historial reciente (para contexto)
Rama `reproducibilidad-quick-wins` (ver sección anterior). Commit directo en main `11653b6`: validación agrupada por Sample (`GROUP_BY`, tests en `pruebas/unitarias/test_grouping.py`). PR #10 `outliers`: endpoint de detección de outliers + selector de MS para PCA y búsqueda por nombre. PR #9 `feature-bbdd-interface`: endpoints de export/stats. PR #8 `sensor-identity-cleanup`: Alembic + auto-reconciliación, rename de sensor, quitar `pin`. Antes: migración WS→MQTT, Makefile, compose con podman, PCA en la API. Ramas remotas: `fastapi-init`, `feature/model`, `joel`, `sensor-identity-cleanup`.
