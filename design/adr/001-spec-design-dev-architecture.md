# ADR 001 — Arquitectura Spec → Design → Dev

**Estado**: Aceptado  
**Fecha**: 2026-05-30  
**Autor**: Jesus Veiga

## Contexto

El pipeline original tenía todos los módulos al mismo nivel (`src/*.py`), sin
separación de responsabilidades. Añadir un nuevo sensor o algoritmo requería
modificar varios archivos sin un contrato claro de qué debía implementarse.

## Decisión

Adoptar la filosofía **Specification → Design → Development**:

| Capa | Carpeta | Propósito |
|---|---|---|
| Spec | `spec/contracts/` | Protocolos Python (`typing.Protocol`) que definen las interfaces |
| Spec | `spec/schemas/` | Modelos Pydantic que validan los datos en las fronteras del sistema |
| Design | `design/adr/` | Decisiones de arquitectura con contexto y razonamiento |
| Dev | `src/enose/` | Implementaciones reales, organizadas por dominio |

## Estructura del paquete `src/enose/`

```
src/enose/
├── io/          # Ingesta de datos (lectura de archivos, extracción de etiquetas)
├── signal/      # Procesamiento de señal (suavizado, normalización, ventanas)
├── features/    # Extractores (handcrafted, pca) — intercambiables via Protocol
├── model/       # Entrenamiento y evaluación del clasificador
├── pipeline/    # Orquestación del flujo completo (dataset, training)
├── config.py    # Configuración tipada con dataclasses
└── utils.py     # Utilidades compartidas (logging, plots, validación)
```

## Consecuencias

**Beneficios**:
- Añadir un nuevo extractor de características = implementar `SignalExtractorProtocol`
- Añadir un nuevo sensor = actualizar `SENSOR_COLUMNS` en `config.py` + validadores del schema
- Los tests de contrato verifican que las implementaciones siguen la spec sin acoplamiento

**Costes**:
- Más archivos que la versión flat
- Import paths más largos (`from enose.features.pca import ...`)

## Alternativas descartadas

- **Mantener estructura flat**: simple pero no escala cuando se añaden nuevos algoritmos
- **Usar ABCs (Abstract Base Classes)**: más rígido que Protocols — requiere herencia explícita
