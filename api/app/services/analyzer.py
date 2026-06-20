"""Analizador de señal de la nariz electrónica.

Recibe muestras crudas (timestamp en ms + valor por sensor) y decide, por cada
canal de forma independiente, si la señal está **subiendo** o **estabilizada**.
No sabe nada de Postgres ni de la placa: solo calcula y devuelve una decisión.

Resuelve los cuatro problemas del enfoque ingenuo:

1. **Pendiente fiable**: regresión lineal por mínimos cuadrados sobre una
   ventana deslizante de varios segundos, no la resta de dos puntos. Un pico
   aislado apenas mueve la recta.
2. **Estabilidad numérica**: el tiempo de cada ventana se refiere a su primer
   punto (``t - t0``) y se trabaja en segundos (unidades/segundo), no en ``millis()`` crudos. Así
   se evita restar números grandes casi iguales y perder precisión.
3. **Histéresis (banda muerta)**: dos umbrales en vez de uno. Se confirma
   ``ESTABILIZADO`` cuando ``|pendiente| < lower`` y se vuelve a ``SUBIENDO``
   cuando ``|pendiente| > upper``. Dentro de la banda no se cambia de estado,
   lo que evita el *chattering* (empezar–parar–empezar) cuando la señal oscila
   junto al umbral. El umbral central es un valor **pequeño positivo**: se mide
   la *magnitud* de la pendiente, de modo que cero (señal plana) cae siempre
   por debajo de ``lower`` y la estabilización sí se confirma.
4. **Debounce temporal**: una condición debe sostenerse un tiempo mínimo
   (``confirm_seconds``) antes de dar el cambio por bueno. Un cruce puntual del
   umbral que vuelve atrás no dispara una transición falsa.

El reloj del debounce es el **tiempo de la propia señal** (el ``arduino_ms`` de
la última muestra), no el reloj de pared: si dejan de llegar datos, el tiempo no
avanza y no se confirma nada, que es justo lo que queremos.

**Latch "primero sube, luego se estabiliza"** (``require_rise``): en la fase de
medición la señal arranca plana (el olor aún no ha llegado al sensor), lo que el
analizador confundiría con "ya estabilizado". Por eso un canal solo puede
confirmar ESTABILIZADO si antes ha llegado a subir de verdad (``|pendiente| >
upper``). En la fase de base no aplica: la línea base es plana y solo debe
asentarse, sin subida previa.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ChannelState(str, Enum):
    """Estado de un canal (un sensor)."""

    SUBIENDO = "subiendo"
    ESTABILIZADO = "estabilizado"


class Policy(str, Enum):
    """Cómo se combinan los estados de los canales en una única decisión."""

    ALL = "all"  # estable solo si TODOS los canales están estabilizados
    ANY = "any"  # estable si CUALQUIER canal lo está
    MAJORITY = "majority"  # estable si lo está la mayoría


@dataclass
class ChannelResult:
    """Resultado del análisis de un canal en un instante dado."""

    slope: float | None  # pendiente en unidades/segundo; None si faltan datos
    state: ChannelState
    has_risen: bool = False


@dataclass
class AnalysisResult:
    """Resultado combinado de un ``update`` del analizador."""

    channels: dict[str, ChannelResult]
    stable: bool  # decisión combinada según la política multi-sensor
    # estado combinado nuevo si acaba de cambiar en este update; None si no hubo
    # transición. El Observer actúa SOLO cuando esto no es None.
    transition: ChannelState | None


def _slope_per_second(points: list[tuple[float, float]]) -> float | None:
    """Pendiente (unidades/segundo) por mínimos cuadrados.

    ``points`` son pares ``(t_segundos, valor)`` ya filtrados a la ventana. El
    tiempo se refiere internamente al primer punto para mantener la precisión.
    Devuelve None si no hay puntos suficientes o la recta es vertical.
    """
    n = len(points)
    if n < 2:
        return None

    t0 = points[0][0]
    xs = [t - t0 for t, _ in points]
    ys = [v for _, v in points]

    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xy = sum(x * y for x, y in zip(xs, ys))
    sum_x2 = sum(x * x for x in xs)

    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:  # todos los puntos en el mismo instante
        return None
    return (n * sum_xy - sum_x * sum_y) / denom


@dataclass
class _ChannelFSM:
    """Máquina de estados con histéresis y debounce para un solo canal."""

    state: ChannelState = ChannelState.SUBIENDO
    _candidate: ChannelState | None = None
    _candidate_since: float | None = None
    _has_risen: bool = False  # ¿este canal ha llegado a subir de verdad?

    def update(
        self,
        slope: float,
        now: float,
        lower: float,
        upper: float,
        confirm_seconds: float,
        require_rise: bool,
    ) -> None:
        """Actualiza el estado del canal a partir de la pendiente actual.

        ``now`` es el tiempo (segundos) de la última muestra, usado para el
        debounce. ``lower``/``upper`` son los límites de la banda muerta.
        ``require_rise``: si es True, no se confirma ESTABILIZADO hasta que el
        canal haya subido antes (evita el falso positivo de arranque en frío,
        cuando la medición empieza plana porque el olor aún no ha llegado).
        """
        magnitude = abs(slope)

        if magnitude > upper:
            self._has_risen = True

        if magnitude < lower:
            vote = ChannelState.ESTABILIZADO
        elif magnitude > upper:
            vote = ChannelState.SUBIENDO
        else:
            vote = None  # dentro de la banda muerta: no se propone cambio

        # latch: en medición no se confirma estabilización sin haber subido antes
        if vote is ChannelState.ESTABILIZADO and require_rise and not self._has_risen:
            vote = None

        # nada que confirmar si no hay voto o ya estamos en ese estado
        if vote is None or vote == self.state:
            self._candidate = None
            self._candidate_since = None
            return

        # arranca o mantiene el candidato a transición
        if self._candidate != vote:
            self._candidate = vote
            self._candidate_since = now

        # confirma solo si la condición se ha sostenido el tiempo mínimo
        if self._candidate_since is not None and now - self._candidate_since >= confirm_seconds:
            self.state = vote
            self._candidate = None
            self._candidate_since = None


@dataclass
class SignalAnalyzer:
    """Analiza N canales de forma independiente y combina su decisión.

    Es **stateful**: mantiene el estado de cada canal entre llamadas a
    ``update``. Llama a ``reset`` al empezar una fase nueva (p. ej. al pasar de
    base a medicion) para que la detección de estabilización vuelva a partir de
    ``SUBIENDO``.
    """

    window_seconds: float = 4.0
    slope_threshold: float = 7.5  # umbral central, pequeño positivo (u/s)
    hysteresis: float = 0.15  # ancho de banda muerta como fracción del umbral
    confirm_seconds: float = 1.0
    policy: Policy = Policy.ALL
    # ¿exigir que un canal suba antes de poder estabilizarse? True en medición
    # (rampa → meseta), False en base (señal plana que solo debe asentarse).
    require_rise: bool = True

    _channels: dict[str, _ChannelFSM] = field(default_factory=dict)
    _combined_state: ChannelState = ChannelState.SUBIENDO

    @property
    def lower(self) -> float:
        return self.slope_threshold * (1 - self.hysteresis)

    @property
    def upper(self) -> float:
        return self.slope_threshold * (1 + self.hysteresis)

    def reset(self, require_rise: bool = True) -> None:
        """Reinicia todos los canales y la decisión combinada a ``SUBIENDO``.

        ``require_rise`` fija el modo de la fase que empieza: True para medición
        (exige subida previa), False para base (la señal plana puede asentarse
        directamente).
        """
        self._channels.clear()
        self._combined_state = ChannelState.SUBIENDO
        self.require_rise = require_rise

    def update(self, samples: list[tuple[int, dict[str, float]]]) -> AnalysisResult:
        """Procesa una ventana de muestras y devuelve la decisión.

        ``samples`` es ``[(arduino_ms, {sensor: valor}), ...]`` ordenado por
        tiempo ascendente. Solo se usan las muestras dentro de los últimos
        ``window_seconds`` respecto a la más reciente.
        """
        if not samples:
            return AnalysisResult(channels={}, stable=False, transition=None)

        now = samples[-1][0] / 1000.0  # ms -> s
        window_start = now - self.window_seconds

        # puntos por canal dentro de la ventana temporal
        per_channel: dict[str, list[tuple[float, float]]] = {}
        for arduino_ms, values in samples:
            t = arduino_ms / 1000.0
            if t < window_start:
                continue
            for name, value in values.items():
                per_channel.setdefault(name, []).append((t, value))

        results: dict[str, ChannelResult] = {}
        for name, points in per_channel.items():
            fsm = self._channels.setdefault(name, _ChannelFSM())
            slope = _slope_per_second(points)
            if slope is not None:
                fsm.update(
                    slope, now, self.lower, self.upper,
                    self.confirm_seconds, self.require_rise,
                )
            results[name] = ChannelResult(slope=slope, state=fsm.state, has_risen=fsm._has_risen)

        stable = self._combine([r.state for r in results.values()])
        new_combined = ChannelState.ESTABILIZADO if stable else ChannelState.SUBIENDO

        transition = new_combined if new_combined != self._combined_state else None
        self._combined_state = new_combined

        return AnalysisResult(channels=results, stable=stable, transition=transition)

    def _combine(self, states: list[ChannelState]) -> bool:
        if not states:
            return False
        stable_flags = [s == ChannelState.ESTABILIZADO for s in states]
        if self.policy is Policy.ALL:
            return all(stable_flags)
        if self.policy is Policy.ANY:
            return any(stable_flags)
        if self.policy is Policy.MAJORITY:
            return sum(stable_flags) > len(stable_flags) / 2
        return False
