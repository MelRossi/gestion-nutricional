import json
from copy import deepcopy
from datetime import date, timedelta
import pandas as pd


import streamlit as st
from database import run_query, run_command
from utils import mostrar_sidebar, page_header, section_label, info_banner, divider
from composicion_utils import (
    build_composicion_payload,
    build_composicion_pdf,
    calcular_edad,
    calcular_imc,
    logo_to_data_uri,
    show_composicion_preview,
)
from plan_utils import (
    read_plan_record,
    read_template_record,
    default_template_structured,
    build_patient_plan_payload,
    plain_text_summary_from_plan,
    show_plan_preview,
    build_plan_pdf,
    send_plan_email,
)

import re
import unicodedata


def limpiar_nombre_archivo(texto):
    texto = str(texto or "").strip()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = texto.replace(" ", "_")
    texto = re.sub(r"[^A-Za-z0-9_\-]", "", texto)
    texto = re.sub(r"_+", "_", texto).strip("_")
    return texto or "sin_nombre"


def nombre_pdf_plan(titulo, version, paciente_data):
    nombre_plan = limpiar_nombre_archivo(titulo or "plan")
    apellido = limpiar_nombre_archivo(paciente_data.get("apellido") or "Paciente")
    nombre = limpiar_nombre_archivo(paciente_data.get("nombre") or "")
    fecha = date.today().strftime("%d-%m-%Y")
    return f"plan_{nombre_plan}_V{version}_{apellido}_{nombre}_{fecha}.pdf"


# CONTROL DE ACCESO

if "usuario" not in st.session_state:
    st.warning("Debes iniciar sesión.")
    st.stop()

if st.session_state["usuario"]["rol"] not in ("administrador", "nutricionista"):
    st.error("No tienes permisos para acceder.")
    st.stop()

usuario = st.session_state["usuario"]
rol = usuario["rol"]
id_nutri = usuario.get("id_nutricionista")

mostrar_sidebar()
page_header("Planes nutricionales")


# PACIENTE


id_paciente = st.session_state.get("id_paciente_ficha")
lista = []

if rol == "administrador":
    lista = run_query("""
        SELECT DISTINCT p.id_paciente,
               p.nombre || ' ' || p.apellido AS nombre
        FROM pacientes p
        JOIN contratos c ON p.id_paciente = c.id_paciente
        WHERE p.estado = 'activo'
          AND c.estado = 'activo'
        ORDER BY nombre
    """)
else:
    lista = run_query("""
        SELECT DISTINCT p.id_paciente,
               p.nombre || ' ' || p.apellido AS nombre
        FROM pacientes p
        JOIN contratos c ON p.id_paciente = c.id_paciente
        WHERE p.estado = 'activo'
          AND c.estado = 'activo'
          AND c.id_nutricionista = %s
        ORDER BY nombre
    """, (id_nutri,))

if not lista:
    st.info("No hay pacientes disponibles.")
    st.stop()

opciones_paciente = {p["nombre"]: p["id_paciente"] for p in lista}
nombres_paciente = list(opciones_paciente.keys())

if not id_paciente:
    paciente_sel = st.selectbox(
        "Seleccionar paciente",
        nombres_paciente,
        key="selector_paciente_planes"
    )
    id_paciente = opciones_paciente[paciente_sel]
else:
    nombre_actual = next((k for k, v in opciones_paciente.items() if v == id_paciente), None)
    if nombre_actual and nombre_actual in nombres_paciente:
        idx_actual = nombres_paciente.index(nombre_actual)
    else:
        idx_actual = 0
        id_paciente = opciones_paciente[nombres_paciente[0]]

    paciente_sel = st.selectbox(
        "Seleccionar paciente",
        nombres_paciente,
        index=idx_actual,
        key="selector_paciente_planes"
    )
    id_paciente = opciones_paciente[paciente_sel]

paciente_rs = run_query("""
    SELECT p.id_paciente, p.nombre, p.apellido, p.email, p.telefono,
           p.dni, p.genero, p.fecha_nacimiento, p.tipo_paciente, p.id_empresa,
           e.nombre AS empresa
    FROM pacientes p
    LEFT JOIN empresas e ON e.id_empresa = p.id_empresa
    WHERE p.id_paciente = %s
""", (id_paciente,))

if not paciente_rs:
    st.error("Paciente no encontrado.")
    st.stop()

paciente = paciente_rs[0]
nombre_paciente = f"{paciente['nombre']} {paciente['apellido']}".strip()

contrato = run_query("""
    SELECT c.id_contrato, c.id_nutricionista, pr.nombre AS programa
    FROM contratos c
    JOIN programas pr ON c.id_programa = pr.id_programa
    WHERE c.id_paciente = %s
      AND c.estado = 'activo'
    LIMIT 1
""", (id_paciente,))

ultima_anam = run_query("""
    SELECT *
    FROM anamnesis
    WHERE id_paciente = %s
    ORDER BY version DESC
    LIMIT 1
""", (id_paciente,))
anam = ultima_anam[0] if ultima_anam else {}


# HISTORIAL + BUSCADOR

busqueda = st.text_input(
    "Buscar en planes anteriores",
    placeholder="Ej: hipocalórico, proteínas, DASH, ansiedad...",
    key="buscar_planes_historial"
)

