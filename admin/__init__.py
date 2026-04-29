# admin/__init__.py
from __future__ import annotations

from functools import wraps

from flask import Blueprint, session, abort, redirect, url_for, flash


admin_bp = Blueprint(
    "admin",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/admin/static",
)


def get_usuario_sessao() -> dict:
    return (
        session.get("usuario")
        or session.get("user")
        or session.get("auth_user")
        or {}
    )


def is_master() -> bool:
    usuario = get_usuario_sessao()

    role = str(
        session.get("role")
        or usuario.get("role")
        or ""
    ).upper()

    return (
        role in {"MASTER", "ROOT", "SUPERADMIN"}
        or session.get("is_master") is True
        or session.get("is_superuser") is True
        or usuario.get("is_master") is True
        or usuario.get("is_superuser") is True
    )


def is_admin() -> bool:
    usuario = get_usuario_sessao()

    role = str(
        session.get("role")
        or usuario.get("role")
        or ""
    ).upper()

    return role == "ADMIN" or is_master()


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Faça login para continuar.", "warning")
            return redirect(url_for("auth.login"))

        if not is_admin():
            abort(403)

        return f(*args, **kwargs)

    return wrapper


def master_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Faça login para continuar.", "warning")
            return redirect(url_for("auth.login"))

        if not is_master():
            abort(403)

        return f(*args, **kwargs)

    return wrapper


# Importa as rotas no final para evitar import circular
from . import routes  # noqa: F401