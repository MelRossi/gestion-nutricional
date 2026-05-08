from datetime import date, timedelta
import unicodedata

import altair as alt
import pandas as pd
import streamlit as st

from database import run_query, run_command
from utils import mostrar_sidebar, page_header, info_banner



# CONTROL DE ACCESO

if "usuario" not in st.session_state:
    st.warning("Debés iniciar sesión.")
    st.stop()

if st.session_state["usuario"]["rol"] not in ("administrador", "nutricionista"):
    st.error("No tenés permisos.")
    st.stop()

usuario = st.session_state["usuario"]
rol = usuario["rol"]
id_nutri = usuario.get("id_nutricionista")
id_usuario = usuario.get("id_usuario") or id_nutri

mostrar_sidebar()
page_header("Pacientes")


# HELPERS

def normalizar(texto):
    if not texto:
        return ""
    texto = str(texto).lower().strip()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto


def fmt_fecha(valor):
    if valor is None or valor == "":
        return "—"
    try:
        return pd.to_datetime(valor).strftime("%d/%m/%Y")
    except Exception:
        return str(valor)[:10]


def safe_int(valor, default=0):
    try:
        return int(valor or default)
    except Exception:
        return default


def tipo_paciente_visual(valor):
    return "Empresa" if (valor or "persona").lower() == "empresa" else "Persona"


def estado_contrato_visual(row):
    estado_raw = row.get("estado_contrato")
    estado = "" if pd.isna(estado_raw) else str(estado_raw).lower()
    fecha_fin_real = row.get("fecha_fin_real")
    fecha_fin_teorica = row.get("fecha_fin_teorica")
    realizadas = safe_int(row.get("sesiones_realizadas"))
    total = safe_int(row.get("cantidad_sesiones"))
    fecha_control = fecha_fin_real or fecha_fin_teorica

    if not estado:
        return "Sin contrato"

    if estado in ("cancelado", "cancelada"):
        return "Cancelado"

    if estado in ("finalizado", "finalizada", "cerrado", "cerrada"):
        return "Finalizado"

    if fecha_control:
        try:
            if pd.to_datetime(fecha_control).date() < date.today() and estado == "activo":
                return "Vencido"
        except Exception:
            pass

    if total > 0 and realizadas >= total:
        return "Completado"

    if estado == "activo":
        return "Activo"

    return estado.capitalize()


def abrir_ficha(id_paciente):
    st.session_state["id_paciente_ficha"] = int(id_paciente)
    st.switch_page("pages/3_ficha_paciente.py")


def preparar_df_pacientes(registros, incluir_nutricionista=False):
    if not registros:
        return pd.DataFrame(), []

    df = pd.DataFrame(registros)

    df["Realizadas"] = df["sesiones_realizadas"].fillna(0).astype(int)
    df["Total"] = df["cantidad_sesiones"].fillna(0).astype(int)
    df["Restantes"] = (df["Total"] - df["Realizadas"]).clip(lower=0)

    df["Contrato"] = df.apply(estado_contrato_visual, axis=1)
    df["Inicio"] = df["fecha_inicio"].apply(fmt_fecha)
    df["Fin teórico"] = df["fecha_fin_teorica"].apply(fmt_fecha)
    df["Fin real"] = df["fecha_fin_real"].apply(fmt_fecha)

    df["Tipo"] = df["tipo_paciente"].apply(tipo_paciente_visual)
    df["Empresa"] = df["empresa"].fillna("—") if "empresa" in df.columns else "—"

    df["Reprogramaciones"] = (
        df["reprogramaciones_usadas"].fillna(0).astype(int).astype(str)
        + "/"
        + df["reprogramaciones_max"].fillna(0).astype(int).astype(str)
    )

    df = df.rename(
        columns={
            "paciente": "Paciente",
            "programa": "Programa",
            "nutricionista": "Nutricionista",
        }
    )

    df["_fecha_orden"] = pd.to_datetime(df.get("fecha_inicio"), errors="coerce")
    df = df.sort_values("_fecha_orden", ascending=False, na_position="last")
    df = df.drop(columns=["_fecha_orden"], errors="ignore")

    # Importante para st.dataframe(on_select):
    # al ordenar, pandas conserva el índice original; Streamlit puede devolver
    # la fila seleccionada según el índice visible/interno y abrir otra ficha.
    # Resetear el índice evita desfasajes entre la fila seleccionada y el id_paciente.
    df = df.reset_index(drop=True)

    cols = ["Paciente", "Tipo", "Empresa", "Programa"]

    if incluir_nutricionista:
        cols.append("Nutricionista")

    cols += [
        "Realizadas",
        "Restantes",
        "Contrato",
        "Inicio",
        "Fin teórico",
        "Fin real",
        "Reprogramaciones",
    ]

    return df, [c for c in cols if c in df.columns]


