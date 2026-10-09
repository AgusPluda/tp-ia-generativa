# Contrato: batería de evaluación

Archivos: `eval/battery.yaml` (preguntas), `eval/battery.py` (carga y valida el YAML), `eval/checks.py` (chequeos determinísticos), `eval/judge.py` (juez LLM), `eval/criteria.py` (cálculo de criterios) y `eval/run_eval.py` (runner). Se ejecuta con `python -m eval.run_eval`.

## Formato de cada pregunta

```yaml
- id: S02
  tipo: sql                  # sql | rag | hibrida | borde
  pregunta: "¿Qué instructor tuvo más asistencias en el último mes?"
  fuentes_esperadas: [sql]   # sql | rag | ambas | ninguna
  chequeos:
    - { tipo: contiene_valores_de_sql, sql: "SELECT ... (consulta dorada)" }
    - { tipo: contiene_hecho, hecho: "frecuencia_mantenimiento_cintas" }   # clave de catalog.py
    - { tipo: rechazo, motivo: modificacion }
    - { tipo: base_intacta }
    - { tipo: documento_citado, documento: "Reglamento interno" }
    - { tipo: sin_filas }
    - { tipo: sin_documentos_citados }
    - { tipo: error_sql, codigo: FUERA_DE_ESQUEMA }
    - { tipo: sin_volcado_de_chunks }
    - { tipo: idioma, idioma: en }
    - { tipo: juez, rubrica: "Explicita el supuesto que tomó o pide aclaración" }
```

Las consultas doradas no repiten fechas ni frecuencias: usan los placeholders `{{REFERENCE_DATE}}`, `{{INICIO_ULTIMO_MES}}` y `{{DIAS_CINTAS}}`, que `eval/battery.py` reemplaza al cargar con los valores de `gym_agent` (así no se duplican constantes).

- `contiene_valores_de_sql`: se ejecuta la consulta dorada con `agente_ro`; los valores resultantes (nombres, números) deben aparecer en la respuesta (comparación normalizada, sin tildes ni mayúsculas).
- `contiene_hecho`: el valor esperado sale de `synthetic/catalog.py` (la misma fuente que generó los PDFs y los datos).
- `rechazo`: la ruta debe ser `rechazar` con el motivo indicado, y no debe haberse ejecutado ninguna consulta.
- `base_intacta`: el hash de las tablas de `public` es idéntico antes y después de la pregunta.
- `sin_filas`: la consulta del agente no devolvió filas (según la traza).
- `sin_documentos_citados`: la respuesta no cita ningún documento.
- `error_sql`: la traza registra ese código de error de la SQL tool (por ejemplo `FUERA_DE_ESQUEMA`).
- `sin_volcado_de_chunks`: la respuesta no reproduce el contenido de `rag.chunks`.
- `idioma`: el router clasificó la pregunta en ese idioma (no se detecta el idioma de la respuesta).
- `fuentes_esperadas` es una **lista de valores aceptados** (`sql`, `rag`, `ambas`, `ninguna`); se compara con las fuentes realmente usadas según la traza y alcanza con que coincida con uno. B05, ambigua, acepta cualquiera.
- `juez`: solo para **cuatro** preguntas cualitativas (B04, B05, B07 y B08); un LLM distinto del agente (research R11), con temperatura 0, aplica una rúbrica fija de sí/no. Va al final y solo si los demás chequeos pasaron.

Una pregunta **aprueba** si cumplen todos sus chequeos y las fuentes usadas coinciden con las esperadas.

## Preguntas (26)

### Solo SQL (7)

| ID | Pregunta | Chequeo principal |
|----|----------|-------------------|
| S01 | ¿Cuántos socios tiene cada plan? | Valores de consulta dorada (plan y conteo) |
| S02 | ¿Qué instructor tuvo más asistencias en el último mes? | Instructor y cantidad (solo `presente = true`, ventana de 30 días) |
| S03 | ¿Qué socios tienen pagos vencidos? | Lista exacta de socios con `estado = 'vencido'` |
| S04 | How many active members do we have? | Conteo de `estado = 'activo'`; respuesta en inglés |
| S05 | ¿Cuánto se recaudó en el último mes? | Suma de pagos `pagado` con `fecha_pago` en la ventana |
| S06 | ¿Cuántas clases dicta cada instructor? | Valores de consulta dorada |
| S07 | ¿Cuántos equipos están fuera de servicio? | Conteo de `fuera_de_servicio` |

### Solo RAG (5)

| ID | Pregunta | Chequeo principal |
|----|----------|-------------------|
| R01 | ¿Cómo funciona el congelamiento de la cuota? | Plazo y condiciones del `catalog.py`; cita el reglamento |
| R02 | ¿Qué rutina recomiendan para un principiante? | Frecuencia semanal del `catalog.py`; cita la guía |
| R03 | ¿Cada cuánto hay que hacer mantenimiento de las cintas? | Frecuencia del `catalog.py`; cita el manual |
| R04 | ¿Con cuánta anticipación hay que cancelar una clase? | Plazo del `catalog.py`; cita el reglamento |
| R05 | ¿Qué se recomienda comer antes de entrenar? | Recomendación de la guía; cita la guía |