if busqueda and len(busqueda.strip()) >= 2:
    planes_hist = run_query("""
        SELECT pl.id_plan,
               pl.version,
               COALESCE(pl.titulo, 'Plan v' || pl.version::text) AS titulo,
               pl.estado,
               pl.fecha_creacion,
               pl.fecha_vigencia,
               pl.contenido,
               pl.contenido_json,
               pl.archivo_url,
               n.nombre || ' ' || n.apellido AS nutricionista
        FROM planes_nutricionales pl
        JOIN nutricionistas n ON pl.id_nutricionista = n.id_nutricionista
        WHERE pl.id_paciente = %s
          AND (
                COALESCE(pl.titulo, '') ILIKE %s
             OR COALESCE(pl.contenido, '') ILIKE %s
             OR COALESCE(pl.contenido_json::text, '') ILIKE %s
             OR (n.nombre || ' ' || n.apellido) ILIKE %s
          )
        ORDER BY pl.fecha_creacion DESC, pl.version DESC
        LIMIT 20
    """, (
        id_paciente,
        f"%{busqueda}%",
        f"%{busqueda}%",
        f"%{busqueda}%",
        f"%{busqueda}%"
    ))
else:
    planes_hist = run_query("""
        SELECT pl.id_plan,
               pl.version,
               COALESCE(pl.titulo, 'Plan v' || pl.version::text) AS titulo,
               pl.estado,
               pl.fecha_creacion,
               pl.fecha_vigencia,
               pl.contenido,
               pl.contenido_json,
               pl.archivo_url,
               n.nombre || ' ' || n.apellido AS nutricionista
        FROM planes_nutricionales pl
        JOIN nutricionistas n ON pl.id_nutricionista = n.id_nutricionista
        WHERE pl.id_paciente = %s
        ORDER BY pl.fecha_creacion DESC, pl.version DESC
        LIMIT 20
    """, (id_paciente,))

with st.container(border=True):
    st.markdown(f"### {nombre_paciente}")
    st.markdown("**Historial de planes**")

    if planes_hist:
        opciones_hist = {}
        for p in planes_hist:
            fecha_txt = str(p["fecha_creacion"])[:10]
            label = f"{p['titulo']} · v{p['version']} · {fecha_txt}"
            opciones_hist[label] = p

        seleccionado_hist = st.selectbox(
            "Seleccionar plan del historial",
            list(opciones_hist.keys()),
            key="selector_historial_planes"
        )

        plan_sel = opciones_hist[seleccionado_hist]
        parsed = read_plan_record(plan_sel)
        contenido_json_hist = plan_sel.get("contenido_json")
        if isinstance(contenido_json_hist, str):
            try:
                contenido_json_hist = json.loads(contenido_json_hist)
            except Exception:
                contenido_json_hist = None

        es_composicion = isinstance(contenido_json_hist, dict) and contenido_json_hist.get("tipo") == "composicion_corporal"

        vigencia_txt = str(plan_sel["fecha_vigencia"])[:10] if plan_sel["fecha_vigencia"] else "—"
        tipo_doc = "Infografía corporal" if es_composicion else "Plan nutricional"
        st.caption(
            f"Tipo: {tipo_doc} · Nutricionista: {plan_sel['nutricionista']} · Estado: {plan_sel['estado']} · Vigencia: {vigencia_txt}"
        )

        col_espacio, col_btn1, col_btn2 = st.columns([3, 1, 1])
        with col_btn1:
            if es_composicion:
                pdf_hist = build_composicion_pdf(contenido_json_hist)
                st.download_button(
                    "Descargar infografía PDF",
                    data=pdf_hist,
                    file_name=f"infografia_composicion_v{plan_sel['version']}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key=f"descargar_infografia_historial_{plan_sel['id_plan']}"
                )
            elif parsed["kind"] == "structured":
                pdf_hist = build_plan_pdf(parsed["data"])
                st.download_button(
                    "Descargar PDF",
                    data=pdf_hist,
                    file_name=nombre_pdf_plan(plan_sel.get("titulo"), plan_sel.get("version"), paciente),
                    mime="application/pdf",
                    use_container_width=True,
                    key=f"descargar_historial_{plan_sel['id_plan']}"
                )
        with col_btn2:
            if plan_sel.get("archivo_url"):
                st.link_button("Abrir archivo", plan_sel["archivo_url"], use_container_width=True)

        st.markdown("---")
        if es_composicion:
            show_composicion_preview(contenido_json_hist, height=920)
        elif parsed["kind"] == "structured":
            show_plan_preview(parsed["data"], height=920)
        else:
            st.info("Este documento pertenece al formato anterior.")
            st.markdown(parsed["legacy_text"] or "—")
    else:
        st.info("No se encontraron planes para ese criterio.")

divider()


# PESTAÑAS

tab_modelo, tab_plan, tab_composicion, tab_archivo = st.tabs(["Crear modelo", "Crear plan", "Composición corporal", "Subir archivo"])


# CREAR MODELO

