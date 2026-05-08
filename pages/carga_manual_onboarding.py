import json
from datetime import date

import streamlit as st
from database import run_query, run_command
from utils import mostrar_sidebar, page_header

st.set_page_config(page_title="Carga manual de formulario", layout="wide")

if "usuario" not in st.session_state:
    st.warning("Debés iniciar sesión.")
    st.stop()

usuario = st.session_state["usuario"]
if usuario["rol"] not in ("administrador", "nutricionista"):
    st.error("No tenés permisos.")
    st.stop()

mostrar_sidebar()
page_header("Carga manual de formulario", "Carga las respuestas de un formulario externo (Tally u otro)")

st.info("Usa esta sección cuando el paciente completó el formulario fuera del sistema (Tally, papel, etc.) y querés registrar sus datos manualmente.")

# ── Selección de paciente ──
st.markdown("### 1. Selecciona el paciente")

pacientes = run_query("""
    SELECT p.id_paciente,
           p.nombre || ' ' || p.apellido AS nombre,
           p.email, p.tipo_paciente
    FROM pacientes p
    ORDER BY p.apellido, p.nombre
""")

if not pacientes:
    st.warning("No hay pacientes registrados.")
    st.stop()

pac_opts = {f"{p['nombre']} ({p['email'] or 'sin email'})": p for p in pacientes}
pac_sel_key = st.selectbox("Paciente", list(pac_opts.keys()))
paciente = pac_opts[pac_sel_key]
id_paciente = paciente["id_paciente"]

# ── Selección de formulario ──
st.markdown("### 2. Selecciona el formulario")

formularios = run_query("""
    SELECT id_formulario, nombre, tipo_formulario
    FROM formularios_onboarding
    WHERE activo = TRUE
    ORDER BY nombre
""")

if not formularios:
    st.warning("No hay formularios configurados.")
    st.stop()

form_opts = {f"{f['nombre']} ({f['tipo_formulario']})": f for f in formularios}
form_sel_key = st.selectbox("Formulario", list(form_opts.keys()))
formulario = form_opts[form_sel_key]
id_formulario = formulario["id_formulario"]

# Cargar estructura del formulario
form_data = run_query("""
    SELECT estructura_json FROM formularios_onboarding
    WHERE id_formulario = %s
""", (id_formulario,))[0]

estructura = form_data["estructura_json"]
if isinstance(estructura, str):
    estructura = json.loads(estructura)

secciones = estructura.get("secciones", [])

st.markdown("---")
st.markdown("### 3. Completa las respuestas")
st.caption("Completa los campos según las respuestas que dio el paciente en el formulario externo.")

respuestas = {}

for seccion in secciones:
    with st.expander(f"{seccion['titulo']}", expanded=True):
        for preg in seccion.get("preguntas", []):
            pid    = preg["id"]
            label  = preg["label"]
            tipo   = preg["tipo"]
            opts   = preg.get("opciones", [])
            key    = f"manual_{pid}"

            if tipo in ("text", "email"):
                respuestas[pid] = st.text_input(label, key=key)

            elif tipo == "textarea":
                respuestas[pid] = st.text_area(label, height=100, key=key)

            elif tipo == "number":
                v = st.number_input(label, min_value=0.0, step=0.1, key=key)
                respuestas[pid] = v if v > 0 else None

            elif tipo == "date":
                v = st.date_input(label, value=date(1990,1,1),
                                  min_value=date(1920,1,1),
                                  max_value=date.today(), key=key)
                respuestas[pid] = str(v)

            elif tipo == "scale":
                mn = preg.get("min", 1); mx = preg.get("max", 5)
                respuestas[pid] = st.slider(label, mn, mx, mn, key=key)

            elif tipo == "select_one":
                respuestas[pid] = st.selectbox(label, ["(Sin respuesta)"] + opts, key=key)
                if respuestas[pid] == "(Sin respuesta)":
                    respuestas[pid] = None

            elif tipo in ("multi_select", "checkbox_multiple"):
                respuestas[pid] = st.multiselect(label, opts, key=key)

            elif tipo == "checkbox":
                respuestas[pid] = st.checkbox(label, key=key)

            elif tipo == "file":
                st.caption(f"📎 {label} — adjuntá el archivo por separado si es necesario.")
                respuestas[pid] = st.text_input(f"Referencia del archivo (opcional)", key=key)

st.markdown("---")
st.markdown("### 4. Preferencia de turno")
preferencia_turno = st.text_area(
    "Preferencia de día y horario para la primera sesión (si el paciente la indicó)",
    height=100,
    placeholder="Ej: prefiere las mañanas, disponible lunes y miércoles..."
)

