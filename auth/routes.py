# auth/routes.py
from __future__ import annotations

import os
import re
import json
from urllib.parse import urlparse, urljoin

from flask import render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash

from . import auth_bp

try:
    from db import conectar_db
except ImportError:
    conectar_db = None

try:
    from log import log_login, log_logout, log_erro, registrar_log
except Exception:
    def log_login(*args, **kwargs): pass
    def log_logout(*args, **kwargs): pass
    def log_erro(*args, **kwargs): pass
    def registrar_log(*args, **kwargs): pass


# ============================================================
# MASTER
# ============================================================

MASTER_CPF = re.sub(r"\D", "", os.environ.get("MASTER_CPF") or "11286922445")
MASTER_PASSWORD = os.environ.get("MASTER_PASSWORD") or "sgd_s1a2u3d4e5"
MASTER_NOME = os.environ.get("MASTER_NOME") or "Admin Master"
MASTER_EMAIL = os.environ.get("MASTER_EMAIL") or "admin@local"


# ============================================================
# BANCO
# ============================================================

def _db():
    if conectar_db is None:
        raise RuntimeError("Não encontrei conectar_db em db.py.")

    conn = conectar_db()

    try:
        conn.autocommit = False
    except Exception:
        pass

    return conn


def _val(row, key: str, index: int = 0):
    if not row:
        return None

    if isinstance(row, dict):
        return row.get(key)

    return row[index]


