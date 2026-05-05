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
page_header("Contratos")


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


def aplicar_pago(id_pago, monto, medio_pago, tipo_movimiento, confirmado=True):
    pago = run_query(
        """
        SELECT id_pago, monto_programado, monto_pagado
        FROM pagos
        WHERE id_pago = %s
        LIMIT 1
        """,
        (id_pago,),
    )

    if not pago:
        raise Exception("No se encontró la cuota seleccionada.")

    p = pago[0]
    monto_actual = safe_float(p["monto_pagado"])
    monto_programado = safe_float(p["monto_programado"])

    if tipo_movimiento == "anulacion":
        monto_movimiento = -abs(float(monto))
    else:
        monto_movimiento = abs(float(monto))

    nuevo_pagado = max(monto_actual + monto_movimiento, 0)

    if nuevo_pagado >= monto_programado:
        nuevo_estado = "pagado"
    elif nuevo_pagado > 0:
        nuevo_estado = "parcial"
    else:
        nuevo_estado = "pendiente"

    run_command(
        """
        INSERT INTO movimientos_pago
            (id_pago, monto, fecha_pago, medio_pago, comprobante,
             tipo_movimiento, confirmado, registrado_por)
        VALUES (%s, %s, CURRENT_DATE, %s, NULL, %s, %s, %s)
        """,
        (
            id_pago,
            monto_movimiento,
            medio_pago,
            tipo_movimiento,
            confirmado,
            registrado_por,
        ),
    )

    run_command(
        """
        UPDATE pagos
        SET monto_pagado = %s,
            estado = %s
        WHERE id_pago = %s
        """,
        (nuevo_pagado, nuevo_estado, id_pago),
    )


tab1, tab2, tab3 = st.tabs(["Ver contratos", "Nuevo contrato", "Reprogramaciones"])



# VER CONTRATOS

with tab1:
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

        st.markdown("---")
        section_label("Registrar pago")

        contratos_opts = {
            f"#{c['id_contrato']} — {c['paciente']} ({c['programa']})": c
            for c in contratos
        }

        contrato_pago_sel = st.selectbox(
            "Contrato",
            list(contratos_opts.keys()),
            key="contrato_pago_sel",
        )

        contrato_pago = contratos_opts[contrato_pago_sel]

        cuotas = run_query(
            """
            SELECT id_pago,
                   numero_cuota,
                   monto_programado,
                   monto_pagado,
                   fecha_vencimiento,
                   estado
            FROM pagos
            WHERE id_contrato = %s
            ORDER BY numero_cuota
            """,
            (contrato_pago["id_contrato"],),
        )

        if not cuotas:
            st.info("Este contrato no tiene cuotas programadas.")
        else:
            cuotas_opts = {
                (
                    f"Cuota {c['numero_cuota']} · "
                    f"{c['estado']} · "
                    f"S/ {safe_float(c['monto_pagado']):,.2f} / "
                    f"S/ {safe_float(c['monto_programado']):,.2f} · "
                    f"vence {fmt_fecha(c['fecha_vencimiento'])}"
                ): c
                for c in cuotas
            }

            cuota_sel = st.selectbox("Cuota", list(cuotas_opts.keys()), key="cuota_pago_sel")
            cuota = cuotas_opts[cuota_sel]

            col1, col2, col3 = st.columns(3)

            saldo_cuota = max(
                safe_float(cuota["monto_programado"]) - safe_float(cuota["monto_pagado"]),
                0,
            )

            with col1:
                monto = st.number_input(
                    "Monto pagado (S/)",
                    min_value=0.0,
                    value=float(saldo_cuota),
                    step=10.0,
                    key="monto_pago",
                )

            with col2:
                medio = st.selectbox(
                    "Método de pago",
                    ["transferencia", "yape", "plin", "efectivo", "tarjeta", "web"],
                    key="medio_pago",
                )

            with col3:
                tipo_mov = st.selectbox(
                    "Tipo de movimiento",
                    ["pago", "ajuste", "anulacion"],
                    key="tipo_mov_pago",
                )

            confirmado = st.checkbox("Pago confirmado", value=True, key="pago_confirmado")

            if st.button("Registrar pago", type="primary", use_container_width=True):
                if monto <= 0:
                    st.error("El monto debe ser mayor a 0.")
                else:
                    try:
                        aplicar_pago(
                            id_pago=cuota["id_pago"],
                            monto=monto,
                            medio_pago=medio,
                            tipo_movimiento=tipo_mov,
                            confirmado=confirmado,
                        )
                        st.success("Pago registrado correctamente.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al registrar pago: {e}")

            if cuotas:
                st.markdown("**Cuotas del contrato**")
                df_cuotas = pd.DataFrame(cuotas)
                df_cuotas["Vencimiento"] = df_cuotas["fecha_vencimiento"].apply(fmt_fecha)
                df_cuotas["Monto programado"] = df_cuotas["monto_programado"].apply(
                    lambda x: f"S/ {safe_float(x):,.2f}"
                )
                df_cuotas["Monto pagado"] = df_cuotas["monto_pagado"].apply(
                    lambda x: f"S/ {safe_float(x):,.2f}"
                )
                df_cuotas = df_cuotas.rename(
                    columns={
                        "numero_cuota": "Cuota",
                        "estado": "Estado",
                    }
                )
                st.dataframe(
                    df_cuotas[
                        [
                            "Cuota",
                            "Monto programado",
                            "Monto pagado",
                            "Vencimiento",
                            "Estado",
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )

    else:
        st.info("No hay contratos.")



# NUEVO CONTRATO

with tab2:
    section_label("Crear nuevo contrato")


    pacientes_list = run_query(
        """
        SELECT id_paciente, nombre || ' ' || apellido AS nombre
        FROM pacientes
        WHERE estado IN ('activo', 'pendiente_pago')
        ORDER BY apellido, nombre
        """
    )

    programas_list = run_query(
        """
        SELECT *
        FROM programas
        WHERE activo = TRUE
        ORDER BY precio_base
        """
    )

    nutris_list = run_query(
        """
        SELECT id_nutricionista, nombre || ' ' || apellido AS nombre
        FROM nutricionistas
        WHERE estado = TRUE
        ORDER BY apellido, nombre
        """
    )

    if not pacientes_list or not programas_list or not nutris_list:
        st.warning("Se requiere al menos un paciente, un programa y una nutricionista activos.")
    else:
        col1, col2 = st.columns(2)

        with col1:
            pac_opts = {p["nombre"]: p["id_paciente"] for p in pacientes_list}
            pac_sel = st.selectbox("Paciente *", list(pac_opts.keys()), key="nc_pac")

            prog_opts = {p["nombre"]: p for p in programas_list}
            prog_sel = st.selectbox("Programa *", list(prog_opts.keys()), key="nc_prog")

        with col2:
            nutr_opts = {n["nombre"]: n["id_nutricionista"] for n in nutris_list}
            nutr_sel = st.selectbox("Nutricionista *", list(nutr_opts.keys()), key="nc_nutr")

            f_inicio = st.date_input("Fecha de inicio *", value=date.today(), key="nc_inicio")

        prog = prog_opts[prog_sel]
        f_fin_teorica = f_inicio + datetime.timedelta(days=int(prog["duracion_dias"]))

        st.markdown("---")
        st.markdown("### Datos del contrato")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown(f"**Sesiones:** {prog['cantidad_sesiones']}")
            st.markdown(f"**Duración:** {prog['duracion_dias']} días")

        with col2:
            st.markdown(f"**Fecha inicio:** {fmt_fecha(f_inicio)}")
            st.markdown(f"**Fecha fin teórica:** {fmt_fecha(f_fin_teorica)}")

        with col3:
            st.markdown(f"**Precio base:** S/ {safe_float(prog['precio_base']):,.2f}")
            st.markdown(f"**Modalidad:** {prog['modalidad']}")

        st.markdown("---")
        st.markdown("### Pago inicial")

        col1, col2, col3 = st.columns(3)

        with col1:
            descuento = float(
                st.number_input(
                    "Descuento (S/)",
                    min_value=0.0,
                    step=10.0,
                    key="nc_desc",
                )
            )

        precio_sugerido = max(float(prog["precio_base"]) - float(descuento), 0)

        with col2:
            precio_fin = float(
                st.number_input(
                    "Precio final (S/)",
                    min_value=0.0,
                    value=float(precio_sugerido),
                    step=10.0,
                    key="nc_precio_final_editable",
                )
            )

        with col3:
            metodo = st.selectbox(
                "Método de pago",
                ["transferencia", "yape", "plin", "efectivo", "tarjeta", "web"],
                key="nc_metodo",
            )

        col4, col5, col6 = st.columns(3)

        with col4:
            tipo_pago = st.selectbox(
                "Tipo de pago",
                ["pago_total", "pago_parcial", "sin_pago_inicial"],
                format_func=lambda x: {
                    "pago_total": "Pago total",
                    "pago_parcial": "Pago parcial",
                    "sin_pago_inicial": "Sin pago inicial",
                }[x],
                key="nc_tipo_pago",
            )

        with col5:
            if tipo_pago == "pago_total":
                monto_inicial = precio_fin
                st.number_input(
                    "Monto inicial (S/)",
                    min_value=0.0,
                    value=float(monto_inicial),
                    disabled=True,
                    key="nc_monto_inicial_total",
                )
            elif tipo_pago == "pago_parcial":
                monto_inicial = float(
                    st.number_input(
                        "Monto inicial (S/)",
                        min_value=0.0,
                        max_value=float(precio_fin),
                        step=10.0,
                        key="nc_monto_inicial_parcial",
                    )
                )
            else:
                monto_inicial = 0.0
                st.number_input(
                    "Monto inicial (S/)",
                    min_value=0.0,
                    value=0.0,
                    disabled=True,
                    key="nc_monto_inicial_cero",
                )

        with col6:
            num_cuotas = st.number_input(
                "Número de cuotas",
                min_value=1,
                max_value=12,
                value=1,
                step=1,
                key="nc_cuotas",
            )

        observaciones_pago = st.text_area(
            "Observaciones de pago",
            placeholder="Ej: pago parcial por Yape, queda saldo pendiente, comprobante enviado por WhatsApp...",
            key="nc_obs_pago",
        )

        if st.button("Crear contrato", use_container_width=True, type="primary", key="btn_crear_ct"):
            try:
                id_pac = pac_opts[pac_sel]
                id_prog = prog["id_programa"]
                id_nutr = nutr_opts[nutr_sel]

                estado_contrato = "activo" if monto_inicial > 0 or tipo_pago == "pago_total" else "pendiente_pago"

                run_command(
                    """
                    INSERT INTO contratos
                        (id_paciente, id_programa, id_nutricionista,
                         fecha_inicio, fecha_fin, fecha_fin_teorica, fecha_fin_real,
                         precio_base_contrato, descuento_contrato, precio_final,
                         estado, metodo_pago, reprogramaciones_usadas)
                    VALUES (%s, %s, %s, %s, %s, %s, NULL,
                            %s, %s, %s, %s, %s, 0)
                    """,
                    (
                        id_pac,
                        id_prog,
                        id_nutr,
                        f_inicio,
                        f_fin_teorica,
                        f_fin_teorica,
                        prog["precio_base"],
                        descuento,
                        precio_fin,
                        estado_contrato,
                        metodo,
                    ),
                )

                id_contrato = run_query(
                    """
                    SELECT id_contrato
                    FROM contratos
                    WHERE id_paciente = %s
                    ORDER BY fecha_creacion DESC
                    LIMIT 1
                    """,
                    (id_pac,),
                )[0]["id_contrato"]

                frec_map = {"semanal": 7, "quincenal": 14, "mensual": 30}
                dias_frec = frec_map.get(prog["frecuencia"], 14)

                for i in range(int(prog["cantidad_sesiones"])):
                    fecha_s = f_inicio + datetime.timedelta(days=i * dias_frec)
                    fecha_hora_s = datetime.datetime.combine(fecha_s, datetime.time(9, 0))

                    run_command(
                        """
                        INSERT INTO sesiones
                            (id_contrato, id_nutricionista_prog, numero_sesion,
                             fecha_hora_original, fecha_hora_programada,
                             modalidad, estado, contador_reprogramaciones)
                        VALUES (%s, %s, %s, %s, %s, %s, 'programada', 0)
                        """,
                        (
                            id_contrato,
                            id_nutr,
                            i + 1,
                            fecha_hora_s,
                            fecha_hora_s,
                            prog["modalidad"],
                        ),
                    )

                monto_cuota = round(float(precio_fin) / int(num_cuotas), 2)
                ids_pagos = []

                for i in range(int(num_cuotas)):
                    vence = f_inicio + datetime.timedelta(days=30 * i)
                    run_command(
                        """
                        INSERT INTO pagos
                            (id_contrato, numero_cuota, monto_programado,
                             monto_pagado, fecha_vencimiento, estado)
                        VALUES (%s, %s, %s, 0, %s, 'pendiente')
                        """,
                        (id_contrato, i + 1, monto_cuota, vence),
                    )

                    id_pago = run_query(
                        """
                        SELECT id_pago
                        FROM pagos
                        WHERE id_contrato = %s
                          AND numero_cuota = %s
                        LIMIT 1
                        """,
                        (id_contrato, i + 1),
                    )[0]["id_pago"]

                    ids_pagos.append(id_pago)

                monto_restante_a_aplicar = float(monto_inicial)

                for id_pago in ids_pagos:
                    if monto_restante_a_aplicar <= 0:
                        break

                    pago_actual = run_query(
                        """
                        SELECT id_pago, monto_programado, monto_pagado
                        FROM pagos
                        WHERE id_pago = %s
                        """,
                        (id_pago,),
                    )[0]

                    saldo_cuota = safe_float(pago_actual["monto_programado"]) - safe_float(pago_actual["monto_pagado"])
                    monto_a_aplicar = min(monto_restante_a_aplicar, saldo_cuota)

                    if monto_a_aplicar > 0:
                        aplicar_pago(
                            id_pago=id_pago,
                            monto=monto_a_aplicar,
                            medio_pago=metodo,
                            tipo_movimiento="pago",
                            confirmado=True,
                        )

                    monto_restante_a_aplicar -= monto_a_aplicar

                st.success(
                    f"Contrato #{id_contrato} creado con {prog['cantidad_sesiones']} sesiones "
                    f"y {num_cuotas} cuota(s)."
                )
                st.rerun()

            except Exception as e:
                st.error(f"Error: {e}")



# REPROGRAMACIONES

with tab3:
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