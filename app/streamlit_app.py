"""Entrada de la interfaz Streamlit del asistente del gimnasio (contrato `ui.md`).

Se ejecuta con `streamlit run app/streamlit_app.py` desde la raíz del repositorio. Arma la
navegación de la barra lateral (Chat y Preguntas evaluativas) y el link a Phoenix; el contenido
de cada página está en `app/paginas/`.
"""

from pathlib import Path

import streamlit as st

from gym_agent.presentacion import url_phoenix

st.set_page_config(page_title="Gym AI Agent", page_icon="🏋️")

st.logo(str(Path(__file__).parent / "logo.svg"), size="large")

pagina = st.navigation(
    [
        st.Page("paginas/chat.py", title="Chat", icon="💬", default=True),
        st.Page("paginas/preguntas.py", title="Preguntas evaluativas", icon="📋"),
    ]
)

st.sidebar.link_button("Observabilidad en Phoenix", url_phoenix(), icon="🔭")
st.sidebar.caption("Requiere `docker compose --profile observability up -d`.")

pagina.run()
