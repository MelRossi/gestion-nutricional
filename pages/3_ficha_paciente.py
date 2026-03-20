import streamlit as st
import pandas as pd
from database import run_query, run_command
from datetime import date
from utils import mostrar_sidebar

# ─────────────────────────────────────────
# CONTROL DE ACCESO
# ─────────────────────────────────────────
if "usuario" not in st.session_state:
    st.warning("Debés iniciar sesión.")
    st.stop()

if st.session_state["usuario"]["rol"] not in ("administrador", "nutricionista", "paciente"):
    st.error("No tenés permisos.")
    st.stop()

usuario = st.session_state["usuario"]
rol     = usuario["rol"]

# ─────────────────────────────────────────
# FUNCIÓN ANAMNESIS
# ─────────────────────────────────────────
def mostrar_form_anamnesis(id_paciente, id_contrato, datos_existentes):
    es_nueva = datos_existentes is None
    d = datos_existentes or {}
    with st.form("form_anamnesis"):
        col1, col2 = st.columns(2)
        with col1:
            objetivo      = st.text_area("Objetivo principal",        value=d.get("objetivo_principal",""))
            antecedentes  = st.text_area("Antecedentes",              value=d.get("antecedentes",""))
            enfermedades  = st.text_area("Enfermedades",              value=d.get("enfermedades",""))
            medicamentos  = st.text_area("Medicamentos",              value=d.get("medicamentos",""))
            alergias      = st.text_area("Alergias / Intolerancias",  value=d.get("alergias_intolerancias",""))
            restricciones = st.text_area("Restricciones de dieta",    value=d.get("restricciones_dieta",""))
        with col2:
            habitos       = st.text_area("Hábitos alimentarios",      value=d.get("habitos_alimentarios",""))
            antec_dieta   = st.text_area("Antecedentes de dieta",     value=d.get("antecedentes_dieta",""))
            actividad     = st.text_input("Actividad física",         value=d.get("actividad_fisica",""))
            frec_act      = st.text_input("Frecuencia actividad",     value=d.get("frecuencia_actividad",""))
            tipo_trabajo  = st.text_input("Tipo de trabajo",          value=d.get("tipo_trabajo",""))
            horas_trab    = st.number_input("Horas trabajo/día", min_value=0, max_value=24, value=int(d.get("horas_trabajo") or 8))
            horas_sueno   = st.number_input("Horas sueño/día",   min_value=0, max_value=24, value=int(d.get("horas_sueno") or 7))
            consumo_agua  = st.number_input("Agua (litros/día)",  min_value=0.0, max_value=10.0, step=0.1, value=float(d.get("consumo_agua_litros") or 1.5))
            opciones_e    = ["bajo","moderado","alto","muy_alto"]
            idx_e         = opciones_e.index(d.get("nivel_estres","medio")) if d.get("nivel_estres") in opciones_e else 1
            nivel_estres  = st.selectbox("Nivel de estrés", opciones_e, index=idx_e)
            observaciones = st.text_area("Observaciones", value=d.get("observaciones",""))

        if st.form_submit_button("Guardar anamnesis", use_container_width=True):
            try:
                version = (d.get("version",0) + 1) if not es_nueva else 1
                run_command("""
                    INSERT INTO anamnesis
                        (id_paciente, id_contrato, objetivo_principal, antecedentes,
                         enfermedades, medicamentos, alergias_intolerancias,
                         habitos_alimentarios, restricciones_dieta, antecedentes_dieta,
                         actividad_fisica, frecuencia_actividad, tipo_trabajo,
                         horas_trabajo, horas_sueno, consumo_agua_litros,
                         nivel_estres, observaciones, version, estado)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'completa')
                """, (id_paciente, id_contrato, objetivo, antecedentes, enfermedades,
                      medicamentos, alergias, habitos, restricciones, antec_dieta,
                      actividad, frec_act, tipo_trabajo, horas_trab, horas_sueno,
                      consumo_agua, nivel_estres, observaciones, version))
                st.success(f"Anamnesis v{version} guardada.")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

