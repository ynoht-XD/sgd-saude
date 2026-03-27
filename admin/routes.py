# admin/routes.py
from __future__ import annotations

from datetime import datetime, timedelta
import sqlite3
import json
import re

from flask import render_template, request, redirect, url_for, flash, jsonify
from werkzeug.security import generate_password_hash

from . import admin_bp, admin_required

# ======= Banco de dados unificado =======
from db import conectar_db  # use sempre este conector; não use sqlite3.connect direto


# =============================================================================
# HELPERS (ÚNICOS)
# =============================================================================

def only_digits(s: str) -> str:
    return re.sub(r"\D+", "", s or "")

def has_table(conn, table_name: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=? LIMIT 1;",
        (table_name,),
    )
    return cur.fetchone() is not None

def list_columns(conn, table_name: str) -> set:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name});")
    return {row[1] for row in cur.fetchall()}  # row[1] = name

def digits_sql(expr: str) -> str:
    """
    Remove caracteres não numéricos via REPLACE em SQLite (sem REGEXP nativo).
    """
    s = expr
    for ch in (".", "-", "/", "(", ")", " "):
        s = f"REPLACE({s}, '{ch}', '')"
    return s

def db_conn(readonly: bool = False):
    """
    Wrapper único do conector do projeto.
    - NÃO passa readonly como argumento (compatível com teu db.py atual).
    - Se readonly=True, ativa PRAGMA query_only (SQLite) para proteger escrita acidental.
    """
    conn = conectar_db()  # <<< sem readonly=
    try:
        if readonly:
            conn.execute("PRAGMA query_only = 1;")
    except Exception:
        # se algum ambiente/driver não suportar, só ignora
        pass
    return conn


# =============================================================================
# USERS · SCHEMA / MIGRAÇÃO
# =============================================================================

def ensure_users_table():
    """
    - Cria a tabela usuarios se não existir.
    - Garante TODAS as colunas usadas pelas rotas/forms.
    - Garante ambas colunas de senha: senha_hash e password_hash (legado).
    - Espelha valores entre elas quando uma delas estiver nula.
    - Retropreenche cpf_digits e criado_em quando vazios.
    - Cria índices únicos idempotentes.
    """
    conn = conectar_db()
    try:
        cur = conn.cursor()

        # 1) Cria base (compatível com legado)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                nome              TEXT,
                email             TEXT,
                cpf               TEXT,
                cpf_digits        TEXT,
                cns               TEXT,
                nascimento        TEXT,
                sexo              TEXT,
                conselho          TEXT,
                registro_conselho TEXT,
                uf_conselho       TEXT,
                cbo               TEXT,
                telefone          TEXT,
                role              TEXT,
                is_active         INTEGER DEFAULT 1,
                cep               TEXT,
                logradouro        TEXT,
                numero            TEXT,
                complemento       TEXT,
                bairro            TEXT,
                municipio         TEXT,
                uf                TEXT,
                permissoes_json   TEXT,
                senha_hash        TEXT,
                password_hash     TEXT,  -- legado
                criado_em         TEXT,
                atualizado_em     TEXT
            );
        """)

        # 2) Adiciona colunas ausentes
        def colset():
            cur.execute("PRAGMA table_info(usuarios);")
            return {r[1] for r in cur.fetchall()}

        cols = colset()

        def ensure_col(name: str, ddl: str):
            nonlocal cols
            if name not in cols:
                cur.execute(f"ALTER TABLE usuarios ADD COLUMN {ddl};")
                cols = colset()

        # Campos de identificação/controle
        ensure_col("nome", "nome TEXT")
        ensure_col("email", "email TEXT")
        ensure_col("cpf", "cpf TEXT")
        ensure_col("cpf_digits", "cpf_digits TEXT")
        ensure_col("role", "role TEXT")
        ensure_col("is_active", "is_active INTEGER DEFAULT 1")

        # Colunas de senha — garanta ambas
        ensure_col("senha_hash", "senha_hash TEXT")
        ensure_col("password_hash", "password_hash TEXT")

        ensure_col("criado_em", "criado_em TEXT")
        ensure_col("atualizado_em", "atualizado_em TEXT")

        # Profissionais/pessoais
        ensure_col("cns", "cns TEXT")
        ensure_col("nascimento", "nascimento TEXT")
        ensure_col("sexo", "sexo TEXT")
        ensure_col("conselho", "conselho TEXT")
        ensure_col("registro_conselho", "registro_conselho TEXT")
        ensure_col("uf_conselho", "uf_conselho TEXT")
        ensure_col("cbo", "cbo TEXT")
        ensure_col("telefone", "telefone TEXT")

        # Endereço
        ensure_col("cep", "cep TEXT")
        ensure_col("logradouro", "logradouro TEXT")
        ensure_col("numero", "numero TEXT")
        ensure_col("complemento", "complemento TEXT")
        ensure_col("bairro", "bairro TEXT")
        ensure_col("municipio", "municipio TEXT")
        ensure_col("uf", "uf TEXT")

        ensure_col("permissoes_json", "permissoes_json TEXT")

        # 3) Retropreencher campos
        cols = colset()

        if "cpf" in cols and "cpf_digits" in cols:
            cur.execute("""
                UPDATE usuarios
                   SET cpf_digits = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(cpf,''),'.',''),'-',''),'/',''),'(',''),')',''),' ','')
                 WHERE cpf IS NOT NULL
                   AND (cpf_digits IS NULL OR TRIM(cpf_digits)='');
            """)

        if "criado_em" in cols:
            cur.execute("""
                UPDATE usuarios
                   SET criado_em = datetime('now')
                 WHERE criado_em IS NULL OR TRIM(criado_em)='';
            """)

        # Espelhar senhas entre colunas (para legados com NOT NULL numa delas)
        if "senha_hash" in cols and "password_hash" in cols:
            # Se só senha_hash tem valor, copia para password_hash
            cur.execute("""
                UPDATE usuarios
                   SET password_hash = senha_hash
                 WHERE (password_hash IS NULL OR TRIM(password_hash) = '')
                   AND (senha_hash IS NOT NULL AND TRIM(senha_hash) <> '');
            """)
            # Se só password_hash tem valor, copia para senha_hash
            cur.execute("""
                UPDATE usuarios
                   SET senha_hash = password_hash
                 WHERE (senha_hash IS NULL OR TRIM(senha_hash) = '')
                   AND (password_hash IS NOT NULL AND TRIM(password_hash) <> '');
            """)

        # 4) Índices únicos idempotentes (filtrados)
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_email
                ON usuarios(email)
                WHERE email IS NOT NULL AND TRIM(email) <> '';
        """)
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_cpf
                ON usuarios(cpf)
                WHERE cpf IS NOT NULL AND TRIM(cpf) <> '';
        """)
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_cpf_digits
                ON usuarios(cpf_digits)
                WHERE cpf_digits IS NOT NULL AND TRIM(cpf_digits) <> '';
        """)

        conn.commit()
    finally:
        conn.close()


