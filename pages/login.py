import streamlit as st
from database import get_connection, verificar_password, run_query

st.set_page_config(
    page_title="Iniciar sesión",
    page_icon="",
    layout="centered"
)

# Si ya está logueado, redirigir
if "usuario" in st.session_state:
    st.switch_page("app.py")

def verificar_login(email, password):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT u.id_usuario, u.email, u.rol, u.estado_aprobacion,
               n.id_nutricionista, n.nombre, n.apellido,
               p.id_paciente, p.nombre AS p_nombre, p.apellido AS p_apellido
        FROM usuarios u
        LEFT JOIN nutricionistas n ON u.id_usuario = n.id_usuario
        LEFT JOIN pacientes p      ON u.id_usuario = p.id_usuario
        WHERE u.email = %s AND u.estado = TRUE
    """, (email,))
    usuario = cur.fetchone()
    conn.close()

    if not usuario:
        return None, "Email o contraseña incorrectos."
    if usuario[3] == "pendiente":
        return None, "Tu cuenta está pendiente de aprobación."
    if usuario[3] == "rechazado":
        return None, "Tu cuenta fue rechazada. Contactá al administrador."

    row = run_query("SELECT password_hash FROM usuarios WHERE email = %s", (email,))
    if not row or not verificar_password(password, row[0]["password_hash"]):
        return None, "Email o contraseña incorrectos."

    return {
        "id_usuario":       usuario[0],
        "email":            usuario[1],
        "rol":              usuario[2],
        "id_nutricionista": usuario[4],
        "nombre":           usuario[5] or usuario[8] or "",
        "apellido":         usuario[6] or usuario[9] or "",
        "id_paciente":      usuario[7],
    }, None

# ─────────────────────────────────────────
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.page_link("app.py", label="← Volver al inicio")
    st.markdown("## Iniciar sesión")
    st.markdown("---")

    tab_login, tab_reset = st.tabs(["Iniciar sesión", "Olvidé mi contraseña"])

    with tab_login:
        email    = st.text_input("Email", placeholder="tu@email.com")
        password = st.text_input("Contraseña", type="password")

        if st.button("Ingresar", use_container_width=True, type="primary"):
            if not email or not password:
                st.error("Completá email y contraseña.")
            else:
                usuario, error = verificar_login(email, password)
                if usuario:
                    st.session_state["usuario"] = usuario
                    st.switch_page("app.py")
                else:
                    st.error(error)

        st.markdown("---")
        st.page_link("pages/registro.py", label="¿No tenés cuenta? Registrate aquí")

    with tab_reset:
        st.markdown("Ingresá tu email y te enviaremos un link para restablecer tu contraseña.")
        email_reset = st.text_input("Email", placeholder="tu@email.com", key="reset_email")

        if st.button("Enviar link", use_container_width=True):
            import os
            if not os.environ.get("SENDGRID_API_KEY"):
                st.warning("""
                El envío de emails aún no está configurado.

                **Para recuperar tu contraseña:**
                Contactá al administrador indicando tu email.
                """)
            else:
                st.success("Si tu email está registrado, recibirás un link en minutos.")