with tab_modelo:
    section_label("Crear modelo reutilizable")

    FIELD_H_SMALL = 90
    FIELD_H_BIG = 180

    nombre_modelo = st.text_input(
        "Nombre del modelo",
        placeholder="Ej: Plan hipocalórico",
        key="modelo_nombre"
    )
    descripcion_modelo = st.text_area(
        "Descripción",
        placeholder="Notas internas u observaciones",
        height=90,
        key="modelo_descripcion"
    )

    st.markdown("### Cabecera")
    col_a, col_b = st.columns(2)
    with col_a:
        titulo_visible_m = st.text_input(
            "Título",
            value="PLAN DE ALIMENTACIÓN",
            key="modelo_titulo_visible"
        )
        objetivo_m = st.text_area(
            "Objetivo",
            value="",
            height=FIELD_H_SMALL,
            key="modelo_objetivo"
        )
        alergias_m = st.text_area(
            "Alergias",
            value="",
            height=FIELD_H_SMALL,
            key="modelo_alergias"
        )
    with col_b:
        intolerancias_m = st.text_area(
            "Intolerancias / restricciones",
            value="",
            height=FIELD_H_SMALL,
            key="modelo_intolerancias"
        )
        diagnostico_m = st.text_area(
            "Diagnóstico nutricional",
            height=FIELD_H_BIG,
            key="modelo_diagnostico"
        )

    st.markdown("### Días 1 a 7")
    dias_modelo = {}
    for i in range(1, 8):
        with st.expander(f"Día {i}", expanded=(i == 1)):
            col_d1, col_d2, col_d3 = st.columns(3)
            with col_d1:
                desayuno = st.text_area("Desayuno", key=f"modelo_des_{i}", height=150)
            with col_d2:
                almuerzo = st.text_area("Almuerzo", key=f"modelo_alm_{i}", height=150)
            with col_d3:
                cena = st.text_area("Cena", key=f"modelo_cena_{i}", height=150)

            dias_modelo[f"dia_{i}"] = {
                "desayuno": desayuno,
                "almuerzo": almuerzo,
                "cena": cena,
            }

    st.markdown("### Bloques adicionales")

    with st.expander("1/2 mañana y 1/2 tarde", expanded=False):
        media_m = st.text_area(
            "Contenido",
            height=FIELD_H_BIG,
            key="modelo_media_manana_tarde",
            label_visibility="collapsed"
        )

    with st.expander("Ensalada", expanded=False):
        ensalada_m = st.text_area(
            "Contenido",
            height=FIELD_H_BIG,
            key="modelo_ensalada",
            label_visibility="collapsed"
        )

    col_c, col_d = st.columns(2)
    with col_c:
        cantidades_m = st.text_area("Cantidades", height=FIELD_H_BIG, key="modelo_cantidades")
        recomendaciones_m = st.text_area("Recomendaciones", height=240, key="modelo_recomendaciones")
    with col_d:
        consejos_m = st.text_area("Consejos claves", height=240, key="modelo_consejos")

    if st.button("Guardar modelo", use_container_width=True, type="primary", key="btn_guardar_modelo"):
        try:
            estructura = default_template_structured(nombre_modelo or "Modelo sin nombre")
            estructura["nombre_modelo"] = nombre_modelo or "Modelo sin nombre"
            estructura["contenido_base"] = {
                "cabecera": {
                    "titulo": titulo_visible_m or "PLAN DE ALIMENTACIÓN",
                    "objetivo": objetivo_m,
                    "alergias": alergias_m,
                    "intolerancias": intolerancias_m,
                },
                "diagnostico_texto": diagnostico_m,
                "media_manana_tarde_texto": media_m,
                "ensalada_texto": ensalada_m,
                "dias": dias_modelo,
                "cantidades_texto": cantidades_m,
                "recomendaciones_texto": recomendaciones_m,
                "consejos_texto": consejos_m,
            }

            run_command("""
                INSERT INTO plantillas_plan (nombre, descripcion, estructura, estructura_json, activa, creada_por)
                VALUES (%s, %s, %s, %s::jsonb, TRUE, %s)
            """, (
                nombre_modelo or "Modelo sin nombre",
                descripcion_modelo,
                "Modelo estructurado",
                json.dumps(estructura, ensure_ascii=False),
                usuario.get("id_usuario"),
            ))
            st.success("Modelo guardado correctamente.")
            st.rerun()
        except Exception as e:
            st.error(f"Error guardando modelo: {e}")


# CREAR PLAN

