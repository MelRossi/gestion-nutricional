import streamlit as st
import pandas as pd
from database import run_query
from utils import mostrar_sidebar
from datetime import date

if "usuario" not in st.session_state:
    st.warning("Debés iniciar sesión.")
    st.stop()

if st.session_state["usuario"]["rol"] != "paciente":
    st.error("Esta vista es solo para pacientes.")
    st.stop()

usuario     = st.session_state["usuario"]
id_paciente = usuario["id_paciente"]

mostrar_sidebar()
st.markdown("## Mi progreso")
st.markdown("---")

# Contrato activo
contrato = run_query("""
    SELECT c.id_contrato, pr.nombre AS programa, pr.cantidad_sesiones,
           c.fecha_inicio, c.fecha_fin,
           n.nombre||' '||n.apellido AS nutricionista
    FROM contratos c
    JOIN programas pr     ON c.id_programa=pr.id_programa
    JOIN nutricionistas n ON c.id_nutricionista=n.id_nutricionista
    WHERE c.id_paciente=%s AND c.estado='activo'
    ORDER BY c.fecha_creacion DESC LIMIT 1
""", (id_paciente,))

if not contrato:
    st.info("No tenés un programa activo.")
    st.stop()

c = contrato[0]

# Sesiones
sesiones = run_query("""
    SELECT s.estado FROM sesiones s
    JOIN contratos ct ON s.id_contrato=ct.id_contrato
    WHERE ct.id_paciente=%s AND ct.estado='activo'
""", (id_paciente,))

realizadas = sum(1 for s in sesiones if s["estado"] == "atendida")
total      = int(c["cantidad_sesiones"])
restantes  = total - realizadas
pct        = realizadas / total if total > 0 else 0

# ── RESUMEN DEL PROGRAMA ──
with st.container(border=True):
    col1, col2 = st.columns([3, 2])
    with col1:
        st.markdown(f"**{c['programa']}**")
        st.caption(f"Nutricionista: {c['nutricionista']}")
        st.caption(f"Desde {str(c['fecha_inicio'])[:10]} hasta {str(c['fecha_fin'])[:10]}")
    with col2:
        st.caption("Avance del programa")
        st.progress(pct, text=f"{realizadas} de {total} sesiones realizadas")
        st.caption(f"Quedan **{restantes}** sesión(es)")

st.markdown("---")

# ── PRÓXIMA SESIÓN ──
proxima = run_query("""
    SELECT s.numero_sesion, s.fecha_hora_programada, s.modalidad, s.estado_confirmacion
    FROM sesiones s
    JOIN contratos c ON s.id_contrato=c.id_contrato
    WHERE c.id_paciente=%s AND c.estado='activo'
    AND s.estado='programada' AND s.fecha_hora_programada >= NOW()
    ORDER BY s.fecha_hora_programada LIMIT 1
""", (id_paciente,))

if proxima:
    ps   = proxima[0]
    conf = ps.get("estado_confirmacion", "")
    badge = {"confirmada":"confirmada", "pendiente":"pendiente de confirmación", "modificada":"horario modificado por tu nutricionista"}.get(conf, conf)
    st.markdown(f"**Próxima sesión:** #{ps['numero_sesion']} · {str(ps['fecha_hora_programada'])[:16]} · {ps['modalidad']} · {badge}")
    st.markdown("---")

# ── HISTORIA NUTRICIONAL ──
historia = run_query("""
    SELECT version, peso, talla, imc, circ_cintura, circ_cadera, circ_brazo,
           avance_objetivos, fecha_registro
    FROM historia_nutricional
    WHERE id_paciente=%s ORDER BY version
""", (id_paciente,))

