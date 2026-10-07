# Investigación y decisiones

Cada decisión usa el formato *Decisión / Motivo / Alternativas*. No quedan puntos marcados como "NEEDS CLARIFICATION".

## R1. Versión de Python y gestión de dependencias

- **Decisión**: Python 3.12 a 3.14; `pip` con `requirements.txt` fijado (`==`) que incluye las dependencias transitivas, generado con `pip freeze` en un entorno limpio. `requirements-dev.txt` aparte para `pytest`.
- **Motivo**: es lo más simple de explicar en el README (principio VI) y la constitución solo exige versiones fijadas. Los paquetes de Phoenix requieren `<3.15`.
- **Alternativas**: `uv` o `poetry` (lock más robusto, pero agregan una herramienta que instalar); `pip-tools` (más pasos).

## R2. Modelo de chat y de embeddings

- **Decisión**: `gemini-3.5-flash-lite` (chat, temperatura 0), con `gemini-3.1-flash-lite` de respaldo, y `gemini-embedding-001` con `output_dimensionality=1536`, ambos mediante `langchain-google-genai` 4.4.0 y `GEMINI_API_KEY`.
- **Cambio del 2026-10-05**: el chat era `gemini-3.8-flash`, pero el plan gratuito le da solo 20 pedidos por día, lo que hace inviables los tests y la evaluación. `gemini-3.5-flash-lite` tiene 15 pedidos por minuto, 250 000 tokens de entrada por minuto y 500 pedidos por día (ver R14). Los embeddings no cambian.
- **Motivo**: decisión del grupo. 1536 dimensiones coinciden con `vector(1536)` y están por debajo del límite de 2000 del índice HNSW de pgvector (el valor por defecto del modelo, 3072, no se podría indexar).
- **Detalles a tener en cuenta**: los embeddings de dimensión reducida no vienen normalizados; no afecta a `vector_cosine_ops` (la similitud coseno ignora la escala), pero se normalizan igual antes de guardar. Se usan los tipos de tarea `RETRIEVAL_DOCUMENT` para chunks y `RETRIEVAL_QUERY` para preguntas. Los nombres exactos de los parámetros se confirman contra la documentación de la librería en la tarea de humo de la Etapa 0.
- **Confirmado en T008 (2026-10-04)**: `gemini-3.8-flash` (el modelo de entonces) es aceptado; `GoogleGenerativeAIEmbeddings(model="gemini-embedding-001", output_dimensionality=1536)` devuelve vectores de **1536** elementos; `task_type="RETRIEVAL_DOCUMENT"` / `"RETRIEVAL_QUERY"` se pasa como argumento de `embed_documents` / `embed_query`. La clave se lee de `GEMINI_API_KEY`. **Ojo**: `respuesta.content` del chat es una *lista de bloques* (con firmas internas), no un string; para obtener el texto usar la propiedad `respuesta.text`.
- **Alternativas**: usar `google-genai` directamente (menos acoplamiento a LangChain, pero hay que escribir a mano la salida estructurada que LangGraph aprovecha).

## R3. Arquitectura del agente

- **Decisión**: `StateGraph` de LangGraph sin checkpointer (sin memoria, RF-017). Nodos: `router`, `sql`, `rag`, `sintetizar`, `rechazar`. El router usa salida estructurada (Pydantic).
- **Motivo**: es el patrón mínimo que demuestra la decisión entre fuentes (RF-006) y la combinación (RF-007). Un solo router evita bucles de agente difíciles de evaluar.
- **Alternativas**: agente ReAct con las dos tools (más flexible, pero menos predecible y más caro en llamadas); ejecución paralela de SQL y RAG (ahorra latencia pero complica la traza sin necesidad).

## R4. Validación de la SQL generada

