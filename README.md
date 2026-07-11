# enose

Hardware & Software para una nariz electrónica básica y ampliable.

Este repositorio agrupa el trabajo del equipo. Cada bloque vive en su propia carpeta
para no pisarse entre ramas.

## Contenido

| Carpeta | Descripción |
|---|---|
| [`api/`](api/) | Backend FastAPI: adquisición de datos, observador en tiempo real y API REST. Habla con la placa por MQTT. |
| [`esp32s3/`](esp32s3/) | Firmware PlatformIO para la ESP32-S3: lee los 4 sensores y publica/recibe por MQTT. |
| [`analog-reader-arduino/`](analog-reader-arduino/) | Sketch de Arduino: lee 4 sensores TGS y los vuelca por serie cada 250 ms. |
| [`serial-reader/`](serial-reader/) | Cliente Python que lee el puerto serie y graba un CSV etiquetando la fase (`inicio`/`base`/`medicion`). |
| [`datasets/`](datasets/) | Grabaciones CSV de las mezclas medidas (una por fichero). |
| [`implementacion/`](implementacion/) | Pipeline de ML: procesamiento de señal, extracción de características y clasificación SVM. |

## Ejecutar desde la raíz

Cada subproyecto define sus propias librerías (`api/pyproject.toml`,
`esp32s3/platformio.ini`), pero se manejan desde la raíz sin `cd` mediante el
`Makefile`:

```bash
make            # lista todos los comandos disponibles
make up         # levanta API + Mosquitto + Postgres (podman compose)
make api-dev    # API con autoreload
make api-test   # tests del analizador
make esp-build  # compila el firmware de la ESP32
make esp-upload # flashea la ESP32
make esp-monitor# monitor serie
```

## Hardware y formato de datos

La nariz usa **4 sensores TGS** (Figaro): `v20`=TGS2620, `v11`=TGS2611,
`v02`=TGS2602, `v00`=TGS2600. El Arduino los muestrea cada 250 ms (~4 Hz) y el
`serial-reader` guarda cada grabación como un CSV:

```
data,v20,v11,v02,v00,estado
0,24,10,70,17,inicio
...
```

- `data`   : timestamp en ms (Arduino `millis()`).
- `v20..v00`: lecturas analógicas de los 4 sensores.
- `estado` : fase del experimento — `inicio` (calentamiento, se descarta),
  `base` (aire limpio → línea base R0) y `medicion` (respuesta al estímulo).

Cada CSV de [`datasets/`](datasets/) es **una grabación de una mezcla**. Mezclas
medidas hasta ahora:

| Fichero | Mezcla |
|---|---|
| `agua.csv` | 100% agua |
| `alcohol.csv` | 100% alcohol etílico |
| `vino.csv` | 100% vino (12.5º) |
| `vinoyagua.csv` | 50% vino + 50% agua |
| `vinoagitacionrara.csv` | 50% vino + 50% alcohol etílico |

## Proyecto: pipeline de ML (implementacion/)

El pipeline (Fases 4 y 5), su documentación y sus tests están en
[`implementacion/`](implementacion/). Para los detalles —arquitectura, inicio rápido,
configuración y cómo extenderlo— consulta **[implementacion/README.md](implementacion/README.md)**.

Inicio rápido:

```bash
cd implementacion
pip install -r requirements.txt
python main.py --phase 4    # genera el dataset maestro desde datasets/*.csv
```

## Referencia

Macias, M. M. et al. "Electronic Nose for Wine Discrimination." *Sensors* 13.5 (2013): 5528–5543.
