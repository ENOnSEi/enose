# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository structure

This is a multi-component project for an electronic nose (4 TGS gas sensors):

| Folder | What it is |
|---|---|
| `api/` | FastAPI backend — data acquisition, real-time observer, REST API |
| `esp32s3/` | Arduino firmware for the ESP32-S3 board (WebSocket server, reads ADC, controls relays) |
| `implementacion/` | Offline ML pipeline — signal processing, feature extraction, SVM classifier |
| `datasets/` | Raw CSV recordings used for ML training and observer calibration |
| `serial-reader/` | Legacy serial CSV recorder (superseded by the WebSocket-based `api/`) |

## API commands (run from `api/`)

```bash
uv run uvicorn main:app --reload        # start dev server
uv run python tests/test_analyzer.py   # run analyzer tests (no DB or board needed)
python tools/calibrate.py               # calibrate slope threshold against datasets/
```

API docs available at `http://localhost:8000/docs` once running.

## API architecture

The API is the active part of the system. Everything below runs from `api/`.

### Startup (main.py)

On startup, the lifespan context:
1. Creates DB tables (`SQLModel.metadata.create_all`)
2. Seeds the `sensors` table from `SENSOR_NAMES` in `.env` (matched by name against ESP32 readings, not position; physical wiring lives only in firmware)
3. Starts two permanent async background tasks: `_drain_to_db` and `Observer.run()`

The observer and drain run for the lifetime of the process. No measurement is active until `POST /serial/start` is called.

### Data flow

```
ESP32-S3 (WebSocket :81)
    │  JSON: {type:"reading", arduino_ms, values:{tgs2620:N, ...}}
    ▼
board_ws._connection_loop  (async task)
    │  put_nowait → _queue (thread-safe Queue, maxsize=2000)
    ▼
_drain_to_db  (async task, polls every 0.5s)
    │  INSERT Reading + ReadingValues; aborts on zero-value sensors
    ▼
PostgreSQL
    │  SELECT last N readings (per ms_id)
    ▼
Observer  (async task, polls every OBSERVER_POLL_INTERVAL seconds)
    │  feeds samples to SignalAnalyzer
    ▼
board_ws.set_estado() / .stop()  →  sends JSON command back to ESP32
```

### Shared mutable state

Three module-level singletons coordinate the layers — there is no DI container:

- `board_ws` — WebSocket connection, reading queue, `_estado`, `_running`. All public functions are thread-safe.
- `measurement_state` — active `sample_id`, `ms_id`, `n_repetitions`, `min_medicion_seconds`. Written by the router on `/start`, read by drain and observer.
- `sensor_cache` — `{name: db_id}` dict, built at startup, read-only thereafter.

### Observer state machine

`Observer.run()` cycles through states: `start_base → waiting_base → measuring → cooldown → start_base`.

Key invariant: the observer stops a `MeasurementSet` only when the signal has been **continuously stable** for at least `min_medicion_seconds` (not merely elapsed since measurement start). `stable_since` tracks the monotonic time when stability was first detected; any instability resets it to `None`.

`min_medicion_seconds` is set per-run via `POST /serial/start?min_medicion_seconds=N` and stored in `measurement_state`. The default (30.0) is in `config.py` as `OBSERVER_MIN_MEDICION_SECONDS`.

### SignalAnalyzer (`app/services/analyzer.py`)

Stateful per-channel FSM. Decides SUBIENDO vs ESTABILIZADO using:
- Least-squares slope over a sliding `OBSERVER_WINDOW_SECONDS` window
- Hysteresis band (`lower`/`upper` around `OBSERVER_SLOPE_THRESHOLD`)
- Temporal debounce (`OBSERVER_CONFIRM_SECONDS`, measured in signal time, not wall time)
- `require_rise` latch: in `medicion` mode, a channel can only confirm ESTABILIZADO after having first risen above `upper`. Prevents false-positive stop when measurement starts flat.

Call `reset(require_rise=False)` for base/cooldown phases, `reset(require_rise=True)` for measuring.

### Database schema

```
Sample (1) ──< MeasurementSet (1) ──< Reading (1) ──< ReadingValue
                                                          └── Sensor
```

- `Sample`: one substance measurement session. `completed_repetitions` < `n_repetitions` means it was interrupted.
- `MeasurementSet`: one base→medicion cycle. `stopped_at = NULL` means incomplete (discard for ML).
- `Reading`: one poll from the board (all sensors together). `estado` = `base` | `medicion` | `cooldown`. Cooldown readings have `measurement_set_id = NULL`.
- `ReadingValue`: one sensor value per reading.

### Observer calibration

Run `python tools/calibrate.py` against `datasets/*.csv` to find the valid range for `OBSERVER_SLOPE_THRESHOLD`. The default 7.5 u/s is calibrated for the current 4-sensor set: above the highest plateau slope (~5.3 u/s) and below the weakest sensor's rise peak (~9.7 u/s). Recalibrate when new recordings are added.

### ESP32 firmware (`esp32s3/websockets-read.ino`)

Listens on WebSocket port 81. Receives JSON commands `{type:"command", estado:"base"|"medicion"}` and controls two relays (`medicionRelayPin=14`, `idleRelayPin=13`). Sends readings every 200 ms at 5 Hz. WiFi credentials are in `secrets.h` (gitignored).

## ML pipeline (`implementacion/`)

Offline pipeline; does not connect to the API. Input: `datasets/*.csv`. Output: trained SVM model.

```bash
cd implementacion
pip install -r requirements.txt
python main.py --phase 4    # build master dataset from datasets/*.csv
```

Architecture follows Spec → Design → Dev: `spec/contracts/` has Python `Protocol` interfaces, `spec/schemas/` has Pydantic validation models, `src/enose/` has the implementations. Signal processing uses Savitzky-Golay smoothing and fractional baseline normalization `(R0 − Rs) / R0`.
