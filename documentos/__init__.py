# documentos/__init__.py
"""Documentos medicos emitidos a partir de um atendimento (receita, atestado, declaracao, encaminhamento,
solicitacao de exame). Uma tabela unica (`documentos_atendimento`); novo tipo = novo valor em `tipo` + um
validador em `validacao.py` (sem migracao de schema)."""
from flask import Blueprint

documentos_bp = Blueprint(
    "documentos",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/documentos/static",
)

from . import routes  # noqa: E402,F401
