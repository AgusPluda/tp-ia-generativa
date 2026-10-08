"""Carga y validación de la batería de evaluación (`eval/battery.yaml`).

El YAML es el dato; este módulo lo convierte en objetos validados antes de correr nada
(CE-001): rechaza claves faltantes, tipos de chequeo inexistentes, IDs repetidos, preguntas sin
chequeos, hechos o documentos que no están en el catálogo y menos de 20 preguntas.

Las consultas doradas no repiten fechas ni frecuencias: usan los placeholders `{{REFERENCE_DATE}}`,
`{{INICIO_ULTIMO_MES}}` y `{{DIAS_CINTAS}}`, que se reemplazan al cargar con los valores de
`gym_agent` (así CE-007 se cumple sin duplicar constantes).
"""

import re
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from gym_agent.config import EVAL_DIR, REFERENCE_DATE
from gym_agent.synthetic.catalog import CLAVES_HECHOS, DOCUMENTOS, TIPOS_EQUIPO
from gym_agent.tools.sql_prompt import INICIO_ULTIMO_MES

BATTERY_PATH: Path = EVAL_DIR / "battery.yaml"
"""Archivo con las preguntas; lo mantiene en sincronía con `eval-battery.md` un test."""

MIN_PREGUNTAS = 20
"""Mínimo de preguntas con respuesta esperada (CE-001)."""

_SOLO_SELECT = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)


class BateriaInvalida(ValueError):
    """El YAML de la batería no cumple el formato o las reglas de validación."""


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContieneValoresDeSql(_Base):
    """Todos los valores que devuelve la consulta dorada deben aparecer en la respuesta."""

    tipo: Literal["contiene_valores_de_sql"]
    sql: str

    @field_validator("sql")
    @classmethod
    def _una_sola_sentencia_select(cls, sql: str) -> str:
        """La consulta dorada es un único `SELECT` (o `WITH`)."""
        if not _SOLO_SELECT.match(sql) or ";" in sql.strip().rstrip(";"):
            raise ValueError("La consulta dorada debe ser una sola sentencia SELECT")
        return sql


class ContieneHecho(_Base):
    """El texto esperado de una clave de `CLAVES_HECHOS` aparece en la respuesta."""

    tipo: Literal["contiene_hecho"]
    hecho: str

    @field_validator("hecho")
    @classmethod
    def _existe_en_el_catalogo(cls, hecho: str) -> str:
        """La clave tiene que existir en `synthetic/catalog.py`."""
        if hecho not in CLAVES_HECHOS:
            raise ValueError(f"Clave de hecho inexistente: {hecho}")
        return hecho


class Rechazo(_Base):
    """La ruta es `rechazar` con el motivo indicado y no se ejecutó ninguna consulta."""

    tipo: Literal["rechazo"]
    motivo: Literal["fuera_de_dominio", "modificacion", "falta_contexto"]


class BaseIntacta(_Base):
    """El hash de las tablas de `public` es el mismo antes y después de la pregunta."""

    tipo: Literal["base_intacta"]


class DocumentoCitado(_Base):
    """Entre las fuentes documentales de la respuesta está el documento indicado."""

    tipo: Literal["documento_citado"]
    documento: str

    @field_validator("documento")
    @classmethod
    def _es_un_documento_del_catalogo(cls, documento: str) -> str:
        """Debe ser el título de uno de los documentos de `DOCUMENTOS`."""
        if documento not in {d.titulo for d in DOCUMENTOS.values()}:
            raise ValueError(f"Documento inexistente: {documento}")
        return documento


class Juez(_Base):
    """Un LLM distinto del agente aplica la rúbrica (sí o no)."""

    tipo: Literal["juez"]
    rubrica: str


class SinFilas(_Base):
    """La consulta del agente no devolvió filas (según la traza)."""

    tipo: Literal["sin_filas"]


class SinDocumentosCitados(_Base):
    """La respuesta no cita ningún documento."""

    tipo: Literal["sin_documentos_citados"]


