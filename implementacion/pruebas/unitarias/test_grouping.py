"""
Agrupación para la validación cruzada (config.GROUP_BY).

Las reps de un mismo Sample comparten día, deriva y humedad. Si se reparten
entre train y test, el modelo puede acertar reconociendo "la tanda" en vez de
"la sustancia". Estos tests comprueban que con GROUP_BY='sample' eso no ocurre.
"""

import dataclasses
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from enose.config import FILENAME_COLUMN, GROUP_COLUMN, LABEL_COLUMN
from enose.model import trainer as trainer_mod
from enose.model.trainer import ModelTrainer
from enose.pipeline.dataset import derive_groups


def _synthetic_dataset(n_classes=3, samples_per_class=4, reps=3, n_features=12, seed=0):
    """Dataset SIN señal de clase: cada Sample tiene un offset propio grande
    (efecto tanda) y sus reps solo añaden ruido pequeño. Cualquier acierto por
    encima del azar solo puede venir de reconocer la tanda."""
    rng = np.random.default_rng(seed)
    rows = []
    sample_id = 0
    for c in range(n_classes):
        for _ in range(samples_per_class):
            sample_id += 1
            offset = rng.normal(0, 3.0, n_features)
            for rep in range(1, reps + 1):
                feats = offset + rng.normal(0, 0.1, n_features)
                rows.append({
                    FILENAME_COLUMN: f"clase{c}_rep{rep}_ms{sample_id * 10 + rep}",
                    LABEL_COLUMN: f"clase{c}",
                    GROUP_COLUMN: f"sample_{sample_id}",
                    **{f"f{i}": v for i, v in enumerate(feats)},
                })
    return pd.DataFrame(rows)


def _prepared_trainer(tmp_path, df, monkeypatch, group_by):
    monkeypatch.setattr(trainer_mod, "GROUP_BY", group_by)
    # sin procesos paralelos: en Windows arrancarlos cuesta más que el ajuste
    monkeypatch.setattr(trainer_mod, "ML_CONFIG",
                        dataclasses.replace(trainer_mod.ML_CONFIG, n_jobs=1, verbose=0))
    path = tmp_path / "dataset.csv"
    df.to_csv(path, index=False)
    t = ModelTrainer(dataset_path=path)
    assert t.load_and_validate_data()
    assert t.prepare_features()
    return t


# ---------------------------------------------------------------------------
# derive_groups
# ---------------------------------------------------------------------------

def test_sample_mode_uses_group_column():
    df = pd.DataFrame({
        FILENAME_COLUMN: ["a_rep1_ms1", "a_rep2_ms2", "b_rep1_ms3"],
        GROUP_COLUMN: ["sample_1", "sample_1", "sample_2"],
    })
    assert list(derive_groups(df, "sample")) == ["sample_1", "sample_1", "sample_2"]


def test_recording_mode_ignores_group_column():
    df = pd.DataFrame({
        FILENAME_COLUMN: ["a_rep1_ms1", "a_rep2_ms2"],
        GROUP_COLUMN: ["sample_1", "sample_1"],
    })
    assert list(derive_groups(df, "recording")) == ["a_rep1_ms1", "a_rep2_ms2"]


def test_sample_mode_falls_back_to_recording_for_legacy_csv():
    # dataset de CSVs legacy: sin columna Grupo, con ventanas '#wNN'
    df = pd.DataFrame({FILENAME_COLUMN: ["vino.csv#w00", "vino.csv#w01", "agua.csv#w00"]})
    assert list(derive_groups(df, "sample")) == ["vino.csv", "vino.csv", "agua.csv"]


def test_unknown_group_by_raises():
    with pytest.raises(ValueError):
        derive_groups(pd.DataFrame({FILENAME_COLUMN: ["x"]}), "session")


def test_group_column_is_not_a_feature(tmp_path, monkeypatch):
    t = _prepared_trainer(tmp_path, _synthetic_dataset(), monkeypatch, "sample")
    assert GROUP_COLUMN not in t.X.columns
    assert FILENAME_COLUMN not in t.X.columns


# ---------------------------------------------------------------------------
# ModelTrainer
# ---------------------------------------------------------------------------

def test_split_keeps_reps_of_a_sample_together(tmp_path, monkeypatch):
    t = _prepared_trainer(tmp_path, _synthetic_dataset(), monkeypatch, "sample")
    assert t.n_groups == 12
    assert t.split_data()
    train_groups = set(t.groups_train)
    test_groups = set(t.df.loc[t.X_test.index, GROUP_COLUMN])
    assert train_groups.isdisjoint(test_groups)


def test_grouped_cv_is_not_fooled_by_batch_effect(tmp_path, monkeypatch):
    """Sin señal de clase, agrupar por Sample debe dar ~azar; mezclar reps debe
    dar una accuracy alta y falsa. Es exactamente la fuga que se corrige."""
    t = _prepared_trainer(tmp_path, _synthetic_dataset(), monkeypatch, "sample")
    assert t.split_data()
    assert t.build_pipeline()
    assert t.optimize_hyperparameters()

    cmp = t._grouping_comparison()
    chance = 1 / 3
    assert cmp["cv_score_grouped"] < chance + 0.25
    assert cmp["cv_inflation"] > 0.25


def test_single_sample_per_class_fails_cleanly(tmp_path, monkeypatch):
    df = _synthetic_dataset(samples_per_class=1)
    t = _prepared_trainer(tmp_path, df, monkeypatch, "sample")
    assert not t.split_data()


def test_recording_mode_reproduces_old_behaviour(tmp_path, monkeypatch):
    df = _synthetic_dataset(samples_per_class=1)
    t = _prepared_trainer(tmp_path, df, monkeypatch, "recording")
    assert t.n_groups == len(df)
    assert t.split_data()
