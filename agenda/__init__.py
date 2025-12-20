# agenda/__init__.py
from flask import Blueprint
agenda_bp = Blueprint(
    "agenda", __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/agenda/static/agenda"
)

from . import routes  # noqa: F401
