# sgd/financeiro/__init__.py
from flask import Blueprint

financeiro_bp = Blueprint(
    "financeiro",
    __name__,
    url_prefix="/financeiro",        # tudo do Financeiro fica sob /financeiro/...
    template_folder="templates",     # sgd/financeiro/templates
    static_folder="static",          # sgd/financeiro/static
    static_url_path="/financeiro/static",
)

from . import routes  # noqa: E402,F401
