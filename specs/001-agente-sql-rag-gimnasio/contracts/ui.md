# Contrato: interfaz Streamlit

Entrada: `app/streamlit_app.py`. Se ejecuta con `streamlit run app/streamlit_app.py` **desde la raíz del repositorio** (ahí lee `.streamlit/config.toml`). Llama a `run_question` en el mismo proceso. La app importa solo `streamlit`, `gym_agent.graph` y `gym_agent.presentacion`.

## Estructura

| Archivo | Contenido |
|---------|-----------|
| `app/streamlit_app.py` | `set_page_config` (título "Gym AI Agent" e ícono 🏋️), `st.logo` (`app/logo.svg`), navegación nativa (`st.navigation`) y bloque de Phoenix en la barra lateral |
| `app/paginas/chat.py` | Página "Chat" (por defecto) |
| `app/paginas/preguntas.py` | Página "Preguntas evaluativas" |
| `src/gym_agent/presentacion.py` | Etiquetas de ruta, citas, escape de `$`, ejemplos, lectura de la batería y URL de Phoenix; no importa `streamlit`, `gym_agent.tools` ni `gym_agent.db` |
| `.streamlit/config.toml` | Tema y servidor |

## Diseño

- **Tema oscuro** con acento naranja (`#FF7043`) y `gatherUsageStats = false`. `headless = true`: sin él Streamlit pide un correo por consola y no arranca (R16); por eso el navegador **no se abre solo** y hay que abrir la URL que imprime la consola.
- **Barra lateral permanente**: el título "🏋️ Gym AI Agent" arriba, luego las páginas "Chat" y "Preguntas evaluativas", y debajo el botón "Observabilidad en Phoenix" (link a `http://localhost:6006`, derivado de `PHOENIX_ENDPOINT`) con el aviso de que requiere `docker compose --profile observability up -d`.

## Página "Chat"

| Elemento | Comportamiento |
|----------|----------------|
| Título y texto de ayuda | "🏋️ Gym AI Agent"; indica que el agente responde sobre el gimnasio y que cada pregunta se procesa de forma independiente |
| Ejemplos | Una fila de tres botones arriba del campo, con etiqueta corta ("Socios por plan", "Congelamiento de cuota", "Equipos en mantenimiento") y la pregunta completa como tooltip. Son S01, R01 y H02 de la batería. Al hacer clic rellenan el campo con la pregunta completa, sin enviarla. Claves `ejemplo_0` a `ejemplo_2` |
| Campo de pregunta | Texto libre, castellano o inglés; clave `pregunta`. Se envía con el botón "Preguntar" (clave `preguntar`) o con Enter |
| Pregunta en blanco | Aviso "Escribí una pregunta." y no se llama a `run_question` |
| Estado de carga | Indicador "Pensando..." mientras se procesa |
| Respuesta | Texto de `respuesta`, en el idioma de la pregunta; cada `$` se escapa para que Streamlit no lo tome como fórmula |
| Etiqueta de ruta | "Fuente: Base de datos", "Documentos", "Ambas" o "Rechazada"; "No disponible" cuando `fallo` es verdadero |
| Desplegable "Consulta SQL ejecutada" | Visible solo si `sql_ejecutado` no es nulo; muestra la consulta tal como se ejecutó, sin reformatear (CE-006) |
| Desplegable "Documentos citados" | Visible solo si hay `fuentes_documentales`; lista "Documento, p. N" (CE-006). No aparece en B08 (los documentos no cubren la pregunta) |
| Falla | Si `fallo` es verdadero o `run_question` lanza, `st.error` con el mensaje genérico; nunca se muestran trazas ni mensajes internos |
| Duración | "Respondido en N s" |

Una pregunta rechazada (modificación, fuera de dominio, falta de contexto) se muestra como respuesta normal con la etiqueta "Rechazada"; solo una falla real se muestra como error.

## Página "Preguntas evaluativas"

Una sola página que lista la batería de [eval-battery.md](eval-battery.md), como en el markdown: un subtítulo por sección con su cantidad ("Solo SQL (7)", "Solo RAG (5)", "Híbridas (4)", "Casos borde (10)") y una tabla con ID, Pregunta y Chequeo principal. Solo muestra: no envía preguntas al agente. La fuente es el markdown; en la Etapa 4, cuando exista `eval/battery.yaml`, un test verifica que ambos tengan las mismas preguntas.

## No incluye

Historial de conversación (RF-017, sin memoria entre preguntas), autenticación ni edición de datos.

## Pruebas

- `tests/unit/test_streamlit_app.py` y `tests/unit/test_presentacion.py`: `AppTest` con `run_question` falso y lógica de presentación, sin LLM ni base.
- `tests/integration/test_app_llm.py` (marcador `llm`): la app con el LLM y la base reales.
- Verificación manual guiada en [quickstart.md](../quickstart.md) (CE-006): una pregunta de cada tipo y comprobación de que el origen es visible sin herramientas externas.
