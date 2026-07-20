from datetime import datetime

from pydantic import BaseModel, Field


class SensorOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    retired_at: datetime | None

    model_config = {"from_attributes": True}


class RenameSensorRequest(BaseModel):
    archive_as: str = Field(
        min_length=1,
        max_length=50,
        description=(
            "Nombre bajo el que queda archivada la fila actual (el sensor "
            "físico saliente). No puede coincidir con un nombre ya en uso."
        ),
    )


class RenameSensorResponse(BaseModel):
    archived: SensorOut
    replacement: SensorOut
