from __future__ import annotations

from datetime import date, datetime

from flask import jsonify, render_template, request

from . import atendimentos_bp
from db import conectar_db

from .helpers import (
    digits,
    fetch_pacientes,
    has_column,
    has_table,
    table_columns,
    ensure_fila_table,
    sync_today_agenda_to_fila,
    buscar_combo_ativo_paciente,
    resolve_paciente,
    listar_profissionais_usuarios,
    _row_get,
)


# ============================================================
# PÁGINA PRINCIPAL DA FILA
# ============================================================

@atendimentos_bp.route("/", methods=["GET"])
def lista_atendimentos():
    with conectar_db() as conn:
        pacientes = fetch_pacientes(conn)
        profissionais = listar_profissionais_usuarios(conn)

    return render_template(
        "lista_atendimentos.html",
        pacientes=pacientes,
        profissionais=profissionais,
        fila=[],
        data_hoje=date.today().isoformat(),
    )


# ============================================================
# FILA DE ATENDIMENTOS
# ============================================================

@atendimentos_bp.route("/api/fila/sync_hoje", methods=["POST"])
def api_fila_sync_hoje():
    with conectar_db() as conn:
        ensure_fila_table(conn)
        sync_today_agenda_to_fila(conn)

    return jsonify({"ok": True})


