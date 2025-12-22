# auth/routes.py
from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime
from urllib.parse import urlparse, urljoin

from flask import render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash

from . import auth_bp

# ============================================================
# BANCO (Render usa /tmp por enquanto)
# ============================================================

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CAMINHO_DB = os.environ.get("SQLITE_PATH") or os.path.join(BASE_DIR, "data_base", "sgd_db.db")
print("🧠 SQLite AUTH em:", CAMINHO_DB)

# ============================================================
# MASTER (seed automático ao acessar /auth/login)
# ============================================================

MASTER_CPF = os.environ.get("MASTER_CPF") or "11286922445"
MASTER_PASSWORD = os.environ.get("MASTER_PASSWORD") or "sgd_s1a2u3d4e5"
MASTER_NOME = os.environ.get("MASTER_NOME") or "Admin Master"
MASTER_EMAIL = os.environ.get("MASTER_EMAIL") or "admin@local"


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(CAMINHO_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


# ============================================================
# MIGRATION HELPERS (idempotentes)
# ============================================================

def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return {r[1] for r in cur.fetchall()}


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=? LIMIT 1;", (table,))
    return cur.fetchone() is not None


def _add_col(conn: sqlite3.Connection, table: str, col: str, ddl: str) -> None:
    """
    ddl exemplo: "INTEGER NOT NULL DEFAULT 0"
    """
    cols = _table_columns(conn, table)
    if col in cols:
        return
    cur = conn.cursor()
    cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl};")
    conn.commit()


def _ensure_schema(conn: sqlite3.Connection):
    """
    Cria a tabela 'usuarios' se não existir.
    Se existir (em versões antigas), adiciona colunas faltantes.
    """
    cur = conn.cursor()

    # 1) cria base mínima se não existir
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            nome             TEXT NOT NULL,
            cpf              TEXT NOT NULL UNIQUE,
            email            TEXT,
            role             TEXT NOT NULL,
            profissional_id  INTEGER,
            password_hash    TEXT NOT NULL
        )
        """
    )
    conn.commit()

    # 2) migra colunas faltantes (compat com tabelas antigas)
    # flags/controle
    _add_col(conn, "usuarios", "must_change_pass", "INTEGER NOT NULL DEFAULT 0")
    _add_col(conn, "usuarios", "is_active", "INTEGER NOT NULL DEFAULT 1")
    _add_col(conn, "usuarios", "last_login_at", "TEXT")
    _add_col(conn, "usuarios", "created_at", "TEXT NOT NULL DEFAULT (datetime('now'))")

    # 3) índices (não quebra se já existir)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_role ON usuarios(role);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_active ON usuarios(is_active);")
    conn.commit()


def _ensure_admin_exists():
    """Garante o usuário master com CPF e senha definidos acima."""
    conn = None
    try:
        conn = _db()
        _ensure_schema(conn)

        c = conn.cursor()

        pw_hash = generate_password_hash(MASTER_PASSWORD, method="pbkdf2:sha256", salt_length=16)

        # Se já existir, atualiza; se não, cria
        c.execute("SELECT id FROM usuarios WHERE cpf=? LIMIT 1", (MASTER_CPF,))
        row = c.fetchone()

        if row:
            c.execute(
                """
                UPDATE usuarios
                   SET nome=?,
                       email=?,
                       role='ADMIN',
                       is_active=1,
                       password_hash=?,
                       must_change_pass=0
                 WHERE id=?
                """,
                (MASTER_NOME, MASTER_EMAIL, pw_hash, row["id"]),
            )
        else:
            c.execute(
                """
                INSERT INTO usuarios
                    (nome, cpf, email, role, profissional_id, password_hash, must_change_pass, is_active, created_at)
                VALUES
                    (?, ?, ?, 'ADMIN', NULL, ?, 0, 1, ?)
                """,
                (MASTER_NOME, MASTER_CPF, MASTER_EMAIL, pw_hash, datetime.utcnow().isoformat()),
            )

        # opcional: desativar placeholders antigos
        try:
            c.execute("UPDATE usuarios SET is_active=0 WHERE cpf='00000000000'")
        except Exception:
            pass

        conn.commit()

    except Exception as e:
        print("❌ ERRO ao seedar MASTER:", str(e))
    finally:
        if conn:
            conn.close()


def _is_safe_url(target: str) -> bool:
    if not target:
        return False
    host_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ("http", "https") and host_url.netloc == test_url.netloc


def _normalize_next(next_url: str | None) -> str:
    if next_url and _is_safe_url(next_url) and not next_url.startswith("/admin"):
        return next_url
    return url_for("index")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    _ensure_admin_exists()

    raw_next = request.values.get("next")
    next_url = _normalize_next(raw_next)

    if request.method == "POST":
        cpf = re.sub(r"\D", "", (request.form.get("cpf") or ""))
        senha = request.form.get("senha") or ""

        raw_next_post = request.form.get("next") or request.args.get("next")
        next_url = _normalize_next(raw_next_post)

        if not cpf or not senha:
            flash("Informe CPF e senha.", "error")
            return redirect(url_for("auth.login", next=next_url))

        conn = _db()
        try:
            _ensure_schema(conn)  # ✅ garante colunas antes de query
            c = conn.cursor()
            c.execute("SELECT * FROM usuarios WHERE cpf=? AND is_active=1 LIMIT 1", (cpf,))
            u = c.fetchone()

            if not u or not check_password_hash(u["password_hash"], senha):
                flash("CPF ou senha inválidos.", "error")
                return redirect(url_for("auth.login", next=next_url))

            c.execute("UPDATE usuarios SET last_login_at=? WHERE id=?", (datetime.utcnow().isoformat(), u["id"]))
            conn.commit()

            # sessão
            session.clear()
            session["user_id"] = u["id"]
            session["nome"] = u["nome"]
            session["role"] = (u["role"] or "").upper()
            session["profissional_id"] = u["profissional_id"]

            primeiro_nome = (u["nome"] or "").split()[0] if u["nome"] else "usuário"
            flash(f"Bem-vindo, {primeiro_nome}!", "success")
            return redirect(next_url)

        finally:
            conn.close()

    return render_template("login.html", next_url=next_url)


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("Você saiu da sua sessão.", "info")
    return redirect(url_for("auth.login"))
