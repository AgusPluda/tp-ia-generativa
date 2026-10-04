# Plan de implementación: Agente conversacional SQL + RAG para gimnasio

**Rama**: `001-agente-sql-rag-gimnasio` | **Fecha**: 2026-10-04 | **Spec**: [spec.md](spec.md)

**Entrada**: especificación `specs/001-agente-sql-rag-gimnasio/spec.md` y constitución v1.0.0.

## Resumen

Un agente LangGraph recibe una pregunta en castellano o inglés, decide si responderla con la base (SQL), con los PDFs (RAG), con ambas fuentes, o si debe rechazarla, y sintetiza una respuesta en el idioma de la pregunta mostrando su origen (consulta ejecutada y/o documento y página). Cada pregunta es independiente (sin memoria).

El trabajo se ordena en **etapas**; la primera es el *setup* de datos, porque todo lo demás (agente, evaluación) depende de que la base y los PDFs existan y sean coherentes entre sí:

| Etapa | Contenido | Fecha objetivo |
|-------|-----------|----------------|
| 0. Setup | Entorno Python, `.env`, datos sintéticos deterministas, 3 PDFs sintéticos, ingesta a `rag.chunks` | 06/10 |
| 1. Tools | SQL tool (validación + solo lectura) y RAG tool, con tests unitarios | 08/10 |
| 2. Agente | Grafo LangGraph (router → tools → síntesis), trazas JSONL y Phoenix | 10/10 |
| 3. Interfaz | App Streamlit | 11/10 |
| 4. Evaluación | Batería de 26 preguntas + runner de CE-001 a CE-004; ajuste de prompts | 13/10 |
| 5. Cierre | README desde cero, informe técnico, prueba CE-005 con otra persona | 15/10 |

La entrega es el 16/10/2026; las fechas dejan un día de margen.

## Contexto técnico

**Lenguaje/Versión**: Python 3.12 a 3.14 (los paquetes de Phoenix requieren `<3.15`). El lock de dependencias se genera con la versión de la máquina de desarrollo (3.14.6); las dos personas del grupo deben usar el mismo minor.

**Dependencias principales** (versiones consultadas en PyPI el 2026-10-04; el archivo `requirements.txt` final incluye además las dependencias transitivas fijadas con `pip freeze`):

| Paquete | Versión | Uso |
|---------|---------|-----|
| `langgraph` | 1.2.12 | Grafo del agente |
| `langchain-core` | 1.6.6 | Mensajes, salida estructurada |
| `langchain-google-genai` | 4.4.0 | Chat `gemini-3.8-flash` y embeddings `gemini-embedding-001` |
| `psycopg[binary]` | 3.3.6 | Conexiones a Postgres (admin y solo lectura) |
| `sqlglot` | 30.21.0 | Validación sintáctica de las consultas generadas |
| `pypdf` | 6.19.0 | Extracción de texto por página |
| `reportlab` | 5.0.1 | Generación de los PDFs sintéticos |
| `streamlit` | 1.65.0 | Interfaz |
| `arize-phoenix-otel` | 0.17.2 | Registro de trazas hacia Phoenix |
| `openinference-instrumentation-langchain` | 0.1.78 | Instrumentación de LangChain/LangGraph |
| `pydantic` | 2.13.5 | Contratos de entrada/salida |
| `python-dotenv` | 1.2.4 | Lectura de `.env` |
| `PyYAML` | 6.0.3 | Batería de evaluación |
| `pytest` (dev) | 9.1.1 | Tests |

Phoenix corre en Docker (`arizephoenix/phoenix:version-20.19.0`, ya existe en Docker Hub); en Python solo se instala el cliente OTEL, no el servidor.

**Almacenamiento**: PostgreSQL 16 + pgvector (`pgvector/pgvector:pg16`). Dos esquemas: `public` (negocio) y `rag` (documentos y chunks). Ver [data-model.md](data-model.md).

**Testing**: `pytest`. Los tests unitarios no llaman al LLM. Los tests de integración necesitan la base levantada. La evaluación (`eval/`) sí llama al LLM.

**Plataforma**: ejecución local (Windows/Linux/macOS) con Docker para la base; la app Streamlit corre en el entorno virtual del host.

**Tipo de proyecto**: aplicación local de un solo proceso (agente + UI) más scripts de setup y evaluación.

**Objetivos de rendimiento**: una respuesta en menos de 20 s en el caso típico (2 a 3 llamadas al LLM). No hay requisitos de concurrencia (una persona a la vez).

**Restricciones**: solo lectura sobre la base (RF-008); `statement_timeout` de 5 s (ya configurado en el rol); máximo 50 filas por consulta; cuota de la API de Gemini (ver riesgos en [research.md](research.md)).