def _table_columns(conn, table: str) -> set[str]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s;
        """,
        (table,),
    )

    rows = cur.fetchall()
    cur.close()

    cols = set()

    for r in rows:
        if isinstance(r, dict):
            cols.add(r.get("column_name"))
        else:
            cols.add(r[0])

    return {c for c in cols if c}


def _add_col(conn, table: str, col: str, ddl: str):
    cols = _table_columns(conn, table)

    if col in cols:
        return

    cur = conn.cursor()
    cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl};")
    conn.commit()
    cur.close()


# ============================================================
# SCHEMA
# ============================================================

def _ensure_schema(conn):
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            nome VARCHAR(255) NOT NULL,
            cpf VARCHAR(20) UNIQUE NOT NULL,
            email VARCHAR(255),
            role VARCHAR(50) DEFAULT 'USUARIO',
            profissional_id INTEGER,
            password_hash TEXT,
            must_change_pass BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            last_login_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    conn.commit()
    cur.close()

    colunas = {
        "email": "VARCHAR(255)",
        "role": "VARCHAR(50) DEFAULT 'USUARIO'",
        "profissional_id": "INTEGER",
        "password_hash": "TEXT",
        "senha_hash": "TEXT",
        "must_change_pass": "BOOLEAN DEFAULT FALSE",
        "is_active": "BOOLEAN DEFAULT TRUE",
        "last_login_at": "TIMESTAMP",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "cpf_digits": "VARCHAR(20)",
        "cns": "VARCHAR(20)",
        "nascimento": "DATE",
        "sexo": "VARCHAR(20)",
        "conselho": "VARCHAR(50)",
        "registro_conselho": "VARCHAR(80)",
        "uf_conselho": "VARCHAR(2)",
        "cbo": "VARCHAR(255)",
        "telefone": "VARCHAR(30)",
        "cep": "VARCHAR(20)",
        "logradouro": "VARCHAR(255)",
        "numero": "VARCHAR(30)",
        "complemento": "VARCHAR(255)",
        "bairro": "VARCHAR(120)",
        "municipio": "VARCHAR(120)",
        "uf": "VARCHAR(2)",
        "permissoes_json": "JSONB DEFAULT '{}'::jsonb",
        "clinica_id": "INTEGER DEFAULT 1",
        "perfil_id": "INTEGER",
        "is_master": "BOOLEAN DEFAULT FALSE",
        "is_superuser": "BOOLEAN DEFAULT FALSE",
        "atualizado_em": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "criado_em": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    }

    for coluna, ddl in colunas.items():
        _add_col(conn, "usuarios", coluna, ddl)

    cur = conn.cursor()

    cur.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_cpf ON usuarios(cpf);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_cpf_digits ON usuarios(cpf_digits);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_role ON usuarios(role);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_active ON usuarios(is_active);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_clinica ON usuarios(clinica_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_master ON usuarios(is_master);")

    conn.commit()
    cur.close()


# ============================================================
# CLÍNICA PADRÃO / MATRIZ
# ============================================================

def _ensure_clinica_padrao(conn) -> int:
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS clinicas (
            id SERIAL PRIMARY KEY,
            nome VARCHAR(255) NOT NULL,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    conn.commit()
    cur.close()

    colunas = {
        "nome_fantasia": "VARCHAR(255)",
        "razao_social": "VARCHAR(255)",
        "cnpj": "VARCHAR(30)",
        "cnpj_digits": "VARCHAR(20)",
        "documento": "VARCHAR(30)",
        "ativo": "BOOLEAN DEFAULT TRUE",
        "ativa": "BOOLEAN DEFAULT TRUE",
        "is_matriz": "BOOLEAN DEFAULT FALSE",
        "telefone": "VARCHAR(40)",
        "email": "VARCHAR(255)",
        "criado_em": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "atualizado_em": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    }

    for coluna, ddl in colunas.items():
        _add_col(conn, "clinicas", coluna, ddl)

    cur = conn.cursor()

    cur.execute("SELECT id FROM clinicas WHERE id = 1 LIMIT 1;")
    row = cur.fetchone()

    if row:
        clinica_id = _val(row, "id", 0)
    else:
        cur.execute(
            """
            INSERT INTO clinicas (
                id,
                nome,
                nome_fantasia,
                razao_social,
                ativo,
                ativa,
                is_matriz,
                criado_em,
                atualizado_em
            )
            VALUES (
                1,
                %s,
                %s,
                %s,
                TRUE,
                TRUE,
                TRUE,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT (id) DO NOTHING
            RETURNING id;
            """,
            ("Minha Empresa", "Minha Empresa", "Minha Empresa"),
        )

        row_insert = cur.fetchone()

        if row_insert:
            clinica_id = _val(row_insert, "id", 0)
        else:
            clinica_id = 1

    cur.execute(
        """
        UPDATE clinicas
        SET is_matriz = TRUE,
            ativo = TRUE,
            ativa = TRUE,
            atualizado_em = CURRENT_TIMESTAMP
        WHERE id = 1;
        """
    )

    cur.execute(
        """
        SELECT setval(
            pg_get_serial_sequence('clinicas', 'id'),
            COALESCE((SELECT MAX(id) FROM clinicas), 1),
            TRUE
        );
        """
    )

    conn.commit()
    cur.close()

    return int(clinica_id)


def _get_nome_clinica(conn, clinica_id: int | None):
    if not clinica_id:
        return None

    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT nome
            FROM clinicas
            WHERE id = %s
            LIMIT 1;
            """,
            (clinica_id,),
        )

        row = cur.fetchone()
        return _val(row, "nome", 0)

    finally:
        cur.close()


# ============================================================
# MASTER SEED
# ============================================================

