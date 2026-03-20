import streamlit as st
from database import run_query, run_command, hashear_password, email_existe
from datetime import date
from utils import mostrar_sidebar

st.set_page_config(page_title="Registro", page_icon="🥗", layout="centered")

if "usuario" in st.session_state:
    st.switch_page("app.py")

mostrar_sidebar()

st.markdown("## Crear tu cuenta")
st.page_link("pages/login.py", label="Ya tengo cuenta, iniciar sesion")
st.markdown("---")

tab_pac, tab_nutri = st.tabs(["Soy paciente", "Soy nutricionista"])

# ═══════════════════════════════════════
# REGISTRO PACIENTE
# ═══════════════════════════════════════
with tab_pac:
    st.markdown("**Paso 1 de 2 — Crea tu acceso**")
    st.caption("Completa tus datos de acceso. Luego vas a completar tu perfil dentro de la app.")

    # Programa preseleccionado (si vino desde la landing)
    prog_pre = st.session_state.get("programa_preseleccionado")
    programas = run_query("SELECT id_programa, nombre, precio_base FROM programas WHERE activo=TRUE ORDER BY precio_base")

    if prog_pre:
        st.success(f"Programa seleccionado: **{prog_pre['nombre']}** — S/ {float(prog_pre['precio_base']):,.0f}")
        id_prog_elegido = prog_pre["id_programa"]
        if st.button("Cambiar programa", key="cambiar_prog"):
            st.session_state.pop("programa_preseleccionado", None)
            st.rerun()
    else:
        if programas:
            prog_opts = {f"{p['nombre']} — S/ {float(p['precio_base']):,.0f}": p for p in programas}
            prog_sel  = st.selectbox("Selecciona el programa que compraste *", list(prog_opts.keys()))
            id_prog_elegido = prog_opts[prog_sel]["id_programa"]
        else:
            st.warning("No hay programas disponibles.")
            st.stop()

    st.markdown("---")
    with st.form("form_registro_paciente"):
        st.markdown("**Datos de acceso**")
        col1, col2 = st.columns(2)
        with col1:
            email    = st.text_input("Email *", placeholder="tu@email.com")
            pass1    = st.text_input("Contraseña *", type="password")
            pass2    = st.text_input("Repetir contraseña *", type="password")
        with col2:
            nombre   = st.text_input("Nombre *")
            apellido = st.text_input("Apellido *")

        st.markdown("---")
        st.markdown("**Datos personales**")
        col3, col4 = st.columns(2)
        with col3:
            telefono  = st.text_input("Teléfono", placeholder="+51 999 999 999")
            fecha_nac = st.date_input("Fecha de nacimiento *",
                                       min_value=date(1940,1,1),
                                       max_value=date.today(),
                                       value=date(1990,1,1))
        with col4:
            genero    = st.selectbox("Género",
                                      ["femenino","masculino","otro","prefiero_no_decir"])
            ocupacion = st.text_input("Ocupación", placeholder="Ej: docente, ingeniera...")

        st.caption("Al registrarte aceptas nuestros términos y condiciones.")
        registrar = st.form_submit_button("Crear cuenta y continuar", use_container_width=True)

    if registrar:
        errores = []
        if not email:              errores.append("Email requerido.")
        if not nombre:             errores.append("Nombre requerido.")
        if not apellido:           errores.append("Apellido requerido.")
        if not pass1:              errores.append("Contrasena requerida.")
        if pass1 != pass2:         errores.append("Las contrasenas no coinciden.")
        if len(pass1) < 6:         errores.append("Minimo 6 caracteres.")
        if email and email_existe(email): errores.append("Ese email ya esta registrado.")

        if errores:
            for e in errores: st.error(e)
        else:
            try:
                ph = hashear_password(pass1)
                run_command("""
                    INSERT INTO usuarios (email, password_hash, rol, estado, estado_aprobacion)
                    VALUES (%s, %s, 'paciente', TRUE, 'aprobado')
                """, (email, ph))

                id_usuario = run_query("SELECT id_usuario FROM usuarios WHERE email=%s", (email,))[0]["id_usuario"]

                run_command("""
                    INSERT INTO pacientes (id_usuario, nombre, apellido, email,
                        telefono, fecha_nacimiento, genero,
                        estado, onboarding_paso)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'activo', 1)
                """, (id_usuario, nombre, apellido, email,
                      telefono, fecha_nac, genero))

                id_paciente = run_query("SELECT id_paciente FROM pacientes WHERE id_usuario=%s", (id_usuario,))[0]["id_paciente"]

                # Crear contrato en pendiente_pago vinculado al programa elegido
                prog_data = run_query("SELECT * FROM programas WHERE id_programa=%s", (id_prog_elegido,))[0]
                from datetime import timedelta
                f_inicio = date.today()
                f_fin    = f_inicio + timedelta(days=int(prog_data["duracion_dias"]))

                run_command("""
                    INSERT INTO contratos
                        (id_paciente, id_programa, id_nutricionista,
                         fecha_inicio, fecha_fin,
                         precio_base_contrato, descuento_contrato, precio_final,
                         estado, reprogramaciones_usadas)
                    SELECT %s, %s,
                           (SELECT id_nutricionista FROM nutricionistas WHERE estado=TRUE LIMIT 1),
                           %s, %s, %s, 0, %s, 'activo', 0
                """, (id_paciente, id_prog_elegido, f_inicio, f_fin,
                      prog_data["precio_base"], prog_data["precio_base"]))

                # Iniciar sesion automaticamente
                # Obtener id del contrato recién creado
                id_contrato = run_query(
                    "SELECT id_contrato FROM contratos WHERE id_paciente=%s ORDER BY fecha_creacion DESC LIMIT 1",
                    (id_paciente,)
                )[0]["id_contrato"]

                # Generar sesiones automáticamente
                import datetime as dt
                frec_map = {"semanal":7,"quincenal":14,"mensual":30}
                dias_frec = frec_map.get(prog_data.get("frecuencia","quincenal"), 14)
                for i in range(int(prog_data["cantidad_sesiones"])):
                    fecha_s = f_inicio + dt.timedelta(days=i * dias_frec)
                    # Fecha placeholder lejana — el paciente elige el turno real en onboarding paso 3
                    placeholder = dt.datetime(2099, 1, 1, 9, 0)
                    run_command("""
                        INSERT INTO sesiones
                            (id_contrato, id_nutricionista_prog, numero_sesion,
                             fecha_hora_original, fecha_hora_programada,
                             modalidad, estado, estado_confirmacion, contador_reprogramaciones)
                        SELECT %s,
                               (SELECT id_nutricionista FROM nutricionistas WHERE estado=TRUE LIMIT 1),
                               %s, %s, %s, %s, 'programada', 'pendiente', 0
                    """, (id_contrato, i+1, placeholder, placeholder, 'presencial'))

                st.session_state["usuario"] = {
                    "id_usuario":       id_usuario,
                    "email":            email,
                    "rol":              "paciente",
                    "id_nutricionista": None,
                    "nombre":           nombre,
                    "apellido":         apellido,
                    "id_paciente":      id_paciente,
                }
                st.session_state.pop("programa_preseleccionado", None)
                st.switch_page("pages/onboarding.py")

            except Exception as e:
                st.error(f"Error al crear cuenta: {e}")

