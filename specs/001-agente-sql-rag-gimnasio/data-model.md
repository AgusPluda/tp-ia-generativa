# Modelo de datos

Documenta el esquema **tal como está** en [db/init/01_schema.sql](../../db/init/01_schema.sql) y los permisos de [db/init/02_roles.sh](../../db/init/02_roles.sh). Este plan no propone cambios; los problemas detectados figuran como observaciones al final.

## Esquema `public` (datos de negocio, los consulta la SQL tool)

```text
planes 1───* socios 1───* asistencias *───1 clases *───1 instructores
                 1
                 │
                 *
               pagos                         equipamiento (independiente)
```

### planes
| Columna | Tipo | Restricciones |
|---------|------|---------------|
| id_plan | SERIAL | PK |
| nombre | VARCHAR(50) | NOT NULL, UNIQUE |
| precio_mensual | NUMERIC(10,2) | NOT NULL, > 0 |
| clases_por_semana | INT | NOT NULL, >= 0 |
| duracion_meses | INT | NOT NULL, DEFAULT 1, > 0 |

### socios
| Columna | Tipo | Restricciones |
|---------|------|---------------|
| id_socio | SERIAL | PK |
| nombre, apellido | VARCHAR(60) | NOT NULL |
| email | VARCHAR(120) | NOT NULL, UNIQUE |
| fecha_nacimiento | DATE | NOT NULL |
| fecha_alta | DATE | NOT NULL |
| id_plan | INT | NOT NULL, FK → planes |
| estado | VARCHAR(10) | NOT NULL, DEFAULT `activo`; valores: `activo`, `congelado`, `baja` |

### instructores
| Columna | Tipo | Restricciones |
|---------|------|---------------|
| id_instructor | SERIAL | PK |
| nombre, apellido | VARCHAR(60) | NOT NULL |
| especialidad | VARCHAR(60) | NOT NULL |
| fecha_ingreso | DATE | NOT NULL |

### clases
| Columna | Tipo | Restricciones |
|---------|------|---------------|
| id_clase | SERIAL | PK |
| nombre | VARCHAR(60) | NOT NULL |
| id_instructor | INT | NOT NULL, FK → instructores |
| dia_semana | VARCHAR(10) | NOT NULL; valores sin tilde: `lunes`, `martes`, `miercoles`, `jueves`, `viernes`, `sabado`, `domingo` |
| hora | TIME | NOT NULL |
| cupo | INT | NOT NULL, > 0 |
| sala | VARCHAR(30) | NOT NULL |

### asistencias
| Columna | Tipo | Restricciones |
|---------|------|---------------|
| id_asistencia | SERIAL | PK |
| id_socio | INT | NOT NULL, FK → socios |
| id_clase | INT | NOT NULL, FK → clases |
| fecha | DATE | NOT NULL |
| presente | BOOLEAN | NOT NULL, DEFAULT TRUE |
| | | UNIQUE (id_socio, id_clase, fecha) |

### pagos
| Columna | Tipo | Restricciones |
|---------|------|---------------|
| id_pago | SERIAL | PK |
| id_socio | INT | NOT NULL, FK → socios |
| fecha_pago | DATE | NULL mientras el pago está pendiente |
| monto | NUMERIC(10,2) | NOT NULL, > 0 |
| mes_correspondiente | DATE | NOT NULL; primer día del mes que se paga |
| medio_pago | VARCHAR(20) | NOT NULL; valores: `efectivo`, `transferencia`, `tarjeta`, `mercado_pago` |
| estado | VARCHAR(10) | NOT NULL; valores: `pagado`, `pendiente`, `vencido` |

### equipamiento
| Columna | Tipo | Restricciones |
|---------|------|---------------|
| id_equipo | SERIAL | PK |
| nombre | VARCHAR(80) | NOT NULL |
| tipo | VARCHAR(40) | NOT NULL |
| sala | VARCHAR(30) | NOT NULL |
| estado | VARCHAR(20) | NOT NULL; valores: `operativo`, `en_mantenimiento`, `fuera_de_servicio` |
| fecha_adquisicion | DATE | NOT NULL |
| ultimo_mantenimiento | DATE | NULL permitido |

**Índices**: `idx_socios_plan`, `idx_asistencias_socio (id_socio, fecha)`, `idx_asistencias_clase`, `idx_pagos_socio_mes (id_socio, mes_correspondiente)`.

## Esquema `rag` (almacenamiento vectorial, lo consulta la RAG tool)

### rag.documentos
| Columna | Tipo | Restricciones |
|---------|------|---------------|
| id_documento | SERIAL | PK |
| nombre_archivo | VARCHAR(200) | NOT NULL, UNIQUE |
| titulo | VARCHAR(200) | NOT NULL |
| fecha_ingesta | TIMESTAMP | NOT NULL, DEFAULT now() |

### rag.chunks
| Columna | Tipo | Restricciones |
|---------|------|---------------|
| id_chunk | SERIAL | PK |
| id_documento | INT | NOT NULL, FK → rag.documentos, ON DELETE CASCADE |
| pagina | INT | NULL permitido |
| orden | INT | NOT NULL |
| contenido | TEXT | NOT NULL |
| embedding | vector(1536) | NOT NULL |

**Índice**: `idx_chunks_embedding` (HNSW, `vector_cosine_ops`).

## Roles y permisos

