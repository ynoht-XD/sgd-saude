# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import re
from datetime import date
from typing import Any, Dict, List, Sequence, Tuple

from flask import request, jsonify, render_template, send_file, session

from db import conectar_db
from . import registros_bp

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth


# =============================================================================
# HELPERS GERAIS · POSTGRES
# =============================================================================

def _safe_str(v) -> str:
    return ("" if v is None else str(v)).strip()


def _only_digits(s: str | None) -> str:
    return re.sub(r"\D+", "", s or "")


def _norm_date_param(s: str) -> str:
    s = _safe_str(s)
    if not s:
        return ""
    if re.match(r"^\d{2}/\d{2}/\d{4}$", s):
        d, m, y = s.split("/")
        return f"{y}-{m}-{d}"
    return s[:10]


def _valid_ident(name: str) -> bool:
    return bool(re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name or ""))


def _row_get(row: Any, key: str, idx: int | None = None, default: Any = None) -> Any:
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


def _rows_to_dicts(cur, rows) -> list[dict]:
    names = [d[0] for d in cur.description] if cur.description else []
    out = []
    for r in rows or []:
        if isinstance(r, dict):
            out.append(dict(r))
        else:
            out.append({names[i]: r[i] for i in range(min(len(names), len(r)))})
    return out


def _get_columns(conn, table: str) -> List[str]:
    if not _valid_ident(table):
        return []
    cur = conn.cursor()
    cur.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = %s
         ORDER BY ordinal_position
        """,
        (table,),
    )
    return [_row_get(r, "column_name", 0, "") for r in cur.fetchall() or []]


def _first_existing(cols: Sequence[str], opts: Sequence[str]) -> str | None:
    for c in opts:
        if c in cols:
            return c
    return None


def _has_table(conn, name: str) -> bool:
    if not _valid_ident(name):
        return False
    cur = conn.cursor()
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
              FROM information_schema.tables
             WHERE table_schema = 'public'
               AND table_name = %s
        )
        """,
        (name,),
    )
    return bool(_row_get(cur.fetchone(), "exists", 0, False))


def _has_column(conn, table: str, col: str) -> bool:
    if not _valid_ident(table) or not _valid_ident(col):
        return False
    cur = conn.cursor()
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = %s
               AND column_name = %s
        )
        """,
        (table, col),
    )
    return bool(_row_get(cur.fetchone(), "exists", 0, False))


def _sql_date_expr(col_sql: str) -> str:
    """
    Postgres:
    aceita campo DATE/TIMESTAMP/TEXT em ISO ou DD/MM/YYYY.
    Retorna expressão DATE.
    """
    return f"""
    (
      CASE
        WHEN {col_sql} IS NULL THEN NULL
        WHEN {col_sql}::text ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}' THEN ({col_sql})::date
        WHEN {col_sql}::text ~ '^\\d{{2}}/\\d{{2}}/\\d{{4}}' THEN TO_DATE(SUBSTRING({col_sql}::text FROM 1 FOR 10), 'DD/MM/YYYY')
        ELSE NULL
      END
    )
    """.strip()


def _pick_att_col(cols: list[str] | set[str], *names: str) -> str | None:
    for n in names:
        if n in cols:
            return n
    return None


# =============================================================================
# USUÁRIO LOGADO / PERMISSÃO EVOLUÇÃO OCULTA
# =============================================================================

def _resolve_logged_user(conn) -> dict:
    """
    Retorna id, nome, cbo do usuário logado.
    Tenta session por id primeiro.
    """
    uid = None
    for key in ("usuario_id", "user_id", "id"):
        val = session.get(key)
        if val:
            try:
                uid = int(val)
                break
            except Exception:
                pass

    login_like = (
        session.get("usuario_logado")
        or session.get("login")
        or session.get("username")
        or session.get("email")
    )

    if not _has_table(conn, "usuarios"):
        return {"id": uid, "nome": "", "cbo": ""}

    cols = _get_columns(conn, "usuarios")
    cur = conn.cursor()

    nome_expr = "COALESCE(nome, '')" if "nome" in cols else "''"
    cbo_expr = "COALESCE(cbo, '')" if "cbo" in cols else "''"

    if uid:
        cur.execute(
            f"""
            SELECT id, {nome_expr} AS nome, {cbo_expr} AS cbo
              FROM usuarios
             WHERE id = %s
             LIMIT 1
            """,
            (uid,),
        )
        r = cur.fetchone()
        if r:
            return {
                "id": _row_get(r, "id", 0),
                "nome": _row_get(r, "nome", 1, "") or "",
                "cbo": _only_digits(_row_get(r, "cbo", 2, "") or ""),
            }

    if login_like:
        busca_cols = [c for c in ("login", "nome", "email") if c in cols]
        if busca_cols:
            conds = [f"LOWER(TRIM(COALESCE({c}, ''))) = LOWER(TRIM(%s))" for c in busca_cols]
            params = [login_like] * len(busca_cols)
            cur.execute(
                f"""
                SELECT id, {nome_expr} AS nome, {cbo_expr} AS cbo
                  FROM usuarios
                 WHERE {" OR ".join(conds)}
                 LIMIT 1
                """,
                params,
            )
            r = cur.fetchone()
            if r:
                return {
                    "id": _row_get(r, "id", 0),
                    "nome": _row_get(r, "nome", 1, "") or "",
                    "cbo": _only_digits(_row_get(r, "cbo", 2, "") or ""),
                }

    return {"id": uid, "nome": "", "cbo": ""}


def _ensure_evolucoes_ocultas_schema(conn) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS atendimento_evolucoes_ocultas (
            id SERIAL PRIMARY KEY,
            atendimento_id INTEGER NOT NULL REFERENCES atendimentos(id) ON DELETE CASCADE,
            paciente_id INTEGER,
            profissional_id INTEGER,
            profissional_nome TEXT,
            profissional_cbo TEXT,
            evolucao_oculta TEXT NOT NULL,
            visibilidade TEXT NOT NULL DEFAULT 'somente_eu',
            cbos_autorizados TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_evo_oculta_atendimento
            ON atendimento_evolucoes_ocultas (atendimento_id)
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_evo_oculta_paciente
            ON atendimento_evolucoes_ocultas (paciente_id)
        """
    )
    conn.commit()


