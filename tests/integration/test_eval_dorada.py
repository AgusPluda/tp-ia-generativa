"""Las consultas doradas de la batería devuelven los datos plantados (research R7). Requiere la base."""

import pytest

from eval.battery import cargar_bateria, ejecutar_dorada


def _doradas():
    return {
        p.id: [c.sql for c in p.chequeos if c.tipo == "contiene_valores_de_sql"]
        for p in cargar_bateria()
        if any(c.tipo == "contiene_valores_de_sql" for c in p.chequeos)
    }


@pytest.fixture(scope="module")
def resultados():
    from tests.integration.conftest import _conectar_o_saltear
    from gym_agent.db import connect_ro

    conn = _conectar_o_saltear(connect_ro)
    try:
        return {id_: [ejecutar_dorada(conn, sql) for sql in sqls] for id_, sqls in _doradas().items()}
    finally:
        conn.close()


def test_todas_las_doradas_devuelven_filas_sin_nulos(resultados):
    assert resultados
    for id_, listas in resultados.items():
        for filas in listas:
            assert filas, id_
            assert all(valor is not None for fila in filas for valor in fila), id_


@pytest.mark.parametrize(
    ("id_", "minimo", "maximo"),
    [
        ("S02", 1, 1),
        ("S03", 4, 6),
        ("H03", 4, 6),
        ("H01", 5, None),
        ("H02", 3, 4),
        ("H04", 1, None),
        ("S01", 5, 5),
        ("S06", 8, 8),
    ],
)
def test_cantidad_de_filas_segun_los_escenarios_plantados(resultados, id_, minimo, maximo):
    cantidad = len(resultados[id_][0])
    assert cantidad >= minimo
    if maximo is not None:
        assert cantidad <= maximo
