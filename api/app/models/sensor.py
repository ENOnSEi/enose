from sqlmodel import Field, SQLModel


class Sensor(SQLModel, table=True):
    
    id: int | None = Field(default=None, primary_key=True)

    name: str = Field(max_length=50, sa_column_kwargs={"unique": True})

    pin: str = Field(max_length=10)
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


