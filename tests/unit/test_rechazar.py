"""Nodo `rechazar`: plantillas fijas por motivo e idioma, sin LLM ni fuentes."""

import pytest

from gym_agent.graph.nodes import MENSAJES_RECHAZO, nodo_rechazar

CLAVES = {
    ("modificacion", "es"): "consultar",
    ("modificacion", "en"): "only",
    ("fuera_de_dominio", "es"): "gimnasio",
    ("fuera_de_dominio", "en"): "gym",
    ("falta_contexto", "es"): "completa",
    ("falta_contexto", "en"): "complete",
}


@pytest.mark.parametrize(("motivo", "idioma"), list(CLAVES))
def test_rechazo_por_motivo_e_idioma(motivo, idioma):
    estado = nodo_rechazar({"pregunta": "x", "idioma": idioma, "motivo_rechazo": motivo})
    assert CLAVES[(motivo, idioma)] in estado["respuesta"]
    assert estado.get("resultado_sql") is None
    assert estado.get("resultado_rag") is None


def test_las_seis_respuestas_son_distintas():
    assert len(set(MENSAJES_RECHAZO.values())) == 6
    assert set(MENSAJES_RECHAZO) == set(CLAVES)
