# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from typing import Any

from flask import (
    render_template,
    redirect,
    request,
    url_for,
    jsonify,
)

from . import pacientes_bp
from .helpers import (
    get_conn,
    ensure_pacientes_schema,
    table_columns,
    upperize_payload,
    calc_idade,
    json_list,
    fetch_pacientes_list,
    fetch_agendamentos_por_paciente,
    fetchone_dict,
    has_table,
    split_profissionais,
)


# =============================================================================
# ROTAS PRINCIPAIS (TELAS)
# =============================================================================

@pacientes_bp.route("/")
def listar_pacientes():
    rows = fetch_pacientes_list(request.args)
    return render_template("pacientes.html", pacientes=rows)


@pacientes_bp.route("/pacientes")
def listar_pacientes_compat():
    return redirect(url_for("pacientes.listar_pacientes"), code=302)


@pacientes_bp.route("/visualizar/<int:id>")
def visualizar_paciente(id: int):
    with get_conn() as conn:
        ensure_pacientes_schema(conn)

        cur = conn.cursor()
        cur.execute("SELECT * FROM pacientes WHERE id = %s LIMIT 1", (id,))
        row = fetchone_dict(cur)

    if not row:
        return "Paciente não encontrado", 404

    paciente = dict(row)
    agds = fetch_agendamentos_por_paciente(paciente.get("nome", ""))

    return render_template(
        "visualizar_paciente.html",
        paciente=paciente,
        agds_upcoming=agds["agds_upcoming"],
        agds_all=agds["agds_all"],
        series_resumo=agds["series_resumo"],
        total_agds=agds["total_agds"],
        total_upcoming=agds["total_upcoming"],
    )


@pacientes_bp.route("/editar/<int:id>")
def editar_paciente(id: int):
    with get_conn() as conn:
        ensure_pacientes_schema(conn)

        cur = conn.cursor()
        cur.execute("SELECT * FROM pacientes WHERE id = %s LIMIT 1", (id,))
        paciente = fetchone_dict(cur)

    if not paciente:
        return "Paciente não encontrado", 404

    return render_template("editar_paciente.html", paciente=paciente)


# =============================================================================
# ATUALIZAÇÃO DE PACIENTE
# =============================================================================

@pacientes_bp.route("/atualizar/<int:id>", methods=["POST"])
def atualizar_paciente(id: int):
    dados_raw = request.form.to_dict(flat=True)
    dados = upperize_payload(dados_raw)

    with get_conn() as conn:
        ensure_pacientes_schema(conn)
        cols = table_columns(conn, "pacientes")

        pairs: list[tuple[str, Any]] = []

        def add_if_exists(col: str, val: Any):
            if col in cols:
                pairs.append((col, "" if val is None else val))

        # -------- principais --------
        add_if_exists("status", dados.get("status"))
        add_if_exists("mod", dados.get("mod"))
        add_if_exists("nome", dados.get("nome"))
        add_if_exists("nascimento", dados.get("nascimento"))
        add_if_exists("sexo", (dados.get("sexo") or "").strip().upper())
        add_if_exists("cid", dados.get("cid"))
        add_if_exists("cid2", dados.get("cid2"))
        add_if_exists("admissao", dados.get("admissao"))
        add_if_exists("raca", dados.get("raca"))

        nasc = (dados.get("nascimento") or "").strip()
        idade_calc = calc_idade(nasc) if nasc else None
        if "idade" in cols:
            pairs.append(("idade", idade_calc))

        # -------- endereço --------
        add_if_exists("logradouro", dados.get("logradouro"))
        add_if_exists("bairro", dados.get("bairro"))
        add_if_exists("numero_casa", dados.get("numero_casa"))
        add_if_exists("complemento", dados.get("complemento"))
        add_if_exists("cep", dados.get("cep"))
        add_if_exists("municipio", dados.get("municipio"))
        add_if_exists("codigo_logradouro", dados.get("codigo_logradouro"))
        add_if_exists("uf", dados.get("uf"))

        # compat
        if "rua" in cols and not (dados.get("rua") or "").strip():
            pairs.append(("rua", dados.get("logradouro") or ""))
        if "numero" in cols and not (dados.get("numero") or "").strip():
            pairs.append(("numero", dados.get("numero_casa") or ""))
        if "cidade" in cols and not (dados.get("cidade") or "").strip():
            pairs.append(("cidade", dados.get("municipio") or ""))

        # -------- documentos --------
        add_if_exists("cpf", dados.get("cpf"))
        add_if_exists("cns", dados.get("cns"))
        add_if_exists("estado_civil", dados.get("estado_civil"))
        add_if_exists("rg", dados.get("rg"))
        add_if_exists("orgao_rg", dados.get("orgao_rg"))
        add_if_exists("nis", dados.get("nis"))

        # -------- contatos --------
        add_if_exists("telefone1", dados.get("telefone1"))
        add_if_exists("telefone2", dados.get("telefone2"))
        add_if_exists("telefone3", dados.get("telefone3"))
        add_if_exists("email", dados.get("email"))

        if "telefone" in cols and not (dados.get("telefone") or "").strip():
            pairs.append(("telefone", dados.get("telefone1") or ""))

        # -------- familiares --------
        add_if_exists("mae", dados.get("mae"))
        add_if_exists("cpf_mae", dados.get("cpf_mae"))
        add_if_exists("rg_mae", dados.get("rg_mae"))
        add_if_exists("rg_ssp_mae", dados.get("rg_ssp_mae"))
        add_if_exists("nis_mae", dados.get("nis_mae"))

        add_if_exists("pai", dados.get("pai"))
        add_if_exists("cpf_pai", dados.get("cpf_pai"))
        add_if_exists("rg_pai", dados.get("rg_pai"))
        add_if_exists("rg_ssp_pai", dados.get("rg_ssp_pai"))

        # -------- responsável --------
        add_if_exists("responsavel", dados.get("responsavel"))
        add_if_exists("cpf_responsavel", dados.get("cpf_responsavel"))
        add_if_exists("rg_responsavel", dados.get("rg_responsavel"))
        add_if_exists("orgao_rg_responsavel", dados.get("orgao_rg_responsavel"))

        if not pairs:
            return redirect(url_for("pacientes.visualizar_paciente", id=id))

        dedup = {}
        for k, v in pairs:
            dedup[k] = v
        pairs = list(dedup.items())

        set_sql = ", ".join([f"{c} = %s" for c, _ in pairs])
        vals = [v for _, v in pairs] + [id]

        try:
            cur = conn.cursor()
            cur.execute(f"UPDATE pacientes SET {set_sql} WHERE id = %s", vals)
            conn.commit()
            return redirect(url_for("pacientes.visualizar_paciente", id=id))
        except Exception as e:
            conn.rollback()
            return f"Erro ao atualizar paciente: {e}", 500