with tab_plan:
    section_label("Crear plan para paciente")

    FIELD_H_SMALL = 90
    FIELD_H_BIG = 180

    modelos_raw = run_query("""
        SELECT id_plantilla, nombre, descripcion, estructura_json
        FROM plantillas_plan
        WHERE activa = TRUE
          AND estructura_json IS NOT NULL
        ORDER BY fecha_creacion DESC, nombre
    """)

    modelos = []
    for m in modelos_raw:
        parsed = read_template_record(m)
        if parsed.get("tipo") == "template_structured":
            modelos.append(m)

    if not modelos:
        st.warning("Todavía no hay modelos guardados. Primero debes crear uno en la pestaña Crear modelo.")
    else:
        modelo_opts = {"(Empezar desde cero)": None}
        for m in modelos:
            modelo_opts[m["nombre"]] = m

        modelo_seleccionado = st.selectbox(
            "Elegir plan",
            list(modelo_opts.keys()),
            key="plan_modelo_selector"
        )

        modelo = modelo_opts[modelo_seleccionado]

        if modelo is None:
            st.info("Para empezar desde cero, crea primero un modelo en la pestaña Crear modelo.")
        else:
            plantilla_base = read_template_record(modelo)
            nombre_modelo_actual = modelo["nombre"]
            id_plantilla_actual = modelo["id_plantilla"]

            vigencia_default = str(date.today() + timedelta(days=30))
            nutricionista_nombre = f"{usuario['nombre']} {usuario['apellido']}".strip()

            initial_plan = build_patient_plan_payload(
                paciente=paciente,
                nutricionista_nombre=nutricionista_nombre,
                id_plantilla=id_plantilla_actual,
                nombre_modelo=nombre_modelo_actual,
                template_struct=plantilla_base,
                vigencia=vigencia_default,
            )

            if anam:
                initial_plan["cabecera"]["objetivo"] = anam.get("objetivo_principal") or initial_plan["cabecera"].get("objetivo", "")
                initial_plan["cabecera"]["alergias"] = anam.get("alergias_intolerancias", "")
                initial_plan["cabecera"]["intolerancias"] = anam.get("restricciones_dieta", "")

            editor_key = f"plan_editor_data_{id_paciente}_{id_plantilla_actual}_{modelo_seleccionado}"
            if editor_key not in st.session_state:
                st.session_state[editor_key] = deepcopy(initial_plan)

            plan_data = st.session_state[editor_key]

            with st.expander("Logos del plan (opcional)", expanded=False):
                col_logo_plan1, col_logo_plan2 = st.columns(2)
                with col_logo_plan1:
                    logo_plan_dueno = st.file_uploader(
                        "Logo del dueño / marca principal",
                        type=["png", "jpg", "jpeg"],
                        key=f"{editor_key}_logo_dueno",
                    )
                with col_logo_plan2:
                    logo_plan_empresa = st.file_uploader(
                        "Logo empresa (si corresponde)",
                        type=["png", "jpg", "jpeg"],
                        key=f"{editor_key}_logo_empresa",
                    )

                if logo_plan_dueno or logo_plan_empresa:
                    plan_data.setdefault("logos", {})
                    if logo_plan_dueno:
                        plan_data["logos"]["dueno"] = logo_to_data_uri(logo_plan_dueno)
                    if logo_plan_empresa:
                        plan_data["logos"]["empresa"] = logo_to_data_uri(logo_plan_empresa)
                    st.session_state[editor_key] = plan_data
                    st.success("Logos aplicados a la vista previa y al PDF de este plan.")

            # ─── VISTA PREVIA (siempre visible) ───
            st.markdown("### Vista previa del modelo")
            show_plan_preview(plan_data, height=980)

            divider()

            # ─── TOGGLE EDICIÓN ───
            modo_edicion_key = f"modo_edicion_{editor_key}"
            if modo_edicion_key not in st.session_state:
                st.session_state[modo_edicion_key] = False

            col_mod1, col_mod2 = st.columns([1, 3])
            with col_mod1:
                if not st.session_state[modo_edicion_key]:
                    if st.button("Modificar plan", use_container_width=True, key=f"btn_activar_edicion_{editor_key}"):
                        st.session_state[modo_edicion_key] = True
                        st.rerun()
                else:
                    if st.button("Cancelar edición", use_container_width=True, key=f"btn_cancelar_edicion_{editor_key}"):
                        st.session_state[modo_edicion_key] = False
                        st.session_state[editor_key] = deepcopy(initial_plan)
                        st.rerun()

            # ─── EDITOR (solo si se activó) ───
            if st.session_state.get(modo_edicion_key, False):
                st.markdown("---")
                st.markdown("### Editar cabecera")
                col1, col2 = st.columns(2)
                with col1:
                    plan_data["cabecera"]["titulo"] = st.text_input(
                        "Título visible del plan",
                        value=plan_data["cabecera"].get("titulo", "PLAN DE ALIMENTACIÓN"),
                        key=f"{editor_key}_titulo_visible"
                    )
                    plan_data["cabecera"]["objetivo"] = st.text_area(
                        "Objetivo",
                        value=plan_data["cabecera"].get("objetivo", ""),
                        height=FIELD_H_SMALL,
                        key=f"{editor_key}_objetivo"
                    )
                    plan_data["cabecera"]["alergias"] = st.text_area(
                        "Alergias",
                        value=plan_data["cabecera"].get("alergias", ""),
                        height=FIELD_H_SMALL,
                        key=f"{editor_key}_alergias"
                    )
                with col2:
                    plan_data["cabecera"]["intolerancias"] = st.text_area(
                        "Intolerancias / restricciones",
                        value=plan_data["cabecera"].get("intolerancias", ""),
                        height=FIELD_H_SMALL,
                        key=f"{editor_key}_intolerancias"
                    )
                    plan_data["diagnostico_texto"] = st.text_area(
                        "Diagnóstico nutricional",
                        value=plan_data.get("diagnostico_texto", ""),
                        height=FIELD_H_BIG,
                        key=f"{editor_key}_diagnostico"
                    )
                    fecha_vigencia = st.date_input(
                        "Vigente hasta",
                        value=date.today() + timedelta(days=30),
                        key=f"{editor_key}_vigencia"
                    )
                    plan_data["meta"]["vigencia"] = str(fecha_vigencia)

                st.markdown("### Días 1 a 7")
                for i in range(1, 8):
                    key = f"dia_{i}"
                    day = plan_data["dias"].setdefault(key, {"desayuno": "", "almuerzo": "", "cena": ""})
                    with st.expander(f"Día {i}", expanded=(i == 1)):
                        col_d1, col_d2, col_d3 = st.columns(3)
                        with col_d1:
                            day["desayuno"] = st.text_area(
                                "Desayuno",
                                value=day.get("desayuno", ""),
                                key=f"{editor_key}_des_{i}",
                                height=150
                            )
                        with col_d2:
                            day["almuerzo"] = st.text_area(
                                "Almuerzo",
                                value=day.get("almuerzo", ""),
                                key=f"{editor_key}_alm_{i}",
                                height=150
                            )
                        with col_d3:
                            day["cena"] = st.text_area(
                                "Cena",
                                value=day.get("cena", ""),
                                key=f"{editor_key}_cena_{i}",
                                height=150
                            )

                st.markdown("### Bloques adicionales")

                with st.expander("1/2 mañana y 1/2 tarde", expanded=False):
                    plan_data["media_manana_tarde_texto"] = st.text_area(
                        "Contenido",
                        value=plan_data.get("media_manana_tarde_texto", ""),
                        height=FIELD_H_BIG,
                        key=f"{editor_key}_media",
                        label_visibility="collapsed"
                    )

                with st.expander("Ensalada", expanded=False):
                    plan_data["ensalada_texto"] = st.text_area(
                        "Contenido",
                        value=plan_data.get("ensalada_texto", ""),
                        height=FIELD_H_BIG,
                        key=f"{editor_key}_ensalada",
                        label_visibility="collapsed"
                    )

                col5, col6 = st.columns(2)
                with col5:
                    plan_data["cantidades_texto"] = st.text_area(
                        "Cantidades",
                        value=plan_data.get("cantidades_texto", ""),
                        height=FIELD_H_BIG,
                        key=f"{editor_key}_cantidades"
                    )
                    plan_data["recomendaciones_texto"] = st.text_area(
                        "Recomendaciones",
                        value=plan_data.get("recomendaciones_texto", ""),
                        height=240,
                        key=f"{editor_key}_recomendaciones"
                    )
                with col6:
                    plan_data["consejos_texto"] = st.text_area(
                        "Consejos claves",
                        value=plan_data.get("consejos_texto", ""),
                        height=240,
                        key=f"{editor_key}_consejos"
                    )

                divider()
                st.markdown("### Vista previa actualizada")
                show_plan_preview(plan_data, height=980)

                divider()

                guardar_como_modelo = st.checkbox(
                    "Guardar también este contenido como nuevo modelo reutilizable",
                    key=f"{editor_key}_guardar_como_modelo"
                )

                titulo_interno = st.text_input(
                    "Nombre interno del plan",
                    value=modelo_seleccionado,
                    key=f"{editor_key}_titulo_interno"
                )
                estado_plan = st.selectbox(
                    "Estado",
                    ["activo", "borrador"],
                    key=f"{editor_key}_estado"
                )

                ultima_version = run_query("""
                    SELECT COALESCE(MAX(version), 0) AS v
                    FROM planes_nutricionales
                    WHERE id_paciente = %s
                """, (id_paciente,))
                nueva_version = int(ultima_version[0]["v"]) + 1

                if st.button("Guardar plan", use_container_width=True, type="primary", key=f"{editor_key}_guardar_plan"):
                    try:
                        id_contrato = contrato[0]["id_contrato"] if contrato else None
                        contenido_json = json.dumps(plan_data, ensure_ascii=False)
                        contenido_texto = plain_text_summary_from_plan(plan_data)
                        pdf_bytes = build_plan_pdf(plan_data)
                        pdf_filename = nombre_pdf_plan(titulo_interno, nueva_version, paciente)

                        if estado_plan == "activo":
                            run_command("""
                                UPDATE planes_nutricionales
                                SET estado = 'reemplazado'
                                WHERE id_paciente = %s
                                  AND estado = 'activo'
                            """, (id_paciente,))

                        run_command("""
                            INSERT INTO planes_nutricionales
                                (id_paciente, id_contrato, id_nutricionista,
                                 version, titulo, contenido, contenido_json,
                                 estado, fecha_vigencia, archivo_url)
                            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                        """, (
                            id_paciente,
                            id_contrato,
                            id_nutri,
                            nueva_version,
                            titulo_interno,
                            contenido_texto,
                            contenido_json,
                            estado_plan,
                            fecha_vigencia,
                            None,
                        ))

                        if guardar_como_modelo:
                            nuevo_modelo = default_template_structured(titulo_interno)
                            nuevo_modelo["contenido_base"] = {
                                "cabecera": plan_data["cabecera"],
                                "diagnostico_texto": plan_data.get("diagnostico_texto", ""),
                                "media_manana_tarde_texto": plan_data.get("media_manana_tarde_texto", ""),
                                "ensalada_texto": plan_data.get("ensalada_texto", ""),
                                "dias": plan_data.get("dias", {}),
                                "cantidades_texto": plan_data.get("cantidades_texto", ""),
                                "recomendaciones_texto": plan_data.get("recomendaciones_texto", ""),
                                "consejos_texto": plan_data.get("consejos_texto", ""),
                            }

                            run_command("""
                                INSERT INTO plantillas_plan (nombre, descripcion, estructura, estructura_json, activa, creada_por)
                                VALUES (%s, %s, %s, %s::jsonb, TRUE, %s)
                            """, (
                                titulo_interno,
                                f"Modelo generado desde plan del paciente {nombre_paciente}",
                                "Modelo estructurado",
                                json.dumps(nuevo_modelo, ensure_ascii=False),
                                usuario.get("id_usuario"),
                            ))

                        email_ok, email_msg = send_plan_email(
                            to_email=paciente.get("email", ""),
                            patient_name=nombre_paciente,
                            pdf_bytes=pdf_bytes,
                            pdf_filename=pdf_filename,
                            subject=f"Tu plan nutricional - {titulo_interno}",
                        )

                        st.success(f"Plan v{nueva_version} guardado correctamente.")
                        if email_ok:
                            st.success("El plan se envió por email al paciente.")
                        else:
                            st.warning(f"Plan guardado, pero el email no se envió: {email_msg}")

                        st.download_button(
                            "Descargar PDF generado",
                            data=pdf_bytes,
                            file_name=pdf_filename,
                            mime="application/pdf",
                            use_container_width=True,
                            key=f"{editor_key}_download_pdf"
                        )

                        st.session_state[modo_edicion_key] = False
                        st.rerun()

                    except Exception as e:
                        st.error(f"Error al guardar: {e}")

            else:
                # Fuera del modo edición: solo guardar sin modificar
                divider()
                titulo_interno = st.text_input(
                    "Nombre interno del plan",
                    value=modelo_seleccionado,
                    key=f"{editor_key}_titulo_interno_directo"
                )
                estado_plan = st.selectbox(
                    "Estado",
                    ["activo", "borrador"],
                    key=f"{editor_key}_estado_directo"
                )

                ultima_version = run_query("""
                    SELECT COALESCE(MAX(version), 0) AS v
                    FROM planes_nutricionales
                    WHERE id_paciente = %s
                """, (id_paciente,))
                nueva_version = int(ultima_version[0]["v"]) + 1

                if st.button("Guardar plan sin modificar", use_container_width=True, type="primary", key=f"{editor_key}_guardar_directo"):
                    try:
                        id_contrato = contrato[0]["id_contrato"] if contrato else None
                        contenido_json = json.dumps(plan_data, ensure_ascii=False)
                        contenido_texto = plain_text_summary_from_plan(plan_data)
                        pdf_bytes = build_plan_pdf(plan_data)
                        pdf_filename = nombre_pdf_plan(titulo_interno, nueva_version, paciente)

                        if estado_plan == "activo":
                            run_command("""
                                UPDATE planes_nutricionales
                                SET estado = 'reemplazado'
                                WHERE id_paciente = %s
                                  AND estado = 'activo'
                            """, (id_paciente,))

                        run_command("""
                            INSERT INTO planes_nutricionales
                                (id_paciente, id_contrato, id_nutricionista,
                                 version, titulo, contenido, contenido_json,
                                 estado, fecha_vigencia, archivo_url)
                            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                        """, (
                            id_paciente,
                            id_contrato,
                            id_nutri,
                            nueva_version,
                            titulo_interno,
                            contenido_texto,
                            contenido_json,
                            estado_plan,
                            date.today() + timedelta(days=30),
                            None,
                        ))

                        email_ok, email_msg = send_plan_email(
                            to_email=paciente.get("email", ""),
                            patient_name=nombre_paciente,
                            pdf_bytes=pdf_bytes,
                            pdf_filename=pdf_filename,
                            subject=f"Tu plan nutricional - {titulo_interno}",
                        )

                        st.success(f"Plan v{nueva_version} guardado correctamente.")
                        if email_ok:
                            st.success("El plan se envió por email al paciente.")
                        else:
                            st.warning(f"Plan guardado, pero el email no se envió: {email_msg}")

                        st.download_button(
                            "Descargar PDF generado",
                            data=pdf_bytes,
                            file_name=pdf_filename,
                            mime="application/pdf",
                            use_container_width=True,
                            key=f"{editor_key}_download_pdf_directo"
                        )
                        st.rerun()

                    except Exception as e:
                        st.error(f"Error al guardar: {e}")

            st.session_state[editor_key] = plan_data



