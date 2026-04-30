# admin/modulos.py
from __future__ import annotations

import re
from functools import wraps

from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    abort,
    jsonify,
)

from . import admin_bp, admin_required

try:
    from db import conectar_db
except ImportError:
    conectar_db = None


# =============================================================================
# MÓDULOS OFICIAIS DO SISTEMA
# =============================================================================

MODULOS_DISPONIVEIS = [
    {
        "codigo": "dashboard",
        "nome": "Início",
        "descricao": "Tela inicial com visão geral do sistema.",
        "icone": "home",
        "ordem": 1,
        "categoria": "Geral",
    },
    {
        "codigo": "agenda",
        "nome": "Agenda",
        "descricao": "Agenda médica, horários e marcações.",
        "icone": "calendar",
        "ordem": 2,
        "categoria": "Operacional",
    },
    {
        "codigo": "meus_atendimentos",
        "nome": "Meus Atendimentos",
        "descricao": "Área do profissional para visualizar e registrar seus atendimentos.",
        "icone": "activity",
        "ordem": 3,
        "categoria": "Operacional",
    },
    {
        "codigo": "cadastro",
        "nome": "Cadastro",
        "descricao": "Cadastro geral e entrada inicial de informações.",
        "icone": "clipboard",
        "ordem": 4,
        "categoria": "Operacional",
    },
    {
        "codigo": "lista_atendimentos",
        "nome": "Lista de Atendimentos",
        "descricao": "Fila, organização e controle dos atendimentos.",
        "icone": "list",
        "ordem": 5,
        "categoria": "Operacional",
    },
    {
        "codigo": "avaliacoes",
        "nome": "Avaliações",
        "descricao": "Avaliações clínicas, formulários e registros avaliativos.",
        "icone": "file-text",
        "ordem": 6,
        "categoria": "Clínico",
    },
    {
        "codigo": "pacientes",
        "nome": "Pacientes",
        "descricao": "Cadastro, edição, visualização e histórico de pacientes.",
        "icone": "users",
        "ordem": 7,
        "categoria": "Clínico",
    },
    {
        "codigo": "pts",
        "nome": "PTS",
        "descricao": "Plano Terapêutico Singular.",
        "icone": "target",
        "ordem": 8,
        "categoria": "Clínico",
    },
    {
        "codigo": "registros",
        "nome": "Registros",
        "descricao": "Histórico, consultas e registros administrativos/assistenciais.",
        "icone": "archive",
        "ordem": 9,
        "categoria": "Clínico",
    },
    {
        "codigo": "financeiro",
        "nome": "Comercial / Financeiro",
        "descricao": "Receitas, despesas, planos, caixa e relatórios financeiros.",
        "icone": "dollar-sign",
        "ordem": 10,
        "categoria": "Comercial",
    },
    {
        "codigo": "combos",
        "nome": "Comercial / Combos",
        "descricao": "Planos, pacotes, combos e vínculos comerciais.",
        "icone": "package",
        "ordem": 11,
        "categoria": "Comercial",
    },
    {
        "codigo": "export_bpai",
        "nome": "Exportações / BPA-i",
        "descricao": "Exportação BPA Individualizado.",
        "icone": "download-cloud",
        "ordem": 12,
        "categoria": "Exportações",
    },
    {
        "codigo": "export_apac",
        "nome": "Exportações / APAC",
        "descricao": "Exportação APAC.",
        "icone": "file-plus",
        "ordem": 13,
        "categoria": "Exportações",
    },
    {
        "codigo": "admin_painel",
        "nome": "Admin / Painel",
        "descricao": "Painel principal administrativo.",
        "icone": "settings",
        "ordem": 14,
        "categoria": "Administração",
    },
    {
        "codigo": "admin_usuarios",
        "nome": "Admin / Usuários",
        "descricao": "Criação, edição e controle de usuários.",
        "icone": "user-cog",
        "ordem": 15,
        "categoria": "Administração",
    },
    {
        "codigo": "admin_modulos",
        "nome": "Admin / Módulos",
        "descricao": "Controle de módulos contratados e permissões.",
        "icone": "shield",
        "ordem": 16,
        "categoria": "Administração",
        "master_only": True,
    },
    {
        "codigo": "admin_cbo",
        "nome": "Admin / CBO",
        "descricao": "Biblioteca e importação de CBO.",
        "icone": "book-open",
        "ordem": 17,
        "categoria": "Administração",
    },
    {
        "codigo": "admin_cid",
        "nome": "Admin / CID",
        "descricao": "Biblioteca e importação de CID.",
        "icone": "tag",
        "ordem": 18,
        "categoria": "Administração",
    },
    {
        "codigo": "admin_cep_ibge",
        "nome": "Admin / CEP-IBGE",
        "descricao": "Biblioteca de CEP, município e IBGE.",
        "icone": "map",
        "ordem": 19,
        "categoria": "Administração",
    },

    # Futuro
    {
        "codigo": "rh",
        "nome": "RH",
        "descricao": "Recursos humanos, colaboradores e controles internos.",
        "icone": "briefcase",
        "ordem": 50,
        "categoria": "Futuros",
    },
    {
        "codigo": "modalidade_intelectual",
        "nome": "Modalidade / Intelectual",
        "descricao": "Módulo da modalidade intelectual.",
        "icone": "brain",
        "ordem": 51,
        "categoria": "Futuros",
    },
    {
        "codigo": "modalidade_fisico",
        "nome": "Modalidade / Físico",
        "descricao": "Módulo da modalidade física.",
        "icone": "activity",
        "ordem": 52,
        "categoria": "Futuros",
    },
    {
        "codigo": "modalidade_auditivo",
        "nome": "Modalidade / Auditivo",
        "descricao": "Módulo da modalidade auditiva.",
        "icone": "volume-2",
        "ordem": 53,
        "categoria": "Futuros",
    },
    {
        "codigo": "modalidade_visual",
        "nome": "Modalidade / Visual",
        "descricao": "Módulo da modalidade visual.",
        "icone": "eye",
        "ordem": 54,
        "categoria": "Futuros",
    },
]