def _hidden_evo_lateral_sql() -> str:
    """
    Usa 2 parâmetros:
    1. profissional_id logado
    2. cbo logado
    """
    return """
    LEFT JOIN LATERAL (
        SELECT
            COUNT(*) AS evo_oculta_total,
            COUNT(*) FILTER (
                WHERE
                    (
                        eo.visibilidade = 'somente_eu'
                        AND eo.profissional_id = %s
                    )
                    OR
                    (
                        eo.visibilidade = 'cbos'
                        AND %s <> ''
                        AND POSITION(
                            ',' || %s || ','
                            IN ',' || REGEXP_REPLACE(COALESCE(eo.cbos_autorizados, ''), '\\s+', '', 'g') || ','
                        ) > 0
                    )
            ) AS evo_oculta_visivel,
            STRING_AGG(
                CASE
                    WHEN (
                        eo.visibilidade = 'somente_eu'
                        AND eo.profissional_id = %s
                    )
                    OR
                    (
                        eo.visibilidade = 'cbos'
                        AND %s <> ''
                        AND POSITION(
                            ',' || %s || ','
                            IN ',' || REGEXP_REPLACE(COALESCE(eo.cbos_autorizados, ''), '\\s+', '', 'g') || ','
                        ) > 0
                    )
                    THEN eo.evolucao_oculta
                    ELSE NULL
                END,
                E'\\n---\\n'
                ORDER BY eo.id
            ) AS evolucoes_ocultas_visiveis
        FROM atendimento_evolucoes_ocultas eo
        WHERE eo.atendimento_id = a.id
    ) eoh ON TRUE
    """


def _hidden_evo_params(user: dict) -> list[Any]:
    uid = user.get("id") or 0
    cbo = _only_digits(user.get("cbo") or "")
    return [uid, cbo, cbo, uid, cbo, cbo]


# =============================================================================
# QUERY COMPARTILHADA
# =============================================================================

def _montar_query_atendimentos(
    conn,
    q: str,
    prof: str,
    data_ini: str,
    data_fim: str,
    status: str,
    sexo: str,
    cid: str,
    cidade: str,
    limit: int | None,
    incluir_evolucao_oculta: bool = True,
) -> Tuple[str, List[Any]]:
    table = "atendimentos"
    cols = _get_columns(conn, table)

    has_proc = _has_table(conn, "atendimento_procedimentos")
    proc_cols = _get_columns(conn, "atendimento_procedimentos") if has_proc else []

    user = _resolve_logged_user(conn)

    nome_cols_raw = [c for c in ["paciente_nome", "nome_paciente", "nome"] if c in cols]
    cpf_cols_raw = [c for c in ["cpf", "paciente_cpf"] if c in cols]
    cns_cols_raw = [c for c in ["cns", "paciente_cns", "cartao_sus"] if c in cols]

    prof_id_col_raw = _first_existing(cols, ["profissional_id", "prof_id", "id_profissional"])
    prof_nome_col_raw = _first_existing(cols, ["profissional_nome", "nome_profissional", "profissional", "usuario_nome", "nome_usuario"])

    data_col_raw = _first_existing(cols, ["data_atendimento", "data", "data_iso", "created_at"])
    status_col_raw = _first_existing(cols, ["status", "situacao", "comparecimento"])
    sexo_col_raw = _first_existing(cols, ["sexo", "sex"])
    cid_col_raw = _first_existing(cols, ["cid", "cid_principal", "cid10"])
    cidade_col_raw = _first_existing(cols, ["cidade", "municipio", "cidade_paciente", "municipio_paciente"])

    nome_cols = [f"a.{c}" for c in nome_cols_raw]
    cpf_cols = [f"a.{c}" for c in cpf_cols_raw]
    cns_cols = [f"a.{c}" for c in cns_cols_raw]

    prof_id_col = f"a.{prof_id_col_raw}" if prof_id_col_raw else None
    prof_nome_col = f"a.{prof_nome_col_raw}" if prof_nome_col_raw else None
    data_col = f"a.{data_col_raw}" if data_col_raw else None
    status_col = f"a.{status_col_raw}" if status_col_raw else None
    sexo_col = f"a.{sexo_col_raw}" if sexo_col_raw else None
    cid_col = f"a.{cid_col_raw}" if cid_col_raw else None
    cidade_col = f"a.{cidade_col_raw}" if cidade_col_raw else None

    joins: List[str] = []
    params: List[Any] = []

    if has_proc:
        joins.append("LEFT JOIN atendimento_procedimentos ap ON ap.atendimento_id = a.id")

    if incluir_evolucao_oculta and _has_table(conn, "atendimento_evolucoes_ocultas"):
        joins.append(_hidden_evo_lateral_sql())
        params.extend(_hidden_evo_params(user))

    where_parts: List[str] = []

    if q:
        like = f"%{q}%"
        sub: List[str] = []

        for c in nome_cols:
            sub.append(f"{c} ILIKE %s")
            params.append(like)

        for c in cpf_cols:
            sub.append(f"{c}::text ILIKE %s")
            params.append(like)

        for c in cns_cols:
            sub.append(f"{c}::text ILIKE %s")
            params.append(like)

        if has_proc:
            if "procedimento" in proc_cols:
                sub.append("ap.procedimento ILIKE %s")
                params.append(like)
            if "codigo_sigtap" in proc_cols:
                sub.append("ap.codigo_sigtap ILIKE %s")
                params.append(like)

        if incluir_evolucao_oculta and _has_table(conn, "atendimento_evolucoes_ocultas"):
            sub.append("COALESCE(eoh.evolucoes_ocultas_visiveis, '') ILIKE %s")
            params.append(like)

        if sub:
            where_parts.append("(" + " OR ".join(sub) + ")")

    if prof:
        if prof.isdigit() and prof_id_col:
            where_parts.append(f"{prof_id_col} = %s")
            params.append(int(prof))
        elif prof_nome_col:
            where_parts.append(f"{prof_nome_col} ILIKE %s")
            params.append(f"%{prof}%")

    data_ini = _norm_date_param(data_ini)
    data_fim = _norm_date_param(data_fim)

    if data_col and (data_ini or data_fim):
        d_expr = _sql_date_expr(data_col)
        if data_ini and data_fim:
            where_parts.append(f"{d_expr} BETWEEN %s::date AND %s::date")
            params.extend([data_ini, data_fim])
        elif data_ini:
            where_parts.append(f"{d_expr} = %s::date")
            params.append(data_ini)
        else:
            where_parts.append(f"{d_expr} = %s::date")
            params.append(data_fim)

    if status and status_col:
        where_parts.append(f"{status_col} = %s")
        params.append(status)

    if sexo and sexo_col:
        where_parts.append(f"{sexo_col} = %s")
        params.append(sexo)

    if cid and cid_col:
        where_parts.append(f"{cid_col} ILIKE %s")
        params.append(f"%{cid}%")

    if cidade and cidade_col:
        where_parts.append(f"{cidade_col} ILIKE %s")
        params.append(f"%{cidade}%")

    select_parts = [
        "a.*",
        *(["ap.procedimento AS ap_procedimento",
           "COALESCE(ap.codigo_sigtap, '') AS ap_codigo_sigtap"] if has_proc else []),
    ]

    if incluir_evolucao_oculta and _has_table(conn, "atendimento_evolucoes_ocultas"):
        select_parts.extend([
            "COALESCE(eoh.evo_oculta_total, 0) AS evo_oculta_total",
            "COALESCE(eoh.evo_oculta_visivel, 0) AS evo_oculta_visivel",
            """
            CASE
                WHEN COALESCE(eoh.evo_oculta_total, 0) = 0 THEN 'sem_evolucao_oculta'
                WHEN COALESCE(eoh.evo_oculta_visivel, 0) > 0 THEN 'visivel'
                ELSE 'restrita'
            END AS evo_oculta_situacao
            """,
            "COALESCE(eoh.evolucoes_ocultas_visiveis, '') AS evolucoes_ocultas_visiveis",
        ])
    else:
        select_parts.extend([
            "0 AS evo_oculta_total",
            "0 AS evo_oculta_visivel",
            "'sem_evolucao_oculta' AS evo_oculta_situacao",
            "'' AS evolucoes_ocultas_visiveis",
        ])

    sql = f"SELECT {', '.join(select_parts)}\nFROM {table} a"

    if joins:
        sql += "\n" + "\n".join(joins)

    if where_parts:
        sql += "\nWHERE " + " AND ".join(where_parts)

    order_parts: List[str] = []
    if data_col:
        order_parts.append(f"{_sql_date_expr(data_col)} DESC NULLS LAST")
    if "id" in cols:
        order_parts.append("a.id DESC")
    if has_proc:
        order_parts.append("ap.id ASC")

    if order_parts:
        sql += "\nORDER BY " + ", ".join(order_parts)

    if limit and limit > 0:
        sql += "\nLIMIT %s"
        params.append(limit)

    return sql, params


