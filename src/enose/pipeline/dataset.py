"""
Generador del dataset maestro (Phase 4).

Orquesta la ingesta, el procesamiento de señal y la extracción de características
sobre todos los archivos de sensor disponibles. Soporta dos modos:
  - handcrafted : estadísticos (max, AUC, slope) por ventana
  - pca_signal  : proyección PCA por (sensor × ventana)
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple
import sys

import pandas as pd

from enose.config import (
    DATA_PROCESSED_DIR, DATA_RAW_DIR, DATASET_MAESTRO_PATH,
    FEATURE_MODE, PCA_CONFIG, SENSOR_COLUMNS,
)
from enose.features.handcrafted import HandcraftedExtractor
from enose.features.pca import PCAFeatureExtractor
from enose.io.reader import extract_substance_label, get_files_recursive, load_sensor_file
from enose.signal.processor import SignalProcessor
from enose.utils import (
    create_output_directory, plot_class_distribution, plot_feature_statistics,
    print_data_summary, setup_logging,
)

logger = setup_logging(__name__)


class DatasetGenerator:
    """Genera el dataset maestro a partir de los archivos de sensor."""

    def __init__(self, data_dir: Path = DATA_RAW_DIR) -> None:
        self.data_dir = Path(data_dir)
        self.processor = SignalProcessor()
        self.handcrafted = HandcraftedExtractor()
        self.records: List[dict] = []
        self.stats: Dict = {"total_files": 0, "processed": 0, "failed": 0, "classes": {}}
        self.pca_extractor = PCAFeatureExtractor(PCA_CONFIG) if FEATURE_MODE == "pca_signal" else None

    # ------------------------------------------------------------------
    # Entrada principal
    # ------------------------------------------------------------------

    def generate_dataset(self, output_path: Optional[Path] = None) -> Optional[pd.DataFrame]:
        output_path = Path(output_path) if output_path else DATASET_MAESTRO_PATH
        create_output_directory(output_path.parent)

        logger.info("=" * 70)
        logger.info("FASE 4: Generando Dataset Maestro")
        logger.info("=" * 70)

        files = self._find_sensor_files()
        self.stats["total_files"] = len(files)
        if not files:
            logger.error("No hay archivos .txt para procesar")
            return None

        logger.info(f"Procesando {len(files)} archivos (modo: {FEATURE_MODE})...")

        if FEATURE_MODE == "handcrafted":
            self._generate_handcrafted(files)
        elif FEATURE_MODE == "pca_signal":
            self._generate_pca(files)
        else:
            logger.error(f"FEATURE_MODE desconocido: '{FEATURE_MODE}'")
            return None

        if not self.records:
            logger.error("No se extrajeron características de ningún archivo")
            return None

        df = pd.DataFrame(self.records)
        if "Calidad_Muestra" in df.columns:
            df.rename(columns={"Calidad_Muestra": "Calidad_Vino"}, inplace=True)

        self.stats["classes"] = df["Calidad_Vino"].value_counts().to_dict() if "Calidad_Vino" in df.columns else {}

        df.to_csv(output_path, index=False)
        self._print_summary(df, output_path)
        return df

    # ------------------------------------------------------------------
    # Estrategias de extracción
    # ------------------------------------------------------------------

    def _generate_handcrafted(self, files: List[Path]) -> None:
        for i, fp in enumerate(files, 1):
            if i % 10 == 0 or i == len(files):
                logger.info(f"  Progreso: {i}/{len(files)}")
            record = self._process_file_handcrafted(fp)
            if record:
                self.records.append(record)

    def _generate_pca(self, files: List[Path]) -> None:
        # Pasada 1: recolectar segmentos
        raw_data = []
        all_segments_by_key: Dict[str, List] = {}

        logger.info("Pasada 1/2: recolectando segmentos de señal...")
        for i, fp in enumerate(files, 1):
            if i % 10 == 0 or i == len(files):
                logger.info(f"  {i}/{len(files)}")
            result = self._extract_segments(fp)
            if result is None:
                continue
            filename, label, sensor_segments = result
            raw_data.append((filename, label, sensor_segments))
            for sensor, windows in sensor_segments.items():
                for win_label, segment in windows.items():
                    all_segments_by_key.setdefault(f"{sensor}_{win_label}", []).append(segment)

        if not raw_data:
            logger.error("No se pudieron extraer segmentos")
            return

        # Ajustar PCA
        logger.info(f"Ajustando PCA sobre {len(raw_data)} muestras...")
        self.pca_extractor.fit(all_segments_by_key)
        pca_path = DATA_PROCESSED_DIR / "pca_transformers.pkl"
        self.pca_extractor.save(pca_path)

        for key, ratios in list(self.pca_extractor.explained_variance_summary().items())[:3]:
            logger.info(f"  {key}: {len(ratios)} PCs, var acumulada={ratios.sum()*100:.1f}%")

        # Pasada 2: proyectar
        logger.info("Pasada 2/2: proyectando sobre PCs...")
        for filename, label, sensor_segments in raw_data:
            record = {"Nombre_Archivo": filename, "Calidad_Muestra": label}
            for sensor, windows in sensor_segments.items():
                for win_label, segment in windows.items():
                    key = f"{sensor}_{win_label}"
                    if key not in self.pca_extractor.pca_models:
                        continue
                    scores = self.pca_extractor.transform(segment, key)
                    for i, score in enumerate(scores, 1):
                        record[f"{key}_pc{i}"] = float(score)
            self.records.append(record)

    # ------------------------------------------------------------------
    # Helpers de procesamiento por archivo
    # ------------------------------------------------------------------

    def _process_file_handcrafted(self, file_path: Path) -> Optional[dict]:
        label = extract_substance_label(file_path.name)
        if label is None:
            self.stats["failed"] += 1
            return None

        df_raw = load_sensor_file(file_path)
        if df_raw is None or df_raw.empty:
            self.stats["failed"] += 1
            return None

        features = self.handcrafted.extract_from_file_data(df_raw)
        self.stats["processed"] += 1
        return {"Nombre_Archivo": file_path.name, "Calidad_Muestra": label, **features}

    def _extract_segments(self, file_path: Path) -> Optional[Tuple]:
        label = extract_substance_label(file_path.name)
        if label is None:
            self.stats["failed"] += 1
            return None

        df_raw = load_sensor_file(file_path)
        if df_raw is None or df_raw.empty:
            self.stats["failed"] += 1
            return None

        sensor_segments: Dict = {}
        for sensor in SENSOR_COLUMNS["sensors"]:
            if sensor not in df_raw.columns:
                continue
            _, normalized = self.processor.process_signal(df_raw[sensor].values)
            segs = self.processor.get_signal_segments(normalized)
            if segs:
                sensor_segments[sensor] = segs

        if not sensor_segments:
            self.stats["failed"] += 1
            return None

        self.stats["processed"] += 1
        return file_path.name, label, sensor_segments

    def _find_sensor_files(self) -> List[Path]:
        files = get_files_recursive(self.data_dir, "*.txt")
        logger.info(f"Archivos .txt encontrados: {len(files)}")
        return files

    def _print_summary(self, df: pd.DataFrame, output_path: Path) -> None:
        logger.info("=" * 70)
        logger.info(f"Total archivos: {self.stats['total_files']}")
        logger.info(f"Procesados: {self.stats['processed']}  |  Errores: {self.stats['failed']}")
        logger.info(f"Dataset: {df.shape[0]} muestras × {df.shape[1]} características")
        if self.stats["classes"]:
            for cls, n in self.stats["classes"].items():
                logger.info(f"  {cls}: {n} ({n/len(df)*100:.1f}%)")
        logger.info(f"Guardado en: {output_path}")

        viz_dir = create_output_directory(DATA_PROCESSED_DIR / "visualizations")
        feature_cols = [c for c in df.columns if c not in ["Nombre_Archivo", "Ruta_Completa", "Calidad_Vino"]]
        try:
            plot_class_distribution(df, label_column="Calidad_Vino", output_path=viz_dir / "class_distribution.png")
            plot_feature_statistics(df, feature_columns=feature_cols, output_path=viz_dir / "feature_statistics.png")
        except Exception as e:
            logger.warning(f"Visualizaciones fallidas: {e}")
        logger.info("=" * 70)


# ---------------------------------------------------------------------------
# Funciones utilitarias
# ---------------------------------------------------------------------------

def validate_dataset(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    issues = []
    if df.empty:
        return False, ["Dataset vacío"]

    for col in ["Nombre_Archivo", "Calidad_Vino"]:
        if col not in df.columns:
            issues.append(f"Falta columna requerida: {col}")

    feature_cols = [c for c in df.columns if c not in ["Nombre_Archivo", "Ruta_Completa", "Calidad_Vino"]]
    if len(feature_cols) < 10:
        issues.append(f"Muy pocas características: {len(feature_cols)}")

    null_cols = df.columns[df.isnull().any()].tolist()
    if null_cols:
        issues.append(f"Columnas con NaN: {null_cols}")

    return len(issues) == 0, issues


def load_dataset(path: Path) -> Optional[pd.DataFrame]:
    try:
        df = pd.read_csv(path)
        is_valid, issues = validate_dataset(df)
        if not is_valid:
            logger.warning(f"Problemas en dataset: {issues}")
        logger.info(f"Dataset cargado: {df.shape[0]} muestras, {df.shape[1]} características")
        return df
    except Exception as e:
        logger.error(f"Error al cargar dataset: {e}")
        return None


def main():
    generator = DatasetGenerator()
    df = generator.generate_dataset()
    if df is not None:
        print_data_summary(df, "Dataset Maestro Final")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
