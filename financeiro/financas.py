# financeiro/financas.py
from __future__ import annotations

import json
from datetime import datetime, date
from typing import Any

from flask import jsonify, render_template, request, session

from db import conectar_db
from . import financeiro_bp
from admin.modulos import require_permission


# ============================================================
# HELPERS
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
    return sql.replace("?", "%s") if _is_postgres_conn(conn) else sql


def _execute(conn, sql: str, params=None):
    params = params or ()
    cur = conn.cursor()
    cur.execute(_adapt_sql(sql, conn), params)
    return cur


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today_iso() -> str:
    return date.today().strftime("%Y-%m-%d")


def _competencia_padrao() -> str:
    return date.today().strftime("%Y-%m")


def _usuario_id_atual():
    return session.get("user_id") or session.get("usuario_id")


def _clinica_id_atual(default=1):
    val = session.get("clinica_id") or session.get("clinic_id") or default

    try:
        return int(val) if val is not None else None
    except Exception:
        return default


def _to_float(v, default=0.0) -> float:
    try:
        if v in (None, "", "null"):
            return float(default)
        return float(str(v).replace(",", "."))
    except Exception:
        return float(default)


def _to_int(v, default=0) -> int:
    try:
        if v in (None, "", "null"):
            return int(default)
        return int(v)
    except Exception:
        return int(default)


def _to_bool(v) -> int:
    if isinstance(v, bool):
        return 1 if v else 0
    return 1 if str(v).lower() in ("1", "true", "sim", "on", "yes") else 0


def _serialize(v):
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")
    return v


def _dict_row(row, cols=None):
    if row is None:
        return None

    if hasattr(row, "keys"):
        return {k: _serialize(row[k]) for k in row.keys()}

    if cols:
        return {cols[i]: _serialize(row[i]) for i in range(len(cols))}

    return dict(row)


def _fetchall_dict(cur):
    rows = cur.fetchall() or []
    cols = [d[0] for d in cur.description] if cur.description else None
    return [_dict_row(r, cols) for r in rows]


def _fetchone_dict(cur):
    row = cur.fetchone()
    cols = [d[0] for d in cur.description] if cur.description else None
    return _dict_row(row, cols)


def _ok(**kwargs):
    payload = {"ok": True}
    payload.update(kwargs)
    return jsonify(payload)


def _fail(msg, status=400, **kwargs):
    payload = {"ok": False, "erro": msg}
    payload.update(kwargs)
    return jsonify(payload), status


def _normalize_digits(txt: str | None) -> str:
    return "".join(ch for ch in str(txt or "") if ch.isdigit())


def _json_loads_safe(value, default=None):
    if default is None:
        default = []

    try:
        return json.loads(value) if value else default
    except Exception:
        return default


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
        else:
            cur = _execute(conn, """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = ?
                LIMIT 1
            """, (table,))

        return bool(cur.fetchone())

    except Exception:
        return False


def _list_columns(conn, table: str) -> set[str]:
    try:
        if _is_postgres_conn(conn):
            cur = _execute(conn, """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = ?
            """, (table,))

            return {
                r["column_name"] if hasattr(r, "keys") else r[0]
                for r in cur.fetchall()
            }

        cur = _execute(conn, f"PRAGMA table_info({table})")

        return {
            r["name"] if hasattr(r, "keys") else r[1]
            for r in cur.fetchall()
        }

    except Exception:
        return set()


def _has_col(conn, table: str, col: str) -> bool:
    return col in _list_columns(conn, table)


def _ensure_column(conn, table: str, column: str, ddl: str):
    if column in _list_columns(conn, table):
        return

    try:
        if _is_postgres_conn(conn):
            _execute(conn, f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl}")
        else:
            _execute(conn, f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    except Exception as e:
        print(f"[FINANCEIRO][SCHEMA] coluna {table}.{column}: {e}")


def _add_clinica_where(conn, table: str, alias: str, where: list[str], params: list, clinica_id=None):
    clinica_id = clinica_id or _clinica_id_atual()

    if not clinica_id:
        return

    if _has_col(conn, table, "clinica_id"):
        where.append(f"{alias}.clinica_id = ?")
        params.append(int(clinica_id))


def _add_clinica_insert(conn, table: str, cols: list[str], vals: list):
    if _has_col(conn, table, "clinica_id") and "clinica_id" not in cols:
        cols.insert(0, "clinica_id")
        vals.insert(0, _clinica_id_atual())

    return cols, vals


def _registrar_log(conn, acao: str, referencia_id=None, detalhes: str = "", sucesso: bool = True):
    """
    Log tolerante:
    - Se tabela logs não existir, ignora.
    - Se alguma coluna não existir, ignora só aquela coluna.
    """

    try:
        if not _table_exists(conn, "logs"):
            return

        cols_logs = _list_columns(conn, "logs")

        campos = []
        valores = []
        params = []

        def add(campo, valor):
            if campo in cols_logs:
                campos.append(campo)
                valores.append("?")
                params.append(valor)

        add("usuario_id", _usuario_id_atual())
        add("clinica_id", _clinica_id_atual())
        add("modulo", "financeiro")
        add("acao", acao)
        add("referencia_id", str(referencia_id or ""))
        add("detalhes", detalhes or "")
        add("sucesso", sucesso)

        if "created_at" in cols_logs:
            campos.append("created_at")
            valores.append("CURRENT_TIMESTAMP")
        elif "criado_em" in cols_logs:
            campos.append("criado_em")
            valores.append("CURRENT_TIMESTAMP")

        if not campos:
            return

        _execute(conn, f"""
            INSERT INTO logs ({", ".join(campos)})
            VALUES ({", ".join(valores)})
        """, params)

    except Exception as e:
        print(f"[FINANCEIRO][LOG] Falha ao registrar log: {e}")


# ============================================================
# SCHEMA
# ============================================================

def ensure_financeiro_schema():
    conn = _conn()

    try:
        if _is_postgres_conn(conn):
            pk = "SERIAL PRIMARY KEY"
            money = "NUMERIC(12,2)"
            dt = "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            clinica_col = "INTEGER"
        else:
            pk = "INTEGER PRIMARY KEY AUTOINCREMENT"
            money = "REAL"
            dt = "TEXT DEFAULT CURRENT_TIMESTAMP"
            clinica_col = "INTEGER"

        _execute(conn, f"""
            CREATE TABLE IF NOT EXISTS financeiro_combos (
                id {pk},
                clinica_id {clinica_col},
                nome TEXT NOT NULL,
                descricao TEXT,
                sessoes INTEGER NOT NULL DEFAULT 0,
                preco {money} NOT NULL DEFAULT 0,
                ativo INTEGER NOT NULL DEFAULT 1,
                criado_em {dt},
                atualizado_em TEXT
            )
        """)

        _execute(conn, f"""
            CREATE TABLE IF NOT EXISTS financeiro_paciente_planos (
                id {pk},
                clinica_id {clinica_col},
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
                valor_total {money} NOT NULL DEFAULT 0,
                recorrente INTEGER NOT NULL DEFAULT 0,
                renovacao_automatica INTEGER NOT NULL DEFAULT 0,
                frequencia TEXT,
                forma_pagamento TEXT,
                observacoes TEXT,
                data_inicio TEXT,
                data_fim TEXT,
                status TEXT NOT NULL DEFAULT 'ativo',
                criado_em {dt},
                atualizado_em TEXT
            )
        """)

        _execute(conn, f"""
            CREATE TABLE IF NOT EXISTS financeiro_lancamentos (
                id {pk},
                clinica_id {clinica_col},
                paciente_id INTEGER,
                plano_id INTEGER,
                origem TEXT DEFAULT 'manual',
                referencia_tipo TEXT,
                referencia_id INTEGER,

                tipo TEXT NOT NULL,
                categoria TEXT,
                subcategoria TEXT,
                descricao TEXT NOT NULL,
                valor {money} NOT NULL DEFAULT 0,

                status TEXT NOT NULL DEFAULT 'pendente',
                forma_pagamento TEXT,

                parcela_numero INTEGER DEFAULT 1,
                parcelas_total INTEGER DEFAULT 1,

                vencimento TEXT,
                data_pagamento TEXT,
                data_movimento TEXT,
                competencia TEXT,

                fornecedor TEXT,
                cliente_nome TEXT,
                documento TEXT,
                observacoes TEXT,

                criado_em {dt},
                atualizado_em TEXT
            )
        """)

        # Colunas obrigatórias de multi-clínica
        _ensure_column(conn, "financeiro_combos", "clinica_id", "INTEGER")
        _ensure_column(conn, "financeiro_paciente_planos", "clinica_id", "INTEGER")
        _ensure_column(conn, "financeiro_lancamentos", "clinica_id", "INTEGER")

        extras_planos = {
            "paciente_cpf": "TEXT",
            "paciente_cns": "TEXT",
            "combo_nome": "TEXT",
            "nome_plano": "TEXT",
            "descricao": "TEXT",
            "sessoes_usadas": "INTEGER NOT NULL DEFAULT 0",
            "valor_total": "NUMERIC(12,2) NOT NULL DEFAULT 0" if _is_postgres_conn(conn) else "REAL NOT NULL DEFAULT 0",
            "recorrente": "INTEGER NOT NULL DEFAULT 0",
            "renovacao_automatica": "INTEGER NOT NULL DEFAULT 0",
            "frequencia": "TEXT",
            "forma_pagamento": "TEXT",
            "observacoes": "TEXT",
            "data_inicio": "TEXT",
            "data_fim": "TEXT",
            "status": "TEXT NOT NULL DEFAULT 'ativo'",
            "criado_em": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP" if _is_postgres_conn(conn) else "TEXT",
            "atualizado_em": "TIMESTAMP" if _is_postgres_conn(conn) else "TEXT",
        }

        for col, ddl in extras_planos.items():
            _ensure_column(conn, "financeiro_paciente_planos", col, ddl)

        extras_lanc = {
            "subcategoria": "TEXT",
            "data_movimento": "TEXT",
            "fornecedor": "TEXT",
            "cliente_nome": "TEXT",
            "documento": "TEXT",
            "observacoes": "TEXT",
            "competencia": "TEXT",
            "origem": "TEXT DEFAULT 'manual'",
            "referencia_tipo": "TEXT",
            "referencia_id": "INTEGER",
            "paciente_id": "INTEGER",
            "plano_id": "INTEGER",
            "parcela_numero": "INTEGER DEFAULT 1",
            "parcelas_total": "INTEGER DEFAULT 1",
            "vencimento": "TEXT",
            "data_pagamento": "TEXT",
            "forma_pagamento": "TEXT",
            "status": "TEXT NOT NULL DEFAULT 'pendente'",
            "criado_em": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP" if _is_postgres_conn(conn) else "TEXT",
            "atualizado_em": "TIMESTAMP" if _is_postgres_conn(conn) else "TEXT",
        }

        for col, ddl in extras_lanc.items():
            _ensure_column(conn, "financeiro_lancamentos", col, ddl)

        if _table_exists(conn, "atendimentos"):
            _ensure_column(conn, "atendimentos", "combo_plano_id", "INTEGER")
            _ensure_column(conn, "atendimentos", "contabiliza_sessao", "INTEGER NOT NULL DEFAULT 1")

        indices = [
            "CREATE INDEX IF NOT EXISTS idx_fin_combos_clinica ON financeiro_combos(clinica_id)",
            "CREATE INDEX IF NOT EXISTS idx_fin_planos_clinica ON financeiro_paciente_planos(clinica_id)",
            "CREATE INDEX IF NOT EXISTS idx_fin_lanc_clinica ON financeiro_lancamentos(clinica_id)",

            "CREATE INDEX IF NOT EXISTS idx_fin_lanc_tipo ON financeiro_lancamentos(tipo)",
            "CREATE INDEX IF NOT EXISTS idx_fin_lanc_status ON financeiro_lancamentos(status)",
            "CREATE INDEX IF NOT EXISTS idx_fin_lanc_categoria ON financeiro_lancamentos(categoria)",
            "CREATE INDEX IF NOT EXISTS idx_fin_lanc_competencia ON financeiro_lancamentos(competencia)",
            "CREATE INDEX IF NOT EXISTS idx_fin_lanc_data_mov ON financeiro_lancamentos(data_movimento)",
            "CREATE INDEX IF NOT EXISTS idx_fin_lanc_venc ON financeiro_lancamentos(vencimento)",
            "CREATE INDEX IF NOT EXISTS idx_fin_lanc_plano ON financeiro_lancamentos(plano_id)",
            "CREATE INDEX IF NOT EXISTS idx_fin_planos_paciente ON financeiro_paciente_planos(paciente_id)",
            "CREATE INDEX IF NOT EXISTS idx_fin_planos_status ON financeiro_paciente_planos(status)",
        ]

        for sql in indices:
            try:
                _execute(conn, sql)
            except Exception as e:
                print(f"[FINANCEIRO][INDEX] {e}")

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


ensure_financeiro_schema()


# ============================================================
# PÁGINAS
# ============================================================

@financeiro_bp.get("/")
@require_permission("financeiro", "ver")
def financeiro_index():
    ensure_financeiro_schema()

    conn = _conn()
    try:
        _registrar_log(conn, "VISUALIZAR_FINANCEIRO", detalhes="Tela principal do financeiro.")
        conn.commit()
    finally:
        conn.close()

    return render_template("financeiro.html", kpis={
        "saldo_caixa": 0.0,
        "entradas": 0.0,
        "saidas": 0.0,
        "pendentes": 0.0,
    })


@financeiro_bp.get("/comercial")
@require_permission("financeiro", "ver")
def comercial_index():
    ensure_financeiro_schema()

    conn = _conn()
    try:
        _registrar_log(conn, "VISUALIZAR_COMERCIAL", detalhes="Tela comercial do financeiro.")
        conn.commit()
    finally:
        conn.close()

    return render_template("comercial.html")


# ============================================================
# PACIENTES
# ============================================================

def _buscar_paciente_por_id(conn, paciente_id: int):
    if not _table_exists(conn, "pacientes"):
        return None

    cols = _list_columns(conn, "pacientes")

    cpf_expr = "COALESCE(cpf, '')" if "cpf" in cols else "''"
    cns_expr = "COALESCE(cns, '')" if "cns" in cols else "''"

    nasc_expr = (
        "COALESCE(nascimento::text, '')"
        if _is_postgres_conn(conn) and "nascimento" in cols
        else ("COALESCE(nascimento, '')" if "nascimento" in cols else "''")
    )

    telefone_expr = "''"

    if "telefone" in cols and "telefone1" in cols:
        telefone_expr = "COALESCE(telefone, telefone1, '')"
    elif "telefone" in cols:
        telefone_expr = "COALESCE(telefone, '')"
    elif "telefone1" in cols:
        telefone_expr = "COALESCE(telefone1, '')"

    where = ["id = ?"]
    params = [paciente_id]
    _add_clinica_where(conn, "pacientes", "pacientes", where, params)

    cur = _execute(conn, f"""
        SELECT
            id,
            COALESCE(nome, '') AS nome,
            {cpf_expr} AS cpf,
            {cns_expr} AS cns,
            {nasc_expr} AS nascimento,
            {telefone_expr} AS telefone
        FROM pacientes
        WHERE {" AND ".join(where)}
        LIMIT 1
    """, params)

    return _fetchone_dict(cur)


@financeiro_bp.get("/api/pacientes/buscar")
@require_permission("financeiro", "ver")
def api_buscar_pacientes():
    ensure_financeiro_schema()

    q = (request.args.get("q") or "").strip()
    limit = min(_to_int(request.args.get("limit"), 20), 100)

    conn = _conn()

    try:
        if not _table_exists(conn, "pacientes"):
            return _ok(items=[])

        cols = _list_columns(conn, "pacientes")

        cpf_expr = "COALESCE(cpf, '')" if "cpf" in cols else "''"
        cns_expr = "COALESCE(cns, '')" if "cns" in cols else "''"

        nasc_expr = (
            "COALESCE(nascimento::text, '')"
            if _is_postgres_conn(conn) and "nascimento" in cols
            else ("COALESCE(nascimento, '')" if "nascimento" in cols else "''")
        )

        where = ["1 = 1"]
        params = []

        _add_clinica_where(conn, "pacientes", "pacientes", where, params)

        if q:
            like = "ILIKE" if _is_postgres_conn(conn) else "LIKE"
            q_digits = _normalize_digits(q)

            where.append(f"""
                (
                    COALESCE(nome, '') {like} ?
                    OR REPLACE(REPLACE(REPLACE({cpf_expr}, '.', ''), '-', ''), ' ', '') {like} ?
                    OR REPLACE(REPLACE(REPLACE({cns_expr}, '.', ''), '-', ''), ' ', '') {like} ?
                )
            """)

            params += [f"%{q}%", f"%{q_digits}%", f"%{q_digits}%"]

        params.append(limit)

        cur = _execute(conn, f"""
            SELECT
                id,
                COALESCE(nome, '') AS nome,
                {cpf_expr} AS cpf,
                {cns_expr} AS cns,
                {nasc_expr} AS nascimento
            FROM pacientes
            WHERE {" AND ".join(where)}
            ORDER BY COALESCE(nome, '')
            LIMIT ?
        """, params)

        return _ok(items=_fetchall_dict(cur))

    except Exception as e:
        return _fail(f"Erro ao buscar pacientes: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.get("/api/pacientes-sem-vinculo")
@require_permission("financeiro", "ver")
def api_pacientes_sem_vinculo():
    ensure_financeiro_schema()

    apenas_com_atendimento = _to_bool(request.args.get("apenas_com_atendimento", 1))
    q = (request.args.get("q") or "").strip()

    conn = _conn()

    try:
        if not _table_exists(conn, "pacientes"):
            return _ok(items=[])

        cols = _list_columns(conn, "pacientes")

        cpf_expr = "COALESCE(p.cpf, '')" if "cpf" in cols else "''"
        cns_expr = "COALESCE(p.cns, '')" if "cns" in cols else "''"

        where = [
            """
            NOT EXISTS (
                SELECT 1
                FROM financeiro_paciente_planos pp
                WHERE pp.paciente_id = p.id
                  AND COALESCE(pp.status, 'ativo') = 'ativo'
            )
            """
        ]
        params = []

        _add_clinica_where(conn, "pacientes", "p", where, params)

        if _has_col(conn, "financeiro_paciente_planos", "clinica_id"):
            where[0] = """
            NOT EXISTS (
                SELECT 1
                FROM financeiro_paciente_planos pp
                WHERE pp.paciente_id = p.id
                  AND pp.clinica_id = ?
                  AND COALESCE(pp.status, 'ativo') = 'ativo'
            )
            """
            params.insert(0, _clinica_id_atual())

        if apenas_com_atendimento and _table_exists(conn, "atendimentos"):
            atend_cols = _list_columns(conn, "atendimentos")

            if "paciente_id" in atend_cols:
                exists_at = """
                    EXISTS (
                        SELECT 1
                        FROM atendimentos a
                        WHERE a.paciente_id = p.id
                    )
                """

                if "clinica_id" in atend_cols:
                    exists_at = """
                        EXISTS (
                            SELECT 1
                            FROM atendimentos a
                            WHERE a.paciente_id = p.id
                              AND a.clinica_id = ?
                        )
                    """
                    params.append(_clinica_id_atual())

                where.append(exists_at)

        if q:
            like = "ILIKE" if _is_postgres_conn(conn) else "LIKE"
            q_digits = _normalize_digits(q)

            where.append(f"""
                (
                    COALESCE(p.nome, '') {like} ?
                    OR REPLACE(REPLACE(REPLACE({cpf_expr}, '.', ''), '-', ''), ' ', '') {like} ?
                    OR REPLACE(REPLACE(REPLACE({cns_expr}, '.', ''), '-', ''), ' ', '') {like} ?
                )
            """)

            params += [f"%{q}%", f"%{q_digits}%", f"%{q_digits}%"]

        cur = _execute(conn, f"""
            SELECT
                p.id,
                COALESCE(p.nome, '') AS nome,
                {cpf_expr} AS cpf,
                {cns_expr} AS cns
            FROM pacientes p
            WHERE {" AND ".join(where)}
            ORDER BY COALESCE(p.nome, '')
        """, params)

        return _ok(items=_fetchall_dict(cur))

    except Exception as e:
        return _fail(f"Erro ao listar pacientes sem vínculo: {e}", 500)

    finally:
        conn.close()


# ============================================================
# PLANOS / COMBOS DO PACIENTE
# ============================================================

def _contar_atendimentos_vinculados(conn, plano_id: int) -> int:
    if not _table_exists(conn, "atendimentos"):
        return 0

    cols = _list_columns(conn, "atendimentos")

    if "combo_plano_id" not in cols:
        return 0

    where = ["combo_plano_id = ?"]
    params = [plano_id]

    if "contabiliza_sessao" in cols:
        where.append("COALESCE(contabiliza_sessao, 1) = 1")

    _add_clinica_where(conn, "atendimentos", "atendimentos", where, params)

    cur = _execute(conn, f"""
        SELECT COUNT(*) AS total
        FROM atendimentos
        WHERE {" AND ".join(where)}
    """, params)

    row = _fetchone_dict(cur) or {}

    return _to_int(row.get("total"), 0)


def _enriquecer_plano(conn, item: dict[str, Any]) -> dict[str, Any]:
    if not item:
        return {}

    contratadas = _to_int(item.get("sessoes_contratadas"), 0)
    usadas = _contar_atendimentos_vinculados(conn, _to_int(item.get("id"), 0))

    restantes = max(0, contratadas - usadas)
    percentual = int(round((usadas / contratadas) * 100)) if contratadas > 0 else 0

    item["sessoes_usadas"] = usadas
    item["sessoes_restantes"] = restantes
    item["percentual_usado"] = percentual
    item["acabou"] = contratadas > 0 and restantes <= 0
    item["perto_de_acabar"] = (
        contratadas > 0
        and restantes <= max(2, round(contratadas * 0.2))
        and restantes > 0
    )

    return item


def _gerar_lancamento_plano(
    conn,
    plano_id,
    paciente_id,
    paciente_nome,
    valor_total,
    forma_pagamento,
    data_inicio,
    descricao,
):
    if valor_total <= 0:
        return

    data_mov = data_inicio or _today_iso()
    competencia = str(data_mov)[:7]

    cols = [
        "paciente_id",
        "plano_id",
        "origem",
        "referencia_tipo",
        "referencia_id",
        "tipo",
        "categoria",
        "subcategoria",
        "descricao",
        "valor",
        "status",
        "forma_pagamento",
        "parcela_numero",
        "parcelas_total",
        "vencimento",
        "data_movimento",
        "competencia",
        "cliente_nome",
        "criado_em",
        "atualizado_em",
    ]

    vals = [
        paciente_id,
        plano_id,
        "plano",
        "plano",
        plano_id,
        "entrada",
        "Serviços clínicos",
        "Combo/Plano",
        descricao,
        valor_total,
        "pendente",
        forma_pagamento,
        1,
        1,
        data_mov,
        data_mov,
        competencia,
        paciente_nome,
        _now_iso(),
        _now_iso(),
    ]

    cols, vals = _add_clinica_insert(conn, "financeiro_lancamentos", cols, vals)

    _execute(conn, f"""
        INSERT INTO financeiro_lancamentos (
            {", ".join(cols)}
        ) VALUES ({", ".join(["?"] * len(cols))})
    """, vals)


@financeiro_bp.get("/api/pacientes-planos")
@require_permission("financeiro", "ver")
def api_listar_pacientes_planos():
    ensure_financeiro_schema()

    conn = _conn()

    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    tipo = (request.args.get("tipo") or "").strip()
    paciente_id = request.args.get("paciente_id")

    try:
        where = ["1 = 1"]
        params = []

        _add_clinica_where(conn, "financeiro_paciente_planos", "financeiro_paciente_planos", where, params)

        if q:
            like = "ILIKE" if _is_postgres_conn(conn) else "LIKE"
            q_digits = _normalize_digits(q)

            where.append(f"""
                (
                    COALESCE(paciente_nome, '') {like} ?
                    OR COALESCE(combo_nome, '') {like} ?
                    OR COALESCE(nome_plano, '') {like} ?
                    OR REPLACE(REPLACE(REPLACE(COALESCE(paciente_cpf, ''), '.', ''), '-', ''), ' ', '') {like} ?
                    OR REPLACE(REPLACE(REPLACE(COALESCE(paciente_cns, ''), '.', ''), '-', ''), ' ', '') {like} ?
                )
            """)

            params += [f"%{q}%", f"%{q}%", f"%{q}%", f"%{q_digits}%", f"%{q_digits}%"]

        if status:
            where.append("status = ?")
            params.append(status)

        if tipo:
            where.append("tipo = ?")
            params.append(tipo)

        if paciente_id:
            where.append("paciente_id = ?")
            params.append(_to_int(paciente_id))

        cur = _execute(conn, f"""
            SELECT *
            FROM financeiro_paciente_planos
            WHERE {" AND ".join(where)}
            ORDER BY criado_em DESC, id DESC
        """, params)

        items = [_enriquecer_plano(conn, row) for row in _fetchall_dict(cur)]

        _registrar_log(
            conn,
            "LISTAR_PLANOS_PACIENTES",
            detalhes=f"q={q}; status={status}; tipo={tipo}; paciente_id={paciente_id}",
        )
        conn.commit()

        return _ok(items=items)

    except Exception as e:
        return _fail(f"Erro ao listar planos: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.get("/api/pacientes-planos/<int:plano_id>")
@require_permission("financeiro", "ver")
def api_obter_paciente_plano(plano_id: int):
    ensure_financeiro_schema()

    conn = _conn()

    try:
        where = ["id = ?"]
        params = [plano_id]

        _add_clinica_where(conn, "financeiro_paciente_planos", "financeiro_paciente_planos", where, params)

        cur = _execute(conn, f"""
            SELECT *
            FROM financeiro_paciente_planos
            WHERE {" AND ".join(where)}
            LIMIT 1
        """, params)

        item = _fetchone_dict(cur)

        if not item:
            return _fail("Plano não encontrado para esta clínica.", 404)

        item = _enriquecer_plano(conn, item)

        lanc_where = ["plano_id = ?"]
        lanc_params = [plano_id]

        _add_clinica_where(conn, "financeiro_lancamentos", "financeiro_lancamentos", lanc_where, lanc_params)

        cur = _execute(conn, f"""
            SELECT *
            FROM financeiro_lancamentos
            WHERE {" AND ".join(lanc_where)}
            ORDER BY parcela_numero ASC, vencimento ASC, id ASC
        """, lanc_params)

        _registrar_log(
            conn,
            "OBTER_PLANO_PACIENTE",
            referencia_id=plano_id,
            detalhes=f"Plano visualizado. id={plano_id}",
        )
        conn.commit()

        return _ok(
            item=item,
            lancamentos=_fetchall_dict(cur)
        )

    except Exception as e:
        return _fail(f"Erro ao obter plano: {e}", 500)

    finally:
        conn.close()
@financeiro_bp.post("/api/pacientes-planos")
@require_permission("financeiro", "editar")
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

    forma_pagamento = (data.get("forma_pagamento") or "").strip()
    data_inicio = (data.get("data_inicio") or _today_iso()).strip()
    data_fim = (data.get("data_fim") or "").strip()
    frequencia = (data.get("frequencia") or "").strip()
    observacoes = (data.get("observacoes") or "").strip()
    status = (data.get("status") or "ativo").strip()

    recorrente = _to_bool(data.get("recorrente"))
    renovacao_automatica = _to_bool(data.get("renovacao_automatica"))

    if paciente_id <= 0:
        return _fail("Selecione um paciente.")

    if tipo not in ("combo", "plano"):
        return _fail("Tipo inválido. Use combo ou plano.")

    conn = _conn()

    try:
        paciente = _buscar_paciente_por_id(conn, paciente_id)

        if not paciente:
            return _fail("Paciente não encontrado para esta clínica.", 404)

        paciente_nome = paciente.get("nome") or ""
        paciente_cpf = paciente.get("cpf") or ""
        paciente_cns = paciente.get("cns") or ""

        combo_nome = None

        if tipo == "combo":
            where_combo = ["id = ?"]
            params_combo = [combo_id]
            _add_clinica_where(conn, "financeiro_combos", "financeiro_combos", where_combo, params_combo)

            cur = _execute(conn, f"""
                SELECT *
                FROM financeiro_combos
                WHERE {" AND ".join(where_combo)}
                LIMIT 1
            """, params_combo)

            combo = _fetchone_dict(cur)

            if not combo:
                return _fail("Combo não encontrado para esta clínica.", 404)

            combo_nome = combo.get("nome")

            if sessoes_contratadas <= 0:
                sessoes_contratadas = _to_int(combo.get("sessoes"), 0)

            if valor_total <= 0:
                valor_total = _to_float(combo.get("preco"), 0)

        if tipo == "plano" and not nome_plano:
            nome_plano = "Particular"

        cols = [
            "paciente_id",
            "paciente_nome",
            "paciente_cpf",
            "paciente_cns",
            "tipo",
            "combo_id",
            "combo_nome",
            "nome_plano",
            "descricao",
            "sessoes_contratadas",
            "sessoes_usadas",
            "valor_total",
            "recorrente",
            "renovacao_automatica",
            "frequencia",
            "forma_pagamento",
            "observacoes",
            "data_inicio",
            "data_fim",
            "status",
            "criado_em",
            "atualizado_em",
        ]

        vals = [
            paciente_id,
            paciente_nome,
            paciente_cpf,
            paciente_cns,
            tipo,
            combo_id,
            combo_nome,
            nome_plano,
            descricao,
            sessoes_contratadas,
            0,
            valor_total,
            recorrente,
            renovacao_automatica,
            frequencia,
            forma_pagamento,
            observacoes,
            data_inicio,
            data_fim,
            status,
            _now_iso(),
            _now_iso(),
        ]

        cols, vals = _add_clinica_insert(conn, "financeiro_paciente_planos", cols, vals)

        if _is_postgres_conn(conn):
            cur = _execute(conn, f"""
                INSERT INTO financeiro_paciente_planos (
                    {", ".join(cols)}
                ) VALUES ({", ".join(["?"] * len(cols))})
                RETURNING id
            """, vals)

            plano_id = _fetchone_dict(cur)["id"]

        else:
            cur = _execute(conn, f"""
                INSERT INTO financeiro_paciente_planos (
                    {", ".join(cols)}
                ) VALUES ({", ".join(["?"] * len(cols))})
            """, vals)

            plano_id = cur.lastrowid

        nome_ref = combo_nome if tipo == "combo" else nome_plano
        desc_fin = f"{'Combo' if tipo == 'combo' else 'Particular'} · {nome_ref} · {paciente_nome}"

        _gerar_lancamento_plano(
            conn,
            plano_id=plano_id,
            paciente_id=paciente_id,
            paciente_nome=paciente_nome,
            valor_total=valor_total,
            forma_pagamento=forma_pagamento,
            data_inicio=data_inicio,
            descricao=desc_fin,
        )

        _registrar_log(
            conn,
            "CRIAR_PLANO_PACIENTE",
            referencia_id=plano_id,
            detalhes=f"Plano/combo vinculado. paciente_id={paciente_id}; tipo={tipo}; valor={valor_total}",
        )

        conn.commit()

        where = ["id = ?"]
        params = [plano_id]
        _add_clinica_where(conn, "financeiro_paciente_planos", "financeiro_paciente_planos", where, params)

        cur = _execute(conn, f"""
            SELECT *
            FROM financeiro_paciente_planos
            WHERE {" AND ".join(where)}
        """, params)

        return _ok(
            item=_enriquecer_plano(conn, _fetchone_dict(cur)),
            mensagem="Plano/combo vinculado com sucesso."
        )

    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao vincular plano/combo: {e}", 500)

    finally:
        conn.close()


# ============================================================
# LIVRO CAIXA / LANÇAMENTOS
# ============================================================

@financeiro_bp.get("/api/lancamentos")
@require_permission("financeiro", "ver")
def api_listar_lancamentos():
    ensure_financeiro_schema()

    conn = _conn()

    tipo = (request.args.get("tipo") or "").strip()
    status = (request.args.get("status") or "").strip()
    categoria = (request.args.get("categoria") or "").strip()
    competencia = (request.args.get("competencia") or "").strip()
    q = (request.args.get("q") or "").strip()

    data_ini = (request.args.get("data_ini") or "").strip()
    data_fim = (request.args.get("data_fim") or "").strip()

    page = max(1, _to_int(request.args.get("page"), 1))
    per_page = min(max(1, _to_int(request.args.get("per_page"), 100)), 500)
    offset = (page - 1) * per_page

    data_ref = (
        "COALESCE(data_movimento, data_pagamento, vencimento, criado_em::text)"
        if _is_postgres_conn(conn)
        else "COALESCE(data_movimento, data_pagamento, vencimento, criado_em)"
    )

    try:
        where = ["1 = 1"]
        params = []

        _add_clinica_where(conn, "financeiro_lancamentos", "financeiro_lancamentos", where, params)

        if tipo in ("entrada", "saida"):
            where.append("tipo = ?")
            params.append(tipo)

        if status:
            where.append("status = ?")
            params.append(status)

        if categoria:
            where.append("categoria = ?")
            params.append(categoria)

        if competencia:
            where.append("competencia = ?")
            params.append(competencia)

        if data_ini:
            where.append(f"{data_ref} >= ?")
            params.append(data_ini)

        if data_fim:
            where.append(f"{data_ref} <= ?")
            params.append(data_fim)

        if q:
            like = "ILIKE" if _is_postgres_conn(conn) else "LIKE"
            where.append(f"""
                (
                    COALESCE(descricao, '') {like} ?
                    OR COALESCE(categoria, '') {like} ?
                    OR COALESCE(subcategoria, '') {like} ?
                    OR COALESCE(cliente_nome, '') {like} ?
                    OR COALESCE(fornecedor, '') {like} ?
                    OR COALESCE(documento, '') {like} ?
                    OR COALESCE(observacoes, '') {like} ?
                )
            """)
            params += [f"%{q}%"] * 7

        where_sql = " AND ".join(where)

        cur = _execute(conn, f"""
            SELECT COUNT(*) AS total
            FROM financeiro_lancamentos
            WHERE {where_sql}
        """, params)

        total = _to_int((_fetchone_dict(cur) or {}).get("total"), 0)

        cur = _execute(conn, f"""
            SELECT *
            FROM financeiro_lancamentos
            WHERE {where_sql}
            ORDER BY {data_ref} DESC, id DESC
            LIMIT ? OFFSET ?
        """, params + [per_page, offset])

        _registrar_log(
            conn,
            "LISTAR_LANCAMENTOS",
            detalhes=f"tipo={tipo}; status={status}; categoria={categoria}; competencia={competencia}; q={q}",
        )
        conn.commit()

        return _ok(
            items=_fetchall_dict(cur),
            total=total,
            page=page,
            per_page=per_page,
        )

    except Exception as e:
        return _fail(f"Erro ao listar lançamentos: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.post("/api/lancamentos")
@require_permission("financeiro", "editar")
def api_criar_lancamento():
    ensure_financeiro_schema()

    data = request.get_json(silent=True) or request.form

    tipo = (data.get("tipo") or "").strip().lower()
    categoria = (data.get("categoria") or "").strip()
    subcategoria = (data.get("subcategoria") or "").strip()
    descricao = (data.get("descricao") or "").strip()
    valor = _to_float(data.get("valor"), 0)

    status = (data.get("status") or "pago").strip().lower()
    forma_pagamento = (data.get("forma_pagamento") or "").strip()

    data_movimento = (data.get("data_movimento") or data.get("data_pagamento") or _today_iso()).strip()
    vencimento = (data.get("vencimento") or data_movimento).strip()
    data_pagamento = (data.get("data_pagamento") or (data_movimento if status == "pago" else "")).strip()

    competencia = (data.get("competencia") or str(data_movimento)[:7] or _competencia_padrao()).strip()

    fornecedor = (data.get("fornecedor") or "").strip()
    cliente_nome = (data.get("cliente_nome") or "").strip()
    documento = (data.get("documento") or "").strip()
    observacoes = (data.get("observacoes") or "").strip()

    paciente_id = _to_int(data.get("paciente_id"), 0) or None
    plano_id = _to_int(data.get("plano_id"), 0) or None

    origem = (data.get("origem") or "manual").strip()
    referencia_tipo = (data.get("referencia_tipo") or "").strip()
    referencia_id = _to_int(data.get("referencia_id"), 0) or None

    if tipo not in ("entrada", "saida"):
        return _fail("Tipo inválido. Use entrada ou saida.")

    if not descricao:
        return _fail("Informe a descrição.")

    if valor <= 0:
        return _fail("Informe um valor maior que zero.")

    if not categoria:
        categoria = "Receita avulsa" if tipo == "entrada" else "Despesa operacional"

    conn = _conn()

    try:
        cols = [
            "paciente_id",
            "plano_id",
            "origem",
            "referencia_tipo",
            "referencia_id",
            "tipo",
            "categoria",
            "subcategoria",
            "descricao",
            "valor",
            "status",
            "forma_pagamento",
            "parcela_numero",
            "parcelas_total",
            "vencimento",
            "data_pagamento",
            "data_movimento",
            "competencia",
            "fornecedor",
            "cliente_nome",
            "documento",
            "observacoes",
            "criado_em",
            "atualizado_em",
        ]

        vals = [
            paciente_id,
            plano_id,
            origem,
            referencia_tipo,
            referencia_id,
            tipo,
            categoria,
            subcategoria,
            descricao,
            valor,
            status,
            forma_pagamento,
            1,
            1,
            vencimento,
            data_pagamento,
            data_movimento,
            competencia,
            fornecedor,
            cliente_nome,
            documento,
            observacoes,
            _now_iso(),
            _now_iso(),
        ]

        cols, vals = _add_clinica_insert(conn, "financeiro_lancamentos", cols, vals)

        if _is_postgres_conn(conn):
            cur = _execute(conn, f"""
                INSERT INTO financeiro_lancamentos (
                    {", ".join(cols)}
                ) VALUES ({", ".join(["?"] * len(cols))})
                RETURNING id
            """, vals)

            lanc_id = _fetchone_dict(cur)["id"]

        else:
            cur = _execute(conn, f"""
                INSERT INTO financeiro_lancamentos (
                    {", ".join(cols)}
                ) VALUES ({", ".join(["?"] * len(cols))})
            """, vals)

            lanc_id = cur.lastrowid

        _registrar_log(
            conn,
            "CRIAR_LANCAMENTO",
            referencia_id=lanc_id,
            detalhes=f"{tipo} · {descricao} · valor={valor}",
        )

        conn.commit()

        where = ["id = ?"]
        params = [lanc_id]
        _add_clinica_where(conn, "financeiro_lancamentos", "financeiro_lancamentos", where, params)

        cur = _execute(conn, f"""
            SELECT *
            FROM financeiro_lancamentos
            WHERE {" AND ".join(where)}
        """, params)

        return _ok(
            item=_fetchone_dict(cur),
            mensagem="Lançamento registrado com sucesso."
        )

    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao criar lançamento: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.put("/api/lancamentos/<int:lancamento_id>")
@require_permission("financeiro", "editar")
def api_editar_lancamento(lancamento_id):
    ensure_financeiro_schema()

    data = request.get_json(silent=True) or request.form

    tipo = (data.get("tipo") or "").strip().lower()
    categoria = (data.get("categoria") or "").strip()
    subcategoria = (data.get("subcategoria") or "").strip()
    descricao = (data.get("descricao") or "").strip()
    valor = _to_float(data.get("valor"), 0)

    status = (data.get("status") or "pendente").strip().lower()
    forma_pagamento = (data.get("forma_pagamento") or "").strip()

    data_movimento = (data.get("data_movimento") or data.get("data_pagamento") or _today_iso()).strip()
    vencimento = (data.get("vencimento") or data_movimento).strip()
    data_pagamento = (data.get("data_pagamento") or (data_movimento if status == "pago" else "")).strip()
    competencia = (data.get("competencia") or str(data_movimento)[:7] or _competencia_padrao()).strip()

    fornecedor = (data.get("fornecedor") or "").strip()
    cliente_nome = (data.get("cliente_nome") or "").strip()
    documento = (data.get("documento") or "").strip()
    observacoes = (data.get("observacoes") or "").strip()

    if tipo not in ("entrada", "saida"):
        return _fail("Tipo inválido.")

    if not descricao:
        return _fail("Informe a descrição.")

    if valor <= 0:
        return _fail("Valor inválido.")

    conn = _conn()

    try:
        where = ["id = ?"]
        params = [lancamento_id]
        _add_clinica_where(conn, "financeiro_lancamentos", "financeiro_lancamentos", where, params)

        cur = _execute(conn, f"""
            SELECT id
            FROM financeiro_lancamentos
            WHERE {" AND ".join(where)}
            LIMIT 1
        """, params)

        if not cur.fetchone():
            return _fail("Lançamento não encontrado para esta clínica.", 404)

        _execute(conn, f"""
            UPDATE financeiro_lancamentos
            SET
                tipo = ?,
                categoria = ?,
                subcategoria = ?,
                descricao = ?,
                valor = ?,
                status = ?,
                forma_pagamento = ?,
                vencimento = ?,
                data_pagamento = ?,
                data_movimento = ?,
                competencia = ?,
                fornecedor = ?,
                cliente_nome = ?,
                documento = ?,
                observacoes = ?,
                atualizado_em = ?
            WHERE {" AND ".join(where)}
        """, (
            tipo,
            categoria,
            subcategoria,
            descricao,
            valor,
            status,
            forma_pagamento,
            vencimento,
            data_pagamento,
            data_movimento,
            competencia,
            fornecedor,
            cliente_nome,
            documento,
            observacoes,
            _now_iso(),
            *params,
        ))

        _registrar_log(
            conn,
            "EDITAR_LANCAMENTO",
            referencia_id=lancamento_id,
            detalhes=f"{tipo} · {descricao} · valor={valor}",
        )

        conn.commit()

        cur = _execute(conn, f"""
            SELECT *
            FROM financeiro_lancamentos
            WHERE {" AND ".join(where)}
        """, params)

        return _ok(
            item=_fetchone_dict(cur),
            mensagem="Lançamento atualizado com sucesso."
        )

    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao atualizar lançamento: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.delete("/api/lancamentos/<int:lancamento_id>")
@require_permission("financeiro", "editar")
def api_excluir_lancamento(lancamento_id):
    ensure_financeiro_schema()

    conn = _conn()

    try:
        where = ["id = ?"]
        params = [lancamento_id]
        _add_clinica_where(conn, "financeiro_lancamentos", "financeiro_lancamentos", where, params)

        cur = _execute(conn, f"""
            SELECT id
            FROM financeiro_lancamentos
            WHERE {" AND ".join(where)}
            LIMIT 1
        """, params)

        if not cur.fetchone():
            return _fail("Lançamento não encontrado para esta clínica.", 404)

        _execute(conn, f"""
            DELETE FROM financeiro_lancamentos
            WHERE {" AND ".join(where)}
        """, params)

        _registrar_log(
            conn,
            "EXCLUIR_LANCAMENTO",
            referencia_id=lancamento_id,
            detalhes="Lançamento excluído.",
        )

        conn.commit()

        return _ok(mensagem="Lançamento excluído com sucesso.")

    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao excluir lançamento: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.post("/api/lancamentos/<int:lancamento_id>/pagar")
@require_permission("financeiro", "editar")
def api_marcar_pago(lancamento_id):
    ensure_financeiro_schema()

    data = request.get_json(silent=True) or request.form

    data_pagamento = (data.get("data_pagamento") or _today_iso()).strip()
    forma_pagamento = (data.get("forma_pagamento") or "").strip()

    conn = _conn()

    try:
        where = ["id = ?"]
        params = [lancamento_id]
        _add_clinica_where(conn, "financeiro_lancamentos", "financeiro_lancamentos", where, params)

        cur = _execute(conn, f"""
            SELECT id
            FROM financeiro_lancamentos
            WHERE {" AND ".join(where)}
            LIMIT 1
        """, params)

        if not cur.fetchone():
            return _fail("Lançamento não encontrado para esta clínica.", 404)

        if forma_pagamento:
            _execute(conn, f"""
                UPDATE financeiro_lancamentos
                SET
                    status = 'pago',
                    data_pagamento = ?,
                    data_movimento = ?,
                    forma_pagamento = ?,
                    atualizado_em = ?
                WHERE {" AND ".join(where)}
            """, (
                data_pagamento,
                data_pagamento,
                forma_pagamento,
                _now_iso(),
                *params,
            ))
        else:
            _execute(conn, f"""
                UPDATE financeiro_lancamentos
                SET
                    status = 'pago',
                    data_pagamento = ?,
                    data_movimento = ?,
                    atualizado_em = ?
                WHERE {" AND ".join(where)}
            """, (
                data_pagamento,
                data_pagamento,
                _now_iso(),
                *params,
            ))

        _registrar_log(
            conn,
            "MARCAR_LANCAMENTO_PAGO",
            referencia_id=lancamento_id,
            detalhes=f"Pagamento em {data_pagamento}; forma={forma_pagamento}",
        )

        conn.commit()

        cur = _execute(conn, f"""
            SELECT *
            FROM financeiro_lancamentos
            WHERE {" AND ".join(where)}
        """, params)

        return _ok(
            item=_fetchone_dict(cur),
            mensagem="Lançamento marcado como pago."
        )

    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao marcar como pago: {e}", 500)

    finally:
        conn.close()


# ============================================================
# RESUMO / FECHAMENTO
# ============================================================

@financeiro_bp.get("/api/resumo")
@require_permission("financeiro", "ver")
def api_resumo_financeiro():
    ensure_financeiro_schema()

    conn = _conn()

    competencia = (request.args.get("competencia") or "").strip()
    data_ini = (request.args.get("data_ini") or "").strip()
    data_fim = (request.args.get("data_fim") or "").strip()

    data_ref = (
        "COALESCE(data_movimento, data_pagamento, vencimento, criado_em::text)"
        if _is_postgres_conn(conn)
        else "COALESCE(data_movimento, data_pagamento, vencimento, criado_em)"
    )

    try:
        where = ["1 = 1"]
        params = []

        _add_clinica_where(conn, "financeiro_lancamentos", "financeiro_lancamentos", where, params)

        if competencia:
            where.append("competencia = ?")
            params.append(competencia)

        if data_ini:
            where.append(f"{data_ref} >= ?")
            params.append(data_ini)

        if data_fim:
            where.append(f"{data_ref} <= ?")
            params.append(data_fim)

        where_sql = " AND ".join(where)

        cur = _execute(conn, f"""
            SELECT
                SUM(CASE WHEN tipo = 'entrada' AND status = 'pago' THEN valor ELSE 0 END) AS entradas_pagas,
                SUM(CASE WHEN tipo = 'saida' AND status = 'pago' THEN valor ELSE 0 END) AS saidas_pagas,
                SUM(CASE WHEN tipo = 'entrada' AND status IN ('pendente', 'parcial') THEN valor ELSE 0 END) AS entradas_pendentes,
                SUM(CASE WHEN tipo = 'saida' AND status IN ('pendente', 'parcial') THEN valor ELSE 0 END) AS saidas_pendentes,
                SUM(CASE WHEN tipo = 'entrada' THEN valor ELSE 0 END) AS entradas_total,
                SUM(CASE WHEN tipo = 'saida' THEN valor ELSE 0 END) AS saidas_total,
                COUNT(*) AS qtd_lancamentos
            FROM financeiro_lancamentos
            WHERE {where_sql}
        """, params)

        r = _fetchone_dict(cur) or {}

        entradas_pagas = _to_float(r.get("entradas_pagas"), 0)
        saidas_pagas = _to_float(r.get("saidas_pagas"), 0)
        entradas_total = _to_float(r.get("entradas_total"), 0)
        saidas_total = _to_float(r.get("saidas_total"), 0)

        planos_where = ["status = 'ativo'"]
        planos_params = []
        _add_clinica_where(conn, "financeiro_paciente_planos", "financeiro_paciente_planos", planos_where, planos_params)

        cur = _execute(conn, f"""
            SELECT COUNT(*) AS total
            FROM financeiro_paciente_planos
            WHERE {" AND ".join(planos_where)}
        """, planos_params)

        planos_ativos = _to_int((_fetchone_dict(cur) or {}).get("total"), 0)

        return _ok(resumo={
            "entradas_pagas": entradas_pagas,
            "saidas_pagas": saidas_pagas,
            "entradas_pendentes": _to_float(r.get("entradas_pendentes"), 0),
            "saidas_pendentes": _to_float(r.get("saidas_pendentes"), 0),
            "entradas_total": entradas_total,
            "saidas_total": saidas_total,
            "saldo_pago": entradas_pagas - saidas_pagas,
            "saldo_projetado": entradas_total - saidas_total,
            "qtd_lancamentos": _to_int(r.get("qtd_lancamentos"), 0),
            "planos_ativos": planos_ativos,
        })

    except Exception as e:
        return _fail(f"Erro ao montar resumo: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.get("/api/fechamento")
@require_permission("financeiro", "ver")
def api_fechamento():
    ensure_financeiro_schema()

    conn = _conn()
    competencia = (request.args.get("competencia") or _competencia_padrao()).strip()

    data_ref = (
        "COALESCE(data_movimento, data_pagamento, vencimento, criado_em::text)"
        if _is_postgres_conn(conn)
        else "COALESCE(data_movimento, data_pagamento, vencimento, criado_em)"
    )

    try:
        where = ["competencia = ?"]
        params = [competencia]

        _add_clinica_where(conn, "financeiro_lancamentos", "financeiro_lancamentos", where, params)

        cur = _execute(conn, f"""
            SELECT
                categoria,
                tipo,
                SUM(CASE WHEN status = 'pago' THEN valor ELSE 0 END) AS total_pago,
                SUM(CASE WHEN status IN ('pendente', 'parcial') THEN valor ELSE 0 END) AS total_pendente,
                SUM(valor) AS total_geral,
                COUNT(*) AS quantidade
            FROM financeiro_lancamentos
            WHERE {" AND ".join(where)}
            GROUP BY categoria, tipo
            ORDER BY tipo ASC, categoria ASC
        """, params)

        por_categoria = _fetchall_dict(cur)

        cur = _execute(conn, f"""
            SELECT
                SUBSTR({data_ref}, 1, 10) AS data_ref,
                SUM(CASE WHEN tipo = 'entrada' AND status = 'pago' THEN valor ELSE 0 END) AS entradas,
                SUM(CASE WHEN tipo = 'saida' AND status = 'pago' THEN valor ELSE 0 END) AS saidas
            FROM financeiro_lancamentos
            WHERE {" AND ".join(where)}
            GROUP BY SUBSTR({data_ref}, 1, 10)
            ORDER BY data_ref ASC
        """, params)

        fluxo_diario = _fetchall_dict(cur)

        entradas = 0.0
        saidas = 0.0
        saldo_acumulado = 0.0

        for dia in fluxo_diario:
            entradas_dia = _to_float(dia.get("entradas"), 0)
            saidas_dia = _to_float(dia.get("saidas"), 0)

            entradas += entradas_dia
            saidas += saidas_dia
            saldo_acumulado += entradas_dia - saidas_dia

            dia["saldo_dia"] = entradas_dia - saidas_dia
            dia["saldo_acumulado"] = saldo_acumulado

        _registrar_log(
            conn,
            "GERAR_FECHAMENTO",
            detalhes=f"competencia={competencia}",
        )
        conn.commit()

        return _ok(fechamento={
            "competencia": competencia,
            "entradas": entradas,
            "saidas": saidas,
            "saldo": entradas - saidas,
            "por_categoria": por_categoria,
            "fluxo_diario": fluxo_diario,
        })

    except Exception as e:
        return _fail(f"Erro ao montar fechamento: {e}", 500)

    finally:
        conn.close()


# ============================================================
# CATEGORIAS PADRÃO PARA O FRONT
# ============================================================

@financeiro_bp.get("/api/categorias")
@require_permission("financeiro", "ver")
def api_categorias_financeiras():
    return _ok(
        receitas=[
            "Serviços clínicos",
            "Combo/Plano",
            "Particular",
            "Materiais terapêuticos",
            "Jogos e brinquedos",
            "Produtos",
            "Outras receitas",
        ],
        despesas=[
            "Aluguel",
            "Água",
            "Energia",
            "Internet",
            "Sistema",
            "Funcionários",
            "Material de consumo",
            "Manutenção",
            "Impostos e taxas",
            "Outras despesas",
        ],
        formas_pagamento=[
            "Dinheiro",
            "Pix",
            "Cartão de débito",
            "Cartão de crédito",
            "Boleto",
            "Transferência",
            "Outro",
        ],
        status=[
            "pago",
            "pendente",
            "parcial",
            "cancelado",
        ],
    )