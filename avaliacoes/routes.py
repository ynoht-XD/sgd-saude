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
# SCHEMA · AVALIACOES
# ============================================================

def ensure_avaliacoes_schema(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS avaliacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,

            paciente_nome TEXT,
            paciente_prontuario TEXT,
            paciente_cpf TEXT,

            usuario_id INTEGER,
            usuario_nome TEXT,
            usuario_cbo TEXT,

            dados_json TEXT NOT NULL,
            criado_em TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_avaliacoes_tipo
        ON avaliacoes (tipo)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_avaliacoes_criado
        ON avaliacoes (criado_em)
    """)
    conn.commit()


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
    if v in ("1", "sim"):
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
    try:
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
    finally:
        conn.close()


# ============================================================
# HUB / LISTAGEM
# ============================================================

@avaliacoes_bp.route("/")
def index():
    conn = conectar_db()
    try:
        conn.row_factory = sqlite3.Row
        ensure_avaliacoes_schema(conn)

        cur = conn.cursor()
        cur.execute("""
            SELECT id, tipo, paciente_nome, paciente_prontuario,
                   usuario_nome, usuario_cbo, criado_em
            FROM avaliacoes
            ORDER BY criado_em DESC
            LIMIT 500
        """)

        cards = [
            {
                "key": k,
                "label": v,
                "route": FORM_ROUTES.get(k)
            }
            for k, v in TIPOS_AVALIACAO.items()
        ]

        return render_template(
            "avaliacoes.html",
            avaliacoes=cur.fetchall(),
            tipos=TIPOS_AVALIACAO,
            cards=cards
        )
    finally:
        conn.close()


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
    try:
        ensure_avaliacoes_schema(conn)
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
    finally:
        conn.close()


# ============================================================
# TELAS (ENDPOINTS EXPLÍCITOS)
# ============================================================

@avaliacoes_bp.route("/anamnese", endpoint="tela_anamnese")
def tela_anamnese():
    return render_template("anamnese.html", tipos=TIPOS_AVALIACAO)


@avaliacoes_bp.route("/social", endpoint="tela_social")
def tela_social():
    return render_template("social.html", tipos=TIPOS_AVALIACAO)


@avaliacoes_bp.route("/enfermagem", endpoint="tela_enfermagem")
def tela_enfermagem():
    return render_template("enfermagem.html", tipos=TIPOS_AVALIACAO)


@avaliacoes_bp.route("/terapia-ocupacional", endpoint="tela_terapia_ocupacional")
def tela_terapia_ocupacional():
    return render_template("terapia_ocupacional.html", tipos=TIPOS_AVALIACAO)


@avaliacoes_bp.route("/psicologia-infantil", endpoint="tela_psicologia_infantil")
def tela_psicologia_infantil():
    return render_template("psicologia_infantil.html", tipos=TIPOS_AVALIACAO)


@avaliacoes_bp.route("/fonoaudiologia-infantil", endpoint="tela_fonoaudiologia_infantil")
def tela_fonoaudiologia_infantil():
    return render_template("fonoaudiologia_infantil.html", tipos=TIPOS_AVALIACAO)
