"""
Visualización completa de las mediciones desde la API.

Usage:
    python3.12 visualize_from_api.py --sample-ids 6 7 8 9 10 11 12 13 15 16 17
"""

import argparse
import sys
from pathlib import Path

import httpx
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).parent / "src"))

from enose.signal.processor import SignalProcessor

DEFAULT_API = "http://127.0.0.1:8000"
SENSOR_COLS = ["v20", "v11", "v02", "v00"]
SENSOR_NAMES = {"v20": "TGS2620", "v11": "TGS2611", "v02": "TGS2602", "v00": "TGS2600"}
COLORS_REP = ["#e74c3c", "#3498db", "#2ecc71"]


def fetch_recordings(api_url: str, sample_ids: list[int] | None = None) -> list[dict]:
    recordings = []
    with httpx.Client(timeout=120) as client:
        if sample_ids:
            for sid in sample_ids:
                print(f"  Fetching sample {sid}...")
                r = client.get(f"{api_url}/export/recordings", params={
                    "sample_id": sid, "only_complete": False,
                })
                r.raise_for_status()
                recordings.extend(r.json())
        else:
            r = client.get(f"{api_url}/export/recordings", params={"only_complete": False})
            r.raise_for_status()
            recordings = r.json()
    return recordings


def recording_to_df(rec: dict) -> pd.DataFrame:
    df = pd.DataFrame(rec["readings"])
    df["estado"] = df["estado"].str.strip().str.lower()
    return df


def normalize_recording(df: pd.DataFrame, processor: SignalProcessor) -> dict:
    base_df = df[df["estado"] == "base"]
    med_df = df[df["estado"] == "medicion"]
    if med_df.empty:
        return {}
    result = {}
    for sensor in SENSOR_COLS:
        signal = med_df[sensor].to_numpy(dtype=float)
        baseline = base_df[sensor].to_numpy(dtype=float) if not base_df.empty else np.array([])
        smoothed, normalized = processor.process_signal(signal, baseline)
        dt = 1.0 / processor.sampling_frequency
        time_axis = np.arange(len(normalized)) * dt
        result[sensor] = {
            "raw": signal,
            "smoothed": smoothed,
            "normalized": normalized,
            "time": time_axis,
            "baseline_mean": float(np.mean(baseline)) if len(baseline) > 0 else 0.0,
        }
    return result


def group_by_substance(recordings: list[dict]) -> dict[str, list[dict]]:
    groups = {}
    for rec in recordings:
        name = rec["sample_name"]
        groups.setdefault(name, []).append(rec)
    for name in groups:
        groups[name].sort(key=lambda r: r["repetition_number"])
    return groups


# ── Plot functions ───────────────────────────────────────────────────────────

def plot_raw_signals(groups: dict, processor: SignalProcessor, out_dir: Path):
    """Raw ADC signals per substance, 4 sensors, 3 reps overlaid."""
    for substance, recs in groups.items():
        fig, axes = plt.subplots(2, 2, figsize=(16, 10))
        fig.suptitle(f"Señal ADC cruda — {substance}", fontsize=14, fontweight="bold")

        for idx, sensor in enumerate(SENSOR_COLS):
            ax = axes[idx // 2][idx % 2]
            for i, rec in enumerate(recs):
                df = recording_to_df(rec)
                med = df[df["estado"] == "medicion"]
                base = df[df["estado"] == "base"]
                if med.empty:
                    continue
                all_vals = pd.concat([base, med])[sensor].to_numpy(dtype=float)
                all_estados = pd.concat([base, med])["estado"].values
                dt = 1.0 / processor.sampling_frequency
                t = np.arange(len(all_vals)) * dt
                ax.plot(t, all_vals, color=COLORS_REP[i], alpha=0.8,
                        label=f"rep{rec['repetition_number']}", linewidth=1.2)
                base_end = len(base)
                if base_end > 0:
                    ax.axvline(x=base_end * dt, color="gray", linestyle="--",
                               alpha=0.4, linewidth=0.8)
            ax.set_title(f"{sensor} ({SENSOR_NAMES[sensor]})")
            ax.set_xlabel("Tiempo (s)")
            ax.set_ylabel("ADC")
            ax.legend(fontsize=8)
            ax.grid(alpha=0.3)

        plt.tight_layout()
        safe_name = substance.replace(" ", "_").replace("/", "_")
        fig.savefig(out_dir / f"01_raw_{safe_name}.png", dpi=200, bbox_inches="tight")
        plt.close(fig)


def plot_normalized_signals(groups: dict, processor: SignalProcessor, out_dir: Path):
    """Normalized signals per substance, 4 sensors, 3 reps overlaid."""
    for substance, recs in groups.items():
        fig, axes = plt.subplots(2, 2, figsize=(16, 10))
        fig.suptitle(f"Señal normalizada (Rs−R0)/R0 — {substance}", fontsize=14, fontweight="bold")

        for idx, sensor in enumerate(SENSOR_COLS):
            ax = axes[idx // 2][idx % 2]
            for i, rec in enumerate(recs):
                df = recording_to_df(rec)
                data = normalize_recording(df, processor)
                if sensor not in data:
                    continue
                d = data[sensor]
                ax.plot(d["time"], d["normalized"], color=COLORS_REP[i], alpha=0.8,
                        label=f"rep{rec['repetition_number']}", linewidth=1.2)
            for t_start, t_end in processor.time_windows:
                ax.axvline(x=t_start, color="orange", linestyle=":", alpha=0.3, linewidth=0.7)
            ax.set_title(f"{sensor} ({SENSOR_NAMES[sensor]})")
            ax.set_xlabel("Tiempo (s)")
            ax.set_ylabel("(Rs−R0)/R0")
            ax.legend(fontsize=8)
            ax.grid(alpha=0.3)

        plt.tight_layout()
        safe_name = substance.replace(" ", "_").replace("/", "_")
        fig.savefig(out_dir / f"02_norm_{safe_name}.png", dpi=200, bbox_inches="tight")
        plt.close(fig)


def plot_all_substances_overlay(groups: dict, processor: SignalProcessor, out_dir: Path):
    """All substances overlaid (mean of reps) per sensor — fingerprint comparison."""
    fig, axes = plt.subplots(2, 2, figsize=(18, 12))
    fig.suptitle("Comparativa de sustancias — señal normalizada (media de reps)",
                 fontsize=14, fontweight="bold")
    cmap = plt.colormaps["tab20"]

    for idx, sensor in enumerate(SENSOR_COLS):
        ax = axes[idx // 2][idx % 2]
        for j, (substance, recs) in enumerate(groups.items()):
            all_norm = []
            for rec in recs:
                df = recording_to_df(rec)
                data = normalize_recording(df, processor)
                if sensor in data:
                    all_norm.append(data[sensor]["normalized"])
            if not all_norm:
                continue
            min_len = min(len(x) for x in all_norm)
            stacked = np.array([x[:min_len] for x in all_norm])
            mean_sig = stacked.mean(axis=0)
            dt = 1.0 / processor.sampling_frequency
            t = np.arange(min_len) * dt
            ax.plot(t, mean_sig, color=cmap(j), label=substance, linewidth=1.5, alpha=0.85)

        ax.set_title(f"{sensor} ({SENSOR_NAMES[sensor]})")
        ax.set_xlabel("Tiempo (s)")
        ax.set_ylabel("(Rs−R0)/R0")
        ax.grid(alpha=0.3)

    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="center right", fontsize=8, bbox_to_anchor=(1.15, 0.5))
    plt.tight_layout()
    fig.savefig(out_dir / "03_all_substances_overlay.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_feature_boxplots(dataset_path: Path, out_dir: Path):
    """Box plots of key features by substance."""
    df = pd.read_csv(dataset_path)
    label_col = "Etiqueta"
    if label_col not in df.columns:
        return

    for sensor in SENSOR_COLS:
        features = [f"{sensor}_w0-5_max", f"{sensor}_w5-15_max", f"{sensor}_w15-40_max",
                     f"{sensor}_w0-5_auc", f"{sensor}_w5-15_auc", f"{sensor}_w15-40_auc",
                     f"{sensor}_w0-5_slope", f"{sensor}_w5-15_slope", f"{sensor}_w15-40_slope"]
        existing = [f for f in features if f in df.columns]
        if not existing:
            continue

        n = len(existing)
        fig, axes = plt.subplots(1, n, figsize=(n * 4, 6))
        if n == 1:
            axes = [axes]
        fig.suptitle(f"Box plots — {sensor} ({SENSOR_NAMES[sensor]})",
                     fontsize=14, fontweight="bold")

        for ax, feat in zip(axes, existing):
            sns.boxplot(data=df, x=label_col, y=feat, ax=ax, palette="Set2")
            ax.set_title(feat.replace(f"{sensor}_", ""), fontsize=10)
            ax.set_xlabel("")
            ax.tick_params(axis="x", rotation=45, labelsize=7)
            ax.grid(axis="y", alpha=0.3)

        plt.tight_layout()
        fig.savefig(out_dir / f"04_boxplot_{sensor}.png", dpi=200, bbox_inches="tight")
        plt.close(fig)


def plot_feature_heatmap(dataset_path: Path, out_dir: Path):
    """Heatmap of all 36 features across all samples."""
    df = pd.read_csv(dataset_path)
    label_col = "Etiqueta"
    fname_col = "Nombre_Archivo"
    non_feat = {label_col, fname_col}
    feat_cols = [c for c in df.columns if c not in non_feat]

    labels = df[label_col].values
    feat_df = df[feat_cols].copy()
    scaler = StandardScaler()
    scaled = pd.DataFrame(scaler.fit_transform(feat_df), columns=feat_cols)
    scaled.index = [f"{l} ({i+1})" for i, l in enumerate(labels)]

    fig, ax = plt.subplots(figsize=(20, max(8, len(df) * 0.4)))
    sns.heatmap(scaled, cmap="RdBu_r", center=0, ax=ax, xticklabels=True,
                yticklabels=True, linewidths=0.3, cbar_kws={"label": "z-score"})
    ax.set_title("Heatmap de features (z-score) por muestra", fontsize=14, fontweight="bold")
    ax.tick_params(axis="x", rotation=45, labelsize=7)
    ax.tick_params(axis="y", labelsize=7)
    plt.tight_layout()
    fig.savefig(out_dir / "05_feature_heatmap.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_pca_projection(dataset_path: Path, out_dir: Path):
    """PCA 2D projection of all samples, colored by substance."""
    df = pd.read_csv(dataset_path)
    label_col = "Etiqueta"
    fname_col = "Nombre_Archivo"
    non_feat = {label_col, fname_col}
    feat_cols = [c for c in df.columns if c not in non_feat]

    X = df[feat_cols].values
    y = df[label_col].values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    pca = PCA(n_components=2)
    X_pca = pca.fit_transform(X_scaled)

    fig, ax = plt.subplots(figsize=(12, 9))
    unique_labels = sorted(set(y))
    cmap = plt.colormaps["tab20"]

    for i, label in enumerate(unique_labels):
        mask = y == label
        ax.scatter(X_pca[mask, 0], X_pca[mask, 1], color=cmap(i), label=label,
                   s=100, edgecolors="black", linewidths=0.5, alpha=0.85)
        for xi, yi in zip(X_pca[mask, 0], X_pca[mask, 1]):
            ax.annotate(label[:8], (xi, yi), fontsize=6, alpha=0.6,
                        textcoords="offset points", xytext=(5, 3))

    ax.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0]*100:.1f}% varianza)")
    ax.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1]*100:.1f}% varianza)")
    ax.set_title("Proyección PCA — ¿se separan las sustancias?", fontsize=14, fontweight="bold")
    ax.legend(fontsize=8, loc="best", bbox_to_anchor=(1.02, 1))
    ax.grid(alpha=0.3)
    plt.tight_layout()
    fig.savefig(out_dir / "06_pca_projection.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_pca_3components(dataset_path: Path, out_dir: Path):
    """Varianza explicada por componente PCA."""
    df = pd.read_csv(dataset_path)
    label_col = "Etiqueta"
    fname_col = "Nombre_Archivo"
    non_feat = {label_col, fname_col}
    feat_cols = [c for c in df.columns if c not in non_feat]

    X = StandardScaler().fit_transform(df[feat_cols].values)
    pca = PCA().fit(X)

    fig, ax = plt.subplots(figsize=(10, 5))
    cumvar = np.cumsum(pca.explained_variance_ratio_) * 100
    ax.bar(range(1, len(pca.explained_variance_ratio_) + 1),
           pca.explained_variance_ratio_ * 100, alpha=0.6, label="Individual")
    ax.plot(range(1, len(cumvar) + 1), cumvar, "ro-", markersize=4, label="Acumulada")
    ax.axhline(y=95, color="gray", linestyle="--", alpha=0.5, label="95%")
    n95 = np.argmax(cumvar >= 95) + 1
    ax.axvline(x=n95, color="green", linestyle="--", alpha=0.5, label=f"n={n95} para 95%")
    ax.set_xlabel("Componente")
    ax.set_ylabel("% Varianza explicada")
    ax.set_title("Varianza explicada por componentes PCA", fontsize=14, fontweight="bold")
    ax.legend()
    ax.grid(alpha=0.3)
    plt.tight_layout()
    fig.savefig(out_dir / "07_pca_variance.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_repeatability(groups: dict, processor: SignalProcessor, out_dir: Path):
    """CV (coef. variación) of normalized peak per sensor per substance — repeatability."""
    rows = []
    for substance, recs in groups.items():
        for sensor in SENSOR_COLS:
            peaks = []
            for rec in recs:
                df = recording_to_df(rec)
                data = normalize_recording(df, processor)
                if sensor in data:
                    peaks.append(float(np.max(np.abs(data[sensor]["normalized"]))))
            if len(peaks) >= 2:
                cv = np.std(peaks) / (np.mean(peaks) + 1e-10) * 100
                rows.append({"Sustancia": substance, "Sensor": SENSOR_NAMES[sensor], "CV%": cv,
                              "mean_peak": np.mean(peaks)})

    if not rows:
        return
    df = pd.DataFrame(rows)
    pivot = df.pivot(index="Sustancia", columns="Sensor", values="CV%")

    fig, ax = plt.subplots(figsize=(12, max(6, len(pivot) * 0.45)))
    sns.heatmap(pivot, annot=True, fmt=".1f", cmap="YlOrRd", ax=ax,
                linewidths=0.5, cbar_kws={"label": "CV%"})
    ax.set_title("Repetibilidad (CV% del pico normalizado, 3 reps) — menor = mejor",
                 fontsize=13, fontweight="bold")
    ax.tick_params(axis="y", rotation=0, labelsize=8)
    plt.tight_layout()
    fig.savefig(out_dir / "08_repeatability_cv.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_sensor_response_profile(groups: dict, processor: SignalProcessor, out_dir: Path):
    """Mean peak response per sensor per substance — radar-like bar chart."""
    rows = []
    for substance, recs in groups.items():
        for sensor in SENSOR_COLS:
            peaks = []
            for rec in recs:
                df = recording_to_df(rec)
                data = normalize_recording(df, processor)
                if sensor in data:
                    peaks.append(float(np.max(np.abs(data[sensor]["normalized"]))))
            if peaks:
                rows.append({"Sustancia": substance, "Sensor": SENSOR_NAMES[sensor],
                              "Peak medio": np.mean(peaks)})

    if not rows:
        return
    df = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(14, 7))
    sns.barplot(data=df, x="Sustancia", y="Peak medio", hue="Sensor", ax=ax, palette="Set2")
    ax.set_title("Respuesta pico media por sensor y sustancia", fontsize=14, fontweight="bold")
    ax.tick_params(axis="x", rotation=45, labelsize=8)
    ax.grid(axis="y", alpha=0.3)
    ax.legend(title="Sensor")
    plt.tight_layout()
    fig.savefig(out_dir / "09_sensor_response_profile.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_correlation_matrix(dataset_path: Path, out_dir: Path):
    """Correlation matrix between the 36 features."""
    df = pd.read_csv(dataset_path)
    non_feat = {"Etiqueta", "Nombre_Archivo"}
    feat_cols = [c for c in df.columns if c not in non_feat]

    corr = df[feat_cols].corr()
    fig, ax = plt.subplots(figsize=(16, 14))
    mask = np.triu(np.ones_like(corr, dtype=bool), k=1)
    sns.heatmap(corr, mask=mask, cmap="coolwarm", center=0, ax=ax,
                xticklabels=True, yticklabels=True, linewidths=0.3,
                vmin=-1, vmax=1, cbar_kws={"label": "Correlación"})
    ax.set_title("Matriz de correlación entre features", fontsize=14, fontweight="bold")
    ax.tick_params(axis="x", rotation=45, labelsize=7)
    ax.tick_params(axis="y", labelsize=7)
    plt.tight_layout()
    fig.savefig(out_dir / "10_correlation_matrix.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_base_vs_medicion_summary(groups: dict, processor: SignalProcessor, out_dir: Path):
    """Base mean vs medicion peak per substance — shows signal-to-baseline ratio."""
    rows = []
    for substance, recs in groups.items():
        for rec in recs:
            df = recording_to_df(rec)
            base_df = df[df["estado"] == "base"]
            med_df = df[df["estado"] == "medicion"]
            for sensor in SENSOR_COLS:
                if base_df.empty or med_df.empty:
                    continue
                base_mean = base_df[sensor].mean()
                med_peak = med_df[sensor].max()
                rows.append({
                    "Sustancia": substance,
                    "Rep": rec["repetition_number"],
                    "Sensor": SENSOR_NAMES[sensor],
                    "Base mean": base_mean,
                    "Medicion peak": med_peak,
                    "Delta": med_peak - base_mean,
                })

    if not rows:
        return
    df = pd.DataFrame(rows)

    fig, axes = plt.subplots(1, 2, figsize=(18, 7))

    sns.boxplot(data=df, x="Sustancia", y="Delta", hue="Sensor", ax=axes[0], palette="Set2")
    axes[0].set_title("Delta (peak medición − base) por sustancia", fontsize=12, fontweight="bold")
    axes[0].tick_params(axis="x", rotation=45, labelsize=7)
    axes[0].grid(axis="y", alpha=0.3)

    sns.scatterplot(data=df, x="Base mean", y="Medicion peak", hue="Sustancia",
                    style="Sensor", ax=axes[1], s=60, alpha=0.8)
    axes[1].set_title("Base vs Peak medición (ADC)", fontsize=12, fontweight="bold")
    axes[1].legend(fontsize=6, bbox_to_anchor=(1.02, 1))
    axes[1].grid(alpha=0.3)

    plt.tight_layout()
    fig.savefig(out_dir / "11_base_vs_medicion.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Visualize recordings from API")
    parser.add_argument("--api-url", default=DEFAULT_API)
    parser.add_argument("--sample-ids", type=int, nargs="*", default=None)
    args = parser.parse_args()

    out_dir = Path(__file__).parent / "datos" / "visualizations"
    out_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = Path(__file__).parent / "datos" / "procesados" / "dataset_maestro.csv"

    print(f"Fetching from {args.api_url}...")
    recordings = fetch_recordings(args.api_url, args.sample_ids)
    print(f"Recordings: {len(recordings)}")

    if not recordings:
        print("No recordings. Is the API running?")
        sys.exit(1)

    groups = group_by_substance(recordings)
    processor = SignalProcessor()

    print(f"Output: {out_dir}")
    print(f"Substances: {list(groups.keys())}")

    print("01 — Raw signals per substance...")
    plot_raw_signals(groups, processor, out_dir)

    print("02 — Normalized signals per substance...")
    plot_normalized_signals(groups, processor, out_dir)

    print("03 — All substances overlay...")
    plot_all_substances_overlay(groups, processor, out_dir)

    if dataset_path.exists():
        print("04 — Feature box plots...")
        plot_feature_boxplots(dataset_path, out_dir)

        print("05 — Feature heatmap...")
        plot_feature_heatmap(dataset_path, out_dir)

        print("06 — PCA projection...")
        plot_pca_projection(dataset_path, out_dir)

        print("07 — PCA variance explained...")
        plot_pca_3components(dataset_path, out_dir)

        print("10 — Correlation matrix...")
        plot_correlation_matrix(dataset_path, out_dir)
    else:
        print(f"SKIP feature plots — {dataset_path} not found (run train_from_api.py first)")

    print("08 — Repeatability (CV%)...")
    plot_repeatability(groups, processor, out_dir)

    print("09 — Sensor response profile...")
    plot_sensor_response_profile(groups, processor, out_dir)

    print("11 — Base vs medición...")
    plot_base_vs_medicion_summary(groups, processor, out_dir)

    print(f"\nDone. {len(list(out_dir.glob('*.png')))} plots saved in:\n  {out_dir}")


if __name__ == "__main__":
    main()
