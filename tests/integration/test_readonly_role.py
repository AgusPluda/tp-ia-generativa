"""CE-003: el rol `agente_ro` solo puede leer, y sus consultas tienen un límite de tiempo.

Requiere solo la base de T010 (no depende de que haya datos cargados).
"""

import time

import pytest
from psycopg import errors

from gym_agent.config import STATEMENT_TIMEOUT_S

ESCRITURAS = [
    "INSERT INTO planes (nombre, precio_mensual, clases_por_semana) VALUES ('Prueba', 1, 1)",
    "UPDATE socios SET estado = 'baja'",
    "DELETE FROM pagos",
    "DROP TABLE equipamiento",
]
RECHAZOS = (errors.ReadOnlySqlTransaction, errors.InsufficientPrivilege)


def test_select_sobre_public_funciona(conn_ro):
    (cantidad,) = conn_ro.execute("SELECT count(*) FROM planes").fetchone()
    assert cantidad >= 0


def test_la_sesion_es_de_solo_lectura(conn_ro):
    (valor,) = conn_ro.execute("SHOW default_transaction_read_only").fetchone()
    assert valor == "on"


@pytest.mark.parametrize("sentencia", ESCRITURAS)
def test_escritura_rechazada(conn_ro, sentencia):
    with pytest.raises(RECHAZOS):
        conn_ro.execute(sentencia)
    conn_ro.rollback()


@pytest.mark.parametrize("sentencia", ESCRITURAS)
def test_escritura_rechazada_aunque_se_desactive_el_solo_lectura(conn_ro, sentencia):
    """Defensa en profundidad: sin el modo de solo lectura, faltan igual los permisos."""
    conn_ro.execute("SET default_transaction_read_only = off")
    conn_ro.commit()
    with pytest.raises(errors.InsufficientPrivilege):
        conn_ro.execute(sentencia)
    conn_ro.rollback()


def test_consulta_larga_cortada_por_statement_timeout(conn_ro):
    inicio = time.monotonic()
    with pytest.raises(errors.QueryCanceled):
        conn_ro.execute("SELECT pg_sleep(10)")
    conn_ro.rollback()
    assert time.monotonic() - inicio < STATEMENT_TIMEOUT_S + 2
