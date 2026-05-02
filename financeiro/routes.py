# financeiro/routes.py
from __future__ import annotations

# ============================================================
# IMPORTAÇÕES FUTURAS DO MÓDULO FINANCEIRO
# ============================================================
# Importa para registrar as rotas do livro caixa:
# /api/lancamentos
# /api/fechamento
# /api/resumo
# /api/categorias
# /api/pacientes-planos
# /api/pacientes/buscar
# /api/pacientes-sem-vinculo
from . import financas  # noqa: F401


from flask import jsonify, request

from . import financeiro_bp

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
)


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


# ============================================================
# COMBOS
# ============================================================

@financeiro_bp.get("/api/combos")
def api_listar_combos():
    ensure_financeiro_schema()

    q = (request.args.get("q") or "").strip()
    ativo = request.args.get("ativo")

    conn = _conn()

    try:
        sql = """
            SELECT
                id,
                nome,
                descricao,
                sessoes,
                preco,
                ativo,
                criado_em,
                atualizado_em
            FROM financeiro_combos
            WHERE 1=1
        """
        params = []

        if q:
            like_op = "ILIKE" if _is_postgres_conn(conn) else "LIKE"
            sql += f"""
                AND (
                    nome {like_op} ?
                    OR COALESCE(descricao, '') {like_op} ?
                )
            """
            params.extend([f"%{q}%", f"%{q}%"])

        if ativo in ("0", "1"):
            sql += " AND ativo = ?"
            params.append(int(ativo))

        sql += " ORDER BY ativo DESC, nome ASC"

        cur = _execute(conn, sql, params)
        return _ok(items=_fetchall_dict(cur))

    except Exception as e:
        return _fail(f"Erro ao listar combos: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.post("/api/combos")
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

    conn = _conn()

    try:
        if _is_postgres_conn(conn):
            cur = _execute(conn, """
                INSERT INTO financeiro_combos (
                    nome,
                    descricao,
                    sessoes,
                    preco,
                    ativo,
                    criado_em,
                    atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                RETURNING id
            """, (
                nome,
                descricao,
                sessoes,
                preco,
                ativo,
                _now_iso(),
                _now_iso(),
            ))

            combo_id = _fetchone_dict(cur)["id"]

        else:
            cur = _execute(conn, """
                INSERT INTO financeiro_combos (
                    nome,
                    descricao,
                    sessoes,
                    preco,
                    ativo,
                    criado_em,
                    atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                nome,
                descricao,
                sessoes,
                preco,
                ativo,
                _now_iso(),
                _now_iso(),
            ))

            combo_id = cur.lastrowid

        conn.commit()

        cur = _execute(conn, """
            SELECT *
            FROM financeiro_combos
            WHERE id = ?
        """, (combo_id,))

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
        cur = _execute(conn, """
            SELECT id
            FROM financeiro_combos
            WHERE id = ?
            LIMIT 1
        """, (combo_id,))

        if not cur.fetchone():
            return _fail("Combo não encontrado.", 404)

        _execute(conn, """
            UPDATE financeiro_combos
            SET
                nome = ?,
                descricao = ?,
                sessoes = ?,
                preco = ?,
                ativo = ?,
                atualizado_em = ?
            WHERE id = ?
        """, (
            nome,
            descricao,
            sessoes,
            preco,
            ativo,
            _now_iso(),
            combo_id,
        ))

        conn.commit()

        cur = _execute(conn, """
            SELECT *
            FROM financeiro_combos
            WHERE id = ?
        """, (combo_id,))

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
def api_excluir_combo(combo_id: int):
    ensure_financeiro_schema()

    conn = _conn()

    try:
        cur = _execute(conn, """
            SELECT COUNT(*) AS total
            FROM financeiro_paciente_planos
            WHERE combo_id = ?
        """, (combo_id,))

        uso = _fetchone_dict(cur) or {}

        if _to_int(uso.get("total"), 0) > 0:
            return _fail(
                "Este combo já está vinculado a paciente(s). Edite ou inative em vez de excluir.",
                409
            )

        _execute(conn, """
            DELETE FROM financeiro_combos
            WHERE id = ?
        """, (combo_id,))

        conn.commit()

        return _ok(mensagem="Combo excluído com sucesso.")

    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao excluir combo: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.patch("/api/combos/<int:combo_id>/status")
def api_alterar_status_combo(combo_id: int):
    ensure_financeiro_schema()

    data = request.get_json(silent=True) or request.form
    ativo = _to_bool(data.get("ativo"))

    conn = _conn()

    try:
        cur = _execute(conn, """
            SELECT id
            FROM financeiro_combos
            WHERE id = ?
            LIMIT 1
        """, (combo_id,))

        if not cur.fetchone():
            return _fail("Combo não encontrado.", 404)

        _execute(conn, """
            UPDATE financeiro_combos
            SET ativo = ?, atualizado_em = ?
            WHERE id = ?
        """, (
            ativo,
            _now_iso(),
            combo_id,
        ))

        conn.commit()

        cur = _execute(conn, """
            SELECT *
            FROM financeiro_combos
            WHERE id = ?
        """, (combo_id,))

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
# PACIENTES x PLANOS / COMBOS - EDITAR / EXCLUIR / DESVINCULAR
# ============================================================

@financeiro_bp.put("/api/pacientes-planos/<int:plano_id>")
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
        cur = _execute(conn, """
            SELECT id
            FROM financeiro_paciente_planos
            WHERE id = ?
            LIMIT 1
        """, (plano_id,))

        if not cur.fetchone():
            return _fail("Plano do paciente não encontrado.", 404)

        campos = []
        params = []

        if combo_id not in (None, ""):
            campos.append("combo_id = ?")
            params.append(_to_int(combo_id, None))

        if status:
            campos.append("status = ?")
            params.append(status)

        if sessoes_contratadas not in (None, ""):
            campos.append("sessoes_contratadas = ?")
            params.append(_to_int(sessoes_contratadas, 0))

        if sessoes_usadas not in (None, ""):
            campos.append("sessoes_usadas = ?")
            params.append(_to_int(sessoes_usadas, 0))

        if valor_total not in (None, ""):
            campos.append("valor_total = ?")
            params.append(_to_float(valor_total, 0))

        campos.append("atualizado_em = ?")
        params.append(_now_iso())

        if not campos:
            return _fail("Nenhum campo enviado para atualizar.")

        params.append(plano_id)

        _execute(conn, f"""
            UPDATE financeiro_paciente_planos
            SET {", ".join(campos)}
            WHERE id = ?
        """, params)

        conn.commit()

        cur = _execute(conn, """
            SELECT *
            FROM financeiro_paciente_planos
            WHERE id = ?
        """, (plano_id,))

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
def api_excluir_paciente_plano(plano_id: int):
    ensure_financeiro_schema()

    conn = _conn()

    try:
        cur = _execute(conn, """
            SELECT *
            FROM financeiro_paciente_planos
            WHERE id = ?
            LIMIT 1
        """, (plano_id,))

        plano = _fetchone_dict(cur)

        if not plano:
            return _fail("Plano do paciente não encontrado.", 404)

        sessoes_usadas = _to_int(plano.get("sessoes_usadas"), 0)

        if sessoes_usadas > 0:
            _execute(conn, """
                UPDATE financeiro_paciente_planos
                SET
                    status = 'cancelado',
                    atualizado_em = ?
                WHERE id = ?
            """, (_now_iso(), plano_id))

            conn.commit()

            return _ok(
                mensagem="Plano já possuía sessões usadas, então foi cancelado em vez de excluído.",
                modo="cancelado"
            )

        _execute(conn, """
            DELETE FROM financeiro_paciente_planos
            WHERE id = ?
        """, (plano_id,))

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
def api_desvincular_atendimentos_plano(plano_id: int):
    """
    Desvincula atendimentos do plano/combo quando existir coluna relacionada.
    Mantém compatível mesmo se a tabela/coluna ainda não existir.
    """
    ensure_financeiro_schema()

    conn = _conn()

    try:
        cur = _execute(conn, """
            SELECT id
            FROM financeiro_paciente_planos
            WHERE id = ?
            LIMIT 1
        """, (plano_id,))

        if not cur.fetchone():
            return _fail("Plano do paciente não encontrado.", 404)

        atualizados = 0

        # Verifica se existe tabela atendimentos
        if _is_postgres_conn(conn):
            cur = _execute(conn, """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'atendimentos'
                LIMIT 1
            """)
            tem_atendimentos = cur.fetchone() is not None
        else:
            cur = _execute(conn, """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = 'atendimentos'
                LIMIT 1
            """)
            tem_atendimentos = cur.fetchone() is not None

        if tem_atendimentos:
            colunas_possiveis = [
                "paciente_plano_id",
                "plano_id",
                "financeiro_plano_id",
                "combo_paciente_id"
            ]

            for coluna in colunas_possiveis:
                if _is_postgres_conn(conn):
                    cur = _execute(conn, """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'atendimentos'
                          AND column_name = ?
                        LIMIT 1
                    """, (coluna,))
                    tem_coluna = cur.fetchone() is not None
                else:
                    cur = _execute(conn, "PRAGMA table_info(atendimentos)")
                    cols = _fetchall_dict(cur)
                    tem_coluna = any(c.get("name") == coluna for c in cols)

                if tem_coluna:
                    cur = _execute(conn, f"""
                        UPDATE atendimentos
                        SET {coluna} = NULL
                        WHERE {coluna} = ?
                    """, (plano_id,))
                    atualizados += cur.rowcount or 0

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