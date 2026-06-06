"""Utilidades compartidas: logging, validación de datos y visualización."""

import logging
from pathlib import Path
from typing import List, Optional, Union

import numpy as np
import pandas as pd

from enose.config import LABEL_COLUMN, LOGGING_CONFIG, SENSOR_COLUMNS


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(name: str = __name__) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(LOGGING_CONFIG.level)
        fmt = logging.Formatter(LOGGING_CONFIG.format)

        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(ch)

        try:
            fh = logging.FileHandler(LOGGING_CONFIG.log_file, encoding="utf-8")
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        except Exception as e:
            logger.warning(f"No se pudo crear archivo de log: {e}")

    return logger


# ---------------------------------------------------------------------------
# Validación de datos
# ---------------------------------------------------------------------------

def validate_sensor_data(df: pd.DataFrame) -> tuple[bool, List[str]]:
    issues = []
    required = list(SENSOR_COLUMNS["sensors"])

    missing = [c for c in required if c not in df.columns]
    if missing:
        issues.append(f"Faltan columnas: {missing}")

    for col in required:
        if col not in df.columns:
            continue
        if not np.issubdtype(df[col].dtype, np.number):
            issues.append(f"{col} no es numérica")
        if df[col].isnull().any():
            issues.append(f"{col} tiene NaN")
        if np.isinf(df[col]).any():
            issues.append(f"{col} tiene infinitos")

    return len(issues) == 0, issues


def validate_dataframe(df: pd.DataFrame, expected_columns: Optional[List[str]] = None) -> bool:
    if df is None or df.empty:
        return False
    if expected_columns:
        return not (set(expected_columns) - set(df.columns))
    return True


# ---------------------------------------------------------------------------
# Archivos
# ---------------------------------------------------------------------------

def create_output_directory(path: Union[str, Path]) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Resumen de datos
# ---------------------------------------------------------------------------

def print_data_summary(df: pd.DataFrame, title: str = "Resumen de Datos") -> None:
    print(f"\n{'='*70}\n{title:^70}\n{'='*70}")
    print(f"Dimensiones: {df.shape[0]} filas × {df.shape[1]} columnas")
    label_col = LABEL_COLUMN if LABEL_COLUMN in df.columns else None
    if label_col:
        print(f"\nDistribución de clases:\n{df[label_col].value_counts()}")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Visualizaciones
# ---------------------------------------------------------------------------

def plot_signal_processing(
    signal_raw: np.ndarray,
    signal_smoothed: np.ndarray,
    signal_normalized: np.ndarray,
    time_axis: Optional[np.ndarray] = None,
    title: str = "Procesamiento de Señal",
    output_path: Optional[Path] = None,
) -> None:
    try:
        import matplotlib.pyplot as plt

        t = time_axis if time_axis is not None else np.arange(len(signal_raw))
        fig, axes = plt.subplots(3, 1, figsize=(12, 8))
        for ax, sig, label, color in zip(
            axes,
            [signal_raw, signal_smoothed, signal_normalized],
            ["Señal Cruda", "Señal Suavizada (Savitzky-Golay)", "Señal Normalizada (Línea Base)"],
            ["b", "g", "r"],
        ):
            ax.plot(t, sig, f"{color}-", linewidth=1.5, alpha=0.7)
            ax.set_title(label, fontweight="bold")
            ax.grid(True, alpha=0.3)

        axes[1].set_ylabel("Amplitud", fontweight="bold")
        axes[2].set_xlabel("Tiempo (muestras)", fontweight="bold")
        fig.suptitle(title, fontsize=14, fontweight="bold")
        plt.tight_layout()

        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()
    except Exception:
        pass


def plot_class_distribution(
    df: pd.DataFrame,
    label_column: str = LABEL_COLUMN,
    output_path: Optional[Path] = None,
) -> None:
    try:
        import matplotlib.pyplot as plt

        if label_column not in df.columns:
            return

        counts = df[label_column].value_counts().sort_index()
        colors = plt.cm.Set3(np.linspace(0, 1, len(counts)))

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        axes[0].bar(counts.index, counts.values, color=colors, edgecolor="black")
        for i, v in enumerate(counts.values):
            axes[0].text(i, v + 0.5, str(v), ha="center", fontweight="bold")
        axes[0].set_title("Distribución de Clases (Barras)", fontweight="bold")
        axes[0].grid(axis="y", alpha=0.3)

        axes[1].pie(counts.values, labels=counts.index, autopct="%1.1f%%", colors=colors)
        axes[1].set_title("Distribución de Clases (Pie)", fontweight="bold")

        plt.tight_layout()
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()
    except Exception:
        pass


def plot_feature_statistics(
    df: pd.DataFrame,
    feature_columns: Optional[List[str]] = None,
    output_path: Optional[Path] = None,
) -> None:
    try:
        import matplotlib.pyplot as plt

        cols = feature_columns or df.select_dtypes(include=[np.number]).columns.tolist()
        cols = cols[:6]

        fig, axes = plt.subplots(2, 3, figsize=(15, 8))
        for ax, col in zip(axes.flatten(), cols):
            if col in df.columns:
                data = df[col].dropna()
                ax.hist(data, bins=20, color="skyblue", edgecolor="black", alpha=0.7)
                ax.set_title(col, fontweight="bold")
                ax.axvline(data.mean(), color="red", linestyle="--", linewidth=2)
                ax.grid(axis="y", alpha=0.3)

        for ax in axes.flatten()[len(cols):]:
            ax.set_visible(False)

        plt.suptitle("Estadísticas de Características Principales", fontsize=14, fontweight="bold")
        plt.tight_layout()
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()
    except Exception:
        pass
