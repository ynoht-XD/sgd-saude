from __future__ import annotations

import json
import io
import re
from datetime import datetime

from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    session,
    send_file,
)

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from . import avaliacoes_bp
from db import conectar_db


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
# HELPERS · POSTGRES
# ============================================================

def _row_to_dict(cur, row):
    cols = [d[0] for d in cur.description]
    return {cols[i]: row[i] for i in range(len(cols))}


def _rows_to_dicts(cur, rows):
    return [_row_to_dict(cur, r) for r in rows or []]


def _safe(v):
    return "" if v is None else str(v).strip()


def _only_digits(v):
    return re.sub(r"\D+", "", v or "")


def has_table(conn, table_name: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
              FROM information_schema.tables
             WHERE table_schema = 'public'
               AND table_name = %s
        )
        """,
        (table_name,),
    )
    return bool(cur.fetchone()[0])


def has_column(conn, table_name: str, column_name: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = %s
               AND column_name = %s
        )
        """,
        (table_name, column_name),
    )
    return bool(cur.fetchone()[0])


def table_columns(conn, table_name: str) -> set[str]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = %s
        """,
        (table_name,),
    )
    return {r[0] for r in cur.fetchall() or []}


def ensure_avaliacoes_schema(conn):
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS avaliacoes (
            id SERIAL PRIMARY KEY,
            tipo TEXT NOT NULL,

            paciente_id INTEGER,
            paciente_nome TEXT,
            paciente_prontuario TEXT,
            paciente_cpf TEXT,

            usuario_id INTEGER,
            usuario_nome TEXT,
            usuario_cbo TEXT,

            dados_json TEXT NOT NULL,
            criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    if not has_column(conn, "avaliacoes", "paciente_id"):
        cur.execute("ALTER TABLE avaliacoes ADD COLUMN paciente_id INTEGER")

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_avaliacoes_tipo
        ON avaliacoes (tipo)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_avaliacoes_criado
        ON avaliacoes (criado_em)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_avaliacoes_paciente
        ON avaliacoes (paciente_id)
    """)

    conn.commit()


def resolver_usuario_logado(conn):
    uid = (
        session.get("user_id")
        or session.get("usuario_id")
        or session.get("id")
    )

    nome = session.get("nome") or session.get("usuario_nome") or ""
    cbo = session.get("cbo") or session.get("usuario_cbo") or ""

    if uid and has_table(conn, "usuarios"):
        cols = table_columns(conn, "usuarios")
        nome_expr = "COALESCE(nome, '')" if "nome" in cols else "''"
        cbo_expr = "COALESCE(cbo, '')" if "cbo" in cols else "''"

        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT id, {nome_expr} AS nome, {cbo_expr} AS cbo
              FROM usuarios
             WHERE id = %s
             LIMIT 1
            """,
            (int(uid),),
        )
        r = cur.fetchone()
        if r:
            return {
                "id": r[0],
                "nome": r[1] or nome or "",
                "cbo": r[2] or cbo or "",
            }

    return {
        "id": int(uid) if str(uid or "").isdigit() else None,
        "nome": nome or "",
        "cbo": cbo or "",
    }


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
    if v in ("1", "sim", True):
        return "Sim"
    if v in ("nao", "não", False):
        return "Não"
    return str(v)


def montar_itens_visualizacao(dados: dict) -> list[dict]:
    itens = []
    for chave, valor in dados.items():
        val = valor_humano(valor)
        if not val:
            continue
        itens.append({"label": labelize(chave), "valor": val})
    return itens


def quebrar_texto_pdf(texto: str, limite: int = 95):
    palavras = (texto or "").split()
    if not palavras:
        return [""]

    linhas = []
    atual = ""

    for palavra in palavras:
        teste = f"{atual} {palavra}".strip()
        if len(teste) <= limite:
            atual = teste
        else:
            if atual:
                linhas.append(atual)
            atual = palavra

    if atual:
        linhas.append(atual)

    return linhas


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
        if not has_table(conn, "pacientes"):
            return jsonify({"items": []})

        cols = table_columns(conn, "pacientes")
        pront_expr = "COALESCE(prontuario, '')" if "prontuario" in cols else "''"
        cpf_expr = "COALESCE(cpf, '')" if "cpf" in cols else "''"

        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT
                id,
                COALESCE(nome, '') AS nome,
                {pront_expr} AS prontuario,
                {cpf_expr} AS cpf
            FROM pacientes
            WHERE
                nome ILIKE %s
                OR REGEXP_REPLACE(COALESCE(cpf::text, ''), '\\D', '', 'g') ILIKE %s
                OR COALESCE(prontuario::text, '') ILIKE %s
            ORDER BY nome
            LIMIT 20
            """,
            (f"%{q}%", f"%{_only_digits(q)}%", f"%{q}%"),
        )

        rows = _rows_to_dicts(cur, cur.fetchall())

        return jsonify({
            "items": [
                {
                    "id": r.get("id"),
                    "nome": r.get("nome") or "",
                    "prontuario": r.get("prontuario") or "",
                    "cpf": r.get("cpf") or "",
                    "label": f'{r.get("nome") or ""} · Pront: {r.get("prontuario") or "-"}'
                }
                for r in rows
            ]
        })
    finally:
        conn.close()


