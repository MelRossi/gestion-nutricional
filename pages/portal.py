import streamlit as st
from database import run_query, run_command
from datetime import date

st.set_page_config(
    page_title="Programas Nutricionales",
    page_icon="",
    layout="wide"
)

# ─────────────────────────────────────────
# ESTADO DE SESIÓN DEL FLUJO DE COMPRA
# ─────────────────────────────────────────
if "paso_compra" not in st.session_state:
    st.session_state["paso_compra"] = 1
if "programa_elegido" not in st.session_state:
    st.session_state["programa_elegido"] = None
if "datos_comprador" not in st.session_state:
    st.session_state["datos_comprador"] = {}


def resetear_flujo():
    st.session_state["paso_compra"] = 1
    st.session_state["programa_elegido"] = None
    st.session_state["datos_comprador"] = {}


# ─────────────────────────────────────────
# ENCABEZADO
# ─────────────────────────────────────────
col_logo, col_login = st.columns([6, 1])
with col_logo:
    st.markdown("## Gisella - Nutrición Profesional")
    st.caption("Transformá tu salud con un plan personalizado")
with col_login:
    st.markdown("<br>", unsafe_allow_html=True)
    if "usuario" in st.session_state:
        st.page_link("app.py", label="→ Mi cuenta")
    else:
        st.page_link("app.py", label="→ Iniciar sesión")

st.markdown("---")

# ─────────────────────────────────────────
# INDICADOR DE PASOS
# ─────────────────────────────────────────
paso = st.session_state["paso_compra"]
pasos = ["1️⃣ Elegí tu programa", "2️⃣ Tus datos", "3️⃣ Términos y condiciones", "4️⃣ Pago"]
cols_pasos = st.columns(4)
for i, (col, texto) in enumerate(zip(cols_pasos, pasos), 1):
    if i == paso:
        col.markdown(f"**{texto}** ◀")
    elif i < paso:
        col.markdown(f"~~{texto}~~ ✅")
    else:
        col.markdown(f"{texto}")

st.markdown("---")


# ═══════════════════════════════════════
# PASO 1 — ELEGIR PROGRAMA
# ═══════════════════════════════════════
if paso == 1:
    st.subheader("Nuestros programas")
    st.caption("Todos los programas incluyen seguimiento personalizado con nutricionista.")

    programas = run_query("""
        SELECT id_programa, nombre, descripcion, modalidad,
               cantidad_sesiones, duracion_dias, frecuencia,
               precio_base, reprogramaciones_max
        FROM programas
        WHERE activo = TRUE
        ORDER BY precio_base
    """)

    if not programas:
        st.info("No hay programas disponibles en este momento.")
        st.stop()

    # Mostrar cards de programas
    cols = st.columns(min(len(programas), 3))
    for i, prog in enumerate(programas):
        with cols[i % 3]:
            with st.container(border=True):
                st.markdown(f"### {prog['nombre']}")
                st.markdown(f"**S/ {prog['precio_base']:,.2f}**")
                st.markdown("---")
                st.markdown(f"**{prog['cantidad_sesiones']} sesiones**")
                st.markdown(f"⏱**{prog['duracion_dias']} días**")
                st.markdown(f"Frecuencia: **{prog['frecuencia']}**")
                st.markdown(f"Modalidad: **{prog['modalidad']}**")
                st.markdown(f"Reprogramaciones: hasta **{prog['reprogramaciones_max']}**")
                if prog["descripcion"]:
                    st.caption(prog["descripcion"])
                st.markdown("")
                if st.button(f"Elegir este programa",
                             key=f"elegir_{prog['id_programa']}",
                             use_container_width=True):
                    st.session_state["programa_elegido"] = prog
                    st.session_state["paso_compra"] = 2
                    st.rerun()


