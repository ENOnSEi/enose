"""
Test de confusión con el tiempo (enose.model.confounder).

Si cada sustancia se mide en su propio "día" (offset de base común a sus
Samples), la base predice la sustancia → el test debe detectarlo. Si los
offsets son independientes de la sustancia, no debe dar falso positivo.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from enose.model.confounder import baseline_features, confounder_test, permute_by_group


def _dataset(confounded: bool, n_classes=3, samples_per_class=4, reps=3, n_features=6, seed=0):
    rng = np.random.default_rng(seed)
    day = {c: rng.normal(0, 3.0, n_features) for c in range(n_classes)}
    X, y, g = [], [], []
    sid = 0
    for c in range(n_classes):
        for _ in range(samples_per_class):
            sid += 1
            offset = day[c] if confounded else rng.normal(0, 3.0, n_features)
            for _ in range(reps):
                X.append(offset + rng.normal(0, 0.3, n_features))
                y.append(f"c{c}")
                g.append(f"sample_{sid}")
    return np.array(X), np.array(y), np.array(g)


def test_detecta_confusion():
    res = confounder_test(*_dataset(confounded=True), n_permutations=50, n_repeats=1)
    assert res.confounded
    assert res.score > res.perm_p95


def test_sin_confusion_no_da_falso_positivo():
    res = confounder_test(*_dataset(confounded=False), n_permutations=50, n_repeats=1)
    assert not res.confounded


def test_permutacion_respeta_grupos():
    X, y, g = _dataset(confounded=True)
    yp = permute_by_group(y, g, np.random.default_rng(1))
    # cada grupo mantiene una sola etiqueta y el nº de grupos por clase se conserva
    df = pd.DataFrame({"y": yp, "g": g})
    assert (df.groupby("g")["y"].nunique() == 1).all()
    orig = pd.DataFrame({"y": y, "g": g}).drop_duplicates("g")["y"].value_counts().sort_index()
    assert df.drop_duplicates("g")["y"].value_counts().sort_index().equals(orig)


def test_baseline_features_usa_solo_fase_base():
    t = np.arange(20) * 200
    df = pd.DataFrame({
        "data": t,
        "v20": [100 + i for i in range(10)] + [999] * 10,
        "v11": 50, "v02": 50, "v00": 50,
        "estado": ["base"] * 10 + ["medicion"] * 10,
    })
    f = baseline_features(df)
    assert f["v20_base_median"] == 104.5
    assert np.isclose(f["v20_base_slope"], 5.0)   # 1 u por lectura a 5 Hz
    assert f["v11_base_std"] == 0.0


def test_baseline_features_sin_base():
    df = pd.DataFrame({"data": [0, 200], "v20": [1, 2], "v11": 1, "v02": 1, "v00": 1,
                       "estado": ["medicion", "medicion"]})
    assert baseline_features(df) is None
