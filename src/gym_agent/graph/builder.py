"""Armado del grafo del agente (contrato `agent-graph.md`, diagrama).

`router` elige la ruta; `ambas` entra por `sql` y sigue por `rag`, de modo que la SQL tool
corre antes que la RAG tool. `rechazar` no toca ninguna tool. Sin checkpointer: cada invocación
parte de un estado vacío (RF-017).
"""

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
from gym_agent.graph.state import DecisionRouter, EstadoAgente, Sintesis
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
