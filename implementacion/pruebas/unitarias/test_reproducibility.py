"""
Métricas de reproducibilidad (enose.report.reproducibility).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from enose.report.reproducibility import icc1, r0_stats, rep_responses, reproducibility_stats


def _recording(r0, rs, n=10):
    return pd.DataFrame({
        "data": np.arange(2 * n) * 200,
        "v20": [r0] * n + [rs] * n, "v11": [r0] * n + [rs] * n,
        "v02": [r0] * n + [rs] * n, "v00": [r0] * n + [rs] * n,
        "estado": ["base"] * n + ["medicion"] * n,
        "is_stable": True,
    })


def test_rep_responses_usa_lecturas_estables():
    df = _recording(1000, 1200)
    df.loc[10:13, "is_stable"] = False          # transitorio de subida, se ignora
    df.loc[10:13, "v20"] = 5000
    r = rep_responses(df)["v20"]
    assert r["r0"] == 1000 and r["rs"] == 1200
    assert r["delta"] == 200 and np.isclose(r["frac"], 0.2)


def test_rep_responses_sin_estables_usa_mitad_final():
    df = _recording(1000, 1200)
    df["is_stable"] = False
    df.loc[10:14, "v20"] = 0                    # primera mitad de la medición
    assert rep_responses(df)["v20"]["rs"] == 1200


def test_icc_extremos():
    groups = np.repeat([1, 2, 3, 4], 5)
    # todo es tanda: dentro de cada grupo los valores son casi idénticos
    batch = np.repeat([1.0, 5.0, 9.0, 13.0], 5) + np.random.default_rng(0).normal(0, 0.01, 20)
    assert icc1(batch, groups) > 0.95
    # sin efecto tanda: misma distribución en todos los grupos
    noise = np.random.default_rng(1).normal(0, 1, 2000)
    assert abs(icc1(noise, np.repeat(np.arange(400), 5))) < 0.1


def _responses(batch_sd, rep_sd=0.01, drift=0.0, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for sid in range(1, 5):
        offset = rng.normal(0, batch_sd)
        for rep in range(1, 6):
            rows.append({"label": "vino", "sensor": "v20", "sample_id": sid, "rep": rep,
                         "r0": 1000 + 50 * sid, "frac": 0.2 + offset + drift * rep + rng.normal(0, rep_sd)})
    return pd.DataFrame(rows)


def test_stats_detecta_efecto_tanda():
    s = reproducibility_stats(_responses(batch_sd=0.05)).iloc[0]
    assert s["n_samples"] == 4 and s["n_reps"] == 20
    assert s["cv_inter"] > 3 * s["cv_intra"]
    assert s["icc_batch"] > 0.8


def test_stats_tendencia_por_rep():
    s = reproducibility_stats(_responses(batch_sd=0.0, rep_sd=0.0, drift=0.01)).iloc[0]
    mean = 0.2 + 0.01 * 3
    assert np.isclose(s["trend_pct_per_rep"], 0.01 / mean * 100)


def test_r0_stats_usa_rep_1():
    r = r0_stats(_responses(batch_sd=0.0)).iloc[0]
    assert r["n_samples"] == 4 and np.isclose(r["r0_mean"], 1125)
    assert r["r0_cv"] > 0
