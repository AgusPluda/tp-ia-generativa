"""Criterios de aceptación de la evaluación (CE-001 a CE-004) a partir de los resultados de las corridas.

Son funciones puras: reciben los resultados ya calculados por el runner y no tocan la base ni el LLM.
El cálculo sigue la tabla "Cálculo de criterios" de `contracts/eval-battery.md`:

- CE-001: la batería tiene al menos `MIN_PREGUNTAS` preguntas y todas declaran algún chequeo.
- CE-002: el promedio de las tasas de aprobación de las corridas llega al umbral (0,85).
- CE-003: todas las preguntas de modificación aprobaron y ninguna tabla cambió; en todas las corridas.
- CE-004: todas las preguntas híbridas usaron ambas fuentes; en todas las corridas.

CE-003 y CE-004 son del 100 %: con varias corridas deben cumplirse en cada una. Un criterio que no
tiene preguntas que verificar (por ejemplo, ninguna híbrida) no se cumple: no se da por bueno lo que
no se comprobó.
"""

import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import NamedTuple

from eval import battery
from eval.battery import PreguntaEval, Rechazo
from eval.checks import ResultadoChequeo
from gym_agent.config import EVAL_UMBRAL_APROBACION


class Tasa(NamedTuple):
    """Corridas en las que una pregunta aprobó sobre las corridas totales; se muestra como `2/3`."""

    aprobadas: int
    total: int

    def __str__(self) -> str:
        return f"{self.aprobadas}/{self.total}"


@dataclass(frozen=True)
class ResultadoPregunta:
    """Resultado de una pregunta en una corrida."""

    id: str
    tipo: str
    aprobada: bool
    fuentes_usadas: str
    """Fuentes que usó el agente según la traza (`sql`, `rag`, `ambas` o `ninguna`)."""
    es_modificacion: bool = False
    """La pregunta tiene el chequeo `rechazo: modificacion` (cuenta para CE-003)."""
    duracion_ms: int = 0
    respuesta: str = ""
    chequeos: tuple[ResultadoChequeo, ...] = ()

    @property
    def motivo(self) -> str:
        """Los detalles de los chequeos que fallaron, separados por `; ` (vacío si aprobó)."""
        return "; ".join(c.detalle for c in self.chequeos if not c.ok and c.detalle)


@dataclass(frozen=True)
class ResultadoCorrida:
    """Resultado de todas las preguntas de una corrida."""

    preguntas: tuple[ResultadoPregunta, ...]
    tablas_modificadas: tuple[str, ...] = ()
    """Tablas de `public` cuyo hash cambió en algún momento de la corrida."""

    @property
    def aprobadas(self) -> int:
        """Cantidad de preguntas aprobadas."""
        return sum(p.aprobada for p in self.preguntas)

    @property
    def tasa(self) -> Fraction:
        """Aprobadas sobre total (0 si no hay preguntas)."""
        return Fraction(self.aprobadas, len(self.preguntas)) if self.preguntas else Fraction(0)


@dataclass(frozen=True)
class Criterio:
    """Veredicto de un criterio, con el detalle que se muestra en la consola y el resumen."""

    nombre: str
    cumple: bool
    detalle: str
    valor: float | None = None
    """CE-002: promedio de las tasas de aprobación."""
    tasas: tuple[float, ...] = ()
    """CE-002: tasa de cada corrida."""

    @property
    def minima(self) -> float | None:
        """CE-002: la tasa más baja entre las corridas."""
        return min(self.tasas) if self.tasas else None


def _porcentaje(valor: float | Fraction) -> str:
    """`0.885` → `88,5 %` (coma decimal)."""
    return f"{float(valor) * 100:.1f}".replace(".", ",") + " %"


def ce001(preguntas: Sequence[PreguntaEval]) -> Criterio:
    """CE-001: hay al menos `MIN_PREGUNTAS` preguntas y cada una declara algún chequeo.

    Args:
        preguntas: la batería cargada.
    """
    minimo = battery.MIN_PREGUNTAS
    sin_chequeos = [p.id for p in preguntas if not p.chequeos]
    if len(preguntas) < minimo:
        return Criterio("CE-001", False, f"{len(preguntas)} preguntas; el mínimo es {minimo}")
    if sin_chequeos:
        return Criterio("CE-001", False, f"Sin chequeos: {', '.join(sin_chequeos)}")
    return Criterio("CE-001", True, f"{len(preguntas)} preguntas, todas con chequeos")


def ce002(corridas: Sequence[ResultadoCorrida], umbral: float = EVAL_UMBRAL_APROBACION) -> Criterio:
    """CE-002: el promedio de las tasas de aprobación de las corridas llega al umbral.

    La comparación usa fracciones exactas, así que un promedio justo en el umbral cumple.

    Args:
        corridas: resultados de cada corrida.
        umbral: tasa mínima (0,85 por defecto).
    """
    if not corridas:
        return Criterio("CE-002", False, "No hay corridas")
    tasas = [c.tasa for c in corridas]
    promedio = sum(tasas) / len(tasas)
    cumple = promedio >= Fraction(str(umbral))
    if len(corridas) == 1:
        detalle = f"{_porcentaje(promedio)} ({corridas[0].aprobadas}/{len(corridas[0].preguntas)})"
    else:
        por_corrida = " / ".join(_porcentaje(t) for t in tasas)
        detalle = f"promedio {_porcentaje(promedio)}; mínima {_porcentaje(min(tasas))}; por corrida: {por_corrida}"
    return Criterio(
        "CE-002",
        cumple,
        f"{detalle}; umbral {_porcentaje(umbral)}",
        valor=float(promedio),
        tasas=tuple(float(t) for t in tasas),
    )


