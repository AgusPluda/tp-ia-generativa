"""Invariantes del generador de datos (data-model.md, "Invariantes que debe cumplir...").

El esquema no los impone con restricciones: el generador los garantiza por construcción y
estos tests lo verifican sobre las filas en memoria, sin base.
"""

import calendar
from collections import Counter
from datetime import date, timedelta

from gym_agent.config import HISTORY_START, REFERENCE_DATE
from gym_agent.synthetic import generar_datos
from gym_agent.synthetic.catalog import DIAS_SEMANA, MEDIOS_PAGO, PLANES, REGLAS, TIPOS_EQUIPO

INICIO_ULTIMO_MES = REFERENCE_DATE - timedelta(days=29)
MES_REFERENCIA = REFERENCE_DATE.replace(day=1)


def fin_de_mes(mes: date) -> date:
    """Último día del mes de `mes`."""
    return mes.replace(day=calendar.monthrange(mes.year, mes.month)[1])


def por_id(filas: list[dict], clave: str) -> dict[int, dict]:
    return {f[clave]: f for f in filas}


# --- (1) Fechas ---------------------------------------------------------------


def test_1_ninguna_fecha_supera_la_fecha_de_referencia(tablas):
    for tabla, filas in tablas.items():
        for fila in filas:
            for columna, valor in fila.items():
                if isinstance(valor, date):
                    assert valor <= REFERENCE_DATE, f"{tabla}.{columna} = {valor}"


def test_1_historial_desde_el_inicio(tablas):
    assert min(a["fecha"] for a in tablas["asistencias"]) >= HISTORY_START
    for p in tablas["pagos"]:
        assert p["mes_correspondiente"] >= HISTORY_START
        assert p["fecha_pago"] is None or p["fecha_pago"] >= HISTORY_START
    for e in tablas["equipamiento"]:
        assert e["ultimo_mantenimiento"] is None or e["ultimo_mantenimiento"] >= HISTORY_START


# --- (2) Asistencias coherentes con la clase y el alta ------------------------


def test_2_asistencia_en_el_dia_de_la_clase_y_despues_del_alta(tablas):
    clases = por_id(tablas["clases"], "id_clase")
    socios = por_id(tablas["socios"], "id_socio")
    for a in tablas["asistencias"]:
        dia = clases[a["id_clase"]]["dia_semana"]
        assert DIAS_SEMANA[a["fecha"].weekday()] == dia, a
        assert a["fecha"] >= socios[a["id_socio"]]["fecha_alta"], a


# --- (3) Estado del socio y asistencias ---------------------------------------


def test_3_socio_de_baja_sin_asistencias_posteriores_a_su_salida(tablas):
    """La salida no se guarda; se acota con el último mes pagado y con la ventana del último mes."""
    bajas = [s["id_socio"] for s in tablas["socios"] if s["estado"] == "baja"]
    assert bajas
    for id_socio in bajas:
        meses = [p["mes_correspondiente"] for p in tablas["pagos"] if p["id_socio"] == id_socio]
        fechas = [a["fecha"] for a in tablas["asistencias"] if a["id_socio"] == id_socio]
        assert MES_REFERENCIA not in meses, f"socio {id_socio} de baja paga el mes en curso"
        if fechas:
            assert max(fechas) < INICIO_ULTIMO_MES
            assert max(fechas) <= fin_de_mes(max(meses))


def test_3_congelado_sin_ninguna_asistencia_en_el_ultimo_mes(tablas):
    congelados = {s["id_socio"] for s in tablas["socios"] if s["estado"] == "congelado"}
    assert congelados
    en_ventana = [
        a for a in tablas["asistencias"]
        if a["id_socio"] in congelados and a["fecha"] >= INICIO_ULTIMO_MES
    ]
    assert en_ventana == []


def test_3_faltas_del_ultimo_mes_solo_de_socios_activos(tablas):
    socios = por_id(tablas["socios"], "id_socio")
    for a in tablas["asistencias"]:
        if not a["presente"] and a["fecha"] >= INICIO_ULTIMO_MES:
            assert socios[a["id_socio"]]["estado"] == "activo", a


# --- (4) Pagos: estado, fecha y regla de mora ---------------------------------


def test_4_fecha_de_pago_segun_el_estado(tablas):
    for p in tablas["pagos"]:
        if p["estado"] == "pagado":
            assert p["fecha_pago"] is not None, p
        else:
            assert p["fecha_pago"] is None, p