if historia:
    st.markdown("### Evolución")
    df_h = pd.DataFrame(historia)

    try:
        import altair as alt

        col1, col2 = st.columns(2)
        with col1:
            st.caption("Peso (kg)")
            df_peso = df_h[["version","peso"]].dropna()
            if len(df_peso) > 0:
                ch = alt.Chart(df_peso).mark_line(point=True, color="#1D9E75").encode(
                    x=alt.X("version:O", title="Sesión"),
                    y=alt.Y("peso:Q", scale=alt.Scale(zero=False), title="kg"),
                    tooltip=["version","peso"]
                ).properties(height=180)
                st.altair_chart(ch, use_container_width=True)

                # Variación
                if len(df_peso) > 1:
                    var = float(df_peso["peso"].iloc[-1]) - float(df_peso["peso"].iloc[0])
                    emoji = "📉" if var < 0 else "📈" if var > 0 else "➡️"
                    st.caption(f"{emoji} Variación total: **{var:+.1f} kg**")
            else:
                st.caption("Sin datos de peso aún.")

        with col2:
            st.caption("IMC")
            df_imc = df_h[["version","imc"]].dropna()
            if len(df_imc) > 0:
                ch2 = alt.Chart(df_imc).mark_line(point=True, color="#185FA5").encode(
                    x=alt.X("version:O", title="Sesión"),
                    y=alt.Y("imc:Q", scale=alt.Scale(zero=False), title="IMC"),
                    tooltip=["version","imc"]
                ).properties(height=180)
                st.altair_chart(ch2, use_container_width=True)

                ultimo_imc = float(df_imc["imc"].iloc[-1])
                if ultimo_imc < 18.5:    cat = "Bajo peso"
                elif ultimo_imc < 25:    cat = "Normal"
                elif ultimo_imc < 30:    cat = "Sobrepeso"
                else:                    cat = "Obesidad"
                st.caption(f"IMC actual: **{ultimo_imc:.1f}** ({cat})")
            else:
                st.caption("Sin datos de IMC aún.")

        # Circunferencias si hay datos
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
                color=alt.Color("medida:N", legend=alt.Legend(title="Medida")),
                tooltip=["version","medida","cm"]
            ).properties(height=180)
            st.altair_chart(ch3, use_container_width=True)

    except ImportError:
        st.info("Instalá altair para ver los gráficos: `pip install altair`")

    # Tabla resumen
    st.markdown("---")
    st.caption("Tabla de mediciones")
    df_tabla = df_h.rename(columns={
        "version":"Sesión","peso":"Peso","talla":"Talla","imc":"IMC",
        "circ_cintura":"Cintura","circ_cadera":"Cadera","circ_brazo":"Brazo",
        "avance_objetivos":"Avances","fecha_registro":"Fecha"
    })
    cols_show = ["Sesión","Peso","Talla","IMC","Cintura","Cadera","Brazo","Fecha"]
    cols_show = [c for c in cols_show if c in df_tabla.columns]
    df_tabla["Fecha"] = pd.to_datetime(df_tabla["Fecha"]).dt.strftime("%d/%m/%Y")
    st.dataframe(df_tabla[cols_show], use_container_width=True, hide_index=True)

else:
    st.info("Aún no hay mediciones registradas. Tu nutricionista las irá cargando sesión a sesión.")

st.markdown("---")

# ── ÚLTIMA ANAMNESIS ──
anamnesis = run_query("""
    SELECT objetivo_principal, actividad_fisica, nivel_estres,
           consumo_agua_litros, version, fecha_registro
    FROM anamnesis WHERE id_paciente=%s ORDER BY version DESC LIMIT 1
""", (id_paciente,))

if anamnesis:
    a = anamnesis[0]
    st.markdown("### Mi perfil")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.caption("Objetivo")
        st.markdown(f"{a.get('objetivo_principal') or '—'}")
    with col2:
        st.caption("Actividad física")
        st.markdown(f"**{a.get('actividad_fisica') or '—'}**")
        st.caption("Nivel de estrés")
        st.markdown(f"**{a.get('nivel_estres') or '—'}**")
    with col3:
        st.caption("Agua diaria")
        st.markdown(f"**{a.get('consumo_agua_litros') or '—'} L**")
        st.caption(f"Última actualización: {str(a.get('fecha_registro',''))[:10]}")