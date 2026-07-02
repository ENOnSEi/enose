from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
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
    is_stable: bool


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


class MeasurementSetSummary(BaseModel):
    id: int
    repetition_number: int
    started_at: str
    stopped_at: str | None
    is_complete: bool


class SampleDetail(SampleSummary):
    is_fully_complete: bool
    measurement_sets: list[MeasurementSetSummary]


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
    base_means: dict[int, float] | None = None,
) -> list[ReadingRow]:
    """base_means, si se pasa, resta a cada valor la media de sensor_id -> valor base estable."""
    rows: list[ReadingRow] = []
    for r in readings:
        if exclude_cooldown and r.estado == "cooldown":
            continue
        vals = {"v20": 0, "v11": 0, "v02": 0, "v00": 0}
        for rv in r.values:
            sensor_name = sensor_map.get(rv.sensor_id, "")
            col = _SENSOR_NAME_TO_COL.get(sensor_name)
            if col:
                value = rv.value
                if base_means is not None:
                    value = round(value - base_means.get(rv.sensor_id, 0))
                vals[col] = value
        rows.append(ReadingRow(data=r.arduino_ms, estado=r.estado, is_stable=r.is_stable, **vals))
    rows.sort(key=lambda r: r.data)
    return rows


def _combined_has_risen(reading: Reading, policy: str) -> bool:
    """Combina el has_risen por sensor de un reading con la misma política
    ("all"/"any"/"majority") que usa SignalAnalyzer._combine para estabilidad."""
    flags = [rv.has_risen for rv in reading.values]
    if not flags:
        return False
    if policy == "all":
        return all(flags)
    if policy == "any":
        return any(flags)
    if policy == "majority":
        return sum(flags) > len(flags) / 2
    return False


async def _fetch_base_means(
    session: AsyncSession, ms_ids: list[int]
) -> dict[int, dict[int, float]]:
    """Media de value por (measurement_set_id, sensor_id) en la fase base estable
    (estado="base", is_stable=true) — usada para restar la base a la medición."""
    stmt = (
        select(
            Reading.measurement_set_id,
            ReadingValue.sensor_id,
            func.avg(ReadingValue.value).label("mean_base"),
        )
        .join(ReadingValue, ReadingValue.reading_id == Reading.id)
        .where(
            Reading.measurement_set_id.in_(ms_ids),
            Reading.estado == "base",
            Reading.is_stable.is_(True),
        )
        .group_by(Reading.measurement_set_id, ReadingValue.sensor_id)
    )
    result: dict[int, dict[int, float]] = {}
    for row in (await session.execute(stmt)).all():
        result.setdefault(row.measurement_set_id, {})[row.sensor_id] = float(row.mean_base)
    return result


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/samples", response_model=list[SampleSummary])
async def list_samples(
    only_fully_complete: bool = Query(
        default=False,
        description=(
            "Solo samples donde completed_repetitions == n_repetitions y stopped_at "
            "no es nulo. No basta con mirar MeasurementSet.stopped_at: un "
            "/serial/stop manual también lo marca en el measurement set en curso "
            "aunque se haya interrumpido a mitad de la medición; "
            "completed_repetitions solo lo incrementa el Observer al cerrar una "
            "repetición de forma natural (ver app/services/observer.py)"
        ),
    ),
    session: AsyncSession = Depends(get_session),
):
    """List all samples with their dates and repetition counts."""
    stmt = select(Sample)
    if only_fully_complete:
        stmt = stmt.where(
            Sample.completed_repetitions == Sample.n_repetitions,
            Sample.stopped_at.is_not(None),
        )
    stmt = stmt.order_by(Sample.started_at)

    rows = (await session.scalars(stmt)).all()
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


