import io
import json
from datetime import date, datetime, timedelta, time

import pandas as pd
import streamlit as st

from database import run_query, run_command
from utils import mostrar_sidebar, page_header, info_banner
from composicion_utils import build_composicion_pdf, show_composicion_preview
from plan_utils import build_plan_pdf, read_plan_record, show_plan_preview


if "usuario" not in st.session_state:
    st.warning("Debés iniciar sesión.")
    st.stop()

usuario = st.session_state["usuario"]
rol = usuario["rol"]
id_usuario = usuario.get("id_usuario")
id_nutri = usuario.get("id_nutricionista")

mostrar_sidebar()
page_header("Ficha del paciente")


def val(x, default="—"):
    return x if x not in (None, "", "None") else default


def fmt_fecha(x):
    if not x:
        return "—"
    try:
        return pd.to_datetime(x).strftime("%d/%m/%Y")
    except Exception:
        return str(x)[:10]


def fmt_fecha_hora(x):
    if not x:
        return "—"
    try:
        return pd.to_datetime(x).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(x)[:16]


def safe_int(x, default=0):
    try:
        return int(x or default)
    except Exception:
        return default


def safe_float(x, default=0.0):
    try:
        return float(x or default)
    except Exception:
        return default


HORA_INICIO = time(9, 0)
HORA_FIN = time(18, 0)
PASO_MIN = 15


def generar_horas_inicio():
    horas = []
    actual = datetime.combine(date.today(), HORA_INICIO)
    fin_dt = datetime.combine(date.today(), HORA_FIN)

    while actual < fin_dt:
        horas.append(actual.time())
        actual += timedelta(minutes=PASO_MIN)

    return horas


def hora_label(h):
    return h.strftime("%H:%M")


def es_horario_laboral(dt):
    return dt.weekday() < 5 and HORA_INICIO <= dt.time() < HORA_FIN


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


def upsert_disponibilidad(id_nutricionista, fecha_hora, duracion, estado, notas=None, id_sesion=None):
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


def obtener_id_nutricionista_actual(sesion=None):
    if id_nutri:
        return id_nutri

    if sesion and sesion.get("id_nutricionista_prog"):
        return sesion["id_nutricionista_prog"]

    return None


def registrar_reprogramacion_sesion(sesion, nueva_fecha_hora, modalidad_nueva, motivo, reprogramada_por):
    prox = run_query(
        """
        SELECT COALESCE(MAX(subnumero), 0) + 1 AS prox_subnumero
        FROM sesiones_historial
        WHERE id_sesion = %s
        """,
        (sesion["id_sesion"],),
    )
    subnumero = prox[0]["prox_subnumero"] if prox else 1

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
            sesion["id_sesion"],
            sesion["id_contrato"],
            sesion["numero_sesion"],
            subnumero,
            sesion["fecha_hora_programada"],
            nueva_fecha_hora,
            sesion["modalidad"],
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
            sesion["id_sesion"],
        ),
    )

    run_command(
        """
        UPDATE contratos
        SET reprogramaciones_usadas = reprogramaciones_usadas + 1,
            fecha_ultima_reprogramacion = %s
        WHERE id_contrato = %s
        """,
        (nueva_fecha_hora.date(), sesion["id_contrato"]),
    )

    limpiar_reserva_disponibilidad(sesion["id_sesion"])
    upsert_disponibilidad(
        id_nutricionista=sesion["id_nutricionista_prog"],
        fecha_hora=nueva_fecha_hora,
        duracion=60,
        estado="reservado",
        notas=motivo or "Turno reprogramado",
        id_sesion=sesion["id_sesion"],
    )


def tipo_paciente_visual(x):
    return "Empresa" if str(x or "persona").lower() == "empresa" else "Persona"


def estado_contrato_visual(c):
    if not c:
        return "Sin contrato"

    estado = (c.get("estado") or "").lower()
    realizadas = safe_int(c.get("sesiones_realizadas"))
    total = safe_int(c.get("cantidad_sesiones"))
    fecha_fin_real = c.get("fecha_fin_real") or c.get("fecha_fin_teorica") or c.get("fecha_fin")

    if estado in ("cancelado", "cancelada"):
        return "Cancelado"
    if estado in ("finalizado", "finalizada", "cerrado", "cerrada"):
        return "Finalizado"

    if fecha_fin_real:
        try:
            if pd.to_datetime(fecha_fin_real).date() < date.today() and estado == "activo":
                return "Vencido"
        except Exception:
            pass

    if total > 0 and realizadas >= total:
        return "Completado"

    if estado == "activo":
        return "Activo"

    return estado.capitalize() if estado else "Sin contrato"


def estado_sesion_label(estado, reprogramada=False):
    if reprogramada:
        return "🟣 Reprogramada"

    estado = (estado or "").lower()

    if estado == "atendida":
        return "🟢 Atendida"
    if estado == "programada":
        return "🟡 Programada"
    if estado in ("cancelada", "cancelado"):
        return "⚪ Cancelada"
    if estado in ("ausente", "no_asistio"):
        return "🔴 Ausente"

    return estado.capitalize() if estado else "—"


def fecha_es_reprogramada(s):
    original = s.get("fecha_hora_original")
    programada = s.get("fecha_hora_programada")
    contador = safe_int(s.get("contador_reprogramaciones"))

    if contador > 0:
        return True

    if original and programada:
        try:
            return pd.to_datetime(original) != pd.to_datetime(programada)
        except Exception:
            return False

    return False


def tiene_permiso_descarga(id_paciente):
    if rol == "administrador":
        return True

    if rol != "nutricionista" or not id_nutri:
        return False

    permiso = run_query(
        """
        SELECT id_solicitud
        FROM solicitudes_descarga_ficha
        WHERE id_paciente = %s
          AND id_nutricionista = %s
          AND estado = 'aprobada'
        ORDER BY fecha_resolucion DESC NULLS LAST, fecha_solicitud DESC
        LIMIT 1
        """,
        (id_paciente, id_nutri),
    )

    return bool(permiso)


