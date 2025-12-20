from flask import Blueprint

pts_bp = Blueprint(
    "pts",
    __name__,
    url_prefix="/pts",
    template_folder="templates",
    static_folder="static",
)

from . import routes  # noqa: E402
