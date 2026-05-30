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

SENSORS = ["MQ3_1", "MQ4_1", "MQ6_1", "MQ3_2", "MQ4_2", "MQ6_2"]
VALID_SENSOR_DATA = {s: [1.0, 2.0, 3.0] for s in SENSORS}


class TestSensorReadingSchema:

    def test_valid_reading(self):
        r = SensorReading(filename="AQ_Wine01.txt", substance_label="AQ", sensor_data=VALID_SENSOR_DATA)
        assert r.substance_label == "AQ"
        assert r.n_samples == 3

    def test_invalid_label_raises(self):
        with pytest.raises(Exception):
            SensorReading(filename="x.txt", substance_label="INVALID", sensor_data=VALID_SENSOR_DATA)

    def test_missing_sensor_raises(self):
        incomplete = {k: [1.0] for k in SENSORS[:-1]}  # falta MQ6_2
        with pytest.raises(Exception):
            SensorReading(filename="x.txt", substance_label="HQ", sensor_data=incomplete)


class TestFeatureVectorSchema:

    def test_valid_vector(self):
        fv = FeatureVector(filename="AQ_Wine01.txt", substance_label="AQ",
                           features={"MQ3_1_w0-2_max": 0.5, "MQ3_1_w0-2_auc": 1.2})
        assert fv.n_features == 2

    def test_empty_features_raises(self):
        with pytest.raises(Exception):
            FeatureVector(filename="x.txt", substance_label="AQ", features={})

    def test_to_flat_record(self):
        fv = FeatureVector(filename="f.txt", substance_label="HQ", features={"feat_a": 0.1})
        record = fv.to_flat_record()
        assert record["Nombre_Archivo"] == "f.txt"
        assert record["feat_a"] == 0.1


class TestPredictionSchema:

    def test_valid_prediction(self):
        p = Prediction(filename="x.txt", predicted_class="ETH", confidence=0.95)
        assert p.predicted_class == "ETH"

    def test_invalid_class_raises(self):
        with pytest.raises(Exception):
            Prediction(filename="x.txt", predicted_class="UNKNOWN")

    def test_confidence_out_of_range_raises(self):
        with pytest.raises(Exception):
            Prediction(filename="x.txt", predicted_class="AQ", confidence=1.5)
