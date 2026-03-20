import streamlit as st
import pandas as pd
from database import run_query, run_command
from utils import mostrar_sidebar
from datetime import date, timedelta

if "usuario" not in st.session_state:
    st.warning("Debés iniciar sesión.")
    st.stop()

if st.session_state["usuario"]["rol"] not in ("administrador", "nutricionista"):
    st.error("No tenés permisos.")
    st.stop()

usuario  = st.session_state["usuario"]
rol      = usuario["rol"]
id_nutri = usuario["id_nutricionista"]

mostrar_sidebar()

# ═══════════════════════════════════════════
# VISTA ADMIN
# ═══════════════════════════════════════════
if rol == "administrador":
    st.title("Pacientes")
    st.markdown("---")

    # ── Solicitudes de permisos pendientes ──
    solicitudes = run_query("""
        SELECT pa.id_permiso,
               p.nombre||' '||p.apellido AS paciente, p.email,
               nb.nombre||' '||nb.apellido AS nutricionista_solicitante,
               na.nombre||' '||na.apellido AS nutricionista_actual,
               pr.nombre AS programa,
               pa.estado, pa.fecha_solicitud, pa.motivo
        FROM permisos_acceso pa
        JOIN pacientes p       ON pa.id_paciente = p.id_paciente
        JOIN nutricionistas nb ON pa.id_nutricionista = nb.id_nutricionista
        JOIN contratos c       ON p.id_paciente = c.id_paciente AND c.estado = 'activo'
        JOIN programas pr      ON c.id_programa = pr.id_programa
        JOIN nutricionistas na ON c.id_nutricionista = na.id_nutricionista
        WHERE pa.estado = 'pendiente'
        ORDER BY pa.fecha_solicitud DESC
    """)

    if solicitudes:
        st.warning(f"⚠️ **{len(solicitudes)} solicitud(es) de acceso pendiente(s)**")
        for s in solicitudes:
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 2, 3])
                with col1:
                    st.markdown(f"🟡 **{s['nutricionista_solicitante']}** solicita acceso a **{s['paciente']}**")
                    st.caption(f"Nutricionista actual: {s['nutricionista_actual']} · Programa: {s['programa']}")
                    if s["motivo"]:
                        st.caption(f"Motivo: {s['motivo']}")
                    st.caption(f"Solicitado: {str(s['fecha_solicitud'])[:10]}")
                with col2:
                    tipo = st.selectbox("Tipo de acceso",
                        ["Temporal", "Permanente (reasignar)"],
                        key=f"tipo_{s['id_permiso']}")
                    if tipo == "Temporal":
                        sesiones_rest = st.selectbox("Sesiones de acceso", list(range(1,21)), index=3, key=f"ses_{s['id_permiso']}")
                        f_exp = date.today() + timedelta(weeks=int(sesiones_rest) * 2)
                        st.caption(f"Expira en {sesiones_rest} sesiones (aprox. {f_exp.strftime('%d/%m/%Y')})")
                    else:
                        f_exp = None
                with col3:
                    ca, cb = st.columns(2)
                    with ca:
                        if st.button("Aprobar", key=f"apr_{s['id_permiso']}", use_container_width=True, type="primary"):
                            if tipo == "Permanente (reasignar)":
                                run_command("""
                                    UPDATE contratos SET id_nutricionista = pa.id_nutricionista
                                    FROM permisos_acceso pa
                                    WHERE contratos.id_paciente = pa.id_paciente
                                    AND pa.id_permiso = %s AND contratos.estado = 'activo'
                                """, (s["id_permiso"],))
                                run_command("""
                                    UPDATE sesiones SET id_nutricionista_prog = pa.id_nutricionista
                                    FROM permisos_acceso pa
                                    JOIN contratos c ON c.id_paciente = pa.id_paciente
                                    WHERE sesiones.id_contrato = c.id_contrato
                                    AND pa.id_permiso = %s AND sesiones.estado = 'programada'
                                """, (s["id_permiso"],))
                                run_command("UPDATE permisos_acceso SET estado='aprobado', fecha_expiracion=NULL WHERE id_permiso=%s", (s["id_permiso"],))
                                st.success("Reasignado permanentemente.")
                            else:
                                run_command("UPDATE permisos_acceso SET estado='aprobado', fecha_expiracion=%s WHERE id_permiso=%s", (f_exp, s["id_permiso"]))
                                st.success(f"Acceso temporal hasta {str(f_exp)[:10]}.")
                            st.rerun()
                    with cb:
                        if st.button("Rechazar", key=f"rec_{s['id_permiso']}", use_container_width=True):
                            run_command("UPDATE permisos_acceso SET estado='rechazado' WHERE id_permiso=%s", (s["id_permiso"],))
                            st.rerun()
        st.markdown("---")

    # ── Reasignación directa ──
    with st.expander("Reasignar paciente directamente"):
        pac_list  = run_query("""
            SELECT p.id_paciente, p.nombre||' '||p.apellido AS nombre,
                   n.nombre||' '||n.apellido AS nutricionista_actual,
                   pr.nombre AS programa, c.id_contrato
            FROM pacientes p
            JOIN contratos c      ON p.id_paciente=c.id_paciente AND c.estado='activo'
            JOIN nutricionistas n ON c.id_nutricionista=n.id_nutricionista
            JOIN programas pr     ON c.id_programa=pr.id_programa
            ORDER BY p.apellido
        """)
        nutr_list = run_query("SELECT id_nutricionista, nombre||' '||apellido AS nombre FROM nutricionistas WHERE estado=TRUE ORDER BY apellido")

        if pac_list and nutr_list:
            col1, col2 = st.columns(2)
            with col1:
                pac_opts = {f"{p['nombre']} ({p['nutricionista_actual']})": p for p in pac_list}
                pac_sel  = st.selectbox("Paciente", list(pac_opts.keys()), key="reas_pac")
            with col2:
                nutr_opts = {n["nombre"]: n["id_nutricionista"] for n in nutr_list}
                nutr_sel  = st.selectbox("Nueva nutricionista", list(nutr_opts.keys()), key="reas_nutr")

            tipo_r = st.radio("Tipo", ["Permanente", "Temporal"], horizontal=True, key="tipo_reas")
            f_exp_r = None
            if tipo_r == "Temporal":
                sesiones_r = st.selectbox("Sesiones de acceso", list(range(1,21)), index=3, key="ses_reas")
                f_exp_r = date.today() + timedelta(weeks=int(sesiones_r) * 2)
                st.caption(f"Expira en {sesiones_r} sesiones (aprox. {f_exp_r.strftime('%d/%m/%Y')})")
            pac_data = pac_opts[pac_sel]
            st.info(f"**{pac_data['nombre']}** pasará de **{pac_data['nutricionista_actual']}** a **{nutr_sel}**")

            if st.button("Reasignar", use_container_width=True, type="primary", key="btn_reas"):
                nueva_id = nutr_opts[nutr_sel]
                if tipo_r == "Permanente":
                    run_command("UPDATE contratos SET id_nutricionista=%s WHERE id_contrato=%s", (nueva_id, pac_data["id_contrato"]))
                    run_command("UPDATE sesiones SET id_nutricionista_prog=%s WHERE id_contrato=%s AND estado='programada'", (nueva_id, pac_data["id_contrato"]))
                    st.success(f"{pac_data['nombre']} reasignado permanentemente a {nutr_sel}.")
                else:
                    run_command("""
                        INSERT INTO permisos_acceso (id_nutricionista, id_paciente, estado, solicitado_por, fecha_solicitud, fecha_expiracion)
                        VALUES (%s, %s, 'aprobado', %s, CURRENT_DATE, %s)
                        ON CONFLICT (id_nutricionista, id_paciente)
                        DO UPDATE SET estado='aprobado', fecha_expiracion=%s
                    """, (nueva_id, pac_data["id_paciente"], nueva_id, f_exp_r, f_exp_r))
                    st.success(f"Acceso temporal hasta {str(f_exp_r)[:10]} otorgado a {nutr_sel}.")
                st.rerun()

    st.markdown("---")

    # ── Lista de todos los pacientes ──
    st.subheader("Todos los pacientes activos")
    pacientes = run_query("""
        SELECT p.nombre||' '||p.apellido AS paciente, p.email,
               pr.nombre AS programa,
               n.nombre||' '||n.apellido AS nutricionista,
               c.estado AS contrato,
               c.fecha_inicio AS inicio, c.fecha_fin AS fin,
               pr.cantidad_sesiones,
               (SELECT COUNT(*) FROM sesiones s WHERE s.id_contrato=c.id_contrato AND s.estado='atendida') AS realizadas
        FROM pacientes p
        JOIN contratos c      ON p.id_paciente=c.id_paciente AND c.estado='activo'
        JOIN programas pr     ON c.id_programa=pr.id_programa
        JOIN nutricionistas n ON c.id_nutricionista=n.id_nutricionista
        ORDER BY paciente
    """)

    if pacientes:
        df = pd.DataFrame(pacientes)
        df["Progreso"] = df.apply(lambda r: f"{int(r['realizadas'])}/{int(r['cantidad_sesiones'])}", axis=1)
        df["Restantes"] = df["cantidad_sesiones"].astype(int) - df["realizadas"].astype(int)
        df = df.rename(columns={
            "paciente":"Paciente","email":"Email","programa":"Programa",
            "nutricionista":"Nutricionista","contrato":"Contrato",
            "inicio":"Inicio","fin":"Fin","realizadas":"Realizadas"
        })
        st.dataframe(df[["Paciente","Email","Programa","Nutricionista",
                          "Progreso","Realizadas","Restantes","Contrato","Inicio","Fin"]],
                     use_container_width=True)

        opciones = {p["paciente"]: run_query("SELECT id_paciente FROM pacientes WHERE nombre||' '||apellido=%s LIMIT 1", (p["paciente"],)) for p in pacientes}
        sel = st.selectbox("Abrir ficha de", list(opciones.keys()))
        if st.button("Abrir ficha", use_container_width=True):
            res = opciones[sel]
            if res:
                st.session_state["id_paciente_ficha"] = res[0]["id_paciente"]
                st.switch_page("pages/3_ficha_paciente.py")
    else:
        st.info("No hay pacientes activos.")

