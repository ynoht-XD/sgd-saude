# sgd/procedimentos/__init__.py
from flask import Blueprint

procedimentos_bp = Blueprint(
    "procedimentos",
    __name__,
    template_folder="templates",
    static_folder="static",
    url_prefix="/procedimentos",
)


from . import routes  # noqa: F401
