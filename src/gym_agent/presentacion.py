"""Lógica de presentación de la interfaz: etiquetas, citas, escape de texto y ejemplos.

No importa `streamlit`, `gym_agent.tools` ni `gym_agent.db`: se prueba sin servidor y la app
solo necesita `gym_agent.graph` y este módulo (contrato `ui.md`).
"""

import re

from gym_agent.graph.state import RespuestaAgente, Ruta

ETIQUETAS_RUTA: dict[Ruta | str, str] = {
    "sql": "Base de datos",
    "rag": "Documentos",
    "ambas": "Ambas",
    "rechazar": "Rechazada",
    "fallo": "No disponible",
}
"""Texto que ve la persona para cada ruta; `fallo` cubre la excepción atrapada en `run_question`."""

EJEMPLOS: tuple[str, str, str] = (
    "¿Cuántos socios tiene cada plan?",
    "¿Cómo funciona el congelamiento de la cuota?",
    "¿Qué equipos están en mantenimiento y cada cuánto se revisan según el manual?",
)
"""Preguntas de ejemplo de la interfaz: S01 (SQL), R01 (RAG) y H02 (híbrida) de la batería."""

_PESOS_SIN_ESCAPAR = re.compile(r"(?<!\\)\$")


def etiqueta_ruta(respuesta: RespuestaAgente) -> str:
    """Etiqueta de origen de la respuesta; una falla atrapada pesa más que la ruta calculada."""
    return ETIQUETAS_RUTA["fallo" if respuesta.fallo else respuesta.ruta]


def documentos_citados(respuesta: RespuestaAgente) -> list[str]:
    """Una línea por fuente: `Documento, p. N`, o solo el documento si no tiene página."""
    return [
        fuente.documento if fuente.pagina is None else f"{fuente.documento}, p. {fuente.pagina}"
        for fuente in respuesta.fuentes_documentales
    ]


def escapar_markdown(texto: str) -> str:
    """Escapa cada `$` para que Streamlit no lo tome como fórmula; no duplica un `\\$` previo."""
    return _PESOS_SIN_ESCAPAR.sub(r"\\$", texto)
