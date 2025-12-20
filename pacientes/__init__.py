from flask import Blueprint

pacientes_bp = Blueprint(
    "pacientes",
    __name__,
    template_folder="templates",
    static_folder="static",
    url_prefix="/pacientes"
)

from . import routes  # noqa
