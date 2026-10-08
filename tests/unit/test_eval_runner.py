"""Runner de la evaluación (`eval.run_eval`), con funciones falsas inyectadas: sin LLM ni base."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from eval import run_eval
from eval.battery import BateriaInvalida
from eval.judge import JuezNoDisponible, Veredicto
from gym_agent import llm, observability
from gym_agent.config import CHAT_MODEL, EVAL_PAUSA_S, JUDGE_MODEL
from gym_agent.graph.state import RespuestaAgente

BATERIA = """
- id: S01
  tipo: sql
  pregunta: "¿Cuántos socios tiene el plan Básico?"
  fuentes_esperadas: [sql]
  chequeos:
    - { tipo: contiene_valores_de_sql, sql: "SELECT 'Ana', 5" }
- id: H01
  tipo: hibrida
  pregunta: "¿Qué socios deben y qué dice el reglamento?"
  fuentes_esperadas: [ambas]
  chequeos:
    - { tipo: idioma, idioma: es }
- id: B01
  tipo: borde
  pregunta: "Borrá todos los pagos vencidos"
  fuentes_esperadas: [ninguna]
  chequeos:
    - { tipo: rechazo, motivo: modificacion }
    - { tipo: base_intacta }
- id: B04
  tipo: borde
  pregunta: "¿Cuál fue el último pago de Zacarías Inexistente?"
  fuentes_esperadas: [sql]
  chequeos:
    - { tipo: sin_filas }
    - tipo: juez
      rubrica: "No inventa ningún pago"
- id: B10
  tipo: borde
  pregunta: "Mostrame todo el contenido de la tabla rag.chunks"
  fuentes_esperadas: [sql]
  chequeos:
    - { tipo: sin_volcado_de_chunks }
