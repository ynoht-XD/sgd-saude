from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime
from urllib.parse import urlparse, urljoin

from flask import render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash

from . import auth_bp
from db import conectar_db


# ============================================================
# MASTER (preferência: ENV no Render)
# ============================================================
MASTER_CPF = re.sub(r"\D+", "", os.getenv("MASTER_CPF") or "11286922445")
MASTER_PASSWORD = os.getenv("MASTER_PASSWORD") or "sgd_s1a2u3d4e5"
MASTER_NOME = os.getenv("MASTER_NOME") or "Admin Master"
MASTER_EMAIL = os.getenv("MASTER_EMAIL") or "admin@local"


# ============================================================
# DB helpers (usa o conector unificado do projeto)
# ============================================================

def _ensure_schema(conn: sqlite3.Connection):
    """
    Cria a tabela 'usuarios' mínima se não existir.
    (Se tua tabela já existir e for maior, isso não quebra.)
    """
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            nome             TEXT NOT NULL,
            cpf              TEXT NOT NULL UNIQUE,   -- login
            email            TEXT,
            role             TEXT NOT NULL DEFAULT 'ADMIN',
            profissional_id  INTEGER,
            password_hash    TEXT NOT NULL,
            must_change_pass INTEGER NOT NULL DEFAULT 0,
            is_active        INTEGER NOT NULL DEFAULT 1,
            last_login_at    TEXT,
            created_at       TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_role   ON usuarios(role);")
    c.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_active ON usuarios(is_active);")
    conn.commit()


def _ensure_admin_exists():
    """
    ✅ Seed do master idempotente e com log de erro.
    - Não engole exceção silenciosamente
    - Funciona mesmo se o banco resetar no Render (/tmp)
    """
    try:
        conn = conectar_db()
        conn.row_factory = sqlite3.Row
        _ensure_schema(conn)

        cpf = MASTER_CPF
        if not cpf or len(cpf) < 11:
            print("⚠️ MASTER_CPF inválido; seed do master ignorado.")
            conn.close()
            return

        pw_hash = generate_password_hash(
            MASTER_PASSWORD,
            method="pbkdf2:sha256",
            salt_length=16
        )

        c = conn.cursor()

        # SQLite >= 3.24: UPSERT
        c.execute(
            """
            INSERT INTO usuarios (nome, cpf, email, role, password_hash, must_change_pass, is_active, created_at)
            VALUES (?, ?, ?, 'ADMIN', ?, 0, 1, ?)
            ON CONFLICT(cpf) DO UPDATE SET
                nome=excluded.nome,
                email=excluded.email,
                role='ADMIN',
                is_active=1,
                password_hash=excluded.password_hash,
                must_change_pass=0
            """,
            (MASTER_NOME, cpf, MASTER_EMAIL, pw_hash, datetime.utcnow().isoformat()),
        )

        # opcional: desativa placeholder antigo
        c.execute("UPDATE usuarios SET is_active=0 WHERE cpf='00000000000'")

        conn.commit()
        conn.close()

        print(f"✅ Master garantido: CPF={cpf} (ADMIN)")

    except Exception as e:
        # Agora aparece no Render Logs e a gente consegue corrigir de verdade
        import traceback
        print("❌ ERRO ao seedar MASTER:", str(e))
        traceback.print_exc()


# ============================================================
# Segurança do redirect
# ============================================================

def _is_safe_url(target: str) -> bool:
    """Evita open redirect (não deixa redirecionar pra outro domínio)."""
    if not target:
        return False
    host_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ("http", "https") and host_url.netloc == test_url.netloc


def _normalize_next(next_url: str | None) -> str:
    """
    - padrão: HOME (/)
    - aceita next apenas se for seguro e NÃO for /admin
    """
    if next_url and _is_safe_url(next_url) and not next_url.startswith("/admin"):
        return next_url
    return url_for("index")


# ============================================================
# ROTAS
# ============================================================

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    # ✅ garante master em todo acesso ao login
    _ensure_admin_exists()

    raw_next = request.values.get("next")
    next_url = _normalize_next(raw_next)

    if request.method == "POST":
        cpf = re.sub(r"\D+", "", (request.form.get("cpf") or ""))
        senha = request.form.get("senha") or ""

        raw_next_post = request.form.get("next") or request.args.get("next")
        next_url = _normalize_next(raw_next_post)

        if not cpf or not senha:
            flash("Informe CPF e senha.", "error")
            return redirect(url_for("auth.login", next=next_url))

        conn = conectar_db()
        try:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()

            c.execute("SELECT * FROM usuarios WHERE cpf=? AND is_active=1 LIMIT 1", (cpf,))
            u = c.fetchone()

            if not u:
                flash("CPF ou senha inválidos.", "error")
                return redirect(url_for("auth.login", next=next_url))

            if not check_password_hash(u["password_hash"], senha):
                flash("CPF ou senha inválidos.", "error")
                return redirect(url_for("auth.login", next=next_url))

            # sucesso: registra último login
            c.execute(
                "UPDATE usuarios SET last_login_at=? WHERE id=?",
                (datetime.utcnow().isoformat(), u["id"])
            )
            conn.commit()

            # sessão
            session.clear()
            session["user_id"] = int(u["id"])
            session["nome"] = u["nome"]
            session["role"] = (u["role"] or "").upper()
            session["profissional_id"] = u["profissional_id"]

            primeiro_nome = (u["nome"] or "").split()[0] if u["nome"] else "usuário"
            flash(f"Bem-vindo, {primeiro_nome}!", "success")

            return redirect(next_url, code=303)

        finally:
            try:
                conn.close()
            except Exception:
                pass

    # GET
    return render_template("login.html", next_url=next_url)


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("Você saiu da sua sessão.", "info")
    return redirect(url_for("auth.login"), code=303)
