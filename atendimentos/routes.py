from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime
from typing import Any

from flask import (
    request, redirect, url_for, flash, render_template, jsonify, session
)
from werkzeug.utils import secure_filename

from . import atendimentos_bp
from db import conectar_db


# ============================================================
# HELPERS DE INTROSPECÇÃO
# ============================================================

def has_table(conn: sqlite3.Connection, table_name: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table_name,),
    )
    return cur.fetchone() is not None


def has_column(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    if not has_table(conn, table_name):
        return False
    cur = conn.cursor()
    try:
        cur.execute(f"PRAGMA table_info({table_name})")
        cols = [r[1] for r in cur.fetchall()]  # (cid, name, type, notnull, dflt, pk)
        return column_name in cols
    except Exception:
        return False


def digits(s: str | None) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())


def _to_int(v, default=0):
    try:
        return int(v)
    except Exception:
        return default


# ============================================================
# HELPERS DE COMBO / COMERCIAL
# ============================================================

def _buscar_combo_ativo_paciente(conn, paciente_id: int | str | None) -> dict | None:
    if not paciente_id:
        return None
    if not has_table(conn, "financeiro_paciente_planos"):
        return None

    cur = conn.cursor()
    cur.execute("""
        SELECT
            pp.id,
            COALESCE(pp.tipo, '') AS tipo,
            COALESCE(pp.combo_nome, '') AS combo_nome,
            COALESCE(pp.nome_plano, '') AS nome_plano,
            COALESCE(pp.sessoes_contratadas, 0) AS sessoes_contratadas,
            COALESCE(pp.status, 'ativo') AS status
        FROM financeiro_paciente_planos pp
        WHERE pp.paciente_id = ?
          AND COALESCE(pp.status, 'ativo') = 'ativo'
        ORDER BY pp.id DESC
        LIMIT 1
    """, (paciente_id,))
    row = cur.fetchone()
    if not row:
        return None

    plano_id = _to_int(row[0], 0)

    usadas = 0
    if has_table(conn, "atendimentos") and has_column(conn, "atendimentos", "combo_plano_id"):
        cur.execute("""
            SELECT COUNT(*)
            FROM atendimentos
            WHERE combo_plano_id = ?
              AND COALESCE(contabiliza_sessao, 1) = 1
        """, (plano_id,))
        usadas = _to_int((cur.fetchone() or [0])[0], 0)

    contratadas = _to_int(row[4], 0)
    restantes = max(0, contratadas - usadas)

    return {
        "id": plano_id,
        "tipo": row[1] or "",
        "combo_nome": row[2] or "",
        "nome_plano": row[3] or "",
        "sessoes_contratadas": contratadas,
        "sessoes_usadas": usadas,
        "sessoes_restantes": restantes,
        "status": row[5] or "ativo",
    }


def _listar_combos_ativos_para_template(conn) -> list[dict]:
    if not has_table(conn, "financeiro_paciente_planos"):
        return []

    cur = conn.cursor()
    cur.execute("""
        SELECT
            pp.id,
            pp.paciente_id,
            COALESCE(pp.paciente_nome, '') AS paciente_nome,
            COALESCE(pp.tipo, '') AS tipo,
            COALESCE(pp.combo_nome, '') AS combo_nome,
            COALESCE(pp.nome_plano, '') AS nome_plano,
            COALESCE(pp.sessoes_contratadas, 0) AS sessoes_contratadas,
            COALESCE(pp.status, 'ativo') AS status
        FROM financeiro_paciente_planos pp
        WHERE COALESCE(pp.status, 'ativo') = 'ativo'
        ORDER BY COALESCE(pp.paciente_nome, '') ASC
    """)
    rows = cur.fetchall() or []

    items = []
    for row in rows:
        plano_id = _to_int(row[0], 0)
        paciente_id = _to_int(row[1], 0)

        usadas = 0
        if has_table(conn, "atendimentos") and has_column(conn, "atendimentos", "combo_plano_id"):
            cur.execute("""
                SELECT COUNT(*)
                FROM atendimentos
                WHERE combo_plano_id = ?
                  AND COALESCE(contabiliza_sessao, 1) = 1
            """, (plano_id,))
            usadas = _to_int((cur.fetchone() or [0])[0], 0)

        contratadas = _to_int(row[6], 0)
        restantes = max(0, contratadas - usadas)

        items.append({
            "id": plano_id,
            "paciente_id": paciente_id,
            "paciente_nome": row[2] or "",
            "tipo": row[3] or "",
            "combo_nome": row[4] or "",
            "nome_plano": row[5] or "",
            "sessoes_contratadas": contratadas,
            "sessoes_usadas": usadas,
            "sessoes_restantes": restantes,
            "status": row[7] or "ativo",
        })

    return items