def filtrar_pacientes(registros, key_prefix="filtros"):
    if not registros:
        return []

    buscar = st.text_input(
        "Buscar por nombre",
        key=f"{key_prefix}_buscar_nombre",
    )

    registros_filtrables = registros

    if buscar:
        buscar_norm = normalizar(buscar)

        coincidencias = [
            r for r in registros
            if buscar_norm in normalizar(r.get("paciente"))
        ]

        if coincidencias:
            opciones = {
                f"{r.get('paciente')} · {r.get('programa') or 'Sin programa'}": r
                for r in coincidencias[:10]
            }

            paciente_elegido = st.selectbox(
                "Coincidencias",
                ["Ver todos los resultados"] + list(opciones.keys()),
                key=f"{key_prefix}_coincidencias_nombre",
            )

            if paciente_elegido != "Ver todos los resultados":
                registros_filtrables = [opciones[paciente_elegido]]
            else:
                registros_filtrables = coincidencias
        else:
            st.caption("Sin coincidencias")
            registros_filtrables = []

    col1, col2, col3 = st.columns(3)

    with col1:
        tipos = ["Todos"] + sorted({tipo_paciente_visual(r.get("tipo_paciente")) for r in registros})
        tipo_sel = st.selectbox("Tipo de paciente", tipos, key=f"{key_prefix}_tipo")

    with col2:
        empresas = ["Todas"] + sorted({r.get("empresa") or "Sin empresa" for r in registros})
        empresa_sel = st.selectbox("Empresa", empresas, key=f"{key_prefix}_empresa")

    with col3:
        estados = ["Todos"] + sorted({estado_contrato_visual(r) for r in registros})
        estado_sel = st.selectbox("Estado", estados, key=f"{key_prefix}_estado")

    filtrados = []

    for r in registros_filtrables:
        if tipo_sel != "Todos" and tipo_paciente_visual(r.get("tipo_paciente")) != tipo_sel:
            continue

        empresa_r = r.get("empresa") or "Sin empresa"
        if empresa_sel != "Todas" and empresa_r != empresa_sel:
            continue

        if estado_sel != "Todos" and estado_contrato_visual(r) != estado_sel:
            continue

        filtrados.append(r)

    return filtrados


def render_desempeno_paciente(id_paciente):
    resumen = run_query(
        """
        SELECT
            COUNT(c.id_contrato) AS programas_total,
            COUNT(*) FILTER (
                WHERE COALESCE((
                    SELECT COUNT(*)
                    FROM sesiones s
                    WHERE s.id_contrato = c.id_contrato
                      AND s.estado = 'atendida'
                ), 0) >= pr.cantidad_sesiones
            ) AS programas_completados,
            COALESCE(SUM(c.reprogramaciones_usadas), 0) AS reprogramaciones_totales
        FROM contratos c
        JOIN programas pr ON pr.id_programa = c.id_programa
        WHERE c.id_paciente = %s
        """,
        (id_paciente,),
    )

    historia = run_query(
        """
        SELECT version, peso, imc, fecha_registro
        FROM historia_nutricional
        WHERE id_paciente = %s
        ORDER BY version
        """,
        (id_paciente,),
    )

    if not resumen:
        return

    r = resumen[0]

    st.markdown("### Desempeño del paciente")

    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric("Programas", safe_int(r.get("programas_total")))

    with c2:
        st.metric("Completados", safe_int(r.get("programas_completados")))

    with c3:
        st.metric("Reprogramaciones totales", safe_int(r.get("reprogramaciones_totales")))

    if historia and len(historia) >= 2:
        df_h = pd.DataFrame(historia)

        df_lineas = df_h.melt(
            id_vars=["version", "fecha_registro"],
            value_vars=["peso", "imc"],
            var_name="Indicador",
            value_name="Valor",
        ).dropna()

        if not df_lineas.empty:
            chart = alt.Chart(df_lineas).mark_line(point=True).encode(
                x=alt.X(
                    "version:O",
                    title="Medición / sesión",
                    axis=alt.Axis(labelAngle=0),
                ),
                y=alt.Y(
                    "Valor:Q",
                    title="Evolución",
                    scale=alt.Scale(zero=False),
                ),
                color=alt.Color(
                    "Indicador:N",
                    scale=alt.Scale(
                        domain=["peso", "imc"],
                        range=["#00DC8E", "#FFCC33"],
                    ),
                    legend=alt.Legend(title="Indicador"),
                ),
                tooltip=["version", "Indicador", "Valor"],
            ).properties(height=220)

            st.altair_chart(chart, use_container_width=True)
    else:
        st.info("Todavía no hay suficientes mediciones para mostrar evolución.")


