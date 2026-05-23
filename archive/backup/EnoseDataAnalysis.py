import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from sklearn.model_selection import StratifiedKFold, GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.metrics import classification_report, confusion_matrix

# =====================================================================
# FASE 1, 2 Y 3: MOTOR DE EXTRACCIÓN DE CARACTERÍSTICAS
# =====================================================================
def extraer_caracteristicas_nariz(ruta_archivo, etiqueta_calidad, frecuencia_muestreo=18.5, ventana_n=9, seg_basales=2.0):
    """
    Lee un archivo crudo de la nariz electrónica, suaviza la señal, normaliza 
    por línea base y extrae descriptores matemáticos (Características).
    """
    nombres_columnas = ['Humedad_%', 'Temperatura_C', 'MQ3_1', 'MQ4_1', 'MQ6_1', 'MQ3_2', 'MQ4_2', 'MQ6_2']
    columnas_sensores = ['MQ3_1', 'MQ4_1', 'MQ6_1', 'MQ3_2', 'MQ4_2', 'MQ6_2']
    
    ruta_segura = Path(ruta_archivo)
    
    # 1. Ingesta
    df_crudo = pd.read_csv(ruta_segura, sep=r'\s+', header=None, names=nombres_columnas)
    
    # 2. Suavizado (Media Móvil Centrada)
    df_limpio = df_crudo.copy()
    df_limpio[columnas_sensores] = df_crudo[columnas_sensores].rolling(window=ventana_n, center=True).mean()
    df_limpio = df_limpio.dropna().reset_index(drop=True)
    
    # 3. Normalización (Sensibilidad Rs)
    filas_basales = int(seg_basales * frecuencia_muestreo)
    df_normalizado = pd.DataFrame()
    
    for sensor in columnas_sensores:
        R0 = df_limpio[sensor].iloc[:filas_basales].mean()
        df_normalizado[sensor] = (R0 - df_limpio[sensor]) / R0

    # 4. Extracción de Características
    dt = 1.0 / frecuencia_muestreo
    caracteristicas = {'Nombre_Archivo': ruta_segura.name, 'Calidad_Vino': etiqueta_calidad}
    
    for sensor in columnas_sensores:
        senal = df_normalizado[sensor].values
        caracteristicas[f'{sensor}_max'] = np.max(senal)
        caracteristicas[f'{sensor}_auc'] = np.trapezoid(senal, dx=dt)
        caracteristicas[f'{sensor}_slope'] = np.max(np.diff(senal) / dt)
        
    return caracteristicas

# =====================================================================
# FASE 4: GENERACIÓN AUTOMÁTICA DEL DATASET MAESTRO (VERSIÓN MEJORADA)
# =====================================================================
print("🛠️ FASE 4: Procesando archivos y generando Dataset Maestro...")
lista_registros = []

# En lugar de mirar solo una carpeta, buscamos en TODO el directorio del proyecto
# rglob("*.txt") buscará todos los txt en cualquier subcarpeta
archivos_txt = list(Path(".").rglob("*.txt"))

if not archivos_txt:
    print("⚠️ No se encontraron archivos .txt en ninguna carpeta.")
else:
    for archivo in archivos_txt:
        nombre_archivo_upper = archivo.name.upper()
        
        # Etiquetamos según el nombre del archivo
        if "AQ_WINE" in nombre_archivo_upper:
            etiqueta = "AQ"
        elif "LQ_WINE" in nombre_archivo_upper:
            etiqueta = "LQ"
        else:
            # Si hay un txt que no es ni AQ ni LQ, lo ignoramos
            continue
            
        registro = extraer_caracteristicas_nariz(archivo, etiqueta)
        lista_registros.append(registro)

    df_maestro = pd.DataFrame(lista_registros)
    df_maestro.to_csv("dataset_maestro_vinos.csv", index=False)
    
    # Comprobación de seguridad: imprimir cuántos hay de cada clase
    conteo_clases = df_maestro['Calidad_Vino'].value_counts()
    print(f"✅ Dataset Maestro generado con éxito ({len(df_maestro)} muestras en total).")
    print(f"📊 Distribución de clases encontradas:\n{conteo_clases.to_string()}\n")

# =====================================================================
# FASE 5: MACHINE LEARNING Y OPTIMIZACIÓN (GRID SEARCH)
# =====================================================================
# Solo ejecutamos esta parte si el dataset maestro fue creado correctamente
archivo_dataset = Path("dataset_maestro_vinos.csv")

if archivo_dataset.exists():
    print("🧠 FASE 5: Entrenando IA y buscando los mejores hiperparámetros...")
    
    # Carga de datos
    df_maestro = pd.read_csv(archivo_dataset)
    X = df_maestro.drop(columns=['Nombre_Archivo', 'Calidad_Vino'])
    y = df_maestro['Calidad_Vino']
    
    # Verificación de seguridad para StratifiedKFold
    # Si tienes muy pocos datos en pruebas, K=3 puede fallar, ajustamos a K=2 o K=3 según tamaño
    k_folds = 3 if len(y) >= 6 else 2 
    skf = StratifiedKFold(n_splits=k_folds, shuffle=True, random_state=42)
    
    # Pipeline: Estandarización + Modelo SVM
    pipeline = Pipeline([
        ('escalador', StandardScaler()),
        ('svm', SVC(random_state=42))
    ])
    
    # Definimos el espacio de búsqueda (Grid)
    # Nota: Usamos 'svm__' para indicarle al pipeline que esos parámetros son para el modelo SVM
    param_grid = [
        {'svm__kernel': ['linear'], 'svm__C': [0.1, 1, 10, 100]},
        {'svm__kernel': ['rbf'], 'svm__C': [0.1, 1, 10, 100], 'svm__gamma': ['scale', 'auto', 0.1, 0.01]}
    ]
    
    # Inicializamos GridSearchCV
    grid_search = GridSearchCV(
        estimator=pipeline,
        param_grid=param_grid,
        cv=skf,
        scoring='accuracy',
        n_jobs=-1, # Usa todos los procesadores disponibles
        verbose=1
    )
    
    # Ejecutamos la búsqueda
    grid_search.fit(X, y)
    
    # Resultados
    print("\n====================================================")
    print("🏆 RESULTADOS DE LA OPTIMIZACIÓN (GridSearchCV)")
    print("====================================================")
    print(f"Mejores Hiperparámetros encontrados:\n{grid_search.best_params_}")
    print(f"Precisión Media en Validación Cruzada: {grid_search.best_score_ * 100:.2f}%\n")
    
    # Evaluación adicional opcional con el mejor modelo encontrado
    mejor_modelo = grid_search.best_estimator_
    y_pred = mejor_modelo.predict(X)
    
    print("Matriz de Confusión Global (sobre todos los datos):")
    print(pd.DataFrame(confusion_matrix(y, y_pred), 
                       index=[f'Real_{clase}' for clase in mejor_modelo.classes_], 
                       columns=[f'Pred_{clase}' for clase in mejor_modelo.classes_]))
else:
    print("❌ No se encontró 'dataset_maestro_vinos.csv'. No se puede ejecutar el entrenamiento.")