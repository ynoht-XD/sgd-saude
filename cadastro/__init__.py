from flask import Blueprint

cadastro_bp = Blueprint(
    'cadastro', __name__,
    template_folder='templates',
    static_folder='static',                  # 👈 precisa disso
    static_url_path='/static/cadastro'       # 👈 define o caminho de acesso
)

from . import routes
