# ENose API

Lee datos del Arduino por puerto serie y los almacena en PostgreSQL.

## Requisitos

- Python 3.13+, [uv](https://docs.astral.sh/uv/)
- PostgreSQL en local
- Arduino conectado por USB

## Configuración

```bash
cp .env.example .env
```

Edita `.env` con tus valores:

```
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/enose_db
SERIAL_PORT=/dev/ttyACM0   # o /dev/ttyUSB0
SERIAL_BAUD=9600
```

Si el puerto serie da error de permisos:

```bash
sudo chmod a+rw /dev/ttyACM0
```

## Arrancar la API

```bash
uv run uvicorn main:app --reload
```

Al arrancar:
- Crea las tablas si no existen (bootstrap para una BD nueva)
- Sincroniza el esquema con Alembic: si la revisión aplicada en la BD queda por detrás o por delante de la que conocen los ficheros de `migrations/` de la rama/commit actual, aplica `upgrade`/`downgrade` automáticamente (ver sección "Migraciones" más abajo)
- Puebla la tabla `sensors` con los sensores configurados
- Inicia el observer y el drain en background (el lector serial arranca al llamar a `/serial/start`)

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

Desde otra terminal, en la carpeta `api/`:

```bash
python cli.py                        # menú interactivo
python cli.py start "nombre"         # iniciar sesión con nombre
python cli.py start                  # iniciar sesión (pide el nombre interactivamente)
python cli.py stop                   # detener la lectura
python cli.py status                 # estado actual y total de lecturas
python cli.py base                   # forzar estado base (solo pruebas)
python cli.py medicion               # forzar estado medicion (solo pruebas)
```

## API REST

Documentación interactiva en `http://localhost:8000/docs`

| Método | Ruta                        | Descripción                          |
|--------|-----------------------------|--------------------------------------|
| GET    | `/health`                   | Estado de la API                     |
| GET    | `/serial/status`            | Estado del lector serial             |
| POST   | `/serial/start`             | Iniciar lectura (crea MeasurementSet)|
| POST   | `/serial/stop`              | Detener lectura                      |
| PUT    | `/serial/estado/{estado}`   | Cambiar estado (`base` o `medicion`) |

## Arquitectura

### Base de datos

```
MeasurementSet          Sensor
id, started_at,         id, name, pin
stopped_at              (tgs2620/A3, ...)
     │
     │ FK
     ▼
  Reading  ──── ReadingValue ──── FK ──→ Sensor
  id, arduino_ms,    reading_id
  estado,            sensor_id
  captured_at        value
```

`Reading` agrupa los 4 valores de una muestra del Arduino. `ReadingValue` tiene una fila por sensor
por muestra. `MeasurementSet` agrupa todas las lecturas de una sesión (de start a stop).

Para añadir sensores nuevos, actualiza `SENSOR_NAMES` en `.env` (se siembran automáticamente en `sensors`
al arrancar). El emparejamiento con las lecturas del ESP32 es por nombre, no por posición. El cableado
físico (pines ADC) es responsabilidad exclusiva del firmware — no se guarda en la base de datos.

### Flujo de datos en runtime

```
Arduino (USB)
    │ readline() — hilo bloqueante
    ▼
serial_reader (thread)
    │ put(arduino_ms, {tgs2620: v, ...}, estado)
    ▼
queue.Queue  ←── thread-safe bridge
    │ drain() cada 500ms
    ▼
_drain_to_db (async task)
    │ Reading + ReadingValues → INSERT
    ▼
PostgreSQL
    │ SELECT últimas N lecturas
    ▼
Observer (async task, poll cada 1s)
    │ SignalAnalyzer.update() → transición confirmada
    ▼
serial_reader.set_estado() / .stop()
```

La `queue.Queue` actúa como puente entre el hilo bloqueante de pyserial (síncrono) y el event loop
de FastAPI (async). El hilo escribe, el drain async lee — sin bloquear ninguno de los dos.

### Estado compartido entre capas

- `serial_reader` — estado del hilo (running, estado, queue). Protegido con `threading.Lock`.
- `measurement_state` — ID del `MeasurementSet` activo. Lo escribe el router en `/start`, lo leen el drain y el observer.
- `sensor_cache` — `{nombre: id}` construido al arrancar desde DB. Solo lectura, no necesita lock.

### Ciclo de vida de una sesión

```
POST /serial/start
  → crea MeasurementSet en DB
  → measurement_state.set_current(id)
  → serial_reader.start()

          [observer en waiting]
          ← SlopeAnalyzer mide pendiente base
          ← todos estables → serial_reader.set_estado("medicion")
          [observer en measuring]
          ← espera 30s o nueva estabilización
          → MeasurementSet.stopped_at = now()
          → serial_reader.stop()

  También: POST /serial/stop (parada manual)
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
| `OBSERVER_MIN_MEDICION_SECONDS` | 30.0    | Tiempo mínimo en medicion. El stop requiere AMBAS: mínimo transcurrido Y pendiente estable |

`OBSERVER_SLOPE_THRESHOLD`, `OBSERVER_HYSTERESIS` y `OBSERVER_CONFIRM_SECONDS` necesitarán
calibración con datos reales. El log del observer traza pendiente y estado por canal en cada
poll para facilitarlo (`[observer] waiting   stable=False | tgs2620=+45.2/subi ...`).