# ============================================================
# LISTAGEM
# ============================================================

@avaliacoes_bp.route("/lista")
def lista():
    conn = conectar_db()
    try:
        ensure_avaliacoes_schema(conn)

        busca = (request.args.get("q") or "").strip()
        tipo = (request.args.get("tipo") or "").strip()

        sql = """
            SELECT
                id,
                tipo,
                paciente_id,
                paciente_nome,
                paciente_prontuario,
                paciente_cpf,
                usuario_nome,
                usuario_cbo,
                criado_em::text AS criado_em
            FROM avaliacoes
            WHERE 1=1
        """
        params = []

        if busca:
            like = f"%{busca}%"
            digits = f"%{_only_digits(busca)}%"

            sql += """
                AND (
                    paciente_nome ILIKE %s
                    OR paciente_prontuario ILIKE %s
                    OR paciente_cpf ILIKE %s
                    OR REGEXP_REPLACE(COALESCE(paciente_cpf, ''), '\\D', '', 'g') ILIKE %s
                    OR usuario_nome ILIKE %s
                )
            """
            params.extend([like, like, like, digits, like])

        if tipo and tipo in TIPOS_AVALIACAO:
            sql += " AND tipo = %s "
            params.append(tipo)

        sql += " ORDER BY id DESC "

        cur = conn.cursor()
        cur.execute(sql, params)
        avaliacoes = _rows_to_dicts(cur, cur.fetchall())

        return render_template(
            "avaliacoes.html",
            avaliacoes=avaliacoes,
            busca=busca,
            tipo=tipo,
            tipos=TIPOS_AVALIACAO,
        )
    finally:
        conn.close()


@avaliacoes_bp.route("/")
def index():
    return redirect(url_for("avaliacoes.lista"))


# ============================================================
# VISUALIZAÇÃO / PDF
# ============================================================

@avaliacoes_bp.route("/visualizar/<int:id>", endpoint="visualizar")
def visualizar(id):
    conn = conectar_db()
    try:
        ensure_avaliacoes_schema(conn)

        cur = conn.cursor()
        cur.execute("SELECT * FROM avaliacoes WHERE id = %s", (id,))
        row = cur.fetchone()

        if not row:
            flash("Avaliação não encontrada.", "warning")
            return redirect(url_for("avaliacoes.lista"))

        av = _row_to_dict(cur, row)

        try:
            dados = json.loads(av.get("dados_json") or "{}")
        except Exception:
            dados = {}

        itens = montar_itens_visualizacao(dados)

        return render_template(
            "avaliacao_visualizar.html",
            avaliacao=av,
            tipo_label=TIPOS_AVALIACAO.get(av.get("tipo"), av.get("tipo")),
            itens=itens,
            dados=dados,
        )
    finally:
        conn.close()


