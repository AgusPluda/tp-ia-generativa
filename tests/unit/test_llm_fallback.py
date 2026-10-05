"""Cambio de modelo de chat cuando se agota la cuota diaria (sin llamar a la API)."""

import pytest

from gym_agent import llm
from gym_agent.config import CHAT_MODELS

CUOTA_DIARIA = (
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota', "
    "'details': [{'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier'}, "
    "{'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '13345s'}]}}"
)
POR_MINUTO = "429 RESOURCE_EXHAUSTED. {'quotaId': 'GenerateRequestsPerMinutePerProjectPerModel', 'retryDelay': '20s'}"


class ErrorAPI(Exception):
    def __init__(self, texto, code=429):
        super().__init__(texto)
        self.code = code


class ModeloFalso:
    """Imita al chat: `invoke` devuelve o lanza lo que se le indicó para su nombre de modelo."""

    def __init__(self, nombre, respuestas, llamados):
        self.nombre, self.respuestas, self.llamados = nombre, respuestas, llamados

    def invoke(self, entrada):
        self.llamados.append(self.nombre)
        respuesta = self.respuestas[self.nombre].pop(0)
        if isinstance(respuesta, Exception):
            raise respuesta
        return f"{respuesta}:{entrada}"


@pytest.fixture
def api(monkeypatch):
    """Reemplaza `get_chat_model` por modelos falsos y limpia la memoria de modelos agotados."""
    respuestas = {m: [] for m in CHAT_MODELS}
    llamados: list[str] = []
    monkeypatch.setattr(llm, "get_chat_model", lambda modelo: ModeloFalso(modelo, respuestas, llamados))
    monkeypatch.setattr(llm, "_modelos_agotados", set())
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    return respuestas, llamados


PRINCIPAL, RESPALDO = CHAT_MODELS[0], CHAT_MODELS[1]


def test_hay_al_menos_un_modelo_de_respaldo():
    assert len(CHAT_MODELS) >= 2
    assert len(set(CHAT_MODELS)) == len(CHAT_MODELS)


def test_la_cuota_diaria_no_es_transitoria_pero_la_por_minuto_si():
    assert llm.es_cuota_agotada(ErrorAPI(CUOTA_DIARIA))
    assert not llm.es_error_transitorio(ErrorAPI(CUOTA_DIARIA))
    assert not llm.es_cuota_agotada(ErrorAPI(POR_MINUTO))
    assert llm.es_error_transitorio(ErrorAPI(POR_MINUTO))


def test_la_cuota_se_detecta_aunque_venga_como_causa():
    try:
        try:
            raise ErrorAPI(CUOTA_DIARIA)
        except ErrorAPI as e:
            raise RuntimeError("envoltorio") from e
    except RuntimeError as envuelta:
        assert llm.es_cuota_agotada(envuelta)


def test_usa_el_principal_si_responde(api):
    respuestas, llamados = api
    respuestas[PRINCIPAL] = ["ok"]
    assert llm.invocar_chat(lambda m: m, "p") == "ok:p"
    assert llamados == [PRINCIPAL]


def test_pasa_al_respaldo_con_la_cuota_diaria_agotada_y_lo_recuerda(api):
    respuestas, llamados = api
    respuestas[PRINCIPAL] = [ErrorAPI(CUOTA_DIARIA)]
    respuestas[RESPALDO] = ["r1", "r2"]
    assert llm.invocar_chat(lambda m: m, "p") == "r1:p"
    assert llm.invocar_chat(lambda m: m, "q") == "r2:q"
    # Un solo pedido al principal: después ya se sabe que está agotado.
    assert llamados == [PRINCIPAL, RESPALDO, RESPALDO]


def test_un_429_por_minuto_se_reintenta_con_el_mismo_modelo(api):
    respuestas, llamados = api
    respuestas[PRINCIPAL] = [ErrorAPI(POR_MINUTO), "ok"]
    assert llm.invocar_chat(lambda m: m, "p") == "ok:p"
    assert llamados == [PRINCIPAL, PRINCIPAL]


def test_un_error_no_transitorio_no_cambia_de_modelo(api):
    respuestas, llamados = api
    respuestas[PRINCIPAL] = [ErrorAPI("400 INVALID_ARGUMENT", code=400)]
    with pytest.raises(ErrorAPI):
        llm.invocar_chat(lambda m: m, "p")
    assert llamados == [PRINCIPAL]


def test_si_todos_agotaron_la_cuota_se_propaga_el_error(api):
    respuestas, llamados = api
    for modelo in CHAT_MODELS:
        respuestas[modelo] = [ErrorAPI(CUOTA_DIARIA)]
    with pytest.raises(ErrorAPI):
        llm.invocar_chat(lambda m: m, "p")
    assert llamados == list(CHAT_MODELS)