# =============================================================================
# PÁGINA
# =============================================================================

@registros_bp.get("/")
def pagina_registros():
    return render_template("registros.html")


# =============================================================================
# API LISTAR
# =============================================================================

@registros_bp.get("/api/list")
def api_listar_atendimentos():
    q = (request.args.get("q") or "").strip()
    prof = (request.args.get("prof") or "").strip()
    data_ini = (request.args.get("data_ini") or "").strip()
    data_fim = (request.args.get("data_fim") or "").strip()
    status = (request.args.get("status") or "").strip()
    sexo = (request.args.get("sexo") or "").strip()
    cid = (request.args.get("cid") or "").strip()
    cidade = (request.args.get("cidade") or "").strip()

    try:
        limit = int(request.args.get("limit", 500))
    except ValueError:
        limit = 500

    conn = conectar_db()
    try:
        _ensure_evolucoes_ocultas_schema(conn)

        cur = conn.cursor()
        sql, params = _montar_query_atendimentos(
            conn,
            q=q,
            prof=prof,
            data_ini=data_ini,
            data_fim=data_fim,
            status=status,
            sexo=sexo,
            cid=cid,
            cidade=cidade,
            limit=limit,
        )

        cur.execute(sql, params)
        data = _rows_to_dicts(cur, cur.fetchall())

        pac_cache: dict = {}
        ag_cache: dict = {}

        for r in data:
            _enrich_with_paciente(conn, r, pac_cache)
            _enrich_with_agendamento(conn, r, ag_cache)

            r["pac__nome"] = r.get("pac__nome") or r.get("paciente_nome") or r.get("nome") or ""
            r["pac__cpf"] = r.get("pac__cpf") or r.get("paciente_cpf") or r.get("cpf") or ""
            r["pac__cns"] = r.get("pac__cns") or r.get("paciente_cns") or r.get("cns") or r.get("cartao_sus") or ""
            r["pac__nascimento"] = r.get("pac__nascimento") or r.get("paciente_nascimento") or r.get("nascimento") or r.get("data_nascimento") or ""
            r["pac__status"] = r.get("pac__status") or r.get("status") or ""
            r["pac__sexo"] = r.get("pac__sexo") or r.get("sexo") or ""
            r["pac__cid"] = r.get("pac__cid") or r.get("cid") or ""
            r["pac__municipio"] = r.get("pac__municipio") or r.get("cidade") or r.get("municipio") or ""

        return jsonify(data)

    finally:
        conn.close()


# =============================================================================
# ENRIQUECIMENTOS
# =============================================================================

