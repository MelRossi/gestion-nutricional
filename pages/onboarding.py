import streamlit as st
from database import run_query, run_command
from datetime import date, timedelta, datetime, time
from utils import mostrar_sidebar

if "usuario" not in st.session_state:
    st.warning("Debes iniciar sesion.")
    st.stop()

if st.session_state["usuario"]["rol"] != "paciente":
    st.switch_page("app.py")

usuario     = st.session_state["usuario"]
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

c    = contrato[0]
paso = int(p.get("onboarding_paso") or 0)

def avanzar_paso(nuevo_paso):
    run_command("UPDATE pacientes SET onboarding_paso=%s WHERE id_paciente=%s", (nuevo_paso, id_paciente))
    st.rerun()

mostrar_sidebar()

# Header
st.markdown(f"## Bienvenida a tu programa nutricional")
st.markdown(f"**{c['programa']}** — Completa los siguientes pasos para comenzar.")
st.markdown("---")

# Indicador de pasos
pasos_labels = ["1. Datos personales","2. Consentimiento","3. Primera sesion","4. Anamnesis","5. Historia nutricional"]
cols_p = st.columns(5)
for i, (col, label) in enumerate(zip(cols_p, pasos_labels), 1):
    if i < paso + 1:
        col.markdown(f"✅ {label}")
    elif i == paso + 1:
        col.markdown(f"**> {label}**")
    else:
        col.markdown(f"🔒 {label}")

st.markdown("---")

# ═══════════════════════════
# PASO 1 — DATOS PERSONALES
# ═══════════════════════════
if paso == 0:
    st.subheader("Paso 1 — Tus datos personales")
    with st.form("form_datos"):
        col1, col2 = st.columns(2)
        with col1:
            nombre   = st.text_input("Nombre *",   value=p.get("nombre",""))
            apellido = st.text_input("Apellido *", value=p.get("apellido",""))
            email    = st.text_input("Email *",    value=p.get("email",""))
            telefono = st.text_input("Telefono",   value=p.get("telefono","") or "")
        with col2:
            fecha_nac = st.date_input("Fecha de nacimiento *",
                                       min_value=date(1940,1,1), max_value=date.today(),
                                       value=p.get("fecha_nacimiento") or date(1990,1,1))
            genero    = st.selectbox("Genero",
                                      ["femenino","masculino","otro","prefiero_no_decir"],
                                      index=["femenino","masculino","otro","prefiero_no_decir"].index(
                                          p.get("genero","femenino") or "femenino"))
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
            st.session_state["usuario"]["nombre"]   = nombre
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

Yo, **{nombre_completo}**, declaro haber sido informada sobre el programa **"{c['programa']}"** y acepto participar bajo las siguientes condiciones:

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
            run_command("UPDATE contratos SET estado='activo' WHERE id_contrato=%s AND estado='pendiente_pago'", (c["id_contrato"],))
            avanzar_paso(2)

