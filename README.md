# enose

Hardware & Software to have a basic expandable electronic nose.

Este repositorio agrupa el trabajo del equipo. Cada bloque vive en su propia carpeta
para no pisarse entre ramas.

## Contenido

| Carpeta | Descripción |
|---|---|
| [`implementacion/`](implementacion/) | Pipeline de ML para clasificación de calidad de vino (nariz electrónica de 6 sensores MQ): procesamiento de señal, extracción de características y clasificación SVM. |

## Proyecto: nariz electrónica (implementacion/)

El pipeline completo (Fases 4 y 5), su documentación y sus tests están en
[`implementacion/`](implementacion/). Para los detalles —arquitectura, inicio rápido,
configuración y cómo extenderlo— consulta **[implementacion/README.md](implementacion/README.md)**.

Inicio rápido:

```bash
cd implementacion
pip install -r requirements.txt
python main.py            # Fases 4 + 5
```

## Referencia

Macias, M. M. et al. "Electronic Nose for Wine Discrimination." *Sensors* 13.5 (2013): 5528–5543.
