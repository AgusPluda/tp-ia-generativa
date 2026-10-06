"""Registro del recorrido (`logs/traza.jsonl`) y arranque opcional de Phoenix, sin LLM ni red."""

import json
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from gym_agent import observability
from gym_agent.observability import iniciar_phoenix, registrar_traza
from gym_agent.tools import ErrorSQL, Fragmento, ResultadoRAG, ResultadoSQL

CLAVES = {
    "timestamp", "pregunta", "idioma", "ruta", "motivo_rechazo", "sql_ejecutado", "filas_devueltas",
    "sql_error", "fragmentos", "respuesta", "duracion_ms", "fuentes_usadas",
}


def respuesta(**campos):
    base = dict(
        respuesta="texto", ruta="ambas", sql_ejecutado="SELECT 1", fuentes_documentales=[],
        idioma="es", duracion_ms=4210, motivo_rechazo=None, fuentes_usadas="ambas",
    )
    return SimpleNamespace(**{**base, **campos})


def estado_completo():
    sql = ResultadoSQL(ok=True, sql_ejecutado="SELECT 1", columnas=["n"], filas=[[1], [2], [3]])
    rag = ResultadoRAG(
        ok=True,
        fragmentos=[
            Fragmento(documento="Reglamento interno", archivo="r.pdf", pagina=2, texto="SECRETO", similitud=0.71)
        ],
    )
    return {"pregunta": "¿Cuántos socios?", "resultado_sql": sql, "resultado_rag": rag}


def leer(ruta):
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]


def test_una_linea_con_las_claves_del_contrato(tmp_path):
    ruta = tmp_path / "traza.jsonl"
    registrar_traza(estado_completo(), respuesta(), ruta)
    (linea,) = leer(ruta)
    assert set(linea) == CLAVES
    assert linea["pregunta"] == "¿Cuántos socios?"
    assert linea["ruta"] == "ambas"
    assert linea["sql_ejecutado"] == "SELECT 1"
    assert linea["filas_devueltas"] == 3
    assert linea["duracion_ms"] == 4210
    assert linea["fuentes_usadas"] == "ambas"
    assert linea["timestamp"].endswith("Z") and linea["timestamp"].startswith("20")


def test_dos_llamadas_dos_lineas(tmp_path):
    ruta = tmp_path / "traza.jsonl"
    registrar_traza(estado_completo(), respuesta(), ruta)
    registrar_traza(estado_completo(), respuesta(), ruta)
    assert len(leer(ruta)) == 2


def test_crea_la_carpeta(tmp_path):
    ruta = tmp_path / "logs" / "anidada" / "traza.jsonl"
    registrar_traza(estado_completo(), respuesta(), ruta)
    assert ruta.exists()


def test_sql_error_es_el_codigo_y_nunca_el_detalle(tmp_path):
    ruta = tmp_path / "traza.jsonl"
    error = ErrorSQL(codigo="TIMEOUT", mensaje="Tardó.", detalle="password=secreta host=db")
    estado = {"pregunta": "p", "resultado_sql": ResultadoSQL(ok=False, error=error)}
    registrar_traza(estado, respuesta(), ruta)
    (linea,) = leer(ruta)
    assert linea["sql_error"] == "TIMEOUT"
    assert "secreta" not in ruta.read_text(encoding="utf-8")


def test_fragmentos_sin_el_texto(tmp_path):
    ruta = tmp_path / "traza.jsonl"
    registrar_traza(estado_completo(), respuesta(), ruta)
    (linea,) = leer(ruta)
    assert linea["fragmentos"] == [{"documento": "Reglamento interno", "pagina": 2, "similitud": 0.71}]
    assert "SECRETO" not in ruta.read_text(encoding="utf-8")


def test_sin_resultados_deja_null_y_lista_vacia(tmp_path):
    ruta = tmp_path / "traza.jsonl"
    estado = {"pregunta": "p", "resultado_sql": None, "resultado_rag": None}
    registrar_traza(estado, respuesta(sql_ejecutado=None, ruta="rechazar"), ruta)
    (linea,) = leer(ruta)
    assert linea["sql_ejecutado"] is None
    assert linea["filas_devueltas"] is None
    assert linea["sql_error"] is None
    assert linea["fragmentos"] == []


def test_la_falla_guarda_el_detalle(tmp_path):
    ruta = tmp_path / "traza.jsonl"
    registrar_traza({"pregunta": "p"}, respuesta(), ruta, error="RuntimeError: clave=secreta")
    (linea,) = leer(ruta)
    assert linea["error"] == "RuntimeError: clave=secreta"


def test_sin_falla_no_agrega_la_clave_error(tmp_path):
    ruta = tmp_path / "traza.jsonl"
    registrar_traza(estado_completo(), respuesta(), ruta)
    assert "error" not in leer(ruta)[0]


def test_conserva_acentos_sin_escapar(tmp_path):
    ruta = tmp_path / "traza.jsonl"
    registrar_traza(estado_completo(), respuesta(respuesta="Está así"), ruta)
    assert "Está así" in ruta.read_text(encoding="utf-8")


def test_ruta_invalida_no_lanza(tmp_path):
    archivo = tmp_path / "es_un_archivo"
    archivo.write_text("x", encoding="utf-8")
    registrar_traza(estado_completo(), respuesta(), archivo / "traza.jsonl")


def test_sin_ruta_usa_traza_path(tmp_path, monkeypatch):
    ruta = tmp_path / "traza.jsonl"
    monkeypatch.setattr(observability, "TRAZA_PATH", ruta)
    registrar_traza(estado_completo(), respuesta())
    assert len(leer(ruta)) == 1


@pytest.fixture
def phoenix_falso(monkeypatch):
    monkeypatch.setattr(observability, "_instrumentado", False)
    register = MagicMock()
    instrument = MagicMock()
    monkeypatch.setattr("phoenix.otel.register", register)
    monkeypatch.setattr("openinference.instrumentation.langchain.LangChainInstrumentor.instrument", instrument)
    return register, instrument


def test_phoenix_sin_servicio_devuelve_false_rapido(monkeypatch):
    monkeypatch.setattr(observability, "_instrumentado", False)
    inicio = time.monotonic()
    assert iniciar_phoenix("http://127.0.0.1:1/v1/traces") is False
    assert time.monotonic() - inicio < 2


def test_phoenix_con_servicio_registra_y_es_idempotente(phoenix_falso, monkeypatch):
    register, instrument = phoenix_falso
    monkeypatch.setattr(observability, "_hay_servicio", lambda endpoint: True)
    assert iniciar_phoenix("http://localhost:6006/v1/traces") is True
    assert iniciar_phoenix("http://localhost:6006/v1/traces") is True
    assert register.call_count == 1
    assert instrument.call_count == 1


def test_phoenix_con_falla_al_registrar_devuelve_false(phoenix_falso, monkeypatch):
    register, _ = phoenix_falso
    register.side_effect = RuntimeError("boom")
    monkeypatch.setattr(observability, "_hay_servicio", lambda endpoint: True)
    assert iniciar_phoenix("http://localhost:6006/v1/traces") is False
