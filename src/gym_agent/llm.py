"""Fábricas de los modelos de Gemini y utilidades de embeddings.

Parámetros confirmados en la prueba de humo T008 (research R2):

- El chat devuelve `respuesta.content` como una *lista de bloques*; para obtener el texto
  hay que usar `respuesta.text`.
- `task_type` (`RETRIEVAL_DOCUMENT` / `RETRIEVAL_QUERY`) se pasa en cada llamada de embeddings.
- La clave se lee de `GEMINI_API_KEY` (la librería la busca sola en el entorno).

Los reintentos del SDK usan una espera fija y no respetan el `retry_delay` del servidor, por
eso se desactivan (`max_retries=1`) y se reintenta acá con espera exponencial (research R13).
"""

import math
import time
from collections.abc import Callable
from typing import TypeVar

from langchain_core.exceptions import (
    ModelAPIError,
    ModelConnectionError,
    ModelRateLimitError,
    ModelTimeoutError,
)
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

from gym_agent.config import CHAT_MODEL, EMBEDDING_DIM, EMBEDDING_MODEL, require_env

T = TypeVar("T")

_CODIGOS_TRANSITORIOS = {429, 500, 502, 503, 504}
_ERRORES_TRANSITORIOS = (ModelRateLimitError, ModelAPIError, ModelConnectionError, ModelTimeoutError)


def get_chat_model() -> ChatGoogleGenerativeAI:
    """Modelo de chat `gemini-3.8-flash` con temperatura 0 (respuestas reproducibles)."""
    require_env("GEMINI_API_KEY")
    return ChatGoogleGenerativeAI(model=CHAT_MODEL, temperature=0, max_retries=1)


def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    """Modelo de embeddings `gemini-embedding-001` reducido a `EMBEDDING_DIM` (1536) dimensiones."""
    require_env("GEMINI_API_KEY")
    return GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL, output_dimensionality=EMBEDDING_DIM)


def normalize(vector: list[float]) -> list[float]:
    """Normaliza un vector a norma L2 = 1.

    Los embeddings de dimensión reducida no vienen normalizados. La similitud coseno no
    depende de la escala, pero se guardan normalizados para que los valores sean comparables.
    """
    norma = math.sqrt(sum(x * x for x in vector))
    if norma == 0:
        raise ValueError("No se puede normalizar un vector nulo.")
    return [x / norma for x in vector]


def es_error_transitorio(exc: BaseException) -> bool:
    """Indica si el error es de límite de tasa o del servidor y conviene reintentar.

    Recorre la cadena de causas porque los embeddings envuelven el error original de
    `google-genai` (que trae el código HTTP en `.code`) en otra excepción.
    """
    actual: BaseException | None = exc
    while actual is not None:
        if isinstance(actual, _ERRORES_TRANSITORIOS):
            return True
        if getattr(actual, "code", None) in _CODIGOS_TRANSITORIOS:
            return True
        actual = actual.__cause__
    return False


def reintentar(
    fn: Callable[..., T], *args, intentos: int = 5, espera_inicial_s: float = 2.0, **kwargs
) -> T:
    """Llama a `fn(*args, **kwargs)` y reintenta con espera exponencial ante errores transitorios.

    Espera 2, 4, 8 y 16 s entre intentos (con los valores por defecto). Los errores que no son
    transitorios (clave inválida, pedido mal formado) se propagan de inmediato.

    Args:
        fn: función a invocar (por ejemplo `modelo.invoke`).
        intentos: cantidad máxima de llamadas.
        espera_inicial_s: espera antes del primer reintento; se duplica en cada uno.
    """
    for intento in range(1, intentos + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if intento == intentos or not es_error_transitorio(e):
                raise
            time.sleep(espera_inicial_s * 2 ** (intento - 1))
    raise AssertionError("inalcanzable")


def embeber_documentos(textos: list[str]) -> list[list[float]]:
    """Embeddings normalizados para fragmentos de documentos (`RETRIEVAL_DOCUMENT`), en lote."""
    modelo = get_embeddings()
    vectores = reintentar(modelo.embed_documents, textos, task_type="RETRIEVAL_DOCUMENT")
    return [normalize(v) for v in vectores]


def embeber_consulta(texto: str) -> list[float]:
    """Embedding normalizado para una pregunta del usuario (`RETRIEVAL_QUERY`)."""
    modelo = get_embeddings()
    return normalize(reintentar(modelo.embed_query, texto, task_type="RETRIEVAL_QUERY"))