# =============================================================================
# NÍVEIS DE ACESSO
# =============================================================================

NIVEIS_ACESSO = [
    {
        "codigo": "nenhum",
        "valor": 0,
        "nome": "Sem acesso",
        "acoes": [],
    },
    {
        "codigo": "ver",
        "valor": 1,
        "nome": "Apenas ver",
        "acoes": ["ver"],
    },
    {
        "codigo": "editar",
        "valor": 2,
        "nome": "Ver e editar",
        "acoes": ["ver", "editar"],
    },
    {
        "codigo": "exportar",
        "valor": 3,
        "nome": "Ver, editar e exportar",
        "acoes": ["ver", "editar", "exportar"],
    },
]

NIVEIS_MAP = {n["codigo"]: n for n in NIVEIS_ACESSO}
NIVEIS_VALOR = {n["valor"]: n for n in NIVEIS_ACESSO}

ROLES_BASE = [
    {"codigo": "ADMIN", "nome": "Admin"},
    {"codigo": "RECEPCAO", "nome": "Recepção"},
    {"codigo": "PROFISSIONAL", "nome": "Profissional"},
]


# =============================================================================
# CONEXÃO
# =============================================================================

def get_conn():
    if conectar_db is None:
        raise RuntimeError(
            "Não encontrei a função conectar_db em db.py. "
            "Ajuste o import no topo de admin/modulos.py."
        )

    conn = conectar_db()

    try:
        conn.autocommit = False
    except Exception:
        pass

    return conn

def row_to_dict(row, cur=None):
    if row is None:
        return None

    if isinstance(row, dict) or hasattr(row, "keys"):
        return dict(row)

    if cur and cur.description:
        cols = [desc[0] for desc in cur.description]
        return dict(zip(cols, row))

    return dict(row)


def row_value(row, key=0):
    if row is None:
        return None

    if isinstance(row, dict) or hasattr(row, "keys"):
        d = dict(row)
        if isinstance(key, int):
            return list(d.values())[key]
        return d.get(key)

    return row[key]


def dictfetchall(cur):
    return [row_to_dict(row, cur) for row in cur.fetchall()]


def dictfetchone(cur):
    return row_to_dict(cur.fetchone(), cur)


def only_digits(valor: str | None) -> str:
    return re.sub(r"\D", "", valor or "")

# =============================================================================
# SEGURANÇA MASTER
# =============================================================================

def usuario_logado():
    return (
        session.get("usuario")
        or session.get("user")
        or session.get("auth_user")
        or {}
    )


