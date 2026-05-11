from flask import Blueprint

clinica_config_bp = Blueprint(
    "clinica_config",
    __name__,
    template_folder="templates",
    static_folder="static",
    url_prefix="/clinica-config"
)

from . import routes