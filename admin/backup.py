# admin/backup.py
from flask import (
    current_app, flash, redirect, url_for,
    send_file, render_template, session, request
)
from datetime import datetime
from functools import wraps
from urllib.parse import urlparse
from werkzeug.utils import secure_filename
import os
import re
import csv
import json
import zipfile
import subprocess
import tempfile
import shutil

import psycopg2

from . import admin_bp

try:
    from db import conectar_db, get_database_url as db_get_database_url
except Exception:
    conectar_db = None
    db_get_database_url = None


BACKUP_KEEP_PER_CLINICA = 5
BACKUP_KEEP_GERAL = 8
SCHEMA = "public"
EXTENSOES_BACKUP = (".backup", ".sql", ".zip")


# =========================================================
# AUTH
# =========================================================

def login_required_local(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("usuario_id") and not session.get("user_id"):
            flash("Faça login para acessar esta área.", "danger")
            return redirect(url_for("auth.login") if "auth.login" in current_app.view_functions else "/login")
        return f(*args, **kwargs)
    return wrapper


def get_usuario_logado():
    return session.get("usuario_nome") or session.get("nome") or session.get("user_nome") or "Sistema"


def get_user_id():
    return session.get("usuario_id") or session.get("user_id")


def get_clinica_id_atual():
    return session.get("clinica_id") or session.get("clinica_atual_id") or session.get("usuario_clinica_id")


def is_master():
    role = str(session.get("role") or session.get("perfil") or "").upper()
    return bool(session.get("is_master") or session.get("is_superuser") or role in {"MASTER", "ROOT", "SUPERADMIN"})


# =========================================================
# PATHS
# =========================================================

def get_backup_dir():
    path = os.path.join(os.getcwd(), "data_base", "backups")
    os.makedirs(path, exist_ok=True)
    return path


def agora_stamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def semana_stamp():
    return datetime.now().strftime("%Y-W%U")


# =========================================================
# POSTGRES
# =========================================================

def get_database_url():
    if db_get_database_url:
        url = db_get_database_url()
        if url:
            return url.replace("postgres://", "postgresql://", 1)

    url = (
        current_app.config.get("DATABASE_URL")
        or current_app.config.get("SQLALCHEMY_DATABASE_URI")
        or os.getenv("DATABASE_URL")
        or os.getenv("SQLALCHEMY_DATABASE_URI")
    )

    return url.replace("postgres://", "postgresql://", 1) if url else None


def get_pg_conn():
    if conectar_db:
        return conectar_db()

    url = get_database_url()
    if not url:
        raise RuntimeError("PostgreSQL não configurado via db.py nem DATABASE_URL.")

    return psycopg2.connect(url)


def parsed_pg_url():
    url = get_database_url()
    if not url:
        raise RuntimeError("Não foi possível obter a URL do PostgreSQL pelo db.py.")
    return urlparse(url)


def get_pg_dump_path():
    encontrado = shutil.which("pg_dump")
    if encontrado:
        return encontrado

    for caminho in [
        r"C:\Program Files\PostgreSQL\17\bin\pg_dump.exe",
        r"C:\Program Files\PostgreSQL\16\bin\pg_dump.exe",
        r"C:\Program Files\PostgreSQL\15\bin\pg_dump.exe",
        r"C:\Program Files\PostgreSQL\14\bin\pg_dump.exe",
        r"C:\Program Files\PostgreSQL\13\bin\pg_dump.exe",
        "/usr/bin/pg_dump",
        "/usr/local/bin/pg_dump",
    ]:
        if os.path.exists(caminho):
            return caminho

    raise RuntimeError("pg_dump não encontrado no sistema.")


def get_pg_restore_path():
    encontrado = shutil.which("pg_restore")
    if encontrado:
        return encontrado

    for caminho in [
        r"C:\Program Files\PostgreSQL\17\bin\pg_restore.exe",
        r"C:\Program Files\PostgreSQL\16\bin\pg_restore.exe",
        r"C:\Program Files\PostgreSQL\15\bin\pg_restore.exe",
        r"C:\Program Files\PostgreSQL\14\bin\pg_restore.exe",
        r"C:\Program Files\PostgreSQL\13\bin\pg_restore.exe",
        "/usr/bin/pg_restore",
        "/usr/local/bin/pg_restore",
    ]:
        if os.path.exists(caminho):
            return caminho

    raise RuntimeError("pg_restore não encontrado no sistema.")


def dict_cursor(conn):
    cur = conn.cursor()

    class DictCursorWrapper:
        def __init__(self, cursor):
            self.cursor = cursor

        def execute(self, *args, **kwargs):
            return self.cursor.execute(*args, **kwargs)

        def _to_dict(self, row):
            if row is None:
                return None
            if isinstance(row, dict):
                return row
            if hasattr(row, "keys"):
                return dict(row)
            cols = [d[0] for d in self.cursor.description]
            return dict(zip(cols, row))

        def fetchone(self):
            return self._to_dict(self.cursor.fetchone())

        def fetchall(self):
            return [self._to_dict(r) for r in self.cursor.fetchall()]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            try:
                self.cursor.close()
            except Exception:
                pass

    return DictCursorWrapper(cur)


# =========================================================
# LOGS
# =========================================================

def garantir_tabela_backup_logs():
    try:
        with get_pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS backup_logs (
                        id SERIAL PRIMARY KEY,
                        tipo VARCHAR(30),
                        acao VARCHAR(80),
                        arquivo TEXT,
                        clinica_id INTEGER,
                        usuario_id INTEGER,
                        usuario_nome TEXT,
                        ip TEXT,
                        detalhes TEXT,
                        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                conn.commit()
    except Exception as e:
        current_app.logger.warning("Não foi possível garantir backup_logs: %s", e)


def registrar_log_backup(acao, detalhes, tipo=None, arquivo=None, clinica_id=None):
    try:
        garantir_tabela_backup_logs()

        with get_pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO backup_logs (
                        tipo, acao, arquivo, clinica_id,
                        usuario_id, usuario_nome, ip, detalhes
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    tipo,
                    acao,
                    arquivo,
                    clinica_id,
                    get_user_id(),
                    get_usuario_logado(),
                    request.remote_addr if request else None,
                    detalhes,
                ))
                conn.commit()

    except Exception as e:
        current_app.logger.info("[BACKUP-LOG-FALLBACK] %s | erro=%s", acao, e)


# =========================================================
# INSPEÇÃO
# =========================================================

def listar_tabelas_publicas():
    with get_pg_conn() as conn:
        with dict_cursor(conn) as cur:
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name;
            """, (SCHEMA,))
            return [r["table_name"] for r in cur.fetchall()]


def listar_colunas_tabela(tabela):
    with get_pg_conn() as conn:
        with dict_cursor(conn) as cur:
            cur.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = %s
                  AND table_name = %s
                ORDER BY ordinal_position;
            """, (SCHEMA, tabela))
            return cur.fetchall()


