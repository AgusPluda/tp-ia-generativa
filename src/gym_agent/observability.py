"""Registro del recorrido de cada pregunta (RF-012, research R10).

`logs/traza.jsonl` es la fuente para el informe y para la evaluación: una línea JSON por
pregunta, escrita siempre, con o sin Phoenix. Phoenix es un extra: si hay un servicio
escuchando en su endpoint, el mismo recorrido queda como traza OpenTelemetry con las
llamadas al LLM y a las tools; si no, el agente funciona igual y no se informa nada.

Ninguna función de este módulo lanza excepciones: observar no puede romper una respuesta.
"""

import json
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from gym_agent.config import PHOENIX_ENDPOINT, TRAZA_PATH

if TYPE_CHECKING:
    from gym_agent.graph.state import EstadoAgente, RespuestaAgente

_instrumentado = False
"""True una vez registrado el tracer de Phoenix; evita registrarlo dos veces."""

_ESPERA_CONEXION_S = 1.0


def registrar_traza(
    estado: "EstadoAgente",
    respuesta: "RespuestaAgente",
    ruta_archivo: Path | None = None,
    *,
    error: str | None = None,
) -> None:
    """Agrega una línea JSON con el recorrido de la pregunta a `ruta_archivo` (`TRAZA_PATH` por defecto).

    `sql_error` es el código del error, nunca su `detalle`; los fragmentos van sin el texto.
    `error` (el detalle de una falla no prevista) se agrega como clave solo si se informa.
    El `timestamp` es la hora real de la ejecución: es un dato de registro, no usa `REFERENCE_DATE`.
    """
    try:
        resultado_sql = estado.get("resultado_sql")
        resultado_rag = estado.get("resultado_rag")
        linea: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "pregunta": estado.get("pregunta", ""),
            "idioma": respuesta.idioma,
            "ruta": respuesta.ruta,
            "motivo_rechazo": respuesta.motivo_rechazo,
            "fuentes_usadas": respuesta.fuentes_usadas,
            "sql_ejecutado": respuesta.sql_ejecutado,
            "filas_devueltas": len(resultado_sql.filas) if resultado_sql is not None else None,
            "sql_error": resultado_sql.error.codigo if resultado_sql and resultado_sql.error else None,
            "fragmentos": [
                {"documento": f.documento, "pagina": f.pagina, "similitud": f.similitud}
                for f in (resultado_rag.fragmentos if resultado_rag is not None else [])
            ],
            "respuesta": respuesta.respuesta,
            "duracion_ms": respuesta.duracion_ms,
        }
        if error is not None:
            linea["error"] = error
        destino = Path(ruta_archivo) if ruta_archivo is not None else TRAZA_PATH
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("a", encoding="utf-8") as archivo:
            archivo.write(json.dumps(linea, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _hay_servicio(endpoint: str) -> bool:
    """Indica si algo escucha en el host y puerto del endpoint (conexión TCP de hasta 1 s)."""
    url = urlparse(endpoint)
    puerto = url.port or (443 if url.scheme == "https" else 80)
    try:
        with socket.create_connection((url.hostname or "localhost", puerto), timeout=_ESPERA_CONEXION_S):
            return True
    except OSError:
        return False


def iniciar_phoenix(endpoint: str = PHOENIX_ENDPOINT) -> bool:
    """Activa la exportación de trazas a Phoenix si hay un servicio escuchando; devuelve si quedó activa.

    Sin servicio devuelve `False` sin ruido. Es idempotente: una vez activa no vuelve a registrar.
    """
    global _instrumentado
    if _instrumentado:
        return True
    try:
        if not _hay_servicio(endpoint):
            return False
        from openinference.instrumentation.langchain import LangChainInstrumentor
        from phoenix.otel import register

        proveedor = register(endpoint=endpoint, project_name="gym-agent", verbose=False)
        LangChainInstrumentor().instrument(tracer_provider=proveedor)
    except Exception:
        return False
    _instrumentado = True
    return True
