from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from flask import session


# ============================================================
# UTILITÁRIOS GERAIS
# ============================================================

def digits(s: str | None) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())


def _to_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _row_get(row: Any, key: str, idx: int | None = None, default: Any = None) -> Any:
    """
    Compatível com:
    - psycopg2 normal: tuple/list
    - psycopg2.extras.RealDictCursor: dict
    """
    if row is None:
        return default

    if isinstance(row, dict):
        return row.get(key, default)

    if idx is not None:
        try:
            return row[idx]
        except Exception:
            return default

    return default


def _valid_ident(name: str) -> bool:
    """
    Segurança simples para nomes de tabelas/colunas usados em SQL dinâmico.
    """
    return bool(re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name or ""))


# ============================================================
# INTROSPECÇÃO POSTGRESQL
# ============================================================

def has_table(conn, table_name: str, schema: str = "public") -> bool:
    if not _valid_ident(table_name):
        return False

    cur = conn.cursor()
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
              FROM information_schema.tables
             WHERE table_schema = %s
               AND table_name = %s
        )
        """,
        (schema, table_name),
    )
    row = cur.fetchone()
    return bool(_row_get(row, "exists", 0, False))


def has_column(conn, table_name: str, column_name: str, schema: str = "public") -> bool:
    if not _valid_ident(table_name) or not _valid_ident(column_name):
        return False

    cur = conn.cursor()
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
              FROM information_schema.columns
             WHERE table_schema = %s
               AND table_name = %s
               AND column_name = %s
        )
        """,
        (schema, table_name, column_name),
    )
    row = cur.fetchone()
    return bool(_row_get(row, "exists", 0, False))


