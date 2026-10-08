"""Chequeos determinísticos de la evaluación (`eval.checks`), sin LLM ni base."""

from decimal import Decimal

import pytest

from eval.battery import (
    BaseIntacta,
    ContieneHecho,
    ContieneValoresDeSql,
    DocumentoCitado,
    ErrorSql,
    Idioma,
    Juez,
    Rechazo,
    SinDocumentosCitados,
    SinFilas,
    SinVolcadoDeChunks,
)
from eval.checks import (
    Contexto,
    Intento,
    ResultadoChequeo,
    base_intacta,
    contiene_hecho,
    contiene_valores_de_sql,
    documento_citado,
    ejecutar_chequeo,
    error_sql,
    fuentes_ok,
    idioma,
    normalizar,
    rechazo,
    sin_documentos_citados,
    sin_filas,
    sin_volcado_de_chunks,
)
from gym_agent.graph.state import FuenteDocumental, RespuestaAgente

HASH = {"socios": "aaa", "pagos": "bbb", "clases": "ccc"}


def _intento(
    texto: str = "",
    *,
    ruta="sql",
    motivo=None,
    sql_ejecutado=None,
    fuentes=(),
    idioma_="es",
    fuentes_usadas="ninguna",
    traza=None,
    hash_antes=None,
    hash_despues=None,
) -> Intento:
    respuesta = RespuestaAgente(
        respuesta=texto,
        ruta=ruta,
        sql_ejecutado=sql_ejecutado,
        fuentes_documentales=[FuenteDocumental(documento=d, pagina=1) for d in fuentes],
        idioma=idioma_,
        duracion_ms=10,
        motivo_rechazo=motivo,
        fuentes_usadas=fuentes_usadas,
    )
    return Intento(
        respuesta=respuesta,
        traza=traza or {},
        hash_antes=HASH if hash_antes is None else hash_antes,
        hash_despues=HASH if hash_despues is None else hash_despues,
    )


# --- normalizar -------------------------------------------------------------------------------


def test_normalizar_quita_tildes_pasa_a_minusculas_y_colapsa_espacios():
    assert normalizar("  PÉREZ,\n  José   Ángel ") == "perez, jose angel"


def test_normalizar_trata_la_enie_como_una_n_en_ambos_lados():
    assert normalizar("Muñoz") == "munoz"
    assert normalizar("MUÑOZ") == normalizar("Munoz")


# --- contiene_valores_de_sql ------------------------------------------------------------------


def test_los_nombres_se_comparan_con_y_sin_tildes():
    filas = [("Martina", "Benítez")]
    assert contiene_valores_de_sql(_intento("La instructora es Martina Benitez."), filas).ok
    assert contiene_valores_de_sql(_intento("MARTINA BENÍTEZ"), filas).ok


@pytest.mark.parametrize("texto", ["$45.000,00", "45.000", "45000", "45,000", "Son $ 45.000 en total"])
def test_un_decimal_de_la_base_aparece_con_cualquier_formato_de_miles(texto):
    resultado = contiene_valores_de_sql(_intento(f"Se cobró {texto}."), [(Decimal("45000.00"),)])
    assert resultado.ok, resultado.detalle


def test_un_decimal_con_centavos_se_compara_con_coma_o_punto_decimal():
    assert contiene_valores_de_sql(_intento("Fueron $1.250,50"), [(Decimal("1250.50"),)]).ok
    assert contiene_valores_de_sql(_intento("Fueron 1250.5"), [(Decimal("1250.50"),)]).ok
    assert not contiene_valores_de_sql(_intento("Fueron $1.250,60"), [(Decimal("1250.50"),)]).ok


def test_un_5_no_coincide_con_el_15():
    assert not contiene_valores_de_sql(_intento("Hay 15 socios."), [(5,)]).ok
    assert contiene_valores_de_sql(_intento("Hay 5 socios."), [(5,)]).ok


def test_un_5_no_coincide_con_el_5_de_un_numero_mas_largo():
    assert not contiene_valores_de_sql(_intento("Hay 1.500 socios y 250 clases."), [(5,)]).ok


def test_un_entero_coincide_con_la_misma_cantidad_escrita_con_decimales():
    assert contiene_valores_de_sql(_intento("Hay 45,0 socios."), [(45,)]).ok


def test_si_falta_un_solo_valor_falla_y_el_detalle_lo_nombra():
    resultado = contiene_valores_de_sql(_intento("Ana Pérez tiene 8 socios."), [("Ana", "Pérez", 8, "Zulema")])
    assert not resultado.ok
    assert "Zulema" in resultado.detalle
    assert "Ana" not in resultado.detalle


def test_con_varias_filas_y_columnas_exige_todos_los_valores():
    filas = [("Anual", 8), ("Básico", 16), ("Estándar", 14)]
    completa = "Anual: 8, Básico: 16, Estándar: 14"
    assert contiene_valores_de_sql(_intento(completa), filas).ok
    incompleta = contiene_valores_de_sql(_intento("Anual: 8, Básico: 16"), filas)
    assert not incompleta.ok
    assert "Estándar" in incompleta.detalle