# ═══════════════════════════════════════
# REGISTRO NUTRICIONISTA
# ═══════════════════════════════════════
with tab_nutri:
    st.caption("Tu cuenta quedara pendiente de aprobacion por el administrador.")

    with st.form("form_registro_nutri"):
        col1, col2 = st.columns(2)
        with col1:
            n_email    = st.text_input("Email *", key="n_email")
            n_pass1    = st.text_input("Contrasena *", type="password", key="n_pass1")
            n_pass2    = st.text_input("Repetir contrasena *", type="password", key="n_pass2")
            n_nombre   = st.text_input("Nombre *", key="n_nombre")
        with col2:
            n_apellido = st.text_input("Apellido *", key="n_apellido")
            n_cmp      = st.text_input("CMP (matricula)", key="n_cmp")
            n_espec    = st.text_input("Especialidad", key="n_espec")
            n_celular  = st.text_input("Celular", key="n_celular")

        registrar_n = st.form_submit_button("Enviar solicitud", use_container_width=True)

    if registrar_n:
        errores = []
        if not n_email:             errores.append("Email requerido.")
        if not n_nombre:            errores.append("Nombre requerido.")
        if not n_apellido:          errores.append("Apellido requerido.")
        if not n_pass1:             errores.append("Contrasena requerida.")
        if n_pass1 != n_pass2:      errores.append("Las contrasenas no coinciden.")
        if len(n_pass1) < 6:        errores.append("Minimo 6 caracteres.")
        if n_email and email_existe(n_email): errores.append("Ese email ya esta registrado.")

        if errores:
            for e in errores: st.error(e)
        else:
            try:
                ph = hashear_password(n_pass1)
                run_command("""
                    INSERT INTO usuarios (email, password_hash, rol, estado, estado_aprobacion)
                    VALUES (%s, %s, 'nutricionista', FALSE, 'pendiente')
                """, (n_email, ph))
                id_u = run_query("SELECT id_usuario FROM usuarios WHERE email=%s", (n_email,))[0]["id_usuario"]
                run_command("""
                    INSERT INTO nutricionistas
                        (id_usuario, nombre, apellido, cmp, especialidad, celular)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (id_u, n_nombre, n_apellido, n_cmp, n_espec, n_celular))
                st.success("Solicitud enviada. El administrador revisara tu cuenta y te avisara.")
            except Exception as e:
                st.error(f"Error: {e}")