# callscore · Calidad de llamadas con un modelo que no escribe

*Read this in [English](README.md).*

Cada grabación de un call center sale catalogada con agente, equipo, fecha, nota de calidad, fallos eliminatorios y KPIs, en una SQLite que alimenta la evolución por agente y equipo, las sesiones de coaching ordenadas por gravedad y un informe de feedback entre equipos. El modelo, Jev (TypeSafe, vía OpenRouter), no escribe ni una palabra: solo elige entre opciones cerradas. El código mide, calcula las notas y copia cada cita de la transcripción.

> La IA tiene riesgos. El código los acota. La norma responde de lo que queda.

**Demo** con llamadas artificiales, declaradas como tales: ni un dato de ningún call center real.

[Filosofía de diseño](#filosofía-de-diseño) · [Los cinco pasos](#los-cinco-pasos-en-este-proyecto) · [Probarlo](#probarlo) · [Resultados](#resultados) · [Medido](#medido) · [Limitaciones](#limitaciones) · [Seguridad y regulación](#seguridad-y-regulación)

---

## Filosofía de diseño

Cualquier aplicación con IA tiene cinco pasos. Solo el paso 4 invoca un modelo; los otros cuatro son código: reproducibles, testeables, sin red. El paso 5 nunca corrige: marca y degrada. Texto completo en [epifaneia.dev](https://epifaneia.dev).

```
 1 LIMPIEZA      2 CONTEXTO      3 GUARDARRAÍL IN    4 PROCESO        5 GUARDARRAÍL OUT
 ■ código        ■ código        ■ código            ▲ modelo         ■ código
```

## El escenario

Un equipo de calidad escucha a mano una muestra de llamadas y las puntúa con un formulario: saludo, verificación, escucha, solución, cierre. Escucha pocas, tarda, y dos evaluadores no puntúan igual. Lo que se quiere es lo mismo con todas las llamadas: cada fallo con el turno que lo demuestra, los KPIs en media frente al objetivo del servicio, y saber qué agente necesita una sesión de coaching y sobre qué.

## Dónde aporta valor la IA

En leer una conversación y contestar preguntas cerradas sobre ella: ¿verifica el agente la identidad?, ¿cuánto sondea la necesidad, de 0 a 2?, ¿qué turno lo muestra mejor? Eso es lo único que hace Jev. Las notas salen de una fórmula, los medidores (duración, silencio, interrupciones) salen de los tiempos del audio, y cada consejo de coaching está escrito de antemano en el formulario, con su fuente. Cuando Jev no está seguro, la línea queda dudosa y va a revisión: no cuenta como fallo ni como acierto.

---

## Los cinco pasos en este proyecto

★ marca dónde está la mejora en este proyecto: un **modelo que solo decide** y un **guardarraíl de salida** que contrasta sus decisiones con lo medido.

| Paso | Qué hace aquí | |
|---|---|---|
| 1 · Limpieza | `pipeline/s1_limpieza.py`: audio en estéreo (agente a la izquierda, cliente a la derecha, como graba una centralita) → turnos numerados con faster-whisper large-v3-turbo en local, palabra a palabra y por canal. Quién habla sale del canal, no de un modelo. Fecha y agente son etiquetas de la grabación. | |
| 2 · Contexto | `pipeline/s2_contexto.py`: el equipo sale de la plantilla; duración, silencio, reparto del habla e interrupciones (solape de 0,3 s o más) salen de los tiempos. El texto que lee Jev marca los turnos que pisan al otro, porque un solape no se ve en el texto. | |
| 3 · Guardarraíl de entrada | `pipeline/s3_guardarrail_in.py`: el formulario (`config/formulario.json`) se convierte en preguntas cerradas: sí/no con criterios explícitos, escalas 0-1-2, y para la evidencia, solo los turnos del agente como opciones. Nada de texto libre. | |
| 4 · Proceso | `pipeline/s4_proceso.py` y `clients/jev.py`: tres pasadas de Jev por llamada (calidad, KPIs, evidencia de los fallos). Por defecto el motor es simulado, sin red; gastar exige `JEV_MOTOR=openrouter` y tiene tope acumulado. | ★ |
| 5 · Guardarraíl de salida | `pipeline/s5_guardarrail_out.py`: una decisión con probabilidad entre 0,35 y 0,65, o con poca confianza, queda **dudosa**. Una eliminatoria dudosa no elimina: manda la llamada a revisión. Una escucha dada por buena con tres interrupciones medidas o más pasa a dudosa. La nota de calidad sale de una fórmula con pesos por gravedad; los KPIs se guardan como medida y se juzgan en media. La cita es el texto del turno, copiado por el código. | ★ |

## Probarlo

Sin red y sin gastar, con el motor simulado (decide al azar, así que solo prueba la fontanería) y las tres transcripciones de muestra:

```bash
python -m venv .venv && .venv\Scripts\activate          # en Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                    # CUSTODIA_ACTOR; la clave de OpenRouter, solo aquí
python run.py                           # → data/prueba/: jev.db, coaching.md, estadistica.html
JEV_MOTOR=seco python run.py            # escribe en data/peticiones/ lo que se enviaría, sin enviarlo
```

Con Jev de verdad (gasta; tope acumulado en dólares con `JEV_TOPE_USD`, 0,25 por defecto):

```bash
JEV_MOTOR=openrouter python run.py
python run.py data/voz/*/*_telefono.wav     # desde audio: cada X.wav con su X.etiquetas.json
```

La muestra completa, día a día, con voz generada en local (ver `requirements-voz.txt`):

```bash
python tools/muestra/avanzar.py --hasta 20     # fabrica, transcribe y procesa los 20 días
python tools/muestra/ejemplos.py               # citas del Equipo Norte para el informe de feedback
python tools/muestra/desvio.py                 # desvío frente al diseño, escrito en este README
python tools/verificar_citas.py                # comprueba que cada cita del formulario es literal en su fuente
```

## Resultados

La muestra completa, procesada con Jev de verdad (120 llamadas, 0,018 $):

- [`data/estadistica.html`](data/estadistica.html): evolución semanal de la nota de calidad y de los KPIs por equipo, cada agente frente a la media de su equipo, y la tabla con llamadas, eliminadas y en revisión por semana. Una página sin dependencias: descárgala y ábrela en el navegador.
- [`data/coaching.md`](data/coaching.md): agentes ordenados por la gravedad de sus faltas, cada una con el consejo del formulario y el turno que la demuestra. Las dudosas van aparte, pendientes de revisión.
- [`data/feedback.md`](data/feedback.md): lo que el Equipo Norte hace mejor que el Sur hasta el día del feedback, línea a línea, con llamadas a la acción (el consejo del formulario, el dato del Norte como objetivo, cómo lo hace el Norte y dónde falla el Sur, con cita) y si la distancia se cerró después.
- [`data/jev.db`](data/jev.db): la SQLite con llamadas, líneas de calidad y KPIs.

**Calidad por llamada, KPIs en media.** Una verificación que falta es un fallo sin más contexto, y una eliminatoria deja la llamada en 0. Los KPIs no: por llamada solo se guarda la medida, y se juzga la media por semana, agente y equipo frente al objetivo del servicio. **La mejor llamada de la muestra es larga**: el perfil P03 (avería compleja: pide permiso para la espera, da cita técnica con fecha, no se resuelve en la llamada porque hace falta un técnico) saca 10 sobre 10 en calidad y es la más larga del catálogo. Las mejores llamadas son las difíciles y necesitan más tiempo; la duración solo es mala en promedio.

---

## De dónde sale el formulario

Ninguna línea de calidad es inventada. Cada una cita el documento público del que sale, con sección y página, y declara aparte lo que es decisión nuestra (pesos, umbrales, qué es eliminatorio). `tools/verificar_citas.py` descarga los originales y comprueba que cada cita está literal en su fuente.

| Fuente | Qué aporta |
|---|---|
| ICA (Colombia), *Protocolo de atención canal telefónico* | El esqueleto de la llamada: saludo, verificación, escucha, espera, solución con plazo, cierre |
| Lanbide (Gobierno Vasco), pliego de atención telefónica, §6.2 | Indicadores: duración media de conversación, llamadas resueltas, satisfacción |
| support-lead-kit (MIT), `scorecards/default.yaml` | Escala 0-1-2 y la idea de fallo eliminatorio (auto_fail) |
| Talkdesk, *Call Scoring Evaluation Form Items* | Contraste por apartados; solo referencia, sin cita literal (derechos reservados) |

Detalle y enlaces en `config/fuentes.json`.

## Las llamadas son artificiales, y se dice

No hay audio público de call center en español con licencia que permita publicarlo y con agente, fecha y fallos conocidos. Así que las llamadas se fabrican, y se declara:

- **Guiones** escritos a mano, con los fallos sembrados a propósito (`muestras/guiones/`). Cada llamada lleva sus etiquetas: fecha y agente. Ningún modelo decide quién es el agente.
- **Voz** de [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (Apache 2.0), en local. Esquema fijo: una voz para el agente (`ef_dora`) y otra para el cliente (`em_alex`), siempre las mismas.
- **Mezcla** en estéreo, agente a la izquierda y cliente a la derecha. Pausas e interrupciones salen del guion, así que son verdad conocida. Dos versiones: limpia (16 kHz) y teléfono (8 kHz, banda 300-3400 Hz, ruido a 25 dB).

## La muestra, día a día

120 llamadas en cuatro semanas de lunes a viernes, una por agente y día, repartidas a mano en `diseno/reparto.json` (nada aleatorio). `python tools/muestra/plan.py` las despliega en `diseno/plan.json` y `diseno/plan.html`, y comprueba el diseño:

- los doce perfiles del catálogo (`diseno/catalogo.html`) aparecen, así que la muestra cubre todos los niveles;
- el Equipo Norte va por delante en nota esperada todas las semanas (9,0-9,7 frente a 6,9-9,0);
- el Equipo Sur recibe feedback el viernes de la semana 2 y mejora en las semanas 3 y 4 en sondeo, escucha, solución y lenguaje, las líneas donde el Norte le sacaba ventaja; ninguna otra línea cae más de 15 puntos.

`tools/muestra/avanzar.py` procesa el siguiente día: pone el nombre del agente en el guion del perfil, genera el audio con Kokoro, lo pasa por el pipeline desde el `.wav` y regenera coaching, estadística, feedback y desvío con los datos hasta ese día. `--reiniciar` vuelve al día 0. Un turno del guion puede llevar `pausa`, segundos de silencio antes, o `interrumpe`, segundos que pisa al anterior. El reparto del habla no se diseña: sale lo que pida cada llamada y se informa tal cual.

Las citas del Norte del informe de feedback las añade `tools/muestra/ejemplos.py`, una pasada más de Jev: en cada línea que pide acción, qué turno de una llamada del Norte que la cumple lo muestra mejor. Si Jev no ve un turno claro, no hay cita.

---

## Medido

### Transcripción

Sobre las tres llamadas de muestra (371 palabras), con `tools/voz/medir_wer.py`:

| condición | WER total | errores de palabra (sin cifras) | turnos |
|---|---|---|---|
| limpio | 12,7 % | 0,5 % | 29/29 |
| teléfono | 9,4 % | 0,5 % | 29/29 |

Casi todo el WER son cifras: Whisper escribe «4» donde el guion dice «cuatro», y un DNI dictado sale junto. Se cuenta como error porque así llega a Jev. Duración e interrupciones medidas desde el audio coinciden con la verdad de la mezcla (±0,3 s); el silencio sale entre 3 y 8 puntos más alto, porque cuenta el aire que Kokoro deja alrededor de cada frase. Antes de elegir Kokoro se probaron Qwen3-TTS 0.6B y Chatterbox Multilingual: 3,8 % y 3,2 % de errores de palabra, y los dos más lentos que el tiempo real en una RTX 2060.

### Desvío de Jev frente al diseño

La verdad es el diseño: cada llamada de la muestra sale de un perfil del catálogo, que fija qué cumple y qué falla. Ese diseño lo escribió un modelo grande y se revisó a mano; Jev no lo ve nunca. `tools/muestra/desvio.py` compara lo que decide Jev con lo diseñado y reescribe esta tabla.

<!-- desvio:inicio -->
120 llamadas con perfil · motor: openrouter · error medio en la nota de calidad: 0.37 puntos sobre 10 · eliminatorias detectadas: 3 de 3 · eliminatorias sin estar en el diseño: 0 eliminaron la llamada, 3 quedaron en revisión

| línea | acuerdo con el diseño | desacuerdos marcados como dudosos | desacuerdos sin marcar |
|---|---|---|---|
| E1 Verificación de identidad | 100 % (120/120) | 0 | 0 |
| E2 Trato respetuoso | 100 % (120/120) | 0 | 0 |
| E3 Sin promesas no autorizadas | 98 % (117/120) | 3 | 0 |
| G1 Saludo y presentación | 89 % (107/120) | 10 | 3 |
| G2 Sondeo de la necesidad | 90 % (108/120) | 10 | 2 |
| G3 Escucha activa | 90 % (108/120) | 9 | 3 |
| G4 Empatía | 70 % (84/120) | 5 | 31 |
| G5 Solución y siguientes pasos | 99 % (119/120) | 0 | 1 |
| G6 Cierre | 99 % (119/120) | 1 | 0 |
| G7 Lenguaje claro | 99 % (119/120) | 1 | 0 |
| N1 Espera con permiso | 100 % (120/120) | 0 | 0 |
| resuelto Resuelto (KPI) | 86 % (103/120) | 5 | 12 |
| satisfaccion Satisfacción (KPI) | 90 % (108/120) | 5 | 7 |
<!-- desvio:fin -->

De las tres eliminatorias diseñadas, dos eliminan la llamada (la falta de respeto y la promesa no autorizada) y la tercera, una verificación que falta, queda en revisión porque Jev no estaba seguro. Las tres marcadas sin estar en el diseño son la misma frase de un guion («en 5 minutos tiene que tener la velocidad contratada»), que Jev lee como dar por seguro algo que no depende del agente: una lectura defendible, y quedó en revisión.

**Lo que destapó la primera medición (día 1, 6 llamadas).** La primera versión de E3 preguntaba con doble negación. Jev leyó como promesa no autorizada justo lo que el formulario pide, tramitar una devolución con plazo, eliminó con seguridad la llamada ejemplar, y el error medio en la nota fue de 3,01 puntos. Además Jev no veía las interrupciones y daba por buena la escucha de un agente que interrumpió tres veces. Se tocaron guardarraíles, no resultados: E3 pasó a preguntar en positivo con criterios de sí y de no, el texto marca los turnos que pisan al otro, y una escucha buena con tres interrupciones medidas pasa a dudosa. Con el mismo día repetido, el error bajó a 0,43 puntos.

### Coste

La muestra completa (120 llamadas, tres pasadas por llamada, más la pasada de ejemplos del feedback): **0,018 $**. Lo apunta el registro de custodia, llamada a llamada.

---

## Limitaciones

- **Las llamadas no son reales.** Hay 21 guiones escritos a mano, dos voces sintéticas fijas y ningún matiz de emoción, acento o ruido de oficina. Nada de lo medido aquí se puede trasladar sin más a llamadas de verdad.
- **La verdad es un diseño, no una anotación independiente.** Los perfiles los escribió un modelo grande y se revisaron a mano, pero nadie más ha anotado las llamadas. El desvío mide cuánto coincide Jev con ese diseño. Donde el diseño discute, como la promesa de P11 que Jev lee como garantía, no hay un tercero que decida.
- **La muestra es pequeña y se repite.** Son 120 llamadas, pero salen de 12 perfiles y 21 guiones, así que Jev lee casi el mismo texto varias veces. Por eso el acuerdo tiene menos variedad de la que sugieren las 120.
- **El sesgo del Norte y la mejora del Sur están sembrados.** La estadística y el informe de feedback demuestran que el pipeline recupera lo que se diseñó, no que esos patrones existan en un call center.
- **Empatía (G4).** Es el punto flojo de Jev: coincide con el diseño en un 70 %, y los 31 desacuerdos que no marca como dudosos van todos en la misma dirección, con Jev más generoso. Se deja medido, sin corregirlo.
- **Lo que se mide en el texto.** «Resuelto» y «satisfecho» los estima Jev a partir de la transcripción, mientras que el pliego de Lanbide mide la satisfacción con encuestas. Jev no oye el tono: las interrupciones solo existen porque el código marca los solapes en el texto.
- **Transcripción.** Whisper falla en las cifras y en algún «a Dios» donde el agente dice «adiós». En tres llamadas, el canal del agente tuvo que transcribirse sin filtro de voz por un fallo conocido de faster-whisper, y queda anotado en los avisos. El silencio medido sale entre 3 y 8 puntos más alto por el aire que deja Kokoro, y por eso el Norte supera el objetivo de silencio.
- **Las citas son de Jev.** El turno que elige como prueba no siempre es el más claro. En escucha cita a menudo «Me da el DNI…», el turno que pisa al cliente, pero la marca de interrupción no se guarda con la cita y en el informe no se ve. En lenguaje claro no encuentra ejemplo del Norte, porque lo bueno es que falten tecnicismos. Las citas de ejemplo se pierden si se reprocesa la llamada.
- **Los umbrales son nuestros.** La banda de dudoso (0,35-0,65), la distancia de 15 puntos que pide acción, el contraste de escucha con tres interrupciones y el objetivo de cada línea son decisiones de diseño, declaradas en `config/` o en el código, no estándares.
- **Jev cambia.** Todo se midió con `typesafe/jev-1.14-20261014` a través de la API alfa de decisiones de OpenRouter. Otra versión puede dar otro desvío.
- **Sin tests automáticos.** La comprobación es la propia muestra: el plan se valida con `plan.py`, los guiones con `guiones.py` y el resultado con `desvio.py`.

---

## Seguridad y regulación

Los mismos cuatro epígrafes que en el resto de repositorios. Las filas **hoy** son lo que hace el código; las filas **siguiente**, lo que falta.

| | | |
|---|---|---|
| **Confidencialidad** | Audio, transcripción, medidores, notas e informes, en local. Lo único que sale de la máquina es el texto de la transcripción hacia OpenRouter y TypeSafe, y solo con `JEV_MOTOR=openrouter`: por defecto el motor es simulado y no hay red. Una petición de más de 30 KB no se envía. `.env`, audios, respuestas en bruto y registro de custodia están fuera de git. | **hoy** |
| | Con llamadas reales, quitar DNI, teléfonos y nombres del cliente en el paso 1, antes de que el texto salga, y acordar con el proveedor dónde se procesa. | **siguiente** |
| **Trazabilidad** | Registro de custodia por llamada a Jev (`logs/custody.jsonl`): quién la lanzó (`CUSTODIA_ACTOR`, sin él no corre), paso, coste, tokens y modelo servido, nunca el texto. Cada respuesta cruda se guarda en `data/respuestas/`. Cada fallo del coaching lleva la llamada y el turno que lo demuestran. | **hoy** |
| **Prevención de fugas** | La clave vive solo en `.env`. Tenerla no gasta: hace falta pedirlo con `JEV_MOTOR=openrouter`, y un tope acumulado (`JEV_TOPE_USD`), sumado del coste real del registro, corta antes de pasarse. `JEV_MOTOR=seco` deja ver cada petición sin enviarla. | **hoy** |
| **Humano en el bucle** | Lo dudoso no cuenta: va a revisión, y una eliminatoria dudosa no deja la llamada en 0. El coaching separa lo pendiente de revisión, y el feedback solo cita fallos seguros. Nada se corrige en silencio: los cambios se hacen en las preguntas y en los guardarraíles, no en los resultados. | **hoy** |
| | Evaluar el rendimiento de trabajadores es un caso de alto riesgo del AI Act (anexo III, punto 4). En uso real, ninguna nota tendría efecto sobre una persona sin que alguien escuche la llamada, y el agente podría ver y discutir su evaluación. | **siguiente** |

Escrito con referencia al EU AI Act (2024/1689), el RGPD e ISO/IEC 27001. No se declara ninguna certificación ni conformidad: la tabla dice qué parte cubre el código y qué parte es de la empresa.

---

## Estructura

```
config/       plantilla.json · formulario.json · kpis.json · fuentes.json
diseno/       catalogo.json/.html · reparto.json · plan.json/.html
pipeline/     s1_limpieza · s2_contexto · s3_guardarrail_in · s4_proceso · s5_guardarrail_out
clients/      jev.py (OpenRouter, seco y simulado)
base/         db.py (SQLite) · coaching.py · estadistica.py · feedback.py
tools/        verificar_citas.py · voz/ (sintetizar, mezclar, medir_wer) · muestra/ (catalogo, plan, guiones, avanzar, ejemplos, desvio)
kit/          piezas del toolkit: custodia (identity, ledger), limpieza (text_norm)
muestras/     guiones/ de los doce perfiles · llamadas/ transcritas a mano para probar
data/         resultados de la muestra: jev.db · coaching.md · feedback.md · estadistica.html
```

Daniel Martín · [epifaneia.dev](https://epifaneia.dev) · Apache-2.0
