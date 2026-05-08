from datetime import date, datetime, timedelta, time
import calendar
import re
import requests

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from database import run_query, run_command
from utils import mostrar_sidebar, page_header


HORA_INICIO = time(9, 0)
HORA_FIN = time(18, 0)
PASO_MIN = 15
PAIS_FERIADOS = "PE"

GOOGLE_HOLIDAYS_ICS = (
    "https://calendar.google.com/calendar/ical/"
    "es.pe%23holiday%40group.v.calendar.google.com/public/basic.ics"
)

COLOR_DISPONIBLE = "#00DC8E"
COLOR_RESERVADO = "#8C52FF"
COLOR_BLOQUEADO = "#808080"
COLOR_NO_LABORABLE = "#E5E7EB"


if "usuario" not in st.session_state:
    st.warning("Debés iniciar sesión.")
    st.stop()

if st.session_state["usuario"]["rol"] not in ("administrador", "nutricionista"):
    st.error("No tenés permisos.")
    st.stop()

usuario = st.session_state["usuario"]
rol = usuario["rol"]
id_nutri = usuario.get("id_nutricionista")
id_usuario = usuario.get("id_usuario") or id_nutri

mostrar_sidebar()
page_header("Agenda")

hoy = date.today()


def fmt_fecha(valor):
    if not valor:
        return "—"
    try:
        return pd.to_datetime(valor).strftime("%d/%m/%Y")
    except Exception:
        return str(valor)[:10]


def fmt_fecha_hora(valor):
    if not valor:
        return "—"
    try:
        return pd.to_datetime(valor).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(valor)[:16]


def safe_int(valor, default=0):
    try:
        return int(valor or default)
    except Exception:
        return default


def generar_horas_inicio():
    horas = []
    actual = datetime.combine(date.today(), HORA_INICIO)
    fin_dt = datetime.combine(date.today(), HORA_FIN)

    while actual < fin_dt:
        horas.append(actual.time())
        actual += timedelta(minutes=PASO_MIN)

    return horas


def generar_horas_fin():
    horas = []
    actual = datetime.combine(date.today(), HORA_INICIO) + timedelta(minutes=PASO_MIN)
    fin_dt = datetime.combine(date.today(), HORA_FIN)

    while actual <= fin_dt:
        horas.append(actual.time())
        actual += timedelta(minutes=PASO_MIN)

    return horas


def hora_label(h):
    return h.strftime("%H:%M")


def es_horario_laboral(dt):
    return dt.weekday() < 5 and HORA_INICIO <= dt.time() < HORA_FIN


@st.cache_data(ttl=60 * 60 * 12)
def obtener_feriados_google(year):
    try:
        resp = requests.get(GOOGLE_HOLIDAYS_ICS, timeout=8)
        resp.raise_for_status()
        txt = resp.text

        eventos = {}
        bloques = txt.split("BEGIN:VEVENT")

        for b in bloques:
            if "DTSTART" not in b:
                continue

            m_fecha = re.search(r"DTSTART(?:;VALUE=DATE)?:([0-9]{8})", b)
            m_sum = re.search(r"SUMMARY:(.+)", b)

            if not m_fecha:
                continue

            f = datetime.strptime(m_fecha.group(1), "%Y%m%d").date()

            if f.year != year:
                continue

            nombre = m_sum.group(1).strip() if m_sum else "Feriado"
            nombre = nombre.replace("\\,", ",").replace("\\;", ";")
            eventos[f] = nombre

        return eventos
    except Exception:
        return {}


def obtener_no_laborables_manual(year):
    try:
        rows = run_query(
            """
            SELECT fecha, nombre, tipo
            FROM calendario_no_laborable
            WHERE activo = TRUE
              AND pais = %s
              AND EXTRACT(YEAR FROM fecha) = %s
            ORDER BY fecha
            """,
            (PAIS_FERIADOS, year),
        )

        return {
            pd.to_datetime(r["fecha"]).date(): {
                "nombre": r["nombre"],
                "tipo": r.get("tipo") or "manual",
            }
            for r in rows
        }
    except Exception:
        return {}


def obtener_no_laborables(year):
    google = obtener_feriados_google(year)
    manuales = obtener_no_laborables_manual(year)

    data = {}

    for f, nombre in google.items():
        data[f] = {"nombre": nombre, "tipo": "google_calendar"}

    for f, d in manuales.items():
        data[f] = d

    return data


def es_no_laborable(fecha, no_laborables):
    return fecha.weekday() >= 5 or fecha in no_laborables


def nombre_no_laborable(fecha, no_laborables):
    if fecha.weekday() == 5:
        return "Sábado"
    if fecha.weekday() == 6:
        return "Domingo"
    if fecha in no_laborables:
        return no_laborables[fecha]["nombre"]
    return ""


def obtener_nutricionistas():
    return run_query(
        """
        SELECT id_nutricionista,
               nombre || ' ' || apellido AS nombre
        FROM nutricionistas
        WHERE estado = TRUE
        ORDER BY apellido, nombre
        """
    )


def selector_nutricionista(key="nutri_sel", label="Nutricionista"):
    if rol == "administrador":
        nutris = obtener_nutricionistas()

        if not nutris:
            st.info("No hay nutricionistas activos.")
            st.stop()

        opts = {n["nombre"]: n["id_nutricionista"] for n in nutris}
        sel = st.selectbox(label, list(opts.keys()), key=key)
        return opts[sel], sel

    nombre = run_query(
        """
        SELECT nombre || ' ' || apellido AS nombre
        FROM nutricionistas
        WHERE id_nutricionista = %s
        """,
        (id_nutri,),
    )

    nombre_txt = nombre[0]["nombre"] if nombre else "Nutricionista"
    st.markdown(f"**{label}:** {nombre_txt}")
    return id_nutri, nombre_txt