def tabela_tem_coluna(tabela, coluna):
    with get_pg_conn() as conn:
        with dict_cursor(conn) as cur:
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = %s
                      AND table_name = %s
                      AND column_name = %s
                ) AS existe;
            """, (SCHEMA, tabela, coluna))
            row = cur.fetchone()
            return bool(row and row.get("existe"))


# =========================================================
# RETENÇÃO
# =========================================================

def aplicar_retencao(prefixo, manter):
    pasta = get_backup_dir()

    arquivos = [
        f for f in os.listdir(pasta)
        if f.startswith(prefixo) and f.endswith(EXTENSOES_BACKUP)
    ]

    arquivos.sort(
        key=lambda f: os.path.getmtime(os.path.join(pasta, f)),
        reverse=True
    )

    for antigo in arquivos[manter:]:
        try:
            os.remove(os.path.join(pasta, antigo))
        except Exception as e:
            current_app.logger.warning("Erro ao apagar backup antigo %s: %s", antigo, e)


# =========================================================
# BACKUP GERAL
# =========================================================

def criar_backup_geral_postgres(prefixo="backup_geral"):
    parsed = parsed_pg_url()

    pasta = get_backup_dir()
    nome = f"{prefixo}_{semana_stamp()}_{agora_stamp()}.backup"
    destino = os.path.join(pasta, nome)

    env = os.environ.copy()
    env["PGPASSWORD"] = parsed.password or ""

    comando = [
        get_pg_dump_path(),
        "-h", parsed.hostname or "localhost",
        "-p", str(parsed.port or 5432),
        "-U", parsed.username or "postgres",
        "-d", parsed.path.lstrip("/"),
        "-F", "c",
        "-f", destino,
        "--no-owner",
        "--no-privileges",
    ]

    resultado = subprocess.run(comando, env=env, capture_output=True, text=True)

    if resultado.returncode != 0:
        raise RuntimeError((resultado.stderr or "").strip() or "Erro ao executar pg_dump.")

    if prefixo == "backup_geral":
        aplicar_retencao("backup_geral_", BACKUP_KEEP_GERAL)

    registrar_log_backup(
        acao="backup_geral" if prefixo == "backup_geral" else "backup_pre_restore",
        tipo="geral",
        arquivo=nome,
        clinica_id=None,
        detalhes=f"Backup PostgreSQL criado: {nome}",
    )

    return destino, nome


# =========================================================
# BACKUP POR CLÍNICA
# =========================================================

def gerar_schema_sql_para_zip(destino_schema):
    parsed = parsed_pg_url()
    env = os.environ.copy()
    env["PGPASSWORD"] = parsed.password or ""

    comando = [
        get_pg_dump_path(),
        "-h", parsed.hostname or "localhost",
        "-p", str(parsed.port or 5432),
        "-U", parsed.username or "postgres",
        "-d", parsed.path.lstrip("/"),
        "--schema-only",
        "--no-owner",
        "--no-privileges",
        "-f", destino_schema,
    ]

    resultado = subprocess.run(comando, env=env, capture_output=True, text=True)

    if resultado.returncode != 0:
        raise RuntimeError((resultado.stderr or "").strip() or "Erro ao gerar schema do backup.")


def exportar_tabela_csv(cur, tabela, destino_csv, clinica_id):
    colunas = listar_colunas_tabela(tabela)
    nomes_colunas = [c["column_name"] for c in colunas]

    if not nomes_colunas:
        return 0

    possui_clinica_id = "clinica_id" in nomes_colunas

    sql = f'SELECT * FROM "{SCHEMA}"."{tabela}"'
    params = []

    if possui_clinica_id:
        sql += " WHERE clinica_id = %s"
        params.append(clinica_id)

    sql += " ORDER BY 1"

    cur.execute(sql, params)
    rows = cur.fetchall()

    with open(destino_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(nomes_colunas)

        for row in rows:
            linha = []

            for col in nomes_colunas:
                valor = row.get(col)

                if isinstance(valor, memoryview):
                    valor = valor.tobytes().hex()
                elif isinstance(valor, bytes):
                    valor = valor.hex()
                elif hasattr(valor, "isoformat"):
                    valor = valor.isoformat()
                elif isinstance(valor, (dict, list)):
                    valor = json.dumps(valor, ensure_ascii=False)

                linha.append(valor)

            writer.writerow(linha)

    return len(rows)


def criar_backup_clinica_postgres(clinica_id):
    pasta = get_backup_dir()
    nome = f"backup_clinica_{clinica_id}_{agora_stamp()}.zip"
    destino_zip = os.path.join(pasta, nome)

    tabelas = listar_tabelas_publicas()

    with tempfile.TemporaryDirectory() as temp_dir:
        data_dir = os.path.join(temp_dir, "dados")
        os.makedirs(data_dir, exist_ok=True)

        schema_path = os.path.join(temp_dir, "schema.sql")
        gerar_schema_sql_para_zip(schema_path)

        manifest = {
            "tipo": "clinica",
            "clinica_id": clinica_id,
            "gerado_em": datetime.now().isoformat(),
            "usuario_id": get_user_id(),
            "usuario_nome": get_usuario_logado(),
            "schema": SCHEMA,
            "tabelas": [],
            "observacao": "Tabelas com clinica_id foram filtradas; tabelas sem clinica_id são globais."
        }

        with get_pg_conn() as conn:
            with dict_cursor(conn) as cur:
                for tabela in tabelas:
                    possui_clinica = tabela_tem_coluna(tabela, "clinica_id")
                    csv_path = os.path.join(data_dir, f"{tabela}.csv")
                    total = exportar_tabela_csv(cur, tabela, csv_path, clinica_id)

                    manifest["tabelas"].append({
                        "tabela": tabela,
                        "arquivo": f"dados/{tabela}.csv",
                        "possui_clinica_id": possui_clinica,
                        "linhas": total,
                        "filtro": f"clinica_id = {clinica_id}" if possui_clinica else "global",
                    })

        manifest_path = os.path.join(temp_dir, "manifest.json")

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        with zipfile.ZipFile(destino_zip, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(schema_path, "schema.sql")
            z.write(manifest_path, "manifest.json")

            for arquivo in os.listdir(data_dir):
                z.write(os.path.join(data_dir, arquivo), f"dados/{arquivo}")

    aplicar_retencao(f"backup_clinica_{clinica_id}_", BACKUP_KEEP_PER_CLINICA)

    registrar_log_backup(
        acao="backup_clinica",
        tipo="clinica",
        arquivo=nome,
        clinica_id=clinica_id,
        detalhes=f"Backup da clínica {clinica_id} criado: {nome}",
    )

    return destino_zip, nome


# =========================================================
# RESTORE GERAL
# =========================================================

def restaurar_backup_geral_postgres(caminho_backup):
    if not os.path.exists(caminho_backup):
        raise RuntimeError("Arquivo de backup não encontrado.")

    if not caminho_backup.endswith(".backup"):
        raise RuntimeError("Restore geral aceita apenas arquivos .backup.")

    parsed = parsed_pg_url()
    env = os.environ.copy()
    env["PGPASSWORD"] = parsed.password or ""

    criar_backup_geral_postgres(prefixo="backup_pre_restore")

    comando = [
        get_pg_restore_path(),
        "-h", parsed.hostname or "localhost",
        "-p", str(parsed.port or 5432),
        "-U", parsed.username or "postgres",
        "-d", parsed.path.lstrip("/"),
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        caminho_backup,
    ]

    resultado = subprocess.run(comando, env=env, capture_output=True, text=True)
    stderr = (resultado.stderr or "").strip()

    ignoravel = (
        'unrecognized configuration parameter "transaction_timeout"' in stderr
        or "SET transaction_timeout = 0" in stderr
    ) and "warning: errors ignored on restore" in stderr

    if resultado.returncode != 0 and not ignoravel:
        raise RuntimeError(stderr or "Erro ao executar pg_restore.")

    if ignoravel:
        current_app.logger.warning("[RESTORE] Restore concluído com aviso ignorado: %s", stderr)

    registrar_log_backup(
        acao="restore_geral",
        tipo="geral",
        arquivo=os.path.basename(caminho_backup),
        clinica_id=None,
        detalhes=f"Restore geral executado usando: {os.path.basename(caminho_backup)}",
    )


# =========================================================
# ROTAS
# =========================================================

@admin_bp.route("/backup")
@login_required_local
def backup_home():
    pasta = get_backup_dir()
    clinica_id = get_clinica_id_atual()
    master = is_master()

    arquivos = []

    for f in os.listdir(pasta):
        if not f.endswith(EXTENSOES_BACKUP):
            continue

        caminho = os.path.join(pasta, f)

        if f.startswith("backup_pre_restore_"):
            tipo = "preventivo"
        elif f.startswith("backup_geral_"):
            tipo = "geral"
        elif f.startswith("backup_importado_") and f.endswith(".backup"):
            tipo = "geral"
        else:
            tipo = "clinica"

        cid = None
        m = re.search(r"backup_clinica_(\d+)_", f)
        if m:
            cid = m.group(1)

        if not master:
            if tipo in {"geral", "preventivo"}:
                continue
            if str(cid) != str(clinica_id):
                continue

        arquivos.append({
            "nome": f,
            "tipo": tipo,
            "clinica_id": cid,
            "tamanho": round(os.path.getsize(caminho) / 1024 / 1024, 2),
            "data_ts": os.path.getmtime(caminho),
            "data": datetime.fromtimestamp(os.path.getmtime(caminho)).strftime("%d/%m/%Y %H:%M"),
        })

    arquivos.sort(key=lambda x: x["data_ts"], reverse=True)

    return render_template(
        "admin/backup.html",
        arquivos=arquivos,
        master=master,
        keep_clinica=BACKUP_KEEP_PER_CLINICA,
    )


@admin_bp.route("/backup/criar")
@login_required_local
def backup_criar():
    if not is_master():
        flash("Apenas o usuário master pode gerar backup geral.", "danger")
        return redirect(url_for("admin.backup_home"))

    try:
        _, nome = criar_backup_geral_postgres()
        flash(f"Backup geral criado: {nome}", "success")
    except Exception as e:
        current_app.logger.exception(e)
        flash(f"Erro ao criar backup geral: {e}", "danger")

    return redirect(url_for("admin.backup_home"))


@admin_bp.route("/backup/criar-clinica")
@login_required_local
def backup_criar_clinica_atual():
    clinica_id = get_clinica_id_atual()

    if not clinica_id:
        flash("Clínica não identificada na sessão.", "danger")
        return redirect(url_for("admin.backup_home"))

    return backup_criar_clinica(int(clinica_id))


@admin_bp.route("/backup/criar-clinica/<int:clinica_id>")
@login_required_local
def backup_criar_clinica(clinica_id):
    if not is_master() and str(clinica_id) != str(get_clinica_id_atual()):
        flash("Você não tem permissão para gerar backup desta clínica.", "danger")
        return redirect(url_for("admin.backup_home"))

    try:
        _, nome = criar_backup_clinica_postgres(clinica_id)
        flash(f"Backup da clínica criado: {nome}", "success")
    except Exception as e:
        current_app.logger.exception(e)
        flash(f"Erro ao criar backup da clínica: {e}", "danger")

    return redirect(url_for("admin.backup_home"))


@admin_bp.route("/backup/download/<path:nome>")
@login_required_local
def backup_download_arquivo(nome):
    nome = os.path.basename(nome)
    caminho = os.path.join(get_backup_dir(), nome)

    if not os.path.exists(caminho):
        flash("Backup não encontrado.", "danger")
        return redirect(url_for("admin.backup_home"))

    if not is_master() and not nome.startswith(f"backup_clinica_{get_clinica_id_atual()}_"):
        flash("Você não tem permissão para baixar este backup.", "danger")
        return redirect(url_for("admin.backup_home"))

    registrar_log_backup(
        acao="download_backup",
        tipo="download",
        arquivo=nome,
        clinica_id=get_clinica_id_atual(),
        detalhes=f"Download do backup: {nome}",
    )

    return send_file(caminho, as_attachment=True, download_name=nome)


@admin_bp.route("/backup/restaurar/<path:nome>", methods=["POST"])
@login_required_local
def backup_restaurar_salvo(nome):
    if not is_master():
        flash("Apenas o usuário master pode restaurar backup geral.", "danger")
        return redirect(url_for("admin.backup_home"))

    nome = os.path.basename(nome)
    caminho = os.path.join(get_backup_dir(), nome)

    try:
        restaurar_backup_geral_postgres(caminho)
        flash(f"Backup restaurado com sucesso: {nome}", "success")
    except Exception as e:
        current_app.logger.exception(e)
        flash(f"Erro ao restaurar backup: {e}", "danger")

    return redirect(url_for("admin.backup_home"))


@admin_bp.route("/backup/excluir/<path:nome>", methods=["POST"])
@login_required_local
def backup_excluir(nome):
    nome = os.path.basename(nome)
    caminho = os.path.join(get_backup_dir(), nome)

    if not os.path.exists(caminho):
        flash("Backup não encontrado.", "danger")
        return redirect(url_for("admin.backup_home"))

    if nome.startswith("backup_geral_") or nome.startswith("backup_pre_restore_"):
        if not is_master():
            flash("Apenas o master pode excluir backups gerais.", "danger")
            return redirect(url_for("admin.backup_home"))
    else:
        clinica_id = get_clinica_id_atual()
        if not is_master() and not nome.startswith(f"backup_clinica_{clinica_id}_"):
            flash("Você não tem permissão para excluir este backup.", "danger")
            return redirect(url_for("admin.backup_home"))

    try:
        os.remove(caminho)

        registrar_log_backup(
            acao="excluir_backup",
            tipo="exclusao",
            arquivo=nome,
            clinica_id=get_clinica_id_atual(),
            detalhes=f"Backup excluído: {nome}",
        )

        flash(f"Backup excluído: {nome}", "success")

    except Exception as e:
        current_app.logger.exception(e)
        flash(f"Erro ao excluir backup: {e}", "danger")

    return redirect(url_for("admin.backup_home"))


@admin_bp.route("/backup/importar", methods=["POST"])
@login_required_local
def backup_importar():
    if not is_master():
        flash("Apenas o master pode importar backups gerais.", "danger")
        return redirect(url_for("admin.backup_home"))

    arquivo = request.files.get("arquivo_backup")

    if not arquivo or not arquivo.filename:
        flash("Selecione um arquivo de backup.", "danger")
        return redirect(url_for("admin.backup_home"))

    filename = secure_filename(arquivo.filename)

    if not filename.endswith(".backup"):
        flash("Por segurança, a importação aceita apenas arquivos .backup gerais.", "danger")
        return redirect(url_for("admin.backup_home"))

    nome_final = f"backup_importado_{agora_stamp()}_{filename}"
    caminho = os.path.join(get_backup_dir(), nome_final)

    try:
        arquivo.save(caminho)

        registrar_log_backup(
            acao="importar_backup",
            tipo="importacao",
            arquivo=nome_final,
            clinica_id=None,
            detalhes=f"Backup importado para biblioteca: {nome_final}",
        )

        flash(f"Backup importado com sucesso: {nome_final}", "success")

    except Exception as e:
        current_app.logger.exception(e)
        flash(f"Erro ao importar backup: {e}", "danger")

    return redirect(url_for("admin.backup_home"))


@admin_bp.route("/download")
@login_required_local
def download_backup():
    prefixo = "backup_geral_" if is_master() else f"backup_clinica_{get_clinica_id_atual()}_"

    arquivos = [
        f for f in os.listdir(get_backup_dir())
        if f.startswith(prefixo) and f.endswith(EXTENSOES_BACKUP)
    ]

    arquivos.sort(
        key=lambda f: os.path.getmtime(os.path.join(get_backup_dir(), f)),
        reverse=True
    )

    if not arquivos:
        flash("Nenhum backup encontrado.", "danger")
        return redirect(url_for("admin.backup_home"))

    return backup_download_arquivo(arquivos[0])