# Execute migração ao importar o módulo (pode mover para create_app se preferir)
ensure_users_table()


# =============================================================================
# CBO · SCHEMA + SEED + CRUD
# =============================================================================

CBO_SEED = [
    ("251605", "Serviço Social"),
    ("223505", "Enfermagem"),
    ("251510", "Psicólogos"),
    ("223905", "Terapeuta Ocupacional"),
    ("223810", "Fonoaudiólogos"),
    ("223605", "Fisioterapeutas"),
    ("239425", "Pedagogos"),
    ("239415", "Pedagogos"),
    ("223710", "Nutrição"),
    ("225112", "Neurologista"),
    ("225125", "Clínico"),
    ("225133", "Psiquiatra"),
    ("225270", "Ortopedista"),
    ("225275", "Otorrino"),
]

def ensure_cbo_table():
    """
    Tabela catálogo de CBOs (código + descrição).
    - Código é UNIQUE
    - Seed inicial idempotente
    """
    conn = db_conn(False)
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cbos_catalogo (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo        TEXT NOT NULL,
                descricao     TEXT NOT NULL,
                criado_em     TEXT,
                atualizado_em TEXT
            );
        """)
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_cbos_catalogo_codigo
            ON cbos_catalogo(codigo);
        """)

        # Seed idempotente: insere se não existir
        for codigo, descricao in CBO_SEED:
            cur.execute("""
                INSERT OR IGNORE INTO cbos_catalogo (codigo, descricao, criado_em)
                VALUES (?, ?, datetime('now'));
            """, (codigo, descricao))

        conn.commit()
    finally:
        conn.close()

def get_cbos_catalogo():
    ensure_cbo_table()
    conn = db_conn(True)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, codigo, descricao
              FROM cbos_catalogo
             ORDER BY descricao ASC, codigo ASC;
        """)
        rows = cur.fetchall() or []
        return [{"id": r["id"], "codigo": r["codigo"], "descricao": r["descricao"]} for r in rows]
    finally:
        conn.close()


@admin_bp.route("/cbos")
@admin_required
def cbos_listar():
    cbos = get_cbos_catalogo()
    return render_template("admin-cbos.html", cbos=cbos)

@admin_bp.route("/cbos/novo", methods=["POST"])
@admin_required
def cbos_criar():
    codigo = only_digits(request.form.get("codigo") or "")
    descricao = (request.form.get("descricao") or "").strip()

    if not codigo or len(codigo) < 6:
        flash("Informe um CBO válido (apenas números).", "error")
        return redirect(url_for("admin.cbos_listar"))
    if not descricao:
        flash("Informe a descrição do CBO.", "error")
        return redirect(url_for("admin.cbos_listar"))

    conn = db_conn(False)
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO cbos_catalogo (codigo, descricao, criado_em)
            VALUES (?, ?, datetime('now'));
        """, (codigo, descricao))
        conn.commit()
        flash("CBO adicionado com sucesso.", "success")
    except sqlite3.IntegrityError:
        flash("Já existe um CBO com esse código.", "error")
    except Exception as e:
        flash(f"Erro ao adicionar CBO: {e}", "error")
    finally:
        conn.close()

    return redirect(url_for("admin.cbos_listar"))