def table_columns(conn, table_name: str, schema: str = "public") -> set[str]:
    if not _valid_ident(table_name):
        return set()

    cur = conn.cursor()
    cur.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_schema = %s
           AND table_name = %s
        """,
        (schema, table_name),
    )
    return {
        _row_get(r, "column_name", 0, "")
        for r in (cur.fetchall() or [])
        if _row_get(r, "column_name", 0, "")
    }


def first_existing(cols: set[str], opts: list[str]) -> str | None:
    for c in opts:
        if c in cols:
            return c
    return None


# ============================================================
# SCHEMAS POSTGRESQL
# ============================================================

def ensure_atendimentos_schema(conn) -> None:
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS atendimentos (
            id SERIAL PRIMARY KEY,
            paciente_id INTEGER,
            data_atendimento DATE,
            status TEXT,
            justificativa TEXT,
            evolucao TEXT,

            nome TEXT,
            prontuario TEXT,
            mod TEXT,
            status_paciente TEXT,

            anexo_atestado TEXT,

            profissional_id INTEGER,
            nome_profissional TEXT,
            cns_profissional TEXT,
            cbo_profissional TEXT,

            combo_plano_id INTEGER,
            contabiliza_sessao INTEGER NOT NULL DEFAULT 0,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cur.execute("ALTER TABLE atendimentos ADD COLUMN IF NOT EXISTS paciente_id INTEGER")
    cur.execute("ALTER TABLE atendimentos ADD COLUMN IF NOT EXISTS data_atendimento DATE")
    cur.execute("ALTER TABLE atendimentos ADD COLUMN IF NOT EXISTS status TEXT")
    cur.execute("ALTER TABLE atendimentos ADD COLUMN IF NOT EXISTS justificativa TEXT")
    cur.execute("ALTER TABLE atendimentos ADD COLUMN IF NOT EXISTS evolucao TEXT")
    cur.execute("ALTER TABLE atendimentos ADD COLUMN IF NOT EXISTS nome TEXT")
    cur.execute("ALTER TABLE atendimentos ADD COLUMN IF NOT EXISTS prontuario TEXT")
    cur.execute("ALTER TABLE atendimentos ADD COLUMN IF NOT EXISTS mod TEXT")
    cur.execute("ALTER TABLE atendimentos ADD COLUMN IF NOT EXISTS status_paciente TEXT")

    cur.execute("ALTER TABLE atendimentos ADD COLUMN IF NOT EXISTS anexo_atestado TEXT")
    cur.execute("ALTER TABLE atendimentos ADD COLUMN IF NOT EXISTS profissional_id INTEGER")
    cur.execute("ALTER TABLE atendimentos ADD COLUMN IF NOT EXISTS nome_profissional TEXT")
    cur.execute("ALTER TABLE atendimentos ADD COLUMN IF NOT EXISTS cns_profissional TEXT")
    cur.execute("ALTER TABLE atendimentos ADD COLUMN IF NOT EXISTS cbo_profissional TEXT")
    cur.execute("ALTER TABLE atendimentos ADD COLUMN IF NOT EXISTS combo_plano_id INTEGER")
    cur.execute("ALTER TABLE atendimentos ADD COLUMN IF NOT EXISTS contabiliza_sessao INTEGER NOT NULL DEFAULT 0")
    cur.execute("ALTER TABLE atendimentos ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    cur.execute("ALTER TABLE atendimentos ADD COLUMN IF NOT EXISTS atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

def ensure_atendimento_procedimentos_schema(conn) -> None:
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS atendimento_procedimentos (
            id SERIAL PRIMARY KEY,
            atendimento_id INTEGER NOT NULL,
            procedimento TEXT NOT NULL,
            codigo_sigtap TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT fk_atendimento_procedimentos_atendimento
                FOREIGN KEY (atendimento_id)
                REFERENCES atendimentos(id)
                ON DELETE CASCADE
        )
        """
    )

    cur.execute("ALTER TABLE atendimento_procedimentos ADD COLUMN IF NOT EXISTS codigo_sigtap TEXT")
    cur.execute("ALTER TABLE atendimento_procedimentos ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP")

    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_proc_atendimento
            ON atendimento_procedimentos (atendimento_id)
        """
    )

    conn.commit()


def ensure_fila_table(conn) -> None:
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fila_atendimentos (
            id SERIAL PRIMARY KEY,
            hora TEXT NOT NULL,
            paciente_id INTEGER,
            paciente_nome TEXT,
            profissional_id INTEGER NOT NULL,
            tipo TEXT,
            prioridade TEXT,
            obs TEXT,
            origem TEXT DEFAULT 'manual',
            agenda_id INTEGER,
            status TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cur.execute("ALTER TABLE fila_atendimentos ADD COLUMN IF NOT EXISTS origem TEXT DEFAULT 'manual'")
    cur.execute("ALTER TABLE fila_atendimentos ADD COLUMN IF NOT EXISTS agenda_id INTEGER")
    cur.execute("ALTER TABLE fila_atendimentos ADD COLUMN IF NOT EXISTS status TEXT")
    cur.execute("ALTER TABLE fila_atendimentos ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP")

    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_fila_chave_dia
            ON fila_atendimentos (hora, paciente_id, profissional_id)
        """
    )

    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_fila_created_at
            ON fila_atendimentos (created_at)
        """
    )

    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_fila_status
            ON fila_atendimentos (status)
        """
    )

    conn.commit()


# ============================================================
# HELPERS DE COMBO / PLANO
# ============================================================

