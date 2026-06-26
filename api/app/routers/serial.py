import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession


from app.db.database import AsyncSessionLocal, get_session
from app.models.measurement_set import MeasurementSet
from app.models.sample import Sample
from app.schemas.reading import SerialStatus
from app.services import board_ws, measurement_state

router = APIRouter(prefix="/serial", tags=["serial"])

EstadoType = Literal["base", "medicion", "cooldown"]


@router.get("/status", response_model=SerialStatus)
async def status():
    return board_ws.get_status()


@router.post("/start")
async def start(name: str, n_repetitions: int = Query(ge=1, le=10), session: AsyncSession = Depends(get_session)):
    from app.core.config import settings

    started = board_ws.start(settings.ESP32_WS_URL, settings.SENSOR_NAMES)
    if not started:
        raise HTTPException(400, "Already running")

    sample = Sample(name=name, n_repetitions=n_repetitions)
    session.add(sample)
    await session.flush()

    ms = MeasurementSet(sample_id=sample.id, repetition_number=1)
    session.add(ms)
    await session.commit()

    measurement_state.set_current_sample(sample.id, n_repetitions)
    measurement_state.set_current_ms(ms.id)

    return {"started": True, "sample_id": sample.id, "name": sample.name, "n_repetitions": n_repetitions}


async def _flush_and_close() -> None:
    for _ in range(20):
        if board_ws.get_status()["readings_queued"] == 0:
            break
        await asyncio.sleep(0.5)

    ms_id = measurement_state.get_current_ms()
    if ms_id:
        async with AsyncSessionLocal() as session:
            ms = await session.get(MeasurementSet, ms_id)
            if ms:
                from datetime import datetime, timezone
                ms.stopped_at = datetime.now(timezone.utc)
                await session.commit()

    sample_id = measurement_state.get_current_sample_id()
    if sample_id:
        async with AsyncSessionLocal() as session:
            sample = await session.get(Sample, sample_id)
            if sample:
                from datetime import datetime, timezone
                sample.stopped_at = datetime.now(timezone.utc)
                await session.commit()

    measurement_state.clear()


@router.post("/stop")
async def stop():
    board_ws.stop()
    asyncio.create_task(_flush_and_close())
    return {"stopped": True}


@router.put("/estado/{estado}")
async def set_estado(estado: EstadoType):
    board_ws.set_estado(estado)
    return {"estado": estado}
