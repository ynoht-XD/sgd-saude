# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import json
import re
from datetime import datetime
from typing import Any

from flask import send_file, request

from . import pacientes_bp
from .helpers import (
    fetch_pacientes_list,
    fetch_agendamentos_por_paciente,
    get_primeiro_agendamento_por_paciente,
    ensure_pacientes_schema,
    get_conn,
    fetchone_dict,
    calc_idade,
    fmt,
    join_addr,
    tags_human,
)


# =============================================================================
# HELPERS DE EXPORTAÇÃO
# =============================================================================

def export_header_order() -> list[str]:
    """
    Ordem preferida das colunas no arquivo.
    O que não existir no row vai ser ignorado; o resto entra no final.
    """
    return [
        "id",
        "prontuario",
        "nome",
        "nascimento",
        "idade",
        "sexo",
        "cpf",
        "cns",
        "telefone",
        "status",
        "mod",
        "cid",
        "cid2",

        # endereço
        "rua",
        "logradouro",
        "numero",
        "numero_casa",
        "bairro",
        "cep",
        "cidade",
        "municipio",
        "uf",

        # família
        "nome_mae",
        "mae",
        "nome_pai",
        "pai",

        # card / autosave
        "end_prontuario",
        "alergias",
        "aviso",
        "comorbidades_json",

        # derivados do agendamento
        "terapeuta",
        "cbo",
        "ag_dia",
        "ag_hora_ini",
        "ag_hora_fim",
        "ag_resumo",
    ]


def pretty_header(col: str) -> str:
    mapa = {
        "id": "ID",
        "prontuario": "Prontuário",
        "nome": "Nome",
        "nascimento": "Nascimento",
        "idade": "Idade",
        "sexo": "Sexo",
        "cpf": "CPF",
        "cns": "CNS",
        "telefone": "Telefone",
        "status": "Status",
        "mod": "Modalidade",
        "cid": "CID",
        "cid2": "CID 2",

        "rua": "Rua",
        "logradouro": "Logradouro",
        "numero": "Número",
        "numero_casa": "Número (casa)",
        "bairro": "Bairro",
        "cep": "CEP",
        "cidade": "Cidade",
        "municipio": "Município",
        "uf": "UF",

        "nome_mae": "Nome da mãe",
        "mae": "Mãe",
        "nome_pai": "Nome do pai",
        "pai": "Pai",

        "end_prontuario": "END (Prontuário físico)",
        "alergias": "Alergias",
        "aviso": "Aviso / Situação",
        "comorbidades_json": "Comorbidades (JSON)",

        "terapeuta": "Terapeuta(s)",
        "cbo": "CBO(s)",
        "ag_dia": "Agendamento (Dia)",
        "ag_hora_ini": "Agendamento (Início)",
        "ag_hora_fim": "Agendamento (Fim)",
        "ag_resumo": "Agendamento (Resumo)",
    }
    return mapa.get(col, col.replace("_", " ").strip().title())


def normalize_cell_value(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        try:
            return json.dumps(v, ensure_ascii=False)
        except Exception:
            return str(v)
    return str(v)


# =============================================================================
# EXPORT XLS/CSV
# =============================================================================

@pacientes_bp.route("/exportar_xls")
def exportar_xls():
    rows = fetch_pacientes_list(request.args)

    keys_all: set[str] = set()
    for r in rows:
        if isinstance(r, dict):
            keys_all.update(r.keys())

    preferred = export_header_order()
    cols = [c for c in preferred if c in keys_all]
    resto = sorted([c for c in keys_all if c not in cols])
    cols.extend(resto)

    headers = [pretty_header(c) for c in cols]

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font
        from openpyxl.utils import get_column_letter

        wb = Workbook()
        ws = wb.active
        ws.title = "Pacientes"

        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        for r in rows:
            ws.append([normalize_cell_value(r.get(c)) for c in cols])

        for idx, _col_name in enumerate(cols, start=1):
            letter = get_column_letter(idx)
            max_len = len(headers[idx - 1])
            for cell in ws[letter]:
                if cell.value is None:
                    continue
                max_len = max(max_len, len(str(cell.value)))
            ws.column_dimensions[letter].width = min(max_len + 2, 60)

        ws.freeze_panes = "A2"

        bio = io.BytesIO()
        wb.save(bio)
        bio.seek(0)

        filename = f"pacientes_full_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        return send_file(
            bio,
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    except ImportError:
        import csv

        bio_txt = io.StringIO()
        writer = csv.writer(bio_txt, delimiter=";")
        writer.writerow(headers)

        for r in rows:
            writer.writerow([normalize_cell_value(r.get(c)) for c in cols])

        data = io.BytesIO(bio_txt.getvalue().encode("utf-8-sig"))
        filename = f"pacientes_full_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        return send_file(
            data,
            as_attachment=True,
            download_name=filename,
            mimetype="text/csv"
        )


