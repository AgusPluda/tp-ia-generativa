"""Lo que ve el LLM para escribir SQL: el esquema de `public`, el glosario de negocio y las reglas.

- `describir_esquema()` lee el esquema de la base con `agente_ro`, solo para `public` (el
  esquema `rag` nunca se muestra).
- `GLOSARIO` traduce las expresiones del negocio a SQL (data-model.md, "Definiciones de
  negocio"). Las fechas van como literales calculados desde `REFERENCE_DATE`: el LLM nunca
  usa el reloj real.
- `construir_prompt_sql(...)` arma el pedido completo, incluido el error del intento anterior
  cuando se reintenta.
"""

from datetime import timedelta
from functools import cache
from typing import NamedTuple

from gym_agent.config import REFERENCE_DATE
from gym_agent.db import connect_ro

INICIO_ULTIMO_MES = REFERENCE_DATE - timedelta(days=29)
"""Primer día del "último mes": 30 días corridos hasta `REFERENCE_DATE` inclusive (2026-09-01)."""


class IntentoPrevio(NamedTuple):
    """Consulta rechazada en el intento anterior y su error, ya saneado."""

    sql: str
    error: str


_COLUMNAS = """
SELECT table_name, column_name, data_type, character_maximum_length,
       numeric_precision, numeric_scale, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
ORDER BY table_name, ordinal_position
"""

# `information_schema.table_constraints` oculta las tablas en las que el rol solo tiene SELECT
# (es el caso de `agente_ro`), así que las claves se leen del catálogo (research R14).
_CLAVES = """
SELECT c.conrelid::regclass::text AS tabla, c.contype,
       a.attname AS columna, c.confrelid::regclass::text AS ref_tabla, af.attname AS ref_columna
FROM pg_constraint c
JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attnum, n) ON true
JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
LEFT JOIN pg_attribute af ON af.attrelid = c.confrelid AND af.attnum = c.confkey[k.n]
WHERE c.connamespace = 'public'::regnamespace AND c.contype IN ('p', 'f')
"""


def _tipo(data_type: str, largo: int | None, precision: int | None, escala: int | None) -> str:
    """Tipo compacto: `varchar(60)`, `numeric(10,2)`, `date`, `integer`..."""
    if data_type == "character varying":
        return f"varchar({largo})" if largo else "varchar"
    if data_type == "numeric" and precision is not None:
        return f"numeric({precision},{escala or 0})"
    if data_type.startswith("time without time zone"):
        return "time"
    if data_type.startswith("timestamp without time zone"):
        return "timestamp"
    return data_type


@cache
def describir_esquema() -> str:
    """Describe las tablas de `public` en texto compacto, una línea por tabla.

    Formato: `socios(id_socio integer PK, ..., id_plan integer -> planes.id_plan)`; las
    columnas que admiten NULL llevan `NULL`. Se consulta una sola vez por proceso.
    """
    with connect_ro() as conn:
        columnas = conn.execute(_COLUMNAS).fetchall()
        claves = conn.execute(_CLAVES).fetchall()

    primarias = {(tabla, col) for tabla, tipo, col, _, _ in claves if tipo == "p"}
    foraneas = {(tabla, col): f"{ref_t}.{ref_c}" for tabla, tipo, col, ref_t, ref_c in claves if tipo == "f"}

    tablas: dict[str, list[str]] = {}
    for tabla, col, data_type, largo, precision, escala, nullable in columnas:
        partes = [col, _tipo(data_type, largo, precision, escala)]
        if (tabla, col) in primarias:
            partes.append("PK")
        if (tabla, col) in foraneas:
            partes.append(f"-> {foraneas[tabla, col]}")
        if nullable == "YES":
            partes.append("NULL")
        tablas.setdefault(tabla, []).append(" ".join(partes))
    return "\n".join(f"{tabla}({', '.join(cols)})" for tabla, cols in tablas.items())


