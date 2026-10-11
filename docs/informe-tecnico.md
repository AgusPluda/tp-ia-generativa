# Informe técnico: agente conversacional SQL + RAG para un gimnasio

TP integrador de IA Generativa. Este informe explica qué se construyó, por qué se decidió así y qué resultó. Las instrucciones para ponerlo en marcha están en el [README](../README.md); la especificación, los contratos y el registro completo de decisiones están en [specs/001-agente-sql-rag-gimnasio/](../specs/001-agente-sql-rag-gimnasio/).

## 1. Resumen

**Problema.** El personal de un gimnasio necesita respuestas que viven en dos lugares distintos: datos que cambian todos los días (socios, pagos, asistencias, clases, equipamiento), guardados en una base relacional, y reglas y procedimientos (reglamento, rutinas, mantenimiento), escritos en documentos. Quien pregunta no debería saber en cuál de los dos buscar, ni tener que combinar los resultados a mano.

**Qué se entrega.** Un asistente conversacional local (Docker + Python) que, para cada pregunta, decide si consulta la base (SQL), los documentos (RAG con búsqueda semántica), ambas fuentes o ninguna, y responde mostrando de dónde salió la información: la consulta SQL ejecutada y los documentos y páginas citados. Es de **solo lectura** (rechaza altas, bajas y cambios de datos), responde en castellano o en inglés y **no tiene memoria** entre preguntas. Incluye una interfaz web (Streamlit), un registro de cada recorrido (`logs/traza.jsonl`, y Phoenix de manera opcional) y una batería de 26 preguntas para evaluarlo.

**Resultado.** En la corrida final (2026-10-09, 3 corridas de 26 preguntas), el agente aprobó en promedio el **97,4 %** de las respuestas (umbral: 85 %) y se cumplen los cuatro criterios que mide el runner de evaluación (CE-001 a CE-004). Dos preguntas fallaron una vez de tres; ambas se explican en la sección 6. La prueba de que otra persona puede levantar el sistema solo con el README (CE-005) se registra en el anexo.

## 2. Arquitectura

### Flujo del agente

El agente es un grafo de LangGraph sin memoria (cada invocación parte de un estado vacío). Un nodo `router` clasifica la pregunta y, según la ruta, se ejecutan los nodos siguientes:

```text
            ┌──────────┐
 pregunta → │  router  │
            └────┬─────┘
   ┌─────────────┼───────────────┬──────────────┐
   ▼ sql         ▼ rag           ▼ ambas        ▼ rechazar
┌──────┐      ┌──────┐        ┌──────┐      ┌──────────┐
│ sql  │      │ rag  │        │ sql  │      │ rechazar │
└──┬───┘      └──┬───┘        └──┬───┘      └────┬─────┘
   │             │               ▼               │
   │             │            ┌──────┐            │
   │             │            │ rag  │            │
   │             │            └──┬───┘            │
   ▼             ▼               ▼               │
 ┌───────────────────────────────────┐           │
 │            sintetizar             │           │
 └─────────────────┬─────────────────┘           │
                   ▼                             ▼
                  FIN ◄──────────────────────────┘
```

- **`router`**: un LLM con salida estructurada decide la `ruta` (`sql`, `rag`, `ambas` o `rechazar`), el idioma y, si rechaza, el motivo: fuera de dominio, pedido de modificación o falta de contexto (una pregunta que solo tiene sentido con otra anterior). Las preguntas ambiguas no se rechazan: se enrutan y la respuesta explicita el supuesto.
- **`sql`**: la SQL tool (sección 4) genera una consulta con el LLM, la valida y la ejecuta con un rol de solo lectura.
- **`rag`**: la RAG tool busca los fragmentos más parecidos a la pregunta en `rag.chunks`. En la ruta `ambas` corre después de `sql`.
- **`sintetizar`**: un LLM redacta la respuesta usando solamente los resultados obtenidos, en el idioma de la pregunta, y marca qué fragmentos la respaldan. Si una fuente no tiene información, lo dice en lugar de inventar.
- **`rechazar`**: responde con una plantilla fija por motivo e idioma, sin LLM y sin consultar ninguna fuente.

