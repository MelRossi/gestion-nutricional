# -*- coding: utf-8 -*-
import os
import traceback
import streamlit as st

# ============================================================
# CARGA DE ESTILOS
# ============================================================

def cargar_estilos():
    """
    Carga el archivo styles.CCS ubicado en la raíz del proyecto.
    Única fuente de estilos globales para evitar competencia de CSS.
    """
    ruta_css = os.path.join(os.path.dirname(__file__), "styles.CCS")
    if os.path.exists(ruta_css):
        with open(ruta_css, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


# ============================================================
# SIDEBAR UNIFICADO
# ============================================================

def mostrar_sidebar():
    """Sidebar única para todas las páginas logueadas."""
    if "usuario" not in st.session_state:
        return

    cargar_estilos()

    usuario = st.session_state["usuario"]
    rol = usuario["rol"]
    nombre = f"{usuario['nombre']} {usuario['apellido']}".strip()

    caller = traceback.extract_stack()[-2].filename
    logout_key = f"logout_{abs(hash(caller)) % 99999}"

    rol_display = {
        "administrador": "ADMINISTRADOR",
        "nutricionista": "NUTRICIONISTA",
        "paciente": "PACIENTE",
    }.get(rol, rol.upper())

    with st.sidebar:
        st.markdown(
            f"""
            <div class="sb-user">
              <div class="sb-user-avatar">{nombre[0].upper() if nombre else 'U'}</div>
              <div class="sb-user-name">{nombre}</div>
              <div class="sb-user-role">{rol_display}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if rol == "administrador":
            _nav_label("GESTIÓN")
            st.page_link("app.py", label="Inicio")
            st.page_link("pages/5_admin.py", label="Administración")
            st.page_link("pages/5b_contratos.py", label="Contratos")

            _nav_label("OPERACIÓN")
            st.page_link("pages/1_agenda.py", label="Agenda")
            st.page_link("pages/2_mis_pacientes.py", label="Pacientes")
            st.page_link("pages/3_ficha_paciente.py", label="Ficha del paciente")
            st.page_link("pages/3b_cargar_plan.py", label="Cargar plan")
            st.page_link("pages/4_pagos.py", label="Pagos")

        elif rol == "nutricionista":
            _nav_label("MI TRABAJO")
            st.page_link("app.py", label="Inicio")
            st.page_link("pages/1_agenda.py", label="Agenda")
            st.page_link("pages/2_mis_pacientes.py", label="Pacientes")
            st.page_link("pages/3_ficha_paciente.py", label="Ficha del paciente")
            st.page_link("pages/3b_cargar_plan.py", label="Cargar plan")

        elif rol == "paciente":
            _nav_label("MI CUENTA")
            st.page_link("app.py", label="Inicio")
            st.page_link("pages/3_ficha_paciente.py", label="Mi ficha")
            st.page_link("pages/6_mi_progreso.py", label="Mi progreso")

        st.markdown('<div class="sb-divider"></div>', unsafe_allow_html=True)

        if st.button("Cerrar sesión", use_container_width=True, key=logout_key):
            st.session_state.clear()
            st.switch_page("app.py")


def _nav_label(texto: str):
    st.markdown(
        f"""
        <div class="sb-nav-label">{texto}</div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# HELPERS UI
# ============================================================

def page_header(titulo: str, subtitulo: str = ""):
    cargar_estilos()
    subtitulo_html = f'<p class="page-subtitle">{subtitulo}</p>' if subtitulo else ""
    st.markdown(
        f"""
        <div class="page-header">
          <h1>{titulo}</h1>
          {subtitulo_html}
          <div class="page-header-line"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_label(texto: str):
    st.markdown(
        f"""
        <div class="section-label">{texto}</div>
        """,
        unsafe_allow_html=True,
    )


def info_banner(mensaje: str, tipo: str = "info"):
    """
    warning -> amarillo prioritario
    info    -> lila suave informativo
    success -> verde
    error   -> rojo suave
    """
    cfg = {
        "info": {
            "border": "#8C52FF",
            "bg": "#F3ECFF",
            "fg": "#6F3FD6",
        },
        "success": {
            "border": "#00DC8E",
            "bg": "rgba(0,220,142,.10)",
            "fg": "#006845",
        },
        "warning": {
            "border": "#FFCC33",
            "bg": "rgba(255,204,51,.18)",
            "fg": "#7A5C00",
        },
        "error": {
            "border": "#EF4444",
            "bg": "rgba(239,68,68,.10)",
            "fg": "#991B1B",
        },
    }

    style = cfg.get(tipo, cfg["info"])

    st.markdown(
        f"""
        <div style="
            background:{style['bg']};
            border-left:4px solid {style['border']};
            border-radius:0 10px 10px 0;
            padding:12px 16px;
            margin:8px 0 14px 0;
            font-family:'DM Sans', sans-serif;
            font-size:.92rem;
            line-height:1.45;
            color:{style['fg']};
            box-shadow:0 1px 3px rgba(0,0,0,.04);
        ">
          {mensaje}
        </div>
        """,
        unsafe_allow_html=True,
    )


def divider():
    st.markdown(
        """
        <div class="divider-soft"></div>
        """,
        unsafe_allow_html=True,
    )