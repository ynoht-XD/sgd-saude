# financeiro/routes.py
from __future__ import annotations

from flask import jsonify, request, session

from . import financeiro_bp

# Registra rotas do livro-caixa/financeiro principal
from . import financas  # noqa: F401

from .financas import (
    ensure_financeiro_schema,
    _conn,
    _execute,
    _fetchall_dict,
    _fetchone_dict,
    _to_float,
    _to_int,
    _to_bool,
    _now_iso,
    _is_postgres_conn,
    _list_columns,
    _has_col,
    _add_clinica_where,
    _exigir_coluna_clinica,
    FiltroClinicaIndisponivel,
    _validar_profissional,
)

from admin.modulos import require_permission

# Catálogo de planos e beneficiários (registram suas rotas no blueprint)
from . import planos_catalogo  # noqa: F401
from . import beneficiarios  # noqa: F401

# Novos combos devem ter profissional_id. Fica False enquanto a tela de combos
# (comercial.js) não envia o campo: ligar para True quando o front for atualizado.
COMBO_EXIGE_PROFISSIONAL = False


# ============================================================
# HELPERS LOCAIS
# ============================================================

def _ok(**kwargs):
    payload = {"ok": True}
    payload.update(kwargs)
    return jsonify(payload)


def _fail(message: str, status: int = 400, **kwargs):
    payload = {"ok": False, "erro": message}
    payload.update(kwargs)
    return jsonify(payload), status


def _usuario_id_atual():
    return session.get("user_id") or session.get("usuario_id")


def _clinica_id_atual(default=1):
    val = session.get("clinica_id") or session.get("clinic_id") or default
    try:
        return int(val) if val is not None else None
    except Exception:
        return default


def _table_exists(conn, table: str) -> bool:
    try:
        if _is_postgres_conn(conn):
            cur = _execute(conn, """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = ?
                LIMIT 1
            """, (table,))
            return cur.fetchone() is not None

        cur = _execute(conn, """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = ?
            LIMIT 1
        """, (table,))
        return cur.fetchone() is not None
    except Exception:
        return False


# _cols/_has_col/_add_clinica_where vem de financas.py (versao que NAO engole excecao
# e recusa a consulta se nao der para garantir o filtro de clinica).
_cols = _list_columns


def _insert_with_optional_clinica(conn, table: str, cols: list[str], values: list):
    _exigir_coluna_clinica(conn, table)

    if "clinica_id" not in cols:
        cols.insert(0, "clinica_id")
        values.insert(0, _clinica_id_atual())

    placeholders = ", ".join(["?"] * len(cols))
    col_sql = ", ".join(cols)

    return col_sql, placeholders, values


def _registrar_log(conn, acao: str, referencia_id=None, detalhes: str = "", sucesso: bool = True):
    """
    Log tolerante:
    - se tabela logs não existir, ignora;
    - se algumas colunas não existirem, usa só as disponíveis.
    """

    try:
        if not _table_exists(conn, "logs"):
            return

        cols = _cols(conn, "logs")
        campos = []
        valores = []
        params = []

        def add(campo, valor):
            if campo in cols:
                campos.append(campo)
                valores.append("?")
                params.append(valor)

        add("usuario_id", _usuario_id_atual())
        add("clinica_id", _clinica_id_atual())
        add("modulo", "financeiro")
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

        if not campos:
            return

        _execute(conn, f"""
            INSERT INTO logs ({", ".join(campos)})
            VALUES ({", ".join(valores)})
        """, params)

    except Exception as e:
        print(f"[FINANCEIRO][LOG] Falha ao registrar log: {e}")


# ============================================================
# COMBOS
# ============================================================

