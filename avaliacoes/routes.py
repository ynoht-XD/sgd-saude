# sgd/avaliacoes/routes.py
from __future__ import annotations

import json
import sqlite3
import io
from datetime import datetime

from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    session,
    abort,
    send_file,
)

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from . import avaliacoes_bp
from db import conectar_db


# ============================================================
# TIPOS DE AVALIAÇÃO
# ============================================================

TIPOS_AVALIACAO = {
    "anamnese": "Anamnese / Avaliação Clínica",
    "avaliacao_social": "Avaliação Social",
    "avaliacao_enfermagem": "Avaliação de Enfermagem",
    "terapia_ocupacional": "Terapia Ocupacional",
    "psicologia_infantil": "Avaliação Psicológica Infantil",
    "fonoaudiologia_infantil": "Fonoaudiologia Infantil",
}

FORM_ROUTES = {
    "anamnese": "avaliacoes.tela_anamnese",
    "avaliacao_social": "avaliacoes.tela_social",
    "avaliacao_enfermagem": "avaliacoes.tela_enfermagem",
    "terapia_ocupacional": "avaliacoes.tela_terapia_ocupacional",
    "psicologia_infantil": "avaliacoes.tela_psicologia_infantil",
    "fonoaudiologia_infantil": "avaliacoes.tela_fonoaudiologia_infantil",
}


# ============================================================
# HELPERS
# ============================================================

def labelize(chave: str) -> str:
    return (
        chave.replace("_", " ")
             .replace("obs", "observações")
             .replace("cpf", "CPF")
             .replace("cns", "CNS")
             .capitalize()
    )

def valor_humano(v):
    if v in (None, "", "0"):
        return None
    if v == "1":
        return "Sim"
    if v == "sim":
        return "Sim"
    if v == "nao":
        return "Não"
    return str(v)


def montar_itens_visualizacao(dados: dict) -> list[dict]:
    itens = []
    for chave, valor in dados.items():
        val = valor_humano(valor)
        if not val:
            continue
        itens.append({
            "label": labelize(chave),
            "valor": val
        })
    return itens


# ============================================================
# API · AUTOCOMPLETE PACIENTES
# ============================================================

@avaliacoes_bp.route("/api/pacientes")
def api_buscar_pacientes():
    q = (request.args.get("q") or "").strip()
    if len(q) < 3:
        return jsonify({"items": []})

    conn = conectar_db()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT id, nome, prontuario
        FROM pacientes
        WHERE nome LIKE ?
        ORDER BY nome
        LIMIT 20
    """, (f"%{q}%",))

    return jsonify({
        "items": [
            {
                "id": r["id"],
                "nome": r["nome"],
                "prontuario": r["prontuario"],
                "label": f'{r["nome"]} · Pront: {r["prontuario"]}'
            }
            for r in cur.fetchall()
        ]
    })


# ============================================================
# HUB / LISTAGEM
# ============================================================

@avaliacoes_bp.route("/")
def index():
    conn = conectar_db()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT id, tipo, paciente_nome, paciente_prontuario,
               usuario_nome, usuario_cbo, criado_em
        FROM avaliacoes
        ORDER BY criado_em DESC
        LIMIT 500
    """)

    return render_template(
        "avaliacoes.html",
        avaliacoes=cur.fetchall(),
        tipos=TIPOS_AVALIACAO
    )


@avaliacoes_bp.route("/lista")
def lista():
    return index()


# ============================================================
# NOVA AVALIAÇÃO
# ============================================================