@atendimentos_bp.route("/api/fila", methods=["GET"])
def api_fila_list():
    with conectar_db() as conn:
        ensure_fila_table(conn)
        sync_today_agenda_to_fila(conn)

        has_prof = has_table(conn, "profissionais")
        has_user = has_table(conn, "usuarios")

        cur = conn.cursor()

        base_cols = """
            f.id,
            f.hora,
            f.paciente_id,
            COALESCE(f.paciente_nome, p.nome) AS paciente_nome,
            f.profissional_id,
        """

        tail_cols = """
            COALESCE(f.tipo, 'Individual') AS tipo,
            COALESCE(f.prioridade, 'verde') AS prioridade,
            COALESCE(f.obs, '') AS obs,
            COALESCE(f.origem, 'manual') AS origem,
            f.agenda_id,
            COALESCE(f.status, '') AS status
        """

        if has_prof and has_user:
            sql = f"""
                SELECT {base_cols}
                       COALESCE(pr.nome, u.nome, '—') AS profissional_nome,
                       {tail_cols}
                  FROM fila_atendimentos f
                  LEFT JOIN pacientes p ON p.id = f.paciente_id
                  LEFT JOIN profissionais pr ON pr.id = f.profissional_id
                  LEFT JOIN usuarios u ON u.id = f.profissional_id
                 ORDER BY f.id DESC
            """
        elif has_prof:
            sql = f"""
                SELECT {base_cols}
                       COALESCE(pr.nome, '—') AS profissional_nome,
                       {tail_cols}
                  FROM fila_atendimentos f
                  LEFT JOIN pacientes p ON p.id = f.paciente_id
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
                  LEFT JOIN usuarios u ON u.id = f.profissional_id
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
        rows = cur.fetchall() or []

        items = []
        for r in rows:
            paciente_id = _row_get(r, "paciente_id", 2)
            origem = _row_get(r, "origem", 9, "manual") or "manual"

            items.append({
                "id": _row_get(r, "id", 0),
                "hora": _row_get(r, "hora", 1),
                "paciente_id": paciente_id,
                "paciente_nome": _row_get(r, "paciente_nome", 3),
                "profissional_id": _row_get(r, "profissional_id", 4),
                "profissional_nome": _row_get(r, "profissional_nome", 5) or "—",
                "tipo": _row_get(r, "tipo", 6) or "Individual",
                "prioridade": _row_get(r, "prioridade", 7) or "verde",
                "obs": _row_get(r, "obs", 8) or "",
                "origem": origem,
                "agenda_id": _row_get(r, "agenda_id", 10),
                "status": _row_get(r, "status", 11) or "",
                "from_agenda": origem == "agenda",
                "combo": buscar_combo_ativo_paciente(conn, paciente_id),
            })

    return jsonify(items)


@atendimentos_bp.route("/api/fila/add", methods=["POST"])
def api_fila_add():
    data = request.get_json(force=True, silent=True) or {}

    with conectar_db() as conn:
        ensure_fila_table(conn)
        cur = conn.cursor()

        profissional_id = data.get("profissional_id")
        if not profissional_id:
            return jsonify({"ok": False, "error": "Profissional obrigatório."}), 400

        existe_prof = False

        if has_table(conn, "profissionais"):
            try:
                cond = ""
                if has_column(conn, "profissionais", "ativo"):
                    cond = "AND (ativo = TRUE OR ativo IS NULL)"

                cur.execute(
                    f"""
                    SELECT 1
                      FROM profissionais
                     WHERE id = %s
                     {cond}
                     LIMIT 1
                    """,
                    (int(profissional_id),),
                )
                existe_prof = cur.fetchone() is not None
            except Exception:
                existe_prof = False

        if not existe_prof and has_table(conn, "usuarios"):
            try:
                cur.execute(
                    "SELECT 1 FROM usuarios WHERE id = %s LIMIT 1",
                    (int(profissional_id),),
                )
                existe_prof = cur.fetchone() is not None
            except Exception:
                existe_prof = False

        if not existe_prof:
            return jsonify({
                "ok": False,
                "error": "Profissional não encontrado."
            }), 400

        pac = resolve_paciente(
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

        cur.execute(
            """
            INSERT INTO fila_atendimentos
                (hora, paciente_id, paciente_nome, profissional_id, tipo, prioridade, obs, created_at, origem)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, 'manual')
            """,
            (
                hora,
                pac["id"],
                pac["nome"],
                int(profissional_id),
                tipo,
                prioridade,
                obs,
            ),
        )

        conn.commit()

    return jsonify({"ok": True})


@atendimentos_bp.route("/api/fila/<int:item_id>", methods=["DELETE"])
def api_fila_delete(item_id: int):
    with conectar_db() as conn:
        ensure_fila_table(conn)

        cur = conn.cursor()
        cur.execute("DELETE FROM fila_atendimentos WHERE id = %s", (item_id,))
        conn.commit()

    return jsonify({"ok": True})


@atendimentos_bp.route("/api/fila/clear", methods=["POST"])
def api_fila_clear():
    with conectar_db() as conn:
        ensure_fila_table(conn)

        cur = conn.cursor()
        cur.execute("DELETE FROM fila_atendimentos")
        conn.commit()

    return jsonify({"ok": True})


@atendimentos_bp.patch("/api/fila/<int:item_id>")
def api_fila_update(item_id: int):
    data = request.get_json(silent=True, force=True) or {}

    allowed = {
        "hora": "hora",
        "tipo": "tipo",
        "prioridade": "prioridade",
        "obs": "obs",
        "profissional_id": "profissional_id",
        "status": "status",
    }

    fields = []
    params = []

    for key, col in allowed.items():
        if key not in data:
            continue

        value = data.get(key)

        if key == "profissional_id":
            try:
                value = int(value) if value else None
            except Exception:
                value = None
        else:
            value = (value or "").strip()

        fields.append(f"{col} = %s")
        params.append(value)

    if not fields:
        return jsonify({"ok": False, "error": "Nada para atualizar."}), 400

    params.append(item_id)

    with conectar_db() as conn:
        ensure_fila_table(conn)

        cur = conn.cursor()
        cur.execute(
            f"""
            UPDATE fila_atendimentos
               SET {", ".join(fields)}
             WHERE id = %s
            """,
            params,
        )
        conn.commit()

    return jsonify({"ok": True})


# ============================================================
# DECLARAÇÃO
# ============================================================

@atendimentos_bp.get("/declaracao/<int:item_id>")
def declaracao_comparecimento(item_id: int):
    with conectar_db() as conn:
        ensure_fila_table(conn)

        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                f.id,
                f.hora,
                f.paciente_id,
                COALESCE(f.paciente_nome, p.nome) AS paciente_nome,
                f.profissional_id,
                COALESCE(u.nome, pr.nome, '—') AS profissional_nome,
                COALESCE(f.tipo, 'Individual') AS tipo,
                COALESCE(f.prioridade, 'verde') AS prioridade,
                COALESCE(f.obs, '') AS obs,
                f.created_at
            FROM fila_atendimentos f
            LEFT JOIN pacientes p ON p.id = f.paciente_id
            LEFT JOIN usuarios u ON u.id = f.profissional_id
            LEFT JOIN profissionais pr ON pr.id = f.profissional_id
            WHERE f.id = %s
            LIMIT 1
            """,
            (item_id,),
        )

        r = cur.fetchone()

    if not r:
        return "Item não encontrado.", 404

    data = {
        "id": _row_get(r, "id", 0),
        "hora": _row_get(r, "hora", 1),
        "paciente_id": _row_get(r, "paciente_id", 2),
        "paciente_nome": _row_get(r, "paciente_nome", 3),
        "profissional_id": _row_get(r, "profissional_id", 4),
        "profissional_nome": _row_get(r, "profissional_nome", 5) or "—",
        "tipo": _row_get(r, "tipo", 6) or "Individual",
        "prioridade": _row_get(r, "prioridade", 7) or "verde",
        "obs": _row_get(r, "obs", 8) or "",
        "created_at": _row_get(r, "created_at", 9),
    }

    return render_template(
        "declaracao_comparecimento.html",
        **data,
        hoje=date.today(),
    )


