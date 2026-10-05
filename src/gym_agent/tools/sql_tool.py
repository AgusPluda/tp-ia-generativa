"""SQL tool: traduce una pregunta a un único `SELECT`, lo valida y lo ejecuta en solo lectura.

Contrato: specs/001-agente-sql-rag-gimnasio/contracts/sql-tool.md. Pipeline de `consultar`:

1. **Generar** la consulta con el LLM (`generar_sql_llm`).
2. **Validar** con `sql_validator.validar` (sin tocar la base).
3. **Ejecutar** con `agente_ro` (`ejecutar_sql`): transacción de solo lectura, timeout de
   `STATEMENT_TIMEOUT_S` y como máximo `MAX_FILAS` filas.
4. **Recuperar**: ante `INVALIDA`, `TIMEOUT` o `ERROR_EJECUCION` se vuelve a generar, hasta
   `MAX_INTENTOS_SQL` consultas, pasándole al LLM la consulta anterior y el error saneado.
   `NO_ES_SELECT` y `FUERA_DE_ESQUEMA` no se reintentan: otra oportunidad no aporta nada.

`consultar` nunca lanza excepciones: los fallos viajan en `ResultadoSQL.error`. El `detalle`
técnico va solo a la traza; al usuario le llega `mensaje`.
"""

import math
import os
import re
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Literal

import psycopg
from psycopg import errors
from pydantic import BaseModel

from gym_agent.config import MAX_FILAS, MAX_INTENTOS_SQL, STATEMENT_TIMEOUT_S
from gym_agent.db import connect_ro
from gym_agent.llm import invocar_chat
from gym_agent.tools.sql_prompt import IntentoPrevio, construir_prompt_sql, describir_esquema
from gym_agent.tools.sql_validator import SQLNoPermitido, validar

CodigoErrorSQL = Literal["NO_ES_SELECT", "FUERA_DE_ESQUEMA", "INVALIDA", "TIMEOUT", "ERROR_EJECUCION"]

MENSAJES: dict[str, str] = {
    "NO_ES_SELECT": "Solo puedo consultar información; no puedo modificar datos.",
    "FUERA_DE_ESQUEMA": "No puedo consultar esa información.",
    "INVALIDA": "No pude armar una consulta válida para esa pregunta.",
    "TIMEOUT": "La consulta tardó demasiado; probá con una pregunta más acotada.",
    "ERROR_EJECUCION": "No pude obtener los datos en este momento.",
}
"""Mensaje para el usuario de cada código de error (tabla de errores del contrato)."""

_NO_REINTENTABLES = {"NO_ES_SELECT", "FUERA_DE_ESQUEMA"}


class ErrorSQL(BaseModel):
    """Por qué falló la SQL tool."""

    codigo: CodigoErrorSQL
    mensaje: str
    """Texto para el usuario, sin detalles internos."""
    detalle: str
    """Texto técnico (de la base, del validador o del LLM); solo para la traza."""


class ResultadoSQL(BaseModel):
    """Salida de la SQL tool (contrato `ResultadoSQL`)."""

    ok: bool
    sql_ejecutado: str | None = None
    columnas: list[str] = []
    filas: list[list[Any]] = []
    """Hasta `MAX_FILAS` filas, con valores serializables a JSON."""
    truncado: bool = False
    intentos: int = 0
    """Cantidad de consultas que generó el LLM (0 si falló antes de generar la primera)."""
    error: ErrorSQL | None = None


def _error(codigo: CodigoErrorSQL, detalle: str) -> ErrorSQL:
    return ErrorSQL(codigo=codigo, mensaje=MENSAJES[codigo], detalle=detalle)


# --- Saneo de errores -------------------------------------------------------

