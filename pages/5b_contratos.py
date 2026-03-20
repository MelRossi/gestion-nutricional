import streamlit as st
import pandas as pd
from database import run_query, run_command
from datetime import date
from utils import mostrar_sidebar

if "usuario" not in st.session_state:
    st.warning("Debés iniciar sesión.")
    st.stop()

if st.session_state["usuario"]["rol"] != "administrador":
    st.error("Solo administradores.")
    st.stop()

mostrar_sidebar()
st.title("Contratos")
st.markdown("---")

tab1, tab2, tab3 = st.tabs(["Ver contratos", "Nuevo contrato", "Reprogramaciones"])

# ═══════════════════════════════
# TAB 1 — VER CONTRATOS
# ═══════════════════════════════
with tab1:
    filtro_estado = st.selectbox("Estado", ["todos","activo","pendiente_pago","finalizado","cancelado"], key="ct_est")

    q = """
        SELECT c.id_contrato, c.fecha_inicio, c.fecha_fin, c.estado,
               c.precio_final, c.metodo_pago,
               c.reprogramaciones_usadas,
               COALESCE(c.reprogramaciones_max_override, pr.reprogramaciones_max) AS reprog_max,
               c.fecha_ultima_reprogramacion,
               p.nombre||' '||p.apellido AS paciente,
               n.nombre||' '||n.apellido AS nutricionista,
               pr.nombre AS programa,
               pr.cantidad_sesiones,
               (SELECT COUNT(*) FROM sesiones s WHERE s.id_contrato=c.id_contrato AND s.estado='atendida') AS sesiones_realizadas
        FROM contratos c
        JOIN pacientes p      ON c.id_paciente=p.id_paciente
        JOIN nutricionistas n ON c.id_nutricionista=n.id_nutricionista
        JOIN programas pr     ON c.id_programa=pr.id_programa
    """
    params = []
    if filtro_estado != "todos":
        q += " WHERE c.estado=%s"; params.append(filtro_estado)
    q += " ORDER BY c.fecha_inicio DESC"

    contratos = run_query(q, params or None)

    if contratos:
        df = pd.DataFrame(contratos)
        df["Sesiones"] = df.apply(lambda r: f"{int(r['sesiones_realizadas'])}/{int(r['cantidad_sesiones'])}", axis=1)
        df["Reprog."]  = df.apply(lambda r: f"{int(r['reprogramaciones_usadas'])}/{int(r['reprog_max'])}", axis=1)
        df = df.rename(columns={
            "id_contrato":"ID","paciente":"Paciente","nutricionista":"Nutricionista",
            "programa":"Programa","estado":"Estado","precio_final":"Precio",
            "fecha_inicio":"Inicio","fecha_fin":"Fin","metodo_pago":"Pago"
        })
        st.dataframe(df[["ID","Paciente","Programa","Nutricionista","Estado",
                          "Sesiones","Reprog.","Precio","Pago","Inicio","Fin"]],
                     use_container_width=True)

        # Confirmar pago pendiente
        pend = [c for c in contratos if c["estado"] == "pendiente_pago"]
        if pend:
            st.markdown("---")
            with st.expander(f"Confirmar pagos pendientes ({len(pend)})"):
                opts_p = {f"#{c['id_contrato']} — {c['paciente']} ({c['programa']})": c["id_contrato"] for c in pend}
                sel_p  = st.selectbox("Contrato", list(opts_p.keys()), key="pago_sel")
                if st.button("Confirmar pago y activar contrato", key="btn_confirmar_pago"):
                    run_command("UPDATE contratos SET estado='activo' WHERE id_contrato=%s", (opts_p[sel_p],))
                    run_command("UPDATE pacientes SET estado='activo' WHERE id_paciente=(SELECT id_paciente FROM contratos WHERE id_contrato=%s)", (opts_p[sel_p],))
                    st.success("Contrato activado.")
                    st.rerun()
    else:
        st.info("No hay contratos.")

