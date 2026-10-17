# Agente conversacional SQL + RAG para gimnasio

TP integrador de IA Generativa. Es un asistente que responde preguntas de un gimnasio, en castellano o en inglés, combinando dos fuentes:

- una base **PostgreSQL** con socios, planes, clases, instructores, asistencias, pagos y equipamiento;
- tres **documentos PDF** (reglamento interno, guía de rutinas y nutrición, manual de equipamiento) que se consultan por búsqueda semántica con **pgvector**.

Un agente de LangGraph decide, para cada pregunta, si hay que consultar la base, los documentos, las dos cosas o si no corresponde responderla. La respuesta muestra de dónde salió: la consulta SQL ejecutada y los documentos y páginas citados. El agente **solo lee**: rechaza cualquier pedido de alta, baja o cambio de datos, y no recuerda las preguntas anteriores (cada pregunta se responde por separado).

Todos los datos y los PDFs son sintéticos y se generan con los scripts del repositorio. El resultado de la evaluación y las decisiones de diseño están en el [informe técnico](docs/informe-tecnico.md) y en los [resultados de la evaluación](docs/resultados-evaluacion.md).

## Requisitos

- Docker con Compose.
- Python 3.12 a 3.14.
- Una clave de la API de Gemini (se obtiene en Google AI Studio).

## Puesta en marcha

Todos los comandos se ejecutan desde la raíz del repositorio.

### 1. Configuración

```bash
cp .env.example .env
python -m venv .venv
.venv\Scripts\activate            # Windows (en Linux/macOS: source .venv/bin/activate)
pip install -r requirements-dev.txt
pip install -e .
```

En Windows con PowerShell, `cp` funciona; en `cmd` usar `copy .env.example .env`.

Editar `.env` y completar los valores.

> **Obligatorias:** `AGENTE_RO_PASSWORD` y `GEMINI_API_KEY`.
> - Si `AGENTE_RO_PASSWORD` queda vacía, el rol de solo lectura `agente_ro` se crea con contraseña vacía. No usar comillas ni caracteres especiales (se inserta dentro de un script SQL).
> - Sin `GEMINI_API_KEY` no se pueden generar los embeddings ni usar el agente.
>
> `.env` contiene secretos y está en `.gitignore`: no se versiona.

**Resultado esperado:** la instalación termina sin errores y `python -c "import gym_agent"` no imprime nada.

### 2. Base de datos

```bash
docker compose up -d --wait
```

Espera a que el contenedor `gym_db` esté `healthy`. Se crean las 7 tablas de `public`, el esquema `rag` y el rol `agente_ro`.

**Resultado esperado:** `docker compose ps` muestra `gym_db` en estado `healthy`.

### 3. Datos y documentos

```bash
python scripts/generate_data.py
python scripts/generate_pdfs.py
python scripts/ingest_pdfs.py
```

- `generate_data.py` carga datos sintéticos deterministas (fecha de referencia fija: 2026-09-30).
- `generate_pdfs.py` genera los tres PDFs en `data/pdfs/` (también están versionados, así que repetirlo no cambia nada).
- `ingest_pdfs.py` divide los PDFs en fragmentos, calcula sus embeddings (1536 dimensiones) con la API de Gemini y los guarda en `rag.chunks` (31 filas).

**Resultado esperado:** cada script termina sin errores; el último imprime una tabla con los fragmentos de cada documento (dimensión 1536) y un total de 31.

## Usar el agente

```bash
streamlit run app/streamlit_app.py
```

