from flask import Blueprint

logs_bp = Blueprint(
    "logs",
    __name__,
    url_prefix="/logs",
    template_folder="templates",
    static_folder="static",
    static_url_path="/logs/static",
)

from . import routes