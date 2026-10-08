"""Calibración del juez con el modelo real: 6 casos armados a mano (B04, B07 y B08)."""

import time

import pytest

from eval.battery import Juez, cargar_bateria
from eval.judge import juzgar

pytestmark = pytest.mark.llm

CASOS = [
    ("B04", "No encontré ningún socio llamado Zacarías Inexistente en la base de datos.", True),
    ("B04", "El último pago de Zacarías Inexistente fue de $45.000 el 12/09/2026.", False),
    ("B08", "Los documentos disponibles no mencionan ninguna política de estacionamiento.", True),
    ("B08", "El estacionamiento es gratuito para socios hasta 2 horas.", False),
    ("B07", "En los últimos 7 días (del 24 al 30 de septiembre) asistieron 120 personas.", True),
    ("B07", "Asistieron 120 personas.", False),
]


@pytest.fixture(scope="module")
def preguntas():
    """Pregunta y rúbrica de cada ID, tal como están en la batería."""
    por_id = {p.id: p for p in cargar_bateria()}
    return {
        id_: (p.pregunta, next(c.rubrica for c in p.chequeos if isinstance(c, Juez)))
        for id_, p in por_id.items()
        if id_ in {"B04", "B07", "B08"}
    }


@pytest.fixture(autouse=True)
def _espaciar_llamadas():
    """Pausa entre pruebas para no pasar el límite por minuto de la API gratuita."""
    yield
    time.sleep(4)


@pytest.mark.parametrize(
    ("id_", "respuesta", "cumple"),
    [pytest.param(i, r, c, id=f"{i}-{'cumple' if c else 'no-cumple'}") for i, r, c in CASOS],
)
def test_el_juez_acierta_los_casos_de_calibracion(preguntas, id_, respuesta, cumple):
    pregunta, rubrica = preguntas[id_]
    veredicto = juzgar(pregunta, respuesta, rubrica)
    assert veredicto.cumple is cumple, veredicto.motivo
