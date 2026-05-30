"""
Capa de ingesta de datos: lectura de archivos de sensor y extracción de etiquetas.

Implementa el contrato SignalProcessorProtocol de forma indirecta —
su salida es el input del procesador de señal.
"""

from pathlib import Path
from typing import List, Optional, Union

import pandas as pd

from enose.config import SUBSTANCE_LABELS
from enose.utils import setup_logging, validate_sensor_data

logger = setup_logging(__name__)

_COLUMN_NAMES = ["Humedad_%", "Temperatura_C", "MQ3_1", "MQ4_1", "MQ6_1", "MQ3_2", "MQ4_2", "MQ6_2"]


def load_sensor_file(file_path: Path) -> Optional[pd.DataFrame]:
    """Carga y valida un archivo de sensor (.txt, separado por espacios)."""
    try:
        df = pd.read_csv(file_path, sep=r"\s+", header=None, names=_COLUMN_NAMES)
        is_valid, issues = validate_sensor_data(df)
        if not is_valid:
            logger.warning(f"Problemas en {file_path.name}: {issues}")
        return df
    except Exception as e:
        logger.error(f"Error al cargar {file_path}: {e}")
        return None


def get_files_recursive(directory: Union[str, Path], pattern: str) -> List[Path]:
    """Busca archivos recursivamente en un directorio."""
    path = Path(directory)
    if not path.exists():
        return []
    return sorted(path.rglob(pattern))


def extract_substance_label(filename: str) -> Optional[str]:
    """
    Deriva la etiqueta de sustancia del nombre del archivo.

    Ejemplos
    --------
    'AQ_Wine01-B01_R01.txt' → 'AQ'
    'Ethanol_C1_R01.txt'    → 'ETH'
    """
    upper = filename.upper()
    for key, label in SUBSTANCE_LABELS.items():
        if key.replace("_", "") in upper.replace("_", ""):
            return label
    return None
