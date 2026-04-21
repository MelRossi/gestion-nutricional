import streamlit as st
from database import run_query, run_command
from datetime import date, timedelta, datetime, time
from utils import mostrar_sidebar

def inject_tally_style():
    st.markdown("""
    <style>
    /* ── Layout ── */
    .onb-wrap {
        max-width: 860px;
        margin: 0 auto;
        padding: 10px 8px 48px 8px;
    }
    .onb-title {
        font-size: 2.2rem;
        font-weight: 800;
        color: #00DC8E;
        margin-bottom: 6px;
        line-height: 1.05;
    }
    .onb-subtitle {
        color: #5B6470;
        font-size: 1rem;
        margin-bottom: 18px;
    }
    .onb-divider {
        height: 1px;
        background: #E5E7EB;
        margin: 16px 0 22px 0;
    }

    /* ── Step chips ── */
    .steps-row {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-bottom: 4px;
    }
    .step-chip {
        display: inline-flex;
        align-items: center;
        background: #F3F4F6;
        color: #9CA3AF;
        border-radius: 999px;
        padding: 6px 14px;
        font-size: .88rem;
        font-weight: 600;
        border: 1.5px solid transparent;
        white-space: nowrap;
    }
    .step-chip.active {
        background: rgba(0,220,142,.15);
        color: #067a52;
        border-color: rgba(0,220,142,.4);
    }
    .step-chip.done {
        background: rgba(0,220,142,.12);
        color: #059669;
        border-color: rgba(0,220,142,.3);
    }

    /* ── Forms ── */
    div[data-testid="stForm"] {
        border: none !important;
        padding: 0 !important;
        background: transparent !important;
        box-shadow: none !important;
    }

    /* ── Column safety ── */
    [data-testid="column"] {
        min-width: 0 !important;
    }
    [data-testid="column"] > div {
        width: 100% !important;
        min-width: 0 !important;
    }

    /* ── Widget wrappers ── */
    div[data-testid="stTextInput"],
    div[data-testid="stDateInput"],
    div[data-testid="stTextArea"],
    div[data-testid="stSelectbox"],
    div[data-testid="stNumberInput"] {
        width: 100% !important;
        min-width: 0 !important;
    }

    /* ── Inputs ── */
    div[data-testid="stTextInput"] input,
    div[data-testid="stDateInput"] input,
    div[data-testid="stTextArea"] textarea,
    div[data-testid="stNumberInput"] input,
    div[data-baseweb="select"] > div {
        width: 100% !important;
        max-width: 100% !important;
        box-sizing: border-box !important;
        border-radius: 10px !important;
        min-height: 48px !important;
        border: 1.5px solid #D1D5DB !important;
        box-shadow: none !important;
        background: #fff !important;
        font-size: .97rem !important;
    }

    div[data-testid="stTextArea"] textarea {
        min-height: 110px !important;
    }

    div[data-testid="stTextInput"] input:focus,
    div[data-testid="stTextArea"] textarea:focus,
    div[data-testid="stNumberInput"] input:focus {
        border-color: #00DC8E !important;
        box-shadow: 0 0 0 3px rgba(0,220,142,.12) !important;
    }

    /* ── Labels ── */
    div[data-testid="stTextInput"] label,
    div[data-testid="stTextArea"] label,
    div[data-testid="stDateInput"] label,
    div[data-testid="stSelectbox"] label,
    div[data-testid="stNumberInput"] label {
        margin-bottom: 4px !important;
    }
    div[data-testid="stTextInput"] label p,
    div[data-testid="stTextArea"] label p,
    div[data-testid="stDateInput"] label p,
    div[data-testid="stSelectbox"] label p,
    div[data-testid="stNumberInput"] label p {
        font-size: 0.9rem !important;
        font-weight: 700 !important;
        color: #111827 !important;
        letter-spacing: 0.01em !important;
    }

    /* ── Buttons ── */
    button[kind="primary"],
    div[data-testid="stFormSubmitButton"] button {
        border-radius: 10px !important;
        background: #00DC8E !important;
        color: #fff !important;
        font-weight: 700 !important;
        min-height: 48px !important;
        border: none !important;
        font-size: .97rem !important;
    }
    button[kind="primary"]:hover,
    div[data-testid="stFormSubmitButton"] button:hover {
        background: #00c77f !important;
    }
    button[kind="secondary"] {
        border-radius: 10px !important;
        min-height: 48px !important;
    }

    /* ── Containers ── */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 16px !important;
        border: 1.5px solid #E5E7EB !important;
        box-shadow: 0 1px 4px rgba(0,0,0,.04) !important;
    }

    /* ── Radio buttons ── */
    div[data-testid="stRadio"] label p {
        font-weight: 500 !important;
        color: #374151 !important;
    }
    </style>
    """, unsafe_allow_html=True)


