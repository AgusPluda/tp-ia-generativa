"""Los PDFs se renderizan idénticos en cada corrida y su texto extraído conserva los hechos del catálogo.

No usan la base: están en `integration` porque escriben archivos y pasan por `reportlab` y `pypdf`.
"""

import hashlib
from pathlib import Path

import pytest

from gym_agent.config import PDF_DIR
from gym_agent.rag.ingest import extraer_paginas
from gym_agent.synthetic.catalog import CLAVES_HECHOS, DOCUMENTOS
from gym_agent.synthetic.pdf_content import CONTENIDOS
from gym_agent.synthetic.pdf_render import renderizar_pdfs


def _hashes(directorio: Path) -> dict[str, str]:
    return {
        d.nombre_archivo: hashlib.sha256((directorio / d.nombre_archivo).read_bytes()).hexdigest()
        for d in DOCUMENTOS.values()
    }


@pytest.fixture(scope="module")
def directorio_pdfs(tmp_path_factory) -> Path:
    directorio = tmp_path_factory.mktemp("pdfs")
    renderizar_pdfs(directorio)
    return directorio


def test_dos_renderizados_producen_los_mismos_bytes(directorio_pdfs, tmp_path):
    renderizar_pdfs(tmp_path)
    assert _hashes(directorio_pdfs) == _hashes(tmp_path)


def test_los_pdfs_versionados_estan_al_dia(directorio_pdfs):
    """Si falla, se cambió `pdf_content.py` sin volver a correr `python scripts/generate_pdfs.py`."""
    assert _hashes(PDF_DIR) == _hashes(directorio_pdfs)


@pytest.mark.parametrize("id_documento", list(DOCUMENTOS))
def test_cada_pagina_del_contenido_es_una_pagina_del_pdf(directorio_pdfs, id_documento):
    """Las páginas citadas por el RAG coinciden con las de `pdf_content.py` (ninguna se desborda)."""
    paginas = extraer_paginas(directorio_pdfs / DOCUMENTOS[id_documento].nombre_archivo)
    assert len(paginas) == len(CONTENIDOS[id_documento].paginas)


@pytest.mark.parametrize("clave", list(CLAVES_HECHOS))
def test_cada_hecho_sobrevive_a_la_extraccion_del_pdf(directorio_pdfs, clave):
    """Un salto de línea o una tilde mal extraída harían que el hecho no llegue a los chunks."""
    id_documento, esperado = CLAVES_HECHOS[clave]
    paginas = extraer_paginas(directorio_pdfs / DOCUMENTOS[id_documento].nombre_archivo)
    texto = " ".join(" ".join(paginas).split())
    assert esperado in texto
