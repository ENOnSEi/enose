from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Reading(Base):
    __tablename__ = "readings"

    id: Mapped[int] = mapped_column(primary_key=True)
    arduino_ms: Mapped[int] = mapped_column(BigInteger)
    estado: Mapped[str] = mapped_column(String(20))
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    values: Mapped[list["ReadingValue"]] = relationship(cascade="all, delete-orphan")


class ReadingValue(Base):
    __tablename__ = "reading_values"

    reading_id: Mapped[int] = mapped_column(ForeignKey("readings.id"), primary_key=True)
    sensor_id: Mapped[int] = mapped_column(ForeignKey("sensors.id"), primary_key=True)
    value: Mapped[int] = mapped_column(Integer)
