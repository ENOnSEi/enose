_current_sample_id: int | None = None
_current_sample_n_repetitions: int = 0
_current_ms_id: int | None = None


def set_current_sample(id: int, n_repetitions: int) -> None:
    global _current_sample_id, _current_sample_n_repetitions
    _current_sample_id = id
    _current_sample_n_repetitions = n_repetitions


def get_current_sample_id() -> int | None:
    return _current_sample_id


def get_current_sample_n_repetitions() -> int:
    return _current_sample_n_repetitions


def set_current_ms(id: int | None) -> None:
    global _current_ms_id
    _current_ms_id = id


def get_current_ms() -> int | None:
    return _current_ms_id


def clear() -> None:
    global _current_sample_id, _current_sample_n_repetitions, _current_ms_id
    _current_sample_id = None
    _current_sample_n_repetitions = 0
    _current_ms_id = None
