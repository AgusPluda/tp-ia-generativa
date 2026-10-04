"""Carga de los datos sintéticos en el esquema `public` y hash de su contenido (CE-007).

Se usa solo con la conexión de administrador (`connect_admin()`). No toca el esquema `rag`.
"""

import psycopg
from psycopg import sql

from gym_agent.synthetic.data import CLAVE_PRIMARIA, COLUMNAS


def cargar_datos(conn: psycopg.Connection, datos: dict[str, list[tuple]]) -> None:
    """Vacía las 7 tablas de `public` y carga `datos`, todo en una sola transacción.

    `TRUNCATE ... RESTART IDENTITY` reinicia los `SERIAL`, así que los ids quedan iguales a
    los que asumió `generar_datos()`. Si algo falla, se deshace todo.

    Args:
        conn: conexión como administrador.
        datos: salida de `generar_datos()`.
    """
    tablas = list(COLUMNAS)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("TRUNCATE {} RESTART IDENTITY CASCADE").format(
                    sql.SQL(", ").join(map(sql.Identifier, tablas))
                )
            )
            for tabla in tablas:
                columnas = COLUMNAS[tabla]
                insert = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                    sql.Identifier(tabla),
                    sql.SQL(", ").join(map(sql.Identifier, columnas)),
                    sql.SQL(", ").join([sql.Placeholder()] * len(columnas)),
                )
                cur.executemany(insert, datos[tabla])
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def hash_tablas(conn: psycopg.Connection) -> dict[str, str]:
    """md5 del contenido de cada tabla de `public`, con las filas ordenadas por clave primaria.

    Dos bases con los mismos datos dan los mismos hashes; sirve para CE-007 y, en la
    evaluación, para comprobar que una pregunta no modificó la base.

    Returns:
        Tabla → hash md5 en hexadecimal.
    """
    hashes = {}
    with conn.cursor() as cur:
        for tabla, clave in CLAVE_PRIMARIA.items():
            cur.execute(
                sql.SQL(
                    "SELECT md5(coalesce(string_agg(t::text, E'\\n' ORDER BY t.{}), '')) FROM {} AS t"
                ).format(sql.Identifier(clave), sql.Identifier(tabla))
            )
            hashes[tabla] = cur.fetchone()[0]
    conn.rollback()  # cierra la transacción de solo lectura que abrió el SELECT
    return hashes
