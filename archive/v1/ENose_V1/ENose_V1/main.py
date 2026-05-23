"""
===============================================================================
SCRIPT PRINCIPAL - PIPELINE COMPLETO NARIZ ELECTRÓNICA
===============================================================================

Este script orquesta todo el pipeline de análisis de la nariz electrónica:

FASE 1-3: Extracción de características
FASE 4: Generación del dataset maestro
FASE 5: Entrenamiento y optimización del modelo ML

Uso:
    python main.py [opciones]

Opciones:
    --all               Ejecutar todas las fases (por defecto)
    --phase-4-only      Solo generar dataset
    --phase-5-only      Solo entrenar modelo (requiere dataset existente)
    --skip-phase-4      Saltar generación de dataset
    --skip-phase-5      Saltar entrenamiento del modelo

===============================================================================
"""

import sys
import argparse
import logging
from pathlib import Path

# Configurar path para importar módulos locales
sys.path.insert(0, str(Path(__file__).parent))

from utils import setup_logging, print_data_summary
from phase_4_dataset_generation import DatasetGenerator, load_dataset
from phase_5_model_training import ModelTrainer
from config import DATASET_MAESTRO_PATH, DATA_RAW_DIR

logger = setup_logging(__name__)


def print_banner():
    """Imprime banner del proyecto."""
    banner = """
    ╔════════════════════════════════════════════════════════════════════╗
    ║                                                                    ║
    ║         🔬 PROYECTO NARIZ ELECTRÓNICA - PIPELINE COMPLETO 🔬      ║
    ║                                                                    ║
    ║        Clasificación de Sustancias por Sensores Químicos          ║
    ║                                                                    ║
    ╚════════════════════════════════════════════════════════════════════╝
    """
    print(banner)


def run_phase_4(skip_if_exists: bool = False) -> bool:
    """
    Ejecuta FASE 4: Generación del dataset maestro.
    
    Parámetros:
    -----------
    skip_if_exists : bool
        Si es True y el dataset existe, salta esta fase
    
    Retorna:
    --------
    bool
        True si fue exitosa, False en caso contrario
    """
    logger.info("\n" + "="*70)
    logger.info("▶ EJECUTANDO FASE 4: Generación del Dataset Maestro")
    logger.info("="*70)
    
    # Verificar si dataset ya existe
    if skip_if_exists and DATASET_MAESTRO_PATH.exists():
        logger.info(f"✓ Dataset ya existe: {DATASET_MAESTRO_PATH}")
        logger.info("  Saltando esta fase...")
        return True
    
    # Verificar que haya archivos de sensores
    if not DATA_RAW_DIR.exists():
        logger.error(f"Directorio de datos no encontrado: {DATA_RAW_DIR}")
        return False
    
    try:
        # Generar dataset
        generator = DatasetGenerator(data_dir=DATA_RAW_DIR)
        df_maestro = generator.generate_dataset(output_path=DATASET_MAESTRO_PATH)
        
        if df_maestro is None:
            logger.error("No se pudo generar el dataset maestro")
            return False
        
        # Mostrar información del dataset
        print_data_summary(df_maestro, "Dataset Maestro Generado")
        
        logger.info("✅ FASE 4 completada exitosamente\n")
        return True
    
    except Exception as e:
        logger.error(f"❌ Error en FASE 4: {e}", exc_info=True)
        return False


def run_phase_5() -> bool:
    """
    Ejecuta FASE 5: Entrenamiento del modelo ML.
    
    Retorna:
    --------
    bool
        True si fue exitosa, False en caso contrario
    """
    logger.info("\n" + "="*70)
    logger.info("▶ EJECUTANDO FASE 5: Entrenamiento del Modelo ML")
    logger.info("="*70)
    
    # Verificar que el dataset existe
    if not DATASET_MAESTRO_PATH.exists():
        logger.error(f"Dataset maestro no encontrado: {DATASET_MAESTRO_PATH}")
        logger.error("Ejecute primero la FASE 4 o proporcione el dataset")
        return False
    
    try:
        # Entrenar modelo
        trainer = ModelTrainer(dataset_path=DATASET_MAESTRO_PATH)
        success = trainer.train()
        
        if not success:
            logger.error("No se pudo completar el entrenamiento")
            return False
        
        logger.info("✅ FASE 5 completada exitosamente\n")
        return True
    
    except Exception as e:
        logger.error(f"❌ Error en FASE 5: {e}", exc_info=True)
        return False


def parse_arguments():
    """
    Parsea argumentos de línea de comandos.
    
    Retorna:
    --------
    argparse.Namespace
        Argumentos parseados
    """
    parser = argparse.ArgumentParser(
        description='Pipeline de análisis de Nariz Electrónica',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  python main.py                    # Ejecutar todo el pipeline
  python main.py --phase-4-only     # Solo generar dataset
  python main.py --phase-5-only     # Solo entrenar modelo
  python main.py --skip-phase-4     # Saltar dataset (si ya existe)
        """
    )
    
    parser.add_argument(
        '--all',
        action='store_true',
        help='Ejecutar todas las fases (por defecto)'
    )
    parser.add_argument(
        '--phase-4-only',
        action='store_true',
        help='Solo ejecutar FASE 4 (generar dataset)'
    )
    parser.add_argument(
        '--phase-5-only',
        action='store_true',
        help='Solo ejecutar FASE 5 (entrenar modelo)'
    )
    parser.add_argument(
        '--skip-phase-4',
        action='store_true',
        help='Saltar FASE 4 si el dataset ya existe'
    )
    parser.add_argument(
        '--skip-phase-5',
        action='store_true',
        help='Saltar FASE 5'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Modo verbose (más información de debug)'
    )
    
    return parser.parse_args()


def main():
    """
    Función principal del pipeline.
    """
    # Banner
    print_banner()
    
    # Parsear argumentos
    args = parse_arguments()
    
    # Ajustar nivel de logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Modo verbose activado")
    
    # Determinar qué fases ejecutar
    run_phase_4_flag = True
    run_phase_5_flag = True
    
    if args.phase_4_only:
        run_phase_5_flag = False
    elif args.phase_5_only:
        run_phase_4_flag = False
    
    if args.skip_phase_4:
        run_phase_4_flag = False
    if args.skip_phase_5:
        run_phase_5_flag = False
    
    # Validaciones
    if not run_phase_4_flag and not run_phase_5_flag:
        logger.error("❌ No hay fases seleccionadas para ejecutar")
        return False
    
    logger.info("Configuración del pipeline:")
    logger.info(f"  FASE 4 (Dataset): {'✓ SÍ' if run_phase_4_flag else '✗ NO'}")
    logger.info(f"  FASE 5 (ML): {'✓ SÍ' if run_phase_5_flag else '✗ NO'}\n")
    
    # Ejecutar pipeline
    success = True
    
    if run_phase_4_flag:
        if not run_phase_4(skip_if_exists=args.skip_phase_4):
            success = False
    
    if success and run_phase_5_flag:
        if not run_phase_5():
            success = False
    
    # Resumen final
    print("\n" + "="*70)
    if success:
        print("✅ PIPELINE COMPLETADO EXITOSAMENTE".center(70))
        print("\nResultados guardados en: data/processed/".center(70))
    else:
        print("❌ PIPELINE COMPLETADO CON ERRORES".center(70))
    print("="*70 + "\n")
    
    return success


if __name__ == '__main__':
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("\n⚠️ Pipeline interrumpido por el usuario")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}", exc_info=True)
        sys.exit(1)
