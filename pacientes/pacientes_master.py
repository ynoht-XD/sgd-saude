# -*- coding: utf-8 -*-
from __future__ import annotations

from flask import render_template, request, redirect, url_for, flash, session, abort, jsonify

from . import pacientes_bp
from .helpers import (
    get_conn,
    ensure_pacientes_schema,
    fetchall_dicts,
    fetchone_dict,
    table_columns,
)

try:
    from admin.modulos import require_permission, usuario_eh_master
except Exception:
    def require_permission(modulo_codigo: str, acao: str = "ver"):
        def deco(fn):
            return fn
        return deco

    def usuario_eh_master():
        return bool(session.get("is_master") or session.get("is_superuser"))

try:
    from log import registrar_log, log_erro
except Exception:
    def registrar_log(*args, **kwargs): pass
    def log_erro(*args, **kwargs): pass


# =============================================================================
# HELPERS MASTER
# =============================================================================

def _master_required():
    if not usuario_eh_master():
        abort(403)


def _ensure_schema_master(conn):
    ensure_pacientes_schema(conn)

    cols = table_columns(conn, "pacientes")
    cur = conn.cursor()

    if "clinica_id" not in cols:
        cur.execute("ALTER TABLE pacientes ADD COLUMN IF NOT EXISTS clinica_id INTEGER;")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS clinicas (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            ativo BOOLEAN DEFAULT TRUE,
            ativa BOOLEAN DEFAULT TRUE,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_pacientes_master_clinica
        ON pacientes(clinica_id);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_pacientes_master_nome
        ON pacientes(nome);
    """)

    conn.commit()


def _listar_clinicas(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT id, nome, COALESCE(ativa, ativo, TRUE) AS ativa
          FROM clinicas
         WHERE COALESCE(ativa, ativo, TRUE) = TRUE
         ORDER BY id ASC;
    """)
    return fetchall_dicts(cur)


def _idade_sql():
    return """
    CASE
        WHEN nascimento IS NULL OR TRIM(nascimento::text) = '' THEN
            NULL::integer

        WHEN nascimento::text ~ '^\\d{4}-\\d{2}-\\d{2}' THEN
            DATE_PART('year', AGE(CURRENT_DATE, nascimento::date))::integer

        WHEN nascimento::text ~ '^\\d{2}/\\d{2}/\\d{4}' THEN
            DATE_PART(
                'year',
                AGE(
                    CURRENT_DATE,
                    TO_DATE(SUBSTRING(nascimento::text FROM 1 FOR 10), 'DD/MM/YYYY')
                )
            )::integer

        WHEN idade IS NULL OR TRIM(idade::text) = '' THEN
            NULL::integer

        WHEN idade::text ~ '^\\d+$' THEN
            idade::integer

        ELSE
            NULL::integer
    END
    """

# =============================================================================
# PAINEL MASTER DE PACIENTES
# =============================================================================

@pacientes_bp.route("/master/pacientes", methods=["GET"])
@require_permission("pacientes", "ver")
def pacientes_master_listar():
    _master_required()

    q = (request.args.get("q") or "").strip()
    status_vinculo = (request.args.get("status_vinculo") or "").strip()

    conn = get_conn()

    try:
        _ensure_schema_master(conn)

        clinicas = _listar_clinicas(conn)

        where = []
        params = []

        if q:
            where.append("""
                (
                    p.nome ILIKE %s
                    OR p.cpf ILIKE %s
                    OR p.cns ILIKE %s
                    OR p.prontuario ILIKE %s
                )
            """)
            like = f"%{q}%"
            params.extend([like, like, like, like])

        if status_vinculo == "sem_clinica":
            where.append("p.clinica_id IS NULL")
        elif status_vinculo == "com_clinica":
            where.append("p.clinica_id IS NOT NULL")

        where_sql = "WHERE " + " AND ".join(where) if where else ""

        cur = conn.cursor()
        cur.execute(f"""
            SELECT
                p.id,
                p.nome,
                {_idade_sql()} AS idade,
                COALESCE(NULLIF(p.telefone, ''), NULLIF(p.telefone1, ''), '') AS telefone,
                p.cpf,
                p.cns,
                p.prontuario,
                p.clinica_id,
                c.nome AS clinica_nome
            FROM pacientes p
            LEFT JOIN clinicas c ON c.id = p.clinica_id
            {where_sql}
            ORDER BY
                CASE WHEN p.clinica_id IS NULL THEN 0 ELSE 1 END,
                p.id DESC
            LIMIT 1000;
        """, params)

        pacientes = fetchall_dicts(cur)

        registrar_log(
            modulo="pacientes",
            acao="visualizar_master",
            entidade="pacientes",
            descricao="Master visualizou painel geral de pacientes.",
            detalhes={
                "q": q,
                "status_vinculo": status_vinculo,
                "total": len(pacientes),
            },
        )

        return render_template(
            "pacientes_master.html",
            pacientes=pacientes,
            clinicas=clinicas,
            q=q,
            status_vinculo=status_vinculo,
        )

    except Exception as e:
        log_erro(
            "pacientes",
            e,
            entidade="pacientes",
            descricao="Erro ao abrir painel master de pacientes.",
            detalhes={"q": q, "status_vinculo": status_vinculo},
        )
        return f"Erro ao abrir painel master de pacientes: {e}", 500

    finally:
        conn.close()


