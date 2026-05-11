from functools import wraps
from datetime import date, datetime

from flask import render_template, request, jsonify, session, abort

from . import logs_bp
from db import conectar_db


LOG_TABLE = "logs_sistema"


def is_master_user():
    role = str(session.get("role") or "").upper()

    return bool(
        session.get("is_master")
        or session.get("is_superuser")
        or role in ("MASTER", "ROOT", "SUPERADMIN")
    )


def master_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not is_master_user():
            abort(403)

        return fn(*args, **kwargs)

    return wrapper


def json_safe(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}

    if isinstance(value, list):
        return [json_safe(v) for v in value]

    return value


def row_safe(row):
    return {k: json_safe(v) for k, v in dict(row).items()}


@logs_bp.route("/")
@master_required
def index():
    return render_template("logs/index.html")


@logs_bp.route("/api/listar")
@master_required
def api_listar_logs():
    page = request.args.get("page", 1, type=int)

    if page < 1:
        page = 1

    per_page = 20
    offset = (page - 1) * per_page

    profissional = (request.args.get("profissional") or "").strip()
    clinica = (request.args.get("clinica") or "").strip()
    paciente = (request.args.get("paciente") or "").strip()
    acao = (request.args.get("acao") or "").strip()
    modulo = (request.args.get("modulo") or "").strip()
    entidade = (request.args.get("entidade") or "").strip()
    sucesso = (request.args.get("sucesso") or "").strip()
    data_ini = (request.args.get("data_ini") or "").strip()
    data_fim = (request.args.get("data_fim") or "").strip()

    where = []
    params = {}

    if profissional:
        where.append(
            """
            (
                usuario_nome ILIKE %(profissional)s
                OR usuario_cpf ILIKE %(profissional)s
                OR usuario_role ILIKE %(profissional)s
            )
            """
        )
        params["profissional"] = f"%{profissional}%"

    if clinica:
        where.append(
            """
            (
                clinica_nome ILIKE %(clinica)s
                OR clinica_id::TEXT = %(clinica_id)s
            )
            """
        )
        params["clinica"] = f"%{clinica}%"
        params["clinica_id"] = clinica

    if paciente:
        where.append(
            """
            (
                paciente_nome ILIKE %(paciente)s
                OR entidade ILIKE %(paciente)s
                OR entidade_id ILIKE %(paciente)s
                OR descricao ILIKE %(paciente)s
                OR detalhes_json::TEXT ILIKE %(paciente)s
            )
            """
        )
        params["paciente"] = f"%{paciente}%"
        
    if acao:
        where.append("acao ILIKE %(acao)s")
        params["acao"] = f"%{acao}%"

    if modulo:
        where.append("modulo ILIKE %(modulo)s")
        params["modulo"] = f"%{modulo}%"

    if entidade:
        where.append("entidade ILIKE %(entidade)s")
        params["entidade"] = f"%{entidade}%"

    if sucesso in ("true", "false"):
        where.append("sucesso = %(sucesso)s")
        params["sucesso"] = sucesso == "true"

    if data_ini:
        where.append("criado_em >= %(data_ini)s::date")
        params["data_ini"] = data_ini

    if data_fim:
        where.append("criado_em < (%(data_fim)s::date + INTERVAL '1 day')")
        params["data_fim"] = data_fim

    where_sql = "WHERE " + " AND ".join(where) if where else ""

    try:
        with conectar_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT COUNT(*) AS total
                    FROM {LOG_TABLE}
                    {where_sql}
                    """,
                    params,
                )

                total_row = cur.fetchone()
                total = total_row["total"] if total_row else 0

                params["limit"] = per_page
                params["offset"] = offset

                cur.execute(
                    f"""
                    SELECT
                        id,
                        clinica_id,
                        clinica_nome,
                        usuario_id,
                        usuario_nome,
                        usuario_cpf,
                        usuario_role,
                        modulo,
                        acao,
                        entidade,
                        entidade_id,
                        paciente_nome,
                        descricao,
                        detalhes_json,
                        sucesso,
                        erro_tipo,
                        erro_mensagem,
                        ip,
                        user_agent,
                        metodo,
                        caminho,
                        endpoint,
                        criado_em
                    FROM {LOG_TABLE}
                    {where_sql}
                    ORDER BY criado_em DESC NULLS LAST, id DESC
                    LIMIT %(limit)s OFFSET %(offset)s
                    """,
                    params,
                )
                            
                rows = [row_safe(row) for row in cur.fetchall()]

        return jsonify({
            "ok": True,
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": max((total + per_page - 1) // per_page, 1),
            "rows": rows,
        })

    except Exception as e:
        print("Erro ao listar logs:", e)

        return jsonify({
            "ok": False,
            "erro": "Erro ao buscar logs no banco.",
        }), 500