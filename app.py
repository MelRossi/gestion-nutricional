import streamlit as st
from database import run_query, run_command

st.set_page_config(
    page_title="Gisella - Nutrición Profesional",
    page_icon="🥗",
    layout="wide"
)

# ─────────────────────────────────────────
# DASHBOARDS
# ─────────────────────────────────────────
def _dashboard_admin():
    st.subheader("Resumen general")
    pendientes      = run_query("SELECT COUNT(*) AS n FROM usuarios WHERE rol='nutricionista' AND estado_aprobacion='pendiente'")
    pendientes_pago = run_query("SELECT COUNT(*) AS n FROM contratos WHERE estado='pendiente_pago'")
    if pendientes[0]["n"] > 0:
        st.warning(f"Hay **{pendientes[0]['n']}** nutricionista(s) pendiente(s) de aprobación.")
    if pendientes_pago[0]["n"] > 0:
        st.warning(f"Hay **{pendientes_pago[0]['n']}** pago(s) pendiente(s) de confirmar.")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Pacientes activos",  run_query("SELECT COUNT(*) AS n FROM pacientes WHERE estado='activo'")[0]["n"])
    col2.metric("Contratos activos",  run_query("SELECT COUNT(*) AS n FROM contratos WHERE estado='activo'")[0]["n"])
    col3.metric("Sesiones hoy",       run_query("SELECT COUNT(*) AS n FROM sesiones WHERE DATE(fecha_hora_programada)=CURRENT_DATE AND estado='programada'")[0]["n"])
    col4.metric("Pagos atrasados",    run_query("SELECT COUNT(*) AS n FROM pagos WHERE estado='atrasado'")[0]["n"])

def _dashboard_nutricionista(usuario):
    st.subheader("Mi resumen")
    id_n = usuario["id_nutricionista"]
    if not id_n:
        return
    pendientes_turno = run_query("""
        SELECT COUNT(*) AS n FROM sesiones s
        JOIN contratos c ON s.id_contrato=c.id_contrato
        WHERE s.id_nutricionista_prog=%s
        AND s.numero_sesion=1 AND s.estado_confirmacion='pendiente'
    """, (id_n,))
    if pendientes_turno and pendientes_turno[0]["n"] > 0:
        st.warning(f"Tenés **{pendientes_turno[0]['n']}** turno(s) de primera sesión pendiente(s) de confirmar. Revisá tu Agenda.")
    col1, col2, col3 = st.columns(3)
    col1.metric("Mis pacientes",   run_query("SELECT COUNT(DISTINCT id_paciente) AS n FROM contratos WHERE id_nutricionista=%s AND estado='activo'", (id_n,))[0]["n"])
    col2.metric("Sesiones hoy",    run_query("SELECT COUNT(*) AS n FROM sesiones WHERE id_nutricionista_prog=%s AND DATE(fecha_hora_programada)=CURRENT_DATE AND estado='programada'", (id_n,))[0]["n"])
    col3.metric("Esta semana",     run_query("SELECT COUNT(*) AS n FROM sesiones WHERE id_nutricionista_prog=%s AND DATE(fecha_hora_programada) BETWEEN CURRENT_DATE AND CURRENT_DATE+7 AND estado='programada'", (id_n,))[0]["n"])

