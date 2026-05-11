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
    session,
    abort,
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

try:
    from admin.modulos import require_permission
except Exception:
    def require_permission(modulo_codigo: str, acao: str = "ver"):
        def deco(fn):
            return fn
        return deco

try:
    from log import registrar_log, log_erro
except Exception:
    def registrar_log(*args, **kwargs): pass
    def log_erro(*args, **kwargs): pass


# =============================================================================
# CONTEXTO MULTI-CLÍNICA
# =============================================================================

def _clinica_id_atual() -> int:
    clinica_id = session.get("clinica_id")

    if not clinica_id:
        abort(403)

    try:
        return int(clinica_id)
    except Exception:
        abort(403)


def _ensure_paciente_clinica_schema(conn):
    ensure_pacientes_schema(conn)

    cols = table_columns(conn, "pacientes")

    if "clinica_id" not in cols:
        cur = conn.cursor()
        cur.execute("ALTER TABLE pacientes ADD COLUMN IF NOT EXISTS clinica_id INTEGER DEFAULT 1;")
        conn.commit()

    cur = conn.cursor()
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pacientes_clinica_id ON pacientes(clinica_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pacientes_clinica_nome ON pacientes(clinica_id, nome);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pacientes_clinica_cpf ON pacientes(clinica_id, cpf);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pacientes_clinica_cns ON pacientes(clinica_id, cns);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pacientes_clinica_prontuario ON pacientes(clinica_id, prontuario);")
    conn.commit()


def _buscar_paciente_clinica(conn, paciente_id: int):
    clinica_id = _clinica_id_atual()

    _ensure_paciente_clinica_schema(conn)

    cur = conn.cursor()
    cur.execute("""
        SELECT *
          FROM pacientes
         WHERE id = %s
           AND clinica_id = %s
         LIMIT 1;
    """, (paciente_id, clinica_id))

    return fetchone_dict(cur)


def _redirect_lista():
    return redirect(url_for("pacientes.listar_pacientes"), code=302)


def _tem_busca_manual() -> bool:
    """
    Só gera log de pesquisa quando vier filtro real na URL.
    Assim não registra cada letra das sugestões/autocomplete.
    """
    campos = [
        "nome",
        "prontuario",
        "cpf",
        "cns",
        "sexo",
        "status",
        "mod",
        "cid",
        "cidade",
        "bairro",
        "rua",
        "idade_min",
        "idade_max",
        "dia_semana",
        "terapeuta",
        "cbo",
    ]

    return any((request.args.get(c) or "").strip() for c in campos)


# =============================================================================
# ROTAS PRINCIPAIS
# =============================================================================

@pacientes_bp.route("/")
@require_permission("pacientes", "ver")
def listar_pacientes():
    clinica_id = _clinica_id_atual()

    try:
        args = request.args.copy()
        rows = fetch_pacientes_list(args)

        if _tem_busca_manual():
            registrar_log(
                modulo="pacientes",
                acao="pesquisar",
                entidade="pacientes",
                descricao="Pesquisou pacientes.",
                detalhes={
                    "clinica_id": clinica_id,
                    "filtros": dict(request.args),
                    "total": len(rows),
                },
            )
        else:
            registrar_log(
                modulo="pacientes",
                acao="visualizar",
                entidade="pacientes",
                descricao="Visualizou lista de pacientes.",
                detalhes={
                    "clinica_id": clinica_id,
                    "total": len(rows),
                },
            )

        return render_template(
            "pacientes.html",
            pacientes=rows,
            clinica_id=clinica_id,
            clinica_nome=session.get("clinica_nome"),
        )

    except Exception as e:
        log_erro(
            "pacientes",
            e,
            entidade="pacientes",
            descricao="Erro ao listar/pesquisar pacientes.",
            detalhes={
                "clinica_id": clinica_id,
                "filtros": dict(request.args),
            },
        )
        return f"Erro ao carregar pacientes: {e}", 500


@pacientes_bp.route("/pacientes")
@require_permission("pacientes", "ver")
def listar_pacientes_compat():
    return redirect(url_for("pacientes.listar_pacientes"), code=302)


@pacientes_bp.route("/visualizar/<int:id>")
@require_permission("pacientes", "ver")
def visualizar_paciente(id: int):
    clinica_id = _clinica_id_atual()

    try:
        with get_conn() as conn:
            paciente = _buscar_paciente_clinica(conn, id)

        if not paciente:
            return "Paciente não encontrado nesta clínica.", 404

        paciente = dict(paciente)

        try:
            agds = fetch_agendamentos_por_paciente(
                paciente.get("nome", ""),
                clinica_id=clinica_id,
            )
        except TypeError:
            agds = fetch_agendamentos_por_paciente(paciente.get("nome", ""))

        registrar_log(
            modulo="pacientes",
            acao="visualizar",
            entidade="pacientes",
            entidade_id=id,
            descricao="Visualizou ficha do paciente.",
            detalhes={
                "clinica_id": clinica_id,
                "paciente_id": id,
                "nome": paciente.get("nome"),
            },
        )

        return render_template(
            "visualizar_paciente.html",
            paciente=paciente,
            agds_upcoming=agds["agds_upcoming"],
            agds_all=agds["agds_all"],
            series_resumo=agds["series_resumo"],
            total_agds=agds["total_agds"],
            total_upcoming=agds["total_upcoming"],
        )

    except Exception as e:
        log_erro(
            "pacientes",
            e,
            entidade="pacientes",
            entidade_id=id,
            descricao="Erro ao visualizar paciente.",
            detalhes={"clinica_id": clinica_id},
        )
        return f"Erro ao visualizar paciente: {e}", 500


@pacientes_bp.route("/editar/<int:id>")
@require_permission("pacientes", "editar")
def editar_paciente(id: int):
    clinica_id = _clinica_id_atual()

    try:
        with get_conn() as conn:
            paciente = _buscar_paciente_clinica(conn, id)

        if not paciente:
            return "Paciente não encontrado nesta clínica.", 404

        registrar_log(
            modulo="pacientes",
            acao="visualizar_edicao",
            entidade="pacientes",
            entidade_id=id,
            descricao="Abriu edição do paciente.",
            detalhes={
                "clinica_id": clinica_id,
                "paciente_id": id,
                "nome": paciente.get("nome"),
            },
        )

        return render_template(
            "editar_paciente.html",
            paciente=paciente,
            clinica_id=clinica_id,
            clinica_nome=session.get("clinica_nome"),
        )

    except Exception as e:
        log_erro(
            "pacientes",
            e,
            entidade="pacientes",
            entidade_id=id,
            descricao="Erro ao abrir edição do paciente.",
            detalhes={"clinica_id": clinica_id},
        )
        return f"Erro ao abrir edição do paciente: {e}", 500


# =============================================================================
# ATUALIZAÇÃO DE PACIENTE
# =============================================================================

@pacientes_bp.route("/atualizar/<int:id>", methods=["POST"])
@require_permission("pacientes", "editar")
def atualizar_paciente(id: int):
    clinica_id = _clinica_id_atual()

    dados_raw = request.form.to_dict(flat=True)
    dados = upperize_payload(dados_raw)

    try:
        with get_conn() as conn:
            _ensure_paciente_clinica_schema(conn)

            paciente_atual = _buscar_paciente_clinica(conn, id)

            if not paciente_atual:
                return "Paciente não encontrado nesta clínica.", 404

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
            vals = [v for _, v in pairs] + [id, clinica_id]

            cur = conn.cursor()
            cur.execute(
                f"""
                UPDATE pacientes
                   SET {set_sql}
                 WHERE id = %s
                   AND clinica_id = %s;
                """,
                vals,
            )

            conn.commit()

        registrar_log(
            modulo="pacientes",
            acao="editar",
            entidade="pacientes",
            entidade_id=id,
            descricao="Paciente atualizado.",
            detalhes={
                "clinica_id": clinica_id,
                "paciente_id": id,
                "campos": [c for c, _ in pairs],
            },
        )

        return redirect(url_for("pacientes.visualizar_paciente", id=id))

    except Exception as e:
        log_erro(
            "pacientes",
            e,
            entidade="pacientes",
            entidade_id=id,
            descricao="Erro ao atualizar paciente.",
            detalhes={
                "clinica_id": clinica_id,
                "paciente_id": id,
            },
        )
        return f"Erro ao atualizar paciente: {e}", 500


# =============================================================================
# API AGENDAMENTOS DO PACIENTE
# =============================================================================

@pacientes_bp.route("/api/paciente/<int:id>/agendamentos")
@require_permission("pacientes", "ver")
def api_agendamentos_paciente(id: int):
    clinica_id = _clinica_id_atual()

    try:
        with get_conn() as conn:
            paciente = _buscar_paciente_clinica(conn, id)

        if not paciente:
            return jsonify({"erro": "Paciente não encontrado nesta clínica"}), 404

        try:
            data = fetch_agendamentos_por_paciente(
                paciente["nome"],
                clinica_id=clinica_id,
            )
        except TypeError:
            data = fetch_agendamentos_por_paciente(paciente["nome"])

        return jsonify(data)

    except Exception as e:
        log_erro(
            "pacientes",
            e,
            entidade="agendamentos",
            entidade_id=id,
            descricao="Erro ao buscar agendamentos do paciente.",
            detalhes={"clinica_id": clinica_id},
        )
        return jsonify({"erro": str(e)}), 500


# =============================================================================
# API AUTOSAVE DO CARD
# =============================================================================

@pacientes_bp.route("/api/autosave", methods=["POST"])
@require_permission("pacientes", "editar")
def api_autosave():
    clinica_id = _clinica_id_atual()
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
            _ensure_paciente_clinica_schema(conn)

            paciente = _buscar_paciente_clinica(conn, int(pid))

            if not paciente:
                return jsonify({"error": "Paciente não encontrado nesta clínica"}), 404

            cur = conn.cursor()
            cur.execute(
                f"""
                UPDATE pacientes
                   SET {col} = %s
                 WHERE id = %s
                   AND clinica_id = %s;
                """,
                (value_to_save, pid, clinica_id),
            )
            conn.commit()

        registrar_log(
            modulo="pacientes",
            acao="editar",
            entidade="pacientes",
            entidade_id=pid,
            descricao="Autosave do paciente.",
            detalhes={
                "clinica_id": clinica_id,
                "paciente_id": pid,
                "campo": field,
                "coluna": col,
            },
        )

        return jsonify({"ok": True})

    except Exception as e:
        log_erro(
            "pacientes",
            e,
            entidade="pacientes",
            entidade_id=pid,
            descricao="Erro no autosave do paciente.",
            detalhes={
                "clinica_id": clinica_id,
                "campo": field,
            },
        )
        return jsonify({"error": str(e)}), 500


# =============================================================================
# APIs DE SUGESTÕES
# Sem log aqui para não registrar cada letra digitada.
# =============================================================================

@pacientes_bp.route("/api/sugestoes/prontuarios")
@require_permission("pacientes", "ver")
def api_sugestoes_prontuarios():
    clinica_id = _clinica_id_atual()
    q = (request.args.get("q") or "").strip()

    if len(q) < 3:
        return jsonify([])

    with get_conn() as conn:
        _ensure_paciente_clinica_schema(conn)
        cols = table_columns(conn, "pacientes")

        if "prontuario" not in cols:
            return jsonify([])

        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT prontuario
              FROM pacientes
             WHERE clinica_id = %s
               AND TRIM(COALESCE(prontuario,'')) <> ''
               AND prontuario ILIKE %s
             ORDER BY prontuario
             LIMIT 20;
        """, (clinica_id, f"%{q}%"))
        rows = cur.fetchall()

    out = []

    for r in rows:
        val = r.get("prontuario") if isinstance(r, dict) else r[0]
        if val:
            out.append(val)

    return jsonify(out)


@pacientes_bp.route("/api/sugestoes/nomes")
@require_permission("pacientes", "ver")
def api_sugestoes_nomes():
    clinica_id = _clinica_id_atual()
    q = (request.args.get("q") or "").strip()

    if len(q) < 3:
        return jsonify([])

    with get_conn() as conn:
        _ensure_paciente_clinica_schema(conn)
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
             WHERE clinica_id = %s
               AND nome ILIKE %s
             ORDER BY nome
             LIMIT 20;
        """

        cur = conn.cursor()
        cur.execute(sql, (clinica_id, f"%{q}%"))
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
@require_permission("pacientes", "ver")
def api_sugestoes_terapeutas():
    clinica_id = _clinica_id_atual()
    q = (request.args.get("q") or "").strip()

    if len(q) < 3:
        return jsonify([])

    with get_conn() as conn:
        if not has_table(conn, "agendamentos"):
            return jsonify([])

        cols_ag = table_columns(conn, "agendamentos")

        if "profissional" not in cols_ag:
            return jsonify([])

        filtro_clinica = "AND clinica_id = %s" if "clinica_id" in cols_ag else ""

        params = []

        if filtro_clinica:
            params.append(clinica_id)

        params.append(f"%{q}%")

        cur = conn.cursor()
        cur.execute(f"""
            SELECT DISTINCT profissional
              FROM agendamentos
             WHERE TRIM(COALESCE(profissional,'')) <> ''
               {filtro_clinica}
               AND profissional ILIKE %s
             ORDER BY profissional
             LIMIT 50;
        """, params)
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
@require_permission("pacientes", "ver")
def api_sugestoes_cids():
    clinica_id = _clinica_id_atual()
    q = (request.args.get("q") or "").strip()

    with get_conn() as conn:
        _ensure_paciente_clinica_schema(conn)
        cur = conn.cursor()

        if q:
            cur.execute("""
                SELECT DISTINCT cid
                  FROM pacientes
                 WHERE clinica_id = %s
                   AND cid ILIKE %s
                 ORDER BY cid
                 LIMIT 20;
            """, (clinica_id, f"%{q}%"))
        else:
            cur.execute("""
                SELECT DISTINCT cid
                  FROM pacientes
                 WHERE clinica_id = %s
                   AND cid IS NOT NULL
                   AND TRIM(cid) <> ''
                 ORDER BY cid
                 LIMIT 20;
            """, (clinica_id,))

        rows = cur.fetchall()

    out = []

    for r in rows:
        val = r["cid"] if isinstance(r, dict) else r[0]
        if val:
            out.append(val)

    return jsonify(out)


@pacientes_bp.route("/api/sugestoes/modalidades")
@require_permission("pacientes", "ver")
def api_sugestoes_modalidades():
    clinica_id = _clinica_id_atual()
    q = (request.args.get("q") or "").strip()

    with get_conn() as conn:
        _ensure_paciente_clinica_schema(conn)
        cur = conn.cursor()

        if q:
            cur.execute("""
                SELECT DISTINCT mod
                  FROM pacientes
                 WHERE clinica_id = %s
                   AND mod ILIKE %s
                 ORDER BY mod
                 LIMIT 20;
            """, (clinica_id, f"%{q}%"))
        else:
            cur.execute("""
                SELECT DISTINCT mod
                  FROM pacientes
                 WHERE clinica_id = %s
                   AND mod IS NOT NULL
                   AND TRIM(mod) <> ''
                 ORDER BY mod
                 LIMIT 20;
            """, (clinica_id,))

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
@require_permission("pacientes", "editar")
def excluir_paciente(id: int):
    clinica_id = _clinica_id_atual()

    try:
        with get_conn() as conn:
            _ensure_paciente_clinica_schema(conn)

            paciente = _buscar_paciente_clinica(conn, id)

            if not paciente:
                return "Paciente não encontrado nesta clínica.", 404

            cur = conn.cursor()
            cur.execute("""
                DELETE FROM pacientes
                 WHERE id = %s
                   AND clinica_id = %s;
            """, (id, clinica_id))
            conn.commit()

        registrar_log(
            modulo="pacientes",
            acao="excluir",
            entidade="pacientes",
            entidade_id=id,
            descricao="Paciente excluído.",
            detalhes={
                "clinica_id": clinica_id,
                "paciente_id": id,
                "nome": paciente.get("nome"),
            },
        )

        ref = request.referrer or url_for("pacientes.listar_pacientes")
        return redirect(ref)

    except Exception as e:
        log_erro(
            "pacientes",
            e,
            entidade="pacientes",
            entidade_id=id,
            descricao="Erro ao excluir paciente.",
            detalhes={"clinica_id": clinica_id},
        )
        return f"Erro ao excluir paciente: {e}", 500


# =============================================================================
# DIAGNÓSTICO
# =============================================================================

@pacientes_bp.route("/__ping")
def ping_pacientes():
    return "ok", 200