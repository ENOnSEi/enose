import pandas as pd
import numpy as np
import glob
import os

# =====================================================================
# FUNCTION: PIPELINE COMPLETO PARA UN SOLO ARCHIVO (FASE 1, 2 y 3)
# =====================================================================
def extraer_caracteristicas_vino(ruta_txt):
    nombres_columnas = ['Humedad_%', 'Temperatura_C', 'MQ3_1', 'MQ4_1', 'MQ6_1', 'MQ3_2', 'MQ4_2', 'MQ6_2']
    frecuencia_muestreo = 18.5
    dt = 1 / frecuencia_muestreo
    N = 9
    columnas_sensores = ['MQ3_1', 'MQ4_1', 'MQ6_1', 'MQ3_2', 'MQ4_2', 'MQ6_2']
    
    # Fase 1: Ingesta y Suavizado Centrado
    df_crudo = pd.read_csv(ruta_txt, sep='\s+', header=None, names=nombres_columnas)
    df_limpio = df_crudo.copy()
    df_limpio[columnas_sensores] = df_crudo[columnas_sensores].rolling(window=N, center=True).mean()
    df_limpio = df_limpio.dropna().reset_index(drop=True)
    
    # Fase 2: Normalización por Línea Base (Primeros 2 segundos)
    filas_basales = int(2.0 * frecuencia_muestreo)
    df_normalizado = df_limpio.copy()
    
    for sensor in columnas_sensores:
        R0 = df_limpio[sensor].iloc[:filas_basales].mean()
        df_normalizado[sensor] = (R0 - df_limpio[sensor]) / R0
        
    # Fase 3: Extracción de Descriptores
    caracteristicas = {}
    for sensor in columnas_sensores:
        senal = df_normalizado[sensor].values
        
        pico_max = np.max(senal)
        area_curva = np.trapezoid(senal, dx=dt)
        derivada = np.diff(senal) / dt
        pendiente_max = np.max(derivada)
        
        caracteristicas[f'{sensor}_max'] = pico_max
        caracteristicas[f'{sensor}_auc'] = area_curva
        caracteristicas[f'{sensor}_slope'] = pendiente_max
        
    return caracteristicas

# =====================================================================
# BUCLE PRINCIPAL: PROCESAMIENTO DE LAS CARPETAS DEL DATASET
# =====================================================================
carpetas_objetivo = {
    'AQ': 'AQ_Wines',
    'HQ': 'HQ_Wines',
    'LQ': 'LQ_Wines'
}

lista_muestras_maestras = []

print("🚀 Iniciando procesamiento masivo de sensores de vino...")

for etiqueta, ruta_carpeta in carpetas_objetivo.items():
    # Buscamos todos los archivos .txt dentro de la carpeta actual
    patron_busqueda = os.path.join(ruta_carpeta, "*.txt")
    archivos_txt = glob.glob(patron_busqueda)
    
    print(f"-> Procesando carpeta {etiqueta}: Encontrados {len(archivos_txt)} archivos.")
    
    for archivo in archivos_txt:
        try:
            # 1. Ejecutar el pipeline de características
            firma_diccionario = extraer_caracteristicas_vino(archivo)
            
            # 2. Inyectar metadatos clave: Nombre del archivo y la ETIQUETA de calidad para la IA
            firma_diccionario['Nombre_Archivo'] = os.path.basename(archivo)
            firma_diccionario['Calidad_Vino'] = etiqueta  # AQ, HQ, o LQ
            
            # Guardamos el resultado en nuestra lista colectora
            lista_muestras_maestras.append(firma_diccionario)
            
        except Exception as e:
            print(f"❌ Error al procesar el archivo {archivo}: {str(e)}")

# 3. CONSOLIDAR EL DATASET MAESTRO
df_dataset_maestro = pd.DataFrame(lista_muestras_maestras)

# Reordenamos las columnas para dejar los metadatos al principio
columnas_ordenadas = ['Nombre_Archivo', 'Calidad_Vino'] + [c for c in df_dataset_maestro.columns if c not in ['Nombre_Archivo', 'Calidad_Vino']]
df_dataset_maestro = df_dataset_maestro[columnas_ordenadas]

# 4. GUARDAR EL RESULTADO DE NUESTRO TRABAJO
df_dataset_maestro.to_csv("dataset_maestro_vinos.csv", index=False)

print("\n✅ ¡Dataset Maestro consolidado con éxito!")
print(f"Dimensiones finales de la matriz para la IA: {df_dataset_maestro.shape}")
print(df_dataset_maestro['Calidad_Vino'].value_counts())