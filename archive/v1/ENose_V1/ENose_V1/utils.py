"""
===============================================================================
UTILIDADES Y FUNCIONES AUXILIARES - NARIZ ELECTRÓNICA
===============================================================================

Este módulo contiene funciones reutilizables para:
- Manejo de archivos y rutas
- Validación de datos
- Logging
- Visualización de resultados

===============================================================================
"""

import logging
from pathlib import Path
from typing import List, Optional, Union
import numpy as np
import pandas as pd

from config import LOGGING_CONFIG, SENSOR_COLUMNS


# ============================================================================
# CONFIGURACIÓN DE LOGGING
# ============================================================================

def setup_logging(name: str = __name__) -> logging.Logger:
    """
    Configura y retorna un logger para el módulo.
    
    Parámetros:
    -----------
    name : str
        Nombre del logger (típicamente __name__)
    
    Retorna:
    --------
    logging.Logger
        Logger configurado
    """
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        logger.setLevel(LOGGING_CONFIG['level'])
        
        # Handler para consola
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(LOGGING_CONFIG['format']))
        logger.addHandler(console_handler)
        
        # Handler para archivo
        try:
            file_handler = logging.FileHandler(LOGGING_CONFIG['log_file'])
            file_handler.setFormatter(logging.Formatter(LOGGING_CONFIG['format']))
            logger.addHandler(file_handler)
        except Exception as e:
            logger.warning(f"No se pudo crear archivo de log: {e}")
    
    return logger


# ============================================================================
# VALIDACIÓN DE DATOS Y ARCHIVOS
# ============================================================================

def validate_file_path(file_path: Union[str, Path]) -> bool:
    """
    Valida que un archivo exista y sea legible.
    
    Parámetros:
    -----------
    file_path : str or Path
        Ruta del archivo a validar
    
    Retorna:
    --------
    bool
        True si el archivo es válido, False en caso contrario
    """
    path = Path(file_path)
    return path.exists() and path.is_file() and path.stat().st_size > 0


def validate_dataframe(df: pd.DataFrame, expected_columns: Optional[List[str]] = None) -> bool:
    """
    Valida que un DataFrame sea válido.
    
    Parámetros:
    -----------
    df : pd.DataFrame
        DataFrame a validar
    expected_columns : list, optional
        Columnas esperadas
    
    Retorna:
    --------
    bool
        True si el DataFrame es válido
    """
    if df is None or df.empty:
        return False
    
    if expected_columns:
        missing_cols = set(expected_columns) - set(df.columns)
        if missing_cols:
            return False
    
    return True


# ============================================================================
# FUNCIONES UTILITARIAS DE ARCHIVOS
# ============================================================================

def get_files_by_pattern(directory: Union[str, Path], pattern: str) -> List[Path]:
    """
    Obtiene archivos de un directorio que coincidan con un patrón.
    
    Parámetros:
    -----------
    directory : str or Path
        Directorio donde buscar
    pattern : str
        Patrón de búsqueda (ej: '*.txt')
    
    Retorna:
    --------
    list of Path
        Lista de archivos que coinciden
    """
    path = Path(directory)
    if not path.exists():
        return []
    return sorted(list(path.glob(pattern)))


def get_files_recursive(directory: Union[str, Path], pattern: str) -> List[Path]:
    """
    Obtiene archivos recursivamente en un directorio y subdirectorios.
    
    Parámetros:
    -----------
    directory : str or Path
        Directorio raíz de búsqueda
    pattern : str
        Patrón de búsqueda (ej: '*.txt')
    
    Retorna:
    --------
    list of Path
        Lista de archivos que coinciden
    """
    path = Path(directory)
    if not path.exists():
        return []
    return sorted(list(path.rglob(pattern)))