# SUBIR ARCHIVO

with tab_archivo:
    section_label("Subir archivo complementario")
    st.caption("Úsalo para cargar una infografía, PDF u otro archivo de apoyo para el paciente.")

    archivo = st.file_uploader(
        "Seleccioná un archivo",
        type=["pdf", "png", "jpg", "jpeg", "webp"],
        accept_multiple_files=False,
        key="subir_archivo_complementario"
    )

    if archivo:
        st.info(f"Archivo cargado: {archivo.name}")
        st.warning("En esta etapa el archivo se carga manualmente, pero todavía no queda guardado en la base ni en Drive.")


# COMPOSICIÓN CORPORAL / INFOGRAFÍA

with tab_composicion:
    section_label("Composición corporal")
    st.caption(
        "Generá la infografía dinámica desde la historia nutricional del paciente. "
        "Se precarga la última medición y podés editarla; al guardar se crea una nueva versión en historia_nutricional."
    )

    def _fmt_fecha(x):
        if not x:
            return "—"
        try:
            return pd.to_datetime(x).strftime("%d/%m/%Y")
        except Exception:
            return str(x)[:10]

    def _safe_num(x, default=0.0):
        try:
            return float(x or default)
        except Exception:
            return default

    def _siguiente_version_historia(id_paciente_actual):
        rows = run_query("""
            SELECT COALESCE(MAX(version), 0) + 1 AS version
            FROM historia_nutricional
            WHERE id_paciente = %s
        """, (id_paciente_actual,))
        return int(rows[0]["version"] or 1) if rows else 1

    def _obtener_historia(id_paciente_actual):
        return run_query("""
            SELECT id_historia, id_paciente, id_sesion, fecha_registro, version,
                   peso, talla, imc,
                   circ_cintura, circ_cadera, circ_brazo,
                   masa_grasa_pct, masa_muscular_pct, grasa_visceral,
                   perimetro_abdominal, perimetro_torax,
                   fuente_datos, avance_objetivos, cambios_habitos, notas_medicion
            FROM historia_nutricional
            WHERE id_paciente = %s
            ORDER BY fecha_registro DESC, version DESC
        """, (id_paciente_actual,))

    def _historia_para_payload(h):
        if not h:
            return {}
        return {
            "id_historia": h.get("id_historia"),
            "version": h.get("version"),
            "fecha_medicion": str(h.get("fecha_registro") or date.today())[:10],
            "peso": h.get("peso"),
            "talla": h.get("talla"),
            "imc": h.get("imc"),
            "masa_grasa_pct": h.get("masa_grasa_pct"),
            "masa_muscular_pct": h.get("masa_muscular_pct"),
            "grasa_visceral": h.get("grasa_visceral"),
            "perimetro_abdominal": h.get("perimetro_abdominal") or h.get("circ_cintura"),
            "perimetro_cintura": h.get("circ_cintura"),
            "perimetro_cadera": h.get("circ_cadera"),
            "perimetro_brazo": h.get("circ_brazo"),
            "perimetro_torax": h.get("perimetro_torax"),
            "fuente_datos": h.get("fuente_datos"),
            "notas": h.get("notas_medicion") or h.get("avance_objetivos") or "",
        }

    historias = _obtener_historia(id_paciente)
    historia_actual = historias[0] if historias else None
    base = _historia_para_payload(historia_actual)

    if not historias:
        info_banner(
            "Este paciente todavía no tiene historia nutricional con mediciones. Podés cargar la primera medición abajo.",
            "info",
        )

    with st.container(border=True):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Paciente", nombre_paciente)
        c2.metric("DNI", paciente.get("dni") or "—")
        c3.metric("Edad", calcular_edad(paciente.get("fecha_nacimiento")) or "—")
        c4.metric("Empresa", paciente.get("empresa") or "—")

    st.markdown("### Medición a utilizar")
    st.caption(
        "La app precarga la última medición de historia nutricional. Al guardar, se registra una nueva versión, "
        "así el historial queda completo y la infografía puede comparar evaluaciones."
    )

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        fecha_base = base.get("fecha_medicion") or date.today()
        fecha_medicion = st.date_input(
            "Fecha de medición",
            value=pd.to_datetime(fecha_base).date(),
            key="comp_fecha_medicion",
        )
        peso = st.number_input("Peso (kg)", min_value=0.0, value=_safe_num(base.get("peso")), step=0.1, key="comp_peso")
        talla = st.number_input("Talla (cm)", min_value=0.0, value=_safe_num(base.get("talla")), step=0.1, key="comp_talla")
    with col_b:
        imc_default = base.get("imc") or calcular_imc(peso, talla)
        imc = st.number_input("IMC", min_value=0.0, value=_safe_num(imc_default), step=0.01, key="comp_imc")
        masa_grasa = st.number_input("Masa grasa (%)", min_value=0.0, value=_safe_num(base.get("masa_grasa_pct")), step=0.1, key="comp_masa_grasa")
        masa_muscular = st.number_input("Masa muscular (%)", min_value=0.0, value=_safe_num(base.get("masa_muscular_pct")), step=0.1, key="comp_masa_muscular")
    with col_c:
        grasa_visceral = st.number_input("Grasa visceral", min_value=0.0, value=_safe_num(base.get("grasa_visceral")), step=0.1, key="comp_visceral")
        per_abd = st.number_input("Perímetro abdominal (cm)", min_value=0.0, value=_safe_num(base.get("perimetro_abdominal") or base.get("perimetro_cintura")), step=0.1, key="comp_per_abd")
        per_cintura = st.number_input("Cintura (cm)", min_value=0.0, value=_safe_num(base.get("perimetro_cintura") or base.get("perimetro_abdominal")), step=0.1, key="comp_per_cintura")

    col_d, col_e, col_f = st.columns(3)
    with col_d:
        per_cadera = st.number_input("Cadera (cm)", min_value=0.0, value=_safe_num(base.get("perimetro_cadera")), step=0.1, key="comp_per_cadera")
    with col_e:
        per_brazo = st.number_input("Brazo (cm)", min_value=0.0, value=_safe_num(base.get("perimetro_brazo")), step=0.1, key="comp_per_brazo")
    with col_f:
        per_torax = st.number_input("Tórax (cm)", min_value=0.0, value=_safe_num(base.get("perimetro_torax")), step=0.1, key="comp_per_torax")

    notas_comp = st.text_area("Notas internas / observaciones", value=base.get("notas") or "", height=90, key="comp_notas")

    st.markdown("### Logos")
    st.caption("Podés cargar logo principal y logo empresa. Si el paciente es de empresa, el segundo logo se usa para co-branding.")
    col_logo1, col_logo2 = st.columns(2)
    with col_logo1:
        logo_dueno_file = st.file_uploader("Logo del dueño / marca principal", type=["png", "jpg", "jpeg"], key="comp_logo_dueno")
    with col_logo2:
        logo_empresa_file = st.file_uploader("Logo empresa", type=["png", "jpg", "jpeg"], key="comp_logo_empresa")

    version_preview = _siguiente_version_historia(id_paciente)
    medicion_editada = {
        "version": version_preview,
        "fecha_medicion": str(fecha_medicion),
        "sexo": paciente.get("genero"),
        "edad": calcular_edad(paciente.get("fecha_nacimiento")),
        "peso": peso or None,
        "talla": talla or None,
        "imc": imc or calcular_imc(peso, talla),
        "masa_grasa_pct": masa_grasa or None,
        "masa_muscular_pct": masa_muscular or None,
        "grasa_visceral": grasa_visceral or None,
        "perimetro_abdominal": per_abd or None,
        "perimetro_cintura": per_cintura or None,
        "perimetro_cadera": per_cadera or None,
        "perimetro_brazo": per_brazo or None,
        "perimetro_torax": per_torax or None,
        "notas": notas_comp,
        "fuente_datos": "edicion_infografia",
    }

    evaluaciones_previas = [_historia_para_payload(h) for h in reversed(historias[:3])]
    evaluaciones_preview = evaluaciones_previas + [medicion_editada]

    logo_dueno_data = logo_to_data_uri(logo_dueno_file)
    logo_empresa_data = logo_to_data_uri(logo_empresa_file)
    payload_comp = build_composicion_payload(
        paciente=paciente,
        mediciones=evaluaciones_preview,
        medicion_actual=medicion_editada,
        logo_dueno=logo_dueno_data,
        logo_empresa=logo_empresa_data,
        notas=notas_comp,
    )

    divider()
    st.markdown("### Vista previa")
    show_composicion_preview(payload_comp, height=900)

    pdf_comp = build_composicion_pdf(payload_comp)
    nombre_pdf_comp = f"infografia_composicion_{paciente['apellido']}_{paciente['nombre']}_{date.today()}.pdf".replace(" ", "_")

    col_save, col_down = st.columns(2)
    with col_down:
        st.download_button(
            "Descargar PDF de infografía",
            data=pdf_comp,
            file_name=nombre_pdf_comp,
            mime="application/pdf",
            use_container_width=True,
            key="comp_descargar_pdf",
        )

    with col_save:
        guardar_y_enviar = st.button("Guardar y enviar al paciente", type="primary", use_container_width=True, key="comp_guardar_enviar")

    if guardar_y_enviar:
        if not peso or not talla:
            st.error("Peso y talla son obligatorios para guardar la medición e infografía.")
        else:
            try:
                version_hist = _siguiente_version_historia(id_paciente)
                id_contrato = contrato[0]["id_contrato"] if contrato else None
                id_nutricionista = id_nutri or (contrato[0].get("id_nutricionista") if contrato else None)
                imc_final = imc or calcular_imc(peso, talla)

                run_command("""
                    INSERT INTO historia_nutricional
                        (id_paciente, id_sesion, version, peso, talla, imc,
                         circ_cintura, circ_cadera, circ_brazo,
                         masa_grasa_pct, masa_muscular_pct, grasa_visceral,
                         perimetro_abdominal, perimetro_torax,
                         fuente_datos, notas_medicion, creado_por)
                    VALUES (%s,NULL,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'edicion_infografia',%s,%s)
                """, (
                    id_paciente,
                    version_hist,
                    peso or None,
                    talla or None,
                    imc_final,
                    per_cintura or None,
                    per_cadera or None,
                    per_brazo or None,
                    masa_grasa or None,
                    masa_muscular or None,
                    grasa_visceral or None,
                    per_abd or None,
                    per_torax or None,
                    notas_comp,
                    usuario.get("id_usuario"),
                ))

                payload_comp["medicion_actual"]["version"] = version_hist
                contenido_json = json.dumps(payload_comp, ensure_ascii=False)
                contenido_texto = f"Infografía de composición corporal - {nombre_paciente} - {fecha_medicion}"

                ultima_version_doc = run_query("""
                    SELECT COALESCE(MAX(version), 0) AS v
                    FROM planes_nutricionales
                    WHERE id_paciente = %s
                """, (id_paciente,))
                nueva_version_doc = int(ultima_version_doc[0]["v"] or 0) + 1

                run_command("""
                    INSERT INTO planes_nutricionales
                        (id_paciente, id_contrato, id_nutricionista,
                         version, titulo, contenido, contenido_json,
                         estado, fecha_vigencia, archivo_url)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, 'activo', %s, %s)
                """, (
                    id_paciente,
                    id_contrato,
                    id_nutricionista,
                    nueva_version_doc,
                    "Infografía de composición corporal",
                    contenido_texto,
                    contenido_json,
                    date.today() + timedelta(days=30),
                    None,
                ))

                email_ok, email_msg = send_plan_email(
                    to_email=paciente.get("email", ""),
                    patient_name=nombre_paciente,
                    pdf_bytes=pdf_comp,
                    pdf_filename=nombre_pdf_comp,
                    subject="Tu infografía de composición corporal",
                )

                st.success("Infografía guardada correctamente.")
                if email_ok:
                    st.success("La infografía se envió por email al paciente.")
                else:
                    st.warning(f"Infografía guardada, pero el email no se envió: {email_msg}")
                st.rerun()
            except Exception as e:
                st.error(f"Error al guardar la infografía: {e}")