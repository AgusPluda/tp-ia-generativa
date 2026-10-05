"""Tools del agente: es lo único que importa el grafo (Etapa 2).

- `consultar`: pregunta → un `SELECT` validado, ejecutado en solo lectura (`ResultadoSQL`).
- `buscar`: pregunta → fragmentos de los PDFs con documento y página (`ResultadoRAG`).

Ninguna lanza excepciones: los fallos viajan en `error`. Ninguna usa `connect_admin()`
(principio II): solo `connect_ro()`.
"""

from gym_agent.tools.rag_tool import ErrorRAG, Fragmento, ResultadoRAG, buscar
from gym_agent.tools.sql_tool import ErrorSQL, ResultadoSQL, consultar

__all__ = [
    "ErrorRAG",
    "ErrorSQL",
    "Fragmento",
    "ResultadoRAG",
    "ResultadoSQL",
    "buscar",
    "consultar",
]
