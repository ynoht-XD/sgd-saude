# sgd/pts/routes.py
from __future__ import annotations

from datetime import date, datetime

from flask import (
    request, jsonify, render_template, redirect,
    url_for, flash
)
from werkzeug.exceptions import NotFound

from . import pts_bp
from db import conectar_db

from admin.modulos import require_permission

from .helpers import (
    _val,
    _only_digits,
    _safe_page,
    ensure_pts_schema,
    require_clinica_id,
    resolve_logged_usuario_id,
    registrar_log,
    has_table,
    has_column,
    table_columns,
    buscar_nome_ocupacao,
    cbo_label,
    fetch_paciente_full,
    fetch_pts_by_id,
    fetch_participantes,
    insert_pts_participantes,
    build_pts_where_and_params,
)

from .pts_export import (
    export_pts_excel_service,
    export_pts_pdf_service,
)


# ============================================================
# PÁGINA · NOVO PTS
# ============================================================

@pts_bp.get("/")
@require_permission("pts", "ver")
def pts_page():
    paciente_id = (request.args.get("paciente_id") or "").strip()

    return render_template(
        "pts.html",
        data_hoje=date.today().isoformat(),
        paciente_id=paciente_id,
    )


@pts_bp.post("/")
@require_permission("pts", "editar")
def pts_page_post():
    conn = conectar_db()

    try:
        ensure_pts_schema(conn)
        clinica_id = require_clinica_id()

        paciente_id = (request.form.get("paciente_id") or "").strip()

        if not paciente_id:
            flash("Selecione um paciente na lista.", "error")
            return redirect(url_for("pts.pts_page"))

        paciente = fetch_paciente_full(conn, paciente_id, clinica_id)
        if not paciente:
            flash("Paciente não encontrado para esta clínica.", "error")
            return redirect(url_for("pts.pts_page"))

        objetivo_geral = (request.form.get("objetivo_geral") or "").strip()
        avaliacao = (request.form.get("diagnostico_funcional") or "").strip()
        plano = (request.form.get("encaminhamentos") or "").strip()
        observacoes = (request.form.get("outras_observacoes") or "").strip()

        participantes_ids = (request.form.get("participantes_ids") or "").strip()
        ids = []

        if participantes_ids:
            for x in participantes_ids.split(","):
                x = x.strip()
                if x.isdigit():
                    ids.append(int(x))

        created_by = resolve_logged_usuario_id(conn)
        now = datetime.now()

        cur = conn.cursor()
        cur.execute("""
            INSERT INTO pts (
                clinica_id,
                paciente_id,
                data_pts,
                objetivo_geral,
                avaliacao,
                plano,
                observacoes,
                created_by,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            int(clinica_id),
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

        pts_id = int(_val(cur.fetchone(), "id", 0))

        insert_pts_participantes(
            conn=conn,
            pts_id=pts_id,
            ids=ids,
            clinica_id=clinica_id,
            now=now,
        )

        registrar_log(
            conn,
            acao="CRIAR_PTS_FORM",
            modulo="pts",
            referencia_id=pts_id,
            detalhes=f"PTS criado via formulário para paciente_id={paciente_id}",
        )

        conn.commit()

        flash("PTS salvo com sucesso!", "success")
        return redirect(url_for("pts.pts_visualizar_item", pts_id=pts_id))

    except PermissionError as e:
        try:
            conn.rollback()
        except Exception:
            pass

        flash(str(e), "error")
        return redirect(url_for("pts.pts_page"))

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


# ============================================================
# PÁGINA · LISTAGEM
# ============================================================

@pts_bp.get("/visualizar")
@require_permission("pts", "ver")
def pts_visualizar():
    conn = conectar_db()

    try:
        ensure_pts_schema(conn)
        clinica_id = require_clinica_id()

        q_paciente = (request.args.get("paciente") or "").strip()
        q_prof = (request.args.get("prof") or "").strip()
        q_cbo = (request.args.get("cbo") or "").strip()
        competencia = (request.args.get("competencia") or "").strip()
        page = _safe_page(request.args.get("page"), 1)

        per_page = 20
        offset = (page - 1) * per_page

        where_sql, params = build_pts_where_and_params(
            q_paciente=q_paciente,
            q_prof=q_prof,
            q_cbo=q_cbo,
            competencia=competencia,
            clinica_id=clinica_id,
        )

        pac_cols = table_columns(conn, "pacientes") if has_table(conn, "pacientes") else set()
        pac_has_clinica = "clinica_id" in pac_cols

        join_paciente = """
            LEFT JOIN pacientes p
                   ON p.id = t.paciente_id
        """

        if pac_has_clinica:
            join_paciente = """
                LEFT JOIN pacientes p
                       ON p.id = t.paciente_id
                      AND p.clinica_id = t.clinica_id
            """

        cur = conn.cursor()

        cur.execute(
            f"""
            SELECT COUNT(1)
              FROM pts t
              {join_paciente}
              {where_sql}
            """,
            params,
        )

        total = int(_val(cur.fetchone(), "count", 0, 0) or 0)

        cur.execute(
            f"""
            SELECT
                t.id,
                t.paciente_id,
                COALESCE(t.data_pts::text, '') AS data_pts,
                TO_CHAR(t.data_pts, 'YYYY-MM') AS competencia,
                COALESCE(p.nome, '') AS paciente_nome,
                COALESCE(p.prontuario, '') AS prontuario,
                COALESCE(p.cid, '') AS cid,
                (
                  SELECT STRING_AGG(
                           TRIM(COALESCE(pp.nome, '')) ||
                           CASE
                             WHEN COALESCE(pp.funcao, '') <> '' THEN ' · ' || pp.funcao
                             WHEN COALESCE(pp.cbo, '') <> '' THEN ' · CBO ' || pp.cbo
                             ELSE ''
                           END,
                           ' · '
                           ORDER BY pp.nome
                         )
                    FROM pts_participantes pp
                   WHERE pp.pts_id = t.id
                     AND pp.clinica_id = t.clinica_id
                ) AS equipe
              FROM pts t
              {join_paciente}
              {where_sql}
             ORDER BY t.data_pts DESC NULLS LAST, t.id DESC
             LIMIT %s OFFSET %s
            """,
            params + [per_page, offset],
        )

        rows = cur.fetchall() or []

        itens = [
            {
                "id": _val(r, "id", 0),
                "paciente_id": _val(r, "paciente_id", 1),
                "data_pts": _val(r, "data_pts", 2, ""),
                "competencia": _val(r, "competencia", 3, ""),
                "paciente_nome": _val(r, "paciente_nome", 4, ""),
                "prontuario": _val(r, "prontuario", 5, ""),
                "cid": _val(r, "cid", 6, ""),
                "equipe": _val(r, "equipe", 7, "") or "",
            }
            for r in rows
        ]

        pages = max(1, (total + per_page - 1) // per_page)

        pager = {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": pages,
            "has_prev": page > 1,
            "has_next": page < pages,
            "prev_page": page - 1,
            "next_page": page + 1,
        }

        filtros = {
            "paciente": q_paciente,
            "prof": q_prof,
            "cbo": q_cbo,
            "competencia": competencia,
        }

        registrar_log(
            conn,
            acao="LISTAR_PTS",
            modulo="pts",
            referencia_id=None,
            detalhes=f"Filtros: paciente={q_paciente}; prof={q_prof}; cbo={q_cbo}; competencia={competencia}",
        )

        conn.commit()

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

    except PermissionError as e:
        flash(str(e), "error")
        return redirect(url_for("index"))

    finally:
        try:
            conn.close()
        except Exception:
            pass


# ============================================================
# PÁGINA · DETALHE
# ============================================================

@pts_bp.get("/visualizar/<int:pts_id>")
@require_permission("pts", "ver")
def pts_visualizar_item(pts_id: int):
    conn = conectar_db()

    try:
        ensure_pts_schema(conn)
        clinica_id = require_clinica_id()

        pts = fetch_pts_by_id(conn, pts_id, clinica_id)
        if not pts:
            raise NotFound("PTS não encontrado.")

        paciente = fetch_paciente_full(conn, pts["paciente_id"], clinica_id)
        participantes = fetch_participantes(conn, pts_id, clinica_id)

        pts_view = dict(pts)
        pts_view["resumo"] = pts_view.get("avaliacao", "")

        registrar_log(
            conn,
            acao="VISUALIZAR_PTS",
            modulo="pts",
            referencia_id=pts_id,
            detalhes=f"Visualização do PTS #{pts_id}",
        )

        conn.commit()

        return render_template(
            "pts_visualizar.html",
            data_hoje=date.today().isoformat(),
            modo="detalhe",
            paciente=paciente,
            pts=pts_view,
            equipe=[
                {
                    "nome": p.get("nome", ""),
                    "cbo": p.get("cbo", ""),
                    "funcao": p.get("ocupacao") or p.get("funcao", ""),
                    "ocupacao": p.get("ocupacao", ""),
                }
                for p in participantes
            ],
            itens=[],
            filtros=None,
            pager=None,
            paciente_id=str(pts["paciente_id"]),
        )

    except PermissionError as e:
        flash(str(e), "error")
        return redirect(url_for("pts.pts_visualizar"))

    finally:
        try:
            conn.close()
        except Exception:
            pass


# ============================================================
# API · PROFISSIONAIS
# ============================================================

@pts_bp.get("/api/profissionais")
@require_permission("pts", "ver")
def api_pts_profissionais():
    q = (request.args.get("q") or "").strip()
    all_mode = (request.args.get("all") or "").strip() == "1"

    if not all_mode and len(q) < 3:
        return jsonify(ok=True, items=[])

    conn = conectar_db()

    try:
        clinica_id = require_clinica_id()

        if not has_table(conn, "usuarios") or not has_column(conn, "usuarios", "nome"):
            return jsonify(ok=True, items=[])

        cols = table_columns(conn, "usuarios")

        has_cbo = "cbo" in cols
        has_active = "is_active" in cols
        has_role = "role" in cols
        has_clinica = "clinica_id" in cols

        cbo_expr = "TRIM(COALESCE(cbo::text, '')) AS cbo" if has_cbo else "'' AS cbo"

        conds = ["TRIM(COALESCE(nome, '')) <> ''"]
        params = []

        if not all_mode:
            conds.append("(nome ILIKE %s OR COALESCE(cbo::text, '') ILIKE %s)")
            params.extend([f"%{q}%", f"%{_only_digits(q)}%"])

        role_filter = False
        if has_role:
            role_filter = True
            conds.append("UPPER(COALESCE(role, '')) IN ('PROFISSIONAL', 'PROFISSIONAIS')")

        if has_active:
            conds.append("(is_active IS TRUE OR is_active IS NULL)")

        if has_clinica:
            conds.append("(clinica_id = %s OR clinica_id IS NULL)")
            params.append(int(clinica_id))

        sql = f"""
            SELECT id, TRIM(COALESCE(nome, '')) AS nome, {cbo_expr}
              FROM usuarios
             WHERE {" AND ".join(conds)}
             ORDER BY nome ASC
             LIMIT {500 if all_mode else 50}
        """

        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall() or []

        if role_filter and not rows:
            conds2 = ["TRIM(COALESCE(nome, '')) <> ''"]
            params2 = []

            if not all_mode:
                conds2.append("(nome ILIKE %s OR COALESCE(cbo::text, '') ILIKE %s)")
                params2.extend([f"%{q}%", f"%{_only_digits(q)}%"])

            if has_active:
                conds2.append("(is_active IS TRUE OR is_active IS NULL)")

            if has_clinica:
                conds2.append("(clinica_id = %s OR clinica_id IS NULL)")
                params2.append(int(clinica_id))

            cur.execute(
                f"""
                SELECT id, TRIM(COALESCE(nome, '')) AS nome, {cbo_expr}
                  FROM usuarios
                 WHERE {" AND ".join(conds2)}
                 ORDER BY nome ASC
                 LIMIT {500 if all_mode else 50}
                """,
                params2,
            )
            rows = cur.fetchall() or []

        items = []

        for r in rows:
            uid = _val(r, "id", 0)
            nome = (_val(r, "nome", 1, "") or "").strip()
            cbo = (_val(r, "cbo", 2, "") or "").strip()

            if not nome:
                continue

            ocupacao = buscar_nome_ocupacao(conn, cbo)
            label_cbo = cbo_label(conn, cbo)

            label = nome
            if label_cbo:
                label = f"{nome} · {label_cbo}"

            items.append({
                "id": int(uid or 0),
                "nome": nome,
                "cbo": cbo,
                "funcao": ocupacao,
                "ocupacao": ocupacao,
                "label": label,
            })

        return jsonify(ok=True, items=items)

    except PermissionError as e:
        return jsonify(ok=False, error=str(e)), 403

    finally:
        try:
            conn.close()
        except Exception:
            pass


# ============================================================
# API · DADOS DO PACIENTE + ÚLTIMO PTS
# ============================================================

@pts_bp.get("/api/dados")
@require_permission("pts", "ver")
def api_pts_dados():
    paciente_id = (request.args.get("paciente_id") or "").strip()

    if not paciente_id:
        return jsonify(ok=False, error="paciente_id é obrigatório."), 400

    conn = conectar_db()

    try:
        ensure_pts_schema(conn)
        clinica_id = require_clinica_id()

        paciente = fetch_paciente_full(conn, paciente_id, clinica_id)
        if not paciente:
            return jsonify(ok=False, error="Paciente não encontrado."), 404

        cur = conn.cursor()
        cur.execute("""
            SELECT
                id,
                COALESCE(data_pts::text, '') AS data_pts,
                COALESCE(objetivo_geral, '') AS objetivo_geral,
                COALESCE(avaliacao, '') AS avaliacao,
                COALESCE(plano, '') AS plano,
                COALESCE(observacoes, '') AS observacoes
              FROM pts
             WHERE paciente_id = %s
               AND clinica_id = %s
             ORDER BY data_pts DESC NULLS LAST, id DESC
             LIMIT 1
        """, (
            int(paciente_id),
            int(clinica_id),
        ))

        r = cur.fetchone()

        pts = None
        participantes = []

        if r:
            pts_id = int(_val(r, "id", 0))
            data_pts_val = _val(r, "data_pts", 1, "") or ""

            pts = {
                "id": pts_id,
                "data_pts": data_pts_val,
                "data": data_pts_val,
                "competencia": data_pts_val[:7],
                "objetivo_geral": _val(r, "objetivo_geral", 2, "") or "",
                "avaliacao": _val(r, "avaliacao", 3, "") or "",
                "plano": _val(r, "plano", 4, "") or "",
                "observacoes": _val(r, "observacoes", 5, "") or "",
                "status": "",
                "resumo": _val(r, "avaliacao", 3, "") or "",
            }

            participantes = fetch_participantes(conn, pts_id, clinica_id)

        return jsonify(
            ok=True,
            paciente=paciente,
            pts=pts,
            participantes=participantes,
        )

    except PermissionError as e:
        return jsonify(ok=False, error=str(e)), 403

    finally:
        try:
            conn.close()
        except Exception:
            pass


# ============================================================
# API · SALVAR PTS
# ============================================================

@pts_bp.post("/api/salvar")
@require_permission("pts", "editar")
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
        clinica_id = require_clinica_id()

        paciente = fetch_paciente_full(conn, paciente_id, clinica_id)
        if not paciente:
            return jsonify(ok=False, error="Paciente não encontrado para esta clínica."), 404

        created_by = resolve_logged_usuario_id(conn)
        now = datetime.now()

        cur = conn.cursor()
        cur.execute("""
            INSERT INTO pts (
                clinica_id,
                paciente_id,
                data_pts,
                objetivo_geral,
                avaliacao,
                plano,
                observacoes,
                created_by,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            int(clinica_id),
            int(paciente_id),
            data_pts,
            data.get("objetivo_geral") or "",
            data.get("avaliacao") or "",
            data.get("plano") or "",
            data.get("observacoes") or "",
            int(created_by) if created_by else None,
            now,
            now,
        ))

        pts_id = int(_val(cur.fetchone(), "id", 0))

        insert_pts_participantes(
            conn=conn,
            pts_id=pts_id,
            ids=norm_ids,
            clinica_id=clinica_id,
            now=now,
        )

        registrar_log(
            conn,
            acao="CRIAR_PTS_API",
            modulo="pts",
            referencia_id=pts_id,
            detalhes=f"PTS criado via API para paciente_id={paciente_id}",
        )

        conn.commit()

        return jsonify(ok=True, pts_id=pts_id)

    except PermissionError as e:
        try:
            conn.rollback()
        except Exception:
            pass

        return jsonify(ok=False, error=str(e)), 403

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
@require_permission("pts", "exportar")
def export_pts_excel(pts_id: int):
    conn = conectar_db()

    try:
        return export_pts_excel_service(conn, pts_id)

    except PermissionError as e:
        flash(str(e), "error")
        return redirect(url_for("pts.pts_visualizar"))

    finally:
        try:
            conn.close()
        except Exception:
            pass


# ============================================================
# EXPORT · PDF
# ============================================================

@pts_bp.get("/export/pdf/<int:pts_id>")
@require_permission("pts", "exportar")
def export_pts_pdf(pts_id: int):
    conn = conectar_db()

    try:
        return export_pts_pdf_service(conn, pts_id)

    except PermissionError as e:
        flash(str(e), "error")
        return redirect(url_for("pts.pts_visualizar"))

    finally:
        try:
            conn.close()
        except Exception:
            pass