def buscar_combo_ativo_paciente(conn, paciente_id: int | str | None) -> dict | None:
    if not paciente_id:
        return None

    if not has_table(conn, "financeiro_paciente_planos"):
        return None

    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            pp.id,
            COALESCE(pp.tipo, '') AS tipo,
            COALESCE(pp.combo_nome, '') AS combo_nome,
            COALESCE(pp.nome_plano, '') AS nome_plano,
            COALESCE(pp.sessoes_contratadas, 0) AS sessoes_contratadas,
            COALESCE(pp.status, 'ativo') AS status
        FROM financeiro_paciente_planos pp
        WHERE pp.paciente_id = %s
          AND COALESCE(pp.status, 'ativo') = 'ativo'
        ORDER BY pp.id DESC
        LIMIT 1
        """,
        (paciente_id,),
    )

    row = cur.fetchone()
    if not row:
        return None

    plano_id = _to_int(_row_get(row, "id", 0), 0)

    usadas = 0
    if has_table(conn, "atendimentos") and has_column(conn, "atendimentos", "combo_plano_id"):
        cur.execute(
            """
            SELECT COUNT(*)
              FROM atendimentos
             WHERE combo_plano_id = %s
               AND COALESCE(contabiliza_sessao, 1) = 1
            """,
            (plano_id,),
        )
        usadas = _to_int(_row_get(cur.fetchone(), "count", 0), 0)

    contratadas = _to_int(_row_get(row, "sessoes_contratadas", 4), 0)
    restantes = max(0, contratadas - usadas)

    return {
        "id": plano_id,
        "tipo": _row_get(row, "tipo", 1, "") or "",
        "combo_nome": _row_get(row, "combo_nome", 2, "") or "",
        "nome_plano": _row_get(row, "nome_plano", 3, "") or "",
        "sessoes_contratadas": contratadas,
        "sessoes_usadas": usadas,
        "sessoes_restantes": restantes,
        "status": _row_get(row, "status", 5, "ativo") or "ativo",
    }


def listar_combos_ativos_para_template(conn) -> list[dict]:
    if not has_table(conn, "financeiro_paciente_planos"):
        return []

    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            pp.id,
            pp.paciente_id,
            COALESCE(pp.paciente_nome, '') AS paciente_nome,
            COALESCE(pp.tipo, '') AS tipo,
            COALESCE(pp.combo_nome, '') AS combo_nome,
            COALESCE(pp.nome_plano, '') AS nome_plano,
            COALESCE(pp.sessoes_contratadas, 0) AS sessoes_contratadas,
            COALESCE(pp.status, 'ativo') AS status
        FROM financeiro_paciente_planos pp
        WHERE COALESCE(pp.status, 'ativo') = 'ativo'
        ORDER BY LOWER(COALESCE(pp.paciente_nome, '')) ASC
        """
    )

    rows = cur.fetchall() or []
    items = []

    for row in rows:
        plano_id = _to_int(_row_get(row, "id", 0), 0)

        usadas = 0
        if has_table(conn, "atendimentos") and has_column(conn, "atendimentos", "combo_plano_id"):
            cur.execute(
                """
                SELECT COUNT(*)
                  FROM atendimentos
                 WHERE combo_plano_id = %s
                   AND COALESCE(contabiliza_sessao, 1) = 1
                """,
                (plano_id,),
            )
            usadas = _to_int(_row_get(cur.fetchone(), "count", 0), 0)

        contratadas = _to_int(_row_get(row, "sessoes_contratadas", 6), 0)
        restantes = max(0, contratadas - usadas)

        items.append({
            "id": plano_id,
            "paciente_id": _to_int(_row_get(row, "paciente_id", 1), 0),
            "paciente_nome": _row_get(row, "paciente_nome", 2, "") or "",
            "tipo": _row_get(row, "tipo", 3, "") or "",
            "combo_nome": _row_get(row, "combo_nome", 4, "") or "",
            "nome_plano": _row_get(row, "nome_plano", 5, "") or "",
            "sessoes_contratadas": contratadas,
            "sessoes_usadas": usadas,
            "sessoes_restantes": restantes,
            "status": _row_get(row, "status", 7, "ativo") or "ativo",
        })

    return items


