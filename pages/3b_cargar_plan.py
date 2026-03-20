import streamlit as st
from utils import mostrar_sidebar
from database import run_query, run_command
from datetime import date, timedelta
import base64

# ─────────────────────────────────────────
# CONTROL DE ACCESO
# ─────────────────────────────────────────
if "usuario" not in st.session_state:
    st.warning("Debés iniciar sesión.")
    st.stop()

if st.session_state["usuario"]["rol"] not in ("administrador", "nutricionista"):
    st.error("No tenés permisos para acceder.")
    st.stop()

usuario  = st.session_state["usuario"]
id_nutri = usuario["id_nutricionista"]

# ─────────────────────────────────────────
# DETERMINAR PACIENTE
# ─────────────────────────────────────────
id_paciente = st.session_state.get("id_paciente_ficha")
lista       = []

if not id_paciente:
    if usuario["rol"] == "administrador":
        lista = run_query("""
            SELECT id_paciente, nombre || ' ' || apellido AS nombre
            FROM pacientes WHERE estado = 'activo' ORDER BY apellido
        """)
    else:
        lista = run_query("""
            SELECT DISTINCT p.id_paciente, p.nombre || ' ' || p.apellido AS nombre
            FROM pacientes p
            JOIN contratos c ON p.id_paciente = c.id_paciente
            WHERE c.id_nutricionista = %s AND c.estado = 'activo'
        """, (id_nutri,))

    if not lista:
        mostrar_sidebar()
        st.info("No hay pacientes disponibles.")
        st.stop()

# Cargar datos del paciente
if id_paciente:
    paciente = run_query(
        "SELECT nombre || ' ' || apellido AS nombre FROM pacientes WHERE id_paciente = %s",
        (id_paciente,)
    )
    nombre_paciente = paciente[0]["nombre"] if paciente else "Paciente"
else:
    nombre_paciente = ""

contrato = run_query("""
    SELECT c.id_contrato, pr.nombre AS programa
    FROM contratos c
    JOIN programas pr ON c.id_programa = pr.id_programa
    WHERE c.id_paciente = %s AND c.estado = 'activo'
    LIMIT 1
""", (id_paciente,)) if id_paciente else []

# ─────────────────────────────────────────
# PÁGINA
# ─────────────────────────────────────────
mostrar_sidebar()

st.title("Cargar plan nutricional")
st.markdown("---")

# Selector de paciente debajo del título
if not st.session_state.get("id_paciente_ficha"):
    opciones    = {p["nombre"]: p["id_paciente"] for p in lista}
    sel         = st.selectbox("Seleccioná el paciente", list(opciones.keys()))
    id_paciente = opciones[sel]
    # Recargar datos con el paciente elegido
    paciente = run_query(
        "SELECT nombre || ' ' || apellido AS nombre FROM pacientes WHERE id_paciente = %s",
        (id_paciente,)
    )
    nombre_paciente = paciente[0]["nombre"] if paciente else "Paciente"
    contrato = run_query("""
        SELECT c.id_contrato, pr.nombre AS programa
        FROM contratos c
        JOIN programas pr ON c.id_programa = pr.id_programa
        WHERE c.id_paciente = %s AND c.estado = 'activo'
        LIMIT 1
    """, (id_paciente,))

st.markdown(f"**Paciente:** {nombre_paciente}")
st.markdown("---")

# ═══════════════════════════════════════
# BUSCADOR DE PLANES
# ═══════════════════════════════════════
with st.expander("Buscar en planes anteriores de este paciente", expanded=False):
    busqueda = st.text_input("Buscá una palabra o frase",
                              placeholder="Ej: proteína, hidratación, semana 3...",
                              key="buscador_planes")

    if busqueda and len(busqueda) >= 2:
        resultados = run_query("""
            SELECT pl.id_plan, pl.version, pl.titulo, pl.estado,
                   pl.fecha_creacion, pl.contenido, pl.archivo_url,
                   n.nombre||' '||n.apellido AS nutricionista
            FROM planes_nutricionales pl
            JOIN nutricionistas n ON pl.id_nutricionista=n.id_nutricionista
            WHERE pl.id_paciente=%s
            AND (
                pl.contenido ILIKE %s
                OR pl.titulo  ILIKE %s
                OR (n.nombre||' '||n.apellido) ILIKE %s
            )
            ORDER BY pl.version DESC
        """, (id_paciente,
              f"%{busqueda}%", f"%{busqueda}%", f"%{busqueda}%"))

        if resultados:
            st.caption(f"{len(resultados)} plan(es) encontrado(s) con '{busqueda}':")
            for r in resultados:
                titulo = r.get("titulo") or f"Plan v{r['version']}"
                with st.container(border=True):
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        badge = {"activo":"🟢","reemplazado":"⚫","borrador":"🟡"}.get(r["estado"],"⚪")
                        st.markdown(f"{badge} **{titulo}** (v{r['version']}) — {r['nutricionista']}")
                        st.caption(f"Estado: {r['estado']} · Fecha: {str(r['fecha_creacion'])[:10]}")
                        if r["contenido"] and busqueda.lower() in r["contenido"].lower():
                            idx   = r["contenido"].lower().find(busqueda.lower())
                            start = max(0, idx - 60)
                            end   = min(len(r["contenido"]), idx + 80)
                            fragmento = r["contenido"][start:end].replace(
                                busqueda, f"**{busqueda}**"
                            )
                            st.caption(f"...{fragmento}...")
                    with col2:
                        if st.button("Ver", key=f"ver_plan_{r['id_plan']}", use_container_width=True):
                            k = f"expand_{r['id_plan']}"
                            st.session_state[k] = not st.session_state.get(k, False)
                    if st.session_state.get(f"expand_{r['id_plan']}", False):
                        st.markdown("---")
                        st.markdown(r["contenido"] or "Sin contenido.")
        else:
            st.info(f"No se encontraron planes con '{busqueda}'.")
    elif busqueda:
        st.caption("Ingresá al menos 2 caracteres para buscar.")

