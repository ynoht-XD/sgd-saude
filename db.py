# db.py
from __future__ import annotations

import os


# ============================================================
# CONFIG POSTGRES LOCAL
# ============================================================

PG_HOST = os.environ.get("PG_HOST", "127.0.0.1")
PG_PORT = os.environ.get("PG_PORT", "5434")
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASS = os.environ.get("PG_PASS", "sgd_database")
PG_DB = os.environ.get("PG_DB", "sgd_database")


# ============================================================
# DATABASE URL
# ============================================================

def get_database_url() -> str:
    """
    Se DATABASE_URL existir, usa ela.
    Se não existir, monta a URL local do PostgreSQL.
    """
    url = os.environ.get("DATABASE_URL", "").strip()

    if url:
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url

    return f"postgresql://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_DB}"


def get_pg_url(db_name: str) -> str:
    return f"postgresql://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{db_name}"


# ============================================================
# GARANTIR BANCO LOCAL
# ============================================================

def ensure_database_exists():
    """
    Cria o banco local automaticamente, se ainda não existir.
    No Render, normalmente DATABASE_URL já aponta para um banco existente.
    """
    if os.environ.get("DATABASE_URL", "").strip():
        return

    import psycopg

    conn = psycopg.connect(get_pg_url("postgres"))
    conn.autocommit = True

    try:
        cur = conn.cursor()

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
    Conexão única do sistema usando apenas PostgreSQL.
    """
    import psycopg

    ensure_database_exists()

    conn = psycopg.connect(get_database_url())
    conn.autocommit = False
    return conn


# Alias usado por alguns módulos antigos
def db_conn(readonly: bool = False):
    return conectar_db()