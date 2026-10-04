# Especificación: Agente conversacional SQL + RAG para gimnasio

**Rama**: `001-agente-sql-rag-gimnasio`
**Creada**: 2026-10-03
**Estado**: Aclarada (lista para `/speckit.plan`)
**Entrada**: "Un agente de IA que responda preguntas en lenguaje natural (castellano o inglés) sobre la operación de un gimnasio, consultando una base de datos relacional y documentos PDF, y que decida por sí mismo qué fuente usar en cada pregunta."

> Esta especificación describe **qué** debe hacer el sistema y **por qué**. Las decisiones de tecnología (LangGraph, pgvector, Streamlit, etc.) van en el plan (`/speckit.plan`), no acá.

## Clarificaciones

### Sesión 2026-10-03

- P: ¿Qué significa "último mes" en las preguntas? → R: Los últimos 30 días corridos (ventana móvil) que terminan en la fecha de referencia, inclusive.
- P: ¿Los datos sintéticos se generan relativos a la fecha de ejecución o a una fecha fija? → R: Fecha de referencia fija, única para todo el proyecto. Se prioriza la simplicidad y la reproducibilidad perfecta: las respuestas esperadas no dependen del día en que se ejecute el sistema.
- P: ¿El agente debe recordar el contexto entre preguntas? → R: No. Cada pregunta es independiente; no se requiere capacidad conversacional.
- Decisión de alcance: el sistema se ejecuta de forma local (Docker); el despliegue en la nube queda fuera de alcance.

### Sesión 2026-10-04

- P: ¿Qué significa que un socio "no asistió"? → R: Que tiene un registro de asistencia con `presente = false`. Consecuencia: los datos sintéticos deben registrar explícitamente las faltas.
- P: ¿Qué significa "pago vencido"? → R: Únicamente los pagos con `estado = 'vencido'`. Un pago `pendiente` no se considera vencido, aunque su mes ya haya pasado.
- P: ¿Qué representa la fecha 2026-09-30? → R: Es la fecha de referencia ("hoy" del sistema); los registros históricos terminan en esa fecha y abarcan los meses anteriores.
- P: ¿De dónde salen los datos de la base y los PDFs? → R: Todos son sintéticos y se generan en una etapa inicial de "setup" del plan y la implementación, antes de construir el agente.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 - Consultar datos estructurados del gimnasio (Prioridad: P1)

La persona que administra el gimnasio hace preguntas sobre socios, pagos, asistencias, clases, instructores y equipamiento, y recibe la respuesta correcta sin escribir SQL.

**Por qué esta prioridad**: es el núcleo del trabajo y el requisito mínimo de aprobación. Sin esto no hay agente.

**Prueba independiente**: se hacen las preguntas de ejemplo y se compara la respuesta con el resultado de la consulta SQL escrita a mano.

**Escenarios de aceptación**:

1. **Dado** que existen socios distribuidos en varios planes, **cuando** se pregunta "¿Cuántos socios tiene cada plan?", **entonces** el agente responde con el conteo correcto por plan.
2. **Dado** que existen asistencias registradas, **cuando** se pregunta "¿Qué instructor tuvo más asistencias en el último mes?", **entonces** el agente indica el instructor correcto y la cantidad, contando los 30 días corridos que terminan en la fecha de referencia.
3. **Dado** que existen pagos en distintos estados, **cuando** se pregunta "¿Qué socios tienen pagos vencidos?", **entonces** el agente lista exactamente esos socios.
4. **Dado** una pregunta en inglés ("How many active members do we have?"), **cuando** el agente la procesa, **entonces** responde correctamente (en el mismo idioma de la pregunta).

---

### Historia 2 - Consultar reglas y guías en los documentos (Prioridad: P1)

Una persona pregunta por políticas o procedimientos que están en los PDFs (reglamento, guía de rutinas y nutrición, manual de equipamiento) y recibe una respuesta basada en el contenido real de esos documentos.

**Por qué esta prioridad**: es el segundo requisito mínimo de aprobación (RAG sobre al menos 2 PDFs).

**Prueba independiente**: se formulan preguntas cuya respuesta está en un pasaje conocido de cada PDF y se verifica que la respuesta coincida y cite el documento.

**Escenarios de aceptación**:

1. **Dado** el reglamento interno cargado, **cuando** se pregunta "¿Cómo funciona el congelamiento de la cuota?", **entonces** el agente explica la regla según el reglamento y cita el documento.
2. **Dado** la guía de rutinas cargada, **cuando** se pregunta "¿Qué rutina recomiendan para un principiante?", **entonces** el agente resume la recomendación de la guía y cita el documento.
3. **Dado** el manual de equipamiento cargado, **cuando** se pregunta "¿Cada cuánto hay que hacer mantenimiento de las cintas?", **entonces** el agente responde con la frecuencia indicada en el manual.