_HOSTS = re.compile(r"\blocalhost\b|\b\d{1,3}(?:\.\d{1,3}){3}\b|(?<![\w:])::1\b", re.IGNORECASE)
_PUERTOS = re.compile(r"(\bport\s*=?\s*)\"?\d{2,5}\"?|(?<=<host>):\d{2,5}\b", re.IGNORECASE)
_RUTAS_WINDOWS = re.compile(r"\b[A-Za-z]:\\[^\s\"']*")
_RUTAS_LINUX = re.compile(r"(?<![\w./<])/(?:[\w.-]+/)+[\w.-]*")


def sanear_error(texto: str) -> str:
    """Quita del texto de un error los datos de la infraestructura antes de pasarlo al LLM.

    Reemplaza las contraseñas de `.env`, los usuarios de la base, hosts, puertos y rutas de
    archivos, pero conserva el motivo útil (por ejemplo `column "xyz" does not exist`).
    """
    for variable in ("AGENTE_RO_PASSWORD", "POSTGRES_PASSWORD"):
        if valor := os.getenv(variable):
            texto = texto.replace(valor, "<clave>")
    usuarios = {"agente_ro", "gym_admin", os.getenv("POSTGRES_USER", "")} - {""}
    for usuario in sorted(usuarios, key=len, reverse=True):
        texto = re.sub(rf"\b{re.escape(usuario)}\b", "<usuario>", texto)
    if host := os.getenv("POSTGRES_HOST"):
        texto = texto.replace(host, "<host>")
    texto = _HOSTS.sub("<host>", texto)
    texto = _PUERTOS.sub(lambda m: f"{m.group(1)}<puerto>" if m.group(1) else ":<puerto>", texto)
    texto = _RUTAS_WINDOWS.sub("<ruta>", texto)
    return _RUTAS_LINUX.sub("<ruta>", texto)


# --- Parte 1: ejecución (sin LLM) -------------------------------------------


def _a_json(valor: Any) -> Any:
    """Convierte un valor de psycopg en algo que `json.dumps` acepta."""
    if valor is None or isinstance(valor, (bool, int, str)):
        return valor
    if isinstance(valor, float):
        return valor if math.isfinite(valor) else str(valor)
    if isinstance(valor, Decimal):  # `numeric`: entero si no tiene decimales (count, sum de int)
        if not valor.is_finite():
            return str(valor)
        return int(valor) if valor.as_tuple().exponent >= 0 else float(valor)
    if isinstance(valor, (date, datetime, time)):  # datetime es subclase de date
        return valor.isoformat()
    if isinstance(valor, (list, tuple)):
        return [_a_json(v) for v in valor]
    if isinstance(valor, timedelta):
        return str(valor)
    return str(valor)


def ejecutar_sql(sql: str) -> ResultadoSQL:
    """Ejecuta `sql` como `agente_ro` en una transacción de solo lectura y devuelve las filas.

    No valida la consulta (eso es de `sql_validator`): si llega una escritura, la rechaza la
    base. Nunca lanza excepciones; la conexión se cierra siempre (sin commit).

    Errores: `QueryCanceled` → `TIMEOUT`; `ReadOnlySqlTransaction` o `InsufficientPrivilege`
    → `NO_ES_SELECT`; cualquier otro error de la base o de conexión → `ERROR_EJECUCION`.
    """
    conn: psycopg.Connection | None = None
    try:
        conn = connect_ro()
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT_S}s'")
            cur.execute(sql)  # sin parámetros: psycopg no interpreta los `%` de un ILIKE
            if cur.description is None:
                return ResultadoSQL(ok=True, sql_ejecutado=sql)
            columnas = [c.name for c in cur.description]
            filas = cur.fetchmany(MAX_FILAS + 1)
        return ResultadoSQL(
            ok=True,
            sql_ejecutado=sql,
            columnas=columnas,
            filas=[[_a_json(v) for v in fila] for fila in filas[:MAX_FILAS]],
            truncado=len(filas) > MAX_FILAS,
        )
    except errors.QueryCanceled as e:
        return ResultadoSQL(ok=False, sql_ejecutado=sql, error=_error("TIMEOUT", str(e)))
    except (errors.ReadOnlySqlTransaction, errors.InsufficientPrivilege) as e:
        return ResultadoSQL(ok=False, sql_ejecutado=sql, error=_error("NO_ES_SELECT", str(e)))
    except (psycopg.Error, RuntimeError) as e:
        return ResultadoSQL(ok=False, sql_ejecutado=sql, error=_error("ERROR_EJECUCION", str(e)))
    finally:
        if conn is not None:
            conn.close()


