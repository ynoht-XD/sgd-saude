from flask import Blueprint

financeiro_bp = Blueprint(
    "financeiro",
    __name__,
    url_prefix="/financeiro",
    template_folder="templates",
    static_folder="static",
)

from . import routes