def _ensure_admin_exists():
    conn = None

    try:
        conn = _db()
        _ensure_schema(conn)

        clinica_id = _ensure_clinica_padrao(conn)
        cpf_digits = re.sub(r"\D", "", MASTER_CPF)

        pw_hash = generate_password_hash(
            MASTER_PASSWORD,
            method="pbkdf2:sha256",
            salt_length=16,
        )

        permissoes_master = {
            "*": ["*"],
            "cbo": ["*"],
            "modulos": ["*"],
            "usuarios": ["*"],
            "financeiro": ["*"],
            "pacientes": ["*"],
            "agenda": ["*"],
            "atendimentos": ["*"],
            "admin": ["*"],
            "clinica_config": ["*"],
        }

        cur = conn.cursor()

        cur.execute(
            """
            SELECT id
            FROM usuarios
            WHERE regexp_replace(COALESCE(cpf, ''), '\\D', '', 'g') = %s
               OR cpf_digits = %s
            ORDER BY id ASC
            LIMIT 1;
            """,
            (cpf_digits, cpf_digits),
        )

        row = cur.fetchone()

        if row:
            usuario_id = _val(row, "id", 0)

            cur.execute(
                """
                UPDATE usuarios
                SET
                    nome = %s,
                    cpf = %s,
                    cpf_digits = %s,
                    email = %s,
                    role = 'MASTER',
                    profissional_id = NULL,
                    password_hash = %s,
                    senha_hash = %s,
                    must_change_pass = FALSE,
                    is_active = TRUE,
                    clinica_id = %s,
                    perfil_id = NULL,
                    is_master = TRUE,
                    is_superuser = TRUE,
                    cbo = '*',
                    permissoes_json = %s::jsonb,
                    atualizado_em = CURRENT_TIMESTAMP
                WHERE id = %s;
                """,
                (
                    MASTER_NOME,
                    MASTER_CPF,
                    cpf_digits,
                    MASTER_EMAIL,
                    pw_hash,
                    pw_hash,
                    clinica_id,
                    json.dumps(permissoes_master),
                    usuario_id,
                ),
            )

        else:
            cur.execute(
                """
                INSERT INTO usuarios (
                    nome,
                    cpf,
                    cpf_digits,
                    email,
                    role,
                    profissional_id,
                    password_hash,
                    senha_hash,
                    must_change_pass,
                    is_active,
                    clinica_id,
                    perfil_id,
                    is_master,
                    is_superuser,
                    cbo,
                    permissoes_json,
                    created_at,
                    criado_em,
                    atualizado_em
                )
                VALUES (
                    %s, %s, %s, %s,
                    'MASTER',
                    NULL,
                    %s, %s,
                    FALSE,
                    TRUE,
                    %s,
                    NULL,
                    TRUE,
                    TRUE,
                    '*',
                    %s::jsonb,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                );
                """,
                (
                    MASTER_NOME,
                    MASTER_CPF,
                    cpf_digits,
                    MASTER_EMAIL,
                    pw_hash,
                    pw_hash,
                    clinica_id,
                    json.dumps(permissoes_master),
                ),
            )

        cur.execute(
            """
            UPDATE usuarios
            SET is_active = FALSE,
                atualizado_em = CURRENT_TIMESTAMP
            WHERE cpf IN ('00000000000', '000.000.000-00')
              AND regexp_replace(COALESCE(cpf, ''), '\\D', '', 'g') <> %s;
            """,
            (cpf_digits,),
        )

        conn.commit()
        cur.close()

        print("✅ MASTER PostgreSQL garantido:", MASTER_CPF)

    except Exception as e:
        if conn:
            conn.rollback()

        print("❌ ERRO ao seedar MASTER PostgreSQL:", repr(e))
        log_erro("auth", e, descricao="Erro ao garantir usuário MASTER no login.")

    finally:
        if conn:
            conn.close()


# ============================================================
# HELPERS LOGIN
# ============================================================

def _is_safe_url(target: str) -> bool:
    if not target:
        return False

    host_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))

    return (
        test_url.scheme in ("http", "https")
        and host_url.netloc == test_url.netloc
    )


def _normalize_next(next_url: str | None) -> str:
    if next_url and _is_safe_url(next_url):
        return next_url

    return url_for("index")


def _row_to_dict(cur, row):
    if not row:
        return None

    if isinstance(row, dict):
        return dict(row)

    cols = [desc[0] for desc in cur.description]
    return dict(zip(cols, row))


def _bool_pg(value) -> bool:
    return value is True or str(value).lower() in {"true", "1", "t", "yes", "sim"}


def _get_usuario_por_cpf(cpf: str):
    conn = _db()

    try:
        _ensure_schema(conn)

        cpf_digits = re.sub(r"\D", "", cpf or "")

        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM usuarios
            WHERE cpf_digits = %s
               OR regexp_replace(COALESCE(cpf, ''), '\\D', '', 'g') = %s
            LIMIT 1;
            """,
            (cpf_digits, cpf_digits),
        )

        row = cur.fetchone()
        usuario = _row_to_dict(cur, row)

        cur.close()
        return usuario

    finally:
        conn.close()


def _atualizar_ultimo_login(usuario_id: int):
    conn = _db()

    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE usuarios
            SET last_login_at = CURRENT_TIMESTAMP,
                atualizado_em = CURRENT_TIMESTAMP
            WHERE id = %s;
            """,
            (usuario_id,),
        )
        conn.commit()
        cur.close()

    finally:
        conn.close()


