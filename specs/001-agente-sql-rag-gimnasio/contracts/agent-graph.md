# Contrato: grafo del agente

Módulo: `src/gym_agent/graph/`. Punto de entrada público: `run_question(pregunta: str) -> RespuestaAgente`.

## Diagrama

```text
            ┌──────────┐
 pregunta → │  router  │
            └────┬─────┘
   ┌─────────────┼───────────────┬──────────────┐
   ▼ sql         ▼ rag           ▼ ambas        ▼ rechazar
┌──────┐      ┌──────┐        ┌──────┐      ┌──────────┐
│ sql  │      │ rag  │        │ sql  │      │ rechazar │
└──┬───┘      └──┬───┘        └──┬───┘      └────┬─────┘
   │             │               ▼               │
   │             │            ┌──────┐            │
   │             │            │ rag  │            │
   │             │            └──┬───┘            │
   ▼             ▼               ▼               │
 ┌───────────────────────────────────┐           │
 │            sintetizar             │           │
 └─────────────────┬─────────────────┘           │
                   ▼                             ▼
                  FIN ◄──────────────────────────┘
```

Sin checkpointer ni memoria: cada invocación parte de un estado vacío (RF-017).

## Estado (`EstadoAgente`)

| Campo | Tipo | Quién lo escribe |
|-------|------|------------------|
| `pregunta` | str | Entrada |
| `idioma` | `"es"` \| `"en"` | `router` |
| `ruta` | `"sql"` \| `"rag"` \| `"ambas"` \| `"rechazar"` | `router` |
| `motivo_rechazo` | `"fuera_de_dominio"` \| `"modificacion"` \| `"falta_contexto"` \| null | `router` |
| `resultado_sql` | `ResultadoSQL` \| null | `sql` ([contrato](sql-tool.md)) |
| `resultado_rag` | `ResultadoRAG` \| null | `rag` ([contrato](rag-tool.md)) |
| `respuesta` | str | `sintetizar` / `rechazar` |

## Nodos

### `router`
- **Entrada**: `pregunta`. **Salida**: `ruta`, `idioma`, `motivo_rechazo` (salida estructurada Pydantic, temperatura 0).
- **Criterios** (en el prompt):
  - `sql`: datos variables o transaccionales (socios, pagos, asistencias, clases, instructores, equipamiento, planes, precios).
  - `rag`: reglas, políticas, procedimientos, rutinas, nutrición, uso y mantenimiento de equipos.
  - `ambas`: la pregunta pide datos **y** reglas.
  - `rechazar` con `fuera_de_dominio`: nada que ver con el gimnasio (RF-009; no se consulta ninguna fuente).
  - `rechazar` con `modificacion`: pide alta, baja, cambio o borrado de datos (RF-008).
  - `rechazar` con `falta_contexto`: solo tiene sentido con una pregunta anterior ("¿Y el mes anterior?"); se pide formular la pregunta completa (RF-017).
- Las preguntas ambiguas **no** se rechazan: se enrutan y la síntesis explicita el supuesto (Historia 4, escenario 4).

### `sql`
Ejecuta la SQL tool y guarda `resultado_sql`. Nunca lanza excepciones: los fallos viajan en `resultado_sql.error`.

### `rag`
Ejecuta la RAG tool y guarda `resultado_rag`. Con la ruta `ambas`, corre después de `sql`.

### `sintetizar`
- **Entrada**: pregunta, idioma, resultados disponibles.
- **Reglas del prompt**: responder **solo** con lo que traen los resultados; en el idioma de la pregunta; si SQL devolvió 0 filas o RAG no devolvió fragmentos, decir que no se encontró información y no inventar; si hay `truncado`, aclararlo; si falló una tool, explicarlo sin detalles técnicos; explicitar cualquier supuesto (por ejemplo, el significado de "esta semana"); para preguntas híbridas, cubrir las dos partes.
- **Salida**: `respuesta`.

### `rechazar`
Redacta, en el idioma de la pregunta, una respuesta breve según `motivo_rechazo`: solo se puede consultar información (modificación), solo se responde sobre el gimnasio (fuera de dominio), o hay que formular cada pregunta completa (falta de contexto). No consulta ninguna fuente.

## Respuesta final (`RespuestaAgente`)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `respuesta` | str | Texto para el usuario |
| `ruta` | str | Ruta elegida (se muestra en la UI) |
| `sql_ejecutado` | str \| null | Consulta ejecutada (RF-011) |
| `fuentes_documentales` | list[{`documento`, `pagina`}] | Documentos y páginas citados (RF-011) |
| `idioma` | str | |
| `duracion_ms` | int | |

## Registro del recorrido (RF-012)

Para cada pregunta, `observability.py` agrega una línea a `logs/traza.jsonl`:

```json
{
  "timestamp": "2026-10-04T15:20:11Z",
  "pregunta": "...", "idioma": "es", "ruta": "ambas", "motivo_rechazo": null,
  "sql_ejecutado": "SELECT ...", "filas_devueltas": 7, "sql_error": null,
  "fragmentos": [{"documento": "Reglamento interno", "pagina": 2, "similitud": 0.71}],
  "respuesta": "...", "duracion_ms": 4210
}
```

(`timestamp` es la hora real de la ejecución; es un dato de registro, no de negocio, y no usa `REFERENCE_DATE`.)

Si Phoenix está activo (`docker compose --profile observability up -d`), el mismo recorrido queda como traza OpenTelemetry con las llamadas al LLM y a las tools. Si no está activo, el agente funciona igual.

## Manejo de fallas generales

- Error del LLM (cuota, red): reintentos con espera exponencial; si persisten, la respuesta es un mensaje genérico de "servicio no disponible" y el detalle va a la traza.
- Cualquier excepción no prevista en un nodo se captura en `run_question`, se registra y se devuelve un mensaje genérico; la UI nunca muestra trazas de error.