def render_tabla_pacientes(registros, incluir_nutricionista=False, key_prefix="pac"):
    if not registros:
        st.info("No hay pacientes para mostrar.")
        return

    df, cols = preparar_df_pacientes(
        registros,
        incluir_nutricionista=incluir_nutricionista,
    )

    # Seguridad: tabla interna con índice limpio y el id oculto.
    # La tabla visible NO muestra id_paciente, pero la selección queda vinculada
    # al id real guardado en df.
    df = df.reset_index(drop=True)
    df_visible = df[cols].copy().reset_index(drop=True)

    st.markdown(f"**{len(df)} paciente(s)**")

    evento = st.dataframe(
        df_visible,
        use_container_width=True,
        height=390,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"{key_prefix}_tabla_pacientes",
    )

    # IMPORTANTE:
    # Al hacer click en "Abrir ficha", Streamlit vuelve a ejecutar la página.
    # Si usamos directamente evento.selection en ese rerun, puede abrir otra fila.
    # Por eso guardamos el id seleccionado en session_state en el momento de selección
    # y el botón abre SIEMPRE ese id guardado.
    try:
        filas = evento.selection.rows
        if filas:
            pos = int(filas[0])
            if 0 <= pos < len(df):
                seleccion = df.iloc[pos]
                st.session_state[f"{key_prefix}_paciente_sel_id"] = int(seleccion["id_paciente"])
                st.session_state[f"{key_prefix}_paciente_sel_nombre"] = str(seleccion["Paciente"])
    except Exception:
        pass

    id_sel = st.session_state.get(f"{key_prefix}_paciente_sel_id")
    nombre_sel = st.session_state.get(f"{key_prefix}_paciente_sel_nombre")

    if id_sel:
        col_a, col_b = st.columns([3, 1])

        with col_a:
            st.caption(f"Seleccionaste: {nombre_sel}")

        with col_b:
            if st.button(
                "Abrir ficha",
                use_container_width=True,
                type="primary",
                key=f"{key_prefix}_abrir_ficha",
            ):
                abrir_ficha(int(id_sel))

        st.markdown("---")
        render_desempeno_paciente(int(id_sel))



# VISTA ADMIN

if rol == "administrador":

    solicitudes = run_query(
        """
        SELECT pa.id_permiso,
               pa.id_paciente,
               pa.id_nutricionista,
               p.nombre||' '||p.apellido AS paciente,
               nb.nombre||' '||nb.apellido AS nutricionista_solicitante,
               na.nombre||' '||na.apellido AS nutricionista_actual,
               c.id_contrato,
               c.id_nutricionista AS id_nutricionista_actual,
               pr.nombre AS programa,
               pa.estado,
               pa.fecha_solicitud,
               pa.motivo
        FROM permisos_acceso pa
        JOIN pacientes p       ON pa.id_paciente = p.id_paciente
        JOIN nutricionistas nb ON pa.id_nutricionista = nb.id_nutricionista
        JOIN contratos c       ON p.id_paciente = c.id_paciente AND c.estado = 'activo'
        JOIN programas pr      ON c.id_programa = pr.id_programa
        JOIN nutricionistas na ON c.id_nutricionista = na.id_nutricionista
        WHERE pa.estado = 'pendiente'
        ORDER BY pa.fecha_solicitud DESC
        """
    )

    if solicitudes:
        info_banner(
            f"Hay {len(solicitudes)} solicitud(es) de acceso pendiente(s).",
            "warning",
        )

        for s in solicitudes:
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 2, 3])

                with col1:
                    st.markdown(
                        f"🟡 **{s['nutricionista_solicitante']}** solicita acceso a **{s['paciente']}**"
                    )
                    st.caption(
                        f"Nutricionista actual: {s['nutricionista_actual']} · Programa: {s['programa']}"
                    )
                    if s.get("motivo"):
                        st.caption(f"Motivo: {s['motivo']}")
                    st.caption(f"Solicitado: {fmt_fecha(s['fecha_solicitud'])}")

                with col2:
                    tipo = st.selectbox(
                        "Tipo de acceso",
                        ["Temporal", "Permanente (reasignar)"],
                        key=f"tipo_{s['id_permiso']}",
                    )

                    if tipo == "Temporal":
                        sesiones_rest = st.number_input(
                            "Cantidad de citas",
                            min_value=1,
                            max_value=20,
                            value=4,
                            step=1,
                            key=f"ses_{s['id_permiso']}",
                        )
                        f_exp = date.today() + timedelta(weeks=int(sesiones_rest) * 2)
                        st.caption(f"Expira aprox.: {f_exp.strftime('%d/%m/%Y')}")
                    else:
                        f_exp = None

                with col3:
                    ca, cb = st.columns(2)

                    with ca:
                        if st.button(
                            "Aprobar",
                            key=f"apr_{s['id_permiso']}",
                            use_container_width=True,
                            type="primary",
                        ):
                            if tipo == "Permanente (reasignar)":
                                run_command(
                                    """
                                    INSERT INTO historial_asignaciones_paciente
                                        (id_paciente, id_contrato, id_nutricionista_anterior,
                                         id_nutricionista_nueva, tipo_cambio, motivo, creado_por)
                                    VALUES (%s, %s, %s, %s, 'reasignacion_permanente', %s, %s)
                                    """,
                                    (
                                        s["id_paciente"],
                                        s["id_contrato"],
                                        s["id_nutricionista_actual"],
                                        s["id_nutricionista"],
                                        s.get("motivo"),
                                        id_usuario,
                                    ),
                                )

                                run_command(
                                    """
                                    UPDATE contratos
                                    SET id_nutricionista = pa.id_nutricionista
                                    FROM permisos_acceso pa
                                    WHERE contratos.id_paciente = pa.id_paciente
                                      AND pa.id_permiso = %s
                                      AND contratos.estado = 'activo'
                                    """,
                                    (s["id_permiso"],),
                                )

                                run_command(
                                    """
                                    UPDATE sesiones
                                    SET id_nutricionista_prog = pa.id_nutricionista
                                    FROM permisos_acceso pa
                                    JOIN contratos c ON c.id_paciente = pa.id_paciente
                                    WHERE sesiones.id_contrato = c.id_contrato
                                      AND pa.id_permiso = %s
                                      AND sesiones.estado = 'programada'
                                    """,
                                    (s["id_permiso"],),
                                )

                                run_command(
                                    """
                                    UPDATE permisos_acceso
                                    SET estado='aprobado',
                                        fecha_expiracion=NULL,
                                        aprobado_por=%s,
                                        fecha_resolucion=NOW()
                                    WHERE id_permiso=%s
                                    """,
                                    (id_usuario, s["id_permiso"]),
                                )

                                st.success("Paciente reasignado permanentemente.")
                            else:
                                run_command(
                                    """
                                    UPDATE permisos_acceso
                                    SET estado='aprobado',
                                        fecha_expiracion=%s,
                                        aprobado_por=%s,
                                        fecha_resolucion=NOW()
                                    WHERE id_permiso=%s
                                    """,
                                    (f_exp, id_usuario, s["id_permiso"]),
                                )

                                st.success(f"Acceso temporal aprobado hasta {fmt_fecha(f_exp)}.")

                            st.rerun()

                    with cb:
                        if st.button(
                            "Rechazar",
                            key=f"rec_{s['id_permiso']}",
                            use_container_width=True,
                        ):
                            run_command(
                                """
                                UPDATE permisos_acceso
                                SET estado='rechazado',
                                    aprobado_por=%s,
                                    fecha_resolucion=NOW()
                                WHERE id_permiso=%s
                                """,
                                (id_usuario, s["id_permiso"]),
                            )
                            st.rerun()

        st.markdown("---")

    with st.expander("Reasignar paciente directamente"):
        pac_list = run_query(
            """
            SELECT p.id_paciente,
                   p.nombre||' '||p.apellido AS nombre,
                   n.nombre||' '||n.apellido AS nutricionista_actual,
                   c.id_nutricionista AS id_nutricionista_actual,
                   pr.nombre AS programa,
                   c.id_contrato
            FROM pacientes p
            JOIN contratos c      ON p.id_paciente=c.id_paciente
            JOIN nutricionistas n ON c.id_nutricionista=n.id_nutricionista
            JOIN programas pr     ON c.id_programa=pr.id_programa
            WHERE c.estado='activo'
            ORDER BY p.apellido, p.nombre
            """
        )

        nutr_list = run_query(
            """
            SELECT id_nutricionista,
                   nombre||' '||apellido AS nombre
            FROM nutricionistas
            WHERE estado=TRUE
            ORDER BY apellido, nombre
            """
        )

        if pac_list and nutr_list:
            col1, col2 = st.columns(2)

            with col1:
                pac_opts = {
                    f"{p['nombre']} ({p['nutricionista_actual']})": p
                    for p in pac_list
                }
                pac_sel = st.selectbox("Paciente", list(pac_opts.keys()), key="reas_pac")

            with col2:
                nutr_opts = {n["nombre"]: n["id_nutricionista"] for n in nutr_list}
                nutr_sel = st.selectbox("Nueva nutricionista", list(nutr_opts.keys()), key="reas_nutr")

            tipo_r = st.radio(
                "Tipo",
                ["Permanente", "Temporal"],
                horizontal=True,
                key="tipo_reas",
            )

            f_exp_r = None

            if tipo_r == "Temporal":
                sesiones_r = st.number_input(
                    "Cantidad de citas",
                    min_value=1,
                    max_value=20,
                    value=4,
                    step=1,
                    key="ses_reas",
                )
                f_exp_r = date.today() + timedelta(weeks=int(sesiones_r) * 2)
                st.caption(f"Expira aprox.: {f_exp_r.strftime('%d/%m/%Y')}")

            pac_data = pac_opts[pac_sel]

            st.info(
                f"**{pac_data['nombre']}** pasará de **{pac_data['nutricionista_actual']}** a **{nutr_sel}**"
            )

            if st.button(
                "Aplicar",
                use_container_width=True,
                type="primary",
                key="btn_reas",
            ):
                nueva_id = nutr_opts[nutr_sel]

                if tipo_r == "Permanente":
                    run_command(
                        """
                        INSERT INTO historial_asignaciones_paciente
                            (id_paciente, id_contrato, id_nutricionista_anterior,
                             id_nutricionista_nueva, tipo_cambio, motivo, creado_por)
                        VALUES (%s, %s, %s, %s, 'reasignacion_directa', %s, %s)
                        """,
                        (
                            pac_data["id_paciente"],
                            pac_data["id_contrato"],
                            pac_data["id_nutricionista_actual"],
                            nueva_id,
                            "Reasignación directa desde administración",
                            id_usuario,
                        ),
                    )

                    run_command(
                        "UPDATE contratos SET id_nutricionista=%s WHERE id_contrato=%s",
                        (nueva_id, pac_data["id_contrato"]),
                    )

                    run_command(
                        """
                        UPDATE sesiones
                        SET id_nutricionista_prog=%s
                        WHERE id_contrato=%s
                          AND estado='programada'
                        """,
                        (nueva_id, pac_data["id_contrato"]),
                    )

                    st.success(f"{pac_data['nombre']} reasignado permanentemente a {nutr_sel}.")
                else:
                    run_command(
                        """
                        INSERT INTO permisos_acceso
                            (id_nutricionista, id_paciente, estado, solicitado_por,
                             fecha_solicitud, fecha_expiracion, motivo)
                        VALUES (%s, %s, 'aprobado', %s, NOW(), %s, %s)
                        ON CONFLICT (id_nutricionista, id_paciente)
                        DO UPDATE SET estado='aprobado',
                                      fecha_expiracion=%s,
                                      motivo=%s
                        """,
                        (
                            nueva_id,
                            pac_data["id_paciente"],
                            id_usuario,
                            f_exp_r,
                            "Acceso temporal otorgado por administración",
                            f_exp_r,
                            "Acceso temporal otorgado por administración",
                        ),
                    )

                    st.success(f"Acceso temporal hasta {fmt_fecha(f_exp_r)} otorgado a {nutr_sel}.")

                st.rerun()
        else:
            st.info("No hay pacientes o nutricionistas disponibles para reasignar.")

    st.markdown("---")
    st.subheader("Todos los pacientes")

    pacientes = run_query(
        """
        SELECT DISTINCT ON (p.id_paciente)
               p.id_paciente,
               p.nombre||' '||p.apellido AS paciente,
               p.tipo_paciente,
               e.nombre AS empresa,
               pr.nombre AS programa,
               n.nombre||' '||n.apellido AS nutricionista,
               c.estado AS estado_contrato,
               c.fecha_inicio,
               c.fecha_fin_teorica,
               c.fecha_fin_real,
               c.id_contrato,
               pr.cantidad_sesiones,
               c.reprogramaciones_usadas,
               COALESCE(c.reprogramaciones_max_override, pr.reprogramaciones_max) AS reprogramaciones_max,
               COALESCE((
                    SELECT COUNT(*)
                    FROM sesiones s
                    WHERE s.id_contrato=c.id_contrato
                      AND s.estado='atendida'
               ), 0) AS sesiones_realizadas
        FROM pacientes p
        LEFT JOIN empresas e ON p.id_empresa = e.id_empresa
        LEFT JOIN contratos c ON p.id_paciente = c.id_paciente
        LEFT JOIN programas pr ON c.id_programa = pr.id_programa
        LEFT JOIN nutricionistas n ON c.id_nutricionista = n.id_nutricionista
        ORDER BY p.id_paciente,
                 CASE WHEN c.estado='activo' THEN 0 ELSE 1 END,
                 c.fecha_inicio DESC NULLS LAST
        """
    )

    pacientes_filtrados = filtrar_pacientes(
        pacientes,
        key_prefix="admin_pac",
    )

    render_tabla_pacientes(
        pacientes_filtrados,
        incluir_nutricionista=True,
        key_prefix="admin",
    )



