from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session
from app.models.sensor import Sensor
from app.schemas.sensor import RenameSensorRequest, RenameSensorResponse, SensorOut

router = APIRouter(prefix="/sensors", tags=["sensors"])


@router.post("/{name}/rename", response_model=RenameSensorResponse)
async def rename_sensor(
    name: str,
    body: RenameSensorRequest,
    session: AsyncSession = Depends(get_session),
) -> RenameSensorResponse:
    """Archiva el sensor saliente y libera ``name`` para su reemplazo físico.

    Uso: cuando se sustituye o recoloca un sensor físico, el operador llama
    a este endpoint para renombrar la fila activa (p. ej. ``tgs2611`` ->
    ``tgs2611_2026-07``) y crea de inmediato una fila nueva con el nombre
    original (``tgs2611``) y su propio ``created_at``. Así las lecturas
    anteriores y posteriores al cambio quedan bajo ``sensor_id`` distintos,
    sin conflacionarse, y no hace falta reiniciar la API.
    """

    if body.archive_as == name:
        raise HTTPException(400, "archive_as debe ser distinto de name")

    sensor = await session.scalar(select(Sensor).where(Sensor.name == name))
    if sensor is None:
        raise HTTPException(404, f"sensor '{name}' no encontrado")

    conflict = await session.scalar(select(Sensor).where(Sensor.name == body.archive_as))
    if conflict is not None:
        raise HTTPException(409, f"el nombre '{body.archive_as}' ya está en uso")

    sensor.name = body.archive_as
    sensor.retired_at = datetime.now(timezone.utc)
    session.add(sensor)

    replacement = Sensor(name=name)
    session.add(replacement)

    await session.commit()
    await session.refresh(sensor)
    await session.refresh(replacement)

    return RenameSensorResponse(
        archived=SensorOut.model_validate(sensor),
        replacement=SensorOut.model_validate(replacement),
    )
