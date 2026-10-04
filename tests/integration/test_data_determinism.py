"""CE-007: dos cargas de los datos sintéticos dejan las tablas de `public` idénticas.

El esquema `rag` queda fuera (su `fecha_ingesta` usa `now()`).
"""

from gym_agent.synthetic import cargar_datos, generar_datos, hash_tablas
from gym_agent.synthetic.data import COLUMNAS


def test_dos_cargas_producen_el_mismo_hash_por_tabla(conn_admin):
    cargar_datos(conn_admin, generar_datos())
    primero = hash_tablas(conn_admin)

    cargar_datos(conn_admin, generar_datos())
    segundo = hash_tablas(conn_admin)

    assert set(primero) == set(COLUMNAS)
    assert primero == segundo
