# db.py
import sqlite3
import os

DB_DIR = 'data_base'
DB_NAME = 'sgd_db.db'

def conectar_db(readonly=False):
    os.makedirs(DB_DIR, exist_ok=True)
    caminho = os.path.join(DB_DIR, DB_NAME)

    if readonly and not os.path.exists(caminho):
        raise FileNotFoundError(f"[DB] Banco não encontrado em: {caminho}")

    modo = 'ro' if readonly else 'rw'
    if not os.path.exists(caminho):
        modo = 'rwc'  # ← cria se não existir (somente se readonly=False)

    uri = f"file:{os.path.abspath(caminho)}?mode={modo}"

    conn = sqlite3.connect(uri, uri=True, timeout=20, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.execute("PRAGMA foreign_keys = ON;")  # segurança extra
    print(f"📡 Conectado ao banco SQLite: {caminho}")
    return conn
