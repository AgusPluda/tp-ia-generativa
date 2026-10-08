"""Criterios de aceptación de la evaluación (`eval.criteria`), sin LLM ni base."""

import pytest

from eval.battery import BaseIntacta, PreguntaEval
from eval.checks import ResultadoChequeo
from eval.criteria import (
    ResultadoCorrida,
    ResultadoPregunta,
    calcular_criterios,
    ce001,
    ce002,
    ce003,
    ce004,
    duraciones,
    tasa_por_pregunta,
    veredicto,
)


def _pregunta_eval(id_: str, *, con_chequeos: bool = True) -> PreguntaEval:
    """Pregunta de la batería; `model_construct` permite armar una sin chequeos (el YAML no lo deja)."""
    chequeos = [BaseIntacta(tipo="base_intacta")] if con_chequeos else []
    return PreguntaEval.model_construct(
        id=id_, tipo="sql", pregunta="¿?", fuentes_esperadas=["sql"], chequeos=chequeos
    )


def _p(
    id_: str,
    *,
    tipo: str = "sql",
    ok: bool = True,
    fuentes: str = "sql",
    modificacion: bool = False,
    duracion_ms: int = 1000,
) -> ResultadoPregunta:
    return ResultadoPregunta(
        id=id_,
        tipo=tipo,
        aprobada=ok,
        fuentes_usadas=fuentes,
        es_modificacion=modificacion,
        duracion_ms=duracion_ms,
    )


def _corrida(preguntas: list[ResultadoPregunta], tablas_modificadas: tuple[str, ...] = ()) -> ResultadoCorrida:
    return ResultadoCorrida(preguntas=tuple(preguntas), tablas_modificadas=tablas_modificadas)


def _corrida_de_26(aprobadas: int) -> ResultadoCorrida:
    """26 preguntas de las que aprueban las primeras `aprobadas`."""
    return _corrida([_p(f"Q{i:02d}", ok=i < aprobadas) for i in range(26)])


# --- CE-001 -------------------------------------------------------------------------------------


def test_ce001_cumple_con_26_preguntas_con_chequeos():
    assert ce001([_pregunta_eval(f"Q{i}") for i in range(26)]).cumple


def test_ce001_cumple_justo_en_el_minimo_de_20():
    assert ce001([_pregunta_eval(f"Q{i}") for i in range(20)]).cumple


def test_ce001_no_cumple_con_19_preguntas():
    criterio = ce001([_pregunta_eval(f"Q{i}") for i in range(19)])
    assert not criterio.cumple
    assert "19" in criterio.detalle


def test_ce001_no_cumple_si_una_pregunta_no_tiene_chequeos():
    preguntas = [_pregunta_eval(f"Q{i}") for i in range(25)] + [_pregunta_eval("SIN", con_chequeos=False)]
    criterio = ce001(preguntas)
    assert not criterio.cumple
    assert "SIN" in criterio.detalle


# --- CE-002 -------------------------------------------------------------------------------------


def test_ce002_cumple_con_23_de_26():
    criterio = ce002([_corrida_de_26(23)])
    assert criterio.cumple
    assert criterio.valor == pytest.approx(23 / 26)


def test_ce002_no_cumple_con_22_de_26():
    criterio = ce002([_corrida_de_26(22)])
    assert not criterio.cumple
    assert criterio.valor == pytest.approx(22 / 26)


def test_ce002_cumple_justo_en_el_umbral():
    corrida = _corrida([_p(f"Q{i}", ok=i < 17) for i in range(20)])
    assert ce002([corrida], umbral=0.85).cumple


def test_ce002_con_varias_corridas_usa_el_promedio_y_informa_la_minima_y_cada_tasa():
    # 26/26 y 22/26: promedio 0,923 (cumple) aunque una corrida quede por debajo del umbral.
    criterio = ce002([_corrida_de_26(26), _corrida_de_26(22)])
    assert criterio.cumple
    assert criterio.valor == pytest.approx((1 + 22 / 26) / 2)
    assert criterio.tasas == pytest.approx((1.0, 22 / 26))
    assert criterio.minima == pytest.approx(22 / 26)


def test_ce002_el_promedio_puede_no_alcanzar_aunque_una_corrida_si():
    criterio = ce002([_corrida_de_26(24), _corrida_de_26(20), _corrida_de_26(20)])
    assert not criterio.cumple


def test_ce002_sin_corridas_no_cumple():
    assert not ce002([]).cumple


def test_ce002_el_detalle_muestra_el_porcentaje_con_coma():
    assert "88,5" in ce002([_corrida_de_26(23)]).detalle


# --- CE-003 -------------------------------------------------------------------------------------


def _con_modificaciones(*aprobadas: bool) -> list[ResultadoPregunta]:
    return [_p("S01")] + [_p(f"B0{i}", ok=ok, modificacion=True) for i, ok in enumerate(aprobadas, start=1)]


def test_ce003_cumple_si_todas_las_de_modificacion_aprueban_y_la_base_no_cambio():
    assert ce003([_corrida(_con_modificaciones(True, True))]).cumple


def test_ce003_falla_si_una_pregunta_de_modificacion_no_aprueba():
    criterio = ce003([_corrida(_con_modificaciones(True, False))])
    assert not criterio.cumple
    assert "B02" in criterio.detalle


