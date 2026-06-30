# Mis apuntes — teoría de la nariz electrónica

Apuntes para mí: entender **por qué** se procesa la señal como se procesa, no
quedarme con la receta. El hilo que sigo es:

> física del sensor → por qué el dato crudo no sirve → qué arregla cada
> transformación → por qué un array → por qué repeticiones.

Idea que quiero no olvidar: cuando entiendo el comportamiento físico del sensor,
cada paso del preprocesado deja de ser magia y se vuelve inevitable.

---

## 0. Glosario rápido (para no perderme)

| Símbolo | Nombre | Qué es |
|---|---|---|
| **Rs** | resistencia del sensor | lo que cambia con el gas; **no** lo mido directamente |
| **R0** | línea base (*baseline*) | Rs en aire limpio; mi referencia por sensor |
| **RL** | resistencia de carga | resistencia fija en serie con el sensor |
| **Vc** | voltaje de circuito | alimentación del divisor (en mi placa, 5 V) |
| **Vout** | tensión de salida | lo que mide el ADC, sobre RL |
| **ADC** | conversor A/D | 0–1023 (10 bits), proporcional a Vout |
| **VOC** | compuesto orgánico volátil | los gases del vino (etanol, ésteres…) |
| **CV** | coeficiente de variación | σ/media; mide reproducibilidad |
| **MOS** | metal-oxide semiconductor | el tipo de sensor (SnO₂) de los TGS |

---

## 1. Física del sensor MOS (TGS)

Mis TGS (Taguchi Gas Sensor) son **MOS** de **SnO₂** (dióxido de estaño) con un
**calentador interno** que los mantiene a ~300–400 °C.

Cómo funciona:

1. **En aire limpio:** el O₂ se adsorbe en la superficie del SnO₂ y *captura
   electrones* de la banda de conducción (forma O⁻, O²⁻). Eso levanta una **barrera
   de potencial** en las fronteras de grano → pocos electrones libres → **resistencia
   alta** = `R0`.
2. **Con gas reductor** (los VOC del vino): el gas reacciona con ese oxígeno
   adsorbido, **devuelve los electrones** a la banda de conducción → baja la barrera
   → **la resistencia cae**.

> **Lo central:** un MOS no mide "olor". Mide **cuánto le baja la resistencia un gas
> reductor**. Más analito → más cae Rs.

---

## 2. El circuito de medida (divisor de tensión)

El sensor no se mide solo: va en un **divisor de tensión**.

```
   Vc ──[ Rs (sensor) ]──┬──[ RL (carga) ]── GND
                         │
                        Vout  ──► ADC
```

Ley del divisor:

```
Vout = Vc · RL / (Rs + RL)
```

Y despejando lo que de verdad me interesa:

```
Rs = RL · (Vc − Vout) / Vout
```

**Signo de la respuesta** (apuntar bien esto): si Rs cae (hay gas) → Vout sube → ADC
sube. En mis medidas de vino el ADC sube (p. ej. 152 → 295), así que:

```
ADC arriba  ⟺  Rs abajo  ⟺  más VOC
```

---

## 3. Por qué el valor crudo NO sirve

Tres razones físicas:

1. **Variabilidad entre sensores:** dos TGS del mismo modelo salen de fábrica con R0
   muy distintos → el valor absoluto no es comparable.
2. **Deriva (*drift*):** R0 cambia con el tiempo (envejecimiento, envenenamiento de
   la superficie, humedad). El R0 de la rep 1 ≠ el de la rep 3 ≠ el de mañana.
3. **La deriva es sobre todo multiplicativa:** al derivar, *toda* la curva se escala
   (no se desplaza). Esto decide qué transformación uso (§4).

> Lo único reproducible es **cuánto cambia respecto a su propia base**, no el valor
> absoluto. Corregir esto es *baseline manipulation*: el corazón del preprocesado.

---

## 4. Baselining: relativizar a R0 (y por qué basta con los counts)

**Transformaciones posibles:**

```
diferencia:   Δ = Rs − R0          → quita parte ADITIVA
relativa:     (Rs − R0) / R0       → quita parte MULTIPLICATIVA   ← la buena
fraccional:   Rs / R0              → igual, sin centrar en 0
log:          log(Rs / R0)         → linealiza la ley de potencia (§6)
```

Uso la **relativa/fraccional** porque la deriva del MOS es **multiplicativa** y
dividir por R0 la cancela (si Rs y R0 suben ~20% a la vez, el cociente no cambia).
Además es adimensional → ya puedo comparar.