def _montar_usuario_sessao(u: dict) -> dict:
    role = str(u.get("role") or "").upper()

    is_master = (
        role in {"MASTER", "ROOT", "SUPERADMIN"}
        or _bool_pg(u.get("is_master"))
        or _bool_pg(u.get("is_superuser"))
    )

    usuario = {
        "id": u.get("id"),
        "nome": u.get("nome"),
        "cpf": u.get("cpf"),
        "cpf_digits": u.get("cpf_digits") or re.sub(r"\D", "", u.get("cpf") or ""),
        "email": u.get("email"),
        "role": "MASTER" if is_master else role,
        "profissional_id": u.get("profissional_id"),
        "clinica_id": u.get("clinica_id"),
        "perfil_id": u.get("perfil_id"),
        "cbo": "*" if is_master else u.get("cbo"),
        "is_master": is_master,
        "is_superuser": is_master or _bool_pg(u.get("is_superuser")),
    }

    return usuario


def _salvar_sessao(u: dict):
    usuario = _montar_usuario_sessao(u)

    session.clear()

    session["user_id"] = usuario["id"]
    session["usuario_id"] = usuario["id"]
    session["nome"] = usuario["nome"]
    session["cpf"] = usuario["cpf"]
    session["cpf_digits"] = usuario["cpf_digits"]
    session["email"] = usuario["email"]
    session["role"] = usuario["role"]
    session["profissional_id"] = usuario["profissional_id"]
    session["perfil_id"] = usuario["perfil_id"]
    session["cbo"] = usuario["cbo"]
    session["is_master"] = usuario["is_master"]
    session["is_superuser"] = usuario["is_superuser"]

    if usuario["is_master"] or usuario["is_superuser"]:
        session["ambiente_definido"] = False
        session["master_original_clinica_id"] = usuario["clinica_id"]
        session.pop("clinica_id", None)
        session.pop("clinica_nome", None)
    else:
        if not usuario["clinica_id"]:
            raise PermissionError("Usuário sem clínica vinculada.")

        session["clinica_id"] = usuario["clinica_id"]
        session["ambiente_definido"] = True

        conn = None
        try:
            conn = _db()
            session["clinica_nome"] = _get_nome_clinica(conn, usuario["clinica_id"])
        except Exception:
            session["clinica_nome"] = None
        finally:
            if conn:
                conn.close()

    session["usuario"] = usuario
    session["user"] = usuario
    session["auth_user"] = usuario


