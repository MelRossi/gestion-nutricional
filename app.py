# -*- coding: utf-8 -*-
import streamlit as st
from database import run_query
from utils import cargar_estilos, mostrar_sidebar, page_header, info_banner

st.set_page_config(
    page_title="Gisella - Nutrición Profesional",
    page_icon="🥗",
    layout="wide"
)

cargar_estilos()


# ─────────────────────────────────────────
# DASHBOARDS
# ─────────────────────────────────────────
def _dashboard_admin():
    st.subheader("Resumen general")

    pendientes = run_query("""
        SELECT COUNT(*) AS n
        FROM usuarios
        WHERE rol = 'nutricionista'
          AND estado_aprobacion = 'pendiente'
    """)
    pendientes_pago = run_query("""
        SELECT COUNT(*) AS n
        FROM contratos
        WHERE estado = 'pendiente_pago'
    """)

    if pendientes and pendientes[0]["n"] > 0:
        info_banner(
            f"Hay {pendientes[0]['n']} nutricionista(s) pendiente(s) de aprobación.",
            "warning"
        )

    if pendientes_pago and pendientes_pago[0]["n"] > 0:
        info_banner(
            f"Hay {pendientes_pago[0]['n']} pago(s) pendiente(s) de confirmar.",
            "warning"
        )

    col1, col2, col3, col4 = st.columns(4)

    total_pacientes = run_query("""
        SELECT COUNT(*) AS n
        FROM pacientes
        WHERE estado = 'activo'
    """)

    total_contratos = run_query("""
        SELECT COUNT(*) AS n
        FROM contratos
        WHERE estado = 'activo'
    """)

    sesiones_hoy = run_query("""
        SELECT COUNT(*) AS n
        FROM sesiones
        WHERE DATE(fecha_hora_programada) = CURRENT_DATE
          AND estado = 'programada'
    """)

    pagos_atrasados = run_query("""
        SELECT COUNT(*) AS n
        FROM pagos
        WHERE estado = 'atrasado'
    """)

    col1.metric("Pacientes activos", total_pacientes[0]["n"])
    col2.metric("Contratos activos", total_contratos[0]["n"])
    col3.metric("Sesiones hoy", sesiones_hoy[0]["n"])
    col4.metric("Pagos atrasados", pagos_atrasados[0]["n"])


def _dashboard_nutricionista(usuario):
    st.subheader("Mi resumen")

    id_n = usuario["id_nutricionista"]
    if not id_n:
        info_banner("No se encontró perfil de nutricionista.", "info")
        return

    pendientes_turno = run_query("""
        SELECT COUNT(*) AS n
        FROM sesiones s
        JOIN contratos c ON s.id_contrato = c.id_contrato
        WHERE s.id_nutricionista_prog = %s
          AND s.numero_sesion = 1
          AND s.estado_confirmacion = 'pendiente'
    """, (id_n,))

    if pendientes_turno and pendientes_turno[0]["n"] > 0:
        info_banner(
            f"Tenés {pendientes_turno[0]['n']} turno(s) de primera sesión pendiente(s) de confirmar. Revisá tu Agenda.",
            "warning"
        )

    col1, col2, col3 = st.columns(3)

    mis_pacientes = run_query("""
        SELECT COUNT(DISTINCT id_paciente) AS n
        FROM contratos
        WHERE id_nutricionista = %s
          AND estado = 'activo'
    """, (id_n,))

    mis_sesiones_hoy = run_query("""
        SELECT COUNT(*) AS n
        FROM sesiones
        WHERE id_nutricionista_prog = %s
          AND DATE(fecha_hora_programada) = CURRENT_DATE
          AND estado = 'programada'
    """, (id_n,))

    mis_sesiones_semana = run_query("""
        SELECT COUNT(*) AS n
        FROM sesiones
        WHERE id_nutricionista_prog = %s
          AND DATE(fecha_hora_programada) BETWEEN CURRENT_DATE AND CURRENT_DATE + 7
          AND estado = 'programada'
    """, (id_n,))

    col1.metric("Mis pacientes", mis_pacientes[0]["n"])
    col2.metric("Sesiones hoy", mis_sesiones_hoy[0]["n"])
    col3.metric("Esta semana", mis_sesiones_semana[0]["n"])


