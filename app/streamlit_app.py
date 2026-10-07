"""Interfaz Streamlit del asistente del gimnasio (contrato `ui.md`).

Se ejecuta con `streamlit run app/streamlit_app.py` desde la raíz del repositorio. Llama a
`run_question` en el mismo proceso y muestra la respuesta junto con su origen. No guarda
historial: solo se ve la respuesta de la última pregunta enviada (RF-017).
"""

import streamlit as st

from gym_agent.graph import run_question
from gym_agent.presentacion import EJEMPLOS, documentos_citados, escapar_markdown, etiqueta_ruta

MENSAJE_GENERICO = "En este momento no puedo responder. Probá de nuevo en unos minutos."

st.set_page_config(page_title="Asistente del gimnasio")
st.title("Asistente del gimnasio")
st.write(
    "Preguntá sobre socios, pagos, clases, equipamiento y los documentos del gimnasio, "
    "en castellano o en inglés. Cada pregunta se procesa por separado: no recuerdo las anteriores."
)


def _usar_ejemplo(texto: str) -> None:
    """Rellena el campo de pregunta sin enviarla."""
    st.session_state["pregunta"] = texto


with st.form("formulario"):
    pregunta = st.text_input("Pregunta", key="pregunta")
    enviado = st.form_submit_button("Preguntar", key="preguntar")

st.caption("Ejemplos:")
for i, ejemplo in enumerate(EJEMPLOS):
    st.button(ejemplo, key=f"ejemplo_{i}", on_click=_usar_ejemplo, args=(ejemplo,))

if enviado:
    if not pregunta.strip():
        st.warning("Escribí una pregunta.")
    else:
        try:
            with st.spinner("Pensando..."):
                respuesta = run_question(pregunta)
        except Exception:
            # run_question no debería lanzar; si lo hace, nunca se muestra el detalle.
            st.error(MENSAJE_GENERICO)
        else:
            if respuesta.fallo:
                st.error(respuesta.respuesta)
            else:
                # Streamlit toma `$...$` como fórmula LaTeX; los importes del LLM deben salir literales.
                st.markdown(escapar_markdown(respuesta.respuesta))
            st.caption(f"Fuente: {etiqueta_ruta(respuesta)}")
            if respuesta.sql_ejecutado is not None:
                with st.expander("Consulta SQL ejecutada"):
                    st.code(respuesta.sql_ejecutado, language="sql")
            citados = documentos_citados(respuesta)
            if citados:
                with st.expander("Documentos citados"):
                    st.markdown("\n".join(f"- {escapar_markdown(c)}" for c in citados))
            st.caption(f"Respondido en {respuesta.duracion_ms / 1000:.1f} s")