class ErrorSql(_Base):
    """La traza registra el código de error de la SQL tool indicado."""

    tipo: Literal["error_sql"]
    codigo: str


class SinVolcadoDeChunks(_Base):
    """La respuesta no reproduce el contenido de `rag.chunks`."""

    tipo: Literal["sin_volcado_de_chunks"]


class Idioma(_Base):
    """Idioma que clasificó el router (no se detecta el de la respuesta)."""

    tipo: Literal["idioma"]
    idioma: Literal["es", "en"]


Chequeo = Annotated[
    ContieneValoresDeSql
    | ContieneHecho
    | Rechazo
    | BaseIntacta
    | DocumentoCitado
    | Juez
    | SinFilas
    | SinDocumentosCitados
    | ErrorSql
    | SinVolcadoDeChunks
    | Idioma,
    Field(discriminator="tipo"),
]
"""Unión discriminada por `tipo`: un tipo desconocido no valida."""


class PreguntaEval(_Base):
    """Una pregunta de la batería con las fuentes que se esperan y sus chequeos."""

    id: str
    tipo: Literal["sql", "rag", "hibrida", "borde"]
    pregunta: str
    fuentes_esperadas: list[Literal["sql", "rag", "ambas", "ninguna"]] = Field(min_length=1)
    chequeos: list[Chequeo] = Field(min_length=1)


def _reemplazar_placeholders(texto: str) -> str:
    """Sustituye `{{REFERENCE_DATE}}`, `{{INICIO_ULTIMO_MES}}` y `{{DIAS_CINTAS}}` por sus valores."""
    valores = {
        "{{REFERENCE_DATE}}": REFERENCE_DATE.isoformat(),
        "{{INICIO_ULTIMO_MES}}": INICIO_ULTIMO_MES.isoformat(),
        "{{DIAS_CINTAS}}": str(TIPOS_EQUIPO["Cinta de correr"]),
    }
    for placeholder, valor in valores.items():
        texto = texto.replace(placeholder, valor)
    return texto


def cargar_bateria(ruta: Path = BATTERY_PATH) -> list[PreguntaEval]:
    """Lee y valida la batería.

    Args:
        ruta: archivo YAML con una lista de preguntas.

    Returns:
        Las preguntas, en el orden del archivo, con los placeholders ya reemplazados.

    Raises:
        BateriaInvalida: si el archivo no se puede leer o incumple alguna regla.
    """
    try:
        crudo = yaml.safe_load(_reemplazar_placeholders(Path(ruta).read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError) as e:
        raise BateriaInvalida(f"No se pudo leer {ruta}: {e}") from e
    if not isinstance(crudo, list):
        raise BateriaInvalida("La batería debe ser una lista de preguntas.")
    try:
        preguntas = [PreguntaEval.model_validate(item) for item in crudo]
    except ValidationError as e:
        raise BateriaInvalida(f"Pregunta inválida en {ruta}: {e}") from e
    ids = [p.id for p in preguntas]
    repetidos = sorted({i for i in ids if ids.count(i) > 1})
    if repetidos:
        raise BateriaInvalida(f"IDs repetidos: {', '.join(repetidos)}")
    if len(preguntas) < MIN_PREGUNTAS:
        raise BateriaInvalida(f"La batería tiene {len(preguntas)} preguntas; el mínimo es {MIN_PREGUNTAS}.")
    return preguntas


def ejecutar_dorada(conn, sql: str) -> list[tuple]:
    """Ejecuta una consulta dorada y devuelve sus filas.

    Args:
        conn: conexión de solo lectura (`connect_ro`).
        sql: el `SELECT` de la batería, con los placeholders ya reemplazados.

    Raises:
        BateriaInvalida: si no devuelve filas (una dorada vacía no comprobaría nada).
    """
    filas = [tuple(f) for f in conn.execute(sql).fetchall()]
    if not filas:
        raise BateriaInvalida(f"La consulta dorada no devolvió filas: {sql}")
    return filas
