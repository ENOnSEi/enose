"""Gráficos de diagnóstico (PNG), solo lectura.

- /measurement-sets/{ms_id}/chart : curva de una repetición con sus fases
- /samples/{sample_id}/chart      : repeticiones superpuestas (repetibilidad)
- /export/drift/chart             : nivel de aire limpio (R0) a lo largo de los días
- /export/fingerprint/chart       : huella (radar) de cada sustancia

Nivel de referencia de cada sensor: media de la base estable (estado=base,
is_stable=true) de la repetición; si no hay lecturas estables, media de la
segunda mitad de la base.
"""

import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_session
from app.models.measurement_set import MeasurementSet
from app.models.reading import Reading
from app.models.sample import Sample
from app.routers.export import _SENSOR_COLORS, _fetch_means_by_estado, _get_sensor_map

router = APIRouter(tags=["charts"])

_PHASE_COLORS = {"base": "#9DB4C8", "medicion": "#E8A33D", "cooldown": "#B9D7C4"}
_PHASE_LABELS = {"base": "base", "medicion": "medición", "cooldown": "cooldown"}


# ── utilidades ──────────────────────────────────────────────────────────────

def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _png(fig) -> Response:
    plt = _plt()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    return Response(content=buf.getvalue(), media_type="image/png")


def _sensor_order(names) -> list[str]:
    known = [n for n in _SENSOR_COLORS if n in names]
    return known + sorted(n for n in names if n not in _SENSOR_COLORS)


async def _readings_of(session: AsyncSession, ms_ids: list[int]) -> dict[int, list[Reading]]:
    rows = (await session.scalars(
        select(Reading)
        .where(Reading.measurement_set_id.in_(ms_ids))
        .options(selectinload(Reading.values))
        .order_by(Reading.arduino_ms)
    )).all()
    out: dict[int, list[Reading]] = {}
    for r in rows:
        out.setdefault(r.measurement_set_id, []).append(r)
    return out


def _series(readings: list[Reading], sensor_map: dict[int, str]) -> dict[str, list[tuple[float, int, str, bool]]]:
    """{sensor: [(t_seg, valor, estado, is_stable)]} con t relativo a la primera lectura."""
    if not readings:
        return {}
    t0 = readings[0].arduino_ms
    out: dict[str, list] = {}
    for r in readings:
        t = (r.arduino_ms - t0) / 1000.0
        for rv in r.values:
            name = sensor_map.get(rv.sensor_id)
            if name:
                out.setdefault(name, []).append((t, rv.value, r.estado, r.is_stable))
    return out


