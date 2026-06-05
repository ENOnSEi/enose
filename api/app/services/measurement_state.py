_current_id: int | None = None


def set_current(id: int) -> None:
    global _current_id
    _current_id = id


def get_current() -> int | None:
    return _current_id


def clear() -> None:
    global _current_id
    _current_id = None
