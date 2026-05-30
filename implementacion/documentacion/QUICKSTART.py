"""
===============================================================================
GUÍA RÁPIDA DE INICIO - NARIZ ELECTRÓNICA
===============================================================================

Este archivo es una guía de inicio rápido para usar el nuevo pipeline.

¿Qué cambió?
============
El código original (EnoseDataAnalysis.py) ha sido refactorizado en:
- 6 módulos separados por responsabilidad
- Código más limpio, documentado y mantenible
- Mejor manejo de errores
- Logging completo
- Configuración centralizada

¿Cómo empiezo?
==============

PASO 1: Instalar dependencias (solo la primera vez)
    pip install -r requirements.txt

PASO 2: Ejecutar el pipeline completo
    python main.py

¿Eso es todo! El script:
✓ Buscará archivos de sensores en data/raw/
✓ Generará dataset_maestro_vinos.csv (FASE 4)
✓ Entrenará un modelo SVM (FASE 5)
✓ Guardará resultados en data/processed/

¿Quiero más control?
====================

Ver todas las opciones:
    python main.py --help

Solo generar dataset (sin entrenar modelo):
    python main.py --phase 4

Solo entrenar modelo (sin generar dataset):
    python main.py --phase 5
    (requiere que dataset_maestro_vinos.csv exista)

¿Dónde está cada cosa?
======================

El código vive en el paquete src/enose/ (organizado por responsabilidad):

1. enose/config.py
   └─ Configuración centralizada (dataclasses tipadas)
   └─ Modifica aquí los parámetros del proyecto

2. enose/utils.py
   └─ Funciones auxiliares reutilizables

3. enose/signal/processor.py
   └─ Procesado de señal (Savitzky-Golay, normalización por línea base, segmentación)

4. enose/features/perkey_pca.py
   └─ PCA por (sensor × ventana) integrado en el Pipeline (sin data leakage)

5. enose/pipeline/dataset.py  (FASE 4)
   └─ Generación del dataset maestro

6. enose/model/trainer.py  (FASE 5)
   └─ Entrenamiento y evaluación del modelo SVM (validación por grupos)

7. main.py
   └─ Orquestador del pipeline completo ⭐
   └─ RECOMENDADO: Usar este para ejecutar todo

¿Cómo importo en mi código?
===========================

Para usar en otros scripts (con src/ en el sys.path, como hace main.py):

    from enose.signal.processor import SignalProcessor
    from enose.pipeline.dataset import DatasetGenerator
    from enose.model.trainer import ModelTrainer

Ejemplo:
    processor = SignalProcessor()
    generator = DatasetGenerator()
    trainer = ModelTrainer()

¿Dónde están los resultados?
=============================

Después de ejecutar main.py:

    data/processed/
    ├── best_model.pkl            ← Modelo entrenado
    ├── training_results.pkl       ← Métricas y resultados
    └── confusion_matrix.png       ← Gráfica

También:
    enose_project.log             ← Archivo de logs completo

¿Necesito cambiar algo?
========================

Los parámetros están en src/enose/config.py (dataclasses tipadas):

    SignalConfig(
        sampling_frequency=18.5,
        savgol_window=15,
        baseline_seconds=2.0,
    )

    MLConfig(
        n_splits_cv=3,
        scoring_metric='balanced_accuracy',   # clases desbalanceadas
        n_jobs=-1,
    )

    GRID_PARAMS = [...]

¿Qué pasa si hay errores?
==========================

1. Verifica que los datos estén en data/raw/
2. Revisa enose_project.log para errores específicos
3. Lee README.md para troubleshooting
4. Ejecuta con --verbose para más detalles

¿Puedo usar los datos/modelo posteriormente?
==============================================

Sí! El modelo se guarda como pickle:

    import pickle
    with open('data/processed/best_model.pkl', 'rb') as f:
        model = pickle.load(f)
    
    # Usar para predicción
    predictions = model.predict(new_data)

¿Necesito ayuda?
=================

Lee estos archivos:
- README.md (en src/)                   ← Documentación completa
- config.py                             ← Parámetros disponibles
- Docstrings en cada módulo             ← help(module.function)

¿Comparación Old vs New?
==========================

ANTES (1 archivo):
  python EnoseDataAnalysis_ORIGINAL.py

AHORA (Versión 2.0):
  python main.py                         ← ✨ Recomendado

✅ Beneficios:
  ✓ Modular
  ✓ Documentado
  ✓ Flexible
  ✓ Reutilizable
  ✓ Con logging
  ✓ Con manejo de errores
  ✓ Con CLI

¡Listo para comenzar!
======================

Próximo paso:
    python main.py

===============================================================================
"""

print(__doc__)

# Script de demostración
if __name__ == '__main__':
    print("\n" + "="*70)
    print("VERIFICANDO INSTALACIÓN".center(70))
    print("="*70)
    
    # Verificar módulos necesarios
    modules_to_check = {
        'pandas': 'Análisis de datos',
        'numpy': 'Computación numérica',
        'sklearn': 'Machine Learning',
        'matplotlib': 'Visualización',
        'seaborn': 'Visualización avanzada'
    }
    
    all_ok = True
    for module_name, description in modules_to_check.items():
        try:
            __import__(module_name)
            print(f"✓ {module_name:15} ({description})")
        except ImportError:
            print(f"✗ {module_name:15} ({description}) - FALTA INSTALAR")
            all_ok = False
    
    print("\n" + "="*70)
    
    if all_ok:
        print("✅ Todas las dependencias están instaladas".center(70))
        print("\nPuedes ejecutar: python main.py".center(70))
    else:
        print("⚠️ Faltan dependencias. Instala con:".center(70))
        print("pip install -r requirements.txt".center(70))
    
    print("="*70 + "\n")
