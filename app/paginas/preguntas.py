"""Página "Preguntas evaluativas": la batería con la que se evalúa el agente.

Muestra, sección por sección y como en `eval-battery.md`, cada pregunta con su tipo de chequeo.
Solo lista: no envía nada al agente.
"""

import streamlit as st

from gym_agent.presentacion import secciones_bateria, tabla_markdown

st.title("Preguntas evaluativas")
st.write("Estas son las preguntas con las que se evalúa al agente y lo que se verifica en cada una.")

for seccion in secciones_bateria():
    st.subheader(seccion.titulo)
    st.markdown(tabla_markdown(seccion.preguntas))
