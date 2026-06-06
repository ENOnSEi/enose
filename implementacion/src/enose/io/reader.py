"""
Capa de ingesta de datos: lectura de grabaciones del serial-reader y extracción
de etiquetas.

Cada grabación es un CSV con cabecera ``data,v20,v11,v02,v00,estado`` (ver
``enose.config``). Su salida es el input del procesador de señal.
"""

from pathlib import Path
from typing import Dict, List, Optional, Union

import pandas as pd

from enose.config import (
    BASELINE_STATE, MEASUREMENT_STATE, SENSOR_COLUMNS, STATE_COLUMN,
    SUBSTANCE_LABELS, TIMESTAMP_COLUMN, WARMUP_STATE,
)
from enose.utils import setup_logging, validate_sensor_data

logger = setup_logging(__name__)

_SENSOR_COLS: List[str] = list(SENSOR_COLUMNS["sensors"])
_EXPECTED_COLS = [TIMESTAMP_COLUMN, *_SENSOR_COLS, STATE_COLUMN]


def load_sensor_file(file_path: Path) -> Optional[pd.DataFrame]:
    """
    Carga y valida una grabación CSV del serial-reader.

    Devuelve un DataFrame con las columnas ``data,v20,v11,v02,v00,estado`` o
    ``None`` si el fichero no se puede leer o le faltan columnas esperadas.
    """
    try:
        df = pd.read_csv(file_path)
        missing = [c for c in _EXPECTED_COLS if c not in df.columns]
        if missing:
            logger.error(f"{file_path.name}: faltan columnas {missing}; se omite.")
            return None
        if STATE_COLUMN in df.columns:
            df[STATE_COLUMN] = df[STATE_COLUMN].astype(str).str.strip().str.lower()
        is_valid, issues = validate_sensor_data(df)
        if not is_valid:
            logger.warning(f"Problemas en {file_path.name}: {issues}")
        return df
    except Exception as e:
        logger.error(f"Error al cargar {file_path}: {e}")
        return None


def get_files_recursive(directory: Union[str, Path], pattern: str = "*.csv") -> List[Path]:
    """Busca grabaciones recursivamente en un directorio (por defecto *.csv)."""
    path = Path(directory)
    if not path.exists():
        return []
    return sorted(path.rglob(pattern))


def extract_substance_label(filename: str) -> Optional[str]:
    """
    Deriva la etiqueta de mezcla a partir del nombre del fichero.

    Se hace por coincidencia EXACTA del nombre (sin extensión, en minúsculas)
    contra ``SUBSTANCE_LABELS``. Si el nombre no está en el mapa, se usa el
    propio nombre del fichero como etiqueta — así nuevas grabaciones quedan
    etiquetadas aunque todavía no tengan una entrada en config.

    Ejemplos
    --------
    'vino.csv'              → 'Vino'
    'vinoyagua.csv'         → 'Vino+Agua'
    'vinoagitacionrara.csv' → 'Vino+Alcohol'
    'mezcla_nueva.csv'      → 'mezcla_nueva'   (fallback)
    """
    stem = Path(filename).stem.strip().lower()
    if stem in SUBSTANCE_LABELS:
        return SUBSTANCE_LABELS[stem]
    logger.info(f"'{filename}': nombre no mapeado en SUBSTANCE_LABELS; se usa '{stem}' como etiqueta.")
    return stem or None


def split_by_state(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """
    Separa una grabación por la columna 'estado'.

    Devuelve un dict ``{estado: sub-DataFrame}`` con las claves presentes en la
    grabación (típicamente 'inicio', 'base', 'medicion').
    """
    if STATE_COLUMN not in df.columns:
        return {MEASUREMENT_STATE: df}
    return {state: group.reset_index(drop=True) for state, group in df.groupby(STATE_COLUMN, sort=False)}


def get_baseline_and_signal(
    df: pd.DataFrame, sensor: str
) -> Optional[tuple]:
    """
    Para un sensor, devuelve ``(baseline, signal)`` como arrays de numpy:

      - baseline : valores del sensor durante la fase 'base' (R0 / aire limpio).
      - signal   : valores del sensor durante la fase 'medicion' (respuesta).

    La fase 'inicio' (calentamiento) se ignora. Si no hay fase 'base', el
    baseline se devuelve vacío y el procesador usará un fallback interno. Si no
    hay fase 'medicion', se devuelve ``None``.
    """
    if sensor not in df.columns:
        return None

    by_state = split_by_state(df)
    measurement = by_state.get(MEASUREMENT_STATE)
    if measurement is None or measurement.empty:
        return None

    baseline_df = by_state.get(BASELINE_STATE)
    baseline = baseline_df[sensor].to_numpy() if baseline_df is not None else []
    signal = measurement[sensor].to_numpy()
    return baseline, signal


__all__ = [
    "load_sensor_file",
    "get_files_recursive",
    "extract_substance_label",
    "split_by_state",
    "get_baseline_and_signal",
    "WARMUP_STATE",
    "BASELINE_STATE",
    "MEASUREMENT_STATE",
]
