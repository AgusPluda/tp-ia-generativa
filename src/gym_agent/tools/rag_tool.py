"""RAG tool: busca en los PDFs los fragmentos más parecidos a la pregunta.

Contrato: specs/001-agente-sql-rag-gimnasio/contracts/rag-tool.md. Pipeline de `buscar`:

1. **Embeber** la pregunta (`embeber_consulta`, ya normalizada) y verificar que tenga `EMBEDDING_DIM`.
2. **Consultar** `rag.chunks` con `agente_ro`: la consulta es fija y parametrizada, el LLM no
   escribe SQL en esta tool.
3. **Filtrar** los fragmentos con similitud menor al umbral.

El umbral filtra ruido, pero NO decide si los documentos responden la pregunta: una pregunta
fuera de tema puede superarlo (research R9). Esa decisión es de la síntesis de la Etapa 2.

`buscar` nunca lanza excepciones: los fallos viajan en `ResultadoRAG.error`. El `detalle` técnico
va solo a la traza; al usuario le llega `mensaje`.
"""

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from gym_agent.config import EMBEDDING_DIM, K_FRAGMENTOS, UMBRAL_SIMILITUD
from gym_agent.db import connect_ro
from gym_agent.llm import embeber_consulta, literal_vector

CodigoErrorRAG = Literal["EMBEDDING_FALLO", "DIMENSION_INVALIDA", "ERROR_EJECUCION"]

MENSAJES: dict[str, str] = {
    "EMBEDDING_FALLO": "No pude buscar en los documentos en este momento.",
    "DIMENSION_INVALIDA": "No pude buscar en los documentos en este momento.",
    "ERROR_EJECUCION": "No pude buscar en los documentos en este momento.",
}
"""Mensaje para el usuario de cada código de error."""

CONSULTA = """
SELECT d.titulo, d.nombre_archivo, c.pagina, c.contenido,
       1 - (c.embedding <=> %(q)s::vector) AS similitud
FROM rag.chunks c JOIN rag.documentos d USING (id_documento)
ORDER BY c.embedding <=> %(q)s::vector
LIMIT %(k)s
"""


class Fragmento(BaseModel):
    """Un fragmento de un PDF con su origen."""

    documento: str
    archivo: str
    pagina: int | None
    texto: str
    similitud: float
    """`1 - distancia coseno`."""


class ErrorRAG(BaseModel):
    """Por qué falló la RAG tool."""

    codigo: CodigoErrorRAG
    mensaje: str
    """Texto para el usuario, sin detalles internos."""
    detalle: str
    """Texto técnico; solo para la traza."""


class ResultadoRAG(BaseModel):
    """Salida de la RAG tool (contrato `ResultadoRAG`)."""

    ok: bool
    """`True` si la búsqueda se ejecutó, aunque no haya fragmentos relevantes."""
    fragmentos: list[Fragmento] = []
    """Ordenados por similitud descendente; vacío si ninguno supera el umbral."""
    error: ErrorRAG | None = None


def _error(codigo: CodigoErrorRAG, detalle: str) -> ResultadoRAG:
    return ResultadoRAG(ok=False, error=ErrorRAG(codigo=codigo, mensaje=MENSAJES[codigo], detalle=detalle))


def consultar_base(vector: list[float], k: int) -> list[Fragmento]:
    """Los `k` chunks más cercanos al vector, con `agente_ro`. La conexión se cierra siempre."""
    conn = connect_ro()
    try:
        with conn.cursor() as cur:
            cur.execute(CONSULTA, {"q": literal_vector(vector), "k": k})
            filas = cur.fetchall()
    finally:
        conn.close()
    return [
        Fragmento(documento=titulo, archivo=archivo, pagina=pagina, texto=contenido, similitud=float(similitud))
        for titulo, archivo, pagina, contenido, similitud in filas
    ]


Embeber = Callable[[str], list[float]]
Buscador = Callable[[list[float], int], list[Fragmento]]


def buscar(
    pregunta: str,
    k: int = K_FRAGMENTOS,
    umbral: float = UMBRAL_SIMILITUD,
    *,
    embeber: Embeber = embeber_consulta,
    consultar: Buscador = consultar_base,
) -> ResultadoRAG:
    """Devuelve hasta `k` fragmentos de los PDFs con similitud `>= umbral`, de mayor a menor.

    Args:
        pregunta: texto del usuario.
        k: cantidad máxima de fragmentos que se piden a la base.
        umbral: similitud mínima; un fragmento con exactamente ese valor se conserva.
        embeber: calcula el vector (normalizado) de la pregunta; inyectable para los tests.
        consultar: busca los `k` vecinos más cercanos; inyectable para los tests.
    """
    try:
        vector = embeber(pregunta)
    except Exception as e:
        return _error("EMBEDDING_FALLO", f"{type(e).__name__}: {e}")
    if len(vector) != EMBEDDING_DIM:
        return _error("DIMENSION_INVALIDA", f"el vector tiene {len(vector)} elementos y se esperaban {EMBEDDING_DIM}")
    try:
        fragmentos = consultar(vector, k)
    except Exception as e:  # la tool no propaga nada: el detalle queda en la traza
        return _error("ERROR_EJECUCION", f"{type(e).__name__}: {e}")
    relevantes = [f for f in fragmentos if f.similitud >= umbral]
    relevantes.sort(key=lambda f: f.similitud, reverse=True)
    return ResultadoRAG(ok=True, fragmentos=relevantes)
