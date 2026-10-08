"""Tests de la SQL tool sin base ni LLM: el generador y el ejecutor se inyectan como funciones falsas.

Contrato: specs/001-agente-sql-rag-gimnasio/contracts/sql-tool.md.
"""

import pytest

from gym_agent.tools.sql_prompt import IntentoPrevio, construir_prompt_sql
from gym_agent.tools.sql_tool import ErrorSQL, ResultadoSQL, consultar, sanear_error

VALIDA = "SELECT nombre FROM planes"

MENSAJES_DEL_CONTRATO = {
    "NO_ES_SELECT": "Solo puedo consultar información; no puedo modificar datos.",
    "FUERA_DE_ESQUEMA": "No puedo consultar esa información.",
    "INVALIDA": "No pude armar una consulta válida para esa pregunta.",
    "TIMEOUT": "La consulta tardó demasiado; probá con una pregunta más acotada.",
    "ERROR_EJECUCION": "No pude obtener los datos en este momento.",
}


# --- Dobles de prueba ---------------------------------------------------------


class GeneradorFalso:
    """Devuelve las respuestas en orden (una excepción se lanza) y registra cada llamado."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.llamados: list[IntentoPrevio | None] = []

    def __call__(self, pregunta, idioma, intento_previo=None):
        self.llamados.append(intento_previo)
        respuesta = self.respuestas[len(self.llamados) - 1]
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta


class EjecutorFalso:
    """Devuelve los resultados en orden (el último se repite) y registra las consultas recibidas."""

    def __init__(self, *resultados):
        self.resultados = list(resultados) or [_exito()]
        self.consultas: list[str] = []

    def __call__(self, sql):
        self.consultas.append(sql)
        return self.resultados[min(len(self.consultas), len(self.resultados)) - 1]


def _exito(filas=None):
    filas = [["Mensual"]] if filas is None else filas
    return ResultadoSQL(ok=True, columnas=["nombre"], filas=filas)


def _fallo(codigo, detalle="detalle técnico"):
    return ResultadoSQL(ok=False, error=ErrorSQL(codigo=codigo, mensaje="x", detalle=detalle))


# --- (a) a (g): el bucle de consultar -----------------------------------------


def test_a_consulta_valida_al_primer_intento():
    generador, ejecutor = GeneradorFalso(VALIDA + ";"), EjecutorFalso()
    resultado = consultar("¿Qué planes hay?", "es", generador=generador, ejecutor=ejecutor)
    assert resultado.ok
    assert resultado.intentos == 1
    assert resultado.sql_ejecutado == VALIDA
    assert ejecutor.consultas == [VALIDA]
    assert resultado.filas == [["Mensual"]]
    assert resultado.error is None


def test_b_reintenta_tras_una_consulta_invalida_y_pasa_el_error():
    generador, ejecutor = GeneradorFalso("SELECT now()", VALIDA), EjecutorFalso()
    resultado = consultar("¿Qué hora es?", "es", generador=generador, ejecutor=ejecutor)
    assert resultado.ok
    assert resultado.intentos == 2
    assert generador.llamados[0] is None
    previo = generador.llamados[1]
    assert previo.sql == "SELECT now()"
    assert "INVALIDA" in previo.error
    assert ejecutor.consultas == [VALIDA]  # la inválida nunca llegó a la base


def test_c_tres_consultas_invalidas_agotan_los_intentos():
    generador = GeneradorFalso("SELECT now()", "SELECT CURRENT_DATE", "hola", VALIDA)
    ejecutor = EjecutorFalso()
    resultado = consultar("¿Qué día es?", "es", generador=generador, ejecutor=ejecutor)
    assert not resultado.ok
    assert resultado.error.codigo == "INVALIDA"
    assert resultado.intentos == 3
    assert len(generador.llamados) == 3
    assert ejecutor.consultas == []


@pytest.mark.parametrize(
    ("sql", "codigo"),
    [("DELETE FROM pagos", "NO_ES_SELECT"), ("SELECT * FROM rag.chunks", "FUERA_DE_ESQUEMA")],
)
def test_d_escritura_o_esquema_ajeno_no_se_reintentan(sql, codigo):
    generador, ejecutor = GeneradorFalso(sql, VALIDA), EjecutorFalso()
    resultado = consultar("Borrá los pagos", "es", generador=generador, ejecutor=ejecutor)
    assert not resultado.ok
    assert resultado.error.codigo == codigo
    assert resultado.intentos == 1
    assert len(generador.llamados) == 1
    assert ejecutor.consultas == []


def test_d_la_base_rechaza_una_escritura_y_tampoco_se_reintenta():
    generador, ejecutor = GeneradorFalso(VALIDA, VALIDA), EjecutorFalso(_fallo("NO_ES_SELECT"))
    resultado = consultar("x", "es", generador=generador, ejecutor=ejecutor)
    assert resultado.error.codigo == "NO_ES_SELECT"
    assert resultado.intentos == 1


def test_e_timeout_y_luego_exito_se_reintenta():
    generador = GeneradorFalso(VALIDA, VALIDA)
    ejecutor = EjecutorFalso(_fallo("TIMEOUT", "canceling statement due to statement timeout"), _exito())
    resultado = consultar("x", "es", generador=generador, ejecutor=ejecutor)
    assert resultado.ok
    assert resultado.intentos == 2
    assert "TIMEOUT" in generador.llamados[1].error


def test_e_error_de_ejecucion_tres_veces():
    detalle = 'connection to server at "localhost" (127.0.0.1), port 5432: column "xyz" does not exist'
    generador = GeneradorFalso(VALIDA, VALIDA, VALIDA, VALIDA)
    ejecutor = EjecutorFalso(_fallo("ERROR_EJECUCION", detalle))
    resultado = consultar("x", "es", generador=generador, ejecutor=ejecutor)
    assert not resultado.ok
    assert resultado.error.codigo == "ERROR_EJECUCION"
    assert resultado.intentos == 3
    assert len(ejecutor.consultas) == 3
    # El error que vuelve al LLM está saneado pero conserva el motivo.
    for previo in generador.llamados[1:]:
        assert "localhost" not in previo.error
        assert "127.0.0.1" not in previo.error
        assert "5432" not in previo.error
        assert 'column "xyz" does not exist' in previo.error


def test_f_cero_filas_es_un_resultado_valido():
    resultado = consultar("x", "es", generador=GeneradorFalso(VALIDA), ejecutor=EjecutorFalso(_exito([])))
    assert resultado.ok
    assert resultado.filas == []
    assert resultado.truncado is False


def test_g_una_falla_del_llm_no_se_propaga():
    generador = GeneradorFalso(RuntimeError("503 UNAVAILABLE"))
    ejecutor = EjecutorFalso()
    resultado = consultar("x", "es", generador=generador, ejecutor=ejecutor)
    assert not resultado.ok
    assert resultado.error.codigo == "ERROR_EJECUCION"
    assert "503" in resultado.error.detalle
    assert ejecutor.consultas == []


def test_g_una_excepcion_del_ejecutor_no_se_propaga():
    def ejecutor_roto(sql):
        raise ValueError("inesperado")

    resultado = consultar("x", "es", generador=GeneradorFalso(VALIDA, VALIDA, VALIDA), ejecutor=ejecutor_roto)
    assert not resultado.ok
    assert resultado.error.codigo == "ERROR_EJECUCION"


# --- (h) Mensajes al usuario --------------------------------------------------

_CASOS_POR_CODIGO = {
    "NO_ES_SELECT": (GeneradorFalso("DROP TABLE socios"), EjecutorFalso()),
    "FUERA_DE_ESQUEMA": (GeneradorFalso("SELECT * FROM rag.chunks"), EjecutorFalso()),
    "INVALIDA": (GeneradorFalso("hola", "hola", "hola"), EjecutorFalso()),
    "TIMEOUT": (GeneradorFalso(VALIDA, VALIDA, VALIDA), EjecutorFalso(_fallo("TIMEOUT", "statement timeout"))),
    "ERROR_EJECUCION": (GeneradorFalso(VALIDA, VALIDA, VALIDA), EjecutorFalso(_fallo("ERROR_EJECUCION", "boom"))),
}


@pytest.mark.parametrize("codigo", list(_CASOS_POR_CODIGO))
def test_h_mensaje_del_contrato_sin_detalle(codigo):
    generador, ejecutor = _CASOS_POR_CODIGO[codigo]
    resultado = consultar("x", "es", generador=generador, ejecutor=ejecutor)
    assert resultado.error.codigo == codigo
    assert resultado.error.mensaje == MENSAJES_DEL_CONTRATO[codigo]
    assert resultado.error.detalle
    assert resultado.error.detalle not in resultado.error.mensaje


# --- (i) sanear_error ---------------------------------------------------------


def test_i_sanear_error_quita_host_usuario_puerto_rutas_y_claves(monkeypatch):
    monkeypatch.setenv("AGENTE_RO_PASSWORD", "clave-ro-falsa")
    monkeypatch.setenv("POSTGRES_PASSWORD", "clave-admin-falsa")
    texto = (
        'connection to server at "localhost" (127.0.0.1), port 5432 failed: '
        'FATAL: password authentication failed for user "agente_ro" | '
        "también ::1 y gym_admin con clave-ro-falsa y clave-admin-falsa | "
        r"archivo E:\REPOSITORIOS\tp-ia-generativa\src\gym_agent\db.py | "
        "datos en /var/lib/postgresql/data/base | "
        'ERROR: column "xyz" does not exist'
    )
    saneado = sanear_error(texto)
    for secreto in [
        "localhost", "127.0.0.1", "::1", "5432", "agente_ro", "gym_admin",
        "clave-ro-falsa", "clave-admin-falsa", "REPOSITORIOS", "/var/lib",
    ]:  # fmt: skip
        assert secreto not in saneado, secreto
    assert 'column "xyz" does not exist' in saneado


def test_i_sanear_error_conserva_un_error_sin_datos_sensibles():
    texto = 'syntax error at or near "FORM"\nLINE 1: SELECT * FORM socios'
    assert sanear_error(texto) == texto


# --- (j) construir_prompt_sql -------------------------------------------------

ESQUEMA_FALSO = "socios(id_socio integer PK, nombre varchar)\nclases(id_clase integer PK, dia_semana varchar)"


def test_j_prompt_con_esquema_pregunta_y_reglas_de_fecha():
    prompt = construir_prompt_sql(ESQUEMA_FALSO, "¿Cuántos socios activos hay?", "es")
    assert ESQUEMA_FALSO in prompt
    assert "¿Cuántos socios activos hay?" in prompt
    assert "2026-09-30" in prompt
    assert "2026-09-01" in prompt
    assert "miercoles" in prompt and "sabado" in prompt
    assert "tildes" in prompt
    assert "CURRENT_DATE" in prompt and "now()" in prompt
    assert "Consulta anterior" not in prompt


def test_j_prompt_con_las_reglas_de_la_primera_corrida_de_evaluacion():
    # research R17: H01 (faltas), B10 (tabla fuera del esquema), H04 (umbral del manual) y B09 (estado).
    prompt = construir_prompt_sql(ESQUEMA_FALSO, "¿Qué socios no asistieron el último mes?", "es")
    assert "presente = false" in prompt and "NOT EXISTS" in prompt and "UNION" in prompt
    assert "SELECT * FROM rag.chunks" in prompt and "SELECT 1 WHERE false" in prompt
    assert "ignorala" in prompt and "no inventes ese valor" in prompt
    assert "cualquiera sea su estado" in prompt


def test_j_prompt_de_reintento_incluye_la_consulta_y_el_error():
    previo = IntentoPrevio(sql="SELECT now()", error="INVALIDA: usa la fecha real: now()")
    prompt = construir_prompt_sql(ESQUEMA_FALSO, "How many members?", "en", previo)
    assert "SELECT now()" in prompt
    assert "INVALIDA: usa la fecha real: now()" in prompt
    assert "How many members?" in prompt