# VISTA NUTRICIONISTA

else:
    tab1, tab2 = st.tabs(["Pacientes", "Solicitar acceso a paciente"])

    with tab1:
        pacientes = run_query(
            """
            SELECT DISTINCT ON (p.id_paciente)
                   p.id_paciente,
                   p.nombre||' '||p.apellido AS paciente,
                   p.tipo_paciente,
                   e.nombre AS empresa,
                   pr.nombre AS programa,
                   n.nombre||' '||n.apellido AS nutricionista,
                   c.estado AS estado_contrato,
                   c.fecha_inicio,
                   c.fecha_fin_teorica,
                   c.fecha_fin_real,
                   c.id_contrato,
                   pr.cantidad_sesiones,
                   c.reprogramaciones_usadas,
                   COALESCE(c.reprogramaciones_max_override, pr.reprogramaciones_max) AS reprogramaciones_max,
                   COALESCE((
                        SELECT COUNT(*)
                        FROM sesiones s
                        WHERE s.id_contrato=c.id_contrato
                          AND s.estado='atendida'
                   ), 0) AS sesiones_realizadas
            FROM pacientes p
            JOIN contratos c ON p.id_paciente=c.id_paciente
            JOIN programas pr ON c.id_programa=pr.id_programa
            JOIN nutricionistas n ON c.id_nutricionista=n.id_nutricionista
            LEFT JOIN empresas e ON p.id_empresa=e.id_empresa
            WHERE c.id_nutricionista=%s
            ORDER BY p.id_paciente,
                     CASE WHEN c.estado='activo' THEN 0 ELSE 1 END,
                     c.fecha_inicio DESC NULLS LAST
            """,
            (id_nutri,),
        )

        con_permiso = run_query(
            """
            SELECT DISTINCT ON (p.id_paciente)
                   p.id_paciente,
                   p.nombre||' '||p.apellido AS paciente,
                   p.tipo_paciente,
                   e.nombre AS empresa,
                   pr.nombre AS programa,
                   n.nombre||' '||n.apellido AS nutricionista,
                   c.estado AS estado_contrato,
                   c.fecha_inicio,
                   c.fecha_fin_teorica,
                   c.fecha_fin_real,
                   c.id_contrato,
                   pr.cantidad_sesiones,
                   c.reprogramaciones_usadas,
                   COALESCE(c.reprogramaciones_max_override, pr.reprogramaciones_max) AS reprogramaciones_max,
                   COALESCE((
                        SELECT COUNT(*)
                        FROM sesiones s
                        WHERE s.id_contrato=c.id_contrato
                          AND s.estado='atendida'
                   ), 0) AS sesiones_realizadas
            FROM permisos_acceso pa
            JOIN pacientes p ON pa.id_paciente=p.id_paciente
            JOIN contratos c ON p.id_paciente=c.id_paciente
            JOIN programas pr ON c.id_programa=pr.id_programa
            JOIN nutricionistas n ON c.id_nutricionista=n.id_nutricionista
            LEFT JOIN empresas e ON p.id_empresa=e.id_empresa
            WHERE pa.id_nutricionista=%s
              AND pa.estado='aprobado'
              AND (pa.fecha_expiracion IS NULL OR pa.fecha_expiracion >= CURRENT_DATE)
            ORDER BY p.id_paciente,
                     CASE WHEN c.estado='activo' THEN 0 ELSE 1 END,
                     c.fecha_inicio DESC NULLS LAST
            """,
            (id_nutri,),
        )

        ids = {p["id_paciente"] for p in pacientes}
        for p in con_permiso:
            if p["id_paciente"] not in ids:
                pacientes.append(p)

        pacientes_filtrados = filtrar_pacientes(
            pacientes,
            key_prefix="nutri_pac",
        )

        render_tabla_pacientes(
            pacientes_filtrados,
            incluir_nutricionista=False,
            key_prefix="nutri",
        )

    with tab2:
        st.subheader("Solicitar acceso a un paciente")
        st.caption(
            "El admin aprobará o rechazará tu solicitud. La nutricionista original quedará informada en el panel de solicitudes."
        )

        buscar_pac = st.text_input(
            "Nombre o email del paciente (mínimo 3 caracteres)",
            key="buscar_acceso",
        )

        if buscar_pac and len(buscar_pac) >= 3:
            resultados = run_query(
                """
                SELECT DISTINCT p.id_paciente,
                       p.nombre||' '||p.apellido AS nombre,
                       p.email,
                       pr.nombre AS programa,
                       n.nombre||' '||n.apellido AS nutricionista_actual
                FROM pacientes p
                JOIN contratos c ON p.id_paciente=c.id_paciente AND c.estado='activo'
                JOIN programas pr ON c.id_programa=pr.id_programa
                JOIN nutricionistas n ON c.id_nutricionista=n.id_nutricionista
                WHERE c.id_nutricionista != %s
                  AND (
                    LOWER(p.nombre||' '||p.apellido) LIKE %s
                    OR LOWER(COALESCE(p.email,'')) LIKE %s
                  )
                ORDER BY nombre
                """,
                (
                    id_nutri,
                    f"%{buscar_pac.lower()}%",
                    f"%{buscar_pac.lower()}%",
                ),
            )

            if resultados:
                for r in resultados:
                    with st.container(border=True):
                        col1, col2 = st.columns([3, 1.4])

                        with col1:
                            st.markdown(f"**{r['nombre']}**")
                            st.caption(
                                f"Programa: {r['programa']} · Nutricionista original: {r['nutricionista_actual']}"
                            )

                        with col2:
                            tipo_solicitud = st.selectbox(
                                "Tipo",
                                ["Temporal", "Permanente"],
                                key=f"tipo_sol_{r['id_paciente']}",
                            )

                            citas = None
                            if tipo_solicitud == "Temporal":
                                citas = st.number_input(
                                    "Citas a atender",
                                    min_value=1,
                                    max_value=20,
                                    value=1,
                                    step=1,
                                    key=f"citas_sol_{r['id_paciente']}",
                                )

                            motivo = st.text_input(
                                "Motivo",
                                key=f"mot_{r['id_paciente']}",
                            )

                            if st.button(
                                "Solicitar",
                                key=f"sol_{r['id_paciente']}",
                                use_container_width=True,
                            ):
                                motivo_final = f"[{tipo_solicitud}"

                                if citas:
                                    motivo_final += f" · {citas} cita(s)"

                                motivo_final += "]"

                                if motivo:
                                    motivo_final += f" {motivo}"

                                run_command(
                                    """
                                    INSERT INTO permisos_acceso
                                        (id_nutricionista, id_paciente, estado,
                                         solicitado_por, fecha_solicitud, motivo)
                                    VALUES (%s, %s, 'pendiente', %s, NOW(), %s)
                                    """,
                                    (
                                        id_nutri,
                                        r["id_paciente"],
                                        id_usuario,
                                        motivo_final,
                                    ),
                                )

                                st.success("Solicitud enviada.")
                                st.rerun()
            else:
                st.info("No se encontraron pacientes.")
        elif buscar_pac:
            st.caption("Ingresa al menos 3 caracteres.")