def usuario_eh_master() -> bool:
    user = usuario_logado()

    role = str(
        session.get("role")
        or user.get("role")
        or user.get("nivel")
        or ""
    ).upper()

    return (
        role in {"MASTER", "SUPERADMIN", "ROOT"}
        or session.get("is_master") is True
        or session.get("is_superuser") is True
        or user.get("is_master") is True
        or user.get("is_superuser") is True
    )


def master_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not usuario_eh_master():
            abort(403)

        return view(*args, **kwargs)

    return wrapper


# =============================================================================
# BANCO - SCHEMA
# =============================================================================

def ensure_modulos_schema():
    """
    Nova lógica:
    - sistema_modulos: catálogo oficial de telas/módulos
    - clinicas: unidades/clientes
    - clinica_modulos: módulo contratado/ativo por clínica
    - modulo_regras_acesso: regras por ROLE, CBO ou USUARIO

    alvo_tipo:
        ROLE    -> ADMIN, RECEPCAO, PROFISSIONAL
        CBO     -> código CBO
        USUARIO -> id do usuário

    nivel_acesso:
        0 = sem acesso
        1 = apenas ver
        2 = ver e editar
        3 = ver, editar e exportar
    """

    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sistema_modulos (
            id SERIAL PRIMARY KEY,
            codigo VARCHAR(100) UNIQUE NOT NULL,
            nome VARCHAR(180) NOT NULL,
            descricao TEXT,
            icone VARCHAR(80),
            categoria VARCHAR(100),
            ordem INTEGER DEFAULT 999,
            ativo BOOLEAN DEFAULT TRUE,
            master_only BOOLEAN DEFAULT FALSE,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS clinicas (
            id SERIAL PRIMARY KEY,
            nome VARCHAR(180) NOT NULL,
            documento VARCHAR(30),
            ativo BOOLEAN DEFAULT TRUE,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS clinica_modulos (
            id SERIAL PRIMARY KEY,
            clinica_id INTEGER NOT NULL REFERENCES clinicas(id) ON DELETE CASCADE,
            modulo_codigo VARCHAR(100) NOT NULL REFERENCES sistema_modulos(codigo) ON DELETE CASCADE,
            ativo BOOLEAN DEFAULT TRUE,
            observacao TEXT,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (clinica_id, modulo_codigo)
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS modulo_regras_acesso (
            id SERIAL PRIMARY KEY,
            clinica_id INTEGER NOT NULL REFERENCES clinicas(id) ON DELETE CASCADE,
            modulo_codigo VARCHAR(100) NOT NULL REFERENCES sistema_modulos(codigo) ON DELETE CASCADE,

            alvo_tipo VARCHAR(20) NOT NULL,
            alvo_valor VARCHAR(120) NOT NULL,

            nivel_acesso INTEGER NOT NULL DEFAULT 0,
            permitido BOOLEAN DEFAULT TRUE,

            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            UNIQUE (clinica_id, modulo_codigo, alvo_tipo, alvo_valor)
        );
        """
    )

    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_clinica_modulos_clinica
        ON clinica_modulos (clinica_id);
        """
    )

    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_clinica_modulos_modulo
        ON clinica_modulos (modulo_codigo);
        """
    )

    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_regras_acesso_clinica_modulo
        ON modulo_regras_acesso (clinica_id, modulo_codigo);
        """
    )

    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_regras_acesso_alvo
        ON modulo_regras_acesso (alvo_tipo, alvo_valor);
        """
    )

    conn.commit()
    cur.close()
    conn.close()


def seed_modulos():
    conn = get_conn()
    cur = conn.cursor()

    for modulo in MODULOS_DISPONIVEIS:
        cur.execute(
            """
            INSERT INTO sistema_modulos (
                codigo,
                nome,
                descricao,
                icone,
                categoria,
                ordem,
                ativo,
                master_only,
                atualizado_em
            )
            VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (codigo)
            DO UPDATE SET
                nome = EXCLUDED.nome,
                descricao = EXCLUDED.descricao,
                icone = EXCLUDED.icone,
                categoria = EXCLUDED.categoria,
                ordem = EXCLUDED.ordem,
                master_only = EXCLUDED.master_only,
                atualizado_em = CURRENT_TIMESTAMP;
            """,
            (
                modulo["codigo"],
                modulo["nome"],
                modulo.get("descricao"),
                modulo.get("icone"),
                modulo.get("categoria"),
                modulo.get("ordem", 999),
                bool(modulo.get("master_only", False)),
            ),
        )

    conn.commit()
    cur.close()
    conn.close()


def ensure_clinica_padrao():
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("SELECT id FROM clinicas ORDER BY id ASC LIMIT 1;")
        row = cur.fetchone()

        if row:
            clinica_id = row_value(row, "id")
        else:
            cur.execute(
                """
                INSERT INTO clinicas (nome, documento, ativo)
                VALUES (%s, %s, TRUE)
                RETURNING id;
                """,
                ("Clínica Principal", None),
            )
            clinica_id = row_value(cur.fetchone(), "id")
            conn.commit()

        return int(clinica_id)

    except Exception:
        conn.rollback()
        raise

    finally:
        cur.close()
        conn.close()

def preparar_modulos():
    ensure_modulos_schema()
    seed_modulos()
    return ensure_clinica_padrao()


# =============================================================================
# CONSULTAS BASE
# =============================================================================

def listar_clinicas():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, nome, documento, ativo
        FROM clinicas
        ORDER BY nome ASC;
        """
    )

    dados = dictfetchall(cur)

    cur.close()
    conn.close()

    return dados


