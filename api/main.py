import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from sqlalchemy import select

import app.models
from app.core.config import settings
from app.db.database import AsyncSessionLocal, Base, engine
from app.db.migrations_sync import sync_schema_with_alembic
from app.models.measurement_set import MeasurementSet
from app.models.reading import Reading, ReadingValue
from app.models.sample import Sample
from app.models.sensor import Sensor
from app.routers.export import router as export_router
from app.routers.measurement_sets import router as measurement_sets_router
from app.routers.sensors import router as sensors_router
from app.routers.serial import router as serial_router
from app.services import board_ws, measurement_state
from app.services.analyzer import Policy
from app.services.observer import Observer
from app.db.database import create_db_and_tables


async def _seed_sensors() -> dict[str, int]:
    async with AsyncSessionLocal() as session:
        for name in settings.SENSOR_NAMES:
            exists = await session.scalar(select(Sensor).where(Sensor.name == name))
            if not exists:
                session.add(Sensor(name=name))
        await session.commit()
        rows = (
            await session.scalars(select(Sensor).where(Sensor.retired_at.is_(None)))
        ).all()
        return {s.name: s.id for s in rows}


async def _abort_on_sensor_fault() -> None:
    now = datetime.now(timezone.utc)
    ms_id = measurement_state.get_current_ms()
    if ms_id:
        async with AsyncSessionLocal() as session:
            ms = await session.get(MeasurementSet, ms_id)
            if ms:
                ms.stopped_at = now
                await session.commit()

    sample_id = measurement_state.get_current_sample_id()
    if sample_id:
        async with AsyncSessionLocal() as session:
            sample = await session.get(Sample, sample_id)
            if sample:
                sample.stopped_at = now
                await session.commit()

    measurement_state.clear()


async def _drain_to_db(sensor_cache: dict[str, int]) -> None:
    while True:
        await asyncio.sleep(0.5)
        items = board_ws.drain()
        if not items:
            continue
        try:
            async with AsyncSessionLocal() as session:
                fault = False
                for arduino_ms, values, estado in items:
                    zero_sensors = [n for n, v in values.items() if v == 0]
                    if zero_sensors:
                        print(f"[drain] zero value on sensors {zero_sensors} — aborting measurement")
                        board_ws.stop()
                        asyncio.create_task(_abort_on_sensor_fault())
                        fault = True
                        break
                    sensor_risen = measurement_state.get_sensor_risen()
                    session.add(Reading(
                        sample_id=measurement_state.get_current_sample_id(),
                        measurement_set_id=measurement_state.get_current_ms(),
                        arduino_ms=arduino_ms,
                        estado=estado,
                        is_stable=measurement_state.get_stable(),
                        values=[
                            ReadingValue(
                                sensor_id=sensor_cache[name],
                                value=val,
                                has_risen=sensor_risen.get(name, False),
                            )
                            for name, val in values.items()
                            if name in sensor_cache
                        ],
                    ))
                if not fault:
                    await session.commit()
        except Exception as e:
            print(f"[db] write error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await create_db_and_tables(engine)
    await sync_schema_with_alembic(engine)

    sensor_cache = await _seed_sensors()

    drain_task = asyncio.create_task(_drain_to_db(sensor_cache))
    observer_task = asyncio.create_task(
        Observer(
            sensor_cache=sensor_cache,
            window_seconds=settings.OBSERVER_WINDOW_SECONDS,
            slope_threshold=settings.OBSERVER_SLOPE_THRESHOLD,
            hysteresis=settings.OBSERVER_HYSTERESIS,
            confirm_seconds=settings.OBSERVER_CONFIRM_SECONDS,
            policy=Policy(settings.OBSERVER_POLICY),
            fetch_limit=settings.OBSERVER_FETCH_LIMIT,
            poll_interval=settings.OBSERVER_POLL_INTERVAL,
            min_medicion_seconds=settings.OBSERVER_MIN_MEDICION_SECONDS,
        ).run()
    )

    yield

    board_ws.stop()
    drain_task.cancel()
    observer_task.cancel()
    await engine.dispose()


app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG, lifespan=lifespan)
app.include_router(serial_router)
app.include_router(measurement_sets_router)
app.include_router(export_router)
app.include_router(sensors_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


