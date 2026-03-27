from __future__ import annotations

import json
import sqlite3
from datetime import datetime, date
from typing import Any

from flask import jsonify, render_template, request

from db import conectar_db
from . import financeiro_bp


# ============================================================
# HELPERS BÁSICOS
# ============================================================

def _conn() -> sqlite3.Connection:
    conn = conectar_db()
    conn.row_factory = sqlite3.Row
    return conn


def _dict_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def _rows_to_dict(rows) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


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


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str):
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        LIMIT 1
    """, (table,)).fetchone()
    return bool(row)


# ============================================================
# SCHEMA / GARANTIAS MÍNIMAS
# ============================================================

def ensure_financeiro_schema():
    conn = _conn()
    try:
        # ------------------------------
        # COMBOS
        # ------------------------------
        conn.execute("""
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

        # ------------------------------
        # PACIENTE x COMBOS/PLANOS
        # ------------------------------
        conn.execute("""
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

        # ------------------------------
        # LIVRO CAIXA / LANÇAMENTOS
        # ------------------------------
        conn.execute("""
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

        _ensure_column(conn, "financeiro_paciente_planos", "forma_pagamento", "TEXT")
        _ensure_column(conn, "financeiro_paciente_planos", "observacoes", "TEXT")
        _ensure_column(conn, "financeiro_paciente_planos", "frequencia", "TEXT")
        _ensure_column(conn, "financeiro_paciente_planos", "data_inicio", "TEXT")
        _ensure_column(conn, "financeiro_paciente_planos", "data_fim", "TEXT")
        _ensure_column(conn, "financeiro_paciente_planos", "recorrente", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "financeiro_paciente_planos", "renovacao_automatica", "INTEGER NOT NULL DEFAULT 0")

        _ensure_column(conn, "financeiro_lancamentos", "competencia", "TEXT")
        _ensure_column(conn, "financeiro_lancamentos", "origem", "TEXT DEFAULT 'manual'")
        _ensure_column(conn, "financeiro_lancamentos", "referencia_tipo", "TEXT")
        _ensure_column(conn, "financeiro_lancamentos", "referencia_id", "INTEGER")

        # ------------------------------
        # ATENDIMENTOS → vínculo financeiro
        # ------------------------------
        if _table_exists(conn, "atendimentos"):
            _ensure_column(conn, "atendimentos", "combo_plano_id", "INTEGER")
            _ensure_column(conn, "atendimentos", "contabiliza_sessao", "INTEGER NOT NULL DEFAULT 1")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_atend_combo_plano_id ON atendimentos(combo_plano_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_atend_paciente_id ON atendimentos(paciente_id)")

        # Índices
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fin_combo_nome ON financeiro_combos(nome)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fin_pp_paciente_id ON financeiro_paciente_planos(paciente_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fin_pp_status ON financeiro_paciente_planos(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fin_lanc_tipo ON financeiro_lancamentos(tipo)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fin_lanc_status ON financeiro_lancamentos(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fin_lanc_venc ON financeiro_lancamentos(vencimento)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fin_lanc_data_pag ON financeiro_lancamentos(data_pagamento)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fin_lanc_paciente_id ON financeiro_lancamentos(paciente_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fin_lanc_plano_id ON financeiro_lancamentos(plano_id)")

        conn.commit()
    finally:
        conn.close()


ensure_financeiro_schema()


# ============================================================
# HELPERS DE NEGÓCIO
# ============================================================

def _buscar_paciente_por_id(conn: sqlite3.Connection, paciente_id: int):
    return conn.execute("""
        SELECT
            id,
            COALESCE(nome, '') AS nome,
            COALESCE(cpf, '') AS cpf,
            COALESCE(cns, '') AS cns,
            COALESCE(nascimento, '') AS nascimento,
            COALESCE(telefone, telefone1, '') AS telefone
        FROM pacientes
        WHERE id = ?
        LIMIT 1
    """, (paciente_id,)).fetchone()


def _competencia_from_date(dt_text: str | None) -> str:
    if not dt_text:
        return datetime.now().strftime("%Y-%m")
    try:
        return str(dt_text)[:7]
    except Exception:
        return datetime.now().strftime("%Y-%m")


def _safe_label_nome_plano(tipo: str, combo_nome: str | None, nome_plano: str | None) -> str:
    if tipo == "combo":
        return (combo_nome or "Combo").strip()
    return (nome_plano or "Plano do paciente").strip()


def _gerar_lancamentos_do_plano(
    conn: sqlite3.Connection,
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
        conn.execute("""
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

        conn.execute("""
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


def _contar_atendimentos_vinculados(conn: sqlite3.Connection, plano_id: int) -> int:
    """
    Conta quantos atendimentos realmente consomem sessão deste combo/plano.
    Fonte da verdade = tabela atendimentos.
    """
    if not _table_exists(conn, "atendimentos"):
        return 0

    row = conn.execute("""
        SELECT COUNT(*) AS total
        FROM atendimentos
        WHERE combo_plano_id = ?
          AND COALESCE(contabiliza_sessao, 1) = 1
    """, (plano_id,)).fetchone()

    return _to_int(row["total"] if row else 0, 0)


def _recalcular_saldo_sessoes(conn: sqlite3.Connection, plano_id: int):
    """
    Recalcula sessões usadas e restantes com base nos atendimentos vinculados.
    """
    row = conn.execute("""
        SELECT id, sessoes_contratadas, status
        FROM financeiro_paciente_planos
        WHERE id = ?
        LIMIT 1
    """, (plano_id,)).fetchone()

    if not row:
        return

    contratadas = _to_int(row["sessoes_contratadas"], 0)
    usadas = _contar_atendimentos_vinculados(conn, plano_id)

    restantes = max(0, contratadas - usadas)

    novo_status = row["status"] or "ativo"
    if contratadas > 0 and restantes <= 0:
        novo_status = "encerrado"
    elif novo_status == "encerrado" and restantes > 0:
        novo_status = "ativo"

    conn.execute("""
        UPDATE financeiro_paciente_planos
        SET
            sessoes_usadas = ?,
            atualizado_em = ?,
            status = ?
        WHERE id = ?
    """, (
        usadas,
        _now_iso(),
        novo_status,
        plano_id
    ))

def _recalcular_saldo_sessoes(conn: sqlite3.Connection, plano_id: int):
    row = conn.execute("""
        SELECT id, sessoes_contratadas, status
        FROM financeiro_paciente_planos
        WHERE id = ?
        LIMIT 1
    """, (plano_id,)).fetchone()

    if not row:
        return

    contratadas = _to_int(row["sessoes_contratadas"], 0)
    usadas = _contar_atendimentos_vinculados(conn, plano_id)

    if contratadas > 0 and usadas > contratadas:
        usadas = contratadas

    novo_status = row["status"] or "ativo"
    if contratadas > 0 and usadas >= contratadas:
        novo_status = "encerrado"
    elif novo_status == "encerrado" and usadas < contratadas:
        novo_status = "ativo"

    conn.execute("""
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

    percentual = int(round((usadas / contratadas) * 100)) if contratadas else 0
    limite_alerta = max(2, int(round(contratadas * 0.2)))

    return {
        "sessoes_restantes": restantes,
        "perto_de_acabar": restantes > 0 and restantes <= limite_alerta,
        "acabou": restantes <= 0,
        "percentual_usado": percentual,
    }

def _buscar_datas_agendamento_do_paciente(conn: sqlite3.Connection, paciente_nome: str) -> dict[str, Any]:
    if not paciente_nome or not _table_exists(conn, "agendamentos"):
        return {
            "datas_resumo": "",
            "dia_semana": "",
            "indeterminado": False,
        }

    rows = conn.execute("""
        SELECT
            COALESCE(inicio, '') AS inicio,
            COALESCE(fim, '') AS fim,
            COALESCE(dia, '') AS dia,
            COALESCE(recorrente, 0) AS recorrente,
            COALESCE(status, 'ativo') AS status
        FROM agendamentos
        WHERE TRIM(LOWER(COALESCE(paciente, ''))) = TRIM(LOWER(?))
          AND COALESCE(status, 'ativo') = 'ativo'
        ORDER BY inicio
    """, (paciente_nome,)).fetchall()

    if not rows:
        return {
            "datas_resumo": "",
            "dia_semana": "",
            "indeterminado": False,
        }

    dias = []
    datas = []

    for r in rows:
        dia = (r["dia"] or "").strip()
        inicio = (r["inicio"] or "").strip()

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


def _montar_resumo_datas(item: sqlite3.Row | dict[str, Any], agenda_info: dict[str, Any]) -> dict[str, Any]:
    data_inicio = (item["data_inicio"] or "").strip() if item["data_inicio"] is not None else ""
    data_fim = (item["data_fim"] or "").strip() if item["data_fim"] is not None else ""
    frequencia = (item["frequencia"] or "").strip() if item["frequencia"] is not None else ""

    if data_inicio and data_fim:
        return {
            "datas_resumo": f"{data_inicio} até {data_fim}",
            "dia_semana": "",
            "indeterminado": False,
        }

    if data_inicio and not data_fim:
        return {
            "datas_resumo": f"Início: {data_inicio}",
            "dia_semana": "",
            "indeterminado": False,
        }

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
        return {
            "datas_resumo": "",
            "dia_semana": frequencia,
            "indeterminado": True,
        }

    return {
        "datas_resumo": "",
        "dia_semana": "",
        "indeterminado": False,
    }


def _vinculo_ativo_existente(conn: sqlite3.Connection, paciente_id: int, ignore_id: int | None = None):
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
    return conn.execute(sql, params).fetchone()


def _enriquecer_plano_item(conn: sqlite3.Connection, item: dict[str, Any]) -> dict[str, Any]:
    plano_id = _to_int(item.get("id"), 0)
    contratadas = _to_int(item.get("sessoes_contratadas"), 0)

    # ATENÇÃO:
    # usadas vem SEMPRE da tabela atendimentos
    usadas_calc = _contar_atendimentos_vinculados(conn, plano_id)

    item["sessoes_usadas"] = usadas_calc

    faixa = _faixa_consumo(contratadas, usadas_calc)
    item["sessoes_restantes"] = faixa["sessoes_restantes"]
    item["perto_de_acabar"] = faixa["perto_de_acabar"]
    item["acabou"] = faixa["acabou"]
    item["percentual_usado"] = faixa["percentual_usado"]

    agenda_info = _buscar_datas_agendamento_do_paciente(conn, item.get("paciente_nome", ""))
    resumo = _montar_resumo_datas(item, agenda_info)
    item["datas_resumo"] = resumo["datas_resumo"]
    item["dia_semana"] = resumo["dia_semana"]
    item["indeterminado"] = resumo["indeterminado"]

    return item

# ============================================================
# PÁGINAS
# ============================================================

@financeiro_bp.get("/")
def financeiro_index():
    ensure_financeiro_schema()

    kpis = {
        "saldo_caixa": 0.0,
        "entradas": 0.0,
        "saidas": 0.0,
        "pendentes": 0.0,
    }

    return render_template("financeiro.html", kpis=kpis)


@financeiro_bp.get("/comercial")
def comercial_index():
    ensure_financeiro_schema()
    return render_template("comercial.html")


# ============================================================
# PACIENTES - BUSCA
# ============================================================

@financeiro_bp.get("/api/pacientes/buscar")
def api_buscar_pacientes():
    q = (request.args.get("q") or "").strip()
    limit = min(_to_int(request.args.get("limit"), 20), 100)

    conn = _conn()
    try:
        sql = """
            SELECT
                id,
                COALESCE(nome, '') AS nome,
                COALESCE(cpf, '') AS cpf,
                COALESCE(cns, '') AS cns,
                COALESCE(nascimento, '') AS nascimento,
                COALESCE(telefone, telefone1, '') AS telefone
            FROM pacientes
        """
        params: list[Any] = []

        if q:
            q_digits = _normalize_digits(q)
            sql += """
                WHERE
                    COALESCE(nome, '') LIKE ?
                    OR REPLACE(REPLACE(REPLACE(COALESCE(cpf, ''), '.', ''), '-', ''), ' ', '') LIKE ?
                    OR REPLACE(REPLACE(REPLACE(COALESCE(cns, ''), '.', ''), '-', ''), ' ', '') LIKE ?
            """
            params.extend([f"%{q}%", f"%{q_digits}%", f"%{q_digits}%"])

        sql += " ORDER BY COALESCE(nome, '') LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        return _ok(items=_rows_to_dict(rows))
    except Exception as e:
        return _fail(f"Erro ao buscar pacientes: {e}", 500)
    finally:
        conn.close()


@financeiro_bp.get("/api/pacientes-sem-vinculo")
def api_pacientes_sem_vinculo():
    q = (request.args.get("q") or "").strip()
    apenas_com_atendimento = _to_bool(request.args.get("apenas_com_atendimento", 1))

    conn = _conn()
    try:
        sql = """
            SELECT
                p.id,
                COALESCE(p.nome, '') AS nome,
                COALESCE(p.cpf, '') AS cpf,
                COALESCE(p.cns, '') AS cns,
                COALESCE(p.nascimento, '') AS nascimento,
                COALESCE(p.telefone, p.telefone1, '') AS telefone
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
            sql += """
                AND EXISTS (
                    SELECT 1
                    FROM atendimentos a
                    WHERE a.paciente_id = p.id
                       OR TRIM(LOWER(COALESCE(a.nome, ''))) = TRIM(LOWER(COALESCE(p.nome, '')))
                )
            """

        if q:
            q_digits = _normalize_digits(q)
            sql += """
                AND (
                    COALESCE(p.nome, '') LIKE ?
                    OR REPLACE(REPLACE(REPLACE(COALESCE(p.cpf, ''), '.', ''), '-', ''), ' ', '') LIKE ?
                    OR REPLACE(REPLACE(REPLACE(COALESCE(p.cns, ''), '.', ''), '-', ''), ' ', '') LIKE ?
                )
            """
            params.extend([f"%{q}%", f"%{q_digits}%", f"%{q_digits}%"])

        sql += " ORDER BY COALESCE(p.nome, '')"
        rows = conn.execute(sql, params).fetchall()

        return _ok(items=_rows_to_dict(rows))
    except Exception as e:
        return _fail(f"Erro ao listar pacientes sem vínculo: {e}", 500)
    finally:
        conn.close()


# ============================================================
# COMBOS
# ============================================================

@financeiro_bp.get("/api/combos")
def api_listar_combos():
    q = (request.args.get("q") or "").strip()
    ativo = request.args.get("ativo")

    conn = _conn()
    try:
        sql = """
            SELECT
                id, nome, descricao, sessoes, preco, ativo, criado_em, atualizado_em
            FROM financeiro_combos
            WHERE 1=1
        """
        params: list[Any] = []

        if q:
            sql += " AND (nome LIKE ? OR COALESCE(descricao, '') LIKE ?)"
            params.extend([f"%{q}%", f"%{q}%"])

        if ativo in ("0", "1"):
            sql += " AND ativo = ?"
            params.append(int(ativo))

        sql += " ORDER BY ativo DESC, nome ASC"

        rows = conn.execute(sql, params).fetchall()
        return _ok(items=_rows_to_dict(rows))
    except Exception as e:
        return _fail(f"Erro ao listar combos: {e}", 500)
    finally:
        conn.close()


@financeiro_bp.post("/api/combos")
def api_criar_combo():
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
        cur = conn.execute("""
            INSERT INTO financeiro_combos (
                nome, descricao, sessoes, preco, ativo, criado_em, atualizado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (nome, descricao, sessoes, preco, ativo, _now_iso(), _now_iso()))
        conn.commit()

        row = conn.execute("SELECT * FROM financeiro_combos WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _ok(item=_dict_row(row), mensagem="Combo cadastrado com sucesso.")
    except Exception as e:
        return _fail(f"Erro ao cadastrar combo: {e}", 500)
    finally:
        conn.close()


@financeiro_bp.put("/api/combos/<int:combo_id>")
def api_editar_combo(combo_id: int):
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
        exists = conn.execute("SELECT id FROM financeiro_combos WHERE id = ?", (combo_id,)).fetchone()
        if not exists:
            return _fail("Combo não encontrado.", 404)

        conn.execute("""
            UPDATE financeiro_combos
            SET nome = ?, descricao = ?, sessoes = ?, preco = ?, ativo = ?, atualizado_em = ?
            WHERE id = ?
        """, (nome, descricao, sessoes, preco, ativo, _now_iso(), combo_id))
        conn.commit()

        row = conn.execute("SELECT * FROM financeiro_combos WHERE id = ?", (combo_id,)).fetchone()
        return _ok(item=_dict_row(row), mensagem="Combo atualizado com sucesso.")
    except Exception as e:
        return _fail(f"Erro ao atualizar combo: {e}", 500)
    finally:
        conn.close()


@financeiro_bp.delete("/api/combos/<int:combo_id>")
def api_excluir_combo(combo_id: int):
    conn = _conn()
    try:
        uso = conn.execute("""
            SELECT COUNT(*) AS total
            FROM financeiro_paciente_planos
            WHERE combo_id = ?
        """, (combo_id,)).fetchone()

        if uso and int(uso["total"]) > 0:
            return _fail("Este combo já está vinculado a paciente(s). Edite ou inative em vez de excluir.", 409)

        conn.execute("DELETE FROM financeiro_combos WHERE id = ?", (combo_id,))
        conn.commit()
        return _ok(mensagem="Combo excluído com sucesso.")
    except Exception as e:
        return _fail(f"Erro ao excluir combo: {e}", 500)
    finally:
        conn.close()


# ============================================================
# PACIENTE x PLANOS / COMBOS
# ============================================================

@financeiro_bp.get("/api/pacientes-planos")
def api_listar_pacientes_planos():
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
            sql += """
                AND (
                    COALESCE(pp.paciente_nome, '') LIKE ?
                    OR COALESCE(pp.combo_nome, '') LIKE ?
                    OR COALESCE(pp.nome_plano, '') LIKE ?
                    OR REPLACE(REPLACE(REPLACE(COALESCE(pp.paciente_cpf, ''), '.', ''), '-', ''), ' ', '') LIKE ?
                    OR REPLACE(REPLACE(REPLACE(COALESCE(pp.paciente_cns, ''), '.', ''), '-', ''), ' ', '') LIKE ?
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

        rows = conn.execute(sql, params).fetchall()

        items: list[dict[str, Any]] = []
        for row in rows:
            item = _enriquecer_plano_item(conn, dict(row))

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
    conn = _conn()
    try:
        row = conn.execute("""
            SELECT pp.*
            FROM financeiro_paciente_planos pp
            WHERE pp.id = ?
            LIMIT 1
        """, (plano_id,)).fetchone()

        if not row:
            return _fail("Registro não encontrado.", 404)

        item = _enriquecer_plano_item(conn, dict(row))

        lancs = conn.execute("""
            SELECT *
            FROM financeiro_lancamentos
            WHERE plano_id = ?
            ORDER BY parcela_numero ASC, vencimento ASC, id ASC
        """, (plano_id,)).fetchall()

        return _ok(item=item, lancamentos=_rows_to_dict(lancs))
    except Exception as e:
        return _fail(f"Erro ao obter registro: {e}", 500)
    finally:
        conn.close()


@financeiro_bp.post("/api/pacientes-planos")
def api_criar_paciente_plano():
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
        paciente = _buscar_paciente_por_id(conn, paciente_id)
        if not paciente:
            return _fail("Paciente não encontrado.", 404)

        existente = _vinculo_ativo_existente(conn, paciente_id)
        if existente:
            return _fail(
                "Este paciente já possui vínculo ativo no comercial. Edite o registro existente em vez de cadastrar outro.",
                409,
                registro_existente=_dict_row(existente),
            )

        paciente_nome = (paciente["nome"] or "").strip()
        paciente_cpf = (paciente["cpf"] or "").strip()
        paciente_cns = (paciente["cns"] or "").strip()

        combo_nome = None

        if tipo == "combo":
            if not combo_id:
                return _fail("Informe o combo a ser vinculado.")

            combo = conn.execute("""
                SELECT * FROM financeiro_combos WHERE id = ? LIMIT 1
            """, (combo_id,)).fetchone()

            if not combo:
                return _fail("Combo não encontrado.", 404)

            combo_nome = combo["nome"]

            if sessoes_contratadas <= 0:
                sessoes_contratadas = _to_int(combo["sessoes"], 0)
            if valor_total <= 0:
                valor_total = _to_float(combo["preco"], 0)

        if tipo == "plano" and not nome_plano:
            nome_plano = "Plano do paciente"

        cur = conn.execute("""
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

        row = conn.execute("""
            SELECT pp.*
            FROM financeiro_paciente_planos pp
            WHERE pp.id = ?
        """, (plano_id,)).fetchone()

        item = _enriquecer_plano_item(conn, dict(row))

        lancs = conn.execute("""
            SELECT *
            FROM financeiro_lancamentos
            WHERE plano_id = ?
            ORDER BY parcela_numero ASC, vencimento ASC, id ASC
        """, (plano_id,)).fetchall()

        return _ok(
            item=item,
            lancamentos=_rows_to_dict(lancs),
            mensagem="Plano/combo vinculado ao paciente com sucesso."
        )
    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao vincular plano/combo: {e}", 500)
    finally:
        conn.close()


@financeiro_bp.put("/api/pacientes-planos/<int:plano_id>")
def api_editar_paciente_plano(plano_id: int):
    data = request.get_json(silent=True) or request.form

    conn = _conn()
    try:
        antigo = conn.execute("""
            SELECT * FROM financeiro_paciente_planos WHERE id = ? LIMIT 1
        """, (plano_id,)).fetchone()

        if not antigo:
            return _fail("Registro não encontrado.", 404)

        tipo = (data.get("tipo") or antigo["tipo"] or "").strip().lower()
        combo_id = _to_int(data.get("combo_id"), antigo["combo_id"] or 0) or None
        nome_plano = (data.get("nome_plano") or antigo["nome_plano"] or "").strip()
        descricao = (data.get("descricao") or antigo["descricao"] or "").strip()

        sessoes_contratadas = _to_int(data.get("sessoes_contratadas"), antigo["sessoes_contratadas"] or 0)
        valor_total = _to_float(data.get("valor_total"), antigo["valor_total"] or 0)

        recorrente = _to_bool(data.get("recorrente", antigo["recorrente"]))
        renovacao_automatica = _to_bool(data.get("renovacao_automatica", antigo["renovacao_automatica"]))
        frequencia = (data.get("frequencia") or antigo["frequencia"] or "").strip()
        forma_pagamento = (data.get("forma_pagamento") or antigo["forma_pagamento"] or "").strip()
        data_inicio = (data.get("data_inicio") or antigo["data_inicio"] or "").strip()
        data_fim = (data.get("data_fim") or antigo["data_fim"] or "").strip()
        status = (data.get("status") or antigo["status"] or "ativo").strip()
        observacoes = (data.get("observacoes") or antigo["observacoes"] or "").strip()

        combo_nome = antigo["combo_nome"]

        if tipo not in ("combo", "plano"):
            return _fail("Tipo inválido.")

        existente = _vinculo_ativo_existente(conn, _to_int(antigo["paciente_id"]), ignore_id=plano_id)
        if status == "ativo" and existente:
            return _fail(
                "Este paciente já possui outro vínculo ativo no comercial. Encerre o anterior antes de ativar outro.",
                409,
                registro_existente=_dict_row(existente),
            )

        if tipo == "combo":
            if not combo_id:
                return _fail("Informe o combo.")
            combo = conn.execute("""
                SELECT * FROM financeiro_combos WHERE id = ? LIMIT 1
            """, (combo_id,)).fetchone()
            if not combo:
                return _fail("Combo não encontrado.", 404)
            combo_nome = combo["nome"]

        if tipo == "plano" and not nome_plano:
            nome_plano = "Plano do paciente"

        conn.execute("""
            UPDATE financeiro_paciente_planos
            SET
                tipo = ?,
                combo_id = ?,
                combo_nome = ?,
                nome_plano = ?,
                descricao = ?,
                sessoes_contratadas = ?,
                valor_total = ?,
                recorrente = ?,
                renovacao_automatica = ?,
                frequencia = ?,
                forma_pagamento = ?,
                observacoes = ?,
                data_inicio = ?,
                data_fim = ?,
                status = ?,
                atualizado_em = ?
            WHERE id = ?
        """, (
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
            plano_id
        ))

        _recalcular_saldo_sessoes(conn, plano_id)

        paciente_nome = antigo["paciente_nome"]
        nome_ref = _safe_label_nome_plano(tipo, combo_nome, nome_plano)
        descricao_base = f"{'Combo' if tipo == 'combo' else 'Plano'} · {nome_ref} · {paciente_nome}"

        conn.execute("""
            UPDATE financeiro_lancamentos
            SET
                descricao = CASE
                    WHEN referencia_tipo = 'parcela' AND COALESCE(parcelas_total, 1) > 1
                    THEN ? || ' · Parcela ' || COALESCE(parcela_numero, 1) || '/' || COALESCE(parcelas_total, 1)
                    ELSE ?
                END,
                forma_pagamento = COALESCE(NULLIF(?, ''), forma_pagamento),
                atualizado_em = ?
            WHERE plano_id = ?
              AND status IN ('pendente', 'parcial')
        """, (
            descricao_base,
            descricao_base,
            forma_pagamento,
            _now_iso(),
            plano_id
        ))

        conn.commit()

        row = conn.execute("""
            SELECT pp.*
            FROM financeiro_paciente_planos pp
            WHERE pp.id = ?
            LIMIT 1
        """, (plano_id,)).fetchone()

        item = _enriquecer_plano_item(conn, dict(row))
        return _ok(item=item, mensagem="Registro atualizado com sucesso.")
    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao atualizar registro: {e}", 500)
    finally:
        conn.close()


@financeiro_bp.post("/api/pacientes-planos/<int:plano_id>/desvincular-atendimentos")
def api_desvincular_atendimentos(plano_id: int):
    conn = _conn()
    try:
        exists = conn.execute("""
            SELECT id FROM financeiro_paciente_planos WHERE id = ?
        """, (plano_id,)).fetchone()

        if not exists:
            return _fail("Registro não encontrado.", 404)

        if not _table_exists(conn, "atendimentos"):
            return _fail("Tabela de atendimentos não encontrada no banco.", 404)

        conn.execute("""
            UPDATE atendimentos
            SET combo_plano_id = NULL,
                contabiliza_sessao = 0
            WHERE combo_plano_id = ?
        """, (plano_id,))

        _recalcular_saldo_sessoes(conn, plano_id)
        conn.commit()

        row = conn.execute("""
            SELECT *
            FROM financeiro_paciente_planos
            WHERE id = ?
        """, (plano_id,)).fetchone()

        item = _enriquecer_plano_item(conn, dict(row))
        return _ok(item=item, mensagem="Atendimentos desvinculados com sucesso.")
    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao desvincular atendimentos: {e}", 500)
    finally:
        conn.close()


@financeiro_bp.delete("/api/pacientes-planos/<int:plano_id>")
def api_excluir_paciente_plano(plano_id: int):
    conn = _conn()
    try:
        exists = conn.execute("SELECT id FROM financeiro_paciente_planos WHERE id = ?", (plano_id,)).fetchone()
        if not exists:
            return _fail("Registro não encontrado.", 404)

        if _table_exists(conn, "atendimentos"):
            vinculados = conn.execute("""
                SELECT COUNT(*) AS total
                FROM atendimentos
                WHERE combo_plano_id = ?
            """, (plano_id,)).fetchone()

            if vinculados and _to_int(vinculados["total"], 0) > 0:
                return _fail(
                    "Este combo/plano possui atendimentos vinculados. Desvincule os atendimentos antes de excluir.",
                    409
                )

        conn.execute("DELETE FROM financeiro_lancamentos WHERE plano_id = ?", (plano_id,))
        conn.execute("DELETE FROM financeiro_paciente_planos WHERE id = ?", (plano_id,))
        conn.commit()

        return _ok(mensagem="Plano/combo removido com sucesso.")
    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao excluir registro: {e}", 500)
    finally:
        conn.close()


# ============================================================
# VÍNCULO COM ATENDIMENTOS
# ============================================================

@financeiro_bp.post("/api/pacientes-planos/<int:plano_id>/vincular-atendimentos")
def api_vincular_atendimentos(plano_id: int):
    data = request.get_json(silent=True) or request.form
    somente_sem_vinculo = _to_bool(data.get("somente_sem_vinculo", 1))

    conn = _conn()
    try:
        plano = conn.execute("""
            SELECT *
            FROM financeiro_paciente_planos
            WHERE id = ?
            LIMIT 1
        """, (plano_id,)).fetchone()

        if not plano:
            return _fail("Registro não encontrado.", 404)

        if not _table_exists(conn, "atendimentos"):
            return _fail("Tabela de atendimentos não encontrada no banco.", 404)

        paciente_id = _to_int(plano["paciente_id"], 0)
        paciente_nome = (plano["paciente_nome"] or "").strip()

        if paciente_id <= 0 and not paciente_nome:
            return _fail("Registro sem paciente válido para vincular.", 400)

        sql = """
            UPDATE atendimentos
            SET combo_plano_id = ?,
                contabiliza_sessao = 1
            WHERE (
                paciente_id = ?
                OR TRIM(LOWER(COALESCE(nome, ''))) = TRIM(LOWER(?))
            )
        """
        params: list[Any] = [plano_id, paciente_id, paciente_nome]

        if somente_sem_vinculo:
            sql += " AND combo_plano_id IS NULL"

        cur = conn.execute(sql, params)

        _recalcular_saldo_sessoes(conn, plano_id)
        conn.commit()

        row = conn.execute("""
            SELECT *
            FROM financeiro_paciente_planos
            WHERE id = ?
        """, (plano_id,)).fetchone()

        item = _enriquecer_plano_item(conn, dict(row))
        return _ok(
            item=item,
            vinculados=cur.rowcount,
            mensagem="Atendimentos vinculados ao combo/plano com sucesso."
        )
    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao vincular atendimentos: {e}", 500)
    finally:
        conn.close()


# ============================================================
# LIVRO CAIXA / LANÇAMENTOS
# ============================================================

@financeiro_bp.get("/api/lancamentos")
def api_listar_lancamentos():
    q = (request.args.get("q") or "").strip()
    tipo = (request.args.get("tipo") or "").strip()
    status = (request.args.get("status") or "").strip()
    categoria = (request.args.get("categoria") or "").strip()
    data_ini = (request.args.get("data_ini") or "").strip()
    data_fim = (request.args.get("data_fim") or "").strip()
    competencia = (request.args.get("competencia") or "").strip()

    conn = _conn()
    try:
        sql = """
            SELECT *
            FROM financeiro_lancamentos
            WHERE 1=1
        """
        params: list[Any] = []

        if q:
            sql += " AND (descricao LIKE ? OR COALESCE(observacoes, '') LIKE ?)"
            params.extend([f"%{q}%", f"%{q}%"])

        if tipo:
            sql += " AND tipo = ?"
            params.append(tipo)

        if status:
            sql += " AND status = ?"
            params.append(status)

        if categoria:
            sql += " AND categoria = ?"
            params.append(categoria)

        if competencia:
            sql += " AND competencia = ?"
            params.append(competencia)

        if data_ini:
            sql += " AND COALESCE(data_pagamento, vencimento, criado_em) >= ?"
            params.append(data_ini)

        if data_fim:
            sql += " AND COALESCE(data_pagamento, vencimento, criado_em) <= ?"
            params.append(data_fim)

        sql += " ORDER BY COALESCE(data_pagamento, vencimento, criado_em) DESC, id DESC"

        rows = conn.execute(sql, params).fetchall()
        return _ok(items=_rows_to_dict(rows))
    except Exception as e:
        return _fail(f"Erro ao listar lançamentos: {e}", 500)
    finally:
        conn.close()


@financeiro_bp.post("/api/lancamentos")
def api_criar_lancamento():
    data = request.get_json(silent=True) or request.form

    tipo = (data.get("tipo") or "").strip()
    categoria = (data.get("categoria") or "").strip()
    descricao = (data.get("descricao") or "").strip()
    valor = _to_float(data.get("valor"), 0)
    status = (data.get("status") or "pago").strip()
    forma_pagamento = (data.get("forma_pagamento") or "").strip()
    vencimento = (data.get("vencimento") or _today_iso()).strip()
    data_pagamento = (data.get("data_pagamento") or "").strip()
    observacoes = (data.get("observacoes") or "").strip()
    competencia = (data.get("competencia") or _competencia_from_date(vencimento)).strip()
    paciente_id = _to_int(data.get("paciente_id"), 0) or None

    if tipo not in ("entrada", "saida"):
        return _fail("Tipo inválido. Use 'entrada' ou 'saida'.")
    if not descricao:
        return _fail("Informe a descrição do lançamento.")
    if valor <= 0:
        return _fail("Informe um valor maior que zero.")

    conn = _conn()
    try:
        cur = conn.execute("""
            INSERT INTO financeiro_lancamentos (
                paciente_id, plano_id,
                origem, referencia_tipo, referencia_id,
                tipo, categoria, descricao, valor,
                status, forma_pagamento,
                vencimento, data_pagamento, competencia,
                observacoes, criado_em, atualizado_em
            ) VALUES (?, NULL, 'manual', ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            paciente_id,
            categoria or "manual",
            tipo,
            categoria,
            descricao,
            valor,
            status,
            forma_pagamento,
            vencimento,
            data_pagamento or None,
            competencia,
            observacoes,
            _now_iso(),
            _now_iso()
        ))
        conn.commit()

        row = conn.execute("SELECT * FROM financeiro_lancamentos WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _ok(item=_dict_row(row), mensagem="Lançamento cadastrado com sucesso.")
    except Exception as e:
        return _fail(f"Erro ao cadastrar lançamento: {e}", 500)
    finally:
        conn.close()


@financeiro_bp.put("/api/lancamentos/<int:lanc_id>")
def api_editar_lancamento(lanc_id: int):
    data = request.get_json(silent=True) or request.form

    conn = _conn()
    try:
        antigo = conn.execute("SELECT * FROM financeiro_lancamentos WHERE id = ?", (lanc_id,)).fetchone()
        if not antigo:
            return _fail("Lançamento não encontrado.", 404)

        tipo = (data.get("tipo") or antigo["tipo"] or "").strip()
        categoria = (data.get("categoria") or antigo["categoria"] or "").strip()
        descricao = (data.get("descricao") or antigo["descricao"] or "").strip()
        valor = _to_float(data.get("valor"), antigo["valor"] or 0)
        status = (data.get("status") or antigo["status"] or "pendente").strip()
        forma_pagamento = (data.get("forma_pagamento") or antigo["forma_pagamento"] or "").strip()
        vencimento = (data.get("vencimento") or antigo["vencimento"] or "").strip()
        data_pagamento = (data.get("data_pagamento") or antigo["data_pagamento"] or "").strip()
        observacoes = (data.get("observacoes") or antigo["observacoes"] or "").strip()
        competencia = (data.get("competencia") or antigo["competencia"] or _competencia_from_date(vencimento)).strip()

        if tipo not in ("entrada", "saida"):
            return _fail("Tipo inválido.")
        if not descricao:
            return _fail("Informe a descrição.")
        if valor <= 0:
            return _fail("Informe um valor válido.")

        conn.execute("""
            UPDATE financeiro_lancamentos
            SET
                tipo = ?,
                categoria = ?,
                descricao = ?,
                valor = ?,
                status = ?,
                forma_pagamento = ?,
                vencimento = ?,
                data_pagamento = ?,
                competencia = ?,
                observacoes = ?,
                atualizado_em = ?
            WHERE id = ?
        """, (
            tipo,
            categoria,
            descricao,
            valor,
            status,
            forma_pagamento,
            vencimento,
            data_pagamento or None,
            competencia,
            observacoes,
            _now_iso(),
            lanc_id
        ))
        conn.commit()

        row = conn.execute("SELECT * FROM financeiro_lancamentos WHERE id = ?", (lanc_id,)).fetchone()
        return _ok(item=_dict_row(row), mensagem="Lançamento atualizado com sucesso.")
    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao atualizar lançamento: {e}", 500)
    finally:
        conn.close()


@financeiro_bp.delete("/api/lancamentos/<int:lanc_id>")
def api_excluir_lancamento(lanc_id: int):
    conn = _conn()
    try:
        exists = conn.execute("SELECT id FROM financeiro_lancamentos WHERE id = ?", (lanc_id,)).fetchone()
        if not exists:
            return _fail("Lançamento não encontrado.", 404)

        conn.execute("DELETE FROM financeiro_lancamentos WHERE id = ?", (lanc_id,))
        conn.commit()
        return _ok(mensagem="Lançamento removido com sucesso.")
    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao excluir lançamento: {e}", 500)
    finally:
        conn.close()


# ============================================================
# BAIXA DE PAGAMENTO
# ============================================================

@financeiro_bp.post("/api/lancamentos/<int:lanc_id>/baixar")
def api_baixar_lancamento(lanc_id: int):
    data = request.get_json(silent=True) or request.form

    data_pagamento = (data.get("data_pagamento") or _today_iso()).strip()
    forma_pagamento = (data.get("forma_pagamento") or "").strip()
    valor_pago = data.get("valor_pago")

    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM financeiro_lancamentos WHERE id = ?", (lanc_id,)).fetchone()
        if not row:
            return _fail("Lançamento não encontrado.", 404)

        valor_original = _to_float(row["valor"], 0)
        valor_pago_num = _to_float(valor_pago, valor_original)
        status = "pago" if valor_pago_num >= valor_original else "parcial"

        conn.execute("""
            UPDATE financeiro_lancamentos
            SET
                status = ?,
                data_pagamento = ?,
                forma_pagamento = COALESCE(NULLIF(?, ''), forma_pagamento),
                atualizado_em = ?
            WHERE id = ?
        """, (status, data_pagamento, forma_pagamento, _now_iso(), lanc_id))
        conn.commit()

        novo = conn.execute("SELECT * FROM financeiro_lancamentos WHERE id = ?", (lanc_id,)).fetchone()
        return _ok(item=_dict_row(novo), mensagem="Lançamento baixado com sucesso.")
    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao baixar lançamento: {e}", 500)
    finally:
        conn.close()


# ============================================================
# CONSUMO / ESTORNO MANUAL DE SESSÕES
# ============================================================

@financeiro_bp.post("/api/pacientes-planos/<int:plano_id>/consumir-sessao")
def api_consumir_sessao(plano_id: int):
    data = request.get_json(silent=True) or request.form
    qtd = max(1, _to_int(data.get("qtd"), 1))

    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM financeiro_paciente_planos WHERE id = ?", (plano_id,)).fetchone()
        if not row:
            return _fail("Plano não encontrado.", 404)

        usadas = _contar_atendimentos_vinculados(conn, plano_id)
        contratadas = _to_int(row["sessoes_contratadas"], 0)

        novas_usadas = usadas + qtd
        if contratadas > 0 and novas_usadas > contratadas:
            return _fail("Não há sessões suficientes restantes para este consumo.", 409)

        conn.execute("""
            UPDATE financeiro_paciente_planos
            SET sessoes_usadas = ?, atualizado_em = ?
            WHERE id = ?
        """, (novas_usadas, _now_iso(), plano_id))

        if contratadas > 0 and novas_usadas >= contratadas:
            conn.execute("""
                UPDATE financeiro_paciente_planos
                SET status = 'encerrado', atualizado_em = ?
                WHERE id = ?
            """, (_now_iso(), plano_id))

        conn.commit()

        atualizado = conn.execute("""
            SELECT *
            FROM financeiro_paciente_planos
            WHERE id = ?
        """, (plano_id,)).fetchone()

        item = _enriquecer_plano_item(conn, dict(atualizado))
        return _ok(item=item, mensagem="Sessão consumida com sucesso.")
    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao consumir sessão: {e}", 500)
    finally:
        conn.close()


@financeiro_bp.post("/api/pacientes-planos/<int:plano_id>/estornar-sessao")
def api_estornar_sessao(plano_id: int):
    data = request.get_json(silent=True) or request.form
    qtd = max(1, _to_int(data.get("qtd"), 1))

    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM financeiro_paciente_planos WHERE id = ?", (plano_id,)).fetchone()
        if not row:
            return _fail("Plano não encontrado.", 404)

        usadas = max(0, _to_int(row["sessoes_usadas"], 0) - qtd)
        status = row["status"]

        if status == "encerrado":
            status = "ativo"

        conn.execute("""
            UPDATE financeiro_paciente_planos
            SET sessoes_usadas = ?, status = ?, atualizado_em = ?
            WHERE id = ?
        """, (usadas, status, _now_iso(), plano_id))
        conn.commit()

        atualizado = conn.execute("""
            SELECT *
            FROM financeiro_paciente_planos
            WHERE id = ?
        """, (plano_id,)).fetchone()

        item = _enriquecer_plano_item(conn, dict(atualizado))
        return _ok(item=item, mensagem="Sessão estornada com sucesso.")
    except Exception as e:
        conn.rollback()
        return _fail(f"Erro ao estornar sessão: {e}", 500)
    finally:
        conn.close()


# ============================================================
# RESUMO / DASHBOARD
# ============================================================

@financeiro_bp.get("/api/resumo")
def api_resumo_financeiro():
    data_ini = (request.args.get("data_ini") or "").strip()
    data_fim = (request.args.get("data_fim") or "").strip()
    competencia = (request.args.get("competencia") or "").strip()

    conn = _conn()
    try:
        where = ["1=1"]
        params: list[Any] = []

        if competencia:
            where.append("competencia = ?")
            params.append(competencia)

        if data_ini:
            where.append("COALESCE(data_pagamento, vencimento, criado_em) >= ?")
            params.append(data_ini)

        if data_fim:
            where.append("COALESCE(data_pagamento, vencimento, criado_em) <= ?")
            params.append(data_fim)

        where_sql = " AND ".join(where)

        resumo = conn.execute(f"""
            SELECT
                SUM(CASE WHEN tipo = 'entrada' AND status = 'pago' THEN valor ELSE 0 END) AS entradas_pagas,
                SUM(CASE WHEN tipo = 'saida'   AND status = 'pago' THEN valor ELSE 0 END) AS saidas_pagas,
                SUM(CASE WHEN tipo = 'entrada' AND status IN ('pendente', 'parcial') THEN valor ELSE 0 END) AS entradas_pendentes,
                SUM(CASE WHEN tipo = 'saida'   AND status IN ('pendente', 'parcial') THEN valor ELSE 0 END) AS saidas_pendentes,
                SUM(CASE WHEN tipo = 'entrada' THEN valor ELSE 0 END) AS entradas_total,
                SUM(CASE WHEN tipo = 'saida'   THEN valor ELSE 0 END) AS saidas_total
            FROM financeiro_lancamentos
            WHERE {where_sql}
        """, params).fetchone()

        combos_ativos = conn.execute("""
            SELECT COUNT(*) AS total
            FROM financeiro_paciente_planos
            WHERE tipo = 'combo' AND status = 'ativo'
        """).fetchone()

        planos_ativos = conn.execute("""
            SELECT COUNT(*) AS total
            FROM financeiro_paciente_planos
            WHERE tipo = 'plano' AND status = 'ativo'
        """).fetchone()

        saldo_pago = _to_float(resumo["entradas_pagas"], 0) - _to_float(resumo["saidas_pagas"], 0)
        saldo_projetado = _to_float(resumo["entradas_total"], 0) - _to_float(resumo["saidas_total"], 0)

        return _ok(
            resumo={
                "entradas_pagas": _to_float(resumo["entradas_pagas"], 0),
                "saidas_pagas": _to_float(resumo["saidas_pagas"], 0),
                "entradas_pendentes": _to_float(resumo["entradas_pendentes"], 0),
                "saidas_pendentes": _to_float(resumo["saidas_pendentes"], 0),
                "entradas_total": _to_float(resumo["entradas_total"], 0),
                "saidas_total": _to_float(resumo["saidas_total"], 0),
                "saldo_pago": saldo_pago,
                "saldo_projetado": saldo_projetado,
                "combos_ativos": _to_int(combos_ativos["total"], 0),
                "planos_ativos": _to_int(planos_ativos["total"], 0),
            }
        )
    except Exception as e:
        return _fail(f"Erro ao montar resumo financeiro: {e}", 500)
    finally:
        conn.close()


@financeiro_bp.get("/api/fechamento")
def api_fechamento_financeiro():
    data_ini = (request.args.get("data_ini") or "").strip()
    data_fim = (request.args.get("data_fim") or "").strip()
    competencia = (request.args.get("competencia") or "").strip()

    conn = _conn()
    try:
        where = ["1=1"]
        params: list[Any] = []

        if competencia:
            where.append("competencia = ?")
            params.append(competencia)

        if data_ini:
            where.append("COALESCE(data_pagamento, vencimento, criado_em) >= ?")
            params.append(data_ini)

        if data_fim:
            where.append("COALESCE(data_pagamento, vencimento, criado_em) <= ?")
            params.append(data_fim)

        where_sql = " AND ".join(where)

        por_categoria = conn.execute(f"""
            SELECT
                COALESCE(categoria, 'sem_categoria') AS categoria,
                tipo,
                status,
                COUNT(*) AS qtd,
                SUM(valor) AS total
            FROM financeiro_lancamentos
            WHERE {where_sql}
            GROUP BY COALESCE(categoria, 'sem_categoria'), tipo, status
            ORDER BY categoria, tipo, status
        """, params).fetchall()

        por_dia = conn.execute(f"""
            SELECT
                SUBSTR(COALESCE(data_pagamento, vencimento, criado_em), 1, 10) AS dia,
                SUM(CASE WHEN tipo = 'entrada' THEN valor ELSE 0 END) AS entradas,
                SUM(CASE WHEN tipo = 'saida' THEN valor ELSE 0 END) AS saidas
            FROM financeiro_lancamentos
            WHERE {where_sql}
            GROUP BY SUBSTR(COALESCE(data_pagamento, vencimento, criado_em), 1, 10)
            ORDER BY dia ASC
        """, params).fetchall()

        return _ok(
            por_categoria=_rows_to_dict(por_categoria),
            por_dia=_rows_to_dict(por_dia),
        )
    except Exception as e:
        return _fail(f"Erro ao gerar fechamento: {e}", 500)
    finally:
        conn.close()