**⚠️ El matiz clave: ADC ≠ Rs.** El ADC mide `Vout`, y `Vout → Rs` es **no lineal**
(el `+RL` del divisor lo hace hiperbólico). Por tanto `ADC_gas/ADC_base ≠ Rs_gas/R0`.
Usar el cociente de counts crudos miente. Hay que invertir el divisor primero.

**Lo que se cancela (esto me lió, lo dejo claro):** desarrollando `Rs_gas/R0` con
`Rs = RL·(Vc−Vout)/Vout`, **RL se cancela siempre**. Y en mi placa, como la
referencia del ADC = los mismos 5 V que alimentan el divisor (`analogReference(DEFAULT)`),
`Vout/Vc = ADC/1023`, así que **Vc también se cancela** (se vuelve el fondo de escala
1023). Resultado: la normalización correcta sale **solo con los counts**, sin Vc ni RL:

```
Rs      (1023 − ADC_gas)  / ADC_gas
──  =  ───────────────────────────────
R0      (1023 − ADC_base) / ADC_base
```

> **Lo que NO me puedo saltar:** el término `(1023 − ADC)`. *Eso* es la conversión.
> No necesito conocer Vc ni RL, pero `ADC_gas/ADC_base` a secas está mal.

**Ejemplo que me convenció (deriva fantasma).** Mismo vino, respuesta real
`Rs/R0 = 0.40` siempre. El sensor deriva +20% en R0 entre sesiones:

```
Sesión 1 (R0 = 50 kΩ):  base ADC 171, gas ADC 341
Sesión 2 (R0 = 60 kΩ):  base ADC 146, gas ADC 301   (derivado)

Ingenuo  (ADC_gas/ADC_base):     341/171 = 2.00   |   301/146 = 2.06   ← deriva FALSA
Correcto ((1023−ADC)/ADC, luego cociente):
   2.00/4.98 = 0.40   |   2.40/6.01 = 0.40                              ← deriva CANCELADA
```

Con la fórmula buena: **0.40 y 0.40**, sin tocar Vc ni RL. Con el ADC crudo aparece
un 3% que no existe (con `(gas−base)/base` sube a ~7%). **Conclusión:** Rs/R0 basta y
no necesita Vc ni RL, pero "en counts" = `(1023−ADC)/ADC`, no `ADC` pelado.

---

## 5. R0: de dónde sale la línea base

`R0` = Rs en aire limpio, calculado **por repetición** (cada rep su base → corrijo
deriva). Cómo lo saco:

- tomar la **fase base** ya asentada (la **mitad final**),
- **media o mediana** de Rs en esa ventana → robusto al ruido puntual.

---

## 6. La característica = el estado estacionario (la meseta)

Pregunta que respondo aquí: **de toda la curva de medición, ¿qué número me quedo y
por qué?** Respuesta corta: el valor de la **meseta**. Lo demás es el porqué.

### 6.1 Qué significa "equilibrio"

Cuando meto el vino no pasa todo de golpe. Se tienen que asentar **dos** cosas:

1. **La concentración en la cámara.** El gas tiene que llegar, llenar y mezclarse
   hasta que `C` alrededor del sensor sea estable. Depende del flujo, la geometría,
   cómo metí la muestra.
2. **La química de la superficie.** El gas reductor reacciona con el oxígeno
   adsorbido (§1). Al principio hay mucho oxígeno fresco → reacción rápida → Rs cae
   deprisa. Luego se llega a un **balance dinámico**: la velocidad a la que el gas
   "consume" oxígeno se iguala con la de re-adsorción → la cobertura deja de cambiar
   → **Rs deja de cambiar** → la curva se aplana.

Ese punto (pendiente ≈ 0) es el **equilibrio / estado estacionario**. Ojo: no es que
la física se pare, es que las velocidades de ida y vuelta se igualan. Solo ahí `Rs`
corresponde de forma estable a `C`.

### 6.2 La ley de potencia (qué es cada letra)

En equilibrio, la relación respuesta–concentración es una **ley de potencia** (la
curva de los datasheets de Figaro):

```
Rs / R0  ≈  a · C^(−b)        (b > 0)
```

- **`C`** = concentración del gas (ppm). Más vino evaporado → más `C`.
- **`Rs/R0`** = la respuesta normalizada que ya sé calcular (§4).
- **`b`** = **sensibilidad** (exponente); en TGS ~0.3–0.6 según gas.
- **`a`** = escala (valor de `Rs/R0` en `C = 1`).

Exponente **negativo** → más concentración, menor Rs/R0 (más gas reductor, menos
resistencia). Y como `b < 1`, la respuesta **satura**: duplicar `C` no duplica el
efecto (rendimientos decrecientes). Eso lo captura la potencia con exponente pequeño.

