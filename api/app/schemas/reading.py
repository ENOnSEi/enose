from datetime import datetime

from pydantic import BaseModel


class SensorReadingOut(BaseModel):
    id: int
    arduino_ms: int
    v20: int
    v11: int
    v02: int
    v00: int
    estado: str
    captured_at: datetime

    model_config = {"from_attributes": True}


class SerialStatus(BaseModel):
    running: bool
    connected: bool
    estado: str
    readings_queued: int
    readings_total: int
    last_error: str | None
    board_url: str | None
