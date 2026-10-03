# ENose API

Backend FastAPI de la nariz electrónica. Recibe por **MQTT** las lecturas de la ESP32-S3
(4 sensores TGS a 5 Hz), las guarda en PostgreSQL y automatiza el ciclo
base → medición → cooldown con un *observer*. También expone endpoints de export,
estadísticas, PCA y detección de outliers para el pipeline de ML (`../implementacion`).

## Requisitos

- Python 3.13+, [uv](https://docs.astral.sh/uv/)
- PostgreSQL (local, el de `compose.yml` o Neon)
- Broker MQTT (Mosquitto, ver `../mosquitto/` y `../compose.yml`)
- ESP32-S3 con el firmware de `../esp32s3/` publicando en el broker

## Configuración

```bash
cp .env.example .env
```

Edita `.env`. `DATABASE_URL` es **obligatoria** (no tiene valor por defecto) y debe usar el driver
asyncpg:

```
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/enose_db
# Neon: postgresql+asyncpg://USER:PASSWORD@HOST/neondb?ssl=require   (no sslmode/channel_binding)
BOARD_TRANSPORT=mqtt            # "ws" = WebSocket directo a la placa (legacy)
MQTT_BROKER_HOST=localhost      # en compose: mosquitto
MQTT_BROKER_PORT=1883
```

El resto de claves (topics MQTT, `SENSOR_NAMES`, `OBSERVER_*`) están en `.env.example`.
Con `podman compose` (`make up` desde la raíz) `DATABASE_URL` y `MQTT_BROKER_HOST` ya vienen
definidos con los nombres de servicio.

## Arrancar la API

```bash
uv run uvicorn main:app --reload      # o, desde la raíz: make api-dev
```

Al arrancar:
- Crea las tablas si no existen (bootstrap para una BD nueva)
- Sincroniza el esquema con Alembic: si la revisión aplicada en la BD queda por detrás o por delante de la que conocen los ficheros de `migrations/` de la rama/commit actual, aplica `upgrade`/`downgrade` automáticamente (ver sección "Migraciones" más abajo)
- Puebla la tabla `sensor` con `SENSOR_NAMES`
- Inicia el observer y el drain en background. **Nada se mide hasta `POST /serial/start`**: el cliente MQTT solo se conecta al hacer start y se desconecta en stop.

## Migraciones (Alembic)

El esquema de la BD se versiona con [Alembic](https://alembic.sqlalchemy.org/) en `migrations/`. `env.py` toma la URL de conexión de `settings.DATABASE_URL` (no de `alembic.ini`), así que un solo `.env` gobierna tanto el runtime como las migraciones.

```bash
uv run alembic revision --autogenerate -m "descripción del cambio"   # generar una migración a partir del diff de modelos
uv run alembic upgrade head                                          # aplicar migraciones pendientes
uv run alembic downgrade -1                                          # revertir la última migración
uv run alembic current                                               # ver la revisión aplicada en la BD
```

En cada arranque, `sync_schema_with_alembic()` (`app/db/migrations_sync.py`) compara la revisión almacenada en la BD contra la que la rama/commit actual conoce (los ficheros presentes en `migrations/versions/`):
- Si la BD está por detrás → `upgrade head`.
- Si la BD está por delante pero la revisión sigue estando entre los ficheros presentes → `downgrade` hasta el head actual.
- Si la revisión de la BD no aparece entre los ficheros presentes (p. ej. acabas de hacer `git checkout` a una rama/commit anterior a esa migración) → se omite la sincronización automática y se registra un aviso; hay que cambiar de rama o ejecutar `alembic upgrade`/`downgrade` a mano.

## CLI

Desde otra terminal, en la carpeta `api/` (con la API arrancada):

```bash
python cli.py                              # menú interactivo
python cli.py start "nombre" 3             # iniciar un Sample de 3 repeticiones
python cli.py start                        # pide nombre y repeticiones
python cli.py stop                         # detener
python cli.py status                       # estado de la conexión y la cola
python cli.py base | medicion | cooldown   # forzar estado (solo pruebas)
```

## API REST

Documentación interactiva en `http://localhost:8000/docs`.

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Estado de la API |
| GET | `/serial/status` | Estado de la conexión con la placa y de la cola |
| POST | `/serial/start?name&n_repetitions&min_medicion_seconds` | Crea el Sample y la rep 1 y arranca la placa (400 si ya está midiendo) |
| POST | `/serial/stop` | Parada manual; cierra MS/Sample cuando se vacía la cola |
| PUT | `/serial/estado/{base\|medicion\|cooldown}` | Forzar estado (solo pruebas) |
| POST | `/sensors/{name}/rename` | Sustitución física de un sensor (archiva la fila antigua) |
| GET | `/export/samples`, `/export/samples/{id}` | Listado y detalle de Samples |
| GET | `/export/recordings[/{ms_id}]` | Grabaciones pivotadas (lo consume el ML) |
| GET | `/export/readings` | Export filtrado por estado/estabilidad/sample/MS |
| GET | `/export/stable-means[/chart]` | Media estable por sensor y MS |
| GET | `/export/pca[/chart]` | PCA 2D entre Samples |
| GET | `/measurement-sets/{id}/stats`, `/samples/{id}/stats` | Estadísticas y diagnóstico por fase |
| POST | `/samples/{id}/detect-outliers?iqr_factor&min_reps&force` | Etiqueta reps outlier por sensor (Tukey); guarda método y fecha en `Sample.outlier_detection` |

## Arquitectura

### Base de datos

```
Sample 1─< MeasurementSet 1─< Reading 1─< ReadingValue >─1 Sensor
Sample 1─< Reading            (las lecturas de cooldown no tienen measurement_set_id)
```

- `Sample`: una sustancia medida N veces seguidas (`name`, `n_repetitions`, `completed_repetitions`, `outlier_detection`).
- `MeasurementSet`: una repetición base→medición (`repetition_number`, `stopped_at`, `outlier_sensors`). `stopped_at = NULL` ⇒ incompleta.
- `Reading`: una lectura de la placa (`arduino_ms`, `estado`, `is_stable`). `ReadingValue`: una fila por sensor.
- `Sensor`: `name` único, `retired_at`. El emparejamiento con las lecturas es **por nombre**; el
  cableado (pines ADC) vive solo en el firmware.

Reglas de dominio completas en [CONTEXT.md](CONTEXT.md).

### Flujo de datos en runtime

```
ESP32-S3 ──MQTT enose/readings (5 Hz)──► board_mqtt (hilo de paho-mqtt)
    │ put(arduino_ms, {tgs2620: v, ...}, estado)
    ▼
queue.Queue  ←── puente thread-safe
    │ drain() cada 500 ms
    ▼
_drain_to_db (tarea async) ── Reading + ReadingValue → INSERT
    │                          (cualquier valor 0 ⇒ fallo de sensor: para todo)
    ▼
PostgreSQL ── últimas N lecturas ──► Observer (poll cada 1 s) ── SignalAnalyzer
    │
    ▼
board.set_estado() / stop() ──MQTT enose/commands──► ESP32 (conmuta relés)
```

### Ciclo de vida de un Sample

```
POST /serial/start → Sample + MeasurementSet rep 1 → board.start()
  base:      espera a que la señal se estabilice → set_estado("medicion")
  medicion:  cada sensor debe subir y luego estabilizarse; para cuando la señal lleva
             estable de forma CONTINUA ≥ min_medicion_seconds (30 s por defecto)
             → cierra el MeasurementSet
  cooldown:  (si quedan reps) espera a que se estabilice → siguiente rep (vuelve a base)
  última rep: cierra el Sample y board.stop()

También: POST /serial/stop (parada manual) o un valor 0 en cualquier sensor (fallo).
```

### Analizador de señal (`SignalAnalyzer`)

El analizador ([app/services/analyzer.py](app/services/analyzer.py)) decide, por cada sensor de
forma independiente, si la señal está **subiendo** o **estabilizada**. El Observer no calcula
nada: solo le pasa muestras y actúa cuando el analizador **confirma una transición**.

Cuatro mecanismos para que la decisión sea fiable con sensores TGS (ruidosos y con deriva):

1. **Regresión sobre ventana deslizante** — la pendiente se ajusta por mínimos cuadrados sobre
   todos los puntos de los últimos `OBSERVER_WINDOW_SECONDS`, no restando dos puntos. Un pico
   aislado apenas la mueve.
2. **Estabilidad numérica** — el tiempo de cada ventana se refiere a su primer punto (`t − t0`)
   y se trabaja en segundos, evitando restar `millis()` grandes casi iguales.
3. **Histéresis (banda muerta)** — dos umbrales en vez de uno: se confirma `ESTABILIZADO` cuando
   `|pendiente| < lower` y se vuelve a `SUBIENDO` cuando `|pendiente| > upper`, con
   `lower = umbral·(1−hyst)` y `upper = umbral·(1+hyst)`. Dentro de la banda no se cambia de
   estado, lo que evita el *chattering*. Se mide la **magnitud** de la pendiente y el umbral es
   un valor pequeño positivo, de modo que la señal plana (pendiente ≈ 0) cae por debajo de
   `lower` y la estabilización sí se confirma.
4. **Debounce temporal** — la condición debe sostenerse `OBSERVER_CONFIRM_SECONDS` (medidos con
   el tiempo de la propia señal) antes de dar el cambio por bueno. Un cruce puntual no dispara.
5. **Latch "primero sube, luego se estabiliza"** (`require_rise`) — en medición la señal arranca
   plana (el olor aún no ha llegado al sensor), lo que el analizador confundiría con "ya
   estabilizado" y dispararía un `stop` prematuro. Un canal solo puede confirmar `ESTABILIZADO`
   si antes ha llegado a subir de verdad (`|pendiente| > upper`). En la fase de base no aplica:
   la línea base es plana y solo debe asentarse.

El estado de cada canal se mantiene entre polls; el Observer llama a `reset()` al parar y al
pasar de base a medicion, para re-detectar la estabilización desde cero en la nueva fase
(con `require_rise=False` en base y `True` en medicion).

La **política multi-sensor** (`OBSERVER_POLICY`) combina los canales: `all` (todos estables,
por defecto), `any` (cualquiera) o `majority` (la mayoría).

Tests del analizador (no requieren BD ni placa):

```bash
uv run python tests/test_analyzer.py
```

**Calibración del umbral** — [tools/calibrate.py](tools/calibrate.py) pasa los CSV reales de
`datasets/` por el analizador (offline, sin placa) y muestra, por sensor, el pico de subida vs.
la pendiente de meseta, más a qué segundo dispararía el `stop` para varios umbrales:

```bash
python tools/calibrate.py
```

El default `OBSERVER_SLOPE_THRESHOLD=7.5` sale de ahí: el rango factible con política `all` es
~6.2–8.4 u/s (por encima de la meseta más alta ≈5.3 u/s y por debajo del pico del sensor que
responde más flojo ≈9.7 u/s). Un umbral más alto deja a ese sensor sin "subir" y la medición no
estabiliza nunca. **Reejecuta la calibración cuando recojas más grabaciones.**

### Parámetros del observer (configurables en `.env`)

| Variable                        | Default | Descripción                                      |
|---------------------------------|---------|--------------------------------------------------|
| `OBSERVER_WINDOW_SECONDS`       | 4.0     | Ventana temporal (segundos) de la regresión de pendiente. La dinámica de los TGS es de segundos |
| `OBSERVER_SLOPE_THRESHOLD`      | 7.5     | Umbral central de pendiente (u/s), pequeño positivo. Calibrado con `datasets/` (rango factible ~6.2–8.4) |
| `OBSERVER_HYSTERESIS`           | 0.15    | Ancho de la banda muerta como fracción del umbral (0.15 → ±15 %) |
| `OBSERVER_CONFIRM_SECONDS`      | 1.0     | Debounce: tiempo que la condición debe sostenerse antes de confirmar |
| `OBSERVER_POLICY`               | all     | Política multi-sensor: `all` / `any` / `majority` |
| `OBSERVER_FETCH_LIMIT`          | 300     | Nº de lecturas recientes que se traen de la BD para cubrir la ventana |
| `OBSERVER_POLL_INTERVAL`        | 1.0     | Segundos entre cada comprobación del observer    |
| `OBSERVER_MIN_MEDICION_SECONDS` | 30.0    | Segundos de estabilidad **continua** exigidos en medicion antes de parar (cualquier inestabilidad reinicia la cuenta). Se puede pasar por Sample en `/serial/start` |

`OBSERVER_SLOPE_THRESHOLD`, `OBSERVER_HYSTERESIS` y `OBSERVER_CONFIRM_SECONDS` necesitarán
calibración con datos reales. El log del observer traza pendiente y estado por canal en cada
poll para facilitarlo (`[observer] waiting   stable=False | tgs2620=+45.2/subi ...`).