def buscar_clinica(clinica_id: int):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, nome, documento, ativo
        FROM clinicas
        WHERE id = %s;
        """,
        (clinica_id,),
    )

    dado = dictfetchone(cur)

    cur.close()
    conn.close()

    return dado


def listar_modulos_da_clinica(clinica_id: int):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            sm.codigo,
            sm.nome,
            sm.descricao,
            sm.icone,
            sm.categoria,
            sm.ordem,
            sm.master_only,
            COALESCE(cm.ativo, FALSE) AS contratado,
            cm.observacao
        FROM sistema_modulos sm
        LEFT JOIN clinica_modulos cm
               ON cm.modulo_codigo = sm.codigo
              AND cm.clinica_id = %s
        WHERE sm.ativo = TRUE
        ORDER BY sm.ordem ASC, sm.nome ASC;
        """,
        (clinica_id,),
    )

    dados = dictfetchall(cur)

    cur.close()
    conn.close()

    return dados


def listar_regras_acesso(clinica_id: int):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            id,
            clinica_id,
            modulo_codigo,
            alvo_tipo,
            alvo_valor,
            nivel_acesso,
            permitido
        FROM modulo_regras_acesso
        WHERE clinica_id = %s
        ORDER BY modulo_codigo, alvo_tipo, alvo_valor;
        """,
        (clinica_id,),
    )

    dados = dictfetchall(cur)

    cur.close()
    conn.close()

    return dados


def listar_usuarios_por_role(clinica_id: int | None = None):
    """
    Lista usuários agrupáveis por role.
    Se clinica_id existir na tabela, filtra por clínica.
    """

    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'usuarios';
        """
    )
    cols = {row_value(r, "column_name") for r in cur.fetchall()}

    filtro_clinica = ""
    params = []

    if clinica_id and "clinica_id" in cols:
        filtro_clinica = "AND COALESCE(clinica_id, %s) = %s"
        params.extend([clinica_id, clinica_id])

    cur.execute(
        f"""
        SELECT
            id,
            nome,
            cpf,
            email,
            UPPER(COALESCE(role, '')) AS role,
            COALESCE(cbo, '') AS cbo,
            COALESCE(is_active, TRUE) AS is_active
        FROM usuarios
        WHERE COALESCE(is_active, TRUE) = TRUE
          AND UPPER(COALESCE(role, '')) IN ('ADMIN', 'RECEPCAO', 'RECEPÇÃO', 'PROFISSIONAL', 'PROFISSIONAIS')
          {filtro_clinica}
        ORDER BY role ASC, nome ASC;
        """,
        params,
    )

    usuarios = dictfetchall(cur)

    cur.close()
    conn.close()

    for u in usuarios:
        role = (u.get("role") or "").upper()

        if role == "RECEPÇÃO":
            u["role"] = "RECEPCAO"

        if role == "PROFISSIONAIS":
            u["role"] = "PROFISSIONAL"

        u["cbo_digits"] = only_digits(u.get("cbo"))

    return usuarios


