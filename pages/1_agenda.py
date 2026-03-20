import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import json
from database import run_query, run_command
from datetime import date, timedelta, datetime
from utils import mostrar_sidebar

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
st.title("Agenda")
st.markdown("---")

hoy = date.today()

# ── MÉTRICAS ──
if rol == "administrador":
    m1 = run_query("SELECT COUNT(*) AS n FROM sesiones WHERE DATE(fecha_hora_programada)=%s AND estado='programada'", (hoy,))
    m2 = run_query("SELECT COUNT(*) AS n FROM sesiones WHERE DATE(fecha_hora_programada)=%s AND estado='atendida'", (hoy,))
    m3 = run_query("SELECT COUNT(*) AS n FROM sesiones WHERE DATE(fecha_hora_programada) BETWEEN %s AND %s AND estado='programada'", (hoy, hoy+timedelta(days=7)))
    m4 = run_query("SELECT COUNT(DISTINCT id_nutricionista_prog) AS n FROM sesiones WHERE DATE(fecha_hora_programada)=%s", (hoy,))
else:
    m1 = run_query("SELECT COUNT(*) AS n FROM sesiones WHERE DATE(fecha_hora_programada)=%s AND estado='programada' AND id_nutricionista_prog=%s", (hoy, id_nutri))
    m2 = run_query("SELECT COUNT(*) AS n FROM sesiones WHERE DATE(fecha_hora_programada)=%s AND estado='atendida' AND id_nutricionista_prog=%s", (hoy, id_nutri))
    m3 = run_query("SELECT COUNT(*) AS n FROM sesiones WHERE DATE(fecha_hora_programada) BETWEEN %s AND %s AND estado='programada' AND id_nutricionista_prog=%s", (hoy, hoy+timedelta(days=7), id_nutri))
    m4 = run_query("SELECT COUNT(*) AS n FROM sesiones WHERE DATE(fecha_hora_programada)=%s AND estado='ausente' AND id_nutricionista_prog=%s", (hoy, id_nutri))
    # Turnos pendientes de confirmar
    turnos_pend = run_query("""
        SELECT COUNT(*) AS n FROM sesiones
        WHERE id_nutricionista_prog=%s AND numero_sesion=1
        AND estado_confirmacion='pendiente'
    """, (id_nutri,))
    if turnos_pend and turnos_pend[0]["n"] > 0:
        n = turnos_pend[0]["n"]
        if st.warning(f"Tenés **{n}** turno(s) de primera sesión pendiente(s) de confirmar."):
            pass
        # Click en la notificación lleva al tab confirmar turnos
        if st.button("→ Ir a confirmar turnos", key="btn_goto_conf"):
            st.session_state["agenda_tab"] = "confirmar"
            st.rerun()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Pendientes hoy",  m1[0]["n"])
col2.metric("Realizadas hoy",  m2[0]["n"])
col3.metric("Esta semana",     m3[0]["n"])
col4.metric("Nutricionistas hoy" if rol=="administrador" else "Ausentes hoy", m4[0]["n"])

st.markdown("---")

# ── TABS ──
tab_names_admin = ["Hoy", "Por fecha", "Realizadas", "Canceladas/Ausentes", "Disponibilidad", "Permisos / Reasignaciones"]
tab_names_nutri = ["Hoy", "Por fecha", "Realizadas", "Canceladas/Ausentes", "Disponibilidad", "Confirmar turnos"]

if rol == "administrador":
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(tab_names_admin)
else:
    tab1, tab2, tab3, tab4, tab5, tab_conf = st.tabs(tab_names_nutri)
    tab6 = None

