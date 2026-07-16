from sqlmodel import Field, SQLModel


class Sensor(SQLModel, table=True):
    """Identidad estable de un sensor, keyed por ``name``.

    El cableado físico (pines ADC) es propiedad exclusiva del firmware del
    ESP32 — no se duplica aquí. Ver ``api/CONTEXT.md`` (sección "Sensor").
    """

    id: int | None = Field(default=None, primary_key=True)

    name: str = Field(max_length=50, sa_column_kwargs={"unique": True})
