"""
Generador de informes de ejecución en Markdown.

Implementa ReportGeneratorProtocol (spec/contracts/reporter.py): a partir de un
ExecutionReport ya validado, materializa una carpeta autocontenida con timestamp:

    informes/informe_YYYY-MM-DD_HH-MM-SS/
      ├─ informe.md          ← informe legible (enlaza los PNG)
      ├─ report.json         ← volcado del ExecutionReport (comparación entre runs)
      └─ *.png               ← gráficos copiados de las visualizaciones del pipeline

Este es el único módulo de la capa Dev (enose) que importa la capa Spec en
runtime; ver design/adr/001-informe-automatico-de-ejecucion.md. Por eso añade
PROJECT_ROOT al sys.path, igual que hacen los tests, para poder importar `spec`.
"""

import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from enose.config import (
    DATA_PROCESSED_DIR, LABEL_COLUMN, NON_FEATURE_COLUMNS, PROJECT_ROOT, REPORTS_DIR, SENSOR_COLUMNS,
)
from enose.utils import create_output_directory, setup_logging

# El informe es la frontera Dev→Spec: la estructura validada es la fuente de verdad.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from spec.schemas.execution_report import (  # noqa: E402  (import tras ajustar sys.path)
    DatasetSummary, ExecutionReport, ModelResults, SplitSummary,
)

logger = setup_logging(__name__)

# PNGs que el pipeline deja en datos/procesados/visualizations/ y que el informe
# copia a su propia carpeta para ser autocontenido. (título, nombre de archivo).
PHASE4_IMAGES = [
    ("Distribución de clases", "class_distribution.png"),
    ("Estadísticas de características", "feature_statistics.png"),
]
PHASE5_IMAGES = [
    ("Matriz de confusión", "01_confusion_matrix.png"),
    ("Precisión: entrenamiento vs prueba", "02_accuracy_comparison.png"),
    ("Reporte de clasificación", "03_classification_report.png"),
    ("Distribución verdadero vs predicho", "04_distribution_comparison.png"),
]


# ===========================================================================
# Ensamblado del informe desde el estado del trainer
# ===========================================================================

