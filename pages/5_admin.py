import streamlit as st
from utils import mostrar_sidebar
import pandas as pd
from database import run_query, run_command, hashear_password, email_existe

if "usuario" not in st.session_state:
    st.warning("Debés iniciar sesión para acceder a esta página.")
    st.stop()

if st.session_state["usuario"]["rol"] != "administrador":
    st.error("No tenés permisos para acceder a esta sección.")
    st.stop()

mostrar_sidebar()

st.title("Administración")
st.markdown("---")

pendientes = run_query("""
    SELECT COUNT(*) AS n FROM usuarios
    WHERE rol = 'nutricionista' AND estado_aprobacion = 'pendiente'
""")
if pendientes[0]["n"] > 0:
    st.warning(f"⚠️ Hay **{pendientes[0]['n']}** nutricionista(s) pendiente(s) de aprobación.")

tab1, tab2, tab3, tab4 = st.tabs(["Aprobaciones", "Usuarios", "Programas", "Resumen BD"])

# ═══════════════════════════════════════
# TAB 1 — APROBACIONES
# ═══════════════════════════════════════
with tab1:
    st.subheader("Solicitudes de registro — Nutricionistas")

    pendientes_lista = run_query("""
        SELECT u.id_usuario, u.email, u.fecha_creacion, u.estado_aprobacion,
               n.nombre, n.apellido, n.especialidad, n.cmp, n.celular
        FROM usuarios u
        JOIN nutricionistas n ON u.id_usuario = n.id_usuario
        WHERE u.rol = 'nutricionista'
        AND u.estado_aprobacion IN ('pendiente', 'rechazado')
        ORDER BY u.fecha_creacion DESC
    """)

    if not pendientes_lista:
        st.success("No hay solicitudes pendientes.")
    else:
        for p in pendientes_lista:
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.markdown(f"**{p['nombre']} {p['apellido']}**")
                    st.caption(f"{p['email']} · CMP: {p['cmp'] or '—'} · {p['especialidad'] or '—'}")
                    st.caption(f"Solicitó: {str(p['fecha_creacion'])[:16]}")
                with col2:
                    if st.button("Aprobar", key=f"apr_{p['id_usuario']}", use_container_width=True):
                        run_command("""
                            UPDATE usuarios SET estado_aprobacion = 'aprobado', estado = TRUE
                            WHERE id_usuario = %s
                        """, (p["id_usuario"],))
                        st.success(f"{p['nombre']} aprobado.")
                        st.rerun()
                with col3:
                    if st.button("Rechazar", key=f"rec_{p['id_usuario']}", use_container_width=True):
                        run_command("""
                            UPDATE usuarios SET estado_aprobacion = 'rechazado', estado = FALSE
                            WHERE id_usuario = %s
                        """, (p["id_usuario"],))
                        st.warning(f"Solicitud de {p['nombre']} rechazada.")
                        st.rerun()

    st.markdown("---")
    st.subheader("Todos los nutricionistas")
    todos = run_query("""
        SELECT n.nombre || ' ' || n.apellido AS nombre, u.email,
               u.estado_aprobacion, u.estado, n.especialidad, n.cmp, n.fecha_ingreso
        FROM nutricionistas n
        JOIN usuarios u ON n.id_usuario = u.id_usuario
        ORDER BY u.estado_aprobacion, n.apellido
    """)
    if todos:
        df_t = pd.DataFrame(todos)
        df_t["estado"] = df_t["estado"].map({True: "Activo", False: "Inactivo"})
        st.dataframe(df_t, use_container_width=True)