# --- Parte 2: generación con el LLM y bucle de reintentos -------------------


class ConsultaSQL(BaseModel):
    """Salida estructurada del LLM."""

    sql: str
    """Una única consulta SELECT de PostgreSQL."""


def generar_sql_llm(pregunta: str, idioma: str, intento_previo: IntentoPrevio | None = None) -> str:
    """Pide al LLM la consulta para `pregunta` (con el error anterior si es un reintento).

    Raises:
        Cualquier error de la API o de la base al leer el esquema; `consultar` los atrapa.
    """
    prompt = construir_prompt_sql(describir_esquema(), pregunta, idioma, intento_previo)
    respuesta = invocar_chat(lambda modelo: modelo.with_structured_output(ConsultaSQL), prompt)
    if respuesta is None:
        raise ValueError("el LLM no devolvió una consulta con el formato pedido")
    return respuesta.sql


Generador = Callable[[str, str, IntentoPrevio | None], str]
Ejecutor = Callable[[str], ResultadoSQL]


def consultar(
    pregunta: str,
    idioma: str,
    *,
    generador: Generador = generar_sql_llm,
    ejecutor: Ejecutor = ejecutar_sql,
) -> ResultadoSQL:
    """Responde `pregunta` con datos de la base: generar → validar → ejecutar, con reintentos.

    Args:
        pregunta: la pregunta del usuario, tal como llegó.
        idioma: `"es"` o `"en"` (lo determina el router).
        generador: produce la consulta; por defecto el LLM. Los tests pasan uno falso.
        ejecutor: corre la consulta validada; por defecto `ejecutar_sql`.

    Returns:
        Un `ResultadoSQL`; nunca lanza excepciones. `intentos` cuenta las consultas generadas.
    """
    intento_previo: IntentoPrevio | None = None
    ultimo: ResultadoSQL | None = None
    for intento in range(1, MAX_INTENTOS_SQL + 1):
        try:
            sql = generador(pregunta, idioma, intento_previo)
        except Exception as e:
            detalle = f"falló la generación de SQL: {type(e).__name__}: {e}"
            return ResultadoSQL(ok=False, intentos=intento - 1, error=_error("ERROR_EJECUCION", detalle))

        try:
            sql_valido = validar(sql)
        except SQLNoPermitido as e:
            ultimo = ResultadoSQL(ok=False, intentos=intento, error=_error(e.codigo, f"{e.detalle} | sql: {sql}"))
            if e.codigo in _NO_REINTENTABLES:
                return ultimo
            intento_previo = IntentoPrevio(sql=sql, error=sanear_error(f"{e.codigo}: {e.detalle}"))
            continue

        try:
            resultado = ejecutor(sql_valido)
        except Exception as e:
            resultado = ResultadoSQL(
                ok=False, sql_ejecutado=sql_valido, error=_error("ERROR_EJECUCION", f"{type(e).__name__}: {e}")
            )
        error = resultado.error
        if not resultado.ok:  # el mensaje al usuario sale siempre de MENSAJES
            error = _error(error.codigo, error.detalle) if error else _error("ERROR_EJECUCION", "falla sin detalle")
        ultimo = resultado.model_copy(update={"intentos": intento, "sql_ejecutado": sql_valido, "error": error})
        if ultimo.ok or error.codigo in _NO_REINTENTABLES:
            return ultimo
        intento_previo = IntentoPrevio(sql=sql_valido, error=sanear_error(f"{error.codigo}: {error.detalle}"))

    return ultimo
