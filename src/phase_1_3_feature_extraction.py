"""
===============================================================================
FASE 1-3: EXTRACCIÓN DE CARACTERÍSTICAS (VERSIÓN 2 - MEJORADA)
===============================================================================

Este módulo implementa el motor de extracción de características actualizado:

FASE 1: Ingesta de datos (Lectura y validación de CSV)
FASE 2: Procesamiento de señales
  - Suavizado avanzado con filtro Savitzky-Golay (preserva picos y pendientes)
  - Normalización termodinámica por línea base (R0 - Rs) / R0
FASE 3: Extracción de características por VENTANAS TEMPORALES
  - Extrae Máximo, AUC y Pendiente, segmentando la señal en las 
    fases de inyección y limpieza (basado en referencias bibliográficas).

===============================================================================
"""

import pickle
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, Optional, Tuple, List
from scipy.signal import savgol_filter
from sklearn.decomposition import PCA

# Importaciones correctas (mismo nivel)
from utils import setup_logging, validate_sensor_data, plot_signal_processing, create_output_directory
from config import SENSOR_COLUMNS, SIGNAL_PROCESSING_V2, DATA_PROCESSED_DIR, PCA_CONFIG

logger = setup_logging(__name__)


class SignalProcessor:
    """
    Procesa señales de sensores de la nariz electrónica.
    Realiza suavizado (Savitzky-Golay), normalización y extracción por ventanas.
    """
    
    def __init__(self, 
                 sampling_frequency: float = None,
                 savgol_window: int = None,
                 savgol_polyorder: int = None,
                 baseline_seconds: float = None,
                 time_windows: Optional[List[Tuple[float, float]]] = None):
        """
        Parámetros:
        -----------
        sampling_frequency : Frecuencia de muestreo en Hz (si None, usa config)
        savgol_window : Tamaño de la ventana para Savitzky-Golay (si None, usa config)
        savgol_polyorder : Orden del polinomio (si None, usa config)
        baseline_seconds : Segundos iniciales como línea base (si None, usa config)
        time_windows : Lista de tuplas (inicio_seg, fin_seg) (si None, usa config)
        """
        # Usar config si no se proporciona
        config = SIGNAL_PROCESSING_V2
        
        self.sampling_frequency = sampling_frequency or config['sampling_frequency']
        self.savgol_window = (savgol_window or config['savgol_window'])
        self.savgol_polyorder = savgol_polyorder or config['savgol_polyorder']
        self.baseline_seconds = baseline_seconds or config['baseline_seconds']
        self.time_windows = time_windows or config['time_windows']
        
        # Validar que savgol_window sea impar
        if self.savgol_window % 2 == 0:
            self.savgol_window += 1
        
        self.dt = 1.0 / self.sampling_frequency
        self.baseline_samples = int(self.baseline_seconds * self.sampling_frequency)
    
    def smooth_signal(self, signal: np.ndarray) -> np.ndarray:
        if len(signal) < self.savgol_window:
            logger.warning("La señal es demasiado corta para el filtro. Devolviendo señal original.")
            return signal
            
        smoothed = savgol_filter(signal, window_length=self.savgol_window, polyorder=self.savgol_polyorder)
        return smoothed
    
    def normalize_by_baseline(self, signal: np.ndarray) -> np.ndarray:
        """
        Normaliza una señal por su línea base usando cambio fraccional.
        Fórmula: (R0 - Rs) / R0
        """
        if len(signal) < self.baseline_samples:
            logger.warning("Señal más corta que línea base. Usando toda la señal como línea base.")
            baseline_samples = len(signal)
        else:
            baseline_samples = self.baseline_samples
        
        R0 = np.mean(signal[:baseline_samples])
        
        if R0 == 0:
            logger.warning("R0 = 0. Usando Z-score como normalización alternativa.")
            return (signal - np.mean(signal)) / (np.std(signal) + 1e-10)
        
        normalized = (R0 - signal) / R0
        return normalized
    
    def extract_features(self, signal: np.ndarray) -> Dict[str, float]:
        """
        Extrae características matemáticas segmentadas por ventanas de tiempo.
        """
        features = {}
        total_length_sec = len(signal) * self.dt
        
        for start_sec, end_sec in self.time_windows:
            # Ignorar ventanas que caen completamente fuera de la señal
            if start_sec >= total_length_sec:
                continue
                
            start_idx = int(start_sec * self.sampling_frequency)
            end_idx = int(end_sec * self.sampling_frequency)
            
            # Asegurar que los índices no se salgan del array
            start_idx = max(0, min(start_idx, len(signal) - 1))
            end_idx = max(0, min(end_idx, len(signal)))
            
            segment = signal[start_idx:end_idx]
            
            if len(segment) == 0:
                continue
                
            # Etiqueta para nombrar la columna en el dataset final (ej. "w10-40")
            win_label = f"w{int(start_sec)}-{int(end_sec)}"
            
            # Extracción de métricas para este segmento específico
            features[f'{win_label}_max'] = float(np.max(segment))
            features[f'{win_label}_auc'] = float(np.trapezoid(segment, dx=self.dt))
            
            if len(segment) > 1:
                derivatives = np.diff(segment) / self.dt
                features[f'{win_label}_slope'] = float(np.max(np.abs(derivatives)))
            else:
                features[f'{win_label}_slope'] = 0.0
                
        return features
    
    def process_signal(self, signal: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Procesa una señal completa (suavizado + normalización)."""
        smoothed = self.smooth_signal(signal)
        normalized = self.normalize_by_baseline(smoothed)
        return smoothed, normalized

    def get_signal_segments(self, signal: np.ndarray) -> Dict[str, np.ndarray]:
        """
        Devuelve los segmentos de señal normalizada por ventana temporal (modo PCA).
        A diferencia de extract_features, devuelve el array crudo en lugar de estadísticos.
        """
        segments = {}
        total_length_sec = len(signal) * self.dt

        for start_sec, end_sec in self.time_windows:
            if start_sec >= total_length_sec:
                continue

            start_idx = int(start_sec * self.sampling_frequency)
            end_idx = int(end_sec * self.sampling_frequency)
            start_idx = max(0, min(start_idx, len(signal) - 1))
            end_idx = max(0, min(end_idx, len(signal)))

            segment = signal[start_idx:end_idx]
            if len(segment) == 0:
                continue

            win_label = f"w{int(start_sec)}-{int(end_sec)}"
            segments[win_label] = segment

        return segments


def load_sensor_file(file_path: Path) -> Optional[pd.DataFrame]:
    """Carga un archivo de datos de sensores."""
    try:
        nombres_columnas = ['Humedad_%', 'Temperatura_C', 'MQ3_1', 'MQ4_1', 'MQ6_1', 'MQ3_2', 'MQ4_2', 'MQ6_2']
        df = pd.read_csv(file_path, sep=r'\s+', header=None, names=nombres_columnas)
        
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
    FASE 1-3 integrada: Ingesta, Procesamiento y Extracción por Ventanas.
    """
    if processor is None:
        processor = SignalProcessor()
    
    logger.info(f"[FASE 1] Ingesta: {file_path.name}")
    df_raw = load_sensor_file(file_path)
    
    if df_raw is None or df_raw.empty:
        return None
    
    result = {
        'Nombre_Archivo': file_path.name,
        'Ruta_Completa': str(file_path),
        'Calidad_Muestra': substance_label
    }
    
    sensor_cols = SENSOR_COLUMNS['sensors']
    logger.info(f"[FASE 2-3] Procesamiento y extracción por ventanas temporales")
    
    for sensor in sensor_cols:
        if sensor not in df_raw.columns:
            continue
            
        signal_raw = df_raw[sensor].values
        smoothed, normalized = processor.process_signal(signal_raw)
        features = processor.extract_features(normalized)
        
        # Guarda las características indicando Sensor + Ventana + Métrica (ej: MQ3_1_w10-40_max)
        for feature_name, feature_value in features.items():
            key = f"{sensor}_{feature_name}"
            result[key] = feature_value
            
    return result

class PCAFeatureExtractor:
    """
    Ajusta un PCA independiente por cada combinación (sensor, ventana temporal).
    Se ajusta sobre todos los archivos del dataset (Phase 4) y luego proyecta
    cada segmento de señal sobre sus componentes principales.

    Nomenclatura de columnas resultantes: {sensor}_{win_label}_pc{n}
    Ejemplo: MQ3_1_w2-10_pc1, MQ3_1_w2-10_pc2
    """

    def __init__(self, config: dict = None):
        cfg = config or PCA_CONFIG
        self.n_components = cfg.get('n_components')
        self.explained_variance_threshold = cfg.get('explained_variance_threshold', 0.95)
        self.whiten = cfg.get('whiten', False)
        self.pca_models: Dict[str, PCA] = {}
        self.segment_lengths: Dict[str, int] = {}
        self.is_fitted = False

    def _pad_truncate(self, signal: np.ndarray, length: int) -> np.ndarray:
        """Iguala la longitud de un segmento por truncado o relleno con el último valor."""
        if len(signal) >= length:
            return signal[:length]
        pad_value = signal[-1] if len(signal) > 0 else 0.0
        return np.concatenate([signal, np.full(length - len(signal), pad_value)])

    def fit(self, all_segments: Dict[str, List[np.ndarray]]) -> None:
        """
        Ajusta un PCA por clave (sensor_ventana) sobre la colección completa de segmentos.

        Parámetros
        ----------
        all_segments : {key: [array_muestra_1, array_muestra_2, ...]}
        """
        for key, segments in all_segments.items():
            lengths = [len(s) for s in segments]
            # Longitud fija = la más frecuente (robusta a señales ligeramente más cortas)
            fixed_length = max(set(lengths), key=lengths.count)
            self.segment_lengths[key] = fixed_length

            X = np.array([self._pad_truncate(s, fixed_length) for s in segments])

            n_comp = self.n_components if self.n_components is not None \
                     else self.explained_variance_threshold
            max_possible = min(X.shape[0], X.shape[1])
            if isinstance(n_comp, int):
                n_comp = min(n_comp, max_possible)

            pca = PCA(n_components=n_comp, whiten=self.whiten)
            pca.fit(X)
            self.pca_models[key] = pca

        self.is_fitted = True
        logger.info(f"PCA ajustado: {len(self.pca_models)} modelos "
                    f"({list(self.pca_models.keys())[:3]}...)")

    def transform(self, segment: np.ndarray, key: str) -> np.ndarray:
        """Proyecta un segmento sobre los PCs del modelo correspondiente."""
        pca = self.pca_models[key]
        fixed_length = self.segment_lengths[key]
        padded = self._pad_truncate(segment, fixed_length)
        return pca.transform(padded.reshape(1, -1))[0]

    def explained_variance_summary(self) -> Dict[str, np.ndarray]:
        return {key: pca.explained_variance_ratio_ for key, pca in self.pca_models.items()}

    def save(self, path: Path) -> None:
        with open(path, 'wb') as f:
            pickle.dump({'pca_models': self.pca_models,
                         'segment_lengths': self.segment_lengths}, f)
        logger.info(f"PCA transformers guardados en: {path}")

    @classmethod
    def load(cls, path: Path, config: dict = None) -> 'PCAFeatureExtractor':
        extractor = cls(config)
        with open(path, 'rb') as f:
            data = pickle.load(f)
        extractor.pca_models = data['pca_models']
        extractor.segment_lengths = data['segment_lengths']
        extractor.is_fitted = True
        return extractor


def extract_segments_from_file(
    file_path: Path,
    substance_label: str,
    processor: Optional[SignalProcessor] = None
) -> Optional[Tuple[str, Dict[str, Dict[str, np.ndarray]]]]:
    """
    Modo PCA — equivalente a extract_features_from_file pero devuelve arrays de señal,
    no estadísticos. Necesario para ajustar PCAFeatureExtractor en Phase 4.

    Retorna
    -------
    (substance_label, {sensor: {win_label: np.ndarray}})  o  None si hay error
    """
    if processor is None:
        processor = SignalProcessor()

    df_raw = load_sensor_file(file_path)
    if df_raw is None or df_raw.empty:
        return None

    sensor_segments: Dict[str, Dict[str, np.ndarray]] = {}
    for sensor in SENSOR_COLUMNS['sensors']:
        if sensor not in df_raw.columns:
            continue
        signal_raw = df_raw[sensor].values
        _, normalized = processor.process_signal(signal_raw)
        segments = processor.get_signal_segments(normalized)
        if segments:
            sensor_segments[sensor] = segments

    if not sensor_segments:
        return None

    return substance_label, sensor_segments


def main():
    # Código de demostración mantenido igual que en V1
    pass

if __name__ == '__main__':
    main()