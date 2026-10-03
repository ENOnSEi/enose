"""
Ficha del modelo (enose.model.model_card): se escribe al guardar el modelo y
predict_from_api.py la usa para avisar de incompatibilidades.
"""

import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from enose.model import model_card as mc
from enose.model import trainer as trainer_mod
from enose.model.trainer import ModelTrainer

sys.path.insert(0, str(Path(__file__).parent))
from test_grouping import _synthetic_dataset  # noqa: E402


def _trained(tmp_path, monkeypatch):
    monkeypatch.setattr(trainer_mod, "ML_CONFIG",
                        dataclasses.replace(trainer_mod.ML_CONFIG, n_jobs=1, verbose=0))
    path = tmp_path / "dataset.csv"
    _synthetic_dataset().to_csv(path, index=False)
    t = ModelTrainer(dataset_path=path)
    t._generate_visualizations = lambda *a, **k: None   # no escribir PNG en datos/procesados
    for step in (t.load_and_validate_data, t.prepare_features, t.split_data,
                 t.build_pipeline, t.optimize_hyperparameters, t.evaluate_model):
        assert step()
    out = tmp_path / "model"
    assert t.save_model(out)
    return t, out / "best_model.pkl"


def test_save_model_writes_card(tmp_path, monkeypatch):
    t, model_path = _trained(tmp_path, monkeypatch)
    card = json.loads(mc.card_path_for(model_path).read_text(encoding="utf-8"))
    assert card["dataset"]["n_rows"] == len(t.df)
    assert card["dataset"]["sha256"] and len(card["dataset"]["sha256"]) == 64
    assert card["dataset"]["ms_ids"]                       # sacados de "_ms<id>" en Nombre_Archivo
    assert card["features"]["names"] == list(t.X.columns)
    assert "Grupo" not in card["features"]["names"]
    assert card["training"]["group_by"] == trainer_mod.GROUP_BY
    assert "cv_score_grouped" in card["metrics"]
    assert mc.check_model_card(model_path, t.grid_search.best_estimator_) == []
    assert "agrupado" in mc.describe_model_card(model_path)


def test_warns_when_feature_config_changed(tmp_path, monkeypatch):
    t, model_path = _trained(tmp_path, monkeypatch)
    card_file = mc.card_path_for(model_path)
    card = json.loads(card_file.read_text(encoding="utf-8"))
    card["features"]["config"]["signal"]["sampling_frequency"] = 5.0
    card_file.write_text(json.dumps(card), encoding="utf-8")
    warnings = mc.check_model_card(model_path)
    assert len(warnings) == 1 and "signal" in warnings[0]


def test_warns_when_card_missing(tmp_path):
    warnings = mc.check_model_card(tmp_path / "best_model.pkl")
    assert len(warnings) == 1 and "model_card.json" in warnings[0]
    assert mc.describe_model_card(tmp_path / "best_model.pkl") is None
