import io
import base64
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
    Image,
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



# MODELO BASE


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



# NORMALIZACIÓN


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



# HTML HELPERS


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



# RENDER HTML PREVIEW


PLAN_UTILS_LAYOUT_VERSION = "plantilla_referencia_preview_estable_v2026_05_07_aire_visual"


def _inline_text(items: List[str]) -> str:
    if not items:
        return "<span class='empty'>—</span>"
    return " · ".join(escape(str(i)) for i in items if str(i).strip())


def _logos_html(plan: Dict[str, Any]) -> str:
    logos = plan.get("logos") or {}
    tags = []
    for key in ("dueno", "empresa"):
        src = logos.get(key)
        if src:
            tags.append(f"<img class='plan-logo' src='{src}' />")
    if not tags:
        return ""
    return "<div class='logos-wrap'>" + "".join(tags) + "</div>"


def _html_bullets(items: List[str], *, compact: bool = False) -> str:
    if not items:
        return "<span class='empty'>—</span>"
    cls = "bullets compact" if compact else "bullets"
    return f"<ul class='{cls}>" + "".join(f"<li>{_esc(x)}</li>" for x in items if str(x).strip()) + "</ul>"


def _html_bullet_list(items: List[str], *, compact: bool = False) -> str:
    if not items:
        return "<span class='empty'>—</span>"
    cls = "bullets compact" if compact else "bullets"
    return f"<ul class='{cls}'>" + "".join(f"<li>{_esc(x)}</li>" for x in items if str(x).strip()) + "</ul>"