if "usuario" not in st.session_state:
    st.warning("Debes iniciar sesion.")
    st.stop()

if st.session_state["usuario"]["rol"] != "paciente":
    st.switch_page("app.py")

usuario = st.session_state["usuario"]
id_paciente = usuario["id_paciente"]

if not id_paciente:
    st.error("No se encontro tu perfil. Contacta al administrador.")
    st.stop()

paciente = run_query("SELECT * FROM pacientes WHERE id_paciente=%s", (id_paciente,))
if not paciente:
    st.error("Perfil no encontrado.")
    st.stop()
p = paciente[0]

contrato = run_query("""
    SELECT c.*, pr.nombre AS programa, pr.id_programa,
           pr.cantidad_sesiones, pr.modalidad
    FROM contratos c
    JOIN programas pr ON c.id_programa=pr.id_programa
    WHERE c.id_paciente=%s AND c.estado IN ('activo','pendiente_pago')
    ORDER BY c.fecha_creacion DESC LIMIT 1
""", (id_paciente,))

if not contrato:
    st.warning("No tenes un programa activo. Contacta al administrador.")
    st.stop()

c = contrato[0]
paso = int(p.get("onboarding_paso") or 0)

def avanzar_paso(nuevo_paso):
    run_command("UPDATE pacientes SET onboarding_paso=%s WHERE id_paciente=%s", (nuevo_paso, id_paciente))
    st.rerun()

mostrar_sidebar()
inject_tally_style()

st.markdown('<div class="onb-wrap">', unsafe_allow_html=True)
st.markdown('<div class="onb-title">Bienvenido/a a tu programa nutricional</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="onb-subtitle"><strong>{c["programa"]}</strong> — Completá los siguientes pasos para comenzar.</div>',
    unsafe_allow_html=True
)

pasos_labels = [
    "1. Datos personales",
    "2. Consentimiento",
    "3. Primera sesión",
    "4. Anamnesis",
    "5. Historia nutricional",
]

chips_html = ""
for i, label in enumerate(pasos_labels, 1):
    if i < paso + 1:
        clase = "step-chip done"
    elif i == paso + 1:
        clase = "step-chip active"
    else:
        clase = "step-chip"
    chips_html += f'<span class="{clase}">{label}</span>'

st.markdown(f'<div class="steps-row">{chips_html}</div>', unsafe_allow_html=True)
st.markdown('<div class="onb-divider"></div>', unsafe_allow_html=True)

# ═══════════════════════════
# PASO 1 — DATOS PERSONALES
# ═══════════════════════════
if paso == 0:
    st.subheader("Paso 1 — Tus datos personales")

    with st.form("form_datos"):
        # FILA 1
        col1, col2 = st.columns(2)
        with col1:
            nombre = st.text_input("Nombre *", value=p.get("nombre", ""))
        with col2:
            apellido = st.text_input("Apellido *", value=p.get("apellido", ""))

        # FILA 2
        col1, col2 = st.columns(2)
        with col1:
            email = st.text_input("Email *", value=p.get("email", ""))
        with col2:
            telefono = st.text_input("Teléfono", value=p.get("telefono", "") or "")

        # FILA 3
        col1, col2 = st.columns(2)
        with col1:
            fecha_nac = st.date_input(
                "Fecha de nacimiento *",
                min_value=date(1940, 1, 1),
                max_value=date.today(),
                value=p.get("fecha_nacimiento") or date(1990, 1, 1)
            )
        with col2:
            opciones_genero = ["femenino", "masculino", "otro", "prefiero_no_decir"]
            genero_actual = p.get("genero", "femenino") or "femenino"
            genero = st.selectbox(
                "Género",
                opciones_genero,
                index=opciones_genero.index(genero_actual) if genero_actual in opciones_genero else 0
            )

        guardar = st.form_submit_button("Guardar y continuar", use_container_width=True)

    if guardar:
        if not nombre or not apellido or not email:
            st.error("Nombre, apellido y email son obligatorios.")
        else:
            run_command("""
                UPDATE pacientes SET nombre=%s, apellido=%s, email=%s,
                telefono=%s, fecha_nacimiento=%s, genero=%s, onboarding_paso=1
                WHERE id_paciente=%s
            """, (nombre, apellido, email, telefono, fecha_nac, genero, id_paciente))
            st.session_state["usuario"]["nombre"] = nombre
            st.session_state["usuario"]["apellido"] = apellido
            avanzar_paso(1)

