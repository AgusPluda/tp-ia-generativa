"""El texto de los PDFs es coherente con `catalog.py` y no pisa datos de la base (principio III)."""

import re

import pytest

from gym_agent.synthetic.catalog import (
    CLAVES_HECHOS,
    COMIDA_PRE_ENTRENAMIENTO_HORAS,
    DOCUMENTOS,
    PLANES,
    REGLAS,
    TIPOS_EQUIPO,
)
from gym_agent.synthetic.pdf_content import CONTENIDOS, texto_documento


def _normalizar(texto: str) -> str:
    return " ".join(texto.split())


def test_hay_contenido_para_cada_documento_del_catalogo():
    assert set(CONTENIDOS) == set(DOCUMENTOS)
    for id_documento, contenido in CONTENIDOS.items():
        assert contenido.documento == DOCUMENTOS[id_documento]


@pytest.mark.parametrize("id_documento", list(DOCUMENTOS))
def test_cada_documento_tiene_de_3_a_6_paginas(id_documento):
    assert 3 <= len(CONTENIDOS[id_documento].paginas) <= 6


@pytest.mark.parametrize("clave", list(CLAVES_HECHOS))
def test_cada_hecho_aparece_literal_en_su_documento(clave):
    id_documento, esperado = CLAVES_HECHOS[clave]
    assert _normalizar(esperado) in _normalizar(texto_documento(id_documento))


def test_el_reglamento_publica_los_plazos_de_reglas():
    texto = _normalizar(texto_documento("reglamento_interno"))
    for valor in (
        f"{REGLAS.congelamiento_max_dias} días",
        f"{REGLAS.congelamiento_max_veces_anio} veces",
        f"{REGLAS.congelamiento_aviso_horas} horas",
        f"{REGLAS.mora_dias_para_vencido} días",
        f"{REGLAS.mora_dias_suspension} días",
        f"{REGLAS.baja_aviso_dias} días",
        f"{REGLAS.cancelacion_anticipacion_horas} horas",
        f"{REGLAS.faltas_sin_aviso_limite} faltas",
    ):
        assert valor in texto


def test_la_guia_publica_frecuencia_de_principiantes_y_comida_previa():
    texto = _normalizar(texto_documento("guia_rutinas_nutricion"))
    assert f"{REGLAS.rutina_principiante_dias_semana} días por semana" in texto
    assert COMIDA_PRE_ENTRENAMIENTO_HORAS in texto


def test_el_manual_tiene_una_seccion_por_tipo_de_equipo_con_su_frecuencia():
    """Las secciones se llaman igual que `equipamiento.tipo` y cada una trae solo su frecuencia."""
    secciones = {
        s.titulo: _normalizar(" ".join(s.parrafos))
        for pagina in CONTENIDOS["manual_equipamiento"].paginas
        for s in pagina
    }
    for tipo, dias in TIPOS_EQUIPO.items():
        assert tipo in secciones, f"falta la sección {tipo!r} en el manual"
        assert f"{dias} días" in secciones[tipo]
        otras = {f"{d} días" for t, d in TIPOS_EQUIPO.items() if d != dias}
        assert not any(o in secciones[tipo] for o in otras), f"la sección {tipo!r} mezcla frecuencias"


_PATRONES_MONTO = (
    r"\$",
    r"\bpesos\b",
    r"\bARS\b",
    r"\d{1,3}(?:\.\d{3})+",  # 35.000
    r"\d{4,}",  # 35000
)


@pytest.mark.parametrize("id_documento", list(DOCUMENTOS))
def test_ningun_documento_contiene_precios_ni_montos(id_documento):
    texto = texto_documento(id_documento)
    for patron in _PATRONES_MONTO:
        assert not re.search(patron, texto, flags=re.IGNORECASE), f"{patron!r} en {id_documento}"
    for plan in PLANES:
        assert str(int(plan.precio_mensual)) not in texto


@pytest.mark.parametrize("id_documento", list(DOCUMENTOS))
def test_ningun_documento_habla_de_estacionamiento(id_documento):
    """La pregunta B08 espera que los documentos no cubran el tema."""
    assert "estacionamiento" not in texto_documento(id_documento).lower()
