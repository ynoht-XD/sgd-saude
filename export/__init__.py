from flask import Blueprint

export_bp = Blueprint(
    "export",
    __name__,
    url_prefix="/export",                 # << aqui
    template_folder="templates",
    static_folder="static",
    static_url_path="/export/static"      # << aqui (coerente com outros módulos)
)

from . import routes
