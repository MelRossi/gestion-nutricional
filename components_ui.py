import streamlit as st
from utils import mostrar_sidebar


# NOTIFICACIONES CON COLORES DE PALETA

def mostrar_notificacion(tipo, mensaje, icono=None):
    """
    Muestra notificación con colores de la paleta oficial.
    
    Args:
        tipo (str): 'success', 'info', 'warning', 'error'
        mensaje (str): Texto del mensaje
        icono (str, optional): Emoji personalizado
    
    Returns:
        None
    """
    colores = {
        'success': {'bg': '#00DC8E', 'border': '#00b874', 'text': '#141414', 'icon': '✓'},
        'info': {'bg': '#CBF9F9', 'border': '#00DC8E', 'text': '#141414', 'icon': 'ℹ'},
        'warning': {'bg': '#FFCC33', 'border': '#e6b82e', 'text': '#141414', 'icon': '⚠'},
        'error': {'bg': '#EF4444', 'border': '#dc2626', 'text': '#ffffff', 'icon': '✕'}
    }
    
    color = colores.get(tipo, colores['info'])
    icono_display = icono or color['icon']
    
    bg_opacity = '15' if tipo != 'error' else '20'
    
    st.markdown(f"""
        <div style="
            background: {color['bg']}{bg_opacity};
            border-left: 4px solid {color['border']};
            padding: 12px 16px;
            border-radius: 10px;
            margin: 12px 0;
            display: flex;
            align-items: center;
            gap: 12px;
        ">
            <span style="font-size: 1.2rem; flex-shrink: 0;">{icono_display}</span>
            <span style="color: {color['text']}; font-size: 0.9rem; line-height: 1.5;">{mensaje}</span>
        </div>
    """, unsafe_allow_html=True)



# BOTONES CON TAMAÑOS CONSISTENTES

def boton_primario(label, key=None, on_click=None, disabled=False, ancho="auto", icono=None):
    """
    Botón principal verde con tamaño consistente.
    
    Args:
        label (str): Texto del botón
        key (str, optional): Key única para el botón
        on_click (callable, optional): Función a ejecutar al hacer clic
        disabled (bool): Si el botón está deshabilitado
        ancho (str): 'auto', 'medio' (50%), 'completo' (100%)
        icono (str, optional): Emoji para el botón
    
    Returns:
        bool: True si se hizo clic en el botón
    """
    label_final = f"{icono} {label}" if icono else label
    
    if ancho == "completo":
        return st.button(
            label_final,
            key=key,
            on_click=on_click,
            disabled=disabled,
            use_container_width=True,
            type="primary"
        )
    elif ancho == "medio":
        col1, col2 = st.columns([0.5, 0.5])
        with col1:
            return st.button(
                label_final,
                key=key,
                on_click=on_click,
                disabled=disabled,
                use_container_width=True,
                type="primary"
            )
    else:  # auto
        return st.button(
            label_final,
            key=key,
            on_click=on_click,
            disabled=disabled,
            type="primary"
        )


def boton_secundario(label, key=None, on_click=None, posicion='derecha', icono=None):
    """
    Botón secundario (descarga, cancelar, etc.) con posicionamiento.
    
    Args:
        label (str): Texto del botón
        key (str, optional): Key única para el botón
        on_click (callable, optional): Función a ejecutar al hacer clic
        posicion (str): 'izquierda', 'derecha', 'centro'
        icono (str, optional): Emoji para el botón
    
    Returns:
        bool: True si se hizo clic en el botón
    """
    label_final = f"{icono} {label}" if icono else label
    
    col_config = {
        'izquierda': [0.4, 0.6],
        'derecha': [0.6, 0.4],
        'centro': [0.3, 0.4, 0.3]
    }
    
    if posicion in ['izquierda', 'derecha']:
        cols = st.columns(col_config[posicion])
        col_index = 0 if posicion == 'izquierda' else 1
        with cols[col_index]:
            return st.button(
                label_final,
                key=key,
                on_click=on_click,
                type="secondary"
            )
    else:  # centro
        cols = st.columns(col_config['centro'])
        with cols[1]:
            return st.button(
                label_final,
                key=key,
                on_click=on_click,
                type="secondary"
            )