# ─────────────────────────────────────────
# DETERMINAR PACIENTE
# ─────────────────────────────────────────
if rol == "paciente":
    id_paciente = usuario["id_paciente"]
elif "id_paciente_ficha" in st.session_state:
    id_paciente = st.session_state["id_paciente_ficha"]
else:
    if rol == "administrador":
        lista = run_query("SELECT id_paciente, nombre||' '||apellido AS nombre FROM pacientes WHERE estado='activo' ORDER BY apellido")
    else:
        lista = run_query("""
            SELECT DISTINCT p.id_paciente, p.nombre||' '||p.apellido AS nombre
            FROM pacientes p JOIN contratos c ON p.id_paciente=c.id_paciente
            WHERE c.id_nutricionista=%s AND c.estado='activo' ORDER BY nombre
        """, (usuario["id_nutricionista"],))
    if not lista:
        st.info("No hay pacientes disponibles.")
        st.stop()
    opciones    = {p["nombre"]: p["id_paciente"] for p in lista}
    sel         = st.selectbox("Seleccioná un paciente", list(opciones.keys()))
    id_paciente = opciones[sel]

if not id_paciente:
    st.error("No se encontró el paciente.")
    st.stop()

# ─────────────────────────────────────────
# CARGAR DATOS
# ─────────────────────────────────────────
paciente = run_query("""
    SELECT p.*, EXTRACT(YEAR FROM AGE(p.fecha_nacimiento)) AS edad
    FROM pacientes p WHERE p.id_paciente=%s
""", (id_paciente,))

if not paciente:
    st.error("Paciente no encontrado.")
    st.stop()

p               = paciente[0]
nombre_completo = f"{p['nombre']} {p['apellido']}"

# Todos los contratos (historial)
todos_contratos = run_query("""
    SELECT c.*, pr.nombre AS programa,
           n.nombre||' '||n.apellido AS nutricionista,
           pr.cantidad_sesiones,
           COALESCE(c.reprogramaciones_max_override, pr.reprogramaciones_max) AS reprog_max,
           (SELECT COUNT(*) FROM sesiones s WHERE s.id_contrato=c.id_contrato AND s.estado='atendida') AS sesiones_realizadas
    FROM contratos c
    JOIN programas pr     ON c.id_programa=pr.id_programa
    JOIN nutricionistas n ON c.id_nutricionista=n.id_nutricionista
    WHERE c.id_paciente=%s
    ORDER BY c.fecha_inicio DESC
""", (id_paciente,))

# Contrato activo
c = next((x for x in todos_contratos if x["estado"] == "activo"), None)

mostrar_sidebar()

# ─────────────────────────────────────────
# ENCABEZADO — más compacto
# ─────────────────────────────────────────
st.markdown(f"**{nombre_completo}**")

if c:
    realizadas = int(c["sesiones_realizadas"])
    total      = int(c["cantidad_sesiones"])
    restantes  = total - realizadas

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.caption("Programa")
        st.markdown(f"**{c['programa']}**")
    with col2:
        st.caption("Nutricionista")
        st.markdown(f"**{c['nutricionista'].split()[0]}**")
    with col3:
        st.caption("Realizadas")
        st.markdown(f"**{realizadas}/{total}**")
    with col4:
        st.caption("Restantes")
        st.markdown(f"**{restantes}**")
    with col5:
        st.caption("Reprogramaciones")
        st.markdown(f"**{c['reprogramaciones_usadas']}/{c['reprog_max']}**")
    st.progress(realizadas / total if total > 0 else 0,
                text=f"{realizadas} realizadas · {restantes} restantes")

st.markdown("---")

# ─────────────────────────────────────────
# TABS
# ─────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Datos personales", "Anamnesis", "Historia nutricional",
    "Plan nutricional", "Sesiones", "Historial de programas"
])

