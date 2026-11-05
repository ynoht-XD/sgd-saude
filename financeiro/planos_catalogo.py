# financeiro/planos_catalogo.py
"""Catálogo de planos (financeiro_planos): listar, criar, editar, ativar/desativar.

Espelha o CRUD de combos (routes.py). Cada plano pertence a um profissional
(profissional_id = usuarios.id da clínica, validado aqui: não há FK no banco).
"""
from __future__ import annotations

from flask import request

from . import financeiro_bp
from admin.modulos import require_permission

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
    _add_clinica_where,
    _add_clinica_insert,
    _validar_profissional,
    _registrar_log,
    _ok,
    _fail,
)

PERIODOS = ("semana", "mes")


def _ler_payload(data, atual: dict | None = None):
    """Valida o payload. `atual` (edição): campos ausentes mantêm o valor atual.

    Devolve (campos, erro).
    """
    atual = atual or {}

    def pega(chave, padrao=None):
        if chave in data and data.get(chave) not in (None, ""):
            return data.get(chave)
        return atual.get(chave, padrao)

    nome = str(pega("nome", "") or "").strip()
    descricao = str(pega("descricao", "") or "").strip()
    valor = _to_float(pega("valor_mensalidade", 0), 0)
    duracao = _to_int(pega("duracao_meses", 1), 0)
    por_periodo = _to_int(pega("sessoes_por_periodo", 1), 0)
    periodo = str(pega("periodo", "semana") or "").strip().lower()
    max_benef = _to_int(pega("max_beneficiarios", 1), 0)
    profissional_id = _to_int(pega("profissional_id", 0), 0)

    if "ativo" in data and data.get("ativo") not in (None, ""):
        ativo = _to_bool(data.get("ativo"))
    else:
        ativo = _to_int(atual.get("ativo", 1), 1)

    if not nome:
        return None, "Informe o nome do plano."
    if valor < 0:
        return None, "Valor da mensalidade inválido."
    if duracao <= 0:
        return None, "Informe a duração do plano em meses (maior que zero)."
    if por_periodo <= 0:
        return None, "Informe quantas consultas por período (maior que zero)."
    if periodo not in PERIODOS:
        return None, "Período inválido. Use 'semana' ou 'mes'."
    if max_benef <= 0:
        return None, "Máximo de beneficiários deve ser pelo menos 1."
    if profissional_id <= 0:
        return None, "Informe o profissional do plano (profissional_id)."

    return {
        "profissional_id": profissional_id,
        "nome": nome,
        "descricao": descricao,
        "valor_mensalidade": valor,
        "duracao_meses": duracao,
        "sessoes_por_periodo": por_periodo,
        "periodo": periodo,
        "max_beneficiarios": max_benef,
        "ativo": ativo,
    }, None


def _buscar_plano(conn, plano_id: int):
    where = ["id = ?"]
    params = [plano_id]
    _add_clinica_where(conn, "financeiro_planos", "financeiro_planos", where, params)

    cur = _execute(conn, f"""
        SELECT *
        FROM financeiro_planos
        WHERE {" AND ".join(where)}
        LIMIT 1
    """, params)

    return _fetchone_dict(cur), where, params


@financeiro_bp.get("/api/planos")
@require_permission("financeiro", "ver")
def api_listar_planos():
    ensure_financeiro_schema()

    q = (request.args.get("q") or "").strip()
    ativo = request.args.get("ativo")
    profissional_id = _to_int(request.args.get("profissional_id"), 0)

    conn = _conn()

    try:
        where = ["1=1"]
        params = []

        _add_clinica_where(conn, "financeiro_planos", "fp", where, params)

        if q:
            like_op = "ILIKE" if _is_postgres_conn(conn) else "LIKE"
            where.append(f"(fp.nome {like_op} ? OR COALESCE(fp.descricao, '') {like_op} ?)")
            params.extend([f"%{q}%", f"%{q}%"])

        if ativo in ("0", "1"):
            where.append("fp.ativo = ?")
            params.append(int(ativo))

        if profissional_id > 0:
            where.append("fp.profissional_id = ?")
            params.append(profissional_id)

        cur = _execute(conn, f"""
            SELECT fp.*
            FROM financeiro_planos fp
            WHERE {" AND ".join(where)}
            ORDER BY fp.ativo DESC, fp.nome ASC
        """, params)

        _registrar_log(conn, "LISTAR_PLANOS_CATALOGO", detalhes=f"q={q}; ativo={ativo}; profissional_id={profissional_id}")
        conn.commit()

        return _ok(items=_fetchall_dict(cur))

    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao listar planos do catálogo: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.post("/api/planos")
@require_permission("financeiro", "editar")
def api_criar_plano():
    ensure_financeiro_schema()

    data = request.get_json(silent=True) or request.form

    campos, erro = _ler_payload(data)
    if erro:
        return _fail(erro)

    conn = _conn()

    try:
        if not _validar_profissional(conn, campos["profissional_id"]):
            return _fail("Profissional não encontrado nesta clínica.", 404)

        cols = list(campos.keys()) + ["criado_em", "atualizado_em"]
        vals = list(campos.values()) + [_now_iso(), _now_iso()]
        cols, vals = _add_clinica_insert(conn, "financeiro_planos", cols, vals)

        sql = f"""
            INSERT INTO financeiro_planos ({", ".join(cols)})
            VALUES ({", ".join(["?"] * len(cols))})
        """

        if _is_postgres_conn(conn):
            cur = _execute(conn, sql + " RETURNING id", vals)
            plano_id = _fetchone_dict(cur)["id"]
        else:
            plano_id = _execute(conn, sql, vals).lastrowid

        _registrar_log(conn, "CRIAR_PLANO_CATALOGO", referencia_id=plano_id,
                       detalhes=f"Plano criado: {campos['nome']}")
        conn.commit()

        item, _, _ = _buscar_plano(conn, plano_id)

        return _ok(item=item, mensagem="Plano cadastrado com sucesso.")

    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao cadastrar plano: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.put("/api/planos/<int:plano_id>")
@require_permission("financeiro", "editar")
def api_editar_plano(plano_id: int):
    ensure_financeiro_schema()

    data = request.get_json(silent=True) or request.form

    conn = _conn()

    try:
        atual, where, params = _buscar_plano(conn, plano_id)

        if not atual:
            return _fail("Plano não encontrado para esta clínica.", 404)

        campos, erro = _ler_payload(data, atual)
        if erro:
            return _fail(erro)

        if campos["profissional_id"] != _to_int(atual.get("profissional_id"), 0):
            if not _validar_profissional(conn, campos["profissional_id"]):
                return _fail("Profissional não encontrado nesta clínica.", 404)

        sets = [f"{c} = ?" for c in campos] + ["atualizado_em = ?"]

        _execute(conn, f"""
            UPDATE financeiro_planos
            SET {", ".join(sets)}
            WHERE {" AND ".join(where)}
        """, [*campos.values(), _now_iso(), *params])

        _registrar_log(conn, "EDITAR_PLANO_CATALOGO", referencia_id=plano_id,
                       detalhes=f"Plano editado: {campos['nome']}")
        conn.commit()

        item, _, _ = _buscar_plano(conn, plano_id)

        return _ok(item=item, mensagem="Plano atualizado com sucesso. Contratos já vendidos não mudam.")

    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao atualizar plano: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.patch("/api/planos/<int:plano_id>/status")
@require_permission("financeiro", "editar")
def api_alterar_status_plano(plano_id: int):
    ensure_financeiro_schema()

    data = request.get_json(silent=True) or request.form

    if data.get("ativo") in (None, ""):
        return _fail("Informe 'ativo' (0 ou 1).")

    ativo = _to_bool(data.get("ativo"))

    conn = _conn()

    try:
        atual, where, params = _buscar_plano(conn, plano_id)

        if not atual:
            return _fail("Plano não encontrado para esta clínica.", 404)

        _execute(conn, f"""
            UPDATE financeiro_planos
            SET ativo = ?, atualizado_em = ?
            WHERE {" AND ".join(where)}
        """, [ativo, _now_iso(), *params])

        _registrar_log(conn, "ALTERAR_STATUS_PLANO_CATALOGO", referencia_id=plano_id,
                       detalhes=f"Plano do catálogo ativo={ativo}")
        conn.commit()

        item, _, _ = _buscar_plano(conn, plano_id)

        return _ok(item=item, mensagem="Status do plano atualizado com sucesso.")

    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao alterar status do plano: {e}", 500)

    finally:
        conn.close()
