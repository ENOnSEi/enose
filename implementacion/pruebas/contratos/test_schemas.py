"""
Tests de validación de schemas Pydantic.

Verifican que los schemas rechazan datos inválidos y aceptan datos correctos.
"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from spec.schemas.sensor_reading import SensorReading
from spec.schemas.feature_vector import FeatureVector
from spec.schemas.prediction import Prediction

SENSORS = ["v20", "v11", "v02", "v00"]
VALID_SENSOR_DATA = {s: [1.0, 2.0, 3.0] for s in SENSORS}


class TestSensorReadingSchema:

    def test_valid_reading(self):
        r = SensorReading(filename="vino.csv", substance_label="Vino", sensor_data=VALID_SENSOR_DATA)
        assert r.substance_label == "Vino"
        assert r.n_samples == 3

    def test_empty_label_raises(self):
        with pytest.raises(Exception):
            SensorReading(filename="x.csv", substance_label="   ", sensor_data=VALID_SENSOR_DATA)

    def test_missing_sensor_raises(self):
        incomplete = {k: [1.0] for k in SENSORS[:-1]}  # falta v00
        with pytest.raises(Exception):
            SensorReading(filename="x.csv", substance_label="Vino", sensor_data=incomplete)


class TestFeatureVectorSchema:

    def test_valid_vector(self):
        fv = FeatureVector(filename="vino.csv", substance_label="Vino",
                           features={"v20_w0-5_max": 0.5, "v20_w0-5_auc": 1.2})
        assert fv.n_features == 2

    def test_empty_features_raises(self):
        with pytest.raises(Exception):
            FeatureVector(filename="x.csv", substance_label="Vino", features={})

    def test_to_flat_record(self):
        fv = FeatureVector(filename="f.csv", substance_label="Agua", features={"feat_a": 0.1})
        record = fv.to_flat_record()
        assert record["Nombre_Archivo"] == "f.csv"
        assert record["Etiqueta"] == "Agua"
        assert record["feat_a"] == 0.1


class TestPredictionSchema:

    def test_valid_prediction(self):
        p = Prediction(filename="x.csv", predicted_class="Alcohol", confidence=0.95)
        assert p.predicted_class == "Alcohol"

    def test_empty_class_raises(self):
        with pytest.raises(Exception):
            Prediction(filename="x.csv", predicted_class="")

    def test_confidence_out_of_range_raises(self):
        with pytest.raises(Exception):
            Prediction(filename="x.csv", predicted_class="Vino", confidence=1.5)