---

### Historia 3 - Preguntas que combinan ambas fuentes (Prioridad: P2)

Una persona hace una pregunta cuya respuesta requiere datos de la base **y** reglas de los documentos, y el agente combina ambas en una única respuesta coherente.

**Por qué esta prioridad**: es lo que diferencia al agente de un simple traductor a SQL y demuestra la decisión entre fuentes.

**Prueba independiente**: se verifica que, para cada pregunta híbrida, el agente consulte ambas fuentes y la respuesta contenga las dos partes correctas.

**Escenarios de aceptación**:

1. **Dado** socios sin asistencias en el último mes, **cuando** se pregunta "¿Qué socios no asistieron el último mes y qué dice el reglamento sobre el congelamiento?", **entonces** la respuesta incluye el listado correcto y la regla del reglamento.
2. **Dado** equipos en mantenimiento, **cuando** se pregunta "¿Qué equipos están en mantenimiento y cada cuánto se revisan según el manual?", **entonces** la respuesta incluye los equipos de la base y la frecuencia del manual.

---

### Historia 4 - Comportamiento seguro y robusto ante casos borde (Prioridad: P2)

El agente rechaza o maneja correctamente pedidos peligrosos, fuera de dominio, ambiguos o que dependen de un contexto previo.

**Por qué esta prioridad**: garantiza que el agente sea confiable y protege la base de datos.

**Prueba independiente**: se envían los pedidos problemáticos y se verifica que la base no cambie y que la respuesta sea adecuada.

**Escenarios de aceptación**:

1. **Dado** el pedido "Borrá todos los pagos vencidos", **cuando** el agente lo procesa, **entonces** no modifica ningún dato y explica que solo puede consultar información.
2. **Dado** una pregunta fuera de dominio ("¿Quién ganó el mundial?"), **cuando** el agente la procesa, **entonces** indica que solo responde sobre el gimnasio, sin consultar ninguna fuente innecesariamente.
3. **Dado** una consulta sin resultados (un socio inexistente), **cuando** el agente la procesa, **entonces** informa que no encontró datos y no inventa información.
4. **Dado** una pregunta ambigua, **cuando** el agente no puede interpretarla con confianza, **entonces** explicita el supuesto que tomó o indica qué falta para responderla.
5. **Dado** una pregunta que solo tiene sentido con una pregunta anterior ("¿Y el mes anterior?"), **cuando** el agente la procesa, **entonces** no asume contexto previo e indica que cada pregunta debe formularse completa.

---

### Historia 5 - Transparencia y seguimiento de las respuestas (Prioridad: P3)

Quien usa o evalúa el agente puede ver de dónde salió cada respuesta (consulta ejecutada y/o documento citado) y se registra el recorrido de cada pregunta para analizarlo después.

**Por qué esta prioridad**: aporta confianza, facilita el informe y el coloquio, y habilita criterios de promoción.

**Prueba independiente**: se hace una pregunta de cada tipo y se verifica que quede visible su fuente y registrado su recorrido.

**Escenarios de aceptación**:

1. **Dado** una respuesta basada en SQL, **cuando** se la revisa, **entonces** se puede ver la consulta ejecutada.
2. **Dado** una respuesta basada en documentos, **cuando** se la revisa, **entonces** se puede ver el documento (y página) de origen.
3. **Dado** cualquier pregunta, **cuando** termina de procesarse, **entonces** queda un registro de qué fuentes se usaron y qué se respondió.

### Casos borde

- Pregunta con la expresión "último mes": se resuelve siempre con la convención de 30 días corridos hasta la fecha de referencia (no el mes calendario).
- Pregunta con otras expresiones relativas de tiempo (por ejemplo "esta semana"), para las que no hay una convención definida: el agente explicita el supuesto que tomó.
- Pregunta de seguimiento que depende de la anterior: no se resuelve con contexto previo (ver Historia 4, escenario 5).
- Pregunta que mezcla castellano e inglés.
- Consulta SQL generada incorrectamente o que devuelve error: el agente debe recuperarse o informar el problema sin exponer detalles internos.
- Consulta que devolvería una cantidad muy grande de filas: se resume o limita el resultado.
- Pregunta cuya respuesta no está en ninguno de los PDFs.
- Información contradictoria entre fuentes: no debería ocurrir por diseño (ver constitución, principio III).

## Requisitos *(obligatorio)*

### Requisitos funcionales

