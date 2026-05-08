import datetime
from datetime import date

import pandas as pd
import streamlit as st

from database import run_query, run_command
from utils import mostrar_sidebar, page_header, info_banner, section_label


if "usuario" not in st.session_state:
    st.warning("Debe iniciar sesión.")
    st.stop()

if st.session_state["usuario"]["rol"] != "administrador":
    st.error("Solo administradores.")
    st.stop()

usuario = st.session_state["usuario"]
registrado_por = usuario.get("email") or str(usuario.get("id_usuario") or "admin")

mostrar_sidebar()
page_header("Contratos y reprogramaciones")


def fmt_fecha(x):
    if not x:
        return "—"
    try:
        return pd.to_datetime(x).strftime("%d/%m/%Y")
    except Exception:
        return str(x)[:10]


def safe_float(x, default=0.0):
    try:
        return float(x or default)
    except Exception:
        return default


def estado_contrato_visual(row):
    estado = (row.get("estado") or "").lower()
    fecha_fin_teorica = row.get("fecha_fin_teorica") or row.get("fecha_fin")
    sesiones_realizadas = int(row.get("sesiones_realizadas") or 0)
    cantidad_sesiones = int(row.get("cantidad_sesiones") or 0)

    if estado in ("cancelado", "finalizado", "pausado", "pendiente_pago"):
        return estado.replace("_", " ").capitalize()

    if cantidad_sesiones > 0 and sesiones_realizadas >= cantidad_sesiones:
        return "Completado"

    if fecha_fin_teorica:
        try:
            if pd.to_datetime(fecha_fin_teorica).date() < date.today() and sesiones_realizadas < cantidad_sesiones:
                return "Vencido"
        except Exception:
            pass

    if estado == "activo":
        return "Activo"

    return estado.capitalize() if estado else "—"



tab_reprog, tab_contratos = st.tabs(["Reprogramaciones", "Ver contratos"])



# VER CONTRATOS

with tab_contratos:
    section_label("Ver contratos")

    filtro_estado = st.selectbox(
        "Estado",
        ["todos", "activo", "pendiente_pago", "finalizado", "cancelado", "vencido"],
        key="ct_est",
    )

    q = """
        SELECT c.id_contrato,
               c.fecha_inicio,
               c.fecha_fin,
               c.fecha_fin_teorica,
               c.fecha_fin_real,
               c.estado,
               c.precio_final,
               c.metodo_pago,
               c.reprogramaciones_usadas,
               COALESCE(c.reprogramaciones_max_override, pr.reprogramaciones_max) AS reprog_max,
               c.fecha_ultima_reprogramacion,
               p.nombre || ' ' || p.apellido AS paciente,
               n.nombre || ' ' || n.apellido AS nutricionista,
               pr.nombre AS programa,
               pr.cantidad_sesiones,
               COALESCE((
                    SELECT COUNT(*)
                    FROM sesiones s
                    WHERE s.id_contrato = c.id_contrato
                      AND s.estado = 'atendida'
               ), 0) AS sesiones_realizadas,
               COALESCE((
                    SELECT SUM(pg.monto_pagado)
                    FROM pagos pg
                    WHERE pg.id_contrato = c.id_contrato
               ), 0) AS total_pagado
        FROM contratos c
        JOIN pacientes p      ON c.id_paciente = p.id_paciente
        JOIN nutricionistas n ON c.id_nutricionista = n.id_nutricionista
        JOIN programas pr     ON c.id_programa = pr.id_programa
    """

    params = []

    if filtro_estado != "todos":
        q += " WHERE c.estado = %s"
        params.append(filtro_estado)

    q += " ORDER BY c.fecha_inicio DESC"

    contratos = run_query(q, params or None)

    if contratos:
        df = pd.DataFrame(contratos)

        df["Estado visual"] = df.apply(estado_contrato_visual, axis=1)
        df["Sesiones"] = df.apply(
            lambda r: f"{int(r['sesiones_realizadas'])}/{int(r['cantidad_sesiones'])}",
            axis=1,
        )
        df["Reprog."] = df.apply(
            lambda r: f"{int(r['reprogramaciones_usadas'])}/{int(r['reprog_max'])}",
            axis=1,
        )
        df["Precio"] = df["precio_final"].apply(lambda x: f"S/ {safe_float(x):,.2f}")
        df["Pagado"] = df["total_pagado"].apply(lambda x: f"S/ {safe_float(x):,.2f}")
        df["Saldo"] = df.apply(
            lambda r: f"S/ {max(safe_float(r['precio_final']) - safe_float(r['total_pagado']), 0):,.2f}",
            axis=1,
        )
        df["Inicio"] = df["fecha_inicio"].apply(fmt_fecha)
        df["Fin teórico"] = df.apply(
            lambda r: fmt_fecha(r.get("fecha_fin_teorica") or r.get("fecha_fin")),
            axis=1,
        )
        df["Fin real"] = df["fecha_fin_real"].apply(fmt_fecha)

        df = df.rename(
            columns={
                "id_contrato": "ID",
                "paciente": "Paciente",
                "nutricionista": "Nutricionista",
                "programa": "Programa",
                "metodo_pago": "Método",
            }
        )

        st.dataframe(
            df[
                [
                    "ID",
                    "Paciente",
                    "Programa",
                    "Nutricionista",
                    "Estado visual",
                    "Sesiones",
                    "Reprog.",
                    "Precio",
                    "Pagado",
                    "Saldo",
                    "Método",
                    "Inicio",
                    "Fin teórico",
                    "Fin real",
                ]
            ],
            use_container_width=True,
            hide_index=True,
            height=300,
        )


    else:
        st.info("No hay contratos.")





# REPROGRAMACIONES

with tab_reprog:
    section_label("Gestión de reprogramaciones")
    st.markdown("**Regla vigente:** máximo 2 reprogramaciones totales por programa · 1 por mes calendario.")
    st.markdown("---")

    rtab1, rtab2 = st.tabs(["Estado por paciente", "Excepciones y ajustes"])

    with rtab1:
        buscar_r = st.text_input("Buscar paciente por nombre", key="buscar_reprog")

        contratos_reprog = run_query(
            """
            SELECT c.id_contrato,
                   p.nombre || ' ' || p.apellido AS paciente,
                   pr.nombre AS programa,
                   c.reprogramaciones_usadas,
                   COALESCE(c.reprogramaciones_max_override, pr.reprogramaciones_max) AS reprog_max,
                   c.fecha_ultima_reprogramacion,
                   pr.reprogramaciones_max AS reprog_programa
            FROM contratos c
            JOIN pacientes p  ON c.id_paciente = p.id_paciente
            JOIN programas pr ON c.id_programa = pr.id_programa
            WHERE c.estado = 'activo'
            ORDER BY p.apellido
            """
        )

        if buscar_r:
            contratos_reprog = [
                c for c in contratos_reprog
                if buscar_r.lower() in c["paciente"].lower()
            ]

        if not contratos_reprog:
            st.info("No hay contratos activos.")
        else:
            for cr in contratos_reprog:
                hoy_d = date.today()
                ultima = cr["fecha_ultima_reprogramacion"]
                puede_reprogramar = True
                msg_bloqueo = ""

                meses = [
                    "enero", "febrero", "marzo", "abril", "mayo", "junio",
                    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
                ]

                if cr["reprogramaciones_usadas"] >= cr["reprog_max"]:
                    puede_reprogramar = False
                    msg_bloqueo = f"Límite total alcanzado ({cr['reprog_max']} reprogramaciones)."
                elif ultima:
                    ultima_d = ultima if isinstance(ultima, date) else ultima.date()
                    if ultima_d.year == hoy_d.year and ultima_d.month == hoy_d.month:
                        puede_reprogramar = False
                        msg_bloqueo = (
                            f"Ya reprogramó el {ultima_d.strftime('%d/%m/%Y')}. "
                            f"Próxima disponible en {meses[hoy_d.month % 12]}."
                        )

                badge = "🟢" if puede_reprogramar else "🔴"
                usadas = cr["reprogramaciones_usadas"]
                max_r = cr["reprog_max"]

                with st.container(border=True):
                    col1, col2, col3 = st.columns([3, 2, 2])

                    with col1:
                        st.markdown(f"{badge} **{cr['paciente']}**")
                        st.caption(cr["programa"])
                        if not puede_reprogramar:
                            st.caption(f"⚠️ {msg_bloqueo}")

                    with col2:
                        st.markdown(f"Usadas: **{usadas} / {max_r}**")
                        st.caption(f"Última: {fmt_fecha(ultima)}")
                        st.progress(min(usadas / max_r, 1.0) if max_r > 0 else 0)

                    with col3:
                        if puede_reprogramar:
                            sesiones_prog = run_query(
                                """
                                SELECT id_sesion, numero_sesion, fecha_hora_programada
                                FROM sesiones
                                WHERE id_contrato = %s
                                  AND estado = 'programada'
                                ORDER BY numero_sesion
                                """,
                                (cr["id_contrato"],),
                            )

                            if sesiones_prog:
                                opts_s = {
                                    f"Sesión #{s['numero_sesion']} — {str(s['fecha_hora_programada'])[:16]}": s
                                    for s in sesiones_prog
                                }

                                sel_s = st.selectbox("Sesión", list(opts_s.keys()), key=f"rs_{cr['id_contrato']}")
                                nueva_f = st.date_input("Nueva fecha", value=hoy_d, key=f"rf_{cr['id_contrato']}")
                                nueva_h = st.time_input("Nueva hora", key=f"rh_{cr['id_contrato']}")
                                motivo = st.text_input("Motivo", key=f"rm_{cr['id_contrato']}")

                                if st.button("Reprogramar", key=f"btn_r_{cr['id_contrato']}", use_container_width=True):
                                    ses = opts_s[sel_s]
                                    nueva_fh = datetime.datetime.combine(nueva_f, nueva_h)

                                    run_command(
                                        """
                                        UPDATE sesiones
                                        SET fecha_hora_programada = %s,
                                            estado_confirmacion = 'modificada',
                                            contador_reprogramaciones = contador_reprogramaciones + 1,
                                            motivo_reprogramacion = %s,
                                            reprogramada_por = 'admin'
                                        WHERE id_sesion = %s
                                        """,
                                        (nueva_fh, motivo or None, ses["id_sesion"]),
                                    )

                                    run_command(
                                        """
                                        UPDATE contratos
                                        SET reprogramaciones_usadas = reprogramaciones_usadas + 1,
                                            fecha_ultima_reprogramacion = %s
                                        WHERE id_contrato = %s
                                        """,
                                        (hoy_d, cr["id_contrato"]),
                                    )

                                    st.success("Reprogramado.")
                                    st.rerun()
                            else:
                                st.caption("Sin sesiones programadas.")

    with rtab2:
        st.markdown("Ajuste de límites de reprogramación para casos especiales.")
        st.markdown("---")

        contratos_exc = run_query(
            """
            SELECT c.id_contrato,
                   p.nombre || ' ' || p.apellido AS paciente,
                   pr.nombre AS programa,
                   c.reprogramaciones_usadas,
                   pr.reprogramaciones_max AS reprog_programa,
                   c.reprogramaciones_max_override,
                   COALESCE(c.reprogramaciones_max_override, pr.reprogramaciones_max) AS reprog_max,
                   c.fecha_ultima_reprogramacion
            FROM contratos c
            JOIN pacientes p  ON c.id_paciente = p.id_paciente
            JOIN programas pr ON c.id_programa = pr.id_programa
            WHERE c.estado = 'activo'
            ORDER BY p.apellido
            """
        )

        if contratos_exc:
            opts_exc = {f"{c['paciente']} — {c['programa']}": c for c in contratos_exc}
            sel_exc = st.selectbox("Seleccione el contrato", list(opts_exc.keys()), key="sel_exc")
            cr_exc = opts_exc[sel_exc]

            with st.container(border=True):
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown(f"**Paciente:** {cr_exc['paciente']}")
                    st.markdown(f"**Programa:** {cr_exc['programa']}")
                    st.markdown(f"**Límite del programa:** {cr_exc['reprog_programa']}")
                    st.markdown(f"**Override actual:** {cr_exc['reprogramaciones_max_override'] or 'Sin override'}")
                    st.markdown(f"**Usadas:** {cr_exc['reprogramaciones_usadas']}")
                    st.markdown(f"**Última reprogramación:** {fmt_fecha(cr_exc['fecha_ultima_reprogramacion'])}")

                with col2:
                    st.markdown("**Ajustes disponibles:**")

                    nuevo_limite = st.number_input(
                        "Nuevo límite total (0 = usar el del programa)",
                        min_value=0,
                        max_value=20,
                        value=int(cr_exc["reprogramaciones_max_override"] or 0),
                        key="nuevo_limite",
                    )

                    if st.button("Guardar límite", key="btn_limite"):
                        override = nuevo_limite if nuevo_limite > 0 else None
                        run_command(
                            """
                            UPDATE contratos
                            SET reprogramaciones_max_override = %s
                            WHERE id_contrato = %s
                            """,
                            (override, cr_exc["id_contrato"]),
                        )
                        st.success(f"Límite actualizado a {nuevo_limite or 'default del programa'}.")
                        st.rerun()

                    st.markdown("---")
                    st.markdown("**Resetear bloqueo mensual:**")
                    st.caption("Permite reprogramar aunque ya se haya usado una reprogramación este mes.")

                    if st.button("Resetear mes", key="btn_reset_mes", use_container_width=True):
                        run_command(
                            """
                            UPDATE contratos
                            SET fecha_ultima_reprogramacion = NULL
                            WHERE id_contrato = %s
                            """,
                            (cr_exc["id_contrato"],),
                        )
                        st.success("Contador mensual reseteado.")
                        st.rerun()

                    st.markdown("---")
                    st.markdown("**Resetear contador total:**")
                    st.caption("Vuelve a 0 las reprogramaciones usadas.")

                    if st.button("Resetear total", key="btn_reset_total", use_container_width=True):
                        run_command(
                            """
                            UPDATE contratos
                            SET reprogramaciones_usadas = 0
                            WHERE id_contrato = %s
                            """,
                            (cr_exc["id_contrato"],),
                        )
                        st.success("Contador total reseteado a 0.")
                        st.rerun()