# ═══════════════════════════
# PASO 2 — CONSENTIMIENTO
# ═══════════════════════════
elif paso == 1:
    st.subheader("Paso 2 — Consentimiento informado")
    nombre_completo = f"{p['nombre']} {p['apellido']}"

    with st.container(border=True):
        st.markdown(f"""
**CONSENTIMIENTO INFORMADO**

Yo, **{nombre_completo}**, declaro haber sido informado/a sobre el programa **"{c['programa']}"** y acepto participar bajo las siguientes condiciones:

**1. NATURALEZA DEL SERVICIO**
El programa incluye {c['cantidad_sesiones']} sesiones de consulta nutricional personalizada con seguimiento profesional.

**2. COMPROMISOS**
- Asistir puntualmente a las sesiones programadas.
- Informar cambios relevantes en mi estado de salud.
- Comunicar con anticipacion cualquier imposibilidad de asistencia.

**3. REPROGRAMACIONES**
Se permite una reprogramacion por mes calendario. Las ausencias sin aviso previo seran contabilizadas como sesiones realizadas.

**4. CONFIDENCIALIDAD**
Toda la informacion clinica es estrictamente confidencial y sera utilizada unicamente para fines del tratamiento nutricional.

**5. CONSENTIMIENTO DE DATOS**
Autorizo el uso de mis datos personales y clinicos para fines del tratamiento, en cumplimiento con las normas de proteccion de datos vigentes.
        """)

    aceptado = st.checkbox("He leido, entiendo y acepto los terminos del consentimiento informado.")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Volver", use_container_width=True):
            avanzar_paso(0)
    with col2:
        if st.button("Aceptar y continuar", use_container_width=True, type="primary", disabled=not aceptado):
            run_command(
                "UPDATE contratos SET estado='activo' WHERE id_contrato=%s AND estado='pendiente_pago'",
                (c["id_contrato"],)
            )
            avanzar_paso(2)

