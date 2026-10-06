"""Nodos del grafo del agente (contrato `agent-graph.md`).

Los nodos que dependen de un LLM o de una tool reciben esa función por parámetro para poder
probarlos sin red ni base.
"""

from collections.abc import Callable

from gym_agent.graph.prompts import construir_prompt_router, construir_prompt_sintesis
from gym_agent.graph.state import DecisionRouter, EstadoAgente, Idioma, MotivoRechazo, Sintesis
from gym_agent.llm import invocar_chat
from gym_agent.tools import ResultadoRAG, ResultadoSQL

MENSAJES_RECHAZO: dict[tuple[MotivoRechazo, Idioma], str] = {
    ("modificacion", "es"): "Solo puedo consultar información; no puedo modificar datos.",
    ("modificacion", "en"): "I can only look up information; I cannot modify data.",
    ("fuera_de_dominio", "es"): (
        "Solo puedo responder preguntas sobre el gimnasio: socios, pagos, clases, equipamiento "
        "y sus reglamentos y guías."
    ),
    ("fuera_de_dominio", "en"): (
        "I can only answer questions about the gym: members, payments, classes, equipment "
        "and their rules and guides."
    ),
    ("falta_contexto", "es"): (
        "Cada pregunta se responde por separado: formulala completa, sin depender de una anterior."
    ),
    ("falta_contexto", "en"): (
        "Each question is answered on its own: please ask it in complete form, "
        "without relying on a previous one."
    ),
}
"""Respuestas fijas de rechazo por (motivo, idioma); no usan LLM."""


def clasificar_llm(pregunta: str) -> DecisionRouter:
    """Clasifica la pregunta con el LLM (salida estructurada).

    Raises:
        ValueError: si el modelo no devuelve una decisión.
    """
    decision = invocar_chat(
        lambda modelo: modelo.with_structured_output(DecisionRouter),
        construir_prompt_router(pregunta),
    )
    if decision is None:
        raise ValueError("El router no devolvió una decisión")
    return decision


def nodo_router(clasificar: Callable[[str], DecisionRouter]) -> Callable[[EstadoAgente], EstadoAgente]:
    """Nodo `router`: escribe `ruta`, `idioma` y `motivo_rechazo`.

    Una pregunta vacía se rechaza sin llamar a `clasificar`. Si `clasificar` falla, la excepción
    sube: la atrapa `run_question`.
    """

    def nodo(estado: EstadoAgente) -> EstadoAgente:
        pregunta = estado.get("pregunta", "")
        if not pregunta.strip():
            return {"ruta": "rechazar", "idioma": "es", "motivo_rechazo": "falta_contexto"}
        decision = clasificar(pregunta)
        return {
            "ruta": decision.ruta,
            "idioma": decision.idioma,
            "motivo_rechazo": decision.motivo_rechazo,
        }

    return nodo


def nodo_rechazar(estado: EstadoAgente) -> EstadoAgente:
    """Nodo `rechazar`: responde con la plantilla del motivo en el idioma de la pregunta."""
    motivo = estado.get("motivo_rechazo") or "fuera_de_dominio"
    idioma = estado.get("idioma", "es")
    return {
        "respuesta": MENSAJES_RECHAZO[(motivo, idioma)],
        "fuentes_usadas": "ninguna",
        "fragmentos_citados": [],
    }


def nodo_sql(consultar: Callable[[str, str], ResultadoSQL]) -> Callable[[EstadoAgente], EstadoAgente]:
    """Nodo `sql`: ejecuta la SQL tool, que nunca lanza; los fallos viajan en `resultado_sql.error`."""

    def nodo(estado: EstadoAgente) -> EstadoAgente:
        return {"resultado_sql": consultar(estado["pregunta"], estado["idioma"])}

    return nodo


def nodo_rag(buscar: Callable[[str], ResultadoRAG]) -> Callable[[EstadoAgente], EstadoAgente]:
    """Nodo `rag`: ejecuta la RAG tool y guarda `resultado_rag`."""

    def nodo(estado: EstadoAgente) -> EstadoAgente:
        return {"resultado_rag": buscar(estado["pregunta"])}

    return nodo


def sintetizar_llm(prompt: str) -> Sintesis:
    """Redacta la respuesta con el LLM (salida estructurada).

    Raises:
        ValueError: si el modelo no devuelve una síntesis.
    """
    sintesis = invocar_chat(lambda modelo: modelo.with_structured_output(Sintesis), prompt)
    if sintesis is None:
        raise ValueError("La síntesis no devolvió una respuesta")
    return sintesis


def nodo_sintetizar(sintetizar: Callable[[str], Sintesis]) -> Callable[[EstadoAgente], EstadoAgente]:
    """Nodo `sintetizar`: responde solo con lo que trajeron las tools.

    `fuentes_usadas` sale de lo que se ejecutó, no de lo que diga el LLM. De los números de
    fragmento que cita la síntesis se quedan los que existen, sin repetir y en su orden.
    """

    def nodo(estado: EstadoAgente) -> EstadoAgente:
        resultado_sql = estado.get("resultado_sql")
        resultado_rag = estado.get("resultado_rag")
        prompt = construir_prompt_sintesis(
            estado["pregunta"], estado.get("idioma", "es"), resultado_sql, resultado_rag
        )
        sintesis = sintetizar(prompt)

        cantidad = len(resultado_rag.fragmentos) if resultado_rag is not None else 0
        citados = list(dict.fromkeys(n for n in sintesis.fuentes_usadas if 1 <= n <= cantidad))

        if resultado_sql is not None and resultado_rag is not None:
            fuentes = "ambas"
        elif resultado_sql is not None:
            fuentes = "sql"
        elif resultado_rag is not None:
            fuentes = "rag"
        else:
            fuentes = "ninguna"
        return {"respuesta": sintesis.respuesta, "fuentes_usadas": fuentes, "fragmentos_citados": citados}

    return nodo