@admin_bp.route("/cbos/<int:cbo_id>/editar", methods=["POST"])
@admin_required
def cbos_editar(cbo_id: int):
    codigo = only_digits(request.form.get("codigo") or "")
    descricao = (request.form.get("descricao") or "").strip()

    if not codigo or len(codigo) < 6:
        flash("Informe um CBO válido (apenas números).", "error")
        return redirect(url_for("admin.cbos_listar"))
    if not descricao:
        flash("Informe a descrição do CBO.", "error")
        return redirect(url_for("admin.cbos_listar"))

    conn = db_conn(False)
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE cbos_catalogo
               SET codigo=?,
                   descricao=?,
                   atualizado_em=datetime('now')
             WHERE id=?;
        """, (codigo, descricao, cbo_id))
        conn.commit()
        flash("CBO atualizado com sucesso.", "success")
    except sqlite3.IntegrityError:
        flash("Já existe outro CBO com esse código.", "error")
    except Exception as e:
        flash(f"Erro ao atualizar CBO: {e}", "error")
    finally:
        conn.close()

    return redirect(url_for("admin.cbos_listar"))

@admin_bp.route("/cbos/<int:cbo_id>/remover", methods=["POST"])
@admin_required
def cbos_remover(cbo_id: int):
    conn = db_conn(False)
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM cbos_catalogo WHERE id=?;", (cbo_id,))
        conn.commit()
        flash("CBO removido com sucesso.", "success")
    except Exception as e:
        flash(f"Erro ao remover CBO: {e}", "error")
    finally:
        conn.close()

    return redirect(url_for("admin.cbos_listar"))

@admin_bp.route("/cbos.json")
@admin_required
def cbos_json():
    return jsonify(get_cbos_catalogo())


# =============================================================================
# CONST · NÍVEIS
# =============================================================================

NIVEIS = [
    {
        "slug": "ADMIN",
        "nome": "Administrador",
        "permissoes": ["cadastro","pacientes","atendimentos","agenda","export_bpai","export_apac","export_ciha","financeiro","rh"],
    },
    {
        "slug": "RECEPCAO",
        "nome": "Recepção",
        "permissoes": ["cadastro","pacientes","atendimentos","agenda"],
    },
    {
        "slug": "PROFISSIONAL",
        "nome": "Profissional",
        "permissoes": ["pacientes","atendimentos","agenda"],
    },
]


# =============================================================================
# USER HELPERS
# =============================================================================

def load_user(uid: int):
    conn = db_conn(True)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM usuarios WHERE id=? LIMIT 1;", (uid,))
        return cur.fetchone()
    finally:
        conn.close()


# =============================================================================
# DASHBOARD
# =============================================================================

@admin_bp.route("/")
@admin_required
def admin_home():
    try:
        conn = db_conn(True)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(1), SUM(is_active=1) FROM usuarios;")
        row = cur.fetchone() or (0, 0)
        total_usuarios = int(row[0] or 0)
        usuarios_ativos = int(row[1] or 0)
    except Exception:
        total_usuarios = 0
        usuarios_ativos = 0
    finally:
        try:
            conn.close()
        except Exception:
            pass

    ctx = {
        "total_usuarios": total_usuarios,
        "usuarios_ativos": usuarios_ativos,
        "modulos_habilitados": 3,
        "ultimo_backup": (datetime.now() - timedelta(days=2)).strftime("%d/%m/%Y %H:%M"),
    }
    return render_template("admin.html", **ctx)


# =============================================================================
# USUÁRIOS - LISTAR + MODAL
# =============================================================================

@admin_bp.route("/usuarios")
@admin_required
def usuarios_listar():
    ensure_users_table()   # garante colunas/índices
    ensure_cbo_table()     # garante catálogo CBO seedado
    usuarios = []

    try:
        conn = db_conn(True)
        cur = conn.cursor()
        cur.execute("""
            SELECT id, nome, cpf, cpf_digits, email, role, is_active, criado_em
              FROM usuarios
             ORDER BY id DESC
        """)
        rows = cur.fetchall() or []
        for r in rows:
            usuarios.append({
                "id": r["id"],
                "nome": r["nome"],
                "cpf": r["cpf"],
                "cpf_digits": r["cpf_digits"],
                "email": r["email"],
                "role": r["role"],
                "is_active": bool(r["is_active"]),
                "criado_em": r["criado_em"],
            })
    except Exception as e:
        flash(f"Falha ao carregar usuários: {e}", "error")
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return render_template(
        "admin-usuarios.html",
        usuarios=usuarios,
        niveis=NIVEIS,
        cbos_catalogo=get_cbos_catalogo(),  # <<< AQUI AGORA VEM DO BANCO
    )


# =============================================================================
# USUÁRIOS - CRIAR
# =============================================================================

@admin_bp.route("/usuarios/novo", methods=["GET", "POST"])
@admin_required
def usuarios_criar():
    if request.method != "POST":
        return redirect(url_for("admin.usuarios_listar"))

    # inicializa tudo para evitar "referenced before assignment"
    nome = cpf = role = None
    cpf_digits = None
    email = cns = nasc = sexo = None
    conselho = registro_conselho = uf_conselho = None
    cbo = telefone = None
    cep = logr = numero = comp = bairro = municipio = uf = None
    permissoes_json = None
    senha_hash = None
    conn = None

    try:
        def nz(v):
            v = (v or "").strip()
            return v if v else None

        # ------ validações básicas ------
        nome = (request.form.get("nome") or "").strip()
        cpf  = (request.form.get("cpf") or "").strip()
        role = (request.form.get("role") or "").strip() or "RECEPCAO"
        is_active = 1 if (request.form.get("is_active") or "1") == "1" else 0

        if not nome or not cpf or not role:
            flash("Preencha ao menos Nome, CPF e Nível.", "error")
            return redirect(url_for("admin.usuarios_listar"))

        # CPF dígitos
        cpf_digits = only_digits(cpf)
        if len(cpf_digits) != 11:
            flash("CPF inválido. Informe 11 dígitos.", "error")
            return redirect(url_for("admin.usuarios_listar"))

        # senha
        senha  = request.form.get("senha") or ""
        senha2 = request.form.get("senha2") or ""
        if not senha or len(senha) < 6:
            flash("Defina uma senha com pelo menos 6 caracteres.", "error")
            return redirect(url_for("admin.usuarios_listar"))
        if senha != senha2:
            flash("A confirmação da senha não confere.", "error")
            return redirect(url_for("admin.usuarios_listar"))
        senha_hash = generate_password_hash(senha, method="pbkdf2:sha256", salt_length=16)

        # opcionais (normalizados para None)
        email = nz(request.form.get("email"))
        cns   = nz(request.form.get("cns"))
        nasc  = nz(request.form.get("nascimento"))
        sexo  = nz(request.form.get("sexo"))

        conselho          = nz(request.form.get("conselho"))
        registro_conselho = nz(request.form.get("registro_conselho"))
        uf_conselho       = nz(request.form.get("uf_conselho"))
        cbo               = nz(request.form.get("cbo"))

        telefone = nz(request.form.get("telefone"))

        cep    = nz(request.form.get("cep"))
        logr   = nz(request.form.get("logradouro"))
        numero = nz(request.form.get("numero"))
        comp   = nz(request.form.get("complemento"))
        bairro = nz(request.form.get("bairro"))
        municipio = nz(request.form.get("municipio"))
        uf       = nz(request.form.get("uf"))

        # permissoes rápidas (perm_* = 1)
        permissoes = []
        for k in request.form.keys():
            if k.startswith("perm_") and request.form.get(k) == "1":
                permissoes.append(k.replace("perm_", "", 1))
        permissoes_json = json.dumps(permissoes, ensure_ascii=False) if permissoes else None

        # garante schema
        ensure_users_table()

        conn = db_conn(False)
        cur = conn.cursor()

        # checa colunas existentes (suporte a legado)
        cur.execute("PRAGMA table_info(usuarios);")
        cols = {r[1] for r in cur.fetchall()}
        has_pwd_pt = "senha_hash" in cols
        has_pwd_en = "password_hash" in cols

        # monta INSERT dinamicamente
        columns = [
            "nome","email","cpf","cpf_digits","cns","nascimento","sexo",
            "conselho","registro_conselho","uf_conselho","cbo",
            "telefone","role","is_active",
            "cep","logradouro","numero","complemento","bairro","municipio","uf",
            "permissoes_json"
        ]
        values = [
            nome, email, cpf, cpf_digits, cns, nasc, sexo,
            conselho, registro_conselho, uf_conselho, cbo,
            telefone, role, is_active,
            cep, logr, numero, comp, bairro, municipio, uf,
            permissoes_json
        ]

        # adiciona colunas de senha conforme existirem
        if has_pwd_pt:
            columns.append("senha_hash"); values.append(senha_hash)
        if has_pwd_en:
            columns.append("password_hash"); values.append(senha_hash)

        placeholders = ",".join("?" for _ in values)
        sql = f"INSERT INTO usuarios ({','.join(columns)}) VALUES ({placeholders});"
        cur.execute(sql, values)

        uid = cur.lastrowid

        # seta criado_em (não usamos default não-constante em ALTER TABLE)
        cur.execute(
            "UPDATE usuarios SET criado_em = COALESCE(criado_em, datetime('now')) WHERE id=?;",
            (uid,),
        )
        conn.commit()

        flash("Usuário criado com sucesso.", "success")
        return redirect(url_for("admin.usuarios_listar"))

    except sqlite3.IntegrityError as e:
        msg = str(e)
        if "cpf_digits" in msg or "usuarios.cpf_digits" in msg or "idx_usuarios_cpf_digits" in msg:
            flash("Já existe um usuário com esse CPF.", "error")
        elif "usuarios.cpf" in msg or "idx_usuarios_cpf" in msg:
            flash("Já existe um usuário com esse CPF.", "error")
        elif "usuarios.email" in msg or "idx_usuarios_email" in msg:
            flash("Já existe um usuário com esse e-mail.", "error")
        else:
            flash(f"Erro de integridade ao salvar o usuário: {msg}", "error")
        return redirect(url_for("admin.usuarios_listar"))
    except Exception as e:
        flash(f"Erro ao criar usuário: {e}", "error")
        return redirect(url_for("admin.usuarios_listar"))
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


# =============================================================================
# USUÁRIOS - OBTÉM DADOS (JSON) para preencher modal
# =============================================================================

@admin_bp.route("/usuarios/<int:uid>.json")
@admin_required
def usuarios_json(uid):
    row = load_user(uid)
    if not row:
        return jsonify({"error": "Usuário não encontrado"}), 404
    data = dict(row)
    data.pop("senha_hash", None)
    data.pop("password_hash", None)
    return jsonify(data)


# =============================================================================
# USUÁRIOS - EDITAR
# =============================================================================

@admin_bp.route("/usuarios/<int:uid>/editar", methods=["POST"])
@admin_required
def usuarios_editar(uid):
    row = load_user(uid)
    if not row:
        flash("Usuário não encontrado.", "error")
        return redirect(url_for("admin.usuarios_listar"))

    conn = None
    try:
        nome = (request.form.get("nome") or "").strip()
        cpf  = (request.form.get("cpf") or "").strip()
        role = (request.form.get("role") or "").strip() or row["role"]
        is_active = 1 if (request.form.get("is_active") or str(row["is_active"])) == "1" else 0

        if not nome or not cpf or not role:
            flash("Preencha Nome, CPF e Nível.", "error")
            return redirect(url_for("admin.usuarios_listar"))

        cpf_digits = only_digits(cpf)
        if len(cpf_digits) != 11:
            flash("CPF inválido. Informe 11 dígitos.", "error")
            return redirect(url_for("admin.usuarios_listar"))

        email = (request.form.get("email") or "").strip() or None
        cns   = (request.form.get("cns") or "").strip() or None
        nasc  = (request.form.get("nascimento") or "").strip() or None
        sexo  = (request.form.get("sexo") or "").strip() or None
        conselho          = (request.form.get("conselho") or "").strip() or None
        registro_conselho = (request.form.get("registro_conselho") or "").strip() or None
        uf_conselho       = (request.form.get("uf_conselho") or "").strip() or None
        cbo               = (request.form.get("cbo") or "").strip() or None
        telefone = (request.form.get("telefone") or "").strip() or None
        cep   = (request.form.get("cep") or "").strip() or None
        logr  = (request.form.get("logradouro") or "").strip() or None
        numero= (request.form.get("numero") or "").strip() or None
        comp  = (request.form.get("complemento") or "").strip() or None
        bairro= (request.form.get("bairro") or "").strip() or None
        municipio = (request.form.get("municipio") or "").strip() or None
        uf       = (request.form.get("uf") or "").strip() or None

        permissoes = []
        for k in request.form.keys():
            if k.startswith("perm_") and request.form.get(k) == "1":
                permissoes.append(k.replace("perm_", "", 1))
        permissoes_json = json.dumps(permissoes, ensure_ascii=False)

        conn = db_conn(False)
        cur = conn.cursor()
        cur.execute("""
            UPDATE usuarios SET
                nome=?, email=?, cpf=?, cpf_digits=?, cns=?, nascimento=?, sexo=?,
                conselho=?, registro_conselho=?, uf_conselho=?, cbo=?,
                telefone=?, role=?, is_active=?,
                cep=?, logradouro=?, numero=?, complemento=?, bairro=?, municipio=?, uf=?,
                permissoes_json=?, atualizado_em=datetime('now')
            WHERE id=?;
        """, (
            nome, email, cpf, cpf_digits, cns, nasc, sexo,
            conselho, registro_conselho, uf_conselho, cbo,
            telefone, role, is_active,
            cep, logr, numero, comp, bairro, municipio, uf,
            permissoes_json, uid
        ))
        conn.commit()
        flash("Usuário atualizado com sucesso.", "success")

    except sqlite3.IntegrityError as e:
        msg = str(e)
        if "idx_usuarios_cpf_digits" in msg or "usuarios.cpf_digits" in msg:
            flash("Já existe um usuário com esse CPF.", "error")
        elif "idx_usuarios_cpf" in msg or "usuarios.cpf" in msg:
            flash("Já existe um usuário com esse CPF.", "error")
        elif "idx_usuarios_email" in msg or "usuarios.email" in msg:
            flash("Já existe um usuário com esse e-mail.", "error")
        else:
            flash("Erro de integridade ao atualizar o usuário.", "error")
    except Exception as e:
        flash(f"Erro ao atualizar usuário: {e}", "error")
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass

    return redirect(url_for("admin.usuarios_listar"))


# =============================================================================
# USUÁRIOS - MUDAR SENHA
# =============================================================================

@admin_bp.route("/usuarios/<int:uid>/senha", methods=["POST"])
@admin_required
def usuarios_mudar_senha(uid):
    row = load_user(uid)
    if not row:
        flash("Usuário não encontrado.", "error")
        return redirect(url_for("admin.usuarios_listar"))

    senha  = request.form.get("senha") or ""
    senha2 = request.form.get("senha2") or ""
    if not senha or len(senha) < 6:
        flash("Defina uma senha com pelo menos 6 caracteres.", "error")
        return redirect(url_for("admin.usuarios_listar"))
    if senha != senha2:
        flash("A confirmação da senha não confere.", "error")
        return redirect(url_for("admin.usuarios_listar"))

    conn = None
    try:
        senha_hash = generate_password_hash(senha, method="pbkdf2:sha256", salt_length=16)
        conn = db_conn(False)
        cur = conn.cursor()

        # Descobre colunas existentes (para suportar legados)
        cur.execute("PRAGMA table_info(usuarios);")
        cols = {r[1] for r in cur.fetchall()}
        has_pwd_pt = "senha_hash" in cols
        has_pwd_en = "password_hash" in cols

        if not has_pwd_pt and not has_pwd_en:
            flash("Não há coluna de senha na tabela de usuários (senha_hash/password_hash).", "error")
            return redirect(url_for("admin.usuarios_listar"))

        sets = []
        params = []

        if has_pwd_pt:
            sets.append("senha_hash=?")
            params.append(senha_hash)
        if has_pwd_en:
            sets.append("password_hash=?")
            params.append(senha_hash)

        sets.append("atualizado_em=datetime('now')")

        sql = f"UPDATE usuarios SET {', '.join(sets)} WHERE id=?;"
        params.append(uid)

        cur.execute(sql, params)
        conn.commit()

        flash("Senha atualizada com sucesso.", "success")

    except Exception as e:
        flash(f"Erro ao atualizar senha: {e}", "error")
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass

    return redirect(url_for("admin.usuarios_listar"))


# =============================================================================
# USUÁRIOS - REMOVER
# =============================================================================

@admin_bp.route("/usuarios/<int:uid>/remover", methods=["POST"])
@admin_required
def usuarios_remover(uid):
    row = load_user(uid)
    if not row:
        flash("Usuário não encontrado.", "error")
        return redirect(url_for("admin.usuarios_listar"))

    conn = None
    try:
        conn = db_conn(False)
        cur = conn.cursor()
        cur.execute("DELETE FROM usuarios WHERE id=?;", (uid,))
        conn.commit()
        flash("Usuário removido com sucesso.", "success")
    except Exception as e:
        flash(f"Erro ao remover usuário: {e}", "error")
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass

    return redirect(url_for("admin.usuarios_listar"))


# =============================================================================
# NÍVEIS - CRIAR (Preview)
# =============================================================================

@admin_bp.route("/usuarios/niveis/criar", methods=["POST"])
@admin_required
def niveis_criar():
    nome = request.form.get("nome_nivel", "").strip()
    slug = request.form.get("slug", "").strip()
    permissoes = request.form.getlist("permissoes_nivel")

    if not nome or not slug:
        flash("Informe Nome do nível e Slug.", "error")
        return redirect(url_for("admin.usuarios_listar"))

    flash(f"Nível '{nome}' ({slug}) criado (preview).", "success")
    return redirect(url_for("admin.usuarios_listar"))


# =============================================================================
# MÓDULOS - HABILITAR/DESABILITAR (FRONT)
# =============================================================================

@admin_bp.route("/modulos", methods=["GET", "POST"])
@admin_required
def modulos():
    modulos_disponiveis = [
        {"chave": "cadastro", "nome": "Cadastro"},
        {"chave": "pacientes", "nome": "Pacientes"},
        {"chave": "atendimentos", "nome": "Lista de Atendimentos"},
        {"chave": "agenda", "nome": "Agenda"},
        {"chave": "export_all", "nome": "Export (Tudo)"},
        {"chave": "export_bpai", "nome": "Export BPA-i"},
        {"chave": "export_apac", "nome": "Export APAC"},
        {"chave": "export_ciha", "nome": "Export CIHA"},
        {"chave": "financeiro", "nome": "Financeiro"},
        {"chave": "rh", "nome": "RH"},
    ]

    habilitados = {"cadastro", "pacientes", "atendimentos"}

    if request.method == "POST":
        selecionados = set(request.form.getlist("modulos"))
        flash("Preferências de módulos salvas (preview).", "success")
        habilitados = selecionados

    return render_template(
        "modulos.html",
        modulos=modulos_disponiveis,
        habilitados=habilitados,
    )



import os
import io
import json
import time
import sqlite3
import zipfile
import tempfile
from pathlib import Path
from datetime import datetime
from flask import (
    render_template, request, redirect, url_for, flash,
    current_app, send_file, abort
)
# =============================================================================
# BACKUP / RESTAURAÇÃO (COMPLETO)
# - Salva em data_base/backups
# - Mantém apenas os 5 mais recentes
# - Faz download automático do arquivo gerado
# - Permite baixar backups antigos
# - Permite excluir backup
# - Permite restaurar backup via upload .zip
# - Possui rotina para backup automático semanal (sexta-feira)
# =============================================================================

MAX_BACKUPS = 5


def _resolve_sqlite_path() -> str | None:
    """
    Descobre o caminho real do banco SQLite principal.
    """
    db_cfg = current_app.config.get("DATABASE")
    if db_cfg:
        return str(db_cfg)

    conn = None
    try:
        conn = conectar_db()
        cur = conn.cursor()
        cur.execute("PRAGMA database_list;")
        rows = cur.fetchall()
        for row in rows:
            # formato esperado: (seq, name, file)
            if len(row) >= 3 and row[1] == "main" and row[2]:
                return row[2]
    except Exception:
        return None
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass

    return None


def _backup_dir() -> Path:
    """
    Cria/retorna a pasta: data_base/backups
    com base no caminho do banco principal.
    """
    db_path = _resolve_sqlite_path()
    if db_path:
        db_dir = Path(db_path).parent
    else:
        # fallback
        db_dir = Path(current_app.root_path).parent / "data_base"

    pasta = db_dir / "backups"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _format_bytes(num: int) -> str:
    """
    Formata bytes em KB/MB/GB.
    """
    if not isinstance(num, (int, float)) or num < 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num)
    idx = 0

    while size >= 1024 and idx < len(units) - 1:
        size /= 1024.0
        idx += 1

    if idx == 0:
        return f"{int(size)} {units[idx]}"
    return f"{size:.2f} {units[idx]}"


def _listar_backups():
    pasta = _backup_dir()
    arquivos = []

    for f in sorted(pasta.glob("*.zip"), key=lambda x: x.stat().st_mtime, reverse=True):
        st = f.stat()
        arquivos.append({
            "nome": f.name,
            "caminho": str(f),
            "tamanho": st.st_size,
            "tamanho_fmt": _format_bytes(st.st_size),
            "criado_em": datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y %H:%M"),
            "timestamp": st.st_mtime,
        })

    return arquivos


def _podar_backups():
    """
    Mantém apenas os MAX_BACKUPS mais recentes.
    Remove os mais antigos.
    """
    backups = _listar_backups()
    excedentes = backups[MAX_BACKUPS:]

    for item in excedentes:
        try:
            Path(item["caminho"]).unlink(missing_ok=True)
        except Exception:
            pass


def _gerar_backup_zip(*, origem_manual: bool = True) -> tuple[Path, str]:
    """
    Gera backup consistente do SQLite, compacta em .zip, salva em data_base/backups
    e retorna (zip_path, nome_arquivo).
    """
    db_path = _resolve_sqlite_path()
    if not db_path:
        raise RuntimeError("Não foi possível localizar o banco de dados configurado.")

    db_file = Path(db_path)
    if not db_file.exists():
        raise FileNotFoundError(f"Banco de dados não encontrado: {db_file}")

    pasta = _backup_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    origem = "manual" if origem_manual else "auto"

    nome_base = f"sgd_backup_{origem}_{timestamp}"
    temp_db = pasta / f"{nome_base}.db"
    zip_path = pasta / f"{nome_base}.zip"
    meta_path = pasta / f"{nome_base}_info.txt"

    src = None
    dst = None

    try:
        # abre origem e destino
        src = sqlite3.connect(str(db_file))
        dst = sqlite3.connect(str(temp_db))

        # copia o banco para o arquivo temporário
        src.backup(dst)
        dst.commit()

        # MUITO IMPORTANTE NO WINDOWS:
        # fechar as conexões antes de compactar ou excluir o arquivo
        dst.close()
        dst = None

        src.close()
        src = None

        # cria metadados
        meta_path.write_text(
            "\n".join([
                "SGD - Backup do banco SQLite",
                f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
                f"Tipo: {'Manual' if origem_manual else 'Automático'}",
                f"Banco de origem: {db_file}",
                f"Arquivo gerado: {temp_db.name}",
            ]),
            encoding="utf-8"
        )

        # compacta
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(temp_db, arcname=temp_db.name)
            zf.write(meta_path, arcname=meta_path.name)

        # remove arquivos temporários
        if temp_db.exists():
            temp_db.unlink()
        if meta_path.exists():
            meta_path.unlink()

        # mantém só os 5 mais recentes
        _podar_backups()

        return zip_path, zip_path.name

    except Exception:
        # limpa temporários se algo falhar
        try:
            if dst:
                dst.close()
        except Exception:
            pass

        try:
            if src:
                src.close()
        except Exception:
            pass

        try:
            if temp_db.exists():
                temp_db.unlink()
        except Exception:
            pass

        try:
            if meta_path.exists():
                meta_path.unlink()
        except Exception:
            pass

        raise

def _extrair_db_de_zip(zip_file_path: Path, destino_tmp: Path) -> Path:
    """
    Extrai o primeiro .db encontrado dentro do zip.
    """
    with zipfile.ZipFile(zip_file_path, "r") as zf:
        nomes = zf.namelist()
        dbs = [n for n in nomes if n.lower().endswith(".db")]

        if not dbs:
            raise ValueError("O arquivo .zip não contém nenhum banco .db válido.")

        alvo = dbs[0]
        zf.extract(alvo, path=destino_tmp)
        return destino_tmp / alvo


def _restaurar_backup_de_arquivo(zip_path: Path) -> None:
    """
    Restaura o banco principal a partir de um .zip contendo um .db.
    Antes de restaurar, gera um backup de segurança automático.
    """
    db_path = _resolve_sqlite_path()
    if not db_path:
        raise RuntimeError("Não foi possível localizar o banco de dados principal.")

    db_file = Path(db_path)
    if not db_file.exists():
        raise FileNotFoundError(f"Banco principal não encontrado: {db_file}")

    # backup preventivo antes de restaurar
    _gerar_backup_zip(origem_manual=False)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        restored_db = _extrair_db_de_zip(zip_path, tmpdir_path)

        if not restored_db.exists():
            raise FileNotFoundError("Não foi possível localizar o .db extraído do backup.")

        src = None
        dst = None
        try:
            src = sqlite3.connect(str(restored_db))
            dst = sqlite3.connect(str(db_file))

            # sobrescreve o banco principal com o conteúdo do backup
            src.backup(dst)
            dst.commit()
        finally:
            try:
                if dst:
                    dst.close()
            except Exception:
                pass
            try:
                if src:
                    src.close()
            except Exception:
                pass


def _ja_foi_gerado_backup_automatico_hoje() -> bool:
    """
    Verifica se já existe backup automático gerado hoje.
    """
    hoje = datetime.now().strftime("%Y%m%d")
    for item in _listar_backups():
        nome = item["nome"].lower()
        if f"sgd_backup_auto_{hoje}" in nome:
            return True
    return False


def verificar_backup_automatico_sexta():
    """
    Gera backup automático na sexta-feira, apenas 1 vez por dia.
    Pode ser chamado em app.py no startup ou em um before_request leve.
    weekday(): segunda=0 ... sexta=4
    """
    try:
        agora = datetime.now()

        # só sexta
        if agora.weekday() != 4:
            return

        # não duplica no mesmo dia
        if _ja_foi_gerado_backup_automatico_hoje():
            return

        _gerar_backup_zip(origem_manual=False)

    except Exception as e:
        # só loga; não quebra sistema
        print(f"[BACKUP AUTO] Falha ao gerar backup automático: {e}")


@admin_bp.route("/backup")
@admin_required
def backup():
    backups = _listar_backups()
    ultimo_backup = backups[0]["criado_em"] if backups else None

    return render_template(
        "backup.html",
        backups=backups,
        total_backups=len(backups),
        ultimo_backup=ultimo_backup,
        max_backups=MAX_BACKUPS,
    )


@admin_bp.route("/backup/run", methods=["POST"])
@admin_required
def backup_run():
    """
    Gera backup manual, salva na pasta local e baixa externamente.
    """
    try:
        zip_path, nome = _gerar_backup_zip(origem_manual=True)

        return send_file(
            str(zip_path),
            as_attachment=True,
            download_name=nome,
            mimetype="application/zip",
            max_age=0
        )

    except Exception as e:
        flash(f"Erro ao gerar backup: {e}", "error")
        return redirect(url_for("admin.backup"))


@admin_bp.route("/backup/download/<path:nome>")
@admin_required
def backup_download(nome):
    pasta = _backup_dir()
    alvo = (pasta / nome).resolve()

    # proteção simples contra path traversal
    if pasta.resolve() not in alvo.parents and alvo != pasta.resolve():
        abort(404)

    if not alvo.exists() or alvo.suffix.lower() != ".zip":
        abort(404)

    return send_file(
        str(alvo),
        as_attachment=True,
        download_name=alvo.name,
        mimetype="application/zip",
        max_age=0
    )


@admin_bp.route("/backup/excluir/<path:nome>", methods=["POST"])
@admin_required
def backup_excluir(nome):
    pasta = _backup_dir()
    alvo = (pasta / nome).resolve()

    if pasta.resolve() not in alvo.parents and alvo != pasta.resolve():
        flash("Arquivo inválido.", "error")
        return redirect(url_for("admin.backup"))

    if not alvo.exists() or alvo.suffix.lower() != ".zip":
        flash("Arquivo de backup não encontrado.", "error")
        return redirect(url_for("admin.backup"))

    try:
        alvo.unlink()
        flash(f"Backup '{alvo.name}' removido com sucesso.", "success")
    except Exception as e:
        flash(f"Não foi possível excluir o backup: {e}", "error")

    return redirect(url_for("admin.backup"))


@admin_bp.route("/backup/restaurar", methods=["POST"])
@admin_required
def backup_restaurar():
    """
    Restaura o banco principal a partir de um .zip enviado pelo usuário.
    Espera um input file com name='arquivo_backup'.
    """
    arquivo = request.files.get("arquivo_backup")

    if not arquivo or not arquivo.filename:
        flash("Selecione um arquivo .zip de backup para restaurar.", "error")
        return redirect(url_for("admin.backup"))

    nome_original = arquivo.filename.strip()
    if not nome_original.lower().endswith(".zip"):
        flash("Envie um arquivo .zip válido.", "error")
        return redirect(url_for("admin.backup"))

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        zip_tmp = tmpdir_path / nome_original

        try:
            arquivo.save(str(zip_tmp))
            _restaurar_backup_de_arquivo(zip_tmp)
            flash("Backup restaurado com sucesso.", "success")
        except Exception as e:
            flash(f"Erro ao restaurar backup: {e}", "error")

    return redirect(url_for("admin.backup"))


@admin_bp.route("/backup/restaurar/<path:nome>", methods=["POST"])
@admin_required
def backup_restaurar_salvo(nome):
    """
    Restaura usando um backup já salvo na pasta local.
    """
    pasta = _backup_dir()
    alvo = (pasta / nome).resolve()

    if pasta.resolve() not in alvo.parents and alvo != pasta.resolve():
        flash("Arquivo inválido.", "error")
        return redirect(url_for("admin.backup"))

    if not alvo.exists() or alvo.suffix.lower() != ".zip":
        flash("Backup não encontrado.", "error")
        return redirect(url_for("admin.backup"))

    try:
        _restaurar_backup_de_arquivo(alvo)
        flash(f"Backup '{alvo.name}' restaurado com sucesso.", "success")
    except Exception as e:
        flash(f"Erro ao restaurar backup salvo: {e}", "error")

    return redirect(url_for("admin.backup"))


@admin_bp.route("/backup/run-auto", methods=["POST"])
@admin_required
def backup_run_auto():
    """
    Rota opcional para testar manualmente a rotina automática.
    """
    try:
        zip_path, nome = _gerar_backup_zip(origem_manual=False)
        flash(f"Backup automático gerado com sucesso: {nome}", "success")
    except Exception as e:
        flash(f"Erro ao gerar backup automático: {e}", "error")

    return redirect(url_for("admin.backup"))