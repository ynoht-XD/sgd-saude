# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple

from flask import session

from db import conectar_db


# =============================================================================
# CONSTANTES
# =============================================================================

_PT_WEEKDAYS = [
    "Segunda",
    "Terça",
    "Quarta",
    "Quinta",
    "Sexta",
    "Sábado",
    "Domingo",
]

DEFAULT_TAGS = [
    ("diabetico", "Diabético"),
    ("bpc", "BPC"),
    ("cardiopata", "Cardiopata"),
    ("obeso", "Obeso"),
    ("hipertenso", "Hipertenso"),
    ("cadeirante", "Cadeirante"),
    ("surdo", "Surdo"),
    ("cego", "Cego"),
]

_UPPER_FIELDS = {
    "nome",
    "mae",
    "pai",
    "responsavel",
    "logradouro",
    "rua",
    "bairro",
    "municipio",
    "cidade",
    "complemento",
    "estado_civil",
    "orgao_rg",
    "orgao_rg_responsavel",
    "status",
    "mod",
    "cid",
    "cid2",
    "raca",
    "codigo_logradouro",
    "terapeuta",
    "cbo",
    "cbo_nome",
}


# =============================================================================
# MULTI-CLÍNICA
# =============================================================================

def current_clinica_id() -> int:
    """
    Retorna a clínica atual da sessão.
    """
    clinica_id = session.get("clinica_id")

    try:
        return int(clinica_id)
    except Exception:
        return 1


# =============================================================================
# CONEXÃO / FETCH
# =============================================================================

def get_conn():
    """
    Conexão padrão PostgreSQL.
    Compatível local + Render.
    """
    conn = conectar_db()

    try:
        from psycopg.rows import dict_row
        conn.row_factory = dict_row
    except Exception:
        pass

    return conn


def fetchone_dict(cur) -> Optional[dict]:
    row = cur.fetchone()

    if row is None:
        return None

    if isinstance(row, dict):
        return dict(row)

    try:
        return dict(row)
    except Exception:
        cols = [c[0] for c in cur.description] if cur.description else []
        return dict(zip(cols, row))


def fetchall_dicts(cur) -> List[dict]:
    rows = cur.fetchall() or []

    out: List[dict] = []

    cols = [c[0] for c in cur.description] if cur.description else []

    for row in rows:
        if isinstance(row, dict):
            out.append(dict(row))
        else:
            try:
                out.append(dict(row))
            except Exception:
                out.append(dict(zip(cols, row)))

    return out


# =============================================================================
# SCHEMA / INTROSPECÇÃO
# =============================================================================

def has_table(conn, table: str) -> bool:
    cur = conn.cursor()

    cur.execute(
        """
        SELECT 1
          FROM information_schema.tables
         WHERE table_schema = 'public'
           AND table_name = %s
         LIMIT 1;
        """,
        (table,),
    )

    return cur.fetchone() is not None


def table_columns(conn, table: str) -> set[str]:
    cur = conn.cursor()

    cur.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = %s
         ORDER BY ordinal_position;
        """,
        (table,),
    )

    return {r["column_name"] for r in fetchall_dicts(cur)}


def ensure_column(
    conn,
    table: str,
    col: str,
    ddl_type: str,
    default_sql: str | None = None,
):
    sql = f"""
        ALTER TABLE {table}
        ADD COLUMN IF NOT EXISTS {col} {ddl_type}
    """

    if default_sql is not None:
        sql += f" DEFAULT {default_sql}"

    sql += ";"

    cur = conn.cursor()
    cur.execute(sql)
    conn.commit()


def ensure_pacientes_schema(conn):
    """
    Schema principal pacientes.
    Multi-clínica ready.
    """

    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pacientes (
            id SERIAL PRIMARY KEY
        );
    """)

    conn.commit()

    # =========================================================================
    # MULTI-CLÍNICA
    # =========================================================================

    ensure_column(conn, "pacientes", "clinica_id", "INTEGER", "1")

    # =========================================================================
    # BASE
    # =========================================================================

    ensure_column(conn, "pacientes", "prontuario", "TEXT", "''")
    ensure_column(conn, "pacientes", "nome", "TEXT", "''")
    ensure_column(conn, "pacientes", "nascimento", "TEXT", "''")
    ensure_column(conn, "pacientes", "idade", "INTEGER", "NULL")
    ensure_column(conn, "pacientes", "sexo", "TEXT", "''")
    ensure_column(conn, "pacientes", "status", "TEXT", "''")
    ensure_column(conn, "pacientes", "mod", "TEXT", "''")
    ensure_column(conn, "pacientes", "cid", "TEXT", "''")
    ensure_column(conn, "pacientes", "cid2", "TEXT", "''")

    # =========================================================================
    # ENDEREÇO
    # =========================================================================

    ensure_column(conn, "pacientes", "rua", "TEXT", "''")
    ensure_column(conn, "pacientes", "logradouro", "TEXT", "''")
    ensure_column(conn, "pacientes", "numero", "TEXT", "''")
    ensure_column(conn, "pacientes", "numero_casa", "TEXT", "''")
    ensure_column(conn, "pacientes", "bairro", "TEXT", "''")
    ensure_column(conn, "pacientes", "cep", "TEXT", "''")
    ensure_column(conn, "pacientes", "cidade", "TEXT", "''")
    ensure_column(conn, "pacientes", "municipio", "TEXT", "''")
    ensure_column(conn, "pacientes", "uf", "TEXT", "''")
    ensure_column(conn, "pacientes", "complemento", "TEXT", "''")
    ensure_column(conn, "pacientes", "codigo_logradouro", "TEXT", "''")

    # =========================================================================
    # DOCUMENTOS
    # =========================================================================

    ensure_column(conn, "pacientes", "cpf", "TEXT", "''")
    ensure_column(conn, "pacientes", "cns", "TEXT", "''")
    ensure_column(conn, "pacientes", "telefone", "TEXT", "''")
    ensure_column(conn, "pacientes", "telefone1", "TEXT", "''")
    ensure_column(conn, "pacientes", "telefone2", "TEXT", "''")
    ensure_column(conn, "pacientes", "telefone3", "TEXT", "''")
    ensure_column(conn, "pacientes", "email", "TEXT", "''")
    ensure_column(conn, "pacientes", "rg", "TEXT", "''")
    ensure_column(conn, "pacientes", "orgao_rg", "TEXT", "''")
    ensure_column(conn, "pacientes", "estado_civil", "TEXT", "''")
    ensure_column(conn, "pacientes", "nis", "TEXT", "''")
    ensure_column(conn, "pacientes", "raca", "TEXT", "''")

    # =========================================================================
    # RESPONSÁVEIS
    # =========================================================================

    ensure_column(conn, "pacientes", "nome_mae", "TEXT", "''")
    ensure_column(conn, "pacientes", "mae", "TEXT", "''")
    ensure_column(conn, "pacientes", "cpf_mae", "TEXT", "''")
    ensure_column(conn, "pacientes", "rg_mae", "TEXT", "''")
    ensure_column(conn, "pacientes", "rg_ssp_mae", "TEXT", "''")
    ensure_column(conn, "pacientes", "nis_mae", "TEXT", "''")

    ensure_column(conn, "pacientes", "nome_pai", "TEXT", "''")
    ensure_column(conn, "pacientes", "pai", "TEXT", "''")
    ensure_column(conn, "pacientes", "cpf_pai", "TEXT", "''")
    ensure_column(conn, "pacientes", "rg_pai", "TEXT", "''")
    ensure_column(conn, "pacientes", "rg_ssp_pai", "TEXT", "''")

    ensure_column(conn, "pacientes", "responsavel", "TEXT", "''")
    ensure_column(conn, "pacientes", "cpf_responsavel", "TEXT", "''")
    ensure_column(conn, "pacientes", "rg_responsavel", "TEXT", "''")
    ensure_column(conn, "pacientes", "orgao_rg_responsavel", "TEXT", "''")

    # =========================================================================
    # EXTRAS
    # =========================================================================

    ensure_column(conn, "pacientes", "end_prontuario", "TEXT", "''")
    ensure_column(conn, "pacientes", "alergias", "TEXT", "''")
    ensure_column(conn, "pacientes", "aviso", "TEXT", "''")
    ensure_column(conn, "pacientes", "comorbidades_json", "TEXT", "'[]'")

    ensure_column(conn, "pacientes", "terapeuta", "TEXT", "''")
    ensure_column(conn, "pacientes", "cbo", "TEXT", "''")
    ensure_column(conn, "pacientes", "cbo_nome", "TEXT", "''")

    # =========================================================================
    # ÍNDICES OTIMIZADOS MULTI-CLÍNICA
    # =========================================================================

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_pacientes_clinica
        ON pacientes(clinica_id);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_pacientes_clinica_nome
        ON pacientes(clinica_id, nome);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_pacientes_clinica_cpf
        ON pacientes(clinica_id, cpf);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_pacientes_clinica_prontuario
        ON pacientes(clinica_id, prontuario);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_pacientes_clinica_cid
        ON pacientes(clinica_id, cid);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_pacientes_clinica_cidade
        ON pacientes(clinica_id, municipio);
    """)

    conn.commit()


# =============================================================================
# NORMALIZAÇÃO
# =============================================================================

def to_upper(x: Any) -> str:
    if x is None:
        return ""
    return str(x).strip().upper()


def upperize_payload(dados: dict) -> dict:
    out = {}

    for k, v in (dados or {}).items():
        out[k] = to_upper(v) if k in _UPPER_FIELDS else v

    return out


# =============================================================================
# DATAS
# =============================================================================

def calc_idade(nasc_str: Any) -> Optional[int]:
    if not nasc_str:
        return None

    nasc_str = str(nasc_str).strip()

    fmts = (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
    )

    dt = None

    for f in fmts:
        try:
            dt = datetime.strptime(nasc_str, f).date()
            break
        except Exception:
            continue

    if not dt:
        s = "".join(ch for ch in nasc_str if ch.isdigit())

        try:
            if len(s) == 8:
                if int(s[:4]) > 1900:
                    dt = date(int(s[:4]), int(s[4:6]), int(s[6:8]))
                else:
                    dt = date(int(s[4:8]), int(s[2:4]), int(s[0:2]))
        except Exception:
            return None

    if not dt:
        return None

    today = date.today()

    anos = (
        today.year
        - dt.year
        - ((today.month, today.day) < (dt.month, dt.day))
    )

    return max(0, anos)


def parse_dt_flex(s: Any) -> Optional[datetime]:
    if not s:
        return None

    s = str(s).strip()

    if not s:
        return None

    s2 = s.replace("Z", "").strip()

    fmts = (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
    )

    for fmt in fmts:
        try:
            return datetime.strptime(s2, fmt)
        except Exception:
            pass

    try:
        return datetime.fromisoformat(s2)
    except Exception:
        pass

    return None


# =============================================================================
# JSON
# =============================================================================

def json_list(v: Any) -> List[str]:
    if v is None:
        return []

    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]

    s = str(v).strip()

    if not s:
        return []

    try:
        j = json.loads(s)

        if isinstance(j, list):
            return [str(x).strip() for x in j if str(x).strip()]
    except Exception:
        pass

    return [p.strip() for p in s.split(",") if p.strip()]


# =============================================================================
# PROFISSIONAIS / CBO
# =============================================================================

_SPLIT_PROF_RE = re.compile(
    r"\s*(?:,|;|/|\||\+|&|\be\b)\s*",
    re.IGNORECASE,
)


def split_profissionais(raw: str) -> list[str]:
    if not raw:
        return []

    s = str(raw).strip()

    if not s:
        return []

    partes = [
        p.strip()
        for p in _SPLIT_PROF_RE.split(s)
        if p and p.strip()
    ]

    seen = set()
    out = []

    for p in partes:
        k = p.upper()

        if k in seen:
            continue

        seen.add(k)
        out.append(p)

    return out


def map_cbo_por_profissionais(nomes: list[str]) -> dict[str, str]:
    if not nomes:
        return {}

    clinica_id = current_clinica_id()

    with get_conn() as conn:
        if not has_table(conn, "usuarios"):
            return {}

        cols = table_columns(conn, "usuarios")

        if "nome" not in cols or "cbo" not in cols:
            return {}

        cur = conn.cursor()

        if "clinica_id" in cols:
            cur.execute("""
                SELECT nome, cbo
                  FROM usuarios
                 WHERE clinica_id = %s
                   AND TRIM(COALESCE(nome,'')) <> ''
            """, (clinica_id,))
        else:
            cur.execute("""
                SELECT nome, cbo
                  FROM usuarios
                 WHERE TRIM(COALESCE(nome,'')) <> ''
            """)

        rows = fetchall_dicts(cur)

    nomes_set = {n.upper().strip() for n in nomes}

    m = {}

    for r in rows:
        nm = (r.get("nome") or "").strip()
        cbo = (r.get("cbo") or "").strip()

        if nm and nm.upper() in nomes_set:
            m[nm.upper()] = cbo

    return m


def enriquecer_com_prof_cbo(a: dict, cbo_map: dict[str, str]) -> dict:
    prof_raw = a.get("profissional") or ""

    profs = split_profissionais(prof_raw)

    cbos: list[str] = []

    seen = set()

    for p in profs:
        cbo = (cbo_map.get(p.upper(), "") or "").strip()

        if cbo and cbo not in seen:
            seen.add(cbo)
            cbos.append(cbo)

    a["profissionais_lista"] = profs
    a["cbo_lista"] = cbos
    a["cbo_str"] = ", ".join(cbos) if cbos else ""

    return a


# =============================================================================
# FILTROS
# =============================================================================

def where_and_params(args, cols: set) -> Tuple[str, List[Any]]:
    where: List[str] = []
    params: List[Any] = []

    # =========================================================================
    # MULTI-CLÍNICA
    # =========================================================================

    if "clinica_id" in cols:
        where.append("clinica_id = %s")
        params.append(current_clinica_id())

    pront = (args.get("prontuario") or "").strip()

    if pront and "prontuario" in cols:
        where.append("prontuario = %s")
        params.append(pront)

    nome = (args.get("nome") or "").strip()

    if nome and "nome" in cols:
        where.append("nome ILIKE %s")
        params.append(f"%{nome}%")

    sexo = (args.get("sexo") or "").strip().upper()

    if sexo in ("M", "F") and "sexo" in cols:
        where.append("sexo = %s")
        params.append(sexo)

    status = (args.get("status") or "").strip()

    if status and "status" in cols:
        where.append("status = %s")
        params.append(status)

    mod = (args.get("mod") or "").strip()

    if mod and "mod" in cols:
        where.append("mod ILIKE %s")
        params.append(f"%{mod}%")

    cid = (args.get("cid") or "").strip()

    if cid and ("cid" in cols or "cid2" in cols):
        if "cid" in cols and "cid2" in cols:
            where.append("(cid ILIKE %s OR cid2 ILIKE %s)")
            params.extend([f"%{cid}%", f"%{cid}%"])

        elif "cid" in cols:
            where.append("cid ILIKE %s")
            params.append(f"%{cid}%")

        else:
            where.append("cid2 ILIKE %s")
            params.append(f"%{cid}%")

    clause = " WHERE " + " AND ".join(where) if where else ""

    return clause, params


# =============================================================================
# LISTAGEM PACIENTES
# =============================================================================

def enriquecer_agendamento_row(a: dict) -> dict:
    dt_ini = parse_dt_flex(a.get("inicio"))
    dt_fim = parse_dt_flex(a.get("fim"))

    if dt_ini:
        a["dia_semana"] = _PT_WEEKDAYS[dt_ini.weekday()]
        a["hora_ini"] = dt_ini.strftime("%H:%M")
        a["data_br"] = dt_ini.strftime("%d/%m/%Y")
    else:
        a["dia_semana"] = ""
        a["hora_ini"] = ""
        a["data_br"] = ""

    a["hora_fim"] = dt_fim.strftime("%H:%M") if dt_fim else ""
    return a


def get_primeiro_agendamento_por_paciente() -> dict:
    return {}


def fetch_agendamentos_por_paciente(nome_paciente: str, clinica_id: int | None = None) -> dict:
    return {
        "agds_upcoming": [],
        "agds_all": [],
        "series_resumo": [],
        "total_agds": 0,
        "total_upcoming": 0,
    }


def fetch_pacientes_list(args=None):
    with get_conn() as conn:
        ensure_pacientes_schema(conn)

        cols = table_columns(conn, "pacientes")

        base_cols = [
            "id",
            "clinica_id",
            "prontuario",
            "nome",
            "nascimento",
            "idade",
            "sexo",
            "status",
            "mod",
            "cid",
            "cid2",
            "cpf",
            "cns",
            "telefone",
            "telefone1",
            "nome_mae",
            "mae",
            "nome_pai",
            "pai",
            "rua",
            "logradouro",
            "numero",
            "numero_casa",
            "bairro",
            "cep",
            "cidade",
            "municipio",
            "uf",
            "end_prontuario",
            "alergias",
            "aviso",
            "comorbidades_json",
        ]

        select_cols = [c for c in base_cols if c in cols]

        if not select_cols:
            select_cols = ["*"]

        if args is None:
            clause, params = "", []
        else:
            clause, params = where_and_params(args, cols)

        cur = conn.cursor()

        cur.execute(
            f"""
            SELECT {', '.join(select_cols)}
              FROM pacientes
              {clause}
             ORDER BY id DESC
            """,
            params,
        )

        rows = fetchall_dicts(cur)

    return rows


# =============================================================================
# FORMATOS
# =============================================================================

def headers_padrao():
    return [
        "ID",
        "Prontuário",
        "Nome",
        "Nascimento",
        "Sexo",
        "Status",
        "Modalidade",
        "CID",
    ]


def fmt(v: Any) -> str:
    s = "" if v is None else str(v).strip()
    return s if s else "—"


def join_addr(p: dict) -> str:
    parts = []

    rua = (p.get("rua") or p.get("logradouro") or "").strip()
    num = (p.get("numero") or p.get("numero_casa") or "").strip()
    bairro = (p.get("bairro") or "").strip()
    cep = (p.get("cep") or "").strip()
    cid = (p.get("cidade") or p.get("municipio") or "").strip()
    uf = (p.get("uf") or "").strip()

    if rua:
        parts.append(rua)

    if num:
        parts.append(f"Nº {num}")

    if bairro:
        parts.append(bairro)

    if cep:
        parts.append(f"CEP {cep}")

    if cid:
        parts.append(cid)

    if uf:
        parts.append(uf)

    return " • ".join(parts) if parts else "—"


def tags_human(p: dict) -> str:
    raw = p.get("comorbidades_json")

    keys = json_list(raw)

    if not keys:
        return "—"

    mapa = dict(DEFAULT_TAGS)

    labels = [mapa.get(k, k) for k in keys]
    labels = [x for x in labels if str(x).strip()]

    return ", ".join(labels) if labels else "—"