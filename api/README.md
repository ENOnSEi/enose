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
- Crea las tablas si no existen
- Puebla la tabla `sensors` con los sensores configurados
- Inicia el observer y el drain en background (el lector serial arranca al llamar a `/serial/start`)

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

Para añadir sensores nuevos, inserta en `sensors` y actualiza `SENSOR_NAMES` / `SENSOR_PINS` en `.env`.

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
    │ SlopeAnalyzer.all_stable()
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

### Parámetros del observer (configurables en `.env`)

| Variable                        | Default | Descripción                                      |
|---------------------------------|---------|--------------------------------------------------|
| `OBSERVER_WINDOW`               | 60      | Lecturas usadas para calcular la pendiente (15s a 4 Hz) |
| `OBSERVER_SLOPE_THRESHOLD`      | 1.0     | Umbral de pendiente (unidades/segundo) para "estable" |
| `OBSERVER_POLL_INTERVAL`        | 1.0     | Segundos entre cada comprobación del observer    |
| `OBSERVER_MIN_MEDICION_SECONDS` | 30.0    | Tiempo mínimo en medicion. El stop requiere que se cumplan AMBAS condiciones: mínimo transcurrido Y pendiente estable |

`OBSERVER_SLOPE_THRESHOLD` necesitará calibración con datos reales una vez se hayan recogido
las primeras sesiones.
