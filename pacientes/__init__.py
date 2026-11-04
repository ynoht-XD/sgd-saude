from flask import Blueprint

pacientes_bp = Blueprint(
    "pacientes",
    __name__,
    template_folder="templates",
    static_folder="static",
    url_prefix="/pacientes"
)

# Rotas existentes
from . import routes  # noqa

# Frequência digital e estação de assinatura
# TODO: reativar quando a decisão sobre a estação/tablet estiver tomada
# e o template pacientes/frequencia_assinatura.html existir.
# from . import frequencia  # noqa