# -*- coding: utf-8 -*-
from __future__ import annotations

"""
pacientes/routes.py
-------------------

Arquivo central do módulo Pacientes.

Responsabilidades:
- Expor helpers principais do módulo.
- Importar os arquivos que registram rotas no blueprint `pacientes_bp`.
- Manter compatibilidade com imports antigos.

Importante:
As regras de:
- clinica_id
- logs
- módulos/permissões

ficam aplicadas nos arquivos que possuem rotas reais:
- pacientes.py
- exports.py
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

# ============================================================
# ROTAS DO MÓDULO
# ============================================================
# Estes imports registram as rotas no blueprint pacientes_bp.
# Não remova, mesmo que pareçam "sem uso".
from . import pacientes  # noqa: F401,E402
from . import exports    # noqa: F401,E402
from . import pacientes_master  # noqa: F401,E402

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