"""Validador de las consultas que genera el LLM (primera capa de seguridad de la SQL tool).

Analiza el texto con `sqlglot` (dialecto `postgres`) sin tocar la base. Una consulta se
rechaza con `SQLNoPermitido` según estas reglas, en este orden:

1. Texto vacío, que no se puede parsear o que no es una consulta → `INVALIDA`.
2. Más de un statement → `NO_ES_SELECT` si alguno no es `SELECT`; si no, `INVALIDA`.
3. La raíz no es `SELECT` (se admiten `WITH ... SELECT`, `UNION`/`INTERSECT`/`EXCEPT` y un
   `SELECT` entre paréntesis), o en cualquier parte del árbol hay escritura o DDL (incluido un
   `DELETE` dentro de un CTE), `SELECT ... INTO` o `FOR UPDATE`/`FOR SHARE` → `NO_ES_SELECT`.
4. Se referencia el esquema `rag`, `pg_catalog` o `information_schema` (sin distinguir
   mayúsculas ni comillas), o una tabla `pg_*` sin calificar (`pg_catalog` está en el
   `search_path`) → `FUERA_DE_ESQUEMA`.
5. Se usa el reloj real o una función del servidor → `INVALIDA`:
   - funciones de reloj (`now`, `current_date`, `current_timestamp`, `current_time`,
     `localtime`, `localtimestamp`, `clock_timestamp`, `statement_timestamp`,
     `transaction_timestamp`, `timeofday`) y `age` con un solo argumento (resta desde hoy);
   - literales de texto que son exactamente `now`, `today`, `tomorrow` o `yesterday`
     (Postgres los convierte a fecha con el reloj real);
   - funciones `pg_*`, `lo_*`, `dblink*`, `set_config`, `current_setting`, `nextval`,
     `setval` y las `*_to_xml*` (ejecutan SQL escrito dentro de un string).

Límite conocido: un texto armado en tiempo de ejecución (`('to' || 'day')::date`) no se
detecta. No es un riesgo de seguridad (la base sigue en solo lectura), solo de exactitud.
"""

from typing import Literal

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

CodigoRechazo = Literal["NO_ES_SELECT", "FUERA_DE_ESQUEMA", "INVALIDA"]


class SQLNoPermitido(Exception):
    """La consulta no pasó la validación.

    Attributes:
        codigo: `NO_ES_SELECT`, `FUERA_DE_ESQUEMA` o `INVALIDA` (contrato de la SQL tool).
        detalle: texto técnico del motivo; va a la traza, nunca al usuario.
    """

    def __init__(self, codigo: CodigoRechazo, detalle: str) -> None:
        super().__init__(f"{codigo}: {detalle}")
        self.codigo = codigo
        self.detalle = detalle


# Raíces permitidas: SELECT, UNION/INTERSECT/EXCEPT y un SELECT entre paréntesis.
_RAICES_DE_CONSULTA = (exp.Select, exp.SetOperation, exp.Subquery)

# Nodos que escriben, cambian el esquema o la sesión, o bloquean filas. `Command` es lo que
# devuelve sqlglot para lo que no sabe parsear (CALL, DO, EXPLAIN, LOCK, PREPARE...).
_NODOS_PROHIBIDOS = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge,
    exp.Create, exp.Drop, exp.Alter, exp.TruncateTable, exp.Comment,
    exp.Grant, exp.Revoke, exp.Copy, exp.Set, exp.Command,
    exp.Transaction, exp.Commit, exp.Rollback, exp.Analyze,
    exp.Into, exp.Lock,
)  # fmt: skip

_ESQUEMAS_PROHIBIDOS = {"rag", "pg_catalog", "information_schema"}

# Funciones que sqlglot reconoce como nodos propios (no como `Anonymous`).
_NODOS_DE_RELOJ = (
    exp.CurrentDate, exp.CurrentTime, exp.CurrentTimestamp, exp.CurrentDatetime,
    exp.CurrentTimestampLTZ, exp.Localtime, exp.Localtimestamp,
)  # fmt: skip

_FUNCIONES_DE_RELOJ = {
    "now", "current_date", "current_time", "current_timestamp", "localtime", "localtimestamp",
    "clock_timestamp", "statement_timestamp", "transaction_timestamp", "timeofday",
}  # fmt: skip
_FUNCIONES_PROHIBIDAS = {"set_config", "current_setting", "nextval", "setval"}
_PREFIJOS_PROHIBIDOS = ("pg_", "lo_", "dblink")

_LITERALES_DE_RELOJ = {"now", "today", "tomorrow", "yesterday"}

# Strings: comunes, E'...' (ByteString en sqlglot), $$...$$ y U&'...'.
_NODOS_DE_TEXTO = (exp.RawString, exp.ByteString, exp.UnicodeString)


def validar(sql: str) -> str:
    """Valida que `sql` sea un único `SELECT` de solo lectura sobre el esquema `public`.

    Args:
        sql: la consulta generada por el LLM.

    Returns:
        La consulta tal como llegó, sin espacios sobrantes ni `;` final (no la regenerada
        por sqlglot, para mostrar en la UI lo que escribió el LLM).

    Raises:
        SQLNoPermitido: si viola alguna de las reglas del docstring del módulo.
    """
    texto = (sql or "").strip()
    while texto.endswith(";"):
        texto = texto[:-1].rstrip()
    if not texto:
        raise SQLNoPermitido("INVALIDA", "la consulta está vacía")

    statements = _parsear(texto)
    _validar_raiz(statements)
    arbol = statements[0]
    _validar_solo_lectura(arbol)
    _validar_esquemas(arbol)
    _validar_funciones_y_literales(arbol)
    return texto