# ═══════════════════════════════
# TAB 1 — HOY
# ═══════════════════════════════
with tab1:
    st.subheader(f"Sesiones del {hoy.strftime('%d/%m/%Y')}")
    if rol == "administrador":
        sesiones = run_query("""
            SELECT s.id_sesion, s.numero_sesion, s.fecha_hora_programada,
                   s.modalidad, s.estado, s.contador_reprogramaciones,
                   p.nombre||' '||p.apellido AS paciente,
                   n.nombre||' '||n.apellido AS nutricionista,
                   pr.nombre AS programa
            FROM sesiones s
            JOIN contratos c      ON s.id_contrato=c.id_contrato
            JOIN pacientes p      ON c.id_paciente=p.id_paciente
            JOIN nutricionistas n ON s.id_nutricionista_prog=n.id_nutricionista
            JOIN programas pr     ON c.id_programa=pr.id_programa
            WHERE DATE(s.fecha_hora_programada)=%s
            AND s.estado IN ('programada','atendida','ausente')
            ORDER BY s.fecha_hora_programada
        """, (hoy,))
    else:
        sesiones = run_query("""
            SELECT s.id_sesion, s.numero_sesion, s.fecha_hora_programada,
                   s.modalidad, s.estado, s.contador_reprogramaciones,
                   p.nombre||' '||p.apellido AS paciente,
                   n.nombre||' '||n.apellido AS nutricionista,
                   pr.nombre AS programa
            FROM sesiones s
            JOIN contratos c      ON s.id_contrato=c.id_contrato
            JOIN pacientes p      ON c.id_paciente=p.id_paciente
            JOIN nutricionistas n ON s.id_nutricionista_prog=n.id_nutricionista
            JOIN programas pr     ON c.id_programa=pr.id_programa
            WHERE DATE(s.fecha_hora_programada)=%s
            AND s.id_nutricionista_prog=%s
            AND s.estado IN ('programada','atendida','ausente')
            ORDER BY s.fecha_hora_programada
        """, (hoy, id_nutri))

    if not sesiones:
        st.info("No hay sesiones para hoy.")
    else:
        for s in sesiones:
            hora  = str(s["fecha_hora_programada"])[11:16]
            icono = {"programada":"🟡","atendida":"🟢","ausente":"🔴"}.get(s["estado"],"⚪")
            with st.container(border=True):
                col1, col2, col3 = st.columns([3,2,2])
                with col1:
                    st.markdown(f"{icono} **{hora} — {s['paciente']}**")
                    st.caption(f"Sesión #{s['numero_sesion']} · {s['programa']} · {s['modalidad']}")
                    if rol == "administrador":
                        st.caption(f"Nutricionista: {s['nutricionista']}")
                with col2:
                    st.markdown(f"**Estado:** {s['estado'].capitalize()}")
                    if s["contador_reprogramaciones"] > 0:
                        veces = "vez" if s["contador_reprogramaciones"] == 1 else "veces"
                        st.caption(f"Reprogramada {s['contador_reprogramaciones']} {veces}")
                with col3:
                    if s["estado"] == "programada":
                        ca, cb = st.columns(2)
                        with ca:
                            if st.button("✅", key=f"real_{s['id_sesion']}", use_container_width=True, help="Marcar atendida"):
                                run_command("UPDATE sesiones SET estado='atendida', fecha_hora_atencion=NOW(), id_nutricionista_aten=%s WHERE id_sesion=%s", (id_nutri, s["id_sesion"]))
                                st.rerun()
                        with cb:
                            if st.button("❌", key=f"aus_{s['id_sesion']}", use_container_width=True, help="Marcar ausente"):
                                run_command("UPDATE sesiones SET estado='ausente' WHERE id_sesion=%s", (s["id_sesion"],))
                                st.rerun()

# ═══════════════════════════════
# TAB 2 — POR FECHA
# ═══════════════════════════════
with tab2:
    col1, col2 = st.columns(2)
    with col1:
        f_desde = st.date_input("Desde", value=hoy, key="ag_desde")
    with col2:
        f_hasta = st.date_input("Hasta", value=hoy+timedelta(days=14), key="ag_hasta")
    filtro_e = st.selectbox("Estado", ["todos","programada","atendida","ausente","cancelada"], key="ag_est")

    if rol == "administrador":
        nutris = run_query("SELECT id_nutricionista, nombre||' '||apellido AS nombre FROM nutricionistas WHERE estado=TRUE ORDER BY apellido")
        nutr_opts = {"Todas": None}
        nutr_opts.update({n["nombre"]: n["id_nutricionista"] for n in nutris})
        nutr_sel  = st.selectbox("Nutricionista", list(nutr_opts.keys()), key="ag_nutri")
        id_filtro = nutr_opts[nutr_sel]
        q = """SELECT s.numero_sesion, s.fecha_hora_programada, s.modalidad, s.estado,
                   s.contador_reprogramaciones,
                   p.nombre||' '||p.apellido AS paciente,
                   n.nombre||' '||n.apellido AS nutricionista, pr.nombre AS programa
            FROM sesiones s
            JOIN contratos c      ON s.id_contrato=c.id_contrato
            JOIN pacientes p      ON c.id_paciente=p.id_paciente
            JOIN nutricionistas n ON s.id_nutricionista_prog=n.id_nutricionista
            JOIN programas pr     ON c.id_programa=pr.id_programa
            WHERE DATE(s.fecha_hora_programada) BETWEEN %s AND %s"""
        params = [f_desde, f_hasta]
        if filtro_e != "todos": q += " AND s.estado=%s"; params.append(filtro_e)
        if id_filtro: q += " AND s.id_nutricionista_prog=%s"; params.append(id_filtro)
        q += " ORDER BY s.fecha_hora_programada"
        sesiones2 = run_query(q, params)
    else:
        q = """SELECT s.numero_sesion, s.fecha_hora_programada, s.modalidad, s.estado,
                   s.contador_reprogramaciones,
                   p.nombre||' '||p.apellido AS paciente,
                   n.nombre||' '||n.apellido AS nutricionista, pr.nombre AS programa
            FROM sesiones s
            JOIN contratos c      ON s.id_contrato=c.id_contrato
            JOIN pacientes p      ON c.id_paciente=p.id_paciente
            JOIN nutricionistas n ON s.id_nutricionista_prog=n.id_nutricionista
            JOIN programas pr     ON c.id_programa=pr.id_programa
            WHERE DATE(s.fecha_hora_programada) BETWEEN %s AND %s AND s.id_nutricionista_prog=%s"""
        params = [f_desde, f_hasta, id_nutri]
        if filtro_e != "todos": q += " AND s.estado=%s"; params.append(filtro_e)
        q += " ORDER BY s.fecha_hora_programada"
        sesiones2 = run_query(q, params)

    if not sesiones2:
        st.info("No hay sesiones para ese período.")
    else:
        iconos = {"programada":"🟡","atendida":"🟢","ausente":"🔴","cancelada":"⚫"}
        df = pd.DataFrame(sesiones2)
        df["fecha_hora_programada"] = pd.to_datetime(df["fecha_hora_programada"]).dt.strftime("%d/%m/%Y %H:%M")
        df[""] = df["estado"].map(lambda x: iconos.get(x,"⚪"))
        df = df.rename(columns={"numero_sesion":"N°","fecha_hora_programada":"Fecha","modalidad":"Modalidad","estado":"Estado","paciente":"Paciente","nutricionista":"Nutricionista","programa":"Programa","contador_reprogramaciones":"Reprog."})
        cols = ["","Fecha","Paciente","N°","Programa","Modalidad","Estado","Reprog."]
        if rol == "administrador": cols.insert(4,"Nutricionista")
        st.dataframe(df[cols], use_container_width=True)
        st.caption(f"Total: {len(sesiones2)} sesiones")

