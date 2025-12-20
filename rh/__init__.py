# sgd/rh/__init__.py
from flask import Blueprint

rh_bp = Blueprint(
    'rh',
    __name__,
    url_prefix='/rh',                # tudo do RH ficará em /rh/...
    template_folder='templates',     # sgd/rh/templates
    static_folder='static',          # sgd/rh/static
    static_url_path='/rh/static'     # para servir CSS/JS do módulo
)

from . import routes  # noqa: E402,F401
