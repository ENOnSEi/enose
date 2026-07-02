# ADR 002 — Modo de extracción de características: PCA vs Handcrafted

**Estado**: Aceptado — **default actual: `handcrafted` + ratios entre sensores**  
**Fecha**: 2026-05-30 · revisado 2026-06-03 (V6) y 2026-06-30 (ratios)  
**Autor**: Jesus Veiga

> **Actualización 2026-06-30 (ratios entre sensores):**
> - A las 36 features handcrafted se añaden **24 ratios** entre pares de sensores
>   (`max` y `auc` de 4 pares × 3 ventanas). Los ratios cancelan la intensidad del
>   vapor y capturan la composición relativa del gas. Total: **60 features**.
> - Resultado: la accuracy de test subió de 36% a 64% (11 clases × 3 reps).
> - Detalle y justificación geométrica en
>   `documentacion/como_funcionan_las_features_y_el_modelo.md`.
>
> **Actualización 2026-06-03 (V6 — migración a 4 sensores TGS y CSV con fases):**
> - Con el nuevo formato cada grabación produce, por defecto, **una muestra**, por lo
>   que el default pasa a **`handcrafted`** (features deterministas sin necesidad de
>   ajustar un PCA con pocas muestras). `pca_signal` sigue disponible y es preferible
>   cuando se generan muchas muestras (ventaneando la fase `medicion`).
> - La dimensionalidad handcrafted base es **36 features** (4 sensores × 3 ventanas ×
>   3 estadísticos), no 54.
> - La agrupación para la validación por grupos es por **grabación** (sufijo `#wNN`),
>   no por vino-lote. El resto del razonamiento de este ADR sigue vigente.

## Contexto

El pipeline soporta dos modos de extracción de características controlados por
`FEATURE_MODE` en `config.py`. La elección afecta tanto a la dimensionalidad del
dataset como al proceso de inferencia en producción.

## Opciones

### `handcrafted` (max, AUC, slope por ventana + ratios entre sensores)

- **Ventajas**: Determinista, interpretable, sin artefactos de ajuste
- **Dimensionalidad**: 36 estadísticos (4 sensores × 3 ventanas × 3) + 24 ratios = 60
- **Producción**: Solo necesita `best_model.pkl`
- **Desventaja**: Descarta el detalle punto a punto de la forma de la curva

### `pca_signal` (proyección PCA por sensor×ventana)

- **Ventajas**: Captura varianza de la forma completa de la señal, generalmente mejor accuracy
- **Dimensionalidad**: Variable (~15-20 features, controlado por `explained_variance_threshold`)
- **Producción**: Solo necesita `best_model.pkl` (el PCA viaja dentro del Pipeline)
- **Desventaja**: No interpretable, los PCs no tienen significado físico directo

## Decisión

`handcrafted` como default (`FEATURE_MODE = 'handcrafted'` en `config.py`), con los
ratios entre sensores incluidos.

Justificación: con el formato actual cada grabación produce una sola muestra, así que
ajustar un PCA con tan pocas muestras no es fiable. Los estadísticos handcrafted son
deterministas y, sumados a los ratios (que aíslan la huella química de la intensidad),
dan la mejor accuracy con los datos disponibles sin riesgo de sobreajuste del PCA.
`pca_signal` queda como alternativa para cuando haya muchas muestras por grabación
(ventaneando `medicion`).

## Cómo cambiar

Editar `FEATURE_MODE` en `src/enose/config.py` y re-ejecutar la Fase 4 completa.
El pipeline detecta el modo automáticamente.

## Dónde se ajusta el PCA (corrección de data leakage)

> **Cambio 2026-05-30**: el PCA ya **no** se ajusta en la Fase 4.

Antes, la Fase 4 ajustaba el PCA sobre *todas* las muestras (train + test) y
guardaba las proyecciones en el CSV. El split train/test ocurría después en la
Fase 5, por lo que el PCA "veía" el conjunto de test → **data leakage** y accuracy
sobreestimada.

Ahora:
- La **Fase 4** serializa los **segmentos crudos** por (sensor×ventana) en columnas
  `{sensor}_{ventana}__t{idx}`. No ajusta ningún PCA.
- La **Fase 5** incluye `PerKeyPCA` (`features/perkey_pca.py`) como primer paso del
  `Pipeline` de sklearn. El PCA se reajusta **solo sobre los datos de entrenamiento**
  en cada fold de la validación cruzada y en el split final, eliminando la fuga.

`PCAFeatureExtractor` se mantiene por compatibilidad con `SignalExtractorProtocol`
(tests de contrato) pero ya no participa en el pipeline activo.

> **Segunda fuente de fuga (corregida aparte):** además del PCA, las réplicas del
> mismo vino-lote se repartían entre train y test. La Fase 5 usa ahora
> `StratifiedGroupKFold` agrupando por vino-lote. Ver CHANGELOG V5 y `model/trainer.py`.

## Impacto en producción

Para modo `pca_signal`, la inferencia sobre nuevas muestras requiere:
1. Procesar la señal cruda → segmentar por (sensor×ventana) → recortar/rellenar a
   la longitud fija y construir una fila con columnas `{sensor}_{ventana}__t{idx}`
2. Pasar esa fila a `best_model.pkl` — el `PerKeyPCA` + `StandardScaler` + `SVM`
   embebidos en el Pipeline hacen el resto. Ya **no** hace falta `pca_transformers.pkl`.