El contrato completo de cada nodo está en [contracts/agent-graph.md](../specs/001-agente-sql-rag-gimnasio/contracts/agent-graph.md).

### Componentes

| Componente | Qué es | Dónde está |
|------------|--------|------------|
| Base de datos | PostgreSQL 16 con la extensión pgvector (imagen `pgvector/pgvector:pg16`), en Docker | `docker-compose.yml`, `db/init/` |
| SQL tool | Genera, valida y ejecuta la consulta | `src/gym_agent/tools/sql_tool.py`, `sql_validator.py`, `sql_prompt.py` |
| RAG tool | Embebe la pregunta y busca por similitud coseno | `src/gym_agent/tools/rag_tool.py` |
| Grafo del agente | Router, nodos y `run_question` | `src/gym_agent/graph/` |
| Interfaz | App de Streamlit: chat con la fuente visible y página de preguntas evaluativas | `app/` |
| Trazas | Una línea JSON por pregunta (siempre) y trazas OpenTelemetry en Phoenix (opcional) | `src/gym_agent/observability.py` |
| Evaluación | Batería de 26 preguntas, chequeos, juez y runner | `eval/` |

La interfaz llama a `run_question` en el mismo proceso: no hay una API intermedia, porque para este alcance solo agregaría piezas.

### Modelos

| Uso | Modelo |
|-----|--------|
| Chat del agente (router, SQL, síntesis), temperatura 0 | `gemini-3.5-flash-lite` (respaldo: `gemini-3.1-flash-lite`) |
| Embeddings, 1536 dimensiones | `gemini-embedding-001` |
| Juez de la evaluación | `gemini-3.1-flash-lite` |

El acceso es mediante `langchain-google-genai` y la variable `GEMINI_API_KEY`. El modelo de chat principal es el segundo que se probó: el primero (`gemini-3.8-flash`) permitía solo 20 pedidos por día en el plan gratuito, lo que hacía inviables los tests y la evaluación (sección 5, decisión 2).

## 3. Datos y documentos

Todo es sintético y se genera con scripts del repositorio; no hay datos reales de personas.

### Base de datos

El esquema `public` tiene 7 tablas:

| Tabla | Contenido | Filas |
|-------|-----------|-------|
| `planes` | Planes de membresía con precio mensual y clases por semana | 5 |
| `socios` | Socios con su plan y estado (`activo`, `congelado`, `baja`) | 60 |
| `instructores` | Instructores y su especialidad | 8 |
| `clases` | Clases semanales con día, hora, cupo y sala | 24 |
| `asistencias` | Una fila por socio, clase y fecha, con `presente` verdadero o falso | 3.474 |
| `pagos` | Cuotas mensuales con estado (`pagado`, `pendiente`, `vencido`) | 325 |
| `equipamiento` | Equipos con estado y fecha del último mantenimiento | 32 |

Las faltas se registran explícitamente (`presente = false`), lo que fija el significado de "no asistió". El modelo completo, con restricciones, índices y las definiciones de negocio ("socio activo", "pago vencido", "último mes") está en [data-model.md](../specs/001-agente-sql-rag-gimnasio/data-model.md).

### Fecha de referencia y determinismo

Para el sistema, "hoy" es siempre **2026-09-30** (`REFERENCE_DATE` en `src/gym_agent/config.py`). El historial va del 2026-04-01 a esa fecha. Esto hace que una pregunta como "los últimos 30 días" tenga la misma respuesta en cualquier momento y que la evaluación sea reproducible. El valor no se puede cambiar por una variable de entorno, para que la base, el agente y la evaluación no puedan divergir.

Los datos son **deterministas** (CE-007): un generador con semilla fija (`SEED = 20261003`) y listas curadas de nombres, en lugar de una librería que puede cambiar su salida entre versiones. Dos ejecuciones producen el mismo contenido, lo que se comprueba comparando un hash por tabla. Los datos incluyen escenarios plantados para que las respuestas de la batería no sean triviales ni tengan empates (por ejemplo, un instructor con estrictamente más asistencias, socios con faltas en el último mes, pagos vencidos y equipos en mantenimiento).