# ═══════════════════════════════
# TAB 3 — REALIZADAS
# ═══════════════════════════════
with tab3:
    col1, col2 = st.columns(2)
    with col1: r_desde = st.date_input("Desde", value=hoy-timedelta(days=30), key="r_desde")
    with col2: r_hasta = st.date_input("Hasta", value=hoy, key="r_hasta")
    if rol == "administrador":
        realizadas = run_query("""SELECT s.numero_sesion, s.fecha_hora_programada, s.fecha_hora_atencion,
                   s.modalidad, p.nombre||' '||p.apellido AS paciente,
                   n.nombre||' '||n.apellido AS nutricionista, pr.nombre AS programa
            FROM sesiones s JOIN contratos c ON s.id_contrato=c.id_contrato
            JOIN pacientes p ON c.id_paciente=p.id_paciente
            JOIN nutricionistas n ON s.id_nutricionista_prog=n.id_nutricionista
            JOIN programas pr ON c.id_programa=pr.id_programa
            WHERE s.estado='atendida' AND DATE(s.fecha_hora_atencion) BETWEEN %s AND %s
            ORDER BY s.fecha_hora_atencion DESC""", (r_desde, r_hasta))
    else:
        realizadas = run_query("""SELECT s.numero_sesion, s.fecha_hora_programada, s.fecha_hora_atencion,
                   s.modalidad, p.nombre||' '||p.apellido AS paciente,
                   n.nombre||' '||n.apellido AS nutricionista, pr.nombre AS programa
            FROM sesiones s JOIN contratos c ON s.id_contrato=c.id_contrato
            JOIN pacientes p ON c.id_paciente=p.id_paciente
            JOIN nutricionistas n ON s.id_nutricionista_prog=n.id_nutricionista
            JOIN programas pr ON c.id_programa=pr.id_programa
            WHERE s.estado='atendida' AND s.id_nutricionista_prog=%s
            AND DATE(s.fecha_hora_atencion) BETWEEN %s AND %s
            ORDER BY s.fecha_hora_atencion DESC""", (id_nutri, r_desde, r_hasta))
    if not realizadas:
        st.info("No hay sesiones realizadas en ese período.")
    else:
        df_r = pd.DataFrame(realizadas)
        df_r["fecha_hora_programada"] = pd.to_datetime(df_r["fecha_hora_programada"]).dt.strftime("%d/%m/%Y %H:%M")
        df_r["fecha_hora_atencion"]   = pd.to_datetime(df_r["fecha_hora_atencion"]).dt.strftime("%d/%m/%Y %H:%M")
        df_r = df_r.rename(columns={"numero_sesion":"N°","fecha_hora_programada":"Programada","fecha_hora_atencion":"Atendida","modalidad":"Modalidad","paciente":"Paciente","nutricionista":"Nutricionista","programa":"Programa"})
        cols_r = ["N°","Paciente","Programada","Atendida","Modalidad","Programa"]
        if rol == "administrador": cols_r.append("Nutricionista")
        st.dataframe(df_r[cols_r], use_container_width=True)
        st.caption(f"Total: {len(realizadas)}")

# ═══════════════════════════════
# TAB 4 — CANCELADAS / AUSENTES
# ═══════════════════════════════
with tab4:
    if rol == "administrador":
        canceladas = run_query("""SELECT s.numero_sesion, s.fecha_hora_programada, s.estado, s.motivo_reprogramacion,
                   p.nombre||' '||p.apellido AS paciente, n.nombre||' '||n.apellido AS nutricionista, pr.nombre AS programa
            FROM sesiones s JOIN contratos c ON s.id_contrato=c.id_contrato
            JOIN pacientes p ON c.id_paciente=p.id_paciente
            JOIN nutricionistas n ON s.id_nutricionista_prog=n.id_nutricionista
            JOIN programas pr ON c.id_programa=pr.id_programa
            WHERE s.estado IN ('cancelada','ausente') ORDER BY s.fecha_hora_programada DESC LIMIT 100""")
    else:
        canceladas = run_query("""SELECT s.numero_sesion, s.fecha_hora_programada, s.estado, s.motivo_reprogramacion,
                   p.nombre||' '||p.apellido AS paciente, n.nombre||' '||n.apellido AS nutricionista, pr.nombre AS programa
            FROM sesiones s JOIN contratos c ON s.id_contrato=c.id_contrato
            JOIN pacientes p ON c.id_paciente=p.id_paciente
            JOIN nutricionistas n ON s.id_nutricionista_prog=n.id_nutricionista
            JOIN programas pr ON c.id_programa=pr.id_programa
            WHERE s.estado IN ('cancelada','ausente') AND s.id_nutricionista_prog=%s
            ORDER BY s.fecha_hora_programada DESC LIMIT 100""", (id_nutri,))
    if not canceladas:
        st.info("No hay cancelaciones ni ausencias.")
    else:
        df_c = pd.DataFrame(canceladas)
        df_c["fecha_hora_programada"] = pd.to_datetime(df_c["fecha_hora_programada"]).dt.strftime("%d/%m/%Y %H:%M")
        df_c["estado"] = df_c["estado"].map({"ausente":"🔴 Ausente","cancelada":"⚫ Cancelada"})
        df_c = df_c.rename(columns={"numero_sesion":"N°","fecha_hora_programada":"Fecha","estado":"Estado","motivo_reprogramacion":"Motivo","paciente":"Paciente","nutricionista":"Nutricionista","programa":"Programa"})
        cols_c = ["N°","Paciente","Fecha","Estado","Motivo","Programa"]
        if rol == "administrador": cols_c.append("Nutricionista")
        st.dataframe(df_c[cols_c], use_container_width=True)

