_current_sample_id: int | None = None
_current_sample_n_repetitions: int = 0
_current_ms_id: int | None = None
_min_medicion_seconds: float = 30.0
_is_stable: bool = False
_sensor_risen: dict[str, bool] = {}


def set_current_sample(id: int, n_repetitions: int, min_medicion_seconds: float = 30.0) -> None:
    global _current_sample_id, _current_sample_n_repetitions, _min_medicion_seconds
    _current_sample_id = id
    _current_sample_n_repetitions = n_repetitions
    _min_medicion_seconds = min_medicion_seconds


def get_min_medicion_seconds() -> float:
    return _min_medicion_seconds


def get_current_sample_id() -> int | None:
    return _current_sample_id


def get_current_sample_n_repetitions() -> int:
    return _current_sample_n_repetitions


def set_current_ms(id: int | None) -> None:
    global _current_ms_id
    _current_ms_id = id


def get_current_ms() -> int | None:
    return _current_ms_id


def set_stable(stable: bool) -> None:
    global _is_stable
    _is_stable = stable


def get_stable() -> bool:
    return _is_stable


def set_sensor_risen(risen: dict[str, bool]) -> None:
    global _sensor_risen
    _sensor_risen = risen


def get_sensor_risen() -> dict[str, bool]:
    return _sensor_risen


def clear() -> None:
    global _current_sample_id, _current_sample_n_repetitions, _current_ms_id
    global _min_medicion_seconds, _is_stable, _sensor_risen
    _current_sample_id = None
    _current_sample_n_repetitions = 0
    _current_ms_id = None
    _min_medicion_seconds = 30.0
    _is_stable = False
    _sensor_risen = {}