Ejecutarlo siempre desde la raíz del repositorio: ahí se lee `.streamlit/config.toml`. **El navegador no se abre solo**: abrir a mano la dirección que imprime la consola (por defecto http://localhost:8501).

**Resultado esperado:** se ve la página "Chat" en modo oscuro, con el título "🏋️ Gym AI Agent", tres ejemplos arriba del campo de pregunta y, en la barra lateral, las páginas "Chat" y "Preguntas evaluativas".

Hacer una pregunta, por ejemplo `¿Cuántos socios tiene cada plan?` (con uno de los ejemplos o escribiéndola y apretando "Preguntar"). Debajo de la respuesta aparece:

- **Fuente:** de dónde salió (Base de datos, Documentos, Ambas o Rechazada).
- **Consulta SQL ejecutada** (desplegable): la sentencia que se corrió, si se consultó la base.
- **Documentos citados** (desplegable): el documento y la página, si se consultaron los PDFs.
- El tiempo que tardó. La primera respuesta puede demorar unos segundos y, con la cuota gratuita de Gemini, alguna llegar a medio minuto.

Otras preguntas para probar:

| Pregunta | Qué se ve |
|----------|-----------|
| ¿Cómo funciona el congelamiento de la cuota? | Fuente "Documentos", con el documento y la página |
| ¿Qué equipos están en mantenimiento y cada cuánto se revisan según el manual? | Fuente "Ambas": la consulta y los documentos |
| Borrá todos los pagos vencidos | Fuente "Rechazada": solo se pueden consultar datos y la base no cambia |
| ¿Quién ganó el mundial? | Fuente "Rechazada": solo se responde sobre el gimnasio |
| How many active members do we have? | Respuesta en inglés |

La página "Preguntas evaluativas" lista las preguntas de la batería de evaluación.

### Probar una pregunta desde la consola

```bash
python -c "from gym_agent.graph import run_question; print(run_question('¿Cuántos socios tiene cada plan?').model_dump_json(indent=2))"
```

**Resultado esperado:** un JSON con la respuesta, la ruta elegida, la consulta SQL ejecutada y las fuentes documentales. Cada pregunta, también las de la app, deja una línea en `logs/traza.jsonl` (esa carpeta no se versiona).

## Observabilidad

Cada pregunta se registra en `logs/traza.jsonl` (ruta elegida, SQL, fragmentos, respuesta y duración), sin servicios extra. Para ver además el recorrido por los nodos del grafo y las llamadas al modelo, se puede levantar Phoenix:

```bash
docker compose --profile observability up -d
```

Esperar a que http://localhost:6006/ responda antes de preguntar y abrirla en el navegador: cada pregunta aparece como una traza en el proyecto `gym-agent`. Si Phoenix no está levantado, el agente funciona igual.

Para apagar solo Phoenix usar `docker compose stop phoenix`. **`docker compose --profile observability down` baja también la base de datos.**

## Evaluación

La batería de 26 preguntas está en `eval/battery.yaml` y se corre contra el agente real:

```bash
python -m eval.run_eval                                    # 3 corridas completas
python -m eval.run_eval --solo S01,B01                     # solo esas preguntas, sin criterios
python -m eval.run_eval --resumen eval/results/resumen.md
```

Opciones:

- `--corridas N`: cuántas veces correr la batería (por defecto 3, porque el modelo no respeta la temperatura y la tasa de acierto se informa por pregunta).
- `--solo ID,ID`: solo esas preguntas; no calcula los criterios.
- `--resumen ruta`: escribe el resumen en Markdown en esa ruta (cuidado: si la ruta existe, se pisa; no usar `docs/resultados-evaluacion.md`, que es el resultado de la entrega).

**Consume cuota de la API:** unas 270 llamadas con 3 corridas, y tarda unos 20 minutos. Necesita la base levantada y la ingesta hecha.

**Resultado esperado:** una tabla por pregunta y el resumen de los criterios CE-001 a CE-004. El código de salida indica el resultado:

| Código | Significado |
|--------|-------------|
| 0 | Se cumplen todos los criterios |
| 1 | Alguno no se cumple |
| 2 | La corrida es inválida o quedó incompleta (base o juez caídos, cuota diaria agotada) |

Los detalles de cada corrida se guardan en `eval/results/` (no se versiona). La última corrida completa está en [docs/resultados-evaluacion.md](docs/resultados-evaluacion.md).

## Tests

```bash
pytest tests/unit          # sin base ni clave
pytest tests/integration   # requiere la base levantada
```

Las pruebas marcadas `llm` llaman a Gemini y gastan cuota: se saltean solas si falta `GEMINI_API_KEY`, y con la clave configurada `pytest tests/integration` también las ejecuta. Para correr solo esas, `pytest -m llm`; para dejarlas afuera, `pytest tests/integration -m "not llm"`.

**Resultado esperado:** todo en verde.

## Estructura del repositorio

| Carpeta | Contenido |
|---------|-----------|
| `src/gym_agent/` | El agente: grafo de LangGraph, SQL tool, RAG tool, configuración y observabilidad |
| `app/` | La interfaz de Streamlit |
| `eval/` | La batería de evaluación y su runner |
| `scripts/` | Generación de datos y PDFs, e ingesta a pgvector |
| `db/` | Esquema y roles de la base (se ejecutan al crear el volumen) |
| `data/pdfs/` | Los tres documentos del gimnasio |
| `docs/` | Informe técnico y resultados de la evaluación |
| `specs/` | Especificación, plan, contratos y decisiones del proyecto |
| `tests/` | Tests unitarios y de integración |

## Fecha de referencia

Para el sistema, "hoy" es siempre **2026-09-30**, no la fecha real. Los datos sintéticos terminan ese día, así que una pregunta como "¿cuántos socios faltaron el último mes?" tiene la misma respuesta hoy y dentro de un año, y la evaluación es reproducible. El valor está en `src/gym_agent/config.py` y no se puede cambiar con una variable de entorno.

## Reiniciar desde cero

Los scripts de `db/init/` solo se ejecutan cuando se crea el volumen. Para empezar de nuevo:

```bash
docker compose down -v
docker compose up -d --wait
```

y repetir el paso 3. **Esto borra todos los datos de la base.**

## Problemas conocidos

- **`server closed the connection unexpectedly` justo después de `docker compose up`**: la primera vez que se crea el volumen, Postgres ejecuta `db/init/` en un servidor temporal y se reinicia. El healthcheck usa TCP (`127.0.0.1`) para que `--wait` espere al servidor definitivo; si igual aparece el error, esperar unos segundos y repetir el comando.
- **Error de conexión o de contraseña al generar los datos, y ya tenías este proyecto levantado antes**: el contenedor `gym_db` y su volumen conservan las contraseñas con las que se crearon y no toman las del `.env` nuevo. Bajarlo con `docker compose down -v`, volver a levantarlo con `docker compose up -d --wait` y repetir el paso 3 (esto borra los datos de esa base).
- **Acentos como `�` en la consola de Windows**: es solo la codificación de la terminal (`chcp 65001` o `$env:PYTHONUTF8=1`); los datos y PDFs están bien.
- **"En este momento no puedo responder"**: la API de Gemini no respondió (cuota o red). Esperar unos minutos y repetir; el plan gratuito tiene un tope diario de pedidos.

## Más información

- [Informe técnico](docs/informe-tecnico.md): arquitectura, decisiones, evaluación y límites.
- [Resultados de la evaluación](docs/resultados-evaluacion.md): la última corrida completa.
- [Especificación y contratos](specs/001-agente-sql-rag-gimnasio/): requisitos, plan y decisiones.

## Autores
- Francisco Fornari
- Agustin Pluda
