from typing import Literal

from fastapi import APIRouter, HTTPException

from app.schemas.reading import SerialStatus
from app.services import serial_reader

router = APIRouter(prefix="/serial", tags=["serial"])

EstadoType = Literal["base", "medicion"]


@router.get("/status", response_model=SerialStatus)
async def status():
    return serial_reader.get_status()


@router.post("/start")
async def start():
    from app.core.config import settings

    started = serial_reader.start(settings.SERIAL_PORT, settings.SERIAL_BAUD, settings.SENSOR_NAMES)
    if not started:
        raise HTTPException(400, "Already running")
    return {"started": True}


@router.post("/stop")
async def stop():
    serial_reader.stop()
    return {"stopped": True}


@router.put("/estado/{estado}")
async def set_estado(estado: EstadoType):
    serial_reader.set_estado(estado)
    return {"estado": estado}
