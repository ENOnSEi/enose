"""
Detecta repeticiones "sospechosas" dentro de cada sample: marca para revisión,
NO borra nada. Con solo 3 reps no se puede distinguir fiablemente "error de
medición" de "variación real" — la decisión de descartar debe tomarla una
persona tras mirar la causa (ver el reporte y las gráficas de
visualize_from_api.py).

Método: para cada sample con ≥3 repeticiones completas, se extraen las 60
features de cada rep, se estandarizan (z-score) usando la escala de TODO el
dataset (la misma que ve el clasificador), y se calcula la distancia eucídea
entre cada par de reps. Si una rep está mucho más lejos de las otras dos que
ellas entre sí, se marca como candidata a outlier.

outlier_ratio = distancia_media(candidata, resto) / distancia_media(resto entre sí)

  ratio ~ 1   → las 3 reps son igual de (dis)similares entre sí → homogéneo
  ratio > 2   → la candidata está > 2x más lejos que el par que sí concuerda
                → revisar (umbral configurable con --threshold)

Uso:
    python check_repeatability.py
    python check_repeatability.py --threshold 2.5
    python check_repeatability.py --sample-ids 6 7 8
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).parent / "src"))

from enose.config import FILENAME_COLUMN, LABEL_COLUMN
from enose.features.handcrafted import HandcraftedExtractor
from enose.io.api import DEFAULT_API, fetch_recordings, recording_to_features
from enose.utils import setup_logging

logger = setup_logging(__name__)

DEFAULT_THRESHOLD = 2.0


def build_feature_table(recordings: list[dict]) -> pd.DataFrame:
    """Una fila por grabación válida: sample_id, sample_name, repetition_number,
    ms_id, + columnas de features."""
    extractor = HandcraftedExtractor()
    rows = []
    for rec in recordings:
        features = recording_to_features(rec, extractor)
        if features is None:
            logger.warning(
                f"ms_id={rec.get('measurement_set_id')} "
                f"({rec.get('sample_name')} rep{rec.get('repetition_number')}): "
                f"sin fase medicion, se omite del análisis"
            )
            continue
        rows.append({
            "sample_id": rec["sample_id"],
            "sample_name": rec["sample_name"],
            "repetition_number": rec["repetition_number"],
            "ms_id": rec["measurement_set_id"],
            **features,
        })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    feature_cols = [c for c in df.columns if c not in
                    {"sample_id", "sample_name", "repetition_number", "ms_id"}]
    df[feature_cols] = df[feature_cols].fillna(0.0)
    return df


def analyze_sample(group: pd.DataFrame, feature_cols: list[str], threshold: float) -> dict | None:
    """Analiza las reps de UN sample ya estandarizadas globalmente.

    Devuelve None si hay <3 reps (no hay suficiente info para detectar outlier
    de forma fiable; con 2 reps solo se puede reportar su distancia).
    """
    n = len(group)
    X = group[feature_cols].to_numpy()
    reps = group["repetition_number"].to_numpy()
    ms_ids = group["ms_id"].to_numpy()

    if n < 2:
        return None

    # matriz de distancias euclídeas entre todas las reps
    dist = np.linalg.norm(X[:, None, :] - X[None, :, :], axis=-1)
    np.fill_diagonal(dist, np.nan)

    if n == 2:
        return {
            "n_reps": 2,
            "outlier_rep": None,
            "outlier_ms_id": None,
            "ratio": None,
            "note": "solo 2 reps: no se puede determinar outlier, solo se reporta distancia",
            "pair_distance": float(dist[0, 1]),
            "top_features": None,
        }

    # avg_dist[i] = distancia media de la rep i a todas las demás
    avg_dist = np.nanmean(dist, axis=1)
    outlier_idx = int(np.argmax(avg_dist))
    others_idx = [i for i in range(n) if i != outlier_idx]

    baseline = float(np.mean(avg_dist[others_idx]))
    candidate = float(avg_dist[outlier_idx])
    ratio = candidate / baseline if baseline > 1e-9 else float("inf")

    top_features = None
    if ratio >= threshold:
        # qué features concretas más alejan a la candidata del centroide del resto
        centroid_others = X[others_idx].mean(axis=0)
        delta = np.abs(X[outlier_idx] - centroid_others)
        top_idx = np.argsort(delta)[::-1][:5]
        top_features = [(feature_cols[i], float(delta[i])) for i in top_idx]

    return {
        "n_reps": n,
        "outlier_rep": int(reps[outlier_idx]) if ratio >= threshold else None,
        "outlier_ms_id": int(ms_ids[outlier_idx]) if ratio >= threshold else None,
        "ratio": ratio,
        "note": None,
        "pair_distance": baseline,
        "top_features": top_features,
    }


def main():
    parser = argparse.ArgumentParser(description="Detecta reps sospechosas dentro de cada sample")
    parser.add_argument("--api-url", default=DEFAULT_API)
    parser.add_argument("--sample-ids", type=int, nargs="*", default=None)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"ratio a partir del cual se marca (default {DEFAULT_THRESHOLD})")
    args = parser.parse_args()

    logger.info(f"Fetching desde {args.api_url}...")
    recordings = fetch_recordings(args.api_url, args.sample_ids, only_complete=True)
    if not recordings:
        print("No hay grabaciones completas. ¿Está la API arriba y hay datos?")
        sys.exit(1)

    df = build_feature_table(recordings)
    if df.empty:
        print("Ninguna grabación tiene fase 'medicion' usable.")
        sys.exit(1)

    feature_cols = [c for c in df.columns if c not in
                    {"sample_id", "sample_name", "repetition_number", "ms_id"}]

    # Estandarización GLOBAL (misma escala que ve el clasificador en producción):
    # así las distancias son comparables entre samples con intensidades distintas.
    scaler = StandardScaler()
    df[feature_cols] = scaler.fit_transform(df[feature_cols])

    print()
    print("=" * 72)
    print("  REVISIÓN DE REPETIBILIDAD POR SAMPLE")
    print(f"  {len(df)} grabaciones · {df['sample_id'].nunique()} samples · umbral ratio = {args.threshold}")
    print("=" * 72)

    flagged = []
    for sample_id, group in df.groupby("sample_id", sort=True):
        sample_name = group["sample_name"].iloc[0]
        result = analyze_sample(group, feature_cols, args.threshold)

        if result is None:
            print(f"\n  [{sample_id:>3}] {sample_name:30}  1 sola rep — nada que comparar")
            continue

        if result["n_reps"] == 2:
            print(f"\n  [{sample_id:>3}] {sample_name:30}  2 reps, dist={result['pair_distance']:.2f} "
                  f"— {result['note']}")
            continue

        flag = "  <-- REVISAR" if result["outlier_rep"] is not None else ""
        print(f"\n  [{sample_id:>3}] {sample_name:30}  {result['n_reps']} reps  "
              f"ratio={result['ratio']:.2f}{flag}")

        if result["outlier_rep"] is not None:
            print(f"        rep sospechosa: rep{result['outlier_rep']} (ms_id={result['outlier_ms_id']})")
            print(f"        features que más se desvían del resto:")
            for feat, delta in result["top_features"]:
                print(f"          {feat:28} |Δz|={delta:5.2f}")
            flagged.append({
                "sample_id": sample_id,
                "sample_name": sample_name,
                "outlier_rep": result["outlier_rep"],
                "outlier_ms_id": result["outlier_ms_id"],
                "ratio": result["ratio"],
            })

    print("\n" + "=" * 72)
    if flagged:
        print(f"  {len(flagged)} sample(s) con rep sospechosa — revisar antes de decidir:")
        for f in flagged:
            print(f"    - {f['sample_name']} (sample_id={f['sample_id']}): "
                  f"rep{f['outlier_rep']} (ms_id={f['outlier_ms_id']}), ratio={f['ratio']:.2f}")
        print()
        print("  Antes de descartar, inspecciona la curva cruda de esa rep")
        print("  (visualize_from_api.py --sample-ids <id>) y busca una causa técnica")
        print("  concreta (saturación, base inestable, corte prematuro). Si no hay")
        print("  causa clara, es variación real: consérvala.")
    else:
        print("  Ningún sample marcado. Repetibilidad homogénea dentro del umbral.")
    print("=" * 72)


if __name__ == "__main__":
    main()
