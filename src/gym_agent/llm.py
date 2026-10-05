"""Fábricas de los modelos de Gemini y utilidades de embeddings.

Parámetros confirmados en la prueba de humo T008 (research R2):

- El chat devuelve `respuesta.content` como una *lista de bloques*; para obtener el texto
  hay que usar `respuesta.text`.
- `task_type` (`RETRIEVAL_DOCUMENT` / `RETRIEVAL_QUERY`) se pasa en cada llamada de embeddings.
- La clave se lee de `GEMINI_API_KEY` (la librería la busca sola en el entorno).

Los reintentos del SDK usan una espera fija y no respetan el `retry_delay` del servidor, por
eso se desactivan (`max_retries=1`) y se reintenta acá con espera exponencial (research R13).

La cuota diaria del plan gratuito es por modelo: cuando se agota, esperar no sirve (el servidor
pide horas), así que `invocar_chat` pasa al siguiente modelo de `CHAT_MODELS` (research R14).
"""

import logging
import math
import re
import time
from collections.abc import Callable
from typing import Any, TypeVar

from langchain_core.exceptions import (
    ModelAPIError,
    ModelConnectionError,
    ModelRateLimitError,
    ModelTimeoutError,
)
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

from gym_agent.config import CHAT_MODEL, CHAT_MODELS, EMBEDDING_DIM, EMBEDDING_MODEL, require_env

T = TypeVar("T")

log = logging.getLogger(__name__)

_CODIGOS_TRANSITORIOS = {429, 500, 502, 503, 504}
_ERRORES_TRANSITORIOS = (ModelRateLimitError, ModelAPIError, ModelConnectionError, ModelTimeoutError)

_ESPERA_MAXIMA_RAZONABLE_S = 300
"""Si el servidor pide esperar más que esto, la cuota no se libera reintentando."""
_RETRY_DELAY = re.compile(r"retryDelay'?\"?\s*:\s*'?\"?(\d+)")

_modelos_agotados: set[str] = set()
"""Modelos con la cuota diaria agotada en este proceso: no se les vuelve a pedir nada."""


def get_chat_model(modelo: str = CHAT_MODEL) -> ChatGoogleGenerativeAI:
    """Modelo de chat de Gemini (por defecto el principal) con temperatura 0 (respuestas reproducibles)."""
    require_env("GEMINI_API_KEY")
    return ChatGoogleGenerativeAI(model=modelo, temperature=0, max_retries=1)


def _cadena(exc: BaseException):
    """La excepción y sus causas (`__cause__`), en orden."""
    actual: BaseException | None = exc
    while actual is not None:
        yield actual
        actual = actual.__cause__


def es_cuota_agotada(exc: BaseException) -> bool:
    """Indica si el error es la cuota diaria agotada (u otra que pide esperar más de 5 minutos).

    El 429 de Gemini trae el `quotaId` (`...PerDay...`) y el `retryDelay` en el texto del error.
    """
    for actual in _cadena(exc):
        texto = str(actual)
        if "PerDay" in texto:
            return True
        if (espera := _RETRY_DELAY.search(texto)) and int(espera.group(1)) > _ESPERA_MAXIMA_RAZONABLE_S:
            return True
    return False


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
    `google-genai` (que trae el código HTTP en `.code`) en otra excepción. La cuota diaria
    agotada no es transitoria: reintentar solo perdería tiempo.
    """
    if es_cuota_agotada(exc):
        return False
    return any(
        isinstance(actual, _ERRORES_TRANSITORIOS) or getattr(actual, "code", None) in _CODIGOS_TRANSITORIOS
        for actual in _cadena(exc)
    )


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


def invocar_chat(armar: Callable[[ChatGoogleGenerativeAI], Any], entrada: Any) -> Any:
    """Invoca el chat con el primer modelo de `CHAT_MODELS` que todavía tenga cuota.

    Con cada modelo se reintentan los errores transitorios (`reintentar`); si el modelo agotó
    la cuota diaria, se lo recuerda como agotado y se pasa al siguiente.

    Args:
        armar: recibe el modelo de chat y devuelve lo que se invoca, por ejemplo
            `lambda m: m.with_structured_output(ConsultaSQL)`.
        entrada: lo que se pasa a `.invoke` (el prompt).

    Raises:
        La excepción del último modelo si todos fallan, o cualquier error no transitorio.
    """
    disponibles = [m for m in CHAT_MODELS if m not in _modelos_agotados] or [CHAT_MODELS[-1]]
    for modelo in disponibles:
        try:
            return reintentar(armar(get_chat_model(modelo)).invoke, entrada)
        except Exception as e:
            if not es_cuota_agotada(e):
                raise
            _modelos_agotados.add(modelo)
            if modelo == disponibles[-1]:
                raise
            log.warning("Cuota diaria agotada en %s; se usa el modelo de respaldo.", modelo)
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
