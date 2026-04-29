# -*- coding: utf-8 -*-
from __future__ import annotations

"""
routes.py
---------
Arquivo central do módulo pacientes.

Responsabilidades:
- carregar helpers do módulo
- carregar rotas de pacientes
- carregar rotas de exportação

Observação:
As rotas são registradas ao importar os módulos abaixo,
pois eles usam decorators em `pacientes_bp`.
"""

from .helpers import (
    get_conn,
    has_table,
    table_columns,
    ensure_column,
    ensure_pacientes_schema,
    fetchone_dict,
    fetchall_dicts,
    to_upper,
    upperize_payload,
    calc_idade,
    parse_dt_flex,
    enriquecer_agendamento_row,
    json_list,
    split_profissionais,
    map_cbo_por_profissionais,
    enriquecer_com_prof_cbo,
    get_primeiro_agendamento_por_paciente,
    fetch_agendamentos_por_paciente,
    where_and_params,
    fetch_pacientes_list,
    headers_padrao,
    fmt,
    join_addr,
    tags_human,
)

# Importa os módulos que efetivamente registram rotas no blueprint
from . import pacientes  # noqa: F401
from . import exports    # noqa: F401


__all__ = [
    "get_conn",
    "has_table",
    "table_columns",
    "ensure_column",
    "ensure_pacientes_schema",
    "fetchone_dict",
    "fetchall_dicts",
    "to_upper",
    "upperize_payload",
    "calc_idade",
    "parse_dt_flex",
    "enriquecer_agendamento_row",
    "json_list",
    "split_profissionais",
    "map_cbo_por_profissionais",
    "enriquecer_com_prof_cbo",
    "get_primeiro_agendamento_por_paciente",
    "fetch_agendamentos_por_paciente",
    "where_and_params",
    "fetch_pacientes_list",
    "headers_padrao",
    "fmt",
    "join_addr",
    "tags_human",
]