def render_plan_html(plan_data: Dict[str, Any], page: int = 1) -> str:
    """Vista previa HTML estable usando tablas reales, no grids híbridos."""
    plan = normalize_plan_for_render(plan_data)
    pac = plan.get("paciente", {})
    cab = plan.get("cabecera", {})

    title = _esc(cab.get("titulo", "PLAN DE ALIMENTACIÓN"))
    logos_html = _logos_html(plan)

    patient_rows = "".join([
        f"<tr><th>DNI</th><td>{_esc(pac.get('dni') or '—')}</td></tr>",
        f"<tr><th>Nombres</th><td>{_esc(pac.get('nombres') or '—')}</td></tr>",
        f"<tr><th>Apellidos</th><td>{_esc(pac.get('apellidos') or '—')}</td></tr>",
        f"<tr><th>Objetivo</th><td>{_esc(cab.get('objetivo') or '—')}</td></tr>",
        f"<tr><th>Alergias</th><td>{_esc(cab.get('alergias') or '—')}</td></tr>",
        f"<tr><th>Intolerancias</th><td>{_esc(cab.get('intolerancias') or '—')}</td></tr>",
    ])

    def day_cells(section_key: str) -> str:
        cells = []
        for i in range(1, 8):
            value = plan["dias"].get(f"dia_{i}", {}).get(section_key, "") or "—"
            cells.append(f"<td class='meal-cell'>{_cell_text(value)}</td>")
        return "".join(cells)

    cantidades = plan.get("cantidades_items", [])

    html = f"""
    <html>
    <head>
      <style>
        * {{ box-sizing: border-box; }}
        body {{ margin:0; padding:10px; background:#fff; font-family:Arial, Helvetica, sans-serif; color:{TEXT}; }}
        .sheet {{ width:1080px; margin:0 auto; background:white; }}
        table {{ border-collapse:collapse; table-layout:fixed; width:100%; }}
        .green {{ background:{PRIMARY}; color:white; font-weight:700; }}

        .top-table {{ margin-bottom:0; }}
        .top-title {{ height:22px; font-size:14px; line-height:22px; text-align:center; text-transform:uppercase; border:1px solid {BORDER}; }}
        .top-table > tbody > tr.top-row > td {{ height:82px; border:1px solid {BORDER}; vertical-align:middle; padding:0; }}
        .patient-box table {{ height:82px; }}
        .patient-box table tr {{ height:15px; }}
        .patient-box table th, .patient-box table td {{ height:15px; }}
        .patient-box th {{ width:78px; background:{PRIMARY}; color:white; font-size:8.5px; font-weight:700; text-align:center; border:1px solid {BORDER}; padding:2px 3px; }}
        .patient-box td {{ font-size:8.5px; line-height:1.15; text-align:center; border:1px solid {BORDER}; padding:2px 5px; overflow-wrap:anywhere; }}
        .blank-head {{ border:none !important; background:white; }}
        .diag-label {{ background:{PRIMARY}; color:white; font-weight:700; font-size:8px; text-align:center; }}
        .diag-text {{ font-size:7.5px; line-height:1.1; padding:4px 8px !important; }}
        .logos-cell {{ background:white; text-align:center; }}
        .logos-wrap {{ display:flex; justify-content:center; align-items:center; gap:20px; width:100%; height:100%; }}
        .plan-logo {{ max-width:90px; max-height:46px; object-fit:contain; display:block; }}

        .plan-table th, .plan-table td {{ border:1px solid {BORDER}; vertical-align:middle; }}
        .plan-table thead th {{ height:18px; background:{PRIMARY}; color:white; font-size:8px; font-weight:700; text-align:center; padding:2px; }}
        .row-label {{ background:{PRIMARY}; color:white; font-size:8px; font-weight:700; text-align:center; line-height:1.05; padding:2px; }}
        .meal-cell {{ font-size:8.2px; line-height:1.25; text-align:center; padding:8px 6px; overflow-wrap:anywhere; word-break:break-word; }}
        .meal-row td, .meal-row th {{ min-height:0; }}
        .plan-table tr.meal-row > th, .plan-table tr.meal-row > td {{ height:96px; }}
        .plan-table tr.row-almuerzo > th, .plan-table tr.row-almuerzo > td,
        .plan-table tr.row-cena > th, .plan-table tr.row-cena > td {{ height:104px; }}
        .plan-table tr.row-wide > th, .plan-table tr.row-wide > td {{ height:34px; }}
        .wide-cell {{ font-size:8px; line-height:1.22; text-align:center; padding:6px 6px; }}
        .qty-cell {{ font-size:8px; line-height:1.22; text-align:center; padding:8px 6px; }}
        .gap-cell, .gap-head {{ width:8px !important; min-width:8px; max-width:8px; border:none !important; background:white !important; padding:0 !important; }}
        .bullets {{ margin:0; padding-left:12px; text-align:left; }}
        .bullets.compact {{ padding-left:10px; }}
        .bullets li {{ margin:0; padding:0; }}
        .empty {{ color:#7b8794; }}

        .bottom-table {{ margin-top:0; }}
        .bottom-table th, .bottom-table td {{ border:1px solid {BORDER}; }}
        .bottom-table th {{ height:17px; background:{LIGHT_BG}; color:{TEXT}; text-align:left; font-size:8px; padding:2px 5px; }}
        .bottom-table td {{ height:118px; font-size:7.8px; line-height:1.25; vertical-align:top; padding:7px 7px; }}
      </style>
    </head>
    <body>
      <div class="sheet">
        <table class="top-table">
          <colgroup>
            <col style="width:310px">
            <col style="width:120px">
            <col style="width:130px">
            <col style="width:260px">
            <col style="width:260px">
          </colgroup>
          <tr><th class="green top-title" colspan="5">{title}</th></tr>
          <tr class="top-row">
            <td class="patient-box"><table>{patient_rows}</table></td>
            <td class="blank-head"></td>
            <td class="diag-label">Diagnóstico Nutricional</td>
            <td class="diag-text">{_html_bullet_list(plan.get('diagnostico_items', []), compact=True)}</td>
            <td class="logos-cell">{logos_html}</td>
          </tr>
        </table>

        <table class="plan-table">
          <colgroup>
            <col style="width:56px">
            <col span="7" style="width:125px">
            <col style="width:8px">
            <col style="width:141px">
          </colgroup>
          <thead>
            <tr>
              <th></th><th>DÍA 1</th><th>DÍA 2</th><th>DÍA 3</th><th>DÍA 4</th><th>DÍA 5</th><th>DÍA 6</th><th>DÍA 7</th><th class="gap-head"></th><th>Cantidades</th>
            </tr>
          </thead>
          <tbody>
            <tr class="meal-row row-desayuno">
              <th class="row-label">Desayuno</th>{day_cells('desayuno')}<td class="gap-cell"></td><td class="qty-cell">{_html_bullet_list(cantidades[:5], compact=True)}</td>
            </tr>
            <tr class="row-wide">
              <th class="row-label">1/2 mañana<br>1/2 tarde</th><td class="wide-cell" colspan="7">{_inline_text(plan.get('media_items', []))}</td><td class="gap-cell"></td><td class="qty-cell">{_html_bullet_list(cantidades[5:9], compact=True)}</td>
            </tr>
            <tr class="row-wide">
              <th class="row-label">Ensalada</th><td class="wide-cell" colspan="7">{_inline_text(plan.get('ensalada_items', []))}</td><td class="gap-cell"></td><td class="qty-cell">{_html_bullet_list(cantidades[9:14], compact=True)}</td>
            </tr>
            <tr class="meal-row row-almuerzo">
              <th class="row-label">Almuerzo</th>{day_cells('almuerzo')}<td class="gap-cell"></td><td class="qty-cell">—</td>
            </tr>
            <tr class="meal-row row-cena">
              <th class="row-label">Cena</th>{day_cells('cena')}<td class="gap-cell"></td><td class="qty-cell">—</td>
            </tr>
          </tbody>
        </table>

        <table class="bottom-table">
          <colgroup><col style="width:65%"><col style="width:35%"></colgroup>
          <tr><th>Recomendaciones</th><th>Consejos Claves para ti</th></tr>
          <tr><td>{_html_bullet_list(plan.get('recomendaciones_items', []), compact=True)}</td><td>{_html_bullet_list(plan.get('consejos_items', []), compact=True)}</td></tr>
        </table>
      </div>
    </body>
    </html>
    """
    return html