# ═══════════════════════════
# PASO 3 — ELEGIR TURNO
# ═══════════════════════════
elif paso == 2:
    st.subheader("Paso 3 — Elegí tu primera sesion")

    primera = run_query("""
        SELECT s.id_sesion, s.fecha_hora_programada, s.modalidad,
               s.estado_confirmacion,
               n.nombre||' '||n.apellido AS nutricionista
        FROM sesiones s
        LEFT JOIN nutricionistas n ON s.id_nutricionista_prog=n.id_nutricionista
        WHERE s.id_contrato=%s AND s.numero_sesion=1
    """, (c["id_contrato"],))

    turno_elegido = (
        primera and primera[0].get("fecha_hora_programada") and
        str(primera[0]["fecha_hora_programada"])[:4] != "2099"
    )

    if turno_elegido and primera[0].get("estado_confirmacion") in ("pendiente", "confirmada", "modificada"):
        ps = primera[0]
        conf = ps["estado_confirmacion"]

        if conf == "confirmada":
            st.success(f"Tu primera sesion fue confirmada: **{str(ps['fecha_hora_programada'])[:16]}** con **{ps['nutricionista']}**")
            if st.button("Continuar al siguiente paso", use_container_width=True, type="primary"):
                avanzar_paso(3)
            if st.button("← Volver", use_container_width=True, key="volver_conf"):
                avanzar_paso(1)

        elif conf == "modificada":
            st.warning(f"Tu nutricionista propuso un nuevo horario: **{str(ps['fecha_hora_programada'])[:16]}** con **{ps['nutricionista']}**")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Aceptar nuevo horario", use_container_width=True, type="primary"):
                    run_command("UPDATE sesiones SET estado_confirmacion='confirmada' WHERE id_sesion=%s", (ps["id_sesion"],))
                    st.rerun()
            with col2:
                if st.button("Elegir otro horario", use_container_width=True):
                    run_command("""
                        UPDATE sesiones SET fecha_hora_programada=NULL,
                        estado_confirmacion='pendiente', id_nutricionista_prog=NULL
                        WHERE id_sesion=%s
                    """, (ps["id_sesion"],))
                    st.rerun()

        else:
            st.info(f"Elegiste el turno: **{str(ps['fecha_hora_programada'])[:16]}** — esperando confirmacion de la nutricionista.")
            st.caption("Te notificaremos cuando sea confirmado.")
            if st.button("Continuar y completar mis datos mientras espero", use_container_width=True):
                avanzar_paso(3)
            if st.button("← Volver", use_container_width=True, key="volver_pend"):
                avanzar_paso(1)

    else:
        modalidad = st.radio("Modalidad", ["presencial", "virtual"], horizontal=True)

        nutris_prog = run_query("""
            SELECT n.id_nutricionista, n.nombre||' '||n.apellido AS nombre
            FROM programa_nutricionistas pn
            JOIN nutricionistas n ON pn.id_nutricionista=n.id_nutricionista
            WHERE pn.id_programa=%s AND pn.activo=TRUE AND n.estado=TRUE
        """, (c["id_programa"],))

        if not nutris_prog:
            st.info("El equipo aun esta organizando la agenda. Continua completando tus datos.")
            if st.button("Continuar", use_container_width=True):
                avanzar_paso(3)
        else:
            col1, col2 = st.columns(2)
            with col1:
                f_desde = st.date_input("Desde", value=date.today())
            with col2:
                f_hasta = st.date_input("Hasta", value=date.today() + timedelta(days=30))

            ids_nutris = [n["id_nutricionista"] for n in nutris_prog]
            placeholders = ",".join(["%s"] * len(ids_nutris))
            slots = run_query(f"""
                SELECT d.id_slot, d.fecha_hora_inicio, d.duracion_minutos,
                       n.id_nutricionista,
                       n.nombre||' '||n.apellido AS nutricionista
                FROM disponibilidad d
                JOIN nutricionistas n ON d.id_nutricionista=n.id_nutricionista
                WHERE d.id_nutricionista IN ({placeholders})
                AND d.estado='disponible'
                AND DATE(d.fecha_hora_inicio) BETWEEN %s AND %s
                AND EXTRACT(HOUR FROM d.fecha_hora_inicio) BETWEEN 9 AND 17
                ORDER BY d.fecha_hora_inicio
            """, ids_nutris + [f_desde, f_hasta])

            if not slots:
                st.info("No hay turnos disponibles en ese período. Tu nutricionista te asignará un horario y te lo comunicará.")
                obs_sin_turno = st.text_area(
                    "Preferencias u observaciones para tu nutricionista (opcional)",
                    placeholder="Ej: prefiero las mañanas, solo puedo lunes y miércoles, etc.",
                    key="obs_sin_turno"
                )
                col_cont1, col_cont2 = st.columns(2)
                with col_cont1:
                    if st.button("← Volver", use_container_width=True, key="volver_sin_turno"):
                        avanzar_paso(1)
                with col_cont2:
                    if st.button("Continuar a Anamnesis →", use_container_width=True, type="primary", key="continuar_sin_turno"):
                        if obs_sin_turno:
                            run_command(
                                "UPDATE sesiones SET motivo_reprogramacion=%s WHERE id_contrato=%s AND numero_sesion=1",
                                (f"Preferencia paciente: {obs_sin_turno}", c["id_contrato"])
                            )
                        avanzar_paso(3)
            else:
                from collections import defaultdict
                por_dia = defaultdict(list)
                for s in slots:
                    dia = str(s["fecha_hora_inicio"])[:10]
                    por_dia[dia].append(s)

                st.markdown(f"**{len(slots)} turnos disponibles:**")
                dias_es = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]

                slots_map = {s["id_slot"]: s for s in slots}

                for dia, slots_dia in sorted(por_dia.items()):
                    fecha_obj = date.fromisoformat(dia)
                    nombre_dia = dias_es[fecha_obj.weekday()]
                    st.markdown(f"**{nombre_dia} {fecha_obj.strftime('%d/%m/%Y')}**")
                    cols = st.columns(min(len(slots_dia), 4))
                    for i, slot in enumerate(slots_dia):
                        hora = str(slot["fecha_hora_inicio"])[11:16]
                        with cols[i % 4]:
                            if st.button(
                                f"{hora}\n{slot['nutricionista'].split()[0]}",
                                key=f"slot_{slot['id_slot']}",
                                use_container_width=True
                            ):
                                st.session_state["slot_elegido_id"] = slot["id_slot"]
                                st.rerun()

                slot_eleg = None
                if "slot_elegido_id" in st.session_state:
                    slot_eleg = slots_map.get(st.session_state["slot_elegido_id"])

                if slot_eleg:
                    st.markdown("---")
                    fh_str = str(slot_eleg["fecha_hora_inicio"])[:16]
                    st.success(f"Seleccionaste: **{fh_str}** con **{slot_eleg['nutricionista']}**")
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("Cambiar horario", use_container_width=True):
                            del st.session_state["slot_elegido_id"]
                            st.rerun()
                    with col2:
                        if st.button("Confirmar turno", use_container_width=True, type="primary"):
                            try:
                                run_command("""
                                    UPDATE contratos SET id_nutricionista=%s, modalidad_primera_sesion=%s
                                    WHERE id_contrato=%s
                                """, (slot_eleg["id_nutricionista"], modalidad, c["id_contrato"]))
                                run_command("""
                                    UPDATE sesiones
                                    SET fecha_hora_programada=%s, id_nutricionista_prog=%s,
                                        modalidad=%s, estado='programada',
                                        estado_confirmacion='pendiente'
                                    WHERE id_contrato=%s AND numero_sesion=1
                                """, (slot_eleg["fecha_hora_inicio"], slot_eleg["id_nutricionista"],
                                      modalidad, c["id_contrato"]))
                                run_command("""
                                    UPDATE disponibilidad SET estado='reservado',
                                    id_sesion=(SELECT id_sesion FROM sesiones
                                               WHERE id_contrato=%s AND numero_sesion=1 LIMIT 1)
                                    WHERE id_slot=%s
                                """, (c["id_contrato"], slot_eleg["id_slot"]))
                                if "slot_elegido_id" in st.session_state:
                                    del st.session_state["slot_elegido_id"]
                                avanzar_paso(3)
                            except Exception as e:
                                import traceback
                                st.error(f"Error al confirmar: {e}")
                                st.code(traceback.format_exc())

        if st.button("Volver", use_container_width=True, key="volver_p3"):
            avanzar_paso(1)

