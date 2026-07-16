from datetime import datetime, timezone

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


class Sensor(SQLModel, table=True):
    """Identidad estable de un sensor, keyed por ``name``.

    El cableado físico (pines ADC) es propiedad exclusiva del firmware del
    ESP32 — no se duplica aquí. Si un sensor físico se sustituye o se
    reordena, no reutilizar el mismo ``name``: usar
    ``POST /sensors/{name}/rename`` para archivar la fila antigua bajo un
    nombre nuevo y liberar el nombre original para el sensor de reemplazo.
    Ver ``api/CONTEXT.md`` (sección "Sensor").
    """

    id: int | None = Field(default=None, primary_key=True)

    name: str = Field(max_length=50, sa_column_kwargs={"unique": True})

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    retired_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
