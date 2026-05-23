"""
===============================================================================
FASE 4: GENERACIÓN DEL DATASET MAESTRO - NARIZ ELECTRÓNICA
===============================================================================

Este módulo genera el dataset maestro a partir de todos los archivos de
sensores disponibles en el proyecto. Integra:

1. Búsqueda recursiva de archivos de sensores
2. Etiquetado automático según nombre del archivo
3. Extracción de características (usando FASE 1-3)
4. Generación del CSV maestro
5. Validación y estadísticas

===============================================================================
"""

import pandas as pd
from pathlib import Path
from typing import List, Tuple, Optional
import sys

from utils import setup_logging, get_files_recursive, extract_substance_label
from utils import print_data_summary, create_output_directory, plot_class_distribution, plot_feature_statistics
from phase_1_3_feature_extraction import extract_features_from_file, SignalProcessor
from config import DATA_RAW_DIR, DATASET_MAESTRO_PATH, DATA_PROCESSED_DIR

logger = setup_logging(__name__)


class DatasetGenerator:
    """
    Genera el dataset maestro a partir de archivos de sensores.
    """
    
    def __init__(self, data_dir: Path = DATA_RAW_DIR):
        """
        Inicializa el generador de dataset.
        
        Parámetros:
        -----------
        data_dir : Path
            Directorio donde buscar archivos de sensores
        """
        self.data_dir = Path(data_dir)
        self.processor = SignalProcessor()
        self.records = []
        self.stats = {
            'total_files': 0,
            'processed_files': 0,
            'failed_files': 0,
            'class_distribution': {}
        }
    
    def find_sensor_files(self) -> List[Path]:
        """
        Busca todos los archivos de sensores (.txt) en el directorio.
        
        Retorna:
        --------
        list of Path
            Lista de archivos de sensores encontrados
        """
        logger.info(f"Buscando archivos de sensores en: {self.data_dir}")
        
        files = get_files_recursive(self.data_dir, "*.txt")
        
        if not files:
            logger.warning(f"No se encontraron archivos .txt en {self.data_dir}")
            return []
        
        logger.info(f"✓ Se encontraron {len(files)} archivos de sensores")
        return files
    
    def process_file(self, file_path: Path) -> Optional[dict]:
        """
        Procesa un archivo individual.
        
        Parámetros:
        -----------
        file_path : Path
            Ruta del archivo a procesar
        
        Retorna:
        --------
        dict or None
            Características extraídas o None si hay error
        """
        # Extraer etiqueta de sustancia del nombre
        label = extract_substance_label(file_path.name)
        
        if label is None:
            logger.warning(f"No se pudo identificar sustancia en: {file_path.name}")
            self.stats['failed_files'] += 1
            return None
        
        # Extraer características
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
    
    def generate_dataset(self, output_path: Optional[Path] = None) -> Optional[pd.DataFrame]:
        """
        Genera el dataset maestro completo.
        
        Parámetros:
        -----------
        output_path : Path, optional
            Ruta donde guardar el CSV. Si es None, usa la configuración.
        
        Retorna:
        --------
        pd.DataFrame or None
            DataFrame maestro o None si hay error
        """
        if output_path is None:
            output_path = DATASET_MAESTRO_PATH
        else:
            output_path = Path(output_path)
        
        # Asegurar que el directorio existe
        create_output_directory(output_path.parent)
        
        logger.info("\n" + "="*70)
        logger.info("FASE 4: Generando Dataset Maestro")
        logger.info("="*70)
        
        # Buscar archivos
        files = self.find_sensor_files()
        self.stats['total_files'] = len(files)
        
        if not files:
            logger.error("No hay archivos para procesar")
            return None
        
        # Procesar archivos
        logger.info(f"\nProcesando {len(files)} archivos...")
        for i, file_path in enumerate(files, 1):
            # Mostrar progreso cada 10 archivos
            if i % 10 == 0 or i == len(files):
                logger.info(f"Progreso: {i}/{len(files)} archivos procesados")
            
            features = self.process_file(file_path)
            if features is not None:
                self.records.append(features)
        
        # Validar que se procesaron registros
        if not self.records:
            logger.error("No se pudieron extraer características de ningún archivo")
            return None
        
        # Crear DataFrame
        logger.info("Creando DataFrame maestro...")
        df_maestro = pd.DataFrame(self.records)
        
        # Renombrar columna para consistencia
        if 'Calidad_Muestra' in df_maestro.columns:
            df_maestro.rename(columns={'Calidad_Muestra': 'Calidad_Vino'}, inplace=True)
        
        # Calcular estadísticas
        self._calculate_statistics(df_maestro)
        
        # Guardar a CSV
        logger.info(f"\nGuardando dataset a: {output_path}")
        df_maestro.to_csv(output_path, index=False)
        logger.info(f"✓ Dataset guardado exitosamente")
        
        # Mostrar resumen
        self._print_summary(df_maestro, output_path)
        
        return df_maestro
    
    def _calculate_statistics(self, df: pd.DataFrame) -> None:
        """
        Calcula estadísticas del dataset.
        
        Parámetros:
        -----------
        df : pd.DataFrame
            Dataset a analizar
        """
        if 'Calidad_Vino' in df.columns:
            self.stats['class_distribution'] = df['Calidad_Vino'].value_counts().to_dict()
    
    def _print_summary(self, df: pd.DataFrame, output_path: Path) -> None:
        """
        Imprime un resumen de la generación del dataset.
        
        Parámetros:
        -----------
        df : pd.DataFrame
            Dataset generado
        output_path : Path
            Ruta del archivo guardado
        """
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
        
        # Generar visualizaciones
        logger.info("\nGenerando visualizaciones del dataset...")
        viz_dir = create_output_directory(DATA_PROCESSED_DIR / "visualizations")
        
        try:
            # Gráfica de distribución de clases
            plot_class_distribution(
                df,
                label_column='Calidad_Vino',
                output_path=viz_dir / "class_distribution.png"
            )
            
            # Gráfica de estadísticas de características
            feature_cols = [col for col in df.columns 
                           if col not in ['Nombre_Archivo', 'Ruta_Completa', 'Calidad_Vino']]
            plot_feature_statistics(
                df,
                feature_columns=feature_cols,
                output_path=viz_dir / "feature_statistics.png"
            )
            
            logger.info("✓ Visualizaciones generadas exitosamente")
        except Exception as e:
            logger.warning(f"No se pudieron generar visualizaciones: {e}")
        
        logger.info("="*70 + "\n")


# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================

def validate_dataset(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    """
    Valida la integridad del dataset maestro.
    
    Parámetros:
    -----------
    df : pd.DataFrame
        Dataset a validar
    
    Retorna:
    --------
    tuple of (bool, list)
        (Es válido, Lista de problemas)
    """
    issues = []
    
    # Verificar que no esté vacío
    if df.empty:
        issues.append("Dataset vacío")
        return False, issues
    
    # Verificar columnas requeridas
    required_cols = ['Nombre_Archivo', 'Calidad_Vino']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        issues.append(f"Faltan columnas requeridas: {missing_cols}")
    
    # Verificar que haya características
    feature_cols = [col for col in df.columns 
                   if col not in ['Nombre_Archivo', 'Ruta_Completa', 'Calidad_Vino']]
    if len(feature_cols) < 10:
        issues.append(f"Muy pocas características: {len(feature_cols)}")
    
    # Verificar valores nulos
    null_counts = df.isnull().sum()
    if null_counts.any():
        null_cols = null_counts[null_counts > 0].index.tolist()
        issues.append(f"Columnas con valores nulos: {null_cols}")
    
    return len(issues) == 0, issues


def load_dataset(path: Path) -> Optional[pd.DataFrame]:
    """
    Carga un dataset maestro generado previamente.
    
    Parámetros:
    -----------
    path : Path
        Ruta del archivo CSV
    
    Retorna:
    --------
    pd.DataFrame or None
        Dataset cargado o None si hay error
    """
    try:
        logger.info(f"Cargando dataset desde: {path}")
        df = pd.read_csv(path)
        
        is_valid, issues = validate_dataset(df)
        
        if not is_valid:
            logger.warning(f"Problemas en dataset: {issues}")
        
        logger.info(f"✓ Dataset cargado: {df.shape[0]} muestras, {df.shape[1]} características")
        return df
    
    except Exception as e:
        logger.error(f"Error al cargar dataset: {e}")
        return None


# ============================================================================
# FUNCIÓN PRINCIPAL
# ============================================================================

def main():
    """
    Ejecuta la generación del dataset maestro.
    """
    try:
        # Crear generador
        generator = DatasetGenerator()
        
        # Generar dataset
        df_maestro = generator.generate_dataset()
        
        if df_maestro is not None:
            # Mostrar resumen detallado
            print_data_summary(df_maestro, "Dataset Maestro Final")
            logger.info("✅ Generación completada exitosamente")
        else:
            logger.error("❌ Error en la generación del dataset")
            sys.exit(1)
    
    except Exception as e:
        logger.error(f"❌ Error inesperado: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