**Escala**: unos 60 socios, ~3.000 asistencias, ~350 pagos, 3 PDFs de 3 a 6 páginas cada uno (~45 chunks).

## Verificación contra la constitución

*Compuerta previa a la investigación; se vuelve a evaluar al final del diseño.*

| Principio | Cumple | Cómo |
|-----------|--------|------|
| I. Reproducibilidad primero | Sí | Datos y PDFs deterministas (semilla fija, `reportlab` con modo invariante); `requirements.txt` fijado; credenciales solo en `.env`. *Decisión (2026-10-04)*: la app Streamlit corre fuera de Docker, en un entorno virtual del host. `docker compose up` levanta la infraestructura (base y, con el perfil `observability`, Phoenix) y se interpreta "entorno" en ese sentido; el README documenta los dos pasos. Motivo: ciclo de desarrollo más rápido y menos piezas. Contenerizar la app queda como mejora opcional si sobra tiempo. |
| II. Acceso a datos seguro | Sí | Conexión con `agente_ro`, validación previa con `sqlglot`, transacción de solo lectura, timeout, límite de filas, sin esquema `rag` visible. Ver [contracts/sql-tool.md](contracts/sql-tool.md). |
| III. Cada fuente tiene un rol claro | Sí | Los PDFs no contienen precios ni cifras de la base. El router decide la fuente; las híbridas usan ambas. |
| IV. Respuestas trazables | Sí | La respuesta final incluye `sql_ejecutado` y `fuentes_documentales`; si no hay información suficiente, lo dice. |
| V. Evaluación guiada por preguntas | Sí | Batería definida en [contracts/eval-battery.md](contracts/eval-battery.md) antes de implementar; runner automatizable. |
| VI. Código documentado y simple | Sí | Docstrings, README, un solo grafo con pocos nodos, sin frameworks extra. |

**Restricciones técnicas**: Python, PostgreSQL + pgvector en Docker, LangGraph, Streamlit y Phoenix. Todo coincide. La constitución v1.0.0 dejaba la observabilidad diferida; la v1.1.0 (2026-10-04) fijó Phoenix, por lo que este plan ya no tiene decisiones pendientes en ese punto.

**Compuerta**: sin violaciones. No se completa la tabla de complejidad.

## Estructura del proyecto

### Documentación de esta feature

```text
specs/001-agente-sql-rag-gimnasio/
├── spec.md
├── plan.md                  # este archivo
├── research.md              # decisiones y alternativas
├── data-model.md            # esquema existente, tal cual, y observaciones
├── quickstart.md            # validación de punta a punta
├── contracts/
│   ├── agent-graph.md       # estado, router, nodos, respuesta final, traza
│   ├── sql-tool.md
│   ├── rag-tool.md
│   ├── eval-battery.md      # formato de la batería y las 26 preguntas
│   └── ui.md
└── tasks.md                 # lo genera /speckit-tasks
```

### Código fuente (raíz del repositorio)

```text
db/init/                      # ya existe: 01_schema.sql, 02_roles.sh
docker-compose.yml            # ya existe (se fija la versión de Phoenix)
.env.example                  # ya existe (se agrega la variable de modelo si hace falta)
requirements.txt              # dependencias fijadas (runtime + transitivas)
requirements-dev.txt          # pytest

data/pdfs/                    # 3 PDFs generados (se versionan: forman parte de la entrega)
├── reglamento_interno.pdf
├── guia_rutinas_nutricion.pdf
└── manual_equipamiento.pdf

scripts/                      # CLI delgados que llaman a src/gym_agent
├── generate_data.py          # carga los datos sintéticos como admin
├── generate_pdfs.py          # genera data/pdfs/*.pdf
└── ingest_pdfs.py            # extrae, divide, embebe e inserta en rag.chunks

src/gym_agent/
├── config.py                 # REFERENCE_DATE y demás configuración (única fuente)
├── db.py                     # conexiones: admin (setup) y agente_ro (agente)
├── llm.py                    # fábricas de chat y embeddings (Gemini)
├── observability.py          # registro en Phoenix + traza JSONL
├── synthetic/
│   ├── catalog.py            # hechos compartidos entre base y PDFs (frecuencias, plazos)
│   ├── data.py               # generación determinista de filas
│   ├── loader.py             # carga a la base y hash por tabla
│   ├── pdf_content.py        # texto de los 3 documentos
│   └── pdf_render.py         # renderiza los PDFs con reportlab
├── rag/
│   ├── chunking.py
│   └── ingest.py
├── tools/
│   ├── sql_validator.py
│   ├── sql_tool.py
│   └── rag_tool.py
└── graph/
    ├── state.py
    ├── prompts.py
    ├── nodes.py
    └── builder.py            # construye y expone run_question(pregunta)

app/streamlit_app.py
eval/
├── battery.yaml              # las preguntas con sus chequeos
├── criteria.py               # cálculo de CE-001 a CE-004
├── run_eval.py               # runner
└── results/                  # salidas (no se versionan; el resumen va a docs/)

tests/
├── unit/                     # validador SQL, chunking, ventana de fechas, invariantes de datos
└── integration/              # rol de solo lectura, ingesta, determinismo de datos

docs/                         # informe técnico y resultados de evaluación
README.md
```