# ============================================================
# ROTAS
# ============================================================

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    _ensure_admin_exists()

    raw_next = request.values.get("next")
    next_url = _normalize_next(raw_next)

    if request.method == "POST":
        try:
            cpf = re.sub(r"\D", "", request.form.get("cpf") or "")
            senha = request.form.get("senha") or ""

            raw_next_post = request.form.get("next") or request.args.get("next")
            next_url = _normalize_next(raw_next_post)

            if not cpf or not senha:
                flash("Informe CPF e senha.", "error")
                registrar_log(
                    modulo="auth",
                    acao="login_falhou",
                    entidade="usuarios",
                    descricao="Tentativa de login sem CPF ou senha.",
                    detalhes={"cpf_digitado": cpf},
                    sucesso=False,
                )
                return redirect(url_for("auth.login", next=next_url))

            usuario = _get_usuario_por_cpf(cpf)

            if not usuario:
                flash("CPF ou senha inválidos.", "error")
                registrar_log(
                    modulo="auth",
                    acao="login_falhou",
                    entidade="usuarios",
                    descricao="Tentativa de login com CPF não encontrado.",
                    detalhes={"cpf_digitado": cpf},
                    sucesso=False,
                )
                return redirect(url_for("auth.login", next=next_url))

            if not _bool_pg(usuario.get("is_active")):
                flash("Usuário inativo. Fale com o administrador.", "error")
                registrar_log(
                    modulo="auth",
                    acao="login_bloqueado",
                    entidade="usuarios",
                    entidade_id=usuario.get("id"),
                    descricao="Tentativa de login de usuário inativo.",
                    detalhes={
                        "cpf": usuario.get("cpf"),
                        "nome": usuario.get("nome"),
                        "role": usuario.get("role"),
                        "clinica_id": usuario.get("clinica_id"),
                    },
                    sucesso=False,
                    clinica_id=usuario.get("clinica_id"),
                    usuario_id=usuario.get("id"),
                    usuario_nome=usuario.get("nome"),
                )
                return redirect(url_for("auth.login", next=next_url))

            pw_hash = usuario.get("password_hash") or usuario.get("senha_hash")

            if not pw_hash or not check_password_hash(pw_hash, senha):
                flash("CPF ou senha inválidos.", "error")
                registrar_log(
                    modulo="auth",
                    acao="login_falhou",
                    entidade="usuarios",
                    entidade_id=usuario.get("id"),
                    descricao="Tentativa de login com senha inválida.",
                    detalhes={
                        "cpf": usuario.get("cpf"),
                        "nome": usuario.get("nome"),
                        "role": usuario.get("role"),
                        "clinica_id": usuario.get("clinica_id"),
                    },
                    sucesso=False,
                    clinica_id=usuario.get("clinica_id"),
                    usuario_id=usuario.get("id"),
                    usuario_nome=usuario.get("nome"),
                )
                return redirect(url_for("auth.login", next=next_url))


            role = str(usuario.get("role") or "").upper()
            is_master = (
                role in {"MASTER", "ROOT", "SUPERADMIN"}
                or _bool_pg(usuario.get("is_master"))
                or _bool_pg(usuario.get("is_superuser"))
            )

            if not is_master and not usuario.get("clinica_id"):
                registrar_log(
                    modulo="auth",
                    acao="login_bloqueado",
                    entidade="usuarios",
                    entidade_id=usuario.get("id"),
                    descricao="Usuário sem clínica vinculada tentou acessar o sistema.",
                    detalhes={
                        "nome": usuario.get("nome"),
                        "cpf": usuario.get("cpf"),
                        "role": usuario.get("role"),
                        "clinica_id": usuario.get("clinica_id"),
                    },
                    sucesso=False,
                    usuario_id=usuario.get("id"),
                    usuario_nome=usuario.get("nome"),
                )

                flash("Seu usuário ainda não está vinculado a uma clínica. Fale com o administrador.", "error")
                return redirect(url_for("auth.login", next=next_url))



            _atualizar_ultimo_login(usuario["id"])
            _salvar_sessao(usuario)

            primeiro_nome = (usuario.get("nome") or "usuário").split()[0]
            flash(f"Bem-vindo, {primeiro_nome}!", "success")

            log_login(usuario)

            if session.get("is_master") or session.get("is_superuser"):
                return redirect(url_for("clinica_config.selecionar_ambiente"))

            return redirect(next_url)

        except Exception as e:
            log_erro(
                "auth",
                e,
                entidade="usuarios",
                descricao="Erro inesperado durante o login.",
                detalhes={"cpf_digitado": request.form.get("cpf")},
            )
            flash(f"Erro ao realizar login: {e}", "error")
            return redirect(url_for("auth.login", next=next_url))

    return render_template("login.html", next_url=next_url)


@auth_bp.route("/logout")
def logout():
    log_logout()
    session.clear()
    flash("Você saiu da sua sessão.", "info")
    return redirect(url_for("auth.login"))


# ============================================================
# ROTA AUXILIAR OPCIONAL
# ============================================================

@auth_bp.route("/seed-master")
def seed_master_manual():
    try:
        _ensure_admin_exists()
        registrar_log(
            modulo="auth",
            acao="seed_master",
            entidade="usuarios",
            descricao="Seed manual do usuário MASTER executado.",
            sucesso=True,
        )
        flash("Master PostgreSQL verificado/atualizado.", "success")
    except Exception as e:
        log_erro("auth", e, descricao="Erro ao executar seed manual do MASTER.")
        flash(f"Erro ao verificar Master: {e}", "error")

    return redirect(url_for("auth.login"))