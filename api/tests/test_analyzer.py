"""Tests del SignalAnalyzer. Ejecutable sin pytest:

    uv run python tests/test_analyzer.py

Cubre: cálculo de pendiente, estabilidad numérica, histéresis, debounce y
política multi-sensor.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.analyzer import (  # noqa: E402
    ChannelState,
    Policy,
    SignalAnalyzer,
    _ChannelFSM,
    _slope_per_second,
)

PASSED = 0


def check(cond: bool, msg: str) -> None:
    global PASSED
    assert cond, f"FALLO: {msg}"
    PASSED += 1


# --- pendiente -------------------------------------------------------------

def test_slope_lineal():
    # y = 10 + 2t  → pendiente 2.0/s
    points = [(float(t), 10 + 2 * t) for t in range(5)]
    check(abs(_slope_per_second(points) - 2.0) < 1e-9, "pendiente lineal = 2.0")


def test_slope_numerica_con_ms_grandes():
    # Timestamps tipo millis() grandes (en segundos): la referencia a t0 debe
    # mantener la precisión. y = 5*t + 100.
    base = 3_600_000 / 1000.0  # 1h de uptime, en segundos
    points = [(base + t * 0.25, 5 * (base + t * 0.25) + 100) for t in range(16)]
    check(abs(_slope_per_second(points) - 5.0) < 1e-6, "pendiente estable con t grande")


def test_slope_insuficiente():
    check(_slope_per_second([(0.0, 1.0)]) is None, "1 punto → None")


# --- FSM: histéresis + debounce -------------------------------------------

def test_debounce_no_dispara_con_cruce_puntual():
    fsm = _ChannelFSM()  # arranca SUBIENDO
    # pendiente baja un instante (0.5s < confirm 1.0s) y vuelve a subir.
    # require_rise=False (modo base) para aislar el debounce del latch.
    fsm.update(slope=1.0, now=0.0, lower=17, upper=23, confirm_seconds=1.0, require_rise=False)
    fsm.update(slope=1.0, now=0.5, lower=17, upper=23, confirm_seconds=1.0, require_rise=False)
    fsm.update(slope=50.0, now=0.6, lower=17, upper=23, confirm_seconds=1.0, require_rise=False)
    check(fsm.state is ChannelState.SUBIENDO, "cruce puntual no confirma")


def test_debounce_confirma_si_sostenido():
    fsm = _ChannelFSM()
    fsm.update(slope=1.0, now=0.0, lower=17, upper=23, confirm_seconds=1.0, require_rise=False)
    fsm.update(slope=1.0, now=1.0, lower=17, upper=23, confirm_seconds=1.0, require_rise=False)
    check(fsm.state is ChannelState.ESTABILIZADO, "condición sostenida 1s confirma")


def test_histeresis_banda_muerta():
    fsm = _ChannelFSM(state=ChannelState.ESTABILIZADO)
    # pendiente 20 cae dentro de [17,23] → no debe volver a SUBIENDO
    fsm.update(slope=20.0, now=0.0, lower=17, upper=23, confirm_seconds=1.0, require_rise=False)
    fsm.update(slope=20.0, now=2.0, lower=17, upper=23, confirm_seconds=1.0, require_rise=False)
    check(fsm.state is ChannelState.ESTABILIZADO, "banda muerta evita chattering")


def test_latch_arranque_plano_no_estabiliza():
    # require_rise=True y la señal nunca sube → no debe confirmar ESTABILIZADO
    fsm = _ChannelFSM()
    fsm.update(slope=1.0, now=0.0, lower=17, upper=23, confirm_seconds=1.0, require_rise=True)
    fsm.update(slope=1.0, now=2.0, lower=17, upper=23, confirm_seconds=1.0, require_rise=True)
    check(fsm.state is ChannelState.SUBIENDO, "sin subida previa no se estabiliza (latch)")


def test_latch_sube_luego_estabiliza():
    # primero sube (latch satisfecho), luego se aplana → sí estabiliza
    fsm = _ChannelFSM()
    fsm.update(slope=50.0, now=0.0, lower=17, upper=23, confirm_seconds=1.0, require_rise=True)
    fsm.update(slope=1.0, now=1.0, lower=17, upper=23, confirm_seconds=1.0, require_rise=True)
    fsm.update(slope=1.0, now=2.0, lower=17, upper=23, confirm_seconds=1.0, require_rise=True)
    check(fsm.state is ChannelState.ESTABILIZADO, "subida + meseta sostenida estabiliza")


# --- analizador completo ---------------------------------------------------

def _feed_signal(analyzer: SignalAnalyzer, value_fn, t_end=14.0, dt=0.25):
    """Simula un stream a 1/dt Hz alimentando ventanas sucesivas."""
    full = []
    last = None
    t = 0.0
    while t <= t_end:
        ms = int(t * 1000)
        full.append((ms, {"s1": value_fn(t)}))
        last = analyzer.update(full)
        t += dt
    return last


def test_senal_que_sube_no_estabiliza():
    analyzer = SignalAnalyzer()  # threshold 20, lower 17, upper 23
    result = _feed_signal(analyzer, lambda t: 100 + 50 * t, t_end=8.0)
    check(not result.stable, "señal en rampa nunca estabiliza")
    check(result.channels["s1"].state is ChannelState.SUBIENDO, "estado = SUBIENDO")


def test_senal_que_se_aplana_estabiliza():
    analyzer = SignalAnalyzer()
    # sube hasta t=5, luego plana
    result = _feed_signal(analyzer, lambda t: 100 + 50 * t if t < 5 else 350.0)
    check(result.stable, "señal que se aplana acaba estable")
    check(result.transition is None, "sin transición en el último update (ya estable)")


def test_politica_multisensor_all():
    analyzer = SignalAnalyzer(policy=Policy.ALL)
    full = []
    last = None
    t = 0.0
    while t <= 14.0:
        ms = int(t * 1000)
        # s1 sube y se aplana; s2 sigue subiendo indefinidamente
        s1 = 100 + 50 * t if t < 5 else 350.0
        full.append((ms, {"s1": s1, "s2": 100 + 50 * t}))
        last = analyzer.update(full)
        t += 0.25
    check(not last.stable, "ALL: un sensor inestable mantiene el conjunto inestable")
    check(last.channels["s1"].state is ChannelState.ESTABILIZADO, "s1 estabilizado")
    check(last.channels["s2"].state is ChannelState.SUBIENDO, "s2 subiendo")


def test_latch_medicion_arranque_plano_no_estabiliza():
    # medición que arranca plana y NO sube (require_rise=True por defecto):
    # no debe estabilizarse (replica el bug de arranque en frío ya corregido)
    analyzer = SignalAnalyzer()
    result = _feed_signal(analyzer, lambda t: 300.0, t_end=10.0)
    check(not result.stable, "medición plana sin subida no estabiliza (latch)")


def test_base_plana_si_estabiliza():
    # en modo base (require_rise=False) una señal plana SÍ debe asentarse
    analyzer = SignalAnalyzer()
    analyzer.reset(require_rise=False)
    result = _feed_signal(analyzer, lambda t: 300.0, t_end=10.0)
    check(result.stable, "base plana se asienta (sin exigir subida)")


def test_emite_transicion_una_sola_vez():
    analyzer = SignalAnalyzer()
    full = []
    transitions = []
    t = 0.0
    while t <= 14.0:
        ms = int(t * 1000)
        full.append((ms, {"s1": 100 + 50 * t if t < 5 else 350.0}))
        r = analyzer.update(full)
        if r.transition is not None:
            transitions.append((round(t, 2), r.transition))
        t += 0.25
    check(len(transitions) == 1, f"exactamente 1 transición (fueron {transitions})")
    check(transitions[0][1] is ChannelState.ESTABILIZADO, "la transición es a ESTABILIZADO")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ok  {name}")
    print(f"\n{PASSED} comprobaciones OK")