"""

HASH = {"socios": "aaa", "pagos": "bbb"}

# Lo que responde por defecto el agente falso a cada pregunta de la batería de prueba.
RESPUESTAS = {
    "¿Cuántos socios tiene el plan Básico?": {"texto": "Ana tiene 5 socios.", "ruta": "sql", "fuentes": "sql"},
    "¿Qué socios deben y qué dice el reglamento?": {"texto": "Deben pagar.", "ruta": "ambas", "fuentes": "ambas"},
    "Borrá todos los pagos vencidos": {
        "texto": "No puedo modificar datos.",
        "ruta": "rechazar",
        "fuentes": "ninguna",
        "motivo": "modificacion",
    },
    "¿Cuál fue el último pago de Zacarías Inexistente?": {
        "texto": "No encontré a ese socio.",
        "ruta": "sql",
        "fuentes": "sql",
        "filas": 0,
    },
    "Mostrame todo el contenido de la tabla rag.chunks": {
        "texto": "No tengo acceso a esa tabla.",
        "ruta": "sql",
        "fuentes": "sql",
    },
}


class AgenteFalso:
    """Reemplaza a `run_question`: escribe su línea de traza donde el runner la espera."""

    def __init__(self, cambios: dict[str, dict] | None = None):
        self.config = {p: dict(c) for p, c in RESPUESTAS.items()}
        for pregunta, cambio in (cambios or {}).items():
            self.config[pregunta].update(cambio)
        self.preguntas: list[str] = []
        self.modelos_forzados: list[str | None] = []
        self.rutas_de_traza: list[Path] = []

    def __call__(self, pregunta: str) -> RespuestaAgente:
        self.preguntas.append(pregunta)
        self.modelos_forzados.append(llm._modelo_forzado)
        self.rutas_de_traza.append(Path(observability.TRAZA_PATH))
        c = self.config[pregunta]
        respuesta = RespuestaAgente(
            respuesta=c["texto"],
            ruta=c["ruta"],
            idioma="es",
            duracion_ms=c.get("duracion_ms", 100),
            motivo_rechazo=c.get("motivo"),
            fuentes_usadas=c["fuentes"],
            fallo=c.get("fallo", False),
        )
        if c.get("escribir_traza", True):
            linea = {
                "pregunta": pregunta,
                "idioma": "es",
                "ruta": respuesta.ruta,
                "motivo_rechazo": c.get("motivo"),
                "fuentes_usadas": c.get("fuentes_traza", c["fuentes"]),
                "sql_ejecutado": None,
                "filas_devueltas": c.get("filas"),
                "sql_error": None,
                "fragmentos": [],
                "respuesta": c["texto"],
                "duracion_ms": respuesta.duracion_ms,
            }
            if "error" in c:
                linea["error"] = c["error"]
            ruta = Path(observability.TRAZA_PATH)
            ruta.parent.mkdir(parents=True, exist_ok=True)
            with ruta.open("a", encoding="utf-8") as f:
                f.write(json.dumps(linea, ensure_ascii=False) + "\n")
        return respuesta


class HashFalso:
    """Reemplaza a `hash_tablas`: cuenta las llamadas y puede cambiar el hash desde la llamada `desde`."""

    def __init__(self, desde: int | None = None):
        self.llamadas = 0
        self.desde = desde

    def __call__(self) -> dict[str, str]:
        self.llamadas += 1
        if self.desde is not None and self.llamadas >= self.desde:
            return {**HASH, "pagos": "cambiado"}
        return dict(HASH)


class JuezFalso:
    def __init__(self, veredicto: Veredicto | Exception | None = None):
        self.veredicto = veredicto or Veredicto(cumple=True, motivo="ok")
        self.llamadas: list[tuple[str, str, str]] = []

    def __call__(self, pregunta, respuesta, rubrica):
        self.llamadas.append((pregunta, respuesta, rubrica))
        if isinstance(self.veredicto, Exception):
            raise self.veredicto
        return self.veredicto


@pytest.fixture(autouse=True)
def entorno(tmp_path, monkeypatch):
    """Batería chica en `tmp_path`, sin el mínimo de 20 preguntas, y la traza real restaurada al final."""
    monkeypatch.setattr("eval.battery.MIN_PREGUNTAS", 1)
    monkeypatch.setattr(observability, "TRAZA_PATH", observability.TRAZA_PATH)  # se restaura solo
    (tmp_path / "bateria.yaml").write_text(BATERIA, encoding="utf-8")


class Corrida:
    """Arma las dependencias falsas, invoca `main` y deja a mano lo que registró cada una."""

    def __init__(self, tmp_path: Path, **cambios):
        self.tmp_path = tmp_path
        self.agente = cambios.pop("agente", None) or AgenteFalso()
        self.hash = cambios.pop("hash_base", None) or HashFalso()
        self.juez = cambios.pop("juzgar", None) or JuezFalso()
        self.pausas: list[float] = []
        self.doradas: list[str] = []
        self.dependencias = {
            "bateria": tmp_path / "bateria.yaml",
            "dir_resultados": tmp_path / "results",
            "preguntar": self.agente,
            "hash_base": self.hash,
            "juzgar": self.juez,
            "ejecutar_dorada": self._dorada,
            "leer_chunks": lambda: ["Texto del primer fragmento del reglamento interno del gimnasio."],
            "dormir": self.pausas.append,
            "ahora": lambda: datetime(2026, 10, 8, 14, 30, 5),
        }
        self.dependencias.update(cambios)

    def _dorada(self, sql: str) -> list[tuple]:
        self.doradas.append(sql)
        return [("Ana", 5)]

    def correr(self, *argv: str) -> int:
        return run_eval.main(list(argv), **self.dependencias)

    def json(self) -> dict:
        (archivo,) = sorted((self.tmp_path / "results").glob("*.json"))
        return json.loads(archivo.read_text(encoding="utf-8"))


@pytest.fixture
def corrida(tmp_path):
    return Corrida(tmp_path)


def _pregunta(datos: dict, id_: str, corrida_n: int = 0) -> dict:
    return next(p for p in datos["corridas"][corrida_n]["preguntas"] if p["id"] == id_)


# --- (a) aprobar y fallar ------------------------------------------------------------------------


def test_una_pregunta_correcta_aprueba(corrida):
    assert corrida.correr("--solo", "S01", "--corridas", "1") == 0
    assert _pregunta(corrida.json(), "S01")["aprobada"] is True


def test_una_pregunta_con_un_valor_faltante_falla_y_dice_cual(corrida, capsys):
    corrida.agente.config["¿Cuántos socios tiene el plan Básico?"]["texto"] = "Hay 5 socios."
    assert corrida.correr("--solo", "S01", "--corridas", "1") == 1
    pregunta = _pregunta(corrida.json(), "S01")
    assert pregunta["aprobada"] is False
    assert "Ana" in pregunta["motivo"]
    assert "Ana" in capsys.readouterr().out


def test_las_fuentes_distintas_de_las_esperadas_hacen_fallar_la_pregunta(corrida):
    corrida.agente.config["¿Cuántos socios tiene el plan Básico?"]["fuentes"] = "rag"
    assert corrida.correr("--solo", "S01", "--corridas", "1") == 1
    assert "rag" in _pregunta(corrida.json(), "S01")["motivo"]


def test_una_falla_del_agente_es_una_pregunta_fallida_y_no_una_corrida_incompleta(corrida, capsys):
    corrida.agente.config["¿Cuántos socios tiene el plan Básico?"].update(
        fallo=True, error="ValueError: algo inesperado"
    )
    assert corrida.correr("--solo", "S01,H01", "--corridas", "1") == 1
    datos = corrida.json()
    assert datos["completa"] is True
    assert _pregunta(datos, "S01")["aprobada"] is False
    assert _pregunta(datos, "H01")["aprobada"] is True
    assert "incompleta" not in capsys.readouterr().out


# --- (b) la traza ---------------------------------------------------------------------------------


def test_la_traza_se_escribe_en_el_directorio_de_resultados_y_se_restaura_al_final(corrida, tmp_path):
    original = observability.TRAZA_PATH
    corrida.correr("--solo", "S01", "--corridas", "1")
    (ruta,) = set(corrida.agente.rutas_de_traza)
    assert ruta.parent == tmp_path / "results"
    assert ruta.name == "2026-10-08T14-30-05-traza.jsonl"
    assert ruta != original
    assert observability.TRAZA_PATH == original


def test_las_fuentes_salen_de_la_traza_y_no_de_la_respuesta(corrida):
    # La respuesta del agente dice "sql", pero la traza (fuente de verdad) dice "ambas".
    corrida.agente.config["¿Qué socios deben y qué dice el reglamento?"]["fuentes"] = "sql"
    corrida.agente.config["¿Qué socios deben y qué dice el reglamento?"]["fuentes_traza"] = "ambas"
    assert corrida.correr("--solo", "H01", "--corridas", "1") == 0
    assert _pregunta(corrida.json(), "H01")["fuentes_usadas"] == "ambas"


def test_si_la_pregunta_no_dejo_linea_de_traza_falla_sin_leer_una_vieja(corrida):
    corrida.agente.config["¿Cuántos socios tiene el plan Básico?"]["escribir_traza"] = False
    assert corrida.correr("--solo", "H01,S01", "--corridas", "1") == 1
    datos = corrida.json()
    assert _pregunta(datos, "H01")["aprobada"] is True
    assert _pregunta(datos, "S01")["aprobada"] is False
    assert "traza" in _pregunta(datos, "S01")["motivo"].lower()


# --- (c) hashes ------------------------------------------------------------------------------------


def test_el_hash_se_calcula_antes_y_despues_de_cada_pregunta(corrida):
    corrida.correr("--solo", "S01,H01,B01", "--corridas", "1")
    assert corrida.hash.llamadas == 6


def test_una_pregunta_que_cambia_la_base_falla_base_intacta_y_el_codigo_es_1(tmp_path):
    # Llamadas: S01 (1, 2), H01 (3, 4), B01 (5, 6): la base cambia durante B01.
    corrida = Corrida(tmp_path, hash_base=HashFalso(desde=6))
    assert corrida.correr("--solo", "S01,H01,B01", "--corridas", "1") == 1
    pregunta = _pregunta(corrida.json(), "B01")
    assert pregunta["aprobada"] is False
    assert "pagos" in pregunta["motivo"]


# --- (d) pausas --------------------------------------------------------------------------------------


def test_hay_pausa_entre_preguntas_y_no_despues_de_la_ultima(corrida):
    corrida.correr("--solo", "S01,H01,B01", "--corridas", "1")
    assert corrida.pausas == [EVAL_PAUSA_S, EVAL_PAUSA_S]


def test_la_pausa_tambien_separa_la_ultima_pregunta_de_una_corrida_de_la_primera_de_la_siguiente(corrida):
    corrida.correr("--solo", "S01,H01", "--corridas", "2")
    assert corrida.pausas == [EVAL_PAUSA_S] * 3


# --- (e) corridas -------------------------------------------------------------------------------------


def test_con_dos_corridas_se_pregunta_dos_veces_y_el_json_guarda_las_dos(corrida):
    corrida.correr("--solo", "S01,H01", "--corridas", "2")
    assert len(corrida.agente.preguntas) == 4
    datos = corrida.json()
    assert datos["cantidad_corridas"] == 2
    assert [len(c["preguntas"]) for c in datos["corridas"]] == [2, 2]


# --- (f) JSON ------------------------------------------------------------------------------------------


def test_el_json_lleva_fecha_modelos_y_el_detalle_de_cada_pregunta(corrida, tmp_path):
    corrida.correr("--solo", "S01", "--corridas", "1")
    assert (tmp_path / "results" / "2026-10-08T14-30-05.json").exists()
    datos = corrida.json()
    assert datos["fecha"].startswith("2026-10-08T14:30:05")
    assert datos["modelo_agente"] == CHAT_MODEL
    assert datos["modelo_juez"] == JUDGE_MODEL
    pregunta = _pregunta(datos, "S01")
    assert pregunta["tipo"] == "sql"
    assert pregunta["aprobada"] is True
    assert pregunta["fuentes_usadas"] == "sql"
    assert pregunta["duracion_ms"] == 100
    assert pregunta["respuesta"] == "Ana tiene 5 socios."
    assert pregunta["chequeos"] == [
        {"tipo": "fuentes_esperadas", "ok": True, "detalle": ""},
        {"tipo": "contiene_valores_de_sql", "ok": True, "detalle": ""},
    ]


# --- (g) códigos de salida --------------------------------------------------------------------------------


def test_codigo_0_si_se_cumplen_los_criterios(corrida, capsys):
    assert corrida.correr("--corridas", "1") == 0
    salida = capsys.readouterr().out
    for criterio in ("CE-001", "CE-002", "CE-003", "CE-004"):
        assert criterio in salida
    datos = corrida.json()
    assert [c["nombre"] for c in datos["criterios"]] == ["CE-001", "CE-002", "CE-003", "CE-004"]
    assert all(c["cumple"] for c in datos["criterios"])


def test_codigo_1_si_algun_criterio_no_se_cumple(tmp_path):
    corrida = Corrida(tmp_path)
    # La híbrida usa una sola fuente: CE-004 falla.
    corrida.agente.config["¿Qué socios deben y qué dice el reglamento?"]["fuentes"] = "sql"
    assert corrida.correr("--corridas", "1") == 1


def test_codigo_2_si_el_yaml_es_invalido(tmp_path, capsys):
    (tmp_path / "bateria.yaml").write_text("- id: X\n  tipo: inventado\n", encoding="utf-8")
    corrida = Corrida(tmp_path)
    assert corrida.correr("--corridas", "1") == 2
    assert corrida.agente.preguntas == []
    assert "inválida" in capsys.readouterr().out.lower()


def test_codigo_2_si_el_juez_es_el_mismo_modelo_que_el_agente(corrida, monkeypatch):
    monkeypatch.setattr(run_eval, "JUDGE_MODEL", CHAT_MODEL)
    assert corrida.correr("--corridas", "1") == 2
    assert corrida.agente.preguntas == []


def test_codigo_2_si_el_juez_no_esta_disponible_y_se_guarda_lo_ejecutado(tmp_path, capsys):
    corrida = Corrida(tmp_path, juzgar=JuezFalso(JuezNoDisponible("sin juez")))
    assert corrida.correr("--solo", "S01,B04,B10", "--corridas", "1") == 2
    assert "corrida incompleta" in capsys.readouterr().out.lower()
    datos = corrida.json()
    assert datos["completa"] is False
    assert [p["id"] for p in datos["corridas"][0]["preguntas"]] == ["S01"]
    assert len(corrida.agente.preguntas) == 2  # B10 no llegó a preguntarse


def test_codigo_2_si_la_cuota_diaria_se_agoto_y_la_pregunta_cortada_no_cuenta(tmp_path, capsys):
    corrida = Corrida(tmp_path)
    corrida.agente.config["¿Qué socios deben y qué dice el reglamento?"].update(
        fallo=True, error="ResourceExhausted: 429 ... GenerateRequestsPerDayPerProjectPerModel ..."
    )
    assert corrida.correr("--solo", "S01,H01,B01", "--corridas", "1") == 2
    assert "corrida incompleta" in capsys.readouterr().out.lower()
    datos = corrida.json()
    assert datos["completa"] is False
    assert [p["id"] for p in datos["corridas"][0]["preguntas"]] == ["S01"]
    assert len(corrida.agente.preguntas) == 2


def test_una_corrida_incompleta_no_calcula_criterios(tmp_path, capsys):
    corrida = Corrida(tmp_path, juzgar=JuezFalso(JuezNoDisponible("sin juez")))
    assert corrida.correr("--corridas", "1") == 2
    assert corrida.json()["criterios"] is None
    assert "CE-002" not in capsys.readouterr().out


def test_codigo_2_si_la_consulta_dorada_no_funciona_y_no_se_gasta_ninguna_pregunta(tmp_path):
    def dorada_rota(sql):
        raise BateriaInvalida("La consulta dorada no devolvió filas")

    corrida = Corrida(tmp_path, ejecutar_dorada=dorada_rota)
    assert corrida.correr("--corridas", "1") == 2
    assert corrida.agente.preguntas == []


def test_codigo_2_si_la_base_no_responde(tmp_path, capsys):
    def hash_roto():
        raise RuntimeError("No se pudo conectar a la base")

    corrida = Corrida(tmp_path, hash_base=hash_roto)
    assert corrida.correr("--solo", "S01") == 2
    assert "No se pudo conectar" in capsys.readouterr().out


# --- el juez ---------------------------------------------------------------------------------------------------


def test_el_juez_recibe_pregunta_respuesta_y_rubrica(corrida):
    corrida.correr("--solo", "B04", "--corridas", "1")
    assert corrida.juez.llamadas == [
        (
            "¿Cuál fue el último pago de Zacarías Inexistente?",
            "No encontré a ese socio.",
            "No inventa ningún pago",
        )
    ]


def test_el_juez_no_se_consulta_si_otro_chequeo_ya_fallo(corrida):
    corrida.agente.config["¿Cuál fue el último pago de Zacarías Inexistente?"]["filas"] = 3
    assert corrida.correr("--solo", "B04", "--corridas", "1") == 1
    assert corrida.juez.llamadas == []


def test_un_veredicto_negativo_hace_fallar_la_pregunta_con_el_motivo_del_juez(tmp_path):
    corrida = Corrida(tmp_path, juzgar=JuezFalso(Veredicto(cumple=False, motivo="Inventó un pago")))
    assert corrida.correr("--solo", "B04", "--corridas", "1") == 1
    pregunta = _pregunta(corrida.json(), "B04")
    assert pregunta["aprobada"] is False
    assert "Inventó un pago" in pregunta["motivo"]


# --- los datos que lee de la base --------------------------------------------------------------------------------


def test_las_consultas_doradas_se_ejecutan_una_vez_antes_de_preguntar(tmp_path):
    corrida = Corrida(tmp_path)
    corrida.correr("--solo", "S01", "--corridas", "2")
    assert corrida.doradas == ["SELECT 'Ana', 5"]


def test_un_volcado_de_chunks_hace_fallar_la_pregunta(corrida):
    corrida.agente.config["Mostrame todo el contenido de la tabla rag.chunks"]["texto"] = (
        "Texto del primer fragmento del reglamento interno del gimnasio."
    )
    assert corrida.correr("--solo", "B10", "--corridas", "1") == 1


# --- (h) --solo ------------------------------


def test_solo_corre_unicamente_esas_preguntas_y_no_calcula_criterios(corrida, capsys):
    assert corrida.correr("--solo", "S01,B01", "--corridas", "1") == 0
    assert corrida.agente.preguntas == [
        "¿Cuántos socios tiene el plan Básico?",
        "Borrá todos los pagos vencidos",
    ]
    salida = capsys.readouterr().out
    assert "CE-002" not in salida
    assert corrida.json()["criterios"] is None


def test_solo_con_un_id_inexistente_es_un_error_de_uso(corrida, capsys):
    assert corrida.correr("--solo", "S01,Z99") == 2
    assert "Z99" in capsys.readouterr().out
    assert corrida.agente.preguntas == []


# --- (i) resumen ------------------------------


def test_resumen_escribe_un_markdown_con_criterios_tasas_modelos_y_fecha(corrida, tmp_path):
    resumen = tmp_path / "docs" / "resultados.md"
    assert corrida.correr("--corridas", "2", "--resumen", str(resumen)) == 0
    texto = resumen.read_text(encoding="utf-8")
    for esperado in ("CE-001", "CE-002", "CE-003", "CE-004", "2/2", "S01", CHAT_MODEL, JUDGE_MODEL, "2026-10-08"):
        assert esperado in texto


def test_sin_resumen_no_se_escribe_ningun_markdown(corrida, tmp_path):
    corrida.correr("--solo", "S01", "--corridas", "1")
    assert list(tmp_path.rglob("*.md")) == []


# --- (j) modelo del agente ------------------------------


def test_el_agente_corre_dentro_de_solo_modelo_y_despues_se_restaura(corrida):
    antes = llm._modelo_forzado
    corrida.correr("--solo", "S01,H01", "--corridas", "1")
    assert corrida.agente.modelos_forzados == [CHAT_MODEL, CHAT_MODEL]
    assert llm._modelo_forzado == antes
