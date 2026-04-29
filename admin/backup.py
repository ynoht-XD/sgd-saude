from flask import current_app, flash, redirect, url_for, send_file
from datetime import datetime
import os
import shutil

from . import admin_bp

try:
    from flask_login import login_required
except:
    def login_required(f): return f

def get_db_path():
    return current_app.config.get("DATABASE")


def get_backup_dir():
    path = os.path.join(os.getcwd(), "data_base", "backups")
    os.makedirs(path, exist_ok=True)
    return path

# =========================================================
# BACKUP - CRIAR
# =========================================================
@admin_bp.route("/backup/criar")
@login_required
def backup_criar():
    db_path = current_app.config.get("DATABASE")

    if not db_path or not os.path.exists(db_path):
        flash("Banco não encontrado.", "danger")
        return redirect(url_for("admin.admin_home"))

    pasta = os.path.join(current_app.root_path, "data_base", "backups")
    os.makedirs(pasta, exist_ok=True)

    nome = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    destino = os.path.join(pasta, nome)

    shutil.copy2(db_path, destino)

    flash(f"Backup criado: {nome}", "success")
    return redirect(url_for("admin.admin_home"))

# =========================================================
# DOWNLOAD DO BACKUP MAIS RECENTE
# =========================================================
@admin_bp.route("/download")
@login_required
def download_backup():
    backup_dir = get_backup_dir()

    arquivos = sorted(
        [f for f in os.listdir(backup_dir) if f.endswith(".db")],
        reverse=True
    )

    if not arquivos:
        flash("Nenhum backup encontrado.", "error")
        return redirect(url_for("admin.admin_home"))

    caminho = os.path.join(backup_dir, arquivos[0])

    return send_file(caminho, as_attachment=True)