# =============================================================================
# PDF DO PRONTUÁRIO INDIVIDUAL
# =============================================================================

@pacientes_bp.route("/exportar_prontuario_pdf/<int:id>")
def exportar_prontuario_pdf(id: int):
    """
    Exporta PDF do prontuário individual do paciente.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import mm
        from reportlab.lib import colors
    except ImportError:
        return ("⚠️ Para exportar PDF, instale o pacote 'reportlab' (pip install reportlab).", 501)

    with get_conn() as conn:
        ensure_pacientes_schema(conn)

        cur = conn.cursor()
        cur.execute("SELECT * FROM pacientes WHERE id = %s LIMIT 1", (id,))
        row = fetchone_dict(cur)

    if not row:
        return ("Paciente não encontrado.", 404)

    p = dict(row)

    if not (p.get("telefone") or "").strip():
        p["telefone"] = (p.get("telefone1") or "").strip()
    if not (p.get("nome_mae") or "").strip():
        p["nome_mae"] = (p.get("mae") or "").strip()
    if not (p.get("nome_pai") or "").strip():
        p["nome_pai"] = (p.get("pai") or "").strip()

    if p.get("idade") is None:
        p["idade"] = calc_idade(p.get("nascimento"))

    ag_map = get_primeiro_agendamento_por_paciente()
    info_ag = ag_map.get((p.get("nome") or "").strip().upper(), {}) if p.get("nome") else {}

    terapeuta = (info_ag.get("terapeuta_str") or "").strip()
    cbo_str = (info_ag.get("cbo_str") or "").strip()
    ag_resumo = (info_ag.get("agenda_str") or "").strip()

    agds = fetch_agendamentos_por_paciente(p.get("nome") or "")
    agds_upcoming = agds.get("agds_upcoming", [])

    bio = io.BytesIO()
    c = canvas.Canvas(bio, pagesize=A4)
    W, H = A4

    margin = 14 * mm
    x0 = margin
    y = H - margin
    page_no = 1

    C_BORDER = colors.HexColor("#E5E7EB")
    C_SOFT = colors.HexColor("#F8FAFC")
    C_SOFT2 = colors.HexColor("#F1F5F9")
    C_TEXT = colors.HexColor("#0F172A")
    C_MUTED = colors.HexColor("#475569")

    def new_page():
        nonlocal y, page_no
        c.showPage()
        page_no += 1
        y = H - margin
        draw_header()

    def ensure_space(mm_needed: float):
        nonlocal y
        if y < margin + (mm_needed * mm):
            new_page()

    def wrap_text(text: str, max_w: float, font="Helvetica", size=10) -> list[str]:
        c.setFont(font, size)
        text = (text or "").strip()
        if not text:
            return ["—"]
        words = text.split()
        lines = []
        curw = words[0]
        for w in words[1:]:
            test = curw + " " + w
            if c.stringWidth(test, font, size) <= max_w:
                curw = test
            else:
                lines.append(curw)
                curw = w
        lines.append(curw)
        return lines

    def draw_header():
        nonlocal y
        c.setFillColor(C_TEXT)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(x0, y, "Prontuário do Paciente")
        c.setFont("Helvetica", 9)
        c.setFillColor(C_MUTED)
        c.drawRightString(W - margin, y, f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        y -= 7 * mm

        c.setFillColor(C_TEXT)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(x0, y, fmt(p.get("nome")))
        c.setFont("Helvetica", 9)
        c.setFillColor(C_MUTED)
        c.drawRightString(W - margin, y, f"Página {page_no}")
        y -= 6 * mm

        c.setStrokeColor(C_BORDER)
        c.setLineWidth(0.8)
        c.line(x0, y, W - margin, y)
        y -= 8 * mm

    def card_box(title: str, mm_h: float):
        nonlocal y
        ensure_space(mm_h + 10)
        w = W - 2 * margin
        h = mm_h * mm
        y_top = y

        c.setFillColor(C_SOFT)
        c.setStrokeColor(C_BORDER)
        c.setLineWidth(0.8)
        c.roundRect(x0, y_top - h, w, h, 10, stroke=1, fill=1)

        c.setFillColor(C_TEXT)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(x0 + 10, y_top - 16, title)

        y = y_top - 26
        return (x0 + 10, y, w - 20, h - 26)

    def draw_chip(x, y, label: str, value: Any, max_w: float):
        lab = (label or "").upper()
        val = fmt(value)
        text = f"{lab}: {val}"

        c.setFont("Helvetica", 9)
        w = min(max_w, c.stringWidth(text, "Helvetica", 9) + 16)

        c.setFillColor(C_SOFT2)
        c.setStrokeColor(C_BORDER)
        c.roundRect(x, y - 12, w, 16, 8, stroke=1, fill=1)

        c.setFillColor(C_TEXT)
        c.drawString(x + 8, y, text)
        return w + 6

    def draw_kv(x, y, label: str, value: Any, col_w: float):
        c.setFillColor(C_MUTED)
        c.setFont("Helvetica", 8)
        c.drawString(x, y, (label or "").upper())
        y2 = y - 4.2 * mm

        c.setFillColor(C_TEXT)
        lines = wrap_text(fmt(value), col_w, "Helvetica", 10)
        for ln in lines:
            c.setFont("Helvetica", 10)
            c.drawString(x, y2, ln)
            y2 -= 4.6 * mm

        return (y - y2) + (1.5 * mm)

    def draw_note_box(x, y, w, title: str, text: Any):
        c.setFillColor(C_SOFT2)
        c.setStrokeColor(C_BORDER)
        c.roundRect(x, y - 70, w, 70, 10, stroke=1, fill=1)

        c.setFillColor(C_TEXT)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x + 10, y - 16, title)

        c.setFillColor(C_TEXT)
        lines = wrap_text(fmt(text), w - 20, "Helvetica", 10)
        yy = y - 28
        for ln in lines[:6]:
            c.drawString(x + 10, yy, ln)
            yy -= 4.6 * mm
        if len(lines) > 6:
            c.setFont("Helvetica-Oblique", 9)
            c.setFillColor(C_MUTED)
            c.drawString(x + 10, yy, "… (texto cortado)")
        return 75

    draw_header()

    # 1) Identificação
    x, y_in, w_in, _ = card_box("Identificação", mm_h=56)

    col_gap = 12
    col_w = (w_in - col_gap) / 2
    left_x = x
    right_x = x + col_w + col_gap

    yy = y_in
    used = 0
    used += draw_chip(left_x, yy, "CPF", p.get("cpf"), col_w)
    used += draw_chip(left_x + used, yy, "CNS", p.get("cns"), col_w - used)

    used2 = 0
    used2 += draw_chip(right_x, yy, "Nascimento", p.get("nascimento"), col_w)
    used2 += draw_chip(right_x + used2, yy, "Idade", p.get("idade"), col_w - used2)

    yy -= 10 * mm
    h1 = draw_kv(left_x, yy, "Prontuário (código)", p.get("prontuario"), col_w)
    h2 = draw_kv(right_x, yy, "Sexo", p.get("sexo"), col_w)
    yy -= max(h1, h2)

    h1 = draw_kv(left_x, yy, "Telefone", p.get("telefone"), col_w)
    h2 = draw_kv(right_x, yy, "END (Prontuário físico)", p.get("end_prontuario"), col_w)
    yy -= max(h1, h2)

    y = (y_in - (56 * mm)) - 10

    # 2) Status e Classificação
    x, y_in, w_in, _ = card_box("Status e Classificação", mm_h=44)

    yy = y_in
    used = 0
    used += draw_chip(x, yy, "Status", p.get("status"), w_in)
    used += draw_chip(x + used, yy, "Modalidade", p.get("mod"), w_in - used)

    cid_combo = fmt(p.get("cid"))
    if (p.get("cid2") or "").strip():
        cid_combo = f"{cid_combo} | CID2: {fmt(p.get('cid2'))}"

    yy -= 10 * mm
    draw_kv(x, yy, "CID", cid_combo, w_in)

    y = (y_in - (44 * mm)) - 10

    # 3) Endereço e Família
    x, y_in, w_in, _ = card_box("Endereço e Família", mm_h=52)

    yy = y_in
    h1 = draw_kv(x, yy, "Endereço", join_addr(p), w_in)
    yy -= h1

    col_gap = 12
    col_w = (w_in - col_gap) / 2
    left_x = x
    right_x = x + col_w + col_gap

    h1 = draw_kv(left_x, yy, "Nome da mãe", p.get("nome_mae"), col_w)
    h2 = draw_kv(right_x, yy, "Nome do pai", p.get("nome_pai"), col_w)
    yy -= max(h1, h2)

    y = (y_in - (52 * mm)) - 10

    # 4) Evolução / Observações
    x, y_in, w_in, _ = card_box("Evolução / Observações", mm_h=78)

    col_gap = 12
    col_w = (w_in - col_gap) / 2
    left_x = x
    right_x = x + col_w + col_gap
    yy = y_in + 6

    draw_note_box(left_x, yy, col_w, "Alergias", p.get("alergias"))
    draw_note_box(right_x, yy, col_w, "Aviso / Situação", p.get("aviso"))

    yy -= 78
    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(left_x, yy, "COMORBIDADES / PROJETOS")
    c.setFillColor(C_TEXT)
    c.setFont("Helvetica", 10)
    for ln in wrap_text(tags_human(p), w_in, "Helvetica", 10)[:2]:
        yy -= 5 * mm
        c.drawString(left_x, yy, ln)

    y = (y_in - (78 * mm)) - 10

    # 5) Agenda / Terapias
    x, y_in, w_in, _ = card_box("Agenda / Terapias", mm_h=60)

    yy = y_in
    if terapeuta:
        draw_chip(x, yy, "Terapeuta(s)", terapeuta, w_in)

    if cbo_str:
        yy -= 10 * mm
        draw_chip(x, yy, "CBO(s)", cbo_str, w_in)

    yy -= 12 * mm
    draw_kv(x, yy, "Resumo do agendamento", fmt(ag_resumo), w_in)

    y = (y_in - (60 * mm)) - 10

    # 6) Próximos agendamentos
    if agds_upcoming:
        x, y_in, w_in, _ = card_box("Próximos agendamentos", mm_h=80)
        yy = y_in

        c.setFont("Helvetica", 10)
        c.setFillColor(C_TEXT)

        max_items = 20
        count = 0
        for a in agds_upcoming:
            if count >= max_items:
                c.setFont("Helvetica-Oblique", 9)
                c.setFillColor(C_MUTED)
                c.drawString(x, yy, "… (lista cortada para manter o PDF leve)")
                yy -= 6 * mm
                break

            dia = fmt(a.get("dia_semana"))
            data_br = fmt(a.get("data_br"))
            hi = fmt(a.get("hora_ini"))
            hf = (a.get("hora_fim") or "").strip()
            faixa = f"{hi}–{hf}" if hf else hi
            prof = fmt(a.get("profissional"))

            linha = f"{dia} • {data_br} • {faixa} — {prof}"
            for ln in wrap_text(linha, w_in, "Helvetica", 10)[:2]:
                c.drawString(x, yy, ln)
                yy -= 5 * mm
            yy -= 1.5 * mm

            count += 1
            if yy < (y_in - (80 * mm) + 18):
                new_page()
                x, y_in, w_in, _ = card_box("Próximos agendamentos (continuação)", mm_h=80)
                yy = y_in

        y = (y_in - (80 * mm)) - 10

    c.showPage()
    c.save()
    bio.seek(0)

    nome_slug = re.sub(r"[^A-Za-z0-9]+", "_", (p.get("nome") or "paciente").strip()).strip("_")
    filename = f"prontuario_{nome_slug}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    return send_file(bio, as_attachment=True, download_name=filename, mimetype="application/pdf")