def _enrich_with_paciente(conn, base_row: dict, cache: dict) -> None:
    if not _has_table(conn, "pacientes"):
        return

    pcols = _get_columns(conn, "pacientes")
    col_id = _pick_att_col(pcols, "id", "paciente_id")
    col_nome = _pick_att_col(pcols, "nome", "paciente_nome", "nome_paciente")
    col_cpf = _pick_att_col(pcols, "cpf", "paciente_cpf", "cpf_digits", "cpf_cidadao")
    col_cns = _pick_att_col(pcols, "cns", "paciente_cns", "cns_digits", "cartao_sus")
    col_nasc = _pick_att_col(pcols, "nascimento", "data_nascimento", "dt_nasc", "paciente_nascimento")
    col_pront = _pick_att_col(pcols, "prontuario", "prontuario_num")
    col_idade = _pick_att_col(pcols, "idade")

    extras = {
        "sexo": _pick_att_col(pcols, "sexo", "sex"),
        "telefone": _pick_att_col(pcols, "telefone", "telefone1", "paciente_telefone1", "celular"),
        "cep": _pick_att_col(pcols, "cep", "paciente_cep"),
        "logradouro": _pick_att_col(pcols, "logradouro", "rua", "paciente_logradouro"),
        "numero": _pick_att_col(pcols, "numero", "numero_casa", "paciente_numero_casa"),
        "bairro": _pick_att_col(pcols, "bairro", "paciente_bairro"),
        "municipio": _pick_att_col(pcols, "municipio", "cidade", "paciente_municipio", "paciente_cidade"),
        "uf": _pick_att_col(pcols, "uf"),
        "mod": _pick_att_col(pcols, "mod", "modalidade"),
        "status": _pick_att_col(pcols, "status", "situacao"),
        "cid": _pick_att_col(pcols, "cid", "cid_principal", "cid10"),
        "cid2": _pick_att_col(pcols, "cid2"),
        "mae": _pick_att_col(pcols, "mae", "nome_mae"),
        "pai": _pick_att_col(pcols, "pai", "nome_pai"),
        "responsavel": _pick_att_col(pcols, "responsavel"),
        "alergias": _pick_att_col(pcols, "alergias"),
        "aviso": _pick_att_col(pcols, "aviso"),
        "comorbidades_json": _pick_att_col(pcols, "comorbidades_json"),
        "raca": _pick_att_col(pcols, "raca"),
        "estado_civil": _pick_att_col(pcols, "estado_civil"),
        "complemento": _pick_att_col(pcols, "complemento"),
    }

    if not col_id:
        return

    pid = base_row.get("paciente_id") or base_row.get("pacienteId") or ""
    cpf = base_row.get("paciente_cpf") or base_row.get("cpf") or ""
    cns = base_row.get("paciente_cns") or base_row.get("cns") or base_row.get("cartao_sus") or ""
    nome = base_row.get("paciente_nome") or base_row.get("nome_paciente") or base_row.get("nome") or ""
    nasc = base_row.get("paciente_nascimento") or base_row.get("nascimento") or base_row.get("data_nascimento") or ""

    cpf_d = _only_digits(str(cpf))
    cns_d = _only_digits(str(cns))
    nasc_iso = _norm_date_param(str(nasc))

    if str(pid).strip():
        cache_key = f"pid:{pid}"
    elif cpf_d:
        cache_key = f"cpf:{cpf_d}"
    elif cns_d:
        cache_key = f"cns:{cns_d}"
    elif str(nome).strip() and nasc_iso:
        cache_key = f"nn:{str(nome).strip().lower()}|{nasc_iso}"
    else:
        return

    if cache_key in cache:
        pac = cache[cache_key]
    else:
        cur = conn.cursor()
        fields = [col_id]

        for c in [col_nome, col_cpf, col_cns, col_nasc, col_pront, col_idade, *extras.values()]:
            if c and c not in fields:
                fields.append(c)

        pac = None

        if str(pid).strip() and str(pid).strip().isdigit():
            cur.execute(
                f"SELECT {', '.join(fields)} FROM pacientes WHERE {col_id} = %s LIMIT 1",
                (int(pid),),
            )
            pac = cur.fetchone()

        if pac is None and col_cpf and cpf_d:
            cur.execute(
                f"""
                SELECT {', '.join(fields)}
                  FROM pacientes
                 WHERE REGEXP_REPLACE(COALESCE({col_cpf}::text, ''), '\\D', '', 'g') = %s
                 LIMIT 1
                """,
                (cpf_d,),
            )
            pac = cur.fetchone()

        if pac is None and col_cns and cns_d:
            cur.execute(
                f"""
                SELECT {', '.join(fields)}
                  FROM pacientes
                 WHERE REGEXP_REPLACE(COALESCE({col_cns}::text, ''), '\\D', '', 'g') = %s
                 LIMIT 1
                """,
                (cns_d,),
            )
            pac = cur.fetchone()

        if pac is None and col_nome and col_nasc and str(nome).strip() and nasc_iso:
            cur.execute(
                f"""
                SELECT {', '.join(fields)}
                  FROM pacientes
                 WHERE TRIM(LOWER({col_nome})) = TRIM(LOWER(%s))
                   AND {_sql_date_expr(col_nasc)} = %s::date
                 LIMIT 1
                """,
                (str(nome).strip(), nasc_iso),
            )
            pac = cur.fetchone()

        pac_dict = {}
        if pac is not None:
            for i, fname in enumerate(fields):
                pac_dict[fname] = _row_get(pac, fname, i, "")

        cache[cache_key] = pac_dict
        pac = pac_dict

    if not isinstance(pac, dict) or not pac:
        return

    def put(out_key: str, col: str | None):
        if col and col in pac:
            base_row[out_key] = pac.get(col, "")

    put("pac__nome", col_nome)
    put("pac__cpf", col_cpf)
    put("pac__cns", col_cns)
    put("pac__nascimento", col_nasc)
    put("pac__prontuario", col_pront)
    put("pac__idade", col_idade)

    for key, col in extras.items():
        put(f"pac__{key}", col)


def _enrich_with_agendamento(conn, base_row: dict, cache: dict) -> None:
    if not _has_table(conn, "agendamentos"):
        return

    acols = _get_columns(conn, "agendamentos")
    col_pid = _pick_att_col(acols, "paciente_id", "cidadao_id")
    col_pnome = _pick_att_col(acols, "paciente", "paciente_nome", "nome_paciente", "nome")
    col_ini = _pick_att_col(acols, "inicio", "datahora", "data_hora", "data_inicio")
    col_prof = _pick_att_col(acols, "profissional", "profissional_nome", "nome_profissional")
    col_profid = _pick_att_col(acols, "profissional_id", "prof_id")
    col_profcbo = _pick_att_col(acols, "profissional_cbo", "cbo")

    if not col_ini:
        return

    dt_raw = base_row.get("data_atendimento") or base_row.get("data") or base_row.get("data_iso") or base_row.get("created_at") or ""
    dt_iso = _norm_date_param(str(dt_raw)[:10])
    if not dt_iso:
        return

    pid = base_row.get("paciente_id") or ""
    nome = base_row.get("paciente_nome") or base_row.get("nome_paciente") or base_row.get("nome") or ""

    if str(pid).strip():
        key = f"ag:{pid}|{dt_iso}"
    elif str(nome).strip():
        key = f"ag:n:{str(nome).strip().lower()}|{dt_iso}"
    else:
        return

    if key in cache:
        ag = cache[key]
    else:
        cur = conn.cursor()
        ag = None

        if col_pid and str(pid).strip() and str(pid).strip().isdigit():
            cur.execute(
                f"""
                SELECT *
                  FROM agendamentos
                 WHERE {_sql_date_expr(col_ini)} = %s::date
                   AND {col_pid} = %s
                 ORDER BY {col_ini} ASC
                 LIMIT 1
                """,
                (dt_iso, int(pid)),
            )
            ag = cur.fetchone()

        if ag is None and col_pnome and str(nome).strip():
            cur.execute(
                f"""
                SELECT *
                  FROM agendamentos
                 WHERE {_sql_date_expr(col_ini)} = %s::date
                   AND TRIM(LOWER({col_pnome})) = TRIM(LOWER(%s))
                 ORDER BY {col_ini} ASC
                 LIMIT 1
                """,
                (dt_iso, str(nome).strip()),
            )
            ag = cur.fetchone()

        ag_dict = {}
        if ag is not None:
            names = [d[0] for d in cur.description]
            if isinstance(ag, dict):
                ag_dict = dict(ag)
            else:
                ag_dict = {names[i]: ag[i] for i in range(min(len(names), len(ag)))}

        cache[key] = ag_dict
        ag = ag_dict

    if not isinstance(ag, dict) or not ag:
        return

    ini = ag.get(col_ini, "")
    base_row["ag__inicio"] = ini
    base_row["ag__hora"] = str(ini)[11:16] if isinstance(ini, str) and len(ini) >= 16 else ""

    if col_prof and col_prof in ag:
        base_row["ag__profissional"] = ag.get(col_prof, "")
    if col_profid and col_profid in ag:
        base_row["ag__profissional_id"] = ag.get(col_profid, "")
    if col_profcbo and col_profcbo in ag:
        base_row["ag__prof_cbo"] = ag.get(col_profcbo, "")


