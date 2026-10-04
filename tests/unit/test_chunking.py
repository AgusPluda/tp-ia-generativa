"""División del texto de los PDFs en chunks (research R9): tamaño, solape, páginas y orden."""

from gym_agent.rag.chunking import Chunk, dividir_en_chunks

MAX_CHARS = 800
SOLAPE = 100


def _parrafo(pagina: int, n: int, palabras: int) -> str:
    """Párrafo con palabras marcadas con su página (`p1w...`), cortado en líneas como en un PDF."""
    tokens = [f"p{pagina}w{n}x{i}" for i in range(palabras)]
    lineas = [" ".join(tokens[i : i + 8]) for i in range(0, len(tokens), 8)]
    return "\n".join(lineas)


def _pagina(numero: int, tamanios: list[int]) -> str:
    return "\n\n".join(_parrafo(numero, n, palabras) for n, palabras in enumerate(tamanios))


# Página 1: varios párrafos medianos; página 2: uno larguísimo (más de 800 caracteres) entre dos cortos.
PAGINAS = [
    _pagina(1, [30, 45, 12, 60, 25, 40, 50]),
    _pagina(2, [10, 200, 15]),
]


def _palabras(texto: str) -> list[str]:
    return texto.split()


def test_ningun_chunk_supera_el_maximo():
    chunks = dividir_en_chunks(PAGINAS, MAX_CHARS, SOLAPE)
    assert len(chunks) > 3
    assert all(0 < len(c.contenido) <= MAX_CHARS for c in chunks)


def test_ningun_chunk_cruza_una_pagina_y_conserva_su_numero():
    for c in dividir_en_chunks(PAGINAS, MAX_CHARS, SOLAPE):
        assert all(p.startswith(f"p{c.pagina}w") for p in _palabras(c.contenido))


def test_el_orden_es_creciente_y_las_paginas_no_retroceden():
    chunks = dividir_en_chunks(PAGINAS, MAX_CHARS, SOLAPE)
    assert [c.orden for c in chunks] == list(range(1, len(chunks) + 1))
    assert [c.pagina for c in chunks] == sorted(c.pagina for c in chunks)
    assert {c.pagina for c in chunks} == {1, 2}


def test_chunks_consecutivos_de_la_misma_pagina_se_solapan_hasta_100_caracteres():
    chunks = dividir_en_chunks(PAGINAS, MAX_CHARS, SOLAPE)
    pares = [(a, b) for a, b in zip(chunks, chunks[1:]) if a.pagina == b.pagina]
    assert pares
    for anterior, siguiente in pares:
        solape = max(
            (k for k in range(1, SOLAPE + 1) if anterior.contenido[-k:] == siguiente.contenido[:k]),
            default=0,
        )
        assert SOLAPE // 2 <= solape <= SOLAPE


def test_el_primer_chunk_de_una_pagina_no_arrastra_texto_de_la_anterior():
    chunks = dividir_en_chunks(PAGINAS, MAX_CHARS, SOLAPE)
    primero_p2 = next(c for c in chunks if c.pagina == 2)
    assert primero_p2.contenido.startswith("p2w0x0")


def test_no_se_pierde_texto():
    chunks = dividir_en_chunks(PAGINAS, MAX_CHARS, SOLAPE)
    for numero, pagina in enumerate(PAGINAS, start=1):
        en_chunks = set().union(*(_palabras(c.contenido) for c in chunks if c.pagina == numero))
        assert set(_palabras(pagina)) <= en_chunks


def test_las_lineas_de_un_parrafo_se_unen_con_espacios():
    (chunk,) = dividir_en_chunks(["Título de sección\nprimera línea\nsegunda línea."])
    assert chunk == Chunk(pagina=1, orden=1, contenido="Título de sección primera línea segunda línea.")


def test_las_paginas_vacias_no_generan_chunks_pero_cuentan_para_la_numeracion():
    chunks = dividir_en_chunks(["Texto de la página uno.", "  \n\n ", "Texto de la página tres."])
    assert [(c.pagina, c.orden) for c in chunks] == [(1, 1), (3, 2)]
