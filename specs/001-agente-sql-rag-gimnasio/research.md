# Investigación y decisiones

Cada decisión usa el formato *Decisión / Motivo / Alternativas*. No quedan puntos marcados como "NEEDS CLARIFICATION".

## R1. Versión de Python y gestión de dependencias

- **Decisión**: Python 3.12 a 3.14; `pip` con `requirements.txt` fijado (`==`) que incluye las dependencias transitivas, generado con `pip freeze` en un entorno limpio. `requirements-dev.txt` aparte para `pytest`.
- **Motivo**: es lo más simple de explicar en el README (principio VI) y la constitución solo exige versiones fijadas. Los paquetes de Phoenix requieren `<3.15`.
- **Alternativas**: `uv` o `poetry` (lock más robusto, pero agregan una herramienta que instalar); `pip-tools` (más pasos).

## R2. Modelo de chat y de embeddings

- **Decisión**: `gemini-3.8-flash` (chat, temperatura 0) y `gemini-embedding-001` con `output_dimensionality=1536`, ambos mediante `langchain-google-genai` 4.4.0 y `GEMINI_API_KEY`.
- **Motivo**: decisión del grupo. 1536 dimensiones coinciden con `vector(1536)` y están por debajo del límite de 2000 del índice HNSW de pgvector (el valor por defecto del modelo, 3072, no se podría indexar).
- **Detalles a tener en cuenta**: los embeddings de dimensión reducida no vienen normalizados; no afecta a `vector_cosine_ops` (la similitud coseno ignora la escala), pero se normalizan igual antes de guardar. Se usan los tipos de tarea `RETRIEVAL_DOCUMENT` para chunks y `RETRIEVAL_QUERY` para preguntas. Los nombres exactos de los parámetros se confirman contra la documentación de la librería en la tarea de humo de la Etapa 0.
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
- **Alternativas**: archivo SQL de semilla escrito a mano (reproducible, pero poco coherente y laborioso de mantener).

## R8. PDFs sintéticos

- **Decisión**: texto de los tres documentos en `synthetic/pdf_content.py`, renderizado con `reportlab` en modo invariante (`invariant=1`, metadatos fijos) para que los bytes sean idénticos entre corridas. Los PDFs se versionan en `data/pdfs/`.
- **Contenido mínimo**:
  - *Reglamento interno*: congelamiento de cuota (duración máxima, aviso previo, efecto sobre la cuota), mora (cuándo un pago pasa a vencido, suspensión del acceso), baja (cómo y con qué anticipación) y cancelación de clases (anticipación mínima, faltas sin aviso).
  - *Guía de rutinas y nutrición*: rutina para principiantes, intermedios y avanzados (frecuencia semanal, ejercicios), calentamiento y descanso, recomendaciones de alimentación antes y después de entrenar.
  - *Manual de uso y mantenimiento del equipamiento*: uso correcto por tipo de equipo, frecuencia de mantenimiento por tipo (cintas, bicicletas, máquinas de pesas, pesas libres), qué hacer ante una falla.
- **Coherencia con la base**: los nombres de tipo de equipo de la tabla `equipamiento.tipo` son los mismos que aparecen como secciones del manual. Por el principio III, los PDFs **no** incluyen precios, cupos ni cantidades que vivan en la base.
- **Motivo**: generarlos por script hace reproducible el proyecto y permite que la batería derive los valores esperados del mismo `catalog.py`.
- **Alternativas**: redactarlos en un procesador de texto (sin garantía de coherencia con la base ni de reproducibilidad).

## R9. Chunking e ingesta

- **Decisión**: extracción con `pypdf` página por página; división por párrafos hasta ~800 caracteres con solape de 100, sin cruzar páginas (así cada chunk tiene una página definida para la cita). Ingesta idempotente: por documento, se borran sus chunks y se vuelven a insertar. Los embeddings se piden en lote.
- **Motivo**: documentos cortos y bien estructurados; un divisor propio de ~40 líneas evita sumar `langchain-text-splitters`.
- **Alternativas**: divisores de LangChain (más opciones, una dependencia más); chunks por sección con encabezados (frágil si cambia el formato).

## R10. Observabilidad y registro del recorrido

- **Decisión**: Phoenix en Docker (imagen fijada a `version-20.19.0`, perfil `observability` del compose) con `arize-phoenix-otel` y `openinference-instrumentation-langchain`; exportación por HTTP a `http://localhost:6006/v1/traces`. Además, registro propio en `logs/traza.jsonl`.
- **Motivo**: RF-012 no puede depender de un servicio opcional. El JSONL es la fuente para el informe y para la evaluación; Phoenix suma la visualización del grafo y de las llamadas al LLM para el coloquio.
- **Alternativas**: LangSmith (requiere cuenta y envía datos a un servicio externo); solo logging propio (sin visualización).

## R11. Evaluación

- **Decisión**: batería en YAML con 26 preguntas; chequeos determinísticos (valores calculados con una consulta SQL "dorada" ejecutada con `agente_ro`, hechos de `catalog.py`, lista de fuentes usadas tomada de la traza, hash de la base antes y después). Tres preguntas cualitativas (ambigua, "esta semana", sin información en los PDFs) usan un juez LLM con rúbrica fija.
- **Motivo**: las respuestas esperadas se derivan de los datos y no de números copiados a mano, por lo que no se rompen si el generador cambia. Minimizar el juez LLM reduce el ruido.
- **Alternativas**: juez LLM para todo (variable y caro); respuestas esperadas literales (se desactualizan).

## R12. Interfaz

- **Decisión**: Streamlit con un campo de pregunta, la respuesta, un desplegable "Consulta SQL ejecutada" y otro "Documentos citados", más la ruta elegida por el router. El agente se invoca en el mismo proceso (sin API intermedia).
- **Motivo**: simplicidad (principio VI) y RF-013/CE-006.
- **Alternativas**: FastAPI + frontend (más piezas sin beneficio para el alcance).

## R13. Cuota y reintentos de la API

- **Decisión**: reintentos con espera exponencial ante errores de límite de tasa; el runner de evaluación espera un intervalo configurable entre preguntas. Cada pregunta hace de 2 a 4 llamadas (router, generación SQL, eventual reintento SQL, síntesis) más una de embeddings si usa RAG.
- **Motivo**: evitar falsos fallos en la evaluación por límites de la API y no depender del plan gratuito para el uso interactivo.