# ══════════════════════════════
# TAB 1 — DATOS PERSONALES
# ══════════════════════════════
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Nombre:** {nombre_completo}")
        st.markdown(f"**Email:** {p.get('email') or '—'}")
        st.markdown(f"**Teléfono:** {p.get('telefono') or '—'}")
    with col2:
        st.markdown(f"**Nacimiento:** {p.get('fecha_nacimiento') or '—'}")
        st.markdown(f"**Edad:** {int(p['edad']) if p.get('edad') else '—'} años")
        st.markdown(f"**Género:** {p.get('genero') or '—'}")
        st.markdown(f"**Estado:** {p.get('estado') or '—'}")

    if rol in ("administrador","nutricionista"):
        st.markdown("---")
        # Botón descargar PDF de ficha completa
        if st.button("Descargar ficha completa (PDF)", use_container_width=True):
            # Obtener datos para el PDF
            anamnesis_pdf = run_query("SELECT * FROM anamnesis WHERE id_paciente=%s ORDER BY version DESC LIMIT 1", (id_paciente,))
            historia_pdf  = run_query("SELECT * FROM historia_nutricional WHERE id_paciente=%s ORDER BY version", (id_paciente,))

            try:
                from reportlab.lib.pagesizes import A4
                from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
                from reportlab.lib import colors
                from reportlab.lib.units import cm
                import io

                buffer = io.BytesIO()
                doc    = SimpleDocTemplate(buffer, pagesize=A4,
                                           topMargin=2*cm, bottomMargin=2*cm,
                                           leftMargin=2*cm, rightMargin=2*cm)
                styles = getSampleStyleSheet()
                story  = []

                title_style = ParagraphStyle('title', parent=styles['Heading1'],
                                              fontSize=16, spaceAfter=6)
                h2_style    = ParagraphStyle('h2', parent=styles['Heading2'],
                                              fontSize=12, spaceAfter=4, textColor=colors.HexColor('#1F4E79'))
                normal      = styles['Normal']

                story.append(Paragraph(f"Ficha del paciente: {nombre_completo}", title_style))
                story.append(Paragraph(f"Generada el {date.today().strftime('%d/%m/%Y')}", normal))
                story.append(Spacer(1, 0.4*cm))

                # Datos personales
                story.append(Paragraph("Datos personales", h2_style))
                datos_table = [
                    ["Nombre", nombre_completo, "Email", p.get('email') or '—'],
                    ["Teléfono", p.get('telefono') or '—', "Fecha nacimiento", str(p.get('fecha_nacimiento') or '—')[:10]],
                    ["Género", p.get('genero') or '—', "Estado", p.get('estado') or '—'],
                ]
                t = Table(datos_table, colWidths=[4*cm, 6*cm, 4*cm, 6*cm])
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#D6E4F0')),
                    ('BACKGROUND', (2,0), (2,-1), colors.HexColor('#D6E4F0')),
                    ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
                    ('FONTSIZE', (0,0), (-1,-1), 9),
                    ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                    ('PADDING', (0,0), (-1,-1), 4),
                ]))
                story.append(t)
                story.append(Spacer(1, 0.4*cm))

                # Anamnesis
                if anamnesis_pdf:
                    a = anamnesis_pdf[0]
                    story.append(Paragraph(f"Anamnesis (v{a['version']})", h2_style))
                    campos_a = [
                        ("Objetivo", a.get('objetivo_principal')),
                        ("Enfermedades", a.get('enfermedades')),
                        ("Medicamentos", a.get('medicamentos')),
                        ("Alergias", a.get('alergias_intolerancias')),
                        ("Actividad física", a.get('actividad_fisica')),
                        ("Hábitos alimentarios", a.get('habitos_alimentarios')),
                        ("Agua (litros/día)", a.get('consumo_agua_litros')),
                        ("Nivel de estrés", a.get('nivel_estres')),
                        ("Observaciones", a.get('observaciones')),
                    ]
                    rows_a = [[k, str(v or '—')] for k,v in campos_a]
                    ta = Table(rows_a, colWidths=[5*cm, 15*cm])
                    ta.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#D6E4F0')),
                        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
                        ('FONTSIZE', (0,0), (-1,-1), 9),
                        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                        ('PADDING', (0,0), (-1,-1), 4),
                        ('VALIGN', (0,0), (-1,-1), 'TOP'),
                    ]))
                    story.append(ta)
                    story.append(Spacer(1, 0.4*cm))

                # Historia nutricional
                if historia_pdf:
                    story.append(Paragraph("Historia nutricional", h2_style))
                    rows_h = [["Sesión","Peso","Talla","IMC","Cintura","Cadera","Brazo","Fecha"]]
                    for h in historia_pdf:
                        rows_h.append([
                            str(h.get('version','—')),
                            str(h.get('peso','—')),
                            str(h.get('talla','—')),
                            str(h.get('imc','—')),
                            str(h.get('circ_cintura','—')),
                            str(h.get('circ_cadera','—')),
                            str(h.get('circ_brazo','—')),
                            str(h.get('fecha_registro','—'))[:10],
                        ])
                    th = Table(rows_h, colWidths=[2*cm,2.5*cm,2.5*cm,2.5*cm,2.5*cm,2.5*cm,2.5*cm,3*cm])
                    th.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1F4E79')),
                        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
                        ('FONTSIZE', (0,0), (-1,-1), 8),
                        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                        ('PADDING', (0,0), (-1,-1), 3),
                        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F2F2F2')]),
                    ]))
                    story.append(th)

                doc.build(story)
                buffer.seek(0)
                st.download_button(
                    label="Descargar PDF",
                    data=buffer,
                    file_name=f"ficha_{nombre_completo.replace(' ','_')}.pdf",
                    mime="application/pdf"
                )
            except ImportError:
                st.warning("Instalá reportlab: `pip install reportlab`")
            except Exception as e:
                st.error(f"Error generando PDF: {e}")

