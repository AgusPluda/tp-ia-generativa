"""Fixtures de los tests de integración: requieren la base levantada (`docker compose up -d`)."""

import pytest

from gym_agent.db import connect_admin, connect_ro


def _conectar_o_saltear(conectar):
    try:
        return conectar()
    except RuntimeError as e:
        pytest.skip(f"Base no disponible: {e}")


@pytest.fixture
def conn_admin():
    """Conexión como administrador; se cierra al terminar el test."""
    conn = _conectar_o_saltear(connect_admin)
    yield conn
    conn.close()


@pytest.fixture
def conn_ro():
    """Conexión como `agente_ro`; se cierra al terminar el test."""
    conn = _conectar_o_saltear(connect_ro)
    yield conn
    conn.close()
