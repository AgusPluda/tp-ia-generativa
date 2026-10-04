# Agente conversacional SQL + RAG para gimnasio

TP integrador de IA Generativa. Un agente responde preguntas de un gimnasio combinando una base PostgreSQL (socios, clases, asistencias, pagos, equipamiento) con tres documentos PDF consultados por búsqueda semántica (pgvector).

> **Estado:** Etapa 0 (datos y documentos). El agente, la app y la evaluación se agregan en las etapas siguientes y este README se completa en la Etapa 5.

## Requisitos

- Docker con Compose.
- Python 3.12 a 3.14.
- Una clave de la API de Gemini.

## Puesta en marcha

### 1. Configuración

```bash
cp .env.example .env
python -m venv .venv
.venv\Scripts\activate            # Windows (en Linux/macOS: source .venv/bin/activate)
pip install -r requirements-dev.txt
pip install -e .
```

Editar `.env` y completar los valores.

> **Obligatorias:** `AGENTE_RO_PASSWORD` y `GEMINI_API_KEY`.
> - Si `AGENTE_RO_PASSWORD` queda vacía, el rol de solo lectura `agente_ro` se crea con contraseña vacía. No usar comillas ni caracteres especiales (se inserta dentro de un script SQL).
> - Sin `GEMINI_API_KEY` no se pueden generar los embeddings ni usar el agente.
>
> `.env` contiene secretos y está en `.gitignore`: no se versiona.

### 2. Base de datos

```bash
docker compose up -d --wait
```

Espera a que el contenedor `gym_db` esté `healthy`. Se crean las 7 tablas de `public`, el esquema `rag` y el rol `agente_ro`.

### 3. Datos y documentos

```bash
python scripts/generate_data.py
python scripts/generate_pdfs.py
python scripts/ingest_pdfs.py
```

- `generate_data.py` carga datos sintéticos deterministas (fecha de referencia fija: 2026-09-30).
- `generate_pdfs.py` genera los tres PDFs en `data/pdfs/` (también están versionados).
- `ingest_pdfs.py` divide los PDFs en fragmentos, calcula sus embeddings (1536 dimensiones) y los guarda en `rag.chunks` (31 filas).

### 4. Tests

```bash
pytest tests/unit tests/integration   # los de integración requieren la base levantada
```

## Reiniciar desde cero

Los scripts de `db/init/` solo se ejecutan cuando se crea el volumen. Para empezar de nuevo:

```bash
docker compose down -v
docker compose up -d --wait
```

y repetir el paso 3. **Esto borra todos los datos de la base.**

## Problemas conocidos

- **`server closed the connection unexpectedly` justo después de `docker compose up`**: la primera vez que se crea el volumen, Postgres ejecuta `db/init/` en un servidor temporal y se reinicia. El healthcheck usa TCP (`127.0.0.1`) para que `--wait` espere al servidor definitivo; si igual aparece el error, esperar unos segundos y repetir el comando.
- **Acentos como `�` en la consola de Windows**: es solo la codificación de la terminal (`chcp 65001` o `$env:PYTHONUTF8=1`); los datos y PDFs están bien.
