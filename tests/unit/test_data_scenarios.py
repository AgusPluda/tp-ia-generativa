"""Escenarios plantados en los datos (research R7) para que la batería no tenga respuestas triviales."""

from collections import Counter
from datetime import timedelta

from gym_agent.config import REFERENCE_DATE
from gym_agent.synthetic.catalog import TIPOS_EQUIPO

INICIO_ULTIMO_MES = REFERENCE_DATE - timedelta(days=29)


def test_instructor_con_mas_asistencias_del_ultimo_mes_es_unico(tablas):
    """Pregunta S02: el primero tiene estrictamente más asistencias presentes que el segundo."""
    instructor_de = {c["id_clase"]: c["id_instructor"] for c in tablas["clases"]}
    conteo = Counter(
        instructor_de[a["id_clase"]]
        for a in tablas["asistencias"]
        if a["presente"] and a["fecha"] >= INICIO_ULTIMO_MES
    )
    (_, primero), (_, segundo) = conteo.most_common(2)
    assert primero > segundo


def test_al_menos_cinco_socios_con_faltas_en_el_ultimo_mes(tablas):
    """Preguntas H01: socios con `presente = false` en la ventana."""
    socios = {
        a["id_socio"]
        for a in tablas["asistencias"]
        if not a["presente"] and a["fecha"] >= INICIO_ULTIMO_MES
    }
    assert len(socios) >= 5


def test_entre_cuatro_y_seis_pagos_vencidos(tablas):
    """Preguntas S03 y H03."""
    vencidos = [p for p in tablas["pagos"] if p["estado"] == "vencido"]
    assert 4 <= len(vencidos) <= 6


def test_hay_pagos_pendientes_del_mes_en_curso(tablas):
    """Un `pendiente` no es vencido: tiene que existir para que la distinción se pueda probar."""
    assert any(p["estado"] == "pendiente" for p in tablas["pagos"])


def test_entre_tres_y_cuatro_equipos_en_mantenimiento(tablas):
    """Pregunta H02."""
    en_mantenimiento = [e for e in tablas["equipamiento"] if e["estado"] == "en_mantenimiento"]
    assert 3 <= len(en_mantenimiento) <= 4


def test_hay_equipos_fuera_de_servicio(tablas):
    """Pregunta S07: el conteo no debe ser cero."""
    assert any(e["estado"] == "fuera_de_servicio" for e in tablas["equipamiento"])


def test_hay_cintas_con_mantenimiento_atrasado(tablas):
    """Pregunta H04: cinta con último mantenimiento anterior a la frecuencia del manual."""
    limite = REFERENCE_DATE - timedelta(days=TIPOS_EQUIPO["Cinta de correr"])
    atrasadas = [
        e for e in tablas["equipamiento"]
        if e["tipo"] == "Cinta de correr"
        and e["ultimo_mantenimiento"] is not None
        and e["ultimo_mantenimiento"] < limite
    ]
    assert atrasadas


def test_conteos_minimos_rf002(tablas):
    """RF-002: más de 15 filas en al menos cinco tablas."""
    for tabla in ("socios", "clases", "asistencias", "pagos", "equipamiento"):
        assert len(tablas[tabla]) > 15, tabla