# ═══════════════════════════════
# TAB 5 — DISPONIBILIDAD CON CALENDARIO
# ═══════════════════════════════
with tab5:
    if rol == "administrador":
        nutris_d    = run_query("SELECT id_nutricionista, nombre||' '||apellido AS nombre FROM nutricionistas WHERE estado=TRUE ORDER BY apellido")
        nutr_d_opts = {n["nombre"]: n["id_nutricionista"] for n in nutris_d}
        nutr_d_sel  = st.selectbox("Nutricionista", list(nutr_d_opts.keys()), key="disp_nutri")
        id_disp     = nutr_d_opts[nutr_d_sel]
    else:
        id_disp     = id_nutri
        nutr_nombre = run_query("SELECT nombre||' '||apellido AS n FROM nutricionistas WHERE id_nutricionista=%s", (id_nutri,))
        st.markdown(f"Disponibilidad de: **{nutr_nombre[0]['n'] if nutr_nombre else ''}**")

    # Programas del nutricionista para conocer duraciones
    progs_nutri = run_query("""
        SELECT DISTINCT pr.nombre, 
               COALESCE(pr.duracion_sesion_minutos, 60) AS duracion_min
        FROM programa_nutricionistas pn
        JOIN programas pr ON pn.id_programa=pr.id_programa
        WHERE pn.id_nutricionista=%s AND pn.activo=TRUE
        ORDER BY pr.nombre
    """, (id_disp,))

    if progs_nutri:
        st.caption("Duraciones según programas asignados: " + 
                   " · ".join([f"**{p['nombre']}**: {p['duracion_min']} min" for p in progs_nutri]))

    dtab1, dtab2 = st.tabs(["Calendario", "Cargar slots"])

    with dtab1:
        # Cargar slots del mes actual
        import calendar
        mes_actual = hoy.replace(day=1)
        ultimo_dia = calendar.monthrange(hoy.year, hoy.month)[1]
        fin_mes    = hoy.replace(day=ultimo_dia)

        slots_mes = run_query("""
            SELECT d.id_slot, d.fecha_hora_inicio, d.duracion_minutos, d.estado,
                   CASE WHEN d.id_sesion IS NOT NULL THEN p.nombre||' '||p.apellido ELSE NULL END AS paciente
            FROM disponibilidad d
            LEFT JOIN sesiones s  ON d.id_sesion=s.id_sesion
            LEFT JOIN contratos c ON s.id_contrato=c.id_contrato
            LEFT JOIN pacientes p ON c.id_paciente=p.id_paciente
            WHERE d.id_nutricionista=%s
            AND DATE(d.fecha_hora_inicio) BETWEEN %s AND %s
            ORDER BY d.fecha_hora_inicio
        """, (id_disp, mes_actual, fin_mes))

        # Construir datos para el calendario
        slots_json = []
        for s in slots_mes:
            fh  = s["fecha_hora_inicio"]
            dia = int(str(fh)[:10].split("-")[2])
            hora = str(fh)[11:16]
            color = {"disponible":"#1D9E75","reservado":"#185FA5","bloqueado":"#888780"}.get(s["estado"],"#888780")
            slots_json.append({
                "dia": dia, "hora": hora,
                "duracion": s["duracion_minutos"],
                "estado": s["estado"],
                "color": color,
                "paciente": s["paciente"] or "",
                "id": s["id_slot"]
            })

        meses_es = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio",
                    "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
        dias_semana = ["Dom","Lun","Mar","Mié","Jue","Vie","Sáb"]
        primer_dia_semana = calendar.monthrange(hoy.year, hoy.month)[0]  # 0=lunes
        # Ajustar: calendar.monthrange devuelve 0=lunes, queremos 0=domingo
        primer_dia_semana = (primer_dia_semana + 1) % 7

        cal_html = f"""
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: system-ui, sans-serif; background: transparent; }}
  .cal-header {{ display: flex; justify-content: space-between; align-items: center; 
                  padding: 8px 0 12px; }}
  .cal-title {{ font-size: 16px; font-weight: 500; color: #1a1a1a; }}
  .cal-grid {{ display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px; }}
  .cal-dow {{ text-align: center; font-size: 11px; font-weight: 500; 
               color: #888; padding: 4px 0 8px; }}
  .cal-day {{ min-height: 72px; border: 1px solid #e8e6e0; border-radius: 6px;
               padding: 4px; background: #fafaf8; }}
  .cal-day.empty {{ background: transparent; border-color: transparent; }}
  .cal-day.today {{ border-color: #1D9E75; background: #f0faf7; }}
  .cal-day-num {{ font-size: 12px; font-weight: 500; color: #555; margin-bottom: 3px; }}
  .cal-day.today .cal-day-num {{ color: #1D9E75; font-weight: 700; }}
  .slot-pill {{ font-size: 10px; border-radius: 3px; padding: 2px 4px; 
                margin-bottom: 2px; cursor: pointer; white-space: nowrap;
                overflow: hidden; text-overflow: ellipsis; color: white;
                line-height: 1.4; }}
  .slot-pill:hover {{ opacity: 0.85; }}
  .legend {{ display: flex; gap: 12px; margin-top: 10px; flex-wrap: wrap; }}
  .leg-item {{ display: flex; align-items: center; gap: 4px; font-size: 11px; color: #666; }}
  .leg-dot {{ width: 10px; height: 10px; border-radius: 2px; }}
  .tooltip {{ position: fixed; background: #1a1a1a; color: white; padding: 6px 10px;
               border-radius: 6px; font-size: 11px; pointer-events: none;
               display: none; z-index: 999; max-width: 200px; line-height: 1.5; }}
</style>

<div class="cal-header">
  <span class="cal-title">{meses_es[hoy.month]} {hoy.year}</span>
  <span style="font-size:12px;color:#888">{len(slots_mes)} slots este mes</span>
</div>

<div class="cal-grid">
  {''.join([f'<div class="cal-dow">{d}</div>' for d in dias_semana])}
  {''.join([f'<div class="cal-day empty"></div>' for _ in range(primer_dia_semana)])}
  {''.join([
    f'''<div class="cal-day {'today' if d == hoy.day else ''}">
      <div class="cal-day-num">{d}</div>
      {''.join([
        f'<div class="slot-pill" style="background:{s["color"]}"'
        f' onmouseenter="showTip(event,\'{s["hora"]} · {s["duracion"]}min'
        f'{"· " + s["paciente"] if s["paciente"] else ""}\')"'
        f' onmouseleave="hideTip()">'
        f'{s["hora"]}'
        f'{" · " + s["paciente"][:10] if s["paciente"] else ""}'
        f'</div>'
        for s in slots_json if s["dia"] == d
      ])}
    </div>'''
    for d in range(1, ultimo_dia + 1)
  ])}
</div>

<div class="legend">
  <div class="leg-item"><div class="leg-dot" style="background:#1D9E75"></div> Disponible</div>
  <div class="leg-item"><div class="leg-dot" style="background:#185FA5"></div> Reservado</div>
  <div class="leg-item"><div class="leg-dot" style="background:#888780"></div> Bloqueado</div>
</div>

<div class="tooltip" id="tip"></div>
<script>
function showTip(e, text) {{
  const t = document.getElementById('tip');
  t.textContent = text;
  t.style.display = 'block';
  t.style.left = (e.clientX + 10) + 'px';
  t.style.top  = (e.clientY - 30) + 'px';
}}
function hideTip() {{
  document.getElementById('tip').style.display = 'none';
}}
</script>
"""
        # Calcular altura del calendario
        filas = (primer_dia_semana + ultimo_dia + 6) // 7
        cal_height = 40 + 24 + (filas * 80) + 60
        components.html(cal_html, height=cal_height, scrolling=False)

        # Gestión de slots debajo del calendario
        if slots_mes:
            with st.expander("🔧 Cambiar estado de un slot"):
                slots_mod = [s for s in slots_mes if s["estado"] != "reservado"]
                if slots_mod:
                    opts_sl = {f"{str(s['fecha_hora_inicio'])[:16]} ({s['estado']})": s["id_slot"] for s in slots_mod}
                    sel_sl  = st.selectbox("Slot", list(opts_sl.keys()), key="sl_sel")
                    nuevo_e = st.selectbox("Nuevo estado", ["disponible","bloqueado"], key="sl_nuevo")
                    if st.button("Actualizar", key="btn_sl"):
                        run_command("UPDATE disponibilidad SET estado=%s WHERE id_slot=%s", (nuevo_e, opts_sl[sel_sl]))
                        st.success("Actualizado.")
                        st.rerun()

    with dtab2:
        st.subheader("Cargar disponibilidad")

        # Obtener duraciones disponibles para este nutricionista
        durs_disponibles = run_query("""
            SELECT DISTINCT COALESCE(pr.duracion_sesion_minutos, 60) AS duracion_min, pr.nombre
            FROM programa_nutricionistas pn
            JOIN programas pr ON pn.id_programa=pr.id_programa
            WHERE pn.id_nutricionista=%s AND pn.activo=TRUE
            ORDER BY duracion_min
        """, (id_disp,))

        modo = st.radio("Modo", ["Slot individual","Múltiples slots en un día"], horizontal=True, key="modo_slot")

        if modo == "Slot individual":
            col1, col2 = st.columns(2)
            with col1:
                f_slot = st.date_input("Fecha", value=hoy, key="fs_ind")
                h_slot = st.time_input("Hora (entre 9:00 y 18:00)", key="hs_ind")
            with col2:
                if durs_disponibles:
                    dur_opts = {f"{d['duracion_min']} min ({d['nombre']})": d["duracion_min"] for d in durs_disponibles}
                    dur_sel  = st.selectbox("Duración según programa", list(dur_opts.keys()), key="dur_prog")
                    dur_sl   = dur_opts[dur_sel]
                else:
                    dur_sl = st.number_input("Duración (min)", min_value=15, max_value=180, value=60, step=15, key="dur_ind")
                notas_sl = st.text_input("Notas", key="notas_ind")

            if st.button("Agregar slot", use_container_width=True, key="btn_add_ind"):
                fh = datetime.combine(f_slot, h_slot)
                if h_slot.hour < 9 or h_slot.hour >= 18:
                    st.error("El horario debe estar entre las 9:00 y las 18:00.")
                else:
                    try:
                        run_command("INSERT INTO disponibilidad (id_nutricionista,fecha_hora_inicio,duracion_minutos,estado,notas) VALUES (%s,%s,%s,'disponible',%s)",
                                    (id_disp, fh, dur_sl, notas_sl or None))
                        st.success(f"Slot agregado: {fh.strftime('%d/%m/%Y %H:%M')} ({dur_sl} min)")
                        st.rerun()
                    except Exception as e:
                        st.error("Ya existe un slot en ese horario." if "unique" in str(e).lower() else str(e))
        else:
            col1, col2 = st.columns(2)
            with col1:
                f_multi = st.date_input("Fecha", value=hoy, key="f_multi")
                h_ini   = st.time_input("Hora inicio", value=datetime.strptime("09:00","%H:%M").time(), key="h_ini")
            with col2:
                h_fin_  = st.time_input("Hora fin (máx. 18:00)", value=datetime.strptime("17:00","%H:%M").time(), key="h_fin")
                if durs_disponibles:
                    dur_opts_m = {f"{d['duracion_min']} min ({d['nombre']})": d["duracion_min"] for d in durs_disponibles}
                    dur_sel_m  = st.selectbox("Duración según programa", list(dur_opts_m.keys()), key="dur_prog_m")
                    dur_m      = dur_opts_m[dur_sel_m]
                else:
                    dur_m = st.number_input("Duración por slot (min)", min_value=15, max_value=180, value=60, step=15, key="dur_m")

            slots_prev = []
            if h_fin_ > h_ini:
                actual = datetime.combine(f_multi, h_ini)
                fin_dt = datetime.combine(f_multi, min(h_fin_, datetime.strptime("18:00","%H:%M").time()))
                while actual + timedelta(minutes=dur_m) <= fin_dt:
                    if actual.hour >= 9:
                        slots_prev.append(actual)
                    actual += timedelta(minutes=dur_m)

            if slots_prev:
                st.caption(f"Se generarán {len(slots_prev)} slots de {dur_m} min: " + " · ".join(s.strftime("%H:%M") for s in slots_prev))

            if st.button(f"Cargar {len(slots_prev)} slots", use_container_width=True, key="btn_add_multi", disabled=len(slots_prev)==0):
                ok = err = 0
                for sdt in slots_prev:
                    try:
                        run_command("INSERT INTO disponibilidad (id_nutricionista,fecha_hora_inicio,duracion_minutos,estado) VALUES (%s,%s,%s,'disponible')",
                                    (id_disp, sdt, dur_m))
                        ok += 1
                    except: err += 1
                st.success(f"✅ {ok} slots de {dur_m} min cargados." + (f" {err} omitidos (ya existían)." if err else ""))
                st.rerun()

