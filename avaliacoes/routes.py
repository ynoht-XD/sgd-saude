from __future__ import annotations

import json
import io
import re
from datetime import datetime

from flask import (
    render_template, request, redirect, url_for,
    flash, jsonify, session, send_file, abort
)

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from . import avaliacoes_bp
from db import conectar_db
from admin.modulos import require_permission

# Futuro motor de avaliações customizadas
try:
    from . import avalia_config  # noqa: F401
except Exception:
    avalia_config = None

try:
    from . import make_avaliacoes  # noqa: F401
except Exception:
    make_avaliacoes = None


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

def _val(row, key: str, index: int = 0, default=None):
    if not row:
        return default
    if isinstance(row, dict) or hasattr(row, "keys"):
        return dict(row).get(key, default)
    try:
        return row[index]
    except Exception:
        return default


def _row_to_dict(cur, row):
    if not row:
        return {}
    if isinstance(row, dict) or hasattr(row, "keys"):
        return dict(row)
    cols = [d[0] for d in cur.description]
    return {cols[i]: row[i] for i in range(len(cols))}


def _rows_to_dicts(cur, rows):
    return [_row_to_dict(cur, r) for r in rows or []]


def _safe(v):
    return "" if v is None else str(v).strip()


def _only_digits(v):
    return re.sub(r"\D+", "", v or "")


def _usuario_id_atual():
    return session.get("user_id") or session.get("usuario_id") or session.get("id")


def _clinica_id_atual(default=1):
    val = session.get("clinica_id") or session.get("clinic_id") or default
    try:
        return int(val) if val is not None else None
    except Exception:
        return default


def has_table(conn, table_name: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1
                  FROM information_schema.tables
                 WHERE table_schema = 'public'
                   AND table_name = %s
            ) AS existe
        """, (table_name,))
        return bool(_val(cur.fetchone(), "existe", 0, False))
    finally:
        cur.close()


def has_column(conn, table_name: str, column_name: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1
                  FROM information_schema.columns
                 WHERE table_schema = 'public'
                   AND table_name = %s
                   AND column_name = %s
            ) AS existe
        """, (table_name, column_name))
        return bool(_val(cur.fetchone(), "existe", 0, False))
    finally:
        cur.close()


