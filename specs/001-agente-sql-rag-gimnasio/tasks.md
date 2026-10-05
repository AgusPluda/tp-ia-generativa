---

description: "Tareas de la Etapa 0 (setup, completada) y de la Etapa 1 (tools SQL y RAG) del agente SQL + RAG para gimnasio"
---

# Tareas: Agente conversacional SQL + RAG para gimnasio, Etapa 0 (Setup)

**Entrada**: documentos de diseño en `specs/001-agente-sql-rag-gimnasio/` ([plan.md](plan.md), [spec.md](spec.md), [data-model.md](data-model.md), [research.md](research.md), [contracts/](contracts/), [quickstart.md](quickstart.md)).

**Alcance de la Etapa 0**: solo la **Etapa 0** del plan (entorno, datos sintéticos deterministas, 3 PDFs sintéticos e ingesta a `rag.chunks`), completada. Fecha objetivo: 06/10/2026. La **Etapa 1** (tools SQL y RAG) está al final de este archivo, desde la Fase 6. Las etapas 2 a 5 se generan después con `/speckit-tasks`.

**Tests**: el plan y el quickstart piden tests de invariantes de datos, determinismo (CE-007), chunking y rol de solo lectura (CE-003); por eso se incluyen. Ninguno llama al LLM salvo la tarea de humo T008.

**Organización**: la Etapa 0 no es una historia de usuario, sino la base de todas. Se divide en Preparación (Fase 1), Fundamentos comunes (Fase 2) y dos bloques que dejan listo lo que necesitan las historias: **Datos** (habilita Historia 1 y la parte SQL de la 3 y 4) y **Documentos** (habilita Historia 2 y la parte RAG de la 3). Por eso no llevan etiqueta `[US#]`.

## Formato: `[ID] [P?] Descripción con ruta`

- **[P]**: se puede hacer en paralelo (archivos distintos, sin depender de tareas incompletas).
- Todas las rutas son relativas a la raíz del repositorio.

## Fase 1: Preparación (entorno y repositorio)

**Propósito**: dejar el proyecto instalable y la infraestructura corriendo.

