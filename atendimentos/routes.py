# atendimentos/routes.py
from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime

from flask import request, redirect, url_for, flash, render_template, jsonify, session
from werkzeug.utils import secure_filename

from . import atendimentos_bp
from db import conectar_db


# ============================================================
# HELPERS DE INTROSPECÇÃO
# ============================================================

def has_table(conn, table_name: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table_name,),
    )
    return cur.fetchone() is not None


def has_column(conn, table_name: str, column_name: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute(f"PRAGMA table_info({table_name})")
        cols = [r[1] for r in cur.fetchall()]  # (cid, name, type, notnull, dflt, pk)
        return column_name in cols
    except Exception:
        return False


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
            cur.execute(
                """
                SELECT id
                  FROM usuarios
                 WHERE TRIM(LOWER(COALESCE(login, nome, email, ''))) = TRIM(LOWER(?))
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
                _id = r[0]
                _nome = r[1] or ""
                _cns  = r[2] or ""
                _cbo  = r[3] or ""
                return _id, _nome, _cns, _cbo
        except Exception:
            pass

    return pid, "", "", ""


def _resolve_prof_nome(conn, profissional_id: int) -> str:
    cur = conn.cursor()

    # tenta profissionais
    if has_table(conn, "profissionais"):
        try:
            cur.execute(
                "SELECT nome FROM profissionais WHERE id = ? AND (ativo = 1 OR ativo IS NULL) LIMIT 1",
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
            sql = f"""
                SELECT nome
                  FROM usuarios
                 WHERE id = ?
                   {cond_role}
                   {cond_active}
                 LIMIT 1
            """
            cur.execute(sql, (profissional_id,))
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

def digits(s: str | None) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())


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

def _get_prof_cbo(conn, profissional_id: int | None) -> str:
    if not profissional_id:
        return ""
    _id, _nome, _cns, _cbo = _resolve_prof_dados(conn, profissional_id)
    return (_cbo or "").strip()

def _find_procedimentos_table(conn) -> tuple[str | None, dict]:
    """
    Tenta localizar a tabela de procedimentos e mapear colunas.
    Você pode adicionar/ajustar nomes aqui conforme seu BD.
    """
    candidates = [
        "procedimentos",
        "procedimentos_sigtap",
        "sigtap_procedimentos",
        "tb_procedimentos",
    ]
    for t in candidates:
        if has_table(conn, t):
            cols = _table_columns(conn, t)
            # mapeia colunas comuns
            col_codigo = _first_existing(cols, ["codigo", "codigo_sigtap", "cod_sigtap", "procedimento_codigo"])
            col_desc   = _first_existing(cols, ["descricao", "procedimento", "nome", "procedimento_nome"])
            col_cid    = _first_existing(cols, ["cid", "cid_regra", "cid_min", "cid_compat"])
            col_cbo    = _first_existing(cols, ["cbo", "cbo_prof", "cbo_codigo", "cbo_permitido"])
            return t, {
                "codigo": col_codigo,
                "desc": col_desc,
                "cid": col_cid,
                "cbo": col_cbo,
                "cols": cols,
            }
    return None, {}

def _listar_procedimentos_compatíveis_db(conn, cbo: str, paciente_cids: list[str]) -> list[dict]:
    """
    Tabela (seu schema):
      pa_cod, pa_descricao, pa_cid, pa_cbo, ativo

    Regras:
      - CBO do profissional (pa_cbo) tem que bater
      - ativo = 1
      - se pa_cid vazio/NULL => sempre pode
      - se pa_cid preenchido => precisa casar com algum CID do paciente (prefixo)
        Ex: proc F84 casa com paciente F84.0
    """
    cbo = (cbo or "").strip()
    if not cbo:
        return []

    # normaliza CIDs do paciente (remove ponto/espaço): F84.0 -> F840
    pac_norms = [ _cid_norm_py(x) for x in (paciente_cids or []) if x ]

    cur = conn.cursor()

    # Normaliza o CID do procedimento no SQL removendo "." e espaços
    proc_norm = "REPLACE(REPLACE(UPPER(COALESCE(pa_cid,'')),'.',''),' ','')"

    params: list[str] = [cbo]

    # CID rule
    cid_ok_parts = ["TRIM(COALESCE(pa_cid,'')) = ''"]  # sem CID = ok

    if pac_norms:
        for pn in pac_norms:
            # prefix match: paciente começa com proc_cid OR proc_cid começa com paciente
            cid_ok_parts.append(f"({proc_norm} <> '' AND (? LIKE {proc_norm} || '%' OR {proc_norm} LIKE ? || '%'))")
            params.append(pn)
            params.append(pn)
    # se paciente não tem CID, só passa o "sem CID" mesmo

    sql = f"""
        SELECT
            TRIM(COALESCE(pa_cod,''))        AS codigo,
            TRIM(COALESCE(pa_descricao,''))  AS descricao,
            TRIM(COALESCE(pa_cid,''))        AS cid_regra
        FROM procedimentos   -- ⚠️ TROQUE se o nome real da tabela for outro
        WHERE TRIM(COALESCE(pa_cbo,'')) = TRIM(?)
          AND COALESCE(ativo,1) = 1
          AND ({' OR '.join(cid_ok_parts)})
        ORDER BY descricao COLLATE NOCASE, codigo
        LIMIT 600
    """

    cur.execute(sql, params)
    rows = cur.fetchall()

    return [
        {"codigo": r[0] or "", "descricao": r[1] or "", "cid_regra": r[2] or ""}
        for r in rows
        if (r[1] or "").strip()
    ]

# ============================================================
# SCHEMAS ( PROCEDIMENTOS SUGERIDOS)
# ============================================================

@atendimentos_bp.get("/api/procedimentos_sugeridos")
def api_procedimentos_sugeridos():
    paciente_id = (request.args.get("paciente_id") or "").strip()
    if not paciente_id:
        return jsonify(ok=False, error="paciente_id é obrigatório."), 400

    conn = conectar_db()
    try:
        profissional_id = _resolve_logged_profissional_id(conn)
        if not profissional_id:
            return jsonify(ok=False, error="Profissional logado não identificado."), 401

        _, _, _, prof_cbo = _resolve_prof_dados(conn, profissional_id)
        pac_cids = _get_paciente_cids(conn, paciente_id)

        items = _listar_procedimentos_compatíveis_db(conn, prof_cbo, pac_cids)

        return jsonify(ok=True, cbo=(prof_cbo or ""), paciente_cids=pac_cids, items=items)
    finally:
        try: conn.close()
        except Exception: pass




# ============================================================
# SCHEMAS (ATENDIMENTOS + PROCEDIMENTOS)
# ============================================================

def ensure_atendimentos_schema(conn):
    """
    Garante colunas mínimas na tabela 'atendimentos'.
    OBS: aqui assumimos que a tabela já existe no seu projeto.
    """
    cur = conn.cursor()

    # profissional_id
    if not has_column(conn, "atendimentos", "profissional_id"):
        try:
            cur.execute("ALTER TABLE atendimentos ADD COLUMN profissional_id INTEGER")
        except Exception:
            pass

    # nome_profissional
    if not has_column(conn, "atendimentos", "nome_profissional"):
        try:
            cur.execute("ALTER TABLE atendimentos ADD COLUMN nome_profissional TEXT")
        except Exception:
            pass

    # cns_profissional
    if not has_column(conn, "atendimentos", "cns_profissional"):
        try:
            cur.execute("ALTER TABLE atendimentos ADD COLUMN cns_profissional TEXT")
        except Exception:
            pass

    # cbo_profissional
    if not has_column(conn, "atendimentos", "cbo_profissional"):
        try:
            cur.execute("ALTER TABLE atendimentos ADD COLUMN cbo_profissional TEXT")
        except Exception:
            pass

    # índice útil
    try:
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_atends_paciente_data
                ON atendimentos (paciente_id, data_atendimento)
        """)
    except Exception:
        pass

    conn.commit()


def ensure_atendimento_procedimentos_schema(conn):
    """
    1 atendimento (pai) → N procedimentos (filhos)
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
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_proc_atendimento
        ON atendimento_procedimentos (atendimento_id)
    """)
    conn.commit()