def table_columns(conn, table_name: str) -> set[str]:
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = %s
        """, (table_name,))
        return {
            _val(r, "column_name", 0)
            for r in cur.fetchall() or []
            if _val(r, "column_name", 0)
        }
    finally:
        cur.close()


def ensure_column(conn, table_name: str, column_name: str, ddl_type: str):
    if has_column(conn, table_name, column_name):
        return

    cur = conn.cursor()
    try:
        cur.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {ddl_type}")
        conn.commit()
    finally:
        cur.close()


def _add_clinica_where(conn, table: str, alias: str, where: list[str], params: list, clinica_id=None):
    clinica_id = clinica_id or _clinica_id_atual()
    if clinica_id and has_column(conn, table, "clinica_id"):
        where.append(f"{alias}.clinica_id = %s")
        params.append(int(clinica_id))


def registrar_log(conn, acao: str, referencia_id=None, detalhes="", sucesso=True):
    try:
        if not has_table(conn, "logs"):
            return

        cols = table_columns(conn, "logs")

        campos = []
        valores = []
        params = []

        def add(campo, valor):
            if campo in cols:
                campos.append(campo)
                valores.append("%s")
                params.append(valor)

        add("usuario_id", _usuario_id_atual())
        add("clinica_id", _clinica_id_atual())
        add("modulo", "avaliacoes")
        add("acao", acao)
        add("referencia_id", str(referencia_id or ""))
        add("detalhes", detalhes or "")
        add("sucesso", sucesso)

        if "created_at" in cols:
            campos.append("created_at")
            valores.append("CURRENT_TIMESTAMP")
        elif "criado_em" in cols:
            campos.append("criado_em")
            valores.append("CURRENT_TIMESTAMP")

        if campos:
            cur = conn.cursor()
            try:
                cur.execute(
                    f"""
                    INSERT INTO logs ({", ".join(campos)})
                    VALUES ({", ".join(valores)})
                    """,
                    params,
                )
            finally:
                cur.close()

    except Exception as e:
        print(f"[AVALIAÇÕES][LOG] Falha ao registrar log: {e}")


def ensure_avaliacoes_schema(conn):
    cur = conn.cursor()

    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS avaliacoes (
                id SERIAL PRIMARY KEY,
                clinica_id INTEGER,
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
        conn.commit()
    finally:
        cur.close()

    ensure_column(conn, "avaliacoes", "clinica_id", "INTEGER")
    ensure_column(conn, "avaliacoes", "paciente_id", "INTEGER")
    ensure_column(conn, "avaliacoes", "paciente_nome", "TEXT")
    ensure_column(conn, "avaliacoes", "paciente_prontuario", "TEXT")
    ensure_column(conn, "avaliacoes", "paciente_cpf", "TEXT")
    ensure_column(conn, "avaliacoes", "usuario_id", "INTEGER")
    ensure_column(conn, "avaliacoes", "usuario_nome", "TEXT")
    ensure_column(conn, "avaliacoes", "usuario_cbo", "TEXT")
    ensure_column(conn, "avaliacoes", "dados_json", "TEXT")
    ensure_column(conn, "avaliacoes", "criado_em", "TIMESTAMP")

    cur = conn.cursor()
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_avaliacoes_clinica ON avaliacoes (clinica_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_avaliacoes_tipo ON avaliacoes (tipo)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_avaliacoes_criado ON avaliacoes (criado_em)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_avaliacoes_paciente ON avaliacoes (paciente_id)")
        conn.commit()
    finally:
        cur.close()


def resolver_usuario_logado(conn):
    uid = _usuario_id_atual()
    nome = session.get("nome") or session.get("usuario_nome") or ""
    cbo = session.get("cbo") or session.get("usuario_cbo") or ""

    if uid and has_table(conn, "usuarios"):
        cols = table_columns(conn, "usuarios")
        nome_expr = "COALESCE(nome, '')" if "nome" in cols else "''"
        cbo_expr = "COALESCE(cbo, '')" if "cbo" in cols else "''"

        where = ["id = %s"]
        params = [int(uid)]

        if "clinica_id" in cols:
            where.append("(clinica_id = %s OR clinica_id IS NULL)")
            params.append(_clinica_id_atual())

        cur = conn.cursor()
        try:
            cur.execute(f"""
                SELECT id, {nome_expr} AS nome, {cbo_expr} AS cbo
                  FROM usuarios
                 WHERE {" AND ".join(where)}
                 LIMIT 1
            """, params)
            r = cur.fetchone()

            if r:
                return {
                    "id": _val(r, "id", 0),
                    "nome": _val(r, "nome", 1, "") or nome or "",
                    "cbo": _val(r, "cbo", 2, "") or cbo or "",
                }
        finally:
            cur.close()

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
        if val:
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


def _buscar_avaliacao_por_id(conn, avaliacao_id: int):
    ensure_avaliacoes_schema(conn)

    where = ["id = %s"]
    params = [avaliacao_id]
    _add_clinica_where(conn, "avaliacoes", "avaliacoes", where, params)

    cur = conn.cursor()
    try:
        cur.execute(f"""
            SELECT *
            FROM avaliacoes
            WHERE {" AND ".join(where)}
            LIMIT 1
        """, params)
        row = cur.fetchone()
        return _row_to_dict(cur, row) if row else None
    finally:
        cur.close()


# ============================================================
# API · AUTOCOMPLETE PACIENTES
# ============================================================

@avaliacoes_bp.route("/api/pacientes")
@require_permission("avaliacoes", "ver")
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

        where = ["""
            (
                nome ILIKE %s
                OR REGEXP_REPLACE(COALESCE(cpf::text, ''), '\\D', '', 'g') ILIKE %s
                OR COALESCE(prontuario::text, '') ILIKE %s
            )
        """]
        params = [f"%{q}%", f"%{_only_digits(q)}%", f"%{q}%"]

        _add_clinica_where(conn, "pacientes", "pacientes", where, params)

        cur = conn.cursor()
        try:
            cur.execute(f"""
                SELECT
                    id,
                    COALESCE(nome, '') AS nome,
                    {pront_expr} AS prontuario,
                    {cpf_expr} AS cpf
                FROM pacientes
                WHERE {" AND ".join(where)}
                ORDER BY nome
                LIMIT 20
            """, params)
            rows = _rows_to_dicts(cur, cur.fetchall())
        finally:
            cur.close()

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
@require_permission("avaliacoes", "ver")
def lista():
    conn = conectar_db()
    try:
        ensure_avaliacoes_schema(conn)

        busca = (request.args.get("q") or "").strip()
        tipo = (request.args.get("tipo") or "").strip()

        where = ["1=1"]
        params = []

        _add_clinica_where(conn, "avaliacoes", "avaliacoes", where, params)

        if busca:
            like = f"%{busca}%"
            digits = f"%{_only_digits(busca)}%"

            where.append("""
                (
                    paciente_nome ILIKE %s
                    OR paciente_prontuario ILIKE %s
                    OR paciente_cpf ILIKE %s
                    OR REGEXP_REPLACE(COALESCE(paciente_cpf, ''), '\\D', '', 'g') ILIKE %s
                    OR usuario_nome ILIKE %s
                )
            """)
            params.extend([like, like, like, digits, like])

        if tipo and tipo in TIPOS_AVALIACAO:
            where.append("tipo = %s")
            params.append(tipo)

        cur = conn.cursor()
        try:
            cur.execute(f"""
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
                WHERE {" AND ".join(where)}
                ORDER BY id DESC
            """, params)
            avaliacoes = _rows_to_dicts(cur, cur.fetchall())
        finally:
            cur.close()

        registrar_log(conn, "LISTAR_AVALIACOES", detalhes=f"busca={busca}; tipo={tipo}")
        conn.commit()

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
@require_permission("avaliacoes", "ver")
def index():
    return redirect(url_for("avaliacoes.lista"))


# ============================================================
# VISUALIZAÇÃO / PDF
# ============================================================

@avaliacoes_bp.route("/visualizar/<int:id>", endpoint="visualizar")
@require_permission("avaliacoes", "ver")
def visualizar(id):
    conn = conectar_db()
    try:
        av = _buscar_avaliacao_por_id(conn, id)

        if not av:
            flash("Avaliação não encontrada para esta clínica.", "warning")
            return redirect(url_for("avaliacoes.lista"))

        try:
            dados = json.loads(av.get("dados_json") or "{}")
        except Exception:
            dados = {}

        itens = montar_itens_visualizacao(dados)

        registrar_log(conn, "VISUALIZAR_AVALIACAO", referencia_id=id)
        conn.commit()

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
@require_permission("avaliacoes", "exportar")
def exportar_pdf(id):
    conn = conectar_db()
    try:
        av = _buscar_avaliacao_por_id(conn, id)

        if not av:
            flash("Avaliação não encontrada para esta clínica.", "warning")
            return redirect(url_for("avaliacoes.lista"))

        try:
            dados = json.loads(av.get("dados_json") or "{}")
        except Exception:
            dados = {}

        itens = montar_itens_visualizacao(dados)

        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        largura, altura = A4

        margem_x = 40
        y = altura - 70

        def nova_pagina():
            nonlocal y
            pdf.showPage()
            y = altura - 70

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

        registrar_log(conn, "EXPORTAR_AVALIACAO_PDF", referencia_id=id)
        conn.commit()

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
@require_permission("avaliacoes", "editar")
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

        clinica_id = _clinica_id_atual()

        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO avaliacoes (
                    clinica_id,
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
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                clinica_id,
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
            ))

            avaliacao_id = _val(cur.fetchone(), "id", 0)

            registrar_log(
                conn,
                "CRIAR_AVALIACAO",
                referencia_id=avaliacao_id,
                detalhes=f"tipo={tipo}; paciente={paciente_nome}",
            )

            conn.commit()
        finally:
            cur.close()

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
@require_permission("avaliacoes", "editar")
def tela_anamnese():
    return render_template("anamnese.html", tipos=TIPOS_AVALIACAO)


@avaliacoes_bp.route("/social", endpoint="tela_social")
@require_permission("avaliacoes", "editar")
def tela_social():
    return render_template("social.html", tipos=TIPOS_AVALIACAO)


@avaliacoes_bp.route("/enfermagem", endpoint="tela_enfermagem")
@require_permission("avaliacoes", "editar")
def tela_enfermagem():
    return render_template("enfermagem.html", tipos=TIPOS_AVALIACAO)


@avaliacoes_bp.route("/terapia-ocupacional", endpoint="tela_terapia_ocupacional")
@require_permission("avaliacoes", "editar")
def tela_terapia_ocupacional():
    return render_template("terapia_ocupacional.html", tipos=TIPOS_AVALIACAO)


@avaliacoes_bp.route("/psicologia-infantil", endpoint="tela_psicologia_infantil")
@require_permission("avaliacoes", "editar")
def tela_psicologia_infantil():
    return render_template("psicologia_infantil.html", tipos=TIPOS_AVALIACAO)


@avaliacoes_bp.route("/fonoaudiologia-infantil", endpoint="tela_fonoaudiologia_infantil")
@require_permission("avaliacoes", "editar")
def tela_fonoaudiologia_infantil():
    return render_template("fonoaudiologia_infantil.html", tipos=TIPOS_AVALIACAO)