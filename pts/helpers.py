# sgd/pts/helpers.py
from __future__ import annotations

from datetime import datetime
import re
from flask import session


# ============================================================
# BÁSICOS
# ============================================================

def _safe_str(v) -> str:
    return ("" if v is None else str(v)).strip()


def _only_digits(v: str | None) -> str:
    return re.sub(r"\D+", "", v or "")


def _valid_ident(name: str) -> bool:
    return bool(re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name or ""))


def _val(row, key: str, index: int = 0, default=None):
    if not row:
        return default

    if isinstance(row, dict):
        return row.get(key, default)

    try:
        return row[index]
    except Exception:
        return default


def _like(s: str) -> str:
    return f"%{(s or '').strip()}%"


def _safe_page(v, default=1) -> int:
    try:
        p = int(v)
        return p if p > 0 else default
    except Exception:
        return default


# ============================================================
# POSTGRES · INSPEÇÃO
# ============================================================

def has_table(conn, table_name: str) -> bool:
    if not _valid_ident(table_name):
        return False

    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                  FROM information_schema.tables
                 WHERE table_schema = 'public'
                   AND table_name = %s
            ) AS existe
            """,
            (table_name,),
        )
        return bool(_val(cur.fetchone(), "existe", 0, False))
    finally:
        cur.close()


def has_column(conn, table_name: str, column_name: str) -> bool:
    if not _valid_ident(table_name) or not _valid_ident(column_name):
        return False

    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                  FROM information_schema.columns
                 WHERE table_schema = 'public'
                   AND table_name = %s
                   AND column_name = %s
            ) AS existe
            """,
            (table_name, column_name),
        )
        return bool(_val(cur.fetchone(), "existe", 0, False))
    finally:
        cur.close()


def table_columns(conn, table: str) -> set[str]:
    if not _valid_ident(table):
        return set()

    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = %s
            """,
            (table,),
        )
        rows = cur.fetchall() or []
        return {
            _val(r, "column_name", 0)
            for r in rows
            if _val(r, "column_name", 0)
        }
    finally:
        cur.close()


def first_existing(cols: set[str], names: list[str]) -> str | None:
    for n in names:
        if n in cols:
            return n
    return None


# ============================================================
# SESSÃO · CLÍNICA · USUÁRIO
# ============================================================

def resolve_clinica_id(default: int | None = None) -> int | None:
    for key in ("clinica_id", "clinic_id", "id_clinica"):
        val = session.get(key)
        if val is not None:
            try:
                return int(val)
            except Exception:
                pass

    return default


def require_clinica_id() -> int:
    clinica_id = resolve_clinica_id()
    if not clinica_id:
        raise PermissionError("Clínica não identificada na sessão.")
    return int(clinica_id)


def resolve_logged_usuario_id(conn=None) -> int | None:
    for key in ("usuario_id", "user_id", "id"):
        val = session.get(key)
        if val is not None:
            try:
                return int(val)
            except Exception:
                pass

    if conn is None:
        return None

    login_like = (
        session.get("usuario_logado")
        or session.get("login")
        or session.get("username")
        or session.get("email")
    )

    if not login_like or not has_table(conn, "usuarios"):
        return None

    cols = table_columns(conn, "usuarios")
    search_cols = [c for c in ("login", "nome", "email") if c in cols]

    if not search_cols:
        return None

    cur = conn.cursor()
    try:
        conds = [
            f"TRIM(LOWER(COALESCE({c}::text, ''))) = TRIM(LOWER(%s))"
            for c in search_cols
        ]

        cur.execute(
            f"""
            SELECT id
              FROM usuarios
             WHERE {" OR ".join(conds)}
             LIMIT 1
            """,
            [login_like] * len(search_cols),
        )

        r = cur.fetchone()
        if r:
            return int(_val(r, "id", 0))

        return None
    finally:
        cur.close()


# ============================================================
# LOGS
# ============================================================

def registrar_log(
    conn,
    acao: str,
    modulo: str = "pts",
    referencia_id=None,
    detalhes: str | None = None,
):
    """
    Registra log se existir tabela compatível.
    Não quebra o fluxo principal se a tabela de logs ainda não estiver pronta.
    """

    try:
        if not has_table(conn, "logs"):
            return

        cols = table_columns(conn, "logs")
        usuario_id = resolve_logged_usuario_id(conn)
        clinica_id = resolve_clinica_id()

        cur = conn.cursor()

        campos = []
        valores = []
        params = []

        def add(campo, valor):
            if campo in cols:
                campos.append(campo)
                valores.append("%s")
                params.append(valor)

        add("usuario_id", usuario_id)
        add("clinica_id", clinica_id)
        add("modulo", modulo)
        add("acao", acao)
        add("referencia_id", str(referencia_id or ""))
        add("detalhes", detalhes or "")

        if "created_at" in cols:
            campos.append("created_at")
            valores.append("NOW()")
        elif "criado_em" in cols:
            campos.append("criado_em")
            valores.append("NOW()")

        if not campos:
            return

        cur.execute(
            f"""
            INSERT INTO logs ({", ".join(campos)})
            VALUES ({", ".join(valores)})
            """,
            params,
        )

    except Exception as e:
        print(f"[PTS][LOG] Falha ao registrar log: {e}")


# ============================================================
# CBO · USANDO TABELA ocupacoes
# ============================================================

def buscar_nome_ocupacao(conn, cbo: str | None) -> str:
    """
    Usa a tabela ocupacoes:
    - co_ocupacao
    - no_ocupacao

    Mantém fallback vazio se a tabela ainda não existir.
    """

    cbo_digits = _only_digits(cbo)
    if not cbo_digits:
        return ""

    if not has_table(conn, "ocupacoes"):
        return ""

    cols = table_columns(conn, "ocupacoes")
    if "co_ocupacao" not in cols or "no_ocupacao" not in cols:
        return ""

    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT COALESCE(no_ocupacao, '') AS no_ocupacao
              FROM ocupacoes
             WHERE REGEXP_REPLACE(COALESCE(co_ocupacao::text, ''), '\\D', '', 'g') = %s
             LIMIT 1
            """,
            (cbo_digits,),
        )

        r = cur.fetchone()
        return (_val(r, "no_ocupacao", 0, "") or "").strip()
    finally:
        cur.close()


