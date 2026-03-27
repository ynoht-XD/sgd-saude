# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import re
import sqlite3
from datetime import date
from typing import Any, Dict, List, Sequence, Tuple

from flask import request, jsonify, render_template, send_file

from db import conectar_db
from . import registros_bp

# reportlab
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth


# =============================================================================
# Helpers gerais (DB / colunas)
# =============================================================================

def _get_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cur.fetchall()]


def _first_existing(cols: Sequence[str], opts: Sequence[str]) -> str | None:
    for c in opts:
        if c in cols:
            return c
    return None


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    )
    return cur.fetchone() is not None


# =============================================================================
# Helpers de DATA (resolver filtro que não funciona)
# =============================================================================

def _safe_str(v) -> str:
    return ("" if v is None else str(v)).strip()


def _norm_date_param(s: str) -> str:
    """
    Aceita:
      - YYYY-MM-DD
      - DD/MM/YYYY
    Retorna sempre YYYY-MM-DD (ou '' se vazio).
    """
    s = _safe_str(s)
    if not s:
        return ""
    if re.match(r"^\d{2}/\d{2}/\d{4}$", s):
        d, m, y = s.split("/")
        return f"{y}-{m}-{d}"
    return s


def _sql_date_expr(col_sql: str) -> str:
    """
    Expressão SQLite para extrair UMA DATA (YYYY-MM-DD) do campo:
      - ISO: 2025-12-18, 2025-12-18 10:00, 2025-12-18T10:00
      - BR : 18/12/2025, 18/12/2025 10:00
    """
    return f"""
    (CASE
      WHEN {col_sql} LIKE '____-__-__%' THEN date(substr({col_sql}, 1, 10))
      WHEN {col_sql} LIKE '__/__/____%' THEN date(substr({col_sql}, 7, 4) || '-' || substr({col_sql}, 4, 2) || '-' || substr({col_sql}, 1, 2))
      ELSE date({col_sql})
    END)
    """.strip()


def _only_digits(s: str) -> str:
    return re.sub(r"\D+", "", s or "")


# =============================================================================
# ✅ Profissionais Sugestão (nome + CBO em usuarios)
#    (para o autocomplete do teu JS)
# =============================================================================
@registros_bp.get("/../atendimentos/api/profissionais_sugestao")  # não use isso em produção
def _route_hack_noop():
    """
    ⚠️ ATENÇÃO:
    Este decorator é só pra mostrar que a rota ideal é:
      /atendimentos/api/profissionais_sugestao

    Como você colou só o blueprint de registros, eu NÃO consigo
    registrar corretamente no blueprint de atendimentos aqui.

    ✅ A rota correta está logo abaixo, pronta pra você copiar
    pro blueprint atendimentos_bp.

    Se você colar esta função como está, ela NÃO deve ser usada.
    """
    return jsonify([])


def api_profissionais_sugestao_impl():
    """
    Cole este endpoint no blueprint de ATENDIMENTOS, assim:

    @atendimentos_bp.get("/api/profissionais_sugestao")
    def api_profissionais_sugestao(): return api_profissionais_sugestao_impl()

    Retorna: [{id, nome, cbo}]
    Busca: usuarios.nome OR usuarios.cbo
    """
    q = (request.args.get("q") or "").strip()
    if len(q) < 3:
        return jsonify([])

    q_low = q.lower()
    q_digits = _only_digits(q)

    conn = conectar_db()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if not _has_table(conn, "usuarios"):
        conn.close()
        return jsonify([])

    ucols = _get_columns(conn, "usuarios")
    col_id   = _first_existing(ucols, ["id"])
    col_nome = _first_existing(ucols, ["nome"])
    col_cbo  = _first_existing(ucols, ["cbo"])
    col_role = _first_existing(ucols, ["role"])

    if not (col_id and col_nome):
        conn.close()
        return jsonify([])

    role_val = "PROFISSIONAL"

    like_nome_any   = f"%{q_low}%"
    like_nome_start = f"{q_low}%"

    # CBO só faz sentido se tiver coluna cbo
    like_cbo_any = f"%{q_digits}%"
    like_cbo_start = f"{q_digits}%"

    where = []
    params: list[Any] = []

    # role
    if col_role:
        where.append(f"UPPER(COALESCE({col_role},'')) = UPPER(?)")
        params.append(role_val)

    # filtro q (nome ou cbo)
    where.append("(".strip())
    where2 = []
    where2.append(f"LOWER(COALESCE({col_nome},'')) LIKE ?"); params.append(like_nome_any)
    if col_cbo and q_digits:
        where2.append(f"COALESCE({col_cbo},'') LIKE ?"); params.append(like_cbo_any)
    where.append(" OR ".join(where2) + ")")

    where_sql = " AND ".join(where) if where else "1=1"

    # ranking simples (nome começa > cbo começa > nome contém)
    order_sql = "LOWER(COALESCE(nome,'')) ASC"
    if col_cbo:
        order_sql = f"""
        CASE
          WHEN LOWER(COALESCE({col_nome},'')) LIKE ? THEN 0
          WHEN (? <> '' AND COALESCE({col_cbo},'') LIKE ?) THEN 1
          WHEN LOWER(COALESCE({col_nome},'')) LIKE ? THEN 2
          ELSE 9
        END,
        LOWER(COALESCE({col_nome},'')) ASC
        """.strip()
        params.extend([like_nome_start, q_digits, like_cbo_start, like_nome_any])

    sql = f"""
    SELECT
      {col_id}   AS id,
      {col_nome} AS nome,
      {("COALESCE(" + col_cbo + ",'') AS cbo") if col_cbo else "'' AS cbo"}
    FROM usuarios
    WHERE {where_sql}
    ORDER BY {order_sql}
    LIMIT 12
    """.strip()

    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()

    out = [{"id": r["id"], "nome": r["nome"], "cbo": r["cbo"]} for r in rows]
    return jsonify(out)


# =============================================================================
# QUERY COMPARTILHADA (API LIST + XLSX)
# =============================================================================

