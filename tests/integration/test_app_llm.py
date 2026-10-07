"""App de Streamlit con el LLM y la base reales (`AppTest`, sin parchear `run_question`).

Pruebas de humo de lo que ve la persona (CE-006); la batería completa es de la Etapa 4.
Requiere `GEMINI_API_KEY`, la base levantada, los datos cargados y la ingesta hecha.
"""

import time

import pytest
from streamlit.testing.v1 import AppTest

from gym_agent import observability
from gym_agent.config import REPO_ROOT
from gym_agent.synthetic.loader import hash_tablas

pytestmark = pytest.mark.llm

APP = str(REPO_ROOT / "app" / "streamlit_app.py")
PROHIBIDOS = ("Traceback", "psycopg", "Exception")


@pytest.fixture(autouse=True)
def _aislar_traza(tmp_path, monkeypatch):
    """La traza de estas pruebas no se mezcla con `logs/traza.jsonl`."""
    monkeypatch.setattr(observability, "TRAZA_PATH", tmp_path / "traza.jsonl")
    yield
    time.sleep(4)


def preguntar(texto):
    at = AppTest.from_file(APP, default_timeout=90).run()
    at.text_input(key="pregunta").set_value(texto)
    at.button(key="preguntar").click().run()
    assert not at.exception
    return at


def captions(at):
    return [c.value for c in at.caption]


def desplegables(at):
    return [e.label for e in at.expander]


def sin_mensajes_tecnicos(at):
    elementos = [*at.title, *at.markdown, *at.caption, *at.code, *at.error, *at.warning,
                 *at.info, *at.text, *at.exception]
    visibles = [str(e.value) for e in elementos] + desplegables(at)
    for texto in visibles:
        for prohibido in PROHIBIDOS:
            assert prohibido not in texto, texto


def test_s01_muestra_la_consulta_sql():
    at = preguntar("¿Cuántos socios tiene cada plan?")
    assert "Fuente: Base de datos" in captions(at)
    assert desplegables(at) == ["Consulta SQL ejecutada"]
    (codigo,) = at.expander[0].code
    assert codigo.value.lstrip().upper().startswith(("SELECT", "WITH"))
    sin_mensajes_tecnicos(at)


def test_r01_muestra_los_documentos_citados():
    at = preguntar("¿Cómo funciona el congelamiento de la cuota?")
    assert "Fuente: Documentos" in captions(at)
    assert "Documentos citados" in desplegables(at)
    assert "Consulta SQL ejecutada" not in desplegables(at)
    citados = " ".join(m.value for e in at.expander for m in e.markdown)
    assert "Reglamento interno" in citados
    sin_mensajes_tecnicos(at)


def test_h02_muestra_las_dos_fuentes():
    at = preguntar("¿Qué equipos están en mantenimiento y cada cuánto se revisan según el manual?")
    assert "Fuente: Ambas" in captions(at)
    assert sorted(desplegables(at)) == ["Consulta SQL ejecutada", "Documentos citados"]
    sin_mensajes_tecnicos(at)


def test_b01_rechaza_sin_tocar_la_base(conn_admin):
    antes = hash_tablas(conn_admin)
    at = preguntar("Borrá todos los pagos vencidos")
    assert "Fuente: Rechazada" in captions(at)
    assert not at.expander
    assert hash_tablas(conn_admin) == antes
    sin_mensajes_tecnicos(at)


def test_b03_fuera_de_dominio_es_rechazada():
    at = preguntar("¿Quién ganó el mundial?")
    assert "Fuente: Rechazada" in captions(at)
    assert not at.expander
    sin_mensajes_tecnicos(at)


def test_s04_responde_en_ingles():
    at = preguntar("How many active members do we have?")
    assert any("member" in m.value.lower() for m in at.markdown)
    sin_mensajes_tecnicos(at)
