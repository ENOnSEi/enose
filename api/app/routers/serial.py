import asyncio
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import AsyncSessionLocal, get_db
from app.models.measurement_set import MeasurementSet
from app.schemas.reading import SerialStatus
from app.services import measurement_state, serial_reader

router = APIRouter(prefix="/serial", tags=["serial"])

EstadoType = Literal["base", "medicion"]


@router.get("/status", response_model=SerialStatus)
async def status():
    return serial_reader.get_status()


@router.post("/start")
async def start(name: str, session: AsyncSession = Depends(get_db)):
    from app.core.config import settings

    started = serial_reader.start(settings.SERIAL_PORT, settings.SERIAL_BAUD, settings.SENSOR_NAMES)
    if not started:
        raise HTTPException(400, "Already running")

    ms = MeasurementSet(name=name)
    session.add(ms)
    await session.commit()
    measurement_state.set_current(ms.id)

    return {"started": True, "measurement_set_id": ms.id, "name": ms.name}


async def _flush_and_close() -> None:
    for _ in range(20):
        if serial_reader.get_status()["readings_queued"] == 0:
            break
        await asyncio.sleep(0.5)

    ms_id = measurement_state.get_current()
    if ms_id is None:
        return
    async with AsyncSessionLocal() as session:
        ms = await session.get(MeasurementSet, ms_id)
        if ms:
            ms.stopped_at = datetime.now(timezone.utc)
            await session.commit()
    measurement_state.clear()


@router.post("/stop")
async def stop():
    serial_reader.stop()
    asyncio.create_task(_flush_and_close())
    return {"stopped": True}


@router.put("/estado/{estado}")
async def set_estado(estado: EstadoType):
    serial_reader.set_estado(estado)
    return {"estado": estado}