def recalcular_saldo_combo(conn, combo_plano_id: int | None) -> None:
    if not combo_plano_id:
        return

    if not has_table(conn, "financeiro_paciente_planos"):
        return

    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            COALESCE(sessoes_contratadas, 0) AS sessoes_contratadas,
            COALESCE(status, 'ativo') AS status
        FROM financeiro_paciente_planos
        WHERE id = %s
        LIMIT 1
        """,
        (combo_plano_id,),
    )

    row = cur.fetchone()
    if not row:
        return

    contratadas = _to_int(_row_get(row, "sessoes_contratadas", 0), 0)

    cur.execute(
        """
        SELECT COUNT(*)
          FROM atendimentos
         WHERE combo_plano_id = %s
           AND COALESCE(contabiliza_sessao, 1) = 1
        """,
        (combo_plano_id,),
    )

    usadas = _to_int(_row_get(cur.fetchone(), "count", 0), 0)
    restantes = max(0, contratadas - usadas)

    novo_status = "encerrado" if contratadas > 0 and restantes <= 0 else "ativo"

    cur.execute(
        """
        UPDATE financeiro_paciente_planos
           SET sessoes_usadas = %s,
               status = %s,
               atualizado_em = CURRENT_TIMESTAMP
         WHERE id = %s
        """,
        (usadas, novo_status, combo_plano_id),
    )

    conn.commit()


# ============================================================
# LOGIN / PROFISSIONAL
# ============================================================

def resolve_logged_profissional_id(conn) -> int | None:
    for key in ("usuario_id", "user_id", "id"):
        val = session.get(key)
        if val is not None:
            try:
                return int(val)
            except Exception:
                pass

    login_like = (
        session.get("usuario_logado")
        or session.get("login")
        or session.get("username")
        or session.get("email")
    )

    if not login_like or not has_table(conn, "usuarios"):
        return None

    cols = table_columns(conn, "usuarios")
    busca_cols = [c for c in ("login", "nome", "email") if c in cols]

    if not busca_cols:
        return None

    conds = [f"TRIM(LOWER(COALESCE({c}, ''))) = TRIM(LOWER(%s))" for c in busca_cols]
    params = [login_like] * len(busca_cols)

    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT id
          FROM usuarios
         WHERE {" OR ".join(conds)}
         LIMIT 1
        """,
        params,
    )

    row = cur.fetchone()
    return _to_int(_row_get(row, "id", 0), None) if row else None


def resolve_prof_dados(conn, profissional_id: int | None):
    if not profissional_id:
        return None, "", "", ""

    if not has_table(conn, "usuarios"):
        return profissional_id, "", "", ""

    cols = table_columns(conn, "usuarios")

    nome_expr = "COALESCE(nome, '')" if "nome" in cols else "''"
    cns_expr = "COALESCE(cns, '')" if "cns" in cols else "''"
    cbo_expr = "COALESCE(cbo, '')" if "cbo" in cols else "''"

    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT
            id,
            {nome_expr} AS nome,
            {cns_expr} AS cns,
            {cbo_expr} AS cbo
        FROM usuarios
        WHERE id = %s
        LIMIT 1
        """,
        (profissional_id,),
    )

    row = cur.fetchone()
    if not row:
        return profissional_id, "", "", ""

    return (
        _row_get(row, "id", 0),
        _row_get(row, "nome", 1, "") or "",
        _row_get(row, "cns", 2, "") or "",
        _row_get(row, "cbo", 3, "") or "",
    )


def resolve_prof_nome(conn, profissional_id: int | None) -> str:
    if not profissional_id:
        return "—"

    cur = conn.cursor()

    if has_table(conn, "profissionais") and has_column(conn, "profissionais", "nome"):
        cond = ""
        if has_column(conn, "profissionais", "ativo"):
            cond = "AND (ativo = TRUE OR ativo IS NULL)"

        cur.execute(
            f"""
            SELECT nome
              FROM profissionais
             WHERE id = %s
               {cond}
             LIMIT 1
            """,
            (profissional_id,),
        )
        row = cur.fetchone()
        nome = _row_get(row, "nome", 0, "")
        if nome:
            return nome

    if has_table(conn, "usuarios") and has_column(conn, "usuarios", "nome"):
        conds = []

        if has_column(conn, "usuarios", "role"):
            conds.append("UPPER(COALESCE(role, '')) = 'PROFISSIONAL'")

        if has_column(conn, "usuarios", "is_active"):
            conds.append("(is_active IS TRUE OR is_active IS NULL)")

        extra = f"AND {' AND '.join(conds)}" if conds else ""

        cur.execute(
            f"""
            SELECT nome
              FROM usuarios
             WHERE id = %s
             {extra}
             LIMIT 1
            """,
            (profissional_id,),
        )
        row = cur.fetchone()
        nome = _row_get(row, "nome", 0, "")
        if nome:
            return nome

    return "—"


# ============================================================
# CIDs / PROCEDIMENTOS
# ============================================================

def split_cids(raw: str | None) -> list[str]:
    if not raw:
        return []

    s = str(raw).upper()
    for ch in [";", "|", "\n", "\t"]:
        s = s.replace(ch, ",")

    return [p.strip() for p in s.split(",") if p.strip()]


def cid_norm_py(cid: str | None) -> str:
    return "".join(ch for ch in (cid or "").upper().strip() if ch.isalnum())


def split_codes_csv(raw: str | None) -> list[str]:
    if not raw:
        return []

    s = str(raw)
    for ch in [";", "|", "\n", "\t"]:
        s = s.replace(ch, ",")

    items = []
    vistos = set()

    for part in s.split(","):
        item = cid_norm_py(part)
        if not item or item in vistos:
            continue

        vistos.add(item)
        items.append(item)

    return items


def get_paciente_cids(conn, paciente_id: str | int | None) -> list[str]:
    if not paciente_id or not has_table(conn, "pacientes"):
        return []

    cols = table_columns(conn, "pacientes")
    cid_cols = [c for c in ("cid", "cid2", "cid3", "cid4", "cid5") if c in cols]

    if not cid_cols:
        return []

    select_parts = [f"COALESCE({c}, '') AS {c}" for c in cid_cols]

    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT {", ".join(select_parts)}
          FROM pacientes
         WHERE id = %s
         LIMIT 1
        """,
        (paciente_id,),
    )

    row = cur.fetchone()
    if not row:
        return []

    coletados = []
    vistos = set()

    for idx, col in enumerate(cid_cols):
        raw = _row_get(row, col, idx, "")
        for cid in split_cids(raw):
            norm = cid_norm_py(cid)
            if not norm or norm in vistos:
                continue

            vistos.add(norm)
            coletados.append(norm)

    return coletados


