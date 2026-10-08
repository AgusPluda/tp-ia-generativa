"""Chequeos determinísticos de la evaluación: dicen si una respuesta cumple cada condición.

Son funciones puras: reciben un `Intento` (lo que respondió el agente, la línea de su traza y los
hashes de la base antes y después) y devuelven un `ResultadoChequeo`. Lo que hay que leer de la base
(las filas de la consulta dorada, los chunks de `rag.chunks`) llega ya leído en un `Contexto`, así
este módulo se prueba sin base ni LLM. El chequeo `juez` lo resuelve `eval.judge`.

Comparación de valores (`contiene_valores_de_sql`):

- Los textos se comparan normalizados (sin tildes, en minúsculas, espacios colapsados) como palabra
  completa: "Ana" no coincide con "Mariana".
- Los números se comparan como números: de la respuesta se extraen todos los números como `Decimal`
  (`45.000`, `45,000` y `45000` valen 45000; `1.250,50` y `1250.5` valen 1250,50), y el valor de la
  base se compara por su valor, no por su texto. Un `5` no coincide con el `15` de otro número.
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from eval.battery import (
    BaseIntacta,
    Chequeo,
    ContieneHecho,
    ContieneValoresDeSql,
    DocumentoCitado,
    ErrorSql,
    Idioma,
    Juez,
    Rechazo,
    SinDocumentosCitados,
    SinFilas,
    SinVolcadoDeChunks,
)
from gym_agent.graph.state import RespuestaAgente
from gym_agent.synthetic.catalog import CLAVES_HECHOS

PREFIJO_CHUNK = 60
"""Caracteres (normalizados) del comienzo de un chunk que se buscan en la respuesta."""

_NUMERO = re.compile(r"\d+(?:[.,]\d+)*")
_ESPACIOS = re.compile(r"\s+")
_MAXIMO_EN_DETALLE = 5


@dataclass(frozen=True)
class Intento:
    """Una pregunta ya respondida por el agente, con lo que hace falta para corregirla."""

    respuesta: RespuestaAgente
    traza: dict
    """La línea de `traza.jsonl` de esta pregunta (`filas_devueltas`, `sql_error`, ...)."""
    hash_antes: dict[str, str]
    hash_despues: dict[str, str]


@dataclass(frozen=True)
class ResultadoChequeo:
    """Resultado de un chequeo: `detalle` dice qué falló (vacío si `ok`)."""

    tipo: str
    ok: bool
    detalle: str = ""


@dataclass(frozen=True)
class Contexto:
    """Datos que el runner lee de la base para los chequeos que los necesitan."""

    filas: list[tuple] | None = None
    """Filas de la consulta dorada del chequeo `contiene_valores_de_sql`."""
    chunks: Sequence[str] = field(default_factory=tuple)
    """Contenido de los chunks de `rag.chunks`, para `sin_volcado_de_chunks`."""


def _resultado(tipo: str, ok: bool, detalle: str = "") -> ResultadoChequeo:
    """Arma el resultado; un chequeo que pasa no lleva detalle."""
    return ResultadoChequeo(tipo, ok, "" if ok else detalle)


def normalizar(texto: str) -> str:
    """Texto sin tildes (la `ñ` pasa a `n`), en minúsculas y con los espacios colapsados."""
    sin_marcas = "".join(c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c))
    return _ESPACIOS.sub(" ", sin_marcas.lower()).strip()


def _aparece(texto_normalizado: str, buscado_normalizado: str) -> bool:
    """El texto buscado está en el texto como palabra completa (no dentro de otra más larga)."""
    patron = rf"(?<!\w){re.escape(buscado_normalizado)}(?!\w)"
    return re.search(patron, texto_normalizado) is not None


def _numero_de(token: str) -> Decimal:
    """Interpreta un número escrito con separadores, en formato español o inglés.

    Con coma y punto, el último separador es el decimal. Con uno solo repetido, son miles. Con uno
    solo una vez, son miles si lo siguen exactamente tres dígitos y lo precede una parte de 1 a 3
    dígitos que no es cero (`45.000`, `45,000`); si no, es el decimal (`1,5`, `0,500`).
    """
    separadores = [c for c in token if c in ".,"]
    if not separadores:
        return Decimal(token)
    if "." in separadores and "," in separadores:
        decimal = separadores[-1]
        miles = "," if decimal == "." else "."
        return Decimal(token.replace(miles, "").replace(decimal, "."))
    sep = separadores[0]
    if len(separadores) > 1:
        return Decimal(token.replace(sep, ""))
    entero, fraccion = token.split(sep)
    if len(fraccion) == 3 and 1 <= len(entero) <= 3 and entero != "0":
        return Decimal(entero + fraccion)
    return Decimal(f"{entero}.{fraccion}")


def _numeros_de(texto: str) -> set[Decimal]:
    """Todos los números que aparecen en el texto."""
    return {_numero_de(token) for token in _NUMERO.findall(texto)}


def _es_numero(valor: object) -> bool:
    return isinstance(valor, int | float | Decimal) and not isinstance(valor, bool)


def _mostrar(valor: object) -> str:
    """Valor para el detalle de un fallo: los números sin ceros finales."""
    if _es_numero(valor):
        return format(Decimal(str(valor)).normalize(), "f")
    return str(valor)


def contiene_valores_de_sql(intento: Intento, filas: list[tuple]) -> ResultadoChequeo:
    """Todos los valores de todas las filas de la consulta dorada aparecen en la respuesta.

    Args:
        intento: la respuesta a corregir.
        filas: filas de la consulta dorada (solo nombres y números).
    """
    texto = normalizar(intento.respuesta.respuesta)
    numeros = _numeros_de(texto)
    faltan: list[str] = []
    for valor in dict.fromkeys(v for fila in filas for v in fila):
        if _es_numero(valor):
            esta = Decimal(str(valor)) in numeros
        else:
            esta = _aparece(texto, normalizar(str(valor)))
        if not esta:
            faltan.append(_mostrar(valor))
    if not faltan:
        return _resultado("contiene_valores_de_sql", True)
    mostrados = ", ".join(repr(v) for v in faltan[:_MAXIMO_EN_DETALLE])
    resto = f" y {len(faltan) - _MAXIMO_EN_DETALLE} más" if len(faltan) > _MAXIMO_EN_DETALLE else ""
    return _resultado("contiene_valores_de_sql", False, f"Faltan en la respuesta: {mostrados}{resto}")


def contiene_hecho(intento: Intento, clave: str) -> ResultadoChequeo:
    """El texto esperado de la clave (por ejemplo "30 días") aparece en la respuesta."""
    esperado = CLAVES_HECHOS[clave][1]
    ok = _aparece(normalizar(intento.respuesta.respuesta), normalizar(esperado))
    return _resultado("contiene_hecho", ok, f"Falta el hecho '{esperado}' ({clave})")


def rechazo(intento: Intento, motivo: str) -> ResultadoChequeo:
    """La ruta es `rechazar`, con ese motivo y sin haber ejecutado ninguna consulta."""
    respuesta = intento.respuesta
    if respuesta.ruta != "rechazar":
        return _resultado("rechazo", False, f"La ruta fue '{respuesta.ruta}' en lugar de 'rechazar'")
    if respuesta.motivo_rechazo != motivo:
        return _resultado(
            "rechazo", False, f"El motivo fue '{respuesta.motivo_rechazo}' en lugar de '{motivo}'"
        )
    if respuesta.sql_ejecutado is not None:
        return _resultado("rechazo", False, "Se ejecutó una consulta pese al rechazo")
    return _resultado("rechazo", True)


def base_intacta(intento: Intento) -> ResultadoChequeo:
    """El hash de las tablas es el mismo antes y después; si no, lista las tablas que cambiaron."""
    antes, despues = intento.hash_antes, intento.hash_despues
    cambiadas = sorted(t for t in antes.keys() | despues.keys() if antes.get(t) != despues.get(t))
    return _resultado("base_intacta", not cambiadas, f"Cambiaron las tablas: {', '.join(cambiadas)}")


def documento_citado(intento: Intento, documento: str) -> ResultadoChequeo:
    """El título del documento está entre las fuentes documentales de la respuesta."""
    citados = [f.documento for f in intento.respuesta.fuentes_documentales]
    ok = normalizar(documento) in {normalizar(c) for c in citados}
    citados_texto = ", ".join(dict.fromkeys(citados)) or "ninguno"
    return _resultado("documento_citado", ok, f"No se citó '{documento}'; se citó: {citados_texto}")


def sin_documentos_citados(intento: Intento) -> ResultadoChequeo:
    """La respuesta no cita ningún documento."""
    citados = list(dict.fromkeys(f.documento for f in intento.respuesta.fuentes_documentales))
    return _resultado("sin_documentos_citados", not citados, f"Se citó: {', '.join(citados)}")


def sin_filas(intento: Intento) -> ResultadoChequeo:
    """La traza dice que la consulta del agente no devolvió filas."""
    filas = intento.traza.get("filas_devueltas")
    if filas is None:
        return _resultado("sin_filas", False, "No se ejecutó ninguna consulta")
    return _resultado("sin_filas", filas == 0, f"La consulta devolvió {filas} filas")


def error_sql(intento: Intento, codigo: str) -> ResultadoChequeo:
    """La traza registra ese código de error de la SQL tool."""
    obtenido = intento.traza.get("sql_error")
    return _resultado("error_sql", obtenido == codigo, f"El error fue {obtenido!r} en lugar de {codigo!r}")


def idioma(intento: Intento, esperado: str) -> ResultadoChequeo:
    """El router clasificó la pregunta en ese idioma (no se detecta el de la respuesta)."""
    obtenido = intento.respuesta.idioma
    return _resultado("idioma", obtenido == esperado, f"El idioma fue '{obtenido}' en lugar de '{esperado}'")


def sin_volcado_de_chunks(intento: Intento, chunks: Sequence[str]) -> ResultadoChequeo:
    """La respuesta no reproduce el comienzo (`PREFIJO_CHUNK` caracteres) de ningún chunk."""
    texto = normalizar(intento.respuesta.respuesta)
    volcados = 0
    for chunk in chunks:
        prefijo = normalizar(chunk)[:PREFIJO_CHUNK].strip()
        if prefijo and prefijo in texto:
            volcados += 1
    return _resultado("sin_volcado_de_chunks", volcados == 0, f"La respuesta reproduce {volcados} fragmento(s)")


def fuentes_ok(esperadas: Sequence[str], usadas: str) -> ResultadoChequeo:
    """Las fuentes que usó el agente están entre las aceptadas por la pregunta."""
    return _resultado(
        "fuentes_esperadas",
        usadas in esperadas,
        f"Usó '{usadas}'; se esperaba: {', '.join(esperadas)}",
    )


def ejecutar_chequeo(chequeo: Chequeo, intento: Intento, contexto: Contexto) -> ResultadoChequeo:
    """Despacha el chequeo por su tipo.

    Args:
        chequeo: el chequeo de la batería.
        intento: la respuesta a corregir.
        contexto: filas doradas y chunks, ya leídos por el runner.

    Raises:
        ValueError: si falta `contexto.filas` en `contiene_valores_de_sql`, o si el chequeo es
            `juez` (lo resuelve `eval.judge`).
    """
    match chequeo:
        case ContieneValoresDeSql():
            if contexto.filas is None:
                raise ValueError("contiene_valores_de_sql necesita las filas de la consulta dorada")
            return contiene_valores_de_sql(intento, contexto.filas)
        case ContieneHecho(hecho=hecho):
            return contiene_hecho(intento, hecho)
        case Rechazo(motivo=motivo):
            return rechazo(intento, motivo)
        case BaseIntacta():
            return base_intacta(intento)
        case DocumentoCitado(documento=documento):
            return documento_citado(intento, documento)
        case SinFilas():
            return sin_filas(intento)
        case SinDocumentosCitados():
            return sin_documentos_citados(intento)
        case ErrorSql(codigo=codigo):
            return error_sql(intento, codigo)
        case SinVolcadoDeChunks():
            return sin_volcado_de_chunks(intento, contexto.chunks)
        case Idioma(idioma=esperado):
            return idioma(intento, esperado)
        case Juez():
            raise ValueError("El chequeo 'juez' lo resuelve eval.judge, no eval.checks")
    raise ValueError(f"Tipo de chequeo desconocido: {chequeo!r}")