- [x] T001 Agregar a `.gitignore` las entradas `logs/` y `eval/results/` (salidas locales que no se versionan).
- [x] T002 Crear la estructura de carpetas del plan con archivos `__init__.py` donde corresponda: `src/gym_agent/` (con subpaquetes `synthetic/`, `rag/`, `tools/`, `graph/`), `scripts/`, `app/`, `eval/`, `tests/unit/`, `tests/integration/`, `data/pdfs/`, `docs/`. Las carpetas que se usan recién en etapas posteriores (`tools/`, `graph/`, `app/`, `eval/`, `docs/`) solo llevan un `.gitkeep` o `__init__.py`.
- [x] T003 Crear `pyproject.toml` mínimo (sin dependencias duplicadas): nombre `gym-agent`, `requires-python = ">=3.12,<3.15"`, diseño `src/` con el paquete `gym_agent`, para poder hacer `pip install -e .`.
- [x] T004 [P] Crear `requirements.txt` con las versiones fijadas (`==`) del plan: `langgraph==1.2.12`, `langchain-core==1.6.6`, `langchain-google-genai==4.4.0`, `psycopg[binary]==3.3.6`, `sqlglot==30.21.0`, `pypdf==6.19.0`, `reportlab==5.0.1`, `streamlit==1.65.0`, `arize-phoenix-otel==0.17.2`, `openinference-instrumentation-langchain==0.1.78`, `pydantic==2.13.5`, `python-dotenv==1.2.4`, `PyYAML==6.0.3`.
- [x] T005 [P] Crear `requirements-dev.txt` con `-r requirements.txt` y `pytest==9.1.1`.
- [x] T006 Generar `requirements.txt` completo en dos pasos: (1) en un entorno virtual temporal, `pip install -r requirements.txt` (solo las dependencias directas de T004) y `pip freeze > requirements.lock.tmp`; (2) reemplazar `requirements.txt` por ese resultado (incluye las dependencias transitivas fijadas) y borrar el temporal. Después, en el entorno de trabajo, `pip install -r requirements-dev.txt` y `pip install -e .`. Verificar `python -c "import gym_agent"`. `pytest` queda solo en `requirements-dev.txt`.
- [x] T007 Actualizar `.env.example`: descomentar y completar `AGENTE_RO_PASSWORD=cambiar_password_ro` y `GEMINI_API_KEY=`; agregar un comentario que indique que ambas son **obligatorias**, que `AGENTE_RO_PASSWORD` no debe llevar comillas ni caracteres especiales (el script `db/init/02_roles.sh` la inserta dentro de un heredoc SQL) y que sin ella el rol `agente_ro` se crea con contraseña vacía. Copiar a `.env` localmente y completar los valores reales (el `.env` está ignorado).
- [x] T008 Prueba de humo del LLM, en el script descartable `scripts/smoke_gemini.py`: una llamada de chat a `gemini-3.8-flash` y un embedding de `gemini-embedding-001` con `output_dimensionality=1536`; imprimir la respuesta y `len(vector)`. Confirmar que el ID del modelo es aceptado por `langchain-google-genai==4.4.0` y que la longitud es **1536**; consultar la documentación de la librería (context7) para los nombres exactos de los parámetros y de los tipos de tarea `RETRIEVAL_DOCUMENT` / `RETRIEVAL_QUERY`. Si falla, anotar el motivo en [research.md](research.md#r2-modelo-de-chat-y-de-embeddings) antes de seguir. Requiere T006 y T007.
- [x] T009 Ajustar `docker-compose.yml`: (a) en el servicio `db`, reemplazar `env_file: .env` por `environment:` explícito con solo `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` y `AGENTE_RO_PASSWORD` (para que `GEMINI_API_KEY` no llegue al contenedor de la base); (b) en `phoenix`, cambiar la imagen a `arizephoenix/phoenix:version-20.19.0` y quitar el comentario "fijar una versión". Los servicios, puertos, volúmenes, healthcheck y el perfil `observability` no cambian.
- [x] T010 Levantar la base con `docker compose up -d` (partiendo de `docker compose down -v` si ya había un volumen) y verificar: contenedor `gym_db` en estado `healthy`; las 7 tablas de `public` y las 2 de `rag` existen (`\dt public.*`, `\dt rag.*`); el rol `agente_ro` existe (`\du`) y su configuración incluye `default_transaction_read_only=on` y `statement_timeout=5s` (`\drds`); además, conectado como `agente_ro`, `SHOW default_transaction_read_only;` devuelve `on`. Requiere T007 y T009.

**Punto de control**: entorno instalable, `.env` listo, base corriendo, modelo de Gemini validado.

---

## Fase 2: Fundamentos comunes (bloquea los dos bloques siguientes)

**Propósito**: configuración, conexiones y el catálogo de hechos compartidos entre base y PDFs.

**⚠️ CRÍTICO**: ni los datos ni los PDFs pueden empezar antes de T011 a T014.

- [x] T011 Crear `src/gym_agent/config.py`: constante `REFERENCE_DATE = date(2026, 9, 30)` (**sin** override por entorno, ver research R6); `HISTORY_START = date(2026, 4, 1)`; `SEED = 20261003`; nombres de modelo `CHAT_MODEL = "gemini-3.8-flash"` y `EMBEDDING_MODEL = "gemini-embedding-001"`; `EMBEDDING_DIM = 1536`; límites `MAX_FILAS = 50` y `STATEMENT_TIMEOUT_S = 5`; carga de `.env` con `python-dotenv`; ruta base del repo y de `data/pdfs/`. Documentar cada constante con un docstring o comentario.
- [x] T012 [P] Crear `src/gym_agent/db.py` con dos funciones: `connect_admin()` (usa `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` en `localhost:${POSTGRES_PORT}`; solo para el setup) y `connect_ro()` (usa `agente_ro` con `AGENTE_RO_PASSWORD`; para el agente). Ambas con `psycopg` 3 y mensajes de error claros si falta una variable del `.env`.
- [x] T013 [P] Crear `src/gym_agent/llm.py` con las fábricas `get_chat_model()` (`gemini-3.8-flash`, temperatura 0) y `get_embeddings()` (`gemini-embedding-001`, `output_dimensionality=1536`) según lo confirmado en T008; incluir una función `normalize(vector)` (L2) y reintentos con espera exponencial ante errores de límite de tasa (research R13).
- [x] T014 Crear `src/gym_agent/synthetic/catalog.py`, **única fuente de verdad** de los hechos que aparecen a la vez en la base y en los PDFs, como constantes tipadas y documentadas:
  - `PLANES`: 5 planes con `nombre` único, `precio_mensual` > 0, `clases_por_semana` >= 0 y `duracion_meses` > 0 (por ejemplo Básico, Estándar, Premium, Estudiante y Anual; los precios **solo** viven acá y en la base, nunca en los PDFs).
  - `TIPOS_EQUIPO`: 4 tipos con su `frecuencia_mantenimiento_dias`: `Cinta de correr` = 30, `Bicicleta fija` = 45, `Elíptico` = 60, `Máquina de pesas` = 90.
  - `REGLAS`: `congelamiento_max_dias = 30` (por vez), `congelamiento_max_veces_anio = 2`, `congelamiento_aviso_horas = 48`, `mora_dias_para_vencido = 10` (días de gracia **después de terminar el mes** de la cuota), `mora_dias_suspension = 30`, `baja_aviso_dias = 15`, `cancelacion_anticipacion_horas = 2`, `faltas_sin_aviso_limite = 3`, `rutina_principiante_dias_semana = 3`.
  - `CLAVES_HECHOS`: diccionario `clave → (documento, texto esperado)` (por ejemplo `frecuencia_mantenimiento_cintas → ("manual_equipamiento", "30 días")`) que usará la batería de evaluación (`contiene_hecho`) y el test T022.
  - Listas curadas de nombres y apellidos (sin `Faker`), de nombres de clase y de salas.

**Punto de control**: `from gym_agent.config import REFERENCE_DATE` y `from gym_agent.synthetic.catalog import REGLAS` funcionan; `connect_admin()` y `connect_ro()` se conectan a la base.

---

## Fase 3: Bloque Datos (deja lista la base para la Historia 1)

**Objetivo**: base poblada con datos sintéticos deterministas, coherentes y con los escenarios que usa la batería.

**Prueba independiente**: ejecutar `python scripts/generate_data.py` y comprobar con `psql` los conteos y los invariantes; ejecutar `pytest tests/unit/test_data_invariants.py tests/integration/test_data_determinism.py`.

### Tests del bloque

> Escribirlos primero y verificar que fallan antes de implementar el generador.

- [x] T015 [P] Crear `tests/unit/test_data_invariants.py`: genera las filas en memoria con `generar_datos()` (sin base) y verifica los 8 invariantes de [data-model.md](data-model.md#invariantes-que-debe-cumplir-el-generador-de-datos): (1) todas las fechas `<= REFERENCE_DATE` y asistencias/pagos/mantenimientos desde `2026-04-01`; (2) cada `asistencias.fecha` cae en el `dia_semana` de su clase y es `>= socios.fecha_alta`; (3) socios `baja` sin asistencias posteriores a su salida; socios `congelado` sin **ninguna** fila de asistencia en el último mes (ni presente ni falta); las faltas `presente = false` del último mes pertenecen solo a socios `activo`; (4) `pagado` ⇒ `fecha_pago` no nulo, `pendiente`/`vencido` ⇒ nulo; (4b) `pendiente` solo para `mes_correspondiente = 2026-09-01` (el mes de `REFERENCE_DATE`) y `vencido` solo si el último día del mes + `mora_dias_para_vencido` es anterior a `REFERENCE_DATE` (meses hasta agosto); (5) a lo sumo un pago por (`id_socio`, `mes_correspondiente`) y `monto` igual al `precio_mensual` del plan; (6) `equipamiento.tipo` pertenece a `TIPOS_EQUIPO` y `ultimo_mantenimiento >= fecha_adquisicion`; (7) existen filas con `presente = false`; (8) ninguna clave única repetida (`email`, `(id_socio, id_clase, fecha)`).
- [x] T016 [P] Crear `tests/unit/test_data_scenarios.py`: verifica los **escenarios plantados**: el instructor con más asistencias `presente = true` en la ventana `REFERENCE_DATE - 29` a `REFERENCE_DATE` es **único** (sin empate); hay al menos 5 socios con `presente = false` en esa ventana; entre 4 y 6 pagos con `estado = 'vencido'`; entre 3 y 4 equipos `en_mantenimiento`; al menos una cinta (`Cinta de correr`) cuyo `ultimo_mantenimiento` es anterior a `REFERENCE_DATE - 30 días`; conteos mínimos de RF-002: más de 15 filas en `socios`, `clases`, `asistencias`, `pagos` y `equipamiento`.
- [x] T017 [P] Crear `tests/integration/test_data_determinism.py` (CE-007; requiere la base levantada): importa `generar_datos`, `cargar_datos` y `hash_tablas` de `gym_agent.synthetic`, carga los datos dos veces y compara los hashes por tabla; deben ser idénticos. Excluye el esquema `rag`.
- [x] T018 [P] Crear `tests/integration/test_readonly_role.py` (CE-003; requiere solo la base de T010, **puede hacerse en cualquier momento después de T010**, sin esperar al generador): conectado como `agente_ro`, un `SELECT` sobre `public` funciona; un `INSERT`, `UPDATE`, `DELETE` y `DROP TABLE` fallan con error de permisos o de transacción de solo lectura; un `SELECT pg_sleep(10)` es cortado por el `statement_timeout` de 5 s.

### Implementación del bloque

- [x] T019 Crear `src/gym_agent/synthetic/data.py` con `generar_datos() -> dict[str, list[tuple]]` (sin acceder a la base), usando `random.Random(SEED)` y los catálogos de `catalog.py`. Respetar el esquema **tal como está**:
  - `planes(nombre VARCHAR(50) UNIQUE, precio_mensual NUMERIC(10,2) > 0, clases_por_semana INT >= 0, duracion_meses INT > 0)`: 5 filas desde `PLANES`.
  - `instructores(nombre/apellido VARCHAR(60), especialidad VARCHAR(60), fecha_ingreso DATE)`: 8 filas.
  - `socios(nombre/apellido VARCHAR(60), email VARCHAR(120) UNIQUE, fecha_nacimiento, fecha_alta, id_plan, estado IN ('activo','congelado','baja'))`: unos 60 socios (aprox. 45 activos, 8 congelados, 7 baja).
  - `clases(nombre VARCHAR(60), id_instructor, dia_semana IN ('lunes','martes','miercoles','jueves','viernes','sabado','domingo') **sin tildes**, hora TIME, cupo INT > 0, sala VARCHAR(30))`: unas 24 clases semanales.
  - `asistencias(id_socio, id_clase, fecha, presente BOOLEAN)`: unas 3.000 filas del 2026-04-01 al `REFERENCE_DATE`, con faltas (`presente = false`) registradas explícitamente solo para socios `activo`; los socios `congelado` no generan ninguna fila en el último mes (ni presente ni falta).
  - `pagos(id_socio, fecha_pago NULL mientras está pendiente, monto > 0, mes_correspondiente = primer día del mes, medio_pago IN ('efectivo','transferencia','tarjeta','mercado_pago'), estado IN ('pagado','pendiente','vencido'))`: unas 350 filas. Regla de mora: la cuota de un mes se paga durante ese mes; `pendiente` solo para `mes_correspondiente = 2026-09-01` y `vencido` solo para meses hasta agosto (último día del mes + `mora_dias_para_vencido` anterior a `REFERENCE_DATE`).
  - `equipamiento(nombre VARCHAR(80), tipo VARCHAR(40) de TIPOS_EQUIPO, sala, estado IN ('operativo','en_mantenimiento','fuera_de_servicio'), fecha_adquisicion, ultimo_mantenimiento NULL permitido)`: unas 32 filas.
  - Cumplir los 8 invariantes y plantar los escenarios de T016. El orden de las filas es fijo (los `SERIAL` quedan idénticos entre corridas). Documentar cada función con docstring.
- [x] T020 Crear `src/gym_agent/synthetic/loader.py` con `cargar_datos(conn, datos)` (vacía las 7 tablas de `public` con `TRUNCATE ... RESTART IDENTITY CASCADE`, inserta en el orden de dependencias `planes`, `instructores`, `socios`, `clases`, `asistencias`, `pagos`, `equipamiento` con `executemany`, todo en una sola transacción) y `hash_tablas(conn) -> dict[str, str]` (md5 de las filas ordenadas por clave primaria, solo esquema `public`). Crear `scripts/generate_data.py` como envoltorio fino: conecta como admin (`connect_admin()`), llama a `generar_datos`, `cargar_datos` y `hash_tablas`, e imprime filas y hash por tabla. Sin tocar el esquema `rag`.
- [x] T021 Ejecutar `python scripts/generate_data.py` y verificar el resumen contra RF-002 (más de 15 filas en 5 tablas), correr `pytest tests/unit/test_data_invariants.py tests/unit/test_data_scenarios.py tests/integration/test_data_determinism.py tests/integration/test_readonly_role.py` y corregir hasta que pasen.

**Punto de control**: la base tiene datos coherentes; la Historia 1 ya se puede probar a mano con consultas SQL contra `public`.

---

## Fase 4: Bloque Documentos (deja listo el RAG para la Historia 2)

**Objetivo**: tres PDFs sintéticos coherentes con la base e ingeridos en `rag.chunks` con embeddings de 1536 dimensiones.

**Prueba independiente**: ejecutar `python scripts/generate_pdfs.py` y `python scripts/ingest_pdfs.py`; consultar `rag.chunks` y hacer una búsqueda por similitud manual de "congelamiento de cuota".

### Tests del bloque

- [x] T022 [P] Crear `tests/unit/test_pdf_content.py`: para cada entrada de `CLAVES_HECHOS`, el `texto esperado` aparece literalmente (normalizando espacios) en el contenido del documento indicado; además, el texto de cada documento menciona los valores de `REGLAS` y `TIPOS_EQUIPO` que le corresponden (por ejemplo el reglamento contiene "30 días" de congelamiento y el manual la frecuencia de cada tipo); **ningún** documento contiene precios en pesos ni montos (principio III: los precios solo viven en la base); los nombres de tipo de equipo del manual coinciden con `TIPOS_EQUIPO`.
- [x] T023 [P] Crear `tests/unit/test_chunking.py`: con un texto de prueba, los chunks tienen como máximo ~800 caracteres, solape de 100, ningún chunk cruza una página, cada chunk conserva su número de página y el orden es creciente.
- [x] T024 [P] Crear `tests/integration/test_pdf_determinism.py`: llama dos veces a `renderizar_pdfs` (de `gym_agent.synthetic.pdf_render`) en directorios temporales y compara el hash de bytes de cada PDF.

### Implementación del bloque

- [x] T025 Crear `src/gym_agent/synthetic/pdf_content.py` con el texto estructurado de los tres documentos, **usando los valores de `catalog.py` y sin precios**:
  - **Reglamento interno**: congelamiento de cuota (duración máxima por vez, veces por año, aviso previo, efecto sobre la cuota), mora (la cuota de cada mes se abona durante ese mes; si al terminar el mes no está paga, hay `mora_dias_para_vencido` días de gracia y pasado ese plazo se considera vencida; suspensión del acceso), baja (aviso previo y procedimiento) y cancelación de clases (anticipación mínima y límite de faltas sin aviso).
  - **Guía de rutinas y nutrición**: rutina para principiantes (frecuencia semanal de `REGLAS`, ejercicios, duración), intermedios y avanzados; calentamiento y descanso; alimentación antes y después de entrenar.
  - **Manual de uso y mantenimiento del equipamiento**: una sección por cada tipo de `TIPOS_EQUIPO` con uso correcto y frecuencia de mantenimiento; qué hacer ante una falla.
  Cada documento de 3 a 6 páginas, con títulos y secciones claros.
- [x] T026 Crear `src/gym_agent/synthetic/pdf_render.py` con `renderizar_pdfs(directorio)` (`reportlab` en modo invariante: `invariant=1`, metadatos y fecha de creación fijos) y `scripts/generate_pdfs.py` como envoltorio fino que la llama y guarda `data/pdfs/reglamento_interno.pdf`, `data/pdfs/guia_rutinas_nutricion.pdf` y `data/pdfs/manual_equipamiento.pdf`. Los PDFs se versionan (forman parte de la entrega).
- [x] T027 [P] Crear `src/gym_agent/rag/chunking.py` con `dividir_en_chunks(paginas: list[str], max_chars=800, solape=100) -> list[Chunk]`: agrupa párrafos hasta ~800 caracteres con solape de 100, **sin cruzar páginas**, y devuelve `Chunk(pagina, orden, contenido)`. Con docstrings.
- [x] T028 Crear `src/gym_agent/rag/ingest.py` con `ingestar(directorio)`: para cada PDF extrae el texto por página con `pypdf`, divide con `dividir_en_chunks`, calcula embeddings en lote con tipo de tarea `RETRIEVAL_DOCUMENT` y los normaliza; **falla con un mensaje claro si algún vector no tiene 1536 elementos** (la columna es `embedding vector(1536) NOT NULL`); e inserta con la conexión admin. Idempotente: hace `INSERT ... ON CONFLICT (nombre_archivo) DO UPDATE` en `rag.documentos` y borra los chunks del documento antes de reinsertarlos. Títulos legibles (`Reglamento interno`, `Guía de rutinas y nutrición`, `Manual de uso y mantenimiento del equipamiento`).
- [x] T029 Crear `scripts/ingest_pdfs.py`: envoltorio que llama a `ingestar(data/pdfs)` e imprime documentos, chunks por documento y dimensión verificada.
- [x] T030 Ejecutar `python scripts/generate_pdfs.py` y `python scripts/ingest_pdfs.py`; verificar en la base que hay 3 filas en `rag.documentos` y unos 45 chunks con `vector_dims(embedding) = 1536`; correr `pytest tests/unit/test_pdf_content.py tests/unit/test_chunking.py tests/integration/test_pdf_determinism.py`.
- [x] T031 Verificación manual de la recuperación (script descartable o `psql`): para "¿Cómo funciona el congelamiento de la cuota?", "¿Qué rutina recomiendan para un principiante?" y "¿Cada cuánto hay que hacer mantenimiento de las cintas?", embeber la pregunta con `RETRIEVAL_QUERY` y buscar con `ORDER BY embedding <=> ... LIMIT 4`; confirmar que el chunk correcto queda entre los primeros y anotar los valores de similitud observados para calibrar el umbral inicial de 0,5 de la RAG tool (contrato [rag-tool.md](contracts/rag-tool.md)).

**Punto de control**: `rag.chunks` poblada; la Historia 2 ya se puede probar a mano con búsquedas por similitud.

---

## Fase 5: Cierre de la Etapa 0

**Propósito**: dejar documentado y validado el punto de partida para la Etapa 1.

- [x] T032 Escribir `README.md` mínimo con: requisitos (Docker, Python 3.12 a 3.14, clave de Gemini), pasos 1 a 3 del [quickstart.md](quickstart.md) (configuración, base, setup de datos y documentos), cómo reiniciar desde cero (`docker compose down -v && docker compose up -d`) y la advertencia de que `AGENTE_RO_PASSWORD` y `GEMINI_API_KEY` son obligatorias. El resto del README (app, evaluación) se completa en la Etapa 5.
- [x] T033 Validación final: desde cero (`docker compose down -v`, base nueva, `.env` listo) ejecutar en orden `docker compose up -d`, `python scripts/generate_data.py`, `python scripts/generate_pdfs.py`, `python scripts/ingest_pdfs.py` y `pytest tests/unit tests/integration`; todo debe pasar sin pasos manuales extra. Registrar en el README cualquier tropiezo.
- [x] T034 Dejar los artefactos listos para commit: revisar con `git status` que no se versiona `.env` ni `logs/`; que sí están `data/pdfs/*.pdf`, `requirements.txt`, `pyproject.toml` y el código; y marcar acá las tareas completadas.

---

## Dependencias y orden de ejecución

### Entre fases

- **Fase 1** (T001 a T010): sin dependencias externas; arranca de inmediato.
- **Fase 2** (T011 a T014): requiere T006 (entorno instalado) y T008 (modelo validado, para T013).
- **Fase 3 (Datos)** y **Fase 4 (Documentos)**: ambas requieren la Fase 2 y T010 (base corriendo). **Son independientes entre sí** y se pueden hacer en paralelo (por ejemplo, una persona cada una).
- **Fase 5**: requiere las Fases 3 y 4.

### Dentro de las fases

- T004 y T005 en paralelo; T006 después de ambos y de T003; T008 después de T006 y T007; T010 después de T007 y T009.
- T012 y T013 en paralelo; T014 puede avanzar en paralelo con ellos pero debe estar antes de T019 y T025.
- Fase 3: los tests T015 a T018 en paralelo (archivos distintos) y antes de T019; T019 → T020 → T021.
- Fase 4: T022 a T024 en paralelo y antes de T025; T025 → T026; T027 en paralelo con T025/T026; T028 después de T027; T029 → T030 → T031.

### Oportunidades de paralelismo

```text
Después de la Fase 2:
  Persona A (Datos):       T015-T018 → T019 → T020 → T021
  Persona B (Documentos):  T022-T024 → T025 → T026 → T027 → T028 → T029 → T030 → T031
```

## Estrategia de implementación

1. **Primero lo que desbloquea a todos**: Fases 1 y 2. Sin entorno, base y configuración no se puede avanzar con nada.
2. **Datos primero si trabaja una sola persona**: la Historia 1 (P1) depende solo de la base, y es el requisito mínimo de aprobación. Documentos después.
3. **Validar en cada punto de control** antes de seguir, y no pasar a la Etapa 1 hasta cerrar T033.
4. **Riesgo principal**: T008. Si `gemini-3.8-flash` o los parámetros de embeddings no son aceptados por la librería fijada, se resuelve ahí, antes de gastar tiempo en el resto.

## Notas

- Los valores numéricos de `catalog.py` (T014) son una propuesta concreta para que la batería tenga respuestas determinadas; pueden ajustarse mientras no cambien después de definir la batería de evaluación.
- El generador no usa la fecha real del sistema en ningún punto (RF-015); cualquier fecha se calcula desde `REFERENCE_DATE`.
- Los scripts `scripts/smoke_gemini.py` y el de T031 son descartables: no forman parte de la entrega y pueden borrarse al cerrar la etapa.

---
---

# Etapa 1: Tools (SQL y RAG)

**Alcance**: la SQL tool ([contracts/sql-tool.md](contracts/sql-tool.md)) y la RAG tool ([contracts/rag-tool.md](contracts/rag-tool.md)), cada una como función Python independiente del grafo, con sus tests. El grafo, el router y la síntesis son la Etapa 2. Fecha objetivo: 08/10/2026. Continúa la numeración de fases y tareas de la Etapa 0.

**Historias que habilita**: Historia 1 (`[US1]`, P1, SQL tool, incluida la defensa contra escrituras de la Historia 4 y CE-003) e Historia 2 (`[US2]`, P1, RAG tool). Son independientes entre sí y se pueden hacer en paralelo.

**Tests**: se piden tests unitarios (sin LLM ni base) y de integración (con la base; los que usan la API de Gemini llevan el marcador `llm` y se saltean sin `GEMINI_API_KEY`). Escribirlos antes de la implementación y verificar que fallan.

**Decisiones de diseño de la etapa** (para que no queden al criterio de quien implementa):

- **Nunca lanzan excepciones**: `consultar(...)` y `buscar(...)` devuelven siempre un resultado; los fallos viajan en `error` (el grafo de la Etapa 2 depende de esto).
- **Inyección de dependencias para testear**: `consultar` acepta `generador` y `ejecutor`; `buscar` acepta `embeber`. Por defecto usan Gemini y la base; los tests pasan versiones falsas.
- **Reintentos de la SQL tool**: se reintenta (hasta `MAX_INTENTOS_SQL` = 3 intentos en total) solo ante `INVALIDA`, `ERROR_EJECUCION` y `TIMEOUT`. `NO_ES_SELECT` y `FUERA_DE_ESQUEMA` **no** se reintentan: dar más oportunidades al LLM tras un intento de escritura o de leer `rag` no aporta nada. Esto ajusta el contrato (se actualiza en T053).
- **Umbral de la RAG tool = 0,6**, no 0,5: según [research.md](research.md#r9-chunking-e-ingesta) (T031), 0,6 filtra lo que está fuera de dominio ("¿Quién ganó el mundial?" saca 0,52). **No** decide si los documentos responden la pregunta: "estacionamiento" (B08) saca 0,69 y las respuestas válidas desde 0,72, así que esa verificación es de la síntesis (Etapa 2).
- **Las tools solo usan `connect_ro()`**; nunca `connect_admin()` (principio II).
- **Modelo de chat**: desde el 2026-10-05 es `gemini-3.5-flash-lite`, con `gemini-3.1-flash-lite` de respaldo (`CHAT_MODELS` en `config.py`). Las tareas de la Etapa 0 mencionan `gemini-3.8-flash` porque era el modelo de ese momento; el motivo del cambio está en [research.md](research.md#r14-sql-tool-validación-con-el-llm).

## Fase 6: Preparación de la Etapa 1

**Propósito**: constantes y marcador de tests que usan las dos tools.

- [x] T035 Agregar a `src/gym_agent/config.py`, con comentario cada una: `K_FRAGMENTOS = 4` (fragmentos máximos que devuelve la RAG tool), `UMBRAL_SIMILITUD = 0.6` (comentar que filtra ruido y **no** decide si hay respuesta; ver research R9) y `MAX_INTENTOS_SQL = 3` (intentos totales de la SQL tool: el primero más dos reintentos). `MAX_FILAS` (50) y `STATEMENT_TIMEOUT_S` (5) ya existen.
- [x] T036 [P] Registrar el marcador `llm` en `[tool.pytest.ini_options]` de `pyproject.toml` (`markers = ["llm: llama a la API de Gemini; se saltea si falta GEMINI_API_KEY"]`) y crear `tests/conftest.py` con un `pytest_collection_modifyitems` que agrega `pytest.mark.skip` a los tests marcados `llm` cuando `GEMINI_API_KEY` no está definida (tras cargar `.env` con `gym_agent.config`).

**Punto de control**: `pytest --markers` lista `llm`; `from gym_agent.config import UMBRAL_SIMILITUD, K_FRAGMENTOS, MAX_INTENTOS_SQL` funciona.

---

## Fase 7: Historia 1, SQL tool (P1)

**Objetivo**: `consultar(pregunta, idioma)` convierte una pregunta en un único `SELECT` válido, lo ejecuta en solo lectura y devuelve un `ResultadoSQL` (contrato [sql-tool.md](contracts/sql-tool.md)).

**Prueba independiente**: `pytest tests/unit/test_sql_validator.py tests/unit/test_sql_tool.py tests/integration/test_sql_executor.py` en verde (sin LLM) y T044 (las 7 preguntas SQL de la batería contra el LLM real).

### Tests de la fase

> Escribirlos primero y verificar que fallan (ModuleNotFoundError) antes de implementar.

- [x] T037 [P] [US1] Crear `tests/unit/test_sql_validator.py` (sin base ni LLM) para `gym_agent.tools.sql_validator.validar(sql) -> str` y `SQLNoPermitido(codigo, detalle)`. Con `pytest.mark.parametrize`:
  - **Se aceptan** (y se devuelve la consulta sin `;` final): `SELECT` simple; `WITH ... SELECT`; joins, agregaciones, subconsultas y funciones de ventana; `fecha BETWEEN DATE '2026-09-01' AND DATE '2026-09-30'`; `ILIKE`; una consulta con un comentario `-- ...` o `/* ... */` que no esconde nada; un `SELECT` con `;` final; un literal como `'today%'` dentro de un `ILIKE` (no es igual a `'today'`).
  - **`NO_ES_SELECT`**: `INSERT`, `UPDATE`, `DELETE`, `DROP TABLE socios`, `ALTER`, `CREATE`, `TRUNCATE`, `GRANT`, `COPY`, `CALL`, `DO`, `SET`; `SELECT 1; DELETE FROM pagos` y `SELECT 1; -- x` seguido de `DELETE` en otra línea (varios statements con alguno que no es `SELECT`); `SELECT * INTO nueva FROM socios`; `SELECT * FROM socios FOR UPDATE`; `WITH x AS (DELETE FROM pagos RETURNING *) SELECT * FROM x` (Postgres admite DML dentro de un CTE).
  - **`FUERA_DE_ESQUEMA`**: `SELECT * FROM rag.chunks`; `rag.documentos` dentro de un `JOIN`, de una subconsulta y de un CTE; `"rag"."chunks"` entrecomillado; `RAG.chunks` en mayúsculas; `pg_catalog.pg_tables`; `information_schema.columns`.
  - **`INVALIDA`**: texto vacío o solo espacios; texto que no es SQL (`"hola"`); sintaxis rota (`SELEC * FROM socios`); dos `SELECT` separados por `;`; funciones de reloj `now()`, `NOW()`, `CURRENT_DATE`, `CURRENT_TIMESTAMP`, `current_time`, `localtimestamp`, `clock_timestamp()`, `statement_timestamp()`, `transaction_timestamp()`; los literales especiales de fecha de Postgres `'now'::timestamp`, `'today'::date`, `'tomorrow'::date`, `'yesterday'::date` (se evalúan con el reloj real); `pg_sleep(10)`, `pg_read_file('/etc/passwd')`, `pg_ls_dir('.')`, `set_config('x','y',false)`, `lo_import('/etc/passwd')`, `dblink('...','...')`.
- [x] T038 [P] [US1] Crear `tests/unit/test_sql_tool.py` (sin base ni LLM; generador y ejecutor falsos). Cubre:
  - (a) `consultar` con un generador que devuelve un `SELECT` válido y un ejecutor falso → `ok = True`, `intentos = 1`, `sql_ejecutado` igual a la consulta validada.
  - (b) primera consulta inválida (`SELECT now()`) y segunda válida → `intentos = 2`, y el generador recibió en el segundo llamado el SQL anterior y un mensaje de error **saneado**.
  - (c) tres consultas inválidas → `ok = False`, `error.codigo = "INVALIDA"`, `intentos = 3`, el generador no se llama una cuarta vez.
  - (d) `DELETE FROM pagos` → `NO_ES_SELECT` con `intentos = 1` (sin reintento); `SELECT * FROM rag.chunks` → `FUERA_DE_ESQUEMA`, también sin reintento; en ambos casos el ejecutor falso **no** se llamó.
  - (e) el ejecutor falso devuelve `TIMEOUT` y luego éxito → se reintenta y `ok = True`; devuelve `ERROR_EJECUCION` tres veces → `ok = False`, `intentos = 3`.
  - (f) 0 filas → `ok = True`, `filas = []`, `truncado = False`.
  - (g) el generador lanza una excepción (falla del LLM) → `ok = False`, `ERROR_EJECUCION`, no se propaga la excepción.
  - (h) `ErrorSQL.mensaje` coincide con el texto de la tabla de errores del contrato para cada código y **no** contiene `detalle`.
  - (i) `sanear_error(texto)` reemplaza host (`localhost`, `127.0.0.1`, `::1`), usuario (`agente_ro`, `gym_admin`), puertos, rutas de Windows (`E:\REPOSITORIOS\...`) y de Linux (`/var/lib/...`) y cualquier valor de `AGENTE_RO_PASSWORD`/`POSTGRES_PASSWORD` presente en el entorno, pero conserva el motivo útil (por ejemplo `column "xyz" does not exist`).
  - (j) `construir_prompt_sql(esquema, pregunta, idioma, intento_previo)` (de `sql_prompt.py`): contiene el esquema recibido, la pregunta, `2026-09-30`, la ventana `2026-09-01` a `2026-09-30` como fechas literales, la aclaración de que `dia_semana` va **sin tildes** (`miercoles`, `sabado`), la prohibición de `CURRENT_DATE`/`now()`, y en un reintento incluye la consulta anterior y el error saneado.
- [x] T039 [P] [US1] Crear `tests/integration/test_sql_executor.py` (requiere la base; **sin LLM**; usa `conn_admin` solo para el hash de control). Cubre `ejecutar_sql` y `describir_esquema`:
  - `SELECT * FROM planes` → 5 filas, `truncado = False`; `SELECT * FROM asistencias` → exactamente 50 filas y `truncado = True`; las columnas vienen en `columnas`.
  - Los valores son serializables a JSON (`json.dumps(resultado.filas)` no falla: fechas como texto ISO, `Decimal` como número).
  - Timeout: `SELECT count(*) FROM generate_series(1, 100000000000)` → `TIMEOUT` en menos de 10 s.
  - **Defensa en profundidad** (CE-003): llamando a `ejecutar_sql` **sin pasar por el validador**, `DELETE FROM pagos`, `UPDATE socios SET estado = 'baja'`, `DROP TABLE socios` y `INSERT INTO planes ...` devuelven `ok = False` con `NO_ES_SELECT`, y `hash_tablas` (de `gym_agent.synthetic`) es idéntico antes y después.
  - `SELECT columna_inexistente FROM socios` → `ERROR_EJECUCION`; `error.detalle` guarda el texto de la base y `error.mensaje` no.
  - `describir_esquema()` incluye las 7 tablas de `public` con sus columnas y claves foráneas y **no** contiene `rag`, `chunks` ni `embedding`.

### Implementación de la fase

- [x] T040 [US1] Crear `src/gym_agent/tools/sql_validator.py`: `class SQLNoPermitido(Exception)` con `codigo` (`"NO_ES_SELECT"` | `"FUERA_DE_ESQUEMA"` | `"INVALIDA"`) y `detalle`, y `validar(sql: str) -> str` que implementa los pasos de validación del contrato con `sqlglot` 30.21.0, dialecto `postgres`:
  - Sin texto, sin parseo o más de un statement → `INVALIDA`; **excepción**: si entre varios statements hay alguno que no es `SELECT`, el código es `NO_ES_SELECT`.
  - La raíz debe ser `SELECT` (se admite `WITH ... SELECT`); cualquier nodo de escritura o DDL **en cualquier parte del árbol** (incluido un `DELETE` dentro de un CTE), `SELECT ... INTO` o `FOR UPDATE`/`FOR SHARE` → `NO_ES_SELECT`.
  - Toda tabla con esquema o catálogo `rag`, `pg_catalog` o `information_schema` (sin distinguir mayúsculas ni comillas) → `FUERA_DE_ESQUEMA`.
  - Funciones de reloj, cualquier función que empiece con `pg_` o `lo_`, `set_config` y `dblink*`, y literales de texto que sean exactamente `now`, `today`, `tomorrow` o `yesterday` (sin distinguir mayúsculas) → `INVALIDA`.
  - Devuelve la consulta original sin espacios sobrantes ni `;` final (no la regenerada por `sqlglot`, para mostrar en la UI lo que escribió el LLM).
  - Antes de escribirlo, comprobar con una prueba rápida en la consola los nombres reales de los nodos de `sqlglot` 30.21.0 (`exp.Into`, `exp.Lock`, `exp.CurrentDate`, `exp.CurrentTimestamp`, `exp.Anonymous`, `exp.Command`, etc.), porque difieren entre versiones. Docstring que liste las reglas.
- [x] T041 [P] [US1] Crear `src/gym_agent/tools/sql_prompt.py`: `describir_esquema() -> str` (lee `information_schema` con `connect_ro()` **solo para `public`**: tablas, columnas con tipo y si admiten NULL, claves primarias y foráneas, en texto compacto; se calcula una vez y se guarda con `functools.cache`); `GLOSARIO` (las definiciones de [data-model.md](data-model.md#definiciones-de-negocio-que-el-agente-debe-respetar): "hoy" = `REFERENCE_DATE`, "último mes" = `fecha BETWEEN REFERENCE_DATE - 29 AND REFERENCE_DATE` **escrito como fechas literales calculadas desde `REFERENCE_DATE`**, "no asistió" = `presente = false`, "pago vencido" = `estado = 'vencido'` y un `pendiente` no lo es, "socio activo", "equipo en mantenimiento"; valores válidos de cada `estado`, `medio_pago` y `dia_semana`; este último **sin tildes**); y `construir_prompt_sql(esquema, pregunta, idioma, intento_previo=None) -> str` con las reglas: un único `SELECT`, sin `CURRENT_DATE`/`now()` ni literales `'today'`, solo tablas del esquema dado, nombres de columnas exactos, fechas literales, y en un reintento la consulta anterior y el error saneado. Docstrings.
- [x] T042 [US1] Crear `src/gym_agent/tools/sql_tool.py` (parte 1, sin LLM): modelos Pydantic `ErrorSQL(codigo, mensaje, detalle)` y `ResultadoSQL(ok, sql_ejecutado, columnas, filas, truncado, intentos, error)` según el contrato; `MENSAJES` con el texto de usuario de cada código (tabla de errores del contrato, en castellano); `sanear_error(texto) -> str` (ver T038 (i)); y `ejecutar_sql(sql) -> ResultadoSQL` que abre `connect_ro()`, pone `conn.read_only = True`, ejecuta `SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT_S}s'`, corre la consulta, lee `fetchmany(MAX_FILAS + 1)` (si hay más de `MAX_FILAS`, corta y marca `truncado`), convierte fechas a texto ISO y `Decimal` a número, y cierra siempre la conexión. Mapeo de errores de `psycopg`: `QueryCanceled` → `TIMEOUT`; `ReadOnlySqlTransaction` e `InsufficientPrivilege` → `NO_ES_SELECT`; cualquier otro `psycopg.Error` o `RuntimeError` de conexión → `ERROR_EJECUCION`; el texto técnico va en `detalle`.
- [x] T043 [US1] Completar `src/gym_agent/tools/sql_tool.py` (parte 2, con LLM): `class ConsultaSQL(BaseModel)` con el campo `sql: str`; `generar_sql_llm(pregunta, idioma, intento_previo=None) -> str` que arma el prompt con `describir_esquema()` y `construir_prompt_sql`, y llama a `get_chat_model().with_structured_output(ConsultaSQL)` a través de `reintentar` (de `gym_agent.llm`); y `consultar(pregunta, idioma, *, generador=generar_sql_llm, ejecutor=ejecutar_sql) -> ResultadoSQL` con el bucle de hasta `MAX_INTENTOS_SQL` intentos: generar → `validar` → ejecutar; las reglas de reintento y de "no reintentar `NO_ES_SELECT`/`FUERA_DE_ESQUEMA`" de esta etapa; el mensaje de error que se le pasa al LLM pasa por `sanear_error`; `intentos` cuenta las consultas generadas; **nunca lanza excepciones** (incluida una falla del LLM). Docstrings.
- [x] T044 [US1] Validación con el LLM real (script descartable en el directorio temporal de la sesión, **no versionado**; requiere `GEMINI_API_KEY` y la base cargada): pasar por `consultar` las preguntas S01 a S07 de [eval-battery.md](contracts/eval-battery.md) y comparar cada resultado con la consulta SQL escrita a mano (la "dorada") ejecutada con `agente_ro`; revisar que "último mes" use las fechas literales `2026-09-01` a `2026-09-30`, que "asistencias" cuente `presente = true` y que "vencido" use `estado = 'vencido'`. Probar además: un socio inexistente (B04) → `ok = True` con `filas = []`; y "Borrá todos los pagos vencidos" enviado **directo** a `consultar` (sin router) → no cambia el hash de las tablas (`hash_tablas`). Si alguna no coincide, ajustar el glosario/prompt de T041 y repetir. Anotar los resultados y los ajustes en [research.md](research.md) (nueva sección R14, "SQL tool: validación con el LLM").

**Punto de control**: los tests de la fase pasan; las 7 preguntas SQL devuelven lo mismo que sus consultas doradas; ningún intento de escritura cambia la base.

---

## Fase 8: Historia 2, RAG tool (P1)

**Objetivo**: `buscar(pregunta)` devuelve los fragmentos más similares de los PDFs con documento y página, o ninguno si no pasan el umbral (contrato [rag-tool.md](contracts/rag-tool.md)).

**Prueba independiente**: `pytest tests/unit/test_rag_tool.py tests/integration/test_rag_tool_db.py` en verde sin LLM y `pytest -m llm tests/integration/test_rag_tool_llm.py` con la clave.

### Tests de la fase

- [x] T045 [P] [US2] Crear `tests/unit/test_rag_tool.py` (sin base ni LLM; `embeber` y el acceso a la base inyectados como funciones falsas). Cubre `buscar`: (a) conserva los fragmentos con `similitud >= umbral` (el valor igual al umbral **se conserva**), los devuelve ordenados de mayor a menor y descarta el resto; (b) si ninguno pasa, `ok = True` y `fragmentos == []`; (c) pasa `k` a la consulta; (d) si `embeber` lanza una excepción → `ok = False`, `EMBEDDING_FALLO`; (e) un vector que no tiene 1536 elementos → `DIMENSION_INVALIDA` y no se consulta la base; (f) si la consulta lanza una excepción → `ERROR_EJECUCION`; (g) en todos los casos de error `buscar` no propaga la excepción y `error.detalle` guarda el texto técnico.
- [x] T046 [P] [US2] Crear `tests/integration/test_rag_tool_db.py` (requiere la base ingestada; **sin LLM**; `embeber` falso). (a) Leer con `conn_admin` el embedding del chunk del reglamento que contiene "Congelamiento de la cuota"; usarlo como embedding de la pregunta: el primer fragmento es ese chunk (mismo texto), `documento = "Reglamento interno"`, `pagina = 3` y `similitud > 0.99`. (b) `k = 2` devuelve como máximo 2 fragmentos y el valor por defecto 4 como máximo 4, ordenados por similitud descendente. (c) Un vector normalizado generado con `random.Random(1)` (sin relación con ningún texto) con umbral 0,6 devuelve `[]`. (d) `Fragmento` trae `documento`, `archivo`, `pagina`, `texto`, `similitud`.
- [x] T047 [P] [US2] Crear `tests/integration/test_rag_tool_llm.py` con `@pytest.mark.llm` (embeddings reales de Gemini; requiere la ingesta hecha). Para cada pregunta, el primer fragmento debe ser del documento esperado: congelamiento → Reglamento interno; rutina para principiante → Guía de rutinas y nutrición; mantenimiento de cintas → Manual de uso y mantenimiento del equipamiento; cancelación de clases → Reglamento interno; qué comer antes de entrenar → Guía de rutinas y nutrición; mora → Reglamento interno. "¿Quién ganó el mundial?" → `fragmentos == []`. Además un test llamado `test_limitacion_conocida_estacionamiento` que documenta que "¿Cuál es la política de estacionamiento del gimnasio?" **sí** devuelve fragmentos (similitud ~0,69, todos del Reglamento interno), con un comentario que remite a research R9 y aclara que decidir que esos fragmentos no responden es trabajo de la síntesis (Etapa 2); si falla porque el umbral cambió, hay que revisar esa decisión, no borrar el test.

### Implementación de la fase

- [x] T048 [US2] Mover `_literal_vector` de `src/gym_agent/rag/ingest.py` a `src/gym_agent/llm.py` como `literal_vector` público (junto a `normalize`, con su docstring) y actualizar `ingest.py` para importarlo; así la RAG tool no importa un módulo que usa `connect_admin()`. Verificar que `pytest tests/unit tests/integration` sigue en verde y que `python scripts/ingest_pdfs.py` sigue funcionando.
- [x] T049 [US2] Crear `src/gym_agent/tools/rag_tool.py`: modelos Pydantic `Fragmento(documento, archivo, pagina, texto, similitud)`, `ErrorRAG(codigo, mensaje, detalle)` y `ResultadoRAG(ok, fragmentos, error)`; y `buscar(pregunta, k=K_FRAGMENTOS, umbral=UMBRAL_SIMILITUD, *, embeber=embeber_consulta) -> ResultadoRAG` que: embebe la pregunta (el vector ya viene normalizado de `embeber_consulta`); verifica que tenga `EMBEDDING_DIM` elementos (`DIMENSION_INVALIDA` si no); ejecuta con `connect_ro()` la consulta **fija y parametrizada** del contrato (`ORDER BY c.embedding <=> %(q)s::vector LIMIT %(k)s`, con `1 - (c.embedding <=> %(q)s::vector) AS similitud` y el vector pasado con `literal_vector`); descarta los de similitud menor al umbral; y cierra siempre la conexión. Nunca lanza excepciones (códigos `EMBEDDING_FALLO`, `DIMENSION_INVALIDA`, `ERROR_EJECUCION`). El docstring del módulo explica que el umbral filtra ruido pero no decide si el documento responde la pregunta.
- [x] T050 [US2] Ejecutar `pytest tests/unit/test_rag_tool.py tests/integration/test_rag_tool_db.py` y después `pytest -m llm tests/integration/test_rag_tool_llm.py`; corregir hasta que pasen. Si alguna similitud difiere de lo anotado en research R9, anotar los valores nuevos allí (no ajustar el umbral en esta etapa: la calibración final es de la Etapa 4, con la batería completa y 2 o 3 reformulaciones por pregunta).

**Punto de control**: `buscar` devuelve el documento y la página correctos para las 6 preguntas con respuesta y `[]` para la de fuera de dominio.

---

## Fase 9: Cierre de la Etapa 1

**Propósito**: interfaz pública de las tools, verificación global y documentación al día.

- [x] T051 Completar `src/gym_agent/tools/__init__.py` con un docstring y las exportaciones `consultar`, `ResultadoSQL`, `ErrorSQL`, `buscar`, `ResultadoRAG`, `Fragmento`, `ErrorRAG`: es lo único que importará el grafo en la Etapa 2. Verificar con `grep` que ningún archivo de `src/gym_agent/tools/` importa `connect_admin` (principio II).
- [x] T052 Correr `pytest tests/unit tests/integration` (con la base levantada) y `pytest -m llm` (con la clave): todo en verde, sin tests saltados salvo los `llm` cuando falta la clave. Confirmar con `hash_tablas` que los tests no dejaron cambios en la base.
- [x] T053 Actualizar la documentación a lo implementado: [contracts/sql-tool.md](contracts/sql-tool.md) (reglas de reintento: `NO_ES_SELECT` y `FUERA_DE_ESQUEMA` no se reintentan; campo `mensaje` de `ErrorSQL`; filas serializadas a JSON; validación de los literales `'now'`, `'today'`, `'tomorrow'`, `'yesterday'` y de DML dentro de CTE), [contracts/rag-tool.md](contracts/rag-tool.md) (umbral 0,6 y su alcance), [plan.md](plan.md) (decisión de diseño 5, "umbral 0,5" → 0,6; y `sql_prompt.py` en la estructura de `tools/`) y la lista de tests de [quickstart.md](quickstart.md) si cambió algún comando.
- [x] T054 Dejar los artefactos listos para commit: `git status` sin `.env` ni `logs/`; confirmar que el script descartable de T044 no está en el repositorio; y marcar acá las tareas completadas.

**Punto de control final de la Etapa 1**: `consultar` y `buscar` funcionan solas con el LLM y la base reales; los tests unitarios y de integración pasan; la Etapa 2 (grafo) puede empezar importando solo `gym_agent.tools`.

---

## Dependencias y orden de ejecución (Etapa 1)

### Entre fases

- **Fase 6**: requiere la Etapa 0 cerrada (T033). Bloquea a las Fases 7 y 8 solo por las constantes de T035 y el marcador de T036.
- **Fase 7 (SQL tool)** y **Fase 8 (RAG tool)**: independientes entre sí; se pueden hacer en paralelo (archivos distintos). Si trabaja una sola persona: primero la Fase 7, porque la Historia 1 es el requisito mínimo.
- **Fase 9**: requiere las Fases 7 y 8.

### Dentro de las fases

- Fase 7: T037 a T039 en paralelo y antes de T040; T040 y T041 en paralelo (archivos distintos); T042 puede avanzar en paralelo con ellos; T043 requiere T040, T041 y T042; T044 requiere T043 y la clave de Gemini.
- Fase 8: T045 a T047 en paralelo y antes de T049; T048 antes de T049; T050 requiere T049 y la clave de Gemini.

### Oportunidades de paralelismo

```text
Después de la Fase 6:
  Persona A (SQL):  T037-T039 → T040 ∥ T041 → T042 → T043 → T044
  Persona B (RAG):  T045-T047 → T048 → T049 → T050
Después de ambas:   T051 → T052 → T053 → T054
```

## Estrategia de implementación (Etapa 1)

1. **SQL tool primero** (Historia 1, P1): es lo que más riesgo de seguridad concentra; el validador (T037/T040) es la pieza que más conviene tener sólida y probada antes de conectar el LLM.
2. **Validar con el LLM real pronto** (T044): es el riesgo principal de la etapa (SQL incorrecto para "último mes" o "no asistió"); si falla, se ajusta el glosario antes de construir el grafo encima.
3. **No ajustar el umbral de la RAG** en esta etapa (T050): se calibra en la Etapa 4 con la batería completa; ahora solo se verifica que filtra lo evidentemente fuera de dominio.
4. **No pasar a la Etapa 2** hasta cerrar T052.
