# sgd/avaliacoes/__init__.py
from flask import Blueprint

avaliacoes_bp = Blueprint(
    "avaliacoes",
    __name__,
    template_folder="templates",
    static_folder="static",
    url_prefix="/avaliacoes"
)

# ⚠️ ESSENCIAL: isso carrega as rotas do blueprint
from . import routes  # noqa: E402,F401
