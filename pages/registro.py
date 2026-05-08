import streamlit as st
from database import run_query, run_command, hashear_password, email_existe
from datetime import date
from utils import mostrar_sidebar

st.set_page_config(page_title="Registro", page_icon="🥗", layout="centered")

if "usuario" in st.session_state:
    st.switch_page("app.py")

mostrar_sidebar()


def _get_tipo_registro():
    """
    Lee el tipo de registro desde la URL:
    /registro?tipo=persona
    /registro?tipo=empresa
    /registro?tipo=nutricionista
    """
    try:
        tipo = st.query_params.get("tipo", None)
    except Exception:
        tipo = None

    if isinstance(tipo, list):
        tipo = tipo[0] if tipo else None

    tipo = (tipo or "").strip().lower()

    if tipo in ("persona", "paciente", "individual"):
        return "persona"
    if tipo in ("empresa", "corporativo", "colaborador"):
        return "empresa"
    if tipo in ("nutricionista", "nutri"):
        return "nutricionista"

    return None


def _set_tipo_registro(tipo):
    try:
        st.query_params["tipo"] = tipo
    except Exception:
        pass
    st.rerun()


tipo_registro = _get_tipo_registro()

st.markdown("## Crear tu cuenta")
st.page_link("pages/login.py", label="Ya tengo cuenta, iniciar sesión")
st.markdown("---")



# PANTALLA INICIAL — SELECCIÓN DE TIPO

if tipo_registro is None:
    st.caption("Seleccioná el tipo de acceso para continuar con el registro correspondiente.")

    col1, col2 = st.columns(2)

    with col1:
        with st.container(border=True):
            st.markdown("### Paciente individual")
            st.caption("Para pacientes que ingresan como persona particular.")
            if st.button("Registrarme como paciente individual", use_container_width=True, type="primary"):
                _set_tipo_registro("persona")

    with col2:
        with st.container(border=True):
            st.markdown("### Paciente empresa")
            st.caption("Para colaboradores o pacientes derivados por una empresa.")
            if st.button("Registrarme como paciente empresa", use_container_width=True):
                _set_tipo_registro("empresa")

    st.markdown("---")

    with st.container(border=True):
        st.markdown("### Soy nutricionista")
        st.caption("Solicitud de acceso para profesionales. Quedará pendiente de aprobación.")
        if st.button("Solicitar acceso como nutricionista", use_container_width=True):
            _set_tipo_registro("nutricionista")

    st.stop()



# REGISTRO PACIENTE PERSONA / EMPRESA

if tipo_registro in ("persona", "empresa"):
    es_empresa = tipo_registro == "empresa"

    if es_empresa:
        st.markdown("### Registro paciente empresa")
        st.caption("Creá tu acceso. Luego vas a completar el formulario correspondiente para pacientes empresa.")
    else:
        st.markdown("### Registro paciente individual")
        st.caption("Creá tu acceso. Luego vas a completar tu historia nutricional.")

    if st.button("← Cambiar tipo de registro", key="cambiar_tipo_registro"):
        try:
            st.query_params.clear()
        except Exception:
            pass
        st.rerun()

    st.markdown("---")

    with st.form(f"form_registro_acceso_{tipo_registro}"):
        st.markdown("**Datos de acceso**")
        st.caption("Estos datos son solo para crear tu usuario. Los datos personales se completan en el formulario siguiente.")

        email = st.text_input("Email *", placeholder="tu@email.com")

        col1, col2 = st.columns(2)
        with col1:
            pass1 = st.text_input("Contraseña *", type="password")
        with col2:
            pass2 = st.text_input("Repetir contraseña *", type="password")

        if es_empresa:
            st.info("Te estás registrando como paciente empresa. El formulario siguiente cargará el onboarding correspondiente.")
        else:
            st.info("Te estás registrando como paciente individual. El formulario siguiente cargará tu historia nutricional.")

        registrar = st.form_submit_button("Crear acceso y continuar", use_container_width=True)

    if registrar:
        errores = []

        if not email:
            errores.append("Email requerido.")
        if not pass1:
            errores.append("Contraseña requerida.")
        if pass1 != pass2:
            errores.append("Las contraseñas no coinciden.")
        if pass1 and len(pass1) < 6:
            errores.append("Mínimo 6 caracteres.")
        if email and email_existe(email):
            errores.append("Ese email ya está registrado.")

        if errores:
            for e in errores:
                st.error(e)
        else:
            try:
                ph = hashear_password(pass1)
                email_clean = email.strip()

                run_command("""
                    INSERT INTO usuarios (email, password_hash, rol, estado, estado_aprobacion)
                    VALUES (%s, %s, 'paciente', TRUE, 'aprobado')
                """, (email_clean, ph))

                id_usuario = run_query(
                    "SELECT id_usuario FROM usuarios WHERE email=%s",
                    (email_clean,),
                )[0]["id_usuario"]

                # Paciente mínimo.
                # La tabla pacientes exige nombre/apellido NOT NULL.
                # El onboarding los reemplaza con los datos reales.
                run_command("""
                    INSERT INTO pacientes
                        (id_usuario, nombre, apellido, email, estado, onboarding_paso, tipo_paciente)
                    VALUES (%s, %s, %s, %s, 'activo', 1, %s)
                """, (
                    id_usuario,
                    "Pendiente",
                    "Completar",
                    email_clean,
                    "empresa" if es_empresa else "persona",
                ))

                id_paciente = run_query(
                    "SELECT id_paciente FROM pacientes WHERE id_usuario=%s",
                    (id_usuario,),
                )[0]["id_paciente"]

                st.session_state["usuario"] = {
                    "id_usuario": id_usuario,
                    "email": email_clean,
                    "rol": "paciente",
                    "id_nutricionista": None,
                    "nombre": "",
                    "apellido": "",
                    "id_paciente": id_paciente,
                }

                st.session_state.pop("programa_preseleccionado", None)
                st.switch_page("pages/onboarding_form.py")

            except Exception as e:
                st.error(f"Error al crear cuenta: {e}")