def obtener_sesiones(fecha_desde, fecha_hasta, estado="todos", id_nutricionista=None):
    q = """
        SELECT s.id_sesion,
               s.id_contrato,
               s.numero_sesion,
               s.fecha_hora_original,
               s.fecha_hora_programada,
               s.fecha_hora_atencion,
               s.modalidad,
               s.estado,
               s.estado_confirmacion,
               s.contador_reprogramaciones,
               p.nombre || ' ' || p.apellido AS paciente,
               n.nombre || ' ' || n.apellido AS nutricionista,
               pr.nombre AS programa
        FROM sesiones s
        JOIN contratos c ON s.id_contrato = c.id_contrato
        JOIN pacientes p ON c.id_paciente = p.id_paciente
        JOIN nutricionistas n ON s.id_nutricionista_prog = n.id_nutricionista
        JOIN programas pr ON c.id_programa = pr.id_programa
        WHERE DATE(s.fecha_hora_programada) BETWEEN %s AND %s
    """

    params = [fecha_desde, fecha_hasta]

    if estado != "todos":
        q += " AND s.estado = %s"
        params.append(estado)

    if id_nutricionista:
        q += " AND s.id_nutricionista_prog = %s"
        params.append(id_nutricionista)

    q += " ORDER BY s.fecha_hora_programada"

    return run_query(q, params)


def obtener_slots(fecha_desde, fecha_hasta, id_nutricionista):
    return run_query(
        """
        SELECT d.id_slot,
               d.fecha_hora_inicio,
               d.duracion_minutos,
               d.estado,
               d.id_sesion,
               d.notas,
               CASE
                    WHEN d.id_sesion IS NOT NULL THEN p.nombre || ' ' || p.apellido
                    ELSE NULL
               END AS paciente
        FROM disponibilidad d
        LEFT JOIN sesiones s ON d.id_sesion = s.id_sesion
        LEFT JOIN contratos c ON s.id_contrato = c.id_contrato
        LEFT JOIN pacientes p ON c.id_paciente = p.id_paciente
        WHERE d.id_nutricionista = %s
          AND DATE(d.fecha_hora_inicio) BETWEEN %s AND %s
        ORDER BY d.fecha_hora_inicio
        """,
        (id_nutricionista, fecha_desde, fecha_hasta),
    )


def obtener_slot_exacto(id_nutricionista, fecha_hora):
    rows = run_query(
        """
        SELECT id_slot, estado, id_sesion
        FROM disponibilidad
        WHERE id_nutricionista = %s
          AND fecha_hora_inicio = %s
        LIMIT 1
        """,
        (id_nutricionista, fecha_hora),
    )

    return rows[0] if rows else None


def upsert_disponibilidad(
    id_nutricionista,
    fecha_hora,
    duracion,
    estado,
    notas=None,
    id_sesion=None,
):
    run_command(
        """
        INSERT INTO disponibilidad
            (id_nutricionista, fecha_hora_inicio, duracion_minutos, estado, notas, id_sesion)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (id_nutricionista, fecha_hora_inicio)
        DO UPDATE SET
            duracion_minutos = EXCLUDED.duracion_minutos,
            estado = EXCLUDED.estado,
            notas = EXCLUDED.notas,
            id_sesion = EXCLUDED.id_sesion
        """,
        (id_nutricionista, fecha_hora, duracion, estado, notas, id_sesion),
    )


def limpiar_reserva_disponibilidad(id_sesion):
    run_command(
        """
        DELETE FROM disponibilidad
        WHERE id_sesion = %s
        """,
        (id_sesion,),
    )


def obtener_pacientes_para_reserva(id_nutricionista):
    return run_query(
        """
        SELECT DISTINCT
               p.id_paciente,
               p.nombre || ' ' || p.apellido AS paciente,
               c.id_contrato,
               pr.nombre AS programa
        FROM pacientes p
        JOIN contratos c ON p.id_paciente = c.id_paciente
        JOIN programas pr ON c.id_programa = pr.id_programa
        WHERE c.estado = 'activo'
          AND c.id_nutricionista = %s
        ORDER BY paciente
        """,
        (id_nutricionista,),
    )


def obtener_sesiones_pendientes_contrato(id_contrato):
    return run_query(
        """
        SELECT id_sesion,
               numero_sesion,
               fecha_hora_programada,
               estado,
               estado_confirmacion
        FROM sesiones
        WHERE id_contrato = %s
          AND estado = 'programada'
        ORDER BY numero_sesion, fecha_hora_programada
        """,
        (id_contrato,),
    )


def reservar_sesion(
    id_nutricionista,
    id_sesion,
    fecha_hora,
    modalidad,
    duracion_minutos=30,
    notas=None,
):
    run_command(
        """
        UPDATE sesiones
        SET fecha_hora_programada = %s,
            fecha_hora_original = COALESCE(fecha_hora_original, %s),
            id_nutricionista_prog = %s,
            modalidad = %s,
            estado = 'programada',
            estado_confirmacion = 'pendiente'
        WHERE id_sesion = %s
        """,
        (fecha_hora, fecha_hora, id_nutricionista, modalidad, id_sesion),
    )

    limpiar_reserva_disponibilidad(id_sesion)

    upsert_disponibilidad(
        id_nutricionista=id_nutricionista,
        fecha_hora=fecha_hora,
        duracion=duracion_minutos,
        estado="reservado",
        notas=notas or "Turno reservado",
        id_sesion=id_sesion,
    )


