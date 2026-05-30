# ADR-001: Informe automático de ejecución del pipeline

- **Estado:** Aceptado
- **Fecha:** 2026-05-31

## Contexto

El pipeline (Fase 4 generación del dataset + Fase 5 entrenamiento/evaluación)
produce hoy artefactos dispersos: el dataset maestro CSV, `training_results.pkl`,
gráficos sueltos en `datos/procesados/visualizations/` y líneas en el log. Para
saber "cómo fue una ejecución" hay que abrir varios archivos y cruzarlos a mano,
y al re-ejecutar se sobrescriben los gráficos, perdiendo el histórico para
comparar configuraciones (handcrafted vs pca_signal, distintos grids, etc.).

Queremos un **informe consolidado por ejecución** que reúna metadata reproducible,
resumen del dataset, división de datos, resultados del modelo, los gráficos y
conclusiones automáticas, conservando un historial.

Decisiones a tomar:

1. **Formato.** Markdown enlazando los PNG vs HTML autocontenido vs PDF.
2. **Alcance.** Solo Fase 5 vs Fases 4 + 5.
3. **Historial.** Sobrescribir vs un informe con timestamp por ejecución.
4. **Disparo.** Automático al final del entrenamiento vs script aparte.
5. **Acoplamiento Spec↔Dev.** Hasta ahora `enose` (Dev) nunca importa `spec`;
   los schemas se validan solo en los tests. ¿El reporting rompe esa regla?

## Decisión

1. **Markdown + PNGs**, dentro de una carpeta por informe. Versionable, legible en
   cualquier editor/GitHub y sin dependencias de render.
2. **Fases 4 + 5.** El resumen de Fase 4 (nº de muestras, features, distribución de
   clases, grupos vino-lote, modo) se deriva del DataFrame ya cargado por el trainer.
3. **Historial con timestamp:** `informes/informe_YYYY-MM-DD_HH-MM-SS/`.
4. **Automático** al final de `ModelTrainer.train()`, como un paso más del
   orquestador. Un fallo del informe **no** invalida el entrenamiento (se loguea
   como warning).
5. **El reporting es la única zona de Dev que importa `spec` en runtime.** El valor
   del informe *es* su estructura validada y su metadata serializable, así que la
   fuente de verdad es el schema `ExecutionReport` (Pydantic). Se concentra el uso
   de `spec` en el paquete `enose.report`, que añade `PROJECT_ROOT` al `sys.path`
   para poder importar `spec` igual que hacen los tests.

### Capas implicadas

| Capa | Artefacto | Rol |
|------|-----------|-----|
| Spec | `spec/schemas/execution_report.py` | Estructura validada del informe (contrato de datos) |
| Spec | `spec/contracts/reporter.py` | `ReportGeneratorProtocol`: `generate(report) -> Path` |
| Design | este ADR | Razonamiento de las decisiones |
| Dev | `src/enose/report/generator.py` | `MarkdownReportGenerator` + ensamblado desde el trainer |

## Consecuencias

- (+) Una sola carpeta autocontenida por ejecución, comparable a lo largo del tiempo.
- (+) `report.json` (volcado del `ExecutionReport`) permite comparar runs de forma
  programática en el futuro.
- (+) Conclusiones automáticas (sobreajuste, clase mejor/peor, desbalanceo) sin
  intervención manual.
- (+) Cambiar a HTML/PDF en el futuro es implementar el mismo protocolo, sin tocar
  el trainer.
- (−) El paquete `enose.report` introduce la primera dependencia runtime Dev→Spec;
  se acepta de forma localizada y se cubre con un test de contrato.
- (−) La carpeta `informes/` crece con cada ejecución; por eso va en `.gitignore`
  (por ahora no se versiona el historial).