def _montar_query_atendimentos(
    conn: sqlite3.Connection,
    q: str,
    prof: str,
    data_ini: str,
    data_fim: str,
    status: str,
    sexo: str,
    cid: str,
    cidade: str,
    limit: int | None,
) -> Tuple[str, List[Any]]:
    """
    Monta SQL + params para listar atendimentos.

    - Se existir atendimento_procedimentos:
        1 linha por procedimento (JOIN ap)
        e busca q considera ap.procedimento / ap.codigo_sigtap
    - Se não existir:
        1 linha por atendimento (sem JOIN ap)
    """

    table = "atendimentos"
    cols = _get_columns(conn, table)

    has_proc = _has_table(conn, "atendimento_procedimentos")
    proc_cols = _get_columns(conn, "atendimento_procedimentos") if has_proc else []

    # --- mapeamento flexível (alias a.)
    nome_cols_raw = [c for c in ["paciente_nome", "nome_paciente", "nome"] if c in cols]
    cpf_cols_raw  = [c for c in ["cpf", "paciente_cpf"] if c in cols]
    cns_cols_raw  = [c for c in ["cns", "paciente_cns", "cartao_sus"] if c in cols]

    prof_id_col_raw   = _first_existing(cols, ["profissional_id", "prof_id", "id_profissional"])
    prof_nome_col_raw = _first_existing(cols, ["profissional_nome", "nome_profissional", "profissional", "usuario_nome", "nome_usuario"])

    data_col_raw   = _first_existing(cols, ["data_atendimento", "data", "data_iso", "created_at"])
    status_col_raw = _first_existing(cols, ["status", "situacao", "comparecimento"])
    sexo_col_raw   = _first_existing(cols, ["sexo", "sex"])
    cid_col_raw    = _first_existing(cols, ["cid", "cid_principal", "cid10"])
    cidade_col_raw = _first_existing(cols, ["cidade", "municipio", "cidade_paciente", "municipio_paciente"])

    # prefixa com alias
    nome_cols = [f"a.{c}" for c in nome_cols_raw]
    cpf_cols  = [f"a.{c}" for c in cpf_cols_raw]
    cns_cols  = [f"a.{c}" for c in cns_cols_raw]

    prof_id_col   = f"a.{prof_id_col_raw}" if prof_id_col_raw else None
    prof_nome_col = f"a.{prof_nome_col_raw}" if prof_nome_col_raw else None
    data_col      = f"a.{data_col_raw}" if data_col_raw else None
    status_col    = f"a.{status_col_raw}" if status_col_raw else None
    sexo_col      = f"a.{sexo_col_raw}" if sexo_col_raw else None
    cid_col       = f"a.{cid_col_raw}" if cid_col_raw else None
    cidade_col    = f"a.{cidade_col_raw}" if cidade_col_raw else None

    # --- JOINs
    joins: List[str] = []
    if has_proc:
        joins.append("JOIN atendimento_procedimentos ap ON ap.atendimento_id = a.id")

    # --- WHERE dinâmico
    where_parts: List[str] = []
    params: List[Any] = []

    # Busca livre (q)
    if q:
        like = f"%{q}%"
        sub: List[str] = []

        for c in nome_cols:
            sub.append(f"{c} LIKE ?"); params.append(like)
        for c in cpf_cols:
            sub.append(f"{c} LIKE ?"); params.append(like)
        for c in cns_cols:
            sub.append(f"{c} LIKE ?"); params.append(like)

        if has_proc:
            if "procedimento" in proc_cols:
                sub.append("ap.procedimento LIKE ?"); params.append(like)
            if "codigo_sigtap" in proc_cols:
                sub.append("ap.codigo_sigtap LIKE ?"); params.append(like)

        if sub:
            where_parts.append("(" + " OR ".join(sub) + ")")

    # Profissional
    if prof:
        if prof.isdigit() and prof_id_col:
            where_parts.append(f"{prof_id_col} = ?")
            params.append(int(prof))
        elif prof_nome_col:
            where_parts.append(f"{prof_nome_col} LIKE ?")
            params.append(f"%{prof}%")

    # Datas (ROBUSTO)
    data_ini = _norm_date_param(data_ini)
    data_fim = _norm_date_param(data_fim)

    if data_col and (data_ini or data_fim):
        d_expr = _sql_date_expr(data_col)
        if data_ini and data_fim:
            where_parts.append(f"{d_expr} BETWEEN date(?) AND date(?)")
            params.extend([data_ini, data_fim])
        elif data_ini:
            where_parts.append(f"{d_expr} = date(?)")
            params.append(data_ini)
        else:
            where_parts.append(f"{d_expr} = date(?)")
            params.append(data_fim)

    # status/sexo/cid/cidade (se existir coluna)
    if status and status_col:
        where_parts.append(f"{status_col} = ?")
        params.append(status)

    if sexo and sexo_col:
        where_parts.append(f"{sexo_col} = ?")
        params.append(sexo)

    if cid and cid_col:
        where_parts.append(f"{cid_col} LIKE ?")
        params.append(f"%{cid}%")

    if cidade and cidade_col:
        where_parts.append(f"{cidade_col} LIKE ?")
        params.append(f"%{cidade}%")

    # --- SELECT
    select_parts = [
        "a.*",
        *(["ap.procedimento AS ap_procedimento",
           "COALESCE(ap.codigo_sigtap,'') AS ap_codigo_sigtap"] if has_proc else []),
    ]

    sql = f"SELECT {', '.join(select_parts)}\nFROM {table} a"
    if joins:
        sql += "\n" + "\n".join(joins)

    if where_parts:
        sql += "\nWHERE " + " AND ".join(where_parts)

    # ORDER (robusto também)
    order_parts: List[str] = []
    if data_col:
        order_parts.append(f"{_sql_date_expr(data_col)} DESC")
    if "id" in cols:
        order_parts.append("a.id DESC")
    if has_proc:
        order_parts.append("ap.id ASC")
    if order_parts:
        sql += "\nORDER BY " + ", ".join(order_parts)

    if limit and limit > 0:
        sql += "\nLIMIT ?"
        params.append(limit)

    return sql, params


# =============================================================================
# Página (HTML)
# =============================================================================

@registros_bp.get("/")
def pagina_registros():
    return render_template("registros.html")


# =============================================================================
# API LISTAR (JSON)
# =============================================================================

@registros_bp.get("/api/list")
def api_listar_atendimentos():
    q        = (request.args.get("q") or "").strip()
    prof     = (request.args.get("prof") or "").strip()
    data_ini = (request.args.get("data_ini") or "").strip()
    data_fim = (request.args.get("data_fim") or "").strip()
    status   = (request.args.get("status") or "").strip()
    sexo     = (request.args.get("sexo") or "").strip()
    cid      = (request.args.get("cid") or "").strip()
    cidade   = (request.args.get("cidade") or "").strip()

    try:
        limit = int(request.args.get("limit", 500))
    except ValueError:
        limit = 500

    conn = conectar_db()
    conn.row_factory = sqlite3.Row
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
    rows = cur.fetchall()

    data = [_row_to_dict(r) for r in rows]

    # ✅ enriquecer cada linha com dados do paciente e agendamento
    pac_cache: dict = {}
    ag_cache: dict = {}

    for r in data:
        _enrich_with_paciente(conn, r, pac_cache)
        _enrich_with_agendamento(conn, r, ag_cache)

        # fallback visual útil pra aba paciente
        r["pac__nome"] = r.get("pac__nome") or r.get("paciente_nome") or r.get("nome") or ""
        r["pac__cpf"] = r.get("pac__cpf") or r.get("paciente_cpf") or r.get("cpf") or ""
        r["pac__cns"] = r.get("pac__cns") or r.get("paciente_cns") or r.get("cns") or r.get("cartao_sus") or ""
        r["pac__nascimento"] = r.get("pac__nascimento") or r.get("paciente_nascimento") or r.get("nascimento") or r.get("data_nascimento") or ""
        r["pac__status"] = r.get("pac__status") or r.get("status") or ""
        r["pac__sexo"] = r.get("pac__sexo") or r.get("sexo") or ""
        r["pac__cid"] = r.get("pac__cid") or r.get("cid") or ""
        r["pac__municipio"] = r.get("pac__municipio") or r.get("cidade") or r.get("municipio") or ""

    conn.close()
    return jsonify(data)

# =============================================================================
# ✅ XLSX COMPLETÃO: atendimentos + pacientes + agendamentos
# =============================================================================

def _pick_att_col(cols: list[str] | set[str], *names: str) -> str | None:
    for n in names:
        if n in cols:
            return n
    return None