def test_ce003_falla_si_cambio_un_hash_aunque_las_preguntas_hayan_aprobado():
    criterio = ce003([_corrida(_con_modificaciones(True, True), tablas_modificadas=("pagos",))])
    assert not criterio.cumple
    assert "pagos" in criterio.detalle


def test_ce003_una_modificacion_en_cualquier_pregunta_hace_fallar():
    # El cambio ocurrió durante una pregunta que no es de modificación (S01): igual falla.
    corrida = _corrida([_p("S01"), *_con_modificaciones(True)[1:]], tablas_modificadas=("socios",))
    assert not ce003([corrida]).cumple


def test_ce003_con_varias_corridas_exige_cumplirse_en_todas():
    buena = _corrida(_con_modificaciones(True, True))
    mala = _corrida(_con_modificaciones(True, False))
    assert ce003([buena, buena]).cumple
    assert not ce003([buena, mala]).cumple


def test_ce003_sin_preguntas_de_modificacion_no_cumple():
    criterio = ce003([_corrida([_p("S01")])])
    assert not criterio.cumple
    assert "modificaci" in criterio.detalle


# --- CE-004 -------------------------------------------------------------------------------------


def _hibridas(*fuentes: str, ok: bool = True) -> list[ResultadoPregunta]:
    return [_p("S01")] + [_p(f"H0{i}", tipo="hibrida", fuentes=f, ok=ok) for i, f in enumerate(fuentes, start=1)]


def test_ce004_cumple_si_todas_las_hibridas_usaron_ambas():
    assert ce004([_corrida(_hibridas("ambas", "ambas"))]).cumple


def test_ce004_falla_si_una_hibrida_uso_una_sola_fuente():
    criterio = ce004([_corrida(_hibridas("ambas", "sql"))])
    assert not criterio.cumple
    assert "H02" in criterio.detalle


def test_ce004_mira_las_fuentes_aunque_otros_chequeos_hayan_fallado():
    assert ce004([_corrida(_hibridas("ambas", "ambas", ok=False))]).cumple


def test_ce004_no_mira_las_preguntas_que_no_son_hibridas():
    corrida = _corrida([_p("S01", fuentes="sql"), *_hibridas("ambas")[1:]])
    assert ce004([corrida]).cumple


def test_ce004_con_varias_corridas_exige_cumplirse_en_todas():
    buena = _corrida(_hibridas("ambas"))
    mala = _corrida(_hibridas("rag"))
    assert not ce004([buena, mala]).cumple


def test_ce004_sin_hibridas_no_cumple():
    assert not ce004([_corrida([_p("S01")])]).cumple


# --- veredicto y tasas ---------------------------------------------------------------------------


def _bateria_y_corrida(aprobadas: int = 26, fuente_h: str = "ambas"):
    preguntas = [_pregunta_eval(f"Q{i:02d}") for i in range(26)]
    resultados = [_p(f"Q{i:02d}", ok=i < aprobadas) for i in range(24)]
    resultados.append(_p("B01", ok=True, modificacion=True))
    resultados.append(_p("H01", tipo="hibrida", fuentes=fuente_h, ok=True))
    return preguntas, [_corrida(resultados)]


def test_calcular_criterios_devuelve_los_cuatro_en_orden():
    criterios = calcular_criterios(*_bateria_y_corrida())
    assert [c.nombre for c in criterios] == ["CE-001", "CE-002", "CE-003", "CE-004"]


def test_veredicto_es_0_si_se_cumplen_los_cuatro():
    assert veredicto(calcular_criterios(*_bateria_y_corrida())) == 0


def test_veredicto_es_1_si_falla_alguno():
    assert veredicto(calcular_criterios(*_bateria_y_corrida(aprobadas=10))) == 1
    assert veredicto(calcular_criterios(*_bateria_y_corrida(fuente_h="sql"))) == 1


def test_tasa_por_pregunta_cuenta_aprobadas_sobre_corridas():
    corridas = [
        _corrida([_p("S01", ok=True), _p("S02", ok=False)]),
        _corrida([_p("S01", ok=True), _p("S02", ok=False)]),
        _corrida([_p("S01", ok=False), _p("S02", ok=False)]),
    ]
    tasas = tasa_por_pregunta(corridas)
    assert list(tasas) == ["S01", "S02"]
    assert str(tasas["S01"]) == "2/3"
    assert str(tasas["S02"]) == "0/3"


def test_duraciones_devuelve_la_mediana_y_la_maxima():
    corrida = _corrida([_p("A", duracion_ms=1000), _p("B", duracion_ms=3000), _p("C", duracion_ms=9000)])
    assert duraciones([corrida]) == (3000, 9000)


def test_el_motivo_de_una_pregunta_reune_los_chequeos_que_fallaron():
    pregunta = ResultadoPregunta(
        id="S01",
        tipo="sql",
        aprobada=False,
        fuentes_usadas="sql",
        chequeos=(
            ResultadoChequeo("contiene_valores_de_sql", False, "Falta 'Ana'"),
            ResultadoChequeo("idioma", True),
        ),
    )
    assert pregunta.motivo == "Falta 'Ana'"
    assert _p("S02").motivo == ""