@avaliacoes_bp.route("/pdf/<int:id>", endpoint="exportar_pdf")
def exportar_pdf(id):
    conn = conectar_db()
    try:
        ensure_avaliacoes_schema(conn)

        cur = conn.cursor()
        cur.execute("SELECT * FROM avaliacoes WHERE id = %s", (id,))
        row = cur.fetchone()

        if not row:
            flash("Avaliação não encontrada.", "warning")
            return redirect(url_for("avaliacoes.lista"))

        av = _row_to_dict(cur, row)

        try:
            dados = json.loads(av.get("dados_json") or "{}")
        except Exception:
            dados = {}

        itens = montar_itens_visualizacao(dados)

        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        largura, altura = A4

        margem_x = 40
        y = altura - 40

        def nova_pagina():
            nonlocal y
            pdf.showPage()
            y = altura - 40

        pdf.setTitle(f"Avaliacao_{id}")

        pdf.setFont("Helvetica-Bold", 15)
        pdf.drawString(margem_x, y, "Avaliação")
        y -= 24

        pdf.setFont("Helvetica", 10)
        pdf.drawString(margem_x, y, f"Tipo: {TIPOS_AVALIACAO.get(av.get('tipo'), av.get('tipo'))}")
        y -= 16
        pdf.drawString(margem_x, y, f"Paciente: {av.get('paciente_nome') or '-'}")
        y -= 16
        pdf.drawString(margem_x, y, f"Prontuário: {av.get('paciente_prontuario') or '-'}")
        y -= 16
        pdf.drawString(margem_x, y, f"CPF: {av.get('paciente_cpf') or '-'}")
        y -= 16
        pdf.drawString(margem_x, y, f"Profissional: {av.get('usuario_nome') or '-'}")
        y -= 16
        pdf.drawString(margem_x, y, f"CBO: {av.get('usuario_cbo') or '-'}")
        y -= 16
        pdf.drawString(margem_x, y, f"Criado em: {av.get('criado_em') or '-'}")
        y -= 28

        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(margem_x, y, "Dados da avaliação")
        y -= 20

        pdf.setFont("Helvetica", 10)

        for item in itens:
            texto = f"{item['label']}: {item['valor']}"
            linhas = quebrar_texto_pdf(texto, 95)

            for linha in linhas:
                if y < 50:
                    nova_pagina()
                    pdf.setFont("Helvetica", 10)

                pdf.drawString(margem_x, y, linha)
                y -= 14

            y -= 4

        pdf.save()
        buffer.seek(0)

        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"avaliacao_{id}.pdf",
            mimetype="application/pdf"
        )
    finally:
        conn.close()


# ============================================================
# NOVA AVALIAÇÃO
# ============================================================

@avaliacoes_bp.route("/nova", methods=["POST"])
def nova():
    tipo = request.form.get("tipo")

    if tipo not in TIPOS_AVALIACAO:
        flash("Tipo inválido.", "danger")
        return redirect(url_for("avaliacoes.index"))

    paciente_nome = (request.form.get("paciente_nome") or "").strip()

    if not paciente_nome:
        flash("Informe o paciente.", "warning")
        return redirect(url_for("avaliacoes.index"))

    conn = conectar_db()
    try:
        ensure_avaliacoes_schema(conn)

        usuario = resolver_usuario_logado(conn)
        usuario_id = usuario.get("id")

        if not usuario_id:
            flash("Sessão expirada.", "danger")
            return redirect(url_for("auth.login"))

        dados = request.form.to_dict(flat=True)

        for k in (
            "tipo",
            "paciente_id",
            "paciente_nome",
            "paciente_prontuario",
            "paciente_cpf",
        ):
            dados.pop(k, None)

        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO avaliacoes (
                tipo,
                paciente_id,
                paciente_nome,
                paciente_prontuario,
                paciente_cpf,
                usuario_id,
                usuario_nome,
                usuario_cbo,
                dados_json,
                criado_em
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                tipo,
                int(request.form.get("paciente_id")) if str(request.form.get("paciente_id") or "").isdigit() else None,
                paciente_nome,
                (request.form.get("paciente_prontuario") or "").strip(),
                (request.form.get("paciente_cpf") or "").strip(),
                usuario_id,
                usuario.get("nome") or "",
                usuario.get("cbo") or "",
                json.dumps(dados, ensure_ascii=False),
                datetime.now(),
            ),
        )

        avaliacao_id = cur.fetchone()[0]
        conn.commit()

        flash("Avaliação registrada com sucesso ✅", "success")
        return redirect(url_for("avaliacoes.visualizar", id=avaliacao_id))

    except Exception as e:
        conn.rollback()
        flash(f"Erro ao registrar avaliação: {e}", "danger")
        return redirect(url_for("avaliacoes.index"))

    finally:
        conn.close()


# ============================================================
# TELAS
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