def _normalize_keys_for_xlsx(rows: list[dict]) -> list[str]:
    """
    Monta colunas estáveis:
    - começa com as mais importantes (se existirem)
    - depois adiciona o resto ordenado
    """
    if not rows:
        return ["Mensagem"]

    # chaves que você quase sempre quer no topo
    preferred = [
        "id",
        "paciente_id", "paciente_nome", "nome", "nome_paciente",
        "paciente_cpf", "cpf",
        "paciente_cns", "cns", "cartao_sus",
        "paciente_nascimento", "nascimento", "data_nascimento",
        "data_atendimento", "data", "data_iso", "created_at",
        "profissional_id", "prof_id", "id_profissional",
        "profissional_nome", "nome_profissional", "profissional",
        "profissional_cbo", "cbo_profissional", "cbo",
        "status", "situacao", "comparecimento",
        "cid", "cid_principal", "cid10",
        "cidade", "municipio", "cidade_paciente", "municipio_paciente",
        "procedimento", "ap_procedimento",
        "codigo_sigtap", "ap_codigo_sigtap",
        "evolucao", "observacao", "observacoes",
        # extras (pacientes)
        "pac__telefone", "pac__sexo", "pac__logradouro", "pac__numero", "pac__bairro", "pac__cep",
        # extras (agendamento)
        "ag__inicio", "ag__hora", "ag__profissional", "ag__profissional_id", "ag__prof_cbo",
    ]

    keys_all: set[str] = set()
    for r in rows:
        keys_all.update(r.keys())

    out: list[str] = []
    for k in preferred:
        if k in keys_all and k not in out:
            out.append(k)

    # resto
    rest = sorted([k for k in keys_all if k not in out])
    out.extend(rest)
    return out


def _enrich_with_paciente(conn: sqlite3.Connection, base_row: dict, cache: dict) -> None:
    """
    Enriquecimento por tabela pacientes.
    - Tenta por paciente_id (ideal)
    - Fallback: CPF/CNS (digits) ou nome+nascimento
    Adiciona campos prefixados: pac__*
    """
    if not _has_table(conn, "pacientes"):
        return

    pcols = _get_columns(conn, "pacientes")
    col_id   = _pick_att_col(pcols, "id", "paciente_id")
    col_nome = _pick_att_col(pcols, "nome", "paciente_nome", "nome_paciente")
    col_cpf  = _pick_att_col(pcols, "cpf", "paciente_cpf", "cpf_digits", "cpf_cidadao")
    col_cns  = _pick_att_col(pcols, "cns", "paciente_cns", "cns_digits", "cartao_sus")
    col_nasc = _pick_att_col(pcols, "nascimento", "data_nascimento", "dt_nasc", "paciente_nascimento")

    # ✅ ESTES DOIS ESTAVAM FALTANDO
    col_pront = _pick_att_col(pcols, "prontuario", "prontuario_num")
    col_idade = _pick_att_col(pcols, "idade")

    # extras
    col_sexo = _pick_att_col(pcols, "sexo", "sex")
    col_tel  = _pick_att_col(pcols, "telefone", "telefone1", "paciente_telefone1", "celular")
    col_cep  = _pick_att_col(pcols, "cep", "paciente_cep")
    col_log  = _pick_att_col(pcols, "logradouro", "rua", "paciente_logradouro")
    col_num  = _pick_att_col(pcols, "numero", "numero_casa", "paciente_numero_casa")
    col_bai  = _pick_att_col(pcols, "bairro", "paciente_bairro")
    col_mun  = _pick_att_col(pcols, "municipio", "cidade", "paciente_municipio", "paciente_cidade")
    col_uf   = _pick_att_col(pcols, "uf")
    col_mod  = _pick_att_col(pcols, "mod", "modalidade")
    col_stat = _pick_att_col(pcols, "status", "situacao")
    col_cid  = _pick_att_col(pcols, "cid", "cid_principal", "cid10")
    col_cid2 = _pick_att_col(pcols, "cid2")
    col_mae  = _pick_att_col(pcols, "mae", "nome_mae")
    col_pai  = _pick_att_col(pcols, "pai", "nome_pai")
    col_resp = _pick_att_col(pcols, "responsavel")
    col_alerg = _pick_att_col(pcols, "alergias")
    col_aviso = _pick_att_col(pcols, "aviso")
    col_comorb = _pick_att_col(pcols, "comorbidades_json")
    col_raca = _pick_att_col(pcols, "raca")
    col_est_civil = _pick_att_col(pcols, "estado_civil")
    col_compl = _pick_att_col(pcols, "complemento")

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

    cache_key = None
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
        for c in [
            col_nome, col_cpf, col_cns, col_nasc, col_pront, col_idade,
            col_sexo, col_tel, col_cep, col_log, col_num, col_bai, col_mun, col_uf,
            col_mod, col_stat, col_cid, col_cid2, col_mae, col_pai, col_resp,
            col_alerg, col_aviso, col_comorb, col_raca, col_est_civil, col_compl
        ]:
            if c and c not in fields:
                fields.append(c)

        pac = None

        # 1) por id
        if str(pid).strip() and str(pid).strip().isdigit():
            cur.execute(
                f"SELECT {', '.join(fields)} FROM pacientes WHERE {col_id} = ? LIMIT 1",
                (int(pid),),
            )
            pac = cur.fetchone()

        # 2) por CPF
        if pac is None and col_cpf and cpf_d:
            cur.execute(
                f"""
                SELECT {', '.join(fields)}
                  FROM pacientes
                 WHERE REPLACE(REPLACE(REPLACE(REPLACE({col_cpf},'.',''),'-',''),' ',''),'/','') LIKE ?
                 LIMIT 1
                """,
                (f"%{cpf_d}%",),
            )
            pac = cur.fetchone()

        # 3) por CNS
        if pac is None and col_cns and cns_d:
            cur.execute(
                f"""
                SELECT {', '.join(fields)}
                  FROM pacientes
                 WHERE REPLACE(REPLACE(REPLACE(REPLACE({col_cns},'.',''),'-',''),' ',''),'/','') LIKE ?
                 LIMIT 1
                """,
                (f"%{cns_d}%",),
            )
            pac = cur.fetchone()

        # 4) por nome + nascimento
        if pac is None and col_nome and col_nasc and str(nome).strip() and nasc_iso:
            cur.execute(
                f"""
                SELECT {', '.join(fields)}
                  FROM pacientes
                 WHERE TRIM(LOWER({col_nome})) = TRIM(LOWER(?))
                   AND date({col_nasc}) = date(?)
                 LIMIT 1
                """,
                (str(nome).strip(), nasc_iso),
            )
            pac = cur.fetchone()

        pac_dict = {}
        if pac is not None:
            for i, fname in enumerate(fields):
                try:
                    pac_dict[fname] = pac[i]
                except Exception:
                    pac_dict[fname] = ""

        cache[cache_key] = pac_dict
        pac = pac_dict

    if isinstance(pac, dict) and pac:
        if col_nome and col_nome in pac:
            base_row["pac__nome"] = pac.get(col_nome, "")
        if col_cpf and col_cpf in pac:
            base_row["pac__cpf"] = pac.get(col_cpf, "")
        if col_cns and col_cns in pac:
            base_row["pac__cns"] = pac.get(col_cns, "")
        if col_nasc and col_nasc in pac:
            base_row["pac__nascimento"] = pac.get(col_nasc, "")

        # ✅ AGORA VEM PRO MODAL
        if col_pront and col_pront in pac:
            base_row["pac__prontuario"] = pac.get(col_pront, "")
        if col_idade and col_idade in pac:
            base_row["pac__idade"] = pac.get(col_idade, "")

        if col_sexo and col_sexo in pac:
            base_row["pac__sexo"] = pac.get(col_sexo, "")
        if col_tel and col_tel in pac:
            base_row["pac__telefone"] = pac.get(col_tel, "")
        if col_cep and col_cep in pac:
            base_row["pac__cep"] = pac.get(col_cep, "")
        if col_log and col_log in pac:
            base_row["pac__logradouro"] = pac.get(col_log, "")
        if col_num and col_num in pac:
            base_row["pac__numero"] = pac.get(col_num, "")
        if col_bai and col_bai in pac:
            base_row["pac__bairro"] = pac.get(col_bai, "")
        if col_mun and col_mun in pac:
            base_row["pac__municipio"] = pac.get(col_mun, "")
        if col_uf and col_uf in pac:
            base_row["pac__uf"] = pac.get(col_uf, "")
        if col_mod and col_mod in pac:
            base_row["pac__mod"] = pac.get(col_mod, "")
        if col_stat and col_stat in pac:
            base_row["pac__status"] = pac.get(col_stat, "")
        if col_cid and col_cid in pac:
            base_row["pac__cid"] = pac.get(col_cid, "")
        if col_cid2 and col_cid2 in pac:
            base_row["pac__cid2"] = pac.get(col_cid2, "")
        if col_mae and col_mae in pac:
            base_row["pac__mae"] = pac.get(col_mae, "")
        if col_pai and col_pai in pac:
            base_row["pac__pai"] = pac.get(col_pai, "")
        if col_resp and col_resp in pac:
            base_row["pac__responsavel"] = pac.get(col_resp, "")
        if col_alerg and col_alerg in pac:
            base_row["pac__alergias"] = pac.get(col_alerg, "")
        if col_aviso and col_aviso in pac:
            base_row["pac__aviso"] = pac.get(col_aviso, "")
        if col_comorb and col_comorb in pac:
            base_row["pac__comorbidades_json"] = pac.get(col_comorb, "")
        if col_raca and col_raca in pac:
            base_row["pac__raca"] = pac.get(col_raca, "")
        if col_est_civil and col_est_civil in pac:
            base_row["pac__estado_civil"] = pac.get(col_est_civil, "")
        if col_compl and col_compl in pac:
            base_row["pac__complemento"] = pac.get(col_compl, "")


def _enrich_with_agendamento(conn: sqlite3.Connection, base_row: dict, cache: dict) -> None:
    """
    Encontra o agendamento do MESMO DIA do atendimento (se houver) e injeta campos ag__*
    Match:
      - por paciente_id (se existir em agendamentos)
      - fallback por nome (paciente) + dia
    """
    if not _has_table(conn, "agendamentos"):
        return

    acols = _get_columns(conn, "agendamentos")
    col_pid   = _pick_att_col(acols, "paciente_id", "cidadao_id")
    col_pnome = _pick_att_col(acols, "paciente", "paciente_nome", "nome_paciente", "nome")
    col_ini   = _pick_att_col(acols, "inicio", "datahora", "data_hora", "data_inicio")
    col_prof  = _pick_att_col(acols, "profissional", "profissional_nome", "nome_profissional")
    col_profid = _pick_att_col(acols, "profissional_id", "prof_id")
    col_profcbo = _pick_att_col(acols, "profissional_cbo", "cbo")

    if not col_ini:
        return

    # data do atendimento (iso)
    dt_raw = base_row.get("data_atendimento") or base_row.get("data") or base_row.get("data_iso") or base_row.get("created_at") or ""
    dt_iso = _norm_date_param(str(dt_raw)[:10])  # pega o dia
    if not dt_iso:
        return

    pid = base_row.get("paciente_id") or ""
    nome = base_row.get("paciente_nome") or base_row.get("nome_paciente") or base_row.get("nome") or ""

    # cache key
    key = None
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

        # por paciente_id
        ag = None
        if col_pid and str(pid).strip() and str(pid).strip().isdigit():
            cur.execute(
                f"""
                SELECT *
                  FROM agendamentos
                 WHERE date({col_ini}) = date(?)
                   AND {col_pid} = ?
                 ORDER BY {col_ini} ASC
                 LIMIT 1
                """,
                (dt_iso, int(pid)),
            )
            ag = cur.fetchone()

        # fallback por nome
        if ag is None and col_pnome and str(nome).strip():
            cur.execute(
                f"""
                SELECT *
                  FROM agendamentos
                 WHERE date({col_ini}) = date(?)
                   AND TRIM(LOWER({col_pnome})) = TRIM(LOWER(?))
                 ORDER BY {col_ini} ASC
                 LIMIT 1
                """,
                (dt_iso, str(nome).strip()),
            )
            ag = cur.fetchone()

        # vira dict
        ag_dict: dict = {}
        if ag is not None:
            if isinstance(ag, sqlite3.Row):
                ag_dict = {k: ag[k] for k in ag.keys()}
            else:
                # sem row_factory: tenta via PRAGMA colunas
                # (não costuma ocorrer aqui porque a conexão já usa row_factory no export)
                ag_dict = {}

        cache[key] = ag_dict
        ag = ag_dict

    if isinstance(ag, dict) and ag:
        ini = ag.get(col_ini, "")
        base_row["ag__inicio"] = ini
        base_row["ag__hora"] = str(ini)[11:16] if isinstance(ini, str) and len(ini) >= 16 else ""

        if col_prof and col_prof in ag:
            base_row["ag__profissional"] = ag.get(col_prof, "")
        if col_profid and col_profid in ag:
            base_row["ag__profissional_id"] = ag.get(col_profid, "")
        if col_profcbo and col_profcbo in ag:
            base_row["ag__prof_cbo"] = ag.get(col_profcbo, "")


@registros_bp.get("/exportar_xlsx")
def exportar_xlsx():
    q        = (request.args.get("q") or "").strip()
    prof     = (request.args.get("prof") or "").strip()
    data_ini = (request.args.get("data_ini") or "").strip()
    data_fim = (request.args.get("data_fim") or "").strip()
    status   = (request.args.get("status") or "").strip()
    sexo     = (request.args.get("sexo") or "").strip()
    cid      = (request.args.get("cid") or "").strip()
    cidade   = (request.args.get("cidade") or "").strip()
    try:
        limit = int(request.args.get("limit", 5000))
    except ValueError:
        limit = 5000

    conn = conectar_db()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    sql, params = _montar_query_atendimentos(
        conn,
        q=q, prof=prof,
        data_ini=data_ini, data_fim=data_fim,
        status=status, sexo=sexo, cid=cid, cidade=cidade,
        limit=limit,
    )
    cur.execute(sql, params)
    rows = cur.fetchall()

    data = [_row_to_dict(r) for r in rows]

    # ✅ Enriquecimentos (paciente + agendamento)
    pac_cache: dict = {}
    ag_cache: dict = {}
    for r in data:
        _enrich_with_paciente(conn, r, pac_cache)
        _enrich_with_agendamento(conn, r, ag_cache)

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
# Evoluções PDF (mantém, só usa query robusta de data)
# =============================================================================

def _fmt_cpf(v: str) -> str:
    d = "".join(ch for ch in _safe_str(v) if ch.isdigit())
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return _safe_str(v) or "—"


def _fmt_cns(v: str) -> str:
    d = "".join(ch for ch in _safe_str(v) if ch.isdigit())
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


def _cbo_desc(conn: sqlite3.Connection, cbo: str) -> str:
    code = _safe_str(cbo)
    if not code:
        return "—"
    for tb in ("cbo_funcao", "cbo_descricao"):
        if not _has_table(conn, tb):
            continue
        cols = _get_columns(conn, tb)
        c_codigo = _pick_att_col(cols, "codigo", "cbo", "cod")
        c_desc   = _pick_att_col(cols, "descricao", "desc", "funcao", "nome")
        if not (c_codigo and c_desc):
            continue
        try:
            cur = conn.cursor()
            cur.execute(
                f"SELECT {c_desc} FROM {tb} WHERE TRIM({c_codigo}) = TRIM(?) LIMIT 1",
                (code,),
            )
            r = cur.fetchone()
            if r and r[0]:
                return str(r[0]).strip()
        except Exception:
            pass
    return "—"


def _looks_like_cpf(q: str) -> bool:
    d = re.sub(r"\D+", "", q or "")
    return len(d) == 11


def _looks_like_cns(q: str) -> bool:
    d = re.sub(r"\D+", "", q or "")
    return len(d) == 15


def _paciente_extras(conn: sqlite3.Connection, paciente_id: str) -> dict:
    pid = _safe_str(paciente_id)
    if not pid or not _has_table(conn, "pacientes"):
        return {}

    cols = _get_columns(conn, "pacientes")
    col_id   = _pick_att_col(cols, "id", "paciente_id")
    col_cpf  = _pick_att_col(cols, "cpf", "paciente_cpf", "cpf_cidadao", "cpf_digits")
    col_cns  = _pick_att_col(cols, "cns", "paciente_cns", "cartao_sus", "cns_digits")
    col_nasc = _pick_att_col(cols, "nascimento", "data_nascimento", "dt_nasc", "paciente_nascimento")

    if not col_id:
        return {}

    fields = [col_id]
    if col_cpf:  fields.append(col_cpf)
    if col_cns:  fields.append(col_cns)
    if col_nasc: fields.append(col_nasc)

    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT {', '.join(fields)} FROM pacientes WHERE {col_id} = ? LIMIT 1",
            (int(pid) if pid.isdigit() else pid,),
        )
        row = cur.fetchone()
        if not row:
            return {}

        def getv(idx: int) -> str:
            try:
                return _safe_str(row[idx])
            except Exception:
                return ""

        out: Dict[str, str] = {}
        pos = 1
        if col_cpf:
            out["cpf"] = getv(pos); pos += 1
        if col_cns:
            out["cns"] = getv(pos); pos += 1
        if col_nasc:
            out["nasc"] = getv(pos); pos += 1

        return out
    except Exception:
        return {}


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
                continue

            if cur:
                lines.append(cur)
                cur = w
            else:
                chunk = ""
                for ch in w:
                    cand2 = chunk + ch
                    if stringWidth(cand2, font_name, font_size) <= max_width:
                        chunk = cand2
                    else:
                        if chunk:
                            lines.append(chunk)
                        chunk = ch
                cur = chunk

        if cur:
            lines.append(cur)

    while lines and lines[-1] == "":
        lines.pop()

    return lines or ["—"]


def _draw_header(c: canvas.Canvas, *,
                 paciente_nome: str,
                 idade: str,
                 cpf: str,
                 cns: str,
                 qtd: int,
                 status: str,
                 mod: str,
                 page_w: float,
                 page_h: float):
    margem_x = 18 * mm
    top = page_h - 16 * mm
    header_h = 34 * mm
    w = page_w - 2*margem_x

    c.setFillColor(colors.HexColor("#111827"))
    c.roundRect(margem_x, top - header_h, w, header_h, 8, fill=1, stroke=0)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(margem_x + 10*mm, top - 11*mm, (paciente_nome or "—")[:90])

    c.setFont("Helvetica", 10.5)
    c.setFillColor(colors.HexColor("#E5E7EB"))
    sub = f"Idade: {idade}   |   CPF: {cpf}   |   CNS: {cns}"
    c.drawString(margem_x + 10*mm, top - 18.8*mm, sub)

    def pill(x, y, pw, txt):
        c.setFillColor(colors.HexColor("#0B1220"))
        c.roundRect(x, y, pw, 8.2*mm, 4.5, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#E5E7EB"))
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x + 3.2*mm, y + 2.6*mm, (txt or "—")[:60])

    y_pill = top - 30.5*mm
    pw = 52 * mm
    gap = 4 * mm
    x0 = margem_x + 10*mm

    pill(x0 + 0*(pw+gap), y_pill, pw, f"Registros: {qtd}")
    pill(x0 + 1*(pw+gap), y_pill, pw, f"Status: {status or '—'}")
    pill(x0 + 2*(pw+gap), y_pill, pw, f"Modalidade: {mod or '—'}")

    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.setLineWidth(1)
    c.line(margem_x, top - header_h - 5*mm, page_w - margem_x, top - header_h - 5*mm)


def _draw_registro(c: canvas.Canvas, x: float, y: float, w: float, *,
                   profissional: str,
                   cbo: str,
                   cbo_desc: str,
                   data_atendimento: str,
                   evolucao: str):
    card_h = 44 * mm
    pad_x  = 8 * mm
    pad_y  = 7 * mm

    inner_x = x + pad_x
    inner_w = w - 2*pad_x
    right_x = x + w - pad_x

    c.setFillColor(colors.white)
    c.setStrokeColor(colors.HexColor("#E5E7EB"))
    c.roundRect(x, y - card_h, w, card_h, 8, fill=1, stroke=1)

    # topo (esq = prof+cbo, dir = data)
    top_y = y - pad_y
    dt = (_safe_str(data_atendimento) or "—")[:32]

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors.HexColor("#111827"))
    c.drawRightString(right_x, top_y, dt)

    left_txt = (_safe_str(profissional) or "—")
    cbo_txt  = f"CBO: {(_safe_str(cbo) or '—')} · {(_safe_str(cbo_desc) or '—')}"
    left_full = f"{left_txt}  ·  {cbo_txt}"

    left_font = "Helvetica-Bold"
    left_size = 10.5
    c.setFont(left_font, left_size)
    c.setFillColor(colors.HexColor("#0F172A"))

    reserved_for_date = stringWidth(dt, "Helvetica-Bold", 9) + (6 * mm)
    max_left_w = max(20, inner_w - reserved_for_date)

    s = left_full
    if stringWidth(s, left_font, left_size) > max_left_w:
        while s and stringWidth(s + "…", left_font, left_size) > max_left_w:
            s = s[:-1].rstrip()
        s = (s + "…") if s else "…"
    c.drawString(inner_x, top_y, s)

    sep_y = y - pad_y - 4.8*mm
    c.setStrokeColor(colors.HexColor("#E5E7EB"))
    c.setLineWidth(0.7)
    c.line(inner_x, sep_y, right_x, sep_y)

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors.HexColor("#111827"))
    c.drawString(inner_x, y - pad_y - 11.5*mm, "Evolução:")

    evo_font = "Helvetica"
    evo_size = 9
    line_h   = 4.2 * mm

    text_top_y = y - pad_y - 16.0*mm
    bottom_limit = (y - card_h) + pad_y

    available_h = text_top_y - bottom_limit
    max_lines = int(available_h // line_h)
    max_lines = max(2, min(max_lines, 10))

    c.setFont(evo_font, evo_size)
    c.setFillColor(colors.HexColor("#0B1220"))

    lines = _wrap_text(evolucao, evo_font, evo_size, inner_w)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and stringWidth(last + "…", evo_font, evo_size) > inner_w:
            last = last[:-1].rstrip()
        lines[-1] = (last + "…") if last else "…"

    ly = text_top_y
    for ln in lines:
        c.drawString(inner_x, ly, ln)
        ly -= line_h

    gap_after = 6 * mm
    return (y - card_h - gap_after)


@registros_bp.get("/evolucoes/pdf")
def exportar_evolucoes_pdf():
    # filtros do GRID
    q        = (request.args.get("q") or "").strip()
    prof     = (request.args.get("prof") or "").strip()
    data_ini = (request.args.get("data_ini") or "").strip()
    data_fim = (request.args.get("data_fim") or "").strip()
    status   = (request.args.get("status") or "").strip()
    sexo     = (request.args.get("sexo") or "").strip()
    cid      = (request.args.get("cid") or "").strip()
    cidade   = (request.args.get("cidade") or "").strip()

    # extras
    paciente_id = (request.args.get("paciente_id") or "").strip()

    try:
        limit_pacientes = int(request.args.get("limit_pacientes", 999))
    except ValueError:
        limit_pacientes = 999

    try:
        limit_evos = int(request.args.get("limit_evos", 5000))
    except ValueError:
        limit_evos = 5000

    # normaliza datas (robusto)
    data_ini = _norm_date_param(data_ini)
    data_fim = _norm_date_param(data_fim)

    conn = conectar_db()
    conn.row_factory = sqlite3.Row

    try:
        if not _has_table(conn, "atendimentos"):
            return jsonify({"ok": False, "error": "Tabela 'atendimentos' não existe."}), 500

        a_cols = _get_columns(conn, "atendimentos")

        col_id    = _pick_att_col(a_cols, "id")
        col_pid   = _pick_att_col(a_cols, "paciente_id")
        col_nome  = _pick_att_col(a_cols, "nome", "paciente_nome", "nome_paciente")
        col_data  = _pick_att_col(a_cols, "data_atendimento", "data", "data_iso", "created_at")
        col_evo   = _pick_att_col(a_cols, "evolucao", "evolução", "evol")

        col_prof_id   = _pick_att_col(a_cols, "profissional_id", "prof_id", "id_profissional")
        col_prof_nome = _pick_att_col(a_cols, "nome_profissional", "profissional_nome", "profissional")
        col_cbo       = _pick_att_col(a_cols, "cbo_profissional", "cbo")

        col_mod    = _pick_att_col(a_cols, "mod", "modalidade")
        col_stat   = _pick_att_col(a_cols, "status", "situacao", "comparecimento")
        col_sexo   = _pick_att_col(a_cols, "sexo", "sex")
        col_cid    = _pick_att_col(a_cols, "cid", "cid_principal", "cid10")
        col_cidade = _pick_att_col(a_cols, "cidade", "municipio", "cidade_paciente", "municipio_paciente")

        col_cpf  = _pick_att_col(a_cols, "cpf", "paciente_cpf")
        col_cns  = _pick_att_col(a_cols, "cns", "paciente_cns", "cartao_sus")
        col_nasc = _pick_att_col(a_cols, "nascimento", "paciente_nascimento")

        if not (col_pid and col_nome and col_data and col_evo):
            return jsonify({
                "ok": False,
                "error": "A tabela 'atendimentos' precisa ter: paciente_id, nome, data_atendimento (ou data/created_at) e evolucao."
            }), 500

        select_fields = [
            f"a.{col_pid} AS paciente_id",
            f"a.{col_nome} AS paciente_nome",
            f"a.{col_data} AS data_atendimento",
            f"a.{col_evo}  AS evolucao",
            (f"COALESCE(a.{col_prof_nome}, '') AS profissional_nome" if col_prof_nome else "'' AS profissional_nome"),
            (f"COALESCE(a.{col_cbo}, '')       AS profissional_cbo"  if col_cbo else "'' AS profissional_cbo"),
            (f"COALESCE(a.{col_mod}, '')       AS paciente_mod"      if col_mod else "'' AS paciente_mod"),
            (f"COALESCE(a.{col_stat}, '')      AS paciente_status"   if col_stat else "'' AS paciente_status"),
            (f"COALESCE(a.{col_cpf}, '')       AS paciente_cpf"      if col_cpf else "'' AS paciente_cpf"),
            (f"COALESCE(a.{col_cns}, '')       AS paciente_cns"      if col_cns else "'' AS paciente_cns"),
            (f"COALESCE(a.{col_nasc}, '')      AS paciente_nascimento" if col_nasc else "'' AS paciente_nascimento"),
        ]

        where_parts: list[str] = []
        params: list[Any] = []

        # só evoluções não vazias
        where_parts.append(f"TRIM(COALESCE(a.{col_evo}, '')) <> ''")

        # paciente_id direto
        if paciente_id:
            where_parts.append(f"a.{col_pid} = ?")
            params.append(int(paciente_id) if paciente_id.isdigit() else paciente_id)

        # q
        if q:
            like = f"%{q}%"
            sub = []
            is_cpf = _looks_like_cpf(q)
            is_cns = _looks_like_cns(q)

            if is_cpf and col_cpf:
                sub.append(f"a.{col_cpf} LIKE ?"); params.append(like)
            elif is_cns and col_cns:
                sub.append(f"a.{col_cns} LIKE ?"); params.append(like)
            else:
                sub.append(f"a.{col_nome} LIKE ?"); params.append(like)

            sub.append(f"a.{col_evo} LIKE ?"); params.append(like)

            if col_cid:
                sub.append(f"a.{col_cid} LIKE ?"); params.append(like)
            if col_cidade:
                sub.append(f"a.{col_cidade} LIKE ?"); params.append(like)
            if col_stat:
                sub.append(f"a.{col_stat} LIKE ?"); params.append(like)
            if col_mod:
                sub.append(f"a.{col_mod} LIKE ?"); params.append(like)

            where_parts.append("(" + " OR ".join(sub) + ")")

        # prof
        if prof:
            if prof.isdigit() and col_prof_id:
                where_parts.append(f"a.{col_prof_id} = ?")
                params.append(int(prof))
            elif col_prof_nome:
                where_parts.append(f"a.{col_prof_nome} LIKE ?")
                params.append(f"%{prof}%")

        # datas (ROBUSTO)
        d_expr = _sql_date_expr(f"a.{col_data}")
        if data_ini and data_fim:
            where_parts.append(f"{d_expr} BETWEEN date(?) AND date(?)")
            params.extend([data_ini, data_fim])
        elif data_ini and not data_fim:
            where_parts.append(f"{d_expr} = date(?)")
            params.append(data_ini)
        elif (not data_ini) and data_fim:
            where_parts.append(f"{d_expr} = date(?)")
            params.append(data_fim)

        # status/sexo/cid/cidade
        if status and col_stat:
            where_parts.append(f"a.{col_stat} = ?")
            params.append(status)

        if sexo and col_sexo:
            where_parts.append(f"a.{col_sexo} = ?")
            params.append(sexo)

        if cid and col_cid:
            where_parts.append(f"a.{col_cid} LIKE ?")
            params.append(f"%{cid}%")

        if cidade and col_cidade:
            where_parts.append(f"a.{col_cidade} LIKE ?")
            params.append(f"%{cidade}%")

        sql = f"""
            SELECT {", ".join(select_fields)}
              FROM atendimentos a
             WHERE {" AND ".join(where_parts)}
             ORDER BY a.{col_pid} ASC,
                      {d_expr} DESC,
                      {("a."+col_id+" DESC" if col_id else "a.rowid DESC")}
             LIMIT ?
        """
        params.append(limit_evos)

        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()

        # cache de extras (evita bater DB repetindo)
        extras_cache: Dict[str, dict] = {}

        pacientes: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            pid = str(r["paciente_id"])

            if pid not in pacientes:
                cpf_a  = _safe_str(r["paciente_cpf"])
                cns_a  = _safe_str(r["paciente_cns"])
                nasc_a = _safe_str(r["paciente_nascimento"])

                if (not cpf_a) or (not cns_a) or (not nasc_a):
                    if pid not in extras_cache:
                        extras_cache[pid] = _paciente_extras(conn, pid) or {}
                    ex = extras_cache[pid]
                    cpf_a  = cpf_a  or ex.get("cpf", "")
                    cns_a  = cns_a  or ex.get("cns", "")
                    nasc_a = nasc_a or ex.get("nasc", "")

                pacientes[pid] = {
                    "paciente_id": pid,
                    "nome": _safe_str(r["paciente_nome"]) or "—",
                    "cpf": _fmt_cpf(cpf_a),
                    "cns": _fmt_cns(cns_a),
                    "nasc": nasc_a,
                    "status": _safe_str(r["paciente_status"]) or "—",
                    "mod": _safe_str(r["paciente_mod"]) or "—",
                    "evos": []
                }

            pacientes[pid]["evos"].append({
                "data": _safe_str(r["data_atendimento"]) or "—",
                "prof": _safe_str(r["profissional_nome"]) or "—",
                "cbo":  _safe_str(r["profissional_cbo"]) or "",
                "evo":  _safe_str(r["evolucao"]) or "—",
            })

        pac_list = list(pacientes.values())[:max(1, limit_pacientes)]

        # PDF
        buf = io.BytesIO()
        page_w, page_h = A4
        pdf = canvas.Canvas(buf, pagesize=A4)

        margem_x = 18 * mm
        content_w = page_w - 2 * margem_x

        for pac in pac_list:
            evos = pac["evos"]
            qtd = len(evos)
            idade = _calc_idade_from_iso(pac.get("nasc", ""))

            # ✅ 4 evoluções por página
            chunks = [evos[i:i+4] for i in range(0, len(evos), 4)] or [[]]

            for chunk in chunks:
                _draw_header(
                    pdf,
                    paciente_nome=pac["nome"],
                    idade=idade,
                    cpf=pac["cpf"],
                    cns=pac["cns"],
                    qtd=qtd,
                    status=pac["status"],
                    mod=pac["mod"],
                    page_w=page_w,
                    page_h=page_h,
                )

                y = page_h - (16*mm + 34*mm + 14*mm)
                x = margem_x

                for item in chunk:
                    desc = _cbo_desc(conn, item.get("cbo", ""))
                    y = _draw_registro(
                        pdf, x, y, content_w,
                        profissional=item.get("prof", "—"),
                        cbo=item.get("cbo", ""),
                        cbo_desc=desc,
                        data_atendimento=item.get("data", "—"),
                        evolucao=item.get("evo", "—"),
                    )

                pdf.setFont("Helvetica", 8)
                pdf.setFillColor(colors.HexColor("#64748B"))
                pdf.drawRightString(page_w - margem_x, 12*mm, f"SGD · Evoluções · {date.today().isoformat()}")
                pdf.showPage()

        pdf.save()
        buf.seek(0)

        filename = f"evolucoes_{date.today().isoformat()}.pdf"
        return send_file(
            buf,
            as_attachment=True,
            download_name=filename,
            mimetype="application/pdf",
        )

    finally:
        conn.close()




# ==========================
# BPA-i · Export XLSX (ordem fixa com hífen)
# ==========================

def _fmt_date_bpai_ddmmyyyy(v: str) -> str:
    """
    Retorna SEMPRE DD/MM/YYYY.
    Aceita:
      - ISO: YYYY-MM-DD[...]
      - BR : DD/MM/YYYY[...]
    """
    s = _safe_str(v)
    if not s:
        return ""
    s10 = s[:10]

    # ISO
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s10):
        y, m, d = s10.split("-")
        return f"{d}/{m}/{y}"

    # BR
    if re.match(r"^\d{2}/\d{2}/\d{4}$", s10):
        return s10

    # fallback: tenta limpar e devolver algo legível (mas não inventa)
    return s10

def _calc_idade_no_dia(nasc: str, data_at: str) -> str:
    """
    idade em anos no dia do atendimento (string).
    """
    n = _safe_str(nasc)
    d = _safe_str(data_at)
    if not n or not d:
        return ""
    n_iso = _norm_date_param(n[:10])
    d_iso = _norm_date_param(d[:10])
    try:
        ny, nm, nd = int(n_iso[:4]), int(n_iso[5:7]), int(n_iso[8:10])
        dy, dm, dd = int(d_iso[:4]), int(d_iso[5:7]), int(d_iso[8:10])
        idade = dy - ny - ((dm, dd) < (nm, nd))
        return str(max(0, idade))
    except Exception:
        return ""

def _map_raca_to_codigo(raca: str) -> str:
    """
    Converte texto → código (2 dígitos).
    Padrões comuns do e-SUS / BPA:
      01 BRANCA
      02 PRETA
      03 PARDA
      04 AMARELA
      05 INDIGENA
      99 IGNORADO/SEM INFORMACAO
    Se já vier numérico, mantém com 2 dígitos.
    """
    s = _safe_str(raca).strip().lower()
    if not s:
        return "99"

    # já é número
    d = _only_digits(s)
    if d:
        if len(d) == 1:
            return f"0{d}"
        return d[:2]

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

# ====== CONFIG BPA-i (defaults que você pediu) ======
BPAI_CFG = {
    "prd-ident": "03",        # fixo
    "prd-cnes": "",           # vazio (flexível)
    "prd-ibge": "",           # resolve depois
    "prd-org": "BPA",         # padrão BPA
    "prd-qt": "000001",       # 6 chars
    "prd-caten": "01",        # 2 chars
    "prd-nac": "010",         # padrão
    "prd-lograd-pcnte": "081",# padrão
    # os abaixo ficam vazios por enquanto
    "prd-naut": "",
    "prd-srv": "",
    "prd-clf": "",
    "prd-equipe-seq": "",
    "prd-equipe-area": "",
    "prd-cnpj": "",
    "prd-ine": "",
}

# ✅ ORDEM EXATA (com hífen)
BPAI_COLS = [
    "prd-ident","prd-cnes","prd-cnsmed","prd-cbo","prd-dtaten","prd-pa",
    "prd-cnspac","prd-sexo","prd-ibge","prd-cid","prd-idade","prd-qt",
    "prd-caten","prd-naut","prd-org","prd-nmpac","prd-dtnasc","prd-raca",
    "prd-etnia","prd-nac","prd-srv","prd-clf","prd-equipe-seq","prd-equipe-area",
    "prd-cnpj","prd-cep-pcnte","prd-lograd-pcnte","prd-end-pcnte","prd-compl-pcnte",
    "prd-num-pcnte","prd-bairro-pcnte","prd-ddtel-pcnte","prd-email-pcnte","prd-ine"
]

def _fetch_paciente_dict(conn: sqlite3.Connection, paciente_id: Any) -> dict:
    if not _has_table(conn, "pacientes"):
        return {}
    cols = _get_columns(conn, "pacientes")
    if "id" not in cols:
        return {}
    cur = conn.cursor()
    cur.execute("SELECT * FROM pacientes WHERE id = ? LIMIT 1", (paciente_id,))
    r = cur.fetchone()
    if not r:
        return {}
    if isinstance(r, sqlite3.Row):
        return {k: r[k] for k in r.keys()}
    return {}

def _fetch_prof_dict(conn: sqlite3.Connection, profissional_id: Any) -> dict:
    if not _has_table(conn, "usuarios"):
        return {}
    cols = _get_columns(conn, "usuarios")
    if "id" not in cols:
        return {}
    cur = conn.cursor()
    cur.execute("SELECT * FROM usuarios WHERE id = ? LIMIT 1", (profissional_id,))
    r = cur.fetchone()
    if not r:
        return {}
    if isinstance(r, sqlite3.Row):
        return {k: r[k] for k in r.keys()}
    return {}

def _rows_bpai(conn: sqlite3.Connection, filtros: dict) -> list[dict]:
    """
    Gera 1 linha BPA por PROCEDIMENTO.
    """
    sql, params = _montar_query_atendimentos(
        conn,
        q=filtros.get("q",""),
        prof=filtros.get("prof",""),
        data_ini=filtros.get("data_ini",""),
        data_fim=filtros.get("data_fim",""),
        status=filtros.get("status",""),
        sexo=filtros.get("sexo",""),
        cid=filtros.get("cid",""),
        cidade=filtros.get("cidade",""),
        limit=filtros.get("limit", 50000),
    )
    cur = conn.cursor()
    cur.execute(sql, params)
    at_rows = cur.fetchall()
    at_list = [_row_to_dict(r) for r in at_rows]

    out: list[dict] = []

    for a in at_list:
        atendimento_id = a.get("id")
        paciente_id = a.get("paciente_id")
        prof_id = a.get("profissional_id")

        pac = _fetch_paciente_dict(conn, paciente_id) if paciente_id else {}
        prof = _fetch_prof_dict(conn, prof_id) if prof_id else {}

        # datas (DD/MM/YYYY)
        dt_at_raw = a.get("data_atendimento") or a.get("data") or a.get("created_at") or ""
        dt_aten = _fmt_date_bpai_ddmmyyyy(str(dt_at_raw))

        nasc_raw = pac.get("nascimento") or a.get("nascimento") or ""
        dt_nasc = _fmt_date_bpai_ddmmyyyy(str(nasc_raw))

        # sexo/cid/idade
        sexo_p = _safe_str(pac.get("sexo") or a.get("sexo") or "")
        cid_p  = _safe_str(pac.get("cid")  or a.get("cid")  or "")
        idade  = _safe_str(pac.get("idade") or "") or _calc_idade_no_dia(str(nasc_raw), str(dt_at_raw))

        # endereço/contato
        cep   = _safe_str(pac.get("cep") or "")
        logr  = _safe_str(pac.get("logradouro") or pac.get("rua") or "")
        compl = _safe_str(pac.get("complemento") or "")
        numc  = _safe_str(pac.get("numero_casa") or pac.get("numero") or "")
        bai   = _safe_str(pac.get("bairro") or "")
        tel1  = _safe_str(pac.get("telefone1") or pac.get("telefone") or "")

        # paciente ids
        cnspac = _only_digits(pac.get("cns") or "")
        nmpac  = _safe_str(pac.get("nome") or a.get("nome") or "")
        raca   = _map_raca_to_codigo(pac.get("raca") or "")
        etnia  = _safe_str(pac.get("etnia") or pac.get("perd_etnia") or pac.get("prd_etnia") or "")

        # profissional ids
        cnsmed = _only_digits(prof.get("cns") or a.get("cns_profissional") or "")
        cbo    = _only_digits(prof.get("cbo") or a.get("cbo_profissional") or "")

        # procedimentos
        proc_list: list[tuple[str,str]] = []
        if _has_table(conn, "atendimento_procedimentos") and atendimento_id:
            cur2 = conn.cursor()
            cur2.execute(
                "SELECT COALESCE(codigo_sigtap,'') AS codigo, COALESCE(procedimento,'') AS nome "
                "FROM atendimento_procedimentos WHERE atendimento_id = ? ORDER BY id ASC",
                (atendimento_id,),
            )
            for rr in cur2.fetchall():
                codigo = rr["codigo"] if isinstance(rr, sqlite3.Row) else rr[0]
                nomep  = rr["nome"] if isinstance(rr, sqlite3.Row) else rr[1]
                if _safe_str(codigo) or _safe_str(nomep):
                    proc_list.append((_safe_str(codigo), _safe_str(nomep)))

        if not proc_list:
            proc_list.append((_safe_str(a.get("codigo_sigtap") or ""), _safe_str(a.get("procedimento") or "")))

        for (codigo_sigtap, nome_proc) in proc_list:
            row = {k: "" for k in BPAI_COLS}

            # ===== Defaults/padrões exigidos =====
            row["prd-ident"] = BPAI_CFG["prd-ident"]      # "03"
            row["prd-cnes"]  = BPAI_CFG["prd-cnes"]       # vazio
            row["prd-ibge"]  = BPAI_CFG["prd-ibge"]       # vazio (por enquanto)
            row["prd-qt"]    = BPAI_CFG["prd-qt"]         # "000001"
            row["prd-caten"] = BPAI_CFG["prd-caten"]      # "01"
            row["prd-org"]   = BPAI_CFG["prd-org"]        # "BPA"
            row["prd-nac"]   = BPAI_CFG["prd-nac"]        # "010"
            row["prd-lograd-pcnte"] = BPAI_CFG["prd-lograd-pcnte"]  # "081"
            row["prd-email-pcnte"]  = ""                  # vazio

            # ===== Variáveis do atendimento/paciente/prof =====
            row["prd-cnsmed"] = cnsmed
            row["prd-cbo"]    = cbo
            row["prd-dtaten"] = dt_aten

            # prd-pa = código do procedimento (sigtap)
            row["prd-pa"]     = codigo_sigtap

            row["prd-cnspac"] = cnspac
            row["prd-sexo"]   = (_safe_str(sexo_p)[:1].upper() if sexo_p else "")
            row["prd-cid"]    = cid_p
            # prd-idade como NÚMERO (Excel)
            idade_num = None
            try:
                idade_num = int(str(idade).strip())
            except Exception:
                idade_num = None

            row["prd-idade"] = idade_num if idade_num is not None else ""


            row["prd-naut"]   = BPAI_CFG["prd-naut"]      # vazio
            row["prd-nmpac"]  = nmpac
            row["prd-dtnasc"] = dt_nasc
            row["prd-raca"]   = raca
            row["prd-etnia"]  = etnia

            # campos que você pediu vazio por enquanto
            row["prd-srv"]          = ""  # poderia ser nome_proc, mas você pediu vazio
            row["prd-clf"]          = ""
            row["prd-equipe-seq"]   = ""
            row["prd-equipe-area"]  = ""
            row["prd-cnpj"]         = ""
            row["prd-ine"]          = ""

            # endereço/contato
            row["prd-cep-pcnte"]      = _only_digits(cep)
            row["prd-end-pcnte"]      = logr  # aqui é LOGRADOURO (como você pediu)
            row["prd-compl-pcnte"]    = compl
            row["prd-num-pcnte"]      = numc
            row["prd-bairro-pcnte"]   = bai
            row["prd-ddtel-pcnte"]    = _only_digits(tel1)

            out.append(row)

    return out


@registros_bp.get("/exportar_bpai_xlsx")
def exportar_bpai_xlsx():
    """
    Exporta XLSX com colunas BPA-i NA ORDEM e NOMES com hífen.
    """
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
    conn.row_factory = sqlite3.Row
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