def _dashboard_paciente(usuario):
    st.subheader("Mi resumen")

    id_p = usuario["id_paciente"]
    if not id_p:
        info_banner("Tu cuenta no tiene perfil de paciente. Contactá al administrador.", "warning")
        return

    contrato = run_query("""
        SELECT c.id_contrato,
               pr.nombre AS programa,
               c.fecha_fin,
               n.nombre || ' ' || n.apellido AS nutricionista,
               c.reprogramaciones_usadas,
               pr.cantidad_sesiones,
               COALESCE(c.reprogramaciones_max_override, pr.reprogramaciones_max) AS reprog_max
        FROM contratos c
        JOIN programas pr ON c.id_programa = pr.id_programa
        JOIN nutricionistas n ON c.id_nutricionista = n.id_nutricionista
        WHERE c.id_paciente = %s
          AND c.estado = 'activo'
        LIMIT 1
    """, (id_p,))

    if not contrato:
        info_banner("No tenés un programa activo.", "info")
        return

    c = contrato[0]

    sesiones_real = run_query("""
        SELECT COUNT(*) AS n
        FROM sesiones s
        JOIN contratos c2 ON s.id_contrato = c2.id_contrato
        WHERE c2.id_paciente = %s
          AND c2.estado = 'activo'
          AND s.estado = 'atendida'
    """, (id_p,))

    realizadas_n = int(sesiones_real[0]["n"]) if sesiones_real else 0
    restantes_n = int(c["cantidad_sesiones"]) - realizadas_n

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

    proxima = run_query("""
        SELECT s.id_sesion,
               s.numero_sesion,
               s.fecha_hora_programada,
               s.modalidad,
               s.estado_confirmacion
        FROM sesiones s
        JOIN contratos c2 ON s.id_contrato = c2.id_contrato
        WHERE c2.id_paciente = %s
          AND c2.estado = 'activo'
          AND s.estado = 'programada'
          AND s.fecha_hora_programada >= NOW()
        ORDER BY s.fecha_hora_programada
        LIMIT 1
    """, (id_p,))

    col_ses, col_repr = st.columns([3, 2])

    with col_ses:
        st.markdown("**Próxima sesión**")
        if proxima:
            ps = proxima[0]
            conf = ps.get("estado_confirmacion", "")
            badge = {
                "confirmada": "confirmada",
                "pendiente": "pendiente",
                "modificada": "horario modificado",
            }.get(conf, conf)
            st.markdown(
                f"#{ps['numero_sesion']} · **{str(ps['fecha_hora_programada'])[:16]}** · {ps['modalidad']}"
            )
            st.caption(badge)
        else:
            st.caption("Sin sesiones programadas próximamente.")

    with col_repr:
        st.markdown("**Reprogramación**")
        st.caption(f"Usadas: {c['reprogramaciones_usadas']} / {c['reprog_max']}")

    st.markdown("---")

    plan = run_query("""
        SELECT pl.id_plan,
               pl.titulo,
               pl.contenido,
               pl.archivo_url,
               pl.fecha_creacion,
               pl.version,
               n.nombre || ' ' || n.apellido AS nutricionista
        FROM planes_nutricionales pl
        JOIN nutricionistas n ON pl.id_nutricionista = n.id_nutricionista
        WHERE pl.id_paciente = %s
          AND pl.estado = 'activo'
        ORDER BY pl.version DESC
        LIMIT 1
    """, (id_p,))

    st.markdown("**Último plan nutricional**")
    if plan:
        pl = plan[0]
        with st.container(border=True):
            col1, col2 = st.columns([3, 1])
            with col1:
                titulo = pl.get("titulo") or f"Plan v{pl['version']}"
                st.markdown(f"**{titulo}**")
                st.caption(f"Por {pl['nutricionista']} · {str(pl['fecha_creacion'])[:10]}")
            with col2:
                if pl["archivo_url"]:
                    st.link_button("Descargar PDF", pl["archivo_url"], use_container_width=True)
    else:
        with st.container(border=True):
            st.caption("Tu nutricionista aún no ha cargado un plan. Aparecerá aquí cuando esté disponible.")


# ─────────────────────────────────────────
# USUARIO LOGUEADO
# ─────────────────────────────────────────
if "usuario" in st.session_state:
    usuario = st.session_state["usuario"]
    rol = usuario["rol"]
    nombre = f"{usuario['nombre']} {usuario['apellido']}".strip()

    if rol == "paciente":
        id_p = usuario["id_paciente"]
        if id_p:
            pac_check = run_query("""
                SELECT onboarding_paso
                FROM pacientes
                WHERE id_paciente = %s
            """, (id_p,))
            if pac_check and int(pac_check[0]["onboarding_paso"] or 0) < 5:
                st.switch_page("pages/onboarding.py")

    mostrar_sidebar()
    page_header("Gisella - Nutrición Profesional", f"Bienvenida, {nombre}")

    if rol == "administrador":
        _dashboard_admin()
    elif rol == "nutricionista":
        _dashboard_nutricionista(usuario)
    elif rol == "paciente":
        _dashboard_paciente(usuario)

    st.stop()


# ─────────────────────────────────────────
# LANDING PÚBLICA
# ─────────────────────────────────────────
col_logo, col_btns = st.columns([5, 1])

with col_logo:
    st.markdown("# Gisella - Nutrición Profesional")
    st.markdown("##### Transforma tu salud con un plan personalizado y seguimiento profesional")

with col_btns:
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.page_link("pages/login.py", label="Iniciar sesión")
    st.page_link("pages/registro.py", label="Registrarse")

st.markdown("---")

st.markdown(
    """
    <div style='text-align:center; padding: 1.5rem 0'>
        <p style='font-size:1.15rem; color:#555; max-width:700px; margin:auto'>
            Trabajamos contigo de forma personalizada para que alcances tus objetivos.<br>
            Cada programa incluye seguimiento con nutricionista y un plan adaptado a ti.
        </p>
    </div>
    """,
    unsafe_allow_html=True
)

_, col_r, col_l, _ = st.columns([2, 1, 1, 2])

with col_r:
    if st.button("Registrarse", use_container_width=True, type="primary"):
        st.switch_page("pages/registro.py")

with col_l:
    if st.button("Iniciar sesión", use_container_width=True, type="secondary"):
        st.switch_page("pages/login.py")

st.markdown("---")

col1, col2, col3 = st.columns(3)

with col1:
    with st.container(border=True):
        st.markdown("### Profesionales certificadas")
        st.caption("Nuestras nutricionistas cuentan con formación clínica y acompañamiento continuo.")

with col2:
    with st.container(border=True):
        st.markdown("### Plan personalizado")
        st.caption("Cada plan se diseña según tu historia, objetivos y estilo de vida.")

with col3:
    with st.container(border=True):
        st.markdown("### Seguimiento real")
        st.caption("Medimos tu progreso en cada sesión para ajustar el plan cuando sea necesario.")

st.markdown("---")

col1, col2, col3 = st.columns([3, 1, 1])

with col1:
    st.caption("© 2026 Nutrición Profesional · Todos los derechos reservados")
with col2:
    st.page_link("pages/login.py", label="Iniciar sesión")
with col3:
    st.page_link("pages/registro.py", label="Registrarse")