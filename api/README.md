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
- Inicia la lectura serial automáticamente en estado `base`

## CLI

Desde otra terminal, en la carpeta `api/`:

```bash
python cli.py              # menú interactivo
python cli.py status       # estado actual y total de lecturas
python cli.py base         # marcar lecturas como "base"
python cli.py medicion     # marcar lecturas como "medicion"
python cli.py stop         # detener la lectura
python cli.py start        # reanudar la lectura
```

## API REST

Documentación interactiva en `http://localhost:8000/docs`

| Método | Ruta                        | Descripción              |
|--------|-----------------------------|--------------------------|
| GET    | `/health`                   | Estado de la API         |
| GET    | `/serial/status`            | Estado del lector serial |
| POST   | `/serial/start`             | Iniciar lectura          |
| POST   | `/serial/stop`              | Detener lectura          |
| PUT    | `/serial/estado/{estado}`   | Cambiar estado (`base` o `medicion`) |

## Esquema de base de datos

```
sensors         id | name    | pin
readings        id | arduino_ms | estado | captured_at
reading_values  reading_id | sensor_id | value
```

Para añadir sensores nuevos, inserta en `sensors` y actualiza `SENSOR_NAMES` / `SENSOR_PINS` en `.env`.
