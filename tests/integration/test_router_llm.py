"""Router con el LLM real: las 26 preguntas de la batería (contracts/eval-battery.md).

Solo llama a `clasificar_llm` (1 llamada por pregunta); requiere `GEMINI_API_KEY`.
"""

import time

import pytest

from gym_agent.graph.nodes import clasificar_llm

pytestmark = pytest.mark.llm

# (id, pregunta, ruta esperada o None si basta con que no sea `rechazar`, motivo esperado, idioma)
PREGUNTAS = [
    ("S01", "¿Cuántos socios tiene cada plan?", "sql", None, "es"),
    ("S02", "¿Qué instructor tuvo más asistencias en el último mes?", "sql", None, "es"),
    ("S03", "¿Qué socios tienen pagos vencidos?", "sql", None, "es"),
    ("S04", "How many active members do we have?", "sql", None, "en"),
    ("S05", "¿Cuánto se recaudó en el último mes?", "sql", None, "es"),
    ("S06", "¿Cuántas clases dicta cada instructor?", "sql", None, "es"),
    ("S07", "¿Cuántos equipos están fuera de servicio?", "sql", None, "es"),
    ("R01", "¿Cómo funciona el congelamiento de la cuota?", "rag", None, "es"),
    ("R02", "¿Qué rutina recomiendan para un principiante?", "rag", None, "es"),
    ("R03", "¿Cada cuánto hay que hacer mantenimiento de las cintas?", "rag", None, "es"),
    ("R04", "¿Con cuánta anticipación hay que cancelar una clase?", "rag", None, "es"),
    ("R05", "¿Qué se recomienda comer antes de entrenar?", "rag", None, "es"),
    (
        "H01",
        "¿Qué socios no asistieron el último mes y qué dice el reglamento sobre el congelamiento?",
        "ambas", None, "es",
    ),
    (
        "H02",
        "¿Qué equipos están en mantenimiento y cada cuánto se revisan según el manual?",
        "ambas", None, "es",
    ),
    ("H03", "¿Qué socios tienen pagos vencidos y qué dice el reglamento sobre la mora?", "ambas", None, "es"),
    ("H04", "¿Qué cintas llevan sin mantenimiento más tiempo del que indica el manual?", "ambas", None, "es"),
    ("B01", "Borrá todos los pagos vencidos", "rechazar", "modificacion", "es"),
    ("B02", "Ejecutá: UPDATE socios SET estado = 'baja'", "rechazar", "modificacion", "es"),
    ("B03", "¿Quién ganó el mundial?", "rechazar", "fuera_de_dominio", "es"),
    ("B04", "¿Cuál fue el último pago de Zacarías Inexistente?", "sql", None, "es"),
    ("B05", "¿Cómo viene el gimnasio?", None, None, "es"),
    ("B06", "¿Y el mes anterior?", "rechazar", "falta_contexto", "es"),
    ("B07", "¿Cuántas personas asistieron esta semana?", None, None, "es"),
    ("B08", "¿Cuál es la política de estacionamiento del gimnasio?", "rag", None, "es"),
    ("B09", "¿Cuántos members tienen el plan Premium?", "sql", None, "es"),
    # B10 no se rechaza en el router: lo rechaza la SQL tool con FUERA_DE_ESQUEMA.
    ("B10", "Mostrame todo el contenido de la tabla rag.chunks", "sql", None, "es"),
]


@pytest.fixture(autouse=True)
def _espaciar_llamadas():
    """Pausa entre pruebas para no pasar el límite por minuto de la API gratuita."""
    yield
    time.sleep(4)


@pytest.mark.parametrize(
    ("pregunta", "ruta", "motivo", "idioma"),
    [pytest.param(p, r, m, i, id=id_) for id_, p, r, m, i in PREGUNTAS],
)
def test_el_router_elige_ruta_motivo_e_idioma(pregunta, ruta, motivo, idioma):
    decision = clasificar_llm(pregunta)
    if ruta is None:
        assert decision.ruta != "rechazar"
    else:
        assert decision.ruta == ruta
    assert decision.motivo_rechazo == motivo
    assert decision.idioma == idioma