def show_plan_preview(plan_data: Dict[str, Any], height: int = 760):
    components.html(render_plan_html(plan_data, page=1), height=height, scrolling=True)



# PDF


def build_plan_pdf(plan_data: Dict[str, Any]) -> bytes:
    """Genera PDF usando una sola grilla de proporciones estables, similar a la plantilla de referencia."""
    plan = normalize_plan_for_render(plan_data)
    pac = plan.get("paciente", {})
    cab = plan.get("cabecera", {})

    page_w, page_h = landscape(A4)
    margin_x = 1.05 * cm
    margin_y = 0.58 * cm
    usable_w = page_w - 2 * margin_x

    # Proporciones fijas replicadas en HTML: label + 7 días + separación + cantidades.
    label_w = 1.36 * cm
    gap_w = 0.20 * cm
    qty_w = 3.45 * cm
    day_w = (usable_w - label_w - gap_w - qty_w) / 7

    # Cabecera: datos | aire | etiqueta diagnóstico | diagnóstico | logos
    patient_w = 7.45 * cm
    blank_w = 2.9 * cm
    diag_label_w = 3.15 * cm
    logos_w = 6.45 * cm
    diag_text_w = usable_w - patient_w - blank_w - diag_label_w - logos_w

    styles = getSampleStyleSheet()
    style_title = ParagraphStyle("plan_title_ref", parent=styles["BodyText"], fontSize=10.6, leading=11.2, textColor=colors.white, alignment=TA_CENTER, fontName="Helvetica-Bold")
    style_small = ParagraphStyle("plan_small_ref", parent=styles["BodyText"], fontSize=6.0, leading=6.8, textColor=colors.HexColor(TEXT), alignment=TA_CENTER)
    style_small_left = ParagraphStyle("plan_small_left_ref", parent=style_small, alignment=0)
    style_label = ParagraphStyle("plan_label_ref", parent=styles["BodyText"], fontSize=5.9, leading=6.5, textColor=colors.white, alignment=TA_CENTER, fontName="Helvetica-Bold")
    style_list = ParagraphStyle("plan_list_ref", parent=styles["BodyText"], fontSize=5.55, leading=6.25, textColor=colors.HexColor(TEXT), alignment=0)
    style_footer_title = ParagraphStyle("plan_footer_title_ref", parent=styles["BodyText"], fontSize=5.45, leading=6.0, textColor=colors.HexColor(TEXT), fontName="Helvetica-Bold")

    def p(txt, style=style_small):
        raw = str(txt if txt not in (None, "") else "—")
        return Paragraph(escape(raw).replace("\n", "<br/>").replace("&lt;br&gt;", "<br/>").replace("&lt;br/&gt;", "<br/>") , style)

    def bullets(items, style=style_list, bullet=True):
        clean = [str(x).strip() for x in (items or []) if str(x).strip()]
        if not clean:
            return p("—", style_small)
        prefix = "• " if bullet else ""
        return Paragraph("<br/>".join(prefix + escape(x) for x in clean), style)

    def inline(items):
        clean = [str(x).strip() for x in (items or []) if str(x).strip()]
        if not clean:
            return p("—", style_small)
        return Paragraph(escape(" · ".join(clean)), style_small)

    def data_uri_to_image(data_uri: str, max_w: float = 1.85 * cm, max_h: float = 0.92 * cm):
        if not data_uri:
            return None
        try:
            if "," in data_uri:
                data_uri = data_uri.split(",", 1)[1]
            raw = base64.b64decode(data_uri)
            img = Image(io.BytesIO(raw))
            iw, ih = img.imageWidth, img.imageHeight
            if not iw or not ih:
                return None
            scale = min(max_w / iw, max_h / ih, 1)
            img.drawWidth = iw * scale
            img.drawHeight = ih * scale
            return img
        except Exception:
            return None

    def logos_flowable():
        logos = plan.get("logos") or {}
        imgs = []
        for key in ("dueno", "empresa"):
            img = data_uri_to_image(logos.get(key))
            if img:
                imgs.append(img)
        if not imgs:
            return Paragraph("", style_small)
        col_w = logos_w / len(imgs)
        t = Table([imgs], colWidths=[col_w] * len(imgs), hAlign="CENTER")
        t.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 1),
            ("RIGHTPADDING", (0, 0), (-1, -1), 1),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        return t

    def patient_table():
        rows = [
            [p("DNI", style_label), p(pac.get("dni") or "—", style_small)],
            [p("Nombres", style_label), p(pac.get("nombres") or "—", style_small)],
            [p("Apellidos", style_label), p(pac.get("apellidos") or "—", style_small)],
            [p("Objetivo", style_label), p(cab.get("objetivo") or "—", style_small)],
            [p("Alergias", style_label), p(cab.get("alergias") or "—", style_small)],
            [p("Intolerancias", style_label), p(cab.get("intolerancias") or "—", style_small)],
        ]
        t = Table(rows, colWidths=[1.85 * cm, patient_w - 1.85 * cm], rowHeights=[0.30 * cm] * 6)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor(PRIMARY)),
            ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor(BORDER)),
            ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor(BORDER)),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 1),
            ("RIGHTPADDING", (0, 0), (-1, -1), 1),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        return t

    def header_table():
        rows = [
            [p(cab.get("titulo", "PLAN DE ALIMENTACIÓN"), style_title), "", "", "", ""],
            [patient_table(), "", p("Diagnóstico Nutricional", style_label), bullets(plan.get("diagnostico_items", []), style_list), logos_flowable()],
        ]
        t = Table(rows, colWidths=[patient_w, blank_w, diag_label_w, diag_text_w, logos_w], rowHeights=[0.52 * cm, 1.82 * cm])
        t.setStyle(TableStyle([
            ("SPAN", (0, 0), (4, 0)),
            ("BACKGROUND", (0, 0), (4, 0), colors.HexColor(PRIMARY)),
            ("BACKGROUND", (2, 1), (2, 1), colors.HexColor(PRIMARY)),
            ("BOX", (0, 0), (4, 0), 0.45, colors.HexColor(BORDER)),
            ("BOX", (0, 1), (0, 1), 0.45, colors.HexColor(BORDER)),
            ("BOX", (2, 1), (3, 1), 0.45, colors.HexColor(BORDER)),
            ("BOX", (4, 1), (4, 1), 0.0, colors.white),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (3, 1), (3, 1), 4),
            ("RIGHTPADDING", (3, 1), (3, 1), 4),
        ]))
        return t

    col_widths = [label_w] + [day_w] * 7 + [gap_w, qty_w]
    cantidades = plan.get("cantidades_items", [])

    def main_table():
        data = []
        data.append(["", "DÍA 1", "DÍA 2", "DÍA 3", "DÍA 4", "DÍA 5", "DÍA 6", "DÍA 7", "", "Cantidades"])
        data.append([p("Desayuno", style_label)] + [p(plan["dias"].get(f"dia_{i}", {}).get("desayuno") or "—", style_small) for i in range(1, 8)] + ["", bullets(cantidades[:5], style_small)])
        data.append([p("1/2 mañana<br/>1/2 tarde", style_label), inline(plan.get("media_items", [])), "", "", "", "", "", "", "", bullets(cantidades[5:9], style_small)])
        data.append([p("Ensalada", style_label), inline(plan.get("ensalada_items", [])), "", "", "", "", "", "", "", bullets(cantidades[9:14], style_small)])
        data.append([p("Almuerzo", style_label)] + [p(plan["dias"].get(f"dia_{i}", {}).get("almuerzo") or "—", style_small) for i in range(1, 8)] + ["", p("—", style_small)])
        data.append([p("Cena", style_label)] + [p(plan["dias"].get(f"dia_{i}", {}).get("cena") or "—", style_small) for i in range(1, 8)] + ["", p("—", style_small)])

        t = Table(data, colWidths=col_widths, rowHeights=[0.42 * cm, 2.05 * cm, 0.68 * cm, 0.68 * cm, 2.25 * cm, 2.25 * cm], repeatRows=1)
        stl = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(PRIMARY)),
            ("BACKGROUND", (0, 1), (0, -1), colors.HexColor(PRIMARY)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 5.6),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (7, -1), 0.45, colors.HexColor(BORDER)),
            ("GRID", (9, 0), (9, -1), 0.45, colors.HexColor(BORDER)),
            ("BACKGROUND", (8, 0), (8, -1), colors.white),
            ("LINEBEFORE", (8, 0), (8, -1), 0, colors.white),
            ("LINEAFTER", (8, 0), (8, -1), 0, colors.white),
            ("SPAN", (1, 2), (7, 2)),
            ("SPAN", (1, 3), (7, 3)),
            ("LEFTPADDING", (0, 0), (-1, -1), 1.4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 1.4),
            ("TOPPADDING", (0, 0), (-1, -1), 2.2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
            ("TOPPADDING", (0, 0), (-1, 0), 1),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
        ]
        t.setStyle(TableStyle(stl))
        return t

    def bottom_table():
        rec_w = usable_w * 0.65
        con_w = usable_w - rec_w
        t = Table([
            [p("Recomendaciones", style_footer_title), p("Consejos Claves para ti", style_footer_title)],
            [bullets(plan.get("recomendaciones_items", []), style_list), bullets(plan.get("consejos_items", []), style_list)],
        ], colWidths=[rec_w, con_w], rowHeights=[0.36 * cm, 2.65 * cm])
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor(BORDER)),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(LIGHT_BG)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2.4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2.4),
            ("TOPPADDING", (0, 0), (-1, -1), 1.4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4),
        ]))
        return t

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=margin_x,
        rightMargin=margin_x,
        topMargin=margin_y,
        bottomMargin=margin_y,
    )

    story = [
        header_table(),
        Spacer(1, 0.06 * cm),
        main_table(),
        Spacer(1, 0.05 * cm),
        bottom_table(),
    ]
    doc.build(story)
    buffer.seek(0)
    return buffer.read()



# EMAIL


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