def _recalcular_saldo_combo(conn, combo_plano_id: int | None):
    if not combo_plano_id:
        return
    if not has_table(conn, "financeiro_paciente_planos"):
        return

    cur = conn.cursor()
    cur.execute("""
        SELECT COALESCE(sessoes_contratadas, 0), COALESCE(status, 'ativo')
        FROM financeiro_paciente_planos
        WHERE id = ?
        LIMIT 1
    """, (combo_plano_id,))
    row = cur.fetchone()
    if not row:
        return

    contratadas = _to_int(row[0], 0)

    cur.execute("""
        SELECT COUNT(*)
        FROM atendimentos
        WHERE combo_plano_id = ?
          AND COALESCE(contabiliza_sessao, 1) = 1
    """, (combo_plano_id,))
    usadas = _to_int((cur.fetchone() or [0])[0], 0)

    restantes = max(0, contratadas - usadas)
    novo_status = "encerrado" if contratadas > 0 and restantes <= 0 else "ativo"

    try:
        cur.execute("""
            UPDATE financeiro_paciente_planos
            SET sessoes_usadas = ?,
                status = ?,
                atualizado_em = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (usadas, novo_status, combo_plano_id))
        conn.commit()
    except Exception:
        pass


# ============================================================
# LOGIN → resolve profissional
# ============================================================

def _resolve_logged_profissional_id(conn) -> int | None:
    """
    Descobre o ID do profissional pelo login.
    Prioriza:
      1) session['usuario_id'] / session['user_id'] / session['id']  (numérico)
      2) session['usuario_logado'] / 'login' / 'username'  → busca em usuarios.login/nome/email
    """
    for key in ("usuario_id", "user_id", "id"):
        val = session.get(key)
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                pass

    login_like = session.get("usuario_logado") or session.get("login") or session.get("username")
    if login_like and has_table(conn, "usuarios"):
        cur = conn.cursor()
        try:
            # tenta bater em login/nome/email se existirem
            parts = []
            if has_column(conn, "usuarios", "login"):
                parts.append("login")
            if has_column(conn, "usuarios", "nome"):
                parts.append("nome")
            if has_column(conn, "usuarios", "email"):
                parts.append("email")

            if parts:
                # usa COALESCE na ordem mais comum
                coalesce = ", ".join(parts + ["''"])
                cur.execute(
                    f"""
                    SELECT id
                      FROM usuarios
                     WHERE TRIM(LOWER(COALESCE({coalesce}))) = TRIM(LOWER(?))
                     LIMIT 1
                    """,
                    (login_like,),
                )
                row = cur.fetchone()
                if row:
                    return int(row[0])
        except Exception:
            pass

    return None


def _resolve_prof_dados(conn, profissional_id: int | None):
    """
    Retorna (id, nome, cns, cbo) do profissional, ou (None, '', '', '').
    Prioriza tabela 'usuarios'.
    """
    if not profissional_id:
        return None, "", "", ""

    pid = int(profissional_id)
    cur = conn.cursor()

    if has_table(conn, "usuarios"):
        try:
            sel = ["id"]
            sel.append("nome" if has_column(conn, "usuarios", "nome") else "'' AS nome")
            sel.append("cns"  if has_column(conn, "usuarios", "cns")  else "'' AS cns")
            sel.append("cbo"  if has_column(conn, "usuarios", "cbo")  else "'' AS cbo")

            sql = f"SELECT {', '.join(sel)} FROM usuarios WHERE id = ? LIMIT 1"
            cur.execute(sql, (pid,))
            r = cur.fetchone()
            if r:
                return (r[0], (r[1] or ""), (r[2] or ""), (r[3] or ""))
        except Exception:
            pass

    return pid, "", "", ""


def _resolve_prof_nome(conn, profissional_id: int) -> str:
    cur = conn.cursor()

    # tenta profissionais
    if has_table(conn, "profissionais"):
        try:
            cond = "AND (ativo = 1 OR ativo IS NULL)" if has_column(conn, "profissionais", "ativo") else ""
            cur.execute(
                f"SELECT nome FROM profissionais WHERE id = ? {cond} LIMIT 1",
                (profissional_id,),
            )
            r = cur.fetchone()
            if r and r[0]:
                return r[0]
        except Exception:
            pass

    # tenta usuarios
    if has_table(conn, "usuarios"):
        try:
            cond_role = "AND UPPER(role) = 'PROFISSIONAL'" if has_column(conn, "usuarios", "role") else ""
            cond_active = "AND (is_active = 1 OR is_active IS NULL)" if has_column(conn, "usuarios", "is_active") else ""
            cur.execute(
                f"""
                SELECT nome
                  FROM usuarios
                 WHERE id = ?
                   {cond_role}
                   {cond_active}
                 LIMIT 1
                """,
                (profissional_id,),
            )
            r = cur.fetchone()
            if r and r[0]:
                return r[0]
        except Exception:
            pass

    return "—"


def _resolve_prof_nome_by_id(conn, profissional_id: int | None) -> str:
    if not profissional_id:
        return "—"
    try:
        return _resolve_prof_nome(conn, int(profissional_id))
    except Exception:
        return "—"


# ============================================================
# PROCEDIMENTOS (DB) · CBO do login x CID do paciente
# ============================================================

def _first_existing(cols: set[str], opts: list[str]) -> str | None:
    for c in opts:
        if c in cols:
            return c
    return None


def _table_columns(conn, table: str) -> set[str]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return {r[1] for r in cur.fetchall()}


def _split_cids(raw: str | None) -> list[str]:
    if not raw:
        return []
    s = str(raw).upper()
    for ch in [";", "|", "\n", "\t"]:
        s = s.replace(ch, ",")
    parts = [p.strip() for p in s.split(",")]
    return [p for p in parts if p]


def _cid_norm_py(cid: str) -> str:
    # remove ponto e espaços, fica "F840" ou "G801"
    return "".join(ch for ch in (cid or "").upper().strip() if ch.isalnum())


def _get_paciente_cids(conn, paciente_id: str | int | None) -> list[str]:
    if not paciente_id or not has_table(conn, "pacientes") or not has_column(conn, "pacientes", "cid"):
        return []
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(cid,'') FROM pacientes WHERE id = ? LIMIT 1", (str(paciente_id),))
    r = cur.fetchone()
    return _split_cids(r[0] if r else "")


def _listar_procedimentos_compatíveis_db(conn, cbo: str, paciente_cids: list[str]) -> list[dict]:
    """
    Espera tabela 'procedimentos' com colunas:
      pa_cod, pa_descricao, pa_cid, pa_cbo, ativo
    """
    cbo = (cbo or "").strip()
    if not cbo:
        return []

    if not has_table(conn, "procedimentos"):
        return []

    pac_norms = [_cid_norm_py(x) for x in (paciente_cids or []) if x]
    cur = conn.cursor()

    proc_norm = "REPLACE(REPLACE(UPPER(COALESCE(pa_cid,'')),'.',''),' ','')"
    params: list[str] = [cbo]

    cid_ok_parts = ["TRIM(COALESCE(pa_cid,'')) = ''"]  # sem CID = ok
    if pac_norms:
        for pn in pac_norms:
            cid_ok_parts.append(f"({proc_norm} <> '' AND (? LIKE {proc_norm} || '%' OR {proc_norm} LIKE ? || '%'))")
            params.append(pn)
            params.append(pn)

    sql = f"""
        SELECT
            TRIM(COALESCE(pa_cod,''))        AS codigo,
            TRIM(COALESCE(pa_descricao,''))  AS descricao,
            TRIM(COALESCE(pa_cid,''))        AS cid_regra
        FROM procedimentos
        WHERE TRIM(COALESCE(pa_cbo,'')) = TRIM(?)
          AND COALESCE(ativo,1) = 1
          AND ({' OR '.join(cid_ok_parts)})
        ORDER BY descricao COLLATE NOCASE, codigo
        LIMIT 600
    """
    cur.execute(sql, params)
    rows = cur.fetchall()

    return [
        {"codigo": (r[0] or ""), "descricao": (r[1] or ""), "cid_regra": (r[2] or "")}
        for r in rows
        if (r[1] or "").strip()
    ]


@atendimentos_bp.get("/api/procedimentos_sugeridos")
def api_procedimentos_sugeridos():
    paciente_id = (request.args.get("paciente_id") or "").strip()
    if not paciente_id:
        return jsonify(ok=False, error="paciente_id é obrigatório."), 400

    with conectar_db() as conn:
        profissional_id = _resolve_logged_profissional_id(conn)
        if not profissional_id:
            return jsonify(ok=False, error="Profissional logado não identificado."), 401

        _, _, _, prof_cbo = _resolve_prof_dados(conn, profissional_id)
        pac_cids = _get_paciente_cids(conn, paciente_id)

        items = _listar_procedimentos_compatíveis_db(conn, (prof_cbo or "").strip(), pac_cids)
        return jsonify(ok=True, cbo=(prof_cbo or ""), paciente_cids=pac_cids, items=items)


# ============================================================
# SCHEMAS (ATENDIMENTOS + PROCEDIMENTOS)
# ============================================================

def ensure_atendimentos_schema(conn):
    """
    Garante tabela/colunas mínimas na 'atendimentos'.
    No Render (DB limpo), isso evita "no such table".
    """
    cur = conn.cursor()

    # cria tabela se não existir (mínimo compatível com o código)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS atendimentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER,
            data_atendimento TEXT,
            status TEXT,
            justificativa TEXT,
            evolucao TEXT,

            -- snapshot do paciente no momento
            nome TEXT,
            prontuario TEXT,
            mod TEXT,
            status_paciente TEXT
        )
    """)

    # colunas opcionais (idempotente)
    if not has_column(conn, "atendimentos", "anexo_atestado"):
        try: cur.execute("ALTER TABLE atendimentos ADD COLUMN anexo_atestado TEXT")
        except Exception: pass

    if not has_column(conn, "atendimentos", "profissional_id"):
        try: cur.execute("ALTER TABLE atendimentos ADD COLUMN profissional_id INTEGER")
        except Exception: pass

    if not has_column(conn, "atendimentos", "nome_profissional"):
        try: cur.execute("ALTER TABLE atendimentos ADD COLUMN nome_profissional TEXT")
        except Exception: pass

    if not has_column(conn, "atendimentos", "cns_profissional"):
        try: cur.execute("ALTER TABLE atendimentos ADD COLUMN cns_profissional TEXT")
        except Exception: pass

    if not has_column(conn, "atendimentos", "cbo_profissional"):
        try: cur.execute("ALTER TABLE atendimentos ADD COLUMN cbo_profissional TEXT")
        except Exception: pass

    # compat: teu código antes usava coluna status_paciente como "status"
    # mas já temos status (do atendimento). garantimos a coluna status_paciente.
    if not has_column(conn, "atendimentos", "status_paciente"):
        try: cur.execute("ALTER TABLE atendimentos ADD COLUMN status_paciente TEXT")
        except Exception: pass

    # NOVO: vínculo com combo/plano
    if not has_column(conn, "atendimentos", "combo_plano_id"):
        try: cur.execute("ALTER TABLE atendimentos ADD COLUMN combo_plano_id INTEGER")
        except Exception: pass

    if not has_column(conn, "atendimentos", "contabiliza_sessao"):
        try: cur.execute("ALTER TABLE atendimentos ADD COLUMN contabiliza_sessao INTEGER NOT NULL DEFAULT 0")
        except Exception: pass

    # índice útil
    try:
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_atends_paciente_data
                ON atendimentos (paciente_id, data_atendimento)
        """)
    except Exception:
        pass

    try:
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_atends_combo_plano
                ON atendimentos (combo_plano_id)
        """)
    except Exception:
        pass

    conn.commit()


def ensure_atendimento_procedimentos_schema(conn):
    """
    1 atendimento (pai) → N procedimentos (filhos)
    Garante também evolução de schema.
    """
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS atendimento_procedimentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            atendimento_id INTEGER NOT NULL,
            procedimento TEXT NOT NULL,
            codigo_sigtap TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (atendimento_id)
                REFERENCES atendimentos(id)
                ON DELETE CASCADE
        )
    """)

    # evolução de schema
    if not has_column(conn, "atendimento_procedimentos", "codigo_sigtap"):
        try:
            cur.execute("ALTER TABLE atendimento_procedimentos ADD COLUMN codigo_sigtap TEXT")
        except Exception:
            pass

    if not has_column(conn, "atendimento_procedimentos", "created_at"):
        try:
            cur.execute("ALTER TABLE atendimento_procedimentos ADD COLUMN created_at TEXT")
            cur.execute("""
                UPDATE atendimento_procedimentos
                   SET created_at = datetime('now')
                 WHERE COALESCE(created_at, '') = ''
            """)
        except Exception:
            pass

    try:
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_proc_atendimento
            ON atendimento_procedimentos (atendimento_id)
        """)
    except Exception:
        pass

    conn.commit()


# ============================================================
# FETCHERS BÁSICOS
# ============================================================

def fetch_pacientes(cur) -> list[dict]:
    # se não existe tabela no Render ainda, não quebra
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pacientes' LIMIT 1")
    if not cur.fetchone():
        return []

    # tenta selecionar colunas comuns com fallback
    cur.execute("PRAGMA table_info(pacientes)")
    cols = {r[1] for r in cur.fetchall()}

    # resolve nomes de colunas
    col_pront = "prontuario" if "prontuario" in cols else ("'' AS prontuario")
    col_mod   = "mod" if "mod" in cols else ("'' AS mod")
    col_stat  = "status" if "status" in cols else ("'' AS status")
    col_cpf   = "cpf" if "cpf" in cols else ("'' AS cpf")

    cur.execute(f"""
        SELECT id,
               COALESCE(nome,'') AS nome,
               COALESCE({col_cpf}, '') AS cpf,
               COALESCE({col_pront}, '') AS prontuario,
               COALESCE({col_mod}, '') AS mod,
               COALESCE({col_stat}, '') AS status
          FROM pacientes
         ORDER BY nome COLLATE NOCASE
    """)
    out = []
    for r in cur.fetchall():
        out.append({
            "id": r[0],
            "nome": r[1],
            "cpf": r[2],
            "prontuario": r[3],
            "mod": r[4],
            "status": r[5],
        })
    return out


# ============================================================
# PÁGINAS
# ============================================================

@atendimentos_bp.route("/", methods=["GET"])
def lista_atendimentos():
    """
    Tela da fila (recepção).
    """
    with conectar_db() as conn:
        cur = conn.cursor()
        pacientes = fetch_pacientes(cur)

        profissionais = []
        try:
            if has_table(conn, "usuarios"):
                nome_expr  = "COALESCE(nome, '')" if has_column(conn, "usuarios", "nome") else "''"
                login_expr = "COALESCE(login, '')" if has_column(conn, "usuarios", "login") else "''"
                email_expr = "COALESCE(email, '')" if has_column(conn, "usuarios", "email") else "''"

                conds = ["1=1"]
                if has_column(conn, "usuarios", "role"):
                    conds.append("UPPER(role) = 'PROFISSIONAL'")
                if has_column(conn, "usuarios", "is_active"):
                    conds.append("(is_active = 1 OR is_active IS NULL)")

                sql = f"""
                    SELECT
                        id,
                        TRIM(
                          CASE
                            WHEN {nome_expr} <> '' THEN {nome_expr}
                            WHEN {login_expr} <> '' THEN {login_expr}
                            ELSE {email_expr}
                          END
                        ) AS nome
                    FROM usuarios
                    WHERE {" AND ".join(conds)}
                    ORDER BY nome COLLATE NOCASE
                """
                cur.execute(sql)
                profissionais = [{"id": r[0], "nome": (r[1] or "").strip()} for r in cur.fetchall()]
        except Exception:
            profissionais = []

    return render_template(
        "lista_atendimentos.html",
        pacientes=pacientes,
        profissionais=profissionais,
        fila=[],
        data_hoje=date.today().isoformat(),
    )


@atendimentos_bp.route("/registrar", methods=["GET"])
def pagina_atendimento():
    """
    Tela de registrar atendimento.
    PROFISSIONAL NÃO É MAIS ESCOLHIDO: vem do usuário logado.
    """
    with conectar_db() as conn:
        cur = conn.cursor()
        pacientes = fetch_pacientes(cur)
        combos_ativos = _listar_combos_ativos_para_template(conn)

    return render_template(
        "atendimentos.html",
        pacientes=pacientes,
        profissionais=[],  # não precisa mais no template
        data_hoje=date.today().isoformat(),
        combos_ativos=combos_ativos,
    )


@atendimentos_bp.get("/api/paciente/<int:paciente_id>/combo")
def api_combo_paciente(paciente_id: int):
    with conectar_db() as conn:
        ensure_atendimentos_schema(conn)
        item = _buscar_combo_ativo_paciente(conn, paciente_id)
        return jsonify({"ok": True, "item": item})


# ============================================================
# SALVAR ATENDIMENTO (1 PAI + N FILHOS)
# ============================================================

def _normalize_procs_from_form():
    """
    Compatível com:
      - campos únicos: procedimento / codigoProcedimento
      - campos múltiplos: procedimento[] / codigoProcedimento[]
    Retorna (procedimentos:list[str], codigos:list[str])
    """
    procs = request.form.getlist("procedimento[]")
    cods  = request.form.getlist("codigoProcedimento[]")

    if not procs:
        p = (request.form.get("procedimento") or "").strip()
        c = (request.form.get("codigoProcedimento") or "").strip()
        if p:
            procs = [p]
            cods = [c] if c else [""]

    if len(cods) < len(procs):
        cods += [""] * (len(procs) - len(cods))

    procs = [str(x or "").strip() for x in procs if str(x or "").strip()]
    cods  = [str(x or "").strip() for x in cods][:len(procs)]
    return procs, cods


@atendimentos_bp.route("/salvar", methods=["POST"], endpoint="salvar_atendimento")
def salvar_atendimento_view():
    conn = conectar_db()
    cursor = conn.cursor()

    is_fetch = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    try:
        ensure_atendimentos_schema(conn)
        ensure_atendimento_procedimentos_schema(conn)
        _ensure_fila_table(conn)

        # ---------------------------------
        # PROFISSIONAL = LOGADO
        # ---------------------------------
        profissional_id = _resolve_logged_profissional_id(conn)
        if not profissional_id:
            msg = "Não foi possível identificar o profissional logado. Faça login novamente."
            if is_fetch:
                return jsonify({"ok": False, "error": msg}), 401
            flash(msg)
            return redirect(url_for("atendimentos.pagina_atendimento"))

        _, prof_nome, prof_cns, prof_cbo = _resolve_prof_dados(conn, profissional_id)

        # ---------------------------------
        # Inputs do form
        # ---------------------------------
        paciente_id      = (request.form.get("nomePaciente") or "").strip()
        data_atendimento = (request.form.get("dataAtendimento") or date.today().isoformat()).strip()
        status_atend     = (request.form.get("status_justificativa") or "Realizado").strip()
        justificativa    = (request.form.get("justificativa") or "").strip()
        evolucao         = (request.form.get("evolucao") or "").strip()

        fila_id_raw = (request.form.get("fila_id") or "").strip()
        fila_id = int(fila_id_raw) if fila_id_raw.isdigit() else None

        # NOVO: combo/plano
        combo_plano_id_raw = (request.form.get("combo_plano_id") or "").strip()
        combo_plano_id = int(combo_plano_id_raw) if combo_plano_id_raw.isdigit() else None

        contabiliza_sessao_raw = (request.form.get("contabiliza_sessao") or "").strip().lower()
        contabiliza_sessao = 1 if contabiliza_sessao_raw in ("1", "true", "on", "sim", "yes") else 0

        if not paciente_id:
            msg = "Paciente não informado."
            if is_fetch:
                return jsonify({"ok": False, "error": msg}), 400
            flash(msg)
            return redirect(url_for("atendimentos.pagina_atendimento"))

        procedimentos, codigos = _normalize_procs_from_form()
        if not procedimentos:
            msg = "Informe pelo menos 1 procedimento."
            if is_fetch:
                return jsonify({"ok": False, "error": msg}), 400
            flash(msg)
            return redirect(url_for("atendimentos.pagina_atendimento"))

        # ---------------------------------
        # Valida paciente
        # ---------------------------------
        cursor.execute("""
            SELECT nome, prontuario, mod, status
              FROM pacientes
             WHERE id = ?
             LIMIT 1
        """, (paciente_id,))
        paciente = cursor.fetchone()

        if not paciente:
            msg = "Paciente não encontrado."
            if is_fetch:
                return jsonify({"ok": False, "error": msg}), 404
            flash(msg)
            return redirect(url_for("atendimentos.pagina_atendimento"))

        nome, prontuario, mod, status_paciente = paciente

        # ---------------------------------
        # Validação combo/sessão
        # ---------------------------------
        if combo_plano_id:
            combo_info = _buscar_combo_ativo_paciente(conn, paciente_id)

            if not combo_info or int(combo_info["id"]) != int(combo_plano_id):
                msg = "Combo/plano inválido para este paciente."
                if is_fetch:
                    return jsonify({"ok": False, "error": msg}), 400
                flash(msg)
                return redirect(url_for("atendimentos.pagina_atendimento"))

            if contabiliza_sessao and _to_int(combo_info["sessoes_restantes"], 0) <= 0:
                msg = "Este combo/plano não possui sessões restantes."
                if is_fetch:
                    return jsonify({"ok": False, "error": msg}), 409
                flash(msg)
                return redirect(url_for("atendimentos.pagina_atendimento"))

            if contabiliza_sessao and has_column(conn, "atendimentos", "combo_plano_id"):
                cursor.execute("""
                    SELECT 1
                      FROM atendimentos
                     WHERE paciente_id = ?
                       AND data_atendimento = ?
                       AND combo_plano_id = ?
                       AND COALESCE(contabiliza_sessao, 1) = 1
                     LIMIT 1
                """, (paciente_id, data_atendimento, combo_plano_id))
                if cursor.fetchone():
                    msg = "Já existe atendimento deste combo contabilizado para este paciente nesta data."
                    if is_fetch:
                        return jsonify({"ok": False, "error": msg}), 409
                    flash(msg)
                    return redirect(url_for("atendimentos.pagina_atendimento"))

        # ---------------------------------
        # Validação CBO x CID
        # ---------------------------------
        pac_cids = _get_paciente_cids(conn, paciente_id)
        permitidos = _listar_procedimentos_compatíveis_db(conn, (prof_cbo or "").strip(), pac_cids)

        permitidos_cod = {(x.get("codigo") or "").strip() for x in permitidos if (x.get("codigo") or "").strip()}
        permitidos_desc = {(x.get("descricao") or "").strip().lower() for x in permitidos if (x.get("descricao") or "").strip()}

        invalidos = []
        for proc_txt, cod in zip(procedimentos, codigos):
            cod = (cod or "").strip()
            desc = (proc_txt or "").strip().lower()

            ok = False
            if cod and cod in permitidos_cod:
                ok = True
            elif desc and desc in permitidos_desc:
                ok = True

            if not ok:
                invalidos.append(proc_txt or cod or "—")

        if invalidos:
            cids_txt = ", ".join(pac_cids) if pac_cids else "—"
            msg = (
                "Procedimento(s) incompatível(is) com o CBO/CID do paciente: "
                + ", ".join(invalidos)
                + f" | CBO: {prof_cbo or '—'} | CID(s): {cids_txt}"
            )
            if is_fetch:
                return jsonify({"ok": False, "error": msg}), 400
            flash(msg)
            return redirect(url_for("atendimentos.pagina_atendimento"))

        # ---------------------------------
        # INSERT ATENDIMENTO
        # ---------------------------------
        cols = []
        vals = []

        def add_if_exists(col_name, value):
            if has_column(conn, "atendimentos", col_name):
                cols.append(col_name)
                vals.append(value)

        add_if_exists("paciente_id", paciente_id)
        add_if_exists("data_atendimento", data_atendimento)
        add_if_exists("status", status_atend)
        add_if_exists("justificativa", justificativa)
        add_if_exists("evolucao", evolucao)

        add_if_exists("nome", nome)
        add_if_exists("prontuario", prontuario)
        add_if_exists("mod", mod)
        add_if_exists("status_paciente", status_paciente)

        add_if_exists("profissional_id", profissional_id)
        add_if_exists("nome_profissional", prof_nome)
        add_if_exists("cns_profissional", prof_cns)
        add_if_exists("cbo_profissional", prof_cbo)

        # NOVO: grava combo/plano no atendimento
        add_if_exists("combo_plano_id", combo_plano_id)
        add_if_exists("contabiliza_sessao", 1 if combo_plano_id and contabiliza_sessao else 0)

        if not cols:
            raise RuntimeError("Nenhuma coluna válida encontrada para inserir em atendimentos.")

        sql = f"""
            INSERT INTO atendimentos ({", ".join(cols)})
            VALUES ({", ".join(["?"] * len(cols))})
        """
        cursor.execute(sql, vals)
        atendimento_id = cursor.lastrowid

        # ---------------------------------
        # INSERT PROCEDIMENTOS (FILHOS)
        # ---------------------------------
        now_iso = datetime.now().isoformat()

        has_cod_sigtap = has_column(conn, "atendimento_procedimentos", "codigo_sigtap")
        has_created_at = has_column(conn, "atendimento_procedimentos", "created_at")

        for proc, cod in zip(procedimentos, codigos):
            cols = ["atendimento_id", "procedimento"]
            vals = [atendimento_id, (proc or "").strip()]

            if has_cod_sigtap:
                cols.append("codigo_sigtap")
                vals.append((cod or "").strip() or None)

            if has_created_at:
                cols.append("created_at")
                vals.append(now_iso)

            sql_proc = f"""
                INSERT INTO atendimento_procedimentos ({", ".join(cols)})
                VALUES ({", ".join(["?"] * len(cols))})
            """
            cursor.execute(sql_proc, vals)

        # ---------------------------------
        # FINALIZA FILA
        # ---------------------------------
        if fila_id:
            cursor.execute("""
                UPDATE fila_atendimentos
                   SET status = 'finalizado',
                       obs = CASE
                               WHEN COALESCE(obs,'') = '' THEN 'ATENDIDO'
                               ELSE obs
                             END
                 WHERE id = ?
            """, (fila_id,))

        conn.commit()

        # NOVO: recalcula saldo do combo
        if combo_plano_id:
            _recalcular_saldo_combo(conn, combo_plano_id)

        if is_fetch:
            return jsonify({
                "ok": True,
                "message": "Atendimento salvo com sucesso.",
                "atendimento_id": atendimento_id,
                "redirect": url_for("atendimentos.lista_atendimentos"),
                "combo_plano_id": combo_plano_id,
                "contabiliza_sessao": 1 if combo_plano_id and contabiliza_sessao else 0,
            })

        flash("Atendimento salvo com sucesso.")
        return redirect(url_for("atendimentos.pagina_atendimento"))

    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass

        msg = f"Erro ao salvar atendimento: {e}"

        if is_fetch:
            return jsonify({"ok": False, "error": msg}), 500

        flash(msg)
        return redirect(url_for("atendimentos.pagina_atendimento"))

    finally:
        try:
            conn.close()
        except Exception:
            pass


# ============================================================
# APIs UTILITÁRIAS (PACIENTE + ÚLTIMO + JSON)
# ============================================================

@atendimentos_bp.route("/api/sugestoes_pacientes")
def sugestoes_pacientes():
    termo = (request.args.get("termo", "") or "").lower().strip()
    if len(termo) < 2:
        return jsonify([])

    with conectar_db() as conn:
        cur = conn.cursor()

        if not has_table(conn, "pacientes"):
            return jsonify([])

        cur.execute("PRAGMA table_info(pacientes)")
        cols = {r[1] for r in cur.fetchall()}

        col_pront = "prontuario" if "prontuario" in cols else "'' AS prontuario"
        col_stat  = "status" if "status" in cols else "'' AS status"
        col_mod   = "mod" if "mod" in cols else "'' AS mod"
        col_nasc  = "nascimento" if "nascimento" in cols else ("data_nascimento" if "data_nascimento" in cols else "'' AS nascimento")
        col_cid   = "cid" if "cid" in cols else "'' AS cid"

        cur.execute(
            f"""
            SELECT id,
                   COALESCE(nome,'') AS nome,
                   COALESCE({col_pront},'') AS prontuario,
                   COALESCE({col_stat},'') AS status,
                   COALESCE({col_mod},'') AS mod,
                   COALESCE({col_nasc},'') AS nascimento,
                   COALESCE({col_cid},'')  AS cid
              FROM pacientes
             WHERE LOWER(COALESCE(nome,'')) LIKE ?
             LIMIT 10
            """,
            (f"%{termo}%",),
        )
        rows = cur.fetchall()

    return jsonify([
        {
            "id": r[0],
            "nome": r[1],
            "prontuario": r[2],
            "status": r[3],
            "mod": r[4],
            "nascimento": r[5],
            "cid": r[6] or "-",
        }
        for r in rows
    ])


@atendimentos_bp.route("/api/paciente")
def api_paciente():
    pid = (request.args.get("id") or "").strip()
    if not pid:
        return jsonify({"ok": False, "error": "Parâmetro 'id' é obrigatório."}), 400

    with conectar_db() as conn:
        cur = conn.cursor()

        if not has_table(conn, "pacientes"):
            return jsonify({"ok": True, "found": False}), 404

        cur.execute("PRAGMA table_info(pacientes)")
        cols = {r[1] for r in cur.fetchall()}

        col_pront = "prontuario" if "prontuario" in cols else "'' AS prontuario"
        col_stat  = "status" if "status" in cols else "'' AS status"
        col_mod   = "mod" if "mod" in cols else "'' AS mod"
        col_nasc  = "nascimento" if "nascimento" in cols else ("data_nascimento" if "data_nascimento" in cols else "'' AS nascimento")
        col_cid   = "cid" if "cid" in cols else "'' AS cid"

        cur.execute(
            f"""
            SELECT id,
                   COALESCE(nome,'') AS nome,
                   COALESCE({col_pront},'') AS prontuario,
                   COALESCE({col_stat},'') AS status,
                   COALESCE({col_mod},'') AS mod,
                   COALESCE({col_nasc},'') AS nascimento,
                   COALESCE({col_cid},'')  AS cid
              FROM pacientes
             WHERE id = ?
             LIMIT 1
            """,
            (pid,),
        )
        row = cur.fetchone()

    if not row:
        return jsonify({"ok": True, "found": False}), 404

    return jsonify({
        "ok": True,
        "found": True,
        "id": row[0],
        "nome": row[1] or "",
        "prontuario": row[2] or "",
        "status": row[3] or "",
        "mod": row[4] or "",
        "nascimento": row[5] or "",
        "cid": (row[6] or "") or "-",
    })


@atendimentos_bp.route("/api/ultimo_atendimento")
def api_ultimo_atendimento():
    paciente_id = (request.args.get("id") or "").strip()
    if not paciente_id:
        return jsonify({
            "ok": False,
            "error": "Parâmetro 'id' (paciente) é obrigatório."
        }), 400

    with conectar_db() as conn:
        ensure_atendimentos_schema(conn)
        ensure_atendimento_procedimentos_schema(conn)
        cur = conn.cursor()

        if not has_table(conn, "atendimentos"):
            return jsonify({
                "ok": True,
                "found": False,
                "data": "-",
                "profissional": "-",
                "id": None
            })

        select_cols = ["id", "paciente_id", "data_atendimento"]

        if has_column(conn, "atendimentos", "nome_profissional"):
            select_cols.append("nome_profissional")
        else:
            select_cols.append("'' AS nome_profissional")

        if has_column(conn, "atendimentos", "status"):
            select_cols.append("status")
        else:
            select_cols.append("'' AS status")

        if has_column(conn, "atendimentos", "justificativa"):
            select_cols.append("justificativa")
        else:
            select_cols.append("'' AS justificativa")

        if has_column(conn, "atendimentos", "anexo_atestado"):
            select_cols.append("anexo_atestado")
        else:
            select_cols.append("'' AS anexo_atestado")

        if has_column(conn, "atendimentos", "evolucao"):
            select_cols.append("evolucao")
        else:
            select_cols.append("'' AS evolucao")

        if has_column(conn, "atendimentos", "combo_plano_id"):
            select_cols.append("COALESCE(combo_plano_id, NULL) AS combo_plano_id")
        else:
            select_cols.append("NULL AS combo_plano_id")

        sql = f"""
            SELECT {", ".join(select_cols)}
              FROM atendimentos
             WHERE paciente_id = ?
             ORDER BY
                 CASE
                   WHEN COALESCE(data_atendimento, '') GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
                     THEN data_atendimento
                   ELSE '0000-00-00'
                 END DESC,
                 id DESC
             LIMIT 1
        """
        cur.execute(sql, (paciente_id,))
        row = cur.fetchone()

        if not row:
            return jsonify({
                "ok": True,
                "found": False,
                "data": "-",
                "profissional": "-",
                "id": None
            })

        aid        = row[0]
        _pid       = row[1]
        data_atend = row[2]
        prof_nome  = row[3]
        status_a   = row[4]
        justif     = row[5]
        anexo      = row[6]
        evol       = row[7]
        combo_plano_id = row[8]

        procs = []
        if has_table(conn, "atendimento_procedimentos"):
            proc_cols = ["procedimento"]
            if has_column(conn, "atendimento_procedimentos", "codigo_sigtap"):
                proc_cols.append("COALESCE(codigo_sigtap,'') AS codigo_sigtap")
            else:
                proc_cols.append("'' AS codigo_sigtap")

            cur.execute(f"""
                SELECT {", ".join(proc_cols)}
                  FROM atendimento_procedimentos
                 WHERE atendimento_id = ?
                 ORDER BY id ASC
            """, (aid,))
            procs = [
                {"procedimento": r[0] or "", "codigo_sigtap": r[1] or ""}
                for r in cur.fetchall()
            ]

        primeiro_proc = procs[0]["procedimento"] if procs else "-"
        primeiro_cod  = procs[0]["codigo_sigtap"] if procs else "-"
        combo = _buscar_combo_ativo_paciente(conn, paciente_id)

    return jsonify({
        "ok": True,
        "found": True,
        "id": aid,
        "data": (data_atend or "-"),
        "profissional": (prof_nome or "-"),
        "status": (status_a or "-"),
        "justificativa": (justif or ""),
        "anexo_atestado": (anexo or ""),
        "evolucao": (evol or ""),
        "procedimento": primeiro_proc,
        "codigo_sigtap": primeiro_cod,
        "procedimentos": procs,
        "combo_plano_id": combo_plano_id,
        "combo": combo,
    })


@atendimentos_bp.route("/<int:aid>.json", methods=["GET"])
def ver_atendimento_json(aid: int):
    conn = conectar_db()
    ensure_atendimentos_schema(conn)
    ensure_atendimento_procedimentos_schema(conn)
    cur = conn.cursor()

    try:
        if not has_table(conn, "atendimentos"):
            return jsonify({"ok": False, "error": "Tabela de atendimentos não encontrada."}), 404

        cols = ["id", "paciente_id", "data_atendimento"]

        if has_column(conn, "atendimentos", "nome_profissional"):
            cols.append("nome_profissional")
        else:
            cols.append("'' AS nome_profissional")

        if has_column(conn, "atendimentos", "status"):
            cols.append("status")
        else:
            cols.append("'' AS status")

        if has_column(conn, "atendimentos", "justificativa"):
            cols.append("justificativa")
        else:
            cols.append("'' AS justificativa")

        if has_column(conn, "atendimentos", "evolucao"):
            cols.append("evolucao")
        else:
            cols.append("'' AS evolucao")

        if has_column(conn, "atendimentos", "nome"):
            cols.append("nome")
        else:
            cols.append("'' AS nome")

        if has_column(conn, "atendimentos", "mod"):
            cols.append("mod")
        else:
            cols.append("'' AS mod")

        if has_column(conn, "atendimentos", "status_paciente"):
            cols.append("status_paciente")
        else:
            cols.append("'' AS status_paciente")

        if has_column(conn, "atendimentos", "anexo_atestado"):
            cols.append("anexo_atestado")
        else:
            cols.append("'' AS anexo_atestado")

        if has_column(conn, "atendimentos", "combo_plano_id"):
            cols.append("COALESCE(combo_plano_id, NULL) AS combo_plano_id")
        else:
            cols.append("NULL AS combo_plano_id")

        sql = f"""
            SELECT {", ".join(cols)}
              FROM atendimentos
             WHERE id = ?
             LIMIT 1
        """
        cur.execute(sql, (aid,))
        r = cur.fetchone()

        if not r:
            return jsonify({"ok": False, "error": "Atendimento não encontrado."}), 404

        idx = 0
        atendimento_id   = r[idx]; idx += 1
        paciente_id      = r[idx]; idx += 1
        data_atendimento = r[idx]; idx += 1
        prof_nome        = r[idx]; idx += 1
        status_atend     = r[idx]; idx += 1
        justificativa    = r[idx]; idx += 1
        evolucao         = r[idx]; idx += 1
        paciente_nome    = r[idx]; idx += 1
        mod              = r[idx]; idx += 1
        status_paciente  = r[idx]; idx += 1
        anexo_atestado   = r[idx]; idx += 1
        combo_plano_id   = r[idx]; idx += 1

        prontuario = ""
        if paciente_id and has_table(conn, "pacientes") and has_column(conn, "pacientes", "prontuario"):
            try:
                cur.execute("""
                    SELECT COALESCE(prontuario, '')
                      FROM pacientes
                     WHERE id = ?
                     LIMIT 1
                """, (paciente_id,))
                rp = cur.fetchone()
                prontuario = (rp[0] or "") if rp else ""
            except Exception:
                prontuario = ""

        procs = []
        if has_table(conn, "atendimento_procedimentos"):
            proc_cols = ["procedimento"]
            if has_column(conn, "atendimento_procedimentos", "codigo_sigtap"):
                proc_cols.append("COALESCE(codigo_sigtap,'') AS codigo_sigtap")
            else:
                proc_cols.append("'' AS codigo_sigtap")

            cur.execute(f"""
                SELECT {", ".join(proc_cols)}
                  FROM atendimento_procedimentos
                 WHERE atendimento_id = ?
                 ORDER BY id ASC
            """, (aid,))
            procs = [
                {
                    "procedimento": x[0] or "",
                    "codigo_sigtap": x[1] or ""
                }
                for x in cur.fetchall()
            ]

        primeiro_proc = procs[0]["procedimento"] if procs else ""
        primeiro_cod  = procs[0]["codigo_sigtap"] if procs else ""
        combo = _buscar_combo_ativo_paciente(conn, paciente_id)

        return jsonify({
            "ok": True,
            "id": atendimento_id,
            "paciente_id": paciente_id,
            "data_atendimento": data_atendimento or "",
            "status": status_atend or "",
            "justificativa": justificativa or "",
            "evolucao": evolucao or "",
            "paciente_nome": paciente_nome or "",
            "prontuario": prontuario or "",
            "mod": mod or "",
            "status_paciente": status_paciente or "",
            "profissional_nome": prof_nome or "—",
            "anexo_atestado": anexo_atestado or "",
            "procedimento": primeiro_proc,
            "codigo_sigtap": primeiro_cod,
            "procedimentos": procs,
            "combo_plano_id": combo_plano_id,
            "combo": combo,
        })

    finally:
        conn.close()


# ============================================================
# HISTÓRICO
# ============================================================

@atendimentos_bp.route("/historico", methods=["GET"])
def historico_page():
    paciente_id = request.args.get("paciente_id")
    paciente_nome = request.args.get("paciente_nome", "")
    return render_template(
        "historico_atendimentos.html",
        data_hoje=date.today().isoformat(),
        paciente_id=paciente_id,
        paciente_nome=paciente_nome,
    )


@atendimentos_bp.route("/api/historico")
def api_historico():
    paciente_id = request.args.get("paciente_id")
    if not paciente_id:
        return jsonify({"ok": False, "error": "Parâmetro 'paciente_id' é obrigatório."}), 400

    with conectar_db() as conn:
        ensure_atendimentos_schema(conn)
        ensure_atendimento_procedimentos_schema(conn)
        cur = conn.cursor()

        sql = """
            SELECT
                a.id                          AS atendimento_id,
                a.data_atendimento            AS data_atendimento,
                ap.procedimento               AS procedimento,
                COALESCE(ap.codigo_sigtap,'') AS codigo_sigtap,

                COALESCE(a.status,'')         AS status,
                COALESCE(a.justificativa,'')  AS justificativa,
                COALESCE(a.evolucao,'')       AS evolucao,

                COALESCE(a.nome_profissional,'') AS nome_profissional,
                COALESCE(a.cns_profissional,'')  AS cns_profissional,
                COALESCE(a.cbo_profissional,'')  AS cbo_profissional
            FROM atendimentos a
            JOIN atendimento_procedimentos ap
              ON ap.atendimento_id = a.id
            WHERE a.paciente_id = ?
            ORDER BY
              CASE
                WHEN a.data_atendimento GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' THEN a.data_atendimento
                ELSE '0000-00-00'
              END DESC,
              a.id DESC,
              ap.id ASC
            LIMIT 800
        """
        cur.execute(sql, (paciente_id,))
        rows = cur.fetchall()

    return jsonify({
        "ok": True,
        "items": [
            {
                "atendimento_id": r[0],
                "data_atendimento": r[1],
                "procedimento": r[2],
                "codigo_sigtap": r[3] or "",
                "status": r[4] or "",
                "justificativa": r[5] or "",
                "evolucao": r[6] or "",
                "profissional": (r[7] or "—"),
                "profissional_cns": r[8] or "",
                "profissional_cbo": r[9] or "",
            }
            for r in rows
        ]
    })


# ============================================================
# ========== FILA DE ATENDIMENTOS ==========
# ============================================================

def _today_iso() -> str:
    return date.today().isoformat()


def _has_agenda_table(conn) -> bool:
    return has_table(conn, "agendamentos")


def _resolve_prof_id_by_nome_ou_cpf(conn, nome: str | None, cpf: str | None) -> int | None:
    cur = conn.cursor()

    if cpf and has_table(conn, "usuarios") and has_column(conn, "usuarios", "cpf"):
        cur.execute(
            "SELECT id FROM usuarios WHERE TRIM(COALESCE(cpf,'')) = TRIM(?) LIMIT 1",
            (cpf,),
        )
        r = cur.fetchone()
        if r:
            return int(r[0])

    if nome:
        if has_table(conn, "usuarios") and has_column(conn, "usuarios", "nome"):
            cur.execute(
                "SELECT id FROM usuarios WHERE TRIM(UPPER(nome)) = TRIM(UPPER(?)) LIMIT 1",
                (nome,),
            )
            r = cur.fetchone()
            if r:
                return int(r[0])

        if has_table(conn, "profissionais") and has_column(conn, "profissionais", "nome"):
            cur.execute(
                "SELECT id FROM profissionais WHERE TRIM(UPPER(nome)) = TRIM(UPPER(?)) LIMIT 1",
                (nome,),
            )
            r = cur.fetchone()
            if r:
                return int(r[0])

    return None


def _resolve_paciente_id_by_nome(conn, nome: str) -> int | None:
    if not has_table(conn, "pacientes"):
        return None
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM pacientes WHERE TRIM(UPPER(nome)) = TRIM(UPPER(?)) LIMIT 1",
        (nome,),
    )
    r = cur.fetchone()
    return int(r[0]) if r else None


def _ensure_fila_table(conn):
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fila_atendimentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hora TEXT NOT NULL,
            paciente_id INTEGER,
            paciente_nome TEXT,
            profissional_id INTEGER NOT NULL,
            tipo TEXT,
            prioridade TEXT,
            obs TEXT,
            created_at TEXT NOT NULL
        )
        """
    )

    cur.execute("PRAGMA table_info(fila_atendimentos)")
    cols = {r[1] for r in cur.fetchall()}

    if "origem" not in cols:
        try: cur.execute("ALTER TABLE fila_atendimentos ADD COLUMN origem TEXT DEFAULT 'manual'")
        except Exception: pass

    if "agenda_id" not in cols:
        try: cur.execute("ALTER TABLE fila_atendimentos ADD COLUMN agenda_id INTEGER")
        except Exception: pass

    if "status" not in cols:
        try: cur.execute("ALTER TABLE fila_atendimentos ADD COLUMN status TEXT")
        except Exception: pass

    try:
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_fila_chave_dia
                ON fila_atendimentos (hora, paciente_id, profissional_id)
        """)
    except Exception:
        pass

    try:
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_fila_created_at
                ON fila_atendimentos (created_at)
        """)
    except Exception:
        pass

    try:
        cur.execute("""CREATE INDEX IF NOT EXISTS idx_fila_status ON fila_atendimentos (status)""")
    except Exception:
        pass

    conn.commit()


def _resolve_paciente(conn, paciente_id: str | None, paciente_texto: str | None):
    if not has_table(conn, "pacientes"):
        return None

    cur = conn.cursor()
    if paciente_id:
        cur.execute(
            "SELECT id, nome, COALESCE(cpf, '') FROM pacientes WHERE id = ? LIMIT 1",
            (paciente_id,),
        )
        r = cur.fetchone()
        if r:
            return {"id": r[0], "nome": r[1], "cpf": r[2]}

    txt = (paciente_texto or "").strip()
    if txt:
        if "(" in txt and txt.endswith(")"):
            cpf_str = txt.split("(")[-1].strip(") ").strip()
            cur.execute(
                "SELECT id, nome, COALESCE(cpf, '') FROM pacientes WHERE cpf = ? LIMIT 1",
                (cpf_str,),
            )
            r = cur.fetchone()
            if r:
                return {"id": r[0], "nome": r[1], "cpf": r[2]}

        nome = txt.split("(")[0].strip()
        if nome:
            cur.execute(
                "SELECT id, nome, COALESCE(cpf,'') FROM pacientes WHERE nome LIKE ? LIMIT 1",
                (f"{nome}%",),
            )
            r = cur.fetchone()
            if r:
                return {"id": r[0], "nome": r[1], "cpf": r[2]}

    return None


def _sync_today_agenda_to_fila(conn):
    if not _has_agenda_table(conn):
        return

    if not has_table(conn, "pacientes"):
        return

    _ensure_fila_table(conn)
    cur = conn.cursor()

    hoje = _today_iso()

    cur.execute("PRAGMA table_info(agendamentos)")
    cols = {r[1] for r in cur.fetchall()}
    has_prof_cpf = "profissional_cpf" in cols

    sql = f"""
        SELECT id,
               TRIM(COALESCE(paciente,''))       AS paciente,
               TRIM(COALESCE(profissional,''))   AS profissional,
               {"TRIM(COALESCE(profissional_cpf,'')) AS prof_cpf," if has_prof_cpf else "'' AS prof_cpf,"}
               strftime('%H:%M', inicio)          AS hora_ini
          FROM agendamentos
         WHERE date(inicio) = ?
         ORDER BY hora_ini ASC, profissional ASC, paciente ASC
    """
    cur.execute(sql, (hoje,))
    ag_rows = cur.fetchall()
    if not ag_rows:
        return

    # garante atendimentos existe pra regra "já foi atendido hoje"
    ensure_atendimentos_schema(conn)

    for aid, pac, prof, prof_cpf, hora in ag_rows:
        if not hora:
            continue

        pac_id = _resolve_paciente_id_by_nome(conn, pac) if pac else None
        prof_id = _resolve_prof_id_by_nome_ou_cpf(conn, prof, prof_cpf if has_prof_cpf else None)

        if not pac_id or not prof_id:
            continue

        # já tem atendimento hoje?
        cur.execute("""
            SELECT 1
              FROM atendimentos
             WHERE paciente_id = ?
               AND data_atendimento = ?
             LIMIT 1
        """, (pac_id, hoje))
        if cur.fetchone():
            continue

        # já está na fila hoje?
        cur.execute("""
            SELECT 1
              FROM fila_atendimentos
             WHERE hora = ?
               AND paciente_id = ?
               AND profissional_id = ?
               AND substr(created_at,1,10) = ?
             LIMIT 1
        """, (hora, pac_id, prof_id, hoje))
        if cur.fetchone():
            continue

        cur.execute("""
            INSERT INTO fila_atendimentos
                (hora, paciente_id, paciente_nome, profissional_id, tipo, prioridade, obs, created_at, origem, agenda_id)
            SELECT ?, id, nome, ?, 'Individual', 'verde', '', ?, 'agenda', ?
              FROM pacientes
             WHERE id = ?
             LIMIT 1
        """, (hora, prof_id, datetime.now().isoformat(), int(aid), pac_id))

    conn.commit()


@atendimentos_bp.route("/api/fila/sync_hoje", methods=["POST"])
def api_fila_sync_hoje():
    with conectar_db() as conn:
        _ensure_fila_table(conn)
        _sync_today_agenda_to_fila(conn)
    return jsonify({"ok": True})


@atendimentos_bp.route("/api/fila", methods=["GET"])
def api_fila_list():
    with conectar_db() as conn:
        _ensure_fila_table(conn)
        _sync_today_agenda_to_fila(conn)

        cur = conn.cursor()
        has_prof = has_table(conn, "profissionais")
        has_user = has_table(conn, "usuarios")

        base_cols = """
            f.id, f.hora, f.paciente_id, COALESCE(f.paciente_nome, p.nome) AS paciente_nome,
            f.profissional_id,
        """
        tail_cols = """
            COALESCE(f.tipo, 'Individual') AS tipo,
            COALESCE(f.prioridade, 'verde') AS prioridade,
            COALESCE(f.obs, '') AS obs,
            COALESCE(f.origem, 'manual') AS origem,
            COALESCE(f.agenda_id, NULL) AS agenda_id,
            COALESCE(f.status, '') AS status
        """

        if has_prof and has_user:
            sql = f"""
                SELECT {base_cols}
                       COALESCE(pr.nome, u.nome, '—') AS profissional_nome,
                       {tail_cols}
                  FROM fila_atendimentos f
                  LEFT JOIN pacientes     p  ON p.id  = f.paciente_id
                  LEFT JOIN profissionais pr ON pr.id = f.profissional_id
                  LEFT JOIN usuarios      u  ON u.id  = f.profissional_id
                 ORDER BY f.id DESC
            """
        elif has_prof:
            sql = f"""
                SELECT {base_cols}
                       COALESCE(pr.nome, '—') AS profissional_nome,
                       {tail_cols}
                  FROM fila_atendimentos f
                  LEFT JOIN pacientes     p  ON p.id  = f.paciente_id
                  LEFT JOIN profissionais pr ON pr.id = f.profissional_id
                 ORDER BY f.id DESC
            """
        elif has_user:
            sql = f"""
                SELECT {base_cols}
                       COALESCE(u.nome, '—') AS profissional_nome,
                       {tail_cols}
                  FROM fila_atendimentos f
                  LEFT JOIN pacientes p ON p.id = f.paciente_id
                  LEFT JOIN usuarios  u ON u.id = f.profissional_id
                 ORDER BY f.id DESC
            """
        else:
            sql = f"""
                SELECT {base_cols}
                       '—' AS profissional_nome,
                       {tail_cols}
                  FROM fila_atendimentos f
                  LEFT JOIN pacientes p ON p.id = f.paciente_id
                 ORDER BY f.id DESC
            """

        cur.execute(sql)
        rows = cur.fetchall()

        items = []
        for r in rows:
            combo_info = _buscar_combo_ativo_paciente(conn, r[2])

            items.append({
                "id": r[0],
                "hora": r[1],
                "paciente_id": r[2],
                "paciente_nome": r[3],
                "profissional_id": r[4],
                "profissional_nome": r[5],
                "tipo": r[6],
                "prioridade": r[7],
                "obs": r[8],
                "origem": r[9],
                "agenda_id": r[10],
                "status": r[11],
                "from_agenda": (r[9] == "agenda"),
                "combo": combo_info,
            })

    return jsonify(items)


@atendimentos_bp.route("/api/fila/add", methods=["POST"])
def api_fila_add():
    data = request.get_json(force=True, silent=True) or {}

    with conectar_db() as conn:
        _ensure_fila_table(conn)
        cur = conn.cursor()

        profissional_id = data.get("profissional_id")
        if not profissional_id:
            return jsonify({"ok": False, "error": "Profissional obrigatório."}), 400

        existe_prof = False
        if has_table(conn, "profissionais"):
            try:
                cond = "AND (ativo = 1 OR ativo IS NULL)" if has_column(conn, "profissionais", "ativo") else ""
                cur.execute(
                    f"SELECT 1 FROM profissionais WHERE id = ? {cond} LIMIT 1",
                    (int(profissional_id),),
                )
                existe_prof = cur.fetchone() is not None
            except Exception:
                existe_prof = False

        if not existe_prof and has_table(conn, "usuarios"):
            try:
                cur.execute("SELECT 1 FROM usuarios WHERE id = ? LIMIT 1", (int(profissional_id),))
                existe_prof = cur.fetchone() is not None
            except Exception:
                existe_prof = False

        if not existe_prof:
            return jsonify({"ok": False, "error": "Profissional não encontrado nas tabelas 'profissionais' ou 'usuarios'."}), 400

        pac = _resolve_paciente(
            conn,
            data.get("paciente_id"),
            data.get("paciente_texto") or data.get("paciente_nome"),
        )
        if not pac:
            return jsonify({"ok": False, "error": "Paciente não identificado."}), 400

        hora = (data.get("hora") or datetime.now().strftime("%H:%M")).strip()
        tipo = (data.get("tipo") or "Individual").strip()
        prioridade = (data.get("prioridade") or "verde").strip()
        obs = (data.get("obs") or "").strip()

        cur.execute("""
            INSERT INTO fila_atendimentos (hora, paciente_id, paciente_nome, profissional_id, tipo, prioridade, obs, created_at, origem)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'manual')
        """, (hora, pac["id"], pac["nome"], int(profissional_id), tipo, prioridade, obs, datetime.now().isoformat()))
        conn.commit()

    return jsonify({"ok": True})


@atendimentos_bp.route("/api/fila/<int:item_id>", methods=["DELETE"])
def api_fila_delete(item_id: int):
    with conectar_db() as conn:
        _ensure_fila_table(conn)
        cur = conn.cursor()
        cur.execute("DELETE FROM fila_atendimentos WHERE id = ?", (item_id,))
        conn.commit()
    return jsonify({"ok": True})


@atendimentos_bp.route("/api/fila/clear", methods=["POST"])
def api_fila_clear():
    with conectar_db() as conn:
        _ensure_fila_table(conn)
        cur = conn.cursor()
        cur.execute("DELETE FROM fila_atendimentos")
        conn.commit()
    return jsonify({"ok": True})


@atendimentos_bp.patch("/api/fila/<int:item_id>")
def api_fila_update(item_id: int):
    data = request.get_json(silent=True, force=True) or {}

    with conectar_db() as conn:
        _ensure_fila_table(conn)
        cur = conn.cursor()

        fields = []
        params = []

        if "hora" in data:
            fields.append("hora = ?"); params.append((data["hora"] or "").strip())
        if "tipo" in data:
            fields.append("tipo = ?"); params.append((data["tipo"] or "Individual").strip())
        if "prioridade" in data:
            fields.append("prioridade = ?"); params.append((data["prioridade"] or "verde").strip())
        if "obs" in data:
            fields.append("obs = ?"); params.append((data["obs"] or "").strip())
        if "profissional_id" in data:
            try:
                pid = int(data["profissional_id"]) if data["profissional_id"] else None
            except Exception:
                pid = None
            fields.append("profissional_id = ?"); params.append(pid)

        if "status" in data:
            fields.append("status = ?"); params.append((data["status"] or "").strip())

        if not fields:
            return jsonify({"ok": False, "error": "Nada para atualizar."}), 400

        params.append(item_id)
        cur.execute(f"UPDATE fila_atendimentos SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()

    return jsonify({"ok": True})


@atendimentos_bp.get("/declaracao/<int:item_id>")
def declaracao_comparecimento(item_id: int):
    with conectar_db() as conn:
        _ensure_fila_table(conn)
        cur = conn.cursor()
        cur.execute("""
            SELECT f.id, f.hora, f.paciente_id, COALESCE(f.paciente_nome, p.nome) AS paciente_nome,
                   f.profissional_id, COALESCE(u.nome, pr.nome, '—') AS profissional_nome,
                   COALESCE(f.tipo, 'Individual') AS tipo, COALESCE(f.prioridade, 'verde') AS prioridade,
                   COALESCE(f.obs, '') AS obs, f.created_at
              FROM fila_atendimentos f
              LEFT JOIN pacientes p      ON p.id = f.paciente_id
              LEFT JOIN usuarios u       ON u.id = f.profissional_id
              LEFT JOIN profissionais pr ON pr.id = f.profissional_id
             WHERE f.id = ?
             LIMIT 1
        """, (item_id,))
        r = cur.fetchone()

    if not r:
        return "Item não encontrado.", 404

    data = {
        "id": r[0], "hora": r[1], "paciente_id": r[2], "paciente_nome": r[3],
        "profissional_id": r[4], "profissional_nome": r[5], "tipo": r[6],
        "prioridade": r[7], "obs": r[8], "created_at": r[9]
    }
    return render_template("declaracao_comparecimento.html", **data, hoje=date.today())


# ============================================================
# AUTOCOMPLETE · PROFISSIONAIS (simples)
# ============================================================

@atendimentos_bp.get("/api/profissionais")
def api_profissionais():
    """
    Autocomplete via tabela usuarios.
    Retorna: { ok:true, items:[{id,nome,cpf,label}] }
    """
    q = (request.args.get("q") or "").strip()
    if len(q) < 3:
        return jsonify(ok=True, items=[])

    with conectar_db() as conn:
        cur = conn.cursor()

        if not has_table(conn, "usuarios") or not has_column(conn, "usuarios", "nome"):
            return jsonify(ok=True, items=[])

        has_cpf = has_column(conn, "usuarios", "cpf")
        qn = q.lower()
        qdigits = digits(q)

        conds = ["LOWER(COALESCE(nome,'')) LIKE ?"]
        params = [f"%{qn}%"]

        if has_cpf and qdigits:
            conds.append("COALESCE(cpf,'') LIKE ?")
            params.append(f"%{qdigits}%")

        sql = f"""
            SELECT
                id,
                TRIM(COALESCE(nome,'')) AS nome,
                {("TRIM(COALESCE(cpf,'')) AS cpf" if has_cpf else "'' AS cpf")}
            FROM usuarios
            WHERE {" OR ".join(conds)}
            ORDER BY nome COLLATE NOCASE
            LIMIT 50
        """
        cur.execute(sql, params)
        rows = cur.fetchall()

    items = []
    for r in rows:
        uid = r[0]
        nome = (r[1] or "").strip()
        cpf  = (r[2] or "").strip()
        if not nome:
            continue
        label = f"{nome} ({cpf})" if cpf else nome
        items.append({"id": uid, "nome": nome, "cpf": cpf, "label": label})

    return jsonify(ok=True, items=items)


# ============================================================
# AUTOCOMPLETE · PROFISSIONAIS (usado em REGISTROS)
# ============================================================

@atendimentos_bp.get("/api/profissionais_sugestao")
def api_profissionais_sugestao():
    q = (request.args.get("q") or "").strip()
    if len(q) < 3:
        return jsonify([])

    q_low = q.lower()
    q_digits = digits(q)

    with conectar_db() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        if not has_table(conn, "usuarios"):
            return jsonify([])

        cols = _table_columns(conn, "usuarios")
        has_role = "role" in cols
        has_cbo = "cbo" in cols
        has_nome = "nome" in cols
        if not has_nome:
            return jsonify([])

        role_filter = "AND UPPER(role) = 'PROFISSIONAL'" if has_role else ""
        cbo_cond = "OR (? <> '' AND COALESCE(cbo,'') LIKE ?)" if has_cbo else ""

        sql = f"""
        SELECT
            id,
            nome,
            {("COALESCE(cbo, '') AS cbo" if has_cbo else "'' AS cbo")}
        FROM usuarios
        WHERE
            1=1
            {role_filter}
            AND (
                LOWER(COALESCE(nome,'')) LIKE ?
                {cbo_cond}
            )
        ORDER BY
            CASE
                WHEN LOWER(COALESCE(nome,'')) LIKE ? THEN 0
                ELSE 9
            END,
            LOWER(COALESCE(nome,'')) 
        LIMIT 12
        """

        params = [f"%{q_low}%"]
        if has_cbo:
            params += [q_digits, f"%{q_digits}%"]
        params += [f"{q_low}%"]

        cur.execute(sql, params)
        rows = cur.fetchall()

    return jsonify([{"id": r["id"], "nome": r["nome"], "cbo": r["cbo"]} for r in rows])