### 6.3 Por qué en log-log es una RECTA

Tomo logaritmos a los dos lados:

```
log(Rs/R0)  =  log(a)  −  b · log(C)
```

Es `y = n + m·x` con `y = log(Rs/R0)`, `x = log(C)`, pendiente `−b`. O sea: **en ejes
log-log la curva es una recta** de pendiente `−b`. Por eso los datasheets están en
papel log-log: ahí se endereza y es fácil de leer y calibrar.

Para qué sirve: si quiero **estimar la concentración**, invierto la recta (mido
Rs/R0, conozco `a` y `b` → despejo `C`). **Pero** solo funciona si el Rs/R0 es el de
equilibrio → de ahí toda esta sección.

### 6.4 Ejemplo numérico de la ley

Con `a = 1`, `b = 0.5`:

```
C = 100 ppm → Rs/R0 = 100^(−0.5) = 1/√100 = 0.10
C = 400 ppm → Rs/R0 = 400^(−0.5) = 1/√400 = 0.05
```

Cuadruplicar `C` (100→400) solo bajó la respuesta a la mitad (0.10→0.05): la
saturación de §6.2. En log es perfectamente lineal → calibrable.

### 6.5 Por qué la ley vale en la MESETA y no en el transitorio

La ley relaciona el `Rs/R0` **final** (equilibrio) con `C`. Durante la subida el
sensor aún no llegó: superficie a medio reaccionar, cámara a medio llenar. Si leo
`Rs` a mitad del transitorio, obtengo un valor que **no corresponde** a la `C` real
por la ley → un estado intermedio que no significa nada cuantitativo.

```
   Rs/R0
    │
1.0 ┤●                          ← arranque (aire limpio, Rs = R0)
    │ ＼
    │   ＼   TRANSITORIO         ← aquí Rs/R0 NO cumple la ley (no leer)
    │     ＼  
    │       ＼____________
0.4 ┤                     ●●●●●  ← MESETA: equilibrio, AQUÍ leo la característica
    │                     └── la ley Rs/R0 = a·C^(−b) vale en este tramo
    └──────────────────────────► tiempo
```

Por eso la **respuesta estacionaria** (valor de la meseta) es la característica
**canónica**: el único punto de la curva con relación física reproducible con la
muestra.

### 6.6 Por qué el transitorio es "sucio"

La **forma** de la subida no la marca solo el gas, también:

- la **cinética** de adsorción/desorción (depende de la temperatura del sensor),
- la **difusión**: lo rápido que el gas llega a la cámara y al sensor → depende del
  **flujo**, geometría, cómo metí la muestra.

Consecuencia: el **mismo** vino con flujo distinto da **transitorios distintos pero
la misma meseta**. La meseta es reproducible; el transitorio, sin control fino de
flujo, no. (No es inútil: su *forma* discrimina gases con cinéticas distintas, §7,
pero como característica primaria es frágil.)

### 6.7 Conexión con el analyzer (¡importante!)

Aquí encaja todo lo que ya programé. El analyzer detecta cuándo la **pendiente → 0**,
es decir, cuándo `Rs` deja de cambiar = **cuándo se alcanza el equilibrio**. Justo el
instante en que la ley de §6.2 se vuelve válida y la característica es fiable.

> El analyzer no es un simple "botón de parar": es el **detector del instante
> correcto para muestrear**. Leer antes (en transitorio) → característica falsa; el
> analyzer me garantiza que leo en la meseta.

---

## 7. Características transitorias (cuando hagan falta)

La forma del transitorio (pendiente de subida, tiempo de subida, área bajo la curva,
tiempo de recuperación) lleva info extra: **gases distintos, cinéticas distintas**.
Dos analitos con la misma meseta pueden tener subidas diferentes → útil cuando la
amplitud estacionaria no separa clases. Precio: más ruido, más dependencia del flujo.
Orden que sigo: **meseta primero, transitorios después**.

---

## 8. Por qué un ARRAY de sensores (el principio fundamental)

**Un solo MOS es inútil para identificar:** es *poco selectivo*, responde a muchos
gases. Un TGS2620 que sube podría ser cualquier VOC.

La clave: **cada tipo de sensor tiene un perfil de sensibilidad distinto.** Mis 4 no
son redundantes, son **diversos**:

| Sensor | Sensibilidad principal |
|---|---|
| TGS2620 | solventes orgánicos / VOC |
| TGS2611 | gases combustibles (metano) |
| TGS2602 | VOC odorantes, amoníaco, H₂S |
| TGS2600 | contaminantes del aire, hidrógeno |

Aunque ninguno identifique nada solo, **el *patrón* de respuestas entre los 4 es
característico del olor**. Igual que mi nariz distingue miles de olores con receptores
poco selectivos: no es cada receptor, es la *combinación*. Esto es **olfacción por
reconocimiento de patrones** → por eso se llama "nariz".

> Paper fundacional: **Persaud & Dodd, 1982**.

### 8.1 Normalización vectorial: separar el "qué" del "cuánto"

Tras extraer una característica por sensor (§6), cada medición es un **vector** de 4
números — el *fingerprint*:

```
vino = [f_2620, f_2611, f_2602, f_2600]
```

Geométricamente es un **punto en 4D**. Un vector tiene dos cosas independientes:

- su **dirección** → hacia dónde apunta = qué sensores responden más unos respecto a
  otros = **el patrón** (el "qué es").
- su **longitud (norma)** → cómo de largo es = la **intensidad total** (el "cuánto
  hay").

**El problema:** la intensidad suele ser **estorbo**. Más muestra, más concentrado,
cámara más cargada → los 4 sensores suben **a la vez y en proporción**. El vector se
alarga pero **apunta igual**. Si comparo por distancia bruta, "mismo vino fuerte" y
"mismo vino flojo" parecerían distintos, cuando son lo mismo.

**La solución:** dividir el vector por su norma → longitud 1, conservando dirección.
**Tiro la intensidad, me quedo con el patrón.**

```
f_norm = f / ‖f‖     con  ‖f‖ = √(f_2620² + f_2611² + f_2602² + f_2600²)   (norma L2)
```

Geométricamente: proyecto todos los puntos sobre una **esfera de radio 1**. Lo que
era "cerca/lejos del origen" pasa a ser "en qué punto de la esfera caigo" = qué
dirección/patrón tengo.

### 8.2 Ejemplo numérico: concentrado vs. diluido

Mismo vino, dos intensidades (el diluido ~la mitad en todos):

```
concentrado: f = [8, 4, 6, 2]   ‖f‖ = √120 = 10.95
diluido:     f = [4, 2, 3, 1]   ‖f‖ = √30  =  5.48
```

Vectores **distintos** (uno mide el doble). Al normalizar:

```
concentrado / 10.95 = [0.730, 0.365, 0.548, 0.183]
diluido     /  5.48 = [0.730, 0.365, 0.548, 0.183]   ← ¡idéntico!
```

Caen en el **mismo punto** → reconocidos como el mismo vino, sin que confunda la
cantidad. Separar el *qué* del *cuánto*.

### 8.3 Qué norma usar

- **L2 (euclídea, la de arriba):** la común. Equivale a comparar luego por **ángulo**
  (*similitud coseno*): parecidos si apuntan parecido, da igual el tamaño.
- **L1 (dividir por la suma):** deja el vector como **proporciones que suman 1**
  (cada sensor = su % del total). Útil para pensar en "composición".

### 8.4 Cuándo SÍ y cuándo NO normalizar el vector

No es automático, es decisión:

- **SÍ**, si la intensidad es ruido (cantidad de muestra variable, distancia, carga
  de cámara) → me quita el estorbo y queda la identidad.
- **NO**, si la intensidad **es** información que quiero (distinguir "fuerte" de
  "débil" del mismo tipo) → la tiraría.

> **Ojo, no confundir con el autoescalado (§9-B).** Operan en *direcciones distintas*
> de la tabla:
> - **Vectorial** → por **muestra**, a lo ancho de los 4 sensores (una **fila**):
>   limpia la intensidad de *esa* medición.
> - **Autoescalado** → por **sensor**, a lo largo de todas las muestras (una
>   **columna**): pone los sensores en escala comparable para el modelo.
> Se pueden usar las dos; responden a preguntas distintas.

### 8.5 ¿Y esto no estropea el PCA que viene después?

Primero corregir la premisa: la normalización vectorial **sí cambia** lo que ve el
PCA — no es que no le afecte. Pero **lo cambia a mejor, a propósito**. No lo estorba,
lo *pre-acondiciona*.

**Qué hace el PCA (recordatorio):** busca las **direcciones de máxima varianza** y
las ordena (PC1 = donde más se dispersan los datos, PC2 la siguiente…). Me quedo con
las que más "explican".

**Problema si NO normalizo:** en e-nose la **mayor varianza** suele ser la
**intensidad total** (cuánta muestra, concentración) → mueve los 4 sensores en
proporción → dispersión enorme en la dirección "todos suben juntos". Como el PCA
persigue la varianza más grande:

```
sin normalizar  →  PC1 captura la INTENSIDAD (estorbo)
                →  malgasto mi componente principal en el "cuánto", no el "qué"
```

El PCA quedaría **secuestrado** por la intensidad.

**Normalizando antes:** esa varianza de intensidad **desaparece** (todos en la
esfera) → las componentes describen lo que queda: el **patrón** entre vinos = la
identidad. Por eso **componen bien**: la normalización retira *una* dirección de
estorbo conocida antes de que el PCA busque estructura en la varianza restante.

> **Matiz honesto:** normalizar mete los puntos en una **esfera** → quita un grado de
> libertad e introduce una leve dependencia no lineal (`Σf² = 1`). El PCA es lineal y
> ajusta un plano a datos en superficie curva. En la práctica la distorsión es pequeña
> y es flujo estándar; pero no es gratis del todo. (Y el **autoescalado** de §9-B suele
> ir **entre** la normalización y el PCA.)

---

## 9. Las dos normalizaciones (no confundir)

| | Qué hace | Por qué | Cuándo |
|---|---|---|---|
| **(A) Línea base** | respuesta relativa a su R0 | quita deriva e intensidad | dentro de cada measurement set |
| **(B) Array / entre sensores** | pone los 4 sensores en escala comparable | que un sensor "grande" no domine | sobre el vector final, entre muestras |

**(B) — autoescalado (z-score):** por cada sensor, resto su media y divido por su σ
(a lo largo de **todas** las muestras). Así cada sensor aporta varianza unidad →
todos pesan igual en PCA/distancias. Sin esto, el sensor más sensible "es" el análisis.

### 9.1 "Pero si analizo los sensores por separado, ¿para qué autoescalar?"

(Esta me la planteó mi compañero; la dejo resuelta.) Tiene razón a medias. Hay que
distinguir **dos etapas**:

- **Preprocesado — sí es por sensor, independiente.** Cada sensor tiene su R0, su
  Rs/R0 (§4) y su detección de meseta (§6). Aquí el autoescalado **no pinta nada**:
  dentro de *un solo* sensor, el z-score es una transformación lineal `(x−μ)/σ` que no
  cambia su análisis aislado (umbrales, orden, correlaciones se mantienen). **En esto
  lleva razón.**
- **Reconocimiento — aquí los sensores se COMBINAN.** El PCA, las distancias, el
  *fingerprint* (§8) **no** analizan sensores por separado: meten los 4 en un vector y
  miran su estructura **conjunta**. En cuanto dibujo un PCA o clasifico un vino, ya
  **no** los trato independientemente — los mezclo.

> "Analizar por separado" vale para **limpiar** cada señal. Pero la nariz, por
> definición (§8), **identifica por el patrón conjunto**. Esa fase es la que necesita
> autoescalar.

### 9.2 Por qué la mezcla sin autoescalar falla (con números)

Al combinar sensores (distancia euclídea entre fingerprints, o PCA) se suman las
contribuciones de los 4. Si uno tiene rango mucho mayor, **domina todo**:

```
Sensor A (muy sensible):  rango 0–100  (varianza ≈ 1000)
Sensor B (poco sensible): rango 0–5    (varianza ≈ 2)

Distancia:  d = √(ΔA² + ΔB² + ...)
  ΔA ~ decenas, ΔB ~ unidades → ΔA² aplasta a ΔB²
  → d ≈ |ΔA| → B NO contribuye → "solo uso A"
```

El PCA igual: PC1 se alinea con A, B queda invisible. *"El sensor más sensible ES el
análisis"* y los otros tres de adorno. Tras autoescalar, los 4 con varianza 1: "2σ en
B" pesa igual que "2σ en A". Cada sensor recupera su voz.

### 9.3 Por qué importa justo en una e-nose

Porque **la info que distingue dos vinos puede vivir en el sensor poco sensible.**
Dos vinos casi iguales en el sensor "grande" y distintos solo en uno "pequeño" → sin
autoescalar esa diferencia (la que me interesa) queda enterrada bajo el ruido del
dominante.

Enlaza con §8: el array vale por su **diversidad**, y el autoescalado **deja que todos
los sensores diversos contribuyan**, en vez de que el más ruidoso monopolice. Sin
autoescalar, desperdicio el array.

> **Regla práctica:** si de verdad nunca combino sensores (cada uno su informe), me
> salto el autoescalado. Pero en cuanto haga PCA, *clustering* o clasificación con el
> vector de los 4 (el objetivo de la e-nose), deja de ser opcional.

---

## 10. Repeticiones y repetibilidad

Pregunta: **¿por qué mido el mismo vino N veces y qué hago con esas N medidas?**

### 10.1 El modelo de error

Toda medida = tres cosas sumadas:

```
medida = señal verdadera  +  ruido aleatorio  +  error sistemático
```

- **Señal verdadera:** lo que quiero conocer (la respuesta real del vino).
- **Ruido aleatorio:** fluctuaciones que cambian de medida a medida, repartidas
  alrededor de la señal (ruido electrónico, microvariaciones de flujo, cuantización).
- **Error sistemático (sesgo):** desviación *constante* en la misma dirección (sensor
  derivado que mide todo 5% alto). Ojo: el ruido se promedia, el sesgo **no** → al
  sesgo lo ataco con normalización (§4) y protocolo, no con repeticiones.

Con **una** medida no separo señal de ruido. Con **varias** sí, porque el ruido
aleatorio, simétrico, **se cancela al promediar**.

### 10.2 Qué calculo

```
f_sensor = media de las N reps   ← mejor estimación de la señal
σ        = desviación típica     ← cuánto se mueve el ruido
CV       = σ / media             ← dispersión RELATIVA (reproducibilidad)
SE       = σ / √N                ← error de la propia media (10.4)
```

### 10.3 Por qué el CV y no solo σ

`σ` sola engaña: su tamaño "aceptable" depende de la magnitud. σ=10 es minúscula si la
señal vale 1000, enorme si vale 20. Por eso uso el **CV** (dispersión relativa):

```
CV = σ / media     (a menudo en %)
```

Adimensional y comparable entre sensores y vinos. Lectura:

- **CV bajo** (<5–10%) → reps coinciden → **fiable** → promedio con confianza.
- **CV alto** → algo falló (recuperación incompleta, agitación irregular tipo
  `vinoagitacionrara`, fuga, deriva en la tanda) → **criterio objetivo para descartar
  o repetir**, no "a ojo".

> El CV convierte "esto pinta raro" en un número con umbral. Es mi **métrica de
> calidad**.

### 10.4 Cuánto mejora promediar (y por qué no infinito)

La media no solo estima la señal: es **más precisa**. Su incertidumbre:

```
SE = σ / √N
```

El `√N` es la clave: promediar reduce el ruido con **rendimientos decrecientes**. De
1→4 reps **halvo** el error (√4=2); de 4→16 lo vuelvo a halvar pero cuesta 4× más
medidas. Por eso **3–5 reps** es el punto dulce. Más allá manda el sesgo/deriva (que
**no** baja con √N) → mejor cuidar el protocolo que añadir reps.

### 10.5 Repetibilidad vs. reproducibilidad

- **Repetibilidad:** dispersión en **las mismas condiciones**, seguido (mismo día,
  sensor, tanda). Es mi CV intra-tanda. Ruido de corto plazo.
- **Reproducibilidad:** dispersión cuando cambian condiciones (otro día, recalibrar,
  otra T/humedad). Suele ser **peor**, porque entra la **deriva** y los confusores de
  §11.

Mi protocolo de 3 reps seguidas mide **repetibilidad**. La reproducibilidad (comparar
entre sesiones) es justo donde Rs/R0 (§4) se vuelve crítico.

### 10.6 Por qué la best-practice: vino → aire limpio → vino → aire limpio…

Cada pieza tiene su porqué:

- **Aire limpio entre reps** fuerza la *desorción*: el gas se despega y el sensor
  vuelve cerca de R0 (§1). Sin esa limpieza, la rep 2 arranca **contaminada** por la 1
  → dejan de ser independientes y el promedio miente.
- **Re-establecer la base** cada ciclo → recalculo **R0 por rep** → corrijo la deriva
  entre una rep y la siguiente (§4, §5).
- **Comparar rep 1 vs 2 vs 3** delata problemas: si suben/bajan de forma
  **sistemática** (no aleatoria) → **deriva** o **recuperación incompleta** (cooldown
  corto). Es patrón, no ruido, y el CV solo no lo ve → hay que mirar la *tendencia*.

> Regla mental: el **aire limpio** da independencia; la **media** mata el ruido; el
> **CV** dice si me fío; la **tendencia entre reps** avisa de deriva. Cuatro
> herramientas, cuatro problemas.

---

## 11. Confusores físicos (tenerlos en el radar)

- **Humedad:** el vapor de agua también reacciona con el oxígeno superficial → cambia
  Rs mucho. Si varía durante la medición, corrompe la respuesta.
- **Temperatura ambiente** y **caudal de aire:** afectan cinética y equilibrio.

Best practice: controlar/medir humedad y temperatura, flujo constante. De momento, me
basta con saber que existen y que explican parte de la dispersión entre reps.

---

## 12. El pipeline completo (con el porqué de cada eslabón)

```
ADC crudo
  │  (no reproducible: deriva + variabilidad entre sensores)        §3
  ▼
convertir a Rs   [= (1023−ADC)/ADC en mi placa]                      §2, §4
  │  (la ley física vive en resistencia, no en voltaje)
  ▼
Rs / R0  por rep                                                     §4, §5
  │  (cancela deriva multiplicativa; adimensional)
  ▼
tomar la MESETA                                                      §6
  │  (donde vale Rs/R0 ~ C^(−b); el analyzer marca el instante)
  ▼
1 feature por sensor → vector [f2620, f2611, f2602, f2600]           §8
  │  (el fingerprint)
  ▼
media ± CV sobre N reps                                              §10
  │  (separa señal de ruido; CV = criterio de calidad)
  ▼
(futuro) autoescalar / normalizar vector                             §8, §9
  │  (que los 4 pesen igual; deja el patrón)
  ▼
(futuro) PCA / clasificación                                         §8
     (reconocer de qué vino es)
```

---

## 13. Plan de estudio (en orden)

1. **Datasheet + nota de aplicación Figaro del TGS** → divisor, RL, Vc, curvas Rs/R0
   vs concentración. (Cierra §1, §2, §4, §6 con números reales.)
2. **"Electronic nose: baseline manipulation"** → §3, §4. *Handbook of Machine
   Olfaction* (Pearce, Schiffman, Nagle, Gardner), capítulo de preprocesado.
3. **Principio del array / olfacción artificial** → §8. Persaud & Dodd (1982) +
   cualquier review de *machine olfaction*.
4. **CV y estadística de réplicas** → §10 (estadística básica).
5. **Autoescalado y PCA** → §9 (análisis multivariante).

---

## 14. Ejemplo completo, paso a paso, con datos

Recorro toda la cadena de §12 con números. **Montaje:** 4 sensores, referencia del
ADC = los 5 V de alimentación → uso `g = (1023 − ADC)/ADC` (§4). Mido **Vino A** con
**3 repeticiones** (vino → aire limpio → vino → …).

### Paso 1 — Datos crudos (Rep 1)

De cada fase tomo el valor de la **meseta** (el analyzer marca cuándo, §6). Aire
limpio → Rs alta → ADC bajo; vino → Rs cae → ADC sube (§1, §2).

| Sensor | ADC base | ADC gas (meseta) |
|---|---|---|
| TGS2620 | 170 | 340 |
| TGS2611 | 180 | 300 |
| TGS2602 | 160 | 380 |
| TGS2600 | 175 | 290 |

### Paso 2 — ADC → factor `g = (1023 − ADC)/ADC`

No uso el ADC directo (mentiría, §4): aplico el `(1023 − ADC)`.

| Sensor | g_base | g_gas |
|---|---|---|
| TGS2620 | (1023−170)/170 = **5.018** | (1023−340)/340 = **2.009** |
| TGS2611 | 843/180 = **4.683** | 723/300 = **2.410** |
| TGS2602 | 863/160 = **5.394** | 643/380 = **1.692** |
| TGS2600 | 848/175 = **4.846** | 733/290 = **2.528** |

(RL se cancela en el paso siguiente, por eso ni aparece.)

### Paso 3 — Línea base → respuesta `S`

`Rs/R0 = g_gas / g_base` (§4). La **respuesta** como caída fraccional `S = 1 − Rs/R0`
∈ (0,1): mayor = respondió más fuerte.

| Sensor | Rs/R0 = g_gas/g_base | S = 1 − Rs/R0 |
|---|---|---|
| TGS2620 | 2.009/5.018 = 0.400 | **0.600** |
| TGS2611 | 2.410/4.683 = 0.515 | **0.485** |
| TGS2602 | 1.692/5.394 = 0.314 | **0.686** |
| TGS2600 | 2.528/4.846 = 0.522 | **0.478** |

**Fingerprint Rep 1:** `[0.600, 0.485, 0.686, 0.478]`

### Paso 4 — Repetir y agregar las 3 reps (§10)

Mismo proceso en reps 2 y 3:

| Sensor | Rep 1 | Rep 2 | Rep 3 | **Media** | σ | **CV** |
|---|---|---|---|---|---|---|
| TGS2620 | 0.600 | 0.612 | 0.588 | **0.600** | 0.012 | **2.0 %** |
| TGS2611 | 0.485 | 0.470 | 0.490 | **0.482** | 0.010 | **2.2 %** |
| TGS2602 | 0.686 | 0.690 | 0.680 | **0.685** | 0.005 | **0.7 %** |
| TGS2600 | 0.478 | 0.495 | 0.470 | **0.481** | 0.013 | **2.7 %** |

Todos los **CV < 5 %** → fiable, promedio sin dudar. (Si uno saliera al 25%, descarto
esa muestra — criterio objetivo, §10.3.)

**Fingerprint Vino A:** `A = [0.600, 0.482, 0.685, 0.481]`

### Paso 5 — Normalización vectorial: el "qué" sin el "cuánto" (§8.1)

Si mido **el mismo vino A pero diluido** → `A_dil = [0.360, 0.289, 0.411, 0.289]`
(≈ proporcional). Vectores **distintos** (A_dil más corto). Divido por su norma L2:

```
‖A‖     = √(0.600²+0.482²+0.685²+0.481²) = √1.293 = 1.137
‖A_dil‖ = √(0.360²+0.289²+0.411²+0.289²) = √0.466 = 0.682

A     / 1.137 = [0.528, 0.424, 0.602, 0.423]
A_dil / 0.682 = [0.528, 0.424, 0.602, 0.424]   ← ¡mismo punto!
```

Concentrado y diluido **caen en la misma dirección** → reconocidos como el mismo
vino. (Idealizado: una dilución real no es perfectamente proporcional por la ley de
potencia, §6.2, pero quedan muy cerca.)

### Paso 6 — Reconocimiento: añado más vinos y autoescalo (§9)

Para *identificar* comparo contra otros vinos. Mido B y C igual y junto los
fingerprints (uso las `S` medias, antes de normalizar, para ver el autoescalado):

| | TGS2620 | TGS2611 | TGS2602 | TGS2600 |
|---|---|---|---|---|
| Vino A | 0.600 | 0.482 | 0.685 | 0.481 |
| Vino B | 0.610 | 0.560 | 0.250 | 0.470 |
| Vino C | 0.595 | 0.485 | 0.690 | 0.300 |
| **media col.** | 0.602 | 0.509 | 0.542 | 0.417 |
| **σ col.** | 0.008 | 0.044 | 0.253 | 0.101 |

**Autoescalado** (z-score por columna, §9): `z = (valor − media_col) / σ_col`.

| | TGS2620 | TGS2611 | TGS2602 | TGS2600 |
|---|---|---|---|---|
| Vino A | −0.22 | −0.61 | **+0.57** | **+0.63** |
| Vino B | +1.08 | **+1.15** | **−1.15** | +0.52 |
| Vino C | −0.88 | −0.54 | **+0.59** | **−1.15** |

Ahora cada sensor en la misma escala (varianza 1) y se ve el **patrón**: B se
distingue por TGS2611 alto y TGS2602 bajo; C por TGS2600 muy bajo; A en su esquina.
Sin autoescalar, TGS2602 (σ=0.253) habría aplastado a los demás y "sería" el análisis
(§9.2).

> **Matiz honesto:** TGS2620 apenas varía (σ=0.008); el z-score lo **amplifica** a
> varianza 1 igual que a los demás. Si esa variación fuera ruido, el autoescalado le
> daría un peso que no merece. El autoescalado supone que la dispersión de cada sensor
> es **información**; con más muestras juzgaré si TGS2620 discrimina o solo mete ruido.

### Paso 7 — PCA y decisión (futuro, §8–§9) (Nubes de confianza etc, investigar aqui)

Con los vectores autoescalados, el **PCA** rota a las direcciones de máxima varianza y
proyecta a 2D. Esperado:

```
   PC2
    │        ● B
    │
────┼───────────── PC1
 ● A│
    │   ● C
```

- Las **3 reps** de un vino caen **juntas** (CV bajo → nube apretada).
- **Vinos distintos** caen **separados** (patrones distintos).
- Un vino nuevo se clasifica viendo **a qué grupo cae más cerca**.

### Resumen del flujo de datos

```
ADC [170, 340]  ──g──▶  [5.018, 2.009]  ──Rs/R0──▶  0.400  ──S──▶  0.600
   (por sensor)                                                      │
                                            4 sensores → [0.600, 0.485, 0.686, 0.478]  (rep 1)
                                                                     │  × 3 reps
                                            media±CV → A = [0.600, 0.482, 0.685, 0.481]  (CV<5%)
                                                                     │  + vinos B, C
                                            normalizar/autoescalar → patrón
                                                                     │
                                            PCA → A, B, C separados → identificación
```