def _parsear(texto: str) -> list[exp.Expression]:
    """Parsea `texto` y devuelve los statements reales (sin vacíos ni `;` sueltos)."""
    try:
        parseados = sqlglot.parse(texto, read="postgres")
    except SqlglotError as e:
        raise SQLNoPermitido("INVALIDA", f"no se pudo parsear: {e}") from e
    except Exception as e:  # sqlglot puede fallar con errores internos ante entradas raras
        raise SQLNoPermitido("INVALIDA", f"error al parsear: {type(e).__name__}: {e}") from e
    # `SELECT 1; -- x` deja un nodo `Semicolon` con el comentario; `SELECT 1;;` deja un None.
    return [s for s in parseados if s is not None and not isinstance(s, exp.Semicolon)]


def _es_consulta(nodo: exp.Expression) -> bool:
    return isinstance(nodo, _RAICES_DE_CONSULTA)


def _validar_raiz(statements: list[exp.Expression]) -> None:
    """Exige un único statement cuya raíz sea una consulta."""
    if not statements:
        raise SQLNoPermitido("INVALIDA", "no hay ninguna consulta")
    if len(statements) > 1:
        tipos = ", ".join(type(s).__name__ for s in statements)
        if any(not _es_consulta(s) for s in statements):
            raise SQLNoPermitido("NO_ES_SELECT", f"varios statements con escritura: {tipos}")
        raise SQLNoPermitido("INVALIDA", f"se esperaba un único SELECT y hay {len(statements)}")
    raiz = statements[0]
    if _es_consulta(raiz):
        return
    if isinstance(raiz, _NODOS_PROHIBIDOS) or not isinstance(raiz, (exp.Condition, exp.Alias)):
        raise SQLNoPermitido("NO_ES_SELECT", f"la sentencia es {type(raiz).__name__}, no SELECT")
    # Texto suelto como "hola" se parsea como una columna o un alias: no es SQL.
    raise SQLNoPermitido("INVALIDA", f"no es una consulta SQL ({type(raiz).__name__})")


def _validar_solo_lectura(arbol: exp.Expression) -> None:
    """Rechaza escritura, DDL, `SELECT ... INTO` y bloqueos en cualquier parte del árbol."""
    for nodo in arbol.walk():
        if isinstance(nodo, _NODOS_PROHIBIDOS):
            raise SQLNoPermitido("NO_ES_SELECT", f"contiene {type(nodo).__name__}: {nodo.sql()[:80]}")


def _validar_esquemas(arbol: exp.Expression) -> None:
    """Rechaza referencias a `rag`, al catálogo del sistema o a tablas `pg_*`."""
    for nodo in arbol.walk():
        calificadores: list[str] = []
        if isinstance(nodo, (exp.Table, exp.Column)):
            calificadores = [nodo.args.get("db"), nodo.args.get("catalog")]
            calificadores = [c.name for c in calificadores if isinstance(c, exp.Identifier)]
        elif isinstance(nodo, exp.Dot) and isinstance(nodo.this, exp.Identifier):
            calificadores = [nodo.this.name]  # esquema.funcion(...)
        prohibidos = {c.lower() for c in calificadores} & _ESQUEMAS_PROHIBIDOS
        if prohibidos:
            raise SQLNoPermitido("FUERA_DE_ESQUEMA", f"usa el esquema {sorted(prohibidos)[0]}")
        if isinstance(nodo, exp.Table) and isinstance(nodo.this, exp.Identifier):
            if nodo.name.lower().startswith("pg_"):
                raise SQLNoPermitido("FUERA_DE_ESQUEMA", f"usa la tabla del sistema {nodo.name}")


def _nombre_de_funcion(nodo: exp.Func) -> str:
    """Nombre en minúsculas de una función, sea `Anonymous` (desconocida) o un nodo propio."""
    if isinstance(nodo, exp.Anonymous):
        return nodo.name.lower()
    return nodo.sql_name().lower()


def _validar_funciones_y_literales(arbol: exp.Expression) -> None:
    """Rechaza el reloj real (funciones y literales) y las funciones del servidor."""
    for nodo in arbol.walk():
        if isinstance(nodo, _NODOS_DE_RELOJ):
            raise SQLNoPermitido("INVALIDA", f"usa la fecha real: {nodo.sql()}")
        if isinstance(nodo, exp.Func):
            nombre = _nombre_de_funcion(nodo)
            if nombre in _FUNCIONES_DE_RELOJ:
                raise SQLNoPermitido("INVALIDA", f"usa la fecha real: {nombre}()")
            if nombre == "age" and len(nodo.expressions) == 1:
                raise SQLNoPermitido("INVALIDA", "age() con un argumento usa la fecha real")
            if (
                nombre in _FUNCIONES_PROHIBIDAS
                or nombre.startswith(_PREFIJOS_PROHIBIDOS)
                or "_to_xml" in nombre
            ):
                raise SQLNoPermitido("INVALIDA", f"usa una función no permitida: {nombre}()")
        es_texto = (isinstance(nodo, exp.Literal) and nodo.is_string) or isinstance(nodo, _NODOS_DE_TEXTO)
        if es_texto and isinstance(nodo.this, str) and nodo.this.strip().lower() in _LITERALES_DE_RELOJ:
            raise SQLNoPermitido("INVALIDA", f"usa el literal de fecha real '{nodo.this}'")
