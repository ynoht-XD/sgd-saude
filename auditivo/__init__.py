# auditivo/__init__.py
from flask import Blueprint

auditivo_bp = Blueprint(
    "auditivo",
    __name__,
    url_prefix="/auditivo",
    template_folder="templates",
    static_folder="static",
    static_url_path="/auditivo/static",
)

from . import routes  # noqa
