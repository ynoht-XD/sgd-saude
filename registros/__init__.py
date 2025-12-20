# registros/__init__.py
from flask import Blueprint

registros_bp = Blueprint(
    "registros",
    __name__,
    template_folder="templates",
    static_folder="static",
    # sem static_url_path -> usa o padrão "/static" combinado com o url_prefix
)

from . import routes  # noqa
