"""Lógica de presentación de la interfaz (sin LLM, base ni Streamlit)."""

import pytest

from gym_agent.config import REPO_ROOT
from gym_agent.graph.state import FuenteDocumental, RespuestaAgente
from gym_agent.presentacion import EJEMPLOS, documentos_citados, escapar_markdown, etiqueta_ruta


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


def test_ejemplos_son_tres_distintas_y_no_vacias():
    assert len(EJEMPLOS) == 3
    assert len(set(EJEMPLOS)) == 3
    assert all(ejemplo.strip() for ejemplo in EJEMPLOS)


def test_ejemplos_figuran_literales_en_la_bateria():
    bateria = (REPO_ROOT / "specs" / "001-agente-sql-rag-gimnasio" / "contracts" / "eval-battery.md").read_text(
        encoding="utf-8"
    )
    for ejemplo in EJEMPLOS:
        assert ejemplo in bateria
