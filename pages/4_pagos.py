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
page_header("Pagos")


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


tab1, tab2 = st.tabs(["Registrar pago", "Resumen de pagos"])


with tab1:
    st.subheader("Registrar pago de paciente")

    pacientes = run_query(
        """
        SELECT DISTINCT
               p.id_paciente,
               p.nombre || ' ' || p.apellido AS paciente
        FROM pacientes p
        JOIN contratos c ON p.id_paciente = c.id_paciente
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
        pacientes_filtrados = [
            p for p in pacientes
            if buscar.lower() in p["paciente"].lower()
        ]

    if not pacientes_filtrados:
        st.info("No se encontraron pacientes.")
    else:
        opciones_pac = {p["paciente"]: p for p in pacientes_filtrados}

        paciente_sel = st.selectbox(
            "Coincidencias",
            list(opciones_pac.keys()),
            key="pago_paciente_sel",
        )

        paciente = opciones_pac[paciente_sel]

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