def cbo_label(conn, cbo: str | None) -> str:
    cbo_digits = _only_digits(cbo)
    nome = buscar_nome_ocupacao(conn, cbo_digits)

    if cbo_digits and nome:
        return f"{nome} · CBO {cbo_digits}"

    if cbo_digits:
        return f"CBO {cbo_digits}"

    return ""


# ============================================================
# SCHEMA PTS
# ============================================================

def ensure_pts_schema(conn):
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pts (
            id SERIAL PRIMARY KEY,
            clinica_id INTEGER,
            paciente_id INTEGER NOT NULL,
            data_pts DATE NOT NULL,

            objetivo_geral TEXT,
            avaliacao TEXT,
            plano TEXT,
            observacoes TEXT,

            created_by INTEGER,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pts_participantes (
            id SERIAL PRIMARY KEY,
            clinica_id INTEGER,
            pts_id INTEGER NOT NULL REFERENCES pts(id) ON DELETE CASCADE,
            usuario_id INTEGER NOT NULL,
            nome TEXT,
            cbo TEXT,
            funcao TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("ALTER TABLE pts ADD COLUMN IF NOT EXISTS clinica_id INTEGER")
    cur.execute("ALTER TABLE pts_participantes ADD COLUMN IF NOT EXISTS clinica_id INTEGER")
    cur.execute("ALTER TABLE pts_participantes ADD COLUMN IF NOT EXISTS funcao TEXT")

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_pts_clinica
        ON pts (clinica_id)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_pts_paciente_data
        ON pts (clinica_id, paciente_id, data_pts)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_pts_part_clinica
        ON pts_participantes (clinica_id)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_pts_part_pts
        ON pts_participantes (pts_id)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_pts_part_usuario
        ON pts_participantes (usuario_id)
    """)

    conn.commit()


# ============================================================
# FETCHERS COM CLINICA_ID
# ============================================================

def fetch_paciente_full(conn, paciente_id: str | int, clinica_id: int | None = None):
    if not has_table(conn, "pacientes"):
        return None

    pid = str(paciente_id).strip()
    if not pid:
        return None

    cols = table_columns(conn, "pacientes")
    has_clinica = "clinica_id" in cols

    def expr(col: str):
        return f"COALESCE({col}::text, '') AS {col}" if col in cols else f"'' AS {col}"

    sel = [
        "id",
        expr("nome"),
        expr("nascimento"),
        expr("cpf"),
        expr("cns"),
        expr("prontuario"),
        expr("mod"),
        expr("status"),
        expr("cid"),
        expr("telefone"),
        expr("sexo"),
    ]

    where = ["id = %s"]
    params = [int(pid)]

    if has_clinica and clinica_id:
        where.append("clinica_id = %s")
        params.append(int(clinica_id))

    cur = conn.cursor()
    try:
        cur.execute(
            f"""
            SELECT {", ".join(sel)}
              FROM pacientes
             WHERE {" AND ".join(where)}
             LIMIT 1
            """,
            params,
        )

        r = cur.fetchone()
        if not r:
            return None

        return {
            "id": _val(r, "id", 0),
            "nome": _val(r, "nome", 1, "") or "",
            "nascimento": _val(r, "nascimento", 2, "") or "",
            "cpf": _val(r, "cpf", 3, "") or "",
            "cns": _val(r, "cns", 4, "") or "",
            "prontuario": _val(r, "prontuario", 5, "") or "",
            "mod": _val(r, "mod", 6, "") or "",
            "status": _val(r, "status", 7, "") or "",
            "cid": _val(r, "cid", 8, "") or "",
            "telefone": _val(r, "telefone", 9, "") or "",
            "sexo": _val(r, "sexo", 10, "") or "",
        }
    finally:
        cur.close()


def fetch_pts_by_id(conn, pts_id: int, clinica_id: int | None = None) -> dict | None:
    ensure_pts_schema(conn)

    where = ["id = %s"]
    params = [int(pts_id)]

    if clinica_id:
        where.append("clinica_id = %s")
        params.append(int(clinica_id))

    cur = conn.cursor()
    try:
        cur.execute(
            f"""
            SELECT
                id,
                clinica_id,
                paciente_id,
                COALESCE(data_pts::text, '') AS data_pts,
                COALESCE(objetivo_geral, '') AS objetivo_geral,
                COALESCE(avaliacao, '') AS avaliacao,
                COALESCE(plano, '') AS plano,
                COALESCE(observacoes, '') AS observacoes,
                created_by,
                COALESCE(created_at::text, '') AS created_at,
                COALESCE(updated_at::text, '') AS updated_at
            FROM pts
            WHERE {" AND ".join(where)}
            LIMIT 1
            """,
            params,
        )

        r = cur.fetchone()
        if not r:
            return None

        data_pts = _val(r, "data_pts", 3, "") or ""

        return {
            "id": int(_val(r, "id", 0)),
            "clinica_id": _val(r, "clinica_id", 1),
            "paciente_id": int(_val(r, "paciente_id", 2)),
            "data_pts": data_pts,
            "data": data_pts,
            "competencia": data_pts[:7],
            "status": "",
            "objetivo_geral": _val(r, "objetivo_geral", 4, "") or "",
            "avaliacao": _val(r, "avaliacao", 5, "") or "",
            "plano": _val(r, "plano", 6, "") or "",
            "observacoes": _val(r, "observacoes", 7, "") or "",
            "created_by": _val(r, "created_by", 8),
            "created_at": _val(r, "created_at", 9, "") or "",
            "updated_at": _val(r, "updated_at", 10, "") or "",
        }
    finally:
        cur.close()


def fetch_participantes(conn, pts_id: int, clinica_id: int | None = None) -> list[dict]:
    ensure_pts_schema(conn)

    where = ["pts_id = %s"]
    params = [int(pts_id)]

    if clinica_id:
        where.append("clinica_id = %s")
        params.append(int(clinica_id))

    cur = conn.cursor()
    try:
        cur.execute(
            f"""
            SELECT
                usuario_id,
                COALESCE(nome, '') AS nome,
                COALESCE(cbo, '') AS cbo,
                COALESCE(funcao, '') AS funcao
            FROM pts_participantes
            WHERE {" AND ".join(where)}
            ORDER BY nome ASC
            """,
            params,
        )

        rows = cur.fetchall() or []
        items = []

        for r in rows:
            cbo = _val(r, "cbo", 2, "") or ""
            funcao = _val(r, "funcao", 3, "") or ""
            ocupacao = buscar_nome_ocupacao(conn, cbo)

            items.append({
                "usuario_id": int(_val(r, "usuario_id", 0) or 0),
                "nome": _val(r, "nome", 1, "") or "",
                "cbo": cbo,
                "funcao": funcao or ocupacao,
                "ocupacao": ocupacao,
                "label": cbo_label(conn, cbo),
            })

        return items
    finally:
        cur.close()


# ============================================================
# PARTICIPANTES
# ============================================================

def insert_pts_participantes(
    conn,
    pts_id: int,
    ids: list[int],
    clinica_id: int,
    now=None,
):
    if not ids or not has_table(conn, "usuarios"):
        return

    now = now or datetime.now()

    cols = table_columns(conn, "usuarios")
    has_nome = "nome" in cols
    has_cbo = "cbo" in cols
    has_clinica = "clinica_id" in cols

    nome_expr = "COALESCE(nome, '')" if has_nome else "''"
    cbo_expr = "COALESCE(cbo, '')" if has_cbo else "''"

    cur = conn.cursor()

    for uid in ids:
        where = ["id = %s"]
        params = [int(uid)]

        if has_clinica:
            where.append("(clinica_id = %s OR clinica_id IS NULL)")
            params.append(int(clinica_id))

        cur.execute(
            f"""
            SELECT {nome_expr} AS nome, {cbo_expr} AS cbo
              FROM usuarios
             WHERE {" AND ".join(where)}
             LIMIT 1
            """,
            params,
        )

        ur = cur.fetchone()
        if not ur:
            continue

        nome_u = (_val(ur, "nome", 0, "") or "").strip()
        cbo_u = (_val(ur, "cbo", 1, "") or "").strip()
        funcao_u = buscar_nome_ocupacao(conn, cbo_u)

        cur.execute("""
            INSERT INTO pts_participantes (
                clinica_id,
                pts_id,
                usuario_id,
                nome,
                cbo,
                funcao,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            int(clinica_id),
            int(pts_id),
            int(uid),
            nome_u,
            cbo_u,
            funcao_u,
            now,
        ))


# ============================================================
# FILTROS DE LISTAGEM
# ============================================================

def build_pts_where_and_params(
    q_paciente: str,
    q_prof: str,
    q_cbo: str,
    competencia: str,
    clinica_id: int,
):
    where = ["t.clinica_id = %s"]
    params = [int(clinica_id)]

    if q_paciente.strip():
        where.append("p.nome ILIKE %s")
        params.append(_like(q_paciente))

    comp = competencia.strip()
    if comp:
        where.append("TO_CHAR(t.data_pts, 'YYYY-MM') = %s")
        params.append(comp)

    if q_prof.strip():
        where.append("""
            EXISTS (
                SELECT 1
                  FROM pts_participantes pp
                 WHERE pp.pts_id = t.id
                   AND pp.clinica_id = t.clinica_id
                   AND pp.nome ILIKE %s
            )
        """)
        params.append(_like(q_prof))

    if q_cbo.strip():
        where.append("""
            EXISTS (
                SELECT 1
                  FROM pts_participantes pp2
                 WHERE pp2.pts_id = t.id
                   AND pp2.clinica_id = t.clinica_id
                   AND (
                        pp2.cbo ILIKE %s
                        OR REGEXP_REPLACE(COALESCE(pp2.cbo::text, ''), '\\D', '', 'g') ILIKE %s
                   )
            )
        """)
        params.append(_like(q_cbo))
        params.append(_like(_only_digits(q_cbo)))

    return "WHERE " + " AND ".join(where), params