"""RAG tool sin base ni LLM: `embeber` y la consulta se inyectan como funciones falsas."""

from gym_agent.config import EMBEDDING_DIM, K_FRAGMENTOS, UMBRAL_SIMILITUD
from gym_agent.tools.rag_tool import Fragmento, buscar

VECTOR = [0.1] * EMBEDDING_DIM


def _frag(similitud: float, texto: str = "t") -> Fragmento:
    return Fragmento(documento="Doc", archivo="doc.pdf", pagina=1, texto=texto, similitud=similitud)


def _embeber(_pregunta: str) -> list[float]:
    return VECTOR


class BaseFalsa:
    """Imita la consulta a la base: devuelve lo indicado y recuerda con qué se la llamó."""

    def __init__(self, fragmentos=None, error: Exception | None = None):
        self.fragmentos, self.error, self.llamadas = fragmentos or [], error, []

    def __call__(self, vector, k):
        self.llamadas.append((vector, k))
        if self.error:
            raise self.error
        return self.fragmentos


def test_conserva_los_que_superan_el_umbral_ordenados_y_descarta_el_resto():
    base = BaseFalsa([_frag(0.65, "b"), _frag(0.9, "a"), _frag(0.4, "x")])
    r = buscar("p", umbral=0.6, embeber=_embeber, consultar=base)
    assert r.ok and r.error is None
    assert [f.texto for f in r.fragmentos] == ["a", "b"]


def test_el_valor_igual_al_umbral_se_conserva():
    r = buscar("p", umbral=0.6, embeber=_embeber, consultar=BaseFalsa([_frag(0.6)]))
    assert len(r.fragmentos) == 1


def test_si_ninguno_pasa_es_ok_y_sin_fragmentos():
    r = buscar("p", umbral=0.6, embeber=_embeber, consultar=BaseFalsa([_frag(0.2), _frag(0.1)]))
    assert r.ok and r.fragmentos == [] and r.error is None


def test_pasa_k_y_el_vector_a_la_consulta():
    base = BaseFalsa()
    buscar("p", k=2, embeber=_embeber, consultar=base)
    buscar("p", embeber=_embeber, consultar=base)
    assert base.llamadas == [(VECTOR, 2), (VECTOR, K_FRAGMENTOS)]


def test_usa_el_umbral_de_la_configuracion_por_defecto():
    base = BaseFalsa([_frag(UMBRAL_SIMILITUD), _frag(UMBRAL_SIMILITUD - 0.01)])
    assert len(buscar("p", embeber=_embeber, consultar=base).fragmentos) == 1


def test_si_embeber_falla_es_embedding_fallo():
    def embeber(_p):
        raise ConnectionError("sin red")

    base = BaseFalsa()
    r = buscar("p", embeber=embeber, consultar=base)
    assert not r.ok and r.fragmentos == []
    assert r.error.codigo == "EMBEDDING_FALLO"
    assert "sin red" in r.error.detalle
    assert base.llamadas == []


def test_un_vector_de_otra_dimension_es_invalido_y_no_consulta_la_base():
    base = BaseFalsa()
    r = buscar("p", embeber=lambda _p: [0.1] * 768, consultar=base)
    assert not r.ok and r.error.codigo == "DIMENSION_INVALIDA"
    assert "768" in r.error.detalle
    assert base.llamadas == []


def test_si_la_consulta_falla_es_error_ejecucion():
    r = buscar("p", embeber=_embeber, consultar=BaseFalsa(error=RuntimeError("base caída")))
    assert not r.ok and r.error.codigo == "ERROR_EJECUCION"
    assert "base caída" in r.error.detalle


def test_el_mensaje_al_usuario_no_trae_el_detalle_tecnico():
    r = buscar("p", embeber=_embeber, consultar=BaseFalsa(error=RuntimeError("password=secreta")))
    assert "secreta" not in r.error.mensaje
    assert "secreta" in r.error.detalle
