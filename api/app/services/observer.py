import asyncio
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.database import AsyncSessionLocal
from app.models.measurement_set import MeasurementSet
from app.models.reading import Reading
from app.models.sample import Sample
from app.services import board_ws, measurement_state
from app.services.analyzer import Policy, SignalAnalyzer


class Observer:
    """Orquesta el ciclo de un Sample: N repeticiones de base → medicion → cooldown.

    Lee lotes de lecturas de Postgres, se los pasa al :class:`SignalAnalyzer` y
    actúa sobre la placa SOLO cuando el analizador confirma la estabilización.
    No calcula pendientes: esa responsabilidad es del analizador.
    """

    def __init__(
        self,
        sensor_cache: dict[str, int],
        window_seconds: float = 4.0,
        slope_threshold: float = 7.5,
        hysteresis: float = 0.15,
        confirm_seconds: float = 1.0,
        policy: Policy = Policy.ALL,
        fetch_limit: int = 300,
        poll_interval: float = 1.0,
        min_medicion_seconds: float = 30.0,
    ):
        self._sensor_id_to_name = {v: k for k, v in sensor_cache.items()}
        self._analyzer = SignalAnalyzer(
            window_seconds=window_seconds,
            slope_threshold=slope_threshold,
            hysteresis=hysteresis,
            confirm_seconds=confirm_seconds,
            policy=policy,
        )
        self._poll_interval = poll_interval
        self._min_medicion_seconds = min_medicion_seconds
        self._fetch_limit = fetch_limit
        # arranca en fase base: señal plana, sin exigir subida previa
        self._analyzer.reset(require_rise=False)

    async def run(self) -> None:
        state = "start_base"
        rep = 0
        medicion_start: float | None = None
        was_running = False

        while True:
            await asyncio.sleep(self._poll_interval)

            running = board_ws.get_status()["running"]

            if was_running and not running:
                state = "start_base"
                rep = 0
                medicion_start = None
                self._analyzer.reset(require_rise=False)

            was_running = running

            if not running:
                continue

            n_reps = measurement_state.get_current_sample_n_repetitions()
            if n_reps == 0:
                continue

            if state == "start_base":
                rep += 1
                # rep 1 ya fue creado por el router; para el resto, crear aquí
                if measurement_state.get_current_ms() is None:
                    ms = await self._create_ms(rep)
                    measurement_state.set_current_ms(ms.id)
                board_ws.set_estado("base")
                # base: señal plana, no se exige subida previa
                self._analyzer.reset(require_rise=False)
                print(f"[observer] rep {rep}/{n_reps}: base iniciada (ms_id={measurement_state.get_current_ms()})")
                state = "waiting_base"

            elif state == "waiting_base":
                samples = await self._fetch_window_by_ms()
                result = self._analyzer.update(samples)
                self._log(state, result)
                if result.stable:
                    print(f"[observer] rep {rep}/{n_reps}: base estable → medicion")
                    board_ws.set_estado("medicion")
                    # medición: exigir subida antes de estabilizar
                    self._analyzer.reset(require_rise=True)
                    state = "measuring"
                    medicion_start = time.monotonic()

            elif state == "measuring" and medicion_start is not None:
                elapsed = time.monotonic() - medicion_start
                samples = await self._fetch_window_by_ms()
                result = self._analyzer.update(samples)
                self._log(state, result)
                if elapsed >= self._min_medicion_seconds and result.stable:
                    print(f"[observer] rep {rep}/{n_reps}: medicion completa ({elapsed:.1f}s)")
                    await self._close_current_ms()
                    await self._increment_completed_repetitions()
                    if rep >= n_reps:
                        print("[observer] sample completo → stop")
                        await self._close_sample()
                        board_ws.stop()
                        state = "start_base"
                        rep = 0
                        medicion_start = None
                        self._analyzer.reset(require_rise=False)
                    else:
                        board_ws.set_estado("cooldown")
                        self._analyzer.reset(require_rise=False)
                        state = "cooldown"

            elif state == "cooldown":
                samples = await self._fetch_window_cooldown()
                result = self._analyzer.update(samples)
                self._log(state, result)
                if result.stable:
                    print(f"[observer] cooldown estable → rep {rep + 1}")
                    state = "start_base"

    def _log(self, state: str, result) -> None:
        """Traza pendiente y estado por canal para calibrar los umbrales."""
        channels = " ".join(
            f"{name}={r.slope:+.1f}/{r.state.value[:4]}" if r.slope is not None
            else f"{name}=--"
            for name, r in result.channels.items()
        )
        if state == "measuring":
            risen = " | risen=" + "".join(
                name[3:] + ("✓" if r.has_risen else "✗")
                for name, r in result.channels.items()
            )
        else:
            risen = ""
        print(f"[observer] {state:11} stable={result.stable} | {channels}{risen}")

    async def _create_ms(self, rep: int) -> MeasurementSet:
        async with AsyncSessionLocal() as session:
            ms = MeasurementSet(
                sample_id=measurement_state.get_current_sample_id(),
                repetition_number=rep,
            )
            session.add(ms)
            await session.commit()
            await session.refresh(ms)
            return ms

    async def _close_current_ms(self) -> None:
        for _ in range(20):
            if board_ws.get_status()["readings_queued"] == 0:
                break
            await asyncio.sleep(0.5)
        ms_id = measurement_state.get_current_ms()
        if ms_id is None:
            return
        async with AsyncSessionLocal() as session:
            ms = await session.get(MeasurementSet, ms_id)
            if ms:
                ms.stopped_at = datetime.now(timezone.utc)
                await session.commit()
        measurement_state.set_current_ms(None)

    async def _increment_completed_repetitions(self) -> None:
        sample_id = measurement_state.get_current_sample_id()
        if sample_id is None:
            return
        async with AsyncSessionLocal() as session:
            sample = await session.get(Sample, sample_id)
            if sample:
                sample.completed_repetitions += 1
                await session.commit()

    async def _close_sample(self) -> None:
        sample_id = measurement_state.get_current_sample_id()
        if sample_id is None:
            return
        async with AsyncSessionLocal() as session:
            sample = await session.get(Sample, sample_id)
            if sample:
                sample.stopped_at = datetime.now(timezone.utc)
                await session.commit()
        measurement_state.clear()

    async def _fetch_window_by_ms(self) -> list[tuple[int, dict[str, int]]]:
        ms_id = measurement_state.get_current_ms()
        if ms_id is None:
            return []
        async with AsyncSessionLocal() as session:
            rows = list(reversed((await session.scalars(
                select(Reading)
                .options(selectinload(Reading.values))
                .where(Reading.measurement_set_id == ms_id)
                .order_by(Reading.id.desc())
                .limit(self._fetch_limit)
            )).all()))
        return self._to_samples(rows)

    async def _fetch_window_cooldown(self) -> list[tuple[int, dict[str, int]]]:
        sample_id = measurement_state.get_current_sample_id()
        if sample_id is None:
            return []
        async with AsyncSessionLocal() as session:
            rows = list(reversed((await session.scalars(
                select(Reading)
                .options(selectinload(Reading.values))
                .where(Reading.sample_id == sample_id, Reading.estado == "cooldown")
                .order_by(Reading.id.desc())
                .limit(self._fetch_limit)
            )).all()))
        return self._to_samples(rows)

    def _to_samples(self, rows: list) -> list[tuple[int, dict[str, int]]]:
        result = []
        for r in rows:
            vals = {
                self._sensor_id_to_name[v.sensor_id]: v.value
                for v in r.values
                if v.sensor_id in self._sensor_id_to_name
            }
            result.append((r.arduino_ms, vals))
        return result
