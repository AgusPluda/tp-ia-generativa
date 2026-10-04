---

description: "Tareas de la Etapa 0 (setup) del agente SQL + RAG para gimnasio"
---

# Tareas: Agente conversacional SQL + RAG para gimnasio, Etapa 0 (Setup)

**Entrada**: documentos de diseño en `specs/001-agente-sql-rag-gimnasio/` ([plan.md](plan.md), [spec.md](spec.md), [data-model.md](data-model.md), [research.md](research.md), [contracts/](contracts/), [quickstart.md](quickstart.md)).

**Alcance**: solo la **Etapa 0** del plan (entorno, datos sintéticos deterministas, 3 PDFs sintéticos e ingesta a `rag.chunks`). Fecha objetivo: 06/10/2026. Las etapas 1 a 5 (tools, agente, interfaz, evaluación, cierre) se generan después con `/speckit-tasks`.

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