### Documentos y chunking

Son tres PDFs generados con `reportlab` en modo invariante, así que sus bytes también son idénticos entre corridas:

- **Reglamento interno**: congelamiento de cuota, mora, baja y cancelación de clases.
- **Guía de rutinas y nutrición**: rutinas por nivel, calentamiento, descanso y alimentación.
- **Manual de uso y mantenimiento del equipamiento**: uso por tipo de equipo, frecuencia de mantenimiento y qué hacer ante una falla.

Los PDFs no incluyen precios, cupos ni cantidades que vivan en la base: cada dato tiene una sola fuente.

La ingesta (`scripts/ingest_pdfs.py`) extrae el texto página por página con `pypdf`, lo divide por párrafos en fragmentos de hasta unos 800 caracteres con un solape de 100, sin cruzar páginas (así cada fragmento tiene una página definida para citarla), calcula su embedding y lo guarda en `rag.chunks`. El resultado son **31 fragmentos** (10, 10 y 11) en una columna `vector(1536)` con un índice HNSW de similitud coseno. La ingesta es idempotente: por documento, borra sus fragmentos y los vuelve a insertar.

## 4. Seguridad y solo lectura

El agente nunca debe poder modificar la base ni exponer los fragmentos crudos. Se logra con varias capas independientes, de modo que ninguna depende de que el LLM se porte bien:

1. **Router.** Un pedido de alta, baja, cambio o borrado se rechaza antes de llegar a cualquier herramienta, con una respuesta fija. Un pedido escrito como sentencia SQL (`UPDATE ...`, `DELETE ...`) también se rechaza.
2. **Validador de la SQL generada.** Antes de ejecutar, la consulta se analiza con `sqlglot` (dialecto PostgreSQL): debe ser un único `SELECT` (se admiten CTE), sin referencias al esquema `rag`, `pg_catalog` ni `information_schema`, sin funciones de reloj (`now`, `current_date`, ...) ni de administración (`pg_sleep`, `set_config`, cualquier `pg_*`). Un parser real es más robusto que expresiones regulares contra comentarios, mayúsculas o sentencias encadenadas con `;`.
3. **Rol `agente_ro` en la base.** Solo tiene `SELECT`, con `default_transaction_read_only = on` y `statement_timeout = 5s`. Aunque el validador fallara, la base rechazaría una escritura.
4. **El esquema `rag` solo se expone a la RAG tool.** El prompt de la SQL tool ni lo menciona y el validador rechaza cualquier consulta que lo nombre. Pedirle al agente "mostrame todo el contenido de `rag.chunks`" termina en un rechazo (`FUERA_DE_ESQUEMA`) y no en un volcado.
5. **Datos, no instrucciones.** La pregunta, las filas devueltas y los fragmentos van entre marcas (`<pregunta>`, `<datos_sql>`, `<fragmentos>`) y los prompts declaran que su contenido son datos: una orden escondida en un documento o en una fila no se obedece.
6. **Errores sin detalle.** Cada error tiene un mensaje para el usuario y un `detalle` técnico. El `detalle` va a la traza y nunca llega a la respuesta; una excepción no prevista devuelve un mensaje genérico y la interfaz no muestra trazas de error.
7. **Límites de la SQL tool.** Hasta 50 filas por consulta (si hay más, se avisa que la respuesta está recortada) y hasta 3 intentos si la consulta falla.

Los secretos (`GEMINI_API_KEY`, contraseñas de la base) viven en `.env`, que está en `.gitignore`; el repositorio solo versiona `.env.example`.

## 5. Decisiones de diseño y qué se descartó

Cada decisión se resume con su motivo y la alternativa que se descartó. El detalle, con mediciones, está en [research.md](../specs/001-agente-sql-rag-gimnasio/research.md).