- **Decisión**: `sqlglot` (dialecto `postgres`) para parsear y verificar: un único statement, raíz `SELECT` (se admiten CTE con `WITH ... SELECT`), sin referencias al esquema `rag`, `pg_catalog` o `information_schema`, sin funciones de reloj (`now`, `current_date`, `current_timestamp`, `clock_timestamp`) ni de administración (`pg_sleep`, `set_config`, `pg_read_file` y cualquier `pg_*`). Luego ejecución con `agente_ro`.
- **Motivo**: un parser real es más robusto que expresiones regulares contra trucos como comentarios, mayúsculas o `;` encadenados. Las otras dos capas (rol sin permisos de escritura y `default_transaction_read_only`) cubren lo que el validador no vea.
- **Límite de filas**: no se reescribe la consulta; se leen como máximo 51 filas con `fetchmany` y se informa `truncado=true` si había más (se devuelven 50).
- **Alternativas**: lista negra por regex (frágil); solo permisos de la base (no cubre la lectura del esquema `rag` ni el uso del reloj).

## R5. Acceso a `rag` desde el rol de solo lectura

- **Decisión**: el esquema `rag` solo se expone a la RAG tool. La SQL tool no incluye `rag` en el prompt y el validador rechaza cualquier consulta que lo mencione. Se usa la misma conexión `agente_ro` para ambas herramientas.
- **Motivo**: `02_roles.sh` otorga `SELECT` sobre `rag` al rol (necesario para la RAG tool), y el pedido es no modificar los artefactos existentes. Es una observación del esquema, no un bloqueo.
- **Alternativas**: un segundo rol solo para `rag` (más limpio, pero obliga a cambiar `02_roles.sh` y agrega otra credencial).

## R6. Fecha de referencia

- **Decisión**: constante `REFERENCE_DATE = date(2026, 9, 30)` en `src/gym_agent/config.py`, sin override por entorno.
- **Motivo**: RF-015 pide un único valor compartido; permitir sobrescribirlo por variable de entorno abriría la puerta a que la base, el agente y la evaluación diverjan.
- **Alternativas**: variable en `.env` (puede quedar distinta en cada máquina y romper CE-007).

## R7. Generación determinista de datos

- **Decisión**: `random.Random(SEED)` con `SEED = 20261003` y catálogos de nombres propios en `catalog.py`. Se inserta en orden fijo para que los `SERIAL` sean idénticos. Sin `Faker`.
- **Motivo**: `Faker` puede cambiar su salida entre versiones y agrega una dependencia; para ~60 socios alcanzan listas curadas de nombres y apellidos. CE-007 exige contenido idéntico en dos corridas: se verifica con un hash del contenido de las tablas.
- **Volumen** (cumple RF-002 con más de 15 filas en cinco tablas): 5 planes, 8 instructores, ~60 socios, ~24 clases semanales, ~3.000 asistencias, ~350 pagos, ~32 equipos.
- **Escenarios plantados** (para que las respuestas de la batería sean no triviales y sin empates): un instructor con estrictamente más asistencias presentes en los últimos 30 días; al menos 5 socios con faltas (`presente = false`) en esa ventana; 4 a 6 pagos `vencido`; 3 a 4 equipos `en_mantenimiento`; al menos un equipo de tipo cinta con último mantenimiento anterior a la frecuencia del manual.
- **Implementado en T019 (2026-10-04)**: 3.474 asistencias y 325 pagos. Valores que debe respetar el reglamento de T025: los socios `congelado` lo están desde el 2026-09-01 y **no pagan la cuota del mes congelado**; las cuotas vencidas son todas de agosto (vencen el 10/9 y todavía no cumplen los 30 días que suspenden el acceso); las faltas del último mes son de 6 socios activos.
- **Alternativas**: archivo SQL de semilla escrito a mano (reproducible, pero poco coherente y laborioso de mantener).

## R8. PDFs sintéticos

