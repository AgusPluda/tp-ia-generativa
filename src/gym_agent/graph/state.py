"""Estado del grafo y modelos tipados del agente (contrato `agent-graph.md`)."""

from typing import Literal, TypedDict

from pydantic import BaseModel, Field, model_validator

from gym_agent.tools import ResultadoRAG, ResultadoSQL

Ruta = Literal["sql", "rag", "ambas", "rechazar"]
"""Camino que elige el router para una pregunta."""

Idioma = Literal["es", "en"]
"""Idioma de la pregunta; la respuesta sale en el mismo."""

MotivoRechazo = Literal["fuera_de_dominio", "modificacion", "falta_contexto"]
"""Por qué el router rechaza una pregunta."""


class EstadoAgente(TypedDict, total=False):
    """Estado que circula por el grafo; cada invocación parte de uno vacío (RF-017)."""

    pregunta: str
    idioma: Idioma
    ruta: Ruta
    motivo_rechazo: MotivoRechazo | None
    resultado_sql: ResultadoSQL | None
    resultado_rag: ResultadoRAG | None
    respuesta: str
    fuentes_usadas: Literal["sql", "rag", "ambas", "ninguna"]


class DecisionRouter(BaseModel):
    """Salida estructurada del router: ruta, idioma y, si rechaza, el motivo."""

    ruta: Ruta
    idioma: Idioma
    motivo_rechazo: MotivoRechazo | None = None

    @model_validator(mode="after")
    def _motivo_solo_al_rechazar(self) -> "DecisionRouter":
        """Exige `motivo_rechazo` solo cuando la ruta es `rechazar` y lo prohíbe en las otras."""
        if self.ruta == "rechazar" and self.motivo_rechazo is None:
            raise ValueError("La ruta 'rechazar' requiere motivo_rechazo")
        if self.ruta != "rechazar" and self.motivo_rechazo is not None:
            raise ValueError("motivo_rechazo solo corresponde a la ruta 'rechazar'")
        return self


class Sintesis(BaseModel):
    """Salida estructurada de la síntesis: el texto y los fragmentos que lo respaldan."""

    respuesta: str
    fuentes_usadas: list[int] = Field(default_factory=list)
    """Números (base 1) de los fragmentos que respaldan la respuesta; vacío si ninguno."""


class FuenteDocumental(BaseModel):
    """Documento y página citados en una respuesta (RF-011)."""

    documento: str
    pagina: int | None = None


class RespuestaAgente(BaseModel):
    """Resultado público de `run_question`, con lo que la UI necesita mostrar (RF-011)."""

    respuesta: str
    ruta: Ruta
    sql_ejecutado: str | None = None
    fuentes_documentales: list[FuenteDocumental] = Field(default_factory=list)
    idioma: Idioma
    duracion_ms: int
    motivo_rechazo: MotivoRechazo | None = None
    fuentes_usadas: Literal["sql", "rag", "ambas", "ninguna"] = "ninguna"