# ═══════════════════════════════════════════
# VISTA NUTRICIONISTA
# ═══════════════════════════════════════════
else:
    st.title("Mis Pacientes")
    st.markdown("---")

    tab1, tab2 = st.tabs(["Pacientes activos", "Solicitar acceso a paciente"])

    with tab1:
        pacientes = run_query("""
            SELECT DISTINCT p.id_paciente,
                   p.nombre||' '||p.apellido AS paciente, p.email,
                   pr.nombre AS programa,
                   n.nombre||' '||n.apellido AS nutricionista,
                   c.estado AS estado_contrato,
                   c.fecha_inicio, c.fecha_fin, c.id_contrato,
                   pr.cantidad_sesiones,
                   (SELECT COUNT(*) FROM sesiones s WHERE s.id_contrato=c.id_contrato AND s.estado='atendida') AS sesiones_realizadas,
                   'propio' AS tipo_acceso
            FROM pacientes p
            JOIN contratos c      ON p.id_paciente=c.id_paciente AND c.estado='activo'
            JOIN programas pr     ON c.id_programa=pr.id_programa
            JOIN nutricionistas n ON c.id_nutricionista=n.id_nutricionista
            WHERE c.id_nutricionista=%s
            ORDER BY paciente
        """, (id_nutri,))

        con_permiso = run_query("""
            SELECT DISTINCT p.id_paciente,
                   p.nombre||' '||p.apellido AS paciente, p.email,
                   pr.nombre AS programa,
                   n.nombre||' '||n.apellido AS nutricionista,
                   c.estado AS estado_contrato,
                   c.fecha_inicio, c.fecha_fin, c.id_contrato,
                   pr.cantidad_sesiones,
                   (SELECT COUNT(*) FROM sesiones s WHERE s.id_contrato=c.id_contrato AND s.estado='atendida') AS sesiones_realizadas,
                   CASE WHEN pa.fecha_expiracion IS NULL THEN 'permiso permanente'
                        ELSE 'hasta '||TO_CHAR(pa.fecha_expiracion,'DD/MM/YYYY') END AS tipo_acceso
            FROM permisos_acceso pa
            JOIN pacientes p      ON pa.id_paciente=p.id_paciente
            JOIN contratos c      ON p.id_paciente=c.id_paciente AND c.estado='activo'
            JOIN programas pr     ON c.id_programa=pr.id_programa
            JOIN nutricionistas n ON c.id_nutricionista=n.id_nutricionista
            WHERE pa.id_nutricionista=%s AND pa.estado='aprobado'
            AND (pa.fecha_expiracion IS NULL OR pa.fecha_expiracion >= CURRENT_DATE)
        """, (id_nutri,))

        ids_ya = {p["id_paciente"] for p in pacientes}
        for p in con_permiso:
            if p["id_paciente"] not in ids_ya:
                pacientes.append(p)

        if not pacientes:
            st.info("No tenés pacientes activos asignados.")
        else:
            buscar = st.text_input("Buscar por nombre o email", "")
            if buscar:
                pacientes = [p for p in pacientes if buscar.lower() in p["paciente"].lower()
                             or buscar.lower() in (p["email"] or "").lower()]

            st.markdown(f"**{len(pacientes)} paciente(s)**")
            df = pd.DataFrame(pacientes)
            df["Progreso"]   = df.apply(lambda r: f"{int(r['sesiones_realizadas'])}/{int(r['cantidad_sesiones'])}", axis=1)
            df["Realizadas"] = df["sesiones_realizadas"].astype(int)
            df["Restantes"]  = df["cantidad_sesiones"].astype(int) - df["sesiones_realizadas"].astype(int)
            df = df.rename(columns={
                "paciente":"Paciente","email":"Email","programa":"Programa",
                "nutricionista":"Nutricionista","estado_contrato":"Contrato",
                "fecha_inicio":"Inicio","fecha_fin":"Fin","tipo_acceso":"Acceso"
            })
            st.dataframe(df[["Paciente","Email","Programa","Progreso",
                              "Realizadas","Restantes","Contrato","Inicio","Fin","Acceso"]],
                         use_container_width=True)

            st.markdown("---")
            opciones = {p["paciente"]: p["id_paciente"] for p in pacientes}
            sel = st.selectbox("Abrir ficha de", list(opciones.keys()))
            if st.button("Abrir ficha", use_container_width=True):
                st.session_state["id_paciente_ficha"] = opciones[sel]
                st.switch_page("pages/3_ficha_paciente.py")

    with tab2:
        st.subheader("Solicitar acceso a un paciente")
        st.caption("El admin aprobará o rechazará tu solicitud.")

        mis_solicitudes = run_query("""
            SELECT pa.id_permiso, p.nombre||' '||p.apellido AS paciente,
                   pa.estado, pa.fecha_solicitud, pa.fecha_expiracion
            FROM permisos_acceso pa
            JOIN pacientes p ON pa.id_paciente=p.id_paciente
            WHERE pa.id_nutricionista=%s
            ORDER BY pa.fecha_solicitud DESC
        """, (id_nutri,))

        if mis_solicitudes:
            st.markdown("**Mis solicitudes:**")
            df_s = pd.DataFrame(mis_solicitudes)
            df_s["fecha_solicitud"]  = pd.to_datetime(df_s["fecha_solicitud"]).dt.strftime("%d/%m/%Y")
            df_s["fecha_expiracion"] = df_s["fecha_expiracion"].apply(lambda x: str(x)[:10] if x else "Permanente")
            badges = {"pendiente":"🟡 pendiente","aprobado":"🟢 aprobado","rechazado":"🔴 rechazado"}
            df_s["estado"] = df_s["estado"].map(lambda x: badges.get(x, x))
            df_s = df_s.rename(columns={"paciente":"Paciente","estado":"Estado",
                                         "fecha_solicitud":"Solicitado","fecha_expiracion":"Expira"})
            st.dataframe(df_s[["Paciente","Estado","Solicitado","Expira"]], use_container_width=True)
            st.markdown("---")

        buscar_pac = st.text_input("Nombre o email del paciente (mínimo 3 caracteres)", key="buscar_acceso")
        if buscar_pac and len(buscar_pac) >= 3:
            resultados = run_query("""
                SELECT DISTINCT p.id_paciente, p.nombre||' '||p.apellido AS nombre, p.email,
                       pr.nombre AS programa, n.nombre||' '||n.apellido AS nutricionista_actual
                FROM pacientes p
                JOIN contratos c      ON p.id_paciente=c.id_paciente AND c.estado='activo'
                JOIN programas pr     ON c.id_programa=pr.id_programa
                JOIN nutricionistas n ON c.id_nutricionista=n.id_nutricionista
                WHERE c.id_nutricionista != %s
                AND (LOWER(p.nombre||' '||p.apellido) LIKE %s OR LOWER(p.email) LIKE %s)
            """, (id_nutri, f"%{buscar_pac.lower()}%", f"%{buscar_pac.lower()}%"))

            if resultados:
                for r in resultados:
                    with st.container(border=True):
                        col1, col2 = st.columns([3,1])
                        with col1:
                            st.markdown(f"**{r['nombre']}** — {r['email']}")
                            st.caption(f"Programa: {r['programa']} · Nutricionista: {r['nutricionista_actual']}")
                        with col2:
                            ya = run_query("SELECT id_permiso FROM permisos_acceso WHERE id_nutricionista=%s AND id_paciente=%s AND estado IN ('pendiente','aprobado')", (id_nutri, r["id_paciente"]))
                            if ya:
                                st.caption("Ya solicitado")
                            else:
                                motivo = st.text_input("Motivo", key=f"mot_{r['id_paciente']}")
                                if st.button("Solicitar", key=f"sol_{r['id_paciente']}", use_container_width=True):
                                    run_command("INSERT INTO permisos_acceso (id_nutricionista,id_paciente,estado,solicitado_por,fecha_solicitud,motivo) VALUES (%s,%s,'pendiente',%s,CURRENT_DATE,%s)",
                                                (id_nutri, r["id_paciente"], id_nutri, motivo or None))
                                    st.success("Solicitud enviada.")
                                    st.rerun()
            else:
                st.info("No se encontraron pacientes.")
        elif buscar_pac:
            st.caption("Ingresá al menos 3 caracteres.")