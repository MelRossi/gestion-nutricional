import streamlit as st
from utils import mostrar_sidebar
import pandas as pd
from database import run_query, run_command
from datetime import date, datetime, timedelta

# ─────────────────────────────────────────
# CONTROL DE ACCESO
# ─────────────────────────────────────────
if "usuario" not in st.session_state:
    st.warning("Debés iniciar sesión.")
    st.stop()

if st.session_state["usuario"]["rol"] not in ("administrador", "nutricionista"):
    st.error("No tenés permisos para acceder.")
    st.stop()

usuario = st.session_state["usuario"]
es_admin = usuario["rol"] == "administrador"

# ─────────────────────────────────────────
# PÁGINA
# ─────────────────────────────────────────

mostrar_sidebar()

st.title("Disponibilidad")
st.markdown("---")

# El admin puede ver/cargar para cualquier nutricionista
# La nutricionista solo ve/carga la suya
nutricionistas = run_query("""
    SELECT id_nutricionista, nombre || ' ' || apellido AS nombre
    FROM nutricionistas WHERE estado = TRUE ORDER BY apellido
""")

if not nutricionistas:
    st.warning("No hay nutricionistas activos.")
    st.stop()

if es_admin:
    nutr_opts = {n["nombre"]: n["id_nutricionista"] for n in nutricionistas}
    nutr_sel  = st.selectbox("Nutricionista", list(nutr_opts.keys()))
    id_nutri  = nutr_opts[nutr_sel]
else:
    id_nutri = usuario["id_nutricionista"]
    nutr_nombre = next((n["nombre"] for n in nutricionistas
                        if n["id_nutricionista"] == id_nutri), "")
    st.markdown(f"Cargando disponibilidad para: **{nutr_nombre}**")

st.markdown("---")
tab1, tab2 = st.tabs(["Ver slots", "Cargar slots"])


# ═══════════════════════════════════════
# TAB 1 — VER SLOTS
# ═══════════════════════════════════════
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        fecha_desde = st.date_input("Desde", value=date.today(), key="ver_desde")
    with col2:
        fecha_hasta = st.date_input("Hasta",
                                     value=date.today() + timedelta(days=14),
                                     key="ver_hasta")

    filtro_estado = st.selectbox("Estado",
                        ["todos", "disponible", "reservado", "bloqueado"],
                        key="filtro_slot")

    query = """
        SELECT d.id_slot,
               d.fecha_hora_inicio,
               d.duracion_minutos,
               d.estado,
               d.notas,
               CASE WHEN d.id_sesion IS NOT NULL
                    THEN p.nombre || ' ' || p.apellido
                    ELSE '—' END AS paciente
        FROM disponibilidad d
        LEFT JOIN sesiones s   ON d.id_sesion  = s.id_sesion
        LEFT JOIN contratos c  ON s.id_contrato = c.id_contrato
        LEFT JOIN pacientes p  ON c.id_paciente = p.id_paciente
        WHERE d.id_nutricionista = %s
        AND DATE(d.fecha_hora_inicio) BETWEEN %s AND %s
    """
    params = [id_nutri, fecha_desde, fecha_hasta]

    if filtro_estado != "todos":
        query += " AND d.estado = %s"
        params.append(filtro_estado)

    query += " ORDER BY d.fecha_hora_inicio"
    slots = run_query(query, params)

    if slots:
        df = pd.DataFrame(slots)
        df["fecha_hora_inicio"] = pd.to_datetime(df["fecha_hora_inicio"]).dt.strftime("%d/%m/%Y %H:%M")
        df["duracion_minutos"] = df["duracion_minutos"].astype(str) + " min"
        df = df.rename(columns={
            "id_slot": "ID", "fecha_hora_inicio": "Fecha y hora",
            "duracion_minutos": "Duración", "estado": "Estado",
            "paciente": "Paciente reservado", "notas": "Notas"
        })
        st.dataframe(df[["ID", "Fecha y hora", "Duración", "Estado",
                          "Paciente reservado", "Notas"]],
                     use_container_width=True)

        # Bloquear / liberar slot
        st.markdown("---")
        with st.expander("Modificar estado de un slot"):
            slots_disponibles = [s for s in slots if s["estado"] != "reservado"]
            if slots_disponibles:
                opciones = {
                    f"#{s['id_slot']} — {str(s['fecha_hora_inicio'])[:16]} ({s['estado']})": s["id_slot"]
                    for s in slots_disponibles
                }
                slot_sel = st.selectbox("Seleccioná un slot", list(opciones.keys()))
                id_slot_sel = opciones[slot_sel]
                nuevo_estado = st.selectbox("Nuevo estado", ["disponible", "bloqueado"])

                if st.button("Actualizar", key="btn_update_slot"):
                    run_command("""
                        UPDATE disponibilidad SET estado = %s WHERE id_slot = %s
                    """, (nuevo_estado, id_slot_sel))
                    st.success("Slot actualizado.")
                    st.rerun()
    else:
        st.info("No hay slots para el período seleccionado.")


