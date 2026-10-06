"""Configuración única del proyecto.

Todas las constantes que comparten el generador de datos, los PDFs, el agente y la
evaluación viven acá (RF-015). Las credenciales se leen del archivo `.env` de la raíz
del repositorio; este módulo lo carga al importarse.
"""

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
"""Raíz del repositorio (donde están `.env`, `data/` y `docker-compose.yml`)."""

PDF_DIR: Path = REPO_ROOT / "data" / "pdfs"
"""Carpeta de los PDFs sintéticos que se ingieren en `rag.chunks`."""

# Se pasa la ruta explícita: `find_dotenv()` depende del directorio de trabajo.
load_dotenv(REPO_ROOT / ".env")

# --- Fechas -----------------------------------------------------------------

REFERENCE_DATE: date = date(2026, 9, 30)
"""El "hoy" del sistema. Nunca se usa la fecha real (research R6): sin override por entorno."""

HISTORY_START: date = date(2026, 4, 1)
"""Primer día del historial de asistencias, pagos y mantenimientos."""

# --- Datos sintéticos -------------------------------------------------------

SEED: int = 20261003
"""Semilla de `random.Random` para el generador de datos (CE-007)."""

# --- Modelos de Gemini (research R2, confirmados en T008) -------------------

CHAT_MODELS: tuple[str, ...] = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite")
"""Modelos de chat en orden de preferencia, con temperatura 0. Si el plan gratuito agota la cuota
diaria de uno, se pasa al siguiente (research R14). Solo el chat: los embeddings no se alternan.
El principal tiene 15 pedidos por minuto y 500 por día; `gemini-3.8-flash` se descartó por su
límite de 20 por día."""

CHAT_MODEL: str = CHAT_MODELS[0]
"""Modelo de chat principal."""

EMBEDDING_MODEL: str = "gemini-embedding-001"
"""Modelo de embeddings para chunks y preguntas."""

EMBEDDING_DIM: int = 1536
"""Dimensión pedida al modelo; coincide con `rag.chunks.embedding vector(1536)`."""

# --- Límites de la SQL tool (principio II) ----------------------------------

MAX_FILAS: int = 50
"""Máximo de filas que devuelve la SQL tool; si hay más, se marca `truncado`."""

STATEMENT_TIMEOUT_S: int = 5
"""Timeout de cada consulta; el rol `agente_ro` ya lo tiene configurado en la base."""

MAX_INTENTOS_SQL: int = 3
"""Intentos totales de la SQL tool por pregunta: el primero más dos reintentos."""

# --- Parámetros de la RAG tool ----------------------------------------------

K_FRAGMENTOS: int = 4
"""Máximo de fragmentos que devuelve la RAG tool."""

UMBRAL_SIMILITUD: float = 0.6
"""Similitud mínima para devolver un fragmento. Solo filtra ruido y NO decide si hay respuesta:
las preguntas válidas puntúan 0,72-0,79 y una fuera de tema como B08 llega a 0,69 (research R9);
esa decisión la toma la síntesis de la Etapa 2."""


# --- Observabilidad (research R10) ------------------------------------------

TRAZA_PATH: Path = REPO_ROOT / "logs" / "traza.jsonl"
"""Archivo donde se registra cada pregunta (una línea JSON); se escribe siempre, con o sin Phoenix."""

PHOENIX_ENDPOINT: str = "http://localhost:6006/v1/traces"
"""Endpoint OTLP de Phoenix (perfil `observability` de docker compose); es opcional."""


def require_env(nombre: str) -> str:
    """Devuelve la variable de entorno `nombre` o falla con un mensaje que indica cómo resolverlo.

    Args:
        nombre: nombre de la variable (por ejemplo `POSTGRES_PASSWORD`).

    Raises:
        RuntimeError: si la variable no existe o está vacía.
    """
    valor = os.getenv(nombre)
    if not valor:
        raise RuntimeError(
            f"Falta la variable {nombre} en {REPO_ROOT / '.env'}. "
            "Copiá .env.example a .env y completá los valores."
        )
    return valor