def _dashboard_paciente(usuario):
    st.subheader("Mi resumen")
    id_p = usuario["id_paciente"]
    if not id_p:
        st.warning("Tu cuenta no tiene perfil de paciente. Contactá al administrador.")
        return

    contrato = run_query("""
        SELECT c.id_contrato, pr.nombre AS programa, c.fecha_fin,
               n.nombre||' '||n.apellido AS nutricionista,
               n.id_nutricionista,
               c.reprogramaciones_usadas, pr.cantidad_sesiones,
               COALESCE(c.reprogramaciones_max_override, pr.reprogramaciones_max) AS reprog_max
        FROM contratos c
        JOIN programas pr     ON c.id_programa=pr.id_programa
        JOIN nutricionistas n ON c.id_nutricionista=n.id_nutricionista
        WHERE c.id_paciente=%s AND c.estado='activo' LIMIT 1
    """, (id_p,))

    if not contrato:
        st.info("No tenés un programa activo.")
        return

    c = contrato[0]
    sesiones_real = run_query("""
        SELECT COUNT(*) AS n FROM sesiones s
        JOIN contratos c2 ON s.id_contrato=c2.id_contrato
        WHERE c2.id_paciente=%s AND c2.estado='activo' AND s.estado='atendida'
    """, (id_p,))
    realizadas_n = int(sesiones_real[0]["n"]) if sesiones_real else 0
    restantes_n  = int(c["cantidad_sesiones"]) - realizadas_n

    # Métricas compactas
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.caption("Programa")
        st.markdown(f"**{c['programa']}**")
    with col2:
        st.caption("Nutricionista")
        st.markdown(f"**{c['nutricionista']}**")
    with col3:
        st.caption("Realizadas")
        st.markdown(f"**{realizadas_n} de {c['cantidad_sesiones']}**")
    with col4:
        st.caption("Restantes")
        st.markdown(f"**{restantes_n}**")

    st.markdown("---")

    # ── PRÓXIMA SESIÓN + REPROGRAMACIÓN ──
    proxima = run_query("""
        SELECT s.id_sesion, s.numero_sesion, s.fecha_hora_programada,
               s.modalidad, s.estado_confirmacion
        FROM sesiones s
        JOIN contratos c2 ON s.id_contrato=c2.id_contrato
        WHERE c2.id_paciente=%s AND c2.estado='activo'
        AND s.estado='programada' AND s.fecha_hora_programada>=NOW()
        ORDER BY s.fecha_hora_programada LIMIT 1
    """, (id_p,))

    col_ses, col_repr = st.columns([3,2])

    with col_ses:
        st.markdown("**Próxima sesión**")
        if proxima:
            ps   = proxima[0]
            conf = ps.get("estado_confirmacion","")
            badge = {"confirmada":"confirmada","pendiente":"pendiente","modificada":"horario modificado"}.get(conf, conf)
            st.markdown(f"#{ps['numero_sesion']} · **{str(ps['fecha_hora_programada'])[:16]}** · {ps['modalidad']}")
            st.caption(badge)
        else:
            st.caption("Sin sesiones programadas próximamente.")

    with col_repr:
        st.markdown("**Reprogramación**")
        # Ver si hay solicitud activa con opciones propuestas
        sol_activa = run_query("""
            SELECT id_solicitud, opcion_1, opcion_2, opcion_3, estado, propuesta_por
            FROM solicitudes_reprogramacion
            WHERE id_paciente=%s AND estado='pendiente'
            AND (opcion_1 IS NOT NULL OR opcion_2 IS NOT NULL OR opcion_3 IS NOT NULL)
            ORDER BY id_solicitud DESC LIMIT 1
        """, (id_p,))

        if sol_activa:
            sol = sol_activa[0]
            st.caption("Tu nutricionista propuso estos horarios:")
            opciones = [(f"Opción 1: {str(sol['opcion_1'])[:16]}", sol['opcion_1']) if sol['opcion_1'] else None,
                        (f"Opción 2: {str(sol['opcion_2'])[:16]}", sol['opcion_2']) if sol['opcion_2'] else None,
                        (f"Opción 3: {str(sol['opcion_3'])[:16]}", sol['opcion_3']) if sol['opcion_3'] else None]
            opciones = [o for o in opciones if o]
            for label, val in opciones:
                if st.button(label, key=f"op_{str(val)}", use_container_width=True):
                    run_command("""
                        UPDATE solicitudes_reprogramacion
                        SET estado='aprobado', opcion_elegida=%s, fecha_aprobacion=NOW()
                        WHERE id_solicitud=%s
                    """, (val, sol["id_solicitud"]))
                    if proxima:
                        run_command("""
                            UPDATE sesiones SET fecha_hora_programada=%s,
                            estado_confirmacion='confirmada',
                            contador_reprogramaciones=contador_reprogramaciones+1
                            WHERE id_sesion=%s
                        """, (val, proxima[0]["id_sesion"]))
                        run_command("""
                            UPDATE contratos SET reprogramaciones_usadas=reprogramaciones_usadas+1,
                            fecha_ultima_reprogramacion=CURRENT_DATE
                            WHERE id_contrato=%s
                        """, (c["id_contrato"],))
                    st.success("¡Horario confirmado!")
                    st.rerun()
        else:
            # Ver si ya tiene solicitud pendiente sin opciones
            sol_pend = run_query("""
                SELECT id_solicitud, estado FROM solicitudes_reprogramacion
                WHERE id_paciente=%s AND estado='pendiente'
                ORDER BY id_solicitud DESC LIMIT 1
            """, (id_p,))

            if sol_pend:
                st.caption("Solicitud enviada. Tu nutricionista pronto te enviará opciones.")
            else:
                # Validar si puede reprogramar
                puede = True
                msg   = ""
                usado = int(c["reprogramaciones_usadas"])
                maximo = int(c["reprog_max"])
                if usado >= maximo:
                    puede = False
                    msg   = f"Alcanzaste el límite de {maximo} reprogramaciones."
                else:
                    from datetime import date
                    ult_repr = run_query("SELECT fecha_ultima_reprogramacion FROM contratos WHERE id_contrato=%s", (c["id_contrato"],))
                    if ult_repr and ult_repr[0]["fecha_ultima_reprogramacion"]:
                        ult = ult_repr[0]["fecha_ultima_reprogramacion"]
                        hoy = date.today()
                        ult_d = ult if isinstance(ult, type(hoy)) else ult.date()
                        if ult_d.year == hoy.year and ult_d.month == hoy.month:
                            puede = False
                            msg   = "Ya reprogramaste este mes. Podés volver a hacerlo el mes próximo."

                if puede and proxima:
                    if st.button("Solicitar reprogramación", use_container_width=True):
                        run_command("""
                            INSERT INTO solicitudes_reprogramacion
                                (id_sesion, id_paciente, estado, propuesta_por, fecha_creacion)
                            VALUES (%s, %s, 'pendiente', 'paciente', NOW())
                        """, (proxima[0]["id_sesion"], id_p))
                        st.success("Solicitud enviada. Tu nutricionista te enviará opciones pronto.")
                        st.rerun()
                    st.caption(f"Usadas: {usado}/{maximo}")
                elif not proxima:
                    st.caption("Sin sesiones para reprogramar.")
                else:
                    st.caption(f"⚠️ {msg}")

    st.markdown("---")

    # ── ÚLTIMO PLAN NUTRICIONAL ──
    plan = run_query("""
        SELECT pl.id_plan, pl.titulo, pl.contenido, pl.archivo_url,
               pl.fecha_creacion, pl.version,
               n.nombre||' '||n.apellido AS nutricionista
        FROM planes_nutricionales pl
        JOIN nutricionistas n ON pl.id_nutricionista=n.id_nutricionista
        WHERE pl.id_paciente=%s AND pl.estado='activo'
        ORDER BY pl.version DESC LIMIT 1
    """, (id_p,))

    st.markdown("**Último plan nutricional**")
    if plan:
        pl = plan[0]
        st.markdown("**Mi plan nutricional activo**")
        with st.container(border=True):
            col1, col2 = st.columns([3,1])
            with col1:
                titulo = pl.get("titulo") or f"Plan v{pl['version']}"
                st.markdown(f"**{titulo}**")
                st.caption(f"Por {pl['nutricionista']} · {str(pl['fecha_creacion'])[:10]}")
            with col2:
                if pl["archivo_url"]:
                    st.link_button("Descargar PDF", pl["archivo_url"], use_container_width=True)
                elif pl["contenido"]:
                    try:
                        from reportlab.lib.pagesizes import A4
                        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
                        from reportlab.lib.styles import getSampleStyleSheet
                        from reportlab.lib.units import cm
                        import io
                        buf = io.BytesIO()
                        doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=2*cm, bottomMargin=2*cm,
                            leftMargin=2*cm, rightMargin=2*cm)
                        styles = getSampleStyleSheet()
                        titulo_plan = pl.get("titulo") or f"Plan v{pl['version']}"
                        story = [
                            Paragraph(f"Plan nutricional: {titulo_plan}", styles["Heading1"]),
                            Paragraph(f"Nutricionista: {pl['nutricionista']}", styles["Normal"]),
                            Paragraph(f"Fecha: {str(pl['fecha_creacion'])[:10]}", styles["Normal"]),
                            Spacer(1, 0.5*cm),
                        ]
                        for linea in (pl["contenido"] or "").split("\n"):
                            story.append(Paragraph(linea or " ", styles["Normal"]))
                        doc.build(story)
                        buf.seek(0)
                        st.download_button("Descargar PDF", data=buf,
                            file_name=f"plan_v{pl['version']}.pdf",
                            mime="application/pdf",
                            key="dl_plan_inicio",
                            use_container_width=True)
                    except ImportError:
                        st.caption("pip install reportlab")
    else:
        with st.container(border=True):
            st.caption("Tu nutricionista aún no ha cargado un plan. Aparecerá aquí cuando esté disponible.")

