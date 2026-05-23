"""
===============================================================================
FASE 1-3: EXTRACCIÓN DE CARACTERÍSTICAS - NARIZ ELECTRÓNICA
===============================================================================

Este módulo implementa el motor de extracción de características que realiza:

FASE 1: Ingesta de datos
- Lectura de archivos CSV
- Validación de estructura

FASE 2: Procesamiento de señales
- Suavizado con media móvil
- Normalización por línea base

FASE 3: Extracción de características matemáticas
- Máximo de la señal
- Área bajo la curva (AUC)
- Pendiente máxima

===============================================================================
"""

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, Optional, Tuple
from src.ENose_V1.utils import setup_logging, validate_sensor_data, plot_signal_processing, create_output_directory
from config import SENSOR_COLUMNS, SIGNAL_PROCESSING, DATA_PROCESSED_DIR

logger = setup_logging(__name__)


class SignalProcessor:
    """
    Procesa señales de sensores de la nariz electrónica.
    
    Realiza suavizado, normalización y extracción de características.
    """
    
    def __init__(self, 
                 sampling_frequency: float = SIGNAL_PROCESSING['sampling_frequency'],
                 smoothing_window: int = SIGNAL_PROCESSING['smoothing_window'],
                 baseline_seconds: float = SIGNAL_PROCESSING['baseline_seconds']):
        """
        Inicializa el procesador de señales.
        
        Parámetros:
        -----------
        sampling_frequency : float
            Frecuencia de muestreo en Hz
        smoothing_window : int
            Tamaño de la ventana para media móvil
        baseline_seconds : float
            Segundos iniciales a usar como línea base
        """
        self.sampling_frequency = sampling_frequency
        self.smoothing_window = smoothing_window
        self.baseline_seconds = baseline_seconds
        self.dt = 1.0 / sampling_frequency
        self.baseline_samples = int(baseline_seconds * sampling_frequency)
    
    def smooth_signal(self, signal: np.ndarray) -> np.ndarray:
        """
        Suaviza una señal usando media móvil centrada.
        
        Parámetros:
        -----------
        signal : np.ndarray
            Señal a suavizar
        
        Retorna:
        --------
        np.ndarray
            Señal suavizada
        """
        # Usar pandas para media móvil centrada
        smoothed = pd.Series(signal).rolling(
            window=self.smoothing_window, 
            center=True
        ).mean().values
        
        # Rellenar valores faltantes (inicio y fin)
        mask = ~np.isnan(smoothed)
        if not np.all(mask):
            valid_indices = np.where(mask)[0]
            if len(valid_indices) > 0:
                smoothed[~mask] = np.interp(
                    np.where(~mask)[0],
                    valid_indices,
                    smoothed[valid_indices]
                )
        
        return smoothed
    
    def normalize_by_baseline(self, signal: np.ndarray) -> np.ndarray:
        """
        Normaliza una señal por su línea base (primeros seg_basales segundos).
        
        La normalización se calcula como: (R0 - Rs) / R0
        donde R0 es la resistencia de la línea base y Rs es la resistencia actual.
        
        Parámetros:
        -----------
        signal : np.ndarray
            Señal a normalizar
        
        Retorna:
        --------
        np.ndarray
            Señal normalizada
        """
        if len(signal) < self.baseline_samples:
            logger.warning(
                f"Señal más corta que línea base "
                f"({len(signal)} < {self.baseline_samples}). "
                f"Usando toda la señal como línea base."
            )
            baseline_samples = len(signal)
        else:
            baseline_samples = self.baseline_samples
        
        R0 = np.mean(signal[:baseline_samples])
        
        # Evitar división por cero
        if R0 == 0:
            logger.warning("R0 = 0. Usando normalización alternativa.")
            return (signal - np.mean(signal)) / (np.std(signal) + 1e-10)
        
        normalized = (R0 - signal) / R0
        return normalized
    
    def extract_features(self, signal: np.ndarray) -> Dict[str, float]:
        """
        Extrae características matemáticas de una señal normalizada.
        
        Características extraídas:
        - max: Máximo valor de la señal
        - auc: Área bajo la curva
        - slope: Pendiente máxima
        
        Parámetros:
        -----------
        signal : np.ndarray
            Señal normalizada
        
        Retorna:
        --------
        dict
            Diccionario con las características extraídas
        """
        features = {}
        
        # Característica 1: Máximo de la señal
        features['max'] = float(np.max(signal))
        
        # Característica 2: Área bajo la curva (AUC)
        features['auc'] = float(np.trapezoid(signal, dx=self.dt))
        
        # Característica 3: Pendiente máxima (máxima derivada)
        if len(signal) > 1:
            derivatives = np.diff(signal) / self.dt
            features['slope'] = float(np.max(np.abs(derivatives)))
        else:
            features['slope'] = 0.0
        
        return features
    
    def process_signal(self, signal: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Procesa una señal completa (suavizado + normalización).
        
        Parámetros:
        -----------
        signal : np.ndarray
            Señal cruda
        
        Retorna:
        --------
        tuple of (np.ndarray, np.ndarray)
            (Señal suavizada, Señal normalizada)
        """
        smoothed = self.smooth_signal(signal)
        normalized = self.normalize_by_baseline(smoothed)
        return smoothed, normalized


def load_sensor_file(file_path: Path) -> Optional[pd.DataFrame]:
    """
    Carga un archivo de datos de sensores.
    
    Parámetros:
    -----------
    file_path : Path
        Ruta del archivo
    
    Retorna:
    --------
    pd.DataFrame or None
        DataFrame con datos o None si hay error
    """
    try:
        nombres_columnas = [
            'Humedad_%', 'Temperatura_C',
            'MQ3_1', 'MQ4_1', 'MQ6_1',
            'MQ3_2', 'MQ4_2', 'MQ6_2'
        ]
        
        df = pd.read_csv(file_path, sep=r'\s+', header=None, names=nombres_columnas)
        
        # Validar datos
        is_valid, issues = validate_sensor_data(df)
        if not is_valid:
            logger.warning(f"Problemas en {file_path.name}: {issues}")
        
        return df
    
    except Exception as e:
        logger.error(f"Error al cargar {file_path}: {e}")
        return None


def extract_features_from_file(file_path: Path, 
                               substance_label: str,
                               processor: Optional[SignalProcessor] = None) -> Optional[Dict]:
    """
    Extrae todas las características de un archivo de sensores.
    
    FASE 1-3 integrada:
    1. Ingesta: Carga el archivo
    2. Procesamiento: Suavizado + normalización
    3. Extracción: Calcula características
    
    Parámetros:
    -----------
    file_path : Path
        Ruta del archivo de sensores
    substance_label : str
        Etiqueta de la sustancia (ej: 'AQ', 'HQ', 'ETH')
    processor : SignalProcessor, optional
        Procesador de señales (se crea uno por defecto si no se proporciona)
    
    Retorna:
    --------
    dict or None
        Diccionario con características extraídas o None si hay error
    """
    if processor is None:
        processor = SignalProcessor()
    
    # FASE 1: Ingesta
    logger.info(f"[FASE 1] Ingesta: {file_path.name}")
    df_raw = load_sensor_file(file_path)
    
    if df_raw is None or df_raw.empty:
        return None
    
    # Diccionario de resultado
    result = {
        'Nombre_Archivo': file_path.name,
        'Ruta_Completa': str(file_path),
        'Calidad_Muestra': substance_label
    }
    
    # Obtener columnas de sensores
    sensor_cols = SENSOR_COLUMNS['sensors']
    
    # FASE 2 y 3: Procesamiento y extracción por cada sensor
    logger.info(f"[FASE 2-3] Procesamiento y extracción de características")
    
    for sensor in sensor_cols:
        if sensor not in df_raw.columns:
            logger.warning(f"Sensor {sensor} no encontrado en {file_path.name}")
            continue
        
        signal_raw = df_raw[sensor].values
        
        # Procesamiento
        smoothed, normalized = processor.process_signal(signal_raw)
        
        # Extracción
        features = processor.extract_features(normalized)
        
        # Guardar características con prefijo del sensor
        for feature_name, feature_value in features.items():
            key = f"{sensor}_{feature_name}"
            result[key] = feature_value
    
    logger.info(f" Características extraídas de {file_path.name}")
    return result


# ============================================================================
# FUNCIÓN PRINCIPAL (Para uso independiente)
# ============================================================================

def main():
    """
    Demuestra el uso del módulo de extracción de características.
    """
    logger.info("="*70)
    logger.info("DEMOSTRACIÓN: Extracción de Características")
    logger.info("="*70)
    
    # Crear procesador
    processor = SignalProcessor()
    logger.info(f"Procesador creado con fs={processor.sampling_frequency} Hz")
    
    # Demostración con señal sintética
    logger.info("\nGenerando señal de prueba...")
    t = np.linspace(0, 10, 1000)
    synthetic_signal = 100 + 50 * np.sin(2 * np.pi * 0.5 * t) + np.random.normal(0, 5, len(t))
    
    smoothed, normalized = processor.process_signal(synthetic_signal)
    features = processor.extract_features(normalized)
    
    logger.info(f"Características extraídas:")
    for name, value in features.items():
        logger.info(f"  {name}: {value:.6f}")
    
    # Generar gráfica de procesamiento
    logger.info("\nGenerando gráfica del procesamiento de señal...")
    output_dir = create_output_directory(DATA_PROCESSED_DIR / "visualizations")
    plot_signal_processing(
        signal_raw=synthetic_signal,
        signal_smoothed=smoothed,
        signal_normalized=normalized,
        time_axis=t,
        title="Demostración: Procesamiento de Señal Sintética",
        output_path=output_dir / "signal_processing_demo.png"
    )
    logger.info("Gráfica generada exitosamente")


if __name__ == '__main__':
    main()
