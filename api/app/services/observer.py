import asyncio
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.database import AsyncSessionLocal
from app.models.measurement_set import MeasurementSet
from app.models.reading import Reading
from app.services import measurement_state, serial_reader
from app.services.slope_analyzer import SlopeAnalyzer


class Observer:
    def __init__(
        self,
        sensor_cache: dict[str, int],
        window: int = 20,
        threshold: float = 1.0,
        poll_interval: float = 1.0,
        min_medicion_seconds: float = 30.0,
    ):
        self._sensor_id_to_name = {v: k for k, v in sensor_cache.items()}
        self._analyzer = SlopeAnalyzer(window=window, threshold=threshold)
        self._poll_interval = poll_interval
        self._min_medicion_seconds = min_medicion_seconds
        self._window = window

    async def run(self) -> None:
        state = "waiting"
        medicion_start: float | None = None
        was_running = False

        while True:
            await asyncio.sleep(self._poll_interval)

            running = serial_reader.get_status()["running"]

            # reset al detectar parada
            if was_running and not running:
                state = "waiting"
                medicion_start = None

            was_running = running

            if not running:
                continue

            samples = await self._fetch_window()
            if len(samples) < 2:
                continue

            if state == "waiting":
                if self._analyzer.all_stable(samples):
                    print("[observer] base estable → medicion")
                    serial_reader.set_estado("medicion")
                    state = "measuring"
                    medicion_start = time.monotonic()

            elif state == "measuring" and medicion_start is not None:
                elapsed = time.monotonic() - medicion_start
                stable = self._analyzer.all_stable(samples)
                if elapsed >= self._min_medicion_seconds and stable:
                    reason = f"{elapsed:.1f}s transcurridos y pendiente estable"
                    print(f"[observer] medicion completa ({reason}) → stop")
                    await self._close_measurement_set()
                    serial_reader.stop()
                    state = "waiting"
                    medicion_start = None

    async def _fetch_window(self) -> list[tuple[int, dict[str, int]]]:
        ms_id = measurement_state.get_current()
        async with AsyncSessionLocal() as session:
            query = (
                select(Reading)
                .options(selectinload(Reading.values))
                .order_by(Reading.id.desc())
                .limit(self._window)
            )
            if ms_id is not None:
                query = query.where(Reading.measurement_set_id == ms_id)
            rows = list(reversed((await session.scalars(query)).all()))

        result = []
        for r in rows:
            vals = {
                self._sensor_id_to_name[v.sensor_id]: v.value
                for v in r.values
                if v.sensor_id in self._sensor_id_to_name
            }
            result.append((r.arduino_ms, vals))
        return result

    async def _close_measurement_set(self) -> None:
        # esperar a que el drain vacíe la queue antes de cerrar
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