# JERARQUÍA VISUAL Y ESTRUCTURA

def titulo_seccion(texto, nivel=3):
    """
    Título de sección con jerarquía clara.
    
    Args:
        texto (str): Texto del título
        nivel (int): Nivel del título (2, 3 o 4)
    """
    if nivel == 2:
        st.markdown(f"## **{texto}**")
    elif nivel == 3:
        st.markdown(f"### **{texto}**")
    else:
        st.markdown(f"#### **{texto}**")


def label_importante(texto):
    """
    Label de campo importante con peso visual.
    
    Args:
        texto (str): Texto del label
    """
    st.markdown(
        f"<p style='font-weight:600; font-size:0.9rem; margin-bottom:8px; color:#141414;'>{texto}</p>", 
        unsafe_allow_html=True
    )


def separador(altura='md'):
    """
    Separador visual entre bloques.
    
    Args:
        altura (str): 'xs', 'sm', 'md', 'lg', 'xl'
    """
    alturas = {
        'xs': 8,
        'sm': 12,
        'md': 16,
        'lg': 24,
        'xl': 32,
    }
    px = alturas.get(altura, 16)
    st.markdown(f"<div style='height:{px}px'></div>", unsafe_allow_html=True)



# BLOQUES Y CARDS


def bloque_info(contenido_html, color_borde="#00DC8E", padding="16px"):
    st.markdown(f"""<div style="
background: white;
border: 2px solid {color_borde};
border-radius: 12px;
padding: {padding};
margin: 12px 0;
">
{contenido_html}
</div>""", unsafe_allow_html=True)


def card_paciente(nombre, programa, realizadas, total, restantes, reprogramaciones):

    html = f"""<div style="
display:flex;
justify-content:space-between;
align-items:flex-start;
gap:16px;
">

<div style="flex:1;">
<p style="margin:0; font-weight:700; font-size:1.1rem; color:#141414;">
{nombre}
</p>

<p style="margin:6px 0 0 0; font-size:0.9rem; color:#6B7280;">
<span style="font-weight:600;">Programa:</span> {programa}
</p>

<p style="margin:6px 0 0 0; font-size:0.85rem; color:#6B7280;">
Reprogramaciones: <strong>{reprogramaciones or 0}</strong>
</p>
</div>

<div style="text-align:right; min-width:140px;">
<p style="margin:0; font-size:0.9rem;">
Realizadas: <strong style="color:#00DC8E;">{realizadas}</strong> / {total}
</p>

<p style="margin:6px 0 0 0; font-size:0.9rem;">
Restantes: <strong style="color:#FFCC33;">{restantes}</strong>
</p>
</div>

</div>"""

    bloque_info(html, color_borde="#00DC8E", padding="20px")


# BADGES Y PILLS DE ESTADO

# Colores estandarizados para estados
COLORES_ESTADO = {
    # Estados de sesiones
    'programada': {'color': '#FFCC33', 'bg': '#FFCC3315', 'border': '#FFCC3350', 'label': 'Programada'},
    'confirmada': {'color': '#00DC8E', 'bg': '#00DC8E15', 'border': '#00DC8E50', 'label': 'Confirmada'},
    'atendida': {'color': '#00DC8E', 'bg': '#00DC8E15', 'border': '#00DC8E50', 'label': 'Atendida'},
    'cancelada': {'color': '#EF4444', 'bg': '#EF444415', 'border': '#EF444450', 'label': 'Cancelada'},
    'ausente': {'color': '#EF4444', 'bg': '#EF444415', 'border': '#EF444450', 'label': 'Ausente'},
    
    # Estados de disponibilidad
    'disponible': {'color': '#00DC8E', 'bg': '#00DC8E15', 'border': '#00DC8E50', 'label': 'Disponible'},
    'reservado': {'color': '#8C52FF', 'bg': '#8C52FF15', 'border': '#8C52FF50', 'label': 'Reservado'},
    'bloqueado': {'color': '#808080', 'bg': '#80808015', 'border': '#80808050', 'label': 'Bloqueado'},
    
    # Estados de contratos
    'activo': {'color': '#00DC8E', 'bg': '#00DC8E15', 'border': '#00DC8E50', 'label': 'Activo'},
    'pendiente_pago': {'color': '#FFCC33', 'bg': '#FFCC3315', 'border': '#FFCC3350', 'label': 'Pendiente pago'},
    'finalizado': {'color': '#808080', 'bg': '#80808015', 'border': '#80808050', 'label': 'Finalizado'},
    
    # Estados generales
    'pendiente': {'color': '#FFCC33', 'bg': '#FFCC3315', 'border': '#FFCC3350', 'label': 'Pendiente'},
    'aprobado': {'color': '#00DC8E', 'bg': '#00DC8E15', 'border': '#00DC8E50', 'label': 'Aprobado'},
    'rechazado': {'color': '#EF4444', 'bg': '#EF444415', 'border': '#EF444450', 'label': 'Rechazado'},
}


