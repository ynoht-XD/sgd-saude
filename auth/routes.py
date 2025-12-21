# auth/routes.py
import os
import re
import sqlite3
from datetime import datetime
from urllib.parse import urlparse, urljoin

from flask import render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from . import auth_bp

# === Caminho do banco (absoluto, a partir da raiz do projeto) ===
# === Caminho do banco ===
# Local: usa data_base/sgd_db.db
# Render (sem disk): usa /tmp/sgd_db.db (pode sumir e tudo bem por enquanto)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CAMINHO_DB = os.environ.get("SQLITE_PATH") or os.path.join(BASE_DIR, "data_base", "sgd_db.db")

# (opcional) log pra você ver no Render qual caminho está usando
print("🧠 SQLite AUTH em:", CAMINHO_DB)

# Master (seed automático ao acessar /auth/login)
MASTER_CPF = "11286922445"
MASTER_PASSWORD = "sgd_s1a2u3d4e5"
MASTER_NOME = "Admin Master"
MASTER_EMAIL = "admin@local"


def _db():
    conn = sqlite3.connect(CAMINHO_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _ensure_schema(conn: sqlite3.Connection):
    """Cria a tabela 'usuarios' mínima se não existir (sem bloqueio por tentativas)."""
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            nome             TEXT NOT NULL,
            cpf              TEXT NOT NULL UNIQUE,   -- login
            email            TEXT,
            role             TEXT NOT NULL CHECK(role IN ('ADMIN','RECEPCAO','PROFISSIONAL')),
            profissional_id  INTEGER,
            password_hash    TEXT NOT NULL,
            must_change_pass INTEGER NOT NULL DEFAULT 0,
            is_active        INTEGER NOT NULL DEFAULT 1,
            last_login_at    TEXT,
            created_at       TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_role ON usuarios(role);")
    c.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_active ON usuarios(is_active);")
    conn.commit()


def _ensure_admin_exists():
    """Garante o usuário master com CPF e senha definidos acima."""
    try:
        conn = _db()
        _ensure_schema(conn)
        c = conn.cursor()

        pw_hash = generate_password_hash(MASTER_PASSWORD, method="pbkdf2:sha256", salt_length=16)

        # Se já existir, atualiza; se não, cria
        c.execute("SELECT id FROM usuarios WHERE cpf=?", (MASTER_CPF,))
        row = c.fetchone()
        if row:
            c.execute(
                """
                UPDATE usuarios
                   SET nome=?, email=?, role='ADMIN', is_active=1,
                       password_hash=?, must_change_pass=0
                 WHERE id=?
                """,
                (MASTER_NOME, MASTER_EMAIL, pw_hash, row["id"]),
            )
        else:
            c.execute(
                """
                INSERT INTO usuarios (nome, cpf, email, role, password_hash, must_change_pass, is_active, created_at)
                VALUES (?, ?, ?, 'ADMIN', ?, 0, 1, ?)
                """,
                (MASTER_NOME, MASTER_CPF, MASTER_EMAIL, pw_hash, datetime.utcnow().isoformat()),
            )

        # (opcional) desativar placeholder antigo
        c.execute("UPDATE usuarios SET is_active=0 WHERE cpf='00000000000'")
        conn.commit()
        conn.close()
    except Exception:
        # Em produção: logar erro; aqui deixamos silencioso
        pass


def _is_safe_url(target: str) -> bool:
    """
    Evita open redirect (não deixa redirecionar pra outro domínio).
    """
    if not target:
        return False
    host_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return (
        test_url.scheme in ("http", "https")
        and host_url.netloc == test_url.netloc
    )


def _normalize_next(next_url: str | None) -> str:
    """
    Regra do projeto:
    - padrão: HOME (/)
    - aceita next apenas se for seguro e NÃO for /admin
    """
    if next_url and _is_safe_url(next_url) and not next_url.startswith("/admin"):
        return next_url
    return url_for("index")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    _ensure_admin_exists()

    # ✅ Padrão agora é HOME, não /admin
    raw_next = request.values.get("next")
    next_url = _normalize_next(raw_next)

    if request.method == "POST":
        # Normaliza CPF para só dígitos
        cpf = re.sub(r"\D", "", (request.form.get("cpf") or ""))
        senha = request.form.get("senha") or ""

        # Recalcula o next vindo do POST (hidden input)
        raw_next_post = request.form.get("next") or request.args.get("next")
        next_url = _normalize_next(raw_next_post)

        if not cpf or not senha:
            flash("Informe CPF e senha.", "error")
            return redirect(url_for("auth.login", next=next_url))

        conn = _db()
        c = conn.cursor()
        c.execute("SELECT * FROM usuarios WHERE cpf=? AND is_active=1", (cpf,))
        u = c.fetchone()

        if not u or not check_password_hash(u["password_hash"], senha):
            conn.close()
            flash("CPF ou senha inválidos.", "error")
            return redirect(url_for("auth.login", next=next_url))

        # sucesso: registra último login (informativo)
        c.execute("UPDATE usuarios SET last_login_at=? WHERE id=?", (datetime.utcnow().isoformat(), u["id"]))
        conn.commit()
        conn.close()

        # sessão
        session.clear()
        session["user_id"] = u["id"]
        session["nome"] = u["nome"]
        session["role"] = u["role"]
        session["profissional_id"] = u["profissional_id"]

        primeiro_nome = (u["nome"] or "").split()[0] if u["nome"] else "usuário"
        flash(f"Bem-vindo, {primeiro_nome}!", "success")

        # ✅ Sempre vai pra HOME, a não ser que next seja seguro e não-admin
        return redirect(next_url)

    # GET
    return render_template("login.html", next_url=next_url)


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("Você saiu da sua sessão.", "info")
    return redirect(url_for("auth.login"))
