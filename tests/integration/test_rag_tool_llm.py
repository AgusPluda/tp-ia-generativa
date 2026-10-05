"""RAG tool con embeddings reales de Gemini; requiere la clave y la ingesta hecha."""

import time

import pytest

from gym_agent.tools.rag_tool import buscar

pytestmark = pytest.mark.llm

REGLAMENTO = "Reglamento interno"
RUTINAS = "Guía de rutinas y nutrición"
EQUIPAMIENTO = "Manual de uso y mantenimiento del equipamiento"


@pytest.fixture(autouse=True)
def _espaciar_llamadas():
    """Evita el límite por minuto de la API gratuita."""
    yield
    time.sleep(1)


@pytest.mark.parametrize(
    ("pregunta", "documento"),
    [
        ("¿Cómo funciona el congelamiento de la cuota?", REGLAMENTO),
        ("¿Qué rutina me recomiendan si soy principiante?", RUTINAS),
        ("¿Cada cuánto se hace el mantenimiento de las cintas de correr?", EQUIPAMIENTO),
        ("¿Cómo se cancela una clase?", REGLAMENTO),
        ("¿Qué conviene comer antes de entrenar?", RUTINAS),
        ("¿Qué pasa si estoy en mora con la cuota?", REGLAMENTO),
    ],
)
def test_el_primer_fragmento_es_del_documento_esperado(pregunta, documento):
    r = buscar(pregunta)
    assert r.ok, r.error
    assert r.fragmentos, "no se devolvió ningún fragmento"
    assert r.fragmentos[0].documento == documento


def test_una_pregunta_fuera_de_dominio_no_devuelve_fragmentos():
    r = buscar("¿Quién ganó el mundial?")
    assert r.ok, r.error
    assert r.fragmentos == []


def test_limitacion_conocida_estacionamiento():
    """Documenta una limitación: el umbral NO filtra esta pregunta (research R9).

    El gimnasio no tiene política de estacionamiento en sus PDFs, pero la similitud con el
    Reglamento interno es ~0,69, por encima del umbral de 0,6. Decidir que esos fragmentos no
    responden la pregunta es trabajo de la síntesis (Etapa 2). Si este test falla porque el
    umbral cambió, hay que revisar esa decisión, no borrar el test.
    """
    r = buscar("¿Cuál es la política de estacionamiento del gimnasio?")
    assert r.ok, r.error
    assert r.fragmentos, "se esperaban fragmentos (similitud ~0,69)"
    assert {f.documento for f in r.fragmentos} == {REGLAMENTO}