@financeiro_bp.get("/api/combos")
@require_permission("financeiro", "ver")
def api_listar_combos():
    ensure_financeiro_schema()

    q = (request.args.get("q") or "").strip()
    ativo = request.args.get("ativo")

    conn = _conn()

    try:
        where = ["1=1"]
        params = []

        _add_clinica_where(conn, "financeiro_combos", "fc", where, params)

        if q:
            like_op = "ILIKE" if _is_postgres_conn(conn) else "LIKE"
            where.append(f"""
                (
                    fc.nome {like_op} ?
                    OR COALESCE(fc.descricao, '') {like_op} ?
                )
            """)
            params.extend([f"%{q}%", f"%{q}%"])

        if ativo in ("0", "1"):
            where.append("fc.ativo = ?")
            params.append(int(ativo))

        prof_filtro = _to_int(request.args.get("profissional_id"), 0)
        if prof_filtro > 0:
            where.append("fc.profissional_id = ?")
            params.append(prof_filtro)

        cur = _execute(conn, f"""
            SELECT
                fc.id,
                fc.profissional_id,
                fc.nome,
                fc.descricao,
                fc.sessoes,
                fc.preco,
                fc.ativo,
                fc.criado_em,
                fc.atualizado_em
            FROM financeiro_combos fc
            WHERE {" AND ".join(where)}
            ORDER BY fc.ativo DESC, fc.nome ASC
        """, params)

        _registrar_log(conn, "LISTAR_COMBOS", detalhes=f"q={q}; ativo={ativo}")
        conn.commit()

        return _ok(items=_fetchall_dict(cur))

    except Exception as e:
        return _fail(f"Erro ao listar combos: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.post("/api/combos")
@require_permission("financeiro", "editar")
def api_criar_combo():
    ensure_financeiro_schema()

    data = request.get_json(silent=True) or request.form

    nome = (data.get("nome") or "").strip()
    descricao = (data.get("descricao") or "").strip()
    sessoes = _to_int(data.get("sessoes"), 0)
    preco = _to_float(data.get("preco"), 0)
    ativo = _to_bool(data.get("ativo", 1))

    if not nome:
        return _fail("Informe o nome do combo.")

    if sessoes <= 0:
        return _fail("Informe a quantidade de sessões do combo.")

    if preco < 0:
        return _fail("Preço inválido.")

    profissional_id = _to_int(data.get("profissional_id"), 0) or None

    if COMBO_EXIGE_PROFISSIONAL and not profissional_id:
        return _fail("Informe o profissional do combo (profissional_id).")

    conn = _conn()

    try:
        if profissional_id and not _validar_profissional(conn, profissional_id):
            return _fail("Profissional não encontrado nesta clínica.", 404)

        cols = [
            "nome",
            "descricao",
            "sessoes",
            "preco",
            "ativo",
            "criado_em",
            "atualizado_em",
            "profissional_id",
        ]

        vals = [
            nome,
            descricao,
            sessoes,
            preco,
            ativo,
            _now_iso(),
            _now_iso(),
            profissional_id,
        ]

        col_sql, placeholders, vals = _insert_with_optional_clinica(
            conn,
            "financeiro_combos",
            cols,
            vals,
        )

        if _is_postgres_conn(conn):
            cur = _execute(conn, f"""
                INSERT INTO financeiro_combos ({col_sql})
                VALUES ({placeholders})
                RETURNING id
            """, vals)

            combo_id = _fetchone_dict(cur)["id"]

        else:
            cur = _execute(conn, f"""
                INSERT INTO financeiro_combos ({col_sql})
                VALUES ({placeholders})
            """, vals)

            combo_id = cur.lastrowid

        _registrar_log(
            conn,
            "CRIAR_COMBO",
            referencia_id=combo_id,
            detalhes=f"Combo criado: {nome}",
        )

        conn.commit()

        where = ["id = ?"]
        params = [combo_id]
        _add_clinica_where(conn, "financeiro_combos", "financeiro_combos", where, params)

        cur = _execute(conn, f"""
            SELECT *
            FROM financeiro_combos
            WHERE {" AND ".join(where)}
        """, params)

        return _ok(
            item=_fetchone_dict(cur),
            mensagem="Combo cadastrado com sucesso."
        )

    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao cadastrar combo: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.put("/api/combos/<int:combo_id>")
@require_permission("financeiro", "editar")
def api_editar_combo(combo_id: int):
    ensure_financeiro_schema()

    data = request.get_json(silent=True) or request.form

    nome = (data.get("nome") or "").strip()
    descricao = (data.get("descricao") or "").strip()
    sessoes = _to_int(data.get("sessoes"), 0)
    preco = _to_float(data.get("preco"), 0)
    ativo = _to_bool(data.get("ativo", 1))

    if not nome:
        return _fail("Informe o nome do combo.")

    if sessoes <= 0:
        return _fail("Informe a quantidade de sessões.")

    if preco < 0:
        return _fail("Preço inválido.")

    conn = _conn()

    try:
        where = ["id = ?"]
        params = [combo_id]
        _add_clinica_where(conn, "financeiro_combos", "financeiro_combos", where, params)

        cur = _execute(conn, f"""
            SELECT id
            FROM financeiro_combos
            WHERE {" AND ".join(where)}
            LIMIT 1
        """, params)

        if not cur.fetchone():
            return _fail("Combo não encontrado para esta clínica.", 404)

        # profissional_id só muda se vier no payload (combo antigo sem profissional segue editável)
        extra_set = ""
        extra_val = []
        prof_novo = _to_int(data.get("profissional_id"), 0)

        if prof_novo > 0:
            if not _validar_profissional(conn, prof_novo):
                return _fail("Profissional não encontrado nesta clínica.", 404)
            extra_set = "profissional_id = ?,"
            extra_val = [prof_novo]

        _execute(conn, f"""
            UPDATE financeiro_combos
            SET
                nome = ?,
                descricao = ?,
                sessoes = ?,
                preco = ?,
                ativo = ?,
                {extra_set}
                atualizado_em = ?
            WHERE {" AND ".join(where)}
        """, (
            nome,
            descricao,
            sessoes,
            preco,
            ativo,
            *extra_val,
            _now_iso(),
            *params,
        ))

        _registrar_log(
            conn,
            "EDITAR_COMBO",
            referencia_id=combo_id,
            detalhes=f"Combo editado: {nome}",
        )

        conn.commit()

        cur = _execute(conn, f"""
            SELECT *
            FROM financeiro_combos
            WHERE {" AND ".join(where)}
        """, params)

        return _ok(
            item=_fetchone_dict(cur),
            mensagem="Combo atualizado com sucesso."
        )

    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao atualizar combo: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.delete("/api/combos/<int:combo_id>")
@require_permission("financeiro", "editar")
def api_excluir_combo(combo_id: int):
    ensure_financeiro_schema()

    conn = _conn()

    try:
        combo_where = ["id = ?"]
        combo_params = [combo_id]
        _add_clinica_where(conn, "financeiro_combos", "financeiro_combos", combo_where, combo_params)

        cur = _execute(conn, f"""
            SELECT id
            FROM financeiro_combos
            WHERE {" AND ".join(combo_where)}
            LIMIT 1
        """, combo_params)

        if not cur.fetchone():
            return _fail("Combo não encontrado para esta clínica.", 404)

        plano_where = ["combo_id = ?"]
        plano_params = [combo_id]
        _add_clinica_where(conn, "financeiro_paciente_planos", "financeiro_paciente_planos", plano_where, plano_params)

        cur = _execute(conn, f"""
            SELECT COUNT(*) AS total
            FROM financeiro_paciente_planos
            WHERE {" AND ".join(plano_where)}
        """, plano_params)

        uso = _fetchone_dict(cur) or {}

        if _to_int(uso.get("total"), 0) > 0:
            return _fail(
                "Este combo já está vinculado a paciente(s). Edite ou inative em vez de excluir.",
                409
            )

        _execute(conn, f"""
            DELETE FROM financeiro_combos
            WHERE {" AND ".join(combo_where)}
        """, combo_params)

        _registrar_log(
            conn,
            "EXCLUIR_COMBO",
            referencia_id=combo_id,
            detalhes=f"Combo excluído. id={combo_id}",
        )

        conn.commit()

        return _ok(mensagem="Combo excluído com sucesso.")

    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao excluir combo: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.patch("/api/combos/<int:combo_id>/status")
@require_permission("financeiro", "editar")
def api_alterar_status_combo(combo_id: int):
    ensure_financeiro_schema()

    data = request.get_json(silent=True) or request.form
    ativo = _to_bool(data.get("ativo"))

    conn = _conn()

    try:
        where = ["id = ?"]
        params = [combo_id]
        _add_clinica_where(conn, "financeiro_combos", "financeiro_combos", where, params)

        cur = _execute(conn, f"""
            SELECT id
            FROM financeiro_combos
            WHERE {" AND ".join(where)}
            LIMIT 1
        """, params)

        if not cur.fetchone():
            return _fail("Combo não encontrado para esta clínica.", 404)

        _execute(conn, f"""
            UPDATE financeiro_combos
            SET ativo = ?, atualizado_em = ?
            WHERE {" AND ".join(where)}
        """, (
            ativo,
            _now_iso(),
            *params,
        ))

        _registrar_log(
            conn,
            "ALTERAR_STATUS_COMBO",
            referencia_id=combo_id,
            detalhes=f"Status do combo alterado para ativo={ativo}",
        )

        conn.commit()

        cur = _execute(conn, f"""
            SELECT *
            FROM financeiro_combos
            WHERE {" AND ".join(where)}
        """, params)

        return _ok(
            item=_fetchone_dict(cur),
            mensagem="Status do combo atualizado com sucesso."
        )

    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao alterar status do combo: {e}", 500)

    finally:
        conn.close()


# ============================================================
# PACIENTES x PLANOS / COMBOS
# ============================================================

@financeiro_bp.put("/api/pacientes-planos/<int:plano_id>")
@require_permission("financeiro", "editar")
def api_editar_paciente_plano(plano_id: int):
    ensure_financeiro_schema()

    data = request.get_json(silent=True) or request.form

    combo_id = data.get("combo_id")
    status = (data.get("status") or "").strip() or None
    sessoes_contratadas = data.get("sessoes_contratadas")
    sessoes_usadas = data.get("sessoes_usadas")
    valor_total = data.get("valor_total")

    conn = _conn()

    try:
        where = ["id = ?"]
        params = [plano_id]
        _add_clinica_where(conn, "financeiro_paciente_planos", "financeiro_paciente_planos", where, params)

        cur = _execute(conn, f"""
            SELECT id
            FROM financeiro_paciente_planos
            WHERE {" AND ".join(where)}
            LIMIT 1
        """, params)

        if not cur.fetchone():
            return _fail("Plano do paciente não encontrado para esta clínica.", 404)

        campos = []
        update_params = []

        if combo_id not in (None, ""):
            campos.append("combo_id = ?")
            update_params.append(_to_int(combo_id, None))

        if status:
            campos.append("status = ?")
            update_params.append(status)

        if sessoes_contratadas not in (None, ""):
            campos.append("sessoes_contratadas = ?")
            update_params.append(_to_int(sessoes_contratadas, 0))

        if sessoes_usadas not in (None, ""):
            campos.append("sessoes_usadas = ?")
            update_params.append(_to_int(sessoes_usadas, 0))

        if valor_total not in (None, ""):
            campos.append("valor_total = ?")
            update_params.append(_to_float(valor_total, 0))

        if not campos:
            return _fail("Nenhum campo enviado para atualizar.")

        campos.append("atualizado_em = ?")
        update_params.append(_now_iso())

        _execute(conn, f"""
            UPDATE financeiro_paciente_planos
            SET {", ".join(campos)}
            WHERE {" AND ".join(where)}
        """, update_params + params)

        _registrar_log(
            conn,
            "EDITAR_PLANO_PACIENTE",
            referencia_id=plano_id,
            detalhes=f"Plano paciente atualizado. status={status}; combo_id={combo_id}",
        )

        conn.commit()

        cur = _execute(conn, f"""
            SELECT *
            FROM financeiro_paciente_planos
            WHERE {" AND ".join(where)}
        """, params)

        return _ok(
            item=_fetchone_dict(cur),
            mensagem="Plano atualizado com sucesso."
        )

    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao atualizar plano: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.delete("/api/pacientes-planos/<int:plano_id>")
@require_permission("financeiro", "editar")
def api_excluir_paciente_plano(plano_id: int):
    ensure_financeiro_schema()

    conn = _conn()

    try:
        where = ["id = ?"]
        params = [plano_id]
        _add_clinica_where(conn, "financeiro_paciente_planos", "financeiro_paciente_planos", where, params)

        cur = _execute(conn, f"""
            SELECT *
            FROM financeiro_paciente_planos
            WHERE {" AND ".join(where)}
            LIMIT 1
        """, params)

        plano = _fetchone_dict(cur)

        if not plano:
            return _fail("Plano do paciente não encontrado para esta clínica.", 404)

        sessoes_usadas = _to_int(plano.get("sessoes_usadas"), 0)

        if sessoes_usadas > 0:
            _execute(conn, f"""
                UPDATE financeiro_paciente_planos
                SET
                    status = 'cancelado',
                    atualizado_em = ?
                WHERE {" AND ".join(where)}
            """, [_now_iso()] + params)

            _registrar_log(
                conn,
                "CANCELAR_PLANO_PACIENTE",
                referencia_id=plano_id,
                detalhes="Plano cancelado porque já possuía sessões usadas.",
            )

            conn.commit()

            return _ok(
                mensagem="Plano já possuía sessões usadas, então foi cancelado em vez de excluído.",
                modo="cancelado"
            )

        _execute(conn, "DELETE FROM financeiro_plano_beneficiarios WHERE contrato_id = ?", [plano_id])

        _execute(conn, f"""
            DELETE FROM financeiro_paciente_planos
            WHERE {" AND ".join(where)}
        """, params)

        _registrar_log(
            conn,
            "EXCLUIR_PLANO_PACIENTE",
            referencia_id=plano_id,
            detalhes="Plano excluído.",
        )

        conn.commit()

        return _ok(
            mensagem="Plano excluído com sucesso.",
            modo="excluido"
        )

    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao excluir plano: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.post("/api/pacientes-planos/<int:plano_id>/desvincular-atendimentos")
@require_permission("financeiro", "editar")
def api_desvincular_atendimentos_plano(plano_id: int):
    """
    Desvincula atendimentos do plano/combo quando existir coluna relacionada.
    Mantém compatível mesmo se a tabela/coluna ainda não existir.
    """
    ensure_financeiro_schema()

    conn = _conn()

    try:
        plano_where = ["id = ?"]
        plano_params = [plano_id]
        _add_clinica_where(conn, "financeiro_paciente_planos", "financeiro_paciente_planos", plano_where, plano_params)

        cur = _execute(conn, f"""
            SELECT id
            FROM financeiro_paciente_planos
            WHERE {" AND ".join(plano_where)}
            LIMIT 1
        """, plano_params)

        if not cur.fetchone():
            return _fail("Plano do paciente não encontrado para esta clínica.", 404)

        atualizados = 0

        # A coluna que liga atendimento -> plano/combo e atendimentos.combo_plano_id
        # (gravada em atendimentos/routes.py). Antes a rota procurava quatro nomes
        # que nao existem e respondia "sucesso" com 0 linhas.
        atend_cols = _cols(conn, "atendimentos")

        if "combo_plano_id" not in atend_cols:
            return _fail(
                "Tabela atendimentos sem a coluna combo_plano_id; nada foi desvinculado.",
                409,
            )

        where = ["combo_plano_id = ?"]
        params = [plano_id]
        _add_clinica_where(conn, "atendimentos", "atendimentos", where, params)

        # Mesma regra do cadastro do atendimento: sem combo => nao contabiliza.
        sets = ["combo_plano_id = NULL"]
        if "contabiliza_sessao" in atend_cols:
            sets.append("contabiliza_sessao = 0")

        cur = _execute(conn, f"""
            UPDATE atendimentos
            SET {", ".join(sets)}
            WHERE {" AND ".join(where)}
        """, params)

        atualizados = cur.rowcount or 0

        # Todos os atendimentos do plano foram soltos: o contador gravado
        # (lido pela agenda) volta a zero na mesma transacao.
        _execute(conn, f"""
            UPDATE financeiro_paciente_planos
            SET sessoes_usadas = 0, atualizado_em = ?
            WHERE {" AND ".join(plano_where)}
        """, [_now_iso()] + plano_params)

        _registrar_log(
            conn,
            "DESVINCULAR_ATENDIMENTOS_PLANO",
            referencia_id=plano_id,
            detalhes=f"Atendimentos desvinculados: {atualizados}",
        )

        conn.commit()

        return _ok(
            mensagem="Atendimentos desvinculados com sucesso.",
            atualizados=atualizados
        )

    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao desvincular atendimentos: {e}", 500)

    finally:
        conn.close()