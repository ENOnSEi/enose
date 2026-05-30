# ADR 003 — Elección del clasificador: SVM con GridSearchCV

**Estado**: Aceptado  
**Fecha**: 2026-05-30  
**Autor**: Jesus Veiga

## Contexto

El dataset tiene ~235 muestras y ~15-54 features. El objetivo es clasificar
4 clases (AQ, HQ, LQ, ETH) con alta fiabilidad. Se priorizan:
- Alta accuracy con pocos datos
- Reproducibilidad
- Compatibilidad con el enfoque de la referencia bibliográfica (Macias et al. 2013)

## Decisión

SVM (Support Vector Machine) con:
- Kernels explorados: `linear` y `rbf`
- Optimización via `GridSearchCV` + `StratifiedKFold`
- Pipeline `StandardScaler → SVC` (evita data leakage en el scaler)

## Justificación

SVM funciona bien con:
- Datasets pequeños-medianos (< 1000 muestras)
- Features con diferente escala (corregida por StandardScaler)
- Pocas clases (4 en este caso)
- Fronteras de decisión no triviales (RBF kernel)

La referencia bibliográfica del proyecto usa SVM, lo que facilita la comparación de resultados.

## Alternativas para experimentar

El contrato `ClassifierProtocol` permite sustituir SVM sin cambiar el pipeline:

| Alternativa | Cuándo probarla |
|---|---|
| Random Forest | Si se añaden muchos más sensores (alta dimensionalidad) |
| XGBoost | Si el dataset crece a >500 muestras |
| Red neuronal | Si se pasa a clasificación de señal cruda sin extracción de features |

## Cómo cambiar el clasificador

Editar `ModelTrainer.build_pipeline()` en `src/enose/model/trainer.py` y actualizar
`GRID_PARAMS` en `config.py`. El resto del pipeline no cambia.
