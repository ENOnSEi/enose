# Diseño — Patrón Observer para fases y actuación de la placa

> Estado: **propuesta para revisar** (no implementado). Sin código aún.
> Referencia: https://refactoring.guru/es/design-patterns/observer

## 1. Objetivo

Que el sistema arranque y pare la medición **de forma autónoma** (sin humano en el
bucle), con el PC como cerebro y la placa actuando el hardware bajo comando. Para
lograrlo sin acoplar la lógica de decisión a cada reacción (serial, BD, WebSockets,
log), aplicamos el **patrón Observer**: el código que decide solo **cambia un estado**
y se olvida; los interesados están **suscritos** y reaccionan.

Beneficio clave (principio abierto/cerrado): añadir una reacción nueva —p. ej.
WebSockets— será **un suscriptor más**, sin tocar la lógica de decisión.

## 2. Mapeo del patrón a nuestro sistema

| Pieza del patrón (refactoring.guru) | Aquí |
|---|---|
| **Publisher / Subject** (`subscribe`/`unsubscribe`/`notify`) | `PhaseState`: guarda la fase actual y el `measurement_set_id`; notifica al cambiar |
| **Interfaz Subscriber** (`update`) | `PhaseSubscriber.on_phase_change(event)` (async) |
| **Suscriptores concretos** | `BoardCommander`, `MeasurementSetCloser`, `PhaseLogger`, (futuro) `WebSocketNotifier` |
| **Cliente** (registra suscriptores) | el arranque de la app (`lifespan` en `main.py`) |

**Importante**: el que *decide* NO es un suscriptor. Es el bucle que sondea Postgres
y alimenta el analizador (hoy mal llamado `Observer`). Ese bucle, al confirmar una
transición, hace `await phase_state.set_phase(...)` y se desentiende del resto.

El **analizador** (`analyzer.py`) sigue siendo una calculadora pura y **no se toca**.

## 3. Componentes y responsabilidades

### 3.1 `Phase` (enum de dominio)
```
BASE        # reposo en aire limpio, fijando la línea base
MEDICION    # exposición activa al olor
PARADO      # sesión terminada / idle
```

### 3.2 `PhaseEvent` (lo que viaja en la notificación)
Objeto inmutable con el contexto que los suscriptores necesitan:
```
phase: Phase                  # fase nueva
previous: Phase               # fase anterior
measurement_set_id: int|None  # sesión activa
reason: str                   # "base estable", "medicion completa", "stop manual"...
at: datetime
```

### 3.3 `PhaseState` (Subject / Publisher)
Única fuente de verdad de la fase y de la sesión activa.
```
class PhaseState:
    phase: Phase                     # lectura pública
    measurement_set_id: int | None

    def subscribe(sub, *, order: int) -> None
    def unsubscribe(sub) -> None
    async def set_phase(new: Phase, *, measurement_set_id=..., reason="") -> None
        # si no cambia, no hace nada (idempotente)
        # si cambia: actualiza estado y await self._notify(event)
    async def _notify(event) -> None
        # recorre los suscriptores EN ORDEN y los await secuencialmente
```
Absorbe lo que hoy hace el módulo `measurement_state` (que se elimina): el `drain`
leerá `phase_state.measurement_set_id`.

### 3.4 Interfaz `PhaseSubscriber`
```
class PhaseSubscriber(Protocol):
    async def on_phase_change(self, event: PhaseEvent) -> None: ...
```
**Async** a propósito (ver §5, trampa 2).

### 3.5 Suscriptores concretos
- **`BoardCommander`** — traduce fase → comando serial y lo envía a la placa:
  `BASE → "BASE\n"`, `MEDICION → "MED\n"`, `PARADO → "STOP\n"`. Es
  **agnóstico del hardware**: qué abre/enciende cada comando es cosa del firmware,
  no del PC. (ACK y heartbeat: ver §6.)
- **`MeasurementSetCloser`** — solo reacciona a `PARADO`: espera a que la cola del
  drain se vacíe (máx. 10 s) y escribe `stopped_at`. **Unifica la lógica de cierre
  hoy duplicada** en `observer._close_measurement_set` y `serial._flush_and_close`.
- **`PhaseLogger`** — registra la transición (sustituye los `print` sueltos).
- **`WebSocketNotifier`** *(futuro)* — empuja la transición a los clientes
  conectados. Entra como un `subscribe()` más, sin tocar nada.

### 3.6 `MeasurementController` (renombrado de `Observer`)
El bucle de decisión. Responsabilidades:
- sondear Postgres (lote reciente) y alimentar el `SignalAnalyzer`,
- aplicar el gate `min_medicion_seconds`,
- al confirmar transición, `await phase_state.set_phase(...)`,
- leer la fase actual de `phase_state` (no mantiene su propia copia del estado).

No conoce ni el serial, ni la BD de cierre, ni WebSockets. Solo decide y publica.

## 4. Flujo completo (autónomo)

```
POST /serial/start (name)
  ├─ crea MeasurementSet en BD
  ├─ serial_reader.start()
  └─ await phase_state.set_phase(BASE, measurement_set_id=id, reason="start")
        → BoardCommander: "BASE\n"   (placa: aire limpio / reposo)
        → PhaseLogger

[MeasurementController, en bucle]
  detecta base estable (analizador, require_rise=False)
  └─ await phase_state.set_phase(MEDICION, reason="base estable")
        → BoardCommander: "MED\n"    (placa: introduce muestra / abre válvula)
        → PhaseLogger

  detecta medición completa (gate 30s + estable, require_rise=True)
  └─ await phase_state.set_phase(PARADO, reason="medicion completa")
        → BoardCommander: "STOP\n"   (placa: cierra/apaga → estado seguro)
        → serial_reader.stop()
        → MeasurementSetCloser: flush cola + stopped_at
        → PhaseLogger

POST /serial/stop  (parada manual)
  └─ await phase_state.set_phase(PARADO, reason="stop manual")   (mismo camino)
```

