"""División del texto de un PDF en chunks para el RAG (research R9).

Recibe el texto de cada página tal como lo deja `ingest.extraer_paginas`: párrafos separados por
una línea en blanco y, dentro de un párrafo, un salto de línea por cada renglón del PDF.

Reglas:

- Los párrafos se agrupan hasta `max_chars` caracteres; un párrafo más largo se corta por
  oraciones y, si hace falta, por palabras.
- Cada chunk empieza con los últimos `solape` caracteres (como máximo, cortados en un límite de
  palabra) del chunk anterior de la misma página.
- Un chunk nunca cruza páginas, así cada uno tiene una página definida para la cita.
"""

import re
from dataclasses import dataclass

_SEPARADOR = "\n\n"
"""Separador entre párrafos dentro de un chunk."""


@dataclass(frozen=True)
class Chunk:
    """Fragmento de un documento, listo para embeber e insertar en `rag.chunks`."""

    pagina: int
    """Página de origen, desde 1."""
    orden: int
    """Posición del chunk dentro del documento, desde 1."""
    contenido: str


def _parrafos(texto: str) -> list[str]:
    """Bloques separados por líneas en blanco, con sus renglones unidos por un espacio."""
    return [" ".join(bloque.split()) for bloque in re.split(r"\n\s*\n", texto) if bloque.strip()]


def _empaquetar(partes: list[str], limite: int) -> list[str]:
    """Une partes consecutivas con un espacio mientras el resultado no supere `limite`."""
    piezas: list[str] = []
    actual = ""
    for parte in partes:
        if not actual:
            actual = parte
        elif len(actual) + 1 + len(parte) <= limite:
            actual = f"{actual} {parte}"
        else:
            piezas.append(actual)
            actual = parte
    if actual:
        piezas.append(actual)
    return piezas


def _partir(texto: str, limite: int) -> list[str]:
    """Corta `texto` en piezas de hasta `limite` caracteres: primero por oraciones y después por palabras."""
    if len(texto) <= limite:
        return [texto]
    for patron in (r"(?<=[.!?])\s+", r"\s+"):
        partes = re.split(patron, texto)
        if len(partes) > 1:
            return _empaquetar([p for parte in partes for p in _partir(parte, limite)], limite)
    return [texto[i : i + limite] for i in range(0, len(texto), limite)]  # una "palabra" enorme


def _cola(texto: str, solape: int) -> str:
    """Los últimos `solape` caracteres de `texto`, sin empezar a mitad de palabra."""
    if solape == 0:
        return ""
    cola = texto[-solape:]
    if len(texto) > solape and not texto[-solape - 1].isspace():
        espacio = re.search(r"\s", cola)
        cola = cola[espacio.end() :] if espacio else cola
    return cola.lstrip()


def dividir_en_chunks(paginas: list[str], max_chars: int = 800, solape: int = 100) -> list[Chunk]:
    """Divide el texto de un documento en chunks de hasta `max_chars` caracteres.

    Args:
        paginas: texto de cada página, en orden (la primera es la página 1). Las páginas vacías
            no generan chunks pero cuentan para la numeración.
        max_chars: tamaño máximo de cada chunk, solape incluido.
        solape: cantidad máxima de caracteres que un chunk repite del anterior de su misma página.

    Returns:
        Los chunks del documento con `orden` creciente desde 1.
    """
    if not 0 <= solape < max_chars // 2:
        raise ValueError("El solape debe ser menor que la mitad de max_chars.")
    # Cada pieza deja lugar para el solape y el separador, así ningún chunk supera max_chars.
    limite = max_chars - solape - len(_SEPARADOR)
    chunks: list[Chunk] = []
    for numero, texto in enumerate(paginas, start=1):
        actual = ""
        for pieza in (p for parrafo in _parrafos(texto) for p in _partir(parrafo, limite)):
            if not actual:
                actual = pieza
            elif len(actual) + len(_SEPARADOR) + len(pieza) <= max_chars:
                actual += _SEPARADOR + pieza
            else:
                chunks.append(Chunk(numero, len(chunks) + 1, actual))
                cola = _cola(actual, solape)
                actual = f"{cola}{_SEPARADOR}{pieza}" if cola else pieza
        if actual:
            chunks.append(Chunk(numero, len(chunks) + 1, actual))
    return chunks