# =============================================================================
# API (AGENDAMENTOS DO PACIENTE)
# =============================================================================

@pacientes_bp.route("/api/paciente/<int:id>/agendamentos")
def api_agendamentos_paciente(id: int):
    with get_conn() as conn:
        ensure_pacientes_schema(conn)

        cur = conn.cursor()
        cur.execute("SELECT nome FROM pacientes WHERE id = %s LIMIT 1", (id,))
        r = fetchone_dict(cur)

    if not r:
        return jsonify({"erro": "Paciente não encontrado"}), 404

    data = fetch_agendamentos_por_paciente(r["nome"])
    return jsonify(data)


# =============================================================================
# API (AUTOSAVE DO CARD)
# =============================================================================

@pacientes_bp.route("/api/autosave", methods=["POST"])
def api_autosave():
    payload = request.get_json(silent=True) or {}

    pid = payload.get("id")
    field = (payload.get("field") or "").strip()
    value = payload.get("value")

    if not pid:
        return jsonify({"error": "id obrigatório"}), 400

    allowed = {
        "end_prontuario": "end_prontuario",
        "alergias": "alergias",
        "aviso": "aviso",
        "tags": "comorbidades_json",
    }
    if field not in allowed:
        return jsonify({"error": f"field inválido: {field}"}), 400

    col = allowed[field]
    if field == "tags":
        arr = json_list(value)
        value_to_save = json.dumps(arr, ensure_ascii=False)
    else:
        value_to_save = "" if value is None else str(value)

    try:
        with get_conn() as conn:
            ensure_pacientes_schema(conn)
            cur = conn.cursor()
            cur.execute(f"UPDATE pacientes SET {col} = %s WHERE id = %s", (value_to_save, pid))
            conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# APIs DE SUGESTÕES
# =============================================================================

