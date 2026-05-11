# admin/users_master.py

from __future__ import annotations

from flask import render_template, request, redirect, url_for, flash, abort, session

from . import admin_bp, admin_required
from .helpers import db_conn, list_columns

try:
    from .modulos import require_permission, usuario_eh_master
except Exception:
    def require_permission(modulo_codigo: str, acao: str = "ver"):
        def deco(fn):
            return fn
        return deco

    def usuario_eh_master():
        return bool(session.get("is_master") or session.get("is_superuser"))

try:
    from log import registrar_log, log_erro, log_edicao
except Exception:
    def registrar_log(*args, **kwargs): pass
    def log_erro(*args, **kwargs): pass
    def log_edicao(*args, **kwargs): pass


def _master_only():
    if not usuario_eh_master():
        abort(403)


def _fetchall(cur):
    rows = cur.fetchall() or []
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) if not isinstance(r, dict) else dict(r) for r in rows]


def _fetchone(cur):
    row = cur.fetchone()
    if not row:
        return None
    if isinstance(row, dict):
        return dict(row)
    cols = [c[0] for c in cur.description]
    return dict(zip(cols, row))


def _normalizar_role(role):
    role = (role or "").strip().upper()
    if role == "RECEPÇÃO":
        return "RECEPCAO"
    if role == "PROFISSIONAIS":
        return "PROFISSIONAL"
    if role not in {"ADMIN", "RECEPCAO", "PROFISSIONAL", "MASTER", "ROOT", "SUPERADMIN"}:
        return "RECEPCAO"
    return role


def _int_or_none(v):
    try:
        v = str(v or "").strip()
        return int(v) if v else None
    except Exception:
        return None


def _redirect_master():
    return redirect(url_for("admin.usuarios_master"))


def _clinica_existe(conn, clinica_id):
    if not clinica_id:
        return False

    cur = conn.cursor()
    cur.execute("SELECT 1 FROM clinicas WHERE id = %s LIMIT 1;", (clinica_id,))
    return cur.fetchone() is not None


@admin_bp.route("/usuarios/master")
@admin_required
def usuarios_master():
    _master_only()

    conn = None
    usuarios = []
    clinicas = []

    try:
        conn = db_conn(True)

        try:
            conn.rollback()
        except Exception:
            pass

        cur = conn.cursor()

        cur.execute("""
            SELECT
                id,
                nome,
                cnpj
            FROM clinicas
            ORDER BY nome ASC;
        """)
        clinicas = _fetchall(cur)

        cur.execute("""
            SELECT
                u.id,
                COALESCE(u.nome, '') AS nome,
                COALESCE(u.cpf, '') AS cpf,
                COALESCE(u.cbo, '') AS cbo,
                COALESCE(u.cbo_descricao, '') AS cbo_descricao,
                COALESCE(u.role, 'RECEPCAO') AS role,
                u.clinica_id,
                TRUE AS is_active,
                CASE
                    WHEN UPPER(COALESCE(u.role, '')) IN ('MASTER', 'ROOT', 'SUPERADMIN')
                    THEN TRUE ELSE FALSE
                END AS is_master,
                CASE
                    WHEN UPPER(COALESCE(u.role, '')) IN ('MASTER', 'ROOT', 'SUPERADMIN')
                    THEN TRUE ELSE FALSE
                END AS is_superuser,
                NULL::TEXT AS email,
                c.nome AS clinica_nome,
                c.cnpj AS clinica_cnpj
            FROM usuarios u
            LEFT JOIN clinicas c
                   ON c.id = u.clinica_id
            ORDER BY
                CASE
                    WHEN u.clinica_id IS NULL THEN 0
                    WHEN c.id IS NULL THEN 1
                    ELSE 2
                END ASC,
                COALESCE(u.clinica_id, 999999),
                COALESCE(u.nome, '') ASC;
        """)

        usuarios = _fetchall(cur)

    except Exception as e:
        if conn:
            conn.rollback()

        flash(f"Erro ao carregar usuários master: {e}", "error")

    finally:
        if conn:
            conn.close()

    return render_template(
        "users_master.html",
        usuarios=usuarios,
        clinicas=clinicas,
    )


@admin_bp.route("/usuarios/master/<int:uid>/designar", methods=["POST"])
@admin_required
def usuarios_master_designar(uid):
    _master_only()

    conn = None

    try:
        clinica_id = _int_or_none(request.form.get("clinica_id"))
        role = _normalizar_role(request.form.get("role"))
        observacao = (request.form.get("observacao") or "").strip()

        if not clinica_id:
            raise ValueError("Informe o ID da clínica.")

        conn = db_conn(False)

        if not _clinica_existe(conn, clinica_id):
            raise ValueError("Clínica não encontrada.")

        cur = conn.cursor()

        cur.execute("""
            SELECT id, nome, role, clinica_id
              FROM usuarios
             WHERE id = %s
             LIMIT 1;
        """, (uid,))

        usuario = _fetchone(cur)

        if not usuario:
            flash("Usuário não encontrado.", "error")
            return _redirect_master()

        cur.execute("""
            UPDATE usuarios
               SET clinica_id = %s,
                   role = %s
             WHERE id = %s;
        """, (clinica_id, role, uid))

        conn.commit()

        log_edicao(
            modulo="admin_users_master",
            entidade="usuarios",
            entidade_id=uid,
            descricao="Usuário designado pelo painel Master.",
            detalhes={
                "usuario": usuario.get("nome"),
                "clinica_anterior": usuario.get("clinica_id"),
                "clinica_nova": clinica_id,
                "role_anterior": usuario.get("role"),
                "role_nova": role,
                "observacao": observacao,
            },
        )

        flash("Usuário atualizado com sucesso.", "success")

    except Exception as e:
        if conn:
            conn.rollback()

        log_erro(
            "admin_users_master",
            e,
            entidade="usuarios",
            entidade_id=uid,
            descricao="Erro ao designar usuário pelo painel Master.",
        )

        flash(f"Erro ao designar usuário: {e}", "error")

    finally:
        if conn:
            conn.close()

    return _redirect_master()