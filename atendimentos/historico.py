from __future__ import annotations

from datetime import date

from flask import jsonify, render_template, request

from . import atendimentos_bp
from db import conectar_db

from .helpers import (
    _row_get,
    has_table,
    has_column,
    ensure_atendimentos_schema,
    ensure_atendimento_procedimentos_schema,
    buscar_combo_ativo_paciente,
)


# ============================================================
# API · ÚLTIMO ATENDIMENTO DO PACIENTE
# ============================================================

@atendimentos_bp.route("/api/ultimo_atendimento")
def api_ultimo_atendimento():
    paciente_id = (request.args.get("id") or "").strip()

    if not paciente_id:
        return jsonify({
            "ok": False,
            "error": "Parâmetro 'id' do paciente é obrigatório."
        }), 400

    with conectar_db() as conn:
        ensure_atendimentos_schema(conn)
        ensure_atendimento_procedimentos_schema(conn)

        if not has_table(conn, "atendimentos"):
            return jsonify({
                "ok": True,
                "found": False,
                "data": "-",
                "profissional": "-",
                "id": None,
            })

        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                id,
                paciente_id,
                data_atendimento,
                COALESCE(nome_profissional, '') AS nome_profissional,
                COALESCE(status, '') AS status,
                COALESCE(justificativa, '') AS justificativa,
                COALESCE(anexo_atestado, '') AS anexo_atestado,
                COALESCE(evolucao, '') AS evolucao,
                combo_plano_id
            FROM atendimentos
            WHERE paciente_id = %s
            ORDER BY
                data_atendimento DESC NULLS LAST,
                id DESC
            LIMIT 1
            """,
            (paciente_id,),
        )

        row = cur.fetchone()

        if not row:
            return jsonify({
                "ok": True,
                "found": False,
                "data": "-",
                "profissional": "-",
                "id": None,
            })

        atendimento_id = _row_get(row, "id", 0)
        data_atendimento = _row_get(row, "data_atendimento", 2)
        profissional = _row_get(row, "nome_profissional", 3, "") or "-"
        status = _row_get(row, "status", 4, "") or "-"
        justificativa = _row_get(row, "justificativa", 5, "") or ""
        anexo_atestado = _row_get(row, "anexo_atestado", 6, "") or ""
        evolucao = _row_get(row, "evolucao", 7, "") or ""
        combo_plano_id = _row_get(row, "combo_plano_id", 8)

        procs = []

        if has_table(conn, "atendimento_procedimentos"):
            cur.execute(
                """
                SELECT
                    COALESCE(procedimento, '') AS procedimento,
                    COALESCE(codigo_sigtap, '') AS codigo_sigtap
                FROM atendimento_procedimentos
                WHERE atendimento_id = %s
                ORDER BY id ASC
                """,
                (atendimento_id,),
            )

            procs = [
                {
                    "procedimento": _row_get(r, "procedimento", 0, "") or "",
                    "codigo_sigtap": _row_get(r, "codigo_sigtap", 1, "") or "",
                }
                for r in (cur.fetchall() or [])
            ]

        primeiro_proc = procs[0]["procedimento"] if procs else "-"
        primeiro_cod = procs[0]["codigo_sigtap"] if procs else "-"
        combo = buscar_combo_ativo_paciente(conn, paciente_id)

    return jsonify({
        "ok": True,
        "found": True,
        "id": atendimento_id,
        "data": str(data_atendimento) if data_atendimento else "-",
        "profissional": profissional,
        "status": status,
        "justificativa": justificativa,
        "anexo_atestado": anexo_atestado,
        "evolucao": evolucao,
        "procedimento": primeiro_proc,
        "codigo_sigtap": primeiro_cod,
        "procedimentos": procs,
        "combo_plano_id": combo_plano_id,
        "combo": combo,
    })


# ============================================================
# API · JSON COMPLETO DE UM ATENDIMENTO
# ============================================================

@atendimentos_bp.route("/<int:aid>.json", methods=["GET"])
def ver_atendimento_json(aid: int):
    with conectar_db() as conn:
        ensure_atendimentos_schema(conn)
        ensure_atendimento_procedimentos_schema(conn)

        if not has_table(conn, "atendimentos"):
            return jsonify({
                "ok": False,
                "error": "Tabela de atendimentos não encontrada."
            }), 404

        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                id,
                paciente_id,
                data_atendimento,
                COALESCE(nome_profissional, '') AS nome_profissional,
                COALESCE(status, '') AS status,
                COALESCE(justificativa, '') AS justificativa,
                COALESCE(evolucao, '') AS evolucao,
                COALESCE(nome, '') AS paciente_nome,
                COALESCE(mod, '') AS mod,
                COALESCE(status_paciente, '') AS status_paciente,
                COALESCE(anexo_atestado, '') AS anexo_atestado,
                combo_plano_id
            FROM atendimentos
            WHERE id = %s
            LIMIT 1
            """,
            (aid,),
        )

        row = cur.fetchone()

        if not row:
            return jsonify({
                "ok": False,
                "error": "Atendimento não encontrado."
            }), 404

        atendimento_id = _row_get(row, "id", 0)
        paciente_id = _row_get(row, "paciente_id", 1)
        data_atendimento = _row_get(row, "data_atendimento", 2)
        profissional_nome = _row_get(row, "nome_profissional", 3, "") or "—"
        status = _row_get(row, "status", 4, "") or ""
        justificativa = _row_get(row, "justificativa", 5, "") or ""
        evolucao = _row_get(row, "evolucao", 6, "") or ""
        paciente_nome = _row_get(row, "paciente_nome", 7, "") or ""
        mod = _row_get(row, "mod", 8, "") or ""
        status_paciente = _row_get(row, "status_paciente", 9, "") or ""
        anexo_atestado = _row_get(row, "anexo_atestado", 10, "") or ""
        combo_plano_id = _row_get(row, "combo_plano_id", 11)

        prontuario = ""

        if paciente_id and has_table(conn, "pacientes") and has_column(conn, "pacientes", "prontuario"):
            cur.execute(
                """
                SELECT COALESCE(prontuario, '') AS prontuario
                FROM pacientes
                WHERE id = %s
                LIMIT 1
                """,
                (paciente_id,),
            )

            rp = cur.fetchone()
            prontuario = _row_get(rp, "prontuario", 0, "") or ""

        procs = []

        if has_table(conn, "atendimento_procedimentos"):
            cur.execute(
                """
                SELECT
                    COALESCE(procedimento, '') AS procedimento,
                    COALESCE(codigo_sigtap, '') AS codigo_sigtap
                FROM atendimento_procedimentos
                WHERE atendimento_id = %s
                ORDER BY id ASC
                """,
                (aid,),
            )

            procs = [
                {
                    "procedimento": _row_get(r, "procedimento", 0, "") or "",
                    "codigo_sigtap": _row_get(r, "codigo_sigtap", 1, "") or "",
                }
                for r in (cur.fetchall() or [])
            ]

        primeiro_proc = procs[0]["procedimento"] if procs else ""
        primeiro_cod = procs[0]["codigo_sigtap"] if procs else ""
        combo = buscar_combo_ativo_paciente(conn, paciente_id)

    return jsonify({
        "ok": True,
        "id": atendimento_id,
        "paciente_id": paciente_id,
        "data_atendimento": str(data_atendimento) if data_atendimento else "",
        "status": status,
        "justificativa": justificativa,
        "evolucao": evolucao,
        "paciente_nome": paciente_nome,
        "prontuario": prontuario,
        "mod": mod,
        "status_paciente": status_paciente,
        "profissional_nome": profissional_nome,
        "anexo_atestado": anexo_atestado,
        "procedimento": primeiro_proc,
        "codigo_sigtap": primeiro_cod,
        "procedimentos": procs,
        "combo_plano_id": combo_plano_id,
        "combo": combo,
    })


