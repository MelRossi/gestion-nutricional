# -*- coding: utf-8 -*-
import json
from copy import deepcopy
from datetime import date, timedelta

import streamlit as st
from database import run_query, run_command
from utils import mostrar_sidebar, page_header, section_label, info_banner, divider
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

# ─────────────────────────────────────────
# CONTROL DE ACCESO
# ─────────────────────────────────────────
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

# ─────────────────────────────────────────
# PACIENTE
# ─────────────────────────────────────────

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
    SELECT p.id_paciente, p.nombre, p.apellido, p.email, p.telefono
    FROM pacientes p
    WHERE p.id_paciente = %s
""", (id_paciente,))

if not paciente_rs:
    st.error("Paciente no encontrado.")
    st.stop()

paciente = paciente_rs[0]
nombre_paciente = f"{paciente['nombre']} {paciente['apellido']}".strip()

contrato = run_query("""
    SELECT c.id_contrato, pr.nombre AS programa
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

# ─────────────────────────────────────────
# HISTORIAL + BUSCADOR
# ─────────────────────────────────────────
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

        vigencia_txt = str(plan_sel["fecha_vigencia"])[:10] if plan_sel["fecha_vigencia"] else "—"
        st.caption(
            f"Nutricionista: {plan_sel['nutricionista']} · Estado: {plan_sel['estado']} · Vigencia: {vigencia_txt}"
        )

        col_btn1, col_btn2 = st.columns([1, 1])
        with col_btn1:
            if parsed["kind"] == "structured":
                pdf_hist = build_plan_pdf(parsed["data"])
                st.download_button(
                    "Descargar PDF",
                    data=pdf_hist,
                    file_name=f"plan_{plan_sel['version']}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key=f"descargar_historial_{plan_sel['id_plan']}"
                )
        with col_btn2:
            if plan_sel.get("archivo_url"):
                st.link_button("Abrir archivo", plan_sel["archivo_url"], use_container_width=True)

        st.markdown("---")
        if parsed["kind"] == "structured":
            show_plan_preview(parsed["data"], height=920)
        else:
            st.info("Este plan pertenece al formato anterior.")
            st.markdown(parsed["legacy_text"] or "—")
    else:
        st.info("No se encontraron planes para ese criterio.")

divider()

# ─────────────────────────────────────────
# PESTAÑAS
# ─────────────────────────────────────────
tab_modelo, tab_plan, tab_archivo = st.tabs(["Crear modelo", "Crear plan", "Subir archivo"])

# ============================================================
# CREAR MODELO
# ============================================================
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

# ============================================================
# CREAR PLAN
# ============================================================
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

            st.markdown("### Cabecera")
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
            st.markdown("### Vista previa")
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
                    pdf_filename = f"plan_{paciente['nombre']}_{paciente['apellido']}_v{nueva_version}.pdf".replace(" ", "_")

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

                except Exception as e:
                    st.error(f"Error al guardar: {e}")

            st.session_state[editor_key] = plan_data

# ============================================================
# SUBIR ARCHIVO
# ============================================================
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