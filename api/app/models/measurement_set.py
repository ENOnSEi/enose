from datetime import datetime, timezone
from sqlalchemy import DateTime
from sqlalchemy import Column
from sqlmodel import Field, SQLModel
from sqlmodel import Relationship


class MeasurementSet(SQLModel, table=True):

    id: int | None = Field(default=None, primary_key=True)

    sample_id: int = Field(foreign_key="sample.id")

    sample: "Sample" = Relationship(back_populates="measurement_sets")

    repetition_number: int

    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    stopped_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )


