"""
Cliente del endpoint de export de la API y conversión a features.

Este módulo es la **única** ruta de "grabación de la BD → vector de features".
Lo usan tanto el entrenamiento (`train_from_api.py`) como la inferencia
(`predict_from_api.py`) y la visualización, de modo que las features de training
e inferencia se calculan exactamente con el mismo código (sin duplicación).

`httpx` se importa de forma perezosa para que importar este módulo no obligue a
tener la dependencia si solo se usa la parte de extracción.
"""

from typing import Optional

import pandas as pd

from enose.features.handcrafted import HandcraftedExtractor

DEFAULT_API = "http://127.0.0.1:8000"


# ---------------------------------------------------------------------------
# Fetch desde la API
# ---------------------------------------------------------------------------

def fetch_recordings(
    api_url: str = DEFAULT_API,
    sample_ids: Optional[list[int]] = None,
    only_complete: bool = False,
    timeout: float = 120.0,
) -> list[dict]:
    """Devuelve la lista de grabaciones (una por measurement_set) desde la API.

    Si ``sample_ids`` se pasa, filtra por cada sample; si no, trae todas.
    """
    import httpx

    recordings: list[dict] = []
    with httpx.Client(timeout=timeout) as client:
        if sample_ids:
            for sid in sample_ids:
                r = client.get(
                    f"{api_url}/export/recordings",
                    params={"sample_id": sid, "only_complete": only_complete},
                )
                r.raise_for_status()
                recordings.extend(r.json())
        else:
            r = client.get(
                f"{api_url}/export/recordings",
                params={"only_complete": only_complete},
            )
            r.raise_for_status()
            recordings = r.json()
    return recordings


def fetch_recording(
    api_url: str, ms_id: int, timeout: float = 120.0
) -> dict:
    """Devuelve una única grabación por su ``measurement_set_id``."""
    import httpx

    with httpx.Client(timeout=timeout) as client:
        r = client.get(f"{api_url}/export/recordings/{ms_id}")
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Conversión grabación → DataFrame → features
# ---------------------------------------------------------------------------

def recording_to_dataframe(recording: dict) -> pd.DataFrame:
    """Convierte el JSON de una grabación al DataFrame que espera el pipeline.

    Columnas resultantes: ``data, v20, v11, v02, v00, estado`` — el mismo
    formato que los CSV del serial-reader, de modo que el resto del pipeline
    (``extract_from_file_data``) funciona sin cambios.
    """
    rows = recording.get("readings", [])
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["estado"] = df["estado"].astype(str).str.strip().str.lower()
    return df


def recording_to_features(
    recording: dict, extractor: Optional[HandcraftedExtractor] = None
) -> Optional[dict[str, float]]:
    """Extrae el vector de features (estadísticos + ratios) de una grabación.

    Es el punto único de extracción: delega en
    ``HandcraftedExtractor.extract_from_file_data``, igual que el pipeline de
    CSVs. Devuelve ``None`` si la grabación no tiene fase ``medicion`` usable.
    """
    extractor = extractor or HandcraftedExtractor()
    df = recording_to_dataframe(recording)
    if df.empty:
        return None
    features = extractor.extract_from_file_data(df)
    return features or None