# =============================================================================
# XLSX COMPLETO
# =============================================================================

def _normalize_keys_for_xlsx(rows: list[dict]) -> list[str]:
    if not rows:
        return ["Mensagem"]

    preferred = [
        "id",
        "paciente_id", "paciente_nome", "nome", "nome_paciente",
        "paciente_cpf", "cpf", "pac__cpf",
        "paciente_cns", "cns", "cartao_sus", "pac__cns",
        "paciente_nascimento", "nascimento", "data_nascimento", "pac__nascimento",
        "data_atendimento", "data", "data_iso", "created_at",
        "profissional_id", "prof_id", "id_profissional",
        "profissional_nome", "nome_profissional", "profissional",
        "profissional_cbo", "cbo_profissional", "cbo",
        "status", "situacao", "comparecimento",
        "cid", "cid_principal", "cid10", "pac__cid",
        "cidade", "municipio", "pac__municipio",
        "procedimento", "ap_procedimento",
        "codigo_sigtap", "ap_codigo_sigtap",
        "evolucao",
        "evo_oculta_situacao",
        "evo_oculta_total",
        "evo_oculta_visivel",
        "evolucoes_ocultas_visiveis",
        "pac__prontuario", "pac__idade",
        "pac__telefone", "pac__sexo", "pac__logradouro", "pac__numero", "pac__bairro", "pac__cep",
        "ag__inicio", "ag__hora", "ag__profissional", "ag__profissional_id", "ag__prof_cbo",
    ]

    keys_all: set[str] = set()
    for r in rows:
        keys_all.update(r.keys())

    out: list[str] = []
    for k in preferred:
        if k in keys_all and k not in out:
            out.append(k)

    out.extend(sorted([k for k in keys_all if k not in out]))
    return out


@registros_bp.get("/exportar_xlsx")
def exportar_xlsx():
    filtros = {
        "q": (request.args.get("q") or "").strip(),
        "prof": (request.args.get("prof") or "").strip(),
        "data_ini": (request.args.get("data_ini") or "").strip(),
        "data_fim": (request.args.get("data_fim") or "").strip(),
        "status": (request.args.get("status") or "").strip(),
        "sexo": (request.args.get("sexo") or "").strip(),
        "cid": (request.args.get("cid") or "").strip(),
        "cidade": (request.args.get("cidade") or "").strip(),
    }

    try:
        limit = int(request.args.get("limit", 5000))
    except ValueError:
        limit = 5000

    conn = conectar_db()
    try:
        _ensure_evolucoes_ocultas_schema(conn)

        cur = conn.cursor()
        sql, params = _montar_query_atendimentos(conn, limit=limit, **filtros)
        cur.execute(sql, params)

        data = _rows_to_dicts(cur, cur.fetchall())

        pac_cache: dict = {}
        ag_cache: dict = {}
        for r in data:
            _enrich_with_paciente(conn, r, pac_cache)
            _enrich_with_agendamento(conn, r, ag_cache)

    finally:
        conn.close()

    try:
        from openpyxl import Workbook
    except ImportError:
        return jsonify({"error": "Instale o pacote 'openpyxl' para exportar XLSX."}), 500

    wb = Workbook()
    ws = wb.active
    ws.title = "Registros"

    if not data:
        ws.append(["Mensagem"])
        ws.append(["Nenhum registro para os filtros selecionados."])
    else:
        cols = _normalize_keys_for_xlsx(data)
        ws.append(cols)
        for row in data:
            ws.append([row.get(c, "") for c in cols])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"registros_{date.today().isoformat()}.xlsx"
    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# =============================================================================
# PDF EVOLUÇÕES
# =============================================================================

def _fmt_cpf(v: str) -> str:
    d = _only_digits(v)
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return _safe_str(v) or "—"


def _fmt_cns(v: str) -> str:
    d = _only_digits(v)
    return d if d else (_safe_str(v) or "—")


def _calc_idade_from_iso(nasc_iso: str) -> str:
    s = _safe_str(nasc_iso)
    if not s or len(s) < 10 or s[4] != "-" or s[7] != "-":
        return "—"
    try:
        y, m, d = int(s[:4]), int(s[5:7]), int(s[8:10])
        hoje = date.today()
        idade = hoje.year - y - ((hoje.month, hoje.day) < (m, d))
        return str(max(0, idade))
    except Exception:
        return "—"


