# -*- coding: utf-8 -*-
import io
import json
import os
import re
import smtplib
from copy import deepcopy
from datetime import date
from email.message import EmailMessage
from html import escape
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
import streamlit.components.v1 as components

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)

PRIMARY = "#00DC8E"
TEXT = "#5F6368"
BORDER = "#00DC8E"
LIGHT_BG = "#F5F7F7"


# ============================================================
# JSON / LEGACY
# ============================================================

def _safe_json_load(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return json.loads(value)
        except Exception:
            return None
    return None


def read_plan_record(row: Dict[str, Any]) -> Dict[str, Any]:
    contenido_json = _safe_json_load(row.get("contenido_json"))
    contenido_legacy = row.get("contenido")

    if isinstance(contenido_json, dict) and contenido_json.get("tipo") == "plan_structured":
        return {
            "kind": "structured",
            "data": contenido_json,
            "legacy_text": contenido_legacy,
        }

    if isinstance(contenido_json, dict) and contenido_json.get("tipo") == "legacy_text":
        return {
            "kind": "legacy",
            "data": None,
            "legacy_text": contenido_json.get("texto") or contenido_legacy or "",
        }

    if contenido_legacy:
        return {
            "kind": "legacy",
            "data": None,
            "legacy_text": contenido_legacy,
        }

    return {"kind": "empty", "data": None, "legacy_text": ""}


def read_template_record(row: Dict[str, Any]) -> Dict[str, Any]:
    estructura_json = _safe_json_load(row.get("estructura_json"))
    estructura_legacy = row.get("estructura")

    if isinstance(estructura_json, dict) and estructura_json.get("tipo") == "template_structured":
        return estructura_json

    if isinstance(estructura_json, dict) and estructura_json.get("tipo") == "legacy_template":
        return {
            "tipo": "legacy_template",
            "markdown": estructura_json.get("markdown", "") or estructura_legacy or "",
        }

    if estructura_legacy:
        return {
            "tipo": "legacy_template",
            "markdown": estructura_legacy,
        }

    return default_template_structured("Modelo base")


# ============================================================
# MODELO BASE
# ============================================================

def _blank_day() -> Dict[str, str]:
    return {
        "desayuno": "",
        "almuerzo": "",
        "cena": "",
    }


def default_template_structured(nombre_modelo: str = "Modelo base") -> Dict[str, Any]:
    return {
        "tipo": "template_structured",
        "template_key": "plan_nutricional_7_dias_v3",
        "layout_key": "plantilla_fiel_empresa_v2",
        "nombre_modelo": nombre_modelo,
        "contenido_base": {
            "cabecera": {
                "titulo": "PLAN DE ALIMENTACIÓN",
                "objetivo": "",
                "alergias": "",
                "intolerancias": "",
            },
            "diagnostico_texto": "",
            "media_manana_tarde_texto": "",
            "ensalada_texto": "",
            "dias": {
                "dia_1": _blank_day(),
                "dia_2": _blank_day(),
                "dia_3": _blank_day(),
                "dia_4": _blank_day(),
                "dia_5": _blank_day(),
                "dia_6": _blank_day(),
                "dia_7": _blank_day(),
            },
            "cantidades_texto": "",
            "recomendaciones_texto": "",
            "consejos_texto": "",
        },
    }


def build_patient_plan_payload(
    *,
    paciente: Dict[str, Any],
    nutricionista_nombre: str,
    id_plantilla: Optional[int],
    nombre_modelo: str,
    template_struct: Dict[str, Any],
    vigencia: Optional[str],
) -> Dict[str, Any]:
    base = deepcopy(template_struct.get("contenido_base", {}))

    return {
        "tipo": "plan_structured",
        "template_key": template_struct.get("template_key", "plan_nutricional_7_dias_v3"),
        "layout_key": template_struct.get("layout_key", "plantilla_fiel_empresa_v2"),
        "origen_modelo": {
            "id_plantilla": id_plantilla,
            "nombre_modelo": nombre_modelo,
        },
        "paciente": {
            "id_paciente": paciente.get("id_paciente"),
            "dni": paciente.get("dni", ""),
            "nombres": paciente.get("nombre", ""),
            "apellidos": paciente.get("apellido", ""),
            "nombre_completo": f"{paciente.get('nombre', '')} {paciente.get('apellido', '')}".strip(),
            "email": paciente.get("email", ""),
        },
        "meta": {
            "fecha_generacion": str(date.today()),
            "vigencia": vigencia,
            "nutricionista": nutricionista_nombre,
        },
        "cabecera": base.get("cabecera", {}),
        "diagnostico_texto": base.get("diagnostico_texto", ""),
        "media_manana_tarde_texto": base.get("media_manana_tarde_texto", ""),
        "ensalada_texto": base.get("ensalada_texto", ""),
        "dias": base.get("dias", {}),
        "cantidades_texto": base.get("cantidades_texto", ""),
        "recomendaciones_texto": base.get("recomendaciones_texto", ""),
        "consejos_texto": base.get("consejos_texto", ""),
    }


# ============================================================
# NORMALIZACIÓN
# ============================================================

def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    value = str(value).replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip()


def _split_lines(text: Any, max_items: int = 30) -> List[str]:
    if text is None:
        return []
    if isinstance(text, list):
        items = []
        for item in text:
            item = _normalize_text(item)
            if item:
                items.append(item)
        return items[:max_items]

    text = str(text).replace("\r", "\n")
    lines = [x.strip(" •-\t") for x in text.split("\n")]
    items = [x for x in lines if x]
    return items[:max_items]


def normalize_plan_for_render(plan_data: Dict[str, Any]) -> Dict[str, Any]:
    out = deepcopy(plan_data)

    out["cabecera"] = out.get("cabecera", {}) or {}
    out["cabecera"]["titulo"] = _normalize_text(out["cabecera"].get("titulo")) or "PLAN DE ALIMENTACIÓN"
    out["cabecera"]["objetivo"] = _normalize_text(out["cabecera"].get("objetivo"))
    out["cabecera"]["alergias"] = _normalize_text(out["cabecera"].get("alergias"))
    out["cabecera"]["intolerancias"] = _normalize_text(out["cabecera"].get("intolerancias"))

    out["diagnostico_items"] = _split_lines(out.get("diagnostico_texto"), max_items=10)
    out["media_items"] = _split_lines(out.get("media_manana_tarde_texto"), max_items=12)
    out["ensalada_items"] = _split_lines(out.get("ensalada_texto"), max_items=12)
    out["cantidades_items"] = _split_lines(out.get("cantidades_texto"), max_items=14)
    out["recomendaciones_items"] = _split_lines(out.get("recomendaciones_texto"), max_items=30)
    out["consejos_items"] = _split_lines(out.get("consejos_texto"), max_items=30)

    dias = out.get("dias", {}) or {}
    normalized_days = {}
    for i in range(1, 8):
        key = f"dia_{i}"
        day = dias.get(key, {}) or {}
        normalized_days[key] = {
            "desayuno": _normalize_text(day.get("desayuno")),
            "almuerzo": _normalize_text(day.get("almuerzo")),
            "cena": _normalize_text(day.get("cena")),
        }
    out["dias"] = normalized_days

    return out


def plain_text_summary_from_plan(plan_data: Dict[str, Any]) -> str:
    plan = normalize_plan_for_render(plan_data)
    cab = plan.get("cabecera", {})
    pac = plan.get("paciente", {})

    lines = [
        cab.get("titulo", "PLAN DE ALIMENTACIÓN"),
        f"Paciente: {pac.get('nombre_completo', '—')}",
        f"Objetivo: {cab.get('objetivo', '—')}",
        f"Alergias: {cab.get('alergias', '—')}",
        f"Intolerancias: {cab.get('intolerancias', '—')}",
        "",
        "Diagnóstico nutricional:",
        *[f"- {x}" for x in plan.get("diagnostico_items", [])],
        "",
        "1/2 mañana - 1/2 tarde:",
        *[f"- {x}" for x in plan.get("media_items", [])],
        "",
        "Ensalada:",
        *[f"- {x}" for x in plan.get("ensalada_items", [])],
        "",
    ]

    for i in range(1, 8):
        d = plan["dias"].get(f"dia_{i}", {})
        lines.extend([
            f"Día {i}",
            f"Desayuno: {d.get('desayuno') or '—'}",
            f"Almuerzo: {d.get('almuerzo') or '—'}",
            f"Cena: {d.get('cena') or '—'}",
            "",
        ])

    lines.extend([
        "Cantidades:",
        *[f"- {x}" for x in plan.get("cantidades_items", [])],
        "",
        "Recomendaciones:",
        *[f"- {x}" for x in plan.get("recomendaciones_items", [])],
        "",
        "Consejos:",
        *[f"- {x}" for x in plan.get("consejos_items", [])],
    ])

    return "\n".join(lines).strip()


# ============================================================
# HTML HELPERS
# ============================================================

def _esc(text: Any) -> str:
    return escape(str(text or "—"))


def _html_list(items: List[str], *, center: bool = False) -> str:
    if not items:
        return "<div class='empty'>—</div>"
    cls = "list-center" if center else "list-left"
    return f"<ul class='{cls}'>" + "".join(f"<li>{_esc(i)}</li>" for i in items) + "</ul>"


def _cell_text(text: str) -> str:
    text = _esc(text or "—")
    text = text.replace("\n", "<br>")
    return text


def _render_day_row(plan: Dict[str, Any], section_key: str, label: str, qty_html: str = "") -> str:
    cells = []
    for i in range(1, 8):
        val = plan["dias"].get(f"dia_{i}", {}).get(section_key, "") or "—"
        cells.append(f"<div class='grid-cell'>{_cell_text(val)}</div>")
    return f"""
    <div class="row-grid">
        <div class="row-label">{label}</div>
        {''.join(cells)}
        <div class="qty-col">{qty_html or "<div class='empty'>—</div>"}</div>
    </div>
    """


# ============================================================
# RENDER HTML PREVIEW
# ============================================================

def render_plan_html(plan_data: Dict[str, Any], page: int = 1) -> str:
    plan = normalize_plan_for_render(plan_data)
    pac = plan.get("paciente", {})
    cab = plan.get("cabecera", {})

    header_html = f"""
    <div class="top-band">{_esc(cab.get('titulo', 'PLAN DE ALIMENTACIÓN'))}</div>

    <div class="header-area">
        <div class="patient-box">
            <div class="patient-row"><div class="left">DNI</div><div class="right">{_esc(pac.get('dni') or '—')}</div></div>
            <div class="patient-row"><div class="left">Nombres</div><div class="right">{_esc(pac.get('nombres') or '—')}</div></div>
            <div class="patient-row"><div class="left">Apellidos</div><div class="right">{_esc(pac.get('apellidos') or '—')}</div></div>
            <div class="patient-row"><div class="left">Objetivo</div><div class="right">{_esc(cab.get('objetivo') or '—')}</div></div>
            <div class="patient-row"><div class="left">Alergias</div><div class="right">{_esc(cab.get('alergias') or '—')}</div></div>
            <div class="patient-row"><div class="left">Intolerancias</div><div class="right">{_esc(cab.get('intolerancias') or '—')}</div></div>
        </div>

        <div class="diagnosis-wrap">
            <div class="diagnosis-label">Diagnóstico Nutricional</div>
            <div class="diagnosis-content">{_html_list(plan.get('diagnostico_items', []))}</div>
        </div>
    </div>
    """

    quantities_1 = _html_list(plan.get("cantidades_items", [])[:5], center=True)
    quantities_2 = _html_list(plan.get("cantidades_items", [])[5:9], center=True)
    quantities_3 = _html_list(plan.get("cantidades_items", [])[9:14], center=True)

    main_table = f"""
    <div class="days-header">
        <div class="label-head"></div>
        <div class="day-head">DÍA 1</div>
        <div class="day-head">DÍA 2</div>
        <div class="day-head">DÍA 3</div>
        <div class="day-head">DÍA 4</div>
        <div class="day-head">DÍA 5</div>
        <div class="day-head">DÍA 6</div>
        <div class="day-head">DÍA 7</div>
        <div class="qty-head">Cantidades</div>
    </div>

    {_render_day_row(plan, 'desayuno', 'Desayuno', quantities_1)}

    <div class="row-wide">
        <div class="row-label wide-label">1/2 mañana<br>1/2 tarde</div>
        <div class="row-wide-content span-7">{_html_list(plan.get('media_items', []))}</div>
        <div class="qty-col short">{quantities_2}</div>
    </div>

    <div class="row-wide">
        <div class="row-label wide-label">Ensalada</div>
        <div class="row-wide-content span-7">{_html_list(plan.get('ensalada_items', []))}</div>
        <div class="qty-col short">{quantities_3}</div>
    </div>

    {_render_day_row(plan, 'almuerzo', 'Almuerzo')}
    {_render_day_row(plan, 'cena', 'Cena')}
    """

    bottom_html = f"""
    <div class="bottom-grid">
        <div class="bottom-box left-box">
            <div class="bottom-title">Recomendaciones</div>
            {_html_list(plan.get('recomendaciones_items', []))}
        </div>
        <div class="bottom-box right-box">
            <div class="bottom-title">Consejos Claves</div>
            {_html_list(plan.get('consejos_items', []))}
        </div>
    </div>
    """

    return f"""
    <html>
    <head>
        <style>
            * {{
                box-sizing: border-box;
            }}
            body {{
                margin: 0;
                padding: 10px;
                background: #ffffff;
                font-family: Arial, Helvetica, sans-serif;
                color: {TEXT};
            }}
            .page {{
                border: 1px solid #cfd8dc;
                padding: 0;
                background: white;
            }}
            .top-band {{
                background: {PRIMARY};
                color: white;
                text-align: center;
                font-weight: 700;
                font-size: 19px;
                text-transform: uppercase;
                padding: 9px 10px;
                letter-spacing: .2px;
            }}
            .header-area {{
                display: grid;
                grid-template-columns: 1.05fr 1fr;
                gap: 12px;
                padding: 12px;
            }}
            .patient-box {{
                border: 1px solid {BORDER};
            }}
            .patient-row {{
                display: grid;
                grid-template-columns: 126px 1fr;
                min-height: 30px;
                border-bottom: 1px solid {BORDER};
            }}
            .patient-row:last-child {{
                border-bottom: none;
            }}
            .patient-row .left {{
                background: {PRIMARY};
                color: white;
                font-weight: 700;
                font-size: 12px;
                display: flex;
                align-items: center;
                padding: 6px 10px;
            }}
            .patient-row .right {{
                display: flex;
                align-items: center;
                justify-content: center;
                text-align: center;
                font-size: 12px;
                line-height: 1.25;
                padding: 6px 10px;
            }}
            .diagnosis-wrap {{
                display: grid;
                grid-template-columns: 180px 1fr;
                border: 1px solid {BORDER};
                min-height: 176px;
            }}
            .diagnosis-label {{
                background: {PRIMARY};
                color: white;
                font-weight: 700;
                font-size: 13px;
                display: flex;
                align-items: center;
                justify-content: center;
                text-align: center;
                padding: 10px;
            }}
            .diagnosis-content {{
                padding: 12px 14px;
                font-size: 12px;
                line-height: 1.3;
                display: flex;
                align-items: center;
                justify-content: center;
                text-align: center;
            }}
            .days-header,
            .row-grid {{
                display: grid;
                grid-template-columns: 120px repeat(7, minmax(110px, 1fr)) 195px;
            }}
            .label-head,
            .day-head,
            .qty-head {{
                background: {PRIMARY};
                color: white;
                font-weight: 700;
                text-align: center;
                padding: 8px 6px;
                font-size: 12px;
                border: 1px solid {BORDER};
            }}
            .row-label {{
                background: {PRIMARY};
                color: white;
                font-weight: 700;
                text-align: center;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 12px;
                border: 1px solid {BORDER};
                padding: 6px;
                min-height: 108px;
                line-height: 1.15;
            }}
            .wide-label {{
                min-height: 58px;
            }}
            .grid-cell {{
                border: 1px solid {BORDER};
                min-height: 108px;
                padding: 10px 8px;
                text-align: center;
                font-size: 12px;
                line-height: 1.28;
                display: flex;
                align-items: center;
                justify-content: center;
                overflow-wrap: anywhere;
                word-break: break-word;
            }}
            .row-wide {{
                display: grid;
                grid-template-columns: 120px repeat(7, minmax(110px, 1fr)) 195px;
            }}
            .row-wide-content {{
                border: 1px solid {BORDER};
                min-height: 52px;
                padding: 8px 10px;
                font-size: 12px;
                line-height: 1.28;
                overflow-wrap: anywhere;
                word-break: break-word;
                display: flex;
                align-items: center;
                justify-content: center;
                text-align: center;
            }}
            .span-7 {{
                grid-column: span 7;
            }}
            .qty-col {{
                border: 1px solid {BORDER};
                min-height: 108px;
                padding: 8px 10px;
                font-size: 12px;
                line-height: 1.28;
                text-align: center;
                display: flex;
                align-items: center;
                justify-content: center;
                overflow-wrap: anywhere;
                word-break: break-word;
            }}
            .qty-col.short {{
                min-height: 52px;
            }}
            .bottom-grid {{
                display: grid;
                grid-template-columns: 2fr 1.15fr;
                gap: 0;
                margin-top: 8px;
                border-top: 1px solid {BORDER};
            }}
            .bottom-box {{
                border: 1px solid {BORDER};
                min-height: 210px;
                padding: 0;
            }}
            .bottom-title {{
                background: {LIGHT_BG};
                color: {TEXT};
                font-weight: 700;
                padding: 8px 10px;
                font-size: 12px;
                border-bottom: 1px solid {BORDER};
            }}
            .bottom-box ul {{
                margin: 0;
                padding: 12px 18px 12px 28px;
                font-size: 12px;
                line-height: 1.32;
            }}
            .list-left {{
                margin: 0;
                padding-left: 18px;
                text-align: left;
            }}
            .list-center {{
                margin: 0;
                padding-left: 18px;
                text-align: center;
                list-style-position: inside;
            }}
            .diagnosis-content ul,
            .row-wide-content ul {{
                margin: 0;
                padding-left: 18px;
            }}
            .empty {{
                padding: 8px;
                font-size: 12px;
                color: #7b8794;
            }}
        </style>
    </head>
    <body>
        <div class="page">
            {header_html if page == 1 else ""}
            {main_table}
            {bottom_html}
        </div>
    </body>
    </html>
    """


def show_plan_preview(plan_data: Dict[str, Any], height: int = 980):
    tab1, tab2 = st.tabs(["Página 1", "Página 2"])
    with tab1:
        components.html(render_plan_html(plan_data, page=1), height=height, scrolling=True)
    with tab2:
        components.html(render_plan_html(plan_data, page=2), height=height, scrolling=True)


# ============================================================
# PDF
# ============================================================

def build_plan_pdf(plan_data: Dict[str, Any]) -> bytes:
    plan = normalize_plan_for_render(plan_data)
    pac = plan.get("paciente", {})
    cab = plan.get("cabecera", {})

    styles = getSampleStyleSheet()

    style_title = ParagraphStyle(
        "style_title",
        parent=styles["Heading1"],
        fontSize=14,
        leading=16,
        alignment=TA_CENTER,
        textColor=colors.white,
    )
    style_small = ParagraphStyle(
        "style_small",
        parent=styles["BodyText"],
        fontSize=7.2,
        leading=8.8,
        textColor=colors.HexColor(TEXT),
        alignment=TA_CENTER,
    )
    style_list = ParagraphStyle(
        "style_list",
        parent=styles["BodyText"],
        fontSize=7.1,
        leading=8.7,
        textColor=colors.HexColor(TEXT),
    )
    style_lbl = ParagraphStyle(
        "style_lbl",
        parent=styles["BodyText"],
        fontSize=8,
        leading=9,
        textColor=colors.white,
        alignment=TA_CENTER,
    )

    def p(txt, style):
        txt = escape(str(txt or "—")).replace("\n", "<br/>")
        return Paragraph(txt, style)

    def list_para(items, style):
        if not items:
            return p("—", style)
        return Paragraph("<br/>".join([f"• {escape(str(x))}" for x in items]), style)

    def title_band():
        t = Table([[p(cab.get("titulo", "PLAN DE ALIMENTACIÓN"), style_title)]],
                  colWidths=[27.4 * cm], rowHeights=[0.92 * cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(PRIMARY)),
            ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor(BORDER)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        return t

    def patient_box():
        rows = [
            [p("<b>DNI</b>", style_lbl), p(pac.get("dni") or "—", style_small)],
            [p("<b>Nombres</b>", style_lbl), p(pac.get("nombres") or "—", style_small)],
            [p("<b>Apellidos</b>", style_lbl), p(pac.get("apellidos") or "—", style_small)],
            [p("<b>Objetivo</b>", style_lbl), p(cab.get("objetivo") or "—", style_small)],
            [p("<b>Alergias</b>", style_lbl), p(cab.get("alergias") or "—", style_small)],
            [p("<b>Intolerancias</b>", style_lbl), p(cab.get("intolerancias") or "—", style_small)],
        ]
        t = Table(rows, colWidths=[3.5 * cm, 10.5 * cm], rowHeights=[0.7 * cm] * 6)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor(PRIMARY)),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor(BORDER)),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor(BORDER)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ]))
        return t

    def diagnosis_box():
        rows = [[p("<b>Diagnóstico Nutricional</b>", style_lbl), list_para(plan.get("diagnostico_items", []), style_list)]]
        t = Table(rows, colWidths=[4.6 * cm, 8.6 * cm], rowHeights=[4.2 * cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(PRIMARY)),
            ("TEXTCOLOR", (0, 0), (0, 0), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor(BORDER)),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor(BORDER)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        return t

    def days_header():
        headers = ["", "DÍA 1", "DÍA 2", "DÍA 3", "DÍA 4", "DÍA 5", "DÍA 6", "DÍA 7", "Cantidades"]
        t = Table([headers], colWidths=[2.15 * cm] + [3.43 * cm] * 7 + [4.95 * cm], rowHeights=[0.66 * cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(PRIMARY)),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor(BORDER)),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor(BORDER)),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))
        return t

    def row_standard(label, field, qty_items=None):
        qty_items = qty_items or []
        row = [p(f"<b>{label}</b>", style_lbl)]
        for i in range(1, 8):
            row.append(p(plan["dias"].get(f"dia_{i}", {}).get(field) or "—", style_small))
        row.append(list_para(qty_items, style_small))
        t = Table([row], colWidths=[2.15 * cm] + [3.43 * cm] * 7 + [4.95 * cm], rowHeights=[2.65 * cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(PRIMARY)),
            ("TEXTCOLOR", (0, 0), (0, 0), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor(BORDER)),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor(BORDER)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (7, 0), "CENTER"),
            ("ALIGN", (8, 0), (8, 0), "CENTER"),
        ]))
        return t

    def row_wide(label, items, qty_items=None):
        qty_items = qty_items or []
        row = [p(f"<b>{label}</b>", style_lbl), list_para(items, style_list), list_para(qty_items, style_small)]
        t = Table([row], colWidths=[2.15 * cm, 24.01 * cm, 4.95 * cm], rowHeights=[1.22 * cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(PRIMARY)),
            ("TEXTCOLOR", (0, 0), (0, 0), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor(BORDER)),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor(BORDER)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        return t

    def bottom_boxes():
        rec = Table([
            [p("<b>Recomendaciones</b>", style_list)],
            [list_para(plan.get("recomendaciones_items", []), style_list)]
        ], colWidths=[17.8 * cm], rowHeights=[0.68 * cm, 4.0 * cm])

        con = Table([
            [p("<b>Consejos Claves</b>", style_list)],
            [list_para(plan.get("consejos_items", []), style_list)]
        ], colWidths=[9.2 * cm], rowHeights=[0.68 * cm, 4.0 * cm])

        for t in (rec, con):
            t.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor(BORDER)),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor(BORDER)),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(LIGHT_BG)),
            ]))
        wrap = Table([[rec, con]], colWidths=[17.8 * cm, 9.2 * cm])
        wrap.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        return wrap

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=0.45 * cm,
        rightMargin=0.45 * cm,
        topMargin=0.45 * cm,
        bottomMargin=0.45 * cm,
    )

    story = []

    story.append(title_band())
    story.append(Spacer(1, 0.15 * cm))
    top = Table([[patient_box(), diagnosis_box()]], colWidths=[14.0 * cm, 13.4 * cm])
    top.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(top)
    story.append(Spacer(1, 0.15 * cm))
    story.append(days_header())
    story.append(row_standard("Desayuno", "desayuno", plan.get("cantidades_items", [])[:5]))
    story.append(row_wide("1/2 mañana\n1/2 tarde", plan.get("media_items", []), plan.get("cantidades_items", [])[5:9]))
    story.append(row_wide("Ensalada", plan.get("ensalada_items", []), plan.get("cantidades_items", [])[9:14]))
    story.append(row_standard("Almuerzo", "almuerzo"))
    story.append(row_standard("Cena", "cena"))
    story.append(Spacer(1, 0.12 * cm))
    story.append(bottom_boxes())

    story.append(PageBreak())
    story.append(days_header())
    story.append(row_standard("Desayuno", "desayuno", plan.get("cantidades_items", [])[:5]))
    story.append(row_wide("1/2 mañana\n1/2 tarde", plan.get("media_items", []), plan.get("cantidades_items", [])[5:9]))
    story.append(row_wide("Ensalada", plan.get("ensalada_items", []), plan.get("cantidades_items", [])[9:14]))
    story.append(row_standard("Almuerzo", "almuerzo"))
    story.append(row_standard("Cena", "cena"))
    story.append(Spacer(1, 0.12 * cm))
    story.append(bottom_boxes())

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