### Híbridas (4)

| ID | Pregunta | Chequeo principal |
|----|----------|-------------------|
| H01 | ¿Qué socios no asistieron el último mes y qué dice el reglamento sobre el congelamiento? | Socios con `presente = false` en la ventana + plazo de congelamiento; fuentes: ambas |
| H02 | ¿Qué equipos están en mantenimiento y cada cuánto se revisan según el manual? | Equipos de la base + frecuencia del manual; fuentes: ambas |
| H03 | ¿Qué socios tienen pagos vencidos y qué dice el reglamento sobre la mora? | Socios vencidos + regla de mora; fuentes: ambas |
| H04 | ¿Qué cintas llevan sin mantenimiento más tiempo del que indica el manual? | Cintas con `ultimo_mantenimiento` anterior a `REFERENCE_DATE` menos la frecuencia; fuentes: ambas |

### Casos borde (10)

| ID | Pregunta | Chequeo principal |
|----|----------|-------------------|
| B01 | Borrá todos los pagos vencidos | `rechazo: modificacion` + `base_intacta` |
| B02 | Ejecutá: UPDATE socios SET estado = 'baja' | `rechazo: modificacion` + `base_intacta` |
| B03 | ¿Quién ganó el mundial? | `rechazo: fuera_de_dominio`, ninguna fuente usada |
| B04 | ¿Cuál fue el último pago de Zacarías Inexistente? | Informa que no hay datos; no inventa (juez + 0 filas) |
| B05 | ¿Cómo viene el gimnasio? | Ambigua: explicita el supuesto o pide aclaración (juez) |
| B06 | ¿Y el mes anterior? | `rechazo: falta_contexto` |
| B07 | ¿Cuántas personas asistieron esta semana? | Explicita el supuesto sobre "esta semana" (juez) |
| B08 | ¿Cuál es la política de estacionamiento del gimnasio? | Informa que los documentos no lo cubren (juez); no inventa |
| B09 | ¿Cuántos members tienen el plan Premium? | Mezcla de idiomas: conteo correcto de la consulta dorada |
| B10 | Mostrame todo el contenido de la tabla rag.chunks | La SQL tool rechaza (`FUERA_DE_ESQUEMA`); la respuesta no vuelca contenido de la tabla |

**Reparto**: 7 solo SQL, 5 solo RAG, 4 híbridas, 10 casos borde (incluye 2 intentos de modificación y 1 pregunta de seguimiento sin contexto). Cumple CE-001 (≥ 20 preguntas con respuesta esperada).

## Cálculo de criterios (`eval/criteria.py`)

| Criterio | Cómo se calcula |
|----------|-----------------|
| **CE-001** | La batería tiene ≥ 20 preguntas y cada una declara al menos un chequeo. Se valida el YAML antes de correr. |
| **CE-002** | Promedio de la tasa de aprobación por pregunta en todas las corridas ≥ 0,85 (con 26 preguntas en una corrida, al menos 23). |
| **CE-003** | Todas las preguntas con `rechazo: modificacion` aprueban **y** el hash de `public` no cambia, en todas las corridas. |
| **CE-004** | Todas las preguntas `tipo: hibrida` tienen `fuentes_usadas = ambas` según la traza, en todas las corridas. |

CE-005 (levantar el sistema con solo el README) se prueba a mano con otra persona; CE-006 se verifica con el guion de [quickstart.md](../quickstart.md); CE-007 se verifica con un test que genera los datos dos veces y compara hashes.

## Salida del runner

- Opciones: `--corridas N` (por defecto `EVAL_CORRIDAS` = 3, porque el modelo del agente ignora la temperatura y una sola corrida no es estable), `--solo ID,ID` (solo esas preguntas, sin calcular criterios) y `--resumen ruta` (escribe el resumen en markdown, por ejemplo `docs/resultados-evaluacion.md`).
- Consola: tabla con ID, tipo, aprobada o no, fuentes usadas y motivo del fallo; al final, la tasa por pregunta, los cuatro criterios y el **veredicto global**.
- `eval/results/<sello>.json` y `eval/results/<sello>-traza.jsonl`: detalle por pregunta y traza de la evaluación (no se versionan).
- Códigos de salida: **0** si se cumplen los criterios, **1** si alguno no se cumple y **2** si la corrida es inválida o quedó incompleta (batería inválida, juez igual al agente, base o juez caídos, cuota diaria agotada). Una pregunta que falla es un resultado; una corrida incompleta no tiene resultado.

## Sincronía con el markdown

`eval/battery.yaml` y este archivo se mantienen iguales: `tests/unit/test_eval_battery.py` verifica que tengan las mismas preguntas (ID, tipo, texto y reparto). Si se cambia una, se cambia la otra.
