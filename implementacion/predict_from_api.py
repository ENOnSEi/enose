"""
Inferencia: clasifica una grabación (o todas las reps de un sample) con el modelo.

Cierra el loop de la nariz electrónica: se mide una sustancia desconocida → la API
le asigna measurement_set_ids → este script la clasifica.

Usa exactamente la MISMA extracción de features que el entrenamiento
(`enose.io.api.recording_to_features`), así que el vector que ve el modelo en
inferencia es idéntico al que vio en training.

Modos:
    # Una sola repetición (por measurement_set_id):
    python predict_from_api.py --ms-id 43

    # Sample completo — agrega las N reps con soft vote (RECOMENDADO):
    python predict_from_api.py --sample-id 22

    # Opciones adicionales:
    python predict_from_api.py --sample-id 22 --api-url http://host:8000
    python predict_from_api.py --sample-id 22 --model ruta/best_model.pkl

Agregación de reps (soft vote):
    Cada rep se procesa de forma independiente (features → decision_function).
    Los scores se promedian entre todas las reps válidas y se elige la clase con
    score medio más alto. Más robusto que el voto duro: una rep ruidosa baja sus
    scores un poco en vez de descartarse entera.
"""

import argparse
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent / "src"))

from enose.config import DATA_PROCESSED_DIR
from enose.io.api import DEFAULT_API, fetch_recording, fetch_recordings, recording_to_features
from enose.utils import setup_logging

logger = setup_logging(__name__)


def load_model(path: Path | None = None):
    path = Path(path) if path else (DATA_PROCESSED_DIR / "best_model.pkl")
    if not path.exists():
        logger.error(f"Modelo no encontrado: {path}. Entrena primero con train_from_api.py")
        sys.exit(1)
    with open(path, "rb") as f:
        return pickle.load(f)


def features_to_row(model, features: dict[str, float]) -> pd.DataFrame:
    """Convierte el dict de features al DataFrame con el orden de columnas del modelo."""
    feat_names = list(getattr(model, "feature_names_in_", []))
    if feat_names:
        return pd.DataFrame([features]).reindex(columns=feat_names, fill_value=0.0)
    return pd.DataFrame([features])


def get_scores(model, features: dict[str, float]) -> np.ndarray | None:
    """Devuelve el vector de decision_function para un vector de features, o None."""
    if not hasattr(model, "decision_function"):
        return None
    row = features_to_row(model, features)
    scores = model.decision_function(row)[0]
    if not hasattr(scores, "__len__") or len(scores) != len(model.classes_):
        return None
    return np.asarray(scores)


def predict_single(model, features: dict[str, float]) -> tuple[str, list]:
    """Predice una sola rep. Devuelve (prediccion, ranking)."""
    row = features_to_row(model, features)
    prediction = model.predict(row)[0]
    scores = get_scores(model, features)
    ranking = []
    if scores is not None:
        ranking = sorted(zip(model.classes_, scores), key=lambda x: x[1], reverse=True)
    return prediction, ranking


def predict_aggregate(model, recs: list[dict]) -> tuple[str, list, list[str], int]:
    """Agrega N reps con soft vote (media de decision_function scores).

    Devuelve (prediccion, ranking_medio, predicciones_individuales, n_validas).
    """
    classes = list(model.classes_)
    all_scores: list[np.ndarray] = []
    individual: list[str] = []

    for rec in recs:
        features = recording_to_features(rec)
        if features is None:
            logger.warning(f"ms_id={rec['measurement_set_id']} rep{rec['repetition_number']}: "
                           f"sin fase medicion, se omite de la agregacion")
            individual.append("(sin datos)")
            continue
        scores = get_scores(model, features)
        if scores is not None:
            all_scores.append(scores)
        row = features_to_row(model, features)
        individual.append(model.predict(row)[0])

    if not all_scores:
        logger.error("Ninguna repeticion tiene datos usables")
        sys.exit(1)

    mean_scores = np.mean(all_scores, axis=0)
    prediction = classes[int(np.argmax(mean_scores))]
    ranking = sorted(zip(classes, mean_scores), key=lambda x: x[1], reverse=True)
    return prediction, ranking, individual, len(all_scores)


def print_single(ms_id: int, rec: dict, prediction: str, ranking: list) -> None:
    nombre = rec.get("sample_name", "?")
    rep = rec.get("repetition_number", "?")
    print()
    print("=" * 62)
    print(f"  Measurement set {ms_id}  ('{nombre}' rep{rep})")
    print("=" * 62)
    print(f"  >> PREDICCION: {prediction}")
    if ranking:
        print()
        print("  Ranking (decision_function):")
        for i, (cls, score) in enumerate(ranking[:5], 1):
            marca = "  <--" if cls == prediction else ""
            print(f"    {i}. {score:+9.3f}  {cls}{marca}")
    print()


def print_aggregate(sample_id: int, sample_name: str, prediction: str,
                    ranking: list, individual: list[str], n_valid: int) -> None:
    print()
    print("=" * 62)
    print(f"  Sample {sample_id}  ('{sample_name}')  — {n_valid} rep(s) validas")
    print("=" * 62)
    print(f"  >> PREDICCION AGREGADA (soft vote): {prediction}")
    print()
    print("  Predicciones individuales por rep:")
    for i, pred in enumerate(individual, 1):
        marca = "  <--" if pred == prediction else ""
        print(f"    rep{i}: {pred}{marca}")
    print()
    print("  Ranking (media de decision_function entre reps):")
    for i, (cls, score) in enumerate(ranking[:5], 1):
        marca = "  <--" if cls == prediction else ""
        print(f"    {i}. {score:+9.3f}  {cls}{marca}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Clasifica una sustancia con el modelo entrenado"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ms-id", type=int, metavar="MS_ID",
                       help="Clasifica UN measurement_set (una repeticion)")
    group.add_argument("--sample-id", type=int, metavar="SAMPLE_ID",
                       help="Clasifica TODAS las reps de un sample con soft vote (recomendado)")
    # retrocompatibilidad: posicional ms_id si se pasa sin flag
    parser.add_argument("ms_id_pos", nargs="?", type=int,
                        help=argparse.SUPPRESS)
    parser.add_argument("--api-url", default=DEFAULT_API)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    # retrocompatibilidad con el uso anterior: predict_from_api.py 43
    if args.ms_id_pos is not None and args.ms_id is None and args.sample_id is None:
        args.ms_id = args.ms_id_pos

    model = load_model(args.model)

    if args.ms_id is not None:
        rec = fetch_recording(args.api_url, args.ms_id)
        features = recording_to_features(rec)
        if features is None:
            logger.error(f"ms_id={args.ms_id}: sin fase 'medicion' usable")
            sys.exit(1)
        prediction, ranking = predict_single(model, features)
        print_single(args.ms_id, rec, prediction, ranking)

    else:
        recs = fetch_recordings(args.api_url, sample_ids=[args.sample_id],
                                only_complete=False)
        if not recs:
            logger.error(f"sample_id={args.sample_id}: sin grabaciones en la API")
            sys.exit(1)
        recs.sort(key=lambda r: r["repetition_number"])
        sample_name = recs[0].get("sample_name", "?")
        prediction, ranking, individual, n_valid = predict_aggregate(model, recs)
        print_aggregate(args.sample_id, sample_name, prediction, ranking,
                        individual, n_valid)


if __name__ == "__main__":
    main()
