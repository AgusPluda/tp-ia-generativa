# Constitución del proyecto: Agente SQL + RAG para gimnasio

## Principios fundamentales

### I. Reproducibilidad primero
Cualquier persona debe poder levantar el proyecto desde cero siguiendo el README.
- La base de datos (Postgres + pgvector) corre en Docker; el entorno completo se levanta con `docker compose up`.
- Los datos sintéticos se generan con un script determinista (semilla fija). Correrlo dos veces produce los mismos datos.
- Las dependencias de Python están fijadas (versiones concretas) y las credenciales viven en `.env` (nunca en el repositorio; se versiona solo `.env.example`).

### II. Acceso a datos seguro (NO NEGOCIABLE)
El agente nunca debe poder modificar la base.
- El agente se conecta con un usuario de solo lectura; el usuario administrador se usa únicamente para el esquema, la carga de datos y la ingesta.
- Solo se ejecutan sentencias `SELECT`. Toda consulta generada por el LLM se valida antes de correr.
- Las consultas tienen timeout y límite de filas.

### III. Cada fuente tiene un rol claro
- **SQL**: datos variables y transaccionales (socios, pagos, asistencias, clases, equipamiento, planes).
- **RAG**: reglas, políticas y procedimientos que viven en los PDFs.
- Un dato no debe existir en ambas fuentes (por ejemplo, los precios están solo en la base), para evitar contradicciones.
- El agente decide qué fuente consultar según la pregunta; las preguntas híbridas usan ambas.

### IV. Respuestas trazables
- Toda respuesta basada en SQL puede mostrar la consulta ejecutada.
- Toda respuesta basada en RAG indica el documento (y página, si corresponde) de origen.
- Si el agente no encuentra información suficiente, lo dice. No inventa datos.

### V. Evaluación guiada por preguntas de prueba
- Las preguntas de prueba (solo SQL, solo RAG, híbridas y casos borde) se definen en la especificación, antes de implementar.
- Existe una batería de evaluación automatizable que se ejecuta ante cada cambio relevante del agente, y sus resultados alimentan el informe técnico.

### VI. Código documentado y simple
- Docstrings en funciones y módulos públicos; README con instalación y ejecución.
- Se prefiere la solución más simple que cumpla el requisito. Alcance acotado: la entrega es el 16/10/2026.

## Restricciones técnicas
- Lenguaje: Python.
- Base de datos: PostgreSQL con la extensión pgvector, en Docker.
- Orquestación del agente: framework agéntico (LangGraph).
- Interfaz: Streamlit.
- Observabilidad: LangSmith o Phoenix (decisión diferida).
- Datos: exclusivamente sintéticos, sin datos personales reales.

## Flujo de trabajo y gobernanza
- Metodología Spec Driven Development: constitución → especificación → plan → tareas → implementación.
- Los artefactos generados (constitución, specs, plan, tasks) se versionan en el repositorio, porque forman parte de la entrega.
- Cambios a esta constitución se acuerdan entre los dos integrantes del grupo y se registran con fecha y motivo.

**Versión**: 1.0.0 | **Ratificada**: 2026-10-03
