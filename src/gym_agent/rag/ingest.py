"""Ingesta de los PDFs en `rag.documentos` y `rag.chunks` (contrato rag-tool, "Ingesta").

Se usa solo desde `scripts/ingest_pdfs.py`, con la conexión de administrador.
"""

from pathlib import Path

from pypdf import PdfReader

from gym_agent.config import EMBEDDING_DIM, PDF_DIR
from gym_agent.db import connect_admin
from gym_agent.llm import embeber_documentos
from gym_agent.rag.chunking import Chunk, dividir_en_chunks
from gym_agent.synthetic.catalog import DOCUMENTOS, Documento


def extraer_paginas(ruta: Path) -> list[str]:
    """Texto de cada página del PDF, en orden.

    Usa `extraction_mode="layout"` porque es el único modo de `pypdf` que deja una línea en
    blanco entre párrafos (el modo normal solo devuelve saltos de línea). Ese modo alinea el
    texto con espacios, así que se colapsan los espacios de cada renglón.
    """
    paginas = []
    for pagina in PdfReader(ruta).pages:
        texto = pagina.extract_text(extraction_mode="layout")
        paginas.append("\n".join(" ".join(renglon.split()) for renglon in texto.splitlines()))
    return paginas


def _verificar_dimension(vectores: list[list[float]], documento: Documento) -> None:
    """Falla con un mensaje claro si algún vector no entra en `rag.chunks.embedding vector(1536)`."""
    for vector in vectores:
        if len(vector) != EMBEDDING_DIM:
            raise ValueError(
                f"El modelo devolvió un embedding de {len(vector)} elementos para "
                f"'{documento.titulo}', pero la columna rag.chunks.embedding es vector({EMBEDDING_DIM}). "
                "Revisá output_dimensionality / EMBEDDING_DIM en src/gym_agent/config.py, o ajustá la "
                "columna en db/init/01_schema.sql y volvé a crear la base."
            )


def _literal_vector(vector: list[float]) -> str:
    """Formato de texto de pgvector (`[0.1,0.2,...]`); se castea con `::vector` en el INSERT."""
    return "[" + ",".join(repr(x) for x in vector) + "]"


def ingestar(directorio: Path = PDF_DIR) -> dict[str, int]:
    """Extrae, divide, embebe e inserta los tres PDFs del catálogo.

    Primero calcula todos los embeddings y recién después escribe, en una sola transacción: si la
    API falla a mitad de camino, la base queda como estaba. Es idempotente: actualiza la fila de
    cada documento (`ON CONFLICT (nombre_archivo)`) y reemplaza todos sus chunks.

    Args:
        directorio: carpeta con los PDFs (por defecto `data/pdfs/`).

    Returns:
        Título del documento → cantidad de chunks insertados.
    """
    preparados: list[tuple[Documento, list[Chunk], list[list[float]]]] = []
    for documento in DOCUMENTOS.values():
        ruta = Path(directorio) / documento.nombre_archivo
        if not ruta.exists():
            raise FileNotFoundError(f"No existe {ruta}. Generá los PDFs con: python scripts/generate_pdfs.py")
        chunks = dividir_en_chunks(extraer_paginas(ruta))
        if not chunks:
            raise ValueError(f"No se pudo extraer texto de {ruta}.")
        vectores = embeber_documentos([c.contenido for c in chunks])
        _verificar_dimension(vectores, documento)
        preparados.append((documento, chunks, vectores))

    with connect_admin() as conn:
        try:
            with conn.cursor() as cur:
                for documento, chunks, vectores in preparados:
                    cur.execute(
                        """
                        INSERT INTO rag.documentos (nombre_archivo, titulo) VALUES (%s, %s)
                        ON CONFLICT (nombre_archivo)
                        DO UPDATE SET titulo = EXCLUDED.titulo, fecha_ingesta = now()
                        RETURNING id_documento
                        """,
                        (documento.nombre_archivo, documento.titulo),
                    )
                    (id_documento,) = cur.fetchone()
                    cur.execute("DELETE FROM rag.chunks WHERE id_documento = %s", (id_documento,))
                    cur.executemany(
                        """
                        INSERT INTO rag.chunks (id_documento, pagina, orden, contenido, embedding)
                        VALUES (%s, %s, %s, %s, %s::vector)
                        """,
                        [
                            (id_documento, c.pagina, c.orden, c.contenido, _literal_vector(v))
                            for c, v in zip(chunks, vectores, strict=True)
                        ],
                    )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    return {documento.titulo: len(chunks) for documento, chunks, _ in preparados}
