from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlmodel import Field, Session, SQLModel, create_engine, select


from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass




def get_session():
    with Session(engine) as session:
        yield session

async def create_db_and_tables(engine):
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
