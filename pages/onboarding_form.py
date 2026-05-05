import json
from datetime import date

import streamlit as st

try:
    from dateutil.relativedelta import relativedelta
    DATEUTIL = True
except ImportError:
    DATEUTIL = False

from database import run_query, run_command

st.set_page_config(
    page_title="Formulario de onboarding",
    page_icon="🥗",
    layout="centered"
)

# ═══════════════════════════════════════════════════════════
# ESTILOS
# ═══════════════════════════════════════════════════════════
def inject_styles():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    * { font-family: 'Inter', sans-serif !important; box-sizing: border-box; }

    /* Layout */
    .stApp { background: #F9FAFB !important; }
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding: 0 !important; max-width: 100% !important; }
    section[data-testid="stSidebar"] { display: none !important; }

    /* Barra progreso */
    .tf-bar {
        position: fixed; top: 0; left: 0; height: 4px;
        background: #00DC8E; z-index: 9999;
        transition: width 0.5s ease;
    }

    /* Wrapper */
    .tf-page {
        max-width: 700px; margin: 0 auto;
        padding: 56px 28px 80px 28px; min-height: 100vh;
    }

    /* Welcome */
    .tf-welcome-tag {
        display: inline-block;
        background: rgba(0,220,142,0.13);
        color: #00875a; font-size: 12px; font-weight: 700;
        letter-spacing: 0.1em; text-transform: uppercase;
        padding: 5px 14px; border-radius: 999px; margin-bottom: 20px;
    }
    .tf-welcome-title {
        font-size: 36px; font-weight: 800; color: #111827;
        line-height: 1.15; margin-bottom: 16px;
    }
    .tf-welcome-sub {
        font-size: 17px; color: #374151; line-height: 1.7;
        margin-bottom: 14px;
    }
    .tf-welcome-note {
        font-size: 13px; color: #6B7280;
        background: #F3F4F6; border-radius: 10px;
        padding: 12px 16px; margin: 20px 0 28px 0;
        line-height: 1.6;
    }

    /* Sección */
    .tf-section-num {
        font-size: 12px; font-weight: 700; color: #00DC8E;
        letter-spacing: 0.12em; text-transform: uppercase;
        margin-bottom: 6px;
    }
    .tf-section-title {
        font-size: 26px; font-weight: 800; color: #111827;
        line-height: 1.2; margin-bottom: 32px; padding-bottom: 14px;
        border-bottom: 2px solid #F3F4F6;
    }

    /* Pregunta */
    .tf-q-label {
        font-size: 16px; font-weight: 700; color: #111827;
        margin-bottom: 12px; line-height: 1.45;
    }
    .tf-q-instruc {
        font-size: 13px; color: #6B7280; line-height: 1.6;
        background: #F9FAFB; border-left: 3px solid #00DC8E;
        border-radius: 0 8px 8px 0; padding: 10px 14px;
        margin-bottom: 12px;
    }

    /* Inputs */
    div[data-testid="stTextInput"] input,
    div[data-testid="stNumberInput"] input,
    div[data-testid="stDateInput"] input,
    div[data-testid="stTextArea"] textarea {
        border-radius: 10px !important;
        border: 1.5px solid #D1D5DB !important;
        font-size: 15px !important;
        padding: 11px 14px !important;
        background: #fff !important;
        color: #111827 !important;
    }
    div[data-testid="stTextInput"] input:focus,
    div[data-testid="stNumberInput"] input:focus,
    div[data-testid="stTextArea"] textarea:focus {
        border-color: #00DC8E !important;
        box-shadow: 0 0 0 3px rgba(0,220,142,0.15) !important;
    }
    div[data-testid="stTextInput"] label p,
    div[data-testid="stNumberInput"] label p,
    div[data-testid="stDateInput"] label p,
    div[data-testid="stTextArea"] label p {
        font-size: 14px !important; font-weight: 600 !important;
        color: #374151 !important; margin-bottom: 6px !important;
    }

    /* Radio — estilo tarjeta */
    div[data-testid="stRadio"] > div {
        display: flex; flex-direction: column; gap: 8px;
    }
    div[data-testid="stRadio"] label {
        background: #fff; border: 1.5px solid #E5E7EB;
        border-radius: 10px; padding: 12px 16px !important;
        cursor: pointer; transition: all 0.15s;
        font-size: 15px !important; font-weight: 500 !important;
        color: #374151 !important;
    }
    div[data-testid="stRadio"] label:has(input:checked) {
        border-color: #00DC8E !important;
        background: rgba(0,220,142,0.07) !important;
        color: #00875a !important; font-weight: 600 !important;
    }
    div[data-testid="stRadio"] label p {
        font-size: 15px !important; font-weight: 500 !important;
    }
    div[data-testid="stRadio"] > label { display: none !important; }

    /* Checkbox */
    div[data-testid="stCheckbox"] label {
        font-size: 15px !important; font-weight: 500 !important;
        color: #374151 !important; cursor: pointer;
    }
    div[data-testid="stCheckbox"]:has(input:checked) label {
        color: #00875a !important; font-weight: 600 !important;
    }

    /* Slider */
    div[data-testid="stSlider"] > div > div > div {
        color: #00DC8E !important;
    }

    /* Botones */
    button[kind="primary"],
    div[data-testid="stFormSubmitButton"] button {
        border-radius: 10px !important;
        background: #00DC8E !important; color: #fff !important;
        font-weight: 700 !important; font-size: 16px !important;
        min-height: 50px !important; border: none !important;
        letter-spacing: 0.01em !important;
    }
    button[kind="primary"]:hover { background: #00c47e !important; }
    button[kind="secondary"] {
        border-radius: 10px !important; min-height: 50px !important;
        font-size: 15px !important; font-weight: 600 !important;
        border: 1.5px solid #E5E7EB !important;
        background: #fff !important; color: #374151 !important;
    }
    button[kind="secondary"]:hover { border-color: #00DC8E !important; }

    /* Separador */
    .tf-sep { height: 1px; background: #F3F4F6; margin: 24px 0; }

    /* Pantalla final */
    .tf-end { text-align: center; padding: 48px 0; }
    .tf-end-icon { font-size: 60px; margin-bottom: 16px; }
    .tf-end-title { font-size: 30px; font-weight: 800; color: #111827; margin-bottom: 12px; }
    .tf-end-sub { font-size: 16px; color: #6B7280; line-height: 1.7; }

    /* Back link */
    .tf-back { font-size: 13px; color: #9CA3AF; cursor: pointer;
               margin-bottom: 32px; display: inline-flex; align-items: center; gap: 4px; }
    .tf-back:hover { color: #00DC8E; }
    </style>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════
def calcular_edad(fecha_str):
    if not fecha_str:
        return None
    try:
        fn = date.fromisoformat(str(fecha_str))
        if DATEUTIL:
            from dateutil.relativedelta import relativedelta
            return relativedelta(date.today(), fn).years
        else:
            hoy = date.today()
            return hoy.year - fn.year - ((hoy.month, hoy.day) < (fn.month, fn.day))
    except Exception:
        return None


def es_visible(item, respuestas):
    vis = item.get("visible_si")
    if not vis:
        return True
    if "edad_menor_que" in vis:
        edad = calcular_edad(respuestas.get("1_5") or respuestas.get("1_4"))
        return edad is not None and edad < vis["edad_menor_que"]
    if "edad_mayor_que" in vis:
        edad = calcular_edad(respuestas.get("1_5") or respuestas.get("1_4"))
        return edad is None or edad > vis["edad_mayor_que"]
    if "pregunta" in vis:
        val = respuestas.get(vis["pregunta"])
        if "valor" in vis:
            return val == vis["valor"]
        if "valor_en" in vis:
            return val in vis["valor_en"]
        if "incluye" in vis:
            return isinstance(val, list) and vis["incluye"] in val
    return True


def render_pregunta(preg, respuestas, key_prefix):
    pid = preg["id"]
    label = preg["label"]
    tipo = preg["tipo"]
    obligatoria = preg.get("obligatoria", False)
    instrucciones = preg.get("instrucciones")
    key = f"{key_prefix}_{pid}"
    sufijo = " *" if obligatoria else ""
    val_actual = respuestas.get(pid)

    if instrucciones:
        st.markdown(f'<div class="tf-q-instruc">{instrucciones}</div>', unsafe_allow_html=True)

    if tipo == "text":
        return st.text_input(label + sufijo, value=val_actual or "", key=key)
    elif tipo == "email":
        return st.text_input(label + sufijo, value=val_actual or "",
                             placeholder="ejemplo@correo.com", key=key)
    elif tipo == "textarea":
        return st.text_area(label + sufijo, value=val_actual or "", height=120, key=key)
    elif tipo == "number":
        v = st.number_input(label + sufijo, min_value=0.0, step=0.1,
                            value=float(val_actual) if val_actual else 0.0, key=key)
        return v if v > 0 else None
    elif tipo == "date":
        try:
            vd = date.fromisoformat(str(val_actual)) if val_actual else date(1990, 1, 1)
        except Exception:
            vd = date(1990, 1, 1)
        r = st.date_input(label + sufijo, value=vd,
                          min_value=date(1920, 1, 1), max_value=date.today(), key=key)
        return str(r) if r else None
    elif tipo == "scale":
        mn = preg.get("min", 1); mx = preg.get("max", 5)
        opts = [str(i) for i in range(mn, mx + 1)]
        nota_min = preg.get("nota_min", ""); nota_max = preg.get("nota_max", "")
        st.markdown(f'<div class="tf-q-label">{label + sufijo}</div>', unsafe_allow_html=True)
        if nota_min or nota_max:
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;font-size:12px;color:#9CA3AF;margin-bottom:4px">'
                f'<span>{nota_min}</span><span>{nota_max}</span></div>',
                unsafe_allow_html=True
            )
        idx = 0
        if val_actual:
            try: idx = opts.index(str(val_actual))
            except: idx = 0
        sel = st.select_slider("", options=opts, value=opts[idx],
                               key=key, label_visibility="collapsed")
        return int(sel)
    elif tipo == "select_one":
        opts = preg.get("opciones", [])
        idx = 0
        if val_actual and val_actual in opts:
            idx = opts.index(val_actual)
        return st.radio(label + sufijo, opts, index=idx, key=key)
    elif tipo == "multi_select":
        opts = preg.get("opciones", [])
        sel = val_actual if isinstance(val_actual, list) else []
        st.markdown(f'<div class="tf-q-label">{label + sufijo}</div>', unsafe_allow_html=True)
        resultado = []
        for op in opts:
            if st.checkbox(op, value=op in sel, key=f"{key}_{op}"):
                resultado.append(op)
        return resultado
    elif tipo == "checkbox":
        return st.checkbox(label + sufijo, value=bool(val_actual), key=key)
    elif tipo == "checkbox_multiple":
        opts = preg.get("opciones", [])
        sel = val_actual if isinstance(val_actual, list) else []
        req_todos = preg.get("requiere_todos", False)
        st.markdown(f'<div class="tf-q-label">{label + sufijo}</div>', unsafe_allow_html=True)
        if req_todos:
            st.caption("Debés aceptar todos para continuar.")
        resultado = []
        for op in opts:
            if st.checkbox(op, value=op in sel, key=f"{key}_{op}"):
                resultado.append(op)
        return resultado
    elif tipo == "file":
        st.markdown(f'<div class="tf-q-label">{label + sufijo}</div>', unsafe_allow_html=True)
        up = st.file_uploader("", key=key, type=["pdf", "jpg", "jpeg", "png"],
                              label_visibility="collapsed")
        return f"[archivo: {up.name}]" if up else val_actual
    return None


def validar_seccion(seccion, respuestas):
    errores = []
    for preg in seccion.get("preguntas", []):
        if not es_visible(preg, respuestas):
            continue
        if not preg.get("obligatoria"):
            continue
        pid = preg["id"]
        val = respuestas.get(pid)
        tipo = preg["tipo"]
        if tipo == "checkbox_multiple" and preg.get("requiere_todos"):
            if not val or len(val) < len(preg.get("opciones", [])):
                errores.append(f"Debés aceptar todos los compromisos: {preg['label'][:50]}")
        elif tipo == "checkbox":
            if not val:
                errores.append(f"Campo requerido: {preg['label'][:60]}")
        elif tipo == "multi_select":
            if not val:
                errores.append(f"Seleccioná al menos una opción: {preg['label'][:50]}")
        elif tipo == "number":
            if not val or val == 0.0:
                errores.append(f"Campo requerido: {preg['label'][:60]}")
        elif not val and val != 0:
            errores.append(f"Campo requerido: {preg['label'][:60]}")
    return errores


# ═══════════════════════════════════════════════════════════
# GUARDAR
# ═══════════════════════════════════════════════════════════
def guardar_respuestas(id_paciente, id_formulario, id_link, respuestas, preferencia_turno):
    resp = dict(respuestas)
    resp["_preferencia_turno"] = preferencia_turno

    run_command("""
        INSERT INTO onboarding_respuestas
            (id_link, id_formulario, id_paciente, respuestas_json, estado)
        VALUES (%s, %s, %s, %s::jsonb, 'completo')
    """, (id_link if id_link and id_link > 0 else None,
          id_formulario, id_paciente,
          json.dumps(resp, ensure_ascii=False, default=str)))

    # Actualizar paciente con datos básicos
    # Soporta ambos formularios (persona: 1_1..1_7 / empresa: 1_1..1_6)
    nombre   = respuestas.get("1_1", "")
    apellido = respuestas.get("1_2", "")
    dni      = respuestas.get("1_3", "")
    celular  = respuestas.get("1_4", "")
    # En empresa, fecha nac es 1_4 y celular no existe separado
    fecha_nac = respuestas.get("1_5") or respuestas.get("1_4")
    email     = respuestas.get("1_7") or respuestas.get("1_6", "")

    run_command("""
        UPDATE pacientes SET
            nombre           = COALESCE(NULLIF(%s,''), nombre),
            apellido         = COALESCE(NULLIF(%s,''), apellido),
            dni              = COALESCE(NULLIF(%s,''), dni),
            telefono         = COALESCE(NULLIF(%s,''), telefono),
            fecha_nacimiento = COALESCE(%s::date, fecha_nacimiento),
            email            = COALESCE(NULLIF(%s,''), email),
            onboarding_paso  = 5
        WHERE id_paciente = %s
    """, (nombre, apellido, dni, celular, fecha_nac, email, id_paciente))

    # Anamnesis
    objetivo = respuestas.get("2_1") or respuestas.get("3_4", "")
    if respuestas.get("2_1_otro"):
        objetivo += f" — {respuestas['2_1_otro']}"
    if respuestas.get("3_4_otro"):
        objetivo += f" — {respuestas['3_4_otro']}"

    enf_txt = "; ".join(filter(None, [
        respuestas.get("2_2_detalle") or respuestas.get("3_1_detalle"),
        respuestas.get("2_3_detalle"),
    ]))
    alerg_txt = ("; ".join(respuestas.get("3_3_1", [])) or
                 respuestas.get("3_3_detalle") or "")
    intol_txt = ("; ".join(respuestas.get("3_4_1", [])) or
                 respuestas.get("3_3_detalle") or "")
    alerg_intol = "; ".join(filter(None, [alerg_txt, intol_txt]))

    act_map = {
        "No realizo": "sedentario", "No realizo actividad física": "sedentario",
        "Ligera (1 a 2 veces semanales)": "leve",
        "1 a 2 veces por semana": "leve",
        "Moderada (3 a 4 veces semanales)": "moderado",
        "3 a 4 veces por semana": "moderado",
        "Intensa (5 veces semanales)": "intenso",
        "5 o más veces por semana": "intenso",
        "Soy deportista de alto rendimiento": "muy_intenso",
    }
    actividad = act_map.get(respuestas.get("4_4") or respuestas.get("4_6", ""), "sedentario")

    estres_raw = respuestas.get("4_3")
    if isinstance(estres_raw, int):
        estres_map = {1:"bajo",2:"bajo",3:"moderado",4:"alto",5:"muy_alto"}
        nivel_estres = estres_map.get(estres_raw, "moderado")
    else:
        nivel_estres = "moderado"

    horas_map = {
        "Menos de 4 horas": 3, "Menos de 6 horas": 5,
        "4 a 8 horas": 6, "6 a 8 horas": 7,
        "8 a 10 horas": 9, "Más de 10 horas": 11,
    }
    horas = horas_map.get(respuestas.get("4_1_1") or respuestas.get("2_5", ""))

    contrato = run_query("""
        SELECT id_contrato FROM contratos
        WHERE id_paciente = %s AND estado IN ('activo','pendiente_pago')
        ORDER BY fecha_creacion DESC LIMIT 1
    """, (id_paciente,))
    id_contrato = contrato[0]["id_contrato"] if contrato else None

    try:
        run_command("""
            INSERT INTO anamnesis
                (id_paciente, id_contrato, objetivo_principal, enfermedades,
                 alergias_intolerancias, actividad_fisica, tipo_trabajo,
                 horas_trabajo, nivel_estres, observaciones, version, estado)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,'completa')
        """, (id_paciente, id_contrato, objetivo, enf_txt, alerg_intol,
              actividad,
              respuestas.get("4_2") or respuestas.get("2_4", ""),
              horas, nivel_estres, preferencia_turno or ""))
    except Exception:
        pass  # puede ya existir anamnesis

    # Historia nutricional (solo si hay medidas — formulario virtual persona)
    peso  = respuestas.get("8_2")
    talla = respuestas.get("8_1")
    if peso and talla and float(peso) > 0 and float(talla) > 0:
        imc = round(float(peso) / ((float(talla) / 100) ** 2), 2)
        try:
            run_command("""
                INSERT INTO historia_nutricional
                    (id_paciente, version, peso, talla, imc,
                     circ_cintura, circ_cadera, circ_brazo, fuente_datos)
                VALUES (%s,1,%s,%s,%s,%s,%s,%s,'formulario_inicial')
            """, (id_paciente, float(peso), float(talla), imc,
                  float(respuestas.get("8_5") or 0) or None,
                  float(respuestas.get("8_7") or 0) or None,
                  float(respuestas.get("8_4") or 0) or None))
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════
# MAIN — resolver modo y cargar formulario
# ═══════════════════════════════════════════════════════════
inject_styles()

params = st.query_params
token  = params.get("token")

modo_interno       = "usuario" in st.session_state and not token
id_paciente_actual = None
id_formulario_actual = None
id_link_actual     = None
nombre_form        = "Historia Nutricional"
bienvenida         = None

if modo_interno:
    usuario = st.session_state["usuario"]
    if usuario["rol"] != "paciente":
        st.switch_page("app.py")
    id_paciente_actual = usuario["id_paciente"]
    row = run_query("""
        SELECT id_formulario, nombre, estructura_json
        FROM formularios_onboarding
        WHERE tipo_formulario = 'persona' AND activo = TRUE
        ORDER BY fecha_creacion DESC LIMIT 1
    """)
    if not row:
        st.error("No hay formulario configurado. Contactá al administrador.")
        st.stop()
    form = row[0]
    id_formulario_actual = form["id_formulario"]
    nombre_form = form["nombre"]
    estructura  = form["estructura_json"]
    id_link_actual = -1

elif token:
    row = run_query("""
        SELECT ol.id_link, ol.id_formulario, ol.id_paciente,
               fo.nombre, fo.estructura_json
        FROM onboarding_links ol
        JOIN formularios_onboarding fo ON ol.id_formulario = fo.id_formulario
        WHERE ol.token = %s AND ol.activo = TRUE
          AND (ol.fecha_vencimiento IS NULL OR ol.fecha_vencimiento > NOW())
    """, (token,))
    if not row:
        st.error("Este link no es válido o ya expiró.")
        st.stop()
    link = row[0]
    estructura           = link["estructura_json"]
    id_paciente_actual   = link.get("id_paciente")
    id_formulario_actual = link["id_formulario"]
    id_link_actual       = link["id_link"]
    nombre_form          = link["nombre"]
else:
    st.warning("Acceso no válido. Usá el link que te enviaron.")
    st.stop()

if isinstance(estructura, str):
    estructura = json.loads(estructura)

secciones  = estructura.get("secciones", [])
bienvenida = estructura.get("bienvenida")

# ── Estado ──
if "tf_paso" not in st.session_state:
    # -1 = pantalla bienvenida, 0..n = secciones, 999 = preferencia turno
    st.session_state["tf_paso"] = -1 if bienvenida else 0
if "tf_resp" not in st.session_state:
    st.session_state["tf_resp"] = {}
if "tf_ok" not in st.session_state:
    st.session_state["tf_ok"] = False

resp = st.session_state["tf_resp"]
paso = st.session_state["tf_paso"]

# Secciones visibles según respuestas actuales
secc_vis = [(i, s) for i, s in enumerate(secciones) if es_visible(s, resp)]
total_pasos = len(secc_vis) + 1  # + preferencia turno

# Calcular progreso
if paso == -1:
    pct = 0
elif paso == 999:
    pct = 95
else:
    pos = next((p for p, (i, _) in enumerate(secc_vis) if i == paso), 0)
    pct = int((pos + 1) / total_pasos * 90)

st.markdown(f'<div class="tf-bar" style="width:{pct}%"></div>', unsafe_allow_html=True)
st.markdown('<div class="tf-page">', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════
# PANTALLA FINAL
# ═══════════════════════════════════════════════════════════
if st.session_state["tf_ok"]:
    st.markdown("""
    <div class="tf-end">
      <div class="tf-end-icon">✅</div>
      <div class="tf-end-title">¡Todo listo!</div>
      <div class="tf-end-sub">
        Tu formulario fue enviado correctamente.<br>
        Tu nutricionista se pondrá en contacto para coordinar
        tu primera sesión según tus preferencias.<br><br>
        <strong>¡Bienvenido/a al programa!</strong>
      </div>
    </div>
    """, unsafe_allow_html=True)
    if modo_interno:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Ir a mi cuenta →", use_container_width=True, type="primary"):
            st.switch_page("app.py")
    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# ═══════════════════════════════════════════════════════════
# PANTALLA BIENVENIDA
# ═══════════════════════════════════════════════════════════
if paso == -1 and bienvenida:
    st.markdown(
        f'<div class="tf-welcome-tag">{nombre_form}</div>',
        unsafe_allow_html=True
    )
    st.markdown(
        f'<div class="tf-welcome-title">{bienvenida.get("titulo","Bienvenido/a")}</div>',
        unsafe_allow_html=True
    )
    if bienvenida.get("subtitulo"):
        st.markdown(
            f'<div class="tf-welcome-sub">{bienvenida["subtitulo"]}</div>',
            unsafe_allow_html=True
        )
    if bienvenida.get("descripcion"):
        st.markdown(
            f'<div class="tf-welcome-sub">{bienvenida["descripcion"]}</div>',
            unsafe_allow_html=True
        )
    if bienvenida.get("nota_privacidad"):
        st.markdown(
            f'<div class="tf-welcome-note">{bienvenida["nota_privacidad"]}</div>',
            unsafe_allow_html=True
        )
    if bienvenida.get("cta"):
        st.markdown(
            f'<div class="tf-welcome-sub" style="color:#00875a;font-weight:600">{bienvenida["cta"]}</div>',
            unsafe_allow_html=True
        )
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button(bienvenida.get("boton", "Comenzar →"), use_container_width=True, type="primary"):
        st.session_state["tf_paso"] = secc_vis[0][0] if secc_vis else 999
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# ═══════════════════════════════════════════════════════════
# PANTALLA PREFERENCIA DE TURNO
# ═══════════════════════════════════════════════════════════
if paso == 999:
    st.markdown('<div class="tf-section-num">Último paso</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="tf-section-title">Preferencia para tu primera sesión</div>',
        unsafe_allow_html=True
    )
    st.markdown("""
    <div style="font-size:15px;color:#4B5563;line-height:1.7;margin-bottom:24px">
    Tu nutricionista te asignará un turno personalmente.
    Contanos qué días y horarios te vienen mejor para que pueda encontrar el momento ideal para vos.
    </div>
    """, unsafe_allow_html=True)

    pref = st.text_area(
        "¿Qué días y horarios preferís? ¿Alguna otra preferencia o comentario?",
        value=resp.get("_pref_turno", ""), height=140,
        placeholder="Ej: prefiero las mañanas de lunes a miércoles, o cualquier tarde del viernes...",
        key="tf_pref"
    )

    st.markdown('<div class="tf-sep"></div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("← Volver", use_container_width=True, key="btn_volver_pref"):
            st.session_state["tf_paso"] = secc_vis[-1][0] if secc_vis else 0
            st.rerun()
    with c2:
        if st.button("Enviar formulario ✓", use_container_width=True, type="primary", key="btn_enviar"):
            resp["_pref_turno"] = pref
            try:
                guardar_respuestas(id_paciente_actual, id_formulario_actual,
                                   id_link_actual, resp, pref)
                st.session_state["tf_ok"] = True
                st.rerun()
            except Exception as e:
                st.error(f"Error al guardar: {e}")

    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# ═══════════════════════════════════════════════════════════
# SECCIÓN ACTUAL
# ═══════════════════════════════════════════════════════════
pos_actual = next((p for p, (i, _) in enumerate(secc_vis) if i == paso), 0)
_, seccion = secc_vis[pos_actual]

# Back link
if pos_actual > 0 or bienvenida:
    if st.button("← Atrás", key="btn_back_top"):
        if pos_actual > 0:
            st.session_state["tf_paso"] = secc_vis[pos_actual - 1][0]
        elif bienvenida:
            st.session_state["tf_paso"] = -1
        st.rerun()

# Header
st.markdown(
    f'<div class="tf-section-num">Sección {pos_actual + 1} de {len(secc_vis)}</div>',
    unsafe_allow_html=True
)
st.markdown(
    f'<div class="tf-section-title">{seccion["titulo"]}</div>',
    unsafe_allow_html=True
)

# Preguntas
for preg in seccion.get("preguntas", []):
    if not es_visible(preg, resp):
        continue
    pid = preg["id"]
    val = render_pregunta(preg, resp, key_prefix=f"s{paso}")
    if val is not None:
        resp[pid] = val
        st.session_state["tf_resp"][pid] = val
    st.markdown('<div style="margin-bottom:18px"></div>', unsafe_allow_html=True)

st.markdown('<div class="tf-sep"></div>', unsafe_allow_html=True)

# Navegación
es_ultima = pos_actual == len(secc_vis) - 1
c1, c2 = st.columns(2)

with c1:
    if pos_actual > 0:
        if st.button("← Anterior", use_container_width=True, key="btn_ant"):
            st.session_state["tf_paso"] = secc_vis[pos_actual - 1][0]
            st.rerun()

with c2:
    lbl = "Siguiente →" if not es_ultima else "Continuar →"
    if st.button(lbl, use_container_width=True, type="primary", key="btn_sig"):
        errores = validar_seccion(seccion, st.session_state["tf_resp"])
        if errores:
            for e in errores:
                st.error(e)
        else:
            # Recalcular secciones visibles con respuestas actualizadas
            sv_nuevo = [(i, s) for i, s in enumerate(secciones)
                        if es_visible(s, st.session_state["tf_resp"])]
            p_nuevo = next((p for p, (i, _) in enumerate(sv_nuevo) if i == paso), 0)
            if p_nuevo + 1 < len(sv_nuevo):
                st.session_state["tf_paso"] = sv_nuevo[p_nuevo + 1][0]
            else:
                st.session_state["tf_paso"] = 999
            st.rerun()

st.markdown('</div>', unsafe_allow_html=True)
