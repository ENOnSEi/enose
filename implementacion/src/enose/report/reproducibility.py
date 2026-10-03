"""
Métricas de reproducibilidad (Obstáculos de reproducibilidad, punto 8).

Unidad de "tanda": el Sample (todas sus reps se miden seguidas, el mismo día).
Cuando exista el concepto de sesión (punto 1) bastará con agrupar por sesión.

Respuesta por rep y sensor (escala provisional, sobre el ADC crudo, hasta que
el punto 3 dé la fórmula de Rs):
    R0    = mediana de la base estable (is_stable); si no hay, mitad final de la base
    Rs    = mediana de la medición estable; si no hay, mitad final de la medición
    delta = Rs − R0            (ADC)
    frac  = (Rs − R0) / R0     (adimensional, corrige en parte la deriva de R0)

Métricas por sustancia × sensor:
    cv_intra  : CV medio entre las reps de un mismo Sample (repetibilidad)
    cv_inter  : CV entre las medias de los Samples (reproducibilidad entre tandas)
    icc_batch : ICC(1) con grupo = Sample: fracción de la varianza que explica la
                tanda. Alto (>0.5) ⇒ las reps se parecen más a su tanda que a la
                sustancia: efecto tanda fuerte.
    trend_pct_per_rep : pendiente de la respuesta con el nº de rep, dentro de cada
                Sample, en % de la respuesta media por rep (deriva/saturación).
Y por sensor, el CV de R0 entre Samples (rep 1 de cada uno).
"""

from typing import Dict, Optional

import numpy as np
import pandas as pd

from enose.config import BASELINE_STATE, MEASUREMENT_STATE, SENSOR_COLUMNS, STATE_COLUMN

_EPS = 1e-9


def _stable_level(phase: pd.DataFrame, sensor: str) -> Optional[float]:
    if phase is None or phase.empty:
        return None
    if "is_stable" in phase.columns and phase["is_stable"].astype(bool).any():
        values = phase.loc[phase["is_stable"].astype(bool), sensor]
    else:
        values = phase[sensor].iloc[len(phase) // 2:]
    return float(np.median(values.to_numpy(dtype=float)))


def rep_responses(df: pd.DataFrame, sensor_cols=None) -> Dict[str, Dict[str, float]]:
    """{sensor: {r0, rs, delta, frac}} de una grabación; sensores sin base o
    medición se omiten."""
    if sensor_cols is None:
        sensor_cols = SENSOR_COLUMNS["sensors"]
    if STATE_COLUMN not in df.columns:
        return {}
    base = df[df[STATE_COLUMN] == BASELINE_STATE]
    med = df[df[STATE_COLUMN] == MEASUREMENT_STATE]
    out = {}
    for sensor in sensor_cols:
        if sensor not in df.columns:
            continue
        r0, rs = _stable_level(base, sensor), _stable_level(med, sensor)
        if r0 is None or rs is None:
            continue
        out[sensor] = {"r0": r0, "rs": rs, "delta": rs - r0,
                       "frac": (rs - r0) / r0 if abs(r0) > _EPS else np.nan}
    return out


def _cv(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    if len(values) < 2 or abs(values.mean()) < _EPS:
        return np.nan
    return float(values.std(ddof=1) / abs(values.mean()))


def icc1(values: np.ndarray, groups: np.ndarray) -> float:
    """ICC(1) de ANOVA de un factor con grupos de tamaño desigual."""
    df = pd.DataFrame({"v": values, "g": groups}).dropna()
    sizes = df.groupby("g")["v"].size()
    a, n = len(sizes), len(df)
    if a < 2 or n <= a:
        return np.nan
    grand = df["v"].mean()
    means = df.groupby("g")["v"].mean()
    ssb = float((sizes * (means - grand) ** 2).sum())
    ssw = float(((df["v"] - df["g"].map(means)) ** 2).sum())
    msb, msw = ssb / (a - 1), ssw / (n - a)
    k0 = (n - (sizes ** 2).sum() / n) / (a - 1)
    denom = msb + (k0 - 1) * msw
    return float((msb - msw) / denom) if denom > _EPS else np.nan


def _trend_pct(sub: pd.DataFrame, col: str) -> float:
    centered_v = sub[col] - sub.groupby("sample_id")[col].transform("mean")
    centered_r = sub["rep"] - sub.groupby("sample_id")["rep"].transform("mean")
    denom = float((centered_r ** 2).sum())
    mean = abs(float(sub[col].mean()))
    if denom < _EPS or mean < _EPS:
        return np.nan
    return float((centered_v * centered_r).sum() / denom / mean * 100)


def reproducibility_stats(responses: pd.DataFrame, value: str = "frac") -> pd.DataFrame:
    """``responses``: una fila por (ms, sensor) con columnas label, sample_id,
    rep, sensor y ``value``. Devuelve una fila por (label, sensor)."""
    rows = []
    for (label, sensor), sub in responses.dropna(subset=[value]).groupby(["label", "sensor"]):
        per_sample = sub.groupby("sample_id")[value]
        intra = [_cv(v.to_numpy()) for _, v in per_sample if len(v) >= 2]
        rows.append({
            "label": label,
            "sensor": sensor,
            "n_samples": int(per_sample.ngroups),
            "n_reps": int(len(sub)),
            "mean": float(sub[value].mean()),
            "cv_intra": float(np.nanmean(intra)) if intra and not np.all(np.isnan(intra)) else np.nan,
            "cv_inter": _cv(per_sample.mean().to_numpy()),
            "icc_batch": icc1(sub[value].to_numpy(), sub["sample_id"].to_numpy()),
            "trend_pct_per_rep": _trend_pct(sub, value),
        })
    return pd.DataFrame(rows)


def r0_stats(responses: pd.DataFrame) -> pd.DataFrame:
    """CV de R0 entre Samples por sensor, con la rep 1 de cada Sample (la que
    no viene precedida de un cooldown)."""
    first = responses[responses["rep"] == responses.groupby("sample_id")["rep"].transform("min")]
    rows = []
    for sensor, sub in first.groupby("sensor"):
        r0 = sub.groupby("sample_id")["r0"].mean().to_numpy()
        rows.append({"sensor": sensor, "n_samples": len(r0), "r0_mean": float(np.mean(r0)),
                     "r0_std": float(np.std(r0, ddof=1)) if len(r0) > 1 else np.nan,
                     "r0_cv": _cv(r0)})
    return pd.DataFrame(rows)