# ─────────────────────────────────────────
# USUARIO LOGUEADO
# ─────────────────────────────────────────
if "usuario" in st.session_state:
    from utils import mostrar_sidebar
    usuario = st.session_state["usuario"]
    rol     = usuario["rol"]
    nombre  = f"{usuario['nombre']} {usuario['apellido']}".strip()

    if rol == "paciente":
        id_p = usuario["id_paciente"]
        if id_p:
            pac_check = run_query("SELECT onboarding_paso FROM pacientes WHERE id_paciente=%s", (id_p,))
            if pac_check and int(pac_check[0]["onboarding_paso"] or 0) < 5:
                st.switch_page("pages/onboarding.py")

    mostrar_sidebar()
    st.title("Gisella - Nutrición Profesional")
    st.markdown(f"Bienvenida, **{nombre}**.")
    st.markdown("---")

    if rol == "administrador":
        _dashboard_admin()
    elif rol == "nutricionista":
        _dashboard_nutricionista(usuario)
    elif rol == "paciente":
        _dashboard_paciente(usuario)
    st.stop()

# ─────────────────────────────────────────
# LANDING PUBLICA
# ─────────────────────────────────────────
col_logo, col_btns = st.columns([5, 1])
with col_logo:
    st.markdown("# Gisella - Nutrición Profesional")
    st.markdown("##### Transformá tu salud con un plan personalizado y seguimiento profesional")
