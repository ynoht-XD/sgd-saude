from flask import Blueprint

procedimentos_bp = Blueprint(
    "procedimentos",
    __name__,
    url_prefix="/procedimentos",
    template_folder="templates",
    static_folder="static",
)

from . import routes  # noqa