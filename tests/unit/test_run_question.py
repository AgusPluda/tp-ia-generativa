"""`run_question` con el grafo armado con funciones falsas (sin LLM ni base)."""

import json

import pytest

from gym_agent import observability
from gym_agent.graph import builder
from gym_agent.graph.builder import construir_grafo, run_question
from gym_agent.graph.state import DecisionRouter, RespuestaAgente, Sintesis
from gym_agent.tools import Fragmento, ResultadoRAG, ResultadoSQL

MENSAJE_ES = "En este momento no puedo responder. Probá de nuevo en unos minutos."
MENSAJE_EN = "I can't answer right now. Please try again in a few minutes."


@pytest.fixture(autouse=True)
def traza(tmp_path, monkeypatch):
    ruta = tmp_path / "traza.jsonl"
    monkeypatch.setattr(observability, "TRAZA_PATH", ruta)
    monkeypatch.setattr(builder, "iniciar_phoenix", lambda: False)
    monkeypatch.setattr(builder, "_phoenix_intentado", False)
    return ruta


def lineas(ruta):
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]


class Falsos:
    def __init__(self, decision, *, falla=None, citados=None):
        self.decision = decision
        self.falla = falla
        self.citados = citados if citados is not None else [1, 3, 1]
        self.llamadas: list[str] = []

    def clasificar(self, pregunta):
        self.llamadas.append("clasificar")
        return self.decision

    def consultar(self, pregunta, idioma):
        self.llamadas.append("consultar")
        if self.falla:
            raise self.falla
        return ResultadoSQL(ok=True, sql_ejecutado="SELECT 1", columnas=["n"], filas=[[1]])

    def buscar(self, pregunta):
        self.llamadas.append("buscar")
        paginas = [2, 2, 5]
        fragmentos = [
            Fragmento(documento="Reglamento interno", archivo="r.pdf", pagina=p, texto="t", similitud=0.7)
            for p in paginas
        ]
        return ResultadoRAG(ok=True, fragmentos=fragmentos)

    def sintetizar(self, prompt):
        self.llamadas.append("sintetizar")
        return Sintesis(respuesta="respuesta", fuentes_usadas=self.citados)

    def grafo(self):
        return construir_grafo(
            clasificar=self.clasificar, consultar=self.consultar,
            buscar=self.buscar, sintetizar=self.sintetizar,
        )


def test_devuelve_la_respuesta_con_su_origen():
    falsos = Falsos(DecisionRouter(ruta="ambas", idioma="es"), citados=[1, 2, 3])
    resultado = run_question("¿Cuántos socios y qué dice el reglamento?", grafo=falsos.grafo())
    assert isinstance(resultado, RespuestaAgente)
    assert resultado.respuesta == "respuesta"
    assert resultado.ruta == "ambas"
    assert resultado.idioma == "es"
    assert resultado.sql_ejecutado == "SELECT 1"
    assert resultado.fuentes_usadas == "ambas"
    assert resultado.motivo_rechazo is None
    assert resultado.duracion_ms >= 0


def test_fuentes_documentales_solo_citadas_y_sin_duplicados():
    falsos = Falsos(DecisionRouter(ruta="rag", idioma="es"), citados=[1, 2, 3])
    resultado = run_question("p", grafo=falsos.grafo())
    # los fragmentos 1 y 2 son del mismo documento y página
    assert [(f.documento, f.pagina) for f in resultado.fuentes_documentales] == [
        ("Reglamento interno", 2),
        ("Reglamento interno", 5),
    ]


def test_sin_citas_no_hay_fuentes_documentales():
    falsos = Falsos(DecisionRouter(ruta="rag", idioma="es"), citados=[])
    assert run_question("p", grafo=falsos.grafo()).fuentes_documentales == []


def test_rechazo_lleva_el_motivo():
    decision = DecisionRouter(ruta="rechazar", idioma="en", motivo_rechazo="modificacion")
    resultado = run_question("Delete all payments", grafo=Falsos(decision).grafo())
    assert resultado.ruta == "rechazar"
    assert resultado.motivo_rechazo == "modificacion"
    assert resultado.fuentes_usadas == "ninguna"
    assert resultado.sql_ejecutado is None


def test_un_nodo_que_lanza_no_filtra_la_excepcion(traza):
    falsos = Falsos(DecisionRouter(ruta="sql", idioma="es"), falla=RuntimeError("clave=secreta"))
    resultado = run_question("p", grafo=falsos.grafo())
    assert resultado.respuesta == MENSAJE_ES
    assert "secreta" not in resultado.respuesta
    (linea,) = lineas(traza)
    assert "clave=secreta" in linea["error"]


def test_cuota_agotada_devuelve_el_mensaje_generico():
    falla = RuntimeError("429 RESOURCE_EXHAUSTED GenerateRequestsPerDayPerProjectPerModel")
    falsos = Falsos(DecisionRouter(ruta="sql", idioma="es"), falla=falla)
    resultado = run_question("p", grafo=falsos.grafo())
    assert resultado.respuesta == MENSAJE_ES
    assert "429" not in resultado.respuesta


def test_toda_pregunta_deja_una_linea(traza):
    ok = Falsos(DecisionRouter(ruta="sql", idioma="es"))
    mal = Falsos(DecisionRouter(ruta="sql", idioma="es"), falla=RuntimeError("x"))
    run_question("una", grafo=ok.grafo())
    run_question("dos", grafo=mal.grafo())
    assert [linea["pregunta"] for linea in lineas(traza)] == ["una", "dos"]


def test_mensaje_generico_en_el_idioma_de_la_pregunta():
    falsos = Falsos(DecisionRouter(ruta="sql", idioma="en"), falla=RuntimeError("x"))
    resultado = run_question("How many members?", grafo=falsos.grafo())
    assert resultado.respuesta == MENSAJE_EN
    assert resultado.idioma == "en"


def test_mensaje_generico_en_castellano_si_el_router_falla():
    class RouterRoto(Falsos):
        def clasificar(self, pregunta):
            raise RuntimeError("sin router")

    resultado = run_question("How many members?", grafo=RouterRoto(DecisionRouter(ruta="sql", idioma="en")).grafo())
    assert resultado.respuesta == MENSAJE_ES
    assert resultado.idioma == "es"


def test_pregunta_vacia_es_falta_contexto_sin_llamar_a_nada():
    falsos = Falsos(DecisionRouter(ruta="sql", idioma="es"))
    resultado = run_question("   ", grafo=falsos.grafo())
    assert resultado.ruta == "rechazar"
    assert resultado.motivo_rechazo == "falta_contexto"
    assert falsos.llamadas == []


def test_inicia_phoenix_solo_la_primera_vez(monkeypatch):
    llamadas = []
    monkeypatch.setattr(builder, "iniciar_phoenix", lambda: llamadas.append(1) or False)
    falsos = Falsos(DecisionRouter(ruta="sql", idioma="es"))
    grafo = falsos.grafo()
    run_question("uno", grafo=grafo)
    run_question("dos", grafo=grafo)
    assert llamadas == [1]


def test_grafo_por_defecto_se_construye_una_vez(monkeypatch):
    construidos = []
    falsos = Falsos(DecisionRouter(ruta="sql", idioma="es"))
    monkeypatch.setattr(builder, "_grafo_por_defecto_cache", None)
    monkeypatch.setattr(builder, "construir_grafo", lambda: construidos.append(1) or falsos.grafo())
    run_question("uno")
    run_question("dos")
    assert construidos == [1]
