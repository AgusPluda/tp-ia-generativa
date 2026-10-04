# Contrato: RAG tool

Módulo: `src/gym_agent/tools/rag_tool.py`. La ingesta vive en `src/gym_agent/rag/` y se invoca con `scripts/ingest_pdfs.py`.

## Entrada

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `pregunta` | str | Pregunta del usuario |
| `k` | int | Cantidad máxima de fragmentos (por defecto 4) |

## Salida (`ResultadoRAG`)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `ok` | bool | `true` si la búsqueda se ejecutó (aunque no haya resultados relevantes) |
| `fragmentos` | list[`Fragmento`] | Ordenados por similitud descendente; vacío si ninguno supera el umbral |
| `error` | `ErrorRAG` \| null | Presente si `ok = false` |

`Fragmento`:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `documento` | str | Título del documento (`rag.documentos.titulo`) |
| `archivo` | str | `nombre_archivo` |
| `pagina` | int \| null | Página de origen |
| `texto` | str | Contenido del chunk |
| `similitud` | float | `1 - distancia coseno` |

## Comportamiento

1. Calcula el embedding de la pregunta con `gemini-embedding-001`, `output_dimensionality=1536`, tarea `RETRIEVAL_QUERY`, y lo normaliza.
2. Consulta con la conexión `agente_ro`:

   ```sql
   SELECT d.titulo, d.nombre_archivo, c.pagina, c.contenido,
          1 - (c.embedding <=> %(q)s) AS similitud
   FROM rag.chunks c JOIN rag.documentos d USING (id_documento)
   ORDER BY c.embedding <=> %(q)s
   LIMIT %(k)s;
   ```

   La consulta es fija y parametrizada: el LLM no escribe SQL en esta tool.
3. Descarta los fragmentos con `similitud` menor al umbral (inicial 0,5; se calibra con la batería, ver [research.md](../research.md)).
4. Si ningún fragmento supera el umbral devuelve `fragmentos = []`; el nodo de síntesis responde que los documentos no contienen esa información (RF-010) en lugar de inventar.

## Errores (`ErrorRAG`)

| `codigo` | Cuándo |
|----------|--------|
| `EMBEDDING_FALLO` | La API de embeddings falló tras los reintentos |
| `DIMENSION_INVALIDA` | El vector no tiene 1536 elementos |
| `ERROR_EJECUCION` | Error de la base |

Igual que en la SQL tool, el detalle técnico va solo a la traza.

## Ingesta (contrato de `scripts/ingest_pdfs.py`)

- **Entrada**: PDFs de `data/pdfs/`. **Efecto**: filas en `rag.documentos` y `rag.chunks`, conectando como `POSTGRES_USER`.
- **Idempotente**: para cada documento se borran sus chunks y se vuelven a insertar; correrlo dos veces deja el mismo estado de contenido.
- **Chunking**: extracción por página con `pypdf`; párrafos agrupados hasta ~800 caracteres con solape de 100; un chunk nunca cruza páginas.
- **Embeddings**: tarea `RETRIEVAL_DOCUMENT`, en lotes, normalizados.
- **Falla rápida**: si un embedding no tiene 1536 elementos, aborta con un mensaje que indica ajustar `vector(1536)` o la configuración.
- **Salida**: resumen por consola (documentos, chunks por documento).
