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

from . import routes