# REGISTRO NUTRICIONISTA

elif tipo_registro == "nutricionista":
    st.markdown("### Registro nutricionista")
    st.caption("Tu cuenta quedará pendiente de aprobación por el administrador.")

    if st.button("← Cambiar tipo de registro", key="cambiar_tipo_registro_nutri"):
        try:
            st.query_params.clear()
        except Exception:
            pass
        st.rerun()

    st.markdown("---")

    with st.form("form_registro_nutri"):
        col1, col2 = st.columns(2)

        with col1:
            n_email = st.text_input("Email *", key="n_email")
            n_pass1 = st.text_input("Contraseña *", type="password", key="n_pass1")
            n_pass2 = st.text_input("Repetir contraseña *", type="password", key="n_pass2")
            n_nombre = st.text_input("Nombre *", key="n_nombre")

        with col2:
            n_apellido = st.text_input("Apellido *", key="n_apellido")
            n_cmp = st.text_input("CMP (matrícula)", key="n_cmp")
            n_espec = st.text_input("Especialidad", key="n_espec")
            n_celular = st.text_input("Celular", key="n_celular")

        registrar_n = st.form_submit_button("Enviar solicitud", use_container_width=True)

    if registrar_n:
        errores = []

        if not n_email:
            errores.append("Email requerido.")
        if not n_nombre:
            errores.append("Nombre requerido.")
        if not n_apellido:
            errores.append("Apellido requerido.")
        if not n_pass1:
            errores.append("Contraseña requerida.")
        if n_pass1 != n_pass2:
            errores.append("Las contraseñas no coinciden.")
        if n_pass1 and len(n_pass1) < 6:
            errores.append("Mínimo 6 caracteres.")
        if n_email and email_existe(n_email):
            errores.append("Ese email ya está registrado.")

        if errores:
            for e in errores:
                st.error(e)
        else:
            try:
                ph = hashear_password(n_pass1)

                run_command("""
                    INSERT INTO usuarios (email, password_hash, rol, estado, estado_aprobacion)
                    VALUES (%s, %s, 'nutricionista', FALSE, 'pendiente')
                """, (n_email.strip(), ph))

                id_u = run_query(
                    "SELECT id_usuario FROM usuarios WHERE email=%s",
                    (n_email.strip(),),
                )[0]["id_usuario"]

                run_command("""
                    INSERT INTO nutricionistas
                        (id_usuario, nombre, apellido, cmp, especialidad, celular)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    id_u,
                    n_nombre.strip(),
                    n_apellido.strip(),
                    n_cmp or None,
                    n_espec or None,
                    n_celular or None,
                ))

                st.success("Solicitud enviada. El administrador revisará tu cuenta y te avisará.")

            except Exception as e:
                st.error(f"Error: {e}")
