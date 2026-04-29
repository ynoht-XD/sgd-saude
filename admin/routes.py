# admin/routes.py
from __future__ import annotations

"""
Arquivo central de rotas do módulo admin.

Responsabilidade:
- importar os submódulos para registrar as rotas no blueprint admin_bp
- não conter regras de negócio
- não conter helpers
- não conter schema
"""

from . import admin_bp

# Importa os módulos para registrar suas rotas no blueprint.
# Os imports parecem "não usados", mas são intencionais.
from . import users       # noqa: F401
from . import bibliotecas # noqa: F401
from . import modulos     # noqa: F401
from . import backup     # noqa: F401

# backup ficará por último, quando formos fechar a estratégia final
# entre SQLite local e PostgreSQL/Render.
# from . import backup    # noqa: F401
