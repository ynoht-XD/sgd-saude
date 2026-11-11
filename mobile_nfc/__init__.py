from flask import Blueprint

mobile_nfc_bp = Blueprint(
    "mobile_nfc",
    __name__,
    template_folder="templates"
)

from . import auth
from . import etiquetas
from . import frequencia_nfc
from . import controle_freq