st.markdown("---")

# ── Modo de creación ──
modo = st.radio("¿Cómo querés crear el plan?",
                ["Usar plantilla", "Subir PDF"],
                horizontal=True)

st.markdown("---")

contenido_plan = ""

# ═══════════════════════════════════════
# MODO 1 — PLANTILLA
# ═══════════════════════════════════════
if modo == "Usar plantilla":
    plantillas = run_query("""
        SELECT id_plantilla, nombre, descripcion, estructura
        FROM plantillas_plan WHERE activa = TRUE ORDER BY nombre
    """)

    if not plantillas:
        st.warning("No hay plantillas disponibles. Creá una desde Administración.")
        st.stop()

    plantilla_opts = {p["nombre"]: p for p in plantillas}
    plantilla_sel  = st.selectbox("Seleccioná una plantilla", list(plantilla_opts.keys()))
    plantilla      = plantilla_opts[plantilla_sel]

    st.caption(plantilla.get("descripcion", ""))
    st.markdown("---")
    st.subheader("Completá el plan")

    estructura = plantilla["estructura"]

    import re
    campos = re.findall(r'\{\{(\w+)\}\}', estructura)

    valores = {
        "PACIENTE":      nombre_paciente,
        "FECHA":         str(date.today()),
        "NUTRICIONISTA": f"{usuario['nombre']} {usuario['apellido']}",
    }

    campos_unicos = list(dict.fromkeys(campos))
    col1, col2 = st.columns(2)

    for i, campo in enumerate(campos_unicos):
        if campo in valores:
            continue
        label = campo.replace("_", " ").capitalize()
        with (col1 if i % 2 == 0 else col2):
            if campo in ("OBJETIVO", "DESAYUNO", "MEDIA_MANANA", "ALMUERZO",
                          "MERIENDA", "CENA", "HIDRATACION", "ACTIVIDAD",
                          "EVITAR", "RECOMENDACIONES"):
                valores[campo] = st.text_area(label, key=f"campo_{campo}", height=80)
            elif campo == "VIGENCIA":
                fecha_v = st.date_input("Vigente hasta",
                                         value=date.today() + timedelta(days=30),
                                         key="vigencia")
                valores[campo] = str(fecha_v)
            else:
                valores[campo] = st.text_input(label, key=f"campo_{campo}")

    contenido_plan = estructura
    for k, v in valores.items():
        contenido_plan = contenido_plan.replace(f"{{{{{k}}}}}", v or "—")

    with st.expander("Vista previa del plan"):
        st.markdown(contenido_plan)


# ═══════════════════════════════════════
# MODO 2 — SUBIR PDF
# ═══════════════════════════════════════
elif modo == "Subir PDF":
    st.subheader("Subir plan en PDF")
    st.info("Subí el PDF del plan nutricional. El paciente podrá descargarlo desde su ficha.")

    archivo = st.file_uploader("Seleccioná el PDF", type=["pdf"])

    if archivo:
        st.success(f"Archivo listo: {archivo.name} ({round(archivo.size/1024, 1)} KB)")
        contenido_plan = f"[PDF adjunto: {archivo.name}]"
        pdf_bytes = archivo.read()
        b64_pdf   = base64.b64encode(pdf_bytes).decode("utf-8")
        st.markdown("**Vista previa:**")
        st.markdown(f'<iframe src="data:application/pdf;base64,{b64_pdf}" width="100%" height="500px"></iframe>',
                    unsafe_allow_html=True)


# ─────────────────────────────────────────
# GUARDAR PLAN
# ─────────────────────────────────────────
st.markdown("---")
st.subheader("Guardar plan")

col1, col2 = st.columns(2)
with col1:
    fecha_vigencia = st.date_input("Vigente hasta",
                                    value=date.today() + timedelta(days=30),
                                    key="fecha_vig_final")
with col2:
    estado_plan = st.selectbox("Estado", ["activo", "borrador"])

ultima_version = run_query("""
    SELECT COALESCE(MAX(version), 0) AS v
    FROM planes_nutricionales WHERE id_paciente = %s
""", (id_paciente,))
nueva_version = ultima_version[0]["v"] + 1

st.info(f"Este será el **Plan v{nueva_version}** para {nombre_paciente}.")

archivo_url = None
if modo == "Subir PDF" and "archivo" in dir() and archivo:
    archivo_url = f"uploads/{archivo.name}"

if st.button("Guardar plan nutricional",
             use_container_width=True,
             type="primary",
             disabled=not contenido_plan):
    try:
        id_contrato = contrato[0]["id_contrato"] if contrato else None

        if estado_plan == "activo":
            run_command("""
                UPDATE planes_nutricionales
                SET estado = 'reemplazado'
                WHERE id_paciente = %s AND estado = 'activo'
            """, (id_paciente,))

        run_command("""
            INSERT INTO planes_nutricionales
                (id_paciente, id_contrato, id_nutricionista,
                 version, contenido, estado,
                 fecha_vigencia, archivo_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (id_paciente, id_contrato, id_nutri,
              nueva_version, contenido_plan,
              estado_plan, fecha_vigencia, archivo_url))

        st.success(f"Plan v{nueva_version} guardado correctamente.")

        if st.button("← Volver a la ficha del paciente"):
            st.switch_page("pages/3_ficha_paciente.py")

    except Exception as e:
        st.error(f"Error al guardar: {e}")