def get_procedimentos_competencia_vigente(conn) -> str:
    if not has_table(conn, "procedimentos"):
        return ""

    if not has_column(conn, "procedimentos", "competencia"):
        return ""

    cur = conn.cursor()
    cur.execute(
        """
        SELECT MAX(TRIM(COALESCE(competencia, ''))) AS competencia
          FROM procedimentos
         WHERE TRIM(COALESCE(competencia, '')) <> ''
        """
    )

    row = cur.fetchone()
    return (_row_get(row, "competencia", 0, "") or "").strip()


def procedimento_compativel(cbo_prof: str, paciente_cids: list[str], proc_row: Any) -> bool:
    cbo_norm = cid_norm_py(cbo_prof)
    if not cbo_norm:
        return False

    cbos_raw = _row_get(proc_row, "cbos_codigos", 5, "")
    cids_raw = _row_get(proc_row, "cids_codigos", 3, "")

    cbos_proc = split_codes_csv(cbos_raw)
    if not cbos_proc or cbo_norm not in cbos_proc:
        return False

    cids_proc = split_codes_csv(cids_raw)
    if not cids_proc:
        return True

    pac_norms = [cid_norm_py(x) for x in (paciente_cids or []) if x]
    if not pac_norms:
        return False

    proc_set = set(cids_proc)
    return any(cid in proc_set for cid in pac_norms)


def listar_procedimentos_compativeis_db(conn, cbo: str, paciente_cids: list[str]) -> list[dict]:
    cbo = (cbo or "").strip()
    if not cbo:
        return []

    if not has_table(conn, "procedimentos"):
        return []

    cols = table_columns(conn, "procedimentos")
    required = {"codigo", "descricao", "competencia", "cids_codigos", "cbos_codigos"}

    if not required.issubset(cols):
        return []

    competencia_vigente = get_procedimentos_competencia_vigente(conn)

    cur = conn.cursor()

    sql = """
        SELECT
            COALESCE(codigo, '') AS codigo,
            COALESCE(descricao, '') AS descricao,
            COALESCE(competencia, '') AS competencia,
            COALESCE(cids_codigos, '') AS cids_codigos,
            COALESCE(cids_descricoes, '') AS cids_descricoes,
            COALESCE(cbos_codigos, '') AS cbos_codigos,
            COALESCE(cbos_descricoes, '') AS cbos_descricoes
        FROM procedimentos
    """

    params = []

    if competencia_vigente:
        sql += " WHERE TRIM(COALESCE(competencia, '')) = TRIM(%s)"
        params.append(competencia_vigente)

    sql += " ORDER BY LOWER(descricao), codigo"

    cur.execute(sql, params)
    rows = cur.fetchall() or []

    items = []
    vistos = set()

    for row in rows:
        if not procedimento_compativel(cbo, paciente_cids, row):
            continue

        codigo = (_row_get(row, "codigo", 0, "") or "").strip()
        descricao = (_row_get(row, "descricao", 1, "") or "").strip()
        chave = (codigo, descricao.lower())

        if not descricao or chave in vistos:
            continue

        vistos.add(chave)

        items.append({
            "codigo": codigo,
            "descricao": descricao,
            "competencia": (_row_get(row, "competencia", 2, "") or "").strip(),
            "cids_codigos": (_row_get(row, "cids_codigos", 3, "") or "").strip(),
            "cids_descricoes": (_row_get(row, "cids_descricoes", 4, "") or "").strip(),
            "cbos_codigos": (_row_get(row, "cbos_codigos", 5, "") or "").strip(),
            "cbos_descricoes": (_row_get(row, "cbos_descricoes", 6, "") or "").strip(),
        })

    return items


# ============================================================
# PACIENTES / PROFISSIONAIS
# ============================================================

def fetch_pacientes(conn) -> list[dict]:
    if not has_table(conn, "pacientes"):
        return []

    cols = table_columns(conn, "pacientes")

    col_pront = "prontuario" if "prontuario" in cols else "''"
    col_mod = "mod" if "mod" in cols else "''"
    col_stat = "status" if "status" in cols else "''"
    col_cpf = "cpf" if "cpf" in cols else "''"

    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT
            id,
            COALESCE(nome, '') AS nome,
            COALESCE({col_cpf}, '') AS cpf,
            COALESCE({col_pront}, '') AS prontuario,
            COALESCE({col_mod}, '') AS mod,
            COALESCE({col_stat}, '') AS status
        FROM pacientes
        ORDER BY LOWER(COALESCE(nome, ''))
        """
    )

    rows = cur.fetchall() or []

    return [
        {
            "id": _row_get(r, "id", 0),
            "nome": _row_get(r, "nome", 1, "") or "",
            "cpf": _row_get(r, "cpf", 2, "") or "",
            "prontuario": _row_get(r, "prontuario", 3, "") or "",
            "mod": _row_get(r, "mod", 4, "") or "",
            "status": _row_get(r, "status", 5, "") or "",
        }
        for r in rows
    ]


def listar_profissionais_usuarios(conn) -> list[dict]:
    if not has_table(conn, "usuarios"):
        return []

    cols = table_columns(conn, "usuarios")

    nome_expr = "COALESCE(nome, '')" if "nome" in cols else "''"
    login_expr = "COALESCE(login, '')" if "login" in cols else "''"
    email_expr = "COALESCE(email, '')" if "email" in cols else "''"

    conds = ["1=1"]

    if "role" in cols:
        conds.append("UPPER(COALESCE(role, '')) = 'PROFISSIONAL'")

    if "is_active" in cols:
        conds.append("(is_active IS TRUE OR is_active IS NULL)")
        
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT
            id,
            TRIM(
                CASE
                    WHEN {nome_expr} <> '' THEN {nome_expr}
                    WHEN {login_expr} <> '' THEN {login_expr}
                    ELSE {email_expr}
                END
            ) AS nome
        FROM usuarios
        WHERE {" AND ".join(conds)}
        ORDER BY LOWER(nome)
        """
    )

    rows = cur.fetchall() or []

    return [
        {
            "id": _row_get(r, "id", 0),
            "nome": (_row_get(r, "nome", 1, "") or "").strip(),
        }
        for r in rows
        if (_row_get(r, "nome", 1, "") or "").strip()
    ]