with col_btns:
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.page_link("pages/login.py",    label="Iniciar sesión")
    st.page_link("pages/registro.py", label="Registrarse")

st.markdown("---")

st.markdown("""
<div style='text-align:center; padding: 1.5rem 0'>
    <p style='font-size:1.15rem; color:#555; max-width:700px; margin:auto'>
        Trabajamos con vos de forma personalizada para que alcancés tus objetivos.<br>
        Cada programa incluye seguimiento con nutricionista y un plan hecho a tu medida.
    </p>
</div>
""", unsafe_allow_html=True)

_, col_r, col_l, _ = st.columns([2,1,1,2])
with col_r:
    if st.button("Registrarse", use_container_width=True, type="primary"):
        st.switch_page("pages/registro.py")
with col_l:
    if st.button("Iniciar sesión", use_container_width=True):
        st.switch_page("pages/login.py")

st.markdown("---")

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("### Profesionales certificadas")
    st.caption("Nuestras nutricionistas tienen formación clínica y acompañamiento continuo.")
with col2:
    st.markdown("### Plan personalizado")
    st.caption("Cada plan se diseña según tu historia, objetivos y estilo de vida.")
with col3:
    st.markdown("### Seguimiento real")
    st.caption("Medimos tu progreso sesión a sesión para ajustar el plan cuando sea necesario.")

st.markdown("---")
col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    st.caption("© 2026 Nutrición Profesional · Todos los derechos reservados")
with col2:
    st.page_link("pages/login.py",    label="Iniciar sesión")
with col3:
    st.page_link("pages/registro.py", label="Registrarse")