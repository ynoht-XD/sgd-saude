# atendimentos/chama_na_tela.py
from flask import Blueprint, render_template, request, jsonify

try:
    from db import conectar_db
except ImportError:
    conectar_db = None


chama_tela_bp = Blueprint(
    "chama_tela",
    __name__,
    template_folder="templates",
    static_folder="static",
    url_prefix="/atendimentos/chama-na-tela"
)


def get_conn():
    if conectar_db:
        return conectar_db()
    raise RuntimeError("Função conectar_db() não encontrada.")


def is_postgres_conn(conn):
    return conn.__class__.__module__.startswith("psycopg2")


def placeholder(conn):
    return "%s" if is_postgres_conn(conn) else "?"


def row_get(row, key, index=None, default=None):
    if row is None:
        return default

    if isinstance(row, dict):
        return row.get(key, default)

    if hasattr(row, "keys"):
        try:
            return row[key]
        except Exception:
            pass

    if index is not None:
        try:
            return row[index]
        except Exception:
            return default

    return default


def ensure_chamada_table():
    conn = get_conn()
    pg = is_postgres_conn(conn)
    cur = conn.cursor()

    if pg:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chamadas_pacientes (
                id SERIAL PRIMARY KEY,
                paciente_id INTEGER,
                paciente_nome TEXT NOT NULL,
                profissional_id INTEGER,
                profissional_nome TEXT,
                cbo TEXT,
                setor TEXT,
                status TEXT DEFAULT 'pendente',
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                exibido_em TIMESTAMP
            );
        """)

        cur.execute("ALTER TABLE chamadas_pacientes ADD COLUMN IF NOT EXISTS profissional_id INTEGER;")
        cur.execute("ALTER TABLE chamadas_pacientes ADD COLUMN IF NOT EXISTS cbo TEXT;")
        cur.execute("ALTER TABLE chamadas_pacientes ADD COLUMN IF NOT EXISTS exibido_em TIMESTAMP;")

    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chamadas_pacientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paciente_id INTEGER,
                paciente_nome TEXT NOT NULL,
                profissional_id INTEGER,
                profissional_nome TEXT,
                cbo TEXT,
                setor TEXT,
                status TEXT DEFAULT 'pendente',
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                exibido_em TIMESTAMP
            );
        """)

        cur.execute("PRAGMA table_info(chamadas_pacientes)")
        cols = [r[1] for r in cur.fetchall()]

        if "profissional_id" not in cols:
            cur.execute("ALTER TABLE chamadas_pacientes ADD COLUMN profissional_id INTEGER;")
        if "cbo" not in cols:
            cur.execute("ALTER TABLE chamadas_pacientes ADD COLUMN cbo TEXT;")
        if "exibido_em" not in cols:
            cur.execute("ALTER TABLE chamadas_pacientes ADD COLUMN exibido_em TIMESTAMP;")

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_chamadas_pacientes_id
        ON chamadas_pacientes (id);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_chamadas_pacientes_status
        ON chamadas_pacientes (status);
    """)

    conn.commit()
    cur.close()
    conn.close()


def buscar_cbo_profissional(conn, profissional_id=None, profissional_nome=None):
    cur = conn.cursor()
    ph = placeholder(conn)

    if profissional_id:
        for tabela in ("usuarios", "profissionais"):
            try:
                cur.execute(
                    f"""
                    SELECT COALESCE(cbo, '') AS cbo
                    FROM {tabela}
                    WHERE id = {ph}
                    LIMIT 1
                    """,
                    (profissional_id,)
                )
                row = cur.fetchone()
                cbo = row_get(row, "cbo", 0, "")
                if cbo:
                    return str(cbo).strip()
            except Exception:
                pass

    if profissional_nome:
        for tabela in ("usuarios", "profissionais"):
            try:
                cur.execute(
                    f"""
                    SELECT COALESCE(cbo, '') AS cbo
                    FROM {tabela}
                    WHERE nome ILIKE {ph}
                    LIMIT 1
                    """ if is_postgres_conn(conn) else f"""
                    SELECT COALESCE(cbo, '') AS cbo
                    FROM {tabela}
                    WHERE LOWER(nome) LIKE LOWER({ph})
                    LIMIT 1
                    """,
                    (profissional_nome,)
                )
                row = cur.fetchone()
                cbo = row_get(row, "cbo", 0, "")
                if cbo:
                    return str(cbo).strip()
            except Exception:
                pass

    return ""


def chamada_to_dict(row):
    return {
        "id": row_get(row, "id", 0),
        "paciente_id": row_get(row, "paciente_id", 1),
        "paciente_nome": row_get(row, "paciente_nome", 2, ""),
        "profissional_id": row_get(row, "profissional_id", 3),
        "profissional_nome": row_get(row, "profissional_nome", 4, ""),
        "cbo": row_get(row, "cbo", 5, ""),
        "setor": row_get(row, "setor", 6, ""),
        "status": row_get(row, "status", 7, ""),
        "criado_em": str(row_get(row, "criado_em", 8, "")),
        "exibido_em": str(row_get(row, "exibido_em", 9, "") or ""),
    }


@chama_tela_bp.before_app_request
def preparar_chamada():
    ensure_chamada_table()


@chama_tela_bp.route("/tv")
def tv_recepcao():
    return render_template("chama_na_tela_tv.html")


@chama_tela_bp.route("/chamar", methods=["POST"])
def chamar_paciente():
    data = request.get_json(silent=True) or request.form

    paciente_id = data.get("paciente_id") or data.get("id")
    paciente_nome = (data.get("paciente_nome") or data.get("nome") or "").strip()

    profissional_id = data.get("profissional_id") or data.get("prof_id")
    profissional_nome = (data.get("profissional_nome") or data.get("profissional") or "").strip()

    cbo = (
        data.get("cbo")
        or data.get("profissional_cbo")
        or data.get("modalidade")
        or ""
    )
    cbo = str(cbo).strip()

    setor = (data.get("setor") or data.get("local") or "").strip()

    if not paciente_nome:
        return jsonify(ok=False, erro="Nome do paciente não informado."), 400

    conn = get_conn()
    ph = placeholder(conn)

    if not cbo:
        cbo = buscar_cbo_profissional(
            conn,
            profissional_id=profissional_id,
            profissional_nome=profissional_nome
        )

    cur = conn.cursor()
    cur.execute(
        f"""
        INSERT INTO chamadas_pacientes (
            paciente_id,
            paciente_nome,
            profissional_id,
            profissional_nome,
            cbo,
            setor,
            status,
            criado_em
        )
        VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, CURRENT_TIMESTAMP)
        """,
        (
            paciente_id,
            paciente_nome,
            profissional_id,
            profissional_nome,
            cbo,
            setor,
            "pendente",
        )
    )

    conn.commit()
    cur.close()
    conn.close()

    return jsonify(
        ok=True,
        mensagem=f"{paciente_nome} entrou na fila de chamada.",
        paciente_nome=paciente_nome,
        profissional_nome=profissional_nome,
        cbo=cbo,
    )


@chama_tela_bp.route("/api/ultima")
def api_ultima_chamada():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            paciente_id,
            paciente_nome,
            profissional_id,
            profissional_nome,
            cbo,
            setor,
            status,
            criado_em,
            exibido_em
        FROM chamadas_pacientes
        ORDER BY id DESC
        LIMIT 1
    """)

    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return jsonify(ok=True, chamada=None)

    return jsonify(ok=True, chamada=chamada_to_dict(row))


