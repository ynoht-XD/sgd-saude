from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, List, Optional

from flask import render_template, request, session, jsonify, url_for

from . import meus_atendimentos_bp
from db import conectar_db


# ============================================================
# HELPERS · POSTGRES
# ============================================================

def _only_digits(v: str | None) -> str:
    return re.sub(r"\D+", "", v or "")


def _val(row, key: str, index: int = 0, default=None):
    if not row:
        return default

    if isinstance(row, dict):
        return row.get(key, default)

    try:
        return row[index]
    except Exception:
        return default


def has_table(conn, table_name: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1
                  FROM information_schema.tables
                 WHERE table_schema = 'public'
                   AND table_name = %s
            ) AS existe
        """, (table_name,))
        return bool(_val(cur.fetchone(), "existe", 0, False))
    finally:
        cur.close()


def has_column(conn, table_name: str, column_name: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1
                  FROM information_schema.columns
                 WHERE table_schema = 'public'
                   AND table_name = %s
                   AND column_name = %s
            ) AS existe
        """, (table_name, column_name))
        return bool(_val(cur.fetchone(), "existe", 0, False))
    finally:
        cur.close()


def _table_columns(conn, table: str) -> set[str]:
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = %s
        """, (table,))
        rows = cur.fetchall() or []
        return {
            _val(r, "column_name", 0)
            for r in rows
            if _val(r, "column_name", 0)
        }
    finally:
        cur.close()


def ensure_column(conn, table: str, col: str, ddl_type: str):
    if not has_table(conn, table):
        return

    if has_column(conn, table, col):
        return

    cur = conn.cursor()
    try:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl_type}")
        conn.commit()
    finally:
        cur.close()


def _first_existing(cols: set[str], opts: list[str]) -> str | None:
    for c in opts:
        if c in cols:
            return c
    return None


def _today_iso() -> str:
    return date.today().isoformat()


def _month_start_iso(d: date | None = None) -> str:
    d = d or date.today()
    return date(d.year, d.month, 1).isoformat()


def _norm_date_iso(s: str) -> Optional[str]:
    if not s:
        return None

    s = str(s).strip()
    if not s:
        return None

    try:
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            datetime.strptime(s[:10], "%Y-%m-%d")
            return s[:10]
    except Exception:
        pass

    try:
        if len(s) == 10 and s[2] == "/" and s[5] == "/":
            dt = datetime.strptime(s, "%d/%m/%Y").date()
            return dt.isoformat()
    except Exception:
        pass

    return None


def _int_or_none(s: str) -> Optional[int]:
    try:
        if s is None:
            return None
        s = str(s).strip()
        if not s:
            return None
        return int(s)
    except Exception:
        return None


def _row_to_dict(cur, row) -> dict:
    if not row:
        return {}

    if isinstance(row, dict):
        return dict(row)

    cols = [d[0] for d in cur.description]
    return {cols[i]: row[i] for i in range(len(cols))}


def _date_expr(col_sql: str) -> str:
    return f"""
    (
      CASE
        WHEN {col_sql} IS NULL THEN NULL
        WHEN {col_sql}::text ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}' THEN ({col_sql})::date
        WHEN {col_sql}::text ~ '^\\d{{2}}/\\d{{2}}/\\d{{4}}' THEN TO_DATE(SUBSTRING({col_sql}::text FROM 1 FOR 10), 'DD/MM/YYYY')
        ELSE NULL
      END
    )
    """


def _idade_expr(nasc_sql: str) -> str:
    return f"""
    (
      CASE
        WHEN {_date_expr(nasc_sql)} IS NULL THEN NULL
        ELSE DATE_PART('year', AGE(CURRENT_DATE, {_date_expr(nasc_sql)}))::int
      END
    )
    """


# ============================================================
# SCHEMA · POSTGRES
# ============================================================

def ensure_atendimentos_schema(conn):
    cur = conn.cursor()

    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS atendimentos (
                id SERIAL PRIMARY KEY,

                profissional_id INTEGER,
                usuario_id INTEGER,

                paciente_id INTEGER,
                cidadao_id INTEGER,
                paciente_nome TEXT,
                nome_paciente TEXT,
                paciente TEXT,
                nome TEXT,

                data_atendimento DATE,
                data TEXT,
                dt_atendimento TEXT,
                criado_em TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                evolucao TEXT,
                evolucao_texto TEXT,

                cidade TEXT,
                municipio TEXT,
                cid TEXT,
                cid_codigo TEXT,

                status TEXT,
                justificativa TEXT,
                cbo_profissional TEXT,
                nome_profissional TEXT,
                cns_profissional TEXT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS atendimento_procedimentos (
                id SERIAL PRIMARY KEY,
                atendimento_id INTEGER NOT NULL REFERENCES atendimentos(id) ON DELETE CASCADE,
                procedimento TEXT,
                procedimento_nome TEXT,
                descricao TEXT,
                codigo_sigtap TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()

    finally:
        cur.close()

    ensure_column(conn, "atendimentos", "profissional_id", "INTEGER")
    ensure_column(conn, "atendimentos", "usuario_id", "INTEGER")
    ensure_column(conn, "atendimentos", "paciente_id", "INTEGER")
    ensure_column(conn, "atendimentos", "cidadao_id", "INTEGER")
    ensure_column(conn, "atendimentos", "data_atendimento", "DATE")
    ensure_column(conn, "atendimentos", "created_at", "TIMESTAMP")
    ensure_column(conn, "atendimentos", "criado_em", "TIMESTAMP")
    ensure_column(conn, "atendimentos", "evolucao", "TEXT")
    ensure_column(conn, "atendimentos", "cidade", "TEXT")
    ensure_column(conn, "atendimentos", "municipio", "TEXT")
    ensure_column(conn, "atendimentos", "cid", "TEXT")
    ensure_column(conn, "atendimentos", "status", "TEXT")
    ensure_column(conn, "atendimentos", "justificativa", "TEXT")

    ensure_column(conn, "atendimento_procedimentos", "codigo_sigtap", "TEXT")

    cur = conn.cursor()

    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_atend_prof ON atendimentos (profissional_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_atend_data ON atendimentos (data_atendimento)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_atend_usuario ON atendimentos (usuario_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ap_atend ON atendimento_procedimentos (atendimento_id)")
        conn.commit()
    finally:
        cur.close()


# ============================================================
# LOGADO -> PROFISSIONAL
# ============================================================

def _resolve_logged_profissional_id(conn) -> int | None:
    for key in ("profissional_id", "usuario_id", "user_id", "id"):
        val = session.get(key)
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                pass

    login_like = (
        session.get("usuario_logado")
        or session.get("login")
        or session.get("username")
        or session.get("email")
    )

    if not login_like:
        return None

    if not has_table(conn, "usuarios"):
        return None

    cols = _table_columns(conn, "usuarios")
    parts = [c for c in ("login", "nome", "email") if c in cols]

    if not parts:
        return None

    cur = conn.cursor()

    try:
        conds = [
            f"TRIM(LOWER(COALESCE({c}::text, ''))) = TRIM(LOWER(%s))"
            for c in parts
        ]

        cur.execute(
            f"""
            SELECT id
              FROM usuarios
             WHERE {" OR ".join(conds)}
             LIMIT 1
            """,
            [login_like] * len(conds),
        )

        row = cur.fetchone()
        return int(_val(row, "id", 0)) if row else None

    finally:
        cur.close()


def _build_url_with_page(page: int) -> str:
    args = dict(request.args)
    args["page"] = str(page)
    return url_for("meus_atendimentos.index", **args)


# ============================================================
# QUERY PRINCIPAL
# ============================================================

def _query_meus_atendimentos_paginado(
    conn,
    profissional_uid: int,
    q_nome: str = "",
    data_ini: Optional[str] = None,
    data_fim: Optional[str] = None,
    idade_min: Optional[int] = None,
    idade_max: Optional[int] = None,
    cidade: str = "",
    cid: str = "",
    page: int = 1,
    per_page: int = 20,
) -> tuple[int, list[dict]]:
    ensure_atendimentos_schema(conn)

    a_cols = _table_columns(conn, "atendimentos")

    col_prof = _first_existing(a_cols, ["profissional_id", "usuario_id", "user_id"])
    col_pac_id = _first_existing(a_cols, ["paciente_id", "cidadao_id"])
    col_pac_nome = _first_existing(a_cols, ["nome", "paciente", "paciente_nome", "nome_paciente"])
    col_data = _first_existing(a_cols, ["data_atendimento", "data", "dt_atendimento", "criado_em", "created_at"])
    col_evol = _first_existing(a_cols, ["evolucao", "evolução", "evolucao_texto", "evolucao_md", "evolucao_html"])
    col_a_cidade = _first_existing(a_cols, ["cidade", "municipio", "município", "cidade_nome"])
    col_a_cid = _first_existing(a_cols, ["cid", "cid_codigo", "cid_principal", "cid10", "cid_primario"])

    if not col_prof:
        raise RuntimeError("Tabela atendimentos sem coluna profissional_id/usuario_id/user_id.")

    if not col_data:
        raise RuntimeError("Tabela atendimentos sem coluna de data.")

    paciente_expr = f"TRIM(COALESCE(a.{col_pac_nome}::text, ''))" if col_pac_nome else "''"
    data_expr = _date_expr(f"a.{col_data}")
    evol_expr = f"COALESCE(a.{col_evol}::text, '')" if col_evol else "''"

    cidade_expr = f"TRIM(LOWER(COALESCE(a.{col_a_cidade}::text, '')))" if col_a_cidade else "''"
    cid_expr = f"TRIM(UPPER(COALESCE(a.{col_a_cid}::text, '')))" if col_a_cid else "''"

    joins = []
    idade_expr = "NULL"

    if col_pac_id and has_table(conn, "pacientes"):
        p_cols = _table_columns(conn, "pacientes")
        col_p_id = _first_existing(p_cols, ["id", "cidadao_id"])
        col_p_nasc = _first_existing(p_cols, ["nascimento", "data_nascimento", "dt_nascimento"])
        col_p_nome = _first_existing(p_cols, ["nome", "nome_completo"])
        col_p_cidade = _first_existing(p_cols, ["municipio", "município", "cidade", "cidade_nome"])
        col_p_cid = _first_existing(p_cols, ["cid", "cid_codigo", "cid_principal", "cid10", "cid_primario"])

        if col_p_id:
            joins.append(f"LEFT JOIN pacientes p ON p.{col_p_id} = a.{col_pac_id}")

        if col_p_id and col_p_nasc:
            idade_expr = _idade_expr(f"p.{col_p_nasc}")

        if col_p_nome and col_pac_nome:
            paciente_expr = f"TRIM(COALESCE(NULLIF(a.{col_pac_nome}::text, ''), p.{col_p_nome}::text, ''))"
        elif col_p_nome and not col_pac_nome:
            paciente_expr = f"TRIM(COALESCE(p.{col_p_nome}::text, ''))"

        if not col_a_cidade and col_p_cidade:
            cidade_expr = f"TRIM(LOWER(COALESCE(p.{col_p_cidade}::text, '')))"

        if not col_a_cid and col_p_cid:
            cid_expr = f"TRIM(UPPER(COALESCE(p.{col_p_cid}::text, '')))"

    proc_expr = "''"

    if has_table(conn, "atendimento_procedimentos"):
        ap_cols = _table_columns(conn, "atendimento_procedimentos")
        col_ap_atend = _first_existing(ap_cols, ["atendimento_id"])
        col_ap_proc = _first_existing(ap_cols, ["procedimento", "procedimento_nome", "descricao"])

        if col_ap_atend and col_ap_proc:
            joins.append("LEFT JOIN atendimento_procedimentos ap ON ap.atendimento_id = a.id")
            proc_expr = f"COALESCE(STRING_AGG(DISTINCT NULLIF(TRIM(ap.{col_ap_proc}::text), ''), ' • '), '')"

    where: List[str] = [f"a.{col_prof} = %s"]
    params: List[Any] = [int(profissional_uid)]

    if q_nome:
        where.append(f"{paciente_expr} ILIKE %s")
        params.append(f"%{q_nome}%")

    if data_ini:
        where.append(f"{data_expr} >= %s::date")
        params.append(data_ini)

    if data_fim:
        where.append(f"{data_expr} <= %s::date")
        params.append(data_fim)

    if idade_expr != "NULL":
        if idade_min is not None:
            where.append(f"({idade_expr}) >= %s")
            params.append(idade_min)

        if idade_max is not None:
            where.append(f"({idade_expr}) <= %s")
            params.append(idade_max)

    if cidade and cidade_expr != "''":
        where.append(f"{cidade_expr} ILIKE %s")
        params.append(f"%{cidade.strip().lower()}%")

    if cid and cid_expr != "''":
        where.append(f"{cid_expr} ILIKE %s")
        params.append(f"%{cid.strip().upper()}%")

    where_sql = " AND ".join(where)
    join_sql = "\n".join(joins)

    count_sql = f"""
        SELECT COUNT(DISTINCT a.id) AS total
          FROM atendimentos a
          {join_sql}
         WHERE {where_sql}
    """

    cur = conn.cursor()

    try:
        cur.execute(count_sql, params)
        total = int(_val(cur.fetchone(), "total", 0, 0) or 0)

        page = max(1, int(page or 1))
        per_page = max(1, min(200, int(per_page or 20)))
        offset = (page - 1) * per_page

        list_sql = f"""
            SELECT
                a.id AS id,
                {paciente_expr} AS paciente,
                {proc_expr} AS procedimento,
                COALESCE({data_expr}::text, '') AS data,
                {evol_expr} AS evolucao,
                SUBSTRING({evol_expr} FROM 1 FOR 260) AS evolucao_preview,
                {idade_expr} AS idade
            FROM atendimentos a
            {join_sql}
            WHERE {where_sql}
            GROUP BY
                a.id,
                {paciente_expr},
                {data_expr},
                {evol_expr},
                {idade_expr}
            ORDER BY {data_expr} DESC NULLS LAST, a.id DESC
            LIMIT %s OFFSET %s
        """

        cur.execute(list_sql, params + [per_page, offset])
        rows = cur.fetchall() or []

        return total, [_row_to_dict(cur, r) for r in rows]

    finally:
        cur.close()


# ============================================================
# ROTAS
# ============================================================

@meus_atendimentos_bp.route("", methods=["GET"])
@meus_atendimentos_bp.route("/", methods=["GET"])
def index():
    conn = conectar_db()

    try:
        ensure_atendimentos_schema(conn)

        profissional_uid = _resolve_logged_profissional_id(conn)

        if not profissional_uid:
            return (
                "<h2>403</h2><p>Não foi possível identificar o profissional logado. Faça login novamente.</p>",
                403,
                {"Content-Type": "text/html; charset=utf-8"},
            )

        q_nome = (request.args.get("q") or "").strip()
        cidade = (request.args.get("cidade") or "").strip()
        cid = (request.args.get("cid") or "").strip()

        data_ini = _norm_date_iso(request.args.get("data_ini") or "")
        data_fim = _norm_date_iso(request.args.get("data_fim") or "")
        idade_min = _int_or_none(request.args.get("idade_min"))
        idade_max = _int_or_none(request.args.get("idade_max"))

        page = _int_or_none(request.args.get("page")) or 1
        per_page = _int_or_none(request.args.get("per_page")) or 20

        if not data_ini and not data_fim:
            data_ini = _month_start_iso()
            data_fim = _today_iso()

        total, rows = _query_meus_atendimentos_paginado(
            conn=conn,
            profissional_uid=profissional_uid,
            q_nome=q_nome,
            data_ini=data_ini,
            data_fim=data_fim,
            idade_min=idade_min,
            idade_max=idade_max,
            cidade=cidade,
            cid=cid,
            page=page,
            per_page=per_page,
        )

        pages = max(1, (total + per_page - 1) // per_page)

        if page > pages:
            page = pages

        has_prev = page > 1
        has_next = page < pages

        return render_template(
            "meus_atendimentos.html",
            atendimentos=rows,
            filtros={
                "q": q_nome,
                "cidade": cidade,
                "cid": cid,
                "data_ini": data_ini or "",
                "data_fim": data_fim or "",
                "idade_min": "" if idade_min is None else str(idade_min),
                "idade_max": "" if idade_max is None else str(idade_max),
            },
            hoje=_today_iso(),
            total=total,
            page=page,
            per_page=per_page,
            pages=pages,
            has_prev=has_prev,
            has_next=has_next,
            prev_url=_build_url_with_page(page - 1) if has_prev else None,
            next_url=_build_url_with_page(page + 1) if has_next else None,
        )

    except RuntimeError as e:
        return (
            f"<h2>500</h2><pre>{str(e)}</pre>",
            500,
            {"Content-Type": "text/html; charset=utf-8"},
        )

    finally:
        try:
            conn.close()
        except Exception:
            pass


@meus_atendimentos_bp.route("/api/list", methods=["GET"])
def api_list():
    conn = conectar_db()

    try:
        ensure_atendimentos_schema(conn)

        profissional_uid = _resolve_logged_profissional_id(conn)

        if not profissional_uid:
            return jsonify({"ok": False, "error": "not_logged_profissional"}), 401

        q_nome = (request.args.get("q") or "").strip()
        cidade = (request.args.get("cidade") or "").strip()
        cid = (request.args.get("cid") or "").strip()

        data_ini = _norm_date_iso(request.args.get("data_ini") or "")
        data_fim = _norm_date_iso(request.args.get("data_fim") or "")
        idade_min = _int_or_none(request.args.get("idade_min"))
        idade_max = _int_or_none(request.args.get("idade_max"))

        page = _int_or_none(request.args.get("page")) or 1
        per_page = _int_or_none(request.args.get("per_page")) or 20

        if not data_ini and not data_fim:
            data_ini = _month_start_iso()
            data_fim = _today_iso()

        total, rows = _query_meus_atendimentos_paginado(
            conn=conn,
            profissional_uid=profissional_uid,
            q_nome=q_nome,
            data_ini=data_ini,
            data_fim=data_fim,
            idade_min=idade_min,
            idade_max=idade_max,
            cidade=cidade,
            cid=cid,
            page=page,
            per_page=per_page,
        )

        pages = max(1, (total + per_page - 1) // per_page)

        items = []

        for r in rows:
            items.append({
                "id": r.get("id"),
                "paciente": r.get("paciente") or "",
                "procedimento": r.get("procedimento") or "",
                "data": r.get("data") or "",
                "idade": r.get("idade"),
                "evolucao_preview": r.get("evolucao_preview") or "",
                "evolucao": r.get("evolucao") or "",
            })

        return jsonify({
            "ok": True,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
            "items": items,
        })

    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    finally:
        try:
            conn.close()
        except Exception:
            pass