def test_el_detalle_no_copia_la_respuesta_entera():
    texto = "respuesta larga " * 50
    resultado = contiene_valores_de_sql(_intento(texto), [("Zulema",)])
    assert "respuesta larga" not in resultado.detalle


def test_un_nombre_no_coincide_con_una_palabra_mas_larga():
    assert not contiene_valores_de_sql(_intento("Mariana Pérez"), [("Ana",)]).ok


def test_el_resultado_lleva_el_tipo_del_chequeo():
    assert contiene_valores_de_sql(_intento("5"), [(5,)]).tipo == "contiene_valores_de_sql"


# --- contiene_hecho ---------------------------------------------------------------------------


@pytest.mark.parametrize("texto", ["hasta 30 días", "HASTA 30 DÍAS", "30 dias corridos"])
def test_el_hecho_se_acepta_con_distinta_capitalizacion_y_tildes(texto):
    assert contiene_hecho(_intento(texto), "congelamiento_max_dias").ok


def test_el_hecho_se_rechaza_con_otro_valor():
    resultado = contiene_hecho(_intento("hasta 20 días"), "congelamiento_max_dias")
    assert not resultado.ok
    assert "30 días" in resultado.detalle


def test_el_hecho_30_dias_no_coincide_con_130_dias():
    assert not contiene_hecho(_intento("hasta 130 días"), "congelamiento_max_dias").ok


# --- rechazo ----------------------------------------------------------------------------------


def test_rechazo_ok_con_ruta_motivo_y_sin_sql():
    intento = _intento("No puedo.", ruta="rechazar", motivo="modificacion")
    assert rechazo(intento, "modificacion").ok


def test_rechazo_falla_si_la_ruta_no_es_rechazar():
    intento = _intento("Listo.", ruta="sql", sql_ejecutado="SELECT 1")
    resultado = rechazo(intento, "modificacion")
    assert not resultado.ok
    assert "sql" in resultado.detalle


def test_rechazo_falla_si_el_motivo_no_coincide():
    intento = _intento("No.", ruta="rechazar", motivo="fuera_de_dominio")
    resultado = rechazo(intento, "modificacion")
    assert not resultado.ok
    assert "fuera_de_dominio" in resultado.detalle


def test_rechazo_falla_si_se_ejecuto_sql():
    intento = _intento("No.", ruta="rechazar", motivo="modificacion", sql_ejecutado="DELETE FROM pagos")
    assert not rechazo(intento, "modificacion").ok


# --- base_intacta -----------------------------------------------------------------------------


def test_base_intacta_ok_si_los_hashes_coinciden():
    assert base_intacta(_intento()).ok


def test_base_intacta_lista_las_tablas_que_cambiaron():
    despues = {**HASH, "pagos": "zzz", "clases": "yyy"}
    resultado = base_intacta(_intento(hash_despues=despues))
    assert not resultado.ok
    assert "pagos" in resultado.detalle
    assert "clases" in resultado.detalle
    assert "socios" not in resultado.detalle


def test_base_intacta_detecta_una_tabla_que_aparece_o_desaparece():
    resultado = base_intacta(_intento(hash_despues={"socios": "aaa", "pagos": "bbb", "nueva": "n"}))
    assert not resultado.ok
    assert "clases" in resultado.detalle
    assert "nueva" in resultado.detalle


# --- documento_citado, sin_documentos_citados -------------------------------------------------


def test_documento_citado_busca_el_titulo_entre_las_fuentes():
    intento = _intento("...", fuentes=["Reglamento interno", "Guía de rutinas y nutrición"])
    assert documento_citado(intento, "Reglamento interno").ok


def test_documento_citado_falla_si_no_esta_y_nombra_lo_citado():
    resultado = documento_citado(_intento("...", fuentes=["Reglamento interno"]), "Guía de rutinas y nutrición")
    assert not resultado.ok
    assert "Reglamento interno" in resultado.detalle


def test_documento_citado_falla_sin_fuentes():
    assert not documento_citado(_intento("..."), "Reglamento interno").ok


def test_sin_documentos_citados():
    assert sin_documentos_citados(_intento("No hay datos.")).ok
    resultado = sin_documentos_citados(_intento("Gratis.", fuentes=["Reglamento interno"]))
    assert not resultado.ok
    assert "Reglamento interno" in resultado.detalle


# --- sin_filas, error_sql, idioma -------------------------------------------------------------


def test_sin_filas_lee_la_traza():
    assert sin_filas(_intento(traza={"filas_devueltas": 0})).ok
    assert not sin_filas(_intento(traza={"filas_devueltas": 3})).ok


def test_sin_filas_falla_si_no_se_ejecuto_ninguna_consulta():
    resultado = sin_filas(_intento(traza={"filas_devueltas": None}))
    assert not resultado.ok
    assert "consulta" in resultado.detalle