def mostrar_solicitud_descarga(id_paciente):
    if rol != "nutricionista":
        return

    solicitud = run_query(
        """
        SELECT id_solicitud, estado, fecha_solicitud, fecha_resolucion, notas_admin
        FROM solicitudes_descarga_ficha
        WHERE id_paciente = %s
          AND id_nutricionista = %s
        ORDER BY fecha_solicitud DESC
        LIMIT 1
        """,
        (id_paciente, id_nutri),
    )

    if solicitud:
        s = solicitud[0]
        estado = s.get("estado")

        if estado == "pendiente":
            info_banner(
                "La solicitud para descargar la ficha completa está pendiente de aprobación.",
                "info",
            )
            return

        if estado == "aprobada":
            info_banner(
                "La solicitud de descarga fue aprobada. Ya podés descargar la ficha completa.",
                "success",
            )
            return

        if estado == "rechazada":
            info_banner(
                "La solicitud de descarga fue rechazada. Podés enviar una nueva solicitud si corresponde.",
                "info",
            )

    info_banner(
        "Para descargar la ficha completa, la nutricionista debe solicitar autorización al administrador.",
        "info",
    )

    with st.expander("Solicitar permiso de descarga"):
        motivo = st.text_area(
            "Motivo de la solicitud",
            placeholder="Ej: necesito compartir la ficha completa con el equipo clínico / seguimiento del paciente...",
            key=f"motivo_descarga_{id_paciente}",
        )

        col_espacio, col_boton = st.columns([3, 1])

        with col_boton:
            enviar_solicitud = st.button(
                "Solicitar permiso",
                type="primary",
                use_container_width=True,
                key=f"btn_solicitar_descarga_{id_paciente}",
            )

        if enviar_solicitud:
            try:
                run_command(
                    """
                    INSERT INTO solicitudes_descarga_ficha
                        (id_paciente, id_nutricionista, motivo, estado, fecha_solicitud)
                    VALUES (%s, %s, %s, 'pendiente', NOW())
                    """,
                    (id_paciente, id_nutri, motivo),
                )
                st.success("Solicitud enviada al administrador.")
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo enviar la solicitud: {e}")


