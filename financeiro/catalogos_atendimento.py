# financeiro/catalogos_atendimento.py
"""Catálogos financeiros de Atendimento Avulso (financeiro_avulsos) e de Avaliação
(financeiro_avaliacoes): listar, criar, editar e ativar/desativar.

Os dois têm a mesma forma (por isso uma fábrica só); muda apenas o nome da coluna de
valor (valor_padrao x valor) e o prefixo das rotas:

    /financeiro/api/avulsos      /financeiro/api/avaliacoes

Padrão de financeiro_combos / financeiro_planos: cada linha pertence a um profissional
(profissional_id = usuarios.id da clínica, validado na aplicação), respeita clinica_id
e usa @require_permission("financeiro", ...).

Nada aqui é lido por agenda/ ou cadastro/ ainda (gancho do Grupo D, não ativado).
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

CATALOGOS = {
    "avulso": {
        "tabela": "financeiro_avulsos",
        "campo_valor": "valor_padrao",
        "rota": "avulsos",
        "rotulo": "atendimento avulso",
        "rotulo_pl": "atendimentos avulsos",
        "log": "AVULSO",
    },
    "avaliacao": {
        "tabela": "financeiro_avaliacoes",
        "campo_valor": "valor",
        "rota": "avaliacoes",
        "rotulo": "avaliação",
        "rotulo_pl": "avaliações",
        "log": "AVALIACAO",
    },
}


def _ler_payload(cfg: dict, data, atual: dict | None = None):
    """Valida o payload. Em edição (`atual`), campo ausente ou em branco mantém o valor atual;
    só `duracao_prevista_min` aceita limpar (enviar null/""). Devolve (campos, erro)."""
    atual = atual or {}
    cv = cfg["campo_valor"]

    def pega(chave, padrao=None):
        if chave in data and data.get(chave) not in (None, ""):
            return data.get(chave)
        return atual.get(chave, padrao)

    descricao = str(pega("descricao", "") or "").strip()
    valor = _to_float(pega(cv, 0), 0)
    profissional_id = _to_int(pega("profissional_id", 0), 0)

    if "duracao_prevista_min" in data:
        bruto = data.get("duracao_prevista_min")
        duracao = None if bruto in (None, "") else _to_int(bruto, 0)
    else:
        duracao = atual.get("duracao_prevista_min")
        duracao = _to_int(duracao, 0) if duracao not in (None, "") else None

    if "ativo" in data and data.get("ativo") not in (None, ""):
        ativo = _to_bool(data.get("ativo"))
    else:
        ativo = _to_int(atual.get("ativo", 1), 1)

    if not descricao:
        return None, f"Informe a descrição ({cfg['rotulo']})."
    if valor < 0:
        return None, "Valor inválido."
    if duracao is not None and duracao <= 0:
        return None, "Duração prevista deve ser maior que zero (em minutos)."
    if profissional_id <= 0:
        return None, "Informe o profissional (profissional_id)."

    return {
        "profissional_id": profissional_id,
        "descricao": descricao,
        cv: valor,
        "duracao_prevista_min": duracao,
        "ativo": ativo,
    }, None


def _buscar(conn, cfg: dict, item_id: int):
    where = ["id = ?"]
    params = [item_id]
    _add_clinica_where(conn, cfg["tabela"], cfg["tabela"], where, params)

    cur = _execute(conn, f"""
        SELECT *
        FROM {cfg['tabela']}
        WHERE {" AND ".join(where)}
        LIMIT 1
    """, params)

    return _fetchone_dict(cur), where, params


def _registrar_catalogo(chave: str):
    cfg = CATALOGOS[chave]
    tabela = cfg["tabela"]
    rota = cfg["rota"]
    sufixo = cfg["log"]

    # -------------------------------------------------------------- listar
    @require_permission("financeiro", "ver")
    def listar():
        ensure_financeiro_schema()

        q = (request.args.get("q") or "").strip()
        ativo = request.args.get("ativo")
        profissional_id = _to_int(request.args.get("profissional_id"), 0)

        conn = _conn()

        try:
            where = ["1=1"]
            params = []

            _add_clinica_where(conn, tabela, "t", where, params)

            if q:
                like_op = "ILIKE" if _is_postgres_conn(conn) else "LIKE"
                where.append(f"t.descricao {like_op} ?")
                params.append(f"%{q}%")

            if ativo in ("0", "1"):
                where.append("t.ativo = ?")
                params.append(int(ativo))

            if profissional_id > 0:
                where.append("t.profissional_id = ?")
                params.append(profissional_id)

            cur = _execute(conn, f"""
                SELECT t.*
                FROM {tabela} t
                WHERE {" AND ".join(where)}
                ORDER BY t.ativo DESC, t.descricao ASC
            """, params)

            _registrar_log(conn, f"LISTAR_{sufixo}", detalhes=f"q={q}; ativo={ativo}; profissional_id={profissional_id}")
            conn.commit()

            return _ok(items=_fetchall_dict(cur))

        except Exception as e:
            conn.rollback()
            return _fail(f"Erro ao listar {cfg['rotulo_pl']}: {e}", 500)

        finally:
            conn.close()

    # -------------------------------------------------------------- criar
    @require_permission("financeiro", "editar")
    def criar():
        ensure_financeiro_schema()

        data = request.get_json(silent=True) or request.form

        campos, erro = _ler_payload(cfg, data)
        if erro:
            return _fail(erro)

        conn = _conn()

        try:
            if not _validar_profissional(conn, campos["profissional_id"]):
                return _fail("Profissional não encontrado nesta clínica.", 404)

            cols = list(campos.keys()) + ["criado_em", "atualizado_em"]
            vals = list(campos.values()) + [_now_iso(), _now_iso()]
            cols, vals = _add_clinica_insert(conn, tabela, cols, vals)

            sql = f"""
                INSERT INTO {tabela} ({", ".join(cols)})
                VALUES ({", ".join(["?"] * len(cols))})
            """

            if _is_postgres_conn(conn):
                cur = _execute(conn, sql + " RETURNING id", vals)
                item_id = _fetchone_dict(cur)["id"]
            else:
                item_id = _execute(conn, sql, vals).lastrowid

            _registrar_log(conn, f"CRIAR_{sufixo}", referencia_id=item_id,
                           detalhes=f"{cfg['rotulo']} criado: {campos['descricao']}")
            conn.commit()

            item, _, _ = _buscar(conn, cfg, item_id)

            return _ok(item=item, mensagem="Cadastrado com sucesso.")

        except Exception as e:
            conn.rollback()
            return _fail(f"Erro ao cadastrar {cfg['rotulo']}: {e}", 500)

        finally:
            conn.close()

    # -------------------------------------------------------------- editar
    @require_permission("financeiro", "editar")
    def editar(item_id: int):
        ensure_financeiro_schema()

        data = request.get_json(silent=True) or request.form

        conn = _conn()

        try:
            atual, where, params = _buscar(conn, cfg, item_id)

            if not atual:
                return _fail("Registro não encontrado para esta clínica.", 404)

            campos, erro = _ler_payload(cfg, data, atual)
            if erro:
                return _fail(erro)

            if campos["profissional_id"] != _to_int(atual.get("profissional_id"), 0):
                if not _validar_profissional(conn, campos["profissional_id"]):
                    return _fail("Profissional não encontrado nesta clínica.", 404)

            sets = [f"{c} = ?" for c in campos] + ["atualizado_em = ?"]

            _execute(conn, f"""
                UPDATE {tabela}
                SET {", ".join(sets)}
                WHERE {" AND ".join(where)}
            """, [*campos.values(), _now_iso(), *params])

            _registrar_log(conn, f"EDITAR_{sufixo}", referencia_id=item_id,
                           detalhes=f"{cfg['rotulo']} editado: {campos['descricao']}")
            conn.commit()

            item, _, _ = _buscar(conn, cfg, item_id)

            return _ok(item=item, mensagem="Atualizado com sucesso.")

        except Exception as e:
            conn.rollback()
            return _fail(f"Erro ao atualizar {cfg['rotulo']}: {e}", 500)

        finally:
            conn.close()

    # -------------------------------------------------------------- ativar/desativar
    @require_permission("financeiro", "editar")
    def alterar_status(item_id: int):
        ensure_financeiro_schema()

        data = request.get_json(silent=True) or request.form

        if data.get("ativo") in (None, ""):
            return _fail("Informe 'ativo' (0 ou 1).")

        ativo = _to_bool(data.get("ativo"))

        conn = _conn()

        try:
            atual, where, params = _buscar(conn, cfg, item_id)

            if not atual:
                return _fail("Registro não encontrado para esta clínica.", 404)

            _execute(conn, f"""
                UPDATE {tabela}
                SET ativo = ?, atualizado_em = ?
                WHERE {" AND ".join(where)}
            """, [ativo, _now_iso(), *params])

            _registrar_log(conn, f"ALTERAR_STATUS_{sufixo}", referencia_id=item_id,
                           detalhes=f"{cfg['rotulo']} ativo={ativo}")
            conn.commit()

            item, _, _ = _buscar(conn, cfg, item_id)

            return _ok(item=item, mensagem="Status atualizado com sucesso.")

        except Exception as e:
            conn.rollback()
            return _fail(f"Erro ao alterar status: {e}", 500)

        finally:
            conn.close()

    # Endpoints com nomes próprios (o Flask exige nomes únicos por blueprint).
    for fn, nome in ((listar, "listar"), (criar, "criar"), (editar, "editar"), (alterar_status, "status")):
        fn.__name__ = f"api_{nome}_{chave}"

    financeiro_bp.add_url_rule(f"/api/{rota}", endpoint=f"api_listar_{chave}", view_func=listar, methods=["GET"])
    financeiro_bp.add_url_rule(f"/api/{rota}", endpoint=f"api_criar_{chave}", view_func=criar, methods=["POST"])
    financeiro_bp.add_url_rule(f"/api/{rota}/<int:item_id>", endpoint=f"api_editar_{chave}", view_func=editar, methods=["PUT"])
    financeiro_bp.add_url_rule(f"/api/{rota}/<int:item_id>/status", endpoint=f"api_status_{chave}", view_func=alterar_status, methods=["PATCH"])


for _chave in CATALOGOS:
    _registrar_catalogo(_chave)