# =============================================================================
# VINCULAR PACIENTE A CLÍNICA
# =============================================================================

@pacientes_bp.route("/master/pacientes/<int:paciente_id>/vincular-clinica", methods=["POST"])
@require_permission("pacientes", "editar")
def pacientes_master_vincular_clinica(paciente_id: int):
    _master_required()

    clinica_id = request.form.get("clinica_id", type=int)

    if not clinica_id:
        flash("Selecione uma clínica.", "error")
        return redirect(request.referrer or url_for("pacientes.pacientes_master_listar"))

    conn = get_conn()

    try:
        _ensure_schema_master(conn)

        cur = conn.cursor()

        cur.execute("SELECT id, nome, clinica_id FROM pacientes WHERE id = %s LIMIT 1;", (paciente_id,))
        paciente = fetchone_dict(cur)

        if not paciente:
            flash("Paciente não encontrado.", "error")
            return redirect(request.referrer or url_for("pacientes.pacientes_master_listar"))

        cur.execute("SELECT id, nome FROM clinicas WHERE id = %s LIMIT 1;", (clinica_id,))
        clinica = fetchone_dict(cur)

        if not clinica:
            flash("Clínica não encontrada.", "error")
            return redirect(request.referrer or url_for("pacientes.pacientes_master_listar"))

        clinica_antiga = paciente.get("clinica_id")

        cur.execute("""
            UPDATE pacientes
               SET clinica_id = %s
             WHERE id = %s;
        """, (clinica_id, paciente_id))

        conn.commit()

        registrar_log(
            modulo="pacientes",
            acao="vincular_clinica",
            entidade="pacientes",
            entidade_id=paciente_id,
            descricao="Master vinculou paciente a uma clínica.",
            detalhes={
                "paciente_id": paciente_id,
                "paciente_nome": paciente.get("nome"),
                "clinica_id_antiga": clinica_antiga,
                "clinica_id_nova": clinica_id,
                "clinica_nome_nova": clinica.get("nome"),
            },
        )

        flash("Paciente vinculado à clínica com sucesso.", "success")
        return redirect(request.referrer or url_for("pacientes.pacientes_master_listar"))

    except Exception as e:
        conn.rollback()

        log_erro(
            "pacientes",
            e,
            entidade="pacientes",
            entidade_id=paciente_id,
            descricao="Erro ao vincular paciente a clínica.",
            detalhes={"clinica_id": clinica_id},
        )

        flash(f"Erro ao vincular paciente: {e}", "error")
        return redirect(request.referrer or url_for("pacientes.pacientes_master_listar"))

    finally:
        conn.close()


# =============================================================================
# API RESUMO
# =============================================================================

@pacientes_bp.route("/master/pacientes/api/resumo")
@require_permission("pacientes", "ver")
def pacientes_master_resumo():
    _master_required()

    conn = get_conn()

    try:
        _ensure_schema_master(conn)

        cur = conn.cursor()
        cur.execute("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE clinica_id IS NULL) AS sem_clinica,
                COUNT(*) FILTER (WHERE clinica_id IS NOT NULL) AS com_clinica
            FROM pacientes;
        """)

        resumo = fetchone_dict(cur) or {}

        return jsonify({"ok": True, "resumo": resumo})

    except Exception as e:
        log_erro(
            "pacientes",
            e,
            entidade="pacientes",
            descricao="Erro ao gerar resumo master de pacientes.",
        )
        return jsonify({"ok": False, "erro": str(e)}), 500

    finally:
        conn.close()