# ═══════════════════════════
# PASO 4 — ANAMNESIS
# ═══════════════════════════
elif paso == 3:
    st.subheader("Paso 4 — Tu historia clinica")
    st.caption("Esta informacion es confidencial y ayuda a tu nutricionista a personalizar tu plan.")

    with st.form("form_anamnesis"):
        col1, col2 = st.columns(2)
        with col1:
            objetivo = st.text_area("Cuál es tu objetivo principal *", placeholder="Ej: bajar de peso, mejorar mis habitos...")
            enfermedades = st.text_area("Enfermedades o condiciones de salud", placeholder="Escribi 'ninguna' si no tenes")
            medicamentos = st.text_area("Medicamentos que tomas", placeholder="Nombre y dosis")
            alergias = st.text_area("Alergias o intolerancias", placeholder="Ej: lactosa, gluten...")
            restricciones = st.text_area("Restricciones en tu dieta", placeholder="Ej: vegetariana, vegana...")
        with col2:
            habitos = st.text_area("Cómo describirías tus habitos alimentarios", placeholder="Ej: como rapido, salteo comidas...")
            actividad = st.selectbox("Nivel de actividad física", ["sedentario", "leve", "moderado", "intenso", "muy_intenso"])
            frec_act = st.text_input("Con qué frecuencia", placeholder="Ej: 3 veces por semana")
            tipo_trabajo = st.text_input("Tipo de trabajo", placeholder="Ej: oficina, trabajo fisico")
            horas_trab = st.selectbox("Horas de trabajo por día", [4, 5, 6, 7, 8, 9, 10, 11, 12], index=4)
            horas_sueno = st.selectbox("Horas de sueño por noche", [4, 5, 6, 7, 8, 9, 10], index=3)
            consumo_agua = st.selectbox("Consumo de agua diario (L)", [0.5, 1.0, 1.5, 2.0, 2.5, 3.0], index=2)
            nivel_estres = st.selectbox("Nivel de estrés habitual", ["bajo", "moderado", "alto", "muy_alto"], index=1)
            observaciones = st.text_area("Algo más que quieras contarle a tu nutricionista", placeholder="Opcional")

        col_b1, col_b2 = st.columns(2)
        with col_b1:
            volver = st.form_submit_button("Volver", use_container_width=True)
        with col_b2:
            guardar = st.form_submit_button("Guardar y continuar", use_container_width=True)

    if volver:
        avanzar_paso(2)
    if guardar:
        if not objetivo:
            st.error("El objetivo es obligatorio.")
        else:
            run_command("""
                INSERT INTO anamnesis
                    (id_paciente, id_contrato, objetivo_principal, enfermedades,
                     medicamentos, alergias_intolerancias, restricciones_dieta,
                     habitos_alimentarios, actividad_fisica, frecuencia_actividad,
                     tipo_trabajo, horas_trabajo, horas_sueno, consumo_agua_litros,
                     nivel_estres, observaciones, version, estado)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,'completa')
            """, (id_paciente, c["id_contrato"], objetivo, enfermedades,
                  medicamentos, alergias, restricciones, habitos,
                  actividad, frec_act, tipo_trabajo, horas_trab,
                  horas_sueno, consumo_agua, nivel_estres, observaciones))

            modalidad_el = run_query("SELECT modalidad_primera_sesion FROM contratos WHERE id_contrato=%s", (c["id_contrato"],))
            if modalidad_el and modalidad_el[0]["modalidad_primera_sesion"] == "virtual":
                avanzar_paso(4)
            else:
                avanzar_paso(5)