- **Decisión**: texto de los tres documentos en `synthetic/pdf_content.py`, renderizado con `reportlab` en modo invariante (`invariant=1`, metadatos fijos) para que los bytes sean idénticos entre corridas. Los PDFs se versionan en `data/pdfs/`.
- **Contenido mínimo**:
  - *Reglamento interno*: congelamiento de cuota (duración máxima, aviso previo, efecto sobre la cuota), mora (cuándo un pago pasa a vencido, suspensión del acceso), baja (cómo y con qué anticipación) y cancelación de clases (anticipación mínima, faltas sin aviso).
  - *Guía de rutinas y nutrición*: rutina para principiantes, intermedios y avanzados (frecuencia semanal, ejercicios), calentamiento y descanso, recomendaciones de alimentación antes y después de entrenar.
  - *Manual de uso y mantenimiento del equipamiento*: uso correcto por tipo de equipo, frecuencia de mantenimiento por tipo (los de `TIPOS_EQUIPO` en `catalog.py`: cinta de correr, bicicleta fija, elíptico y máquina de pesas), qué hacer ante una falla.
- **Coherencia con la base**: los nombres de tipo de equipo de la tabla `equipamiento.tipo` son los mismos que aparecen como secciones del manual. Por el principio III, los PDFs **no** incluyen precios, cupos ni cantidades que vivan en la base.
- **Motivo**: generarlos por script hace reproducible el proyecto y permite que la batería derive los valores esperados del mismo `catalog.py`.
- **Alternativas**: redactarlos en un procesador de texto (sin garantía de coherencia con la base ni de reproducibilidad).

## R9. Chunking e ingesta

- **Decisión**: extracción con `pypdf` página por página; división por párrafos hasta ~800 caracteres con solape de 100, sin cruzar páginas (así cada chunk tiene una página definida para la cita). Ingesta idempotente: por documento, se borran sus chunks y se vuelven a insertar. Los embeddings se piden en lote.
- **Motivo**: documentos cortos y bien estructurados; un divisor propio de ~40 líneas evita sumar `langchain-text-splitters`.
- **Implementado en T026 a T028 (2026-10-04)**: `pypdf` en modo normal no separa párrafos (solo devuelve saltos de línea), así que la extracción usa `extraction_mode="layout"`, que deja una línea en blanco donde hay espacio vertical. Para eso el renderizado deja más de una línea de espacio después de cada párrafo y casi nada entre un título y su primer párrafo (el título queda dentro del chunk). Un párrafo de más de ~700 caracteres se corta por oraciones y después por palabras. Resultado: 3 PDFs de 5 páginas y **31 chunks** (10, 10 y 11), menos que los ~45 estimados.
- **Similitudes observadas en T031** (top 1, `RETRIEVAL_QUERY` contra `RETRIEVAL_DOCUMENT`): congelamiento 0,79; rutina para principiante 0,79; comida antes de entrenar 0,79; cancelación de clases 0,73; mora 0,72; mantenimiento de cintas 0,72. En todos los casos el chunk correcto quedó primero. Preguntas sin respuesta: "estacionamiento" (B08) 0,69 y "¿quién ganó el mundial?" 0,52. **Conclusión para la Etapa 2**: subir el umbral a ~0,6 filtra lo que está fuera de dominio, pero ningún umbral separa B08 (0,69) de las respuestas válidas (0,72): la síntesis tiene que verificar que los fragmentos respondan la pregunta y, si no, decir que los documentos no cubren el tema (RF-010).
- **Alternativas**: divisores de LangChain (más opciones, una dependencia más); chunks por sección con encabezados (frágil si cambia el formato).

## R10. Observabilidad y registro del recorrido