@router.get("/samples/{sample_id}", response_model=SampleDetail)
async def get_sample(sample_id: int, session: AsyncSession = Depends(get_session)):
    """Single sample with all of its measurement sets."""
    sample = await session.get(Sample, sample_id)
    if not sample:
        raise HTTPException(404, f"Sample {sample_id} not found")

    ms_list = (
        await session.scalars(
            select(MeasurementSet)
            .where(MeasurementSet.sample_id == sample_id)
            .order_by(MeasurementSet.repetition_number)
        )
    ).all()

    is_fully_complete = (
        sample.completed_repetitions == sample.n_repetitions
        and sample.stopped_at is not None
    )

    return SampleDetail(
        id=sample.id,
        name=sample.name,
        n_repetitions=sample.n_repetitions,
        completed_repetitions=sample.completed_repetitions,
        started_at=sample.started_at.isoformat(),
        stopped_at=sample.stopped_at.isoformat() if sample.stopped_at else None,
        is_fully_complete=is_fully_complete,
        measurement_sets=[
            MeasurementSetSummary(
                id=ms.id,
                repetition_number=ms.repetition_number,
                started_at=ms.started_at.isoformat(),
                stopped_at=ms.stopped_at.isoformat() if ms.stopped_at else None,
                is_complete=ms.stopped_at is not None,
            )
            for ms in ms_list
        ],
    )


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


@router.get("/readings", response_model=list[RecordingExport])
async def export_readings(
    sample_ids: list[int] | None = Query(default=None, description="Filtra por una o varias muestras"),
    ms_ids: list[int] | None = Query(default=None, description="Filtra por measurement sets concretos"),
    only_complete: bool = Query(
        default=True, description="Solo measurement sets que estabilizaron (stopped_at no nulo)"
    ),
    estado: Literal["base", "medicion", "cooldown"] | None = Query(
        default=None, description="Restringe a una fase concreta; si se omite, se excluye cooldown"
    ),
    is_stable: bool | None = Query(
        default=None,
        description=(
            "True=solo readings estables, False=solo inestables, omitir=ambos. "
            "is_stable también puede ser true en estado=base (señal plana, sin exigir subida previa)"
        ),
    ),
    has_risen: bool | None = Query(
        default=None,
        description=(
            "Combina el has_risen por sensor de cada reading con settings.OBSERVER_POLICY "
            "(all/any/majority) y filtra por ese resultado combinado"
        ),
    ),
    subtract_base: bool = Query(
        default=False,
        description=(
            "Resta a cada ReadingValue la media de ese sensor en la fase base estable "
            "(estado=base, is_stable=true) del mismo measurement set"
        ),
    ),
    session: AsyncSession = Depends(get_session),
):
    """Readings filtrados por reglas de negocio compuestas, pivotados por measurement set."""
    sensor_map = await _get_sensor_map(session)

    stmt = (
        select(MeasurementSet)
        .join(Sample, Sample.id == MeasurementSet.sample_id)
        .options(selectinload(MeasurementSet.sample))
    )
    if sample_ids:
        stmt = stmt.where(MeasurementSet.sample_id.in_(sample_ids))
    if ms_ids:
        stmt = stmt.where(MeasurementSet.id.in_(ms_ids))
    if only_complete:
        stmt = stmt.where(MeasurementSet.stopped_at.is_not(None))
    stmt = stmt.order_by(MeasurementSet.sample_id, MeasurementSet.repetition_number)

    ms_list = (await session.scalars(stmt)).all()
    if not ms_list:
        return []

    found_ms_ids = [ms.id for ms in ms_list]
    readings_stmt = (
        select(Reading)
        .where(Reading.measurement_set_id.in_(found_ms_ids))
        .options(selectinload(Reading.values))
        .order_by(Reading.arduino_ms)
    )
    if estado is not None:
        readings_stmt = readings_stmt.where(Reading.estado == estado)
    if is_stable is not None:
        readings_stmt = readings_stmt.where(Reading.is_stable.is_(is_stable))

    all_readings = (await session.scalars(readings_stmt)).all()

    if has_risen is not None:
        all_readings = [
            r for r in all_readings
            if _combined_has_risen(r, settings.OBSERVER_POLICY) == has_risen
        ]

    base_means_by_ms: dict[int, dict[int, float]] = {}
    if subtract_base:
        base_means_by_ms = await _fetch_base_means(session, found_ms_ids)

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
            readings=_pivot_readings(
                readings,
                sensor_map,
                exclude_cooldown=estado != "cooldown",
                base_means=base_means_by_ms.get(ms.id) if subtract_base else None,
            ),
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