@pacientes_bp.route("/api/sugestoes/prontuarios")
def api_sugestoes_prontuarios():
    q = (request.args.get("q") or "").strip()
    if len(q) < 3:
        return jsonify([])

    with get_conn() as conn:
        ensure_pacientes_schema(conn)
        cols = table_columns(conn, "pacientes")
        if "prontuario" not in cols:
            return jsonify([])

        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT prontuario
              FROM pacientes
             WHERE TRIM(COALESCE(prontuario,'')) <> ''
               AND prontuario ILIKE %s
             ORDER BY prontuario
             LIMIT 20
        """, (f"%{q}%",))
        rows = cur.fetchall()

    out = []
    for r in rows:
        if isinstance(r, dict):
            val = r.get("prontuario")
        else:
            val = r[0]
        if val:
            out.append(val)
    return jsonify(out)


@pacientes_bp.route("/api/sugestoes/nomes")
def api_sugestoes_nomes():
    q = (request.args.get("q") or "").strip()
    if len(q) < 3:
        return jsonify([])

    with get_conn() as conn:
        ensure_pacientes_schema(conn)
        cols = table_columns(conn, "pacientes")
        have_cpf = "cpf" in cols
        have_pront = "prontuario" in cols
        have_nasc = "nascimento" in cols

        sel_parts = ["nome"]
        sel_parts.append("nascimento" if have_nasc else "NULL::text AS nascimento")
        sel_parts.append("cpf" if have_cpf else "NULL::text AS cpf")
        sel_parts.append("prontuario" if have_pront else "NULL::text AS prontuario")

        sql = f"""
            SELECT DISTINCT {", ".join(sel_parts)}
              FROM pacientes
             WHERE nome ILIKE %s
             ORDER BY nome
             LIMIT 20
        """

        cur = conn.cursor()
        cur.execute(sql, (f"%{q}%",))
        rows = cur.fetchall()

    out = []
    for r in rows:
        try:
            row = dict(r)
        except Exception:
            row = {
                "nome": r[0] if len(r) > 0 else "",
                "nascimento": r[1] if len(r) > 1 else None,
                "cpf": r[2] if len(r) > 2 else "",
                "prontuario": r[3] if len(r) > 3 else "",
            }

        nasc = row.get("nascimento")
        out.append({
            "nome": (row.get("nome") or "").strip(),
            "cpf": row.get("cpf") or "",
            "idade": calc_idade(nasc) if nasc else None,
            "prontuario": row.get("prontuario") or "",
        })
    return jsonify(out)


@pacientes_bp.route("/api/sugestoes/terapeutas")
def api_sugestoes_terapeutas():
    q = (request.args.get("q") or "").strip()
    if len(q) < 3:
        return jsonify([])

    with get_conn() as conn:
        if not has_table(conn, "agendamentos"):
            return jsonify([])

        cols_ag = table_columns(conn, "agendamentos")
        if "profissional" not in cols_ag:
            return jsonify([])

        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT profissional
              FROM agendamentos
             WHERE TRIM(COALESCE(profissional,'')) <> ''
               AND profissional ILIKE %s
             ORDER BY profissional
             LIMIT 50
        """, (f"%{q}%",))
        rows = cur.fetchall()

    nomes = set()
    for r in rows:
        raw = r["profissional"] if isinstance(r, dict) else r[0]
        raw = (raw or "").strip()
        for p in split_profissionais(raw):
            if len(p.strip()) >= 3 and q.lower() in p.lower():
                nomes.add(p.strip())

    return jsonify(sorted(nomes)[:20])


@pacientes_bp.route("/api/sugestoes/cids")
def api_sugestoes_cids():
    q = (request.args.get("q") or "").strip()

    with get_conn() as conn:
        ensure_pacientes_schema(conn)
        cur = conn.cursor()

        if q:
            cur.execute("""
                SELECT DISTINCT cid
                  FROM pacientes
                 WHERE cid ILIKE %s
                 ORDER BY cid
                 LIMIT 20
            """, (f"%{q}%",))
        else:
            cur.execute("""
                SELECT DISTINCT cid
                  FROM pacientes
                 WHERE cid IS NOT NULL AND TRIM(cid) <> ''
                 ORDER BY cid
                 LIMIT 20
            """)
        rows = cur.fetchall()

    out = []
    for r in rows:
        val = r["cid"] if isinstance(r, dict) else r[0]
        if val:
            out.append(val)
    return jsonify(out)


@pacientes_bp.route("/api/sugestoes/modalidades")
def api_sugestoes_modalidades():
    q = (request.args.get("q") or "").strip()

    with get_conn() as conn:
        ensure_pacientes_schema(conn)
        cur = conn.cursor()

        if q:
            cur.execute("""
                SELECT DISTINCT mod
                  FROM pacientes
                 WHERE mod ILIKE %s
                 ORDER BY mod
                 LIMIT 20
            """, (f"%{q}%",))
        else:
            cur.execute("""
                SELECT DISTINCT mod
                  FROM pacientes
                 WHERE mod IS NOT NULL AND TRIM(mod) <> ''
                 ORDER BY mod
                 LIMIT 20
            """)
        rows = cur.fetchall()

    out = []
    for r in rows:
        val = r["mod"] if isinstance(r, dict) else r[0]
        if val:
            out.append(val)
    return jsonify(out)


# =============================================================================
# EXCLUSÃO
# =============================================================================

@pacientes_bp.route("/excluir/<int:id>", methods=["POST"])
def excluir_paciente(id: int):
    try:
        with get_conn() as conn:
            ensure_pacientes_schema(conn)

            cur = conn.cursor()
            cur.execute("SELECT 1 FROM pacientes WHERE id = %s LIMIT 1", (id,))
            if not cur.fetchone():
                return "Paciente não encontrado.", 404

            cur.execute("DELETE FROM pacientes WHERE id = %s", (id,))
            conn.commit()

        ref = request.referrer or url_for("pacientes.listar_pacientes")
        return redirect(ref)

    except Exception as e:
        return f"Erro ao excluir paciente: {e}", 500


# =============================================================================
# DIAGNÓSTICO
# =============================================================================

@pacientes_bp.route("/__ping")
def ping_pacientes():
    return "ok", 200