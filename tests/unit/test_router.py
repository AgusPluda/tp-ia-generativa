"""Router del grafo: modelo `DecisionRouter`, `nodo_router` y prompt (sin LLM)."""

import pytest
from pydantic import ValidationError

from gym_agent.graph.nodes import nodo_router
from gym_agent.graph.prompts import construir_prompt_router
from gym_agent.graph.state import DecisionRouter


@pytest.mark.parametrize(
    "datos",
    [
        {"ruta": "sql", "idioma": "es"},
        {"ruta": "rag", "idioma": "en"},
        {"ruta": "ambas", "idioma": "es"},
        {"ruta": "rechazar", "idioma": "en", "motivo_rechazo": "modificacion"},
    ],
)
def test_decision_valida(datos):
    assert DecisionRouter(**datos).ruta == datos["ruta"]


@pytest.mark.parametrize(
    "datos",
    [
        {"ruta": "rechazar", "idioma": "es"},
        {"ruta": "sql", "idioma": "es", "motivo_rechazo": "modificacion"},
        {"ruta": "sql", "idioma": "fr"},
    ],
)
def test_decision_invalida(datos):
    with pytest.raises(ValidationError):
        DecisionRouter(**datos)


def test_nodo_router_escribe_la_decision():
    llamadas = []

    def clasificar(pregunta):
        llamadas.append(pregunta)
        return DecisionRouter(ruta="rechazar", idioma="en", motivo_rechazo="fuera_de_dominio")

    estado = nodo_router(clasificar)({"pregunta": "Who won the world cup?"})
    assert llamadas == ["Who won the world cup?"]
    assert estado == {"ruta": "rechazar", "idioma": "en", "motivo_rechazo": "fuera_de_dominio"}


def test_nodo_router_ruta_sin_motivo():
    def clasificar(pregunta):
        return DecisionRouter(ruta="sql", idioma="es")

    assert nodo_router(clasificar)({"pregunta": "¿Cuántos socios hay?"})["motivo_rechazo"] is None


@pytest.mark.parametrize("pregunta", ["", "   ", "\n\t "])
def test_pregunta_vacia_no_llama_al_llm(pregunta):
    def clasificar(pregunta):
        raise AssertionError("no debe llamarse")

    estado = nodo_router(clasificar)({"pregunta": pregunta})
    assert estado == {"ruta": "rechazar", "idioma": "es", "motivo_rechazo": "falta_contexto"}


def test_el_nodo_no_atrapa_excepciones():
    def clasificar(pregunta):
        raise RuntimeError("falla del LLM")

    with pytest.raises(RuntimeError):
        nodo_router(clasificar)({"pregunta": "hola"})


def test_prompt_router_contenido():
    prompt = construir_prompt_router("¿Cuántos socios hay?")
    assert "¿Cuántos socios hay?" in prompt
    for ruta in ("sql", "rag", "ambas", "rechazar"):
        assert ruta in prompt
    for motivo in ("fuera_de_dominio", "modificacion", "falta_contexto"):
        assert motivo in prompt
    minus = prompt.lower()
    assert "no se rechazan" in minus
    for verbo in ("borrar", "eliminar", "actualizar", "insertar", "cambiar"):
        assert verbo in minus
    assert "sentencia sql" in minus
    assert "predominante" in minus
    assert "2026-09-30" in prompt
