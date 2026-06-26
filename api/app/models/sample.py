from datetime import datetime, timezone
from sqlalchemy import Column, DateTime
from sqlmodel import Field, Relationship, SQLModel



class Sample(SQLModel, table=True):

    id: int | None = Field(default=None, primary_key=True)

    name: str = Field(max_length=200)

    n_repetitions: int

    completed_repetitions: int = Field(default=0)

    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    stopped_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    measurement_sets: list["MeasurementSet"] = Relationship(back_populates="sample")

    readings: list["Reading"] = Relationship(
        back_populates="sample"
    )