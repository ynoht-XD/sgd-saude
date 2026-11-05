# financeiro/beneficiarios.py
"""Beneficiários de um contrato (plano familiar): financeiro_plano_beneficiarios.

Regras:
- contrato.paciente_id é o responsável financeiro (titular) e ganha a primeira
  linha na criação do contrato (financas.api_criar_paciente_plano).
- O limite é contrato.max_beneficiarios (snapshot do catálogo; combo = 1).
- Remover = desativar (ativo = 0): mantém o histórico e libera a vaga. O titular
  não pode ser removido.
- As funções NÃO fazem commit: quem chama decide (as rotas abaixo comitam).
- Sem tela ainda; as rotas são só a API para teste/uso futuro.
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
    _to_int,
    _now_iso,
    _is_postgres_conn,
    _add_clinica_where,
    _buscar_paciente_por_id,
    _inserir_beneficiario_row,
    _registrar_log,
    _ok,
    _fail,
)


class BeneficiarioErro(Exception):
    def __init__(self, mensagem: str, status: int = 400):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status


def _carregar_contrato(conn, contrato_id: int, travar: bool = False) -> dict:
    where = ["id = ?"]
    params = [contrato_id]
    _add_clinica_where(conn, "financeiro_paciente_planos", "financeiro_paciente_planos", where, params)

    # FOR UPDATE (Postgres): duas adições simultâneas não estouram o limite.
    lock = " FOR UPDATE" if travar and _is_postgres_conn(conn) else ""

    cur = _execute(conn, f"""
        SELECT id, paciente_id, status, max_beneficiarios
        FROM financeiro_paciente_planos
        WHERE {" AND ".join(where)}
        LIMIT 1{lock}
    """, params)

    contrato = _fetchone_dict(cur)

    if not contrato:
        raise BeneficiarioErro("Contrato não encontrado para esta clínica.", 404)

    return contrato


def _linha_beneficiario(conn, contrato_id: int, paciente_id: int):
    where = ["contrato_id = ?", "paciente_id = ?"]
    params = [contrato_id, paciente_id]
    _add_clinica_where(conn, "financeiro_plano_beneficiarios", "financeiro_plano_beneficiarios", where, params)

    cur = _execute(conn, f"""
        SELECT id, ativo
        FROM financeiro_plano_beneficiarios
        WHERE {" AND ".join(where)}
        LIMIT 1
    """, params)

    return _fetchone_dict(cur)


def _contar_ativos(conn, contrato_id: int) -> int:
    where = ["contrato_id = ?", "ativo = 1"]
    params = [contrato_id]
    _add_clinica_where(conn, "financeiro_plano_beneficiarios", "financeiro_plano_beneficiarios", where, params)

    cur = _execute(conn, f"""
        SELECT COUNT(*) AS total
        FROM financeiro_plano_beneficiarios
        WHERE {" AND ".join(where)}
    """, params)

    return _to_int((_fetchone_dict(cur) or {}).get("total"), 0)


def listar_beneficiarios(conn, contrato_id: int, apenas_ativos: bool = True) -> list[dict]:
    contrato = _carregar_contrato(conn, contrato_id)

    where = ["b.contrato_id = ?"]
    params = [contrato_id]
    _add_clinica_where(conn, "financeiro_plano_beneficiarios", "b", where, params)

    if apenas_ativos:
        where.append("b.ativo = 1")

    cur = _execute(conn, f"""
        SELECT b.paciente_id, b.ativo, b.criado_em, p.nome AS paciente_nome
        FROM financeiro_plano_beneficiarios b
        LEFT JOIN pacientes p ON p.id = b.paciente_id
        WHERE {" AND ".join(where)}
        ORDER BY b.id ASC
    """, params)

    itens = _fetchall_dict(cur)
    titular = _to_int(contrato.get("paciente_id"), 0)

    for it in itens:
        it["eh_titular"] = _to_int(it.get("paciente_id"), 0) == titular

    return itens


def adicionar_beneficiario(conn, contrato_id: int, paciente_id: int) -> list[dict]:
    paciente_id = _to_int(paciente_id, 0)

    if paciente_id <= 0:
        raise BeneficiarioErro("Informe o paciente (paciente_id).")

    contrato = _carregar_contrato(conn, contrato_id, travar=True)

    if (contrato.get("status") or "ativo") != "ativo":
        raise BeneficiarioErro("Só é possível alterar beneficiários de contrato ativo.", 409)

    if not _buscar_paciente_por_id(conn, paciente_id):
        raise BeneficiarioErro("Paciente não encontrado para esta clínica.", 404)

    existente = _linha_beneficiario(conn, contrato_id, paciente_id)

    if existente and _to_int(existente.get("ativo"), 0) == 1:
        raise BeneficiarioErro("Este paciente já é beneficiário do contrato.", 409)

    limite = _to_int(contrato.get("max_beneficiarios"), 1) or 1

    if _contar_ativos(conn, contrato_id) >= limite:
        raise BeneficiarioErro(
            f"Limite de beneficiários do contrato atingido ({limite}).", 409
        )

    if existente:
        _execute(conn, "UPDATE financeiro_plano_beneficiarios SET ativo = 1 WHERE id = ?", [existente["id"]])
    else:
        _inserir_beneficiario_row(conn, contrato_id, paciente_id)

    return listar_beneficiarios(conn, contrato_id)


def remover_beneficiario(conn, contrato_id: int, paciente_id: int) -> list[dict]:
    paciente_id = _to_int(paciente_id, 0)

    contrato = _carregar_contrato(conn, contrato_id, travar=True)

    if paciente_id == _to_int(contrato.get("paciente_id"), -1):
        raise BeneficiarioErro("O titular (responsável financeiro) não pode ser removido do contrato.", 409)

    existente = _linha_beneficiario(conn, contrato_id, paciente_id)

    if not existente or _to_int(existente.get("ativo"), 0) != 1:
        raise BeneficiarioErro("Beneficiário não encontrado neste contrato.", 404)

    _execute(conn, "UPDATE financeiro_plano_beneficiarios SET ativo = 0 WHERE id = ?", [existente["id"]])

    return listar_beneficiarios(conn, contrato_id)


# ------------------------------------------------------------------ API (sem tela)

@financeiro_bp.get("/api/pacientes-planos/<int:contrato_id>/beneficiarios")
@require_permission("financeiro", "ver")
def api_listar_beneficiarios(contrato_id: int):
    ensure_financeiro_schema()

    conn = _conn()

    try:
        return _ok(items=listar_beneficiarios(conn, contrato_id))

    except BeneficiarioErro as e:
        return _fail(e.mensagem, e.status)

    except Exception as e:
        return _fail(f"Erro ao listar beneficiários: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.post("/api/pacientes-planos/<int:contrato_id>/beneficiarios")
@require_permission("financeiro", "editar")
def api_adicionar_beneficiario(contrato_id: int):
    ensure_financeiro_schema()

    data = request.get_json(silent=True) or request.form
    paciente_id = _to_int(data.get("paciente_id"), 0)

    conn = _conn()

    try:
        itens = adicionar_beneficiario(conn, contrato_id, paciente_id)

        _registrar_log(conn, "ADICIONAR_BENEFICIARIO", referencia_id=contrato_id,
                       detalhes=f"paciente_id={paciente_id}")
        conn.commit()

        return _ok(items=itens, mensagem="Beneficiário adicionado.")

    except BeneficiarioErro as e:
        conn.rollback()
        return _fail(e.mensagem, e.status)

    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao adicionar beneficiário: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.delete("/api/pacientes-planos/<int:contrato_id>/beneficiarios/<int:paciente_id>")
@require_permission("financeiro", "editar")
def api_remover_beneficiario(contrato_id: int, paciente_id: int):
    ensure_financeiro_schema()

    conn = _conn()

    try:
        itens = remover_beneficiario(conn, contrato_id, paciente_id)

        _registrar_log(conn, "REMOVER_BENEFICIARIO", referencia_id=contrato_id,
                       detalhes=f"paciente_id={paciente_id}")
        conn.commit()

        return _ok(items=itens, mensagem="Beneficiário removido.")

    except BeneficiarioErro as e:
        conn.rollback()
        return _fail(e.mensagem, e.status)

    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao remover beneficiário: {e}", 500)

    finally:
        conn.close()
