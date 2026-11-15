# atendimentos/cids_ativos.py
"""CID ATIVO do paciente (condicoes cronicas/permanentes): rotas JSON.

Regra de permissao (decisao): LER usa atendimentos:ver; MARCAR/ENCERRAR usa atendimentos:editar (mesma trava do salvar atendimento),
tanto aqui quanto na secao "Condicoes ativas" do Cadastro do paciente. Quem so tem permissao de editar Cadastro/Pacientes recebe 403.
Sempre isolado por clinica_id da sessao. Logs levam so ids (nunca nome/CPF/CID do paciente).
"""
from __future__ import annotations

from flask import abort, jsonify, request, session

from db import conectar_db

from . import atendimentos_bp
from .helpers import (
    CID_STATUS_ATIVO,
    ensure_paciente_cids_ativos_schema,
    encerrar_cid_ativo,
    listar_cids_ativos,
    registrar_cid_ativo,
)

try:
    from admin.modulos import (
        get_clinica_id_contexto,
        require_permission,
        usuario_eh_master,
        usuario_tem_permissao,
    )
except Exception:  # pragma: no cover
    def require_permission(modulo_codigo: str, acao: str = "ver"):
        def deco(fn):
            return fn
        return deco

    def usuario_eh_master() -> bool:
        return False

    def usuario_tem_permissao(*a, **k) -> bool:
        return False

    def get_clinica_id_contexto(default=1) -> int:
        return default

try:
    from log import registrar_log, log_erro
except Exception:  # pragma: no cover
    def registrar_log(*a, **k): pass
    def log_erro(*a, **k): pass

MODULO = "atendimentos"


def _clinica_id() -> int:
    try:
        return int(session.get("clinica_id"))
    except (TypeError, ValueError):
        abort(403)


def _usuario_id() -> int | None:
    for k in ("usuario_id", "user_id", "id"):
        try:
            v = int(session.get(k))
            if v:
                return v
        except (TypeError, ValueError):
            continue
    return None


def pode_gerir_cids_ativos() -> bool:
    """True se a sessao pode MARCAR/ENCERRAR CID ativo (= atendimentos:editar). Usado para mostrar/esconder botoes; o servidor
    sempre confere de novo com require_permission."""
    try:
        if usuario_eh_master():
            return True
        uid, cid = _usuario_id(), get_clinica_id_contexto()
        return bool(uid and cid and usuario_tem_permissao(int(uid), int(cid), MODULO, "editar"))
    except Exception:
        return False


def _paciente_da_clinica(conn, paciente_id: int, clinica_id: int) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pacientes WHERE id = %s AND clinica_id = %s LIMIT 1", (paciente_id, clinica_id))
    return cur.fetchone() is not None


def _erro(msg: str, status: int, **extra):
    return jsonify(ok=False, error=msg, **extra), status


@atendimentos_bp.get("/api/pacientes/<int:paciente_id>/cids_ativos")
@require_permission(MODULO, "ver")
def api_cids_ativos_listar(paciente_id: int):
    clinica_id = _clinica_id()
    try:
        with conectar_db() as conn:
            ensure_paciente_cids_ativos_schema(conn)
            if not _paciente_da_clinica(conn, paciente_id, clinica_id):
                return _erro("Paciente não encontrado nesta clínica.", 404)
            itens = listar_cids_ativos(conn, clinica_id, paciente_id, CID_STATUS_ATIVO)
        return jsonify(ok=True, items=itens, pode_gerir=pode_gerir_cids_ativos())
    except Exception as e:
        log_erro(MODULO, e, entidade="paciente_cids_ativos", descricao="Erro ao listar CIDs ativos.", detalhes={"paciente_id": paciente_id})
        return _erro("Não foi possível carregar as condições ativas agora.", 500)


@atendimentos_bp.post("/api/pacientes/<int:paciente_id>/cids_ativos")
@require_permission(MODULO, "editar")
def api_cids_ativos_adicionar(paciente_id: int):
    """Adiciona manualmente (sem atendimento). Body JSON: {"cid_codigo": "F84.0"}."""
    clinica_id = _clinica_id()
    dados = request.get_json(silent=True) or {}
    from documentos.cid import valida_cid_atendimento   # import tardio: documentos importa atendimentos.helpers

    try:
        with conectar_db() as conn:
            ensure_paciente_cids_ativos_schema(conn)
            if not _paciente_da_clinica(conn, paciente_id, clinica_id):
                return _erro("Paciente não encontrado nesta clínica.", 404)

            codigo, erro = valida_cid_atendimento(conn, dados.get("cid_codigo"))
            if erro:
                return _erro(erro, 400)
            if not codigo:
                return _erro("Informe o CID da condição.", 400)

            resultado, novo_id = registrar_cid_ativo(conn, clinica_id, paciente_id, codigo, _usuario_id())
            conn.commit()
            itens = listar_cids_ativos(conn, clinica_id, paciente_id, CID_STATUS_ATIVO)

        if resultado == "ja_ativo":
            return _erro(f"O CID {codigo} já é uma condição ativa deste paciente.", 409, items=itens)

        registrar_log(modulo=MODULO, acao="cid_ativo_marcar", entidade="paciente_cids_ativos", entidade_id=novo_id,
                      descricao="CID ativo adicionado ao paciente.", detalhes={"clinica_id": clinica_id, "paciente_id": paciente_id, "origem": "cadastro"})
        return jsonify(ok=True, id=novo_id, items=itens), 201
    except Exception as e:
        log_erro(MODULO, e, entidade="paciente_cids_ativos", descricao="Erro ao adicionar CID ativo.", detalhes={"paciente_id": paciente_id})
        return _erro("Não foi possível adicionar a condição agora.", 500)


@atendimentos_bp.post("/api/cids_ativos/<int:cid_ativo_id>/resolver")
@require_permission(MODULO, "editar")
def api_cids_ativos_resolver(cid_ativo_id: int):
    clinica_id = _clinica_id()
    try:
        with conectar_db() as conn:
            ensure_paciente_cids_ativos_schema(conn)
            resultado, paciente_id = encerrar_cid_ativo(conn, clinica_id, cid_ativo_id, _usuario_id())
            conn.commit()
            itens = listar_cids_ativos(conn, clinica_id, paciente_id, CID_STATUS_ATIVO) if paciente_id else []

        if resultado == "nao_encontrado":
            return _erro("Condição não encontrada nesta clínica.", 404)
        if resultado == "ja_resolvido":
            return _erro("Esta condição já foi encerrada.", 409, items=itens)

        registrar_log(modulo=MODULO, acao="cid_ativo_resolver", entidade="paciente_cids_ativos", entidade_id=cid_ativo_id,
                      descricao="CID ativo do paciente encerrado.", detalhes={"clinica_id": clinica_id, "paciente_id": paciente_id})
        return jsonify(ok=True, paciente_id=paciente_id, items=itens)
    except Exception as e:
        log_erro(MODULO, e, entidade="paciente_cids_ativos", descricao="Erro ao encerrar CID ativo.", detalhes={"id": cid_ativo_id})
        return _erro("Não foi possível encerrar a condição agora.", 500)
