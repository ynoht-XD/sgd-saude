from flask import Blueprint

meus_atendimentos_bp = Blueprint(
    "meus_atendimentos",
    __name__,
    url_prefix="/meus_atendimentos",
    template_folder="templates",
    static_folder="static",
    static_url_path="/meus_atendimentos/static",  # ✅ IMPORTANTE
)

from . import routes  # noqa
