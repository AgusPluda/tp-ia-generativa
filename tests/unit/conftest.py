"""Fixtures de los tests unitarios: los datos sintéticos generados en memoria, sin base."""

import pytest

from gym_agent.synthetic import generar_datos
from gym_agent.synthetic.data import CLAVE_PRIMARIA, COLUMNAS


@pytest.fixture(scope="session")
def datos() -> dict[str, list[tuple]]:
    """Salida cruda de `generar_datos()`: tabla → filas (tuplas sin la clave primaria)."""
    return generar_datos()


@pytest.fixture(scope="session")
def tablas(datos) -> dict[str, list[dict]]:
    """Las mismas filas como diccionarios, con la clave primaria que asignará el `SERIAL`.

    La carga inserta en orden fijo sobre tablas vacías (`RESTART IDENTITY`), así que la fila
    `i` (desde 1) recibe el id `i`.
    """
    return {
        tabla: [
            {CLAVE_PRIMARIA[tabla]: i, **dict(zip(COLUMNAS[tabla], fila, strict=True))}
            for i, fila in enumerate(filas, start=1)
        ]
        for tabla, filas in datos.items()
    }
