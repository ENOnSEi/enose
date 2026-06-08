# El analizador de señal — fundamento matemático

Documento de referencia de `app/services/analyzer.py` (`SignalAnalyzer`). Explica
**qué calcula y por qué**, con el detalle matemático. El analizador decide, por
cada sensor de forma independiente, si su señal está **subiendo** o **estabilizada**.

## 0. Notación y datos de entrada

Cada muestra del Arduino es un instante con un valor por sensor:

```
(t_ms, { sensor: valor_ADC })
```

- `t_ms` = `millis()` del Arduino (entero, milisegundos).
- `valor_ADC` ∈ [0, 1023] (lectura del convertidor de 10 bits).

Trabajamos **por canal** (cada sensor por separado). Para un canal, una ventana es
una secuencia de pares `(t_i, y_i)`, con el tiempo pasado a **segundos**:

```
t_i = t_ms_i / 1000        y_i = valor_ADC_i
```

## 1. Pendiente por regresión lineal (mínimos cuadrados)

Queremos la velocidad de cambio de la señal, es decir la pendiente `b` de la recta
que mejor ajusta los puntos de la ventana:

```
y ≈ a + b·x
```

No usamos dos puntos (que con ruido mienten), sino **todos** los de la ventana,
minimizando la suma de residuos al cuadrado:

```
S(a,b) = Σ_i ( y_i − a − b·x_i )²
```

Derivando e igualando a cero (`∂S/∂a = 0`, `∂S/∂b = 0`) salen las **ecuaciones
normales**:

```
Σy = n·a + b·Σx
Σxy = a·Σx + b·Σx²
```

Resolviendo para la pendiente:

```
        n·Σ(x·y) − Σx·Σy
b  =  ─────────────────────
         n·Σ(x²) − (Σx)²
```

Esto es exactamente lo que calcula `_slope_per_second`:

```
denom      = n·sum_x2 − sum_x²
b (u/s)    = (n·sum_xy − sum_x·sum_y) / denom
```

Como `x` ya está en **segundos**, `b` sale directamente en **unidades ADC por
segundo (u/s)**. No hace falta ningún factor de conversión extra.

**Robustez al ruido**: la regresión pondera todos los puntos; un pico aislado `y_k`
desplaza `b` solo en `O(1/n)`. Con una ventana de 4 s a 4 Hz, `n ≈ 16`.

**Casos degenerados**: si `n < 2`, o `denom = 0` (todos los puntos en el mismo
instante → recta vertical), se devuelve `None` (pendiente indefinida).

## 2. Estabilidad numérica: referir el tiempo a t₀

El denominador se puede reescribir como:

```
denom = n·Σx² − (Σx)² = n²·Var(x)
```

Es decir, es proporcional a la **varianza** de los tiempos. Si `x` son segundos de
`millis()` crudos (p. ej. ~3.6·10³ tras una hora), entonces `Σx²` y `(Σx)²/n` son
ambos enormes (~10⁷) y **casi iguales**: su resta es un número pequeño obtenido
restando dos grandes parecidos → **cancelación catastrófica** en coma flotante, que
destruye la precisión de `b`.

Solución (en `_slope_per_second`): referir el tiempo al primer punto de la ventana,

```
x_i = t_i − t₀,    con t₀ = t_0 de la ventana
```

La pendiente es **invariante** a ese desplazamiento (restar una constante a `x` no
cambia `b`), pero ahora `x_i ∈ [0, W]` (W = ancho de ventana, ~4 s), con magnitudes
pequeñas y `denom` bien condicionado.

## 3. Ventana deslizante temporal

Solo se usan los puntos dentro de los últimos `W = window_seconds` respecto a la
muestra más reciente `t_last`:

```
se incluye (t_i, y_i)  ⟺  t_i ≥ t_last − W
```

La ventana **desliza**: en cada actualización entra lo nuevo y caduca lo viejo. Es
temporal (segundos), no por número de muestras, para ser robusta si cambia la
frecuencia de muestreo. La dinámica de los sensores TGS es de segundos, así que
`W ≈ 4 s` capta la tendencia real sin dejarse llevar por el ruido de ms.

## 4. Decisión con histéresis (banda muerta)

Sea la **magnitud** de la pendiente `m = |b|`. En vez de un único umbral usamos dos,
definidos a partir del umbral central `T` (`slope_threshold`) y la fracción de
histéresis `h` (`hysteresis`):

```
L = T·(1 − h)      (límite inferior)
U = T·(1 + h)      (límite superior)
```

Regla de voto del canal:

```
m < L          → vota ESTABILIZADO
m > U          → vota SUBIENDO
L ≤ m ≤ U      → no vota (banda muerta: se mantiene el estado)
```

- **Por qué la magnitud `|b|`**: nos interesa "se mueve" vs. "está plano",
  independientemente del signo (subida o bajada).
- **Por qué `T` pequeño y positivo, no cero**: estabilizar = `m → 0`. Con `T = 0` la
  banda `[L,U]` colapsa en torno a 0 y la pendiente plana quedaría siempre "dentro",
  sin poder confirmar nunca. Con `T > 0`, `m ≈ 0 < L` confirma estabilización.
- **Por qué dos umbrales**: si solo hubiera uno, cuando `m` oscila junto a él el
  estado conmutaría sin parar (*chattering*). La banda `[L,U]` exige cruzar **todo**
  el ancho para cambiar, como el diferencial de un termostato.

