"""Ingiere los PDFs de `data/pdfs/` en `rag.documentos` y `rag.chunks`.

Uso: python scripts/ingest_pdfs.py

Requiere la base levantada y `GEMINI_API_KEY` (calcula los embeddings). Es idempotente: se puede
volver a correr, por ejemplo si la cuota de la API cortó una ejecución anterior.
"""

from gym_agent.config import PDF_DIR
from gym_agent.db import connect_admin
from gym_agent.rag.ingest import ingestar


def main() -> None:
    ingestar(PDF_DIR)

    with connect_admin() as conn:
        filas = conn.execute(
            """
            SELECT d.titulo, count(c.id_chunk), min(vector_dims(c.embedding)), max(vector_dims(c.embedding))
            FROM rag.documentos d LEFT JOIN rag.chunks c USING (id_documento)
            GROUP BY d.id_documento, d.titulo
            ORDER BY d.id_documento
            """
        ).fetchall()

    print(f"{'documento':<50}{'chunks':>7}  dimensión")
    for titulo, chunks, dim_min, dim_max in filas:
        dimension = dim_min if dim_min == dim_max else f"{dim_min}-{dim_max}"
        print(f"{titulo:<50}{chunks:>7}  {dimension}")
    print(f"{'total':<50}{sum(f[1] for f in filas):>7}")


if __name__ == "__main__":
    main()
