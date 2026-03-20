import streamlit as st
from utils import mostrar_sidebar
from database import run_query, run_command
from datetime import date, timedelta

# ─────────────────────────────────────────
# CONTROL DE ACCESO — solo pacientes
# ─────────────────────────────────────────
if "usuario" not in st.session_state:
    st.warning("Debés iniciar sesión para acceder.")
    st.stop()

if st.session_state["usuario"]["rol"] != "paciente":
    st.error("Esta sección es solo para pacientes.")
    st.stop()

usuario  = st.session_state["usuario"]
id_paciente = usuario["id_paciente"]

if not id_paciente:
    st.error("Tu cuenta no tiene un perfil de paciente. Contactá al administrador.")
    st.stop()

# ─────────────────────────────────────────
# VERIFICAR QUE TENGA CONTRATO ACTIVO
# ─────────────────────────────────────────
contrato = run_query("""
    SELECT c.id_contrato, c.id_nutricionista,
           pr.nombre AS programa,
           pr.cantidad_sesiones,
           n.nombre || ' ' || n.apellido AS nutricionista
    FROM contratos c
    JOIN programas pr ON c.id_programa = pr.id_programa
    JOIN nutricionistas n ON c.id_nutricionista = n.id_nutricionista
    WHERE c.id_paciente = %s AND c.estado = 'activo'
    LIMIT 1
""", (id_paciente,))

if not contrato:
    st.warning("No tenés un contrato activo. Contactá al administrador.")
    st.stop()

c = contrato[0]

# Verificar si ya tiene la primera sesión agendada
primera_sesion = run_query("""
    SELECT id_sesion, fecha_hora_programada, estado
    FROM sesiones
    WHERE id_contrato = %s AND numero_sesion = 1
    LIMIT 1
""", (c["id_contrato"],))

# ─────────────────────────────────────────
# PÁGINA
# ─────────────────────────────────────────
mostrar_sidebar()

st.title("Elegí tu primera consulta")
st.markdown("---")

# Info del programa
with st.container(border=True):
    col1, col2, col3 = st.columns(3)
    col1.metric("Programa",      c["programa"])
    col2.metric("Nutricionista", c["nutricionista"])
    col3.metric("Sesiones",      c["cantidad_sesiones"])

st.markdown("---")

# Si ya tiene primera sesión agendada
if primera_sesion and primera_sesion[0]["estado"] == "programada":
    ps = primera_sesion[0]
    fecha_str = str(ps["fecha_hora_programada"])[:16]
    st.success(f"Tu primera consulta está agendada para el **{fecha_str}**")
    st.info("La nutricionista confirmará la sesión en breve. Te avisaremos por email.")

    if st.button("Cambiar horario"):
        run_command("""
            UPDATE sesiones
            SET estado = 'pendiente', fecha_hora_programada = fecha_hora_original
            WHERE id_sesion = %s
        """, (ps["id_sesion"],))
        st.rerun()
    st.stop()

# ─────────────────────────────────────────
# MOSTRAR SLOTS DISPONIBLES
# ─────────────────────────────────────────
st.subheader("Slots disponibles")
st.caption("Seleccioná el día y horario que mejor te quede para tu primera consulta.")

id_nutricionista = c["id_nutricionista"]

# Filtro de fecha
col1, col2 = st.columns(2)
with col1:
    fecha_desde = st.date_input("Desde", value=date.today())
with col2:
    fecha_hasta = st.date_input("Hasta", value=date.today() + timedelta(days=30))

slots = run_query("""
    SELECT id_slot, fecha_hora_inicio, duracion_minutos
    FROM disponibilidad
    WHERE id_nutricionista = %s
    AND estado = 'disponible'
    AND DATE(fecha_hora_inicio) BETWEEN %s AND %s
    ORDER BY fecha_hora_inicio
""", (id_nutricionista, fecha_desde, fecha_hasta))

if not slots:
    st.info("No hay slots disponibles en ese período. Probá con otras fechas o contactá al equipo.")
    st.stop()

# Agrupar por día
from collections import defaultdict
por_dia = defaultdict(list)
for s in slots:
    dia = str(s["fecha_hora_inicio"])[:10]
    por_dia[dia].append(s)

st.markdown(f"**{len(slots)} horarios disponibles:**")

slot_elegido = None

for dia, slots_dia in sorted(por_dia.items()):
    fecha_obj = date.fromisoformat(dia)
    dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves",
                   "Viernes", "Sábado", "Domingo"]
    nombre_dia = dias_semana[fecha_obj.weekday()]
    st.markdown(f"**{nombre_dia} {fecha_obj.strftime('%d/%m/%Y')}**")

    cols = st.columns(min(len(slots_dia), 4))
    for i, slot in enumerate(slots_dia):
        hora = str(slot["fecha_hora_inicio"])[11:16]
        duracion = slot["duracion_minutos"]
        with cols[i % 4]:
            if st.button(f"{hora}\n({duracion} min)",
                         key=f"slot_{slot['id_slot']}",
                         use_container_width=True):
                slot_elegido = slot

if slot_elegido:
    fecha_hora = slot_elegido["fecha_hora_inicio"]
    fecha_str  = str(fecha_hora)[:16]

    st.markdown("---")
    st.markdown(f"### Confirmás el horario: **{fecha_str}**?")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Sí, confirmar", use_container_width=True, type="primary"):
            try:
                # Actualizar la primera sesión del contrato
                run_command("""
                    UPDATE sesiones
                    SET fecha_hora_programada = %s,
                        estado = 'programada'
                    WHERE id_contrato = %s AND numero_sesion = 1
                """, (fecha_hora, c["id_contrato"]))

                # Marcar el slot como reservado
                run_command("""
                    UPDATE disponibilidad
                    SET estado = 'reservado',
                        id_sesion = (
                            SELECT id_sesion FROM sesiones
                            WHERE id_contrato = %s AND numero_sesion = 1
                        )
                    WHERE id_slot = %s
                """, (c["id_contrato"], slot_elegido["id_slot"]))

                st.success(f"Primera consulta agendada para el {fecha_str}. ¡Te esperamos!")
                st.balloons()
                st.rerun()

            except Exception as e:
                st.error(f"Error al agendar: {e}")
    with col2:
        if st.button("← Elegir otro horario", use_container_width=True):
            st.rerun()