# ══════════════════════════════
# TAB 2 — ANAMNESIS
# ══════════════════════════════
with tab2:
    todas_anamnesis = run_query("""
        SELECT * FROM anamnesis WHERE id_paciente=%s ORDER BY version DESC
    """, (id_paciente,))

    if todas_anamnesis:
        # Mostrar versión actual
        a = todas_anamnesis[0]
        col_v, col_e = st.columns([3,1])
        with col_v:
            st.caption(f"Versión actual: {a['version']} · Estado: {a['estado']} · {str(a.get('fecha_registro',''))[:10]}")
        with col_e:
            if len(todas_anamnesis) > 1:
                ver_hist = st.checkbox("Ver historial", key="anam_hist")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Objetivo:** {a.get('objetivo_principal') or '—'}")
            st.markdown(f"**Enfermedades:** {a.get('enfermedades') or '—'}")
            st.markdown(f"**Medicamentos:** {a.get('medicamentos') or '—'}")
            st.markdown(f"**Alergias:** {a.get('alergias_intolerancias') or '—'}")
            st.markdown(f"**Restricciones:** {a.get('restricciones_dieta') or '—'}")
            st.markdown(f"**Antec. dieta:** {a.get('antecedentes_dieta') or '—'}")
        with col2:
            st.markdown(f"**Hábitos:** {a.get('habitos_alimentarios') or '—'}")
            st.markdown(f"**Actividad:** {a.get('actividad_fisica') or '—'} ({a.get('frecuencia_actividad') or '—'})")
            st.markdown(f"**Trabajo:** {a.get('tipo_trabajo') or '—'} — {a.get('horas_trabajo') or '—'} hs/día")
            st.markdown(f"**Sueño:** {a.get('horas_sueno') or '—'} hs/día")
            st.markdown(f"**Agua:** {a.get('consumo_agua_litros') or '—'} L/día")
            st.markdown(f"**Estrés:** {a.get('nivel_estres') or '—'}")
            st.markdown(f"**Observaciones:** {a.get('observaciones') or '—'}")

        # Historial de versiones anteriores
        if len(todas_anamnesis) > 1 and st.session_state.get("anam_hist"):
            st.markdown("---")
            st.markdown("**Versiones anteriores:**")
            for av in todas_anamnesis[1:]:
                with st.expander(f"Versión {av['version']} — {str(av.get('fecha_registro',''))[:10]}"):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown(f"**Objetivo:** {av.get('objetivo_principal') or '—'}")
                        st.markdown(f"**Enfermedades:** {av.get('enfermedades') or '—'}")
                        st.markdown(f"**Alergias:** {av.get('alergias_intolerancias') or '—'}")
                    with c2:
                        st.markdown(f"**Hábitos:** {av.get('habitos_alimentarios') or '—'}")
                        st.markdown(f"**Agua:** {av.get('consumo_agua_litros') or '—'} L/día")
                        st.markdown(f"**Obs:** {av.get('observaciones') or '—'}")

        if rol in ("administrador","nutricionista"):
            st.markdown("---")
            with st.expander("Nueva versión de anamnesis"):
                mostrar_form_anamnesis(id_paciente, c["id_contrato"] if c else None, a)
    else:
        st.info("Sin anamnesis registrada.")
        if rol in ("administrador","nutricionista"):
            with st.expander("Cargar anamnesis"):
                mostrar_form_anamnesis(id_paciente, c["id_contrato"] if c else None, None)