# ═══════════════════════════════════════
# TAB 2 — CARGAR SLOTS
# ═══════════════════════════════════════
with tab2:
    st.subheader("Cargar disponibilidad")

    modo = st.radio("Modo de carga",
                    ["Slot individual", "Múltiples slots en un día"],
                    horizontal=True)

    if modo == "Slot individual":
        col1, col2 = st.columns(2)
        with col1:
            fecha_slot = st.date_input("Fecha *", value=date.today(), key="fecha_ind")
            hora_slot  = st.time_input("Hora *", key="hora_ind")
        with col2:
            duracion   = st.number_input("Duración (minutos) *",
                                          min_value=30, max_value=180,
                                          value=60, step=15, key="dur_ind")
            notas      = st.text_input("Notas (opcional)", key="notas_ind")

        if st.button("Agregar slot", use_container_width=True, key="btn_ind"):
            fecha_hora = datetime.combine(fecha_slot, hora_slot)
            try:
                run_command("""
                    INSERT INTO disponibilidad
                        (id_nutricionista, fecha_hora_inicio, duracion_minutos, estado, notas)
                    VALUES (%s, %s, %s, 'disponible', %s)
                """, (id_nutri, fecha_hora, duracion, notas or None))
                st.success(f"Slot agregado: {fecha_hora.strftime('%d/%m/%Y %H:%M')}")
                st.rerun()
            except Exception as e:
                if "unique" in str(e).lower():
                    st.error("Ya existe un slot en ese horario para esta nutricionista.")
                else:
                    st.error(f"Error: {e}")

    else:  # Múltiples slots
        st.caption("Cargá todos los slots de un día de una sola vez.")
        col1, col2 = st.columns(2)
        with col1:
            fecha_multi  = st.date_input("Fecha *", value=date.today(), key="fecha_multi")
            hora_inicio  = st.time_input("Hora de inicio *",
                                          value=datetime.strptime("09:00", "%H:%M").time(),
                                          key="h_inicio")
        with col2:
            hora_fin     = st.time_input("Hora de fin *",
                                          value=datetime.strptime("17:00", "%H:%M").time(),
                                          key="h_fin")
            duracion_m   = st.number_input("Duración por slot (min)",
                                            min_value=30, max_value=180,
                                            value=60, step=15, key="dur_multi")

        # Preview de slots a generar
        slots_preview = []
        if hora_fin > hora_inicio:
            actual = datetime.combine(fecha_multi, hora_inicio)
            fin    = datetime.combine(fecha_multi, hora_fin)
            while actual + timedelta(minutes=duracion_m) <= fin:
                slots_preview.append(actual)
                actual += timedelta(minutes=duracion_m)

            st.markdown(f"**Se generarán {len(slots_preview)} slots:**")
            preview_text = " · ".join([s.strftime("%H:%M") for s in slots_preview])
            st.caption(preview_text)

        if st.button(f"Cargar {len(slots_preview)} slots",
                     use_container_width=True,
                     key="btn_multi",
                     disabled=len(slots_preview) == 0):
            agregados = 0
            omitidos  = 0
            for slot_dt in slots_preview:
                try:
                    run_command("""
                        INSERT INTO disponibilidad
                            (id_nutricionista, fecha_hora_inicio, duracion_minutos, estado)
                        VALUES (%s, %s, %s, 'disponible')
                    """, (id_nutri, slot_dt, duracion_m))
                    agregados += 1
                except Exception:
                    omitidos += 1  # Ya existía ese slot

            msg = f"{agregados} slots cargados."
            if omitidos:
                msg += f" {omitidos} omitidos (ya existían)."
            st.success(msg)
            st.rerun()