def listar_cbos_com_profissionais(clinica_id: int | None = None):
    """
    Retorna apenas CBOs que possuem profissional vinculado.
    Não lista a biblioteca inteira, só o que realmente existe em usuários.
    """

    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'usuarios';
        """
    )
    cols = {row_value(r, "column_name") for r in cur.fetchall()}

    filtro_clinica = ""
    params = []

    if clinica_id and "clinica_id" in cols:
        filtro_clinica = "AND COALESCE(u.clinica_id, %s) = %s"
        params.extend([clinica_id, clinica_id])

    # Primeiro tenta buscar descrição em cbo_catalogo, se existir.
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = 'cbo_catalogo'
        );
        """
    )
    tem_cbo_catalogo = bool(row_value(cur.fetchone(), "exists"))

    if tem_cbo_catalogo:
        cur.execute(
            f"""
            SELECT
                regexp_replace(COALESCE(u.cbo, ''), '\\D', '', 'g') AS codigo,
                COALESCE(MAX(c.no_ocupacao), MAX(u.cbo), 'CBO sem descrição') AS descricao,
                COUNT(u.id) AS total_profissionais
            FROM usuarios u
            LEFT JOIN cbo_catalogo c
                   ON regexp_replace(COALESCE(c.co_ocupacao, ''), '\\D', '', 'g')
                    = regexp_replace(COALESCE(u.cbo, ''), '\\D', '', 'g')
            WHERE COALESCE(u.is_active, TRUE) = TRUE
              AND UPPER(COALESCE(u.role, '')) IN ('PROFISSIONAL', 'PROFISSIONAIS')
              AND COALESCE(u.cbo, '') <> ''
              {filtro_clinica}
            GROUP BY regexp_replace(COALESCE(u.cbo, ''), '\\D', '', 'g')
            ORDER BY descricao ASC;
            """,
            params,
        )
    else:
        cur.execute(
            f"""
            SELECT
                regexp_replace(COALESCE(u.cbo, ''), '\\D', '', 'g') AS codigo,
                MAX(u.cbo) AS descricao,
                COUNT(u.id) AS total_profissionais
            FROM usuarios u
            WHERE COALESCE(u.is_active, TRUE) = TRUE
              AND UPPER(COALESCE(u.role, '')) IN ('PROFISSIONAL', 'PROFISSIONAIS')
              AND COALESCE(u.cbo, '') <> ''
              {filtro_clinica}
            GROUP BY regexp_replace(COALESCE(u.cbo, ''), '\\D', '', 'g')
            ORDER BY descricao ASC;
            """,
            params,
        )

    cbos = dictfetchall(cur)

    cur.close()
    conn.close()

    return [c for c in cbos if c.get("codigo")]


def listar_profissionais_por_cbo(clinica_id: int | None = None):
    usuarios = listar_usuarios_por_role(clinica_id)
    profissionais = [u for u in usuarios if u.get("role") == "PROFISSIONAL" and u.get("cbo_digits")]

    por_cbo = {}

    for u in profissionais:
        cbo = u["cbo_digits"]

        if cbo not in por_cbo:
            por_cbo[cbo] = []

        por_cbo[cbo].append(u)

    return por_cbo


def montar_contexto_acessos(clinica_id: int):
    """
    Prepara tudo que o HTML vai precisar:
    - módulos
    - regras já salvas
    - usuários por role
    - CBOs usados
    - profissionais dentro de cada CBO
    """

    modulos = listar_modulos_da_clinica(clinica_id)
    regras = listar_regras_acesso(clinica_id)
    usuarios = listar_usuarios_por_role(clinica_id)
    cbos = listar_cbos_com_profissionais(clinica_id)
    profissionais_por_cbo = listar_profissionais_por_cbo(clinica_id)

    usuarios_por_role = {
        "ADMIN": [],
        "RECEPCAO": [],
        "PROFISSIONAL": [],
    }

    for u in usuarios:
        role = u.get("role")

        if role in usuarios_por_role:
            usuarios_por_role[role].append(u)

    regras_map = {}

    for r in regras:
        chave = f"{r['modulo_codigo']}::{r['alvo_tipo']}::{r['alvo_valor']}"
        regras_map[chave] = r

    return {
        "modulos": modulos,
        "regras": regras,
        "regras_map": regras_map,
        "usuarios": usuarios,
        "usuarios_por_role": usuarios_por_role,
        "cbos": cbos,
        "profissionais_por_cbo": profissionais_por_cbo,
        "roles_base": ROLES_BASE,
        "niveis_acesso": NIVEIS_ACESSO,
    }
# =============================================================================
# GRAVAÇÃO
# =============================================================================

