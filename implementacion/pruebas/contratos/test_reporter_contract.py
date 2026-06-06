"""
Tests de contrato para ReportGeneratorProtocol (MarkdownReportGenerator).

Verifican que la implementación de la capa Dev cumple el protocolo definido en
spec/contracts/reporter.py y que el ExecutionReport ensamblado desde el estado
del trainer es válido y se materializa correctamente a disco.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from enose.report import MarkdownReportGenerator, build_execution_report
from spec.contracts.reporter import ReportGeneratorProtocol
from spec.schemas.execution_report import ExecutionReport, SplitSummary


@pytest.fixture
def fake_dataset():
    rng = np.random.default_rng(0)
    return pd.DataFrame({
        "Nombre_Archivo": [f"grab_{i}.csv" for i in range(6)],
        "Etiqueta": ["Agua", "Agua", "Vino", "Vino", "Alcohol", "Alcohol"],
        "v20_w0-5__t000": rng.random(6),
        "v20_w0-5__t001": rng.random(6),
    })


@pytest.fixture
def fake_results():
    y_test = np.array(["Agua", "Vino", "Alcohol"])
    y_pred = np.array(["Agua", "Vino", "Agua"])
    from sklearn.metrics import classification_report, confusion_matrix
    return {
        "best_params": {"svm__kernel": "rbf", "svm__C": 10},
        "cv_score": 0.82,
        "cv_scoring_metric": "balanced_accuracy",
        "train_accuracy": 0.95,
        "test_accuracy": 0.66,
        "test_balanced_accuracy": 0.66,
        "classification_report": classification_report(y_test, y_pred, output_dict=True, zero_division=0),
        "confusion_matrix": confusion_matrix(y_test, y_pred),
        "y_test": y_test,
        "y_pred": y_pred,
    }


@pytest.fixture
def report(fake_dataset, fake_results):
    return build_execution_report(
        df=fake_dataset,
        results=fake_results,
        feature_mode="pca_signal",
        n_groups=6,
        split=SplitSummary(n_train=3, n_test=3, n_test_groups=3, test_size_effective=0.5),
    )


class TestReporterContract:

    def test_implements_protocol(self):
        assert isinstance(MarkdownReportGenerator(), ReportGeneratorProtocol)

    def test_build_returns_valid_report(self, report):
        assert isinstance(report, ExecutionReport)
        assert report.dataset.n_samples == 6
        assert report.dataset.class_distribution == {"Agua": 2, "Alcohol": 2, "Vino": 2}
        assert report.conclusions  # debe derivar al menos una conclusión

    def test_generate_writes_artifacts(self, report, tmp_path):
        gen = MarkdownReportGenerator(reports_dir=tmp_path, source_viz_dir=tmp_path / "no_viz")
        md_path = gen.generate(report)

        assert md_path.exists() and md_path.name == "informe.md"
        assert (md_path.parent / "report.json").exists()
        content = md_path.read_text(encoding="utf-8")
        assert "Resumen ejecutivo" in content
        assert "Conclusiones" in content

    def test_overfitting_detected_in_conclusions(self, report):
        # train 0.95 vs test 0.66 -> gap 0.29 -> debe avisar de sobreajuste
        assert any("sobreajuste" in c.lower() for c in report.conclusions)
