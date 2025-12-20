# sgd/digitador/__init__.py
from flask import Blueprint

digitador_bp = Blueprint(
    "digitador",
    __name__,
    url_prefix="/digitador",
    template_folder="templates",
    static_folder="static",
    static_url_path="/digitador/static",
)

from . import routes  # noqa: E402,F401