def nivel_para_valor(nivel: str | int | None) -> int:
    """
    Converte:
    - nenhum  -> 0
    - ver     -> 1
    - editar  -> 2
    - exportar -> 3
    """

    if nivel is None:
        return 0

    if isinstance(nivel, int):
        return max(0, min(3, nivel))

    nivel = str(nivel).strip().lower()

    if nivel.isdigit():
        return max(0, min(3, int(nivel)))

    dados = NIVEIS_MAP.get(nivel)

    if not dados:
        return 0

    return int(dados["valor"])


def valor_permite_acao(nivel_valor: int, acao: str) -> bool:
    """
    Verifica se o nível numérico permite determinada ação.
    """

    acao = (acao or "ver").strip().lower()

    if nivel_valor >= 3:
        return acao in {"ver", "editar", "exportar", "criar", "imprimir"}

    if nivel_valor >= 2:
        return acao in {"ver", "editar", "criar", "imprimir"}

    if nivel_valor >= 1:
        return acao in {"ver", "imprimir"}

    return False


def salvar_modulos_clinica(clinica_id: int, modulos_ativos: set[str]):
    codigos_validos = {m["codigo"] for m in MODULOS_DISPONIVEIS}
    modulos_ativos = {m for m in modulos_ativos if m in codigos_validos}

    dados = [
        (
            clinica_id,
            codigo,
            codigo in modulos_ativos,
        )
        for codigo in codigos_validos
    ]

    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.executemany(
            """
            INSERT INTO clinica_modulos (
                clinica_id,
                modulo_codigo,
                ativo,
                atualizado_em
            )
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (clinica_id, modulo_codigo)
            DO UPDATE SET
                ativo = EXCLUDED.ativo,
                atualizado_em = CURRENT_TIMESTAMP;
            """,
            dados,
        )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        cur.close()
        conn.close()


def salvar_regras_acesso_from_form(clinica_id: int, form):
    """
    Salva regras em lote.

    Não apaga tudo antes.
    Só faz UPSERT do que veio do formulário.
    Muito mais rápido que abrir conexão/commit por regra.
    """

    dados = []

    for key, value in form.items():
        if not key.startswith("nivel__"):
            continue

        partes = key.split("__")

        if len(partes) != 4:
            continue

        _, modulo_codigo, alvo_tipo, alvo_valor = partes

        alvo_tipo = str(alvo_tipo).upper().strip()
        alvo_valor = str(alvo_valor).strip()

        if alvo_tipo not in {"ROLE", "CBO", "USUARIO"}:
            continue

        if not modulo_codigo or not alvo_valor:
            continue

        dados.append(
            (
                clinica_id,
                modulo_codigo,
                alvo_tipo,
                alvo_valor,
                nivel_para_valor(value),
                True,
            )
        )

    if not dados:
        return

    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.executemany(
            """
            INSERT INTO modulo_regras_acesso (
                clinica_id,
                modulo_codigo,
                alvo_tipo,
                alvo_valor,
                nivel_acesso,
                permitido,
                atualizado_em
            )
            VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (clinica_id, modulo_codigo, alvo_tipo, alvo_valor)
            DO UPDATE SET
                nivel_acesso = EXCLUDED.nivel_acesso,
                permitido = EXCLUDED.permitido,
                atualizado_em = CURRENT_TIMESTAMP;
            """,
            dados,
        )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        cur.close()
        conn.close()

# =============================================================================
# PERMISSÕES - FUNÇÕES PARA USAR NO SISTEMA TODO
# =============================================================================

def clinica_tem_modulo(clinica_id: int, modulo_codigo: str) -> bool:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT 1
        FROM clinica_modulos
        WHERE clinica_id = %s
          AND modulo_codigo = %s
          AND ativo = TRUE
        LIMIT 1;
        """,
        (clinica_id, modulo_codigo),
    )

    ok = cur.fetchone() is not None

    cur.close()
    conn.close()

    return ok


def buscar_usuario_para_permissao(usuario_id: int):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            id,
            nome,
            UPPER(COALESCE(role, '')) AS role,
            COALESCE(cbo, '') AS cbo,
            COALESCE(clinica_id, 1) AS clinica_id,
            COALESCE(is_master, FALSE) AS is_master,
            COALESCE(is_superuser, FALSE) AS is_superuser
        FROM usuarios
        WHERE id = %s
        LIMIT 1;
        """,
        (usuario_id,),
    )

    usuario = dictfetchone(cur)

    cur.close()
    conn.close()

    if usuario:
        role = (usuario.get("role") or "").upper()

        if role == "RECEPÇÃO":
            usuario["role"] = "RECEPCAO"

        if role == "PROFISSIONAIS":
            usuario["role"] = "PROFISSIONAL"

        usuario["cbo_digits"] = only_digits(usuario.get("cbo"))

    return usuario


