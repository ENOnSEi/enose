# ENose API — Glosario de dominio

## Términos

### Base
El período de reposo en aire limpio previo a la exposición al olor. Su función es establecer la línea de referencia de cada sensor antes de la medición. Las lecturas en estado `base` se usan para normalizar la señal de `medicion`.

### Medicion
El período de exposición activa al olor objetivo. Comienza cuando el observer detecta que la base se ha estabilizado. El período de recuperación posterior a la exposición no está implementado todavía.

### MeasurementSet
Un experimento completo: un único ciclo base→medicion. Se crea al llamar a `/serial/start` y requiere un `name` (string libre, puede repetirse) que sirve únicamente como identificación humana. El análisis y entrenamiento del modelo se hacen usando el `id` del `MeasurementSet`, no el nombre. Tiene `started_at` y `stopped_at`. Cada sustancia que se quiere medir genera un `MeasurementSet` nuevo.

### Cierre de MeasurementSet
Al hacer stop (manual o por observer), el `MeasurementSet` no se cierra inmediatamente. Primero se espera a que la queue del drain esté vacía (máx. 10 segundos) para garantizar que todas las lecturas pendientes se insertan con el `measurement_set_id` correcto. Solo entonces se escribe `stopped_at` y se limpia el estado.

### Criterio de estabilidad
Se requiere que **todos** los sensores tengan pendiente por debajo del umbral (`OBSERVER_SLOPE_THRESHOLD`). Un solo sensor fuera de umbral mantiene el sistema en espera.

### Criterio de stop de medicion
El stop requiere que se cumplan **ambas** condiciones: (1) han transcurrido al menos `OBSERVER_MIN_MEDICION_SECONDS` (30s por defecto) y (2) la pendiente de todos los sensores es estable. Si los sensores se estabilizan antes de los 30s, la medicion continúa hasta completarlos. Si no se estabilizan, la medicion no para aunque supere los 30s.

### Timeout de medicion
Si la fase de `medicion` no se estabiliza, la medicion no termina nunca. **Pendiente de implementar junto con WebSockets**, igual que el timeout de base.

### Timeout de base
Si la fase de `base` no se estabiliza en 5 minutos, el observer debe abortar el `MeasurementSet` y notificar al usuario con un error claro. **Pendiente de implementar junto con WebSockets**, que serán el canal de feedback en tiempo real para este tipo de eventos. Mientras tanto no hay timeout: el observer espera indefinidamente.

### Estado
Etiqueta de cada `Reading` que indica la fase en que fue capturada: `base` o `medicion`. Lo gestiona el observer automáticamente. Los endpoints `PUT /serial/estado/{estado}` y las opciones equivalentes del CLI existen únicamente para pruebas manuales durante el desarrollo, antes de que el observer esté totalmente calibrado. No deben usarse en producción para alterar mediciones reales.
