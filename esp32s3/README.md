# ENose ESP32-S3 firmware (MQTT)

PlatformIO project for the ESP32-S3 node. Reads the 4 TGS gas sensors and talks to
the API over **MQTT** through a Mosquitto broker on the same WiFi (addressed by IP).

## Transport

| Direction | Topic | Payload |
|---|---|---|
| ESP32 → API | `enose/readings` | `{"type":"reading","arduino_ms":N,"values":{"tgs2620":N,...}}` |
| API → ESP32 | `enose/commands` | `{"type":"command","estado":"base\|medicion\|cooldown"}` / `{"type":"command","action":"stop"}` |

Payloads are identical to the legacy WebSocket firmware (`websockets-read.ino`,
kept for reference); only the transport changed.

## Setup

```bash
cp include/secrets.h.example include/secrets.h   # then edit WiFi + broker IP
pio run                                           # build
pio run -t upload                                 # flash
pio device monitor                                # serial logs
```

`secrets.h` holds WiFi credentials and the broker host/port and is gitignored.
Set `MQTT_BROKER_HOST` to the IP of the machine running `docker compose up` (see
the repo-root `compose.yml`, which runs the API + Mosquitto broker).
