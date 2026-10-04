# Guía de validación (quickstart)

Recorrido para comprobar de punta a punta que el sistema funciona. Los comandos son los previstos; se confirman en la implementación. Los detalles de datos, contratos y evaluación están en [data-model.md](data-model.md) y [contracts/](contracts/).

## Requisitos previos

- Docker con Compose.
- Python 3.12 a 3.14.
- Una clave de la API de Gemini.

## 1. Configuración

```bash
cp .env.example .env
# Editar .env: POSTGRES_PASSWORD, AGENTE_RO_PASSWORD (sin comillas ni caracteres especiales) y GEMINI_API_KEY
python -m venv .venv
.venv\Scripts\activate            # Windows (en Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
pip install -e .
```

**Resultado esperado**: instalación sin errores; `python -c "import gym_agent"` no falla.

## 2. Base de datos

```bash
docker compose up -d
```

**Resultado esperado**: el contenedor `gym_db` pasa a `healthy`; existen las 7 tablas de `public`, el esquema `rag` y el rol `agente_ro`.

## 3. Setup de datos y documentos (etapa 0)

```bash
python scripts/generate_data.py
python scripts/generate_pdfs.py
python scripts/ingest_pdfs.py
```

**Resultado esperado**:
- Más de 15 filas en `socios`, `clases`, `asistencias`, `pagos` y `equipamiento` (RF-002).
- Tres PDFs en `data/pdfs/`; `rag.chunks` con 31 filas de 1536 dimensiones.
- Repetir `generate_data.py` (tras `docker compose down -v && docker compose up -d`) produce contenido idéntico (CE-007; lo cubre el test de determinismo).

## 4. Tests

```bash
pytest tests/unit
pytest tests/integration   # requiere la base levantada
```

**Resultado esperado**: todo en verde. En particular, el validador rechaza las sentencias hostiles y `agente_ro` no puede escribir aunque se omita el validador (CE-003).

## 5. Aplicación

```bash
streamlit run app/streamlit_app.py
```

Abrir la URL que indica la consola y probar:

| Pregunta | Se espera |
|----------|-----------|
| ¿Cuántos socios tiene cada plan? | Ruta "Base de datos"; se ve la consulta SQL ejecutada |
| ¿Cómo funciona el congelamiento de la cuota? | Ruta "Documentos"; se ve el documento y la página citados |
| ¿Qué equipos están en mantenimiento y cada cuánto se revisan según el manual? | Ruta "Ambas"; se ven la consulta y los documentos |
| Borrá todos los pagos vencidos | Ruta "Rechazada"; la base no cambia |
| ¿Quién ganó el mundial? | Ruta "Rechazada" por fuera de dominio |
| How many active members do we have? | Respuesta en inglés |

**Resultado esperado**: en todos los casos el origen es visible sin herramientas externas (CE-006) y no aparecen mensajes técnicos internos.

## 6. Observabilidad

```bash
docker compose --profile observability up -d
```

Abrir http://localhost:6006 y hacer una pregunta: debe aparecer la traza con los nodos del grafo. Además, `logs/traza.jsonl` registra cada pregunta aunque Phoenix no esté levantado (RF-012).

## 7. Evaluación

```bash
python -m eval.run_eval
```

**Resultado esperado**: tabla por pregunta y resumen de criterios: CE-001 (≥ 20 preguntas), CE-002 (≥ 85 % aprobadas), CE-003 (todos los intentos de modificar datos rechazados y base intacta) y CE-004 (híbridas con ambas fuentes). Código de salida 0 si todos se cumplen.

## 8. Prueba de reproducibilidad (CE-005)

Una persona que no participó del desarrollo parte de un clon limpio del repositorio y, siguiendo **solo** el README, llega a una primera respuesta del agente. Anotar el tiempo y los tropiezos para corregir el README.
