from sqlmodel import Field, SQLModel


class Sensor(SQLModel, table=True):
    
    id: int | None = Field(default=None, primary_key=True)

    name: str = Field(max_length=50, sa_column_kwargs={"unique": True})

    pin: str = Field(max_length=10)
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Sensor(Base):
    __tablename__ = "sensors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    pin: Mapped[str] = mapped_column(String(32))
