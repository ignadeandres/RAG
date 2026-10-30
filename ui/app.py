"""ROBOOST HR assistant — minimal Streamlit chat with role-based login."""

from __future__ import annotations

import logging

import streamlit as st

from roboost_rag import container as di
from roboost_rag.config import ConfigError
from roboost_rag.services.query import UNAVAILABLE, ServiceUnavailableError

log = logging.getLogger("roboost_rag.ui")

ROLE_LABELS = {"public": "Empleado", "hr_manager": "HR Manager", "admin": "Administrador"}

st.set_page_config(page_title="ROBOOST · Asistente RRHH", page_icon="💬")


@st.cache_resource(show_spinner="Iniciando servicios…")
def get_container():
    return di.build()


@st.cache_resource(ttl=60, show_spinner=False)
def get_warnings() -> list[str]:
    return get_container().startup_warnings()


def logout() -> None:
    for key in ("user", "role", "history"):
        st.session_state.pop(key, None)


def login_view(container) -> None:
    st.title("Asistente de RRHH")
    with st.form("login"):
        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Entrar")
    if submitted:
        role = container.users.authenticate(username, password)
        if role is None:
            st.error("Usuario o contraseña incorrectos.")
        else:
            st.session_state.update(user=username, role=role, history=[])
            st.rerun()


def render_answer(text: str, sources: list) -> None:
    st.markdown(text)
    if sources:
        st.caption("Fuentes: " + " · ".join(f"{s.title} (`{s.path}`)" for s in sources))


def chat_view(container) -> None:
    role = st.session_state.role
    with st.sidebar:
        st.markdown(f"**{st.session_state.user}**")
        st.markdown(f"Rol: `{role.value}` · {ROLE_LABELS[role.value]}")
        st.button("Cerrar sesión", on_click=logout)
        for warning in get_warnings():
            st.warning(warning)

    st.title("Asistente de RRHH")
    for turn in st.session_state.history:
        with st.chat_message("user"):
            st.markdown(turn["question"])
        with st.chat_message("assistant"):
            render_answer(turn["answer"], turn["sources"])

    question = st.chat_input("Pregunta sobre vacaciones, beneficios, políticas…")
    if not question:
        return
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        try:
            with st.spinner("Buscando en la documentación…"):
                answer = container.query.ask(question, role)
        except ServiceUnavailableError as exc:
            st.error(str(exc))
            return
        except Exception:
            log.exception("Error inesperado respondiendo a una consulta")
            st.error(UNAVAILABLE)
            return
        render_answer(answer.text, answer.sources)
    st.session_state.history.append(
        {"question": question, "answer": answer.text, "sources": answer.sources}
    )


def main() -> None:
    try:
        container = get_container()
    except ConfigError as exc:
        st.error(f"Configuración incompleta: {exc}")
        st.stop()
    except Exception:
        log.exception("No se pudieron iniciar los servicios")
        st.error(UNAVAILABLE)
        st.stop()

    if "role" not in st.session_state:
        login_view(container)
    else:
        chat_view(container)


main()