@avaliacoes_bp.route("/nova", methods=["POST"])
def nova():
    tipo = request.form.get("tipo")
    if tipo not in TIPOS_AVALIACAO:
        flash("Tipo inválido", "danger")
        return redirect(url_for("avaliacoes.index"))

    paciente_nome = (request.form.get("paciente_nome") or "").strip()
    if not paciente_nome:
        flash("Informe o paciente", "warning")
        return redirect(url_for("avaliacoes.index"))

    usuario_id = session.get("user_id")
    if not usuario_id:
        flash("Sessão expirada", "danger")
        return redirect(url_for("auth.login"))

    dados = request.form.to_dict(flat=True)
    for k in ("tipo", "paciente_nome", "paciente_id",
              "paciente_prontuario", "paciente_cpf"):
        dados.pop(k, None)

    conn = conectar_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO avaliacoes (
            tipo, paciente_nome, paciente_prontuario, paciente_cpf,
            usuario_id, usuario_nome, usuario_cbo,
            dados_json, criado_em
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        tipo,
        paciente_nome,
        request.form.get("paciente_prontuario"),
        request.form.get("paciente_cpf"),
        usuario_id,
        session.get("nome"),
        session.get("cbo"),
        json.dumps(dados, ensure_ascii=False),
        datetime.now().isoformat(timespec="seconds")
    ))

    conn.commit()
    flash("Avaliação registrada com sucesso ✅", "success")
    return redirect(url_for("avaliacoes.lista"))


# ============================================================
# VISUALIZAR
# ============================================================

@avaliacoes_bp.route("/<int:id>")
def visualizar(id: int):
    conn = conectar_db()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM avaliacoes WHERE id = ?", (id,))
    av = cur.fetchone()
    if not av:
        abort(404)

    dados = json.loads(av["dados_json"] or "{}")

    return render_template(
        "avaliacao_visualizar.html",
        avaliacao={
            **dict(av),
            "titulo": TIPOS_AVALIACAO.get(av["tipo"], av["tipo"]),
            "itens": montar_itens_visualizacao(dados)
        }
    )


# ============================================================
# PDF PROFISSIONAL
# ============================================================

@avaliacoes_bp.route("/<int:id>/pdf")
def imprimir_pdf(id: int):
    conn = conectar_db()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM avaliacoes WHERE id = ?", (id,))
    av = cur.fetchone()
    if not av:
        abort(404)

    dados = json.loads(av["dados_json"] or "{}")
    itens = montar_itens_visualizacao(dados)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    y = h - 50

    # Cabeçalho
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, "AVALIAÇÃO CLÍNICA")
    y -= 18

    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Tipo: {TIPOS_AVALIACAO.get(av['tipo'])}")
    y -= 14
    c.drawString(40, y, f"Paciente: {av['paciente_nome']}")
    y -= 14
    c.drawString(40, y, f"Data: {av['criado_em']}")
    y -= 14
    c.drawString(40, y, f"Profissional: {av['usuario_nome']} ({av['usuario_cbo']})")
    y -= 20

    # Corpo
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "DADOS DA AVALIAÇÃO")
    y -= 16
    c.setFont("Helvetica", 10)

    for item in itens:
        if y < 60:
            c.showPage()
            y = h - 50
            c.setFont("Helvetica", 10)

        c.drawString(40, y, f"{item['label']}:")
        y -= 12
        c.drawString(60, y, item["valor"])
        y -= 16

    # Rodapé
    y -= 30
    c.line(40, y, 260, y)
    c.drawString(40, y - 12, "Assinatura do profissional")

    c.showPage()
    c.save()
    buf.seek(0)

    return send_file(
        buf,
        mimetype="application/pdf",
        download_name=f"avaliacao_{id}.pdf",
        as_attachment=False
    )


# ============================================================
# TELAS
# ============================================================

@avaliacoes_bp.route("/anamnese")
def tela_anamnese():
    return render_template("anamnese.html", tipos=TIPOS_AVALIACAO)

@avaliacoes_bp.route("/social")
def tela_social():
    return render_template("social.html", tipos=TIPOS_AVALIACAO)

@avaliacoes_bp.route("/enfermagem")
def tela_enfermagem():
    return render_template("enfermagem.html", tipos=TIPOS_AVALIACAO)

@avaliacoes_bp.route("/terapia-ocupacional")
def tela_terapia_ocupacional():
    return render_template("terapia_ocupacional.html", tipos=TIPOS_AVALIACAO)

@avaliacoes_bp.route("/psicologia-infantil")
def tela_psicologia_infantil():
    return render_template("psicologia_infantil.html", tipos=TIPOS_AVALIACAO)

@avaliacoes_bp.route("/fonoaudiologia-infantil")
def tela_fonoaudiologia_infantil():
    return render_template("fonoaudiologia_infantil.html", tipos=TIPOS_AVALIACAO)
