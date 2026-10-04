"""Conexiones a Postgres.

Hay dos usuarios con roles bien separados (principio II):

- `connect_admin()`: el propietario del esquema (`POSTGRES_USER`). Solo para el setup:
  carga de datos sintéticos e ingesta de PDFs.
- `connect_ro()`: el rol `agente_ro`, de solo lectura y con `statement_timeout = 5s`
  configurados en la base (`db/init/02_roles.sh`). Es la única conexión que usa el agente.

La base se alcanza en `localhost:${POSTGRES_PORT}` (el puerto que publica Docker Compose).
"""

import os

import psycopg

from gym_agent.config import require_env


def _conectar(usuario: str, password: str) -> psycopg.Connection:
    """Abre una conexión a la base del proyecto con el usuario indicado."""
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    dbname = require_env("POSTGRES_DB")
    try:
        return psycopg.connect(host=host, port=port, dbname=dbname, user=usuario, password=password)
    except psycopg.OperationalError as e:
        raise RuntimeError(
            f"No se pudo conectar a {dbname} en {host}:{port} como {usuario}. "
            "¿Está levantada la base (docker compose up -d) y coinciden las claves de .env? "
            f"Detalle: {e}"
        ) from e


def connect_admin() -> psycopg.Connection:
    """Conexión como administrador (`POSTGRES_USER`). Usar solo en scripts de setup."""
    return _conectar(require_env("POSTGRES_USER"), require_env("POSTGRES_PASSWORD"))


def connect_ro() -> psycopg.Connection:
    """Conexión como `agente_ro` (solo lectura). Es la que usan la SQL tool y la RAG tool."""
    return _conectar("agente_ro", require_env("AGENTE_RO_PASSWORD"))
