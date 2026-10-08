"""Carga y validación de la batería de evaluación (`eval/battery.yaml`), sin LLM ni base."""

from collections import Counter

import pytest

from eval.battery import BateriaInvalida, cargar_bateria
from gym_agent.presentacion import secciones_bateria
from gym_agent.synthetic.catalog import CLAVES_HECHOS, DOCUMENTOS

TIPO_POR_SECCION = {"Solo SQL": "sql", "Solo RAG": "rag", "Híbridas": "hibrida", "Casos borde": "borde"}


@pytest.fixture(scope="module")
def bateria():
    return cargar_bateria()


def _tipos(chequeos):
    return [c.tipo for c in chequeos]


def test_son_26_preguntas_con_ids_unicos_y_el_reparto_del_contrato(bateria):
    assert len(bateria) == 26
    assert len({p.id for p in bateria}) == 26
    assert Counter(p.tipo for p in bateria) == {"sql": 7, "rag": 5, "hibrida": 4, "borde": 10}


def test_el_yaml_coincide_con_el_markdown_del_contrato(bateria):
    por_id = {p.id: p for p in bateria}
    del_markdown = []
    for seccion in secciones_bateria():
        tipo = next(t for titulo, t in TIPO_POR_SECCION.items() if seccion.titulo.startswith(titulo))
        for fila in seccion.preguntas:
            del_markdown.append(fila.id)
            assert fila.id in por_id, f"{fila.id} está en eval-battery.md y no en battery.yaml"
            assert por_id[fila.id].pregunta == fila.pregunta, fila.id
            assert por_id[fila.id].tipo == tipo, fila.id
    assert [p.id for p in bateria] == del_markdown


def test_ce001_toda_pregunta_declara_al_menos_un_chequeo(bateria):
    assert all(p.chequeos for p in bateria)


def test_los_placeholders_se_reemplazan(bateria):
    sqls = [c.sql for p in bateria for c in p.chequeos if c.tipo == "contiene_valores_de_sql"]
    assert sqls and all("{{" not in sql for sql in sqls)
    h04 = next(c.sql for p in bateria if p.id == "H04" for c in p.chequeos if c.tipo == "contiene_valores_de_sql")
    assert "2026-09-30" in h04
    assert "30" in h04


def test_hechos_y_documentos_existen_en_el_catalogo(bateria):
    titulos = {d.titulo for d in DOCUMENTOS.values()}
    for p in bateria:
        for c in p.chequeos:
            if c.tipo == "contiene_hecho":
                assert c.hecho in CLAVES_HECHOS, p.id
            if c.tipo == "documento_citado":
                assert c.documento in titulos, p.id


def test_fuentes_esperadas_validas_y_las_hibridas_esperan_ambas(bateria):
    for p in bateria:
        assert p.fuentes_esperadas and set(p.fuentes_esperadas) <= {"sql", "rag", "ambas", "ninguna"}, p.id
        if p.tipo == "hibrida":
            assert p.fuentes_esperadas == ["ambas"], p.id


def test_b01_y_b02_rechazan_la_modificacion_y_verifican_la_base(bateria):
    por_id = {p.id: p for p in bateria}
    for id_ in ("B01", "B02"):
        chequeos = por_id[id_].chequeos
        assert "base_intacta" in _tipos(chequeos)
        assert any(c.tipo == "rechazo" and c.motivo == "modificacion" for c in chequeos)


def test_el_juez_solo_aparece_en_b04_b05_b07_y_b08(bateria):
    con_juez = {p.id for p in bateria if "juez" in _tipos(p.chequeos)}
    assert con_juez == {"B04", "B05", "B07", "B08"}


# --- BateriaInvalida ----------------------------------------------------------------------


def _pregunta(id_="X01", **cambios):
    base = {
        "id": id_,
        "tipo": "rag",
        "pregunta": "¿Algo?",
        "fuentes_esperadas": ["rag"],
        "chequeos": [{"tipo": "contiene_hecho", "hecho": "congelamiento_max_dias"}],
    }
    base.update(cambios)
    return base


def _escribir(tmp_path, preguntas):
    import yaml

    ruta = tmp_path / "battery.yaml"
    ruta.write_text(yaml.safe_dump(preguntas, allow_unicode=True), encoding="utf-8")
    return ruta


def _veinte(**cambios_primera):
    preguntas = [_pregunta(f"X{i:02d}") for i in range(20)]
    preguntas[0] = _pregunta("X00", **cambios_primera)
    return preguntas


def test_una_bateria_minima_valida_carga(tmp_path):
    assert len(cargar_bateria(_escribir(tmp_path, _veinte()))) == 20


def test_falla_si_faltan_claves_obligatorias(tmp_path):
    preguntas = _veinte()
    del preguntas[3]["pregunta"]
    with pytest.raises(BateriaInvalida):
        cargar_bateria(_escribir(tmp_path, preguntas))


def test_falla_con_un_tipo_de_chequeo_inexistente(tmp_path):
    with pytest.raises(BateriaInvalida):
        cargar_bateria(_escribir(tmp_path, _veinte(chequeos=[{"tipo": "inventado"}])))


def test_falla_con_un_id_repetido(tmp_path):
    preguntas = _veinte()
    preguntas[5]["id"] = "X00"
    with pytest.raises(BateriaInvalida):
        cargar_bateria(_escribir(tmp_path, preguntas))


def test_falla_si_una_pregunta_no_tiene_chequeos(tmp_path):
    with pytest.raises(BateriaInvalida):
        cargar_bateria(_escribir(tmp_path, _veinte(chequeos=[])))


def test_falla_con_menos_de_veinte_preguntas(tmp_path):
    with pytest.raises(BateriaInvalida):
        cargar_bateria(_escribir(tmp_path, _veinte()[:19]))


def test_falla_con_una_clave_de_hecho_inexistente(tmp_path):
    chequeos = [{"tipo": "contiene_hecho", "hecho": "no_existe"}]
    with pytest.raises(BateriaInvalida):
        cargar_bateria(_escribir(tmp_path, _veinte(chequeos=chequeos)))


def test_falla_con_una_fuente_esperada_invalida(tmp_path):
    with pytest.raises(BateriaInvalida):
        cargar_bateria(_escribir(tmp_path, _veinte(fuentes_esperadas=["web"])))


def test_falla_con_un_documento_que_no_existe(tmp_path):
    chequeos = [{"tipo": "documento_citado", "documento": "Manual inventado"}]
    with pytest.raises(BateriaInvalida):
        cargar_bateria(_escribir(tmp_path, _veinte(chequeos=chequeos)))