def resolve_paciente_id_by_nome(conn, nome: str) -> int | None:
    if not nome or not has_table(conn, "pacientes"):
        return None

    cur = conn.cursor()
    cur.execute(
        """
        SELECT id
          FROM pacientes
         WHERE TRIM(UPPER(nome)) = TRIM(UPPER(%s))
         LIMIT 1
        """,
        (nome,),
    )

    row = cur.fetchone()
    return _to_int(_row_get(row, "id", 0), None) if row else None


def resolve_prof_id_by_nome_ou_cpf(conn, nome: str | None, cpf: str | None) -> int | None:
    cur = conn.cursor()

    if cpf and has_table(conn, "usuarios") and has_column(conn, "usuarios", "cpf"):
        cur.execute(
            """
            SELECT id
              FROM usuarios
             WHERE REGEXP_REPLACE(COALESCE(cpf, ''), '\\D', '', 'g') = REGEXP_REPLACE(%s, '\\D', '', 'g')
             LIMIT 1
            """,
            (cpf,),
        )
        row = cur.fetchone()
        if row:
            return _to_int(_row_get(row, "id", 0), None)

    if nome and has_table(conn, "usuarios") and has_column(conn, "usuarios", "nome"):
        cur.execute(
            """
            SELECT id
              FROM usuarios
             WHERE TRIM(UPPER(nome)) = TRIM(UPPER(%s))
             LIMIT 1
            """,
            (nome,),
        )
        row = cur.fetchone()
        if row:
            return _to_int(_row_get(row, "id", 0), None)

    if nome and has_table(conn, "profissionais") and has_column(conn, "profissionais", "nome"):
        cur.execute(
            """
            SELECT id
              FROM profissionais
             WHERE TRIM(UPPER(nome)) = TRIM(UPPER(%s))
             LIMIT 1
            """,
            (nome,),
        )
        row = cur.fetchone()
        if row:
            return _to_int(_row_get(row, "id", 0), None)

    return None


def resolve_paciente(conn, paciente_id: str | None, paciente_texto: str | None):
    if not has_table(conn, "pacientes"):
        return None

    cur = conn.cursor()

    if paciente_id:
        cur.execute(
            """
            SELECT id, nome, COALESCE(cpf, '') AS cpf
              FROM pacientes
             WHERE id = %s
             LIMIT 1
            """,
            (paciente_id,),
        )
        row = cur.fetchone()
        if row:
            return {
                "id": _row_get(row, "id", 0),
                "nome": _row_get(row, "nome", 1, ""),
                "cpf": _row_get(row, "cpf", 2, ""),
            }

    txt = (paciente_texto or "").strip()
    if not txt:
        return None

    if "(" in txt and txt.endswith(")"):
        cpf_str = txt.split("(")[-1].strip(") ").strip()
        cpf_digits = digits(cpf_str)

        cur.execute(
            """
            SELECT id, nome, COALESCE(cpf, '') AS cpf
              FROM pacientes
             WHERE REGEXP_REPLACE(COALESCE(cpf, ''), '\\D', '', 'g') = %s
             LIMIT 1
            """,
            (cpf_digits,),
        )

        row = cur.fetchone()
        if row:
            return {
                "id": _row_get(row, "id", 0),
                "nome": _row_get(row, "nome", 1, ""),
                "cpf": _row_get(row, "cpf", 2, ""),
            }

    nome = txt.split("(")[0].strip()
    if nome:
        cur.execute(
            """
            SELECT id, nome, COALESCE(cpf, '') AS cpf
              FROM pacientes
             WHERE nome ILIKE %s
             ORDER BY nome
             LIMIT 1
            """,
            (f"{nome}%",),
        )

        row = cur.fetchone()
        if row:
            return {
                "id": _row_get(row, "id", 0),
                "nome": _row_get(row, "nome", 1, ""),
                "cpf": _row_get(row, "cpf", 2, ""),
            }

    return None


