import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import select

import app.models  # noqa: F401 — registra modelos en Base.metadata
from app.core.config import settings
from app.db.database import AsyncSessionLocal, Base, engine
from app.models.reading import Reading, ReadingValue
from app.models.sensor import Sensor
from app.routers.serial import router as serial_router
from app.services import measurement_state, serial_reader
from app.services.observer import Observer


async def _seed_sensors() -> dict[str, int]:
    async with AsyncSessionLocal() as session:
        for name, pin in zip(settings.SENSOR_NAMES, settings.SENSOR_PINS):
            exists = await session.scalar(select(Sensor).where(Sensor.name == name))
            if not exists:
                session.add(Sensor(name=name, pin=pin))
        await session.commit()
        rows = (await session.scalars(select(Sensor))).all()
        return {s.name: s.id for s in rows}


async def _drain_to_db(sensor_cache: dict[str, int]) -> None:
    while True:
        await asyncio.sleep(0.5)
        items = serial_reader.drain()
        if not items:
            continue
        try:
            async with AsyncSessionLocal() as session:
                for arduino_ms, values, estado in items:
                    session.add(Reading(
                        sample_id=measurement_state.get_current_sample_id(),
                        measurement_set_id=measurement_state.get_current_ms(),
                        arduino_ms=arduino_ms,
                        estado=estado,
                        values=[
                            ReadingValue(sensor_id=sensor_cache[name], value=val)
                            for name, val in values.items()
                            if name in sensor_cache
                        ],
                    ))
                await session.commit()
        except Exception as e:
            print(f"[db] write error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sensor_cache = await _seed_sensors()

    drain_task = asyncio.create_task(_drain_to_db(sensor_cache))
    observer_task = asyncio.create_task(
        Observer(
            sensor_cache=sensor_cache,
            window=settings.OBSERVER_WINDOW,
            threshold=settings.OBSERVER_SLOPE_THRESHOLD,
            poll_interval=settings.OBSERVER_POLL_INTERVAL,
            min_medicion_seconds=settings.OBSERVER_MIN_MEDICION_SECONDS,
        ).run()
    )

    yield

    serial_reader.stop()
    drain_task.cancel()
    observer_task.cancel()
    await engine.dispose()


app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG, lifespan=lifespan)
app.include_router(serial_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