## 5. Debounce temporal (confirmación)

Un voto distinto al estado actual no cambia el estado de inmediato: debe **sostenerse**
un tiempo mínimo `τ = confirm_seconds`. Formalmente, sea `t*` el instante (en tiempo
de señal) en que el voto empezó a diferir del estado actual:

```
se confirma el cambio  ⟺  t_now − t* ≥ τ   (y el voto no cambió en (t*, t_now])
```

Cualquier interrupción del voto reinicia `t*`. Así, un cruce puntual del umbral que
revierte antes de `τ` **no** dispara una transición falsa.

**Detalle**: `t_now` y `t*` se miden con el **tiempo de la propia señal** (el `t_ms`
de la última muestra), no con el reloj de pared. Si dejan de llegar datos, el tiempo
no avanza y nada se confirma — justo lo deseado.

## 6. Latch "primero sube, luego se estabiliza" (require_rise)

Variable booleana por canal `r` (`_has_risen`), que se activa la primera vez que se
observa una subida real:

```
si m > U  ⟹  r ← verdadero   (de forma permanente hasta el reset)
```

Cuando `require_rise` está activo, el voto ESTABILIZADO se **suprime** mientras el
canal no haya subido:

```
si voto = ESTABILIZADO  ∧  require_rise  ∧  ¬r   ⟹   voto ← (ninguno)
```

**Motivo**: en la fase de medición la señal arranca plana (el olor aún no ha llegado
al sensor), `m ≈ 0 < L`. Sin el latch, el analizador confirmaría ESTABILIZADO en el
arranque y dispararía un `stop` prematuro. Con el latch, solo puede estabilizar tras
haber subido de verdad.

`require_rise` es **por fase**: `False` en base (línea plana que solo debe asentarse,
sin subida previa) y `True` en medición (rampa → meseta).

## 7. Combinación multi-sensor

Cada canal `i` aporta su estado `s_i ∈ {SUBIENDO, ESTABILIZADO}`. La decisión global
combina los canales según la política `P`:

```
estable_global =  AND_i (s_i = ESTABILIZADO)     si P = ALL       (por defecto)
                  OR_i  (s_i = ESTABILIZADO)     si P = ANY
                  ( #{i : s_i = ESTABILIZADO} > n/2 )  si P = MAJORITY
```

Con `ALL`, el canal con la meseta más "movida" es el que manda: el sistema no se
declara estable hasta que **todos** lo están.

## 8. Emisión de transición

El estado global combinado se mapea a `ESTABILIZADO` (si `estable_global`) o
`SUBIENDO`. Se emite una **transición** únicamente en el instante en que ese estado
global **cambia** respecto al `update` anterior:

```
transition = nuevo_estado_global   si  nuevo ≠ anterior
             None                   en otro caso
```

El consumidor (el bucle de control) actúa **solo** cuando `transition ≠ None`, nunca
en cada muestra.

## 9. Parámetros y su calibración

| Símbolo | Parámetro | Valor | Significado |
|---|---|---|---|
| `W` | `window_seconds` | 4.0 s | ancho de la ventana de regresión |
| `T` | `slope_threshold` | 7.5 u/s | umbral central de pendiente |
| `h` | `hysteresis` | 0.15 | semiancho relativo de la banda muerta |
| `τ` | `confirm_seconds` | 1.0 s | debounce |
| `P` | `policy` | ALL | combinación multi-sensor |
| `r` | `require_rise` | True (medición) | latch de subida previa |

### Cómo se eligió `T = 7.5` (ver `tools/calibrate.py`)

Con política `ALL`, el umbral debe cumplir dos cosas a la vez:

1. **Detectar la meseta**: `L` por encima de la pendiente de meseta más alta
   observada `s_meseta` (≈ 5.3 u/s en vino):
   ```
   L = T·(1−h) > s_meseta   ⟹   T > s_meseta / (1−h) = 5.3 / 0.85 ≈ 6.2
   ```
2. **Ver subir al sensor más flojo**: `U` por debajo del pico de subida más pequeño
   `s_pico` (≈ 9.7 u/s en vinoyagua tgs2611):
   ```
   U = T·(1+h) < s_pico    ⟹   T < s_pico / (1+h) = 9.7 / 1.15 ≈ 8.4
   ```

Rango factible `T ∈ (6.2, 8.4)`; se toma el centro ≈ **7.5** (márgenes ~1 u/s a
ambos lados). Un `T` mayor deja al sensor flojo sin "subir" y la medición no
estabiliza nunca; uno menor mete la meseta dentro de la banda de "subiendo".

> Estos valores salen de 5 grabaciones reales. **Reejecuta `calibrate.py` cuando
> tengas más datos**: son un punto de partida, no constantes físicas.

## 10. Resumen del pipeline por `update`

```
muestras ─▶ filtra ventana temporal [t_last−W, t_last]   (§3)
         ─▶ por canal: regresión LS con x = t−t₀ → b (u/s) (§1, §2)
         ─▶ m = |b|; voto por banda muerta [L,U]           (§4)
         ─▶ latch require_rise (suprime ESTABILIZADO si no subió) (§6)
         ─▶ debounce τ con tiempo de señal                 (§5)
         ─▶ estado por canal s_i
         ─▶ combinación política P → estable_global        (§7)
         ─▶ transición si el estado global cambió          (§8)
```
