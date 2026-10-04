# Contrato: SQL tool

Módulo: `src/gym_agent/tools/sql_tool.py` (validación en `sql_validator.py`).

## Entrada

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `pregunta` | str | Pregunta del usuario, tal como llegó |
| `idioma` | `"es"` \| `"en"` | Lo determina el router |

El esquema que ve el LLM se arma al iniciar a partir de `information_schema` **solo para `public`** (tablas, columnas, tipos, claves foráneas), más el glosario de negocio de [data-model.md](../data-model.md#definiciones-de-negocio-que-el-agente-debe-respetar) y la fecha de referencia ("hoy es 2026-09-30"). El esquema `rag` nunca se incluye.

## Salida (`ResultadoSQL`)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `ok` | bool | `true` si se ejecutó una consulta válida |
| `sql_ejecutado` | str \| null | La consulta que efectivamente corrió (la que se muestra en la UI) |
| `columnas` | list[str] | Nombres de columna |
| `filas` | list[list] | Hasta 50 filas |
| `truncado` | bool | Había más de 50 filas |
| `intentos` | int | Cantidad de consultas generadas (1 a 3) |
| `error` | `ErrorSQL` \| null | Presente si `ok = false` |

Una consulta válida que devuelve 0 filas es `ok = true` con `filas = []`; el nodo de síntesis lo informa como "sin datos" (RF-010).

## Pipeline

1. **Generar**: el LLM produce un único `SELECT` (salida estructurada con un campo `sql`).
2. **Validar** (`sql_validator.validar(sql)`), sin tocar la base. Se rechaza si:
   - no se puede parsear como Postgres;
   - hay más de un statement;
   - la raíz no es `SELECT` (se admite `WITH ... SELECT`); cualquier `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `GRANT`, `COPY`, `CALL`, `DO`, `SET`, `SELECT ... INTO`, o `FOR UPDATE`;
   - referencia el esquema `rag`, `pg_catalog` o `information_schema`;
   - usa funciones de reloj (`now`, `current_date`, `current_timestamp`, `current_time`, `localtimestamp`, `clock_timestamp`, `statement_timestamp`, `transaction_timestamp`) o cualquier `pg_*` (`pg_sleep`, `pg_read_file`, etc.), o `set_config`, `lo_*`, `dblink`.
3. **Ejecutar** con `agente_ro` dentro de una transacción de solo lectura, con `statement_timeout` de 5 s (ya definido en el rol; se reafirma por sesión). Se leen como máximo 51 filas.
4. **Recuperar**: si la validación o la ejecución fallan, se reintenta hasta 2 veces más, pasando al LLM el mensaje de error **saneado** (sin nombres de host, usuario ni rutas). Si siguen los fallos, `ok = false`.

## Errores (`ErrorSQL`)

| `codigo` | Cuándo | Mensaje al usuario (el nodo de síntesis lo redacta, sin detalles internos) |
|----------|--------|--------|
| `NO_ES_SELECT` | La consulta no es de solo lectura | "Solo puedo consultar información; no puedo modificar datos." |
| `FUERA_DE_ESQUEMA` | Menciona `rag`, catálogo del sistema | "No puedo consultar esa información." |
| `INVALIDA` | No se puede parsear o usa funciones no permitidas tras los reintentos | "No pude armar una consulta válida para esa pregunta." |
| `TIMEOUT` | Superó los 5 s | "La consulta tardó demasiado; probá con una pregunta más acotada." |
| `ERROR_EJECUCION` | Error de la base tras los reintentos | "No pude obtener los datos en este momento." |

El campo `detalle` (texto técnico del error) se guarda **solo** en la traza JSONL y Phoenix; nunca llega a la respuesta ni a la UI.

## Garantías de seguridad (tres capas independientes)

1. Validador de aplicación (arriba).
2. Rol `agente_ro` sin permisos de escritura (`GRANT SELECT` únicamente).
3. `default_transaction_read_only = on` y `statement_timeout = 5s` en el rol.

Verificado por tests: una batería de sentencias hostiles (`DROP`, `;` encadenados, comentarios que esconden un `DELETE`, `SELECT pg_sleep(10)`, `SELECT * FROM rag.chunks`, `SELECT now()`) debe ser rechazada por el validador; y, con el validador deshabilitado a propósito, la base debe rechazar igualmente las escrituras.