def badge_estado(estado, custom_label=None):
    """
    Genera badge con color correcto según el estado.
    
    Args:
        estado (str): Estado del elemento
        custom_label (str, optional): Label personalizado
    
    Returns:
        str: HTML del badge
    """
    info = COLORES_ESTADO.get(
        estado.lower(), 
        {'color': '#808080', 'bg': '#80808015', 'border': '#80808050', 'label': estado}
    )
    
    label = custom_label or info['label']
    
    return f"""
        <span style="
            background: {info['bg']};
            color: {info['color']};
            padding: 5px 14px;
            border-radius: 14px;
            font-size: 0.8rem;
            font-weight: 600;
            display: inline-block;
            border: 1px solid {info['border']};
            white-space: nowrap;
        ">
            {label}
        </span>
    """


def mostrar_badge(estado, custom_label=None):
    """
    Muestra un badge de estado en Streamlit.
    
    Args:
        estado (str): Estado del elemento
        custom_label (str, optional): Label personalizado
    """
    st.markdown(badge_estado(estado, custom_label), unsafe_allow_html=True)



# ELEMENTOS SELECCIONABLES

def pills_seleccionables(opciones, key="pills", seleccion_actual=None):
    """
    Pills horizontales con estilo moderno y feedback visual.
    
    Args:
        opciones (list): Lista de opciones
        key (str): Key única para el widget
        seleccion_actual (str, optional): Opción seleccionada por defecto
    
    Returns:
        str: Opción seleccionada
    """
    # CSS para pills con hover mejorado
    st.markdown("""
        <style>
        div[data-testid*="pills"] div[role="radiogroup"] > label {
            background: white !important;
            border: 1.5px solid #E2E4DE !important;
            border-radius: 20px !important;
            padding: 10px 24px !important;
            margin: 6px 4px !important;
            display: inline-block !important;
            cursor: pointer !important;
            transition: all 0.2s ease !important;
            font-weight: 500 !important;
            font-size: 0.9rem !important;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
        }
        
        div[data-testid*="pills"] div[role="radiogroup"] > label:hover {
            background: #f9faf8 !important;
            border-color: #00DC8E !important;
            box-shadow: 0 2px 8px rgba(0,220,142,0.15) !important;
            transform: translateY(-1px) !important;
        }
        
        div[data-testid*="pills"] div[role="radiogroup"] > label[data-checked="true"] {
            background: linear-gradient(135deg, #00DC8E, #00b874) !important;
            border-color: #00DC8E !important;
            color: white !important;
            box-shadow: 0 4px 12px rgba(0,220,142,0.3) !important;
            font-weight: 600 !important;
        }
        </style>
    """, unsafe_allow_html=True)
    
    index = opciones.index(seleccion_actual) if seleccion_actual in opciones else 0
    
    return st.radio(
        label="",
        options=opciones,
        horizontal=True,
        key=key,
        index=index,
        label_visibility="collapsed"
    )