GLOSARIO = f"""\
- "Hoy" es {REFERENCE_DATE.isoformat()} (fecha de referencia fija del sistema).
- "Último mes" son los 30 días corridos hasta hoy inclusive: \
`<columna de fecha> BETWEEN DATE '{INICIO_ULTIMO_MES.isoformat()}' AND DATE '{REFERENCE_DATE.isoformat()}'`.
- "Asistió" / "asistencias" = `asistencias.presente = true`; "no asistió" / "faltó" / "faltas" = filas de \
`asistencias` con `presente = false` (una falta registrada). "Socios que no asistieron" son los que \
tienen alguna falta en el período: `JOIN asistencias ... WHERE presente = false`. No agregues socios sin \
registros de asistencia (ni con `NOT IN`, ni con `NOT EXISTS`, ni con `UNION`).
- "Pago vencido" = `pagos.estado = 'vencido'`; un pago `'pendiente'` NO es vencido.
- "Recaudación" o "cuánto se cobró" = suma de `pagos.monto` con `estado = 'pagado'`, filtrando por `fecha_pago`.
- "Socio activo" = `socios.estado = 'activo'`. Filtrá por `socios.estado` solo si la pregunta lo pide \
("activos", "dados de baja", "congelados"); "socios" o "members" a secas son todos, cualquiera sea su estado.
- "Equipo en mantenimiento" = `equipamiento.estado = 'en_mantenimiento'`.
- Valores válidos (exactos, en minúsculas):
  - `socios.estado`: 'activo', 'congelado', 'baja'.
  - `pagos.estado`: 'pagado', 'pendiente', 'vencido'.
  - `pagos.medio_pago`: 'efectivo', 'transferencia', 'tarjeta', 'mercado_pago'.
  - `equipamiento.estado`: 'operativo', 'en_mantenimiento', 'fuera_de_servicio'.
  - `clases.dia_semana`: 'lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo' \
(SIN tildes: 'miercoles' y 'sabado', nunca 'miércoles' ni 'sábado').
- `pagos.mes_correspondiente` es el primer día del mes que se paga (por ejemplo `DATE '2026-09-01'`)."""
"""Definiciones de negocio que el LLM debe respetar (data-model.md)."""


_REGLAS = f"""\
1. Escribí UNA sola consulta `SELECT` de PostgreSQL (se admite `WITH ... SELECT`), sin `;` \
intermedios. Solo se puede leer: nunca INSERT, UPDATE, DELETE ni ninguna otra sentencia.
2. Usá solo las tablas y columnas del esquema, con sus nombres exactos (salvo el caso de la regla 8).
3. Fechas: escribilas como literales (`DATE '2026-09-01'`). Prohibido `CURRENT_DATE`, `now()`, \
`CURRENT_TIMESTAMP`, `age()` con un solo argumento y los literales 'today' o 'now': "hoy" es \
DATE '{REFERENCE_DATE.isoformat()}'. Para edades usá `age(DATE '{REFERENCE_DATE.isoformat()}', fecha_nacimiento)`.
4. Los datos están en castellano aunque la pregunta esté en inglés (por ejemplo "active" → 'activo').
5. Para buscar personas o nombres por texto usá `ILIKE`. Si la respuesta incluye personas, \
devolvé nombre y apellido.
6. Poné alias claros a las columnas calculadas (`AS cantidad`, `AS total`) y ordená el \
resultado cuando tenga sentido.
7. La pregunta puede tener también una parte sobre los documentos del gimnasio (reglamento, manual, \
guías). Esa parte se responde por otro lado: ignorala y escribí la consulta solo para la parte de \
datos. Si los datos se comparan con un valor de los documentos ("más tiempo del que indica el \
manual"), no inventes ese valor ni filtres por él: devolvé las filas pedidas con la columna a \
comparar, ordenadas por ella; la comparación se hace después con el documento.
8. Solo si el usuario nombra una tabla o un esquema que no está arriba (por ejemplo "la tabla \
rag.chunks"), escribí la consulta con ese nombre (`SELECT * FROM rag.chunks`): el sistema la \
rechaza. Nunca la reemplaces por una consulta vacía como `SELECT 1 WHERE false`."""


def construir_prompt_sql(
    esquema: str, pregunta: str, idioma: str, intento_previo: IntentoPrevio | None = None
) -> str:
    """Arma el pedido al LLM para traducir `pregunta` a un único `SELECT`.

    Args:
        esquema: descripción de las tablas (salida de `describir_esquema()`).
        pregunta: la pregunta del usuario, tal como llegó.
        idioma: `"es"` o `"en"`, el idioma de la pregunta (lo determina el router).
        intento_previo: la consulta rechazada antes y su error saneado, si es un reintento.
    """
    idioma_txt = "inglés" if idioma == "en" else "castellano"
    partes = [
        "Sos un experto en PostgreSQL. Traducí la pregunta sobre un gimnasio a una consulta SQL.",
        f"## Esquema (solo estas tablas)\n{esquema}",
        f"## Glosario de negocio\n{GLOSARIO}",
        f"## Reglas\n{_REGLAS}",
        f"## Pregunta (en {idioma_txt})\n{pregunta}",
    ]
    if intento_previo is not None:
        partes.append(
            "## Consulta anterior (rechazada)\n"
            f"{intento_previo.sql}\n\n"
            f"Error: {intento_previo.error}\n\n"
            "Corregí la consulta para evitar ese error."
        )
    return "\n\n".join(partes)