def _cbo_desc(conn, cbo: str) -> str:
    code = _safe_str(cbo)
    if not code:
        return "—"

    for tb in ("cbo_catalogo", "cbos", "ocupacoes", "cbo_funcao", "cbo_descricao"):
        if not _has_table(conn, tb):
            continue

        cols = _get_columns(conn, tb)
        c_codigo = _pick_att_col(cols, "co_ocupacao", "codigo", "cbo", "cod")
        c_desc = _pick_att_col(cols, "no_ocupacao", "descricao", "desc", "funcao", "nome")

        if not (c_codigo and c_desc):
            continue

        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT {c_desc}
              FROM {tb}
             WHERE REGEXP_REPLACE(COALESCE({c_codigo}::text, ''), '\\D', '', 'g') =
                   REGEXP_REPLACE(%s, '\\D', '', 'g')
             LIMIT 1
            """,
            (code,),
        )
        r = cur.fetchone()
        if r and _row_get(r, c_desc, 0, ""):
            return str(_row_get(r, c_desc, 0, "")).strip()

    return "—"


def _wrap_text(text: str, font_name: str, font_size: int, max_width: float) -> list[str]:
    t = _safe_str(text)
    if not t:
        return ["—"]

    t = t.replace("\r", "")
    paragraphs = [p.strip() for p in t.split("\n")]
    lines: list[str] = []

    for p in paragraphs:
        if p == "":
            lines.append("")
            continue

        words = p.split()
        cur = ""

        for w in words:
            cand = (cur + " " + w).strip() if cur else w
            if stringWidth(cand, font_name, font_size) <= max_width:
                cur = cand
            else:
                if cur:
                    lines.append(cur)
                    cur = w
                else:
                    lines.append(w)

        if cur:
            lines.append(cur)

    return lines or ["—"]


def _draw_header(c: canvas.Canvas, *, paciente_nome: str, idade: str, cpf: str, cns: str, qtd: int, status: str, mod: str, page_w: float, page_h: float):
    margem_x = 18 * mm
    top = page_h - 16 * mm
    header_h = 34 * mm
    w = page_w - 2 * margem_x

    c.setFillColor(colors.HexColor("#111827"))
    c.roundRect(margem_x, top - header_h, w, header_h, 8, fill=1, stroke=0)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(margem_x + 10 * mm, top - 11 * mm, (paciente_nome or "—")[:90])

    c.setFont("Helvetica", 10.5)
    c.setFillColor(colors.HexColor("#E5E7EB"))
    c.drawString(margem_x + 10 * mm, top - 18.8 * mm, f"Idade: {idade}   |   CPF: {cpf}   |   CNS: {cns}")

    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.setLineWidth(1)
    c.line(margem_x, top - header_h - 5 * mm, page_w - margem_x, top - header_h - 5 * mm)


def _draw_registro(c: canvas.Canvas, x: float, y: float, w: float, *, profissional: str, cbo: str, cbo_desc: str, data_atendimento: str, evolucao: str, ocultas: str = ""):
    card_h = 52 * mm if ocultas else 44 * mm
    pad_x = 8 * mm
    pad_y = 7 * mm

    inner_x = x + pad_x
    inner_w = w - 2 * pad_x
    right_x = x + w - pad_x

    c.setFillColor(colors.white)
    c.setStrokeColor(colors.HexColor("#E5E7EB"))
    c.roundRect(x, y - card_h, w, card_h, 8, fill=1, stroke=1)

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors.HexColor("#111827"))
    c.drawRightString(right_x, y - pad_y, (_safe_str(data_atendimento) or "—")[:32])

    left_full = f"{_safe_str(profissional) or '—'} · CBO: {_safe_str(cbo) or '—'} · {_safe_str(cbo_desc) or '—'}"
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor("#0F172A"))
    c.drawString(inner_x, y - pad_y, left_full[:115])

    c.setStrokeColor(colors.HexColor("#E5E7EB"))
    c.line(inner_x, y - pad_y - 4.8 * mm, right_x, y - pad_y - 4.8 * mm)

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors.HexColor("#111827"))
    c.drawString(inner_x, y - pad_y - 11.5 * mm, "Evolução:")

    evo_font = "Helvetica"
    evo_size = 9
    line_h = 4.2 * mm
    ly = y - pad_y - 16 * mm

    c.setFont(evo_font, evo_size)
    c.setFillColor(colors.HexColor("#0B1220"))

    lines = _wrap_text(evolucao, evo_font, evo_size, inner_w)[:7 if ocultas else 10]
    for ln in lines:
        c.drawString(inner_x, ly, ln)
        ly -= line_h

    if ocultas:
        ly -= 1 * mm
        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColor(colors.HexColor("#7C3AED"))
        c.drawString(inner_x, ly, "Evolução oculta visível para você:")
        ly -= line_h

        c.setFont("Helvetica", 8.5)
        c.setFillColor(colors.HexColor("#312E81"))
        for ln in _wrap_text(ocultas, "Helvetica", 8.5, inner_w)[:3]:
            c.drawString(inner_x, ly, ln)
            ly -= line_h

    return y - card_h - 6 * mm


@registros_bp.get("/evolucoes/pdf")
def exportar_evolucoes_pdf():
    filtros = {
        "q": (request.args.get("q") or "").strip(),
        "prof": (request.args.get("prof") or "").strip(),
        "data_ini": (request.args.get("data_ini") or "").strip(),
        "data_fim": (request.args.get("data_fim") or "").strip(),
        "status": (request.args.get("status") or "").strip(),
        "sexo": (request.args.get("sexo") or "").strip(),
        "cid": (request.args.get("cid") or "").strip(),
        "cidade": (request.args.get("cidade") or "").strip(),
    }

    paciente_id = (request.args.get("paciente_id") or "").strip()

    try:
        limit_evos = int(request.args.get("limit_evos", 5000))
    except ValueError:
        limit_evos = 5000

    conn = conectar_db()
    try:
        _ensure_evolucoes_ocultas_schema(conn)

        if not _has_table(conn, "atendimentos"):
            return jsonify({"ok": False, "error": "Tabela 'atendimentos' não existe."}), 500

        a_cols = _get_columns(conn, "atendimentos")
        col_pid = _pick_att_col(a_cols, "paciente_id")
        col_nome = _pick_att_col(a_cols, "nome", "paciente_nome", "nome_paciente")
        col_data = _pick_att_col(a_cols, "data_atendimento", "data", "data_iso", "created_at")
        col_evo = _pick_att_col(a_cols, "evolucao", "evolução", "evol")
        col_id = _pick_att_col(a_cols, "id")
        col_prof_nome = _pick_att_col(a_cols, "nome_profissional", "profissional_nome", "profissional")
        col_cbo = _pick_att_col(a_cols, "cbo_profissional", "cbo")
        col_mod = _pick_att_col(a_cols, "mod", "modalidade")
        col_stat = _pick_att_col(a_cols, "status", "situacao", "comparecimento")
        col_cpf = _pick_att_col(a_cols, "cpf", "paciente_cpf")
        col_cns = _pick_att_col(a_cols, "cns", "paciente_cns", "cartao_sus")
        col_nasc = _pick_att_col(a_cols, "nascimento", "paciente_nascimento")

        if not (col_pid and col_nome and col_data and col_evo):
            return jsonify({"ok": False, "error": "Tabela atendimentos incompleta para PDF."}), 500

        where = [f"TRIM(COALESCE(a.{col_evo}, '')) <> ''"]
        params = []

        if paciente_id:
            where.append(f"a.{col_pid} = %s")
            params.append(int(paciente_id) if paciente_id.isdigit() else paciente_id)

        data_ini = _norm_date_param(filtros["data_ini"])
        data_fim = _norm_date_param(filtros["data_fim"])
        d_expr = _sql_date_expr(f"a.{col_data}")

        if data_ini and data_fim:
            where.append(f"{d_expr} BETWEEN %s::date AND %s::date")
            params.extend([data_ini, data_fim])
        elif data_ini:
            where.append(f"{d_expr} = %s::date")
            params.append(data_ini)
        elif data_fim:
            where.append(f"{d_expr} = %s::date")
            params.append(data_fim)

        user = _resolve_logged_user(conn)
        hidden_join = _hidden_evo_lateral_sql()
        hidden_params = _hidden_evo_params(user)

        sql = f"""
            SELECT
                a.{col_pid} AS paciente_id,
                a.{col_nome} AS paciente_nome,
                a.{col_data} AS data_atendimento,
                a.{col_evo} AS evolucao,
                {f"COALESCE(a.{col_prof_nome}, '')" if col_prof_nome else "''"} AS profissional_nome,
                {f"COALESCE(a.{col_cbo}, '')" if col_cbo else "''"} AS profissional_cbo,
                {f"COALESCE(a.{col_mod}, '')" if col_mod else "''"} AS paciente_mod,
                {f"COALESCE(a.{col_stat}, '')" if col_stat else "''"} AS paciente_status,
                {f"COALESCE(a.{col_cpf}, '')" if col_cpf else "''"} AS paciente_cpf,
                {f"COALESCE(a.{col_cns}, '')" if col_cns else "''"} AS paciente_cns,
                {f"COALESCE(a.{col_nasc}, '')" if col_nasc else "''"} AS paciente_nascimento,
                COALESCE(eoh.evolucoes_ocultas_visiveis, '') AS evolucoes_ocultas_visiveis
            FROM atendimentos a
            {hidden_join}
            WHERE {" AND ".join(where)}
            ORDER BY a.{col_pid} ASC, {d_expr} DESC, a.{col_id or 'id'} DESC
            LIMIT %s
        """

        cur = conn.cursor()
        cur.execute(sql, hidden_params + params + [limit_evos])
        rows = _rows_to_dicts(cur, cur.fetchall())

        pacientes: Dict[str, Dict[str, Any]] = {}

        for r in rows:
            pid = str(r["paciente_id"])
            if pid not in pacientes:
                pacientes[pid] = {
                    "nome": _safe_str(r["paciente_nome"]) or "—",
                    "cpf": _fmt_cpf(r.get("paciente_cpf", "")),
                    "cns": _fmt_cns(r.get("paciente_cns", "")),
                    "nasc": _safe_str(r.get("paciente_nascimento", "")),
                    "status": _safe_str(r.get("paciente_status", "")) or "—",
                    "mod": _safe_str(r.get("paciente_mod", "")) or "—",
                    "evos": [],
                }

            pacientes[pid]["evos"].append({
                "data": _safe_str(r["data_atendimento"]) or "—",
                "prof": _safe_str(r["profissional_nome"]) or "—",
                "cbo": _safe_str(r["profissional_cbo"]) or "",
                "evo": _safe_str(r["evolucao"]) or "—",
                "ocultas": _safe_str(r.get("evolucoes_ocultas_visiveis", "")),
            })

        buf = io.BytesIO()
        page_w, page_h = A4
        pdf = canvas.Canvas(buf, pagesize=A4)

        margem_x = 18 * mm
        content_w = page_w - 2 * margem_x

        for pac in pacientes.values():
            idade = _calc_idade_from_iso(pac.get("nasc", ""))
            evos = pac["evos"]

            for chunk_start in range(0, len(evos), 4):
                chunk = evos[chunk_start:chunk_start + 4]

                _draw_header(
                    pdf,
                    paciente_nome=pac["nome"],
                    idade=idade,
                    cpf=pac["cpf"],
                    cns=pac["cns"],
                    qtd=len(evos),
                    status=pac["status"],
                    mod=pac["mod"],
                    page_w=page_w,
                    page_h=page_h,
                )

                y = page_h - (16 * mm + 34 * mm + 14 * mm)
                x = margem_x

                for item in chunk:
                    y = _draw_registro(
                        pdf, x, y, content_w,
                        profissional=item.get("prof", "—"),
                        cbo=item.get("cbo", ""),
                        cbo_desc=_cbo_desc(conn, item.get("cbo", "")),
                        data_atendimento=item.get("data", "—"),
                        evolucao=item.get("evo", "—"),
                        ocultas=item.get("ocultas", ""),
                    )

                pdf.setFont("Helvetica", 8)
                pdf.setFillColor(colors.HexColor("#64748B"))
                pdf.drawRightString(page_w - margem_x, 12 * mm, f"SGD · Evoluções · {date.today().isoformat()}")
                pdf.showPage()

        pdf.save()
        buf.seek(0)

        filename = f"evolucoes_{date.today().isoformat()}.pdf"
        return send_file(buf, as_attachment=True, download_name=filename, mimetype="application/pdf")

    finally:
        conn.close()


# =============================================================================
# BPA-i XLSX
# =============================================================================

def _fmt_date_bpai_ddmmyyyy(v: str) -> str:
    s = _safe_str(v)
    if not s:
        return ""
    s10 = s[:10]
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s10):
        y, m, d = s10.split("-")
        return f"{d}/{m}/{y}"
    if re.match(r"^\d{2}/\d{2}/\d{4}$", s10):
        return s10
    return s10


def _calc_idade_no_dia(nasc: str, data_at: str) -> str:
    n_iso = _norm_date_param(_safe_str(nasc)[:10])
    d_iso = _norm_date_param(_safe_str(data_at)[:10])
    try:
        ny, nm, nd = int(n_iso[:4]), int(n_iso[5:7]), int(n_iso[8:10])
        dy, dm, dd = int(d_iso[:4]), int(d_iso[5:7]), int(d_iso[8:10])
        return str(max(0, dy - ny - ((dm, dd) < (nm, nd))))
    except Exception:
        return ""


def _map_raca_to_codigo(raca: str) -> str:
    s = _safe_str(raca).lower()
    if not s:
        return "99"

    d = _only_digits(s)
    if d:
        return d.zfill(2)[:2]

    m = {
        "branca": "01", "branco": "01",
        "preta": "02", "preto": "02", "negra": "02", "negro": "02",
        "parda": "03", "pardo": "03",
        "amarela": "04", "amarelo": "04",
        "indigena": "05", "indígena": "05",
        "ignorado": "99", "ignorada": "99",
        "sem informacao": "99", "sem informação": "99",
        "nao informado": "99", "não informado": "99",
    }
    return m.get(s, "99")


BPAI_COLS = [
    "prd-ident", "prd-cnes", "prd-cnsmed", "prd-cbo", "prd-dtaten", "prd-pa",
    "prd-cnspac", "prd-sexo", "prd-ibge", "prd-cid", "prd-idade", "prd-qt",
    "prd-caten", "prd-naut", "prd-org", "prd-nmpac", "prd-dtnasc", "prd-raca",
    "prd-etnia", "prd-nac", "prd-srv", "prd-clf", "prd-equipe-seq", "prd-equipe-area",
    "prd-cnpj", "prd-cep-pcnte", "prd-lograd-pcnte", "prd-end-pcnte", "prd-compl-pcnte",
    "prd-num-pcnte", "prd-bairro-pcnte", "prd-ddtel-pcnte", "prd-email-pcnte", "prd-ine"
]


def _fetch_dict_by_id(conn, table: str, id_value: Any) -> dict:
    if not id_value or not _has_table(conn, table) or not _has_column(conn, table, "id"):
        return {}

    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table} WHERE id = %s LIMIT 1", (id_value,))
    row = cur.fetchone()

    if not row:
        return {}

    names = [d[0] for d in cur.description]
    if isinstance(row, dict):
        return dict(row)
    return {names[i]: row[i] for i in range(min(len(names), len(row)))}


def _rows_bpai(conn, filtros: dict) -> list[dict]:
    sql, params = _montar_query_atendimentos(
        conn,
        q=filtros.get("q", ""),
        prof=filtros.get("prof", ""),
        data_ini=filtros.get("data_ini", ""),
        data_fim=filtros.get("data_fim", ""),
        status=filtros.get("status", ""),
        sexo=filtros.get("sexo", ""),
        cid=filtros.get("cid", ""),
        cidade=filtros.get("cidade", ""),
        limit=filtros.get("limit", 50000),
        incluir_evolucao_oculta=False,
    )

    cur = conn.cursor()
    cur.execute(sql, params)
    at_list = _rows_to_dicts(cur, cur.fetchall())

    out: list[dict] = []

    for a in at_list:
        paciente_id = a.get("paciente_id")
        prof_id = a.get("profissional_id")

        pac = _fetch_dict_by_id(conn, "pacientes", paciente_id) if paciente_id else {}
        prof = _fetch_dict_by_id(conn, "usuarios", prof_id) if prof_id else {}

        dt_at_raw = a.get("data_atendimento") or a.get("data") or a.get("created_at") or ""
        dt_aten = _fmt_date_bpai_ddmmyyyy(str(dt_at_raw))

        nasc_raw = pac.get("nascimento") or a.get("nascimento") or ""
        dt_nasc = _fmt_date_bpai_ddmmyyyy(str(nasc_raw))

        sexo_p = _safe_str(pac.get("sexo") or a.get("sexo") or "")
        cid_p = _safe_str(pac.get("cid") or a.get("cid") or "")
        idade = _safe_str(pac.get("idade") or "") or _calc_idade_no_dia(str(nasc_raw), str(dt_at_raw))

        cnspac = _only_digits(pac.get("cns") or "")
        nmpac = _safe_str(pac.get("nome") or a.get("nome") or "")
        cnsmed = _only_digits(prof.get("cns") or a.get("cns_profissional") or "")
        cbo = _only_digits(prof.get("cbo") or a.get("cbo_profissional") or "")

        codigo_sigtap = _safe_str(a.get("ap_codigo_sigtap") or a.get("codigo_sigtap") or "")

        row = {k: "" for k in BPAI_COLS}
        row["prd-ident"] = "03"
        row["prd-cnes"] = ""
        row["prd-cnsmed"] = cnsmed
        row["prd-cbo"] = cbo
        row["prd-dtaten"] = dt_aten
        row["prd-pa"] = codigo_sigtap
        row["prd-cnspac"] = cnspac
        row["prd-sexo"] = sexo_p[:1].upper() if sexo_p else ""
        row["prd-ibge"] = ""
        row["prd-cid"] = cid_p

        try:
            row["prd-idade"] = int(str(idade).strip())
        except Exception:
            row["prd-idade"] = ""

        row["prd-qt"] = "000001"
        row["prd-caten"] = "01"
        row["prd-org"] = "BPA"
        row["prd-nmpac"] = nmpac
        row["prd-dtnasc"] = dt_nasc
        row["prd-raca"] = _map_raca_to_codigo(pac.get("raca") or "")
        row["prd-nac"] = "010"
        row["prd-cep-pcnte"] = _only_digits(pac.get("cep") or "")
        row["prd-lograd-pcnte"] = "081"
        row["prd-end-pcnte"] = _safe_str(pac.get("logradouro") or pac.get("rua") or "")
        row["prd-compl-pcnte"] = _safe_str(pac.get("complemento") or "")
        row["prd-num-pcnte"] = _safe_str(pac.get("numero_casa") or pac.get("numero") or "")
        row["prd-bairro-pcnte"] = _safe_str(pac.get("bairro") or "")
        row["prd-ddtel-pcnte"] = _only_digits(pac.get("telefone1") or pac.get("telefone") or "")

        out.append(row)

    return out


@registros_bp.get("/exportar_bpai_xlsx")
def exportar_bpai_xlsx():
    filtros = {
        "q": (request.args.get("q") or "").strip(),
        "prof": (request.args.get("prof") or "").strip(),
        "data_ini": (request.args.get("data_ini") or "").strip(),
        "data_fim": (request.args.get("data_fim") or "").strip(),
        "status": (request.args.get("status") or "").strip(),
        "sexo": (request.args.get("sexo") or "").strip(),
        "cid": (request.args.get("cid") or "").strip(),
        "cidade": (request.args.get("cidade") or "").strip(),
    }

    try:
        filtros["limit"] = int(request.args.get("limit", 50000))
    except ValueError:
        filtros["limit"] = 50000

    conn = conectar_db()
    try:
        rows = _rows_bpai(conn, filtros)
    finally:
        conn.close()

    try:
        from openpyxl import Workbook
    except ImportError:
        return jsonify({"error": "Instale o pacote 'openpyxl' para exportar XLSX."}), 500

    wb = Workbook()
    ws = wb.active
    ws.title = "BPAi"

    ws.append(BPAI_COLS)

    if not rows:
        ws.append([""] * len(BPAI_COLS))
    else:
        for r in rows:
            ws.append([r.get(c, "") for c in BPAI_COLS])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"bpai_{date.today().isoformat()}.xlsx"
    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )