import streamlit as st
import traceback

def mostrar_sidebar():
    if "usuario" not in st.session_state:
        return

    usuario = st.session_state["usuario"]
    rol     = usuario["rol"]
    nombre  = f"{usuario['nombre']} {usuario['apellido']}".strip()

    # Key única basada en el stack — identifica qué página llama la función
    caller = traceback.extract_stack()[-2].filename
    logout_key = f"logout_{hash(caller) % 999999}"

    with st.sidebar:
        st.markdown(f"### {nombre}")
        st.caption(f"Rol: **{rol.capitalize()}**")
        st.markdown("---")

        if rol == "administrador":
            st.markdown("**Gestión**")
            st.page_link("app.py",                        label="Inicio")
            st.page_link("pages/5_admin.py",              label="Administración")
            st.page_link("pages/5b_contratos.py",         label="Contratos")
            st.markdown("**Operación**")
            st.page_link("pages/1_agenda.py",             label="Agenda")
            st.page_link("pages/2_mis_pacientes.py",      label="Pacientes")
            st.page_link("pages/3_ficha_paciente.py",     label="Ficha del Paciente")
            st.page_link("pages/3b_cargar_plan.py",       label="Cargar Plan")


        elif rol == "nutricionista":
            st.markdown("**Mi trabajo**")
            st.page_link("app.py",                        label="Inicio")
            st.page_link("pages/1_agenda.py",             label="Mi Agenda")
            st.page_link("pages/2_mis_pacientes.py",      label="Mis Pacientes")
            st.page_link("pages/3_ficha_paciente.py",     label="Ficha del Paciente")
            st.page_link("pages/3b_cargar_plan.py",       label="Cargar Plan")


        elif rol == "paciente":
            st.markdown("**Mi cuenta**")
            st.page_link("app.py",                        label="Inicio")
            st.page_link("pages/3_ficha_paciente.py",     label="Mi Ficha")
            st.page_link("pages/6_mi_progreso.py",        label="Mi Progreso")

        st.markdown("---")
        if st.button("Cerrar sesión", use_container_width=True, key=logout_key):
            st.session_state.clear()
            st.switch_page("app.py")