def nivel_regra(
    clinica_id: int,
    modulo_codigo: str,
    alvo_tipo: str,
    alvo_valor: str | int,
) -> int | None:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT nivel_acesso, permitido
        FROM modulo_regras_acesso
        WHERE clinica_id = %s
          AND modulo_codigo = %s
          AND alvo_tipo = %s
          AND alvo_valor = %s
        LIMIT 1;
        """,
        (
            clinica_id,
            modulo_codigo,
            str(alvo_tipo).upper(),
            str(alvo_valor),
        ),
    )

    row = cur.fetchone()

    cur.close()
    conn.close()

    if row is None:
        return None

    dado = row_to_dict(row, cur)

    nivel = dado.get("nivel_acesso")
    permitido = dado.get("permitido")

    if permitido is False:
        return 0

    return int(nivel or 0)


def usuario_tem_permissao(
    usuario_id: int,
    clinica_id: int,
    modulo_codigo: str,
    acao: str = "ver",
    perfil_id: int | None = None,
) -> bool:
    """
    Prioridade:
    1. Master pode tudo.
    2. Clínica precisa ter módulo ativo.
    3. Regra por USUÁRIO tem prioridade máxima.
    4. Depois CBO.
    5. Depois ROLE.
    6. Sem regra = bloqueado.
    """

    if usuario_eh_master():
        return True

    if not clinica_tem_modulo(clinica_id, modulo_codigo):
        return False

    usuario = buscar_usuario_para_permissao(usuario_id)

    if not usuario:
        return False

    if usuario.get("is_master") is True or usuario.get("is_superuser") is True:
        return True

    # 1) Exceção direta por usuário
    nivel_usuario = nivel_regra(
        clinica_id=clinica_id,
        modulo_codigo=modulo_codigo,
        alvo_tipo="USUARIO",
        alvo_valor=usuario_id,
    )

    if nivel_usuario is not None:
        return valor_permite_acao(nivel_usuario, acao)

    # 2) Regra por CBO
    cbo = usuario.get("cbo_digits")

    if cbo:
        nivel_cbo = nivel_regra(
            clinica_id=clinica_id,
            modulo_codigo=modulo_codigo,
            alvo_tipo="CBO",
            alvo_valor=cbo,
        )

        if nivel_cbo is not None:
            return valor_permite_acao(nivel_cbo, acao)

    # 3) Regra por ROLE
    role = usuario.get("role")

    if role:
        nivel_role = nivel_regra(
            clinica_id=clinica_id,
            modulo_codigo=modulo_codigo,
            alvo_tipo="ROLE",
            alvo_valor=role,
        )

        if nivel_role is not None:
            return valor_permite_acao(nivel_role, acao)

    return False


def require_permission(modulo_codigo: str, acao: str = "ver"):
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = usuario_logado()

            usuario_id = (
                user.get("id")
                or session.get("user_id")
                or session.get("usuario_id")
            )

            clinica_id = (
                user.get("clinica_id")
                or session.get("clinica_id")
                or 1
            )

            if usuario_eh_master():
                return view(*args, **kwargs)

            if not usuario_id or not clinica_id:
                abort(403)

            if not usuario_tem_permissao(
                usuario_id=int(usuario_id),
                clinica_id=int(clinica_id),
                modulo_codigo=modulo_codigo,
                acao=acao,
            ):
                abort(403)

            return view(*args, **kwargs)

        return wrapper

    return decorator


# =============================================================================
# ROTAS
# =============================================================================

@admin_bp.route("/modulos", methods=["GET", "POST"])
@admin_required
@master_required
def modulos():
    preparar_modulos()

    clinicas = listar_clinicas()
    clinica_id = request.values.get("clinica_id", type=int)

    if not clinica_id:
        clinica_id = clinicas[0]["id"] if clinicas else preparar_modulos()

    clinica = buscar_clinica(clinica_id)

    if not clinica:
        flash("Clínica não encontrada.", "error")
        return redirect(url_for("admin.modulos"))

    if request.method == "POST":
        modulos_ativos = set(request.form.getlist("modulos_ativos"))

        salvar_modulos_clinica(
            clinica_id=clinica_id,
            modulos_ativos=modulos_ativos,
        )

        salvar_regras_acesso_from_form(
            clinica_id=clinica_id,
            form=request.form,
        )

        flash("Módulos e regras de acesso atualizados com sucesso.", "success")
        return redirect(url_for("admin.modulos", clinica_id=clinica_id))

    contexto = montar_contexto_acessos(clinica_id)

    return render_template(
        "modulos.html",
        clinicas=clinicas,
        clinica=clinica,
        clinica_id=clinica_id,
        is_master=True,
        **contexto,
    )


@admin_bp.route("/modulos/api/clinica/<int:clinica_id>", methods=["GET"])
@admin_required
@master_required
def api_modulos_clinica(clinica_id: int):
    preparar_modulos()

    clinica = buscar_clinica(clinica_id)

    if not clinica:
        return jsonify({"ok": False, "erro": "Clínica não encontrada."}), 404

    contexto = montar_contexto_acessos(clinica_id)

    return jsonify(
        {
            "ok": True,
            "clinica": clinica,
            "modulos": contexto["modulos"],
            "roles_base": contexto["roles_base"],
            "niveis_acesso": contexto["niveis_acesso"],
            "usuarios_por_role": contexto["usuarios_por_role"],
            "cbos": contexto["cbos"],
            "profissionais_por_cbo": contexto["profissionais_por_cbo"],
            "regras": contexto["regras"],
            "regras_map": contexto["regras_map"],
        }
    )


@admin_bp.route("/modulos/api/check", methods=["GET"])
@admin_required
def api_check_permissao():
    preparar_modulos()

    user = usuario_logado()

    modulo_codigo = request.args.get("modulo", "").strip()
    acao = request.args.get("acao", "ver").strip()

    usuario_id = (
        user.get("id")
        or session.get("user_id")
        or session.get("usuario_id")
    )

    clinica_id = (
        user.get("clinica_id")
        or session.get("clinica_id")
        or 1
    )

    if usuario_eh_master():
        return jsonify(
            {
                "ok": True,
                "permitido": True,
                "master": True,
                "nivel": 3,
            }
        )

    if not usuario_id or not clinica_id or not modulo_codigo:
        return jsonify({"ok": False, "permitido": False}), 403

    permitido = usuario_tem_permissao(
        usuario_id=int(usuario_id),
        clinica_id=int(clinica_id),
        modulo_codigo=modulo_codigo,
        acao=acao,
    )

    return jsonify(
        {
            "ok": True,
            "permitido": permitido,
            "master": False,
        }
    )


@admin_bp.route("/modulos/api/usuario/<int:usuario_id>/permissoes", methods=["GET"])
@admin_required
@master_required
def api_usuario_permissoes(usuario_id: int):
    preparar_modulos()

    clinica_id = request.args.get("clinica_id", type=int) or 1
    usuario = buscar_usuario_para_permissao(usuario_id)

    if not usuario:
        return jsonify({"ok": False, "erro": "Usuário não encontrado."}), 404

    modulos = listar_modulos_da_clinica(clinica_id)
    resultado = []

    for modulo in modulos:
        codigo = modulo["codigo"]

        nivel_usuario = nivel_regra(clinica_id, codigo, "USUARIO", usuario_id)
        nivel_cbo = None
        nivel_role = None

        if usuario.get("cbo_digits"):
            nivel_cbo = nivel_regra(clinica_id, codigo, "CBO", usuario["cbo_digits"])

        if usuario.get("role"):
            nivel_role = nivel_regra(clinica_id, codigo, "ROLE", usuario["role"])

        nivel_final = (
            nivel_usuario
            if nivel_usuario is not None
            else nivel_cbo
            if nivel_cbo is not None
            else nivel_role
            if nivel_role is not None
            else 0
        )

        resultado.append(
            {
                "modulo_codigo": codigo,
                "modulo_nome": modulo["nome"],
                "contratado": modulo["contratado"],
                "nivel_usuario": nivel_usuario,
                "nivel_cbo": nivel_cbo,
                "nivel_role": nivel_role,
                "nivel_final": nivel_final,
            }
        )

    return jsonify(
        {
            "ok": True,
            "usuario": usuario,
            "permissoes": resultado,
        }
    )