Nota: arrancar/parar el `serial_reader` y comandar la placa son cosas distintas.
`serial_reader.stop()` (deja de leer) se dispara en `PARADO`; lo ubicamos en el
orden de suscriptores (§5) **después** de mandar `STOP` a la placa.

## 5. Las dos trampas (y cómo las resolvemos)

### Trampa 1 — "los suscriptores reciben notificaciones en orden aleatorio"
La página lo lista como desventaja, y a nosotros nos afecta: en `PARADO` hay
dependencias de secuencia (mandar `STOP` a la placa **antes** de desmontar; cerrar
el `MeasurementSet` solo **después** de vaciar la cola del drain).

**Solución**: la suscripción lleva un `order` explícito; `_notify` recorre y
**`await` secuencialmente** en ese orden. Orden propuesto en `PARADO`:
```
1. BoardCommander       → "STOP\n"  (seguridad primero: la placa para)
2. (serial_reader.stop)
3. MeasurementSetCloser → flush + stopped_at
4. PhaseLogger
```
Determinista, no aleatorio. (El flush+cierre es una secuencia *interna* del closer,
no entre suscriptores.)

### Trampa 2 — `update()` síncrono vs. nuestro mundo async
La página asume `update()` síncrono; nosotros tenemos I/O async (serial, BD). Si
`notify` llamara síncrono a algo bloqueante, congelaría el bucle de decisión.

**Solución**: `on_phase_change` y `_notify` son `async`, y el controller hace
`await set_phase(...)` desde su tarea async. Las reacciones rápidas (comando serial,
log) se await sin problema. Las fire-and-forget (push WebSocket) pueden lanzar
`asyncio.create_task` internamente. El flush de 10 s del closer se await a propósito
(estamos parando: no hay nada que no deba esperar).

## 6. Seguridad de hardware (firmware) — nota

Como la placa actúa hardware, el firmware debe tener **estado seguro + watchdog**:
si no recibe comando en N segundos (PC colgado, USB fuera), vuelve solo a seguro
(válvula cerrada, bomba apagada). Implica que `BoardCommander` envíe un **heartbeat**
periódico, y que la placa **confirme (ACK)** cada comando. Para v1 se puede arrancar
sin ACK (fire-and-forget + log) y añadirlo como mejora; el watchdog del firmware es
innegociable en cuanto haya actuadores físicos.

El protocolo concreto (`BASE`/`MED`/`STOP`, ACK, heartbeat) y **qué actúa cada
comando** se define al cerrar el montaje físico. El diseño Python es **agnóstico**:
solo emite los comandos.

## 7. Cambios en el código existente

**Renombrar**
- `app/services/observer.py` → `app/services/controller.py`
- clase `Observer` → `MeasurementController`
- actualizar import en `main.py`

**Modificar**
- `serial_reader.py`: añadir `send_command(text)` (escribe al puerto). Escribir desde
  la tarea async mientras el hilo lee es válido en pyserial; se coordina con el lock.
- `main.py` (`lifespan`): crear `PhaseState`, registrar suscriptores con su `order`,
  pasar `phase_state` al `MeasurementController`. El `drain` lee `phase_state`.
- `routers/serial.py`: `/start` y `/stop` pasan a publicar fase en `phase_state`
  (en vez de la lógica de cierre actual, que migra al `MeasurementSetCloser`).
- eliminar `measurement_state.py` (su estado vive en `PhaseState`).

**No se toca**
- `analyzer.py` (calculadora pura) y todo el trabajo de Fase 1 (umbral, histéresis,
  debounce, latch). Intactos.

## 8. Plan de implementación por pasos

1. `Phase`, `PhaseEvent`, `PhaseSubscriber`, `PhaseState` (+ tests del Subject:
   suscribir, orden, idempotencia, notificación).
2. Renombrar `Observer → MeasurementController` y que publique en `PhaseState` en vez
   de actuar directamente (comportamiento equivalente, sin placa todavía).
3. `serial_reader.send_command()` + `BoardCommander`.
4. `MeasurementSetCloser` (absorbe la lógica duplicada de cierre).
5. `PhaseLogger`; eliminar `measurement_state`.
6. (futuro) `WebSocketNotifier` + timeouts de base/medición.

Cada paso deja el sistema funcionando; el 2 es puro refactor verificable sin hardware.

## 9. Cuestiones abiertas (a decidir antes de implementar)

- **Nombre del controlador**: `MeasurementController` (propuesto) vs. `PhaseController`
  / `SignalSupervisor`.
- **Notificación secuencial siempre** (propuesto, simple y correcto) vs. concurrente
  para los suscriptores independientes (optimización; de momento no hace falta).
- **ACK de la placa en v1** o como mejora posterior (propuesto: mejora).
- **Eliminar `measurement_state`** y absorberlo en `PhaseState` (propuesto: sí).
- **Protocolo serial y actuadores físicos**: pendiente del montaje de hardware; no
  bloquea el diseño Python (agnóstico).