def _git(*args: str) -> Optional[str]:
    """Ejecuta un comando git en PROJECT_ROOT; None si falla (repo ausente, etc.)."""
    try:
        out = subprocess.run(
            ["git", *args], cwd=PROJECT_ROOT,
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or None if out.returncode == 0 else None
    except Exception:
        return None


def _derive_conclusions(model: ModelResults) -> List[str]:
    """Conclusiones automáticas a partir de las métricas del modelo."""
    notes: List[str] = []

    gap = model.train_accuracy - model.test_accuracy
    if gap > 0.15:
        notes.append(
            f"Posible **sobreajuste**: la precisión de entrenamiento supera a la de "
            f"prueba en {gap*100:.1f} puntos. Considera regularizar (C más bajo) o "
            f"reducir la complejidad del modelo."
        )
    elif gap < 0.05:
        notes.append(
            f"**Buena generalización**: diferencia train−test de solo {gap*100:.1f} "
            f"puntos."
        )

    imbalance = abs(model.test_accuracy - model.test_balanced_accuracy)
    if imbalance > 0.10:
        notes.append(
            f"El **desbalanceo de clases** influye: accuracy ({model.test_accuracy*100:.1f}%) "
            f"y balanced accuracy ({model.test_balanced_accuracy*100:.1f}%) difieren en "
            f"{imbalance*100:.1f} puntos. Las métricas por clase son más fiables que la global."
        )

    # Clase mejor y peor por f1-score
    per_class = {
        k: v for k, v in model.classification_report.items()
        if isinstance(v, dict) and "f1-score" in v
        and k not in {"macro avg", "weighted avg"}
    }
    if per_class:
        best = max(per_class, key=lambda c: per_class[c]["f1-score"])
        worst = min(per_class, key=lambda c: per_class[c]["f1-score"])
        notes.append(
            f"Clase mejor clasificada: **{best}** (f1={per_class[best]['f1-score']:.2f}). "
            f"Clase más difícil: **{worst}** (f1={per_class[worst]['f1-score']:.2f})."
        )

    # Par más confundido (máximo fuera de la diagonal)
    cm = np.array(model.confusion_matrix)
    if cm.size and cm.shape[0] == cm.shape[1] and cm.shape[0] > 1:
        off = cm.copy()
        np.fill_diagonal(off, 0)
        if off.max() > 0:
            i, j = np.unravel_index(off.argmax(), off.shape)
            labels = model.class_labels
            notes.append(
                f"Confusión más frecuente: **{labels[i]} → {labels[j]}** "
                f"({off[i, j]} muestras de '{labels[i]}' predichas como '{labels[j]}')."
            )

    cv_gap = abs(model.cv_score - model.test_balanced_accuracy)
    if cv_gap > 0.15:
        notes.append(
            f"La validación cruzada ({model.cv_score*100:.1f}%) y el test "
            f"({model.test_balanced_accuracy*100:.1f}% balanced) difieren en "
            f"{cv_gap*100:.1f} puntos: el conjunto de test puede ser pequeño o poco "
            f"representativo. Interpreta los resultados con cautela."
        )

    return notes


def build_execution_report(
    df: pd.DataFrame,
    results: Dict,
    feature_mode: str,
    n_groups: int,
    split: Optional[SplitSummary] = None,
) -> ExecutionReport:
    """
    Ensambla un ExecutionReport validado a partir del estado del ModelTrainer.

    Parámetros
    ----------
    df           : dataset maestro cargado (para el resumen de Fase 4)
    results      : ModelTrainer.results (métricas y matriz de confusión)
    feature_mode : 'handcrafted' | 'pca_signal'
    n_groups     : nº de vinos-lote distintos
    split        : resumen de la división train/test (opcional)
    """
    label_col = LABEL_COLUMN if LABEL_COLUMN in df.columns else None
    class_dist = (
        {str(k): int(v) for k, v in df[label_col].value_counts().sort_index().items()}
        if label_col else {}
    )
    n_features = len([c for c in df.columns if c not in NON_FEATURE_COLUMNS])

    y_test = np.asarray(results["y_test"])
    y_pred = np.asarray(results["y_pred"])
    class_labels = [str(c) for c in np.unique(np.concatenate([y_test, y_pred]))]
    cm = np.asarray(results["confusion_matrix"]).astype(int).tolist()

    model = ModelResults(
        best_params={str(k): v for k, v in results["best_params"].items()},
        cv_score=float(results["cv_score"]),
        cv_scoring_metric=str(results["cv_scoring_metric"]),
        train_accuracy=float(results["train_accuracy"]),
        test_accuracy=float(results["test_accuracy"]),
        test_balanced_accuracy=float(results["test_balanced_accuracy"]),
        classification_report=results["classification_report"],
        confusion_matrix=cm,
        class_labels=class_labels,
    )

    dataset = DatasetSummary(
        feature_mode=feature_mode,
        n_samples=int(df.shape[0]),
        n_features=n_features,
        n_groups=int(n_groups),
        class_distribution=class_dist,
        sensors=list(SENSOR_COLUMNS["sensors"]),
    )

    return ExecutionReport(
        timestamp=datetime.now(),
        git_commit=_git("rev-parse", "--short", "HEAD"),
        git_branch=_git("rev-parse", "--abbrev-ref", "HEAD"),
        dataset=dataset,
        split=split,
        model=model,
        conclusions=_derive_conclusions(model),
    )


# ===========================================================================
# Generador Markdown (implementa ReportGeneratorProtocol)
# ===========================================================================

class MarkdownReportGenerator:
    """
    Genera un informe Markdown autocontenido por ejecución.

    Conforme a ReportGeneratorProtocol — sustituible por un generador HTML/PDF
    que implemente el mismo `generate(report) -> Path` sin tocar el trainer.
    """

    def __init__(
        self,
        reports_dir: Path = REPORTS_DIR,
        source_viz_dir: Path = DATA_PROCESSED_DIR / "visualizations",
    ) -> None:
        self.reports_dir = Path(reports_dir)
        self.source_viz_dir = Path(source_viz_dir)

    def generate(self, report: ExecutionReport) -> Path:
        out_dir = create_output_directory(self.reports_dir / report.slug)

        copied = self._copy_images(out_dir)
        (out_dir / "report.json").write_text(
            report.model_dump_json(indent=2), encoding="utf-8"
        )
        md_path = out_dir / "informe.md"
        md_path.write_text(self._render_markdown(report, copied), encoding="utf-8")

        logger.info(f"Informe generado en: {md_path}")
        return md_path

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _copy_images(self, out_dir: Path) -> Dict[str, str]:
        """Copia los PNG existentes del pipeline a la carpeta del informe."""
        copied: Dict[str, str] = {}
        for _, filename in PHASE4_IMAGES + PHASE5_IMAGES:
            src = self.source_viz_dir / filename
            if src.exists():
                shutil.copy2(src, out_dir / filename)
                copied[filename] = filename
        return copied

    @staticmethod
    def _image_section(title: str, images: List, copied: Dict[str, str]) -> List[str]:
        lines: List[str] = []
        for caption, filename in images:
            if filename in copied:
                lines.append(f"**{caption}**\n")
                lines.append(f"![{caption}]({filename})\n")
        return lines

    def _render_markdown(self, report: ExecutionReport, copied: Dict[str, str]) -> str:
        m = report.model
        d = report.dataset
        L: List[str] = []

        # --- Cabecera + metadata ---
        L.append(f"# Informe de ejecución — {report.timestamp:%Y-%m-%d %H:%M:%S}\n")
        L.append("## Metadata\n")
        L.append("| Campo | Valor |")
        L.append("|-------|-------|")
        L.append(f"| Fecha | {report.timestamp:%Y-%m-%d %H:%M:%S} |")
        L.append(f"| Commit | `{report.git_commit or 'N/D'}` |")
        L.append(f"| Rama | `{report.git_branch or 'N/D'}` |")
        L.append(f"| Modo de features | `{d.feature_mode}` |")
        L.append("")

        # --- Resumen ejecutivo ---
        L.append("## Resumen ejecutivo\n")
        L.append("| Métrica | Valor |")
        L.append("|---------|-------|")
        L.append(f"| Accuracy (test) | **{m.test_accuracy*100:.2f}%** |")
        L.append(f"| Balanced accuracy (test) | **{m.test_balanced_accuracy*100:.2f}%** |")
        L.append(f"| Accuracy (train) | {m.train_accuracy*100:.2f}% |")
        L.append(f"| CV score ({m.cv_scoring_metric}) | {m.cv_score*100:.2f}% |")
        L.append(f"| Gap train−test | {report.overfitting_gap*100:.2f} pts |")
        L.append("")

        # --- Fase 4: dataset ---
        L.append("## Fase 4 — Dataset\n")
        L.append(f"- Muestras: **{d.n_samples}**")
        L.append(f"- Características: **{d.n_features}**")
        L.append(f"- Grupos (grabación): **{d.n_groups}**")
        L.append(f"- Sensores: {', '.join(d.sensors)}")
        L.append("")
        if d.class_distribution:
            L.append("Distribución de clases:\n")
            L.append("| Clase | Muestras | % |")
            L.append("|-------|----------|---|")
            total = sum(d.class_distribution.values()) or 1
            for cls, n in d.class_distribution.items():
                L.append(f"| {cls} | {n} | {n/total*100:.1f}% |")
            L.append("")
        L.extend(self._image_section("Fase 4", PHASE4_IMAGES, copied))

        # --- División de datos ---
        if report.split:
            s = report.split
            L.append("## División de datos (por grupos)\n")
            L.append(f"- Train: **{s.n_train}** muestras")
            L.append(f"- Test: **{s.n_test}** muestras (~{s.test_size_effective*100:.0f}%)")
            L.append(f"- Grabaciones en test (disjuntas de train): **{s.n_test_groups}**")
            L.append("")

        # --- Fase 5: modelo ---
        L.append("## Fase 5 — Modelo\n")
        L.append("Mejores hiperparámetros:\n")
        L.append("```")
        for k, v in m.best_params.items():
            L.append(f"{k} = {v}")
        L.append("```\n")

        L.append("Reporte de clasificación por clase:\n")
        L.append("| Clase | Precision | Recall | F1-score | Soporte |")
        L.append("|-------|-----------|--------|----------|---------|")
        for cls in m.class_labels:
            row = m.classification_report.get(cls)
            if isinstance(row, dict):
                L.append(
                    f"| {cls} | {row.get('precision', 0):.2f} | {row.get('recall', 0):.2f} | "
                    f"{row.get('f1-score', 0):.2f} | {int(row.get('support', 0))} |"
                )
        L.append("")

        # Matriz de confusión como tabla
        L.append("Matriz de confusión (filas = verdadero, columnas = predicho):\n")
        header = "| V\\P | " + " | ".join(m.class_labels) + " |"
        L.append(header)
        L.append("|" + "---|" * (len(m.class_labels) + 1))
        for label, row in zip(m.class_labels, m.confusion_matrix):
            L.append(f"| **{label}** | " + " | ".join(str(v) for v in row) + " |")
        L.append("")
        L.extend(self._image_section("Fase 5", PHASE5_IMAGES, copied))

        # --- Conclusiones ---
        L.append("## Conclusiones automáticas\n")
        if report.conclusions:
            for note in report.conclusions:
                L.append(f"- {note}")
        else:
            L.append("- Sin observaciones automáticas destacables.")
        L.append("")

        L.append("---")
        L.append("_Generado automáticamente por `enose.report` · "
                 "ver `report.json` para los datos completos._")
        return "\n".join(L) + "\n"