# ═══════════════════════════════
# TAB 6 — PERMISOS (solo admin)
# ═══════════════════════════════
if rol == "administrador" and tab6 is not None:
    with tab6:
        st.subheader("Permisos y reasignaciones")
        st.markdown("---")
        ptab1, ptab2 = st.tabs(["Solicitudes pendientes", "Reasignar paciente"])
        with ptab1:
            solicitudes = run_query("""
                SELECT pa.id_permiso, p.nombre||' '||p.apellido AS paciente, p.email,
                       nb.nombre||' '||nb.apellido AS nutricionista_solicitante,
                       na.nombre||' '||na.apellido AS nutricionista_actual,
                       pr.nombre AS programa, pa.estado, pa.fecha_solicitud, pa.motivo
                FROM permisos_acceso pa
                JOIN pacientes p       ON pa.id_paciente=p.id_paciente
                JOIN nutricionistas nb ON pa.id_nutricionista=nb.id_nutricionista
                JOIN contratos c       ON p.id_paciente=c.id_paciente AND c.estado='activo'
                JOIN programas pr      ON c.id_programa=pr.id_programa
                JOIN nutricionistas na ON c.id_nutricionista=na.id_nutricionista
                ORDER BY pa.estado, pa.fecha_solicitud DESC
            """)
            if not solicitudes:
                st.info("No hay solicitudes de acceso.")
            else:
                for s in solicitudes:
                    badge = {"pendiente":"🟡","aprobado":"🟢","rechazado":"🔴"}.get(s["estado"],"⚪")
                    with st.container(border=True):
                        col1, col2, col3 = st.columns([3,2,2])
                        with col1:
                            st.markdown(f"{badge} **{s['nutricionista_solicitante']}** solicita acceso a **{s['paciente']}**")
                            st.caption(f"Programa: {s['programa']} · Actual: {s['nutricionista_actual']}")
                            if s["motivo"]: st.caption(f"Motivo: {s['motivo']}")
                        with col2:
                            st.markdown(f"Estado: **{s['estado']}**")
                            st.caption(f"Solicitado: {str(s['fecha_solicitud'])[:10]}")
                        with col3:
                            if s["estado"] == "pendiente":
                                tipo = st.selectbox("Tipo", ["Temporal","Permanente"], key=f"tipo_{s['id_permiso']}")
                                if tipo == "Temporal":
                                    ses_acc = st.selectbox("Sesiones", list(range(1,21)), index=3, key=f"ses_{s['id_permiso']}")
                                    f_exp   = date.today() + timedelta(weeks=int(ses_acc)*2)
                                    st.caption(f"~{f_exp.strftime('%d/%m/%Y')}")
                                else:
                                    f_exp = None
                                ca, cb = st.columns(2)
                                with ca:
                                    if st.button("Aprobar", key=f"apr_{s['id_permiso']}", use_container_width=True):
                                        if tipo == "Permanente":
                                            run_command("UPDATE contratos SET id_nutricionista=pa.id_nutricionista FROM permisos_acceso pa WHERE contratos.id_paciente=pa.id_paciente AND pa.id_permiso=%s AND contratos.estado='activo'", (s["id_permiso"],))
                                            run_command("UPDATE sesiones SET id_nutricionista_prog=pa.id_nutricionista FROM permisos_acceso pa JOIN contratos c ON c.id_paciente=pa.id_paciente WHERE sesiones.id_contrato=c.id_contrato AND pa.id_permiso=%s AND sesiones.estado='programada'", (s["id_permiso"],))
                                            run_command("UPDATE permisos_acceso SET estado='aprobado', fecha_expiracion=NULL WHERE id_permiso=%s", (s["id_permiso"],))
                                        else:
                                            run_command("UPDATE permisos_acceso SET estado='aprobado', fecha_expiracion=%s WHERE id_permiso=%s", (f_exp, s["id_permiso"]))
                                        st.success("Aprobado.")
                                        st.rerun()
                                with cb:
                                    if st.button("❌", key=f"rec_{s['id_permiso']}", use_container_width=True):
                                        run_command("UPDATE permisos_acceso SET estado='rechazado' WHERE id_permiso=%s", (s["id_permiso"],))
                                        st.rerun()
        with ptab2:
            pacientes_activos = run_query("""SELECT p.id_paciente, p.nombre||' '||p.apellido AS nombre, n.nombre||' '||n.apellido AS nutricionista_actual, pr.nombre AS programa, c.id_contrato
                FROM pacientes p JOIN contratos c ON p.id_paciente=c.id_paciente AND c.estado='activo'
                JOIN nutricionistas n ON c.id_nutricionista=n.id_nutricionista
                JOIN programas pr ON c.id_programa=pr.id_programa ORDER BY p.apellido""")
            nutris_list = run_query("SELECT id_nutricionista, nombre||' '||apellido AS nombre FROM nutricionistas WHERE estado=TRUE ORDER BY apellido")
            if pacientes_activos and nutris_list:
                pac_opts  = {f"{p['nombre']} ({p['nutricionista_actual']})": p for p in pacientes_activos}
                nutr_opts = {n["nombre"]: n["id_nutricionista"] for n in nutris_list}
                pac_sel   = st.selectbox("Paciente", list(pac_opts.keys()), key="reas_pac")
                nutr_sel  = st.selectbox("Nueva nutricionista", list(nutr_opts.keys()), key="reas_nutr")
                pac_data  = pac_opts[pac_sel]
                tipo_reas = st.radio("Tipo", ["Permanente","Temporal"], horizontal=True, key="tipo_reas")
                f_exp_reas = None
                if tipo_reas == "Temporal":
                    ses_reas   = st.selectbox("Sesiones de acceso", list(range(1,21)), index=3, key="ses_reas")
                    f_exp_reas = date.today() + timedelta(weeks=int(ses_reas)*2)
                    st.caption(f"Expira ~{f_exp_reas.strftime('%d/%m/%Y')}")
                if st.button("Reasignar", use_container_width=True, type="primary", key="btn_reas"):
                    nueva_id = nutr_opts[nutr_sel]
                    if tipo_reas == "Permanente":
                        run_command("UPDATE contratos SET id_nutricionista=%s WHERE id_contrato=%s", (nueva_id, pac_data["id_contrato"]))
                        run_command("UPDATE sesiones SET id_nutricionista_prog=%s WHERE id_contrato=%s AND estado='programada'", (nueva_id, pac_data["id_contrato"]))
                        st.success(f"Reasignado permanentemente.")
                    else:
                        run_command("INSERT INTO permisos_acceso (id_nutricionista,id_paciente,estado,solicitado_por,fecha_solicitud,fecha_expiracion) VALUES (%s,%s,'aprobado',%s,CURRENT_DATE,%s) ON CONFLICT (id_nutricionista,id_paciente) DO UPDATE SET estado='aprobado', fecha_expiracion=%s",
                                    (nueva_id, pac_data["id_paciente"], nueva_id, f_exp_reas, f_exp_reas))
                        st.success(f"Acceso temporal otorgado.")
                    st.rerun()

