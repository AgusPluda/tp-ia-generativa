"""Genera los datos sintéticos y los carga en el esquema `public`.

Uso: python scripts/generate_data.py

Vacía y vuelve a cargar las 7 tablas de negocio (es idempotente); no toca el esquema `rag`.
Imprime las filas y el hash md5 de cada tabla: dos ejecuciones deben mostrar los mismos hashes.
"""

from gym_agent.db import connect_admin
from gym_agent.synthetic import cargar_datos, generar_datos, hash_tablas


def main() -> None:
    datos = generar_datos()
    with connect_admin() as conn:
        cargar_datos(conn, datos)
        hashes = hash_tablas(conn)

    print(f"{'tabla':<14}{'filas':>7}  hash md5")
    for tabla, filas in datos.items():
        print(f"{tabla:<14}{len(filas):>7}  {hashes[tabla]}")


if __name__ == "__main__":
    main()
