from datetime import date, datetime, timedelta

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
page_header("Pagos y Programas")


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


def fmt_money(x):
    return f"S/ {safe_float(x):,.2f}"


def obtener_o_crear_pago(id_contrato, monto_programado):
    pagos = run_query(
        """
        SELECT id_pago
        FROM pagos
        WHERE id_contrato = %s
        ORDER BY numero_cuota
        LIMIT 1
        """,
        (id_contrato,),
    )

    if pagos:
        return pagos[0]["id_pago"]

    run_command(
        """
        INSERT INTO pagos
            (id_contrato, numero_cuota, monto_programado, monto_pagado, fecha_vencimiento, estado)
        VALUES (%s, 1, %s, 0, CURRENT_DATE, 'pendiente')
        """,
        (id_contrato, monto_programado),
    )

    nuevo = run_query(
        """
        SELECT id_pago
        FROM pagos
        WHERE id_contrato = %s
        ORDER BY id_pago DESC
        LIMIT 1
        """,
        (id_contrato,),
    )

    return nuevo[0]["id_pago"]


def registrar_pago(id_contrato, monto, medio_pago, tipo_pago, precio_final):
    id_pago = obtener_o_crear_pago(id_contrato, precio_final)

    run_command(
        """
        INSERT INTO movimientos_pago
            (id_pago, monto, fecha_pago, medio_pago, comprobante,
             tipo_movimiento, confirmado, registrado_por)
        VALUES (%s, %s, CURRENT_DATE, %s, NULL, 'pago', TRUE, %s)
        """,
        (id_pago, monto, medio_pago, registrado_por),
    )

    pagos = run_query(
        """
        SELECT monto_programado, monto_pagado
        FROM pagos
        WHERE id_pago = %s
        """,
        (id_pago,),
    )

    pago = pagos[0]
    nuevo_pagado = safe_float(pago["monto_pagado"]) + safe_float(monto)
    monto_programado = safe_float(pago["monto_programado"])

    if tipo_pago == "pago_total" or nuevo_pagado >= monto_programado:
        estado_pago = "pagado"
    elif nuevo_pagado > 0:
        estado_pago = "parcial"
    else:
        estado_pago = "pendiente"

    run_command(
        """
        UPDATE pagos
        SET monto_pagado = %s,
            estado = %s
        WHERE id_pago = %s
        """,
        (nuevo_pagado, estado_pago, id_pago),
    )

    run_command(
        """
        UPDATE contratos
        SET metodo_pago = %s
        WHERE id_contrato = %s
        """,
        (medio_pago, id_contrato),
    )



def crear_contrato_programa(
    id_paciente,
    id_programa,
    id_nutricionista,
    fecha_inicio,
):
    """
    Crea contrato, sesiones placeholder y una cuota pendiente.
    El pago se registra luego desde la pestaña 'Registrar pago'.
    """
    prog_rows = run_query(
        """
        SELECT *
        FROM programas
        WHERE id_programa = %s
        LIMIT 1
        """,
        (id_programa,),
    )

    if not prog_rows:
        raise Exception("No se encontró el programa seleccionado.")

    prog = prog_rows[0]
    fecha_fin = fecha_inicio + timedelta(days=int(prog["duracion_dias"] or 0))
    precio_final = safe_float(prog["precio_base"])

    run_command(
        """
        INSERT INTO contratos
            (id_paciente, id_programa, id_nutricionista,
             fecha_inicio, fecha_fin, fecha_fin_teorica, fecha_fin_real,
             precio_base_contrato, descuento_contrato, precio_final,
             estado, metodo_pago, reprogramaciones_usadas)
        VALUES (%s, %s, %s, %s, %s, %s, NULL,
                %s, 0, %s, 'pendiente_pago', NULL, 0)
        """,
        (
            id_paciente,
            id_programa,
            id_nutricionista,
            fecha_inicio,
            fecha_fin,
            fecha_fin,
            prog["precio_base"],
            precio_final,
        ),
    )

    contrato_rows = run_query(
        """
        SELECT id_contrato
        FROM contratos
        WHERE id_paciente = %s
        ORDER BY fecha_creacion DESC
        LIMIT 1
        """,
        (id_paciente,),
    )

    if not contrato_rows:
        raise Exception("No se pudo recuperar el contrato creado.")

    id_contrato = contrato_rows[0]["id_contrato"]

    placeholder = datetime(2099, 1, 1, 9, 0)

    for i in range(int(prog["cantidad_sesiones"] or 0)):
        run_command(
            """
            INSERT INTO sesiones
                (id_contrato, id_nutricionista_prog, numero_sesion,
                 fecha_hora_original, fecha_hora_programada,
                 modalidad, estado, estado_confirmacion, contador_reprogramaciones)
            VALUES (%s, %s, %s, %s, %s, %s, 'programada', 'pendiente', 0)
            """,
            (
                id_contrato,
                id_nutricionista,
                i + 1,
                placeholder,
                placeholder,
                prog["modalidad"],
            ),
        )

    run_command(
        """
        INSERT INTO pagos
            (id_contrato, numero_cuota, monto_programado,
             monto_pagado, fecha_vencimiento, estado)
        VALUES (%s, 1, %s, 0, %s, 'pendiente')
        """,
        (id_contrato, precio_final, fecha_inicio),
    )

    return id_contrato


tab0, tab1, tab2 = st.tabs(["Asignar programa", "Registrar pago", "Resumen de pagos"])


