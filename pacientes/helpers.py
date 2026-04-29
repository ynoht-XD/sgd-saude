# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple

from db import conectar_db


# =============================================================================
# CONSTANTES
# =============================================================================

_PT_WEEKDAYS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

DEFAULT_TAGS = [
    ("diabetico",  "Diabético"),
    ("bpc",        "BPC"),
    ("cardiopata", "Cardiopata"),
    ("obeso",      "Obeso"),
    ("hipertenso", "Hipertenso"),
    ("cadeirante", "Cadeirante"),
    ("surdo",      "Surdo"),
    ("cego",       "Cego"),
]

_UPPER_FIELDS = {
    "nome", "mae", "pai", "responsavel",
    "logradouro", "rua", "bairro", "municipio", "cidade", "complemento",
    "estado_civil",
    "orgao_rg", "orgao_rg_responsavel",
    "status", "mod", "cid", "cid2", "raca",
    "codigo_logradouro",
    "terapeuta", "cbo", "cbo_nome",
}


# =============================================================================
# CONEXÃO / FETCH
# =============================================================================

def get_conn():
    """
    Conexão padrão do módulo pacientes.
    Já tenta habilitar row_factory em dict quando disponível.
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


def ensure_column(conn, table: str, col: str, ddl_type: str, default_sql: str | None = None) -> None:
    """
    Adiciona coluna se não existir.
    Exemplo:
        ensure_column(conn, "pacientes", "cpf", "TEXT", "''")
    """
    sql = f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {ddl_type}"
    if default_sql is not None:
        sql += f" DEFAULT {default_sql}"
    sql += ";"

    cur = conn.cursor()
    cur.execute(sql)
    conn.commit()


def ensure_pacientes_schema(conn) -> None:
    """
    Garante a tabela pacientes e as colunas mínimas do módulo.
    Tudo idempotente.
    """
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pacientes (
            id SERIAL PRIMARY KEY
        );
    """)
    conn.commit()

    # Base
    ensure_column(conn, "pacientes", "prontuario", "TEXT", "''")
    ensure_column(conn, "pacientes", "nome", "TEXT", "''")
    ensure_column(conn, "pacientes", "nascimento", "TEXT", "''")
    ensure_column(conn, "pacientes", "idade", "INTEGER", "NULL")
    ensure_column(conn, "pacientes", "sexo", "TEXT", "''")
    ensure_column(conn, "pacientes", "status", "TEXT", "''")
    ensure_column(conn, "pacientes", "mod", "TEXT", "''")
    ensure_column(conn, "pacientes", "cid", "TEXT", "''")
    ensure_column(conn, "pacientes", "cid2", "TEXT", "''")

    # Endereço
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

    # Documentos / contato
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

    # Família / responsável
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

    # Card / extras
    ensure_column(conn, "pacientes", "end_prontuario", "TEXT", "''")
    ensure_column(conn, "pacientes", "alergias", "TEXT", "''")
    ensure_column(conn, "pacientes", "aviso", "TEXT", "''")
    ensure_column(conn, "pacientes", "comorbidades_json", "TEXT", "'[]'")

    # Apoio agenda
    ensure_column(conn, "pacientes", "terapeuta", "TEXT", "''")
    ensure_column(conn, "pacientes", "cbo", "TEXT", "''")
    ensure_column(conn, "pacientes", "cbo_nome", "TEXT", "''")

    # Índices
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pacientes_nome ON pacientes(nome);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pacientes_cpf ON pacientes(cpf);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pacientes_prontuario ON pacientes(prontuario);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pacientes_cid ON pacientes(cid);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pacientes_cid2 ON pacientes(cid2);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pacientes_cep ON pacientes(cep);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pacientes_municipio ON pacientes(municipio);")
    conn.commit()


# =============================================================================
# NORMALIZAÇÃO / DATAS
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


def calc_idade(nasc_str: Any) -> Optional[int]:
    if not nasc_str:
        return None

    nasc_str = str(nasc_str).strip()
    fmts = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d")
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
    anos = today.year - dt.year - ((today.month, today.day) < (dt.month, dt.day))
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
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
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

    m = re.search(r"(\d{4})-(\d{2})-(\d{2}).*?(\d{2}):(\d{2})", s2)
    if m:
        try:
            y, mo, d, hh, mm = map(int, m.groups())
            return datetime(y, mo, d, hh, mm, 0)
        except Exception:
            return None

    m2 = re.search(r"(\d{2})/(\d{2})/(\d{4}).*?(\d{2}):(\d{2})", s2)
    if m2:
        try:
            d, mo, y, hh, mm = map(int, m2.groups())
            return datetime(y, mo, d, hh, mm, 0)
        except Exception:
            return None

    return None


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

_SPLIT_PROF_RE = re.compile(r"\s*(?:,|;|/|\||\+|&|\be\b)\s*", re.IGNORECASE)


def split_profissionais(raw: str) -> list[str]:
    if not raw:
        return []
    s = str(raw).strip()
    if not s:
        return []

    partes = [p.strip() for p in _SPLIT_PROF_RE.split(s) if p and p.strip()]
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

    with get_conn() as conn:
        if not has_table(conn, "usuarios"):
            return {}

        cols = table_columns(conn, "usuarios")
        if "nome" not in cols or "cbo" not in cols:
            return {}

        cur = conn.cursor()
        cur.execute(
            """
            SELECT nome, cbo
              FROM usuarios
             WHERE TRIM(COALESCE(nome,'')) <> ''
            """
        )
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
# AGENDAMENTOS RELACIONADOS AO PACIENTE
# =============================================================================

def get_primeiro_agendamento_por_paciente() -> dict:
    with get_conn() as conn:
        if not has_table(conn, "agendamentos"):
            return {}

        cols_ag = table_columns(conn, "agendamentos")
        if "paciente" not in cols_ag or "inicio" not in cols_ag:
            return {}

        has_fim = "fim" in cols_ag
        has_prof = "profissional" in cols_ag

        sel = ["paciente", "inicio"]
        sel.append("fim" if has_fim else "NULL::text AS fim")
        sel.append("profissional" if has_prof else "''::text AS profissional")

        cur = conn.cursor()
        cur.execute(f"""
            SELECT {", ".join(sel)}
              FROM agendamentos
             WHERE TRIM(COALESCE(paciente,'')) <> ''
        """)
        rows = fetchall_dicts(cur)

    now = datetime.now()
    por_paciente: dict[str, dict] = {}
    todos_profissionais: list[str] = []

    for r in rows:
        pac = (r.get("paciente") or "").strip()
        if not pac:
            continue
        k = pac.upper()

        por_paciente.setdefault(k, {
            "slots_by_key": {},
            "terapeutas": set(),
        })

        profs = split_profissionais(r.get("profissional") or "")
        for p in profs:
            por_paciente[k]["terapeutas"].add(p)
            todos_profissionais.append(p)

        dt_ini = parse_dt_flex(r.get("inicio"))
        if not dt_ini:
            continue

        slot = enriquecer_agendamento_row({
            "inicio": r.get("inicio"),
            "fim": r.get("fim"),
        })

        dia = (slot.get("dia_semana") or "").strip()
        hi = (slot.get("hora_ini") or "").strip()
        hf = (slot.get("hora_fim") or "").strip()
        if not dia or not hi:
            continue

        key_slot = f"{dia}|{hi}|{hf}"
        entry = por_paciente[k]["slots_by_key"].get(key_slot)

        if entry is None:
            por_paciente[k]["slots_by_key"][key_slot] = {"slot": slot, "dt": dt_ini}
        else:
            dt_old = entry["dt"]
            old_future = dt_old >= now
            new_future = dt_ini >= now

            if old_future and new_future:
                if dt_ini < dt_old:
                    por_paciente[k]["slots_by_key"][key_slot] = {"slot": slot, "dt": dt_ini}
            elif (not old_future) and new_future:
                por_paciente[k]["slots_by_key"][key_slot] = {"slot": slot, "dt": dt_ini}
            elif (not old_future) and (not new_future):
                if dt_ini < dt_old:
                    por_paciente[k]["slots_by_key"][key_slot] = {"slot": slot, "dt": dt_ini}

    uniq_profs, seen = [], set()
    for p in todos_profissionais:
        up = p.upper()
        if up not in seen:
            seen.add(up)
            uniq_profs.append(p)

    cbo_map = map_cbo_por_profissionais(uniq_profs)
    order_dia = {d: i for i, d in enumerate(_PT_WEEKDAYS)}

    resultado: dict[str, dict] = {}
    for pac, info in por_paciente.items():
        terapeutas = sorted(info["terapeutas"])

        cbos: list[str] = []
        seen_cbo = set()
        for t in terapeutas:
            cbo = (cbo_map.get(t.upper(), "") or "").strip()
            if cbo and cbo not in seen_cbo:
                seen_cbo.add(cbo)
                cbos.append(cbo)

        slots = [v["slot"] for v in info["slots_by_key"].values()]
        slots.sort(key=lambda s: (
            order_dia.get(s.get("dia_semana", ""), 99),
            s.get("hora_ini", "99:99")
        ))

        prox_slot = None
        prox_dt = None
        for entry in info["slots_by_key"].values():
            dt_ini = entry["dt"]
            if dt_ini >= now and (prox_dt is None or dt_ini < prox_dt):
                prox_dt = dt_ini
                prox_slot = entry["slot"]

        agenda_partes = []
        for s in slots:
            dia = s.get("dia_semana", "")
            hi = s.get("hora_ini", "")
            hf = s.get("hora_fim", "")
            if hf:
                agenda_partes.append(f"{dia[:3].upper()} {hi}–{hf}")
            else:
                agenda_partes.append(f"{dia[:3].upper()} {hi}")

        prox = prox_slot or {}

        resultado[pac] = {
            "dia_semana": prox.get("dia_semana", ""),
            "hora_ini": prox.get("hora_ini", ""),
            "hora_fim": prox.get("hora_fim", ""),
            "agenda_lista": slots,
            "agenda_str": "; ".join(agenda_partes),
            "terapeutas": terapeutas,
            "cbo_lista": cbos,
            "terapeuta_str": " / ".join(terapeutas),
            "cbo_str": ", ".join(cbos),
        }

    return resultado


def fetch_agendamentos_por_paciente(nome_paciente: str) -> dict:
    if not nome_paciente:
        return {
            "agds_upcoming": [],
            "agds_all": [],
            "series_resumo": [],
            "total_agds": 0,
            "total_upcoming": 0,
        }

    with get_conn() as conn:
        if not has_table(conn, "agendamentos"):
            return {
                "agds_upcoming": [],
                "agds_all": [],
                "series_resumo": [],
                "total_agds": 0,
                "total_upcoming": 0,
            }

        cols_ag = table_columns(conn, "agendamentos")
        if "paciente" not in cols_ag or "inicio" not in cols_ag:
            return {
                "agds_upcoming": [],
                "agds_all": [],
                "series_resumo": [],
                "total_agds": 0,
                "total_upcoming": 0,
            }

        sel = ["id", "paciente", "inicio"]
        sel.append("fim" if "fim" in cols_ag else "NULL::text AS fim")
        sel.append("profissional" if "profissional" in cols_ag else "''::text AS profissional")
        sel.append("observacao" if "observacao" in cols_ag else "''::text AS observacao")
        sel.append("status" if "status" in cols_ag else "''::text AS status")
        sel.append("recorrente" if "recorrente" in cols_ag else "0 AS recorrente")
        sel.append("serie_uid" if "serie_uid" in cols_ag else "''::text AS serie_uid")
        sel.append("profissional_cpf" if "profissional_cpf" in cols_ag else "''::text AS profissional_cpf")
        sel.append("dow_dom" if "dow_dom" in cols_ag else "NULL::integer AS dow_dom")

        cur = conn.cursor()

        cur.execute(f"""
            SELECT {", ".join(sel)}
              FROM agendamentos
             WHERE UPPER(COALESCE(paciente,'')) = UPPER(%s)
             ORDER BY inicio DESC
        """, (nome_paciente,))
        agds_all = [enriquecer_agendamento_row(r) for r in fetchall_dicts(cur)]

        cur.execute(f"""
            SELECT {", ".join(sel)}
              FROM agendamentos
             WHERE UPPER(COALESCE(paciente,'')) = UPPER(%s)
               AND inicio >= NOW()
             ORDER BY inicio ASC
        """, (nome_paciente,))
        agds_upcoming = [enriquecer_agendamento_row(r) for r in fetchall_dicts(cur)]

        if "serie_uid" in cols_ag:
            cur.execute("""
                SELECT COALESCE(serie_uid, '') AS serie_uid,
                       COALESCE(profissional,'') AS profissional,
                       COUNT(*) AS total_sessoes,
                       SUM(CASE WHEN inicio >= NOW() THEN 1 ELSE 0 END) AS sessoes_futuras
                  FROM agendamentos
                 WHERE UPPER(COALESCE(paciente,'')) = UPPER(%s)
                 GROUP BY COALESCE(serie_uid, ''), COALESCE(profissional,'')
                 ORDER BY MIN(inicio) ASC
            """, (nome_paciente,))
            series_resumo = fetchall_dicts(cur)
        else:
            series_resumo = []

    profs_all: list[str] = []
    for a in (agds_upcoming + agds_all):
        profs_all.extend(split_profissionais(a.get("profissional") or ""))

    uniq = []
    seen = set()
    for p in profs_all:
        up = p.upper()
        if up in seen:
            continue
        seen.add(up)
        uniq.append(p)

    cbo_map = map_cbo_por_profissionais(uniq)

    for a in agds_upcoming:
        enriquecer_com_prof_cbo(a, cbo_map)
    for a in agds_all:
        enriquecer_com_prof_cbo(a, cbo_map)

    prox_por_serie = {}
    for a in agds_upcoming:
        key = (a.get("serie_uid") or "", a.get("profissional") or "")
        if key not in prox_por_serie:
            prox_por_serie[key] = a
    for a in agds_all:
        key = (a.get("serie_uid") or "", a.get("profissional") or "")
        if key not in prox_por_serie:
            prox_por_serie[key] = a

    for s in series_resumo:
        key = (s.get("serie_uid") or "", s.get("profissional") or "")
        amostra = prox_por_serie.get(key)
        s["amostra_dia_semana"] = amostra.get("dia_semana") if amostra else None
        if amostra:
            s["amostra_hora"] = amostra["hora_ini"] + (f"–{amostra['hora_fim']}" if amostra.get("hora_fim") else "")
        else:
            s["amostra_hora"] = None

    return {
        "agds_upcoming": agds_upcoming,
        "agds_all": agds_all,
        "series_resumo": series_resumo,
        "total_agds": len(agds_all),
        "total_upcoming": len(agds_upcoming),
    }


# =============================================================================
# FILTROS / LISTAGEM
# =============================================================================

def where_and_params(args, cols: set) -> Tuple[str, List[Any]]:
    where: List[str] = []
    params: List[Any] = []

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

    cidade_val = (args.get("cidade") or "").strip()
    if cidade_val:
        if "cidade" in cols:
            where.append("cidade ILIKE %s")
            params.append(f"%{cidade_val}%")
        elif "municipio" in cols:
            where.append("municipio ILIKE %s")
            params.append(f"%{cidade_val}%")

    bairro = (args.get("bairro") or "").strip()
    if bairro and "bairro" in cols:
        where.append("bairro ILIKE %s")
        params.append(f"%{bairro}%")

    rua = (args.get("rua") or "").strip()
    if rua:
        parts = []
        if "rua" in cols:
            parts.append("rua ILIKE %s")
            params.append(f"%{rua}%")
        if "logradouro" in cols:
            parts.append("logradouro ILIKE %s")
            params.append(f"%{rua}%")
        if parts:
            where.append("(" + " OR ".join(parts) + ")")

    mes_nasc = (args.get("mes_nasc") or "").strip()
    if mes_nasc.isdigit() and "nascimento" in cols:
        mes2 = mes_nasc.zfill(2)
        where.append("""
            (
              SUBSTRING(nascimento FROM 6 FOR 2) = %s
              OR SUBSTRING(nascimento FROM 4 FOR 2) = %s
              OR SUBSTRING(nascimento FROM 5 FOR 2) = %s
            )
        """)
        params.extend([mes2, mes2, mes2])

    clause = " WHERE " + " AND ".join(where) if where else ""
    return clause, params


def fetch_pacientes_list(args=None):
    with get_conn() as conn:
        ensure_pacientes_schema(conn)
        cols = table_columns(conn, "pacientes")

        base_cols = [
            "id", "prontuario", "nome", "nascimento", "idade", "sexo", "status", "mod", "cid", "cid2",
            "cpf", "cns", "telefone", "telefone1",
            "nome_mae", "mae", "nome_pai", "pai",
            "rua", "logradouro", "numero", "numero_casa", "bairro", "cep", "cidade", "municipio", "uf",
            "end_prontuario", "alergias", "aviso", "comorbidades_json",
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
            f"SELECT {', '.join(select_cols)} FROM pacientes {clause} ORDER BY id DESC",
            params
        )
        rows = fetchall_dicts(cur)

    for r in rows:
        if not (r.get("telefone") or "").strip():
            r["telefone"] = (r.get("telefone1") or "").strip()
        if not (r.get("nome_mae") or "").strip():
            r["nome_mae"] = (r.get("mae") or "").strip()
        if not (r.get("nome_pai") or "").strip():
            r["nome_pai"] = (r.get("pai") or "").strip()

    if args:
        idade_min = args.get("idade_min", type=int)
        idade_max = args.get("idade_max", type=int)
        if idade_min is not None or idade_max is not None:
            filtradas = []
            for r in rows:
                idade = r.get("idade")
                if idade is None:
                    idade = calc_idade(r.get("nascimento"))
                if idade is None:
                    continue
                if idade_min is not None and idade < idade_min:
                    continue
                if idade_max is not None and idade > idade_max:
                    continue
                r["idade"] = idade
                filtradas.append(r)
            rows = filtradas

    mapa_ag = get_primeiro_agendamento_por_paciente()

    for r in rows:
        key = (r.get("nome") or "").strip().upper()
        info = mapa_ag.get(key)

        r["ag_dia"] = (info.get("dia_semana") if info else "") or ""
        r["ag_hora_ini"] = (info.get("hora_ini") if info else "") or ""
        r["ag_hora_fim"] = (info.get("hora_fim") if info else "") or ""
        r["ag_resumo"] = (info.get("agenda_str") if info else "") or ""

        r["terapeuta"] = (info.get("terapeuta_str") if info else "") or ""
        r["cbo"] = (info.get("cbo_str") if info else "") or ""
        r["cbo_nome"] = ""

    if args:
        dia_semana = (args.get("dia_semana") or "").strip().lower()
        terapeuta_q = (args.get("terapeuta") or "").strip().lower()
        cbo_q = (args.get("cbo") or "").strip().lower()

        if dia_semana:
            rows = [r for r in rows if (r.get("ag_dia") or "").strip().lower() == dia_semana]

        if terapeuta_q:
            rows = [r for r in rows if terapeuta_q in (r.get("terapeuta") or "").lower()]

        if cbo_q:
            rows = [r for r in rows if cbo_q in (r.get("cbo") or "").lower()]

    return rows


def headers_padrao():
    return ["ID", "Prontuário", "Nome", "Nascimento", "Sexo", "Status", "Modalidade", "CID"]


# =============================================================================
# FORMATOS AUXILIARES
# =============================================================================

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