**Decisión de estructura**: proyecto único con paquete `gym_agent` instalable en modo editable (`pip install -e .` mediante un `pyproject.toml` mínimo, sin dependencias duplicadas). Los scripts son envoltorios finos para que la lógica quede testeable. `synthetic/catalog.py` es la **única fuente de verdad** de los hechos que aparecen a la vez en la base y en los PDFs (tipos de equipo y su frecuencia de mantenimiento, plazos del reglamento): el generador de datos, el generador de PDFs y la batería de evaluación lo importan, de modo que no pueden contradecirse.

## Decisiones de diseño principales

1. **Grafo** (detalle en [contracts/agent-graph.md](contracts/agent-graph.md)): `router` → `sql` y/o `rag` → `sintetizar`; un nodo `rechazar` atiende lo que no se debe responder. El router devuelve salida estructurada: fuente, idioma y, si corresponde, motivo de rechazo (fuera de dominio, intento de modificación, falta de contexto). Las preguntas híbridas ejecutan SQL y luego RAG en secuencia (más simple de trazar que en paralelo y suficiente en latencia).
2. **Defensa en profundidad para escrituras**: aunque el router clasifique mal un pedido como "borrar pagos", la SQL tool solo acepta un `SELECT` y la base rechaza escrituras por el rol y por la transacción de solo lectura. Hay tres capas independientes.
3. **Fecha de referencia**: `REFERENCE_DATE = 2026-09-30` definida una sola vez en `config.py`. El generador de datos, el prompt del agente ("hoy es …") y el runner la importan. La SQL tool rechaza `CURRENT_DATE`, `now()` y similares para que ninguna consulta dependa del reloj real. "Último mes" = `fecha BETWEEN REFERENCE_DATE - 29 AND REFERENCE_DATE`.
4. **Datos**: 6 meses de historia, del 2026-04-01 al 2026-09-30. Los escenarios que usa la batería se **plantan** de forma deliberada (socios con faltas en el último mes, pagos vencidos, equipos en mantenimiento, un único instructor con más asistencias) y se verifican con tests de invariantes.
5. **RAG**: chunks de ~800 caracteres con solape de 100, respetando párrafos y manteniendo la página de origen; embeddings de 1536 dimensiones (coinciden con `vector(1536)`); `k = 4` y umbral de similitud inicial 0,5 que se calibra con la batería. Ver [contracts/rag-tool.md](contracts/rag-tool.md).
6. **Observabilidad doble**: cada pregunta se escribe siempre en `logs/traza.jsonl` (cumple RF-012 aunque Phoenix no esté levantado) y, si Phoenix está activo, además queda como traza OpenTelemetry.
7. **Evaluación**: chequeos determinísticos (valores esperados calculados con consultas SQL "doradas" contra la base, hechos del `catalog.py`, fuentes usadas, base intacta). Solo tres preguntas cualitativas usan un juez LLM con rúbrica. Ver [contracts/eval-battery.md](contracts/eval-battery.md).

## Riesgos

| Riesgo | Mitigación |
|--------|------------|
| El identificador `gemini-3.8-flash` no es aceptado por la versión fijada de `langchain-google-genai` | Tarea de humo en la Etapa 0: una llamada de chat y una de embeddings antes de seguir. El modelo se lee de `config.py` para cambiarlo en un solo lugar. |
| Límites de cuota de la API durante la evaluación (26 preguntas × 2 a 3 llamadas) | Reintentos con espera exponencial y pausa configurable entre preguntas en el runner. |
| El LLM genera SQL incorrecto para "último mes" o "no asistió" | Glosario de negocio en el prompt (definiciones de la spec) y verificación en la batería. |
| Dimensión de embeddings inconsistente | Verificación al iniciar la ingesta: si el vector no tiene 1536 elementos, falla con un mensaje claro. |
| El plazo (12 días) | Etapas con fecha; la Historia 5 (P3) es la primera que se recorta si hace falta. |

## Seguimiento tras el diseño

Se volvió a evaluar la verificación contra la constitución con los artefactos de la fase 1: no aparecen violaciones nuevas. Las observaciones sobre el esquema existente están en [data-model.md](data-model.md#observaciones-sobre-el-esquema-existente).
