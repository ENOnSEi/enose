import asyncio
import json
import queue
from typing import Any

_queue: queue.Queue = queue.Queue(maxsize=2000)
_commands: queue.Queue = queue.Queue(maxsize=100)
_running = False
_connected = False
_estado = "base"
_readings_total = 0
_last_error: str | None = None
_board_url: str | None = None
_sensor_names: list[str] = []


def _enqueue_command(command: dict[str, Any]) -> None:
    try:
        _commands.put_nowait(command)
    except queue.Full:
        pass


async def _send_pending(ws) -> None:
    while not _commands.empty():
        try:
            command = _commands.get_nowait()
        except queue.Empty:
            break
        await ws.send(json.dumps(command))


def _handle_message(message: str) -> None:
    global _readings_total, _last_error

    try:
        payload = json.loads(message)
    except json.JSONDecodeError:
        _last_error = "invalid json from board"
        return

    if payload.get("type") != "reading":
        return

    values = payload.get("values")
    if not isinstance(values, dict):
        _last_error = "reading without values"
        return

    missing = [name for name in _sensor_names if name not in values]
    if missing:
        _last_error = f"reading missing sensors: {', '.join(missing)}"
        return

    try:
        arduino_ms = int(payload["arduino_ms"])
        parsed_values = {name: int(values[name]) for name in _sensor_names}
    except (KeyError, TypeError, ValueError):
        _last_error = "reading contains invalid numeric data"
        return

    try:
        _queue.put_nowait((arduino_ms, parsed_values, _estado))
        _readings_total += 1
        _last_error = None
    except queue.Full:
        _last_error = "reading queue full"


async def _connection_loop(url: str) -> None:
    global _connected, _last_error, _running

    try:
        import websockets
    except ModuleNotFoundError as e:
        _last_error = "missing dependency: websockets"
        _running = False
        print(f"[board_ws] {e}")
        return

    while _running:
        try:
            async with websockets.connect(url) as ws:
                _connected = True
                _last_error = None
                _enqueue_command({"type": "command", "estado": _estado})
                print(f"[board_ws] connected to {url}")

                while _running:
                    await _send_pending(ws)
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=0.1)
                    except asyncio.TimeoutError:
                        continue
                    _handle_message(message)

                await _send_pending(ws)
        except Exception as e:
            _connected = False
            _last_error = str(e)
            if _running:
                print(f"[board_ws] connection error: {e}")
                await asyncio.sleep(1.0)

    _connected = False
    _running = False
    print("[board_ws] stopped")


def start(url: str, sensor_names: list[str]) -> bool:
    global _running, _board_url, _sensor_names, _last_error

    if _running:
        return False

    _running = True
    _board_url = url
    _sensor_names = list(sensor_names)
    _last_error = None
    asyncio.create_task(_connection_loop(url))
    return True


def stop() -> None:
    global _running

    _enqueue_command({"type": "command", "action": "stop"})
    _running = False


def set_estado(estado: str) -> None:
    global _estado

    _estado = estado
    _enqueue_command({"type": "command", "estado": estado})


def get_status() -> dict:
    return {
        "running": _running,
        "connected": _connected,
        "estado": _estado,
        "readings_queued": _queue.qsize(),
        "readings_total": _readings_total,
        "last_error": _last_error,
        "board_url": _board_url,
    }


def drain() -> list[tuple]:
    items = []
    while not _queue.empty():
        try:
            items.append(_queue.get_nowait())
        except queue.Empty:
            break
    return items
