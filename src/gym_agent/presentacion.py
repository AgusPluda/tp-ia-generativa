"""Lógica de presentación de la interfaz: etiquetas, citas, escape de texto y ejemplos.

No importa `streamlit`, `gym_agent.tools` ni `gym_agent.db`: se prueba sin servidor y la app
solo necesita `gym_agent.graph` y este módulo (contrato `ui.md`).
"""

import re
from typing import NamedTuple
from urllib.parse import urlsplit

from gym_agent.config import PHOENIX_ENDPOINT, REPO_ROOT
from gym_agent.graph.state import RespuestaAgente, Ruta

ETIQUETAS_RUTA: dict[Ruta | str, str] = {
    "sql": "Base de datos",
    "rag": "Documentos",
    "ambas": "Ambas",
    "rechazar": "Rechazada",
    "fallo": "No disponible",
}
"""Texto que ve la persona para cada ruta; `fallo` cubre la excepción atrapada en `run_question`."""

class Ejemplo(NamedTuple):
    """Pregunta de ejemplo: la etiqueta va en el botón y la pregunta completa en el tooltip."""

    etiqueta: str
    pregunta: str


EJEMPLOS: tuple[Ejemplo, Ejemplo, Ejemplo] = (
    Ejemplo("Socios por plan", "¿Cuántos socios tiene cada plan?"),
    Ejemplo("Congelamiento de cuota", "¿Cómo funciona el congelamiento de la cuota?"),
    Ejemplo(
        "Equipos en mantenimiento",
        "¿Qué equipos están en mantenimiento y cada cuánto se revisan según el manual?",
    ),
)
"""Ejemplos de la interfaz: S01 (SQL), R01 (RAG) y H02 (híbrida) de la batería."""

BATERIA_PATH = REPO_ROOT / "specs" / "001-agente-sql-rag-gimnasio" / "contracts" / "eval-battery.md"
"""Fuente de las preguntas evaluativas que muestra la interfaz."""

_PESOS_SIN_ESCAPAR = re.compile(r"(?<!\\)\$")
_SEPARADOR_DE_CELDAS = re.compile(r"(?<!\\)\|")


class PreguntaBateria(NamedTuple):
    """Fila de una tabla de la batería: ID, pregunta y chequeo principal."""

    id: str
    pregunta: str
    chequeo: str


class SeccionBateria(NamedTuple):
    """Sección `###` de la batería con sus preguntas."""

    titulo: str
    preguntas: list[PreguntaBateria]


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


def secciones_bateria() -> list[SeccionBateria]:
    """Lee las secciones `###` bajo `## Preguntas` de `eval-battery.md` y las filas de sus tablas."""
    secciones: list[SeccionBateria] = []
    en_preguntas = False
    for linea in BATERIA_PATH.read_text(encoding="utf-8").splitlines():
        if linea.startswith("## "):
            en_preguntas = linea.startswith("## Preguntas")
        elif not en_preguntas:
            continue
        elif linea.startswith("### "):
            secciones.append(SeccionBateria(linea[4:].strip(), []))
        elif linea.startswith("|") and secciones:
            celdas = [c.strip() for c in _SEPARADOR_DE_CELDAS.split(linea.strip())[1:-1]]
            if len(celdas) == 3 and celdas[0] != "ID" and not set(celdas[0]) <= {"-"}:
                secciones[-1].preguntas.append(PreguntaBateria(*celdas))
    return secciones


def tabla_markdown(preguntas: list[PreguntaBateria]) -> str:
    """Tabla markdown con ID, pregunta y chequeo; escapa `$` y `|` dentro de las celdas."""

    def celda(texto: str) -> str:
        return escapar_markdown(texto).replace("|", r"\|")

    filas = ["| ID | Pregunta | Chequeo principal |", "|----|----------|-------------------|"]
    filas += [f"| {celda(p.id)} | {celda(p.pregunta)} | {celda(p.chequeo)} |" for p in preguntas]
    return "\n".join(filas)


def url_phoenix() -> str:
    """URL de la interfaz de Phoenix: el endpoint de trazas sin la ruta."""
    partes = urlsplit(PHOENIX_ENDPOINT)
    return f"{partes.scheme}://{partes.netloc}"