def generar_pdf_ficha(p, contrato, anamnesis, historia, sesiones):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "title",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=8,
        textColor=colors.HexColor("#00DC8E"),
    )

    h2_style = ParagraphStyle(
        "h2",
        parent=styles["Heading2"],
        fontSize=12,
        spaceAfter=6,
        textColor=colors.HexColor("#00DC8E"),
    )

    normal = styles["Normal"]
    story = []

    nombre = f"{p.get('nombre', '')} {p.get('apellido', '')}".strip()

    story.append(Paragraph(f"Ficha del paciente: {nombre}", title_style))
    story.append(Paragraph(f"Generada el {date.today().strftime('%d/%m/%Y')}", normal))
    story.append(Spacer(1, 0.35 * cm))

    story.append(Paragraph("Datos personales", h2_style))

    datos = [
        ["Nombre", nombre, "DNI", val(p.get("dni"))],
        ["Email", val(p.get("email")), "Teléfono", val(p.get("telefono"))],
        ["Nacimiento", fmt_fecha(p.get("fecha_nacimiento")), "Género", val(p.get("genero"))],
        ["Tipo", tipo_paciente_visual(p.get("tipo_paciente")), "Estado", val(p.get("estado"))],
    ]

    t = Table(datos, colWidths=[3 * cm, 6 * cm, 3 * cm, 6 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E9FFF7")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#E9FFF7")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#00DC8E")),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("PADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 0.35 * cm))

    if contrato:
        story.append(Paragraph("Programa actual", h2_style))

        datos_c = [
            ["Programa", val(contrato.get("programa")), "Nutricionista", val(contrato.get("nutricionista"))],
            ["Inicio", fmt_fecha(contrato.get("fecha_inicio")), "Fin teórico", fmt_fecha(contrato.get("fecha_fin_teorica"))],
            ["Fin real", fmt_fecha(contrato.get("fecha_fin_real")), "Estado", estado_contrato_visual(contrato)],
            [
                "Realizadas",
                str(safe_int(contrato.get("sesiones_realizadas"))),
                "Restantes",
                str(max(safe_int(contrato.get("cantidad_sesiones")) - safe_int(contrato.get("sesiones_realizadas")), 0)),
            ],
        ]

        tc = Table(datos_c, colWidths=[3 * cm, 6 * cm, 3 * cm, 6 * cm])
        tc.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E9FFF7")),
                    ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#E9FFF7")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#00DC8E")),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("PADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )

        story.append(tc)
        story.append(Spacer(1, 0.35 * cm))

    if anamnesis:
        story.append(Paragraph(f"Anamnesis v{anamnesis.get('version')}", h2_style))

        campos = [
            ("Objetivo", anamnesis.get("objetivo_principal")),
            ("Enfermedades", anamnesis.get("enfermedades")),
            ("Medicamentos", anamnesis.get("medicamentos")),
            ("Alergias", anamnesis.get("alergias_intolerancias")),
            ("Restricciones", anamnesis.get("restricciones_dieta")),
            ("Antecedentes dieta", anamnesis.get("antecedentes_dieta")),
            ("Hábitos", anamnesis.get("habitos_alimentarios")),
            ("Actividad", anamnesis.get("actividad_fisica")),
            ("Trabajo", anamnesis.get("tipo_trabajo")),
            ("Sueño", anamnesis.get("horas_sueno")),
            ("Agua", anamnesis.get("consumo_agua_litros")),
            ("Estrés", anamnesis.get("nivel_estres")),
            ("Observaciones", anamnesis.get("observaciones")),
        ]

        for label, value in campos:
            story.append(Paragraph(f"<b>{label}:</b> {val(value)}", normal))

        story.append(Spacer(1, 0.35 * cm))

    if historia:
        story.append(Paragraph("Historia nutricional", h2_style))

        data = [["Versión", "Fecha", "Peso", "Talla", "IMC", "Cintura", "Cadera", "Brazo"]]

        for h in historia:
            data.append(
                [
                    val(h.get("version")),
                    fmt_fecha(h.get("fecha_registro")),
                    val(h.get("peso")),
                    val(h.get("talla")),
                    val(h.get("imc")),
                    val(h.get("circ_cintura")),
                    val(h.get("circ_cadera")),
                    val(h.get("circ_brazo")),
                ]
            )

        th = Table(data, repeatRows=1)
        th.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#00DC8E")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("PADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )

        story.append(th)
        story.append(Spacer(1, 0.35 * cm))

    if sesiones:
        story.append(Paragraph("Sesiones", h2_style))

        data_s = [["N° sesión", "Fecha teórica", "Fecha real/programada", "Modalidad", "Estado", "Nutricionista"]]

        for s in sesiones:
            data_s.append(
                [
                    val(s.get("numero_visual")),
                    fmt_fecha_hora(s.get("fecha_teorica")),
                    fmt_fecha_hora(s.get("fecha_real")),
                    val(s.get("modalidad")),
                    val(s.get("estado_visual")),
                    val(s.get("nutricionista_real") or s.get("nutricionista_programada")),
                ]
            )

        ts = Table(data_s, repeatRows=1)
        ts.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#00DC8E")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("PADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )

        story.append(ts)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def mostrar_form_anamnesis(id_paciente, id_contrato, actual=None):
    siguiente = run_query(
        """
        SELECT COALESCE(MAX(version), 0) + 1 AS version
        FROM anamnesis
        WHERE id_paciente = %s
        """,
        (id_paciente,),
    )

    version = siguiente[0]["version"] if siguiente else 1

    with st.form(f"form_anamnesis_{version}"):
        col1, col2 = st.columns(2)

        with col1:
            objetivo = st.text_area("Objetivo", value=actual.get("objetivo_principal", "") if actual else "")
            enfermedades = st.text_area("Enfermedades", value=actual.get("enfermedades", "") if actual else "")
            medicamentos = st.text_area("Medicamentos", value=actual.get("medicamentos", "") if actual else "")
            alergias = st.text_area("Alergias / intolerancias", value=actual.get("alergias_intolerancias", "") if actual else "")
            restricciones = st.text_area("Restricciones", value=actual.get("restricciones_dieta", "") if actual else "")
            antecedentes = st.text_area("Antecedentes dieta", value=actual.get("antecedentes_dieta", "") if actual else "")

        with col2:
            habitos = st.text_area("Hábitos alimentarios", value=actual.get("habitos_alimentarios", "") if actual else "")
            actividad = st.text_input("Actividad física", value=actual.get("actividad_fisica", "") if actual else "")
            frecuencia_actividad = st.text_input("Frecuencia actividad", value=actual.get("frecuencia_actividad", "") if actual else "")
            tipo_trabajo = st.text_input("Trabajo", value=actual.get("tipo_trabajo", "") if actual else "")
            horas_trabajo = st.number_input("Horas trabajo", value=safe_float(actual.get("horas_trabajo") if actual else 0), step=0.5)
            horas_sueno = st.number_input("Horas sueño", value=safe_float(actual.get("horas_sueno") if actual else 0), step=0.5)
            consumo_agua = st.number_input("Agua (L/día)", value=safe_float(actual.get("consumo_agua_litros") if actual else 0), step=0.1)
            nivel_estres = st.text_input("Estrés", value=actual.get("nivel_estres", "") if actual else "")

        observaciones = st.text_area("Observaciones", value=actual.get("observaciones", "") if actual else "")

        guardar = st.form_submit_button("Guardar anamnesis", type="primary", use_container_width=True)

        if guardar:
            run_command(
                """
                INSERT INTO anamnesis
                    (id_paciente, id_contrato, objetivo_principal, enfermedades,
                     medicamentos, alergias_intolerancias, restricciones_dieta,
                     habitos_alimentarios, actividad_fisica, frecuencia_actividad,
                     tipo_trabajo, horas_trabajo, horas_sueno, consumo_agua_litros,
                     nivel_estres, antecedentes_dieta, observaciones, version, estado)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'completa')
                """,
                (
                    id_paciente,
                    id_contrato,
                    objetivo,
                    enfermedades,
                    medicamentos,
                    alergias,
                    restricciones,
                    habitos,
                    actividad,
                    frecuencia_actividad,
                    tipo_trabajo,
                    horas_trabajo,
                    horas_sueno,
                    consumo_agua,
                    nivel_estres,
                    antecedentes,
                    observaciones,
                    version,
                ),
            )
            st.success("Anamnesis guardada.")
            st.rerun()


def mostrar_form_historia(id_paciente, id_contrato):
    siguiente = run_query(
        """
        SELECT COALESCE(MAX(version), 0) + 1 AS version
        FROM historia_nutricional
        WHERE id_paciente = %s
        """,
        (id_paciente,),
    )

    version = siguiente[0]["version"] if siguiente else 1

    sesiones = run_query(
        """
        SELECT id_sesion, numero_sesion, fecha_hora_programada
        FROM sesiones
        WHERE id_contrato = %s
        ORDER BY numero_sesion
        """,
        (id_contrato,),
    ) if id_contrato else []

    with st.form(f"form_historia_{version}"):
        col1, col2, col3 = st.columns(3)

        with col1:
            peso = st.number_input("Peso (kg)", min_value=0.0, step=0.1, key=f"peso_{version}")
            talla = st.number_input("Talla (cm)", min_value=0.0, step=0.1, key=f"talla_{version}")

        with col2:
            cintura = st.number_input("Cintura (cm)", min_value=0.0, step=0.1, key=f"cintura_{version}")
            cadera = st.number_input("Cadera (cm)", min_value=0.0, step=0.1, key=f"cadera_{version}")

        with col3:
            brazo = st.number_input("Brazo (cm)", min_value=0.0, step=0.1, key=f"brazo_{version}")
            fuente = st.selectbox(
                "Fuente",
                ["carga_manual", "sesion_presencial", "sesion_virtual", "formulario_inicial"],
                key=f"fuente_{version}",
            )

        id_sesion = None

        if sesiones:
            opciones = {
                f"Sesión {s['numero_sesion']} · {fmt_fecha_hora(s['fecha_hora_programada'])}": s["id_sesion"]
                for s in sesiones
            }
            sel_sesion = st.selectbox("Sesión asociada", ["Sin asociar"] + list(opciones.keys()))
            if sel_sesion != "Sin asociar":
                id_sesion = opciones[sel_sesion]

        avances = st.text_area("Avances")
        cambios = st.text_area("Cambios de hábitos")

        guardar = st.form_submit_button("Guardar medición", type="primary", use_container_width=True)

        if guardar:
            imc = round(peso / ((talla / 100) ** 2), 2) if peso and talla else None

            run_command(
                """
                INSERT INTO historia_nutricional
                    (id_paciente, id_sesion, version, peso, talla, imc,
                     circ_cintura, circ_cadera, circ_brazo,
                     avance_objetivos, cambios_habitos, fuente_datos)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    id_paciente,
                    id_sesion,
                    version,
                    peso or None,
                    talla or None,
                    imc,
                    cintura or None,
                    cadera or None,
                    brazo or None,
                    avances,
                    cambios,
                    fuente,
                ),
            )
            st.success("Historia nutricional guardada.")
            st.rerun()


def build_sesiones_visuales(id_contrato):
    sesiones = run_query(
        """
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
               s.motivo_reprogramacion,
               np.nombre || ' ' || np.apellido AS nutricionista_programada,
               na.nombre || ' ' || na.apellido AS nutricionista_real
        FROM sesiones s
        LEFT JOIN nutricionistas np ON np.id_nutricionista = s.id_nutricionista_prog
        LEFT JOIN nutricionistas na ON na.id_nutricionista = s.id_nutricionista_aten
        WHERE s.id_contrato = %s
        ORDER BY s.numero_sesion, s.fecha_hora_programada
        """,
        (id_contrato,),
    )

    try:
        historial = run_query(
            """
            SELECT id_historial,
                   id_sesion,
                   numero_sesion,
                   subnumero,
                   fecha_hora_anterior,
                   fecha_hora_nueva,
                   modalidad_anterior,
                   modalidad_nueva,
                   motivo,
                   reprogramada_por,
                   fecha_creacion
            FROM sesiones_historial
            WHERE id_contrato = %s
            ORDER BY numero_sesion, subnumero, fecha_creacion
            """,
            (id_contrato,),
        )
    except Exception:
        historial = []

    hist_por_sesion = {}

    for h in historial:
        hist_por_sesion.setdefault(h["id_sesion"], []).append(h)

    filas = []

    for s in sesiones:
        reprogramada = fecha_es_reprogramada(s)
        numero = str(s.get("numero_sesion"))

        if reprogramada:
            filas.append(
                {
                    "numero_visual": numero,
                    "fecha_teorica": s.get("fecha_hora_original"),
                    "fecha_real": s.get("fecha_hora_original"),
                    "modalidad": s.get("modalidad"),
                    "estado_visual": estado_sesion_label(s.get("estado"), reprogramada=True),
                    "nutricionista_programada": s.get("nutricionista_programada"),
                    "nutricionista_real": s.get("nutricionista_real"),
                    "motivo": s.get("motivo_reprogramacion"),
                }
            )

            hist = hist_por_sesion.get(s["id_sesion"], [])

            if hist:
                for h in hist:
                    filas.append(
                        {
                            "numero_visual": f"{h['numero_sesion']}.{h['subnumero']}",
                            "fecha_teorica": h.get("fecha_hora_anterior"),
                            "fecha_real": h.get("fecha_hora_nueva"),
                            "modalidad": h.get("modalidad_nueva") or s.get("modalidad"),
                            "estado_visual": estado_sesion_label(s.get("estado")),
                            "nutricionista_programada": s.get("nutricionista_programada"),
                            "nutricionista_real": s.get("nutricionista_real"),
                            "motivo": h.get("motivo") or s.get("motivo_reprogramacion"),
                        }
                    )
            else:
                filas.append(
                    {
                        "numero_visual": f"{s.get('numero_sesion')}.1",
                        "fecha_teorica": s.get("fecha_hora_original"),
                        "fecha_real": s.get("fecha_hora_atencion") or s.get("fecha_hora_programada"),
                        "modalidad": s.get("modalidad"),
                        "estado_visual": estado_sesion_label(s.get("estado")),
                        "nutricionista_programada": s.get("nutricionista_programada"),
                        "nutricionista_real": s.get("nutricionista_real"),
                        "motivo": s.get("motivo_reprogramacion"),
                    }
                )
        else:
            filas.append(
                {
                    "numero_visual": numero,
                    "fecha_teorica": s.get("fecha_hora_original"),
                    "fecha_real": s.get("fecha_hora_atencion") or s.get("fecha_hora_programada"),
                    "modalidad": s.get("modalidad"),
                    "estado_visual": estado_sesion_label(s.get("estado")),
                    "nutricionista_programada": s.get("nutricionista_programada"),
                    "nutricionista_real": s.get("nutricionista_real"),
                    "motivo": s.get("motivo_reprogramacion"),
                }
            )

    return filas


if rol == "administrador":
    pacientes = run_query(
        """
        SELECT DISTINCT ON (p.id_paciente)
               p.id_paciente,
               p.nombre || ' ' || p.apellido AS paciente,
               c.fecha_inicio,
               c.estado AS estado_contrato
        FROM pacientes p
        LEFT JOIN contratos c ON c.id_paciente = p.id_paciente
        ORDER BY p.id_paciente,
                 CASE WHEN c.estado='activo' THEN 0 ELSE 1 END,
                 c.fecha_inicio DESC NULLS LAST
        """
    )

    pacientes = sorted(
        pacientes,
        key=lambda p: (
            p.get("fecha_inicio") is None,
            str(p.get("fecha_inicio") or ""),
            p.get("paciente") or "",
        ),
        reverse=False,
    )
elif rol == "nutricionista":
    pacientes = run_query(
        """
        SELECT DISTINCT p.id_paciente, p.nombre || ' ' || p.apellido AS paciente
        FROM pacientes p
        JOIN contratos c ON c.id_paciente = p.id_paciente
        WHERE c.id_nutricionista = %s

        UNION

        SELECT DISTINCT p.id_paciente, p.nombre || ' ' || p.apellido AS paciente
        FROM permisos_acceso pa
        JOIN pacientes p ON p.id_paciente = pa.id_paciente
        WHERE pa.id_nutricionista = %s
          AND pa.estado = 'aprobado'
          AND (pa.fecha_expiracion IS NULL OR pa.fecha_expiracion >= CURRENT_DATE)

        ORDER BY paciente
        """,
        (id_nutri, id_nutri),
    )
elif rol == "paciente":
    pacientes = run_query(
        """
        SELECT id_paciente, nombre || ' ' || apellido AS paciente
        FROM pacientes
        WHERE id_usuario = %s
        """,
        (id_usuario,),
    )
else:
    pacientes = []

if not pacientes:
    st.info("No hay pacientes disponibles.")
    st.stop()

default_id = st.session_state.get("id_paciente_ficha")

# Usamos objetos como opciones para evitar errores si hay nombres repetidos,
# pero visualmente mostramos solo el nombre del paciente, sin ID.
opciones = []
for p in pacientes:
    id_p = p["id_paciente"]
    nombre_p = p.get("paciente") or "Paciente sin nombre"
    opciones.append({
        "label": nombre_p,
        "id_paciente": id_p,
    })

ids = [op["id_paciente"] for op in opciones]
default_index = ids.index(default_id) if default_id in ids else 0

if default_index < 0 or default_index >= len(opciones):
    default_index = 0

opcion_sel = st.selectbox(
    "Seleccionar paciente",
    opciones,
    index=default_index,
    format_func=lambda op: op["label"],
)

id_paciente = opcion_sel["id_paciente"]
st.session_state["id_paciente_ficha"] = id_paciente


paciente = run_query(
    """
    SELECT p.*,
           e.nombre AS empresa
    FROM pacientes p
    LEFT JOIN empresas e ON e.id_empresa = p.id_empresa
    WHERE p.id_paciente = %s
    LIMIT 1
    """,
    (id_paciente,),
)

if not paciente:
    st.error("Paciente no encontrado.")
    st.stop()

p = paciente[0]
nombre_completo = f"{p.get('nombre', '')} {p.get('apellido', '')}".strip()

contratos = run_query(
    """
    SELECT c.*,
           pr.nombre AS programa,
           pr.cantidad_sesiones,
           pr.reprogramaciones_max,
           n.nombre || ' ' || n.apellido AS nutricionista,
           COALESCE((
                SELECT COUNT(*)
                FROM sesiones s
                WHERE s.id_contrato = c.id_contrato
                  AND s.estado = 'atendida'
           ), 0) AS sesiones_realizadas
    FROM contratos c
    JOIN programas pr ON pr.id_programa = c.id_programa
    JOIN nutricionistas n ON n.id_nutricionista = c.id_nutricionista
    WHERE c.id_paciente = %s
    ORDER BY
        CASE WHEN c.estado = 'activo' THEN 0 ELSE 1 END,
        c.fecha_inicio DESC
    """,
    (id_paciente,),
)

contrato = contratos[0] if contratos else None

realizadas = safe_int(contrato.get("sesiones_realizadas") if contrato else 0)
total_sesiones = safe_int(contrato.get("cantidad_sesiones") if contrato else 0)
restantes = max(total_sesiones - realizadas, 0)

reprog_usadas = safe_int(contrato.get("reprogramaciones_usadas") if contrato else 0)
reprog_max = safe_int(
    contrato.get("reprogramaciones_max_override")
    if contrato and contrato.get("reprogramaciones_max_override") is not None
    else contrato.get("reprogramaciones_max") if contrato else 0
)

tipo_paciente = tipo_paciente_visual(p.get("tipo_paciente"))
empresa = p.get("empresa")

subtitulo_tipo = f"Tipo: {tipo_paciente}"

if str(p.get("tipo_paciente") or "persona").lower() == "empresa":
    subtitulo_tipo += f" · Empresa: {empresa or '—'}"


st.markdown(
    """
    <style>
    .patient-name-inline {
        display: flex;
        align-items: baseline;
        gap: 18px;
        margin-top: 18px;
        margin-bottom: 28px;
    }

    .patient-name-inline h2 {
        margin: 0;
        font-size: 24px;
        font-weight: 700;
        color: #111827;
    }

    .patient-type-inline {
        color: #808080;
        font-size: 14px;
        font-weight: 500;
    }

    .metric-label-custom {
        color: #808080;
        font-size: 13px;
        font-weight: 600;
        margin-bottom: 8px;
    }

    .metric-value-custom {
        color: #111827;
        font-size: 15px;
        font-weight: 700;
    }

    .patient-header-space {
        margin-bottom: 24px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <div class="patient-name-inline">
        <h2>{nombre_completo}</h2>
        <div class="patient-type-inline">{subtitulo_tipo}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

col1, col2, col3, col4, col5, col6 = st.columns(6)

with col1:
    st.markdown('<div class="metric-label-custom">Programa</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="metric-value-custom">{val(contrato.get("programa") if contrato else "—")}</div>', unsafe_allow_html=True)

with col2:
    st.markdown('<div class="metric-label-custom">Nutricionista</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="metric-value-custom">{val(contrato.get("nutricionista") if contrato else "—")}</div>', unsafe_allow_html=True)

with col3:
    st.markdown('<div class="metric-label-custom">Realizadas</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="metric-value-custom">{realizadas}</div>', unsafe_allow_html=True)

with col4:
    st.markdown('<div class="metric-label-custom">Restantes</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="metric-value-custom">{restantes}</div>', unsafe_allow_html=True)

with col5:
    st.markdown('<div class="metric-label-custom">Reprogramaciones</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="metric-value-custom">{reprog_usadas}/{reprog_max}</div>', unsafe_allow_html=True)

with col6:
    st.markdown('<div class="metric-label-custom">Estado</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="metric-value-custom">{estado_contrato_visual(contrato)}</div>', unsafe_allow_html=True)

st.markdown('<div class="patient-header-space"></div>', unsafe_allow_html=True)

progreso = realizadas / total_sesiones if total_sesiones else 0
st.progress(progreso)
st.caption(f"{realizadas} realizadas · {restantes} restantes")

st.markdown("---")


tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    [
        "Datos personales",
        "Anamnesis",
        "Historia nutricional",
        "Plan nutricional",
        "Sesiones",
        "Historial de programas",
    ]
)


with tab1:
    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f"**Nombre:** {nombre_completo}")
        st.markdown(f"**DNI:** {val(p.get('dni'))}")
        st.markdown(f"**Email:** {val(p.get('email'))}")
        st.markdown(f"**Teléfono:** {val(p.get('telefono'))}")
        st.markdown(f"**Tipo de paciente:** {tipo_paciente}")

    with col2:
        nacimiento = p.get("fecha_nacimiento")
        edad = "—"
        if nacimiento:
            try:
                edad = pd.Timestamp.today().year - pd.to_datetime(nacimiento).year
            except Exception:
                edad = "—"

        st.markdown(f"**Nacimiento:** {fmt_fecha(nacimiento)}")
        st.markdown(f"**Edad:** {edad} años" if edad != "—" else "**Edad:** —")
        st.markdown(f"**Género:** {val(p.get('genero'))}")
        st.markdown(f"**Estado:** {val(p.get('estado'))}")

        if str(p.get("tipo_paciente") or "persona").lower() == "empresa":
            st.markdown(f"**Empresa:** {val(empresa)}")

    st.markdown("---")

    if tiene_permiso_descarga(id_paciente):
        anamnesis_pdf = run_query(
            """
            SELECT *
            FROM anamnesis
            WHERE id_paciente = %s
            ORDER BY version DESC
            LIMIT 1
            """,
            (id_paciente,),
        )

        historia_pdf = run_query(
            """
            SELECT *
            FROM historia_nutricional
            WHERE id_paciente = %s
            ORDER BY version
            """,
            (id_paciente,),
        )

        sesiones_pdf = build_sesiones_visuales(contrato["id_contrato"]) if contrato else []

        pdf_bytes = generar_pdf_ficha(
            p,
            contrato,
            anamnesis_pdf[0] if anamnesis_pdf else None,
            historia_pdf,
            sesiones_pdf,
        )

        st.download_button(
            "Descargar ficha completa (PDF)",
            data=pdf_bytes,
            file_name=f"ficha_{nombre_completo.replace(' ', '_')}.pdf",
            mime="application/pdf",
            use_container_width=True,
            type="primary",
        )
    else:
        mostrar_solicitud_descarga(id_paciente)


with tab2:
    todas_anamnesis = run_query(
        """
        SELECT *
        FROM anamnesis
        WHERE id_paciente = %s
        ORDER BY version DESC
        """,
        (id_paciente,),
    )

    if todas_anamnesis:
        a = todas_anamnesis[0]

        st.caption(
            f"Versión actual: {a.get('version')} · Estado: {a.get('estado')} · {fmt_fecha(a.get('fecha_registro'))}"
        )

        col1, col2 = st.columns(2)

        with col1:
            st.markdown(f"**Objetivo:** {val(a.get('objetivo_principal'))}")
            st.markdown(f"**Enfermedades:** {val(a.get('enfermedades'))}")
            st.markdown(f"**Medicamentos:** {val(a.get('medicamentos'))}")
            st.markdown(f"**Alergias:** {val(a.get('alergias_intolerancias'))}")
            st.markdown(f"**Restricciones:** {val(a.get('restricciones_dieta'))}")
            st.markdown(f"**Antecedentes dieta:** {val(a.get('antecedentes_dieta'))}")

        with col2:
            st.markdown(f"**Hábitos:** {val(a.get('habitos_alimentarios'))}")
            st.markdown(f"**Actividad:** {val(a.get('actividad_fisica'))}")
            st.markdown(f"**Frecuencia actividad:** {val(a.get('frecuencia_actividad'))}")
            st.markdown(f"**Trabajo:** {val(a.get('tipo_trabajo'))} — {val(a.get('horas_trabajo'))} hs/día")
            st.markdown(f"**Sueño:** {val(a.get('horas_sueno'))} hs/día")
            st.markdown(f"**Agua:** {val(a.get('consumo_agua_litros'))} L/día")
            st.markdown(f"**Estrés:** {val(a.get('nivel_estres'))}")
            st.markdown(f"**Observaciones:** {val(a.get('observaciones'))}")

        if len(todas_anamnesis) > 1:
            st.markdown("---")
            with st.expander("Ver historial de anamnesis"):
                for av in todas_anamnesis[1:]:
                    with st.expander(f"Versión {av['version']} · {fmt_fecha(av.get('fecha_registro'))}"):
                        c1, c2 = st.columns(2)
                        with c1:
                            st.markdown(f"**Objetivo:** {val(av.get('objetivo_principal'))}")
                            st.markdown(f"**Enfermedades:** {val(av.get('enfermedades'))}")
                            st.markdown(f"**Alergias:** {val(av.get('alergias_intolerancias'))}")
                            st.markdown(f"**Antecedentes dieta:** {val(av.get('antecedentes_dieta'))}")
                        with c2:
                            st.markdown(f"**Hábitos:** {val(av.get('habitos_alimentarios'))}")
                            st.markdown(f"**Agua:** {val(av.get('consumo_agua_litros'))} L/día")
                            st.markdown(f"**Observaciones:** {val(av.get('observaciones'))}")

        if rol in ("administrador", "nutricionista"):
            st.markdown("---")
            with st.expander("Nueva versión de anamnesis"):
                mostrar_form_anamnesis(id_paciente, contrato["id_contrato"] if contrato else None, a)

    else:
        st.info("Sin anamnesis registrada.")
        if rol in ("administrador", "nutricionista"):
            with st.expander("Cargar anamnesis"):
                mostrar_form_anamnesis(id_paciente, contrato["id_contrato"] if contrato else None, None)


with tab3:
    historia = run_query(
        """
        SELECT h.version, h.peso, h.talla, h.imc,
               h.circ_cintura, h.circ_cadera, h.circ_brazo,
               h.avance_objetivos, h.cambios_habitos,
               h.fuente_datos, h.fecha_registro
        FROM historia_nutricional h
        WHERE h.id_paciente = %s
        ORDER BY h.version
        """,
        (id_paciente,),
    )

    if historia:
        df_h = pd.DataFrame(historia)

        try:
            import altair as alt

            col_g1, col_g2 = st.columns(2)

            with col_g1:
                st.caption("Peso (kg)")
                df_peso = df_h[["version", "peso"]].dropna()

                if len(df_peso) > 0:
                    linea_peso = alt.Chart(df_peso).mark_line(
                        color="#00DC8E"
                    ).encode(
                        x=alt.X("version:O", title="Sesión", axis=alt.Axis(labelAngle=0)),
                        y=alt.Y("peso:Q", scale=alt.Scale(zero=False), title="kg"),
                        tooltip=["version", "peso"],
                    ).properties(height=180)

                    puntos_peso = alt.Chart(df_peso).mark_point(
                        color="#00DC8E",
                        size=60,
                    ).encode(
                        x=alt.X("version:O", axis=alt.Axis(labelAngle=0)),
                        y=alt.Y("peso:Q"),
                        tooltip=["version", "peso"],
                    )

                    st.altair_chart(linea_peso + puntos_peso, use_container_width=True)

                    if len(df_peso) > 1:
                        var = float(df_peso["peso"].iloc[-1]) - float(df_peso["peso"].iloc[0])
                        st.caption(f"{'📉' if var < 0 else '📈'} Variación: **{var:+.1f} kg**")

            with col_g2:
                st.caption("IMC")
                df_imc = df_h[["version", "imc"]].dropna()

                if len(df_imc) > 0:
                    linea_imc = alt.Chart(df_imc).mark_line(
                        color="#FFCC33"
                    ).encode(
                        x=alt.X("version:O", title="Sesión", axis=alt.Axis(labelAngle=0)),
                        y=alt.Y("imc:Q", scale=alt.Scale(zero=False), title="IMC"),
                        tooltip=["version", "imc"],
                    ).properties(height=180)

                    puntos_imc = alt.Chart(df_imc).mark_point(
                        color="#FFCC33",
                        size=60,
                    ).encode(
                        x=alt.X("version:O", axis=alt.Axis(labelAngle=0)),
                        y=alt.Y("imc:Q"),
                        tooltip=["version", "imc"],
                    )

                    st.altair_chart(linea_imc + puntos_imc, use_container_width=True)

                    ultimo = float(df_imc["imc"].iloc[-1])
                    cat = (
                        "Bajo peso"
                        if ultimo < 18.5
                        else "Normal"
                        if ultimo < 25
                        else "Sobrepeso"
                        if ultimo < 30
                        else "Obesidad"
                    )
                    st.caption(f"IMC actual: **{ultimo:.1f}** ({cat})")

            df_circ = df_h[
                ["version", "circ_cintura", "circ_cadera", "circ_brazo"]
            ].dropna(how="all", subset=["circ_cintura", "circ_cadera", "circ_brazo"])

            if len(df_circ) > 0:
                st.caption("Circunferencias (cm)")

                df_melt = df_circ.melt(
                    id_vars="version",
                    value_vars=["circ_cintura", "circ_cadera", "circ_brazo"],
                    var_name="Medida",
                    value_name="cm",
                ).dropna()

                ch3 = alt.Chart(df_melt).mark_line(point=True).encode(
                    x=alt.X("version:O", title="Sesión", axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("cm:Q", scale=alt.Scale(zero=False), title="cm"),
                    color=alt.Color(
                        "Medida:N",
                        scale=alt.Scale(
                            domain=["circ_cintura", "circ_cadera", "circ_brazo"],
                            range=["#FFCC33", "#00DC8E", "#8C52FF"],
                        ),
                        legend=alt.Legend(title="Medida"),
                    ),
                    tooltip=["version", "Medida", "cm"],
                ).properties(height=220)

                st.altair_chart(ch3, use_container_width=True)

        except Exception:
            st.info("No se pudieron mostrar los gráficos.")

        st.markdown("---")

        df_show = df_h.copy()
        df_show["fecha_registro"] = df_show["fecha_registro"].apply(fmt_fecha)

        df_show = df_show.rename(
            columns={
                "version": "Versión",
                "fecha_registro": "Fecha",
                "peso": "Peso",
                "talla": "Talla",
                "imc": "IMC",
                "circ_cintura": "Cintura",
                "circ_cadera": "Cadera",
                "circ_brazo": "Brazo",
                "avance_objetivos": "Avances",
                "cambios_habitos": "Cambios de hábitos",
                "fuente_datos": "Fuente",
            }
        )

        st.dataframe(df_show, use_container_width=True, hide_index=True)

    else:
        st.info("Sin historia nutricional registrada.")

    if rol in ("administrador", "nutricionista") and contrato:
        st.markdown("---")
        with st.expander("Registrar nueva medición"):
            mostrar_form_historia(id_paciente, contrato["id_contrato"])


with tab4:
    planes = run_query(
        """
        SELECT pn.id_plan,
               pn.version,
               pn.titulo,
               pn.contenido,
               pn.contenido_json,
               pn.estado,
               pn.fecha_creacion,
               pn.fecha_vigencia,
               pn.archivo_url,
               n.nombre || ' ' || n.apellido AS nutricionista
        FROM planes_nutricionales pn
        LEFT JOIN nutricionistas n ON n.id_nutricionista = pn.id_nutricionista
        WHERE pn.id_paciente = %s
        ORDER BY pn.fecha_creacion DESC
        """,
        (id_paciente,),
    )

    if not planes:
        st.info("Este paciente todavía no tiene planes nutricionales.")
    else:
        opciones_planes = {
            f"{p['titulo'] or 'Plan nutricional'} · v{p['version']} · {fmt_fecha(p['fecha_creacion'])}": p
            for p in planes
        }

        sel_plan = st.selectbox("Seleccionar plan", list(opciones_planes.keys()))
        plan = opciones_planes[sel_plan]

        contenido_json = plan.get("contenido_json")
        if isinstance(contenido_json, str):
            try:
                contenido_json = json.loads(contenido_json)
            except Exception:
                contenido_json = None

        es_composicion = isinstance(contenido_json, dict) and contenido_json.get("tipo") == "composicion_corporal"
        tipo_doc = "Infografía corporal" if es_composicion else "Plan nutricional"

        st.caption(
            f"Tipo: {tipo_doc} · Nutricionista: {val(plan.get('nutricionista'))} · Estado: {val(plan.get('estado'))} · Vigencia: {fmt_fecha(plan.get('fecha_vigencia'))}"
        )

        if plan.get("archivo_url"):
            st.markdown(f"Archivo asociado: `{plan['archivo_url']}`")

        if es_composicion:
            pdf_doc = build_composicion_pdf(contenido_json)
            st.download_button(
                "Descargar infografía PDF",
                data=pdf_doc,
                file_name=f"infografia_composicion_v{plan['version']}.pdf",
                mime="application/pdf",
                use_container_width=True,
                key=f"ficha_descargar_comp_{plan['id_plan']}",
            )
            with st.expander("Vista previa"):
                show_composicion_preview(contenido_json, height=850)
        else:
            parsed = read_plan_record(plan)
            if parsed.get("kind") == "structured":
                pdf_doc = build_plan_pdf(parsed["data"])
                st.download_button(
                    "Descargar plan PDF",
                    data=pdf_doc,
                    file_name=f"plan_v{plan['version']}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key=f"ficha_descargar_plan_{plan['id_plan']}",
                )
                with st.expander("Vista previa"):
                    show_plan_preview(parsed["data"], height=850)
            else:
                with st.expander("Ver contenido"):
                    st.write(plan.get("contenido") or "—")

    if rol in ("administrador", "nutricionista"):
        if st.button("Crear / cargar plan nutricional", type="primary", use_container_width=True):
            st.session_state["id_paciente_plan"] = id_paciente
            st.switch_page("pages/3b_cargar_plan.py")


with tab5:
    if not contrato:
        st.info("Este paciente no tiene contrato activo o histórico.")
    else:
        sesiones_visuales = build_sesiones_visuales(contrato["id_contrato"])

        if sesiones_visuales:
            df_s = pd.DataFrame(sesiones_visuales)

            df_s["Fecha teórica"] = df_s["fecha_teorica"].apply(fmt_fecha_hora)
            df_s["Fecha real/programada"] = df_s["fecha_real"].apply(fmt_fecha_hora)

            df_s = df_s.rename(
                columns={
                    "numero_visual": "N° sesión",
                    "modalidad": "Modalidad",
                    "estado_visual": "Estado",
                    "nutricionista_programada": "Nutricionista programada",
                    "nutricionista_real": "Nutricionista que atendió",
                }
            )

            columnas = [
                "N° sesión",
                "Fecha teórica",
                "Fecha real/programada",
                "Modalidad",
                "Estado",
                "Nutricionista programada",
                "Nutricionista que atendió",
            ]

            df_s = df_s[columnas].fillna("—")

            st.dataframe(
                df_s,
                use_container_width=True,
                hide_index=True,
                height=420,
            )

            if rol in ("administrador", "nutricionista"):
                st.markdown("---")
                st.markdown("### Actualizar estado de sesión")

                sesiones_editables = run_query(
                    """
                    SELECT s.id_sesion,
                           s.id_contrato,
                           s.id_nutricionista_prog,
                           s.id_nutricionista_aten,
                           s.numero_sesion,
                           s.fecha_hora_original,
                           s.fecha_hora_programada,
                           s.fecha_hora_atencion,
                           s.modalidad,
                           s.estado,
                           s.estado_confirmacion,
                           s.contador_reprogramaciones,
                           s.motivo_reprogramacion,
                           s.reprogramada_por
                    FROM sesiones s
                    WHERE s.id_contrato = %s
                      AND s.estado = 'programada'
                    ORDER BY s.numero_sesion, s.fecha_hora_programada
                    """,
                    (contrato["id_contrato"],),
                )

                if not sesiones_editables:
                    st.success("No hay sesiones programadas pendientes de actualizar.")
                else:
                    opciones_sesion = {
                        f"Sesión {s['numero_sesion']} · {fmt_fecha_hora(s['fecha_hora_programada'])} · {estado_sesion_label(s['estado'], s.get('estado_confirmacion') == 'modificada')}": s
                        for s in sesiones_editables
                    }

                    sesion_sel = st.selectbox(
                        "Seleccionar sesión",
                        list(opciones_sesion.keys()),
                        key="ficha_actualizar_sesion_sel",
                    )
                    sesion_data = opciones_sesion[sesion_sel]

                    accion_sesion = st.radio(
                        "Acción",
                        ["Marcar atendida", "Marcar ausente", "Reprogramar"],
                        horizontal=True,
                        key="ficha_accion_sesion",
                    )

                    if accion_sesion == "Marcar atendida":
                        col_a, col_b, col_c = st.columns([1, 1, 2])

                        with col_a:
                            fecha_atencion = st.date_input(
                                "Fecha de atención",
                                value=date.today(),
                                key="ficha_fecha_atendida",
                            )

                        with col_b:
                            hora_atencion = st.selectbox(
                                "Hora de atención",
                                generar_horas_inicio(),
                                format_func=hora_label,
                                key="ficha_hora_atendida",
                            )

                        col_esp, col_btn = st.columns([3, 1])
                        with col_btn:
                            if st.button("Guardar atendida", type="primary", use_container_width=True, key="ficha_guardar_atendida"):
                                id_nutri_aten = obtener_id_nutricionista_actual(sesion_data)
                                run_command(
                                    """
                                    UPDATE sesiones
                                    SET estado = 'atendida',
                                        fecha_hora_atencion = %s,
                                        id_nutricionista_aten = %s
                                    WHERE id_sesion = %s
                                    """,
                                    (
                                        datetime.combine(fecha_atencion, hora_atencion),
                                        id_nutri_aten,
                                        sesion_data["id_sesion"],
                                    ),
                                )
                                st.success("Sesión marcada como atendida.")
                                st.rerun()

                    elif accion_sesion == "Marcar ausente":
                        col_esp, col_btn = st.columns([3, 1])
                        with col_btn:
                            if st.button("Guardar ausente", use_container_width=True, key="ficha_guardar_ausente"):
                                run_command(
                                    """
                                    UPDATE sesiones
                                    SET estado = 'ausente'
                                    WHERE id_sesion = %s
                                    """,
                                    (sesion_data["id_sesion"],),
                                )
                                st.success("Sesión marcada como ausente.")
                                st.rerun()

                    else:
                        col_a, col_b, col_c = st.columns(3)

                        with col_a:
                            nueva_fecha = st.date_input(
                                "Nueva fecha",
                                value=max(date.today(), pd.to_datetime(sesion_data["fecha_hora_programada"]).date()),
                                key="ficha_fecha_reprogramar",
                            )

                        with col_b:
                            nueva_hora = st.selectbox(
                                "Nueva hora",
                                generar_horas_inicio(),
                                format_func=hora_label,
                                key="ficha_hora_reprogramar",
                            )

                        with col_c:
                            modalidades = ["virtual", "presencial", "mixta"]
                            modalidad_actual = sesion_data.get("modalidad")
                            idx_modalidad = modalidades.index(modalidad_actual) if modalidad_actual in modalidades else 0
                            nueva_modalidad = st.selectbox(
                                "Modalidad",
                                modalidades,
                                index=idx_modalidad,
                                key="ficha_modalidad_reprogramar",
                            )

                        motivo_rep = st.text_input(
                            "Motivo",
                            placeholder="Ej: pedido del paciente, cambio de agenda...",
                            key="ficha_motivo_reprogramar",
                        )

                        col_esp, col_btn = st.columns([3, 1])
                        with col_btn:
                            if st.button("Guardar reprogramación", type="primary", use_container_width=True, key="ficha_guardar_reprogramacion"):
                                nueva_fh = datetime.combine(nueva_fecha, nueva_hora)

                                if not es_horario_laboral(nueva_fh):
                                    st.error("El horario debe estar entre 9:00 y 18:00 y de lunes a viernes.")
                                else:
                                    slot = obtener_slot_exacto(sesion_data["id_nutricionista_prog"], nueva_fh)

                                    if slot and slot["estado"] in ("reservado", "bloqueado"):
                                        st.error("Ese horario ya está reservado o bloqueado.")
                                    else:
                                        registrar_reprogramacion_sesion(
                                            sesion=sesion_data,
                                            nueva_fecha_hora=nueva_fh,
                                            modalidad_nueva=nueva_modalidad,
                                            motivo=motivo_rep or "Reprogramación desde ficha del paciente",
                                            reprogramada_por="nutricionista" if rol == "nutricionista" else "administrador",
                                        )
                                        st.success("Sesión reprogramada correctamente.")
                                        st.rerun()
        else:
            st.info("No hay sesiones registradas para este programa.")


with tab6:
    if not contratos:
        st.info("No hay programas contratados.")
    else:
        st.markdown("**Todos los programas contratados:**")

        for c in contratos:
            realizadas_c = safe_int(c.get("sesiones_realizadas"))
            total_c = safe_int(c.get("cantidad_sesiones"))
            progreso_c = realizadas_c / total_c if total_c else 0

            with st.container(border=True):
                col1, col2, col3 = st.columns([2, 2, 2])

                with col1:
                    st.markdown(f"🟢 **{c.get('programa')}**")
                    st.caption(f"Nutricionista: {c.get('nutricionista')}")
                    st.caption(f"Estado: {estado_contrato_visual(c)}")

                with col2:
                    st.markdown(f"Inicio: **{fmt_fecha(c.get('fecha_inicio'))}**")
                    st.markdown(f"Fin teórico: **{fmt_fecha(c.get('fecha_fin_teorica'))}**")
                    st.markdown(f"Fin real: **{fmt_fecha(c.get('fecha_fin_real'))}**")

                with col3:
                    st.markdown(f"Sesiones: **{realizadas_c}/{total_c}**")
                    st.progress(progreso_c)
                    max_rep = safe_int(c.get("reprogramaciones_max_override") or c.get("reprogramaciones_max"))
                    st.caption(f"Reprog.: {safe_int(c.get('reprogramaciones_usadas'))}/{max_rep}")

                with st.expander("Ver sesiones del programa"):
                    sesiones_programa = build_sesiones_visuales(c["id_contrato"])

                    if sesiones_programa:
                        df_sp = pd.DataFrame(sesiones_programa)

                        df_sp["Fecha teórica"] = df_sp["fecha_teorica"].apply(fmt_fecha_hora)
                        df_sp["Fecha real/programada"] = df_sp["fecha_real"].apply(fmt_fecha_hora)

                        df_sp = df_sp.rename(
                            columns={
                                "numero_visual": "N° sesión",
                                "modalidad": "Modalidad",
                                "estado_visual": "Estado",
                                "nutricionista_programada": "Nutricionista programada",
                                "nutricionista_real": "Nutricionista que atendió",
                            }
                        )

                        columnas_hist = [
                            "N° sesión",
                            "Fecha teórica",
                            "Fecha real/programada",
                            "Modalidad",
                            "Estado",
                            "Nutricionista programada",
                            "Nutricionista que atendió",
                        ]

                        df_sp = df_sp[columnas_hist].fillna("—")

                        st.dataframe(
                            df_sp,
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.info("Sin sesiones registradas.")

                if rol in ("administrador", "nutricionista"):
                    with st.expander("Resumen / conclusión del programa"):
                        resumen = st.text_area(
                            "Conclusión del programa",
                            value=c.get("resumen_final") or "",
                            key=f"resumen_final_{c['id_contrato']}",
                        )

                        if st.button(
                            "Guardar resumen",
                            type="primary",
                            use_container_width=True,
                            key=f"guardar_resumen_{c['id_contrato']}",
                        ):
                            run_command(
                                """
                                UPDATE contratos
                                SET resumen_final = %s
                                WHERE id_contrato = %s
                                """,
                                (resumen, c["id_contrato"]),
                            )
                            st.success("Resumen guardado.")
                            st.rerun()