# ============================================================
# PÁGINA · HISTÓRICO
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


# ============================================================
# API · HISTÓRICO DO PACIENTE
# ============================================================

@atendimentos_bp.route("/api/historico")
def api_historico():
    paciente_id = (request.args.get("paciente_id") or "").strip()

    if not paciente_id:
        return jsonify({
            "ok": False,
            "error": "Parâmetro 'paciente_id' é obrigatório."
        }), 400

    with conectar_db() as conn:
        ensure_atendimentos_schema(conn)
        ensure_atendimento_procedimentos_schema(conn)

        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                a.id AS atendimento_id,
                a.data_atendimento AS data_atendimento,

                COALESCE(ap.procedimento, '') AS procedimento,
                COALESCE(ap.codigo_sigtap, '') AS codigo_sigtap,

                COALESCE(a.status, '') AS status,
                COALESCE(a.justificativa, '') AS justificativa,
                COALESCE(a.evolucao, '') AS evolucao,

                COALESCE(a.nome_profissional, '') AS nome_profissional,
                COALESCE(a.cns_profissional, '') AS cns_profissional,
                COALESCE(a.cbo_profissional, '') AS cbo_profissional,

                a.combo_plano_id
            FROM atendimentos a
            LEFT JOIN atendimento_procedimentos ap
                   ON ap.atendimento_id = a.id
            WHERE a.paciente_id = %s
            ORDER BY
                a.data_atendimento DESC NULLS LAST,
                a.id DESC,
                ap.id ASC
            LIMIT 800
            """,
            (paciente_id,),
        )

        rows = cur.fetchall() or []

    return jsonify({
        "ok": True,
        "items": [
            {
                "atendimento_id": _row_get(r, "atendimento_id", 0),
                "data_atendimento": str(_row_get(r, "data_atendimento", 1) or ""),
                "procedimento": _row_get(r, "procedimento", 2, "") or "",
                "codigo_sigtap": _row_get(r, "codigo_sigtap", 3, "") or "",
                "status": _row_get(r, "status", 4, "") or "",
                "justificativa": _row_get(r, "justificativa", 5, "") or "",
                "evolucao": _row_get(r, "evolucao", 6, "") or "",
                "profissional": _row_get(r, "nome_profissional", 7, "") or "—",
                "profissional_cns": _row_get(r, "cns_profissional", 8, "") or "",
                "profissional_cbo": _row_get(r, "cbo_profissional", 9, "") or "",
                "combo_plano_id": _row_get(r, "combo_plano_id", 10),
            }
            for r in rows
        ]
    })