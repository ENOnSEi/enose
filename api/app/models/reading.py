from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime
from sqlmodel import Field, Relationship, SQLModel
from app.models.measurement_set import MeasurementSet
from app.models.sample import Sample


class Reading(SQLModel, table=True):

    id: int | None = Field(default=None, primary_key=True)

    sample_id: int | None = Field(
        default=None,
        foreign_key="sample.id",
    )

    sample: "Sample" = Relationship(back_populates="readings")

    measurement_set_id: int | None = Field(
        default=None,
        foreign_key="measurementset.id",
    )

    arduino_ms: int = Field(
        sa_column=Column(BigInteger, nullable=False)
    )

    estado: str = Field(max_length=20)

    captured_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    values: list["ReadingValue"] = Relationship(
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
        }
    )


class ReadingValue(SQLModel, table=True):

    reading_id: int = Field(
        foreign_key="reading.id",
        primary_key=True,
    )

    sensor_id: int = Field(
        foreign_key="sensor.id",
        primary_key=True,
    )

    value: int