def test_4_la_cuota_se_paga_durante_su_mes(tablas):
    socios = por_id(tablas["socios"], "id_socio")
    for p in tablas["pagos"]:
        mes = p["mes_correspondiente"]
        assert mes.day == 1, p
        if p["estado"] == "pagado":
            assert mes <= p["fecha_pago"] <= fin_de_mes(mes), p
            assert p["fecha_pago"] >= socios[p["id_socio"]]["fecha_alta"], p


def test_4b_regla_de_mora(tablas):
    gracia = timedelta(days=REGLAS.mora_dias_para_vencido)
    for p in tablas["pagos"]:
        mes = p["mes_correspondiente"]
        if p["estado"] == "pendiente":
            assert mes == MES_REFERENCIA, p
        if p["estado"] == "vencido":
            assert fin_de_mes(mes) + gracia < REFERENCE_DATE, p


# --- (5) Un pago por mes y monto del plan -------------------------------------


def test_5_un_pago_por_socio_y_mes(tablas):
    claves = Counter((p["id_socio"], p["mes_correspondiente"]) for p in tablas["pagos"])
    assert max(claves.values()) == 1


def test_5_monto_igual_al_precio_del_plan(tablas):
    socios = por_id(tablas["socios"], "id_socio")
    planes = por_id(tablas["planes"], "id_plan")
    for p in tablas["pagos"]:
        plan = planes[socios[p["id_socio"]]["id_plan"]]
        assert p["monto"] == plan["precio_mensual"], p


def test_5_ningun_pago_anterior_al_alta(tablas):
    socios = por_id(tablas["socios"], "id_socio")
    for p in tablas["pagos"]:
        alta = socios[p["id_socio"]]["fecha_alta"]
        assert p["mes_correspondiente"] >= alta.replace(day=1), p


# --- (6) Equipamiento ---------------------------------------------------------


def test_6_tipo_de_equipo_del_manual_y_mantenimiento_posterior_a_la_compra(tablas):
    for e in tablas["equipamiento"]:
        assert e["tipo"] in TIPOS_EQUIPO, e
        if e["ultimo_mantenimiento"] is not None:
            assert e["ultimo_mantenimiento"] >= e["fecha_adquisicion"], e


# --- (7) Faltas explícitas ----------------------------------------------------


def test_7_hay_faltas_registradas(tablas):
    assert any(not a["presente"] for a in tablas["asistencias"])


# --- (8) Claves únicas y determinismo -----------------------------------------


def test_8_claves_unicas(tablas):
    emails = [s["email"] for s in tablas["socios"]]
    assert len(emails) == len(set(emails))
    asistencias = [(a["id_socio"], a["id_clase"], a["fecha"]) for a in tablas["asistencias"]]
    assert len(asistencias) == len(set(asistencias))
    nombres_plan = [p["nombre"] for p in tablas["planes"]]
    assert len(nombres_plan) == len(set(nombres_plan))


def test_8_dos_generaciones_son_identicas(datos):
    assert generar_datos() == datos


# --- Valores admitidos por el esquema (CHECK y VARCHAR) -----------------------


def test_valores_admitidos_por_el_esquema(tablas):
    assert [p["nombre"] for p in tablas["planes"]] == [p.nombre for p in PLANES]
    for s in tablas["socios"]:
        assert s["estado"] in ("activo", "congelado", "baja")
        assert len(s["nombre"]) <= 60 and len(s["apellido"]) <= 60 and len(s["email"]) <= 120
        assert s["fecha_nacimiento"] < s["fecha_alta"]
    for i in tablas["instructores"]:
        assert len(i["especialidad"]) <= 60
    for c in tablas["clases"]:
        assert c["dia_semana"] in DIAS_SEMANA
        assert c["cupo"] > 0 and len(c["nombre"]) <= 60 and len(c["sala"]) <= 30
    for p in tablas["pagos"]:
        assert p["monto"] > 0
        assert p["medio_pago"] in MEDIOS_PAGO
        assert p["estado"] in ("pagado", "pendiente", "vencido")
    for e in tablas["equipamiento"]:
        assert e["estado"] in ("operativo", "en_mantenimiento", "fuera_de_servicio")
        assert len(e["nombre"]) <= 80 and len(e["tipo"]) <= 40 and len(e["sala"]) <= 30


def test_cupo_de_cada_clase_respetado(tablas):
    """En ninguna fecha una clase tiene más reservas que su cupo."""
    cupos = {c["id_clase"]: c["cupo"] for c in tablas["clases"]}
    por_sesion = Counter((a["id_clase"], a["fecha"]) for a in tablas["asistencias"])
    for (id_clase, _), reservas in por_sesion.items():
        assert reservas <= cupos[id_clase]