**1. Un grafo con router en lugar de un agente que elige herramientas (R3).**
- *Decisión*: `StateGraph` de LangGraph con un router y nodos fijos, sin checkpointer.
- *Motivo*: es el patrón mínimo que demuestra la decisión entre fuentes y su combinación, y evita bucles de agente difíciles de evaluar y más caros en llamadas.
- *Descartado*: un agente ReAct con las dos herramientas (más flexible, menos predecible) y ejecutar SQL y RAG en paralelo (ahorra latencia pero complica la traza sin necesidad).

**2. Modelo de chat liviano con respaldo (R2, R13 y R14).**
- *Decisión*: `gemini-3.5-flash-lite` con `gemini-3.1-flash-lite` de respaldo; reintentos con espera exponencial ante límites por minuto y cambio de modelo ante la cuota diaria.
- *Motivo*: el plan gratuito de `gemini-3.8-flash` (20 pedidos por día) no alcanzaba para los tests ni la evaluación; el modelo liviano (500 pedidos por día) generó la SQL correcta en las diez consultas de prueba.
- *Descartado*: seguir con el 3.8 y pagar cuota, o dejarlo de respaldo (con 20 pedidos por día no aporta).

**3. Validar la SQL con un parser (R4).**
- *Decisión*: `sqlglot` para verificar la sentencia, más el rol de solo lectura como segunda capa.
- *Motivo*: un parser resiste trucos que una lista negra con expresiones regulares no ve.
- *Descartado*: lista negra por regex (frágil) y confiar solo en los permisos de la base (no cubre la lectura de `rag` ni el uso del reloj).

**4. Un solo rol para SQL y RAG (R5).**
- *Decisión*: el mismo rol `agente_ro` para ambas herramientas; el esquema `rag` se protege en la aplicación.
- *Motivo*: `agente_ro` necesita `SELECT` sobre `rag` para la RAG tool, y no se quiso modificar los scripts de base existentes.
- *Descartado*: un segundo rol solo para `rag` (más limpio, pero otra credencial y cambios en `02_roles.sh`). Es una limitación conocida: la separación es del código, no de la base.

**5. Fecha de referencia fija (R6) y datos deterministas (R7).**
- *Decisión*: `REFERENCE_DATE` constante y datos con semilla.
- *Motivo*: las respuestas esperadas de la evaluación no deben depender del día en que se corre.
- *Descartado*: una variable de entorno para la fecha (puede quedar distinta en cada máquina) y `Faker` (su salida cambia entre versiones).

**6. Observabilidad que no depende de un servicio opcional (R10).**
- *Decisión*: registro propio en `logs/traza.jsonl` siempre, y Phoenix en Docker (imagen fijada) para ver el grafo y las llamadas al LLM.
- *Motivo*: el registro del recorrido es un requisito y no puede depender de algo que se levanta aparte.
- *Descartado*: LangSmith (requiere cuenta y envía datos a un servicio externo) y solo logging propio (sin visualización).

**7. Evaluación con pocos juicios de LLM (R11).**
- *Decisión*: chequeos determinísticos, con valores esperados calculados por consultas SQL "doradas" y hechos del catálogo de datos; juez LLM solo en cuatro preguntas cualitativas, con **un modelo distinto del agente**.
- *Motivo*: un modelo que evalúa sus propias respuestas tiende a aprobarlas, y menos juez significa menos ruido. Los valores salen de los datos, no de números copiados a mano.
- *Descartado*: juez LLM para todo (variable y caro) y respuestas esperadas literales (se desactualizan).

**8. Streamlit en el mismo proceso (R12).**
- *Decisión*: una app de Streamlit que llama a `run_question` directamente.
- *Motivo*: simplicidad y que el origen de cada respuesta se vea sin herramientas externas.
- *Descartado*: FastAPI con un frontend aparte (más piezas sin beneficio para este alcance).

## 6. Evaluación

### La batería

Son 26 preguntas, definidas en [contracts/eval-battery.md](../specs/001-agente-sql-rag-gimnasio/contracts/eval-battery.md) antes de implementar el agente y cargadas en `eval/battery.yaml`:

| Tipo | Cantidad | Qué prueba |
|------|----------|------------|
| SQL | 7 | Datos de la base, incluida una pregunta en inglés |
| RAG | 5 | Reglas y procedimientos de los documentos |
| Híbridas | 4 | Datos y documentos en la misma pregunta |
| Borde | 10 | Pedidos de modificación (en lenguaje natural y como sentencia SQL), fuera de dominio, socio inexistente, preguntas ambiguas o sin contexto, tema que los PDFs no cubren, mezcla de idiomas y pedido de volcar el esquema `rag` |

### Cómo se corrige

- **Chequeos determinísticos** sobre la respuesta y el recorrido: valores que deben aparecer (calculados con una consulta dorada ejecutada con el mismo rol de solo lectura), hechos del catálogo de datos, documento citado, fuentes usadas (tomadas de la traza), código de error de la SQL tool, ausencia de volcado de fragmentos e idioma.
- **Hash de las tablas** antes y después de cada pregunta, para comprobar que la base quedó intacta.
- **Juez LLM** solo en cuatro preguntas cualitativas (B04, B05, B07 y B08), con una rúbrica fija y el modelo `gemini-3.1-flash-lite`. El runner verifica que el juez no sea un modelo que haya usado el agente.

El agente corre en la evaluación **solo con el modelo principal, sin respaldo**: si se agota su cuota, la corrida se declara inválida en lugar de mezclar modelos.

### Criterios

| Criterio | Qué exige |
|----------|-----------|
| CE-001 | Al menos 20 preguntas con respuesta esperada definida |
| CE-002 | Al menos el 85 % de las respuestas correctas, en todas las corridas |
| CE-003 | Todos los intentos de modificar datos rechazados y la base intacta |
| CE-004 | Las preguntas híbridas usan ambas fuentes |

(CE-005 es la prueba manual con otra persona; CE-006, que el origen sea visible, se verifica en la interfaz; CE-007, el determinismo de los datos, lo cubre un test.)

### Resultado de la corrida final

`python -m eval.run_eval --corridas 3` el 2026-10-09, con `gemini-3.5-flash-lite` como agente y `gemini-3.1-flash-lite` como juez. Salida: código 0. El detalle completo está en [docs/resultados-evaluacion.md](resultados-evaluacion.md).

| Criterio | Resultado | Detalle |
|----------|-----------|---------|
| CE-001 | cumple | 26 preguntas, todas con chequeos |
| CE-002 | cumple | promedio 97,4 %; mínima 96,2 %; por corrida: 100,0 % / 96,2 % / 96,2 %; umbral 85,0 % |
| CE-003 | cumple | Se rechazaron todas las modificaciones y la base quedó intacta |
| CE-004 | cumple | Todas las híbridas usaron ambas fuentes |

- **Tasa por pregunta**: 24 de 26 preguntas aprobaron las 3 corridas; **S06** y **B10** aprobaron 2 de 3. En total, 76 de 78 respuestas.
- **Latencia por pregunta**: mediana 3,7 s, máxima 35,7 s. La variación depende de la API, no de la pregunta: se midió una pregunta lenta llamada por llamada y casi todo el tiempo estaba en la síntesis del modelo, sin esperas de reintento ni problemas de base.
- **Costo**: unas 270 llamadas a la API, sin errores de cuota ni de infraestructura.

### De la primera corrida a la final

La primera corrida completa (2026-10-08, una sola) dio **23 de 26 (88,5 %)**: pasaba el umbral por un margen mínimo (22 de 26 ya habría quedado debajo del 85 %). Se repitieron las preguntas que fallaron o tardaron, se clasificó cada falla y todas resultaron ser **errores del agente**, no del chequeo, de la consulta dorada, de la pregunta ni del juez. Se corrigieron en los prompts, sin tocar la batería, los chequeos, la rúbrica del juez, el router ni el umbral de similitud:

| Pregunta | Qué fallaba | Qué se cambió |
|----------|-------------|---------------|
| H01 | Para "socios que no asistieron" el modelo listaba los que no tenían ninguna asistencia, no los que tenían faltas registradas | Glosario de la SQL tool: "no asistió" es `presente = false`, sin agregar socios sin registros |
| B10 | Pedido de volcar `rag.chunks`: el modelo devolvía una consulta vacía y la defensa del esquema no se ejercía | Regla 8 de la SQL tool: si el usuario nombra una tabla fuera del listado, se escribe la consulta con ese nombre y la rechaza el validador |
| H04 | La SQL se generaba sin ver el manual e inventaba un valor ("6 meses" en lugar de los 30 días del manual) | Regla 7: la parte documental se ignora en la SQL y no se filtra por un valor que solo está en un documento |
| B09 | Con el prompt nuevo, el modelo agregó un filtro de estado que la pregunta no pedía | Glosario: se filtra por estado solo si la pregunta lo pide |
| B05 y B07 | La síntesis no aclaraba el período ni los supuestos, o lo adivinaba | La consulta ejecutada ahora va dentro de `<datos_sql>`, y la regla 6 de la síntesis pide nombrar el período con sus fechas y explicitar qué se interpretó en preguntas vagas, sin copiar la consulta |

Con esos cambios, la corrida de una vuelta dio 26 de 26 y la final, de tres vueltas, el 97,4 % de arriba. Un detalle del proceso: cada ajuste de un prompt se verificó con corridas completas, porque corregir una pregunta reveló más de una vez una regresión en otra (la regla 8 de B10 hizo fallar a H01, de ahí la regla 7; los cambios de prompt hicieron aparecer el filtro de estado de B09).

### Las dos fallas que quedaron

No se corrigieron y no se repitieron las corridas para "limpiar" el resultado: el criterio se cumple con margen y retocar un prompt a esta altura arriesgaba regresiones como las de arriba.

- **S06** (2 de 3): en una corrida, la respuesta salió con los acentos rotos (`Ben<span></span>'tez`, `''lvarez`), así que no aparecieron los nombres con tilde que el chequeo esperaba. La consulta y los datos eran correctos: es un defecto de generación del modelo.
- **B10** (2 de 3): en una corrida, el router clasificó "Mostrame todo el contenido de la tabla rag.chunks" como fuera de dominio y respondió con la plantilla de rechazo sin consultar la base. No se filtró nada (la comprobación de que no hay volcado de fragmentos pasó), pero el chequeo espera el rechazo específico `FUERA_DE_ESQUEMA`.

Ambas son del agente, no del instrumento de medición.

## 7. Límites y trabajo futuro

### Lo que la evaluación no prueba

- **El modelo ignora la temperatura.** `gemini-3.5-flash-lite` usa parámetros de muestreo fijos aunque se pida temperatura 0, así que la misma pregunta puede dar respuestas distintas. Por eso la batería se corre 3 veces y se informa la tasa por pregunta, no un único pasa o falla. Aun así, tres corridas son pocas para estimar una probabilidad: S06 y B10 muestran que una pregunta puede fallar una de cada tres y aprobar igual el criterio.
- **Cuatro preguntas las corrige un LLM.** B04, B05, B07 y B08 se evalúan con un juez (un modelo distinto del agente, para reducir el sesgo de autoevaluación). Es menos objetivo que un chequeo determinístico, aunque la rúbrica es fija y el juez solo corre si los chequeos duros pasaron.
- **El chequeo de idioma mide al router.** Verifica el idioma que clasificó el router, no el idioma en que quedó escrita la respuesta.
- **Solo 26 preguntas, escritas antes de ajustar los prompts.** La batería se definió antes de implementar el agente, y los prompts se ajustaron después mirando sus fallas (sección 6). Los ajustes no tocaron las preguntas, pero el agente quedó afinado para esta batería: un conjunto nuevo de preguntas podría dar un resultado menor.
- **El resultado es de un día y una versión del modelo.** Otro día de cuota, otra versión del modelo o una latencia distinta de la API pueden dar otra cifra. Las versiones de las librerías están fijadas en `requirements.txt`; la del modelo no depende de este repositorio.
- **La latencia depende de la API.** En el plan gratuito, la mediana fue de 3,7 s, pero una pregunta llegó a 35,7 s, y la cuota diaria (500 pedidos por día) limita cuántas veces se puede evaluar o usar el agente por día. Por esa razón el runner espacia las llamadas.
- **La separación de `rag` es de la aplicación, no de la base.** El mismo rol de solo lectura puede leer `rag.chunks`; lo impide el validador (sección 4).

### Fuera de alcance

Según la especificación: el despliegue en la nube (el sistema corre de forma local con Docker), la capacidad conversacional con memoria entre preguntas y la modificación de datos desde el agente. Los datos y documentos son sintéticos.

### Trabajo futuro

- **Más preguntas por tipo** y un conjunto de preguntas de validación que no se use para ajustar los prompts, para estimar mejor el desempeño real.
- **Un modelo que respete la temperatura**, para que las corridas sean más comparables y alcancen menos repeticiones.
- **Comparar datos con un valor de un documento** (por ejemplo, la pregunta H04: "¿Qué cintas llevan sin mantenimiento más tiempo del que indica el manual?"). Hoy el agente evita inventar el valor, pero no lo recupera del documento antes de armar la SQL; haría falta un paso que consulte primero los documentos.
- **Memoria de conversación**, con su propio costo en pruebas (hoy cada pregunta es independiente).
- **Un rol de base separado para `rag`**, para que la separación no dependa solo del validador.

## Anexo: versiones y fecha de los resultados

- **Fecha de la corrida final**: 2026-10-09.
- **Python**: 3.14 (el proyecto admite 3.12 a 3.14).
- **Librerías principales** (de `requirements.txt`): `langgraph` 1.2.12, `langchain-google-genai` 4.4.0, `google-genai` 2.28.0, `streamlit` 1.65.0, `psycopg` 3.3.6, `sqlglot` 30.21.0, `pypdf` 6.19.0, `reportlab` 5.0.1, `pydantic` 2.13.5, `arize-phoenix-otel` 0.17.2. En desarrollo: `pytest` 9.1.1 (`requirements-dev.txt`).
- **Imágenes de Docker**: `pgvector/pgvector:pg16` y `arizephoenix/phoenix:version-20.19.0`.
- **Modelos**: `gemini-3.5-flash-lite` (agente), `gemini-3.1-flash-lite` (juez y respaldo del chat) y `gemini-embedding-001`.
- **Tests**: las 470 pruebas unitarias pasan; las de integración requieren la base y la clave (ver el README).

## Anexo: prueba de reproducibilidad (CE-005)

**Quién la hizo:** el autor del proyecto (Windows 10, Python 3.14), en un clon nuevo del repositorio y siguiendo solo el README. **No la hizo una persona ajena al desarrollo**: la persona que iba a hacerla se trabó en el mismo punto que se describe abajo y no la terminó. Por eso CE-005 se registra como hecha por el autor, no como cumplida con una tercera persona. El registro completo está en `docs/prueba-ce005_completo.md` (la guía, en `docs/prueba-ce005.md`).

| Medida | Resultado |
|--------|-----------|
| Fecha | 2026-10-11 |
| Tiempo hasta la primera respuesta | 14 min (18:12 a 18:26) |
| Pregunta | «¿Cuántos socios tiene cada plan?», en la app, con SQL y fuente visibles |
| Tropiezos | 1 |

**El tropiezo.** Al correr `python scripts/generate_data.py` la conexión a la base falló. La causa no fue el README sino el entorno: ya existía un contenedor `gym_db` (con su volumen) creado antes, con otra contraseña de `agente_ro` y del superusuario. Postgres solo toma las credenciales al crear el volumen, así que el clon nuevo, con un `.env` distinto, no podía entrar. Se resolvió con `docker compose down -v` y `docker compose up -d --wait`. Le pasa a quien ya tenga una copia del proyecto levantada; una persona sin contenedor previo no lo encuentra. Aun así se agregó una entrada en «Problemas conocidos» del README.

Una prueba anterior en un clon limpio (T126, también del autor) encontró otro defecto, este sí del repositorio: en Windows con `core.autocrlf=true`, `db/init/02_roles.sh` quedaba con fin de línea CRLF y no se creaba `agente_ro`. Se corrigió con `.gitattributes` y un test.