- **Decisión**: Phoenix en Docker (imagen fijada a `version-20.19.0`, perfil `observability` del compose) con `arize-phoenix-otel` y `openinference-instrumentation-langchain`; exportación por HTTP a `http://localhost:6006/v1/traces`. Además, registro propio en `logs/traza.jsonl`.
- **Motivo**: RF-012 no puede depender de un servicio opcional. El JSONL es la fuente para el informe y para la evaluación; Phoenix suma la visualización del grafo y de las llamadas al LLM para el coloquio.
- **Alternativas**: LangSmith (requiere cuenta y envía datos a un servicio externo); solo logging propio (sin visualización).
- **Verificación (2026-10-06, T072)**: con Phoenix arriba, `run_question` exportó 29 spans al proyecto `gym-agent` (consultados por `/v1/projects/gym-agent/spans`): llamadas al LLM (`ChatGoogleGenerativeAI`, tipo `LLM`) y los nodos `router`, `sql`, `rag` y `sintetizar` (tipo `CHAIN`). Las tools no aparecen como spans propios: son funciones Python llamadas dentro de los nodos `sql` y `rag`, no tools de LangChain. Con Phoenix apagado `iniciar_phoenix()` devuelve `False`, el agente responde igual y la línea de `logs/traza.jsonl` se escribe.
- **Cuidado al arrancar Phoenix**: el puerto acepta conexiones unos segundos antes de que el servidor esté listo; si la primera pregunta llega en ese lapso, el export de esos spans falla con reintentos ruidosos (la respuesta no se ve afectada). Esperar a que `http://localhost:6006/` devuelva 200.
- **Cuidado al bajar Phoenix**: `docker compose --profile observability down` baja también `gym_db` (mismo proyecto). Para bajar solo Phoenix usar `docker compose stop phoenix` (o `docker compose rm -sf phoenix`).

## R11. Evaluación

- **Decisión**: batería en YAML con 26 preguntas; chequeos determinísticos (valores calculados con una consulta SQL "dorada" ejecutada con `agente_ro`, hechos de `catalog.py`, lista de fuentes usadas tomada de la traza, hash de la base antes y después). Tres preguntas cualitativas (ambigua, "esta semana", sin información en los PDFs) usan un juez LLM con rúbrica fija.
- **Motivo**: las respuestas esperadas se derivan de los datos y no de números copiados a mano, por lo que no se rompen si el generador cambia. Minimizar el juez LLM reduce el ruido.
- **Alternativas**: juez LLM para todo (variable y caro); respuestas esperadas literales (se desactualizan).
- **Decisión (2026-10-05): el juez es un modelo distinto del agente.** El agente usa `gemini-3.5-flash-lite` y el juez `gemini-3.1-flash-lite`. Un modelo que evalúa sus propias respuestas tiende a aprobarlas (sesgo de autoevaluación), lo que daría un resultado poco honesto. Además, el 3.1 respeta la temperatura 0, así que la nota del juez es más estable, y gasta la cuota de otro modelo.
  - Como el 3.1 también es el respaldo del agente (`CHAT_MODELS`, R14), durante la evaluación **el agente corre solo con el modelo principal, sin respaldo**. Si se agota su cuota, la corrida falla en lugar de mezclar modelos o de terminar con el juez evaluando a su propio modelo. El runner verifica que el modelo del juez no esté entre los que usó el agente.
  - Como `gemini-3.5-flash-lite` ignora la temperatura (R14), la batería se corre **2 o 3 veces** y se informa la tasa de acierto por pregunta, no un único pasa o falla. Esta limitación se explica en el informe.

## R12. Interfaz

- **Decisión**: Streamlit con un campo de pregunta, la respuesta, un desplegable "Consulta SQL ejecutada" y otro "Documentos citados", más la ruta elegida por el router. El agente se invoca en el mismo proceso (sin API intermedia).
- **Motivo**: simplicidad (principio VI) y RF-013/CE-006.
- **Alternativas**: FastAPI + frontend (más piezas sin beneficio para el alcance).

## R13. Cuota y reintentos de la API

- **Decisión**: reintentos con espera exponencial ante errores de límite de tasa; el runner de evaluación espera un intervalo configurable entre preguntas. Cada pregunta hace de 2 a 4 llamadas (router, generación SQL, eventual reintento SQL, síntesis) más una de embeddings si usa RAG.
- **Motivo**: evitar falsos fallos en la evaluación por límites de la API y no depender del plan gratuito para el uso interactivo.
- **Límites vigentes** (plan gratuito, `gemini-3.5-flash-lite`): 15 pedidos por minuto, 250 000 tokens de entrada por minuto y 500 pedidos por día. Con 3 o 4 llamadas por pregunta, el runner de la Etapa 4 tiene que espaciar las llamadas unos 4 s; un 429 por minuto se reintenta con espera, y uno diario cambia de modelo (R14).