# ═══════════════════════════════
# TAB CONFIRMAR TURNOS (solo nutricionista)
# ═══════════════════════════════
if rol == "nutricionista":
    with tab_conf:
        st.subheader("Turnos pendientes de confirmación")
        st.caption("Revisá los turnos que eligieron tus pacientes y confirmalos o proponé otro horario.")
        turnos_pend_list = run_query("""
            SELECT s.id_sesion, s.fecha_hora_programada, s.modalidad, s.estado_confirmacion,
                   p.nombre||' '||p.apellido AS paciente, p.email, pr.nombre AS programa,
                   COALESCE(pr.duracion_sesion_minutos, 60) AS duracion_min
            FROM sesiones s
            JOIN contratos c  ON s.id_contrato=c.id_contrato
            JOIN pacientes p  ON c.id_paciente=p.id_paciente
            JOIN programas pr ON c.id_programa=pr.id_programa
            WHERE s.id_nutricionista_prog=%s AND s.numero_sesion=1
            AND s.estado_confirmacion IN ('pendiente','modificada')
            ORDER BY s.fecha_hora_programada
        """, (id_nutri,))

        # Solicitudes de reprogramación del paciente
        sols_repr = run_query("""
            SELECT sr.id_solicitud, sr.id_sesion, sr.id_paciente,
                   p.nombre||' '||p.apellido AS paciente,
                   s.fecha_hora_programada, s.numero_sesion,
                   pr.nombre AS programa
            FROM solicitudes_reprogramacion sr
            JOIN pacientes p  ON sr.id_paciente=p.id_paciente
            JOIN sesiones s   ON sr.id_sesion=s.id_sesion
            JOIN contratos c  ON s.id_contrato=c.id_contrato
            JOIN programas pr ON c.id_programa=pr.id_programa
            WHERE s.id_nutricionista_prog=%s
            AND sr.estado='pendiente'
            AND sr.propuesta_por='paciente'
            AND sr.opcion_1 IS NULL
            ORDER BY sr.id_solicitud DESC
        """, (id_nutri,))

        if sols_repr:
            st.markdown("**Solicitudes de reprogramación de pacientes:**")
            for sr in sols_repr:
                with st.container(border=True):
                    col1, col2 = st.columns([2,3])
                    with col1:
                        st.markdown(f"**{sr['paciente']}**")
                        st.caption(f"{sr['programa']} · Sesión #{sr['numero_sesion']}")
                        st.caption(f"Turno actual: {str(sr['fecha_hora_programada'])[:16]}")
                    with col2:
                        st.markdown("Proponé hasta 3 opciones de horario:")
                        op1 = st.date_input("Opción 1 fecha", key=f"op1d_{sr['id_solicitud']}", value=hoy)
                        h1  = st.time_input("Opción 1 hora", key=f"op1h_{sr['id_solicitud']}")
                        op2 = st.date_input("Opción 2 fecha (opcional)", key=f"op2d_{sr['id_solicitud']}", value=hoy)
                        h2  = st.time_input("Opción 2 hora", key=f"op2h_{sr['id_solicitud']}")
                        if st.button("Enviar opciones", key=f"env_{sr['id_solicitud']}", use_container_width=True):
                            fh1 = datetime.combine(op1, h1)
                            fh2 = datetime.combine(op2, h2) if op2 != op1 else None
                            run_command("""
                                UPDATE solicitudes_reprogramacion
                                SET opcion_1=%s, opcion_2=%s, propuesta_por='nutricionista'
                                WHERE id_solicitud=%s
                            """, (fh1, fh2, sr["id_solicitud"]))
                            st.success("Opciones enviadas al paciente.")
                            st.rerun()
            st.markdown("---")

        if not turnos_pend_list:
            st.success("No hay turnos pendientes de confirmación.")
        else:
            for t in turnos_pend_list:
                badge = "🟡 pendiente" if t["estado_confirmacion"] == "pendiente" else "🔵 modificado"
                with st.container(border=True):
                    col1, col2, col3 = st.columns([3,2,2])
                    with col1:
                        st.markdown(f"**{t['paciente']}**")
                        st.caption(f"{t['programa']} · {t['modalidad']} · {t['duracion_min']} min")
                        st.caption(t['email'])
                        st.markdown(f"Turno: **{str(t['fecha_hora_programada'])[:16]}**")
                        st.caption(f"Estado: {badge}")
                    with col2:
                        if st.button("Confirmar", key=f"conf_{t['id_sesion']}", use_container_width=True, type="primary"):
                            run_command("UPDATE sesiones SET estado_confirmacion='confirmada' WHERE id_sesion=%s", (t["id_sesion"],))
                            st.success("Turno confirmado.")
                            st.rerun()
                    with col3:
                        with st.expander("Proponer otro horario"):
                            nueva_f = st.date_input("Nueva fecha", value=hoy, key=f"nf_{t['id_sesion']}")
                            nueva_h = st.time_input("Nueva hora (9-18hs)", key=f"nh_{t['id_sesion']}")
                            if st.button("Proponer", key=f"prop_{t['id_sesion']}", use_container_width=True):
                                if nueva_h.hour < 9 or nueva_h.hour >= 18:
                                    st.error("El horario debe estar entre las 9:00 y las 18:00.")
                                else:
                                    nueva_fh = datetime.combine(nueva_f, nueva_h)
                                    run_command("UPDATE sesiones SET fecha_hora_programada=%s, estado_confirmacion='modificada' WHERE id_sesion=%s", (nueva_fh, t["id_sesion"]))
                                    st.success(f"Nuevo horario propuesto: {nueva_fh.strftime('%d/%m/%Y %H:%M')}")
                                    st.rerun()