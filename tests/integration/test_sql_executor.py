"""Ejecución de la SQL tool contra la base real (sin LLM ni validador).

Requiere la base levantada y cargada (`generate_data.py`). `conn_admin` se usa solo para el
hash de control de las tablas.
"""

import json
import time

import pytest

from gym_agent.config import MAX_FILAS, STATEMENT_TIMEOUT_S
from gym_agent.synthetic import hash_tablas
from gym_agent.tools.sql_prompt import describir_esquema
from gym_agent.tools.sql_tool import ejecutar_sql

ESCRITURAS = [
    "DELETE FROM pagos",
    "UPDATE socios SET estado = 'baja'",
    "DROP TABLE socios",
    "INSERT INTO planes (nombre, precio_mensual, clases_por_semana) VALUES ('Prueba', 1, 1)",
]

TABLAS = ["planes", "socios", "instructores", "clases", "asistencias", "pagos", "equipamiento"]


@pytest.fixture(autouse=True)
def _base_disponible(conn_ro):
    """Saltea el módulo si la base no está levantada (el fixture `conn_ro` lo resuelve)."""


def test_devuelve_todas_las_filas_si_son_pocas():
    resultado = ejecutar_sql("SELECT * FROM planes")
    assert resultado.ok, resultado.error
    assert len(resultado.filas) == 5
    assert resultado.truncado is False
    assert "nombre" in resultado.columnas
    assert resultado.sql_ejecutado == "SELECT * FROM planes"


def test_corta_en_max_filas_y_marca_truncado():
    resultado = ejecutar_sql("SELECT * FROM asistencias")
    assert resultado.ok, resultado.error
    assert len(resultado.filas) == MAX_FILAS
    assert resultado.truncado is True
    assert resultado.columnas[0] == "id_asistencia"


def test_los_valores_se_pueden_serializar_a_json():
    resultado = ejecutar_sql(
        "SELECT s.fecha_alta, p.precio_mensual, p.nombre, a.presente, a.fecha::timestamp AS momento "
        "FROM socios s JOIN planes p USING (id_plan) JOIN asistencias a USING (id_socio) LIMIT 3"
    )
    assert resultado.ok, resultado.error
    json.dumps(resultado.filas)
    fecha, precio, _, presente, momento = resultado.filas[0]
    assert isinstance(fecha, str) and len(fecha) == 10  # ISO: 2026-04-01
    assert isinstance(precio, (int, float))
    assert isinstance(presente, bool)
    assert isinstance(momento, str)


def test_un_ilike_con_porcentaje_no_se_confunde_con_un_parametro():
    resultado = ejecutar_sql("SELECT count(*) FROM socios WHERE apellido ILIKE '%ez%'")
    assert resultado.ok, resultado.error


def test_consulta_larga_cortada_por_timeout():
    inicio = time.monotonic()
    resultado = ejecutar_sql("SELECT count(*) FROM generate_series(1, 100000000000)")
    assert not resultado.ok
    assert resultado.error.codigo == "TIMEOUT"
    assert time.monotonic() - inicio < STATEMENT_TIMEOUT_S + 5


@pytest.mark.parametrize("sentencia", ESCRITURAS)
def test_la_base_rechaza_escrituras_sin_pasar_por_el_validador(conn_admin, sentencia):
    """CE-003, defensa en profundidad: aun sin validador, la base no se modifica."""
    antes = hash_tablas(conn_admin)
    resultado = ejecutar_sql(sentencia)
    assert not resultado.ok
    assert resultado.error.codigo == "NO_ES_SELECT"
    assert hash_tablas(conn_admin) == antes


def test_error_de_la_base_va_en_detalle_y_no_en_mensaje():
    resultado = ejecutar_sql("SELECT columna_inexistente FROM socios")
    assert not resultado.ok
    assert resultado.error.codigo == "ERROR_EJECUCION"
    assert "columna_inexistente" in resultado.error.detalle
    assert "columna_inexistente" not in resultado.error.mensaje


def test_describir_esquema_incluye_solo_public():
    esquema = describir_esquema()
    for tabla in TABLAS:
        assert f"{tabla}(" in esquema, tabla
    assert "fecha_nacimiento" in esquema
    assert "dia_semana" in esquema
    assert "id_plan integer -> planes.id_plan" in esquema
    assert "id_clase integer -> clases.id_clase" in esquema
    assert "id_socio integer PK" in esquema
    for prohibido in ["rag", "chunks", "embedding"]:
        assert prohibido not in esquema.lower(), prohibido