def registrar_reprogramacion_desde_agenda(
    id_sesion,
    nueva_fecha_hora,
    modalidad_nueva,
    motivo,
    reprogramada_por="nutricionista",
):
    rows = run_query(
        """
        SELECT s.id_sesion,
               s.id_contrato,
               s.numero_sesion,
               s.fecha_hora_programada,
               s.modalidad,
               s.id_nutricionista_prog,
               COALESCE(MAX(sh.subnumero), 0) + 1 AS prox_subnumero
        FROM sesiones s
        LEFT JOIN sesiones_historial sh ON sh.id_sesion = s.id_sesion
        WHERE s.id_sesion = %s
        GROUP BY s.id_sesion, s.id_contrato, s.numero_sesion,
                 s.fecha_hora_programada, s.modalidad, s.id_nutricionista_prog
        """,
        (id_sesion,),
    )

    if not rows:
        raise ValueError("Sesión no encontrada.")

    s = rows[0]

    run_command(
        """
        INSERT INTO sesiones_historial
            (id_sesion, id_contrato, numero_sesion, subnumero,
             fecha_hora_anterior, fecha_hora_nueva,
             modalidad_anterior, modalidad_nueva,
             motivo, reprogramada_por, creado_por)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            id_sesion,
            s["id_contrato"],
            s["numero_sesion"],
            s["prox_subnumero"],
            s["fecha_hora_programada"],
            nueva_fecha_hora,
            s["modalidad"],
            modalidad_nueva,
            motivo,
            reprogramada_por,
            id_usuario,
        ),
    )

    run_command(
        """
        UPDATE sesiones
        SET fecha_hora_programada = %s,
            modalidad = %s,
            estado = 'programada',
            estado_confirmacion = 'modificada',
            contador_reprogramaciones = contador_reprogramaciones + 1,
            motivo_reprogramacion = %s,
            reprogramada_por = %s
        WHERE id_sesion = %s
        """,
        (
            nueva_fecha_hora,
            modalidad_nueva,
            motivo,
            reprogramada_por,
            id_sesion,
        ),
    )

    run_command(
        """
        UPDATE contratos
        SET reprogramaciones_usadas = reprogramaciones_usadas + 1,
            fecha_ultima_reprogramacion = %s
        WHERE id_contrato = %s
        """,
        (nueva_fecha_hora.date(), s["id_contrato"]),
    )

    limpiar_reserva_disponibilidad(id_sesion)

    upsert_disponibilidad(
        id_nutricionista=s["id_nutricionista_prog"],
        fecha_hora=nueva_fecha_hora,
        duracion=PASO_MIN,
        estado="reservado",
        notas=motivo or "Turno reprogramado",
        id_sesion=id_sesion,
    )


def avanzar_mes(fecha_ref, delta):
    mes = fecha_ref.month + delta
    year = fecha_ref.year

    if mes < 1:
        mes = 12
        year -= 1
    elif mes > 12:
        mes = 1
        year += 1

    return date(year, mes, 1)


def render_calendario_mes(id_nutricionista, fecha_ref):
    no_laborables = obtener_no_laborables(fecha_ref.year)

    primer_dia = fecha_ref.replace(day=1)
    ultimo_num = calendar.monthrange(fecha_ref.year, fecha_ref.month)[1]
    ultimo_dia = fecha_ref.replace(day=ultimo_num)

    slots = obtener_slots(primer_dia, ultimo_dia, id_nutricionista)

    slots_por_dia = {}

    for s in slots:
        f = pd.to_datetime(s["fecha_hora_inicio"]).date()
        slots_por_dia.setdefault(f, []).append(s)

    meses = [
        "",
        "Enero",
        "Febrero",
        "Marzo",
        "Abril",
        "Mayo",
        "Junio",
        "Julio",
        "Agosto",
        "Septiembre",
        "Octubre",
        "Noviembre",
        "Diciembre",
    ]
    dias_semana = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

    primer_weekday = primer_dia.weekday()
    cells = []

    for _ in range(primer_weekday):
        cells.append('<div class="cal-day empty"></div>')

    for d in range(1, ultimo_num + 1):
        f = date(fecha_ref.year, fecha_ref.month, d)
        no_lab = es_no_laborable(f, no_laborables)
        motivo = nombre_no_laborable(f, no_laborables)

        clase = "blocked" if no_lab else ""

        if f == hoy:
            clase += " today"

        pills = ""

        if no_lab:
            pills += f'<div class="holiday-label">{motivo}</div>'

        for s in slots_por_dia.get(f, [])[:5]:
            estado = s["estado"]
            color = {
                "disponible": COLOR_DISPONIBLE,
                "reservado": COLOR_RESERVADO,
                "bloqueado": COLOR_BLOQUEADO,
            }.get(estado, COLOR_BLOQUEADO)

            hora = pd.to_datetime(s["fecha_hora_inicio"]).strftime("%H:%M")
            paciente = s.get("paciente") or ""
            nota = s.get("notas") or ""

            texto = f"{hora}"

            if paciente:
                texto += f" · {paciente[:12]}"
            elif nota:
                texto += f" · {nota[:12]}"

            pills += f"""
            <div class="slot-pill" style="background:{color};" title="{hora} · {estado}">
                {texto}
            </div>
            """

        cells.append(
            f"""
            <div class="cal-day {clase}">
                <div class="cal-day-num">{d}</div>
                {pills}
            </div>
            """
        )

    html = f"""
    <style>
    * {{
        box-sizing: border-box;
    }}
    body {{
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: transparent;
    }}
    .cal-title {{
        font-size: 18px;
        font-weight: 700;
        color: #111827;
        margin-bottom: 16px;
    }}
    .cal-grid {{
        display: grid;
        grid-template-columns: repeat(7, 1fr);
        gap: 6px;
    }}
    .dow {{
        text-align: center;
        color: #808080;
        font-size: 12px;
        font-weight: 700;
        padding: 4px 0 8px;
    }}
    .cal-day {{
        min-height: 92px;
        border: 1px solid #00DC8E;
        border-radius: 10px;
        background: #D8FFF3;
        padding: 7px;
        overflow: hidden;
    }}
    .cal-day.empty {{
        background: transparent;
        border: none;
    }}
    .cal-day.blocked {{
        background: #f3f4f6;
        border-color: #d1d5db;
    }}
    .cal-day.today {{
        border: 2px solid #00DC8E;
    }}
    .cal-day-num {{
        font-size: 12px;
        font-weight: 700;
        color: #111827;
        margin-bottom: 5px;
    }}
    .holiday-label {{
        font-size: 10px;
        color: #808080;
        margin-bottom: 4px;
        line-height: 1.2;
    }}
    .slot-pill {{
        color: white;
        font-size: 10px;
        padding: 3px 5px;
        border-radius: 6px;
        margin-bottom: 3px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }}
    .legend {{
        display: flex;
        gap: 18px;
        margin-top: 14px;
        flex-wrap: wrap;
        font-size: 12px;
        color: #555;
    }}
    .leg {{
        display: flex;
        align-items: center;
        gap: 6px;
    }}
    .dot {{
        width: 12px;
        height: 12px;
        border-radius: 3px;
    }}
    </style>

    <div class="cal-title">{meses[fecha_ref.month]} {fecha_ref.year}</div>

    <div class="cal-grid">
        {''.join([f'<div class="dow">{d}</div>' for d in dias_semana])}
        {''.join(cells)}
    </div>

    <div class="legend">
        <div class="leg"><span class="dot" style="background:{COLOR_DISPONIBLE}"></span> Disponible</div>
        <div class="leg"><span class="dot" style="background:{COLOR_RESERVADO}"></span> Reservado</div>
        <div class="leg"><span class="dot" style="background:{COLOR_BLOQUEADO}"></span> Bloqueado</div>
        <div class="leg"><span class="dot" style="background:{COLOR_NO_LABORABLE}; border:1px solid #d1d5db;"></span> No laborable</div>
    </div>
    """

    filas = (primer_weekday + ultimo_num + 6) // 7
    height = 70 + filas * 104 + 60
    components.html(html, height=height, scrolling=False)


def render_detalle_dia(id_nutricionista, fecha_sel):
    no_laborables = obtener_no_laborables(fecha_sel.year)
    slots = obtener_slots(fecha_sel, fecha_sel, id_nutricionista)

    slots_por_hora = {
        pd.to_datetime(s["fecha_hora_inicio"]).strftime("%H:%M"): s
        for s in slots
    }

    st.markdown(f"**Detalle del día: {fecha_sel.strftime('%d/%m/%Y')}**")

    if es_no_laborable(fecha_sel, no_laborables):
        st.info(f"Día no laborable: {nombre_no_laborable(fecha_sel, no_laborables)}")
        return

    filas = []

    for h in generar_horas_inicio():
        h_txt = h.strftime("%H:%M")
        slot = slots_por_hora.get(h_txt)

        if slot:
            estado = slot["estado"]
            paciente = slot.get("paciente")
            notas = slot.get("notas")

            if estado == "reservado":
                detalle = f"Reservado - {paciente or notas or 'sin paciente'}"
            elif estado == "bloqueado":
                detalle = f"Bloqueado - {notas or 'sin nota'}"
            else:
                detalle = "Disponible"

            filas.append(
                {
                    "Hora": h_txt,
                    "Estado": estado.capitalize(),
                    "Detalle": detalle,
                }
            )
        else:
            filas.append(
                {
                    "Hora": h_txt,
                    "Estado": "Disponible",
                    "Detalle": "Disponible",
                }
            )

    st.dataframe(
        pd.DataFrame(filas),
        use_container_width=True,
        hide_index=True,
        height=360,
    )


if rol == "administrador":
    m1 = run_query(
        "SELECT COUNT(*) AS n FROM sesiones WHERE DATE(fecha_hora_programada)=%s AND estado='programada'",
        (hoy,),
    )
    m2 = run_query(
        "SELECT COUNT(*) AS n FROM sesiones WHERE DATE(fecha_hora_programada)=%s AND estado='atendida'",
        (hoy,),
    )
    m3 = run_query(
        """
        SELECT COUNT(*) AS n
        FROM sesiones
        WHERE DATE(fecha_hora_programada) BETWEEN %s AND %s
          AND estado='programada'
        """,
        (hoy, hoy + timedelta(days=7)),
    )
    m4 = run_query(
        "SELECT COUNT(DISTINCT id_nutricionista_prog) AS n FROM sesiones WHERE DATE(fecha_hora_programada)=%s",
        (hoy,),
    )
else:
    m1 = run_query(
        """
        SELECT COUNT(*) AS n
        FROM sesiones
        WHERE DATE(fecha_hora_programada)=%s
          AND estado='programada'
          AND id_nutricionista_prog=%s
        """,
        (hoy, id_nutri),
    )
    m2 = run_query(
        """
        SELECT COUNT(*) AS n
        FROM sesiones
        WHERE DATE(fecha_hora_programada)=%s
          AND estado='atendida'
          AND id_nutricionista_prog=%s
        """,
        (hoy, id_nutri),
    )
    m3 = run_query(
        """
        SELECT COUNT(*) AS n
        FROM sesiones
        WHERE DATE(fecha_hora_programada) BETWEEN %s AND %s
          AND estado='programada'
          AND id_nutricionista_prog=%s
        """,
        (hoy, hoy + timedelta(days=7), id_nutri),
    )
    m4 = run_query(
        """
        SELECT COUNT(*) AS n
        FROM sesiones
        WHERE DATE(fecha_hora_programada)=%s
          AND estado='ausente'
          AND id_nutricionista_prog=%s
        """,
        (hoy, id_nutri),
    )

col1, col2, col3, col4 = st.columns(4)
col1.metric("Pendientes hoy", safe_int(m1[0]["n"] if m1 else 0))
col2.metric("Realizadas hoy", safe_int(m2[0]["n"] if m2 else 0))
col3.metric("Esta semana", safe_int(m3[0]["n"] if m3 else 0))
col4.metric(
    "Nutricionistas hoy" if rol == "administrador" else "Ausentes hoy",
    safe_int(m4[0]["n"] if m4 else 0),
)

st.markdown("---")


if rol == "administrador":
    tab_hoy, tab_sesiones, tab_disp, tab_permisos = st.tabs(
        ["Hoy", "Sesiones", "Disponibilidad", "Permisos / Reasignaciones"]
    )
else:
    tab_hoy, tab_sesiones, tab_disp, tab_turnos = st.tabs(
        ["Hoy", "Sesiones", "Disponibilidad", "Turnos pendientes"]
    )


with tab_hoy:
    st.subheader(f"Sesiones del {hoy.strftime('%d/%m/%Y')}")

    sesiones_hoy = obtener_sesiones(
        hoy,
        hoy,
        estado="todos",
        id_nutricionista=None if rol == "administrador" else id_nutri,
    )

    sesiones_hoy = [
        s for s in sesiones_hoy
        if s["estado"] in ("programada", "atendida", "ausente", "cancelada")
    ]

    if not sesiones_hoy:
        st.info("No hay sesiones para hoy.")
    else:
        for s in sesiones_hoy:
            hora = pd.to_datetime(s["fecha_hora_programada"]).strftime("%H:%M")
            icono = {
                "programada": "🟡",
                "atendida": "🟢",
                "ausente": "🔴",
                "cancelada": "⚫",
            }.get(s["estado"], "⚪")

            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 2])

                with c1:
                    st.markdown(f"{icono} **{hora} — {s['paciente']}**")
                    st.caption(f"Sesión #{s['numero_sesion']} · {s['programa']} · {s['modalidad']}")
                    if rol == "administrador":
                        st.caption(f"Nutricionista: {s['nutricionista']}")

                with c2:
                    etiqueta_conf = (
                        "reprogramada"
                        if s.get("estado_confirmacion") == "modificada"
                        else s.get("estado_confirmacion")
                    )
                    st.markdown(f"**Estado:** {s['estado'].capitalize()}")
                    if etiqueta_conf:
                        st.caption(f"Turno: {etiqueta_conf}")

                with c3:
                    if s["estado"] == "programada":
                        ca, cb, cc = st.columns(3)

                        with ca:
                            if st.button(
                                "Atendida",
                                key=f"real_{s['id_sesion']}",
                                use_container_width=True,
                                type="primary",
                            ):
                                run_command(
                                    """
                                    UPDATE sesiones
                                    SET estado='atendida',
                                        fecha_hora_atencion=NOW(),
                                        id_nutricionista_aten=%s
                                    WHERE id_sesion=%s
                                    """,
                                    (id_nutri, s["id_sesion"]),
                                )
                                st.rerun()

                        with cb:
                            if st.button(
                                "Ausente",
                                key=f"aus_{s['id_sesion']}",
                                use_container_width=True,
                            ):
                                run_command(
                                    "UPDATE sesiones SET estado='ausente' WHERE id_sesion=%s",
                                    (s["id_sesion"],),
                                )
                                st.rerun()

                        with cc:
                            if st.button(
                                "Cancelar",
                                key=f"cancelar_{s['id_sesion']}",
                                use_container_width=True,
                            ):
                                run_command(
                                    "UPDATE sesiones SET estado='cancelada' WHERE id_sesion=%s",
                                    (s["id_sesion"],),
                                )
                                limpiar_reserva_disponibilidad(s["id_sesion"])
                                st.rerun()


with tab_sesiones:
    st.subheader("Consulta de sesiones")

    c1, c2, c3 = st.columns(3)

    with c1:
        f_desde = st.date_input("Desde", value=hoy, key="ses_desde")

    with c2:
        f_hasta = st.date_input("Hasta", value=hoy + timedelta(days=14), key="ses_hasta")

    with c3:
        estado_sel = st.selectbox(
            "Estado",
            ["todos", "programada", "atendida", "ausente", "cancelada"],
            key="ses_estado",
        )

    id_filtro = None

    if rol == "administrador":
        nutris = obtener_nutricionistas()
        opts = {"Todas": None}
        opts.update({n["nombre"]: n["id_nutricionista"] for n in nutris})
        nutr_sel = st.selectbox("Nutricionista", list(opts.keys()), key="ses_nutri")
        id_filtro = opts[nutr_sel]
    else:
        id_filtro = id_nutri

    sesiones = obtener_sesiones(
        f_desde,
        f_hasta,
        estado=estado_sel,
        id_nutricionista=id_filtro,
    )

    if not sesiones:
        st.info("No hay sesiones para los filtros seleccionados.")
    else:
        df = pd.DataFrame(sesiones)
        df["Fecha"] = pd.to_datetime(df["fecha_hora_programada"]).dt.strftime("%d/%m/%Y %H:%M")
        df["Estado"] = df["estado"].map(
            {
                "programada": "🟡 Programada",
                "atendida": "🟢 Atendida",
                "ausente": "🔴 Ausente",
                "cancelada": "⚫ Cancelada",
            }
        ).fillna(df["estado"])
        df["Turno"] = df["estado_confirmacion"].replace({"modificada": "reprogramada"})

        df = df.rename(
            columns={
                "numero_sesion": "N° sesión",
                "paciente": "Paciente",
                "nutricionista": "Nutricionista",
                "programa": "Programa",
                "modalidad": "Modalidad",
            }
        )

        cols = ["Fecha", "Paciente", "N° sesión", "Programa", "Modalidad", "Estado", "Turno"]

        if rol == "administrador":
            cols.insert(2, "Nutricionista")

        st.dataframe(df[cols], use_container_width=True, hide_index=True, height=420)
        st.caption(f"Total: {len(df)} sesiones")


with tab_disp:
    st.subheader("Disponibilidad")

    id_disp, nombre_disp = selector_nutricionista(key="disp_nutri")

    dtab1, dtab2 = st.tabs(["Calendario", "Reservar / bloquear horarios"])

    with dtab1:
        if "agenda_mes_ref" not in st.session_state:
            st.session_state["agenda_mes_ref"] = hoy.replace(day=1)

        c1, c2, c3 = st.columns([1, 2, 1])

        with c1:
            if st.button("◀ Mes anterior", use_container_width=True):
                st.session_state["agenda_mes_ref"] = avanzar_mes(
                    st.session_state["agenda_mes_ref"],
                    -1,
                )
                st.rerun()

        with c2:
            st.markdown("")

        with c3:
            if st.button("Mes siguiente ▶", use_container_width=True):
                st.session_state["agenda_mes_ref"] = avanzar_mes(
                    st.session_state["agenda_mes_ref"],
                    1,
                )
                st.rerun()

        mes_ref = st.session_state["agenda_mes_ref"]
        render_calendario_mes(id_disp, mes_ref)

        st.markdown("---")
        st.markdown("**Ver detalle de un día**")

        fecha_detalle = st.date_input(
            "Seleccionar día",
            value=hoy,
            key="fecha_detalle_cal",
        )

        render_detalle_dia(id_disp, fecha_detalle)

    with dtab2:
        modo = st.radio(
            "Acción",
            ["Reservar turno", "Bloquear horario"],
            horizontal=True,
            key="modo_agenda_accion",
        )

        if modo == "Reservar turno":
            st.markdown("**Reservar turno para paciente**")

            pacientes = obtener_pacientes_para_reserva(id_disp)

            if not pacientes:
                st.info("No hay pacientes activos asignados a esta nutricionista.")
            else:
                opciones_p = {
                    f"{p['paciente']} · {p['programa']}": p
                    for p in pacientes
                }

                paciente_sel = st.selectbox(
                    "Paciente",
                    list(opciones_p.keys()),
                    key="pac_reserva",
                )

                p_data = opciones_p[paciente_sel]
                sesiones_pend = obtener_sesiones_pendientes_contrato(p_data["id_contrato"])

                if not sesiones_pend:
                    st.info("Este paciente no tiene sesiones programadas pendientes.")
                else:
                    opciones_s = {
                        f"Sesión {s['numero_sesion']} · {fmt_fecha_hora(s['fecha_hora_programada'])}": s
                        for s in sesiones_pend
                    }

                    sesion_sel = st.selectbox(
                        "Sesión a reservar",
                        list(opciones_s.keys()),
                        key="sesion_reserva",
                    )

                    s_data = opciones_s[sesion_sel]

                    c1, c2, c3, c4 = st.columns(4)

                    with c1:
                        f_res = st.date_input("Fecha", value=hoy, key="fecha_reserva")

                    with c2:
                        h_inicio_res = st.selectbox(
                            "Hora inicio",
                            generar_horas_inicio(),
                            format_func=hora_label,
                            key="hora_inicio_reserva",
                        )

                    with c3:
                        horas_fin_reserva = [
                            h for h in generar_horas_fin()
                            if h > h_inicio_res
                        ]

                        h_fin_res = st.selectbox(
                            "Hora fin",
                            horas_fin_reserva,
                            format_func=hora_label,
                            key="hora_fin_reserva",
                        )

                    with c4:
                        modalidad = st.selectbox(
                            "Modalidad",
                            ["virtual", "presencial", "mixta"],
                            key="modalidad_reserva",
                        )

                    notas = st.text_input(
                        "Notas",
                        placeholder="Opcional",
                        key="notas_reserva",
                    )

                    if st.button(
                        "Guardar reserva",
                        type="primary",
                        use_container_width=True,
                        key="guardar_reserva",
                    ):
                        fecha_hora = datetime.combine(f_res, h_inicio_res)

                        duracion = int(
                            (
                                datetime.combine(f_res, h_fin_res)
                                - datetime.combine(f_res, h_inicio_res)
                            ).total_seconds() / 60
                        )

                        no_laborables_res = obtener_no_laborables(f_res.year)

                        if es_no_laborable(f_res, no_laborables_res):
                            st.error("No se puede reservar en un día no laborable.")
                        elif not es_horario_laboral(fecha_hora):
                            st.error("La reserva debe estar entre 9:00 y 18:00.")
                        elif h_fin_res <= h_inicio_res:
                            st.error("La hora fin debe ser posterior a la hora inicio.")
                        else:
                            slot_existente = obtener_slot_exacto(id_disp, fecha_hora)

                            if slot_existente and slot_existente["estado"] in ("reservado", "bloqueado"):
                                st.error("Ese horario ya está reservado o bloqueado.")
                            else:
                                reservar_sesion(
                                    id_nutricionista=id_disp,
                                    id_sesion=s_data["id_sesion"],
                                    fecha_hora=fecha_hora,
                                    modalidad=modalidad,
                                    duracion_minutos=duracion,
                                    notas=notas or f"Reserva - {p_data['paciente']}",
                                )
                                st.success("Turno reservado correctamente.")
                                st.rerun()

        else:
            st.markdown("**Bloquear horario**")

            fechas_posibles = []

            for i in range(0, 60):
                f = hoy + timedelta(days=i)
                no_laborables_i = obtener_no_laborables(f.year)

                if not es_no_laborable(f, no_laborables_i):
                    fechas_posibles.append(f)

            fechas_sel = st.multiselect(
                "Seleccionar una o más fechas",
                options=fechas_posibles,
                format_func=lambda x: x.strftime("%d/%m/%Y"),
                placeholder="Seleccionar fechas",
                key="fechas_bloqueo_multi",
            )

            c1, c2 = st.columns(2)

            with c1:
                h_inicio = st.selectbox(
                    "Hora inicio",
                    generar_horas_inicio(),
                    format_func=hora_label,
                    key="h_inicio_bloq",
                )

            with c2:
                horas_fin_validas = [
                    h for h in generar_horas_fin()
                    if h > h_inicio
                ]

                h_fin = st.selectbox(
                    "Hora fin",
                    horas_fin_validas,
                    format_func=hora_label,
                    key="h_fin_bloq",
                )

            notas = st.text_input(
                "Notas",
                placeholder="Ej: reunión, capacitación, bloqueo administrativo...",
                key="notas_bloq",
            )

            if fechas_sel:
                total_slots = 0

                for f in fechas_sel:
                    actual = datetime.combine(f, h_inicio)
                    fin_dt = datetime.combine(f, h_fin)

                    while actual < fin_dt:
                        total_slots += 1
                        actual += timedelta(minutes=PASO_MIN)

                st.caption(f"Se crearán/actualizarán {total_slots} bloqueos.")

            if st.button(
                "Guardar bloqueo",
                type="primary",
                use_container_width=True,
                key="guardar_bloqueo",
            ):
                if not fechas_sel:
                    st.error("Seleccioná al menos una fecha.")
                elif h_fin <= h_inicio:
                    st.error("La hora fin debe ser posterior a la hora inicio.")
                else:
                    ok = 0

                    for f in fechas_sel:
                        actual = datetime.combine(f, h_inicio)
                        fin_dt = datetime.combine(f, h_fin)

                        while actual < fin_dt:
                            slot_existente = obtener_slot_exacto(id_disp, actual)

                            if slot_existente and slot_existente["estado"] == "reservado":
                                actual += timedelta(minutes=PASO_MIN)
                                continue

                            upsert_disponibilidad(
                                id_nutricionista=id_disp,
                                fecha_hora=actual,
                                duracion=PASO_MIN,
                                estado="bloqueado",
                                notas=notas or "Bloqueo manual",
                                id_sesion=None,
                            )
                            ok += 1
                            actual += timedelta(minutes=PASO_MIN)

                    st.success(f"{ok} bloqueo(s) guardado(s).")
                    st.rerun()

        st.markdown("---")
        st.markdown("**Modificar registros existentes**")

        slots = obtener_slots(hoy, hoy + timedelta(days=60), id_disp)

        if not slots:
            st.info("No hay registros próximos para modificar.")
        else:
            opts = {
                f"{fmt_fecha_hora(s['fecha_hora_inicio'])} · {s['estado']} · {s.get('paciente') or s.get('notas') or ''}": s
                for s in slots
            }

            sel = st.selectbox("Registro", list(opts.keys()), key="slot_editar")
            slot = opts[sel]

            c1, c2 = st.columns(2)

            with c1:
                if st.button("Liberar horario", use_container_width=True, key="liberar_slot"):
                    run_command(
                        "DELETE FROM disponibilidad WHERE id_slot=%s",
                        (slot["id_slot"],),
                    )
                    st.success("Horario liberado.")
                    st.rerun()

            with c2:
                if st.button("Bloquear horario", use_container_width=True, key="bloquear_slot"):
                    run_command(
                        """
                        UPDATE disponibilidad
                        SET estado='bloqueado',
                            id_sesion=NULL,
                            notas=COALESCE(notas, 'Bloqueo manual')
                        WHERE id_slot=%s
                        """,
                        (slot["id_slot"],),
                    )
                    st.success("Horario bloqueado.")
                    st.rerun()


if rol == "administrador":
    with tab_permisos:
        st.subheader("Permisos y reasignaciones")

        ptab1, ptab2 = st.tabs(["Solicitudes pendientes", "Reasignar paciente"])

        with ptab1:
            solicitudes = run_query(
                """
                SELECT pa.id_permiso,
                       p.nombre || ' ' || p.apellido AS paciente,
                       nb.nombre || ' ' || nb.apellido AS nutricionista_solicitante,
                       na.nombre || ' ' || na.apellido AS nutricionista_actual,
                       pr.nombre AS programa,
                       pa.estado,
                       pa.fecha_solicitud,
                       pa.motivo
                FROM permisos_acceso pa
                JOIN pacientes p ON pa.id_paciente = p.id_paciente
                JOIN nutricionistas nb ON pa.id_nutricionista = nb.id_nutricionista
                JOIN contratos c ON p.id_paciente = c.id_paciente AND c.estado = 'activo'
                JOIN programas pr ON c.id_programa = pr.id_programa
                JOIN nutricionistas na ON c.id_nutricionista = na.id_nutricionista
                ORDER BY pa.estado, pa.fecha_solicitud DESC
                """
            )

            if not solicitudes:
                st.info("No hay solicitudes de acceso.")
            else:
                for s in solicitudes:
                    badge = {
                        "pendiente": "🟡",
                        "aprobado": "🟢",
                        "rechazado": "🔴",
                    }.get(s["estado"], "⚪")

                    with st.container(border=True):
                        c1, c2, c3 = st.columns([3, 2, 2])

                        with c1:
                            st.markdown(
                                f"{badge} **{s['nutricionista_solicitante']}** solicita acceso a **{s['paciente']}**"
                            )
                            st.caption(f"Programa: {s['programa']} · Actual: {s['nutricionista_actual']}")
                            if s.get("motivo"):
                                st.caption(f"Motivo: {s['motivo']}")

                        with c2:
                            st.markdown(f"Estado: **{s['estado']}**")
                            st.caption(f"Solicitado: {fmt_fecha(s['fecha_solicitud'])}")

                        with c3:
                            if s["estado"] == "pendiente":
                                tipo = st.selectbox(
                                    "Tipo",
                                    ["Temporal", "Permanente"],
                                    key=f"tipo_perm_{s['id_permiso']}",
                                )

                                if tipo == "Temporal":
                                    ses_acc = st.selectbox(
                                        "Sesiones",
                                        list(range(1, 21)),
                                        index=3,
                                        key=f"ses_perm_{s['id_permiso']}",
                                    )
                                    f_exp = date.today() + timedelta(weeks=int(ses_acc) * 2)
                                else:
                                    f_exp = None

                                ca, cb = st.columns(2)

                                with ca:
                                    if st.button(
                                        "Aprobar",
                                        key=f"apr_perm_{s['id_permiso']}",
                                        use_container_width=True,
                                    ):
                                        if tipo == "Permanente":
                                            run_command(
                                                """
                                                UPDATE contratos
                                                SET id_nutricionista = pa.id_nutricionista
                                                FROM permisos_acceso pa
                                                WHERE contratos.id_paciente = pa.id_paciente
                                                  AND pa.id_permiso = %s
                                                  AND contratos.estado = 'activo'
                                                """,
                                                (s["id_permiso"],),
                                            )
                                            run_command(
                                                """
                                                UPDATE sesiones
                                                SET id_nutricionista_prog = pa.id_nutricionista
                                                FROM permisos_acceso pa
                                                JOIN contratos c ON c.id_paciente = pa.id_paciente
                                                WHERE sesiones.id_contrato = c.id_contrato
                                                  AND pa.id_permiso = %s
                                                  AND sesiones.estado = 'programada'
                                                """,
                                                (s["id_permiso"],),
                                            )
                                            run_command(
                                                """
                                                UPDATE permisos_acceso
                                                SET estado='aprobado',
                                                    fecha_expiracion=NULL,
                                                    aprobado_por=%s,
                                                    fecha_resolucion=NOW()
                                                WHERE id_permiso=%s
                                                """,
                                                (id_usuario, s["id_permiso"]),
                                            )
                                        else:
                                            run_command(
                                                """
                                                UPDATE permisos_acceso
                                                SET estado='aprobado',
                                                    fecha_expiracion=%s,
                                                    aprobado_por=%s,
                                                    fecha_resolucion=NOW()
                                                WHERE id_permiso=%s
                                                """,
                                                (f_exp, id_usuario, s["id_permiso"]),
                                            )

                                        st.success("Solicitud aprobada.")
                                        st.rerun()

                                with cb:
                                    if st.button(
                                        "Rechazar",
                                        key=f"rec_perm_{s['id_permiso']}",
                                        use_container_width=True,
                                    ):
                                        run_command(
                                            """
                                            UPDATE permisos_acceso
                                            SET estado='rechazado',
                                                aprobado_por=%s,
                                                fecha_resolucion=NOW()
                                            WHERE id_permiso=%s
                                            """,
                                            (id_usuario, s["id_permiso"]),
                                        )
                                        st.rerun()

        with ptab2:
            pacientes_activos = run_query(
                """
                SELECT p.id_paciente,
                       p.nombre || ' ' || p.apellido AS nombre,
                       n.nombre || ' ' || n.apellido AS nutricionista_actual,
                       c.id_nutricionista AS id_nutricionista_actual,
                       pr.nombre AS programa,
                       c.id_contrato
                FROM pacientes p
                JOIN contratos c ON p.id_paciente = c.id_paciente AND c.estado = 'activo'
                JOIN nutricionistas n ON c.id_nutricionista = n.id_nutricionista
                JOIN programas pr ON c.id_programa = pr.id_programa
                ORDER BY p.apellido
                """
            )

            nutris_list = obtener_nutricionistas()

            if pacientes_activos and nutris_list:
                pac_opts = {
                    f"{p['nombre']} ({p['nutricionista_actual']})": p
                    for p in pacientes_activos
                }
                nutr_opts = {
                    n["nombre"]: n["id_nutricionista"]
                    for n in nutris_list
                }

                pac_sel = st.selectbox("Paciente", list(pac_opts.keys()), key="reas_pac")
                nutr_sel = st.selectbox("Nueva nutricionista", list(nutr_opts.keys()), key="reas_nutr")

                pac_data = pac_opts[pac_sel]
                tipo_reas = st.radio(
                    "Tipo",
                    ["Permanente", "Temporal"],
                    horizontal=True,
                    key="tipo_reas",
                )

                f_exp_reas = None

                if tipo_reas == "Temporal":
                    ses_reas = st.selectbox("Sesiones de acceso", list(range(1, 21)), index=3)
                    f_exp_reas = date.today() + timedelta(weeks=int(ses_reas) * 2)

                if st.button("Reasignar", use_container_width=True, type="primary"):
                    nueva_id = nutr_opts[nutr_sel]

                    if tipo_reas == "Permanente":
                        run_command(
                            """
                            INSERT INTO historial_asignaciones_paciente
                                (id_paciente, id_contrato, id_nutricionista_anterior,
                                 id_nutricionista_nueva, tipo_cambio, motivo, creado_por)
                            VALUES (%s, %s, %s, %s, 'reasignacion_directa', %s, %s)
                            """,
                            (
                                pac_data["id_paciente"],
                                pac_data["id_contrato"],
                                pac_data["id_nutricionista_actual"],
                                nueva_id,
                                "Reasignación directa desde Agenda",
                                id_usuario,
                            ),
                        )

                        run_command(
                            """
                            UPDATE contratos
                            SET id_nutricionista = %s
                            WHERE id_contrato = %s
                            """,
                            (nueva_id, pac_data["id_contrato"]),
                        )

                        run_command(
                            """
                            UPDATE sesiones
                            SET id_nutricionista_prog = %s
                            WHERE id_contrato = %s
                              AND estado = 'programada'
                            """,
                            (nueva_id, pac_data["id_contrato"]),
                        )

                        st.success("Paciente reasignado permanentemente.")
                    else:
                        run_command(
                            """
                            INSERT INTO permisos_acceso
                                (id_nutricionista, id_paciente, estado, solicitado_por,
                                 fecha_solicitud, fecha_expiracion)
                            VALUES (%s, %s, 'aprobado', %s, NOW(), %s)
                            ON CONFLICT (id_nutricionista, id_paciente)
                            DO UPDATE SET
                                estado='aprobado',
                                fecha_expiracion=EXCLUDED.fecha_expiracion
                            """,
                            (
                                nueva_id,
                                pac_data["id_paciente"],
                                nueva_id,
                                f_exp_reas,
                            ),
                        )
                        st.success("Acceso temporal otorgado.")

                    st.rerun()


if rol == "nutricionista":
    with tab_turnos:
        st.subheader("Turnos pendientes")

        turnos = obtener_sesiones(
            hoy - timedelta(days=60),
            hoy + timedelta(days=60),
            estado="programada",
            id_nutricionista=id_nutri,
        )

        if not turnos:
            st.success("No hay turnos programados pendientes.")
        else:
            for t in turnos:
                etiqueta_conf = (
                    "Reprogramada"
                    if t.get("estado_confirmacion") == "modificada"
                    else (t.get("estado_confirmacion") or "pendiente")
                )

                with st.container(border=True):
                    c1, c2, c3 = st.columns([3, 2, 2])

                    with c1:
                        st.markdown(f"**{t['paciente']}**")
                        st.caption(f"{t['programa']} · {t['modalidad']}")
                        st.markdown(f"Turno: **{fmt_fecha_hora(t['fecha_hora_programada'])}**")
                        st.caption(f"Estado de turno: {etiqueta_conf}")

                    with c2:
                        if st.button(
                            "Marcar atendida",
                            key=f"aten_{t['id_sesion']}",
                            use_container_width=True,
                            type="primary",
                        ):
                            run_command(
                                """
                                UPDATE sesiones
                                SET estado='atendida',
                                    fecha_hora_atencion=NOW(),
                                    id_nutricionista_aten=%s
                                WHERE id_sesion=%s
                                """,
                                (id_nutri, t["id_sesion"]),
                            )
                            st.rerun()

                        if st.button(
                            "Marcar ausente",
                            key=f"ausente_{t['id_sesion']}",
                            use_container_width=True,
                        ):
                            run_command(
                                "UPDATE sesiones SET estado='ausente' WHERE id_sesion=%s",
                                (t["id_sesion"],),
                            )
                            st.rerun()

                        if st.button(
                            "Cancelar sesión",
                            key=f"cancelar_turno_{t['id_sesion']}",
                            use_container_width=True,
                        ):
                            run_command(
                                "UPDATE sesiones SET estado='cancelada' WHERE id_sesion=%s",
                                (t["id_sesion"],),
                            )
                            limpiar_reserva_disponibilidad(t["id_sesion"])
                            st.rerun()

                    with c3:
                        with st.expander("Reprogramar"):
                            nueva_f = st.date_input(
                                "Nueva fecha",
                                value=max(
                                    hoy,
                                    pd.to_datetime(t["fecha_hora_programada"]).date(),
                                ),
                                key=f"rep_f_{t['id_sesion']}",
                            )

                            nueva_h = st.selectbox(
                                "Nueva hora",
                                generar_horas_inicio(),
                                format_func=hora_label,
                                key=f"rep_h_{t['id_sesion']}",
                            )

                            nueva_modalidad = st.selectbox(
                                "Modalidad",
                                ["virtual", "presencial", "mixta"],
                                index=["virtual", "presencial", "mixta"].index(t["modalidad"])
                                if t["modalidad"] in ["virtual", "presencial", "mixta"]
                                else 0,
                                key=f"rep_mod_{t['id_sesion']}",
                            )

                            motivo = st.text_input(
                                "Motivo",
                                placeholder="Ej: pedido del paciente, cambio de agenda...",
                                key=f"rep_mot_{t['id_sesion']}",
                            )

                            if st.button(
                                "Guardar reprogramación",
                                key=f"rep_guardar_{t['id_sesion']}",
                                use_container_width=True,
                            ):
                                nueva_fh = datetime.combine(nueva_f, nueva_h)
                                no_labs = obtener_no_laborables(nueva_f.year)

                                if es_no_laborable(nueva_f, no_labs):
                                    st.error("No se puede reprogramar a un día no laborable.")
                                elif not es_horario_laboral(nueva_fh):
                                    st.error("El horario debe estar entre 9:00 y 18:00.")
                                else:
                                    slot_existente = obtener_slot_exacto(id_nutri, nueva_fh)

                                    if slot_existente and slot_existente["estado"] in ("reservado", "bloqueado"):
                                        st.error("Ese horario ya está reservado o bloqueado.")
                                    else:
                                        registrar_reprogramacion_desde_agenda(
                                            id_sesion=t["id_sesion"],
                                            nueva_fecha_hora=nueva_fh,
                                            modalidad_nueva=nueva_modalidad,
                                            motivo=motivo or "Reprogramación desde agenda",
                                            reprogramada_por="nutricionista",
                                        )
                                        st.success("Turno reprogramado.")
                                        st.rerun()