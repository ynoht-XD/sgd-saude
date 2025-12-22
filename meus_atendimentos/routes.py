from __future__ import annotations

import sqlite3
from datetime import date, datetime
from typing import Any, List, Optional

from flask import render_template, request, session, jsonify, url_for

from . import meus_atendimentos_bp
from db import conectar_db


# ============================================================
# SCHEMA · ATENDIMENTOS (CRÍTICO NO RENDER)
# ============================================================

def has_table(conn, table_name: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table_name,),
    )
    return cur.fetchone() is not None


def _table_columns(conn, table: str) -> set[str]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return {r[1] for r in cur.fetchall()}


def ensure_column(conn: sqlite3.Connection, table: str, col: str, ddl_type: str):
    """
    Adiciona coluna se não existir. Idempotente.
    """
    if not has_table(conn, table):
        return
    cols = _table_columns(conn, table)
    if col in cols:
        return
    cur = conn.cursor()
    cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl_type}")
    conn.commit()


def ensure_atendimentos_schema(conn: sqlite3.Connection):
    """
    Garante tabelas mínimas para o módulo 'Meus atendimentos' não quebrar no Render.
    Se tu já tiver schema mais completo em outro lugar, isso aqui não atrapalha:
    - CREATE IF NOT EXISTS
    - ALTER TABLE só adiciona o que faltar
    """
    cur = conn.cursor()

    # Tabela principal (mínimo pra listagem funcionar)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS atendimentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            -- profissional (quem atendeu)
            profissional_id INTEGER,
            usuario_id INTEGER,

            -- paciente
            paciente_id INTEGER,
            cidadao_id INTEGER,
            paciente_nome TEXT,
            nome_paciente TEXT,
            paciente TEXT,
            nome TEXT,

            -- data
            data_atendimento TEXT,
            data TEXT,
            dt_atendimento TEXT,
            criado_em TEXT,
            created_at TEXT,

            -- conteúdo
            evolucao TEXT,
            evolucao_texto TEXT,

            -- extras úteis pra filtros (se existir)
            cidade TEXT,
            municipio TEXT,
            cid TEXT,
            cid_codigo TEXT
        )
    """)

    # Procedimentos (opcional, mas tua query já tenta juntar)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS atendimento_procedimentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            atendimento_id INTEGER NOT NULL,
            procedimento TEXT,
            procedimento_nome TEXT,
            descricao TEXT,
            FOREIGN KEY(atendimento_id) REFERENCES atendimentos(id)
        )
    """)

    # índices (não dói e ajuda)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_atend_prof ON atendimentos (profissional_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_atend_data ON atendimentos (data_atendimento)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_atend_usuario ON atendimentos (usuario_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ap_atend ON atendimento_procedimentos (atendimento_id)")

    conn.commit()

    # Se tua base veio de outro ambiente com colunas faltando, garante o mínimo:
    ensure_column(conn, "atendimentos", "profissional_id", "INTEGER")
    ensure_column(conn, "atendimentos", "usuario_id", "INTEGER")
    ensure_column(conn, "atendimentos", "paciente_id", "INTEGER")
    ensure_column(conn, "atendimentos", "cidadao_id", "INTEGER")
    ensure_column(conn, "atendimentos", "data_atendimento", "TEXT")
    ensure_column(conn, "atendimentos", "criado_em", "TEXT")
    ensure_column(conn, "atendimentos", "evolucao", "TEXT")
    ensure_column(conn, "atendimentos", "cidade", "TEXT")
    ensure_column(conn, "atendimentos", "municipio", "TEXT")
    ensure_column(conn, "atendimentos", "cid", "TEXT")


# ============================================================
# HELPERS DE INTROSPECÇÃO
# ============================================================