def extract_substance_label(filename: str) -> Optional[str]:
    """
    Extrae la etiqueta de sustancia del nombre del archivo.
    
    Parámetros:
    -----------
    filename : str
        Nombre del archivo
    
    Retorna:
    --------
    str or None
        Etiqueta de la sustancia (ej: 'AQ', 'HQ', 'ETH') o None si no coincide
    
    Ejemplos:
    ---------
    >>> extract_substance_label('AQ_Wine01-B01_R01.txt')
    'AQ'
    >>> extract_substance_label('Ethanol_C1_R01.txt')
    'ETH'
    """
    filename_upper = filename.upper()
    
    from config import SUBSTANCE_LABELS
    
    for key, label in SUBSTANCE_LABELS.items():
        if key.replace('_', '') in filename_upper.replace('_', ''):
            return label
    
    return None


# ============================================================================
# FUNCIONES DE VALIDACIÓN DE SENSORES
# ============================================================================

def validate_sensor_data(df: pd.DataFrame) -> tuple[bool, List[str]]:
    """
    Valida que los datos de sensores sean válidos.
    
    Parámetros:
    -----------
    df : pd.DataFrame
        DataFrame con datos de sensores
    
    Retorna:
    --------
    tuple of (bool, list)
        (Es válido, Lista de problemas encontrados)
    """
    issues = []
    
    # Verificar columnas
    required_cols = SENSOR_COLUMNS['sensors']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        issues.append(f"Faltan columnas: {missing_cols}")
    
    # Verificar valores numéricos
    for col in required_cols:
        if col in df.columns:
            if not np.issubdtype(df[col].dtype, np.number):
                issues.append(f"Columna {col} no es numérica")
            if df[col].isnull().any():
                issues.append(f"Columna {col} tiene valores nulos")
            if np.isinf(df[col]).any():
                issues.append(f"Columna {col} tiene valores infinitos")
    
    return len(issues) == 0, issues


# ============================================================================
# FUNCIONES DE ESTADÍSTICAS Y ANÁLISIS
# ============================================================================

def print_data_summary(df: pd.DataFrame, title: str = "Resumen de Datos") -> None:
    """
    Imprime un resumen estadístico de los datos.
    
    Parámetros:
    -----------
    df : pd.DataFrame
        DataFrame a resumir
    title : str
        Título del resumen
    """
    print(f"\n{'='*70}")
    print(f"{title:^70}")
    print(f"{'='*70}")
    print(f"Dimensiones: {df.shape[0]} filas × {df.shape[1]} columnas")
    print(f"\nTipos de datos:\n{df.dtypes}")
    print(f"\nValores faltantes:\n{df.isnull().sum()}")
    if 'Calidad_Vino' in df.columns or 'Calidad_Muestra' in df.columns:
        label_col = 'Calidad_Vino' if 'Calidad_Vino' in df.columns else 'Calidad_Muestra'
        print(f"\nDistribución de clases:\n{df[label_col].value_counts()}")
    print(f"{'='*70}\n")


# ============================================================================
# FUNCIONES DE VISUALIZACIÓN
# ============================================================================