# ═══════════════════════════
# PASO 3 — ELEGIR TURNO
# ═══════════════════════════
elif paso == 2:
    st.subheader("Paso 3 — Elegí tu primera sesion")

    # Ver si ya eligió turno (pendiente de confirmación)
    primera = run_query("""
        SELECT s.id_sesion, s.fecha_hora_programada, s.modalidad,
               s.estado_confirmacion,
               n.nombre||' '||n.apellido AS nutricionista
        FROM sesiones s
        LEFT JOIN nutricionistas n ON s.id_nutricionista_prog=n.id_nutricionista
        WHERE s.id_contrato=%s AND s.numero_sesion=1
    """, (c["id_contrato"],))

    # Fecha 2099 = placeholder, el paciente aún no eligió turno
    turno_elegido = (primera and primera[0].get("fecha_hora_programada") and 
                     str(primera[0]["fecha_hora_programada"])[:4] != "2099")
    if turno_elegido and primera[0].get("estado_confirmacion") in ("pendiente","confirmada","modificada"):
        ps   = primera[0]
        conf = ps["estado_confirmacion"]

        if conf == "confirmada":
            st.success(f"Tu primera sesion fue confirmada: **{str(ps['fecha_hora_programada'])[:16]}** con **{ps['nutricionista']}**")
            if st.button("Continuar al siguiente paso", use_container_width=True, type="primary"):
                avanzar_paso(3)

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

        else:  # pendiente
            st.info(f"Elegiste el turno: **{str(ps['fecha_hora_programada'])[:16]}** — esperando confirmacion de la nutricionista.")
            st.caption("Te notificaremos cuando sea confirmado.")
            if st.button("Continuar y completar mis datos mientras espero", use_container_width=True):
                avanzar_paso(3)

    else:
        # Elegir modalidad
        modalidad = st.radio("Modalidad", ["presencial","virtual"], horizontal=True)

        # Nutricionistas del programa
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
                f_hasta = st.date_input("Hasta", value=date.today()+timedelta(days=30))

            ids_nutris    = [n["id_nutricionista"] for n in nutris_prog]
            placeholders  = ",".join(["%s"]*len(ids_nutris))
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
                st.info("No hay turnos disponibles en ese periodo. Proba con otras fechas.")
            else:
                from collections import defaultdict
                por_dia = defaultdict(list)
                for s in slots:
                    dia = str(s["fecha_hora_inicio"])[:10]
                    por_dia[dia].append(s)

                st.markdown(f"**{len(slots)} turnos disponibles:**")
                dias_es    = ["Lunes","Martes","Miercoles","Jueves","Viernes","Sabado","Domingo"]
                slot_eleg  = None

                for dia, slots_dia in sorted(por_dia.items()):
                    fecha_obj  = date.fromisoformat(dia)
                    nombre_dia = dias_es[fecha_obj.weekday()]
                    st.markdown(f"**{nombre_dia} {fecha_obj.strftime('%d/%m/%Y')}**")
                    cols = st.columns(min(len(slots_dia), 4))
                    for i, slot in enumerate(slots_dia):
                        hora = str(slot["fecha_hora_inicio"])[11:16]
                        with cols[i % 4]:
                            if st.button(f"{hora}\n{slot['nutricionista'].split()[0]}",
                                         key=f"slot_{slot['id_slot']}", use_container_width=True):
                                slot_eleg = slot

                if slot_eleg:
                    st.markdown("---")
                    fh_str = str(slot_eleg["fecha_hora_inicio"])[:16]
                    st.success(f"Seleccionaste: **{fh_str}** con **{slot_eleg['nutricionista']}**")
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("Cambiar horario", use_container_width=True):
                            st.rerun()
                    with col2:
                        if st.button("Confirmar turno", use_container_width=True, type="primary"):
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
                                id_sesion=(SELECT id_sesion FROM sesiones WHERE id_contrato=%s AND numero_sesion=1)
                                WHERE id_slot=%s
                            """, (c["id_contrato"], slot_eleg["id_slot"]))
                            avanzar_paso(3)

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
            objetivo      = st.text_area("Cual es tu objetivo principal *", placeholder="Ej: bajar de peso, mejorar mis habitos...")
            enfermedades  = st.text_area("Enfermedades o condiciones de salud", placeholder="Escribi 'ninguna' si no tenes")
            medicamentos  = st.text_area("Medicamentos que tomas", placeholder="Nombre y dosis")
            alergias      = st.text_area("Alergias o intolerancias", placeholder="Ej: lactosa, gluten...")
            restricciones = st.text_area("Restricciones en tu dieta", placeholder="Ej: vegetariana, vegana...")
        with col2:
            habitos      = st.text_area("Como describirias tus habitos alimentarios", placeholder="Ej: como rapido, salteo comidas...")
            actividad    = st.selectbox("Nivel de actividad fisica",
                                ["sedentario","leve","moderado","intenso","muy_intenso"])
            frec_act     = st.text_input("Con que frecuencia", placeholder="Ej: 3 veces por semana")
            tipo_trabajo = st.text_input("Tipo de trabajo", placeholder="Ej: oficina, trabajo fisico")
            horas_trab   = st.selectbox("Horas de trabajo por dia",   [4,5,6,7,8,9,10,11,12], index=4)
            horas_sueno  = st.selectbox("Horas de sueno por noche",   [4,5,6,7,8,9,10], index=3)
            consumo_agua = st.selectbox("Consumo de agua diario (L)", [0.5,1.0,1.5,2.0,2.5,3.0], index=2)
            nivel_estres = st.selectbox("Nivel de estres habitual",   ["bajo","moderado","alto","muy_alto"], index=1)
            observaciones = st.text_area("Algo mas que quieras contarle a tu nutricionista", placeholder="Opcional")

        col_b1, col_b2 = st.columns(2)
        with col_b1:
            volver  = st.form_submit_button("Volver", use_container_width=True)
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
            peso  = st.number_input("Peso actual (kg) *", min_value=0.0, step=0.1)
            talla = st.number_input("Talla (cm) *",       min_value=0.0, step=0.1)
        with col2:
            cintura = st.number_input("Cintura (cm)", min_value=0.0, step=0.1)
            cadera  = st.number_input("Cadera (cm)",  min_value=0.0, step=0.1)
        with col3:
            brazo   = st.number_input("Brazo (cm)",   min_value=0.0, step=0.1)
        avances = st.text_area("Como te sentis actualmente con tu alimentacion", placeholder="Opcional...")
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            volver  = st.form_submit_button("Volver", use_container_width=True)
        with col_b2:
            guardar = st.form_submit_button("Finalizar", use_container_width=True)

    if volver:
        avanzar_paso(3)
    if guardar:
        if peso == 0 or talla == 0:
            st.error("Peso y talla son obligatorios.")
        else:
            imc = round(peso/((talla/100)**2), 2)
            run_command("""
                INSERT INTO historia_nutricional
                    (id_paciente, id_contrato, version, peso, talla, imc,
                     circ_cintura, circ_cadera, circ_brazo, avance_objetivos, fuente_datos)
                VALUES (%s,%s,1,%s,%s,%s,%s,%s,%s,%s,'formulario')
            """, (id_paciente, c["id_contrato"], peso, talla, imc, cintura, cadera, brazo, avances or None))
            avanzar_paso(5)

# ═══════════════════════════
# ONBOARDING COMPLETO
# ═══════════════════════════
elif paso >= 5:
    st.success("## Todo listo!")
    st.balloons()

    primera = run_query("""
        SELECT s.fecha_hora_programada, s.modalidad, s.estado_confirmacion,
               n.nombre||' '||n.apellido AS nutricionista
        FROM sesiones s
        LEFT JOIN nutricionistas n ON s.id_nutricionista_prog=n.id_nutricionista
        WHERE s.id_contrato=%s AND s.numero_sesion=1
    """, (c["id_contrato"],))

    if primera and primera[0].get("fecha_hora_programada"):
        ps   = primera[0]
        conf = ps.get("estado_confirmacion","")
        if conf == "confirmada":
            st.markdown(f"**Tu primera sesion esta confirmada:**")
            st.markdown(f"- Fecha: **{str(ps['fecha_hora_programada'])[:16]}**")
            st.markdown(f"- Modalidad: **{ps['modalidad']}**")
            st.markdown(f"- Nutricionista: **{ps['nutricionista']}**")
        else:
            st.info(f"Turno solicitado: **{str(ps['fecha_hora_programada'])[:16]}** — pendiente de confirmacion. Te avisaremos por email.")
    else:
        st.info("Tu nutricionista se pondra en contacto para coordinar la primera sesion.")

    st.markdown("---")
    if st.button("Ir a mi cuenta", use_container_width=True, type="primary"):
        st.switch_page("app.py")