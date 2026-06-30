from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_session
from app.models.measurement_set import MeasurementSet
from app.models.reading import Reading, ReadingValue
from app.models.sample import Sample
from app.models.sensor import Sensor

router = APIRouter(prefix="/export", tags=["export"])

SENSOR_ID_TO_COL = {1: "v20", 2: "v11", 3: "v02", 4: "v00"}


# ── Schemas ──────────────────────────────────────────────────────────────────

class ReadingRow(BaseModel):
    data: int
    v20: int
    v11: int
    v02: int
    v00: int
    estado: str


class RecordingExport(BaseModel):
    measurement_set_id: int
    sample_id: int
    sample_name: str
    repetition_number: int
    is_complete: bool
    readings: list[ReadingRow]


class SampleSummary(BaseModel):
    id: int
    name: str
    n_repetitions: int
    completed_repetitions: int
    started_at: str
    stopped_at: str | None


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_sensor_map(session: AsyncSession) -> dict[int, str]:
    rows = (await session.scalars(select(Sensor))).all()
    return {s.id: s.name for s in rows}


_SENSOR_NAME_TO_COL = {
    "tgs2620": "v20",
    "tgs2611": "v11",
    "tgs2602": "v02",
    "tgs2600": "v00",
}


def _pivot_readings(
    readings: list[Reading],
    sensor_map: dict[int, str],
    exclude_cooldown: bool = True,
) -> list[ReadingRow]:
    rows: list[ReadingRow] = []
    for r in readings:
        if exclude_cooldown and r.estado == "cooldown":
            continue
        vals = {"v20": 0, "v11": 0, "v02": 0, "v00": 0}
        for rv in r.values:
            sensor_name = sensor_map.get(rv.sensor_id, "")
            col = _SENSOR_NAME_TO_COL.get(sensor_name)
            if col:
                vals[col] = rv.value
        rows.append(ReadingRow(data=r.arduino_ms, estado=r.estado, **vals))
    rows.sort(key=lambda r: r.data)
    return rows


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/samples", response_model=list[SampleSummary])
async def list_samples(session: AsyncSession = Depends(get_session)):
    """List all samples with their dates and repetition counts."""
    rows = (await session.scalars(
        select(Sample).order_by(Sample.started_at)
    )).all()
    return [
        SampleSummary(
            id=s.id,
            name=s.name,
            n_repetitions=s.n_repetitions,
            completed_repetitions=s.completed_repetitions,
            started_at=s.started_at.isoformat(),
            stopped_at=s.stopped_at.isoformat() if s.stopped_at else None,
        )
        for s in rows
    ]


@router.get("/recordings", response_model=list[RecordingExport])
async def export_recordings(
    sample_id: int | None = Query(default=None, description="Filter by sample"),
    only_complete: bool = Query(default=True, description="Only completed measurement sets"),
    session: AsyncSession = Depends(get_session),
):
    """All measurement sets pivoted as flat readings (base+medicion, no cooldown)."""
    sensor_map = await _get_sensor_map(session)

    stmt = (
        select(MeasurementSet)
        .join(Sample, Sample.id == MeasurementSet.sample_id)
        .options(selectinload(MeasurementSet.sample))
    )
    if sample_id is not None:
        stmt = stmt.where(MeasurementSet.sample_id == sample_id)
    if only_complete:
        stmt = stmt.where(MeasurementSet.stopped_at.is_not(None))
    stmt = stmt.order_by(MeasurementSet.sample_id, MeasurementSet.repetition_number)

    ms_list = (await session.scalars(stmt)).all()
    if not ms_list:
        return []

    ms_ids = [ms.id for ms in ms_list]
    readings_stmt = (
        select(Reading)
        .where(Reading.measurement_set_id.in_(ms_ids))
        .options(selectinload(Reading.values))
        .order_by(Reading.arduino_ms)
    )
    all_readings = (await session.scalars(readings_stmt)).all()

    readings_by_ms: dict[int, list[Reading]] = {}
    for r in all_readings:
        readings_by_ms.setdefault(r.measurement_set_id, []).append(r)

    result = []
    for ms in ms_list:
        readings = readings_by_ms.get(ms.id, [])
        result.append(RecordingExport(
            measurement_set_id=ms.id,
            sample_id=ms.sample_id,
            sample_name=ms.sample.name,
            repetition_number=ms.repetition_number,
            is_complete=ms.stopped_at is not None,
            readings=_pivot_readings(readings, sensor_map),
        ))

    return result


@router.get("/recordings/{ms_id}", response_model=RecordingExport)
async def export_recording(
    ms_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Single measurement set pivoted."""
    sensor_map = await _get_sensor_map(session)

    ms = await session.get(MeasurementSet, ms_id, options=[selectinload(MeasurementSet.sample)])
    if not ms:
        raise HTTPException(404, f"MeasurementSet {ms_id} not found")

    readings_stmt = (
        select(Reading)
        .where(Reading.measurement_set_id == ms_id)
        .options(selectinload(Reading.values))
        .order_by(Reading.arduino_ms)
    )
    readings = (await session.scalars(readings_stmt)).all()

    return RecordingExport(
        measurement_set_id=ms.id,
        sample_id=ms.sample_id,
        sample_name=ms.sample.name,
        repetition_number=ms.repetition_number,
        is_complete=ms.stopped_at is not None,
        readings=_pivot_readings(list(readings), sensor_map),
    )
