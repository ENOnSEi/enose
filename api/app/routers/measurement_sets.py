import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.database import get_session
from app.models.measurement_set import MeasurementSet
from app.models.reading import Reading, ReadingValue
from app.models.sample import Sample
from app.models.sensor import Sensor
from app.routers.export import _compute_stable_means, _get_sensor_map

router = APIRouter(tags=["stats"])

_WINDOW_SECONDS = 5


# ── Schemas ───────────────────────────────────────────────────────────────────

class EstadoStats(BaseModel):
    min: float
    max: float
    mean: float
    n_readings: int


class TransitionDiagnostics(BaseModel):
    base_std: float | None = None
    medicion_std: float | None = None
    transition_duration_s: float | None = None
    slope_estimate: float | None = None  # ADC/s — comparar con OBSERVER_SLOPE_THRESHOLD
    snr: float | None = None             # delta / base_std
    rose: bool | None = None             # slope_estimate > OBSERVER_SLOPE_THRESHOLD
    stabilized: bool | None = None       # measurement set completado normalmente por el Observer


class SensorStats(BaseModel):
    base: EstadoStats | None = None
    medicion: EstadoStats | None = None
    delta: float | None = None
    diagnostics: TransitionDiagnostics | None = None


class MeasurementSetStats(BaseModel):
    measurement_set_id: int
    repetition_number: int | None = None
    is_complete: bool
    stopped_at: datetime | None
    sensors: dict[str, SensorStats]


class MeasurementSetStatsResponse(BaseModel):
    measurement_set_id: int
    is_complete: bool
    stopped_at: datetime | None
    sensors: dict[str, SensorStats]


class SampleStatsResponse(BaseModel):
    sample_id: int
    measurement_sets: list[MeasurementSetStats]


class MeasurementSetOutliers(BaseModel):
    measurement_set_id: int
    repetition_number: int
    outlier_sensors: list[str]


class SampleOutliersResponse(BaseModel):
    sample_id: int
    sample_name: str
    measurement_sets: list[MeasurementSetOutliers]
    # Cómo y cuándo se etiquetó (lo mismo que se guarda en Sample.outlier_detection)
    detection: dict[str, Any] | None = None


# ── Query helpers ─────────────────────────────────────────────────────────────

async def _fetch_stats(session: AsyncSession, ms_ids: list[int]) -> list[Any]:
    """Min/max/mean/std per (ms_id, sensor, estado) for the last _WINDOW_SECONDS
    of each estado, anchored at max(captured_at) within that estado."""
    max_ts_cte = (
        select(
            Reading.measurement_set_id,
            Reading.estado,
            func.max(Reading.captured_at).label("max_ts"),
        )
        .where(
            Reading.measurement_set_id.in_(ms_ids),
            Reading.estado.in_(["base", "medicion"]),
        )
        .group_by(Reading.measurement_set_id, Reading.estado)
        .cte("max_ts")
    )

    stmt = (
        select(
            Reading.measurement_set_id,
            Sensor.name.label("sensor_name"),
            Reading.estado,
            func.min(ReadingValue.value).label("min_val"),
            func.max(ReadingValue.value).label("max_val"),
            func.avg(ReadingValue.value).label("mean_val"),
            func.stddev_pop(ReadingValue.value).label("std_val"),
            func.count(distinct(Reading.id)).label("n_readings"),
        )
        .join(ReadingValue, ReadingValue.reading_id == Reading.id)
        .join(Sensor, Sensor.id == ReadingValue.sensor_id)
        .join(
            max_ts_cte,
            (max_ts_cte.c.estado == Reading.estado)
            & (max_ts_cte.c.measurement_set_id == Reading.measurement_set_id),
        )
        .where(
            Reading.measurement_set_id.in_(ms_ids),
            Reading.estado.in_(["base", "medicion"]),
            Reading.captured_at
            >= max_ts_cte.c.max_ts - timedelta(seconds=_WINDOW_SECONDS),
        )
        .group_by(Reading.measurement_set_id, Sensor.name, Reading.estado)
    )

    return (await session.execute(stmt)).all()


async def _fetch_global_minmax(session: AsyncSession, ms_ids: list[int]) -> list[Any]:
    """Global min/max per (ms_id, sensor, estado) over all readings (no window)."""
    stmt = (
        select(
            Reading.measurement_set_id,
            Sensor.name.label("sensor_name"),
            Reading.estado,
            func.min(ReadingValue.value).label("min_val"),
            func.max(ReadingValue.value).label("max_val"),
        )
        .join(ReadingValue, ReadingValue.reading_id == Reading.id)
        .join(Sensor, Sensor.id == ReadingValue.sensor_id)
        .where(
            Reading.measurement_set_id.in_(ms_ids),
            Reading.estado.in_(["base", "medicion"]),
        )
        .group_by(Reading.measurement_set_id, Sensor.name, Reading.estado)
    )
    return (await session.execute(stmt)).all()


async def _fetch_transition_durations(
    session: AsyncSession, ms_ids: list[int]
) -> dict[int, float | None]:
    """Seconds between the first base reading and the first medicion reading per ms."""
    stmt = (
        select(
            Reading.measurement_set_id,
            func.min(
                case((Reading.estado == "medicion", Reading.captured_at), else_=None)
            ).label("first_medicion"),
            func.min(
                case((Reading.estado == "base", Reading.captured_at), else_=None)
            ).label("first_base"),
        )
        .where(Reading.measurement_set_id.in_(ms_ids))
        .group_by(Reading.measurement_set_id)
    )

    result: dict[int, float | None] = {}
    for row in (await session.execute(stmt)).all():
        if row.first_medicion and row.first_base:
            result[row.measurement_set_id] = (
                row.first_medicion - row.first_base
            ).total_seconds()
        else:
            result[row.measurement_set_id] = None
    return result


def _build_sensors(
    rows: list[Any],
    ms_id: int,
    transition_duration_s: float | None,
    is_complete: bool,
    global_minmax_rows: list[Any],
) -> dict[str, SensorStats]:
    global_minmax: dict[tuple[str, str], tuple[float, float]] = {
        (r.sensor_name, r.estado): (float(r.min_val), float(r.max_val))
        for r in global_minmax_rows
        if r.measurement_set_id == ms_id
    }

    sensor_data: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.measurement_set_id != ms_id:
            continue
        gmin, gmax = global_minmax.get(
            (row.sensor_name, row.estado), (float(row.min_val), float(row.max_val))
        )
        entry = sensor_data.setdefault(row.sensor_name, {})
        entry[row.estado] = {
            "stats": EstadoStats(
                min=gmin,
                max=gmax,
                mean=float(row.mean_val),
                n_readings=row.n_readings,
            ),
            "std": float(row.std_val) if row.std_val is not None else None,
        }

    sensors: dict[str, SensorStats] = {}
    for sensor_name, estados in sensor_data.items():
        base = estados.get("base")
        medicion = estados.get("medicion")

        base_stats: EstadoStats | None = base["stats"] if base else None
        medicion_stats: EstadoStats | None = medicion["stats"] if medicion else None
        base_std: float | None = base["std"] if base else None
        medicion_std: float | None = medicion["std"] if medicion else None

        delta = slope_estimate = snr = None
        rose = None
        if base_stats and medicion_stats:
            delta = medicion_stats.mean - base_stats.mean
            slope_estimate = delta / _WINDOW_SECONDS
            rose = slope_estimate > settings.OBSERVER_SLOPE_THRESHOLD
            if base_std and base_std > 0:
                snr = delta / base_std

        sensors[sensor_name] = SensorStats(
            base=base_stats,
            medicion=medicion_stats,
            delta=delta,
            diagnostics=TransitionDiagnostics(
                base_std=base_std,
                medicion_std=medicion_std,
                transition_duration_s=transition_duration_s,
                slope_estimate=slope_estimate,
                snr=snr,
                rose=rose,
                stabilized=is_complete,
            ),
        )
    return sensors


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/measurement-sets/{ms_id}/stats", response_model=MeasurementSetStatsResponse)
async def get_measurement_set_stats(
    ms_id: int, session: AsyncSession = Depends(get_session)
):
    ms = await session.get(MeasurementSet, ms_id)
    if not ms:
        raise HTTPException(404, f"MeasurementSet {ms_id} not found")

    rows, global_minmax_rows, durations = await asyncio.gather(
        _fetch_stats(session, [ms_id]),
        _fetch_global_minmax(session, [ms_id]),
        _fetch_transition_durations(session, [ms_id]),
    )
    is_complete = ms.stopped_at is not None

    return MeasurementSetStatsResponse(
        measurement_set_id=ms_id,
        is_complete=is_complete,
        stopped_at=ms.stopped_at,
        sensors=_build_sensors(rows, ms_id, durations.get(ms_id), is_complete, global_minmax_rows),
    )


@router.get("/samples/{sample_id}/stats", response_model=SampleStatsResponse)
async def get_sample_stats(
    sample_id: int, session: AsyncSession = Depends(get_session)
):
    if not await session.get(Sample, sample_id):
        raise HTTPException(404, f"Sample {sample_id} not found")

    ms_rows = (
        await session.execute(
            select(
                MeasurementSet.id,
                MeasurementSet.repetition_number,
                MeasurementSet.stopped_at,
            )
            .where(MeasurementSet.sample_id == sample_id)
            .order_by(MeasurementSet.repetition_number)
        )
    ).all()

    ms_ids = [row.id for row in ms_rows]
    rep_map = {row.id: row.repetition_number for row in ms_rows}
    stopped_at_map = {row.id: row.stopped_at for row in ms_rows}

    if ms_ids:
        stats_rows, global_minmax_rows, durations = await asyncio.gather(
            _fetch_stats(session, ms_ids),
            _fetch_global_minmax(session, ms_ids),
            _fetch_transition_durations(session, ms_ids),
        )
    else:
        stats_rows, global_minmax_rows, durations = [], [], {}

    return SampleStatsResponse(
        sample_id=sample_id,
        measurement_sets=[
            MeasurementSetStats(
                measurement_set_id=ms_id,
                repetition_number=rep_map[ms_id],
                is_complete=stopped_at_map[ms_id] is not None,
                stopped_at=stopped_at_map[ms_id],
                sensors=_build_sensors(
                    stats_rows,
                    ms_id,
                    durations.get(ms_id),
                    stopped_at_map[ms_id] is not None,
                    global_minmax_rows,
                ),
            )
            for ms_id in ms_ids
        ],
    )


@router.post("/samples/{sample_id}/detect-outliers", response_model=SampleOutliersResponse)
async def detect_outliers(
    sample_id: int,
    iqr_factor: float = Query(1.5, gt=0, description="Factor k del rango de Tukey [Q1 - k·IQR, Q3 + k·IQR]"),
    min_reps: int = Query(5, ge=3, description="Mínimo de measurement sets completos para etiquetar"),
    force: bool = Query(False, description="Re-etiquetar aunque el sample ya tenga outliers marcados"),
    session: AsyncSession = Depends(get_session),
):
    """Marca, por sensor, qué repeticiones (MeasurementSet) de un sample son
    outliers respecto a sus hermanas, usando el rango de Tukey
    ([Q1 - k·IQR, Q3 + k·IQR], k = ``iqr_factor``) sobre el delta estable
    (medición - base) de cada sensor. Persiste el resultado en
    MeasurementSet.outlier_sensors, y el método/parámetros/fecha en
    Sample.outlier_detection. Con ``force=true`` sobrescribe un etiquetado previo."""
    sample = await session.get(Sample, sample_id)
    if not sample:
        raise HTTPException(404, f"Sample {sample_id} not found")

    ms_list = (
        await session.scalars(
            select(MeasurementSet)
            .where(
                MeasurementSet.sample_id == sample_id,
                MeasurementSet.stopped_at.is_not(None),
            )
            .order_by(MeasurementSet.repetition_number)
        )
    ).all()

    if not ms_list:
        return SampleOutliersResponse(
            sample_id=sample_id, sample_name=sample.name, measurement_sets=[]
        )

    if len(ms_list) < min_reps:
        raise HTTPException(
            400,
            f"Sample {sample_id} has only {len(ms_list)} completed measurement sets; "
            f"at least {min_reps} are required to detect outliers",
        )

    if not force and any(ms.outlier_sensors for ms in ms_list):
        raise HTTPException(
            400,
            f"Sample {sample_id} already has measurement sets labeled as outliers; "
            "use force=true to re-run detect-outliers",
        )

    sensor_map = await _get_sensor_map(session)
    sensor_id_by_name = {name: sid for sid, name in sensor_map.items()}

    stable_means = await _compute_stable_means(
        session, [sample_id], is_stable=True, subtract_base=True
    )
    means_by_ms: dict[int, dict[str, float | None]] = {
        ms_means.measurement_set_id: {sm.sensor: sm.mean for sm in ms_means.means}
        for s in stable_means
        for ms_means in s.measurement_sets
    }

    import numpy as np

    deltas_by_sensor: dict[str, list[float]] = {}
    for ms in ms_list:
        for sensor_name, value in means_by_ms.get(ms.id, {}).items():
            if value is not None:
                deltas_by_sensor.setdefault(sensor_name, []).append(value)

    bounds: dict[str, tuple[float, float]] = {}
    for sensor_name, values in deltas_by_sensor.items():
        q1, q3 = np.percentile(values, [25, 75])
        iqr = q3 - q1
        bounds[sensor_name] = (q1 - iqr_factor * iqr, q3 + iqr_factor * iqr)

    result: list[MeasurementSetOutliers] = []
    for ms in ms_list:
        outlier_names = sorted(
            sensor_name
            for sensor_name, value in means_by_ms.get(ms.id, {}).items()
            if value is not None
            and not (bounds[sensor_name][0] <= value <= bounds[sensor_name][1])
        )
        ms.outlier_sensors = sorted(sensor_id_by_name[name] for name in outlier_names)
        session.add(ms)
        result.append(
            MeasurementSetOutliers(
                measurement_set_id=ms.id,
                repetition_number=ms.repetition_number,
                outlier_sensors=outlier_names,
            )
        )

    sample.outlier_detection = {
        "method": "tukey",
        "scale": "delta_stable",  # media estable de medición − media de base, en ADC
        "iqr_factor": iqr_factor,
        "min_reps": min_reps,
        "n_measurement_sets": len(ms_list),
        "forced": force,
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }
    session.add(sample)
    await session.commit()

    return SampleOutliersResponse(
        sample_id=sample_id,
        sample_name=sample.name,
        measurement_sets=result,
        detection=sample.outlier_detection,
    )
