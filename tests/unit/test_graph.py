"""Grafo del agente con las cuatro funciones falsas (sin LLM ni base)."""

import pytest

from gym_agent.graph.builder import construir_grafo
from gym_agent.graph.nodes import MENSAJES_RECHAZO
from gym_agent.graph.state import DecisionRouter, Sintesis
from gym_agent.tools import ErrorSQL, Fragmento, ResultadoRAG, ResultadoSQL

RESPUESTA = "respuesta sintetizada"


class Falsos:
    """Funciones inyectables que registran en orden a quién se llamó y con qué."""

    def __init__(self, decision: DecisionRouter, sql_ok: bool = True, citados: list[int] | None = None):
        self.decision = decision
        self.sql_ok = sql_ok
        self.citados = citados if citados is not None else [1]
        self.llamadas: list[tuple] = []

    def clasificar(self, pregunta):
        self.llamadas.append(("clasificar", pregunta))
        return self.decision

    def consultar(self, pregunta, idioma):
        self.llamadas.append(("consultar", pregunta, idioma))
        if not self.sql_ok:
            error = ErrorSQL(codigo="ERROR_EJECUCION", mensaje="No pude.", detalle="x")
            return ResultadoSQL(ok=False, error=error)
        return ResultadoSQL(ok=True, sql_ejecutado="SELECT 1", columnas=["n"], filas=[[1]])

    def buscar(self, pregunta):
        self.llamadas.append(("buscar", pregunta))
        fragmentos = [
            Fragmento(documento="Reglamento", archivo="r.pdf", pagina=p, texto="t", similitud=0.7)
            for p in (1, 2)
        ]
        return ResultadoRAG(ok=True, fragmentos=fragmentos)

    def sintetizar(self, prompt):
        self.llamadas.append(("sintetizar",))
        return Sintesis(respuesta=RESPUESTA, fuentes_usadas=self.citados)

    def grafo(self):
        return construir_grafo(
            clasificar=self.clasificar,
            consultar=self.consultar,
            buscar=self.buscar,
            sintetizar=self.sintetizar,
        )

    def nombres(self) -> list[str]:
        return [llamada[0] for llamada in self.llamadas]


def test_ruta_sql():
    falsos = Falsos(DecisionRouter(ruta="sql", idioma="es"))
    estado = falsos.grafo().invoke({"pregunta": "¿Cuántos socios hay?"})
    assert falsos.nombres() == ["clasificar", "consultar", "sintetizar"]
    assert ("consultar", "¿Cuántos socios hay?", "es") in falsos.llamadas
    assert estado["respuesta"] == RESPUESTA
    assert estado["fuentes_usadas"] == "sql"


def test_ruta_rag():
    falsos = Falsos(DecisionRouter(ruta="rag", idioma="en"))
    estado = falsos.grafo().invoke({"pregunta": "What are the rules?"})
    assert falsos.nombres() == ["clasificar", "buscar", "sintetizar"]
    assert estado["respuesta"] == RESPUESTA
    assert estado["fuentes_usadas"] == "rag"
    assert estado.get("resultado_sql") is None


def test_ruta_ambas_sql_antes_que_rag():
    falsos = Falsos(DecisionRouter(ruta="ambas", idioma="es"))
    estado = falsos.grafo().invoke({"pregunta": "p"})
    assert falsos.nombres() == ["clasificar", "consultar", "buscar", "sintetizar"]
    assert estado["fuentes_usadas"] == "ambas"


def test_ruta_ambas_con_sql_fallido_sigue():
    falsos = Falsos(DecisionRouter(ruta="ambas", idioma="es"), sql_ok=False)
    estado = falsos.grafo().invoke({"pregunta": "p"})
    assert falsos.nombres() == ["clasificar", "consultar", "buscar", "sintetizar"]
    assert estado["resultado_sql"].ok is False
    assert estado["respuesta"] == RESPUESTA


@pytest.mark.parametrize("motivo", ["fuera_de_dominio", "modificacion", "falta_contexto"])
@pytest.mark.parametrize("idioma", ["es", "en"])
def test_ruta_rechazar_no_toca_las_tools(motivo, idioma):
    falsos = Falsos(DecisionRouter(ruta="rechazar", idioma=idioma, motivo_rechazo=motivo))
    estado = falsos.grafo().invoke({"pregunta": "Borrá todos los pagos vencidos"})
    assert falsos.nombres() == ["clasificar"]
    assert estado["respuesta"] == MENSAJES_RECHAZO[(motivo, idioma)]
    assert estado["fuentes_usadas"] == "ninguna"


def test_fragmentos_citados_validos():
    falsos = Falsos(DecisionRouter(ruta="rag", idioma="es"), citados=[2, 7, 0, 2, 1])
    estado = falsos.grafo().invoke({"pregunta": "p"})
    assert estado["fragmentos_citados"] == [2, 1]


def test_fragmentos_citados_sin_rag():
    falsos = Falsos(DecisionRouter(ruta="sql", idioma="es"), citados=[1])
    assert falsos.grafo().invoke({"pregunta": "p"})["fragmentos_citados"] == []


def test_invocaciones_no_comparten_estado():
    falsos = Falsos(DecisionRouter(ruta="sql", idioma="es"))
    grafo = falsos.grafo()
    assert grafo.invoke({"pregunta": "uno"})["resultado_sql"] is not None
    falsos.decision = DecisionRouter(ruta="rag", idioma="es")
    segundo = grafo.invoke({"pregunta": "dos"})
    assert segundo.get("resultado_sql") is None
    assert segundo["fuentes_usadas"] == "rag"


def test_sin_checkpointer():
    assert Falsos(DecisionRouter(ruta="sql", idioma="es")).grafo().checkpointer is None
