"""Tests del validador de SQL (primera capa de seguridad de la SQL tool).

No usan la base ni el LLM: `validar` solo analiza el texto con `sqlglot`.
Contrato: specs/001-agente-sql-rag-gimnasio/contracts/sql-tool.md (paso 2 del pipeline).
"""

import pytest

from gym_agent.tools.sql_validator import SQLNoPermitido, validar


def _codigo(sql: str) -> str:
    """Devuelve el código con el que `validar` rechaza `sql` (falla el test si la acepta)."""
    with pytest.raises(SQLNoPermitido) as excinfo:
        validar(sql)
    return excinfo.value.codigo


# --- Se aceptan ---------------------------------------------------------------

ACEPTADAS = [
    "SELECT * FROM socios",
    "WITH activos AS (SELECT * FROM socios WHERE estado = 'activo') SELECT count(*) FROM activos",
    "SELECT p.nombre, count(*) FROM socios s JOIN planes p ON p.id_plan = s.id_plan GROUP BY p.nombre",
    "SELECT nombre FROM socios WHERE id_plan IN (SELECT id_plan FROM planes WHERE precio_mensual > 20000)",
    "SELECT id_socio, rank() OVER (ORDER BY count(*) DESC) FROM asistencias GROUP BY id_socio",
    "SELECT count(*) FROM asistencias WHERE fecha BETWEEN DATE '2026-09-01' AND DATE '2026-09-30'",
    "SELECT * FROM socios WHERE apellido ILIKE '%gomez%'",
    "SELECT nombre FROM clases -- clases del gimnasio",
    "SELECT /* solo nombres */ nombre FROM instructores",
    "SELECT nombre FROM socios WHERE nombre ILIKE 'today%'",
    "SELECT nombre FROM socios UNION SELECT nombre FROM instructores",
    "SELECT date_part('year', age(DATE '2026-09-30', fecha_nacimiento)) FROM socios",
    "SELECT * FROM generate_series(1, 3)",
    "SELECT * FROM public.socios",
]


@pytest.mark.parametrize("sql", ACEPTADAS)
def test_acepta_select_de_solo_lectura(sql):
    assert validar(sql) == sql


@pytest.mark.parametrize(
    ("sql", "esperado"),
    [
        ("SELECT * FROM planes;", "SELECT * FROM planes"),
        ("  SELECT * FROM planes ;  \n", "SELECT * FROM planes"),
        ("SELECT * FROM planes;;", "SELECT * FROM planes"),
    ],
)
def test_devuelve_la_consulta_original_sin_punto_y_coma_final(sql, esperado):
    assert validar(sql) == esperado


def test_devuelve_el_texto_original_y_no_el_regenerado():
    sql = "select   nombre  from socios where estado='activo'"
    assert validar(sql) == sql


# --- NO_ES_SELECT -------------------------------------------------------------

ESCRITURAS = [
    "INSERT INTO planes (nombre, precio_mensual, clases_por_semana) VALUES ('x', 1, 1)",
    "UPDATE socios SET estado = 'baja'",
    "DELETE FROM pagos",
    "DROP TABLE socios",
    "ALTER TABLE socios ADD COLUMN x int",
    "CREATE TABLE t (a int)",
    "TRUNCATE pagos",
    "GRANT SELECT ON socios TO public",
    "REVOKE SELECT ON socios FROM public",
    "COPY socios TO '/tmp/socios.csv'",
    "CALL procedimiento()",
    "DO $$ BEGIN DELETE FROM pagos; END $$",
    "SET statement_timeout = 0",
    "MERGE INTO planes p USING planes q ON p.id_plan = q.id_plan WHEN MATCHED THEN DELETE",
    "LOCK TABLE socios",
    "COMMENT ON TABLE socios IS 'x'",
    "SELECT 1; DELETE FROM pagos",
    "SELECT 1; -- x\nDELETE FROM pagos",
    "SELECT * INTO nueva FROM socios",
    "SELECT * FROM socios FOR UPDATE",
    "SELECT * FROM socios FOR SHARE",
    "SELECT * FROM socios FOR NO KEY UPDATE",
    "SELECT (SELECT 1 FROM socios FOR UPDATE)",
    "WITH x AS (DELETE FROM pagos RETURNING *) SELECT * FROM x",
    "WITH x AS (UPDATE socios SET estado = 'baja' RETURNING *) SELECT count(*) FROM x",
    "WITH x AS (INSERT INTO planes (nombre) VALUES ('x') RETURNING *) SELECT * FROM x",
    "WITH x AS (SELECT 1) DELETE FROM pagos",
    # Un string estándar no interpreta `\`: el `;` lo cierra y el DELETE se ejecutaría.
    "SELECT 'a\\'; DELETE FROM pagos; --'",
    "SELECT $$x$$; DELETE FROM pagos",
]


