"""RAG tool contra la base ingestada, sin LLM: `embeber` es falso."""

import random

import pytest

from gym_agent.config import EMBEDDING_DIM
from gym_agent.llm import normalize
from gym_agent.tools.rag_tool import Fragmento, buscar


@pytest.fixture
def embedding_congelamiento(conn_admin):
    """Embedding guardado del chunk del reglamento que habla del congelamiento de la cuota."""
    with conn_admin.cursor() as cur:
        cur.execute(
            "SELECT embedding::text, contenido FROM rag.chunks WHERE contenido ILIKE %s ORDER BY id_chunk LIMIT 1",
            ("%Congelamiento de la cuota%",),
        )
        fila = cur.fetchone()
    if fila is None:
        pytest.skip("La base no está ingestada: python scripts/ingest_pdfs.py")
    return [float(x) for x in fila[0].strip("[]").split(",")], fila[1]


def test_con_el_embedding_de_un_chunk_el_primero_es_ese_chunk(embedding_congelamiento):
    vector, contenido = embedding_congelamiento
    r = buscar("congelamiento", embeber=lambda _p: vector)
    assert r.ok
    primero = r.fragmentos[0]
    assert primero.texto == contenido
    assert primero.documento == "Reglamento interno"
    assert primero.pagina == 3
    assert primero.similitud > 0.99


def test_k_limita_la_cantidad_de_fragmentos(embedding_congelamiento):
    vector, _ = embedding_congelamiento
    dos = buscar("p", k=2, umbral=-1, embeber=lambda _p: vector)
    por_defecto = buscar("p", umbral=-1, embeber=lambda _p: vector)
    assert len(dos.fragmentos) == 2
    assert len(por_defecto.fragmentos) == 4
    similitudes = [f.similitud for f in por_defecto.fragmentos]
    assert similitudes == sorted(similitudes, reverse=True)


def test_un_vector_sin_relacion_con_ningun_texto_no_devuelve_nada(conn_admin):
    azar = random.Random(1)
    vector = normalize([azar.gauss(0, 1) for _ in range(EMBEDDING_DIM)])
    r = buscar("p", umbral=0.6, embeber=lambda _p: vector)
    assert r.ok and r.fragmentos == []


def test_fragmento_trae_todos_sus_campos(embedding_congelamiento):
    vector, _ = embedding_congelamiento
    f = buscar("p", embeber=lambda _p: vector).fragmentos[0]
    assert isinstance(f, Fragmento)
    assert f.documento and f.archivo.endswith(".pdf") and f.texto
    assert isinstance(f.pagina, int) and isinstance(f.similitud, float)