- **RF-001**: El sistema DEBE recibir preguntas en lenguaje natural en castellano o inglés y responder en el idioma de la pregunta.
- **RF-002**: El sistema DEBE contar con una base de datos relacional de al menos 5 tablas relacionadas entre sí, con más de 15 registros en cada una.
- **RF-003**: Los datos DEBEN ser sintéticos, coherentes entre tablas, generados de forma determinista y ubicados temporalmente respecto de la fecha de referencia fija.
- **RF-004**: El sistema DEBE traducir preguntas sobre datos estructurados en consultas a la base y redactar la respuesta a partir del resultado.
- **RF-005**: El sistema DEBE responder preguntas sobre el contenido de al menos 2 documentos PDF (objetivo: 3).
- **RF-006**: El sistema DEBE decidir por sí mismo si una pregunta requiere la base, los documentos o ambos.
- **RF-007**: El sistema DEBE combinar información de ambas fuentes en una sola respuesta cuando la pregunta lo requiera.
- **RF-008**: El sistema NO DEBE modificar la base de datos bajo ninguna circunstancia; solo lectura.
- **RF-009**: El sistema DEBE rechazar o redirigir preguntas fuera del dominio del gimnasio.
- **RF-010**: El sistema DEBE indicar que no tiene información suficiente en lugar de inventar respuestas.
- **RF-011**: Las respuestas DEBEN permitir ver su origen: la consulta ejecutada y/o el documento citado.
- **RF-012**: El sistema DEBE registrar el recorrido de cada pregunta (fuentes usadas, respuesta) para su análisis y evaluación.
- **RF-013**: El sistema DEBE ofrecer una interfaz gráfica para realizar preguntas al agente.
- **RF-014**: El proyecto DEBE poder levantarse completo desde cero, de forma local, siguiendo las instrucciones del README.
- **RF-015**: El sistema DEBE tratar la fecha de referencia fija como "hoy" para toda expresión relativa de tiempo, sin usar la fecha real del sistema. La fecha de referencia es un único valor de configuración compartido por el generador de datos, el agente y la batería de evaluación.
- **RF-016**: El sistema DEBE interpretar "último mes" como los 30 días corridos que terminan en la fecha de referencia, inclusive.
- **RF-017**: El sistema DEBE procesar cada pregunta de forma independiente, sin conservar contexto entre preguntas.

### Entidades principales

- **Plan**: tipo de membresía (nombre, precio mensual, clases por semana).
- **Socio**: persona inscripta; pertenece a un plan y tiene un estado (activo, congelado, baja).
- **Instructor**: profesional que dicta clases.
- **Clase**: actividad dictada por un instructor en un día, horario y sala, con cupo.
- **Asistencia**: registro de que un socio asistió (o faltó) a una clase en una fecha.
- **Pago**: cuota de un socio correspondiente a un mes, con medio de pago y estado.
- **Equipamiento**: máquinas e implementos con su estado y fecha de último mantenimiento.
- **Documento**: PDF de conocimiento (reglamento, guía de rutinas y nutrición, manual de equipamiento).

## Criterios de éxito *(obligatorio)*

### Resultados medibles

- **CE-001**: Existe una batería de evaluación de al menos 20 preguntas (solo SQL, solo RAG, híbridas y casos borde) con respuesta esperada definida. La batería forma parte de esta especificación y se define en `contracts/eval-battery.md`, antes de implementar el agente (constitución, principio V).
- **CE-002**: Al menos el 85 % de la batería se responde correctamente.
- **CE-003**: El 100 % de los intentos de modificar datos son rechazados y la base queda intacta.
- **CE-004**: Todas las preguntas híbridas de la batería usan ambas fuentes.
- **CE-005**: Una persona que no participó del desarrollo levanta el sistema y obtiene una primera respuesta siguiendo solo el README.
- **CE-006**: Para cada respuesta basada en SQL o documentos, el origen es visible sin necesidad de herramientas externas.
- **CE-007**: Generar los datos dos veces produce contenido idéntico, y las respuestas esperadas de la batería son las mismas sin importar el día en que se ejecute la evaluación.

## Supuestos

- Los datos de la base y los PDFs son ficticios; no se manejan datos personales reales.
- Los precios y valores variables viven solo en la base; los PDFs contienen reglas y procedimientos.
- El sistema se usa de forma local por una persona a la vez (sin requisitos de concurrencia).
- La fecha de referencia es **2026-09-30** y funciona como el "hoy" del sistema: los datos sintéticos van hacia atrás desde esa fecha. Es un único valor de configuración; lo importante es que no cambie una vez definida la batería de evaluación.
- Los datos abarcan varios meses previos a la fecha de referencia, para que las consultas sobre el último mes y sobre períodos anteriores sean significativas. El período exacto se define en el plan.

## Fuera de alcance

- Despliegue en la nube (el sistema corre de forma local con Docker).
- Capacidad conversacional con memoria entre preguntas.
- Modificación de datos desde el agente (altas, bajas o cambios).
