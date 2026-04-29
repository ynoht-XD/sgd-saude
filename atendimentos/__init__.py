# atendimentos/__init__.py
from flask import Blueprint

atendimentos_bp = Blueprint(
    'atendimentos',
    __name__,
    url_prefix='/atendimentos',        # <<< importante
    template_folder='templates',
    static_folder='static',
    static_url_path='/atendimentos/static'
)
# Importa depois de criar o blueprint
from . import routes  # noqa: E402,F401
from . import lista_atendimentos  # noqa: E402,F401
from . import historico  # noqa: E402,F401

from . import routes
