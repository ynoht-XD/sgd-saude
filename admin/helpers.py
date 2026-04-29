# admin/helpers.py
from __future__ import annotations

import re
from typing import Any

from db import conectar_db


# =============================================================================
# HELPERS GERAIS DO MÓDULO ADMIN
# =============================================================================

def only_digits(s: str | None) -> str:
    """
    Retorna apenas os dígitos de uma string.
    Ex.:
        "123.456.789-00" -> "12345678900"
    """
    return re.sub(r"\D+", "", s or "")


def has_table(conn: Any, table_name: str) -> bool:
    """
    Verifica se uma tabela existe.

    Compatível com:
    - SQLite
    - PostgreSQL

    Observação:
    No PostgreSQL, verifica no schema 'public'.
    """
    cur = conn.cursor()

    try:
        # Tenta PostgreSQL primeiro
        cur.execute("""
            SELECT 1
              FROM information_schema.tables
             WHERE table_schema = 'public'
               AND table_name = %s
             LIMIT 1
        """, (table_name,))
        return cur.fetchone() is not None
    except Exception:
        # Fallback SQLite
        try:
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=? LIMIT 1;",
                (table_name,),
            )
            return cur.fetchone() is not None
        finally:
            try:
                cur.close()
            except Exception:
                pass


def list_columns(conn: Any, table_name: str) -> set[str]:
    """
    Lista as colunas de uma tabela.

    Compatível com:
    - SQLite
    - PostgreSQL
    """
    cur = conn.cursor()

    try:
        # Tenta PostgreSQL primeiro
        cur.execute("""
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = %s
             ORDER BY ordinal_position
        """, (table_name,))
        rows = cur.fetchall() or []
        cols = set()

        for row in rows:
            # psycopg normalmente devolve tupla
            if isinstance(row, (list, tuple)):
                cols.add(str(row[0]))
            else:
                # fallback se vier em formato dict-like
                cols.add(str(row["column_name"]))

        if cols:
            return cols
    except Exception:
        pass

    try:
        # Fallback SQLite
        cur.execute(f"PRAGMA table_info({table_name});")
        rows = cur.fetchall() or []
        cols = set()

        for row in rows:
            # sqlite3.Row aceita índice e chave
            try:
                cols.add(str(row[1]))
            except Exception:
                cols.add(str(row["name"]))

        return cols
    finally:
        try:
            cur.close()
        except Exception:
            pass


def digits_sql(expr: str) -> str:
    """
    Gera uma expressão SQL que remove caracteres não numéricos.

    Foi pensada originalmente para SQLite, mas também funciona no PostgreSQL
    porque usa apenas REPLACE encadeado.

    Ex.:
        digits_sql("cpf") -> REPLACE(REPLACE(...cpf...))
    """
    s = expr
    for ch in (".", "-", "/", "(", ")", " "):
        s = f"REPLACE({s}, '{ch}', '')"
    return s


def db_conn(readonly: bool = False):
    """
    Wrapper único de conexão do projeto.

    - Em SQLite:
        aplica PRAGMA query_only quando readonly=True
    - Em PostgreSQL:
        apenas retorna a conexão normalmente
    """
    conn = conectar_db()

    if readonly:
        try:
            # SQLite
            conn.execute("PRAGMA query_only = 1;")
        except Exception:
            # PostgreSQL não usa esse PRAGMA, então ignoramos
            pass

    return conn