"""
===============================================================================
FASE 4: GENERACIÓN DEL DATASET MAESTRO (VERSIÓN 2)
===============================================================================

Este módulo genera el dataset maestro a partir de todos los archivos de
sensores disponibles. 

Compatibilidad V2:
- Recibe automáticamente las nuevas características segmentadas por ventanas
  temporales extraídas en la Fase 1-3.
- Escala dinámicamente el número de columnas resultantes en el CSV maestro.

===============================================================================
"""

import pandas as pd
from pathlib import Path
from typing import List, Tuple, Optional
import sys

# Importaciones correctas (mismo nivel)
from utils import setup_logging, get_files_recursive, extract_substance_label
from utils import print_data_summary, create_output_directory, plot_class_distribution, plot_feature_statistics
from phase_1_3_feature_extraction import (
    extract_features_from_file, extract_segments_from_file,
    SignalProcessor, PCAFeatureExtractor
)
from config import DATA_RAW_DIR, DATASET_MAESTRO_PATH, DATA_PROCESSED_DIR, FEATURE_MODE, PCA_CONFIG

logger = setup_logging(__name__)


class DatasetGenerator:
    """
    Genera el dataset maestro a partir de archivos de sensores.
    """
    
    def __init__(self, data_dir: Path = DATA_RAW_DIR):
        self.data_dir = Path(data_dir)
        self.processor = SignalProcessor()
        self.records = []
        self.stats = {
            'total_files': 0,
            'processed_files': 0,
            'failed_files': 0,
            'class_distribution': {}
        }
        self.pca_extractor = PCAFeatureExtractor(PCA_CONFIG) if FEATURE_MODE == 'pca_signal' else None
    
    def find_sensor_files(self) -> List[Path]:
        logger.info(f"Buscando archivos de sensores en: {self.data_dir}")
        files = get_files_recursive(self.data_dir, "*.txt")
        
        if not files:
            logger.warning(f"No se encontraron archivos .txt en {self.data_dir}")
            return []
        
        logger.info(f" Se encontraron {len(files)} archivos de sensores")
        return files
    
    def process_file(self, file_path: Path) -> Optional[dict]:
        label = extract_substance_label(file_path.name)

        if label is None:
            logger.warning(f"No se pudo identificar sustancia en: {file_path.name}")
            self.stats['failed_files'] += 1
            return None

        features = extract_features_from_file(
            file_path,
            substance_label=label,
            processor=self.processor
        )

        if features is None:
            self.stats['failed_files'] += 1
            return None

        self.stats['processed_files'] += 1
        return features

    def process_file_for_segments(self, file_path: Path) -> Optional[tuple]:
        """
        Modo PCA — extrae segmentos de señal en bruto (sin estadísticos).
        Retorna (filename, label, {sensor: {win_label: array}}) o None si hay error.
        """
        label = extract_substance_label(file_path.name)
        if label is None:
            logger.warning(f"No se pudo identificar sustancia en: {file_path.name}")
            self.stats['failed_files'] += 1
            return None

        result = extract_segments_from_file(file_path, label, self.processor)
        if result is None:
            self.stats['failed_files'] += 1
            return None

        _, sensor_segments = result
        self.stats['processed_files'] += 1
        return file_path.name, label, sensor_segments
    
    def generate_dataset(self, output_path: Optional[Path] = None) -> Optional[pd.DataFrame]:
        if output_path is None:
            output_path = DATASET_MAESTRO_PATH
        else:
            output_path = Path(output_path)
        
        create_output_directory(output_path.parent)
        
        logger.info("\n" + "="*70)
        logger.info("FASE 4: Generando Dataset Maestro (Soporte Multi-Ventana)")
        logger.info("="*70)
        
        files = self.find_sensor_files()
        self.stats['total_files'] = len(files)
        
        if not files:
            logger.error("No hay archivos para procesar")
            return None
        
        logger.info(f"\nProcesando {len(files)} archivos (modo: {FEATURE_MODE})...")

        if FEATURE_MODE == 'handcrafted':
            self._generate_handcrafted(files)
        elif FEATURE_MODE == 'pca_signal':
            self._generate_pca(files, output_path)
        else:
            logger.error(f"FEATURE_MODE desconocido: '{FEATURE_MODE}'. Usa 'handcrafted' o 'pca_signal'.")
            return None

        if not self.records:
            logger.error("No se pudieron extraer características de ningún archivo")
            return None
        
        logger.info("Creando DataFrame maestro...")
        # Pandas mapeará automáticamente todas las nuevas keys (ej: MQ3_1_w10-40_max) como columnas
        df_maestro = pd.DataFrame(self.records)
        
        if 'Calidad_Muestra' in df_maestro.columns:
            df_maestro.rename(columns={'Calidad_Muestra': 'Calidad_Vino'}, inplace=True)
        
        self._calculate_statistics(df_maestro)
        
        logger.info(f"\nGuardando dataset a: {output_path}")
        df_maestro.to_csv(output_path, index=False)
        logger.info(f" Dataset guardado exitosamente")
        
        self._print_summary(df_maestro, output_path)
        
        return df_maestro
    
    def _generate_handcrafted(self, files: list) -> None:
        """Una pasada: extrae estadísticos (max, AUC, slope) por archivo."""
        for i, file_path in enumerate(files, 1):
            if i % 10 == 0 or i == len(files):
                logger.info(f"Progreso: {i}/{len(files)} archivos procesados")
            features = self.process_file(file_path)
            if features is not None:
                self.records.append(features)

    def _generate_pca(self, files: list, output_path) -> None:
        """
        Dos pasadas:
          1. Recolectar segmentos de señal de todos los archivos.
          2. Ajustar PCA por (sensor, ventana) y proyectar cada segmento.
        """
        raw_data = []
        all_segments_by_key = {}

        logger.info("Pasada 1/2: recolectando segmentos de señal...")
        for i, file_path in enumerate(files, 1):
            if i % 10 == 0 or i == len(files):
                logger.info(f"  Progreso: {i}/{len(files)}")
            result = self.process_file_for_segments(file_path)
            if result is None:
                continue
            filename, label, sensor_segments = result
            raw_data.append((filename, label, sensor_segments))
            for sensor, windows in sensor_segments.items():
                for win_label, segment in windows.items():
                    key = f"{sensor}_{win_label}"
                    all_segments_by_key.setdefault(key, []).append(segment)

        if not raw_data:
            logger.error("No se pudieron extraer segmentos de ningún archivo")
            return

        logger.info(f"\nAjustando PCA sobre {len(raw_data)} muestras "
                    f"({len(all_segments_by_key)} combinaciones sensor×ventana)...")
        self.pca_extractor.fit(all_segments_by_key)

        pca_path = DATA_PROCESSED_DIR / "pca_transformers.pkl"
        self.pca_extractor.save(pca_path)

        ev_summary = self.pca_extractor.explained_variance_summary()
        for key, ratios in list(ev_summary.items())[:3]:
            logger.info(f"  {key}: {len(ratios)} PCs, varianza acumulada={ratios.sum()*100:.1f}%")

        logger.info("\nPasada 2/2: proyectando segmentos sobre PCs...")
        for filename, label, sensor_segments in raw_data:
            record = {'Nombre_Archivo': filename, 'Calidad_Muestra': label}
            for sensor, windows in sensor_segments.items():
                for win_label, segment in windows.items():
                    key = f"{sensor}_{win_label}"
                    if key not in self.pca_extractor.pca_models:
                        continue
                    pc_scores = self.pca_extractor.transform(segment, key)
                    for i, score in enumerate(pc_scores, 1):
                        record[f"{sensor}_{win_label}_pc{i}"] = float(score)
            self.records.append(record)

    def _calculate_statistics(self, df: pd.DataFrame) -> None:
        if 'Calidad_Vino' in df.columns:
            self.stats['class_distribution'] = df['Calidad_Vino'].value_counts().to_dict()
    
    def _print_summary(self, df: pd.DataFrame, output_path: Path) -> None:
        logger.info("\n" + "="*70)
        logger.info("RESUMEN DE LA FASE 4")
        logger.info("="*70)
        logger.info(f"Total de archivos encontrados: {self.stats['total_files']}")
        logger.info(f"Archivos procesados exitosamente: {self.stats['processed_files']}")
        logger.info(f"Archivos con error: {self.stats['failed_files']}")
        logger.info(f"\nDimensiones del dataset: {df.shape[0]} muestras × {df.shape[1]} características")
        
        if self.stats['class_distribution']:
            logger.info("\nDistribución de clases:")
            for clase, count in self.stats['class_distribution'].items():
                percentage = (count / len(df)) * 100
                logger.info(f"  {clase}: {count} ({percentage:.1f}%)")
        
        logger.info(f"\nNombres de características ({df.shape[1] - 3}):")
        feature_cols = [col for col in df.columns 
                        if col not in ['Nombre_Archivo', 'Ruta_Completa', 'Calidad_Vino']]
        for i, col in enumerate(feature_cols[:5], 1):
            logger.info(f"  {i}. {col}")
        if len(feature_cols) > 5:
            logger.info(f"  ... y {len(feature_cols) - 5} más")
        
        logger.info(f"\nArchivo guardado en: {output_path}")
        
        logger.info("\nGenerando visualizaciones del dataset...")
        viz_dir = create_output_directory(DATA_PROCESSED_DIR / "visualizations")
        
        try:
            plot_class_distribution(
                df,
                label_column='Calidad_Vino',
                output_path=viz_dir / "class_distribution.png"
            )
            plot_feature_statistics(
                df,
                feature_columns=feature_cols,
                output_path=viz_dir / "feature_statistics.png"
            )
            logger.info(" Visualizaciones generadas exitosamente")
        except Exception as e:
            logger.warning(f"No se pudieron generar visualizaciones: {e}")
        
        logger.info("="*70 + "\n")


