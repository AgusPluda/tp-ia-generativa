"""Lógica de presentación de la interfaz (sin LLM, base ni Streamlit)."""

import pytest

from gym_agent.config import REPO_ROOT
from gym_agent.graph.state import FuenteDocumental, RespuestaAgente
from gym_agent.presentacion import (
    EJEMPLOS,
    Ejemplo,
    PreguntaBateria,
    documentos_citados,
    escapar_markdown,
    etiqueta_ruta,
    secciones_bateria,
    tabla_markdown,
    url_phoenix,
)


def respuesta(ruta="sql", *, fallo=False, motivo=None, fuentes=()):
    return RespuestaAgente(
        respuesta="texto", ruta=ruta, idioma="es", duracion_ms=1,
        motivo_rechazo=motivo, fallo=fallo, fuentes_documentales=list(fuentes),
    )


@pytest.mark.parametrize(
    ("ruta", "etiqueta"),
    [("sql", "Base de datos"), ("rag", "Documentos"), ("ambas", "Ambas")],
)
def test_etiqueta_de_cada_ruta(ruta, etiqueta):
    assert etiqueta_ruta(respuesta(ruta)) == etiqueta


@pytest.mark.parametrize("motivo", ["fuera_de_dominio", "modificacion", "falta_contexto"])
def test_rechazo_es_rechazada_con_cualquier_motivo(motivo):
    assert etiqueta_ruta(respuesta("rechazar", motivo=motivo)) == "Rechazada"


@pytest.mark.parametrize("ruta", ["sql", "rag", "ambas", "rechazar"])
def test_fallo_es_no_disponible_con_cualquier_ruta(ruta):
    motivo = "modificacion" if ruta == "rechazar" else None
    assert etiqueta_ruta(respuesta(ruta, fallo=True, motivo=motivo)) == "No disponible"


def test_documentos_citados_con_y_sin_pagina():
    fuentes = [
        FuenteDocumental(documento="Reglamento interno", pagina=3),
        FuenteDocumental(documento="Manual de equipos", pagina=None),
    ]
    assert documentos_citados(respuesta("rag", fuentes=fuentes)) == [
        "Reglamento interno, p. 3",
        "Manual de equipos",
    ]


def test_documentos_citados_sin_fuentes():
    assert documentos_citados(respuesta("rag")) == []


def test_escapar_cada_signo_pesos():
    escapado = escapar_markdown("Cuota de $15.000 y $20.000")
    assert escapado == r"Cuota de \$15.000 y \$20.000"


def test_texto_sin_pesos_queda_igual():
    assert escapar_markdown("Hay 12 socios") == "Hay 12 socios"


def test_pesos_ya_escapado_no_se_escapa_dos_veces():
    assert escapar_markdown(r"Cuota de \$15.000 y $20.000") == r"Cuota de \$15.000 y \$20.000"


BATERIA_MD = REPO_ROOT / "specs" / "001-agente-sql-rag-gimnasio" / "contracts" / "eval-battery.md"


def test_ejemplos_son_tres_distintos_con_etiqueta_corta():
    assert len(EJEMPLOS) == 3
    assert all(isinstance(e, Ejemplo) for e in EJEMPLOS)
    assert [e.etiqueta for e in EJEMPLOS] == [
        "Socios por plan",
        "Congelamiento de cuota",
        "Equipos en mantenimiento",
    ]
    assert len({e.pregunta for e in EJEMPLOS}) == 3
    assert all(e.etiqueta.strip() and e.pregunta.strip() for e in EJEMPLOS)


def test_ejemplos_figuran_literales_en_la_bateria():
    bateria = BATERIA_MD.read_text(encoding="utf-8")
    for ejemplo in EJEMPLOS:
        assert ejemplo.pregunta in bateria


def test_secciones_de_la_bateria():
    secciones = secciones_bateria()
    assert [s.titulo for s in secciones] == [
        "Solo SQL (7)", "Solo RAG (5)", "Híbridas (4)", "Casos borde (10)",
    ]
    assert [len(s.preguntas) for s in secciones] == [7, 5, 4, 10]
    ids = [p.id for s in secciones for p in s.preguntas]
    assert len(ids) == 26
    assert len(set(ids)) == 26


def test_primera_pregunta_y_chequeo_con_codigo():
    todas = {p.id: p for s in secciones_bateria() for p in s.preguntas}
    assert todas["S01"].pregunta == "¿Cuántos socios tiene cada plan?"
    assert "UPDATE socios SET estado = 'baja'" in todas["B02"].pregunta
    assert "`rechazo: modificacion`" in todas["B02"].chequeo


def test_ejemplos_son_preguntas_de_la_bateria():
    preguntas = {p.pregunta for s in secciones_bateria() for p in s.preguntas}
    assert {e.pregunta for e in EJEMPLOS} <= preguntas


def test_tabla_markdown_arma_encabezado_y_filas():
    preguntas = [
        PreguntaBateria("X1", "Cuesta $5 | o $6", "usa `a | b`"),
        PreguntaBateria("X2", "Otra", "chequeo"),
    ]
    lineas = tabla_markdown(preguntas).splitlines()
    assert lineas[0] == "| ID | Pregunta | Chequeo principal |"
    assert set(lineas[1].replace("|", "").strip()) == {"-"}
    assert len(lineas) == 4
    assert lineas[2] == r"| X1 | Cuesta \$5 \| o \$6 | usa `a \| b` |"
    assert lineas[3] == "| X2 | Otra | chequeo |"


def test_tabla_markdown_de_la_bateria_real_tiene_una_fila_por_pregunta():
    for seccion in secciones_bateria():
        assert len(tabla_markdown(seccion.preguntas).splitlines()) == len(seccion.preguntas) + 2


def test_url_phoenix_deriva_del_endpoint():
    assert url_phoenix() == "http://localhost:6006"
