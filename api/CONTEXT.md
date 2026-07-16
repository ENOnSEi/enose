# ENose API — Glosario de dominio

## Términos

### Base
El período de reposo en aire limpio previo a la exposición al olor. Su función es establecer la línea de referencia de cada sensor antes de la medición. Las lecturas en estado `base` se usan para normalizar la señal de `medicion`.

### Medicion
El período de exposición activa al olor objetivo. Comienza cuando el observer detecta que la base se ha estabilizado. El período de recuperación posterior a la exposición no está implementado todavía.

### Sample
Entidad de nivel superior que representa la medición de una sustancia. Tiene `name` (solo identificación humana, puede repetirse), `n_repetitions` (número de ciclos planificados) y `completed_repetitions` (número de `MeasurementSet` completados con éxito). Si `completed_repetitions < n_repetitions`, el sample fue interrumpido. La decisión de si un sample incompleto es válido para análisis queda en manos del usuario, que compara ambos valores. El análisis y entrenamiento usan el `id` del `Sample`. Se crea al llamar a `/serial/start` con `n_repetitions` entre 1 y 10. Se cierra automáticamente al completar todas las repeticiones. **En el futuro** se añadirán campos adicionales para describir la naturaleza de la muestra (etiqueta de clase, sustancia, condiciones, etc.).

### MeasurementSet
Un único ciclo base→medicion dentro de un `Sample`. Se crea y gestiona automáticamente por el observer. Tiene `sample_id`, `repetition_number` (1-based) y `started_at`/`stopped_at`.

### Cooldown
Fase entre dos `MeasurementSet` consecutivos. El sensor se recupera en aire limpio. Las lecturas tienen `estado="cooldown"`, `sample_id` del sample activo, y `measurement_set_id=NULL`. Termina cuando la pendiente de todos los sensores se estabiliza (mismo criterio que base). No hay cooldown después del último MeasurementSet.

### Validez de datos tras crash
Si la API se reinicia a mitad de un `Sample`, el `Sample` y el `MeasurementSet` activo quedan con `stopped_at = NULL`. No se hace limpieza automática al arrancar. La regla de descarte es:
- `MeasurementSet.stopped_at = NULL` → siempre descartar (ciclo incompleto).
- `Sample.stopped_at = NULL` → no descartar automáticamente; usar `completed_repetitions` para decidir si tiene suficientes ciclos válidos para el análisis.

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
Etiqueta de cada `Reading` que indica la fase en que fue capturada: `base`, `medicion` o `cooldown`. Lo gestiona el observer automáticamente. Los endpoints `PUT /serial/estado/{estado}` y las opciones equivalentes del CLI existen únicamente para pruebas manuales durante el desarrollo, antes de que el observer esté totalmente calibrado. No deben usarse en producción para alterar mediciones reales.

### Sensor
Identidad estable de un sensor de gas, con `name` (único), `created_at` y `retired_at`. Se siembra automáticamente al arrancar desde `SENSOR_NAMES` en `.env`. El emparejamiento con las lecturas del ESP32 es **por nombre** (el JSON del board envía `{"tgs2620": N, ...}`), nunca por posición ni por pin — el orden de `SENSOR_NAMES` en la configuración es irrelevante para el parsing. El cableado físico (a qué pin ADC está conectado cada sensor) es responsabilidad exclusiva del firmware del ESP32 y no se guarda en la base de datos.

**Sustitución de un sensor físico:** `POST /sensors/{name}/rename` con `{"archive_as": "<nombre-archivo>"}`. Renombra la fila activa (el sensor saliente) a `archive_as` y marca `retired_at`, y crea de inmediato una fila nueva con el `name` original para el sensor de reemplazo, con su propio `created_at`. Así las `ReadingValue` capturadas antes y después del cambio quedan bajo `sensor_id` distintos, sin conflacionarse — sin reiniciar la API. Es una acción explícita del operador, no automática: solo quien sustituye el sensor físico sabe que ocurrió el cambio, así que detectarlo comparando `SENSOR_NAMES` entre arranques daría falsos positivos (p. ej. quitar temporalmente un sensor de la config para una prueba no implica una sustitución física).

