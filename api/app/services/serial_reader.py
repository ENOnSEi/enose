import queue
import threading

import serial

_queue: queue.Queue = queue.Queue(maxsize=2000)
_thread: threading.Thread | None = None
_lock = threading.Lock()
_running = False
_estado = "base"
_readings_total = 0


def _reader_loop(port: str, baud: int, sensor_names: list[str]) -> None:
    global _running, _readings_total

    try:
        ser = serial.Serial(port, baud, timeout=1)
    except serial.SerialException as e:
        print(f"[serial] cannot open {port}: {e}")
        with _lock:
            _running = False
        return

    print(f"[serial] reading from {port} at {baud} baud")

    while True:
        with _lock:
            if not _running:
                break
            estado = _estado

        try:
            line = ser.readline().decode(errors="ignore").strip()
        except Exception:
            break

        if not line:
            continue

        parts = line.split(",")
        # espera: arduino_ms + un valor por sensor
        if len(parts) != 1 + len(sensor_names):
            continue

        try:
            arduino_ms = int(parts[0])
            values = {name: int(parts[i + 1]) for i, name in enumerate(sensor_names)}
        except ValueError:
            continue

        try:
            _queue.put_nowait((arduino_ms, values, estado))
            with _lock:
                _readings_total += 1
        except queue.Full:
            pass

    ser.close()
    print("[serial] reader stopped")


def start(port: str, baud: int, sensor_names: list[str]) -> bool:
    global _thread, _running

    with _lock:
        if _running:
            return False
        _running = True

    _thread = threading.Thread(
        target=_reader_loop, args=(port, baud, sensor_names), daemon=True
    )
    _thread.start()
    return True


def stop() -> None:
    global _running
    with _lock:
        _running = False


def set_estado(estado: str) -> None:
    global _estado
    with _lock:
        _estado = estado


def get_status() -> dict:
    with _lock:
        return {
            "running": _running,
            "estado": _estado,
            "readings_queued": _queue.qsize(),
            "readings_total": _readings_total,
        }


def drain() -> list[tuple]:
    items = []
    while not _queue.empty():
        try:
            items.append(_queue.get_nowait())
        except queue.Empty:
            break
    return items