# ═══════════════════════════════════════
# TAB 2 — USUARIOS
# ═══════════════════════════════════════
with tab2:
    st.subheader("Usuarios del sistema")

    usuarios = run_query("""
        SELECT u.id_usuario, u.email, u.rol, u.estado, u.estado_aprobacion,
               u.fecha_creacion,
               COALESCE(n.nombre || ' ' || n.apellido,
                        p.nombre || ' ' || p.apellido, '—') AS nombre_completo
        FROM usuarios u
        LEFT JOIN nutricionistas n ON u.id_usuario = n.id_usuario
        LEFT JOIN pacientes p ON u.id_usuario = p.id_usuario
        ORDER BY u.rol, u.email
    """)

    if usuarios:
        df = pd.DataFrame(usuarios)
        df["estado"] = df["estado"].map({True: "Activo", False: "Inactivo"})
        df = df.rename(columns={
            "id_usuario": "ID", "nombre_completo": "Nombre",
            "email": "Email", "rol": "Rol", "estado": "Estado",
            "estado_aprobacion": "Aprobacion", "fecha_creacion": "Creado"
        })
        st.dataframe(df[["ID", "Nombre", "Email", "Rol", "Estado", "Aprobacion", "Creado"]],
                     use_container_width=True)

    st.markdown("---")
    with st.expander("Crear nuevo usuario"):
        col1, col2 = st.columns(2)
        with col1:
            nuevo_email = st.text_input("Email *", key="nuevo_email")
            nuevo_rol   = st.selectbox("Rol *", ["nutricionista", "paciente", "administrador"], key="nuevo_rol")
        with col2:
            nueva_pass  = st.text_input("Contrasena *", type="password", key="nueva_pass")
            nueva_pass2 = st.text_input("Repetir contrasena *", type="password", key="nueva_pass2")

        if nuevo_rol == "nutricionista":
            st.markdown("**Datos del nutricionista**")
            col3, col4 = st.columns(2)
            with col3:
                n_nombre       = st.text_input("Nombre *", key="n_nombre")
                n_especialidad = st.text_input("Especialidad", key="n_especialidad")
                n_cmp          = st.text_input("CMP", key="n_cmp")
            with col4:
                n_apellido      = st.text_input("Apellido *", key="n_apellido")
                n_celular       = st.text_input("Celular", key="n_celular")
                n_tipo_contrato = st.selectbox("Tipo contrato",
                                    ["planilla", "recibo_honorarios", "outsourcing"], key="n_tipo")
        elif nuevo_rol == "paciente":
            st.markdown("**Datos del paciente**")
            col3, col4 = st.columns(2)
            with col3:
                p_nombre   = st.text_input("Nombre *", key="p_nombre")
                p_telefono = st.text_input("Telefono", key="p_telefono")
                p_genero   = st.selectbox("Genero",
                                ["femenino", "masculino", "otro", "prefiero_no_decir"], key="p_genero")
            with col4:
                p_apellido = st.text_input("Apellido *", key="p_apellido")
                p_fnac     = st.date_input("Fecha de nacimiento", key="p_fnac")

        if st.button("Crear usuario", key="btn_crear_usuario"):
            errores = []
            if not nuevo_email:           errores.append("Email requerido.")
            if not nueva_pass:            errores.append("Contrasena requerida.")
            if nueva_pass != nueva_pass2: errores.append("Las contrasenas no coinciden.")
            if len(nueva_pass) < 6:       errores.append("Minimo 6 caracteres.")
            if nuevo_email and email_existe(nuevo_email):
                errores.append(f"El email {nuevo_email} ya esta registrado.")
            if nuevo_rol == "nutricionista" and (not n_nombre or not n_apellido):
                errores.append("Nombre y apellido del nutricionista requeridos.")
            elif nuevo_rol == "paciente" and (not p_nombre or not p_apellido):
                errores.append("Nombre y apellido del paciente requeridos.")

            if errores:
                for e in errores: st.error(e)
            else:
                try:
                    ph = hashear_password(nueva_pass)
                    run_command("""
                        INSERT INTO usuarios (email, password_hash, rol, estado, estado_aprobacion)
                        VALUES (%s, %s, %s, TRUE, 'aprobado')
                    """, (nuevo_email, ph, nuevo_rol))
                    id_u = run_query("SELECT id_usuario FROM usuarios WHERE email = %s",
                                     (nuevo_email,))[0]["id_usuario"]
                    if nuevo_rol == "nutricionista":
                        run_command("""
                            INSERT INTO nutricionistas
                                (id_usuario, nombre, apellido, especialidad, cmp, celular, tipo_contrato)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (id_u, n_nombre, n_apellido, n_especialidad, n_cmp, n_celular, n_tipo_contrato))
                    elif nuevo_rol == "paciente":
                        run_command("""
                            INSERT INTO pacientes
                                (id_usuario, nombre, apellido, telefono, genero, fecha_nacimiento)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (id_u, p_nombre, p_apellido, p_telefono, p_genero, p_fnac))
                    st.success(f"Usuario {nuevo_email} creado.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

    with st.expander("Activar / Desactivar usuario"):
        if usuarios:
            emails = [u["email"] for u in usuarios]
            email_sel   = st.selectbox("Selecciona un usuario", emails, key="email_toggle")
            usuario_sel = next((u for u in usuarios if u["email"] == email_sel), None)
            if usuario_sel:
                estado_actual = "Activo" if usuario_sel.get("estado") == "Activo" else "Inactivo"
                st.write(f"Estado actual: **{estado_actual}**")
                accion = "Desactivar" if estado_actual == "Activo" else "Activar"
                if st.button(f"{accion} usuario", key="btn_toggle"):
                    run_command("UPDATE usuarios SET estado = %s WHERE email = %s",
                                (estado_actual != "Activo", email_sel))
                    st.success(f"Usuario {accion.lower()}do.")
                    st.rerun()


# ═══════════════════════════════════════
# TAB 3 — PROGRAMAS
# ═══════════════════════════════════════
with tab3:
    st.subheader("Programas nutricionales")

    programas = run_query("""
        SELECT id_programa, nombre, modalidad, cantidad_sesiones,
               duracion_dias, frecuencia, reprogramaciones_max, precio_base, activo
        FROM programas ORDER BY activo DESC, nombre
    """)

    if programas:
        df_p = pd.DataFrame(programas)
        df_p["activo"]      = df_p["activo"].map({True: "Si", False: "No"})
        df_p["precio_base"] = df_p["precio_base"].apply(lambda x: f"S/ {float(x):,.2f}")
        st.dataframe(df_p.rename(columns={
            "id_programa": "ID", "nombre": "Nombre", "modalidad": "Modalidad",
            "cantidad_sesiones": "Sesiones", "duracion_dias": "Dias",
            "frecuencia": "Frecuencia", "reprogramaciones_max": "Reprog. max.",
            "precio_base": "Precio", "activo": "Activo"
        }), use_container_width=True)

    st.markdown("---")
    st.subheader("Nutricionistas por programa")
    st.caption("Asigna las nutricionistas que atienden cada programa.")

    prog_asig  = run_query("SELECT id_programa, nombre FROM programas WHERE activo=TRUE ORDER BY nombre")
    nutri_asig = run_query("SELECT id_nutricionista, nombre||' '||apellido AS nombre FROM nutricionistas WHERE estado=TRUE ORDER BY apellido")

    if prog_asig and nutri_asig:
        col1, col2 = st.columns(2)
        with col1:
            prog_opts  = {p["nombre"]: p["id_programa"] for p in prog_asig}
            prog_sel_a = st.selectbox("Programa", list(prog_opts.keys()), key="prog_asig")
            id_prog_a  = prog_opts[prog_sel_a]

        ya_asignadas = run_query("""
            SELECT n.id_nutricionista, n.nombre||' '||n.apellido AS nombre
            FROM programa_nutricionistas pn
            JOIN nutricionistas n ON pn.id_nutricionista=n.id_nutricionista
            WHERE pn.id_programa=%s AND pn.activo=TRUE
        """, (id_prog_a,))

        with col2:
            st.markdown("**Asignadas actualmente:**")
            if ya_asignadas:
                for na in ya_asignadas:
                    c1, c2 = st.columns([3, 1])
                    c1.markdown(f"- {na['nombre']}")
                    if c2.button("X", key=f"rm_{na['id_nutricionista']}_{id_prog_a}"):
                        run_command("""
                            UPDATE programa_nutricionistas SET activo=FALSE
                            WHERE id_programa=%s AND id_nutricionista=%s
                        """, (id_prog_a, na["id_nutricionista"]))
                        st.rerun()
            else:
                st.caption("Ninguna asignada aun.")

        ids_ya      = {n["id_nutricionista"] for n in ya_asignadas}
        disponibles = [n for n in nutri_asig if n["id_nutricionista"] not in ids_ya]
        if disponibles:
            nutr_add_opts = {n["nombre"]: n["id_nutricionista"] for n in disponibles}
            nutr_add_sel  = st.selectbox("Agregar nutricionista", list(nutr_add_opts.keys()), key="nutr_add")
            if st.button("Agregar al programa", key="btn_add_nutr"):
                run_command("""
                    INSERT INTO programa_nutricionistas (id_programa, id_nutricionista, activo)
                    VALUES (%s, %s, TRUE)
                    ON CONFLICT (id_programa, id_nutricionista) DO UPDATE SET activo=TRUE
                """, (id_prog_a, nutr_add_opts[nutr_add_sel]))
                st.success("Nutricionista asignada.")
                st.rerun()

    st.markdown("---")
    with st.expander("Crear nuevo programa"):
        col1, col2 = st.columns(2)
        with col1:
            prog_nombre     = st.text_input("Nombre *", key="prog_nombre")
            prog_modalidad  = st.selectbox("Modalidad", ["presencial", "virtual", "mixta"], key="prog_mod")
            prog_sesiones   = st.number_input("Sesiones *", min_value=1, value=4, key="prog_ses")
            prog_duracion   = st.number_input("Duracion (dias) *", min_value=1, value=60, key="prog_dur")
        with col2:
            prog_precio     = st.number_input("Precio (S/) *", min_value=0.0, value=350.0, step=10.0, key="prog_pre")
            prog_frecuencia = st.selectbox("Frecuencia", ["semanal", "quincenal", "mensual"], key="prog_fre")
            prog_reprog     = st.number_input("Reprogramaciones max.", min_value=0, value=2, key="prog_rep")
        prog_desc = st.text_area("Descripcion", key="prog_desc")

        if st.button("Crear programa", key="btn_prog"):
            if not prog_nombre:
                st.error("Nombre requerido.")
            else:
                try:
                    run_command("""
                        INSERT INTO programas
                            (nombre, descripcion, duracion_dias, cantidad_sesiones,
                             modalidad, frecuencia, reprogramaciones_max, precio_base, activo)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                    """, (prog_nombre, prog_desc, prog_duracion, prog_sesiones,
                          prog_modalidad, prog_frecuencia, prog_reprog, prog_precio))
                    st.success(f"Programa '{prog_nombre}' creado.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

    st.markdown("---")
    with st.expander("Editar programa existente"):
        if programas:
            prog_edit_opts = {p["nombre"]: p for p in programas}
            prog_edit_sel  = st.selectbox("Selecciona el programa", list(prog_edit_opts.keys()), key="prog_edit")
            pe = prog_edit_opts[prog_edit_sel]

            with st.form("form_editar_prog"):
                col1, col2 = st.columns(2)
                with col1:
                    e_nombre    = st.text_input("Nombre", value=pe["nombre"])
                    e_sesiones  = st.number_input("Sesiones", min_value=1, value=int(pe["cantidad_sesiones"]))
                    e_duracion  = st.number_input("Duracion (dias)", min_value=1, value=int(pe["duracion_dias"]))
                    e_precio    = st.number_input("Precio (S/)", min_value=0.0, value=float(pe["precio_base"]), step=10.0)
                with col2:
                    e_modalidad  = st.selectbox("Modalidad", ["presencial","virtual","mixta"],
                                                 index=["presencial","virtual","mixta"].index(pe["modalidad"]))
                    e_frecuencia = st.selectbox("Frecuencia", ["semanal","quincenal","mensual"],
                                                 index=["semanal","quincenal","mensual"].index(pe["frecuencia"]))
                    e_reprog     = st.number_input("Reprog. max.", min_value=0, value=int(pe["reprogramaciones_max"]))
                    e_activo     = st.checkbox("Activo", value=bool(pe["activo"]))

                if st.form_submit_button("Guardar cambios", use_container_width=True):
                    run_command("""
                        UPDATE programas SET nombre=%s, cantidad_sesiones=%s,
                        duracion_dias=%s, precio_base=%s, modalidad=%s,
                        frecuencia=%s, reprogramaciones_max=%s, activo=%s
                        WHERE id_programa=%s
                    """, (e_nombre, e_sesiones, e_duracion, e_precio,
                          e_modalidad, e_frecuencia, e_reprog, e_activo,
                          pe["id_programa"]))
                    st.success("Programa actualizado.")
                    st.rerun()


# ═══════════════════════════════════════
# TAB 4 — RESUMEN BD
# ═══════════════════════════════════════
with tab4:
    st.subheader("Estado de la base de datos")
    tablas = ["usuarios","nutricionistas","pacientes","programas","contratos",
              "anamnesis","sesiones","historia_nutricional","planes_nutricionales",
              "pagos","movimientos_pago","disponibilidad",
              "solicitudes_reprogramacion","permisos_acceso","plantillas_plan"]
    resultados = []
    for tabla in tablas:
        count = run_query(f"SELECT COUNT(*) AS n FROM {tabla}")
        resultados.append({"Tabla": tabla, "Registros": count[0]["n"]})
    st.dataframe(pd.DataFrame(resultados), use_container_width=True)