# ============================================================
# AUTOCOMPLETE · PROFISSIONAIS
# ============================================================

@atendimentos_bp.get("/api/profissionais")
def api_profissionais():
    q = (request.args.get("q") or "").strip()

    if len(q) < 3:
        return jsonify(ok=True, items=[])

    with conectar_db() as conn:
        if not has_table(conn, "usuarios") or not has_column(conn, "usuarios", "nome"):
            return jsonify(ok=True, items=[])

        cols = table_columns(conn, "usuarios")
        has_cpf = "cpf" in cols

        q_digits = digits(q)

        conds = ["LOWER(COALESCE(nome, '')) LIKE LOWER(%s)"]
        params = [f"%{q}%"]

        if has_cpf and q_digits:
            conds.append("REGEXP_REPLACE(COALESCE(cpf, ''), '\\D', '', 'g') LIKE %s")
            params.append(f"%{q_digits}%")

        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT
                id,
                TRIM(COALESCE(nome, '')) AS nome,
                {"TRIM(COALESCE(cpf, '')) AS cpf" if has_cpf else "'' AS cpf"}
            FROM usuarios
            WHERE {" OR ".join(conds)}
            ORDER BY LOWER(nome)
            LIMIT 50
            """,
            params,
        )

        rows = cur.fetchall() or []

    items = []
    for r in rows:
        uid = _row_get(r, "id", 0)
        nome = (_row_get(r, "nome", 1, "") or "").strip()
        cpf = (_row_get(r, "cpf", 2, "") or "").strip()

        if not nome:
            continue

        label = f"{nome} ({cpf})" if cpf else nome
        items.append({
            "id": uid,
            "nome": nome,
            "cpf": cpf,
            "label": label,
        })

    return jsonify(ok=True, items=items)


@atendimentos_bp.get("/api/profissionais_sugestao")
def api_profissionais_sugestao():
    q = (request.args.get("q") or "").strip()

    if len(q) < 3:
        return jsonify([])

    q_digits = digits(q)

    with conectar_db() as conn:
        if not has_table(conn, "usuarios"):
            return jsonify([])

        cols = table_columns(conn, "usuarios")

        if "nome" not in cols:
            return jsonify([])

        has_role = "role" in cols
        has_cbo = "cbo" in cols

        role_filter = "AND UPPER(COALESCE(role, '')) = 'PROFISSIONAL'" if has_role else ""
        cbo_cond = "OR (%s <> '' AND COALESCE(cbo, '') LIKE %s)" if has_cbo else ""

        params = [f"%{q}%"]

        if has_cbo:
            params += [q_digits, f"%{q_digits}%"]

        params += [f"{q}%"]

        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT
                id,
                nome,
                {"COALESCE(cbo, '') AS cbo" if has_cbo else "'' AS cbo"}
            FROM usuarios
            WHERE 1=1
              {role_filter}
              AND (
                    LOWER(COALESCE(nome, '')) LIKE LOWER(%s)
                    {cbo_cond}
              )
            ORDER BY
                CASE
                    WHEN LOWER(COALESCE(nome, '')) LIKE LOWER(%s) THEN 0
                    ELSE 9
                END,
                LOWER(COALESCE(nome, ''))
            LIMIT 12
            """,
            params,
        )

        rows = cur.fetchall() or []

    return jsonify([
        {
            "id": _row_get(r, "id", 0),
            "nome": _row_get(r, "nome", 1, "") or "",
            "cbo": _row_get(r, "cbo", 2, "") or "",
        }
        for r in rows
    ])