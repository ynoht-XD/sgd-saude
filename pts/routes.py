# sgd/pts/routes.py
from __future__ import annotations

from datetime import date, datetime
import io
import re

from flask import (
    request, jsonify, render_template, session,
    send_file, abort, redirect, url_for, flash
)
from werkzeug.exceptions import NotFound

from . import pts_bp
from db import conectar_db

from openpyxl import Workbook


# ============================================================
# HELPERS · INTROSPECÇÃO SQLITE
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
        cols = [r[1] for r in cur.fetchall()]
        return column_name in cols
    except Exception:
        return False


def _table_columns(conn, table: str) -> set[str]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return {r[1] for r in cur.fetchall()}


# ============================================================
# AUTH · RESOLVE USUÁRIO LOGADO
# ============================================================

def _resolve_logged_usuario_id(conn) -> int | None:
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
            r = cur.fetchone()
            if r:
                return int(r[0])
        except Exception:
            pass

    return None


# ============================================================
# FUNÇÃO SUGERIDA POR CBO (porque usuarios NÃO tem funcao)
# ============================================================

_CBO_TO_FUNCAO = {
    "223605": "Fisioterapeuta",
    "251510": "Psicólogo(a)",
    "223905": "Terapeuta Ocupacional",
    "223810": "Fonoaudiólogo(a)",
    "223505": "Enfermagem",
    "251605": "Assistente Social",
    "223710": "Nutricionista",
}

def _funcao_from_cbo(cbo: str) -> str:
    c = (cbo or "").strip()
    if not c:
        return ""
    return _CBO_TO_FUNCAO.get(c, "")


# ============================================================
# SCHEMA · PTS (pai) + participantes (filhos)
# ============================================================

def ensure_pts_schema(conn):
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER NOT NULL,
            data_pts TEXT NOT NULL,                 -- YYYY-MM-DD

            objetivo_geral TEXT,
            avaliacao TEXT,
            plano TEXT,
            observacoes TEXT,

            created_by INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_pts_paciente_data
        ON pts (paciente_id, data_pts)
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pts_participantes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pts_id INTEGER NOT NULL,
            usuario_id INTEGER NOT NULL,
            nome TEXT,
            cbo TEXT,
            funcao TEXT,               -- ✅ fonte da “função” no PTS
            created_at TEXT NOT NULL,
            FOREIGN KEY (pts_id) REFERENCES pts(id) ON DELETE CASCADE
        )
    """)

    # migração leve (se tabela antiga não tiver funcao)
    try:
        cur.execute("PRAGMA table_info(pts_participantes)")
        cols = {r[1] for r in cur.fetchall()}
        if "funcao" not in cols:
            cur.execute("ALTER TABLE pts_participantes ADD COLUMN funcao TEXT")
    except Exception:
        pass

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_pts_part_pts
        ON pts_participantes (pts_id)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_pts_part_usuario
        ON pts_participantes (usuario_id)
    """)

    conn.commit()


# ============================================================
# FETCHERS
# ============================================================

def _fetch_paciente_full(conn, paciente_id: str | int):
    if not has_table(conn, "pacientes"):
        return None

    pid = str(paciente_id).strip()
    if not pid:
        return None

    cols = _table_columns(conn, "pacientes")

    def pick(col: str, fallback_sql: str = "''"):
        return col if col in cols else f"{fallback_sql} AS {col}"

    sel = [
        "id",
        pick("nome"),
        pick("nascimento"),
        pick("cpf"),
        pick("cns"),
        pick("prontuario"),
        pick("mod"),
        pick("status"),
        pick("cid"),
        pick("telefone"),
        pick("sexo"),
    ]

    cur = conn.cursor()
    cur.execute(f"SELECT {', '.join(sel)} FROM pacientes WHERE id = ? LIMIT 1", (pid,))
    r = cur.fetchone()
    if not r:
        return None

    return {
        "id": r[0],
        "nome": r[1] or "",
        "nascimento": r[2] or "",
        "cpf": r[3] or "",
        "cns": r[4] or "",
        "prontuario": r[5] or "",
        "mod": r[6] or "",
        "status": r[7] or "",
        "cid": r[8] or "",
        "telefone": r[9] or "",
        "sexo": r[10] or "",
    }


def _fetch_pts_by_id(conn, pts_id: int) -> dict | None:
    ensure_pts_schema(conn)
    cur = conn.cursor()
    cur.execute("""
        SELECT
            id, paciente_id, data_pts,
            COALESCE(objetivo_geral,''), COALESCE(avaliacao,''),
            COALESCE(plano,''), COALESCE(observacoes,''),
            COALESCE(created_by, NULL), COALESCE(created_at,''), COALESCE(updated_at,'')
        FROM pts
        WHERE id = ?
        LIMIT 1
    """, (int(pts_id),))
    r = cur.fetchone()
    if not r:
        return None

    return {
        "id": int(r[0]),
        "paciente_id": int(r[1]),
        "data_pts": r[2] or "",
        "data": r[2] or "",
        "competencia": (r[2] or "")[:7],
        "status": "",
        "objetivo_geral": r[3] or "",
        "avaliacao": r[4] or "",
        "plano": r[5] or "",
        "observacoes": r[6] or "",
        "created_by": r[7],
        "created_at": r[8] or "",
        "updated_at": r[9] or "",
    }


def _fetch_participantes(conn, pts_id: int) -> list[dict]:
    ensure_pts_schema(conn)
    cur = conn.cursor()
    cur.execute("""
        SELECT
            usuario_id,
            COALESCE(nome,'')   AS nome,
            COALESCE(cbo,'')    AS cbo,
            COALESCE(funcao,'') AS funcao
        FROM pts_participantes
        WHERE pts_id = ?
        ORDER BY nome COLLATE NOCASE
    """, (int(pts_id),))
    rows = cur.fetchall()
    return [
        {
            "usuario_id": int(r[0]),
            "nome": r[1] or "",
            "cbo": r[2] or "",
            "funcao": r[3] or "",
        }
        for r in rows
    ]


# ============================================================
# LISTAGEM · filtros + paginação (20 por página)
# ============================================================

def _safe_page(v, default=1) -> int:
    try:
        p = int(v)
        return p if p > 0 else default
    except Exception:
        return default


def _like(s: str) -> str:
    return f"%{(s or '').strip().lower()}%"


def _build_pts_where_and_params(q_paciente: str, q_prof: str, q_cbo: str, competencia: str):
    where = []
    params = []

    if q_paciente.strip():
        where.append("LOWER(COALESCE(p.nome,'')) LIKE ?")
        params.append(_like(q_paciente))

    comp = competencia.strip()
    if comp:
        where.append("substr(COALESCE(t.data_pts,''), 1, 7) = ?")
        params.append(comp)

    if q_prof.strip():
        where.append("""
            EXISTS (
                SELECT 1
                  FROM pts_participantes pp
                 WHERE pp.pts_id = t.id
                   AND LOWER(COALESCE(pp.nome,'')) LIKE ?
            )
        """)
        params.append(_like(q_prof))

    if q_cbo.strip():
        where.append("""
            EXISTS (
                SELECT 1
                  FROM pts_participantes pp2
                 WHERE pp2.pts_id = t.id
                   AND LOWER(COALESCE(pp2.cbo,'')) LIKE ?
            )
        """)
        params.append(_like(q_cbo))

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    return where_sql, params


# ============================================================
# PÁGINAS · RENDER
# ============================================================

@pts_bp.get("/")
def pts_page():
    paciente_id = (request.args.get("paciente_id") or "").strip()
    return render_template(
        "pts.html",
        data_hoje=date.today().isoformat(),
        paciente_id=paciente_id,
    )


# ✅ NOVO: salva via POST normal do form (sem fetch)

@pts_bp.post("/")
def pts_page_post():
    """
    Recebe o submit do form (pts.html), salva no SQLite e
    redireciona para /pts/visualizar/<pts_id>.
    """
    conn = conectar_db()
    try:
        ensure_pts_schema(conn)

        paciente_id = (request.form.get("paciente_id") or "").strip()
        if not paciente_id:
            flash("Selecione um paciente na lista (preciso do ID).", "error")
            return redirect(url_for("pts.pts_page"))

        # Campos do PTS (você pode mapear melhor depois)
        objetivo_geral = (request.form.get("objetivo_geral") or "").strip()
        avaliacao      = (
            (request.form.get("diagnostico_funcional") or "").strip()
        )
        plano          = (
            (request.form.get("encaminhamentos") or "").strip()
        )
        observacoes    = (
            (request.form.get("outras_observacoes") or "").strip()
        )

        # Participantes (modo chips): "1,2,3"
        participantes_ids = (request.form.get("participantes_ids") or "").strip()
        ids = []
        if participantes_ids:
            for x in participantes_ids.split(","):
                x = x.strip()
                if x.isdigit():
                    ids.append(int(x))

        created_by = _resolve_logged_usuario_id(conn)
        now = datetime.now().isoformat()

        cur = conn.cursor()
        cur.execute("""
            INSERT INTO pts (
                paciente_id, data_pts,
                objetivo_geral, avaliacao, plano, observacoes,
                created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            int(paciente_id),
            date.today().isoformat(),
            objetivo_geral,
            avaliacao,
            plano,
            observacoes,
            int(created_by) if created_by else None,
            now,
            now,
        ))
        pts_id = int(cur.lastrowid)

        # grava participantes (puxa de usuarios)
        if ids and has_table(conn, "usuarios"):
            has_nome = has_column(conn, "usuarios", "nome")
            has_cbo  = has_column(conn, "usuarios", "cbo")

            for uid in ids:
                cur.execute(f"""
                    SELECT
                      {("COALESCE(nome,'')" if has_nome else "''")} AS nome,
                      {("COALESCE(cbo,'')"  if has_cbo  else "''")} AS cbo
                    FROM usuarios
                    WHERE id = ?
                    LIMIT 1
                """, (uid,))
                ur = cur.fetchone()
                if not ur:
                    continue

                nome_u = (ur[0] or "").strip()
                cbo_u  = (ur[1] or "").strip()
                func_u = _funcao_from_cbo(cbo_u)

                cur.execute("""
                    INSERT INTO pts_participantes (pts_id, usuario_id, nome, cbo, funcao, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (pts_id, uid, nome_u, cbo_u, func_u, now))

        conn.commit()

        flash("PTS salvo com sucesso!", "success")
        return redirect(url_for("pts.pts_visualizar_item", pts_id=pts_id))

    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        flash(f"Erro ao salvar PTS: {e}", "error")
        return redirect(url_for("pts.pts_page"))

    finally:
        try:
            conn.close()
        except Exception:
            pass


@pts_bp.get("/visualizar")
def pts_visualizar():
    conn = conectar_db()
    try:
        ensure_pts_schema(conn)

        q_paciente  = (request.args.get("paciente") or "").strip()
        q_prof      = (request.args.get("prof") or "").strip()
        q_cbo       = (request.args.get("cbo") or "").strip()
        competencia = (request.args.get("competencia") or "").strip()
        page        = _safe_page(request.args.get("page"), 1)

        per_page = 20
        offset = (page - 1) * per_page

        where_sql, params = _build_pts_where_and_params(q_paciente, q_prof, q_cbo, competencia)
        cur = conn.cursor()

        sql_count = f"""
            SELECT COUNT(1)
              FROM pts t
              LEFT JOIN pacientes p ON p.id = t.paciente_id
              {where_sql}
        """
        cur.execute(sql_count, params)
        total = int(cur.fetchone()[0] or 0)

        sql_list = f"""
            SELECT
                t.id,
                t.paciente_id,
                COALESCE(t.data_pts,'') AS data_pts,
                substr(COALESCE(t.data_pts,''), 1, 7) AS competencia,
                COALESCE(p.nome,'') AS paciente_nome,
                COALESCE(p.prontuario,'') AS prontuario,
                COALESCE(p.cid,'') AS cid,
                (
                  SELECT group_concat(
                           TRIM(COALESCE(pp.nome,'')) ||
                           CASE
                             WHEN COALESCE(pp.funcao,'')<>'' THEN ' · '||pp.funcao
                             WHEN COALESCE(pp.cbo,'')<>'' THEN ' (CBO '||pp.cbo||')'
                             ELSE ''
                           END,
                           ' · '
                         )
                    FROM pts_participantes pp
                   WHERE pp.pts_id = t.id
                ) AS equipe
              FROM pts t
              LEFT JOIN pacientes p ON p.id = t.paciente_id
              {where_sql}
             ORDER BY
                CASE
                  WHEN t.data_pts GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' THEN t.data_pts
                  ELSE '0000-00-00'
                END DESC,
                t.id DESC
             LIMIT ? OFFSET ?
        """
        cur.execute(sql_list, params + [per_page, offset])
        rows = cur.fetchall()

        itens = [dict(
            id=r[0],
            paciente_id=r[1],
            data_pts=r[2],
            competencia=r[3],
            paciente_nome=r[4],
            prontuario=r[5],
            cid=r[6],
            equipe=r[7] or "",
        ) for r in rows]

        pages = max(1, (total + per_page - 1) // per_page)
        pager = dict(
            page=page,
            per_page=per_page,
            total=total,
            pages=pages,
            has_prev=page > 1,
            has_next=page < pages,
            prev_page=page - 1,
            next_page=page + 1,
        )

        filtros = dict(paciente=q_paciente, prof=q_prof, cbo=q_cbo, competencia=competencia)

        return render_template(
            "pts_visualizar.html",
            data_hoje=date.today().isoformat(),
            modo="lista",
            itens=itens,
            pager=pager,
            filtros=filtros,
            paciente=None,
            pts=None,
            equipe=[],
            paciente_id="",
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass


@pts_bp.get("/visualizar/<int:pts_id>")
def pts_visualizar_item(pts_id: int):
    conn = conectar_db()
    try:
        ensure_pts_schema(conn)

        pts = _fetch_pts_by_id(conn, pts_id)
        if not pts:
            raise NotFound("PTS não encontrado.")

        paciente = _fetch_paciente_full(conn, pts["paciente_id"])
        participantes = _fetch_participantes(conn, pts_id)

        pts_view = dict(pts)
        pts_view["resumo"] = pts_view.get("avaliacao", "")

        return render_template(
            "pts_visualizar.html",
            data_hoje=date.today().isoformat(),
            modo="detalhe",
            paciente=paciente,
            pts=pts_view,
            equipe=[{
                "nome": p.get("nome",""),
                "cbo": p.get("cbo",""),
                "funcao": p.get("funcao",""),
            } for p in participantes],
            itens=[],
            filtros=None,
            pager=None,
            paciente_id=str(pts["paciente_id"]),
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ============================================================
# API · PROFISSIONAIS (autocomplete + catálogo)
# ============================================================

@pts_bp.get("/api/profissionais")
def api_pts_profissionais():
    """
    - q=texto (3+ chars) filtra
    - all=1 retorna catálogo (até 500)
    Retorna: id, nome, cbo, funcao, label
    """
    q = (request.args.get("q") or "").strip()
    all_mode = (request.args.get("all") or "").strip() == "1"

    # ✅ a partir do 3º caractere
    if not all_mode and len(q) < 3:
        return jsonify(ok=True, items=[])

    conn = conectar_db()
    cur = conn.cursor()

    try:
        if not has_table(conn, "usuarios") or not has_column(conn, "usuarios", "nome"):
            return jsonify(ok=True, items=[])

        has_cbo    = has_column(conn, "usuarios", "cbo")
        has_active = has_column(conn, "usuarios", "is_active")
        has_role   = has_column(conn, "usuarios", "role")

        conds = []
        params = []

        if all_mode:
            conds.append("TRIM(COALESCE(nome,'')) <> ''")
        else:
            conds.append("LOWER(TRIM(COALESCE(nome,''))) LIKE ?")
            params.append(f"%{q.lower()}%")

        # ✅ role pode estar diferente no teu BD (ADMIN/RECEPCAO etc).
        # Então: se tiver role, filtra somente se você quiser MESMO.
        # Recomendo: permitir todos ativos e com nome, e depois você restringe.
        # Se quiser restringir, use IN ('PROFISSIONAL','PROFISSIONAIS').
        # (Vou deixar seguro: aceita PROFESSIONAL/PROFISSIONAIS, mas se não houver nenhum, ainda retorna pelos ativos.)
        role_filter = False
        if has_role:
            # tenta filtrar, mas sem matar tudo
            role_filter = True
            conds.append("UPPER(COALESCE(role,'')) IN ('PROFISSIONAL','PROFISSIONAIS')")

        if has_active:
            conds.append("(is_active = 1 OR is_active IS NULL)")

        sql = f"""
            SELECT
                id,
                TRIM(COALESCE(nome,'')) AS nome,
                {("TRIM(COALESCE(cbo,'')) AS cbo" if has_cbo else "'' AS cbo")}
            FROM usuarios
            WHERE {" AND ".join(conds)}
            ORDER BY nome COLLATE NOCASE
            LIMIT {500 if all_mode else 50}
        """
        cur.execute(sql, params)
        rows = cur.fetchall()

        # ✅ fallback automático: se role_filter matou tudo, tenta sem role
        if role_filter and not rows:
            conds2 = []
            params2 = []
            if all_mode:
                conds2.append("TRIM(COALESCE(nome,'')) <> ''")
            else:
                conds2.append("LOWER(TRIM(COALESCE(nome,''))) LIKE ?")
                params2.append(f"%{q.lower()}%")
            if has_active:
                conds2.append("(is_active = 1 OR is_active IS NULL)")

            sql2 = f"""
                SELECT
                    id,
                    TRIM(COALESCE(nome,'')) AS nome,
                    {("TRIM(COALESCE(cbo,'')) AS cbo" if has_cbo else "'' AS cbo")}
                FROM usuarios
                WHERE {" AND ".join(conds2)}
                ORDER BY nome COLLATE NOCASE
                LIMIT {500 if all_mode else 50}
            """
            cur.execute(sql2, params2)
            rows = cur.fetchall()

        items = []
        for uid, nome, cbo in rows:
            nome = (nome or "").strip()
            if not nome:
                continue
            cbo = (cbo or "").strip()
            funcao = _funcao_from_cbo(cbo)

            extra = []
            if funcao:
                extra.append(funcao)
            if cbo:
                extra.append(f"CBO {cbo}")
            label = f"{nome} · " + " · ".join(extra) if extra else nome

            items.append({
                "id": int(uid),
                "nome": nome,
                "cbo": cbo,
                "funcao": funcao,
                "label": label,
            })

        return jsonify(ok=True, items=items)

    finally:
        try:
            conn.close()
        except Exception:
            pass


# ============================================================
# API · DADOS (paciente + último PTS + equipe)
# ============================================================

@pts_bp.get("/api/dados")
def api_pts_dados():
    paciente_id = (request.args.get("paciente_id") or "").strip()
    if not paciente_id:
        return jsonify(ok=False, error="paciente_id é obrigatório."), 400

    conn = conectar_db()
    try:
        ensure_pts_schema(conn)

        paciente = _fetch_paciente_full(conn, paciente_id)
        if not paciente:
            return jsonify(ok=False, error="Paciente não encontrado."), 404

        cur = conn.cursor()
        cur.execute("""
            SELECT id, data_pts,
                   COALESCE(objetivo_geral,''), COALESCE(avaliacao,''),
                   COALESCE(plano,''), COALESCE(observacoes,'')
              FROM pts
             WHERE paciente_id = ?
             ORDER BY
               CASE
                 WHEN data_pts GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' THEN data_pts
                 ELSE '0000-00-00'
               END DESC,
               id DESC
             LIMIT 1
        """, (str(paciente_id),))
        r = cur.fetchone()

        pts = None
        participantes = []

        if r:
            pts_id = int(r[0])
            pts = {
                "id": pts_id,
                "data_pts": r[1],
                "data": r[1],
                "competencia": (r[1] or "")[:7],
                "objetivo_geral": r[2],
                "avaliacao": r[3],
                "plano": r[4],
                "observacoes": r[5],
                "status": "",
                "resumo": r[3],
            }
            participantes = _fetch_participantes(conn, pts_id)

        return jsonify(ok=True, paciente=paciente, pts=pts, participantes=participantes)

    finally:
        try:
            conn.close()
        except Exception:
            pass


# ============================================================
# API · SALVAR (novo PTS + participantes) — JSON
# ============================================================

@pts_bp.post("/api/salvar")
def api_pts_salvar():
    data = request.get_json(force=True, silent=True) or {}

    paciente_id = str(data.get("paciente_id") or "").strip()
    data_pts = (data.get("data_pts") or date.today().isoformat()).strip()

    if not paciente_id:
        return jsonify(ok=False, error="paciente_id é obrigatório."), 400

    participantes = data.get("participantes") or []
    if isinstance(participantes, str):
        participantes = [p.strip() for p in participantes.split(",") if p.strip()]

    norm_ids: list[int] = []
    seen = set()
    for x in participantes:
        try:
            i = int(x)
            if i not in seen:
                seen.add(i)
                norm_ids.append(i)
        except Exception:
            pass

    conn = conectar_db()
    try:
        ensure_pts_schema(conn)

        pac = _fetch_paciente_full(conn, paciente_id)
        if not pac:
            return jsonify(ok=False, error="Paciente não encontrado."), 404

        created_by = _resolve_logged_usuario_id(conn)
        now = datetime.now().isoformat()

        cur = conn.cursor()

        cur.execute("""
            INSERT INTO pts (
                paciente_id, data_pts,
                objetivo_geral, avaliacao, plano, observacoes,
                created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            int(paciente_id), data_pts,
            (data.get("objetivo_geral") or ""),
            (data.get("avaliacao") or ""),
            (data.get("plano") or ""),
            (data.get("observacoes") or ""),
            int(created_by) if created_by else None,
            now, now
        ))
        pts_id = int(cur.lastrowid)

        if norm_ids and has_table(conn, "usuarios"):
            has_nome = has_column(conn, "usuarios", "nome")
            has_cbo = has_column(conn, "usuarios", "cbo")

            for uid in norm_ids:
                cur.execute(f"""
                    SELECT
                      {("COALESCE(nome,'')" if has_nome else "''")} AS nome,
                      {("COALESCE(cbo,'')"  if has_cbo  else "''")} AS cbo
                    FROM usuarios
                    WHERE id = ?
                    LIMIT 1
                """, (int(uid),))
                ur = cur.fetchone()
                if not ur:
                    continue

                nome_u = (ur[0] or "").strip()
                cbo_u = (ur[1] or "").strip()
                funcao_u = _funcao_from_cbo(cbo_u)

                cur.execute("""
                    INSERT INTO pts_participantes (pts_id, usuario_id, nome, cbo, funcao, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (pts_id, int(uid), nome_u, cbo_u, funcao_u, now))

        conn.commit()
        return jsonify(ok=True, pts_id=pts_id)

    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return jsonify(ok=False, error=str(e)), 500

    finally:
        try:
            conn.close()
        except Exception:
            pass


# ============================================================
# EXPORT · EXCEL
# ============================================================

@pts_bp.get("/export/excel/<int:pts_id>")
def export_pts_excel(pts_id: int):
    conn = conectar_db()
    try:
        ensure_pts_schema(conn)

        pts = _fetch_pts_by_id(conn, pts_id)
        if not pts:
            abort(404, "PTS não encontrado.")

        paciente = _fetch_paciente_full(conn, pts["paciente_id"])
        participantes = _fetch_participantes(conn, pts_id)

        wb = Workbook()
        ws = wb.active
        ws.title = "PTS"

        ws.append(["PTS", f"#{pts['id']}"])
        ws.append(["Data", pts.get("data_pts", "")])
        ws.append(["Competência", pts.get("competencia", "")])
        ws.append([])

        ws.append(["Paciente", (paciente or {}).get("nome", "")])
        ws.append(["Prontuário", (paciente or {}).get("prontuario", "")])
        ws.append(["CPF", (paciente or {}).get("cpf", "")])
        ws.append(["CID", (paciente or {}).get("cid", "")])
        ws.append([])

        ws.append(["Objetivo geral", pts.get("objetivo_geral", "")])
        ws.append(["Avaliação", pts.get("avaliacao", "")])
        ws.append(["Plano", pts.get("plano", "")])
        ws.append(["Observações", pts.get("observacoes", "")])
        ws.append([])

        ws.append(["Participantes"])
        ws.append(["Nome", "CBO", "Função"])
        for p in participantes:
            ws.append([p.get("nome", ""), p.get("cbo", ""), p.get("funcao", "")])

        bio = io.BytesIO()
        wb.save(bio)
        bio.seek(0)

        filename = f"PTS_{pts_id}.xlsx"
        return send_file(
            bio,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ============================================================
# EXPORT · PDF
# ============================================================

@pts_bp.get("/export/pdf/<int:pts_id>")
def export_pts_pdf(pts_id: int):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ModuleNotFoundError:
        return (
            "Exportação PDF indisponível: instale reportlab com `pip install reportlab`.",
            501,
        )

    conn = conectar_db()
    try:
        ensure_pts_schema(conn)

        pts = _fetch_pts_by_id(conn, pts_id)
        if not pts:
            abort(404, "PTS não encontrado.")

        paciente = _fetch_paciente_full(conn, pts["paciente_id"])
        participantes = _fetch_participantes(conn, pts_id)

        bio = io.BytesIO()
        c = canvas.Canvas(bio, pagesize=A4)
        w, h = A4

        def line(y, text, size=11, bold=False):
            c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
            c.drawString(40, y, text)

        y = h - 50
        line(y, f"PTS #{pts_id}", 16, True); y -= 22
        line(y, f"Data: {pts.get('data_pts','')}", 11); y -= 14
        line(y, f"Competência: {pts.get('competencia','')}", 11); y -= 18

        line(y, "Paciente", 13, True); y -= 18
        if paciente:
            line(y, f"Nome: {paciente.get('nome','')}", 11); y -= 14
            line(y, f"Prontuário: {paciente.get('prontuario','')}", 11); y -= 14
            line(y, f"CPF: {paciente.get('cpf','')}", 11); y -= 14
            line(y, f"CID: {paciente.get('cid','')}", 11); y -= 18
        else:
            line(y, "Paciente não encontrado", 11); y -= 18

        line(y, "Participantes", 13, True); y -= 18
        if participantes:
            for p in participantes[:30]:
                nome = p.get("nome","")
                cbo = p.get("cbo","")
                func = p.get("funcao","")
                extra = f" · {func}" if func else (f" · CBO {cbo}" if cbo else "")
                line(y, f"- {nome}{extra}", 11); y -= 14
                if y < 60:
                    c.showPage()
                    y = h - 50
        else:
            line(y, "- (sem participantes)", 11); y -= 14

        c.showPage()
        c.save()

        bio.seek(0)
        filename = f"PTS_{pts_id}.pdf"
        return send_file(
            bio,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
        )

    finally:
        try:
            conn.close()
        except Exception:
            pass