def has_column(conn, table_name: str, column_name: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute(f"PRAGMA table_info({table_name})")
        cols = [r[1] for r in cur.fetchall()]
        return column_name in cols
    except Exception:
        return False


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
    """Aceita YYYY-MM-DD ou DD/MM/YYYY e retorna YYYY-MM-DD."""
    if not s:
        return None
    s = s.strip()
    if not s:
        return None

    try:
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            datetime.strptime(s, "%Y-%m-%d")
            return s
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
        if s == "":
            return None
        return int(s)
    except Exception:
        return None


# ============================================================
# LOGADO -> PROFISSIONAL (usuarios.id)
# ============================================================

def _resolve_logged_profissional_id(conn) -> int | None:
    # 1) tenta id direto na session
    for key in ("usuario_id", "user_id", "id"):
        val = session.get(key)
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                pass

    login_like = session.get("usuario_logado") or session.get("login") or session.get("username")
    if not login_like:
        return None

    if not has_table(conn, "usuarios"):
        return None

    cols = _table_columns(conn, "usuarios")

    parts = []
    if "login" in cols: parts.append("login")
    if "nome" in cols:  parts.append("nome")
    if "email" in cols: parts.append("email")

    if not parts:
        return None

    expr = "COALESCE(" + ", ".join(parts + ["''"]) + ")"

    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT id
          FROM usuarios
         WHERE TRIM(LOWER({expr})) = TRIM(LOWER(?))
         LIMIT 1
        """,
        (login_like,),
    )
    row = cur.fetchone()
    return int(row[0]) if row else None


def _build_url_with_page(page: int) -> str:
    args = dict(request.args)
    args["page"] = str(page)
    return url_for("meus_atendimentos.index", **args)


# ============================================================
# QUERY PRINCIPAL (PAGINADA + COUNT)
# ============================================================

def _query_meus_atendimentos_paginado(
    conn: sqlite3.Connection,
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
) -> tuple[int, list[sqlite3.Row]]:
    """
    Retorna: (total_count, rows_paginated)
    """
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # ✅ garante que exista (no Render pode vir vazio)
    ensure_atendimentos_schema(conn)

    a_cols = _table_columns(conn, "atendimentos")

    col_prof = _first_existing(a_cols, ["profissional_id", "usuario_id", "user_id"])
    col_pac_id = _first_existing(a_cols, ["paciente_id", "cidadao_id"])
    col_pac_nome = _first_existing(a_cols, ["nome", "paciente", "paciente_nome", "nome_paciente"])
    col_data = _first_existing(a_cols, ["data_atendimento", "data", "dt_atendimento", "criado_em", "created_at"])
    col_evol = _first_existing(a_cols, ["evolucao", "evolução", "evolucao_texto", "evolucao_md", "evolucao_html"])

    if not col_prof:
        raise RuntimeError("Tabela atendimentos sem coluna profissional_id/usuario_id/user_id.")
    if not col_data:
        raise RuntimeError("Tabela atendimentos sem coluna de data (data_atendimento/data/etc).")

    paciente_expr = f"TRIM(COALESCE(a.{col_pac_nome}, ''))" if col_pac_nome else "''"
    data_expr = f"date(a.{col_data})"
    evol_expr = f"COALESCE(a.{col_evol}, '')" if col_evol else "''"

    col_a_cidade = _first_existing(a_cols, ["cidade", "municipio", "município", "cidade_nome"])
    col_a_cid = _first_existing(a_cols, ["cid", "cid_codigo", "cid_principal", "cid10", "cid_primario"])

    cidade_expr = f"TRIM(LOWER(COALESCE(a.{col_a_cidade},'')))" if col_a_cidade else "''"
    cid_expr = f"TRIM(UPPER(COALESCE(a.{col_a_cid},'')))" if col_a_cid else "''"

    join_proc = ""
    proc_expr = "''"
    use_group = False
    if has_table(conn, "atendimento_procedimentos"):
        ap_cols = _table_columns(conn, "atendimento_procedimentos")
        col_ap_atend = _first_existing(ap_cols, ["atendimento_id"])
        col_ap_proc = _first_existing(ap_cols, ["procedimento", "procedimento_nome", "descricao"])
        if col_ap_atend and col_ap_proc:
            join_proc = " LEFT JOIN atendimento_procedimentos ap ON ap.atendimento_id = a.id "
            proc_expr = f"COALESCE(GROUP_CONCAT(TRIM(COALESCE(ap.{col_ap_proc},'')), ' • '), '')"
            use_group = True

    join_pac = ""
    idade_expr = "NULL"

    if col_pac_id and has_table(conn, "pacientes"):
        p_cols = _table_columns(conn, "pacientes")
        col_p_id = _first_existing(p_cols, ["id", "cidadao_id"])
        col_p_nasc = _first_existing(p_cols, ["nascimento", "data_nascimento", "dt_nascimento"])
        col_p_nome = _first_existing(p_cols, ["nome", "nome_completo"])

        col_p_cidade = _first_existing(p_cols, ["municipio", "município", "cidade", "cidade_nome"])
        col_p_cid = _first_existing(p_cols, ["cid", "cid_codigo", "cid_principal", "cid10", "cid_primario"])

        if col_p_id:
            join_pac = f" LEFT JOIN pacientes p ON p.{col_p_id} = a.{col_pac_id} "

        if col_p_id and col_p_nasc:
            idade_expr = f"CAST((julianday('now') - julianday(p.{col_p_nasc})) / 365.25 AS INT)"

        if col_p_nome and col_pac_nome:
            paciente_expr = f"TRIM(COALESCE(NULLIF(a.{col_pac_nome},''), p.{col_p_nome}, ''))"
        elif col_p_nome and not col_pac_nome:
            paciente_expr = f"TRIM(COALESCE(p.{col_p_nome}, ''))"

        if (not col_a_cidade) and col_p_cidade:
            cidade_expr = f"TRIM(LOWER(COALESCE(p.{col_p_cidade},'')))"
        if (not col_a_cid) and col_p_cid:
            cid_expr = f"TRIM(UPPER(COALESCE(p.{col_p_cid},'')))"

    where: List[str] = [f"a.{col_prof} = ?"]
    params: List[Any] = [int(profissional_uid)]

    if q_nome:
        where.append(f"{paciente_expr} LIKE ?")
        params.append(f"%{q_nome}%")

    if data_ini:
        where.append(f"{data_expr} >= ?")
        params.append(data_ini)

    if data_fim:
        where.append(f"{data_expr} <= ?")
        params.append(data_fim)

    if idade_expr != "NULL":
        if idade_min is not None:
            where.append(f"({idade_expr}) >= ?")
            params.append(idade_min)
        if idade_max is not None:
            where.append(f"({idade_expr}) <= ?")
            params.append(idade_max)

    if cidade and cidade_expr != "''":
        where.append(f"{cidade_expr} LIKE ?")
        params.append(f"%{cidade.strip().lower()}%")

    if cid and cid_expr != "''":
        where.append(f"{cid_expr} LIKE ?")
        params.append(f"%{cid.strip().upper()}%")

    where_sql = " AND ".join(where)

    count_sql = f"""
        SELECT COUNT(DISTINCT a.id) AS total
          FROM atendimentos a
          {join_pac}
          {join_proc}
         WHERE {where_sql}
    """
    cur.execute(count_sql, params)
    total = int(cur.fetchone()["total"] or 0)

    page = max(1, int(page or 1))
    per_page = max(1, min(200, int(per_page or 20)))
    offset = (page - 1) * per_page

    group_by = "GROUP BY a.id" if use_group else ""

    list_sql = f"""
        SELECT
            a.id                               AS id,
            {paciente_expr}                    AS paciente,
            {proc_expr}                        AS procedimento,
            {data_expr}                        AS data,
            {evol_expr}                        AS evolucao,
            substr({evol_expr}, 1, 260)        AS evolucao_preview,
            {idade_expr}                       AS idade
        FROM atendimentos a
        {join_pac}
        {join_proc}
        WHERE {where_sql}
        {group_by}
        ORDER BY {data_expr} DESC, a.id DESC
        LIMIT ? OFFSET ?
    """
    cur.execute(list_sql, params + [per_page, offset])
    rows = cur.fetchall()

    return total, rows


# ============================================================
# ROTAS
# ============================================================

@meus_atendimentos_bp.route("", methods=["GET"])
@meus_atendimentos_bp.route("/", methods=["GET"])
def index():
    conn = conectar_db()
    try:
        # ✅ garante schema no Render
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
                "id": r["id"],
                "paciente": r["paciente"],
                "procedimento": r["procedimento"],
                "data": r["data"],
                "idade": r["idade"],
                "evolucao_preview": r["evolucao_preview"],
                "evolucao": r["evolucao"],
            })

        return jsonify({
            "ok": True,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
            "items": items
        })

    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass
