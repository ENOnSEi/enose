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


class SensorMean(BaseModel):
    sensor: str
    mean: float | None


class MeasurementSetStableMeans(BaseModel):
    measurement_set_id: int
    repetition_number: int
    means: list[SensorMean]


class SampleStableMeans(BaseModel):
    sample_id: int
    sample_name: str
    measurement_sets: list[MeasurementSetStableMeans]


class PCAPoint(BaseModel):
    sample_id: int
    sample_name: str
    pc1: float
    pc2: float


class PCAResult(BaseModel):
    points: list[PCAPoint]
    explained_variance_ratio: list[float]
    variables: list[str]


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


async def _fetch_means_by_estado(
    session: AsyncSession, ms_ids: list[int], estado: str, is_stable: bool = True
) -> dict[int, dict[int, float]]:
    """Media de value por (measurement_set_id, sensor_id) para un estado y
    valor de is_stable dados — usada tanto para restar la base estable a la
    medición (estado="base", is_stable=true) como para reportar la media de
    medición estable o no estable (estado="medicion")."""
    stmt = (
        select(
            Reading.measurement_set_id,
            ReadingValue.sensor_id,
            func.avg(ReadingValue.value).label("mean_val"),
        )
        .join(ReadingValue, ReadingValue.reading_id == Reading.id)
        .where(
            Reading.measurement_set_id.in_(ms_ids),
            Reading.estado == estado,
            Reading.is_stable.is_(is_stable),
        )
        .group_by(Reading.measurement_set_id, ReadingValue.sensor_id)
    )
    result: dict[int, dict[int, float]] = {}
    for row in (await session.execute(stmt)).all():
        result.setdefault(row.measurement_set_id, {})[row.sensor_id] = float(row.mean_val)
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
        base_means_by_ms = await _fetch_means_by_estado(session, found_ms_ids, "base")

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


# ── Medias de fase de medición (estable/no estable, con/sin base) ───────────

async def _compute_stable_means(
    session: AsyncSession,
    sample_ids: list[int],
    is_stable: bool = True,
    subtract_base: bool = False,
) -> list[SampleStableMeans]:
    """Media por sensor de la fase de medición (estable o no, según
    ``is_stable``) de cada measurement set de las muestras pedidas.
    Si ``subtract_base`` es True, a cada media se le resta la media de la
    base estable (estado=base, is_stable=true) de ese mismo sensor/ms."""
    sensor_map = await _get_sensor_map(session)

    stmt = (
        select(MeasurementSet)
        .join(Sample, Sample.id == MeasurementSet.sample_id)
        .options(selectinload(MeasurementSet.sample))
        .where(MeasurementSet.sample_id.in_(sample_ids))
        .order_by(MeasurementSet.sample_id, MeasurementSet.repetition_number)
    )
    ms_list = (await session.scalars(stmt)).all()
    if not ms_list:
        return []

    ms_ids = [ms.id for ms in ms_list]
    means_by_ms = await _fetch_means_by_estado(session, ms_ids, "medicion", is_stable)

    base_means_by_ms: dict[int, dict[int, float]] = {}
    if subtract_base:
        base_means_by_ms = await _fetch_means_by_estado(session, ms_ids, "base", True)

    samples_by_id: dict[int, SampleStableMeans] = {}
    for ms in ms_list:
        sample_out = samples_by_id.setdefault(
            ms.sample_id,
            SampleStableMeans(sample_id=ms.sample_id, sample_name=ms.sample.name, measurement_sets=[]),
        )
        ms_means = means_by_ms.get(ms.id, {})
        ms_base_means = base_means_by_ms.get(ms.id, {})
        sensor_means: list[SensorMean] = []
        for sensor_id, sensor_name in sensor_map.items():
            value = ms_means.get(sensor_id)
            if value is not None and subtract_base:
                value -= ms_base_means.get(sensor_id, 0)
            sensor_means.append(SensorMean(sensor=sensor_name, mean=value))
        sample_out.measurement_sets.append(
            MeasurementSetStableMeans(
                measurement_set_id=ms.id,
                repetition_number=ms.repetition_number,
                means=sensor_means,
            )
        )
    a = [samples_by_id[sid] for sid in sample_ids if sid in samples_by_id]
    return a


@router.get("/stable-means", response_model=list[SampleStableMeans])
async def get_stable_means(
    sample_ids: list[int] = Query(..., min_length=1, description="IDs de las muestras a incluir"),
    is_stable: bool = Query(
        default=True,
        description="True=fase de medición ya asentada (is_stable=true), False=fase no estable (transitoria/ascendente)",
    ),
    subtract_base: bool = Query(
        default=False,
        description="Resta a cada media la media de la base estable (estado=base, is_stable=true) de ese sensor/measurement set",
    ),
    session: AsyncSession = Depends(get_session),
):
    """Media por sensor de la fase de medición (estable o no, según is_stable)
    de cada measurement set de cada muestra pedida, opcionalmente restando la base."""
    result = await _compute_stable_means(session, sample_ids, is_stable, subtract_base)
    if not result:
        raise HTTPException(404, "No measurement sets found for the given sample_ids")
    return result


_SENSOR_COLORS = {
    "tgs2620": "#1f77b4",
    "tgs2611": "#ff7f0e",
    "tgs2602": "#2ca02c",
    "tgs2600": "#d62728",
}
_CHART_BAR_WIDTH = 0.18
_CHART_MS_GAP = 0.15
_CHART_SAMPLE_GAP = 0.6


@router.get("/stable-means/chart")
async def get_stable_means_chart(
    sample_ids: list[int] = Query(..., min_length=1, description="IDs de las muestras a incluir"),
    is_stable: bool = Query(
        default=True,
        description="True=fase de medición ya asentada (is_stable=true), False=fase no estable (transitoria/ascendente)",
    ),
    subtract_base: bool = Query(
        default=False,
        description="Resta a cada media la media de la base estable (estado=base, is_stable=true) de ese sensor/measurement set",
    ),
    session: AsyncSession = Depends(get_session),
):
    """Gráfico de barras agrupado (PNG): grupo=muestra, subgrupo=measurement
    set, barra=sensor. Usa la misma consulta que /stable-means."""
    samples = await _compute_stable_means(session, sample_ids, is_stable, subtract_base)
    if not samples:
        raise HTTPException(404, "No measurement sets found for the given sample_ids")

    import io

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from fastapi.responses import Response

    n_ms = sum(len(s.measurement_sets) for s in samples)
    fig, ax = plt.subplots(figsize=(max(6, n_ms * 1.4), 5))

    x = 0.0
    ms_ticks: list[tuple[float, str]] = []
    sample_ticks: list[tuple[float, str]] = []
    seen_sensors: set[str] = set()

    for sample in samples:
        group_start = x
        for ms in sample.measurement_sets:
            cluster_start = x
            for i, sm in enumerate(ms.means):
                bar_x = x + i * _CHART_BAR_WIDTH
                height = sm.mean or 0
                ax.bar(
                    bar_x,
                    height,
                    width=_CHART_BAR_WIDTH,
                    color=_SENSOR_COLORS.get(sm.sensor, "#888888"),
                    label=sm.sensor if sm.sensor not in seen_sensors else None,
                )
                seen_sensors.add(sm.sensor)
            cluster_width = len(ms.means) * _CHART_BAR_WIDTH
            ms_ticks.append((cluster_start + cluster_width / 2 - _CHART_BAR_WIDTH / 2, f"rep{ms.repetition_number}"))
            x += cluster_width + _CHART_MS_GAP
        sample_ticks.append(((group_start + x - _CHART_MS_GAP) / 2, sample.sample_name))
        x += _CHART_SAMPLE_GAP

    ax.set_xticks([t[0] for t in ms_ticks])
    ax.set_xticklabels([t[1] for t in ms_ticks], fontsize=8)
    for xc, name in sample_ticks:
        ax.annotate(
            name,
            xy=(xc, 0),
            xytext=(0, -28),
            textcoords="offset points",
            ha="center",
            fontsize=10,
            fontweight="bold",
            annotation_clip=False,
        )
    ax.set_ylabel("Media ADC (medición estable)")
    ax.set_title("Medición estable por muestra / measurement set / sensor")
    ax.legend(title="Sensor")
    fig.subplots_adjust(bottom=0.22)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return Response(content=buf.getvalue(), media_type="image/png")


# ── PCA entre muestras (sensor × measurement_set como variable) ────────────

async def _compute_pca(
    session: AsyncSession,
    sample_ids: list[int],
    is_stable: bool = True,
    subtract_base: bool = False,
) -> PCAResult:
    """PCA (2 componentes) donde cada muestra es una observación y cada
    combinación sensor×measurement_set (repetición) es una variable. Todas
    las muestras deben compartir exactamente el mismo conjunto de
    repetition_number y no tener ninguna media nula, para poder construir
    una matriz rectangular."""
    samples = await _compute_stable_means(session, sample_ids, is_stable, subtract_base)
    if len(samples) < 2:
        raise HTTPException(400, "Se necesitan al menos 2 muestras con datos para la PCA")

    rep_sets = [frozenset(ms.repetition_number for ms in s.measurement_sets) for s in samples]
    if len(set(rep_sets)) != 1:
        detail = {s.sample_name: sorted(r) for s, r in zip(samples, rep_sets)}
        raise HTTPException(
            400,
            "Todas las muestras deben tener el mismo número de measurement sets para "
            f"comparar sensor×measurement_set como variable. Repeticiones encontradas: {detail}",
        )
    reps = sorted(rep_sets[0])
    sensor_names = sorted({sm.sensor for ms in samples[0].measurement_sets for sm in ms.means})
    variables = [f"{sensor}_rep{rep}" for sensor in sensor_names for rep in reps]

    rows: list[list[float]] = []
    for s in samples:
        ms_by_rep = {ms.repetition_number: ms for ms in s.measurement_sets}
        row: list[float] = []
        for sensor in sensor_names:
            for rep in reps:
                sm = next((m for m in ms_by_rep[rep].means if m.sensor == sensor), None)
                if sm is None or sm.mean is None:
                    raise HTTPException(
                        400,
                        f"Muestra '{s.sample_name}' no tiene media estable para {sensor} en "
                        f"rep{rep} — no se puede construir una matriz completa",
                    )
                row.append(sm.mean)
        rows.append(row)

    import numpy as np
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    X = StandardScaler().fit_transform(np.array(rows))
    pca = PCA(n_components=2)
    coords = pca.fit_transform(X)

    return PCAResult(
        points=[
            PCAPoint(sample_id=s.sample_id, sample_name=s.sample_name, pc1=float(c[0]), pc2=float(c[1]))
            for s, c in zip(samples, coords)
        ],
        explained_variance_ratio=[float(v) for v in pca.explained_variance_ratio_],
        variables=variables,
    )


@router.get("/pca", response_model=PCAResult)
async def get_pca(
    sample_ids: list[int] = Query(
        ..., min_length=2, description="IDs de las muestras a comparar (mínimo 2, todas con el mismo número de measurement sets)"
    ),
    is_stable: bool = Query(
        default=True, description="True=fase de medición estable, False=fase no estable (transitoria/ascendente)"
    ),
    subtract_base: bool = Query(
        default=False, description="Resta la media de la base estable antes de construir las variables"
    ),
    session: AsyncSession = Depends(get_session),
):
    """PCA (2 componentes): cada muestra es una observación, cada
    sensor×measurement_set es una variable. Todas las muestras deben tener
    el mismo número de measurement sets con datos completos."""
    return await _compute_pca(session, sample_ids, is_stable, subtract_base)


@router.get("/pca/chart")
async def get_pca_chart(
    sample_ids: list[int] = Query(
        ..., min_length=2, description="IDs de las muestras a comparar (mínimo 2, todas con el mismo número de measurement sets)"
    ),
    is_stable: bool = Query(
        default=True, description="True=fase de medición estable, False=fase no estable (transitoria/ascendente)"
    ),
    subtract_base: bool = Query(
        default=False, description="Resta la media de la base estable antes de construir las variables"
    ),
    session: AsyncSession = Depends(get_session),
):
    """Scatter 2D (PNG) de la PCA: un punto por muestra, etiquetado con su
    nombre, ejes con el % de varianza explicada por cada componente."""
    result = await _compute_pca(session, sample_ids, is_stable, subtract_base)

    import io

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from fastapi.responses import Response

    fig, ax = plt.subplots(figsize=(7, 6))
    cmap = plt.get_cmap("tab10")
    for i, p in enumerate(result.points):
        color = cmap(i % 10)
        ax.scatter(p.pc1, p.pc2, color=color, s=90, label=p.sample_name)
        ax.annotate(
            p.sample_name,
            xy=(p.pc1, p.pc2),
            xytext=(6, 6),
            textcoords="offset points",
            fontsize=8,
        )

    var1, var2 = result.explained_variance_ratio
    ax.set_xlabel(f"PC1 ({var1 * 100:.1f}% var)")
    ax.set_ylabel(f"PC2 ({var2 * 100:.1f}% var)")
    ax.set_title("PCA de muestras (sensor × measurement set como variables)")
    ax.axhline(0, color="#cccccc", linewidth=0.8, zorder=0)
    ax.axvline(0, color="#cccccc", linewidth=0.8, zorder=0)
    ax.legend(fontsize=7, loc="best")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return Response(content=buf.getvalue(), media_type="image/png")