@pytest.mark.parametrize("sql", ESCRITURAS)
def test_rechaza_escrituras_y_ddl(sql):
    assert _codigo(sql) == "NO_ES_SELECT"


# --- FUERA_DE_ESQUEMA ---------------------------------------------------------

FUERA_DE_ESQUEMA = [
    "SELECT * FROM rag.chunks",
    "SELECT s.nombre FROM socios s JOIN rag.documentos d ON d.id_documento = s.id_socio",
    "SELECT * FROM socios WHERE id_socio IN (SELECT id_documento FROM rag.documentos)",
    "WITH d AS (SELECT * FROM rag.documentos) SELECT * FROM d",
    'SELECT * FROM "rag"."chunks"',
    "SELECT * FROM RAG.chunks",
    "SELECT rag.chunks.contenido FROM socios",
    "SELECT * FROM pg_catalog.pg_tables",
    "SELECT * FROM information_schema.columns",
    'SELECT * FROM "information_schema"."tables"',
    "SELECT pg_catalog.now()",
    # pg_catalog está en el search_path: sus vistas se leen sin calificar.
    "SELECT * FROM pg_tables",
    "SELECT usename FROM pg_user",
    "SELECT * FROM pg_stat_activity",
]


@pytest.mark.parametrize("sql", FUERA_DE_ESQUEMA)
def test_rechaza_esquemas_fuera_de_public(sql):
    assert _codigo(sql) == "FUERA_DE_ESQUEMA"


# --- INVALIDA -----------------------------------------------------------------

INVALIDAS = [
    "",
    "   \n\t",
    ";",
    "-- solo un comentario",
    "hola",
    "SELEC * FROM socios",
    "SELECT 'sin cerrar FROM socios",
    "SELECT 1; SELECT 2",
    # Funciones de reloj: el "hoy" es REFERENCE_DATE, nunca la fecha real.
    "SELECT now()",
    "SELECT NOW()",
    "SELECT CURRENT_DATE",
    "SELECT CURRENT_TIMESTAMP",
    "SELECT current_timestamp(0)",
    "SELECT current_time",
    "SELECT localtime",
    "SELECT localtimestamp",
    "SELECT clock_timestamp()",
    "SELECT statement_timestamp()",
    "SELECT transaction_timestamp()",
    "SELECT timeofday()",
    "SELECT count(*) FROM pagos WHERE fecha_pago > CURRENT_DATE - 30",
    # age() con un solo argumento resta desde la fecha real.
    "SELECT age(fecha_nacimiento) FROM socios",
    # Literales especiales de fecha de Postgres: también usan el reloj real.
    "SELECT 'now'::timestamp",
    "SELECT 'today'::date",
    "SELECT 'TODAY'::date",
    "SELECT 'tomorrow'::date",
    "SELECT 'yesterday'::date",
    "SELECT DATE 'today'",
    "SELECT CAST('yesterday' AS date)",
    "SELECT E'today'::date",
    "SELECT $$today$$::date",
    "SELECT count(*) FROM asistencias WHERE fecha > 'today'",
    # Funciones del servidor, de archivos u objetos grandes y conexiones externas.
    "SELECT pg_sleep(10)",
    "SELECT pg_read_file('/etc/passwd')",
    "SELECT pg_ls_dir('.')",
    "SELECT set_config('x', 'y', false)",
    "SELECT current_setting('data_directory')",
    "SELECT lo_import('/etc/passwd')",
    "SELECT * FROM dblink('host=x', 'SELECT 1') AS t(x int)",
    "SELECT dblink_exec('host=x', 'DELETE FROM pagos')",
    # SQL dinámico dentro de un string: saltearía las demás reglas.
    "SELECT query_to_xml('SELECT * FROM rag.chunks', true, false, '')",
    "SELECT table_to_xml('rag.chunks', true, false, '')",
    "SELECT nextval('socios_id_socio_seq')",
]


@pytest.mark.parametrize("sql", INVALIDAS)
def test_rechaza_consultas_invalidas_o_con_funciones_no_permitidas(sql):
    assert _codigo(sql) == "INVALIDA"


# --- La excepción -------------------------------------------------------------


def test_la_excepcion_lleva_codigo_y_detalle():
    with pytest.raises(SQLNoPermitido) as excinfo:
        validar("SELECT * FROM rag.chunks")
    error = excinfo.value
    assert error.codigo == "FUERA_DE_ESQUEMA"
    assert "rag" in error.detalle


def test_validar_no_lanza_otras_excepciones_con_entradas_raras():
    for sql in ["\x00", "'''", "$$", "/*", "SELECT (((", "🙂", "SELECT 1 /* /* */ ; DELETE FROM pagos; /* */"]:
        with pytest.raises(SQLNoPermitido):
            validar(sql)