st.markdown("---")

col1, col2 = st.columns(2)
with col2:
    if st.button("Guardar respuestas en el sistema", use_container_width=True, type="primary"):
        try:
            resp_json = dict(respuestas)
            resp_json["_preferencia_turno"] = preferencia_turno
            resp_json["_cargado_manualmente_por"] = f"{usuario['nombre']} {usuario['apellido']}"

            run_command("""
                INSERT INTO onboarding_respuestas
                    (id_link, id_formulario, id_paciente, respuestas_json, estado)
                VALUES (NULL, %s, %s, %s::jsonb, 'completo')
            """, (id_formulario, id_paciente,
                  json.dumps(resp_json, ensure_ascii=False, default=str)))

            # Detectar tipo de formulario para mapear bien los campos básicos.
            tipo_formulario = formulario.get("tipo_formulario") or "persona"
            nombre   = respuestas.get("1_1", "")
            apellido = respuestas.get("1_2", "")
            dni      = respuestas.get("1_3", "")

            if tipo_formulario == "empresa":
                celular = ""
                fecha_nac = respuestas.get("1_4")
                genero = respuestas.get("1_5", "")
                email = respuestas.get("1_6", "")
                tipo_paciente = "empresa"
            else:
                celular = respuestas.get("1_4", "")
                fecha_nac = respuestas.get("1_5")
                genero = ""
                email = respuestas.get("1_7", "")
                tipo_paciente = "persona"

            run_command("""
                UPDATE pacientes SET
                    nombre           = COALESCE(NULLIF(%s,''), nombre),
                    apellido         = COALESCE(NULLIF(%s,''), apellido),
                    dni              = COALESCE(NULLIF(%s,''), dni),
                    telefono         = COALESCE(NULLIF(%s,''), telefono),
                    fecha_nacimiento = COALESCE(%s::date, fecha_nacimiento),
                    genero           = COALESCE(NULLIF(%s,''), genero),
                    email            = COALESCE(NULLIF(%s,''), email),
                    tipo_paciente    = COALESCE(NULLIF(%s,''), tipo_paciente),
                    onboarding_paso  = 5
                WHERE id_paciente = %s
            """, (nombre, apellido, dni, celular, fecha_nac, genero, email, tipo_paciente, id_paciente))

            # Guardar mediciones numéricas en historia_nutricional, que queda como fuente única
            # para evolución + infografía. Si no hay mediciones, no se inserta historia.
            def _to_float(v):
                try:
                    if v in (None, "", "None"):
                        return None
                    return float(v)
                except Exception:
                    return None

            peso = _to_float(respuestas.get("8_2"))
            talla = _to_float(respuestas.get("8_1"))
            per_torax = _to_float(respuestas.get("8_3"))
            per_brazo = _to_float(respuestas.get("8_4"))
            per_cintura = _to_float(respuestas.get("8_5"))
            per_abdomen = _to_float(respuestas.get("8_6"))
            per_cadera = _to_float(respuestas.get("8_7"))

            if any(v is not None for v in [peso, talla, per_torax, per_brazo, per_cintura, per_abdomen, per_cadera]):
                prox = run_query("""
                    SELECT COALESCE(MAX(version), 0) + 1 AS version
                    FROM historia_nutricional
                    WHERE id_paciente = %s
                """, (id_paciente,))
                version_hist = int(prox[0]["version"] or 1)
                imc = round(peso / ((talla / 100) ** 2), 2) if peso and talla else None

                run_command("""
                    INSERT INTO historia_nutricional
                        (id_paciente, id_sesion, version, peso, talla, imc,
                         circ_cintura, circ_cadera, circ_brazo,
                         perimetro_torax, perimetro_abdominal,
                         fuente_datos, notas_medicion, creado_por)
                    VALUES (%s,NULL,%s,%s,%s,%s,%s,%s,%s,%s,%s,'carga_manual',%s,%s)
                """, (
                    id_paciente, version_hist, peso, talla, imc,
                    per_cintura, per_cadera, per_brazo, per_torax, per_abdomen,
                    "Medición cargada manualmente desde formulario externo",
                    usuario.get("id_usuario"),
                ))

            st.success(f"Respuestas de {paciente['nombre']} guardadas correctamente.")
            st.info("Las respuestas completas quedaron en onboarding_respuestas; las mediciones se registraron en historia_nutricional si estaban presentes.")

        except Exception as e:
            st.error(f"Error al guardar: {e}")

with col1:
    st.caption("Los datos se guardarán en onboarding_respuestas y actualizarán el perfil del paciente.")