# ═══════════════════════════════════════
# PASO 2 — DATOS DEL COMPRADOR
# ═══════════════════════════════════════
elif paso == 2:
    prog = st.session_state["programa_elegido"]
    st.subheader(f"Programa seleccionado: **{prog['nombre']}** — S/ {prog['precio_base']:,.2f}")
    st.markdown("---")
    st.subheader("Tus datos personales")

    with st.form("form_datos"):
        col1, col2 = st.columns(2)
        with col1:
            nombre   = st.text_input("Nombre *")
            email    = st.text_input("Email *")
            telefono = st.text_input("Teléfono")
        with col2:
            apellido = st.text_input("Apellido *")
            fecha_nac = st.date_input("Fecha de nacimiento *",
                                       min_value=date(1940, 1, 1),
                                       max_value=date.today())
            genero   = st.selectbox("Género",
                            ["femenino", "masculino", "otro", "prefiero_no_decir"])

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            volver = st.form_submit_button("← Volver", use_container_width=True)
        with col_btn2:
            continuar = st.form_submit_button("Continuar →", use_container_width=True)

    if volver:
        st.session_state["paso_compra"] = 1
        st.rerun()

    if continuar:
        errores = []
        if not nombre:   errores.append("Nombre requerido.")
        if not apellido: errores.append("Apellido requerido.")
        if not email:    errores.append("Email requerido.")

        if errores:
            for e in errores: st.error(e)
        else:
            st.session_state["datos_comprador"] = {
                "nombre": nombre, "apellido": apellido,
                "email": email, "telefono": telefono,
                "fecha_nacimiento": fecha_nac, "genero": genero
            }
            st.session_state["paso_compra"] = 3
            st.rerun()


# ═══════════════════════════════════════
# PASO 3 — TÉRMINOS Y CONDICIONES
# ═══════════════════════════════════════
elif paso == 3:
    prog = st.session_state["programa_elegido"]
    datos = st.session_state["datos_comprador"]

    st.subheader("Términos y condiciones del servicio")

    with st.container(border=True):
        st.markdown(f"""
**CONTRATO DE SERVICIOS NUTRICIONALES**

Entre el prestador de servicios y **{datos['nombre']} {datos['apellido']}**,
se acuerda la prestación del programa **"{prog['nombre']}"** bajo los siguientes términos:

**1. DESCRIPCIÓN DEL SERVICIO**
El programa incluye {prog['cantidad_sesiones']} sesiones de consulta nutricional,
con una duración total de {prog['duracion_dias']} días, modalidad {prog['modalidad']}.

**2. PRECIO Y FORMA DE PAGO**
El precio total del servicio es de **S/ {prog['precio_base']:,.2f}**.
El pago debe realizarse antes del inicio del programa.

**3. REPROGRAMACIONES**
El paciente tiene derecho a un máximo de **{prog['reprogramaciones_max']} reprogramaciones**
durante la vigencia del programa. Las reprogramaciones deben solicitarse
con al menos 24 horas de anticipación.

**4. CANCELACIONES**
Las sesiones no canceladas con anticipación serán consideradas realizadas
y descontadas del total del programa.

**5. CONFIDENCIALIDAD**
Toda la información clínica del paciente es estrictamente confidencial
y será utilizada únicamente para fines del tratamiento nutricional.

**6. CONSENTIMIENTO DE DATOS**
Al aceptar estos términos, el paciente autoriza el tratamiento de sus datos
personales y clínicos conforme a la política de privacidad del servicio.
        """)

    aceptado = st.checkbox("He leído y acepto los términos y condiciones")

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("← Volver", use_container_width=True):
            st.session_state["paso_compra"] = 2
            st.rerun()
    with col_btn2:
        if st.button("Continuar al pago →",
                     use_container_width=True,
                     disabled=not aceptado):
            st.session_state["paso_compra"] = 4
            st.rerun()


