"""App de Streamlit con `AppTest` y un `run_question` falso (sin LLM ni base)."""

import pytest
from streamlit.testing.v1 import AppTest

from gym_agent.config import REPO_ROOT
from gym_agent.graph.state import FuenteDocumental, RespuestaAgente
from gym_agent.presentacion import EJEMPLOS, secciones_bateria, url_phoenix

APP = str(REPO_ROOT / "app" / "streamlit_app.py")
GENERICO = "En este momento no puedo responder. Probá de nuevo en unos minutos."


def armar(ruta="sql", *, texto="respuesta", sql=None, fuentes=(), fallo=False, motivo=None):
    return RespuestaAgente(
        respuesta=texto, ruta=ruta, sql_ejecutado=sql, idioma="es", duracion_ms=1234,
        fuentes_documentales=[FuenteDocumental(documento=d, pagina=p) for d, p in fuentes],
        fallo=fallo, motivo_rechazo=motivo,
    )


class Falso:
    """Reemplaza a `run_question`: registra las preguntas y devuelve lo configurado."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.llamadas: list[str] = []

    def __call__(self, pregunta):
        self.llamadas.append(pregunta)
        siguiente = self.respuestas[min(len(self.llamadas), len(self.respuestas)) - 1]
        if isinstance(siguiente, Exception):
            raise siguiente
        return siguiente


@pytest.fixture
def correr(monkeypatch):
    """Parchea `run_question` y devuelve la app ya iniciada junto con el falso."""

    def _correr(*respuestas):
        falso = Falso(*respuestas)
        monkeypatch.setattr("gym_agent.graph.run_question", falso)
        return AppTest.from_file(APP, default_timeout=10).run(), falso

    return _correr


def preguntar(at, texto):
    at.text_input(key="pregunta").set_value(texto)
    at.button(key="preguntar").click().run()
    return at


def textos(at):
    """Todo el texto visible de la página, incluidas las etiquetas de los desplegables."""
    elementos = [*at.title, *at.markdown, *at.caption, *at.code, *at.error, *at.warning,
                 *at.info, *at.success, *at.text, *at.exception]
    return [str(e.value) for e in elementos] + [e.label for e in at.expander]


def captions(at):
    return [c.value for c in at.caption]


def desplegables(at):
    return [e.label for e in at.expander]


def test_primer_render_sin_respuesta(correr):
    at, falso = correr(armar())
    assert not at.exception
    assert at.title[0].value == "🏋️ Gym AI Agent"
    assert at.text_input(key="pregunta").value == ""
    assert at.button(key="preguntar") is not None
    for i, ejemplo in enumerate(EJEMPLOS):
        boton = at.button(key=f"ejemplo_{i}")
        assert boton.label == ejemplo.etiqueta
        assert boton.help == ejemplo.pregunta
    assert not at.error and not at.warning
    assert not at.expander
    assert not any(c.startswith("Fuente:") for c in captions(at))
    assert falso.llamadas == []


def test_ruta_sql_muestra_la_consulta(correr):
    sql = "SELECT plan, COUNT(*) FROM socios GROUP BY plan"
    at, falso = correr(armar("sql", texto="Hay 3 planes", sql=sql))
    preguntar(at, "¿Cuántos socios tiene cada plan?")
    assert not at.exception
    assert falso.llamadas == ["¿Cuántos socios tiene cada plan?"]
    assert any("Hay 3 planes" in m.value for m in at.markdown)
    assert "Fuente: Base de datos" in captions(at)
    assert desplegables(at) == ["Consulta SQL ejecutada"]
    (codigo,) = at.expander[0].code
    assert codigo.language == "sql"
    assert codigo.value == sql


def test_ruta_rag_lista_los_documentos(correr):
    fuentes = [("Reglamento interno", 3), ("Manual de equipos", 7)]
    at, _ = correr(armar("rag", fuentes=fuentes))
    preguntar(at, "p")
    assert "Fuente: Documentos" in captions(at)
    assert desplegables(at) == ["Documentos citados"]
    texto = " ".join(m.value for m in at.expander[0].markdown)
    assert "Reglamento interno, p. 3" in texto
    assert "Manual de equipos, p. 7" in texto


def test_ruta_ambas_muestra_los_dos_desplegables(correr):
    at, _ = correr(armar("ambas", sql="SELECT 1", fuentes=[("Manual de equipos", 2)]))
    preguntar(at, "p")
    assert "Fuente: Ambas" in captions(at)
    assert sorted(desplegables(at)) == ["Consulta SQL ejecutada", "Documentos citados"]


def test_rag_sin_citas_no_muestra_desplegables(correr):
    at, _ = correr(armar("rag", fuentes=[]))
    preguntar(at, "p")
    assert "Fuente: Documentos" in captions(at)
    assert not at.expander


def test_rechazo(correr):
    at, _ = correr(armar("rechazar", texto="No puedo modificar datos", motivo="modificacion"))
    preguntar(at, "Borrá los pagos")
    assert "Fuente: Rechazada" in captions(at)
    assert not at.expander
    assert not at.error


def test_fallo_se_muestra_como_error(correr):
    at, _ = correr(armar("rechazar", texto=GENERICO, fallo=True))
    preguntar(at, "p")
    assert "Fuente: No disponible" in captions(at)
    assert [e.value for e in at.error] == [GENERICO]
    assert not at.expander


def test_excepcion_de_run_question_no_filtra_nada(correr):
    at, _ = correr(RuntimeError("password=secreta"))
    preguntar(at, "p")
    assert not at.exception
    assert [e.value for e in at.error] == [GENERICO]
    assert not any("secreta" in t for t in textos(at))
    assert not any("RuntimeError" in t for t in textos(at))


def test_pregunta_en_blanco_no_llama_a_run_question(correr):
    at, falso = correr(armar())
    preguntar(at, "   ")
    assert [w.value for w in at.warning] == ["Escribí una pregunta."]
    assert falso.llamadas == []
    assert not any(c.startswith("Fuente:") for c in captions(at))


def test_ejemplo_rellena_el_campo_sin_enviar(correr):
    at, falso = correr(armar())
    at.button(key="ejemplo_0").click().run()
    assert at.text_input(key="pregunta").value == EJEMPLOS[0].pregunta
    assert falso.llamadas == []
    assert not any(c.startswith("Fuente:") for c in captions(at))


def test_pagina_de_preguntas_evaluativas(correr):
    at, falso = correr(armar())
    at.switch_page("paginas/preguntas.py").run()
    assert not at.exception
    assert [s.value for s in at.subheader] == [s.titulo for s in secciones_bateria()]
    visible = " ".join(m.value for m in at.markdown)
    ids = [p.id for s in secciones_bateria() for p in s.preguntas]
    assert len(ids) == 26
    assert all(f"| {id_} |" in visible for id_ in ids)
    assert "Chequeo principal" in visible
    assert not at.button  # sin botón "Probar en el chat"
    assert falso.llamadas == []


def test_barra_lateral_con_link_a_phoenix(correr):
    at, _ = correr(armar())
    assert not at.exception
    sidebar = " ".join(str(e.value) for e in at.sidebar.caption)
    assert "docker compose --profile observability up -d" in sidebar
    # AppTest no siempre expone link_button; la URL queda cubierta por url_phoenix().
    enlaces = at.sidebar.get("link_button")
    if enlaces:
        assert enlaces[0].proto.url == url_phoenix()
        assert enlaces[0].proto.label == "Observabilidad en Phoenix"


def test_pesos_se_renderizan_escapados(correr):
    at, _ = correr(armar("sql", texto="La cuota es de $15.000 y $20.000"))
    preguntar(at, "p")
    cuerpo = next(m.value for m in at.markdown if "cuota" in m.value)
    assert cuerpo == r"La cuota es de \$15.000 y \$20.000"


def test_sin_historial_entre_preguntas(correr):
    at, falso = correr(armar("sql", texto="primera respuesta"), armar("sql", texto="segunda respuesta"))
    preguntar(at, "uno")
    preguntar(at, "dos")
    assert falso.llamadas == ["uno", "dos"]
    visible = " ".join(m.value for m in at.markdown)
    assert "segunda respuesta" in visible
    assert "primera respuesta" not in visible
    assert sum(c.startswith("Fuente:") for c in captions(at)) == 1
