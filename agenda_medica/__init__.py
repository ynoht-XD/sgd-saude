from flask import Blueprint

agenda_medica_bp = Blueprint(
    "agenda_medica",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static",
    url_prefix="/agenda-medica",
)

from . import routes