| Rol | Uso | Permisos |
|-----|-----|----------|
| `POSTGRES_USER` (`gym_admin`) | Setup: esquema, carga de datos, ingesta | Todos (propietario) |
| `agente_ro` | Agente (SQL tool y RAG tool) | `CONNECT`, `USAGE` sobre `public` y `rag`, `SELECT` sobre todas sus tablas; `default_transaction_read_only = on`; `statement_timeout = 5s` |

## Correspondencia con las entidades de la spec

| Entidad de la spec | Dónde vive |
|--------------------|------------|
| Plan, Socio, Instructor, Clase, Asistencia, Pago, Equipamiento | Tablas homónimas de `public` |
| Documento | `rag.documentos` (metadatos) y `rag.chunks` (contenido); los PDFs en `data/pdfs/` |

## Definiciones de negocio que el agente debe respetar

Derivadas de la spec (sesiones de clarificación del 2026-10-03 y 2026-10-04):

| Expresión | Se traduce en |
|-----------|---------------|
| "Hoy" | `REFERENCE_DATE` = 2026-09-30 (nunca `CURRENT_DATE`) |
| "Último mes" | `fecha BETWEEN REFERENCE_DATE - 29 AND REFERENCE_DATE` (30 días corridos, inclusive) |
| "No asistió" | `asistencias.presente = false` |
| "Asistió" | `asistencias.presente = true` |
| "Pago vencido" | `pagos.estado = 'vencido'` (un `pendiente` no es vencido) |
| "Socio activo" | `socios.estado = 'activo'` |
| "Equipo en mantenimiento" | `equipamiento.estado = 'en_mantenimiento'` |

## Invariantes que debe cumplir el generador de datos

Como el esquema no los impone con restricciones, el generador los garantiza por construcción y los verifican los tests:

1. Todas las fechas son menores o iguales a `REFERENCE_DATE`; el historial abarca del 2026-04-01 al 2026-09-30.
2. `asistencias.fecha` cae en el `dia_semana` de la clase correspondiente, y es posterior o igual a `socios.fecha_alta`.
3. Un socio en estado `baja` no tiene asistencias posteriores a su salida; uno `congelado` no tiene asistencias `presente = true` en el último mes.
4. Un pago `pagado` tiene `fecha_pago` no nulo; uno `pendiente` o `vencido` lo tiene nulo.
5. A lo sumo un pago por (`id_socio`, `mes_correspondiente`); `monto` coincide con el `precio_mensual` del plan.
6. `equipamiento.tipo` pertenece al conjunto de tipos descritos en el manual de equipamiento; `ultimo_mantenimiento` ≥ `fecha_adquisicion`.
7. Las faltas (`presente = false`) se registran explícitamente (definición de "no asistió").
8. Dos ejecuciones producen contenido idéntico (se compara un hash por tabla).

## Observaciones sobre el esquema existente

No se modificó nada; son puntos a tener en cuenta.

1. **Dimensión del embedding**: `vector(1536)` **coincide** con `gemini-embedding-001` configurado a 1536 dimensiones. No hace falta cambiar el esquema. Se agrega una tarea de verificación al ingestar (fallar si el vector no tiene 1536 elementos).
2. **`agente_ro` puede leer `rag`**: el permiso es necesario para la RAG tool, pero significa que una consulta SQL generada por el LLM podría leer `rag.chunks`. Se resuelve en la aplicación (el validador rechaza el esquema `rag`; ver [contracts/sql-tool.md](contracts/sql-tool.md)). Un rol separado sería más limpio.
3. **`AGENTE_RO_PASSWORD` comentada en `.env.example`**: si queda vacía, `02_roles.sh` crea el rol con contraseña vacía. El README debe indicar que es obligatoria. Además, el script usa la clave dentro de un heredoc SQL, por lo que no debe llevar comillas simples.
4. **Sin restricciones de coherencia entre tablas**: no hay `UNIQUE (id_socio, mes_correspondiente)` en `pagos`, ni relación entre `pagos.estado` y `fecha_pago`, ni entre `asistencias.fecha` y `clases.dia_semana`. Se cubre con los invariantes de arriba.
5. **`socios` no guarda fecha de baja ni de congelamiento**: preguntas como "¿desde cuándo está congelado?" no se pueden responder; el agente debe decir que no hay información.
6. **`rag.documentos.fecha_ingesta DEFAULT now()`** es no determinista. No afecta a CE-007 (que se refiere a los datos de negocio), pero la comparación por hash excluye el esquema `rag`.
7. **`dia_semana` sin tildes** (`miercoles`, `sabado`): el glosario del prompt de la SQL tool lo indica para evitar consultas que no devuelven filas.
8. **RF-002**: exige más de 15 registros en cada una de al menos 5 tablas. `planes` (5 filas) e `instructores` (8 filas) quedan por debajo; el requisito se cumple con `socios`, `clases`, `asistencias`, `pagos` y `equipamiento`.
9. **`docker-compose.yml`**: la imagen de Phoenix usa `latest` (se fija a `version-20.19.0`) y `env_file: .env` pasa también `GEMINI_API_KEY` al contenedor de la base, sin necesidad. Ambos son ajustes menores de la Etapa 0.
10. **La carga de datos y la ingesta** corren como `POSTGRES_USER` desde el host (`localhost:${POSTGRES_PORT}`); los scripts de `db/init` solo corren al crear el volumen, por lo que reiniciar desde cero requiere `docker compose down -v`.