# ═══════════════════════════════
# TAB 2 — NUEVO CONTRATO
# ═══════════════════════════════
with tab2:
    st.subheader("Crear nuevo contrato")
    st.caption("Se generarán automáticamente las sesiones y cuotas de pago.")

    pacientes_list = run_query("SELECT id_paciente, nombre||' '||apellido AS nombre FROM pacientes WHERE estado IN ('activo','pendiente_pago') ORDER BY apellido")
    programas_list = run_query("SELECT * FROM programas WHERE activo=TRUE ORDER BY precio_base")
    nutris_list    = run_query("SELECT id_nutricionista, nombre||' '||apellido AS nombre FROM nutricionistas WHERE estado=TRUE ORDER BY apellido")

    if not pacientes_list or not programas_list or not nutris_list:
        st.warning("Necesitás al menos un paciente, programa y nutricionista activos.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            pac_opts  = {p["nombre"]: p["id_paciente"] for p in pacientes_list}
            pac_sel   = st.selectbox("Paciente *", list(pac_opts.keys()), key="nc_pac")
            prog_opts = {p["nombre"]: p for p in programas_list}
            prog_sel  = st.selectbox("Programa *", list(prog_opts.keys()), key="nc_prog")
        with col2:
            nutr_opts = {n["nombre"]: n["id_nutricionista"] for n in nutris_list}
            nutr_sel  = st.selectbox("Nutricionista *", list(nutr_opts.keys()), key="nc_nutr")
            f_inicio  = st.date_input("Fecha de inicio *", value=date.today(), key="nc_inicio")

        prog = prog_opts[prog_sel]
        f_fin = f_inicio + __import__('datetime').timedelta(days=prog["duracion_dias"])

        st.markdown("---")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Sesiones",    prog["cantidad_sesiones"])
        col2.metric("Duración",    f"{prog['duracion_dias']} días")
        col3.metric("Precio base", f"S/ {prog['precio_base']:,.2f}")
        col4.metric("Fecha fin",   str(f_fin))

        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        with col1:
            descuento  = float(st.number_input("Descuento (S/)", min_value=0.0, step=10.0, key="nc_desc"))
        with col2:
            precio_fin = float(prog["precio_base"]) - float(descuento)
            st.metric("Precio final", f"S/ {precio_fin:,.2f}")
        with col3:
            metodo    = st.selectbox("Método de pago", ["yape","plin","transferencia","tarjeta","efectivo"], key="nc_metodo")

        num_cuotas = st.number_input("Número de cuotas", min_value=1, max_value=12, value=1, step=1, key="nc_cuotas")

        if st.button("Crear contrato", use_container_width=True, type="primary", key="btn_crear_ct"):
            try:
                import datetime
                id_pac   = pac_opts[pac_sel]
                id_prog  = prog["id_programa"]
                id_nutr  = nutr_opts[nutr_sel]

                run_command("""
                    INSERT INTO contratos
                        (id_paciente,id_programa,id_nutricionista,fecha_inicio,fecha_fin,
                         precio_base_contrato,descuento_contrato,precio_final,
                         estado,metodo_pago,reprogramaciones_usadas)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'activo',%s,0)
                """, (id_pac, id_prog, id_nutr, f_inicio, f_fin,
                      prog["precio_base"], descuento, precio_fin, metodo))

                id_contrato = run_query("SELECT id_contrato FROM contratos WHERE id_paciente=%s ORDER BY fecha_creacion DESC LIMIT 1", (id_pac,))[0]["id_contrato"]

                # Generar sesiones
                frec_map = {"semanal":7,"quincenal":14,"mensual":30}
                dias_frec = frec_map.get(prog["frecuencia"], 14)
                for i in range(prog["cantidad_sesiones"]):
                    fecha_s = f_inicio + datetime.timedelta(days=i * dias_frec)
                    run_command("""
                        INSERT INTO sesiones
                            (id_contrato,id_nutricionista_prog,numero_sesion,
                             fecha_hora_original,fecha_hora_programada,
                             modalidad,estado,contador_reprogramaciones)
                        VALUES (%s,%s,%s,%s,%s,%s,'programada',0)
                    """, (id_contrato, id_nutr, i+1,
                          datetime.datetime.combine(fecha_s, datetime.time(9,0)),
                          datetime.datetime.combine(fecha_s, datetime.time(9,0)),
                          prog["modalidad"]))

                # Generar cuotas
                monto_cuota = round(float(precio_fin) / int(num_cuotas), 2)
                for i in range(num_cuotas):
                    vence = f_inicio + datetime.timedelta(days=30*i)
                    run_command("""
                        INSERT INTO pagos (id_contrato,numero_cuota,monto_programado,fecha_vencimiento,estado)
                        VALUES (%s,%s,%s,%s,'pendiente')
                    """, (id_contrato, i+1, monto_cuota, vence))

                st.success(f"Contrato #{id_contrato} creado con {prog['cantidad_sesiones']} sesiones y {num_cuotas} cuota(s).")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

# ═══════════════════════════════
# TAB 3 — REPROGRAMACIONES
# ═══════════════════════════════
with tab3:
    st.subheader("Gestión de reprogramaciones")
    st.markdown("**Regla vigente:** máximo 2 reprogramaciones totales por programa · 1 por mes calendario.")
    st.markdown("---")

    rtab1, rtab2 = st.tabs(["Estado por paciente", "Excepciones y ajustes"])

    # ── SUB-TAB 1: ESTADO POR PACIENTE ──
    with rtab1:
        buscar_r = st.text_input("Buscar paciente por nombre", key="buscar_reprog")

        contratos_reprog = run_query("""
            SELECT c.id_contrato, p.nombre||' '||p.apellido AS paciente,
                   pr.nombre AS programa,
                   c.reprogramaciones_usadas,
                   COALESCE(c.reprogramaciones_max_override, pr.reprogramaciones_max) AS reprog_max,
                   c.fecha_ultima_reprogramacion,
                   pr.reprogramaciones_max AS reprog_programa
            FROM contratos c
            JOIN pacientes p  ON c.id_paciente=p.id_paciente
            JOIN programas pr ON c.id_programa=pr.id_programa
            WHERE c.estado='activo'
            ORDER BY p.apellido
        """)

        if buscar_r:
            contratos_reprog = [c for c in contratos_reprog
                                if buscar_r.lower() in c["paciente"].lower()]

        if not contratos_reprog:
            st.info("No hay contratos activos.")
        else:
            for cr in contratos_reprog:
                hoy_d = date.today()
                ultima = cr["fecha_ultima_reprogramacion"]
                puede_reprogramar = True
                msg_bloqueo = ""
                meses = ['enero','febrero','marzo','abril','mayo','junio',
                         'julio','agosto','septiembre','octubre','noviembre','diciembre']

                if cr["reprogramaciones_usadas"] >= cr["reprog_max"]:
                    puede_reprogramar = False
                    msg_bloqueo = f"Límite total alcanzado ({cr['reprog_max']} reprogramaciones)."
                elif ultima:
                    ultima_d = ultima if isinstance(ultima, date) else ultima.date()
                    if ultima_d.year == hoy_d.year and ultima_d.month == hoy_d.month:
                        puede_reprogramar = False
                        msg_bloqueo = f"Ya reprogramó el {ultima_d.strftime('%d/%m/%Y')}. Próxima disponible en {meses[hoy_d.month % 12]}."

                badge = "🟢" if puede_reprogramar else "🔴"
                usadas = cr["reprogramaciones_usadas"]
                max_r  = cr["reprog_max"]

                with st.container(border=True):
                    col1, col2, col3 = st.columns([3, 2, 2])
                    with col1:
                        st.markdown(f"{badge} **{cr['paciente']}**")
                        st.caption(cr["programa"])
                        if not puede_reprogramar:
                            st.caption(f"⚠️ {msg_bloqueo}")
                    with col2:
                        st.markdown(f"Usadas: **{usadas} / {max_r}**")
                        st.caption(f"Última: {str(ultima)[:10] if ultima else 'Nunca'}")
                        # Barra de progreso
                        st.progress(min(usadas / max_r, 1.0) if max_r > 0 else 0)
                    with col3:
                        if puede_reprogramar:
                            sesiones_prog = run_query("""
                                SELECT id_sesion, numero_sesion, fecha_hora_programada
                                FROM sesiones WHERE id_contrato=%s AND estado='programada'
                                ORDER BY numero_sesion
                            """, (cr["id_contrato"],))
                            if sesiones_prog:
                                opts_s  = {f"Sesión #{s['numero_sesion']} — {str(s['fecha_hora_programada'])[:16]}": s for s in sesiones_prog}
                                sel_s   = st.selectbox("Sesión", list(opts_s.keys()), key=f"rs_{cr['id_contrato']}")
                                nueva_f = st.date_input("Nueva fecha", value=hoy_d, key=f"rf_{cr['id_contrato']}")
                                nueva_h = st.time_input("Nueva hora", key=f"rh_{cr['id_contrato']}")
                                motivo  = st.text_input("Motivo", key=f"rm_{cr['id_contrato']}")
                                if st.button("Reprogramar", key=f"btn_r_{cr['id_contrato']}", use_container_width=True):
                                    import datetime
                                    ses = opts_s[sel_s]
                                    nueva_fh = datetime.datetime.combine(nueva_f, nueva_h)
                                    run_command("""
                                        UPDATE sesiones
                                        SET fecha_hora_programada=%s,
                                            contador_reprogramaciones=contador_reprogramaciones+1,
                                            motivo_reprogramacion=%s,
                                            reprogramada_por='admin'
                                        WHERE id_sesion=%s
                                    """, (nueva_fh, motivo or None, ses["id_sesion"]))
                                    run_command("""
                                        UPDATE contratos
                                        SET reprogramaciones_usadas=reprogramaciones_usadas+1,
                                            fecha_ultima_reprogramacion=%s
                                        WHERE id_contrato=%s
                                    """, (hoy_d, cr["id_contrato"]))
                                    st.success("Reprogramado.")
                                    st.rerun()
                            else:
                                st.caption("Sin sesiones programadas.")

    # ── SUB-TAB 2: EXCEPCIONES ──
    with rtab2:
        st.markdown("Ajustá los límites de reprogramación para casos especiales.")
        st.markdown("---")

        contratos_exc = run_query("""
            SELECT c.id_contrato, p.nombre||' '||p.apellido AS paciente,
                   pr.nombre AS programa,
                   c.reprogramaciones_usadas,
                   pr.reprogramaciones_max AS reprog_programa,
                   c.reprogramaciones_max_override,
                   COALESCE(c.reprogramaciones_max_override, pr.reprogramaciones_max) AS reprog_max,
                   c.fecha_ultima_reprogramacion
            FROM contratos c
            JOIN pacientes p  ON c.id_paciente=p.id_paciente
            JOIN programas pr ON c.id_programa=pr.id_programa
            WHERE c.estado='activo'
            ORDER BY p.apellido
        """)

        if contratos_exc:
            opts_exc = {f"{c['paciente']} — {c['programa']}": c for c in contratos_exc}
            sel_exc  = st.selectbox("Seleccioná el contrato", list(opts_exc.keys()), key="sel_exc")
            cr_exc   = opts_exc[sel_exc]

            with st.container(border=True):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Paciente:** {cr_exc['paciente']}")
                    st.markdown(f"**Programa:** {cr_exc['programa']}")
                    st.markdown(f"**Límite del programa:** {cr_exc['reprog_programa']}")
                    st.markdown(f"**Override actual:** {cr_exc['reprogramaciones_max_override'] or 'Sin override'}")
                    st.markdown(f"**Usadas:** {cr_exc['reprogramaciones_usadas']}")
                    ultima_exc = cr_exc["fecha_ultima_reprogramacion"]
                    st.markdown(f"**Última reprogramación:** {str(ultima_exc)[:10] if ultima_exc else 'Nunca'}")

                with col2:
                    st.markdown("**Ajustes disponibles:**")

                    # 1. Cambiar límite total
                    nuevo_limite = st.number_input(
                        "Nuevo límite total (0 = usar el del programa)",
                        min_value=0, max_value=20,
                        value=int(cr_exc["reprogramaciones_max_override"] or 0),
                        key="nuevo_limite"
                    )
                    if st.button("Guardar límite", key="btn_limite"):
                        override = nuevo_limite if nuevo_limite > 0 else None
                        run_command("""
                            UPDATE contratos SET reprogramaciones_max_override=%s
                            WHERE id_contrato=%s
                        """, (override, cr_exc["id_contrato"]))
                        st.success(f"Límite actualizado a {nuevo_limite or 'default del programa'}.")
                        st.rerun()

                    st.markdown("---")

                    # 2. Resetear contador mensual
                    st.markdown("**Resetear bloqueo mensual:**")
                    st.caption("Permite que el paciente reprograme aunque ya lo haya hecho este mes.")
                    if st.button("Resetear mes", key="btn_reset_mes", use_container_width=True):
                        run_command("""
                            UPDATE contratos SET fecha_ultima_reprogramacion=NULL
                            WHERE id_contrato=%s
                        """, (cr_exc["id_contrato"],))
                        st.success("Contador mensual reseteado.")
                        st.rerun()

                    st.markdown("---")

                    # 3. Resetear contador total
                    st.markdown("**Resetear contador total:**")
                    st.caption("Vuelve a 0 las reprogramaciones usadas.")
                    if st.button("Resetear total", key="btn_reset_total", use_container_width=True):
                        run_command("""
                            UPDATE contratos SET reprogramaciones_usadas=0
                            WHERE id_contrato=%s
                        """, (cr_exc["id_contrato"],))
                        st.success("Contador total reseteado a 0.")
                        st.rerun()