def validate_dataset(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    issues = []
    
    if df.empty:
        issues.append("Dataset vacío")
        return False, issues
    
    required_cols = ['Nombre_Archivo', 'Calidad_Vino']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        issues.append(f"Faltan columnas requeridas: {missing_cols}")
    
    feature_cols = [col for col in df.columns 
                    if col not in ['Nombre_Archivo', 'Ruta_Completa', 'Calidad_Vino']]
    if len(feature_cols) < 10:
        issues.append(f"Muy pocas características: {len(feature_cols)}")
    
    null_counts = df.isnull().sum()
    if null_counts.any():
        null_cols = null_counts[null_counts > 0].index.tolist()
        issues.append(f"Columnas con valores nulos: {null_cols}")
    
    return len(issues) == 0, issues


def load_dataset(path: Path) -> Optional[pd.DataFrame]:
    try:
        logger.info(f"Cargando dataset desde: {path}")
        df = pd.read_csv(path)
        
        is_valid, issues = validate_dataset(df)
        
        if not is_valid:
            logger.warning(f"Problemas en dataset: {issues}")
        
        logger.info(f" Dataset cargado: {df.shape[0]} muestras, {df.shape[1]} características")
        return df
    
    except Exception as e:
        logger.error(f"Error al cargar dataset: {e}")
        return None


def main():
    try:
        generator = DatasetGenerator()
        df_maestro = generator.generate_dataset()
        
        if df_maestro is not None:
            print_data_summary(df_maestro, "Dataset Maestro Final")
            logger.info("[OK] Generacion completada exitosamente")
        else:
            logger.error("[ERROR] Error en la generacion del dataset")
            sys.exit(1)

    except Exception as e:
        logger.error(f"[ERROR] Error inesperado: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()