# ═══════════════════════════
# PASO 5 — HISTORIA NUTRICIONAL
# ═══════════════════════════
elif paso == 4:
    st.subheader("Paso 5 — Medidas corporales")
    st.caption("Para sesiones virtuales necesitamos estos datos para preparar tu primera consulta.")

    with st.form("form_historia"):
        col1, col2, col3 = st.columns(3)
        with col1:
            peso = st.number_input("Peso actual (kg) *", min_value=0.0, step=0.1)
            talla = st.number_input("Talla (cm) *", min_value=0.0, step=0.1)
        with col2:
            cintura = st.number_input("Cintura (cm)", min_value=0.0, step=0.1)
            cadera = st.number_input("Cadera (cm)", min_value=0.0, step=0.1)
        with col3:
            brazo = st.number_input("Brazo (cm)", min_value=0.0, step=0.1)

        avances = st.text_area("Como te sentis actualmente con tu alimentacion", placeholder="Opcional...")
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            volver = st.form_submit_button("Volver", use_container_width=True)
        with col_b2:
            guardar = st.form_submit_button("Finalizar", use_container_width=True)

    if volver:
        avanzar_paso(3)
    if guardar:
        if peso == 0 or talla == 0:
            st.error("Peso y talla son obligatorios.")
        else:
            imc = round(peso / ((talla / 100) ** 2), 2)
            run_command("""
                INSERT INTO historia_nutricional
                    (id_paciente, id_sesion, version, peso, talla, imc,
                     circ_cintura, circ_cadera, circ_brazo, avance_objetivos, fuente_datos)
                VALUES (
                    %s,
                    (SELECT id_sesion FROM sesiones WHERE id_contrato=%s AND numero_sesion=1 LIMIT 1),
                    1, %s, %s, %s, %s, %s, %s, %s, 'formulario_inicial'
                )
            """, (id_paciente, c["id_contrato"], peso, talla, imc, cintura, cadera, brazo, avances or None))
            avanzar_paso(5)

# ═══════════════════════════
# ONBOARDING COMPLETO
# ═══════════════════════════
elif paso >= 5:
    st.success("## Todo listo!")

    primera = run_query("""
        SELECT s.fecha_hora_programada, s.modalidad, s.estado_confirmacion,
               n.nombre||' '||n.apellido AS nutricionista
        FROM sesiones s
        LEFT JOIN nutricionistas n ON s.id_nutricionista_prog=n.id_nutricionista
        WHERE s.id_contrato=%s AND s.numero_sesion=1
    """, (c["id_contrato"],))

    if primera and primera[0].get("fecha_hora_programada"):
        ps = primera[0]
        conf = ps.get("estado_confirmacion", "")
        if conf == "confirmada":
            st.markdown("**Tu primera sesión esta confirmada:**")
            st.markdown(f"- Fecha: **{str(ps['fecha_hora_programada'])[:16]}**")
            st.markdown(f"- Modalidad: **{ps['modalidad']}**")
            st.markdown(f"- Nutricionista: **{ps['nutricionista']}**")
        else:
            st.info(f"Turno solicitado: **{str(ps['fecha_hora_programada'])[:16]}** — pendiente de confirmación. Te avisaremos por email.")
    else:
        st.info("Tu nutricionista se pondra en contacto para coordinar la primera sesion.")

    st.markdown("---")
    if st.button("Ir a mi cuenta", use_container_width=True, type="primary"):
        st.switch_page("app.py")

st.markdown('</div>', unsafe_allow_html=True)