def _base_level(points) -> float | None:
    base = [p for p in points if p[2] == "base"]
    if not base:
        return None
    stable = [p[1] for p in base if p[3]]
    values = stable or [p[1] for p in base[len(base) // 2:]]
    return sum(values) / len(values)


def _stable_medicion_level(points) -> float | None:
    med = [p for p in points if p[2] == "medicion"]
    if not med:
        return None
    stable = [p[1] for p in med if p[3]]
    values = stable or [p[1] for p in med[len(med) // 2:]]
    return sum(values) / len(values)


def _phase_blocks(times: list[float], estados: list[str]) -> list[tuple[str, float, float]]:
    blocks: list[tuple[str, float, float]] = []
    for t, e in zip(times, estados):
        if blocks and blocks[-1][0] == e:
            blocks[-1] = (e, blocks[-1][1], t)
        else:
            blocks.append((e, t, t))
    return blocks


# ── 1. curva de una repetición ──────────────────────────────────────────────

@router.get("/measurement-sets/{ms_id}/chart")
async def measurement_set_chart(
    ms_id: int,
    relative: bool = Query(True, description="True = cada sensor relativo a su base (se ve la subida); False = valores ADC brutos"),
    include_cooldown: bool = Query(True, description="Añade el cooldown que siguió a esta repetición, si lo hubo"),
    session: AsyncSession = Depends(get_session),
):
    """Curva de los 4 sensores en una repetición: fases coloreadas, tramos
    estables marcados abajo y línea donde el sistema dio la medición por
    terminada. En la leyenda, la subida (delta) de cada sensor."""
    ms = await session.get(MeasurementSet, ms_id)
    if not ms:
        raise HTTPException(404, f"MeasurementSet {ms_id} not found")
    sample = await session.get(Sample, ms.sample_id)
    sensor_map = await _get_sensor_map(session)
    readings = (await _readings_of(session, [ms_id])).get(ms_id, [])
    if not readings:
        raise HTTPException(404, f"MeasurementSet {ms_id} no tiene lecturas")

    if include_cooldown and ms.stopped_at is not None:
        nxt = await session.scalar(
            select(MeasurementSet.started_at).where(
                MeasurementSet.sample_id == ms.sample_id,
                MeasurementSet.repetition_number == ms.repetition_number + 1,
            )
        )
        stmt = (select(Reading).where(Reading.sample_id == ms.sample_id, Reading.estado == "cooldown",
                                      Reading.captured_at >= ms.stopped_at)
                .options(selectinload(Reading.values)).order_by(Reading.arduino_ms))
        if nxt is not None:
            stmt = stmt.where(Reading.captured_at < nxt)
        cooldown = [r for r in (await session.scalars(stmt)).all() if r.arduino_ms >= readings[-1].arduino_ms]
        readings = readings + cooldown

    series = _series(readings, sensor_map)
    sensors = _sensor_order(series.keys())
    plt = _plt()
    fig, (ax, rug) = plt.subplots(2, 1, figsize=(10, 5.6), sharex=True,
                                  gridspec_kw={"height_ratios": [12, 1], "hspace": 0.05})

    ref = series[sensors[0]]
    times, estados = [p[0] for p in ref], [p[2] for p in ref]
    for estado, a, b in _phase_blocks(times, estados):
        ax.axvspan(a, b, color=_PHASE_COLORS.get(estado, "#eeeeee"), alpha=0.3, lw=0)
        ax.text((a + b) / 2, 1.01, _PHASE_LABELS.get(estado, estado), transform=ax.get_xaxis_transform(),
                ha="center", va="bottom", fontsize=9, color="#444444")

    for name in sensors:
        pts = series[name]
        base = _base_level(pts)
        top = _stable_medicion_level(pts)
        offset = base if (relative and base is not None) else 0
        delta = f" · Δ {top - base:+.0f}" if base is not None and top is not None else ""
        ax.plot([p[0] for p in pts], [p[1] - offset for p in pts], lw=1.4,
                color=_SENSOR_COLORS.get(name, "#888888"), label=f"{name}{delta}")

    med_times = [p[0] for p in ref if p[2] == "medicion"]
    if med_times and ms.stopped_at is not None:
        ax.axvline(med_times[-1], color="#C0392B", lw=1.2, ls="--")
        ax.text(med_times[-1], 0.97, " fin de medición", transform=ax.get_xaxis_transform(),
                color="#C0392B", fontsize=8, va="top")
    if relative:
        ax.axhline(0, color="#999999", lw=0.8)
    ax.set_ylabel("subida respecto a la base (ADC)" if relative else "lectura (ADC)")
    ax.legend(fontsize=8, loc="upper left", frameon=False)
    ax.grid(alpha=0.25)

    for t, e, s in zip(times, estados, [p[3] for p in ref]):
        if s:
            rug.axvspan(t - 0.1, t + 0.1, color=_PHASE_COLORS.get(e, "#999999"), lw=0)
    rug.set_yticks([])
    rug.set_ylabel("estable", rotation=0, ha="right", va="center", fontsize=8)
    rug.set_xlabel("segundos desde el inicio de la repetición")

    estado_txt = "completa" if ms.stopped_at is not None else "INCOMPLETA"
    outl = f" · outlier en: {', '.join(sensor_map.get(i, str(i)) for i in ms.outlier_sensors)}" if ms.outlier_sensors else ""
    fig.suptitle(f"{sample.name if sample else '?'} · rep {ms.repetition_number} (ms {ms_id}) · {estado_txt}{outl}",
                 fontsize=11, y=0.99)
    fig.subplots_adjust(top=0.9, bottom=0.1, left=0.08, right=0.98)
    return _png(fig)


# ── 2. repeticiones superpuestas ────────────────────────────────────────────

@router.get("/samples/{sample_id}/chart")
async def sample_chart(
    sample_id: int,
    only_complete: bool = Query(False, description="Ocultar repeticiones incompletas (por defecto se pintan en gris)"),
    base_seconds: float = Query(10.0, ge=0, description="Segundos de base que se muestran antes del inicio de la medición"),
    session: AsyncSession = Depends(get_session),
):
    """Un panel por sensor con todas las repeticiones superpuestas, alineadas
    al inicio de la medición y relativas a su base. Color = orden de la rep
    (de claro a oscuro); rojo discontinuo = rep marcada como outlier en ese
    sensor; gris punteado = rep incompleta."""
    sample = await session.get(Sample, sample_id)
    if not sample:
        raise HTTPException(404, f"Sample {sample_id} not found")
    ms_list = (await session.scalars(
        select(MeasurementSet).where(MeasurementSet.sample_id == sample_id)
        .order_by(MeasurementSet.repetition_number)
    )).all()
    if only_complete:
        ms_list = [m for m in ms_list if m.stopped_at is not None]
    if not ms_list:
        raise HTTPException(404, f"Sample {sample_id} no tiene repeticiones")

    sensor_map = await _get_sensor_map(session)
    readings = await _readings_of(session, [m.id for m in ms_list])
    per_ms = {m.id: _series(readings.get(m.id, []), sensor_map) for m in ms_list}
    sensors = _sensor_order({s for ser in per_ms.values() for s in ser})
    if not sensors:
        raise HTTPException(404, f"Sample {sample_id} no tiene lecturas")

    plt = _plt()
    cmap = plt.get_cmap("viridis")
    n = len(ms_list)
    ncols = 2
    nrows = (len(sensors) + 1) // 2
    fig, axes = plt.subplots(nrows, ncols, figsize=(11, 3.4 * nrows), squeeze=False)
    for k, name in enumerate(sensors):
        ax = axes[k // ncols][k % ncols]
        ax.axvspan(-base_seconds, 0, color=_PHASE_COLORS["base"], alpha=0.25, lw=0)
        sensor_id = next((i for i, s in sensor_map.items() if s == name), None)
        for j, ms in enumerate(ms_list):
            pts = per_ms[ms.id].get(name, [])
            base = _base_level(pts)
            med = [p for p in pts if p[2] == "medicion"]
            if base is None or not med:
                continue
            t_med = med[0][0]
            shown = [p for p in pts if p[0] >= t_med - base_seconds]
            x = [p[0] - t_med for p in shown]
            y = [p[1] - base for p in shown]
            if ms.stopped_at is None:
                style = dict(color="#9E9E9E", ls=":", lw=1.2)
            elif sensor_id in (ms.outlier_sensors or []):
                style = dict(color="#C0392B", ls="--", lw=1.6)
            else:
                style = dict(color=cmap(0.15 + 0.7 * j / max(n - 1, 1)), lw=1.4)
            ax.plot(x, y, label=f"rep {ms.repetition_number}", **style)
        ax.axhline(0, color="#999999", lw=0.8)
        ax.axvline(0, color="#999999", lw=0.8, ls=":")
        ax.set_title(name, fontsize=10, color=_SENSOR_COLORS.get(name, "#333333"))
        ax.grid(alpha=0.25)
        ax.set_xlabel("segundos desde el inicio de la medición", fontsize=8)
        ax.set_ylabel("subida respecto a la base (ADC)", fontsize=8)
    for k in range(len(sensors), nrows * ncols):
        axes[k // ncols][k % ncols].axis("off")
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper right", fontsize=8, frameon=False, ncol=min(n, 6))
    done = sum(1 for m in ms_list if m.stopped_at is not None)
    fig.suptitle(f"{sample.name} (sample {sample_id}) · {done}/{sample.n_repetitions} repeticiones completas · "
                 "rojo = outlier · gris = incompleta", fontsize=11, x=0.01, ha="left")
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    return _png(fig)


# ── 3. deriva del aire limpio ───────────────────────────────────────────────

@router.get("/export/drift/chart")
async def drift_chart(
    sample_ids: list[int] | None = Query(None, description="Samples a incluir; por defecto, todos"),
    name: str | None = Query(None, description="Filtra por parte del nombre (insensible a mayúsculas)"),
    reps: str = Query("first", pattern="^(first|all)$",
                      description="first = R0 de la primera rep completa de cada Sample; all = media de todas sus reps completas"),
    session: AsyncSession = Depends(get_session),
):
    """Nivel de aire limpio (R0 = media de la base estable) de cada sensor, un
    punto por Sample en orden cronológico. Las franjas alternas agrupan los
    Samples de un mismo día; el color es la sustancia. Si R0 cambia por días,
    o cada sustancia cae en una zona distinta, hay efecto día."""
    stmt = select(Sample).order_by(Sample.started_at)
    if sample_ids:
        stmt = stmt.where(Sample.id.in_(sample_ids))
    if name:
        stmt = stmt.where(Sample.name.ilike(f"%{name}%"))
    samples = (await session.scalars(stmt)).all()
    if not samples:
        raise HTTPException(404, "No hay Samples con esos filtros")

    ms_rows = (await session.scalars(
        select(MeasurementSet).where(MeasurementSet.sample_id.in_([s.id for s in samples]),
                                     MeasurementSet.stopped_at.is_not(None))
        .order_by(MeasurementSet.sample_id, MeasurementSet.repetition_number)
    )).all()
    ms_by_sample: dict[int, list[int]] = {}
    for m in ms_rows:
        ms_by_sample.setdefault(m.sample_id, []).append(m.id)
    chosen = {sid: (ids[:1] if reps == "first" else ids) for sid, ids in ms_by_sample.items()}
    base = await _fetch_means_by_estado(session, [i for ids in chosen.values() for i in ids], "base")
    sensor_map = await _get_sensor_map(session)

    points = []  # (sample, {sensor: r0})
    for s in samples:
        vals: dict[str, list[float]] = {}
        for ms_id in chosen.get(s.id, []):
            for sid, v in base.get(ms_id, {}).items():
                if sid in sensor_map:
                    vals.setdefault(sensor_map[sid], []).append(v)
        if vals:
            points.append((s, {k: sum(v) / len(v) for k, v in vals.items()}))
    if not points:
        raise HTTPException(404, "Ningún Sample tiene base estable en repeticiones completas")

    sensors = _sensor_order({k for _, d in points for k in d})
    names = list(dict.fromkeys(s.name for s, _ in points))
    plt = _plt()
    cmap = plt.get_cmap("tab10" if len(names) <= 10 else "tab20")
    color_of = {n: cmap(i % cmap.N) for i, n in enumerate(names)}
    days = [s.started_at.date() for s, _ in points]

    fig, axes = plt.subplots(len(sensors), 1, figsize=(max(9, len(points) * 0.35), 2.3 * len(sensors) + 1),
                             sharex=True, squeeze=False)
    for k, sensor in enumerate(sensors):
        ax = axes[k][0]
        start = 0
        for i in range(1, len(days) + 1):
            if i == len(days) or days[i] != days[start]:
                if (len({d for d in days[:start]}) % 2) == 1:
                    ax.axvspan(start - 0.5, i - 0.5, color="#EEF2F6", lw=0)
                if k == 0:
                    ax.text((start + i - 1) / 2, 1.02, days[start].strftime("%d/%m"), transform=ax.get_xaxis_transform(),
                            ha="center", fontsize=8, color="#555555")
                start = i
        xs = [i for i, (_, d) in enumerate(points) if sensor in d]
        ys = [d[sensor] for _, d in points if sensor in d]
        ax.plot(xs, ys, color="#BBBBBB", lw=0.8, zorder=1)
        for i, (s, d) in enumerate(points):
            if sensor in d:
                ax.scatter(i, d[sensor], color=color_of[s.name], s=36, zorder=2, edgecolor="white", linewidth=0.5)
        ax.set_ylabel(f"{sensor}\nR0 (ADC)", fontsize=8, color=_SENSOR_COLORS.get(sensor, "#333333"))
        ax.grid(alpha=0.25, axis="y")
    axes[-1][0].set_xticks(range(len(points)))
    axes[-1][0].set_xticklabels([f"{s.id}" for s, _ in points], fontsize=7, rotation=90)
    axes[-1][0].set_xlabel("sample_id (orden cronológico; franjas = días)")
    handles = [plt.Line2D([], [], marker="o", ls="", color=color_of[n], label=n) for n in names]
    fig.legend(handles=handles, loc="upper right", fontsize=8, frameon=False, ncol=min(len(names), 6))
    fig.suptitle("Deriva del aire limpio (R0) por Sample", fontsize=11, x=0.01, ha="left")
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    return _png(fig)


# ── 4. huella de cada sustancia ─────────────────────────────────────────────

@router.get("/export/fingerprint/chart")
async def fingerprint_chart(
    sample_ids: list[int] = Query(..., min_length=1, description="Samples a incluir"),
    normalize: bool = Query(True, description="True = compara la FORMA (cada huella escalada a su sensor máximo); False = tamaño real"),
    session: AsyncSession = Depends(get_session),
):
    """Radar con la respuesta relativa de cada sensor, (medición − base) / base,
    media de las repeticiones completas. Una forma gruesa por sustancia (media
    de sus Samples) y, en fino, cada Sample por separado para ver la dispersión."""
    samples = (await session.scalars(select(Sample).where(Sample.id.in_(sample_ids)))).all()
    if not samples:
        raise HTTPException(404, "No se encontraron esos Samples")
    ms_rows = (await session.scalars(
        select(MeasurementSet).where(MeasurementSet.sample_id.in_([s.id for s in samples]),
                                     MeasurementSet.stopped_at.is_not(None))
    )).all()
    if not ms_rows:
        raise HTTPException(404, "Esos Samples no tienen repeticiones completas")
    ms_ids = [m.id for m in ms_rows]
    base = await _fetch_means_by_estado(session, ms_ids, "base")
    med = await _fetch_means_by_estado(session, ms_ids, "medicion")
    sensor_map = await _get_sensor_map(session)

    per_sample: dict[int, dict[str, float]] = {}
    for m in ms_rows:
        for sid, b in base.get(m.id, {}).items():
            v = med.get(m.id, {}).get(sid)
            if v is None or not b or sid not in sensor_map:
                continue
            per_sample.setdefault(m.sample_id, {}).setdefault(sensor_map[sid], []).append((v - b) / b)
    per_sample = {k: {s: sum(v) / len(v) for s, v in d.items()} for k, d in per_sample.items()}
    if not per_sample:
        raise HTTPException(404, "Ninguna repetición tiene base y medición estables")

    sensors = _sensor_order({s for d in per_sample.values() for s in d})
    name_of = {s.id: s.name for s in samples}

    def scaled(vec: dict[str, float]) -> list[float]:
        vals = [vec.get(s, 0.0) for s in sensors]
        if normalize:
            top = max((abs(v) for v in vals), default=0) or 1.0
            vals = [v / top for v in vals]
        return vals

    by_name: dict[str, list[dict[str, float]]] = {}
    for sid, vec in per_sample.items():
        by_name.setdefault(name_of[sid], []).append(vec)

    import math
    plt = _plt()
    angles = [2 * math.pi * i / len(sensors) for i in range(len(sensors))]
    fig = plt.figure(figsize=(8, 8))
    ax = fig.add_subplot(111, polar=True)
    ax.set_theta_offset(math.pi / 2)   # primer sensor arriba, en sentido horario
    ax.set_theta_direction(-1)
    cmap = plt.get_cmap("tab10")
    for i, (name, vecs) in enumerate(by_name.items()):
        color = cmap(i % 10)
        for vec in vecs:
            vals = scaled(vec)
            ax.plot(angles + angles[:1], vals + vals[:1], color=color, lw=0.7, alpha=0.45)
        mean_vec = {s: sum(v.get(s, 0.0) for v in vecs) / len(vecs) for s in sensors}
        vals = scaled(mean_vec)
        ax.plot(angles + angles[:1], vals + vals[:1], color=color, lw=2.4, label=f"{name} ({len(vecs)} samples)")
        ax.fill(angles + angles[:1], vals + vals[:1], color=color, alpha=0.12)
    ax.set_xticks(angles)
    ax.set_xticklabels(sensors, fontsize=10)
    ax.tick_params(axis="x", pad=14)
    ax.tick_params(axis="y", labelsize=7, colors="#777777")
    ax.set_rlabel_position(45)
    fig.suptitle("Huella por sustancia", fontsize=12, y=0.98)
    fig.text(0.5, 0.935, "forma: cada huella escalada a su sensor máximo · fino = cada Sample" if normalize
             else "(medición − base) / base · fino = cada Sample", ha="center", fontsize=9, color="#555555")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.07), ncol=min(len(by_name), 4), fontsize=9, frameon=False)
    fig.subplots_adjust(top=0.84, bottom=0.12, left=0.1, right=0.9)
    return _png(fig)