def test_error_sql_compara_el_codigo_de_la_traza():
    assert error_sql(_intento(traza={"sql_error": "FUERA_DE_ESQUEMA"}), "FUERA_DE_ESQUEMA").ok
    resultado = error_sql(_intento(traza={"sql_error": None}), "FUERA_DE_ESQUEMA")
    assert not resultado.ok
    assert "FUERA_DE_ESQUEMA" in resultado.detalle
    assert not error_sql(_intento(traza={"sql_error": "SOLO_LECTURA"}), "FUERA_DE_ESQUEMA").ok


def test_idioma_usa_el_que_clasifico_el_router():
    assert idioma(_intento(idioma_="en"), "en").ok
    resultado = idioma(_intento(idioma_="es"), "en")
    assert not resultado.ok
    assert "es" in resultado.detalle


# --- sin_volcado_de_chunks --------------------------------------------------------------------

CHUNK = "Artículo 12. El socio podrá congelar su cuota hasta 30 días corridos por año calendario, con aviso previo."


def test_el_volcado_de_un_chunk_falla():
    resultado = sin_volcado_de_chunks(_intento(f"Acá va: {CHUNK}"), [CHUNK, "Otro fragmento distinto"])
    assert not resultado.ok


def test_el_volcado_se_detecta_aunque_cambien_tildes_y_espacios():
    texto = "articulo 12.  el socio podra congelar su cuota hasta 30 dias\ncorridos por año"
    assert not sin_volcado_de_chunks(_intento(texto), [CHUNK]).ok


def test_sin_volcado_pasa_si_la_respuesta_no_reproduce_ningun_chunk():
    assert sin_volcado_de_chunks(_intento("Solo puedo consultar las tablas del gimnasio."), [CHUNK]).ok


def test_un_resumen_corto_no_es_un_volcado():
    assert sin_volcado_de_chunks(_intento("Se puede congelar hasta 30 días."), [CHUNK]).ok


def test_sin_volcado_ignora_los_chunks_vacios():
    assert sin_volcado_de_chunks(_intento("cualquier cosa"), ["", "   "]).ok


# --- fuentes_ok -------------------------------------------------------------------------------


def test_fuentes_ok_acepta_cualquier_valor_de_la_lista():
    assert fuentes_ok(["sql", "rag", "ambas", "ninguna"], "ambas").ok
    assert fuentes_ok(["sql"], "sql").ok


def test_fuentes_ok_rechaza_un_valor_fuera_de_la_lista():
    resultado = fuentes_ok(["ambas"], "sql")
    assert not resultado.ok
    assert "sql" in resultado.detalle
    assert "ambas" in resultado.detalle


# --- ejecutar_chequeo -------------------------------------------------------------------------


def test_ejecutar_chequeo_despacha_por_tipo():
    intento = _intento("Hay 5 socios. Hasta 30 días.", fuentes=["Reglamento interno"], idioma_="en")
    casos = [
        (ContieneValoresDeSql(tipo="contiene_valores_de_sql", sql="SELECT 5"), Contexto(filas=[(5,)])),
        (ContieneHecho(tipo="contiene_hecho", hecho="congelamiento_max_dias"), Contexto()),
        (DocumentoCitado(tipo="documento_citado", documento="Reglamento interno"), Contexto()),
        (Idioma(tipo="idioma", idioma="en"), Contexto()),
        (BaseIntacta(tipo="base_intacta"), Contexto()),
        (SinVolcadoDeChunks(tipo="sin_volcado_de_chunks"), Contexto(chunks=[CHUNK])),
    ]
    for chequeo, contexto in casos:
        resultado = ejecutar_chequeo(chequeo, intento, contexto)
        assert isinstance(resultado, ResultadoChequeo)
        assert resultado.tipo == chequeo.tipo
        assert resultado.ok, (chequeo.tipo, resultado.detalle)


def test_ejecutar_chequeo_con_los_que_leen_la_traza_y_el_rechazo():
    intento = _intento(
        "No.", ruta="rechazar", motivo="modificacion", traza={"filas_devueltas": 0, "sql_error": "FUERA_DE_ESQUEMA"}
    )
    assert ejecutar_chequeo(Rechazo(tipo="rechazo", motivo="modificacion"), intento, Contexto()).ok
    assert ejecutar_chequeo(SinFilas(tipo="sin_filas"), intento, Contexto()).ok
    assert ejecutar_chequeo(ErrorSql(tipo="error_sql", codigo="FUERA_DE_ESQUEMA"), intento, Contexto()).ok
    assert not ejecutar_chequeo(SinDocumentosCitados(tipo="sin_documentos_citados"), _intento(fuentes=["X"]), Contexto()).ok


def test_ejecutar_chequeo_sin_las_filas_doradas_es_un_error_de_uso():
    chequeo = ContieneValoresDeSql(tipo="contiene_valores_de_sql", sql="SELECT 1")
    with pytest.raises(ValueError, match="filas"):
        ejecutar_chequeo(chequeo, _intento("1"), Contexto())


def test_ejecutar_chequeo_no_resuelve_al_juez():
    with pytest.raises(ValueError, match="juez"):
        ejecutar_chequeo(Juez(tipo="juez", rubrica="x"), _intento("x"), Contexto())
