# db.py
from __future__ import annotations

import os
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode


# ============================================================
# CONFIG POSTGRES LOCAL
# ============================================================

PG_HOST = os.environ.get("PG_HOST", "127.0.0.1")
PG_PORT = os.environ.get("PG_PORT", "5434")
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASS = os.environ.get("PG_PASS", "sgd_database")
PG_DB = os.environ.get("PG_DB", "sgd_database")


# ============================================================
# HELPERS
# ============================================================

def _normalize_database_url(url: str) -> str:
    """
    Normaliza URL para psycopg.
    Render pode fornecer postgresql://.
    Alguns serviços usam postgres://.
    """
    url = (url or "").strip()

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    return url


def _is_render_env() -> bool:
    """
    Detecta ambiente Render.
    """
    return bool(os.environ.get("RENDER"))


def _add_ssl_if_needed(url: str) -> str:
    """
    No Render, a conexão interna normalmente funciona sem sslmode.
    A externa pode exigir SSL.

    Mantemos sem forçar SSL na URL interna.
    Se quiser usar URL externa localmente, defina PGSSLMODE=require no ambiente.
    """
    sslmode = os.environ.get("PGSSLMODE", "").strip()

    if not sslmode:
        return url

    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query))
    query["sslmode"] = sslmode

    return urlunparse(parsed._replace(query=urlencode(query)))


# ============================================================
# DATABASE URL
# ============================================================

def get_database_url() -> str:
    """
    Prioridade:
    1. DATABASE_URL do Render/ambiente
    2. PostgreSQL local montado por variáveis PG_*
    """
    env_url = os.environ.get("DATABASE_URL", "").strip()

    if env_url:
        url = _normalize_database_url(env_url)
        return _add_ssl_if_needed(url)

    return f"postgresql://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_DB}"


def get_pg_url(db_name: str = "postgres") -> str:
    """
    URL usada apenas para criar/verificar banco local.
    """
    return f"postgresql://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{db_name}"


# ============================================================
# GARANTIR BANCO LOCAL
# ============================================================

def ensure_database_exists():
    """
    Cria o banco local automaticamente, se ainda não existir.

    No Render, DATABASE_URL já aponta para um banco existente.
    Então não tentamos criar banco lá.
    """
    if os.environ.get("DATABASE_URL", "").strip():
        return

    import psycopg

    conn = psycopg.connect(get_pg_url("postgres"))
    conn.autocommit = True

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s;",
                (PG_DB,)
            )

            exists = cur.fetchone()

            if not exists:
                cur.execute(f'CREATE DATABASE "{PG_DB}";')
                print(f"🧠 Banco PostgreSQL criado automaticamente: {PG_DB}")

    finally:
        conn.close()


# ============================================================
# CONEXÃO PRINCIPAL
# ============================================================

def conectar_db():
    """
    Conexão única do sistema usando PostgreSQL.

    Local:
      usa PG_HOST, PG_PORT, PG_USER, PG_PASS, PG_DB.

    Render:
      usa DATABASE_URL.
    """
    import psycopg
    from psycopg.rows import dict_row

    ensure_database_exists()

    conn = psycopg.connect(
        get_database_url(),
        row_factory=dict_row
    )
    conn.autocommit = False
    return conn


# ============================================================
# ALIASES / COMPATIBILIDADE
# ============================================================

def db_conn(readonly: bool = False):
    return conectar_db()


def dict_one(row):
    return dict(row) if row else None


def dict_rows(rows):
    return [dict(r) for r in rows]