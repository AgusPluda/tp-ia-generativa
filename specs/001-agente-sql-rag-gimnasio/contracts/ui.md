# Contrato: interfaz Streamlit

Archivo: `app/streamlit_app.py`. Se ejecuta con `streamlit run app/streamlit_app.py`. Llama a `run_question` en el mismo proceso.

## Elementos

| Elemento | Comportamiento |
|----------|----------------|
| Título y texto de ayuda | Indica que el agente responde sobre el gimnasio y que cada pregunta se procesa de forma independiente |
| Campo de pregunta | Texto libre, castellano o inglés; envía con el botón "Preguntar" o con Enter |
| Respuesta | Texto de `respuesta`, en el idioma de la pregunta |
| Etiqueta de ruta | Muestra la fuente usada: "Base de datos", "Documentos", "Ambas" o "Rechazada" |
| Desplegable "Consulta SQL ejecutada" | Visible solo si `sql_ejecutado` no es nulo; muestra la consulta con formato SQL (CE-006) |
| Desplegable "Documentos citados" | Visible solo si hay `fuentes_documentales`; lista documento y página (CE-006) |
| Estado de carga | Indicador mientras se procesa la pregunta |
| Error | Mensaje genérico; nunca se muestran trazas ni mensajes internos |
| Ejemplos | Tres preguntas de ejemplo (una de SQL, una de RAG, una híbrida) que rellenan el campo al hacer clic |

## No incluye

Historial de conversación (RF-017, sin memoria entre preguntas), autenticación ni edición de datos.

## Pruebas

Verificación manual guiada en [quickstart.md](../quickstart.md) (CE-006): una pregunta de cada tipo y comprobación de que el origen es visible sin herramientas externas.