def secciones_card(opciones, key="seccion", seleccion_actual=None):
    """
    Secciones con estilo card y sombreado visual.
    
    Args:
        opciones (list): Lista de opciones
        key (str): Key única para el widget
        seleccion_actual (str, optional): Opción seleccionada por defecto
    
    Returns:
        str: Opción seleccionada
    """
    # CSS para cards con hover
    st.markdown("""
        <style>
        div[data-testid*="seccion"] div[role="radiogroup"] > label {
            background: white !important;
            border: 1.5px solid #E2E4DE !important;
            border-radius: 12px !important;
            padding: 16px 20px !important;
            margin: 8px 0 !important;
            cursor: pointer !important;
            transition: all 0.2s ease !important;
            box-shadow: 0 1px 4px rgba(0,0,0,0.05) !important;
            display: block !important;
        }
        
        div[data-testid*="seccion"] div[role="radiogroup"] > label:hover {
            background: #f9faf8 !important;
            border-color: #00DC8E !important;
            box-shadow: 0 4px 12px rgba(0,220,142,0.15) !important;
            transform: translateY(-2px) !important;
        }
        
        div[data-testid*="seccion"] div[role="radiogroup"] > label[data-checked="true"] {
            background: linear-gradient(135deg, #00DC8E05, #CBF9F910) !important;
            border-color: #00DC8E !important;
            box-shadow: 0 4px 12px rgba(0,220,142,0.2) !important;
            font-weight: 600 !important;
        }
        
        div[data-testid*="seccion"] div[role="radiogroup"] > label span {
            font-family: 'Syne', sans-serif !important;
            font-size: 1rem !important;
            font-weight: 600 !important;
            color: #141414 !important;
        }
        
        div[data-testid*="seccion"] div[role="radiogroup"] > label[data-checked="true"] span {
            color: #00DC8E !important;
        }
        </style>
    """, unsafe_allow_html=True)
    
    index = opciones.index(seleccion_actual) if seleccion_actual in opciones else 0
    
    return st.radio(
        label="",
        options=opciones,
        key=key,
        index=index,
        label_visibility="collapsed"
    )



# HELPERS DE ESPACIADO

ESPACIADO = {
    'xs': 8,
    'sm': 12,
    'md': 16,
    'lg': 24,
    'xl': 32,
}

def espacio(tamaño='md'):
    """
    Genera espaciado vertical consistente.
    
    Args:
        tamaño (str): 'xs', 'sm', 'md', 'lg', 'xl'
    """
    separador(tamaño)



# DIVIDER CON ESTILO

def divider(texto=None):
    """
    Divider con texto opcional y estilo mejorado.
    
    Args:
        texto (str, optional): Texto para el divider
    """
    if texto:
        st.markdown(f"""
            <div style="
                display: flex;
                align-items: center;
                margin: 24px 0;
                gap: 16px;
            ">
                <div style="flex: 1; height: 1px; background: #E2E4DE;"></div>
                <span style="
                    color: #6B7280;
                    font-size: 0.85rem;
                    font-weight: 600;
                    text-transform: uppercase;
                    letter-spacing: 0.05em;
                ">{texto}</span>
                <div style="flex: 1; height: 1px; background: #E2E4DE;"></div>
            </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("---")



# LOADING INDICATOR

def loading_message(mensaje="Cargando..."):
    """
    Mensaje de carga con estilo.
    
    Args:
        mensaje (str): Texto del mensaje
    """
    st.markdown(f"""
        <div style="
            text-align: center;
            padding: 40px 20px;
            color: #6B7280;
        ">
            <div style="
                display: inline-block;
                width: 40px;
                height: 40px;
                border: 4px solid #E2E4DE;
                border-top-color: #00DC8E;
                border-radius: 50%;
                animation: spin 1s linear infinite;
            "></div>
            <p style="margin-top: 16px; font-size: 0.9rem;">{mensaje}</p>
        </div>
        <style>
        @keyframes spin {{
            to {{ transform: rotate(360deg); }}
        }}
        </style>
    """, unsafe_allow_html=True)