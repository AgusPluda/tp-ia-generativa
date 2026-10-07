"""Armado del grafo del agente (contrato `agent-graph.md`, diagrama).

`router` elige la ruta; `ambas` entra por `sql` y sigue por `rag`, de modo que la SQL tool
corre antes que la RAG tool. `rechazar` no toca ninguna tool. Sin checkpointer: cada invocación
parte de un estado vacío (RF-017).
"""

import time
from collections.abc import Callable

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from gym_agent.graph.nodes import (
    clasificar_llm,
    nodo_rag,
    nodo_rechazar,
    nodo_router,
    nodo_sintetizar,
    nodo_sql,
    sintetizar_llm,
)
from gym_agent.graph.state import (
    DecisionRouter,
    EstadoAgente,
    FuenteDocumental,
    Idioma,
    RespuestaAgente,
    Sintesis,
)
from gym_agent.observability import iniciar_phoenix, registrar_traza
from gym_agent.tools import ResultadoRAG, ResultadoSQL
from gym_agent.tools import buscar as buscar_rag
from gym_agent.tools import consultar as consultar_sql

_DESPUES_DEL_ROUTER = {"sql": "sql", "ambas": "sql", "rag": "rag", "rechazar": "rechazar"}


def _despues_del_router(estado: EstadoAgente) -> str:
    return _DESPUES_DEL_ROUTER[estado["ruta"]]


def _despues_de_sql(estado: EstadoAgente) -> str:
    return "rag" if estado["ruta"] == "ambas" else "sintetizar"


def construir_grafo(
    *,
    clasificar: Callable[[str], DecisionRouter] = clasificar_llm,
    consultar: Callable[[str, str], ResultadoSQL] = consultar_sql,
    buscar: Callable[[str], ResultadoRAG] = buscar_rag,
    sintetizar: Callable[[str], Sintesis] = sintetizar_llm,
) -> CompiledStateGraph:
    """Arma y compila el grafo con las cuatro funciones (inyectables para probar sin LLM ni base)."""
    grafo = StateGraph(EstadoAgente)
    grafo.add_node("router", nodo_router(clasificar))
    grafo.add_node("sql", nodo_sql(consultar))
    grafo.add_node("rag", nodo_rag(buscar))
    grafo.add_node("sintetizar", nodo_sintetizar(sintetizar))
    grafo.add_node("rechazar", nodo_rechazar)

    grafo.add_edge(START, "router")
    grafo.add_conditional_edges("router", _despues_del_router, ["sql", "rag", "rechazar"])
    grafo.add_conditional_edges("sql", _despues_de_sql, ["rag", "sintetizar"])
    grafo.add_edge("rag", "sintetizar")
    grafo.add_edge("sintetizar", END)
    grafo.add_edge("rechazar", END)
    return grafo.compile()


MENSAJES_FALLA: dict[Idioma, str] = {
    "es": "En este momento no puedo responder. Probá de nuevo en unos minutos.",
    "en": "I can't answer right now. Please try again in a few minutes.",
}
"""Respuesta genérica ante cualquier falla; nunca incluye el texto de la excepción."""

_grafo_por_defecto_cache: CompiledStateGraph | None = None
_phoenix_intentado = False


def _grafo_por_defecto() -> CompiledStateGraph:
    """El grafo con las funciones reales, construido una sola vez y reutilizado."""
    global _grafo_por_defecto_cache
    if _grafo_por_defecto_cache is None:
        _grafo_por_defecto_cache = construir_grafo()
    return _grafo_por_defecto_cache


def _fuentes_documentales(estado: EstadoAgente) -> list[FuenteDocumental]:
    """Documento y página de los fragmentos citados, sin repetir y en el orden de la síntesis."""
    resultado_rag = estado.get("resultado_rag")
    if resultado_rag is None:
        return []
    fuentes = {
        (f.documento, f.pagina): FuenteDocumental(documento=f.documento, pagina=f.pagina)
        for f in (resultado_rag.fragmentos[n - 1] for n in estado.get("fragmentos_citados", []))
    }
    return list(fuentes.values())


def run_question(pregunta: str, *, grafo: CompiledStateGraph | None = None) -> RespuestaAgente:
    """Responde una pregunta y registra el recorrido; nunca lanza excepciones (RF-011, RF-012).

    Ante cualquier falla devuelve el mensaje genérico, en el idioma de la pregunta si el router
    llegó a clasificarla y en castellano si no; el detalle va solo a la traza.
    """
    global _phoenix_intentado
    inicio = time.perf_counter()
    estado: EstadoAgente = {"pregunta": pregunta}
    detalle: str | None = None
    try:
        if not _phoenix_intentado:
            _phoenix_intentado = True
            iniciar_phoenix()
        for estado in (grafo or _grafo_por_defecto()).stream({"pregunta": pregunta}, stream_mode="values"):
            pass
        resultado_sql = estado.get("resultado_sql")
        respuesta = RespuestaAgente(
            respuesta=estado["respuesta"],
            ruta=estado["ruta"],
            sql_ejecutado=resultado_sql.sql_ejecutado if resultado_sql is not None else None,
            fuentes_documentales=_fuentes_documentales(estado),
            idioma=estado["idioma"],
            duracion_ms=int((time.perf_counter() - inicio) * 1000),
            motivo_rechazo=estado.get("motivo_rechazo"),
            fuentes_usadas=estado["fuentes_usadas"],
        )
    except Exception as exc:
        detalle = f"{type(exc).__name__}: {exc}"
        idioma = estado.get("idioma", "es")
        respuesta = RespuestaAgente(
            respuesta=MENSAJES_FALLA[idioma],
            ruta=estado.get("ruta", "rechazar"),
            idioma=idioma,
            duracion_ms=int((time.perf_counter() - inicio) * 1000),
            fallo=True,
        )
    registrar_traza(estado, respuesta, error=detalle)
    return respuesta
