# db.py
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

# ============================================================
# RESOLUÇÃO DO CAMINHO DO BANCO
# ============================================================

def get_db_path() -> str:
    """
    Ordem de prioridade:
    1) ENV SQLITE_PATH  (Render, Docker, produção)
    2) data_base/sgd_db.db (local)
    """
    env_path = os.environ.get("SQLITE_PATH")
    if env_path:
        return env_path

    base_dir = Path(__file__).resolve().parent
    data_dir = base_dir / "data_base"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "sgd_db.db")


# ============================================================
# CONEXÃO PADRÃO
# ============================================================

def conectar_db() -> sqlite3.Connection:
    """
    Conexão SQLite padronizada para TODO o sistema.
    """
    path = get_db_path()

    # garante diretório se não for /tmp
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    conn = sqlite3.connect(
        path,
        check_same_thread=False,
        timeout=5.0,                 # ✅ ajuda quando o banco está ocupado
        detect_types=sqlite3.PARSE_DECLTYPES,  # opcional (não atrapalha)
    )

    conn.row_factory = sqlite3.Row

    # PRAGMAs importantes
    conn.execute("PRAGMA foreign_keys = ON;")

    # WAL melhora concorrência; se falhar, não derruba o app
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
    except Exception:
        pass

    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA temp_store = MEMORY;")  # opcional: performance

    return conn
