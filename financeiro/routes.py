from __future__ import annotations

import json
from datetime import datetime, date
from typing import Any

from flask import jsonify, render_template, request

from db import conectar_db
from . import financeiro_bp


# ============================================================
# HELPERS BÁSICOS
# ============================================================

def _is_postgres_conn(conn) -> bool:
    mod = conn.__class__.__module__.lower()
    return "psycopg" in mod or "psycopg2" in mod or "pgdb" in mod


def _conn():
    conn = conectar_db()

    if not _is_postgres_conn(conn):
        try:
            import sqlite3
            conn.row_factory = sqlite3.Row
        except Exception:
            pass

    return conn


def _adapt_sql(sql: str, conn) -> str:
    if _is_postgres_conn(conn):
        return sql.replace("?", "%s")
    return sql


def _execute(conn, sql: str, params: tuple | list | None = None):
    if params is None:
        params = ()

    sql = _adapt_sql(sql, conn)

    if hasattr(conn, "execute"):
        return conn.execute(sql, params)

    cur = conn.cursor()
    cur.execute(sql, params)
    return cur


def _executemany(conn, sql: str, seq_of_params):
    sql = _adapt_sql(sql, conn)

    if hasattr(conn, "executemany"):
        return conn.executemany(sql, seq_of_params)

    cur = conn.cursor()
    cur.executemany(sql, seq_of_params)
    return cur


def _serialize_value(v):
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")
    return v


def _dict_row(row, cols=None) -> dict[str, Any] | None:
    if row is None:
        return None

    if isinstance(row, dict):
        return {k: _serialize_value(v) for k, v in row.items()}

    if hasattr(row, "keys"):
        try:
            return {k: _serialize_value(row[k]) for k in row.keys()}
        except Exception:
            pass

    if cols:
        try:
            return {cols[i]: _serialize_value(row[i]) for i in range(len(cols))}
        except Exception:
            pass

    try:
        return {k: _serialize_value(v) for k, v in dict(row).items()}
    except Exception:
        return None


def _rows_to_dict(rows, cols=None) -> list[dict[str, Any]]:
    out = []

    for r in rows or []:
        item = _dict_row(r, cols)
        if item is not None:
            out.append(item)

    return out


def _fetchall_dict(cur):
    rows = cur.fetchall() or []
    cols = [d[0] for d in cur.description] if getattr(cur, "description", None) else None
    return _rows_to_dict(rows, cols)


def _fetchone_dict(cur):
    row = cur.fetchone()
    cols = [d[0] for d in cur.description] if getattr(cur, "description", None) else None
    return _dict_row(row, cols)


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today_iso() -> str:
    return date.today().strftime("%Y-%m-%d")


def _to_float(value, default=0.0) -> float:
    try:
        if value in (None, "", "null"):
            return float(default)
        return float(str(value).replace(",", "."))
    except Exception:
        return float(default)


def _to_int(value, default=0) -> int:
    try:
        if value in (None, "", "null"):
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def _to_bool(value) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if value in (1, "1", "true", "True", "SIM", "sim", "on", "yes", "Y", "y"):
        return 1
    return 0


def _normalize_digits(txt: str | None) -> str:
    if not txt:
        return ""
    return "".join(ch for ch in str(txt) if ch.isdigit())


def _json_loads_safe(value, default=None):
    if default is None:
        default = []
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _ok(**kwargs):
    payload = {"ok": True}
    payload.update(kwargs)
    return jsonify(payload)


def _fail(message: str, status: int = 400, **kwargs):
    payload = {"ok": False, "erro": message}
    payload.update(kwargs)
    return jsonify(payload), status


def _list_columns(conn, table: str) -> set[str]:
    try:
        if _is_postgres_conn(conn):
            cur = _execute(conn, """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = ?
                ORDER BY ordinal_position
            """, (table,))
            rows = _fetchall_dict(cur)
            return {str(r.get("column_name")) for r in rows if r.get("column_name")}

        cur = _execute(conn, f"PRAGMA table_info({table})")
        rows = cur.fetchall() or []
        cols = set()

        for r in rows:
            try:
                cols.add(str(r["name"]))
            except Exception:
                cols.add(str(r[1]))

        return cols
    except Exception:
        return set()


def _table_exists(conn, table: str) -> bool:
    try:
        if _is_postgres_conn(conn):
            cur = _execute(conn, """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = ?
                LIMIT 1
            """, (table,))
            return bool(cur.fetchone())

        cur = _execute(conn, """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            LIMIT 1
        """, (table,))
        return bool(cur.fetchone())
    except Exception:
        return False


def _ensure_column(conn, table: str, column: str, ddl: str):
    cols = _list_columns(conn, table)
    if column in cols:
        return

    try:
        if _is_postgres_conn(conn):
            _execute(conn, f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl}")
        else:
            _execute(conn, f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    except Exception:
        pass


def _col_expr(cols: set[str], preferred: list[str], fallback_sql: str = "''") -> str:
    for c in preferred:
        if c in cols:
            return c
    return fallback_sql


# ============================================================
# SCHEMA
# ============================================================

def ensure_financeiro_schema():
    conn = _conn()

    try:
        if _is_postgres_conn(conn):
            _execute(conn, """
                CREATE TABLE IF NOT EXISTS financeiro_combos (
                    id SERIAL PRIMARY KEY,
                    nome TEXT NOT NULL,
                    descricao TEXT,
                    sessoes INTEGER NOT NULL DEFAULT 0,
                    preco NUMERIC(12,2) NOT NULL DEFAULT 0,
                    ativo INTEGER NOT NULL DEFAULT 1,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    atualizado_em TIMESTAMP
                )
            """)

            _execute(conn, """
                CREATE TABLE IF NOT EXISTS financeiro_paciente_planos (
                    id SERIAL PRIMARY KEY,
                    paciente_id INTEGER,
                    paciente_nome TEXT NOT NULL,
                    paciente_cpf TEXT,
                    paciente_cns TEXT,
                    tipo TEXT NOT NULL,
                    combo_id INTEGER,
                    combo_nome TEXT,
                    nome_plano TEXT,
                    descricao TEXT,
                    sessoes_contratadas INTEGER NOT NULL DEFAULT 0,
                    sessoes_usadas INTEGER NOT NULL DEFAULT 0,
                    valor_total NUMERIC(12,2) NOT NULL DEFAULT 0,
                    recorrente INTEGER NOT NULL DEFAULT 0,
                    renovacao_automatica INTEGER NOT NULL DEFAULT 0,
                    frequencia TEXT,
                    forma_pagamento TEXT,
                    observacoes TEXT,
                    data_inicio TEXT,
                    data_fim TEXT,
                    status TEXT NOT NULL DEFAULT 'ativo',
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    atualizado_em TIMESTAMP
                )
            """)

            _execute(conn, """
                CREATE TABLE IF NOT EXISTS financeiro_lancamentos (
                    id SERIAL PRIMARY KEY,
                    paciente_id INTEGER,
                    plano_id INTEGER,
                    origem TEXT DEFAULT 'manual',
                    referencia_tipo TEXT,
                    referencia_id INTEGER,
                    tipo TEXT NOT NULL,
                    categoria TEXT,
                    descricao TEXT NOT NULL,
                    valor NUMERIC(12,2) NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pendente',
                    forma_pagamento TEXT,
                    parcela_numero INTEGER,
                    parcelas_total INTEGER,
                    vencimento TEXT,
                    data_pagamento TEXT,
                    competencia TEXT,
                    observacoes TEXT,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    atualizado_em TIMESTAMP
                )
            """)
        else:
            _execute(conn, """
                CREATE TABLE IF NOT EXISTS financeiro_combos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL,
                    descricao TEXT,
                    sessoes INTEGER NOT NULL DEFAULT 0,
                    preco REAL NOT NULL DEFAULT 0,
                    ativo INTEGER NOT NULL DEFAULT 1,
                    criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                    atualizado_em TEXT
                )
            """)

            _execute(conn, """
                CREATE TABLE IF NOT EXISTS financeiro_paciente_planos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    paciente_id INTEGER,
                    paciente_nome TEXT NOT NULL,
                    paciente_cpf TEXT,
                    paciente_cns TEXT,
                    tipo TEXT NOT NULL,
                    combo_id INTEGER,
                    combo_nome TEXT,
                    nome_plano TEXT,
                    descricao TEXT,
                    sessoes_contratadas INTEGER NOT NULL DEFAULT 0,
                    sessoes_usadas INTEGER NOT NULL DEFAULT 0,
                    valor_total REAL NOT NULL DEFAULT 0,
                    recorrente INTEGER NOT NULL DEFAULT 0,
                    renovacao_automatica INTEGER NOT NULL DEFAULT 0,
                    frequencia TEXT,
                    forma_pagamento TEXT,
                    observacoes TEXT,
                    data_inicio TEXT,
                    data_fim TEXT,
                    status TEXT NOT NULL DEFAULT 'ativo',
                    criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                    atualizado_em TEXT
                )
            """)

            _execute(conn, """
                CREATE TABLE IF NOT EXISTS financeiro_lancamentos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    paciente_id INTEGER,
                    plano_id INTEGER,
                    origem TEXT DEFAULT 'manual',
                    referencia_tipo TEXT,
                    referencia_id INTEGER,
                    tipo TEXT NOT NULL,
                    categoria TEXT,
                    descricao TEXT NOT NULL,
                    valor REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pendente',
                    forma_pagamento TEXT,
                    parcela_numero INTEGER,
                    parcelas_total INTEGER,
                    vencimento TEXT,
                    data_pagamento TEXT,
                    competencia TEXT,
                    observacoes TEXT,
                    criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                    atualizado_em TEXT
                )
            """)

        _ensure_column(conn, "financeiro_combos", "descricao", "TEXT")
        _ensure_column(conn, "financeiro_combos", "ativo", "INTEGER NOT NULL DEFAULT 1")
        _ensure_column(conn, "financeiro_combos", "criado_em", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP" if _is_postgres_conn(conn) else "TEXT")
        _ensure_column(conn, "financeiro_combos", "atualizado_em", "TIMESTAMP" if _is_postgres_conn(conn) else "TEXT")

        for col, ddl in {
            "forma_pagamento": "TEXT",
            "observacoes": "TEXT",
            "frequencia": "TEXT",
            "data_inicio": "TEXT",
            "data_fim": "TEXT",
            "recorrente": "INTEGER NOT NULL DEFAULT 0",
            "renovacao_automatica": "INTEGER NOT NULL DEFAULT 0",
            "paciente_cpf": "TEXT",
            "paciente_cns": "TEXT",
            "combo_nome": "TEXT",
            "nome_plano": "TEXT",
            "descricao": "TEXT",
            "sessoes_usadas": "INTEGER NOT NULL DEFAULT 0",
            "valor_total": "NUMERIC(12,2) NOT NULL DEFAULT 0" if _is_postgres_conn(conn) else "REAL NOT NULL DEFAULT 0",
            "status": "TEXT NOT NULL DEFAULT 'ativo'",
            "criado_em": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP" if _is_postgres_conn(conn) else "TEXT",
            "atualizado_em": "TIMESTAMP" if _is_postgres_conn(conn) else "TEXT",
        }.items():
            _ensure_column(conn, "financeiro_paciente_planos", col, ddl)

        for col, ddl in {
            "competencia": "TEXT",
            "origem": "TEXT DEFAULT 'manual'",
            "referencia_tipo": "TEXT",
            "referencia_id": "INTEGER",
            "paciente_id": "INTEGER",
            "plano_id": "INTEGER",
            "observacoes": "TEXT",
            "criado_em": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP" if _is_postgres_conn(conn) else "TEXT",
            "atualizado_em": "TIMESTAMP" if _is_postgres_conn(conn) else "TEXT",
        }.items():
            _ensure_column(conn, "financeiro_lancamentos", col, ddl)

        if _table_exists(conn, "atendimentos"):
            _ensure_column(conn, "atendimentos", "combo_plano_id", "INTEGER")
            _ensure_column(conn, "atendimentos", "contabiliza_sessao", "INTEGER NOT NULL DEFAULT 1")

            try:
                _execute(conn, "CREATE INDEX IF NOT EXISTS idx_atend_combo_plano_id ON atendimentos(combo_plano_id)")
                _execute(conn, "CREATE INDEX IF NOT EXISTS idx_atend_paciente_id ON atendimentos(paciente_id)")
            except Exception:
                pass

        for sql in [
            "CREATE INDEX IF NOT EXISTS idx_fin_combo_nome ON financeiro_combos(nome)",
            "CREATE INDEX IF NOT EXISTS idx_fin_pp_paciente_id ON financeiro_paciente_planos(paciente_id)",
            "CREATE INDEX IF NOT EXISTS idx_fin_pp_status ON financeiro_paciente_planos(status)",
            "CREATE INDEX IF NOT EXISTS idx_fin_lanc_tipo ON financeiro_lancamentos(tipo)",
            "CREATE INDEX IF NOT EXISTS idx_fin_lanc_status ON financeiro_lancamentos(status)",
            "CREATE INDEX IF NOT EXISTS idx_fin_lanc_venc ON financeiro_lancamentos(vencimento)",
            "CREATE INDEX IF NOT EXISTS idx_fin_lanc_data_pag ON financeiro_lancamentos(data_pagamento)",
            "CREATE INDEX IF NOT EXISTS idx_fin_lanc_paciente_id ON financeiro_lancamentos(paciente_id)",
            "CREATE INDEX IF NOT EXISTS idx_fin_lanc_plano_id ON financeiro_lancamentos(plano_id)",
        ]:
            try:
                _execute(conn, sql)
            except Exception:
                pass

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


ensure_financeiro_schema()


# ============================================================
# HELPERS DE NEGÓCIO
# ============================================================

def _buscar_paciente_por_id(conn, paciente_id: int):
    if not _table_exists(conn, "pacientes"):
        return None

    cols = _list_columns(conn, "pacientes")

    telefone_expr = "''"
    if "telefone" in cols and "telefone1" in cols:
        telefone_expr = "COALESCE(telefone, telefone1, '')"
    elif "telefone" in cols:
        telefone_expr = "COALESCE(telefone, '')"
    elif "telefone1" in cols:
        telefone_expr = "COALESCE(telefone1, '')"

    cpf_expr = "COALESCE(cpf, '')" if "cpf" in cols else "''"
    cns_expr = "COALESCE(cns, '')" if "cns" in cols else "''"
    nasc_expr = "COALESCE(nascimento::text, '')" if _is_postgres_conn(conn) and "nascimento" in cols else ("COALESCE(nascimento, '')" if "nascimento" in cols else "''")

    cur = _execute(conn, f"""
        SELECT
            id,
            COALESCE(nome, '') AS nome,
            {cpf_expr} AS cpf,
            {cns_expr} AS cns,
            {nasc_expr} AS nascimento,
            {telefone_expr} AS telefone
        FROM pacientes
        WHERE id = ?
        LIMIT 1
    """, (paciente_id,))

    return cur.fetchone()


def _competencia_from_date(dt_text: str | None) -> str:
    if not dt_text:
        return datetime.now().strftime("%Y-%m")
    return str(dt_text)[:7]


def _safe_label_nome_plano(tipo: str, combo_nome: str | None, nome_plano: str | None) -> str:
    if tipo == "combo":
        return (combo_nome or "Combo").strip()
    return (nome_plano or "Plano do paciente").strip()


def _contar_atendimentos_vinculados(conn, plano_id: int) -> int:
    if not _table_exists(conn, "atendimentos"):
        return 0

    cols = _list_columns(conn, "atendimentos")

    if "combo_plano_id" not in cols:
        return 0

    if "contabiliza_sessao" in cols:
        sql = """
            SELECT COUNT(*) AS total
            FROM atendimentos
            WHERE combo_plano_id = ?
              AND COALESCE(contabiliza_sessao, 1) = 1
        """
    else:
        sql = """
            SELECT COUNT(*) AS total
            FROM atendimentos
            WHERE combo_plano_id = ?
        """

    cur = _execute(conn, sql, (plano_id,))
    row = _fetchone_dict(cur) or {}
    return _to_int(row.get("total"), 0)


def _recalcular_saldo_sessoes(conn, plano_id: int):
    cur = _execute(conn, """
        SELECT id, sessoes_contratadas, status
        FROM financeiro_paciente_planos
        WHERE id = ?
        LIMIT 1
    """, (plano_id,))

    row = _fetchone_dict(cur)
    if not row:
        return

    contratadas = _to_int(row.get("sessoes_contratadas"), 0)
    usadas = _contar_atendimentos_vinculados(conn, plano_id)

    if contratadas > 0 and usadas > contratadas:
        usadas = contratadas

    novo_status = row.get("status") or "ativo"

    if contratadas > 0 and usadas >= contratadas:
        novo_status = "encerrado"
    elif novo_status == "encerrado" and usadas < contratadas:
        novo_status = "ativo"

    _execute(conn, """
        UPDATE financeiro_paciente_planos
        SET sessoes_usadas = ?, status = ?, atualizado_em = ?
        WHERE id = ?
    """, (usadas, novo_status, _now_iso(), plano_id))


def _faixa_consumo(contratadas: int, usadas: int) -> dict[str, Any]:
    contratadas = max(0, _to_int(contratadas, 0))
    usadas = max(0, _to_int(usadas, 0))
    restantes = max(0, contratadas - usadas)

    if contratadas <= 0:
        return {
            "sessoes_restantes": 0,
            "perto_de_acabar": False,
            "acabou": False,
            "percentual_usado": 0,
        }

    percentual = int(round((usadas / contratadas) * 100))
    limite_alerta = max(2, int(round(contratadas * 0.2)))

    return {
        "sessoes_restantes": restantes,
        "perto_de_acabar": restantes > 0 and restantes <= limite_alerta,
        "acabou": restantes <= 0,
        "percentual_usado": percentual,
    }


def _buscar_datas_agendamento_do_paciente(conn, paciente_nome: str) -> dict[str, Any]:
    if not paciente_nome or not _table_exists(conn, "agendamentos"):
        return {"datas_resumo": "", "dia_semana": "", "indeterminado": False}

    cols = _list_columns(conn, "agendamentos")

    paciente_col = None
    for c in ["paciente", "paciente_nome", "nome_paciente", "nome"]:
        if c in cols:
            paciente_col = c
            break

    if not paciente_col:
        return {"datas_resumo": "", "dia_semana": "", "indeterminado": False}

    inicio_expr = _col_expr(cols, ["inicio", "data_inicio", "data", "slot", "horario"], "''")
    fim_expr = _col_expr(cols, ["fim", "data_fim"], "''")
    dia_expr = _col_expr(cols, ["dia", "dia_semana"], "''")
    status_expr = _col_expr(cols, ["status"], "'ativo'")

    try:
        if _is_postgres_conn(conn):
            cur = _execute(conn, f"""
                SELECT
                    COALESCE({inicio_expr}::text, '') AS inicio,
                    COALESCE({fim_expr}::text, '') AS fim,
                    COALESCE({dia_expr}::text, '') AS dia,
                    COALESCE({status_expr}::text, 'ativo') AS status
                FROM agendamentos
                WHERE TRIM(LOWER(COALESCE({paciente_col}, ''))) = TRIM(LOWER(?))
                  AND COALESCE({status_expr}::text, 'ativo') = 'ativo'
                ORDER BY {inicio_expr}
            """, (paciente_nome,))
        else:
            cur = _execute(conn, f"""
                SELECT
                    COALESCE({inicio_expr}, '') AS inicio,
                    COALESCE({fim_expr}, '') AS fim,
                    COALESCE({dia_expr}, '') AS dia,
                    COALESCE({status_expr}, 'ativo') AS status
                FROM agendamentos
                WHERE TRIM(LOWER(COALESCE({paciente_col}, ''))) = TRIM(LOWER(?))
                  AND COALESCE({status_expr}, 'ativo') = 'ativo'
                ORDER BY {inicio_expr}
            """, (paciente_nome,))

        rows = _fetchall_dict(cur)

    except Exception:
        return {"datas_resumo": "", "dia_semana": "", "indeterminado": False}

    if not rows:
        return {"datas_resumo": "", "dia_semana": "", "indeterminado": False}

    dias = []
    datas = []

    for r in rows:
        dia = (r.get("dia") or "").strip()
        inicio = (r.get("inicio") or "").strip()

        if dia and dia not in dias:
            dias.append(dia)

        if inicio:
            data_curta = inicio[:10]
            if data_curta and data_curta not in datas:
                datas.append(data_curta)

    if dias and not datas:
        return {
            "datas_resumo": "",
            "dia_semana": " • ".join(dias),
            "indeterminado": True,
        }

    return {
        "datas_resumo": " • ".join(datas[:20]),
        "dia_semana": " • ".join(dias),
        "indeterminado": False,
    }




def _montar_resumo_datas(item: dict[str, Any], agenda_info: dict[str, Any]) -> dict[str, Any]:
    data_inicio = (item.get("data_inicio") or "").strip()
    data_fim = (item.get("data_fim") or "").strip()
    frequencia = (item.get("frequencia") or "").strip()

    if data_inicio and data_fim:
        return {"datas_resumo": f"{data_inicio} até {data_fim}", "dia_semana": "", "indeterminado": False}

    if data_inicio and not data_fim:
        return {"datas_resumo": f"Início: {data_inicio}", "dia_semana": "", "indeterminado": False}

    if agenda_info.get("datas_resumo"):
        return {
            "datas_resumo": agenda_info["datas_resumo"],
            "dia_semana": agenda_info.get("dia_semana", ""),
            "indeterminado": False,
        }

    if agenda_info.get("dia_semana"):
        return {
            "datas_resumo": "",
            "dia_semana": agenda_info["dia_semana"],
            "indeterminado": True,
        }

    if frequencia:
        return {"datas_resumo": "", "dia_semana": frequencia, "indeterminado": True}

    return {"datas_resumo": "", "dia_semana": "", "indeterminado": False}


def _enriquecer_plano_item(conn, item: dict[str, Any]) -> dict[str, Any]:
    if not item:
        return {}

    plano_id = _to_int(item.get("id"), 0)
    contratadas = _to_int(item.get("sessoes_contratadas"), 0)

    try:
        usadas_calc = _contar_atendimentos_vinculados(conn, plano_id)
    except Exception:
        usadas_calc = _to_int(item.get("sessoes_usadas"), 0)

    item["sessoes_usadas"] = usadas_calc

    faixa = _faixa_consumo(contratadas, usadas_calc)

    item.update({
        "sessoes_restantes": faixa["sessoes_restantes"],
        "perto_de_acabar": faixa["perto_de_acabar"],
        "acabou": faixa["acabou"],
        "percentual_usado": faixa["percentual_usado"],
    })

    try:
        agenda_info = _buscar_datas_agendamento_do_paciente(conn, item.get("paciente_nome", ""))
    except Exception:
        agenda_info = {"datas_resumo": "", "dia_semana": "", "indeterminado": False}

    resumo = _montar_resumo_datas(item, agenda_info)

    item["datas_resumo"] = resumo["datas_resumo"]
    item["dia_semana"] = resumo["dia_semana"]
    item["indeterminado"] = resumo["indeterminado"]

    return item


def _vinculo_ativo_existente(conn, paciente_id: int, ignore_id: int | None = None):
    sql = """
        SELECT *
        FROM financeiro_paciente_planos
        WHERE paciente_id = ?
          AND status = 'ativo'
    """
    params: list[Any] = [paciente_id]

    if ignore_id:
        sql += " AND id <> ?"
        params.append(ignore_id)

    sql += " ORDER BY id DESC LIMIT 1"
    return _execute(conn, sql, params).fetchone()


def _gerar_lancamentos_do_plano(
    conn,
    plano_id: int,
    paciente_id: int | None,
    valor_total: float,
    forma_pagamento: str | None,
    vencimento_base: str | None,
    descricao_base: str,
    parcelas: list[dict[str, Any]] | None = None,
):
    competencia = _competencia_from_date(vencimento_base or _today_iso())

    if not parcelas:
        _execute(conn, """
            INSERT INTO financeiro_lancamentos (
                paciente_id, plano_id, origem, referencia_tipo, referencia_id,
                tipo, categoria, descricao, valor, status,
                forma_pagamento, parcela_numero, parcelas_total,
                vencimento, competencia, criado_em, atualizado_em
            ) VALUES (?, ?, 'plano', 'plano', ?, 'entrada', 'plano', ?, ?, 'pendente',
                      ?, 1, 1, ?, ?, ?, ?)
        """, (
            paciente_id,
            plano_id,
            plano_id,
            descricao_base,
            valor_total,
            forma_pagamento,
            vencimento_base or _today_iso(),
            competencia,
            _now_iso(),
            _now_iso(),
        ))
        return

    total_parcelas = len(parcelas)

    for i, parcela in enumerate(parcelas, start=1):
        valor = _to_float(parcela.get("valor"), 0)
        vencimento = parcela.get("vencimento") or vencimento_base or _today_iso()
        status = parcela.get("status") or "pendente"
        forma = parcela.get("forma_pagamento") or forma_pagamento
        comp = _competencia_from_date(vencimento)

        _execute(conn, """
            INSERT INTO financeiro_lancamentos (
                paciente_id, plano_id, origem, referencia_tipo, referencia_id,
                tipo, categoria, descricao, valor, status,
                forma_pagamento, parcela_numero, parcelas_total,
                vencimento, competencia, criado_em, atualizado_em
            ) VALUES (?, ?, 'plano', 'parcela', ?, 'entrada', 'plano', ?, ?, ?,
                      ?, ?, ?, ?, ?, ?, ?)
        """, (
            paciente_id,
            plano_id,
            plano_id,
            f"{descricao_base} · Parcela {i}/{total_parcelas}",
            valor,
            status,
            forma,
            i,
            total_parcelas,
            vencimento,
            comp,
            _now_iso(),
            _now_iso(),
        ))


# ============================================================
# PÁGINAS
# ============================================================

@financeiro_bp.get("/")
def financeiro_index():
    ensure_financeiro_schema()
    return render_template("financeiro.html", kpis={
        "saldo_caixa": 0.0,
        "entradas": 0.0,
        "saidas": 0.0,
        "pendentes": 0.0,
    })


@financeiro_bp.get("/comercial")
def comercial_index():
    ensure_financeiro_schema()
    return render_template("comercial.html")


# ============================================================
# PACIENTES
# ============================================================

@financeiro_bp.get("/api/pacientes/buscar")
def api_buscar_pacientes():
    ensure_financeiro_schema()

    q = (request.args.get("q") or "").strip()
    limit = min(_to_int(request.args.get("limit"), 20), 100)

    conn = _conn()

    try:
        if not _table_exists(conn, "pacientes"):
            return _ok(items=[])

        cols = _list_columns(conn, "pacientes")

        telefone_expr = "''"
        if "telefone" in cols and "telefone1" in cols:
            telefone_expr = "COALESCE(telefone, telefone1, '')"
        elif "telefone" in cols:
            telefone_expr = "COALESCE(telefone, '')"
        elif "telefone1" in cols:
            telefone_expr = "COALESCE(telefone1, '')"

        cpf_expr = "COALESCE(cpf, '')" if "cpf" in cols else "''"
        cns_expr = "COALESCE(cns, '')" if "cns" in cols else "''"
        nasc_expr = "COALESCE(nascimento::text, '')" if _is_postgres_conn(conn) and "nascimento" in cols else ("COALESCE(nascimento, '')" if "nascimento" in cols else "''")

        sql = f"""
            SELECT
                id,
                COALESCE(nome, '') AS nome,
                {cpf_expr} AS cpf,
                {cns_expr} AS cns,
                {nasc_expr} AS nascimento,
                {telefone_expr} AS telefone
            FROM pacientes
        """
        params: list[Any] = []

        if q:
            q_digits = _normalize_digits(q)
            like_op = "ILIKE" if _is_postgres_conn(conn) else "LIKE"
            sql += f"""
                WHERE
                    COALESCE(nome, '') {like_op} ?
                    OR REPLACE(REPLACE(REPLACE({cpf_expr}, '.', ''), '-', ''), ' ', '') {like_op} ?
                    OR REPLACE(REPLACE(REPLACE({cns_expr}, '.', ''), '-', ''), ' ', '') {like_op} ?
            """
            params.extend([f"%{q}%", f"%{q_digits}%", f"%{q_digits}%"])

        sql += " ORDER BY COALESCE(nome, '') LIMIT ?"
        params.append(limit)

        cur = _execute(conn, sql, params)
        return _ok(items=_fetchall_dict(cur))

    except Exception as e:
        return _fail(f"Erro ao buscar pacientes: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.get("/api/pacientes-sem-vinculo")
def api_pacientes_sem_vinculo():
    ensure_financeiro_schema()

    q = (request.args.get("q") or "").strip()
    apenas_com_atendimento = _to_bool(request.args.get("apenas_com_atendimento", 1))

    conn = _conn()

    try:
        if not _table_exists(conn, "pacientes"):
            return _ok(items=[])

        cols = _list_columns(conn, "pacientes")

        telefone_expr = "''"
        if "telefone" in cols and "telefone1" in cols:
            telefone_expr = "COALESCE(p.telefone, p.telefone1, '')"
        elif "telefone" in cols:
            telefone_expr = "COALESCE(p.telefone, '')"
        elif "telefone1" in cols:
            telefone_expr = "COALESCE(p.telefone1, '')"

        cpf_expr = "COALESCE(p.cpf, '')" if "cpf" in cols else "''"
        cns_expr = "COALESCE(p.cns, '')" if "cns" in cols else "''"
        nasc_expr = "COALESCE(p.nascimento::text, '')" if _is_postgres_conn(conn) and "nascimento" in cols else ("COALESCE(p.nascimento, '')" if "nascimento" in cols else "''")

        sql = f"""
            SELECT
                p.id,
                COALESCE(p.nome, '') AS nome,
                {cpf_expr} AS cpf,
                {cns_expr} AS cns,
                {nasc_expr} AS nascimento,
                {telefone_expr} AS telefone
            FROM pacientes p
            WHERE NOT EXISTS (
                SELECT 1
                FROM financeiro_paciente_planos pp
                WHERE pp.paciente_id = p.id
                  AND COALESCE(pp.status, 'ativo') = 'ativo'
            )
        """
        params: list[Any] = []

        if apenas_com_atendimento and _table_exists(conn, "atendimentos"):
            atend_cols = _list_columns(conn, "atendimentos")

            if "paciente_id" in atend_cols:
                sql += """
                    AND EXISTS (
                        SELECT 1
                        FROM atendimentos a
                        WHERE a.paciente_id = p.id
                    )
                """
            elif "nome" in atend_cols:
                sql += """
                    AND EXISTS (
                        SELECT 1
                        FROM atendimentos a
                        WHERE TRIM(LOWER(COALESCE(a.nome, ''))) = TRIM(LOWER(COALESCE(p.nome, '')))
                    )
                """

        if q:
            q_digits = _normalize_digits(q)
            like_op = "ILIKE" if _is_postgres_conn(conn) else "LIKE"
            sql += f"""
                AND (
                    COALESCE(p.nome, '') {like_op} ?
                    OR REPLACE(REPLACE(REPLACE({cpf_expr}, '.', ''), '-', ''), ' ', '') {like_op} ?
                    OR REPLACE(REPLACE(REPLACE({cns_expr}, '.', ''), '-', ''), ' ', '') {like_op} ?
                )
            """
            params.extend([f"%{q}%", f"%{q_digits}%", f"%{q_digits}%"])

        sql += " ORDER BY COALESCE(p.nome, '')"

        cur = _execute(conn, sql, params)
        return _ok(items=_fetchall_dict(cur))

    except Exception as e:
        return _fail(f"Erro ao listar pacientes sem vínculo: {e}", 500)

    finally:
        conn.close()


# ============================================================
# COMBOS
# ============================================================

@financeiro_bp.get("/api/combos")
def api_listar_combos():
    ensure_financeiro_schema()

    q = (request.args.get("q") or "").strip()
    ativo = request.args.get("ativo")

    conn = _conn()

    try:
        sql = """
            SELECT id, nome, descricao, sessoes, preco, ativo, criado_em, atualizado_em
            FROM financeiro_combos
            WHERE 1=1
        """
        params: list[Any] = []

        if q:
            like_op = "ILIKE" if _is_postgres_conn(conn) else "LIKE"
            sql += f" AND (nome {like_op} ? OR COALESCE(descricao, '') {like_op} ?)"
            params.extend([f"%{q}%", f"%{q}%"])

        if ativo in ("0", "1"):
            sql += " AND ativo = ?"
            params.append(int(ativo))

        sql += " ORDER BY ativo DESC, nome ASC"

        cur = _execute(conn, sql, params)
        return _ok(items=_fetchall_dict(cur))

    except Exception as e:
        return _fail(f"Erro ao listar combos: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.post("/api/combos")
def api_criar_combo():
    ensure_financeiro_schema()

    data = request.get_json(silent=True) or request.form

    nome = (data.get("nome") or "").strip()
    descricao = (data.get("descricao") or "").strip()
    sessoes = _to_int(data.get("sessoes"), 0)
    preco = _to_float(data.get("preco"), 0)
    ativo = _to_bool(data.get("ativo", 1))

    if not nome:
        return _fail("Informe o nome do combo.")
    if sessoes <= 0:
        return _fail("Informe a quantidade de sessões do combo.")
    if preco < 0:
        return _fail("Preço inválido.")

    conn = _conn()

    try:
        if _is_postgres_conn(conn):
            cur = _execute(conn, """
                INSERT INTO financeiro_combos (
                    nome, descricao, sessoes, preco, ativo, criado_em, atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                RETURNING id
            """, (nome, descricao, sessoes, preco, ativo, _now_iso(), _now_iso()))

            combo_id = _fetchone_dict(cur)["id"]
        else:
            cur = _execute(conn, """
                INSERT INTO financeiro_combos (
                    nome, descricao, sessoes, preco, ativo, criado_em, atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (nome, descricao, sessoes, preco, ativo, _now_iso(), _now_iso()))

            combo_id = cur.lastrowid

        conn.commit()

        cur = _execute(conn, "SELECT * FROM financeiro_combos WHERE id = ?", (combo_id,))
        return _ok(item=_fetchone_dict(cur), mensagem="Combo cadastrado com sucesso.")

    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao cadastrar combo: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.put("/api/combos/<int:combo_id>")
def api_editar_combo(combo_id: int):
    ensure_financeiro_schema()

    data = request.get_json(silent=True) or request.form

    nome = (data.get("nome") or "").strip()
    descricao = (data.get("descricao") or "").strip()
    sessoes = _to_int(data.get("sessoes"), 0)
    preco = _to_float(data.get("preco"), 0)
    ativo = _to_bool(data.get("ativo", 1))

    if not nome:
        return _fail("Informe o nome do combo.")
    if sessoes <= 0:
        return _fail("Informe a quantidade de sessões.")
    if preco < 0:
        return _fail("Preço inválido.")

    conn = _conn()

    try:
        exists = _execute(conn, "SELECT id FROM financeiro_combos WHERE id = ?", (combo_id,)).fetchone()
        if not exists:
            return _fail("Combo não encontrado.", 404)

        _execute(conn, """
            UPDATE financeiro_combos
            SET nome = ?, descricao = ?, sessoes = ?, preco = ?, ativo = ?, atualizado_em = ?
            WHERE id = ?
        """, (nome, descricao, sessoes, preco, ativo, _now_iso(), combo_id))

        conn.commit()

        cur = _execute(conn, "SELECT * FROM financeiro_combos WHERE id = ?", (combo_id,))
        return _ok(item=_fetchone_dict(cur), mensagem="Combo atualizado com sucesso.")

    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao atualizar combo: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.delete("/api/combos/<int:combo_id>")
def api_excluir_combo(combo_id: int):
    ensure_financeiro_schema()

    conn = _conn()

    try:
        cur = _execute(conn, """
            SELECT COUNT(*) AS total
            FROM financeiro_paciente_planos
            WHERE combo_id = ?
        """, (combo_id,))

        uso = _fetchone_dict(cur) or {}

        if _to_int(uso.get("total"), 0) > 0:
            return _fail("Este combo já está vinculado a paciente(s). Edite ou inative em vez de excluir.", 409)

        _execute(conn, "DELETE FROM financeiro_combos WHERE id = ?", (combo_id,))
        conn.commit()

        return _ok(mensagem="Combo excluído com sucesso.")

    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao excluir combo: {e}", 500)

    finally:
        conn.close()


# ============================================================
# PACIENTE x PLANOS / COMBOS
# ============================================================

@financeiro_bp.get("/api/pacientes-planos")
def api_listar_pacientes_planos():
    ensure_financeiro_schema()

    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    tipo = (request.args.get("tipo") or "").strip()
    paciente_id = request.args.get("paciente_id")
    perto_de_acabar = _to_bool(request.args.get("perto_de_acabar"))

    conn = _conn()

    try:
        sql = """
            SELECT pp.*
            FROM financeiro_paciente_planos pp
            WHERE 1=1
        """
        params: list[Any] = []

        if q:
            q_digits = _normalize_digits(q)
            like_op = "ILIKE" if _is_postgres_conn(conn) else "LIKE"
            sql += f"""
                AND (
                    COALESCE(pp.paciente_nome, '') {like_op} ?
                    OR COALESCE(pp.combo_nome, '') {like_op} ?
                    OR COALESCE(pp.nome_plano, '') {like_op} ?
                    OR REPLACE(REPLACE(REPLACE(COALESCE(pp.paciente_cpf, ''), '.', ''), '-', ''), ' ', '') {like_op} ?
                    OR REPLACE(REPLACE(REPLACE(COALESCE(pp.paciente_cns, ''), '.', ''), '-', ''), ' ', '') {like_op} ?
                )
            """
            params.extend([f"%{q}%", f"%{q}%", f"%{q}%", f"%{q_digits}%", f"%{q_digits}%"])

        if status:
            sql += " AND pp.status = ?"
            params.append(status)

        if tipo:
            sql += " AND pp.tipo = ?"
            params.append(tipo)

        if paciente_id:
            sql += " AND pp.paciente_id = ?"
            params.append(_to_int(paciente_id))

        sql += " ORDER BY pp.criado_em DESC, pp.id DESC"

        cur = _execute(conn, sql, params)
        rows = _fetchall_dict(cur)

        items = []
        for row in rows:
            try:
                item = _enriquecer_plano_item(conn, row)
            except Exception:
                item = row

            if perto_de_acabar and not item.get("perto_de_acabar"):
                continue

            items.append(item)

        return _ok(items=items)

    except Exception as e:
        return _fail(f"Erro ao listar planos/pacientes: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.get("/api/pacientes-planos/<int:plano_id>")
def api_obter_paciente_plano(plano_id: int):
    ensure_financeiro_schema()

    conn = _conn()

    try:
        cur = _execute(conn, """
            SELECT pp.*
            FROM financeiro_paciente_planos pp
            WHERE pp.id = ?
            LIMIT 1
        """, (plano_id,))

        row = _fetchone_dict(cur)

        if not row:
            return _fail("Registro não encontrado.", 404)

        item = _enriquecer_plano_item(conn, row)

        cur = _execute(conn, """
            SELECT *
            FROM financeiro_lancamentos
            WHERE plano_id = ?
            ORDER BY parcela_numero ASC, vencimento ASC, id ASC
        """, (plano_id,))

        return _ok(item=item, lancamentos=_fetchall_dict(cur))

    except Exception as e:
        return _fail(f"Erro ao obter registro: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.post("/api/pacientes-planos")
def api_criar_paciente_plano():
    ensure_financeiro_schema()

    data = request.get_json(silent=True) or request.form

    paciente_id = _to_int(data.get("paciente_id"), 0)
    tipo = (data.get("tipo") or "").strip().lower()
    combo_id = _to_int(data.get("combo_id"), 0) or None
    nome_plano = (data.get("nome_plano") or "").strip()
    descricao = (data.get("descricao") or "").strip()

    sessoes_contratadas = _to_int(data.get("sessoes_contratadas"), 0)
    valor_total = _to_float(data.get("valor_total"), 0)

    recorrente = _to_bool(data.get("recorrente"))
    renovacao_automatica = _to_bool(data.get("renovacao_automatica"))
    frequencia = (data.get("frequencia") or "").strip()
    forma_pagamento = (data.get("forma_pagamento") or "").strip()
    data_inicio = (data.get("data_inicio") or "").strip()
    data_fim = (data.get("data_fim") or "").strip()
    status = (data.get("status") or "ativo").strip()
    observacoes = (data.get("observacoes") or "").strip()

    parcelas = data.get("parcelas")
    if isinstance(parcelas, str):
        parcelas = _json_loads_safe(parcelas, [])
    if not isinstance(parcelas, list):
        parcelas = []

    if paciente_id <= 0:
        return _fail("Selecione um paciente.")

    if tipo not in ("combo", "plano"):
        return _fail("Tipo inválido. Use 'combo' ou 'plano'.")

    conn = _conn()

    try:
        paciente = _dict_row(_buscar_paciente_por_id(conn, paciente_id))
        if not paciente:
            return _fail("Paciente não encontrado.", 404)

        existente = _vinculo_ativo_existente(conn, paciente_id)
        if existente:
            return _fail(
                "Este paciente já possui vínculo ativo no comercial. Edite o registro existente em vez de cadastrar outro.",
                409,
                registro_existente=_dict_row(existente),
            )

        paciente_nome = (paciente.get("nome") or "").strip()
        paciente_cpf = (paciente.get("cpf") or "").strip()
        paciente_cns = (paciente.get("cns") or "").strip()

        combo_nome = None

        if tipo == "combo":
            if not combo_id:
                return _fail("Informe o combo a ser vinculado.")

            cur = _execute(conn, "SELECT * FROM financeiro_combos WHERE id = ? LIMIT 1", (combo_id,))
            combo = _fetchone_dict(cur)

            if not combo:
                return _fail("Combo não encontrado.", 404)

            combo_nome = combo.get("nome")

            if sessoes_contratadas <= 0:
                sessoes_contratadas = _to_int(combo.get("sessoes"), 0)
            if valor_total <= 0:
                valor_total = _to_float(combo.get("preco"), 0)

        if tipo == "plano" and not nome_plano:
            nome_plano = "Plano do paciente"

        if _is_postgres_conn(conn):
            cur = _execute(conn, """
                INSERT INTO financeiro_paciente_planos (
                    paciente_id, paciente_nome, paciente_cpf, paciente_cns,
                    tipo, combo_id, combo_nome, nome_plano, descricao,
                    sessoes_contratadas, sessoes_usadas, valor_total,
                    recorrente, renovacao_automatica, frequencia,
                    forma_pagamento, observacoes,
                    data_inicio, data_fim, status,
                    criado_em, atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
            """, (
                paciente_id, paciente_nome, paciente_cpf, paciente_cns,
                tipo, combo_id, combo_nome, nome_plano, descricao,
                sessoes_contratadas, valor_total,
                recorrente, renovacao_automatica, frequencia,
                forma_pagamento, observacoes,
                data_inicio, data_fim, status,
                _now_iso(), _now_iso()
            ))
            plano_id = _fetchone_dict(cur)["id"]
        else:
            cur = _execute(conn, """
                INSERT INTO financeiro_paciente_planos (
                    paciente_id, paciente_nome, paciente_cpf, paciente_cns,
                    tipo, combo_id, combo_nome, nome_plano, descricao,
                    sessoes_contratadas, sessoes_usadas, valor_total,
                    recorrente, renovacao_automatica, frequencia,
                    forma_pagamento, observacoes,
                    data_inicio, data_fim, status,
                    criado_em, atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                paciente_id, paciente_nome, paciente_cpf, paciente_cns,
                tipo, combo_id, combo_nome, nome_plano, descricao,
                sessoes_contratadas, valor_total,
                recorrente, renovacao_automatica, frequencia,
                forma_pagamento, observacoes,
                data_inicio, data_fim, status,
                _now_iso(), _now_iso()
            ))
            plano_id = cur.lastrowid

        nome_ref = _safe_label_nome_plano(tipo, combo_nome, nome_plano)
        desc_fin = f"{'Combo' if tipo == 'combo' else 'Plano'} · {nome_ref} · {paciente_nome}"

        if valor_total > 0:
            _gerar_lancamentos_do_plano(
                conn=conn,
                plano_id=plano_id,
                paciente_id=paciente_id,
                valor_total=valor_total,
                forma_pagamento=forma_pagamento,
                vencimento_base=data_inicio or _today_iso(),
                descricao_base=desc_fin,
                parcelas=parcelas,
            )

        _recalcular_saldo_sessoes(conn, plano_id)
        conn.commit()

        cur = _execute(conn, "SELECT * FROM financeiro_paciente_planos WHERE id = ?", (plano_id,))
        item = _enriquecer_plano_item(conn, _fetchone_dict(cur))

        cur = _execute(conn, """
            SELECT *
            FROM financeiro_lancamentos
            WHERE plano_id = ?
            ORDER BY parcela_numero ASC, vencimento ASC, id ASC
        """, (plano_id,))

        return _ok(
            item=item,
            lancamentos=_fetchall_dict(cur),
            mensagem="Plano/combo vinculado ao paciente com sucesso."
        )

    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao vincular plano/combo: {e}", 500)

    finally:
        conn.close()


# ============================================================
# RESUMO / LANÇAMENTOS
# ============================================================

@financeiro_bp.get("/api/resumo")
def api_resumo_financeiro():
    ensure_financeiro_schema()

    conn = _conn()

    try:
        cur = _execute(conn, """
            SELECT
                SUM(CASE WHEN tipo = 'entrada' AND status = 'pago' THEN valor ELSE 0 END) AS entradas_pagas,
                SUM(CASE WHEN tipo = 'saida' AND status = 'pago' THEN valor ELSE 0 END) AS saidas_pagas,
                SUM(CASE WHEN tipo = 'entrada' AND status IN ('pendente', 'parcial') THEN valor ELSE 0 END) AS entradas_pendentes,
                SUM(CASE WHEN tipo = 'saida' AND status IN ('pendente', 'parcial') THEN valor ELSE 0 END) AS saidas_pendentes,
                SUM(CASE WHEN tipo = 'entrada' THEN valor ELSE 0 END) AS entradas_total,
                SUM(CASE WHEN tipo = 'saida' THEN valor ELSE 0 END) AS saidas_total
            FROM financeiro_lancamentos
        """)

        resumo = _fetchone_dict(cur) or {}

        cur = _execute(conn, """
            SELECT COUNT(*) AS total
            FROM financeiro_paciente_planos
            WHERE tipo = 'combo' AND status = 'ativo'
        """)
        combos_ativos = _fetchone_dict(cur) or {}

        cur = _execute(conn, """
            SELECT COUNT(*) AS total
            FROM financeiro_paciente_planos
            WHERE tipo = 'plano' AND status = 'ativo'
        """)
        planos_ativos = _fetchone_dict(cur) or {}

        saldo_pago = _to_float(resumo.get("entradas_pagas"), 0) - _to_float(resumo.get("saidas_pagas"), 0)
        saldo_projetado = _to_float(resumo.get("entradas_total"), 0) - _to_float(resumo.get("saidas_total"), 0)

        return _ok(resumo={
            "entradas_pagas": _to_float(resumo.get("entradas_pagas"), 0),
            "saidas_pagas": _to_float(resumo.get("saidas_pagas"), 0),
            "entradas_pendentes": _to_float(resumo.get("entradas_pendentes"), 0),
            "saidas_pendentes": _to_float(resumo.get("saidas_pendentes"), 0),
            "entradas_total": _to_float(resumo.get("entradas_total"), 0),
            "saidas_total": _to_float(resumo.get("saidas_total"), 0),
            "saldo_pago": saldo_pago,
            "saldo_projetado": saldo_projetado,
            "combos_ativos": _to_int(combos_ativos.get("total"), 0),
            "planos_ativos": _to_int(planos_ativos.get("total"), 0),
        })

    except Exception as e:
        return _fail(f"Erro ao montar resumo financeiro: {e}", 500)

    finally:
        conn.close()