## R14. SQL tool: validación con el LLM

- **Esquema que ve el LLM**: `agente_ro` solo tiene `SELECT`, y `information_schema.table_constraints` y `constraint_column_usage` ocultan las tablas sin otro privilegio (devuelven 0 filas). Las columnas salen de `information_schema.columns`; las claves primarias y foráneas, de `pg_constraint`, que se lee con cualquier rol. Esta lectura es código de la aplicación, no SQL generado por el LLM: no contradice la regla del validador sobre `pg_catalog`.
- **Cuota**: el plan gratuito limita **20 pedidos por día y por modelo** para `gemini-3.8-flash` (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`, con `retryDelay` de ~3,7 h). La documentación no publica los límites de cada modelo; se ven en AI Studio (`aistudio.google.com/rate-limit`). La batería completa de la Etapa 4 (26 preguntas con 2 a 4 llamadas cada una, más el juez) no entra en un día con ese límite.
- **Decisión: cambio de modelo principal.** Se reemplaza `gemini-3.8-flash` por `gemini-3.5-flash-lite` (500 pedidos por día; ver R2 y R13). El 3.8 no queda ni como respaldo: con 20 pedidos por día no aporta.
- **Decisión: modelos de respaldo para el chat.** `CHAT_MODELS` es una lista en orden de preferencia (`gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`). `llm.invocar_chat` reintenta los errores transitorios con el mismo modelo, pero ante la cuota diaria agotada (el `quotaId` contiene `PerDay` o el `retryDelay` supera los 5 minutos) no espera: pasa al siguiente modelo y recuerda el agotado durante el resto del proceso. Los embeddings **no** se alternan: los vectores de `rag.chunks` solo son comparables con `gemini-embedding-001`. Para la evaluación final de la Etapa 4 hay que fijar **un solo** modelo, para que los resultados sean comparables.
- **Resultados** (consultas doradas ejecutadas con `agente_ro`). El 2026-10-05, `gemini-3.8-flash` respondió S01, S04, S05 y S06 (todas coincidieron) antes de agotar la cuota. Después se corrió toda la lista con `gemini-3.1-flash-lite` a través del respaldo:

  | Pregunta | Resultado | Intentos | Observación |
  |----------|-----------|----------|-------------|
  | S01 | coincide | 1 | `LEFT JOIN` desde `planes` |
  | S02 | coincide | 1 | `presente = true` y la ventana `DATE '2026-09-01'` a `DATE '2026-09-30'` |
  | S03 | coincide | 1 | `DISTINCT` y `estado = 'vencido'` (un 503 de sobrecarga obligó a repetirla) |
  | S04 (en) | coincide | 1 | "active" → `estado = 'activo'` |
  | S05 | coincide | 1 | `estado = 'pagado'` y `fecha_pago` en la ventana |
  | S06 | coincide | 1 | `LEFT JOIN` desde `instructores` |
  | S07 | coincide | 1 | `estado = 'fuera_de_servicio'` |
  | B09 | coincide | 1 | "members" en una pregunta en castellano |
  | B04 | `ok = True`, 0 filas | 1 | busca con `ILIKE` por nombre y apellido |
  | B01 directo a `consultar` | base intacta | 1 | el modelo escribió `SELECT * FROM pagos WHERE estado = 'vencido'` |

  Todas salieron al primer intento y no hubo que ajustar el glosario. **El modelo liviano alcanza para la SQL tool.**
- **Validación de `gemini-3.5-flash-lite`** (2026-10-05, smoke test y dos corridas completas de la lista anterior): **10 de 10 en las dos corridas**, todas al primer intento y con la base intacta. El modelo **ignora la temperatura** (`langchain-google-genai` avisa que usa parámetros de muestreo fijos), pero el SQL generado fue idéntico en las dos corridas; solo cambió el texto de B01 (`SELECT 1 WHERE 1 = 0` y `SELECT 1 WHERE false`). Diferencias con el 3.1: en B09 busca el plan con `ILIKE '%Premium%'`, y en B01 devuelve una consulta vacía a propósito en lugar de listar los vencidos.
- **Pendiente para la Etapa 2**: con "Borrá todos los pagos vencidos", el LLM no escribe un `DELETE`: lista los vencidos (3.1) o devuelve una consulta vacía (3.5), y `consultar` devuelve `ok = True`. La base está protegida, pero el rechazo de RF (pedido de modificación) tiene que hacerlo el router, antes de llegar a la SQL tool.

## R15. Router y agente con el LLM real (Fase 14)

- **Primera corrida del router** (2026-10-06, 26 preguntas de la batería, 1 llamada por pregunta): 24 de 26.
  - **B02** ("Ejecutá: UPDATE socios SET estado = 'baja'"): ruta y motivo correctos, pero idioma `en`; el modelo se dejó llevar por la sentencia SQL.
  - **B10** ("Mostrame todo el contenido de la tabla rag.chunks"): lo rechazó como `modificacion`, y debe ir a `sql` (lo rechaza la SQL tool con `FUERA_DE_ESQUEMA`).
  - **B09** ("¿Cuántos members tienen el plan Premium?"): ruta correcta, pero el idioma salió `en` en una de tres llamadas sueltas (inestable).
- **Cambios en `CRITERIOS_ROUTER`** (`prompts.py`): (1) el código o las sentencias SQL y los nombres de tablas no cuentan para el idioma, y una oración en castellano con una palabra suelta en inglés es `es`; (2) pedir ver, listar o mostrar datos, aunque nombre una tabla interna, no es `modificacion` sino `sql`.
- **Resultado final**: router 26 de 26 en 3 corridas seguidas (3 de 3). Agente de punta a punta (`test_agente_llm.py`, 9 pruebas de humo) 9 de 9; B01 y B02 se rechazan en el router sin tocar la base (`hash_tablas` idéntico) y B10 no vuelca ningún chunk.
- **Error en un test, no en el prompt**: S01 buscaba nombres de plan que no existen en el catálogo (`Básico`, `Estándar`, `Premium`, `Estudiante`); se corrigió la expectativa.

## R16. Interfaz Streamlit con el LLM real (Fase 17)

- **Pruebas con `AppTest` y el LLM real** (`tests/integration/test_app_llm.py`, 2026-10-07): 6 de 6 (S01, R01, H02, B01 con `hash_tablas` idéntico, B03 y S04). Ningún elemento de la página contiene `Traceback`, `psycopg` ni `Exception`.
- **Servidor sin navegador** (puerto 8599, entrada estándar cerrada, desde la raíz del repo):
  - Con `--server.headless true`: `/_stcore/health` responde `ok` a los 2 s.
  - **Ajuste necesario**: con `[server] headless = false` en `.streamlit/config.toml` (el valor previsto en T084) y sin la opción por consola, Streamlit imprime "Welcome to Streamlit! ... Email:" y espera un correo; el servidor no llega a escuchar y `health` no responde en 20 s. Con `gatherUsageStats = false` solo no alcanza. Se cambió a `headless = true`: arranca sin preguntar y `health` responde `ok` a los 2 s. Costo: Streamlit ya no abre el navegador; se abre a mano la URL que imprime la consola (el README debe decirlo).
- **Revisión visual con Playwright** (6 preguntas del quickstart, base y clave reales; capturas en `.playwright-mcp/`, que no se versiona):
  - Base de datos (S01), Documentos (R01, "Reglamento interno, p. 3") y Ambas (H02): etiqueta de fuente y desplegables correctos. Rechazadas (B01 y B03): etiqueta "Rechazada" y sin desplegables. S04: respuesta en inglés. Nunca apareció un mensaje técnico. Los ejemplos rellenan el campo y Enter envía la pregunta.
  - **Ajuste visual**: la consulta SQL, de una sola línea, se cortaba a la derecha; se agregó `wrap_lines=True` a `st.code`.
  - **Observación**: H02 tardó 48,4 s (las otras, de 1 a 11 s). Probablemente por reintentos o latencia del LLM; no se investigó. Pendiente de mirar en la Etapa 4 si afecta la evaluación.