# ============================================================
# FETCHERS BÁSICOS
# ============================================================

def fetch_pacientes(cur):
    cur.execute("""
        SELECT id, nome, COALESCE(cpf, ''), prontuario, mod, status
          FROM pacientes
         ORDER BY nome
    """)
    return [
        {
            "id": r[0],
            "nome": r[1],
            "cpf": r[2],
            "prontuario": r[3],
            "mod": r[4],
            "status": r[5],
        }
        for r in cur.fetchall()
    ]


# ============================================================
# PÁGINAS
# ============================================================

@atendimentos_bp.route("/", methods=["GET"])
def lista_atendimentos():
    """
    Tela da fila (recepção). Mantive como estava: ainda pode precisar de lista de profissionais.
    """
    conn = conectar_db()
    cur = conn.cursor()
    pacientes = fetch_pacientes(cur)

    # Se sua fila usa select de profissional, a API /api/profissionais segue existindo.
    # Aqui você pode continuar passando profissionais se seu template usa.
    profissionais = []
    try:
        if has_table(conn, "usuarios"):
            # monta SELECT sem citar colunas que não existem
            nome_expr = "COALESCE(nome, '')" if has_column(conn, "usuarios", "nome") else "''"
            login_expr = "COALESCE(login, '')" if has_column(conn, "usuarios", "login") else "''"
            email_expr = "COALESCE(email, '')" if has_column(conn, "usuarios", "email") else "''"

            # filtros bons: só profissionais e só ativos (quando existir)
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


    conn.close()

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
    conn = conectar_db()
    cur = conn.cursor()
    pacientes = fetch_pacientes(cur)
    conn.close()

    return render_template(
        "atendimentos.html",
        pacientes=pacientes,
        profissionais=[],  # não precisa mais no template (pode remover o select)
        data_hoje=date.today().isoformat(),
    )


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

    # fallback: seu HTML atual usa campo único
    if not procs:
        p = (request.form.get("procedimento") or "").strip()
        c = (request.form.get("codigoProcedimento") or "").strip()
        if p:
            procs = [p]
            cods = [c] if c else [""]

    # garante mesmo tamanho (zip seguro)
    if len(cods) < len(procs):
        cods += [""] * (len(procs) - len(cods))

    # limpa
    procs = [str(x or "").strip() for x in procs if str(x or "").strip()]
    cods  = [str(x or "").strip() for x in cods][:len(procs)]

    return procs, cods


@atendimentos_bp.route("/salvar", methods=["POST"], endpoint="salvar_atendimento")
def salvar_atendimento_view():
    conn = conectar_db()
    cursor = conn.cursor()

    try:
        ensure_atendimentos_schema(conn)
        ensure_atendimento_procedimentos_schema(conn)

        # ✅ garante fila schema (pra poder atualizar status)
        _ensure_fila_table(conn)

        # ---------------------------------
        # PROFISSIONAL = LOGADO (obrigatório)
        # ---------------------------------
        profissional_id = _resolve_logged_profissional_id(conn)
        if not profissional_id:
            flash("Não foi possível identificar o profissional logado. Faça login novamente.")
            return redirect(url_for("atendimentos.pagina_atendimento"))

        _, prof_nome, prof_cns, prof_cbo = _resolve_prof_dados(conn, profissional_id)

        # ---------------------------------
        # Inputs do form
        # ---------------------------------
        paciente_id      = request.form.get("nomePaciente")
        data_atendimento = request.form.get("dataAtendimento") or date.today().isoformat()
        status_atend     = request.form.get("status_justificativa") or "Realizado"
        justificativa    = request.form.get("justificativa") or ""
        evolucao         = request.form.get("evolucao") or ""

        # ✅ vem do redirect /atendimentos/registrar?fila_id=...
        # mas o POST NÃO leva query string automaticamente, então usamos hidden input no form
        fila_id_raw = (request.form.get("fila_id") or "").strip()
        fila_id = int(fila_id_raw) if fila_id_raw.isdigit() else None

        # ---------------------------------
        # Procedimentos do form
        # ---------------------------------
        procedimentos, codigos = _normalize_procs_from_form()
        if not procedimentos:
            flash("Informe pelo menos 1 procedimento.")
            return redirect(url_for("atendimentos.pagina_atendimento"))

        # ---------------------------------
        # Valida paciente
        # ---------------------------------
        cursor.execute(
            "SELECT nome, prontuario, mod, status FROM pacientes WHERE id = ?",
            (paciente_id,),
        )
        paciente = cursor.fetchone()
        if not paciente:
            flash("Paciente não encontrado.")
            return redirect(url_for("atendimentos.pagina_atendimento"))

        nome, prontuario, mod, status_paciente = paciente

        # ---------------------------------
        # ✅ VALIDAÇÃO FORTE (DB): CBO x CID
        # ---------------------------------
        pac_cids = _get_paciente_cids(conn, paciente_id)
        permitidos = _listar_procedimentos_compatíveis_db(conn, (prof_cbo or "").strip(), pac_cids)

        permitidos_cod = { (x.get("codigo") or "").strip() for x in permitidos if (x.get("codigo") or "").strip() }
        permitidos_desc = { (x.get("descricao") or "").strip().lower() for x in permitidos if (x.get("descricao") or "").strip() }

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
            flash(
                "Procedimento(s) incompatível(is) com o CBO/CID do paciente: "
                + ", ".join(invalidos)
                + f" | CBO: {prof_cbo or '—'} | CID(s): {cids_txt}"
            )
            return redirect(url_for("atendimentos.pagina_atendimento"))

        # ---------------------------------
        # Upload opcional
        # ---------------------------------
        anexo = request.files.get("anexoFalta")
        caminho_anexo = None
        if anexo and anexo.filename:
            filename = secure_filename(anexo.filename)
            pasta = os.path.join("static", "anexos_atestados")
            os.makedirs(pasta, exist_ok=True)
            caminho_anexo = os.path.join(pasta, filename)
            anexo.save(caminho_anexo)

        # ---------------------------------
        # INSERT ATENDIMENTO (PAI)
        # ---------------------------------
        cols = [
            "paciente_id", "data_atendimento",
            "status", "justificativa", "evolucao",
            "nome", "prontuario", "mod", "status"
        ]
        vals = [
            paciente_id, data_atendimento,
            status_atend, justificativa, evolucao,
            nome, prontuario, mod, status_paciente
        ]

        if has_column(conn, "atendimentos", "anexo_atestado"):
            cols.append("anexo_atestado")
            vals.append(caminho_anexo)

        if has_column(conn, "atendimentos", "profissional_id"):
            cols.append("profissional_id")
            vals.append(profissional_id)

        if has_column(conn, "atendimentos", "nome_profissional"):
            cols.append("nome_profissional")
            vals.append(prof_nome)

        if has_column(conn, "atendimentos", "cns_profissional"):
            cols.append("cns_profissional")
            vals.append(prof_cns)

        if has_column(conn, "atendimentos", "cbo_profissional"):
            cols.append("cbo_profissional")
            vals.append(prof_cbo)

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
        for proc, cod in zip(procedimentos, codigos):
            cursor.execute("""
                INSERT INTO atendimento_procedimentos
                    (atendimento_id, procedimento, codigo_sigtap, created_at)
                VALUES (?, ?, ?, ?)
            """, (
                atendimento_id,
                proc,
                cod if cod else None,
                now_iso
            ))

        # ---------------------------------
        # ✅ FINALIZA A FILA (o pulo do gato)
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
        flash("Atendimento salvo com sucesso.")
        return redirect(url_for("atendimentos.pagina_atendimento"))

    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        flash(f"Erro ao salvar atendimento: {e}")
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
    termo = request.args.get("termo", "").lower()
    conn = conectar_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, nome, prontuario, status, mod, nascimento, cid
          FROM pacientes
         WHERE LOWER(nome) LIKE ?
         LIMIT 10
        """,
        (f"%{termo}%",),
    )
    resultados = [
        {
            "id": row[0],
            "nome": row[1],
            "prontuario": row[2],
            "status": row[3],
            "mod": row[4],
            "nascimento": row[5],
            "cid": row[6] or "-",
        }
        for row in cur.fetchall()
    ]
    conn.close()
    return jsonify(resultados)


@atendimentos_bp.route("/api/paciente")
def api_paciente():
    pid = (request.args.get("id") or "").strip()
    if not pid:
        return jsonify({"ok": False, "error": "Parâmetro 'id' é obrigatório."}), 400

    conn = conectar_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, nome, prontuario, status, mod, nascimento, cid
          FROM pacientes
         WHERE id = ?
         LIMIT 1
        """,
        (pid,),
    )
    row = cur.fetchone()
    conn.close()

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
    paciente_id = request.args.get("id")
    if not paciente_id:
        return jsonify({"ok": False, "error": "Parâmetro 'id' (paciente) é obrigatório."}), 400

    conn = conectar_db()
    ensure_atendimentos_schema(conn)
    ensure_atendimento_procedimentos_schema(conn)
    cur = conn.cursor()

    # pega o atendimento pai mais recente
    select_cols = [
        "id", "data_atendimento",
        "status", "justificativa",
        "anexo_atestado", "evolucao"
    ]
    if not has_column(conn, "atendimentos", "anexo_atestado"):
        # substitui por expressão vazia
        select_cols[4] = "'' AS anexo_atestado"

    if has_column(conn, "atendimentos", "profissional_id"):
        select_cols.insert(1, "profissional_id")

    sql = f"""
        SELECT {", ".join(select_cols)}
          FROM atendimentos
         WHERE paciente_id = ?
         ORDER BY
             CASE
               WHEN data_atendimento GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' THEN data_atendimento
               ELSE '0000-00-00'
             END DESC,
             id DESC
         LIMIT 1
    """
    cur.execute(sql, (paciente_id,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return jsonify({"ok": True, "found": False, "data": "-", "profissional": "-", "id": None})

    col_idx = {name.split(" AS ")[-1].strip(): i for i, name in enumerate(select_cols)}
    aid        = row[col_idx["id"]]
    data_atend = row[col_idx["data_atendimento"]]
    status_a   = row[col_idx["status"]]
    justif     = row[col_idx["justificativa"]]
    anexo      = row[col_idx["anexo_atestado"]]
    evol       = row[col_idx["evolucao"]]

    prof_nome = "—"
    if "profissional_id" in col_idx:
        prof_id = row[col_idx["profissional_id"]]
        prof_nome = _resolve_prof_nome_by_id(conn, prof_id)

    # pega procedimentos filhos
    cur.execute("""
        SELECT procedimento, COALESCE(codigo_sigtap,'')
          FROM atendimento_procedimentos
         WHERE atendimento_id = ?
         ORDER BY id ASC
    """, (aid,))
    procs = [{"procedimento": r[0], "codigo_sigtap": r[1] or ""} for r in cur.fetchall()]

    # compat: mantém procedimento/codigo no topo como "primeiro"
    primeiro_proc = procs[0]["procedimento"] if procs else "-"
    primeiro_cod  = procs[0]["codigo_sigtap"] if procs else "-"

    conn.close()
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
    })


@atendimentos_bp.route("/<int:aid>.json", methods=["GET"])
def ver_atendimento_json(aid: int):
    conn = conectar_db()
    ensure_atendimentos_schema(conn)
    ensure_atendimento_procedimentos_schema(conn)
    cur = conn.cursor()

    # select do PAI
    cols = [
        "id", "paciente_id", "data_atendimento",
        "status", "justificativa", "evolucao",
        "nome", "prontuario", "mod", "status"
    ]

    if has_column(conn, "atendimentos", "anexo_atestado"):
        cols.insert(6, "anexo_atestado")  # antes de nome

    if has_column(conn, "atendimentos", "profissional_id"):
        cols.insert(2, "profissional_id")

    cur.execute(f"SELECT {', '.join(cols)} FROM atendimentos WHERE id = ? LIMIT 1", (aid,))
    r = cur.fetchone()
    if not r:
        conn.close()
        return jsonify({"ok": False, "error": "Atendimento não encontrado."}), 404

    col_idx = {name: i for i, name in enumerate(cols)}
    prof_nome = "—"
    if "profissional_id" in col_idx:
        prof_id = r[col_idx["profissional_id"]]
        prof_nome = _resolve_prof_nome_by_id(conn, prof_id)

    # filhos
    cur.execute("""
        SELECT procedimento, COALESCE(codigo_sigtap,'')
          FROM atendimento_procedimentos
         WHERE atendimento_id = ?
         ORDER BY id ASC
    """, (aid,))
    procs = [{"procedimento": x[0], "codigo_sigtap": x[1] or ""} for x in cur.fetchall()]

    # compat (primeiro proc)
    primeiro_proc = procs[0]["procedimento"] if procs else ""
    primeiro_cod  = procs[0]["codigo_sigtap"] if procs else ""

    out = {
        "ok": True,
        "id": r[col_idx["id"]],
        "paciente_id": r[col_idx["paciente_id"]],
        "data_atendimento": r[col_idx["data_atendimento"]],
        "status": r[col_idx["status"]],
        "justificativa": r[col_idx["justificativa"]],
        "evolucao": r[col_idx["evolucao"]],
        "paciente_nome": r[col_idx["nome"]],
        "prontuario": r[col_idx["prontuario"]],
        "mod": r[col_idx["mod"]],
        "status_paciente": r[col_idx["status"]],
        "profissional_nome": prof_nome,

        # compat com seu front antigo:
        "procedimento": primeiro_proc,
        "codigo_sigtap": primeiro_cod,

        # novo padrão:
        "procedimentos": procs,
    }

    if "anexo_atestado" in col_idx:
        out["anexo_atestado"] = r[col_idx["anexo_atestado"]] or ""

    conn.close()
    return jsonify(out)




# ============================================================
# HISTÓRICO (render + api)
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
    """
    ✅ Retorna 1 linha por PROCEDIMENTO (o que você quer pra 'Registros').
    A evolução/justificativa vem do atendimento PAI (não duplica no banco).
    """
    paciente_id = request.args.get("paciente_id")
    if not paciente_id:
        return jsonify({"ok": False, "error": "Parâmetro 'paciente_id' é obrigatório."}), 400

    conn = conectar_db()
    ensure_atendimentos_schema(conn)
    ensure_atendimento_procedimentos_schema(conn)
    cur = conn.cursor()

    # traz 1 linha por procedimento
    sql = """
        SELECT
            a.id                         AS atendimento_id,
            a.data_atendimento           AS data_atendimento,
            ap.procedimento              AS procedimento,
            COALESCE(ap.codigo_sigtap,'') AS codigo_sigtap,

            COALESCE(a.status,'')        AS status,
            COALESCE(a.justificativa,'') AS justificativa,
            COALESCE(a.evolucao,'')      AS evolucao,

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
    conn.close()

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
# ========== FILA DE ATENDIMENTOS  ==========
# (Seu bloco original continua daqui pra baixo)
# ============================================================

def _today_dow_dom(dt: datetime | None = None) -> int:
    dt = dt or datetime.now()
    return (dt.weekday() + 1) % 7

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
    except Exception: pass

    try:
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_fila_created_at
                ON fila_atendimentos (created_at)
        """)
    except Exception: pass

    try:
        cur.execute("""CREATE INDEX IF NOT EXISTS idx_fila_status ON fila_atendimentos (status)""")
    except Exception: pass

    conn.commit()


def _resolve_paciente(conn, paciente_id: str | None, paciente_texto: str | None):
    cur = conn.cursor()
    if paciente_id:
        cur.execute(
            "SELECT id, nome, COALESCE(cpf, '') FROM pacientes WHERE id = ?",
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

    for aid, pac, prof, prof_cpf, hora in ag_rows:
        if not hora:
            continue

        pac_id = _resolve_paciente_id_by_nome(conn, pac) if pac else None
        prof_id = _resolve_prof_id_by_nome_ou_cpf(conn, prof, prof_cpf if has_prof_cpf else None)

        if not pac_id or not prof_id:
            continue

        # ============================================
        # 🚫 JÁ EXISTE ATENDIMENTO HOJE? (NÃO INSERE SE SIM)
        # ============================================
        cur.execute("""
            SELECT 1
              FROM atendimentos
             WHERE paciente_id = ?
               AND data_atendimento = ?
             LIMIT 1
        """, (pac_id, hoje))
        if cur.fetchone():
            # Já foi atendido hoje, não insere novamente na fila
            continue

        cur.execute(
            """
            SELECT 1
              FROM fila_atendimentos
             WHERE hora = ?
               AND paciente_id = ?
               AND profissional_id = ?
               AND substr(created_at,1,10) = ?
             LIMIT 1
            """,
            (hora, pac_id, prof_id, hoje),
        )
        if cur.fetchone() is not None:
            continue

        cur.execute(
            """
            INSERT INTO fila_atendimentos
                (hora, paciente_id, paciente_nome, profissional_id, tipo, prioridade, obs, created_at, origem, agenda_id)
            SELECT ?, id, nome, ?, 'Individual', 'verde', '', ?, 'agenda', ?
              FROM pacientes
             WHERE id = ?
             LIMIT 1
            """,
            (hora, prof_id, datetime.now().isoformat(), int(aid), pac_id),
        )

    conn.commit()


@atendimentos_bp.route("/api/fila/sync_hoje", methods=["POST"])
def api_fila_sync_hoje():
    conn = conectar_db()
    _ensure_fila_table(conn)
    _sync_today_agenda_to_fila(conn)
    conn.close()
    return jsonify({"ok": True})


@atendimentos_bp.route("/api/fila", methods=["GET"])
def api_fila_list():
    conn = conectar_db()
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
    conn.close()

    return jsonify([
        {
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
        }
        for r in rows
    ])


@atendimentos_bp.route("/api/fila/add", methods=["POST"])
def api_fila_add():
    data = request.get_json(force=True, silent=True) or {}

    conn = conectar_db()
    _ensure_fila_table(conn)
    cur = conn.cursor()

    profissional_id = data.get("profissional_id")
    if not profissional_id:
        conn.close()
        return jsonify({"ok": False, "error": "Profissional obrigatório."}), 400

    existe_prof = False
    if has_table(conn, "profissionais"):
        try:
            cur.execute(
                "SELECT 1 FROM profissionais WHERE id = ? AND (ativo = 1 OR ativo IS NULL) LIMIT 1",
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
        conn.close()
        return jsonify({"ok": False, "error": "Profissional não encontrado nas tabelas 'profissionais' ou 'usuarios'."}), 400

    pac = _resolve_paciente(
        conn,
        data.get("paciente_id"),
        data.get("paciente_texto") or data.get("paciente_nome"),
    )
    if not pac:
        conn.close()
        return jsonify({"ok": False, "error": "Paciente não identificado."}), 400

    hora = (data.get("hora") or datetime.now().strftime("%H:%M")).strip()
    tipo = (data.get("tipo") or "Individual").strip()
    prioridade = (data.get("prioridade") or "verde").strip()
    obs = (data.get("obs") or "").strip()

    cur.execute(
        """
        INSERT INTO fila_atendimentos (hora, paciente_id, paciente_nome, profissional_id, tipo, prioridade, obs, created_at, origem)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'manual')
        """,
        (hora, pac["id"], pac["nome"], int(profissional_id), tipo, prioridade, obs, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@atendimentos_bp.route("/api/fila/<int:item_id>", methods=["DELETE"])
def api_fila_delete(item_id: int):
    conn = conectar_db()
    _ensure_fila_table(conn)
    cur = conn.cursor()
    cur.execute("DELETE FROM fila_atendimentos WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@atendimentos_bp.route("/api/fila/clear", methods=["POST"])
def api_fila_clear():
    conn = conectar_db()
    _ensure_fila_table(conn)
    cur = conn.cursor()
    cur.execute("DELETE FROM fila_atendimentos")
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@atendimentos_bp.patch("/api/fila/<int:item_id>")
def api_fila_update(item_id: int):
    data = request.get_json(silent=True, force=True) or {}
    conn = conectar_db()
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
        conn.close()
        return jsonify({"ok": False, "error": "Nada para atualizar."}), 400

    params.append(item_id)
    cur.execute(f"UPDATE fila_atendimentos SET {', '.join(fields)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@atendimentos_bp.get("/declaracao/<int:item_id>")
def declaracao_comparecimento(item_id: int):
    conn = conectar_db()
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
    conn.close()
    if not r:
        return "Item não encontrado.", 404

    data = {
        "id": r[0], "hora": r[1], "paciente_id": r[2], "paciente_nome": r[3],
        "profissional_id": r[4], "profissional_nome": r[5], "tipo": r[6],
        "prioridade": r[7], "obs": r[8], "created_at": r[9]
    }
    return render_template("declaracao_comparecimento.html", **data, hoje=date.today())


# atendimentos/routes.py (ou onde estiver seu blueprint atendimentos)

@atendimentos_bp.get("/api/profissionais")
def api_profissionais():
    """
    Autocomplete de profissionais via tabela usuarios.
    Como você disse que NÃO existe coluna de profissional/role,
    usamos apenas 'nome' (e 'cpf' se existir).
    Retorna: { ok:true, items:[{id,nome,cpf,label}] }
    """
    q = (request.args.get("q") or "").strip()
    if len(q) < 3:
        return jsonify(ok=True, items=[])

    conn = conectar_db()
    cur = conn.cursor()

    if not has_table(conn, "usuarios") or not has_column(conn, "usuarios", "nome"):
        conn.close()
        return jsonify(ok=True, items=[])

    has_cpf = has_column(conn, "usuarios", "cpf")
    qn = q.lower()
    qdigits = digits(q)

    # busca por nome
    conds = ["LOWER(COALESCE(nome,'')) LIKE ?"]
    params = [f"%{qn}%"]

    # se digitou número, tenta CPF (se existir)
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
    conn.close()

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


from flask import request, jsonify
import sqlite3
from typing import Any

from db import conectar_db
from . import atendimentos_bp

# ============================================================
# AUTOCOMPLETE · PROFISSIONAIS (usado em REGISTROS)
# ============================================================
@atendimentos_bp.get("/api/profissionais_sugestao")
def api_profissionais_sugestao():
    q = (request.args.get("q") or "").strip()
    if len(q) < 3:
        return jsonify([])

    q_low = q.lower()
    q_digits = "".join(c for c in q if c.isdigit())

    conn = conectar_db()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # garante que a tabela existe
    cur.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='usuarios'
        LIMIT 1
    """)
    if not cur.fetchone():
        conn.close()
        return jsonify([])

    sql = """
    SELECT
        id,
        nome,
        COALESCE(cbo, '') AS cbo
    FROM usuarios
    WHERE
        UPPER(role) = 'PROFISSIONAL'
        AND (
            LOWER(nome) LIKE ?
            OR (? <> '' AND cbo LIKE ?)
        )
    ORDER BY
        CASE
            WHEN LOWER(nome) LIKE ? THEN 0
            WHEN (? <> '' AND cbo LIKE ?) THEN 1
            ELSE 9
        END,
        LOWER(nome)
    LIMIT 12
    """

    params = [
        f"%{q_low}%",
        q_digits,
        f"%{q_digits}%",
        f"{q_low}%",
        q_digits,
        f"{q_digits}%"
    ]

    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()

    return jsonify([
        {
            "id": r["id"],
            "nome": r["nome"],
            "cbo": r["cbo"]
        }
        for r in rows
    ])