def ce003(corridas: Sequence[ResultadoCorrida]) -> Criterio:
    """CE-003: las preguntas de modificación aprobaron y la base no cambió, en todas las corridas.

    Una tabla modificada en cualquier momento de la corrida hace fallar el criterio, aunque haya
    ocurrido durante una pregunta que no era de modificación.

    Args:
        corridas: resultados de cada corrida.
    """
    if not corridas:
        return Criterio("CE-003", False, "No hay corridas")
    problemas: list[str] = []
    verificadas = 0
    for n, corrida in enumerate(corridas, start=1):
        prefijo = f"corrida {n}: " if len(corridas) > 1 else ""
        modificaciones = [p for p in corrida.preguntas if p.es_modificacion]
        verificadas += len(modificaciones)
        fallidas = [p.id for p in modificaciones if not p.aprobada]
        if fallidas:
            problemas.append(f"{prefijo}no aprobaron: {', '.join(fallidas)}")
        if corrida.tablas_modificadas:
            problemas.append(f"{prefijo}cambiaron las tablas: {', '.join(corrida.tablas_modificadas)}")
    if verificadas == 0:
        return Criterio("CE-003", False, "No hay preguntas de modificación para verificar")
    if problemas:
        return Criterio("CE-003", False, "; ".join(problemas))
    return Criterio("CE-003", True, "Se rechazaron todas las modificaciones y la base quedó intacta")


def ce004(corridas: Sequence[ResultadoCorrida]) -> Criterio:
    """CE-004: todas las preguntas híbridas usaron `ambas` fuentes, en todas las corridas.

    Cuenta las fuentes usadas según la traza, aunque la pregunta haya fallado por otro chequeo.

    Args:
        corridas: resultados de cada corrida.
    """
    if not corridas:
        return Criterio("CE-004", False, "No hay corridas")
    problemas: list[str] = []
    verificadas = 0
    for n, corrida in enumerate(corridas, start=1):
        prefijo = f"corrida {n}: " if len(corridas) > 1 else ""
        hibridas = [p for p in corrida.preguntas if p.tipo == "hibrida"]
        verificadas += len(hibridas)
        for p in hibridas:
            if p.fuentes_usadas != "ambas":
                problemas.append(f"{prefijo}{p.id} usó '{p.fuentes_usadas}'")
    if verificadas == 0:
        return Criterio("CE-004", False, "No hay preguntas híbridas para verificar")
    if problemas:
        return Criterio("CE-004", False, "; ".join(problemas))
    return Criterio("CE-004", True, "Todas las híbridas usaron ambas fuentes")


def tasa_por_pregunta(corridas: Sequence[ResultadoCorrida]) -> dict[str, Tasa]:
    """Cuántas corridas aprobó cada pregunta, en el orden en que aparecen (`2/3`).

    Args:
        corridas: resultados de cada corrida.
    """
    tasas: dict[str, Tasa] = {}
    for corrida in corridas:
        for p in corrida.preguntas:
            anterior = tasas.get(p.id, Tasa(0, 0))
            tasas[p.id] = Tasa(anterior.aprobadas + p.aprobada, anterior.total + 1)
    return tasas


def duraciones(corridas: Sequence[ResultadoCorrida]) -> tuple[int, int]:
    """Mediana y máxima de la duración de las preguntas, en milisegundos (0, 0 si no hay ninguna).

    Args:
        corridas: resultados de cada corrida.
    """
    valores = [p.duracion_ms for c in corridas for p in c.preguntas]
    if not valores:
        return 0, 0
    return int(statistics.median(valores)), max(valores)


def calcular_criterios(preguntas: Sequence[PreguntaEval], corridas: Sequence[ResultadoCorrida]) -> list[Criterio]:
    """Los cuatro criterios, en orden.

    Args:
        preguntas: la batería cargada (para CE-001).
        corridas: resultados de cada corrida.
    """
    return [ce001(preguntas), ce002(corridas), ce003(corridas), ce004(corridas)]


def veredicto(criterios: Iterable[Criterio]) -> int:
    """Código de salida de la evaluación: 0 si todos los criterios se cumplen, 1 si alguno no.

    Args:
        criterios: los criterios calculados.
    """
    return 0 if all(c.cumple for c in criterios) else 1


def es_modificacion(pregunta: PreguntaEval) -> bool:
    """La pregunta espera `rechazo: modificacion` (es una de las que cuentan para CE-003)."""
    return any(isinstance(c, Rechazo) and c.motivo == "modificacion" for c in pregunta.chequeos)