# ============================================================
# AGENDA → FILA
# ============================================================

def today_iso() -> str:
    return date.today().isoformat()


def has_agenda_table(conn) -> bool:
    return has_table(conn, "agendamentos")


def sync_today_agenda_to_fila(conn) -> None:
    if not has_agenda_table(conn):
        return

    if not has_table(conn, "pacientes"):
        return

    ensure_fila_table(conn)
    ensure_atendimentos_schema(conn)

    cur = conn.cursor()
    hoje = today_iso()

    cols = table_columns(conn, "agendamentos")
    has_prof_cpf = "profissional_cpf" in cols

    prof_cpf_expr = "TRIM(COALESCE(profissional_cpf, '')) AS prof_cpf" if has_prof_cpf else "'' AS prof_cpf"

    cur.execute(
        f"""
        SELECT
            id,
            TRIM(COALESCE(paciente, '')) AS paciente,
            TRIM(COALESCE(profissional, '')) AS profissional,
            {prof_cpf_expr},
            TO_CHAR(inicio, 'HH24:MI') AS hora_ini
        FROM agendamentos
        WHERE DATE(inicio) = %s
        ORDER BY hora_ini ASC, profissional ASC, paciente ASC
        """,
        (hoje,),
    )

    ag_rows = cur.fetchall() or []

    for row in ag_rows:
        aid = _row_get(row, "id", 0)
        pac = _row_get(row, "paciente", 1, "")
        prof = _row_get(row, "profissional", 2, "")
        prof_cpf = _row_get(row, "prof_cpf", 3, "")
        hora = _row_get(row, "hora_ini", 4, "")

        if not hora:
            continue

        pac_id = resolve_paciente_id_by_nome(conn, pac) if pac else None
        prof_id = resolve_prof_id_by_nome_ou_cpf(conn, prof, prof_cpf if has_prof_cpf else None)

        if not pac_id or not prof_id:
            continue

        cur.execute(
            """
            SELECT 1
              FROM atendimentos
             WHERE paciente_id = %s
               AND data_atendimento = %s
             LIMIT 1
            """,
            (pac_id, hoje),
        )
        if cur.fetchone():
            continue

        cur.execute(
            """
            SELECT 1
              FROM fila_atendimentos
             WHERE hora = %s
               AND paciente_id = %s
               AND profissional_id = %s
               AND DATE(created_at) = %s
             LIMIT 1
            """,
            (hora, pac_id, prof_id, hoje),
        )
        if cur.fetchone():
            continue

        cur.execute(
            """
            INSERT INTO fila_atendimentos
                (hora, paciente_id, paciente_nome, profissional_id, tipo, prioridade, obs, created_at, origem, agenda_id)
            SELECT %s, id, nome, %s, 'Individual', 'verde', '', CURRENT_TIMESTAMP, 'agenda', %s
              FROM pacientes
             WHERE id = %s
             LIMIT 1
            """,
            (hora, prof_id, aid, pac_id),
        )

    conn.commit()


# ============================================================
# FORMULÁRIOS
# ============================================================

def normalize_procs_from_form(request_form) -> tuple[list[str], list[str]]:
    procs = request_form.getlist("procedimento[]")
    cods = request_form.getlist("codigoProcedimento[]")

    if not procs:
        p = (request_form.get("procedimento") or "").strip()
        c = (request_form.get("codigoProcedimento") or "").strip()

        if p:
            procs = [p]
            cods = [c] if c else [""]

    procs = [str(x or "").strip() for x in procs if str(x or "").strip()]

    if len(cods) < len(procs):
        cods += [""] * (len(procs) - len(cods))

    cods = [str(x or "").strip() for x in cods][:len(procs)]

    return procs, cods