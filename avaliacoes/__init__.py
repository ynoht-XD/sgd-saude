from flask import Blueprint

avaliacoes_bp = Blueprint(
    "avaliacoes",
    __name__,
    template_folder="templates",
    static_folder="static",
    url_prefix="/avaliacoes"
)

from . import routes  # noqa: E402,F401