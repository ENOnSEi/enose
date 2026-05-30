# ADR 002 — Modo de extracción de características: PCA vs Handcrafted

**Estado**: Aceptado (PCA como default)  
**Fecha**: 2026-05-30  
**Autor**: Jesus Veiga

## Contexto

El pipeline soporta dos modos de extracción de características controlados por
`FEATURE_MODE` en `config.py`. La elección afecta tanto a la dimensionalidad del
dataset como al proceso de inferencia en producción.

## Opciones

### `handcrafted` (max, AUC, slope por ventana)

- **Ventajas**: Determinista, interpretable, sin artefactos de ajuste
- **Dimensionalidad**: 54 features (6 sensores × 3 ventanas × 3 estadísticos)
- **Producción**: Solo necesita `best_model.pkl`
- **Desventaja**: Descarta información de la forma de la curva

### `pca_signal` (proyección PCA por sensor×ventana)

- **Ventajas**: Captura varianza de la forma completa de la señal, generalmente mejor accuracy
- **Dimensionalidad**: Variable (~15-20 features, controlado por `explained_variance_threshold`)
- **Producción**: Necesita `best_model.pkl` + `pca_transformers.pkl`
- **Desventaja**: No interpretable, los PCs no tienen significado físico directo

## Decisión

`pca_signal` como default (`FEATURE_MODE = 'pca_signal'` en `config.py`).

Justificación: mayor accuracy en validación y captura información de la dinámica
temporal completa de la señal, que es precisamente lo que diferencia calidades de vino.

## Cómo cambiar

Editar `FEATURE_MODE` en `src/enose/config.py` y re-ejecutar la Fase 4 completa.
El pipeline detecta el modo automáticamente.

## Impacto en producción

Para modo `pca_signal`, la inferencia sobre nuevas muestras requiere:
1. Cargar `pca_transformers.pkl` con `PCAFeatureExtractor.load()`
2. Procesar la señal cruda → segmentar → proyectar sobre PCs
3. Pasar el vector resultante a `best_model.pkl`
