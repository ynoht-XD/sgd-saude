# financeiro/financas.py
from __future__ import annotations

import json
from datetime import datetime, date
from typing import Any

from flask import jsonify, render_template, request

from db import conectar_db
from . import financeiro_bp


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


def _ensure_column(conn, table: str, column: str, ddl: str):
    if column in _list_columns(conn, table):
        return

    try:
        if _is_postgres_conn(conn):
            _execute(conn, f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl}")
        else:
            _execute(conn, f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    except Exception:
        pass


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
        else:
            pk = "INTEGER PRIMARY KEY AUTOINCREMENT"
            money = "REAL"
            dt = "TEXT DEFAULT CURRENT_TIMESTAMP"

        _execute(conn, f"""
            CREATE TABLE IF NOT EXISTS financeiro_combos (
                id {pk},
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

    return _fetchone_dict(cur)


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

        cpf_expr = "COALESCE(cpf, '')" if "cpf" in cols else "''"
        cns_expr = "COALESCE(cns, '')" if "cns" in cols else "''"

        nasc_expr = (
            "COALESCE(nascimento::text, '')"
            if _is_postgres_conn(conn) and "nascimento" in cols
            else ("COALESCE(nascimento, '')" if "nascimento" in cols else "''")
        )

        sql = f"""
            SELECT
                id,
                COALESCE(nome, '') AS nome,
                {cpf_expr} AS cpf,
                {cns_expr} AS cns,
                {nasc_expr} AS nascimento
            FROM pacientes
            WHERE 1 = 1
        """

        params = []

        if q:
            like = "ILIKE" if _is_postgres_conn(conn) else "LIKE"
            q_digits = _normalize_digits(q)

            sql += f"""
                AND (
                    COALESCE(nome, '') {like} ?
                    OR REPLACE(REPLACE(REPLACE({cpf_expr}, '.', ''), '-', ''), ' ', '') {like} ?
                    OR REPLACE(REPLACE(REPLACE({cns_expr}, '.', ''), '-', ''), ' ', '') {like} ?
                )
            """

            params += [f"%{q}%", f"%{q_digits}%", f"%{q_digits}%"]

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

    apenas_com_atendimento = _to_bool(request.args.get("apenas_com_atendimento", 1))
    q = (request.args.get("q") or "").strip()

    conn = _conn()

    try:
        if not _table_exists(conn, "pacientes"):
            return _ok(items=[])

        cols = _list_columns(conn, "pacientes")

        cpf_expr = "COALESCE(p.cpf, '')" if "cpf" in cols else "''"
        cns_expr = "COALESCE(p.cns, '')" if "cns" in cols else "''"

        sql = f"""
            SELECT
                p.id,
                COALESCE(p.nome, '') AS nome,
                {cpf_expr} AS cpf,
                {cns_expr} AS cns
            FROM pacientes p
            WHERE NOT EXISTS (
                SELECT 1
                FROM financeiro_paciente_planos pp
                WHERE pp.paciente_id = p.id
                  AND COALESCE(pp.status, 'ativo') = 'ativo'
            )
        """

        params = []

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

        if q:
            like = "ILIKE" if _is_postgres_conn(conn) else "LIKE"
            q_digits = _normalize_digits(q)

            sql += f"""
                AND (
                    COALESCE(p.nome, '') {like} ?
                    OR REPLACE(REPLACE(REPLACE({cpf_expr}, '.', ''), '-', ''), ' ', '') {like} ?
                    OR REPLACE(REPLACE(REPLACE({cns_expr}, '.', ''), '-', ''), ' ', '') {like} ?
                )
            """

            params += [f"%{q}%", f"%{q_digits}%", f"%{q_digits}%"]

        sql += " ORDER BY COALESCE(p.nome, '')"

        cur = _execute(conn, sql, params)

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
    item["perto_de_acabar"] = contratadas > 0 and restantes <= max(2, round(contratadas * 0.2)) and restantes > 0

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

    _execute(conn, """
        INSERT INTO financeiro_lancamentos (
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
            parcela_numero,
            parcelas_total,
            vencimento,
            data_movimento,
            competencia,
            cliente_nome,
            criado_em,
            atualizado_em
        ) VALUES (?, ?, 'plano', 'plano', ?, 'entrada',
                  'Serviços clínicos', 'Combo/Plano', ?, ?,
                  'pendente', ?, 1, 1, ?, ?, ?, ?, ?, ?)
    """, (
        paciente_id,
        plano_id,
        plano_id,
        descricao,
        valor_total,
        forma_pagamento,
        data_mov,
        data_mov,
        competencia,
        paciente_nome,
        _now_iso(),
        _now_iso(),
    ))


@financeiro_bp.get("/api/pacientes-planos")
def api_listar_pacientes_planos():
    ensure_financeiro_schema()

    conn = _conn()

    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    tipo = (request.args.get("tipo") or "").strip()
    paciente_id = request.args.get("paciente_id")

    try:
        sql = """
            SELECT *
            FROM financeiro_paciente_planos
            WHERE 1 = 1
        """

        params = []

        if q:
            like = "ILIKE" if _is_postgres_conn(conn) else "LIKE"
            q_digits = _normalize_digits(q)

            sql += f"""
                AND (
                    COALESCE(paciente_nome, '') {like} ?
                    OR COALESCE(combo_nome, '') {like} ?
                    OR COALESCE(nome_plano, '') {like} ?
                    OR REPLACE(REPLACE(REPLACE(COALESCE(paciente_cpf, ''), '.', ''), '-', ''), ' ', '') {like} ?
                    OR REPLACE(REPLACE(REPLACE(COALESCE(paciente_cns, ''), '.', ''), '-', ''), ' ', '') {like} ?
                )
            """

            params += [f"%{q}%", f"%{q}%", f"%{q}%", f"%{q_digits}%", f"%{q_digits}%"]

        if status:
            sql += " AND status = ?"
            params.append(status)

        if tipo:
            sql += " AND tipo = ?"
            params.append(tipo)

        if paciente_id:
            sql += " AND paciente_id = ?"
            params.append(_to_int(paciente_id))

        sql += " ORDER BY criado_em DESC, id DESC"

        cur = _execute(conn, sql, params)
        items = [_enriquecer_plano(conn, row) for row in _fetchall_dict(cur)]

        return _ok(items=items)

    except Exception as e:
        return _fail(f"Erro ao listar planos: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.get("/api/pacientes-planos/<int:plano_id>")
def api_obter_paciente_plano(plano_id: int):
    ensure_financeiro_schema()

    conn = _conn()

    try:
        cur = _execute(conn, """
            SELECT *
            FROM financeiro_paciente_planos
            WHERE id = ?
            LIMIT 1
        """, (plano_id,))

        item = _fetchone_dict(cur)

        if not item:
            return _fail("Plano não encontrado.", 404)

        item = _enriquecer_plano(conn, item)

        cur = _execute(conn, """
            SELECT *
            FROM financeiro_lancamentos
            WHERE plano_id = ?
            ORDER BY parcela_numero ASC, vencimento ASC, id ASC
        """, (plano_id,))

        return _ok(
            item=item,
            lancamentos=_fetchall_dict(cur)
        )

    except Exception as e:
        return _fail(f"Erro ao obter plano: {e}", 500)

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
            return _fail("Paciente não encontrado.", 404)

        paciente_nome = paciente.get("nome") or ""
        paciente_cpf = paciente.get("cpf") or ""
        paciente_cns = paciente.get("cns") or ""

        combo_nome = None

        if tipo == "combo":
            cur = _execute(conn, """
                SELECT *
                FROM financeiro_combos
                WHERE id = ?
                LIMIT 1
            """, (combo_id,))

            combo = _fetchone_dict(cur)

            if not combo:
                return _fail("Combo não encontrado.", 404)

            combo_nome = combo.get("nome")

            if sessoes_contratadas <= 0:
                sessoes_contratadas = _to_int(combo.get("sessoes"), 0)

            if valor_total <= 0:
                valor_total = _to_float(combo.get("preco"), 0)

        if tipo == "plano" and not nome_plano:
            nome_plano = "Particular"

        if _is_postgres_conn(conn):
            cur = _execute(conn, """
                INSERT INTO financeiro_paciente_planos (
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
                    sessoes_usadas,
                    valor_total,
                    recorrente,
                    renovacao_automatica,
                    frequencia,
                    forma_pagamento,
                    observacoes,
                    data_inicio,
                    data_fim,
                    status,
                    criado_em,
                    atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
            """, (
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
            ))

            plano_id = _fetchone_dict(cur)["id"]

        else:
            cur = _execute(conn, """
                INSERT INTO financeiro_paciente_planos (
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
                    sessoes_usadas,
                    valor_total,
                    recorrente,
                    renovacao_automatica,
                    frequencia,
                    forma_pagamento,
                    observacoes,
                    data_inicio,
                    data_fim,
                    status,
                    criado_em,
                    atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
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
            ))

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

        conn.commit()

        cur = _execute(conn, """
            SELECT *
            FROM financeiro_paciente_planos
            WHERE id = ?
        """, (plano_id,))

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
        if _is_postgres_conn(conn):
            cur = _execute(conn, """
                INSERT INTO financeiro_lancamentos (
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
                    parcela_numero,
                    parcelas_total,
                    vencimento,
                    data_pagamento,
                    data_movimento,
                    competencia,
                    fornecedor,
                    cliente_nome,
                    documento,
                    observacoes,
                    criado_em,
                    atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1,
                          ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
            """, (
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
            ))

            lanc_id = _fetchone_dict(cur)["id"]

        else:
            cur = _execute(conn, """
                INSERT INTO financeiro_lancamentos (
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
                    parcela_numero,
                    parcelas_total,
                    vencimento,
                    data_pagamento,
                    data_movimento,
                    competencia,
                    fornecedor,
                    cliente_nome,
                    documento,
                    observacoes,
                    criado_em,
                    atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1,
                          ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
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
            ))

            lanc_id = cur.lastrowid

        conn.commit()

        cur = _execute(conn, """
            SELECT *
            FROM financeiro_lancamentos
            WHERE id = ?
        """, (lanc_id,))

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
        _execute(conn, """
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
            WHERE id = ?
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
            lancamento_id,
        ))

        conn.commit()

        cur = _execute(conn, """
            SELECT *
            FROM financeiro_lancamentos
            WHERE id = ?
        """, (lancamento_id,))

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
def api_excluir_lancamento(lancamento_id):
    ensure_financeiro_schema()

    conn = _conn()

    try:
        _execute(conn, """
            DELETE FROM financeiro_lancamentos
            WHERE id = ?
        """, (lancamento_id,))

        conn.commit()

        return _ok(mensagem="Lançamento excluído com sucesso.")

    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao excluir lançamento: {e}", 500)

    finally:
        conn.close()


@financeiro_bp.post("/api/lancamentos/<int:lancamento_id>/pagar")
def api_marcar_pago(lancamento_id):
    ensure_financeiro_schema()

    data = request.get_json(silent=True) or request.form

    data_pagamento = (data.get("data_pagamento") or _today_iso()).strip()
    forma_pagamento = (data.get("forma_pagamento") or "").strip()

    conn = _conn()

    try:
        if forma_pagamento:
            _execute(conn, """
                UPDATE financeiro_lancamentos
                SET
                    status = 'pago',
                    data_pagamento = ?,
                    data_movimento = ?,
                    forma_pagamento = ?,
                    atualizado_em = ?
                WHERE id = ?
            """, (
                data_pagamento,
                data_pagamento,
                forma_pagamento,
                _now_iso(),
                lancamento_id,
            ))
        else:
            _execute(conn, """
                UPDATE financeiro_lancamentos
                SET
                    status = 'pago',
                    data_pagamento = ?,
                    data_movimento = ?,
                    atualizado_em = ?
                WHERE id = ?
            """, (
                data_pagamento,
                data_pagamento,
                _now_iso(),
                lancamento_id,
            ))

        conn.commit()

        cur = _execute(conn, """
            SELECT *
            FROM financeiro_lancamentos
            WHERE id = ?
        """, (lancamento_id,))

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
def api_resumo_financeiro():
    ensure_financeiro_schema()

    conn = _conn()

    competencia = (request.args.get("competencia") or "").strip()
    data_ini = (request.args.get("data_ini") or "").strip()
    data_fim = (request.args.get("data_fim") or "").strip()

    try:
        where = ["1 = 1"]
        params = []

        if competencia:
            where.append("competencia = ?")
            params.append(competencia)

        if data_ini:
            where.append("COALESCE(data_movimento, data_pagamento, vencimento, criado_em) >= ?")
            params.append(data_ini)

        if data_fim:
            where.append("COALESCE(data_movimento, data_pagamento, vencimento, criado_em) <= ?")
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

        cur = _execute(conn, """
            SELECT COUNT(*) AS total
            FROM financeiro_paciente_planos
            WHERE status = 'ativo'
        """)

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
        cur = _execute(conn, """
            SELECT
                categoria,
                tipo,
                SUM(CASE WHEN status = 'pago' THEN valor ELSE 0 END) AS total_pago,
                SUM(CASE WHEN status IN ('pendente', 'parcial') THEN valor ELSE 0 END) AS total_pendente,
                SUM(valor) AS total_geral,
                COUNT(*) AS quantidade
            FROM financeiro_lancamentos
            WHERE competencia = ?
            GROUP BY categoria, tipo
            ORDER BY tipo ASC, categoria ASC
        """, (competencia,))

        por_categoria = _fetchall_dict(cur)

        cur = _execute(conn, f"""
            SELECT
                SUBSTR({data_ref}, 1, 10) AS data_ref,
                SUM(CASE WHEN tipo = 'entrada' AND status = 'pago' THEN valor ELSE 0 END) AS entradas,
                SUM(CASE WHEN tipo = 'saida' AND status = 'pago' THEN valor ELSE 0 END) AS saidas
            FROM financeiro_lancamentos
            WHERE competencia = ?
            GROUP BY SUBSTR({data_ref}, 1, 10)
            ORDER BY data_ref ASC
        """, (competencia,))

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