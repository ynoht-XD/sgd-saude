# admin/__init__.py
from flask import Blueprint, session, abort
from functools import wraps

# Blueprint do Admin
admin_bp = Blueprint(
    "admin",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/admin/static",
)

# Decorator para restringir rotas ao ADMIN
# (Se o login ainda não estiver pronto, basta não usar esse decorator nas rotas por enquanto.)
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        role = session.get("role")
        if role != "ADMIN":
            abort(403)
        return f(*args, **kwargs)
    return wrapper

# Importa as rotas (mantém no final para evitar import circular)
from . import routes  # noqa: F401