with tab0:
    st.subheader("Asignar programa a paciente")
    st.caption(
        "Usa esta sección cuando el paciente ya completó el onboarding. "
        "Aquí se asigna el programa y se generan contrato y sesiones. "
        "El pago se carga luego desde la pestaña Registrar pago."
    )

    pacientes_sin_contrato = run_query(
        """
        SELECT p.id_paciente,
               p.nombre || ' ' || p.apellido AS paciente,
               p.email,
               p.tipo_paciente,
               p.onboarding_paso,
               p.fecha_registro,
               p.dni,
               p.telefono
        FROM pacientes p
        WHERE p.estado IN ('activo', 'pendiente_pago')
          AND COALESCE(p.onboarding_paso, 0) >= 5
          AND p.nombre IS NOT NULL
          AND p.apellido IS NOT NULL
          AND LOWER(TRIM(p.nombre)) <> 'pendiente'
          AND LOWER(TRIM(p.apellido)) <> 'completar'
          AND NOT EXISTS (
              SELECT 1
              FROM contratos c
              WHERE c.id_paciente = p.id_paciente
                AND c.estado IN ('activo', 'pendiente_pago')
          )
        ORDER BY p.fecha_registro DESC, p.apellido, p.nombre
        """
    )

    programas = run_query(
        """
        SELECT *
        FROM programas
        WHERE activo = TRUE
        ORDER BY precio_base, nombre
        """
    )

    nutricionistas = run_query(
        """
        SELECT id_nutricionista,
               nombre || ' ' || apellido AS nombre
        FROM nutricionistas
        WHERE estado = TRUE
        ORDER BY apellido, nombre
        """
    )

    cantidad_pendientes = len(pacientes_sin_contrato or [])

    if cantidad_pendientes > 0:
        st.info(f"Hay {cantidad_pendientes} paciente(s) con onboarding completo pendiente(s) de asignar programa.")

    if not pacientes_sin_contrato:
        st.info("No hay pacientes con onboarding completo pendientes de asignación de programa.")
        st.caption("Si esperabas ver un paciente, revisá que haya completado el formulario de onboarding.")
    elif not programas:
        st.warning("No hay programas activos configurados.")
    elif not nutricionistas:
        st.warning("No hay nutricionistas activas configuradas.")
    else:
        with st.expander("Ver pacientes pendientes de asignar", expanded=True):
            df_pend = pd.DataFrame(pacientes_sin_contrato)
            df_pend["Fecha registro"] = df_pend["fecha_registro"].apply(fmt_fecha)
            df_pend = df_pend.rename(columns={
                "paciente": "Paciente",
                "email": "Email",
                "tipo_paciente": "Tipo",
                "dni": "DNI",
                "telefono": "Teléfono",
            })
            st.dataframe(
                df_pend[["Paciente", "Email", "Tipo", "DNI", "Teléfono", "Fecha registro"]],
                use_container_width=True,
                hide_index=True,
                height=min(300, 70 + 35 * len(df_pend)),
            )

        buscar_activar = st.text_input(
            "Buscar paciente",
            placeholder="Nombre, apellido o email...",
            key="activar_buscar_paciente",
        )

        pacientes_filtrados = pacientes_sin_contrato

        if buscar_activar:
            q = buscar_activar.lower().strip()
            pacientes_filtrados = [
                p for p in pacientes_sin_contrato
                if q in (p.get("paciente") or "").lower()
                or q in (p.get("email") or "").lower()
            ]

        if not pacientes_filtrados:
            st.info("No se encontraron pacientes con onboarding completo para ese criterio.")
        else:
            pac_opts = {
                f"{p['paciente']} · {p.get('email') or 'sin email'} · {p.get('tipo_paciente') or 'persona'}": p
                for p in pacientes_filtrados
            }

            prog_opts = {
                f"{p['nombre']} · {fmt_money(p['precio_base'])} · {p['cantidad_sesiones']} sesiones": p
                for p in programas
            }

            nutri_opts = {
                n["nombre"]: n["id_nutricionista"]
                for n in nutricionistas
            }

            col1, col2 = st.columns(2)

            with col1:
                pac_sel = st.selectbox("Paciente *", list(pac_opts.keys()), key="activar_paciente")
                prog_sel = st.selectbox("Programa *", list(prog_opts.keys()), key="activar_programa")

            with col2:
                nutri_sel = st.selectbox("Nutricionista asignada *", list(nutri_opts.keys()), key="activar_nutri")
                fecha_inicio = st.date_input(
                    "Fecha de inicio *",
                    value=date.today(),
                    format="DD/MM/YYYY",
                    key="activar_fecha_inicio",
                )

            paciente = pac_opts[pac_sel]
            programa = prog_opts[prog_sel]

            st.markdown("---")

            with st.container(border=True):
                st.markdown("### Resumen de asignación")
                c1, c2, c3 = st.columns(3)

                with c1:
                    st.markdown("**Paciente**")
                    st.write(paciente["paciente"])
                    st.caption(paciente.get("email") or "sin email")

                with c2:
                    st.markdown("**Programa**")
                    st.write(programa["nombre"])
                    st.caption(f"{programa['cantidad_sesiones']} sesiones · {programa['modalidad']}")

                with c3:
                    st.markdown("**Nutricionista**")
                    st.write(nutri_sel)
                    st.caption(f"Inicio: {fmt_fecha(fecha_inicio)}")

                st.markdown("---")
                st.markdown(f"**Precio base del programa:** {fmt_money(programa['precio_base'])}")
                st.caption("El monto abonado y el método de pago se cargan en la pestaña Registrar pago.")

            if st.button(
                "Asignar programa",
                type="primary",
                use_container_width=True,
                key="activar_confirmar",
            ):
                try:
                    id_contrato = crear_contrato_programa(
                        id_paciente=paciente["id_paciente"],
                        id_programa=programa["id_programa"],
                        id_nutricionista=nutri_opts[nutri_sel],
                        fecha_inicio=fecha_inicio,
                    )

                    st.success(
                        f"Programa asignado correctamente. Contrato #{id_contrato} creado "
                        ""
                    )
                    st.rerun()

                except Exception as e:
                    st.error(f"Error al asignar programa: {e}")


with tab1:
    st.subheader("Registrar pago de paciente")
    st.caption("Si el paciente aparece como 'sin programa asignado', primero debe pasar por la pestaña Asignar programa.")

    pacientes = run_query(
        """
        SELECT DISTINCT
               p.id_paciente,
               p.nombre || ' ' || p.apellido AS paciente,
               p.email,
               CASE
                   WHEN EXISTS (
                       SELECT 1
                       FROM contratos c
                       WHERE c.id_paciente = p.id_paciente
                         AND c.estado IN ('activo', 'pendiente_pago')
                   )
                   THEN TRUE ELSE FALSE
               END AS tiene_contrato
        FROM pacientes p
        WHERE p.estado IN ('activo', 'pendiente_pago')
          AND COALESCE(p.onboarding_paso, 0) >= 5
          AND p.nombre IS NOT NULL
          AND p.apellido IS NOT NULL
          AND LOWER(TRIM(p.nombre)) <> 'pendiente'
          AND LOWER(TRIM(p.apellido)) <> 'completar'
        ORDER BY paciente
        """
    )

    buscar = st.text_input(
        "Buscar paciente",
        placeholder="Escriba las primeras letras del nombre...",
        key="buscar_paciente_pago",
    )

    pacientes_filtrados = pacientes

    if buscar:
        q = buscar.lower().strip()
        pacientes_filtrados = [
            p for p in pacientes
            if q in (p.get("paciente") or "").lower()
            or q in (p.get("email") or "").lower()
        ]

    if not pacientes_filtrados:
        st.info("No se encontraron pacientes.")
    else:
        opciones_pac = {
            f"{p['paciente']} · {p.get('email') or 'sin email'}" + ("" if p.get("tiene_contrato") else " · sin programa asignado"): p
            for p in pacientes_filtrados
        }

        paciente_sel = st.selectbox(
            "Coincidencias",
            list(opciones_pac.keys()),
            key="pago_paciente_sel",
        )

        paciente = opciones_pac[paciente_sel]

        if not paciente.get("tiene_contrato"):
            st.warning(
                "Este paciente ya completó el onboarding, pero todavía no tiene programa asignado. "
                "Primero asignale un programa desde la pestaña 'Asignar programa'."
            )
            st.stop()

        contratos = run_query(
            """
            SELECT c.id_contrato,
                   c.estado AS estado_contrato,
                   c.precio_final,
                   c.metodo_pago,
                   pr.nombre AS programa
            FROM contratos c
            JOIN programas pr ON c.id_programa = pr.id_programa
            WHERE c.id_paciente = %s
            ORDER BY c.fecha_inicio DESC
            """,
            (paciente["id_paciente"],),
        )

        if not contratos:
            st.info("Este paciente no tiene programas/contratos cargados.")
        else:
            opciones_contrato = {
                f"{c['programa']} · {c['estado_contrato']} · {fmt_money(c['precio_final'])}": c
                for c in contratos
            }

            contrato_sel = st.selectbox(
                "Programa comprado",
                list(opciones_contrato.keys()),
                key="pago_contrato_sel",
            )

            contrato = opciones_contrato[contrato_sel]

            st.markdown("---")

            col1, col2, col3 = st.columns(3)

            with col1:
                precio_pagado = st.number_input(
                    "Monto abonado (S/)",
                    min_value=0.0,
                    value=float(safe_float(contrato["precio_final"])),
                    step=10.0,
                    key="pago_monto_manual",
                )

            with col2:
                tipo_pago = st.selectbox(
                    "Tipo de pago",
                    ["pago_total", "pago_parcial"],
                    format_func=lambda x: {
                        "pago_total": "Pago total",
                        "pago_parcial": "Pago parcial",
                    }[x],
                    key="pago_tipo_manual",
                )

            with col3:
                medios = ["transferencia", "yape", "plin", "efectivo", "tarjeta", "web"]
                medio_actual = contrato.get("metodo_pago")
                medio_index = medios.index(medio_actual) if medio_actual in medios else 0

                medio_pago = st.selectbox(
                    "Medio de pago",
                    medios,
                    index=medio_index,
                    key="pago_medio_manual",
                )

            observacion = st.text_area(
                "Observaciones",
                placeholder="Opcional. Ej: pago parcial, comprobante enviado, operación bancaria, etc.",
                key="pago_observacion_manual",
            )

            if st.button("Registrar pago", type="primary", use_container_width=True):
                if precio_pagado <= 0:
                    st.error("El monto abonado debe ser mayor a 0.")
                else:
                    try:
                        registrar_pago(
                            id_contrato=contrato["id_contrato"],
                            monto=precio_pagado,
                            medio_pago=medio_pago,
                            tipo_pago=tipo_pago,
                            precio_final=safe_float(contrato["precio_final"]),
                        )
                        st.success("Pago registrado correctamente.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al registrar pago: {e}")

            st.markdown("---")
            st.subheader("Historial de pagos del paciente")

            historial = run_query(
                """
                SELECT mp.fecha_pago,
                       pr.nombre AS programa,
                       mp.monto,
                       mp.medio_pago,
                       mp.tipo_movimiento,
                       mp.confirmado,
                       mp.registrado_por
                FROM movimientos_pago mp
                JOIN pagos pg ON mp.id_pago = pg.id_pago
                JOIN contratos c ON pg.id_contrato = c.id_contrato
                JOIN programas pr ON c.id_programa = pr.id_programa
                WHERE c.id_paciente = %s
                ORDER BY mp.fecha_pago DESC, mp.id_movimiento DESC
                """,
                (paciente["id_paciente"],),
            )

            if not historial:
                st.info("Este paciente todavía no tiene pagos registrados.")
            else:
                df_h = pd.DataFrame(historial)
                df_h["Fecha"] = df_h["fecha_pago"].apply(fmt_fecha)
                df_h["Monto"] = df_h["monto"].apply(fmt_money)
                df_h["Confirmado"] = df_h["confirmado"].map({True: "Sí", False: "No"})

                df_h = df_h.rename(
                    columns={
                        "programa": "Programa",
                        "medio_pago": "Medio utilizado",
                        "tipo_movimiento": "Tipo",
                        "registrado_por": "Registrado por",
                    }
                )

                st.dataframe(
                    df_h[
                        [
                            "Fecha",
                            "Programa",
                            "Monto",
                            "Medio utilizado",
                            "Tipo",
                            "Confirmado",
                            "Registrado por",
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True,
                    height=350,
                )


with tab2:
    st.subheader("Resumen de pagos")

    resumen = run_query(
        """
        SELECT p.nombre || ' ' || p.apellido AS paciente,
               pr.nombre AS programa,
               c.estado AS estado_contrato,
               c.precio_final,
               c.metodo_pago,
               COALESCE(SUM(pg.monto_pagado), 0) AS total_pagado
        FROM contratos c
        JOIN pacientes p ON c.id_paciente = p.id_paciente
        JOIN programas pr ON c.id_programa = pr.id_programa
        LEFT JOIN pagos pg ON c.id_contrato = pg.id_contrato
        GROUP BY c.id_contrato, p.nombre, p.apellido, pr.nombre
        ORDER BY paciente, programa
        """
    )

    if not resumen:
        st.info("No hay pagos para mostrar.")
    else:
        df = pd.DataFrame(resumen)

        df["Precio final"] = df["precio_final"].apply(fmt_money)
        df["Medio utilizado"] = df["metodo_pago"].fillna("—")
        df["Estado contrato"] = (
            df["estado_contrato"]
            .fillna("—")
            .str.replace("_", " ")
            .str.capitalize()
        )

        df = df.rename(
            columns={
                "paciente": "Paciente",
                "programa": "Programa",
            }
        )

        st.dataframe(
            df[
                [
                    "Paciente",
                    "Programa",
                    "Estado contrato",
                    "Precio final",
                    "Medio utilizado",
                ]
            ],
            use_container_width=True,
            hide_index=True,
            height=430,
        )