# ═══════════════════════════════════════
# PASO 4 — PAGO (MOCK)
# ═══════════════════════════════════════
elif paso == 4:
    prog = st.session_state["programa_elegido"]
    datos = st.session_state["datos_comprador"]

    st.subheader("Pago")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("**Resumen de tu compra**")
        with st.container(border=True):
            st.markdown(f"**Programa:** {prog['nombre']}")
            st.markdown(f"**Sesiones:** {prog['cantidad_sesiones']}")
            st.markdown(f"**Duración:** {prog['duracion_dias']} días")
            st.markdown(f"**Paciente:** {datos['nombre']} {datos['apellido']}")
            st.markdown(f"**Email:** {datos['email']}")
            st.markdown("---")
            st.markdown(f"### Total: S/ {prog['precio_base']:,.2f}")

    with col2:
        st.markdown("**Método de pago**")
        metodo = st.selectbox("Seleccioná cómo pagar",
                    ["yape", "plin", "transferencia bancaria", "tarjeta", "efectivo"])

        st.info("""
**Instrucciones:**

**Yape/Plin:** Escaneá el QR o enviá al número del negocio.

**Transferencia:** Te enviaremos los datos por email.

**Tarjeta:** Integración con pasarela disponible próximamente.

**Efectivo:** Podés pagar en la primera consulta.
        """)

    st.markdown("---")

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("← Volver", use_container_width=True):
            st.session_state["paso_compra"] = 3
            st.rerun()
    with col_btn2:
        if st.button("Confirmar solicitud de compra",
                     use_container_width=True,
                     type="primary"):
            try:
                from database import email_existe
                # Registrar la solicitud en la base de datos
                # Se crea el paciente SIN usuario aún (id_usuario NULL)
                # El admin confirma el pago y habilita el registro

                if not email_existe(datos["email"]):
                    # Crear paciente sin usuario
                    run_command("""
                        INSERT INTO pacientes
                            (nombre, apellido, email, telefono,
                             genero, fecha_nacimiento, estado)
                        VALUES (%s, %s, %s, %s, %s, %s, 'pendiente_pago')
                    """, (datos["nombre"], datos["apellido"], datos["email"],
                          datos.get("telefono"), datos.get("genero"),
                          datos.get("fecha_nacimiento")))

                # Obtener id del paciente
                paciente = run_query(
                    "SELECT id_paciente FROM pacientes WHERE email = %s",
                    (datos["email"],)
                )
                id_paciente = paciente[0]["id_paciente"]

                # Crear contrato en estado 'pendiente_pago'
                run_command("""
                    INSERT INTO contratos
                        (id_paciente, id_programa, id_nutricionista,
                         fecha_inicio, fecha_fin,
                         precio_base_contrato, descuento_contrato, precio_final,
                         estado, metodo_pago, reprogramaciones_usadas)
                    SELECT %s, %s,
                           (SELECT id_nutricionista FROM nutricionistas
                            WHERE estado = TRUE LIMIT 1),
                           CURRENT_DATE,
                           CURRENT_DATE + %s,
                           %s, 0, %s,
                           'pendiente_pago', %s, 0
                """, (id_paciente, prog["id_programa"],
                      prog["duracion_dias"],
                      prog["precio_base"], prog["precio_base"],
                      metodo))

                st.session_state["paso_compra"] = 5
                st.session_state["email_comprador"] = datos["email"]
                st.rerun()

            except Exception as e:
                st.error(f"Error al procesar la solicitud: {e}")


# ═══════════════════════════════════════
# PASO 5 — CONFIRMACIÓN
# ═══════════════════════════════════════
elif paso == 5:
    email = st.session_state.get("email_comprador", "")

    st.success("## ¡Solicitud recibida!")
    st.markdown(f"""
Tu solicitud de compra fue registrada correctamente.

**Próximos pasos:**
1. El equipo va a verificar tu pago
2. Recibirás una confirmación a **{email}**
3. Una vez confirmado, podrás crear tu usuario y agendar tu primera consulta

**¿Preguntas?** Contactanos por WhatsApp o email.
    """)

    if st.button("← Volver al inicio", use_container_width=True):
        resetear_flujo()
        st.rerun()