# ============================================================
# EMAIL
# ============================================================

def send_plan_email(
    *,
    to_email: str,
    patient_name: str,
    pdf_bytes: bytes,
    pdf_filename: str,
    subject: Optional[str] = None,
) -> Tuple[bool, str]:
    if not to_email:
        return False, "El paciente no tiene email registrado."

    try:
        smtp_host = st.secrets.get("SMTP_HOST") or os.getenv("SMTP_HOST")
        smtp_port = int(st.secrets.get("SMTP_PORT") or os.getenv("SMTP_PORT") or 587)
        smtp_user = st.secrets.get("SMTP_USER") or os.getenv("SMTP_USER")
        smtp_password = st.secrets.get("SMTP_PASSWORD") or os.getenv("SMTP_PASSWORD")
        smtp_from = st.secrets.get("SMTP_FROM") or os.getenv("SMTP_FROM") or smtp_user
    except Exception:
        smtp_host = os.getenv("SMTP_HOST")
        smtp_port = int(os.getenv("SMTP_PORT") or 587)
        smtp_user = os.getenv("SMTP_USER")
        smtp_password = os.getenv("SMTP_PASSWORD")
        smtp_from = os.getenv("SMTP_FROM") or smtp_user

    if not all([smtp_host, smtp_port, smtp_user, smtp_password, smtp_from]):
        return False, "Faltan variables SMTP en secrets/env."

    mail_subject = subject or "Tu plan nutricional"
    body = f"""
Hola {patient_name},

Te compartimos tu plan nutricional en PDF.

También puedes verlo y descargarlo desde tu cuenta en la app.

Saludos,
Equipo de Nutrición
""".strip()

    msg = EmailMessage()
    msg["Subject"] = mail_subject
    msg["From"] = smtp_from
    msg["To"] = to_email
    msg.set_content(body)
    msg.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=pdf_filename,
    )

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        return True, "Email enviado correctamente."
    except Exception as e:
        return False, f"No se pudo enviar el email: {e}"