def create_output_directory(path: Union[str, Path]) -> Path:
    """
    Crea un directorio si no existe.
    
    Parámetros:
    -----------
    path : str or Path
        Ruta del directorio
    
    Retorna:
    --------
    Path
        Ruta del directorio creado
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


# ============================================================================
# FUNCIONES DE VISUALIZACIÓN CON MATPLOTLIB Y SEABORN
# ============================================================================

def plot_signal_processing(signal_raw: np.ndarray, 
                          signal_smoothed: np.ndarray,
                          signal_normalized: np.ndarray,
                          time_axis: Optional[np.ndarray] = None,
                          title: str = "Procesamiento de Señal",
                          output_path: Optional[Path] = None) -> None:
    """
    Visualiza el proceso de transformación de una señal.
    
    Parámetros:
    -----------
    signal_raw : np.ndarray
        Señal original sin procesar
    signal_smoothed : np.ndarray
        Señal después de suavizado
    signal_normalized : np.ndarray
        Señal después de normalización
    time_axis : np.ndarray, optional
        Eje temporal (si no se proporciona, se usa índice)
    title : str
        Título de la gráfica
    output_path : Path, optional
        Ruta para guardar la gráfica
    """
    try:
        import matplotlib.pyplot as plt
        
        if time_axis is None:
            time_axis = np.arange(len(signal_raw))
        
        fig, axes = plt.subplots(3, 1, figsize=(12, 8))
        
        # Señal cruda
        axes[0].plot(time_axis, signal_raw, 'b-', linewidth=1.5, alpha=0.7)
        axes[0].set_ylabel('Amplitud', fontweight='bold')
        axes[0].set_title('Señal Cruda', fontweight='bold')
        axes[0].grid(True, alpha=0.3)
        
        # Señal suavizada
        axes[1].plot(time_axis, signal_smoothed, 'g-', linewidth=1.5, alpha=0.7)
        axes[1].set_ylabel('Amplitud', fontweight='bold')
        axes[1].set_title('Señal Suavizada (Media Móvil)', fontweight='bold')
        axes[1].grid(True, alpha=0.3)
        
        # Señal normalizada
        axes[2].plot(time_axis, signal_normalized, 'r-', linewidth=1.5, alpha=0.7)
        axes[2].set_xlabel('Tiempo (muestras)', fontweight='bold')
        axes[2].set_ylabel('Amplitud Normalizada', fontweight='bold')
        axes[2].set_title('Señal Normalizada (Línea Base)', fontweight='bold')
        axes[2].grid(True, alpha=0.3)
        
        fig.suptitle(title, fontsize=14, fontweight='bold', y=0.995)
        plt.tight_layout()
        
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(output_path, dpi=300, bbox_inches='tight')
            logger.info(f" Gráfica guardada: {output_path.name}")
        
        plt.close()
    
    except ImportError:
        logger.warning("Matplotlib no disponible para visualización")
    except Exception as e:
        logger.warning(f"Error al generar gráfica de señal: {e}")


def plot_class_distribution(df: pd.DataFrame, 
                           label_column: str = 'Calidad_Vino',
                           output_path: Optional[Path] = None) -> None:
    """
    Visualiza la distribución de clases en el dataset.
    
    Parámetros:
    -----------
    df : pd.DataFrame
        DataFrame con los datos
    label_column : str
        Nombre de la columna de clases
    output_path : Path, optional
        Ruta para guardar la gráfica
    """
    try:
        import matplotlib.pyplot as plt
        import seaborn as sns
        
        if label_column not in df.columns:
            logger.warning(f"Columna {label_column} no encontrada")
            return
        
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        
        # Gráfico de barras
        class_counts = df[label_column].value_counts().sort_index()
        colors = plt.cm.Set3(np.linspace(0, 1, len(class_counts)))
        
        axes[0].bar(class_counts.index, class_counts.values, color=colors, edgecolor='black', linewidth=1.5)
        axes[0].set_xlabel('Clase', fontweight='bold', fontsize=11)
        axes[0].set_ylabel('Cantidad', fontweight='bold', fontsize=11)
        axes[0].set_title('Distribución de Clases (Barras)', fontweight='bold', fontsize=12)
        axes[0].grid(axis='y', alpha=0.3)
        
        # Valores en las barras
        for i, v in enumerate(class_counts.values):
            axes[0].text(i, v + 0.5, str(v), ha='center', fontweight='bold')
        
        # Gráfico de pastel
        axes[1].pie(class_counts.values, labels=class_counts.index, autopct='%1.1f%%',
                   colors=colors, startangle=90, textprops={'fontweight': 'bold'})
        axes[1].set_title('Distribución de Clases (Pie)', fontweight='bold', fontsize=12)
        
        plt.suptitle('Distribución de Clases en el Dataset', fontsize=14, fontweight='bold', y=0.98)
        plt.tight_layout()
        
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(output_path, dpi=300, bbox_inches='tight')
            logger.info(f"✓ Gráfica guardada: {output_path.name}")
        
        plt.close()
    
    except ImportError:
        logger.warning("Matplotlib/Seaborn no disponible para visualización")
    except Exception as e:
        logger.warning(f"Error al generar gráfica de distribución: {e}")


def plot_feature_statistics(df: pd.DataFrame,
                           feature_columns: Optional[List[str]] = None,
                           output_path: Optional[Path] = None) -> None:
    """
    Visualiza estadísticas de características.
    
    Parámetros:
    -----------
    df : pd.DataFrame
        DataFrame con las características
    feature_columns : list, optional
        Columnas de características a visualizar (si None, usa numéricas)
    output_path : Path, optional
        Ruta para guardar la gráfica
    """
    try:
        import matplotlib.pyplot as plt
        import seaborn as sns
        
        # Seleccionar características numéricas
        if feature_columns is None:
            feature_columns = df.select_dtypes(include=[np.number]).columns.tolist()
        
        # Limitar a 6 características principales
        feature_columns = feature_columns[:6]
        
        fig, axes = plt.subplots(2, 3, figsize=(15, 8))
        axes = axes.flatten()
        
        for idx, col in enumerate(feature_columns):
            if col in df.columns:
                data = df[col].dropna()
                axes[idx].hist(data, bins=20, color='skyblue', edgecolor='black', alpha=0.7)
                axes[idx].set_xlabel('Valor', fontweight='bold')
                axes[idx].set_ylabel('Frecuencia', fontweight='bold')
                axes[idx].set_title(f'{col}', fontweight='bold')
                axes[idx].grid(axis='y', alpha=0.3)
                
                # Agregar estadísticas
                mean = data.mean()
                std = data.std()
                axes[idx].axvline(mean, color='red', linestyle='--', linewidth=2, label=f'μ={mean:.2f}')
                axes[idx].axvline(mean+std, color='orange', linestyle=':', linewidth=1, alpha=0.7)
                axes[idx].legend()
        
        # Ocultar subplots vacíos
        for idx in range(len(feature_columns), len(axes)):
            axes[idx].set_visible(False)
        
        plt.suptitle('Estadísticas de Características Principales', fontsize=14, fontweight='bold')
        plt.tight_layout()
        
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(output_path, dpi=300, bbox_inches='tight')
            logger.info(f"✓ Gráfica guardada: {output_path.name}")
        
        plt.close()
    
    except ImportError:
        logger.warning("Matplotlib no disponible para visualización")
    except Exception as e:
        logger.warning(f"Error al generar gráfica de características: {e}")


def plot_correlation_heatmap(df: pd.DataFrame,
                            output_path: Optional[Path] = None,
                            figsize: tuple = (10, 8)) -> None:
    """
    Visualiza la matriz de correlación entre características.
    
    Parámetros:
    -----------
    df : pd.DataFrame
        DataFrame con las características
    output_path : Path, optional
        Ruta para guardar la gráfica
    figsize : tuple
        Tamaño de la figura
    """
    try:
        import matplotlib.pyplot as plt
        import seaborn as sns
        
        # Seleccionar solo columnas numéricas
        numeric_df = df.select_dtypes(include=[np.number])
        
        if numeric_df.empty:
            logger.warning("No hay columnas numéricas para correlación")
            return
        
        # Limitar a 10 características para claridad
        if numeric_df.shape[1] > 10:
            numeric_df = numeric_df.iloc[:, :10]
        
        # Calcular correlación
        correlation = numeric_df.corr()
        
        # Crear heatmap
        fig, ax = plt.subplots(figsize=figsize)
        sns.heatmap(correlation, annot=True, fmt='.2f', cmap='coolwarm', center=0,
                   cbar_kws={'label': 'Correlación'}, ax=ax, square=True)
        ax.set_title('Matriz de Correlación entre Características', fontweight='bold', fontsize=12)
        plt.tight_layout()
        
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(output_path, dpi=300, bbox_inches='tight')
            logger.info(f"✓ Gráfica guardada: {output_path.name}")
        
        plt.close()
    
    except ImportError:
        logger.warning("Matplotlib/Seaborn no disponible para visualización")
    except Exception as e:
        logger.warning(f"Error al generar matriz de correlación: {e}")


logger = setup_logging(__name__)