@chama_tela_bp.route("/api/recentes")
def api_chamadas_recentes():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            paciente_id,
            paciente_nome,
            profissional_id,
            profissional_nome,
            cbo,
            setor,
            status,
            criado_em,
            exibido_em
        FROM chamadas_pacientes
        ORDER BY id DESC
        LIMIT 4
    """)

    rows = cur.fetchall() or []
    cur.close()
    conn.close()

    return jsonify(
        ok=True,
        chamadas=[chamada_to_dict(r) for r in rows]
    )


@chama_tela_bp.route("/api/fila")
def api_fila_chamadas():
    """
    Busca chamadas novas depois do último ID que a TV já processou.
    Isso evita perder chamada quando dois profissionais clicam quase juntos.
    Exemplo:
      /chama-na-tela/api/fila?after_id=10
    """
    after_id_raw = request.args.get("after_id") or "0"

    try:
        after_id = int(after_id_raw)
    except ValueError:
        after_id = 0

    conn = get_conn()
    ph = placeholder(conn)
    cur = conn.cursor()

    cur.execute(
        f"""
        SELECT
            id,
            paciente_id,
            paciente_nome,
            profissional_id,
            profissional_nome,
            cbo,
            setor,
            status,
            criado_em,
            exibido_em
        FROM chamadas_pacientes
        WHERE id > {ph}
        ORDER BY id ASC
        LIMIT 10
        """,
        (after_id,)
    )

    rows = cur.fetchall() or []
    cur.close()
    conn.close()

    return jsonify(
        ok=True,
        chamadas=[chamada_to_dict(r) for r in rows]
    )


@chama_tela_bp.route("/api/marcar-exibida/<int:chamada_id>", methods=["POST"])
def api_marcar_chamada_exibida(chamada_id):
    conn = get_conn()
    ph = placeholder(conn)
    cur = conn.cursor()

    cur.execute(
        f"""
        UPDATE chamadas_pacientes
           SET status = {ph},
               exibido_em = CURRENT_TIMESTAMP
         WHERE id = {ph}
        """,
        ("exibida", chamada_id)
    )

    conn.commit()
    cur.close()
    conn.close()

    return jsonify(ok=True)

@chama_tela_bp.route("/api/fila")
def fila_chamadas():
    after_id = request.args.get("after_id", "0")

    try:
        after_id = int(after_id)
    except ValueError:
        after_id = 0

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            paciente_id,
            paciente_nome,
            profissional_nome,
            cbo,
            setor,
            status,
            criado_em
        FROM chamadas_pacientes
        WHERE id > ?
        ORDER BY id ASC
        LIMIT 10
    """, (after_id,))

    rows = cur.fetchall() or []
    cur.close()
    conn.close()

    chamadas = []
    for r in rows:
        chamadas.append({
            "id": r[0],
            "paciente_id": r[1],
            "paciente_nome": r[2],
            "profissional_nome": r[3],
            "cbo": r[4],
            "setor": r[5],
            "status": r[6],
            "criado_em": str(r[7]),
        })

    return jsonify(ok=True, chamadas=chamadas)