# ══════════════════════════════
# TAB 3 — HISTORIA NUTRICIONAL
# ══════════════════════════════
with tab3:
    historia = run_query("""
        SELECT h.version, h.peso, h.talla, h.imc,
               h.circ_cintura, h.circ_cadera, h.circ_brazo,
               h.avance_objetivos, h.cambios_habitos,
               h.fuente_datos, h.fecha_registro
        FROM historia_nutricional h
        WHERE h.id_paciente=%s ORDER BY h.version
    """, (id_paciente,))

    if historia:
        df_h = pd.DataFrame(historia)

        try:
            import altair as alt

            # Gráficos peso e IMC
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                st.caption("Peso (kg)")
                df_peso = df_h[["version","peso"]].dropna()
                if len(df_peso) > 0:
                    ch = alt.Chart(df_peso).mark_line(point=True, color="#1D9E75").encode(
                        x=alt.X("version:O", title="Sesión"),
                        y=alt.Y("peso:Q", scale=alt.Scale(zero=False), title="kg"),
                        tooltip=["version","peso"]
                    ).properties(height=180)
                    st.altair_chart(ch, use_container_width=True)
                    if len(df_peso) > 1:
                        var = float(df_peso["peso"].iloc[-1]) - float(df_peso["peso"].iloc[0])
                        st.caption(f"{'📉' if var < 0 else '📈'} Variación: **{var:+.1f} kg**")
            with col_g2:
                st.caption("IMC")
                df_imc = df_h[["version","imc"]].dropna()
                if len(df_imc) > 0:
                    ch2 = alt.Chart(df_imc).mark_line(point=True, color="#185FA5").encode(
                        x=alt.X("version:O", title="Sesión"),
                        y=alt.Y("imc:Q", scale=alt.Scale(zero=False), title="IMC"),
                        tooltip=["version","imc"]
                    ).properties(height=180)
                    st.altair_chart(ch2, use_container_width=True)
                    if len(df_imc) > 0:
                        ultimo = float(df_imc["imc"].iloc[-1])
                        cat = "Bajo peso" if ultimo < 18.5 else "Normal" if ultimo < 25 else "Sobrepeso" if ultimo < 30 else "Obesidad"
                        st.caption(f"IMC actual: **{ultimo:.1f}** ({cat})")

            # Circunferencias
            df_circ = df_h[["version","circ_cintura","circ_cadera","circ_brazo"]].dropna(subset=["circ_cintura"])
            if len(df_circ) > 0:
                st.caption("Circunferencias (cm)")
                df_melt = df_circ.melt(id_vars="version",
                                        value_vars=["circ_cintura","circ_cadera","circ_brazo"],
                                        var_name="medida", value_name="cm")
                df_melt["medida"] = df_melt["medida"].map({
                    "circ_cintura":"Cintura","circ_cadera":"Cadera","circ_brazo":"Brazo"
                })
                ch3 = alt.Chart(df_melt).mark_line(point=True).encode(
                    x=alt.X("version:O", title="Sesión"),
                    y=alt.Y("cm:Q", scale=alt.Scale(zero=False)),
                    color=alt.Color("medida:N", legend=alt.Legend(title="")),
                    tooltip=["version","medida","cm"]
                ).properties(height=180)
                st.altair_chart(ch3, use_container_width=True)
        except:
            pass

        # Tabla resumen con variaciones
        st.markdown("---")
        st.caption("Tabla de evolución")
        df_tabla = df_h.copy()
        df_tabla["Fecha"] = pd.to_datetime(df_tabla["fecha_registro"]).dt.strftime("%d/%m/%Y")
        df_tabla = df_tabla.rename(columns={
            "version":"Sesión","peso":"Peso","talla":"Talla","imc":"IMC",
            "circ_cintura":"Cintura","circ_cadera":"Cadera","circ_brazo":"Brazo",
            "avance_objetivos":"Avances"
        })
        cols_t = [c for c in ["Sesión","Fecha","Peso","Talla","IMC","Cintura","Cadera","Brazo","Avances"] if c in df_tabla.columns]
        st.dataframe(df_tabla[cols_t], use_container_width=True, hide_index=True)

        # Resumen de cambios entre primera y última medición
        if len(historia) > 1:
            primera = historia[0]
            ultima  = historia[-1]
            st.markdown("---")
            st.caption("Resumen de cambios (primera vs última medición)")
            rc1, rc2, rc3, rc4 = st.columns(4)
            def delta(campo):
                v1 = primera.get(campo)
                v2 = ultima.get(campo)
                if v1 and v2:
                    d = float(v2) - float(v1)
                    return f"{d:+.1f}"
                return "—"
            rc1.metric("Peso",    f"{ultima.get('peso') or '—'} kg",    delta("peso"))
            rc2.metric("IMC",     f"{ultima.get('imc') or '—'}",         delta("imc"))
            rc3.metric("Cintura", f"{ultima.get('circ_cintura') or '—'} cm", delta("circ_cintura"))
            rc4.metric("Cadera",  f"{ultima.get('circ_cadera') or '—'} cm",  delta("circ_cadera"))

    else:
        st.info("Sin registros de historia nutricional.")

    if rol in ("administrador","nutricionista"):
        st.markdown("---")
        with st.expander("Registrar nueva medición"):
            with st.form("form_medicion"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    peso         = st.number_input("Peso (kg)",    min_value=0.0, step=0.1)
                    talla        = st.number_input("Talla (cm)",   min_value=0.0, step=0.1)
                with col2:
                    circ_cintura = st.number_input("Cintura (cm)", min_value=0.0, step=0.1)
                    circ_cadera  = st.number_input("Cadera (cm)",  min_value=0.0, step=0.1)
                with col3:
                    circ_brazo   = st.number_input("Brazo (cm)",   min_value=0.0, step=0.1)
                    fuente       = st.selectbox("Fuente", ["consulta","formulario","app","otro"])
                avance_obj = st.text_area("Avances")
                cambios_h  = st.text_area("Cambios de hábitos")
                if st.form_submit_button("Guardar", use_container_width=True):
                    imc = round(peso/((talla/100)**2),2) if talla > 0 else None
                    ultima = run_query("SELECT COALESCE(MAX(version),0) AS v FROM historia_nutricional WHERE id_paciente=%s", (id_paciente,))
                    nueva_v = ultima[0]["v"] + 1
                    try:
                        run_command("""
                            INSERT INTO historia_nutricional
                                (id_paciente, id_contrato, version, peso, talla, imc,
                                 circ_cintura, circ_cadera, circ_brazo,
                                 avance_objetivos, cambios_habitos, fuente_datos)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """, (id_paciente, c["id_contrato"] if c else None,
                              nueva_v, peso, talla, imc,
                              circ_cintura, circ_cadera, circ_brazo,
                              avance_obj, cambios_h, fuente))
                        st.success(f"Medición #{nueva_v} guardada. IMC: {imc}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

# ══════════════════════════════
# TAB 4 — PLANES NUTRICIONALES
# ══════════════════════════════
with tab4:
    planes = run_query("""
        SELECT pl.id_plan, pl.version, pl.titulo, pl.estado,
               pl.fecha_creacion, pl.fecha_vigencia,
               pl.contenido, pl.archivo_url,
               n.nombre||' '||n.apellido AS nutricionista
        FROM planes_nutricionales pl
        JOIN nutricionistas n ON pl.id_nutricionista=n.id_nutricionista
        WHERE pl.id_paciente=%s
        ORDER BY pl.version DESC
    """, (id_paciente,))

    if planes:
        activos    = [p for p in planes if p["estado"] == "activo"]
        historicos = [p for p in planes if p["estado"] != "activo"]

        if activos:
            st.markdown("**Plan activo:**")
            plan = activos[0]
            with st.container(border=True):
                col1, col2, col3 = st.columns([3,1,1])
                with col1:
                    titulo = plan.get("titulo") or f"Plan v{plan['version']}"
                    st.markdown(f"🟢 **{titulo}** — {plan['nutricionista']}")
                    vigencia = str(plan['fecha_vigencia'])[:10] if plan['fecha_vigencia'] else '—'
                    st.caption(f"Creado: {str(plan['fecha_creacion'])[:10]} · Vigente hasta: {vigencia}")
                with col2:
                    if plan["archivo_url"]:
                        st.link_button("PDF", plan["archivo_url"], use_container_width=True)
                with col3:
                    bc1, bc2 = st.columns(2)
                    with bc1:
                        if st.button("Ver", key=f"ver_{plan['id_plan']}", use_container_width=True):
                            k = f"show_{plan['id_plan']}"
                            st.session_state[k] = not st.session_state.get(k, False)
                    with bc2:
                        if plan["contenido"]:
                            try:
                                from reportlab.lib.pagesizes import A4
                                from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
                                from reportlab.lib.styles import getSampleStyleSheet
                                from reportlab.lib.units import cm
                                import io
                                buf = io.BytesIO()
                                doc = SimpleDocTemplate(buf, pagesize=A4,
                                    topMargin=2*cm, bottomMargin=2*cm,
                                    leftMargin=2*cm, rightMargin=2*cm)
                                styles = getSampleStyleSheet()
                                titulo_plan = plan.get("titulo") or f"Plan v{plan['version']}"
                                story = [
                                    Paragraph(f"Plan nutricional: {titulo_plan}", styles["Heading1"]),
                                    Paragraph(f"Paciente: {nombre_completo}", styles["Normal"]),
                                    Paragraph(f"Nutricionista: {plan['nutricionista']}", styles["Normal"]),
                                    Paragraph(f"Fecha: {str(plan['fecha_creacion'])[:10]}", styles["Normal"]),
                                    Spacer(1, 0.5*cm),
                                ]
                                for linea in plan["contenido"].split("\n"):
                                    story.append(Paragraph(linea or " ", styles["Normal"]))
                                doc.build(story)
                                buf.seek(0)
                                st.download_button("Descargar", data=buf,
                                    file_name=f"plan_{nombre_completo.replace(' ','_')}_v{plan['version']}.pdf",
                                    mime="application/pdf",
                                    key=f"dl_{plan['id_plan']}",
                                    use_container_width=True)
                            except ImportError:
                                st.caption("pip install reportlab")
                if st.session_state.get(f"show_{plan['id_plan']}", False):
                    st.markdown("---")
                    st.markdown(plan["contenido"] or "Sin contenido.")

        if historicos:
            st.markdown("---")
            st.markdown("**Planes anteriores:**")
            for plan in historicos:
                with st.expander(f"Plan v{plan['version']} — {str(plan['fecha_creacion'])[:10]} ({plan['estado']})"):
                    col1, col2 = st.columns([3,1])
                    with col1:
                        st.caption(f"Nutricionista: {plan['nutricionista']}")
                        st.markdown(plan["contenido"] or "Sin contenido.")
                    with col2:
                        if plan["archivo_url"]:
                            st.link_button("PDF", plan["archivo_url"], use_container_width=True)
    else:
        st.info("No hay planes nutricionales cargados aún.")

    if rol in ("administrador","nutricionista"):
        st.markdown("---")
        if st.button("Crear nuevo plan", use_container_width=True):
            st.session_state["id_paciente_ficha"] = id_paciente
            st.switch_page("pages/3b_cargar_plan.py")

# ══════════════════════════════
# TAB 5 — SESIONES
# ══════════════════════════════
with tab5:
    if not c:
        st.info("No hay contrato activo.")
    else:
        sesiones = run_query("""
            SELECT s.numero_sesion, s.fecha_hora_programada, s.fecha_hora_atencion,
                   s.modalidad, s.estado, s.motivo_reprogramacion,
                   s.contador_reprogramaciones,
                   n.nombre||' '||n.apellido AS nutricionista
            FROM sesiones s
            JOIN nutricionistas n ON s.id_nutricionista_prog=n.id_nutricionista
            WHERE s.id_contrato=%s ORDER BY s.numero_sesion
        """, (c["id_contrato"],))

        if sesiones:
            df_s = pd.DataFrame(sesiones)
            df_s["fecha_hora_programada"] = pd.to_datetime(df_s["fecha_hora_programada"]).dt.strftime("%d/%m/%Y %H:%M")
            iconos = {"programada":"🟡","atendida":"🟢","ausente":"🔴","cancelada":"⚫"}
            df_s[""] = df_s["estado"].map(lambda x: iconos.get(x,"⚪"))
            df_s = df_s.rename(columns={
                "numero_sesion":"N°","fecha_hora_programada":"Fecha",
                "modalidad":"Modalidad","estado":"Estado",
                "nutricionista":"Nutricionista","contador_reprogramaciones":"Reprog."
            })
            st.dataframe(df_s[["","N°","Fecha","Modalidad","Estado","Nutricionista","Reprog."]],
                         use_container_width=True)

            if rol in ("administrador","nutricionista"):
                with st.expander("Marcar sesión como atendida"):
                    prog = [s for s in sesiones if s["estado"]=="programada"]
                    if prog:
                        opts = {f"#{s['numero_sesion']} — {str(s['fecha_hora_programada'])[:16]}": s for s in prog}
                        sel_s = st.selectbox("Sesión", list(opts.keys()))
                        if st.button("Marcar como atendida", key="btn_atendida"):
                            run_command("""
                                UPDATE sesiones SET estado='atendida', fecha_hora_atencion=NOW()
                                WHERE id_contrato=%s AND numero_sesion=%s
                            """, (c["id_contrato"], opts[sel_s]["numero_sesion"]))
                            st.success("Marcada como atendida.")
                            st.rerun()
                    else:
                        st.info("Sin sesiones programadas pendientes.")
        else:
            st.info("Sin sesiones registradas.")

# ══════════════════════════════
# TAB 6 — HISTORIAL DE PROGRAMAS
# ══════════════════════════════
with tab6:
    st.markdown("**Todos los programas contratados:**")
    if todos_contratos:
        for ct in todos_contratos:
            badge = "🟢" if ct["estado"]=="activo" else "⚫"
            real  = int(ct["sesiones_realizadas"])
            tot   = int(ct["cantidad_sesiones"])
            with st.container(border=True):
                col1, col2, col3 = st.columns([3,2,2])
                with col1:
                    st.markdown(f"{badge} **{ct['programa']}**")
                    st.caption(f"Nutricionista: {ct['nutricionista']}")
                    st.caption(f"Estado: {ct['estado']}")
                with col2:
                    st.markdown(f"Inicio: **{str(ct['fecha_inicio'])[:10]}**")
                    st.markdown(f"Fin: **{str(ct['fecha_fin'])[:10]}**")
                with col3:
                    st.markdown(f"Sesiones: **{real}/{tot}**")
                    st.progress(real/tot if tot > 0 else 0)
                    st.caption(f"Reprog.: {ct['reprogramaciones_usadas']}/{ct['reprog_max']}")
    else:
        st.info("Sin historial de programas.")
