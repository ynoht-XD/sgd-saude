from __future__ import annotations

import re
from datetime import date

from flask import flash, jsonify, redirect, render_template, request, url_for

from . import atendimentos_bp
from db import conectar_db

from .helpers import (
    _row_get,
    _to_int,
    fetch_pacientes,
    get_paciente_cids,
    get_procedimentos_competencia_vigente,
    has_column,
    has_table,
    table_columns,
    ensure_atendimentos_schema,
    ensure_atendimento_procedimentos_schema,
    ensure_fila_table,
    listar_combos_ativos_para_template,
    buscar_combo_ativo_paciente,
    recalcular_saldo_combo,
    listar_procedimentos_compativeis_db,
    normalize_procs_from_form,
    resolve_logged_profissional_id,
    resolve_prof_dados,
)


def only_digits(v: str | None) -> str:
    return re.sub(r"\D+", "", v or "")


def ensure_evolucoes_ocultas_schema(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS atendimento_evolucoes_ocultas (
            id SERIAL PRIMARY KEY,
            atendimento_id INTEGER NOT NULL REFERENCES atendimentos(id) ON DELETE CASCADE,
            paciente_id INTEGER,
            profissional_id INTEGER,
            profissional_nome TEXT,
            profissional_cbo TEXT,
            evolucao_oculta TEXT NOT NULL,
            visibilidade TEXT NOT NULL DEFAULT 'somente_eu',
            cbos_autorizados TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_evo_oculta_atendimento
        ON atendimento_evolucoes_ocultas (atendimento_id)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_evo_oculta_paciente
        ON atendimento_evolucoes_ocultas (paciente_id)
    """)
    conn.commit()


@atendimentos_bp.route("/registrar", methods=["GET"])
def pagina_atendimento():
    with conectar_db() as conn:
        pacientes = fetch_pacientes(conn)
        combos_ativos = listar_combos_ativos_para_template(conn)
        ensure_atendimentos_schema(conn)
        ensure_atendimento_procedimentos_schema(conn)
        ensure_evolucoes_ocultas_schema(conn)

    return render_template(
        "atendimentos.html",
        pacientes=pacientes,
        profissionais=[],
        data_hoje=date.today().isoformat(),
        combos_ativos=combos_ativos,
    )


@atendimentos_bp.get("/api/paciente/<int:paciente_id>/combo")
def api_combo_paciente(paciente_id: int):
    with conectar_db() as conn:
        ensure_atendimentos_schema(conn)
        item = buscar_combo_ativo_paciente(conn, paciente_id)

    return jsonify({"ok": True, "item": item})


@atendimentos_bp.get("/api/procedimentos_sugeridos")
def api_procedimentos_sugeridos():
    paciente_id = (request.args.get("paciente_id") or "").strip()

    if not paciente_id:
        return jsonify(ok=False, error="paciente_id é obrigatório."), 400

    with conectar_db() as conn:
        profissional_id = resolve_logged_profissional_id(conn)

        if not profissional_id:
            return jsonify(ok=False, error="Profissional logado não identificado."), 401

        _, _, _, prof_cbo = resolve_prof_dados(conn, profissional_id)
        prof_cbo = (prof_cbo or "").strip()

        pac_cids = get_paciente_cids(conn, paciente_id)
        items = listar_procedimentos_compativeis_db(conn, prof_cbo, pac_cids)
        competencia_vigente = get_procedimentos_competencia_vigente(conn)

    return jsonify(
        ok=True,
        cbo=prof_cbo,
        paciente_cids=pac_cids,
        competencia=competencia_vigente,
        total=len(items),
        items=items,
    )


@atendimentos_bp.get("/api/cbos_sugestoes")
def api_cbos_sugestoes():
    """
    Busca CBO por número ou descrição.
    Tenta primeiro tabela de catálogo/biblioteca; se não existir, usa usuarios.cbo.
    Retorna [{codigo, descricao, label}]
    """
    q = (request.args.get("q") or "").strip()
    q_digits = only_digits(q)

    if len(q) < 2 and len(q_digits) < 2:
        return jsonify(ok=True, items=[])

    with conectar_db() as conn:
        cur = conn.cursor()
        items = []

        # 1) Catálogos possíveis
        catalogos = [
            ("cbo_catalogo", "co_ocupacao", "no_ocupacao"),
            ("cbos", "co_ocupacao", "no_ocupacao"),
            ("ocupacoes", "codigo", "descricao"),
            ("ocupacoes", "co_ocupacao", "no_ocupacao"),
        ]

        for tabela, col_cod, col_desc in catalogos:
            if not has_table(conn, tabela):
                continue

            cols = table_columns(conn, tabela)
            if col_cod not in cols or col_desc not in cols:
                continue

            cur.execute(
                f"""
                SELECT
                    COALESCE({col_cod}::text, '') AS codigo,
                    COALESCE({col_desc}::text, '') AS descricao
                FROM {tabela}
                WHERE
                    REGEXP_REPLACE(COALESCE({col_cod}::text, ''), '\\D', '', 'g') ILIKE %s
                    OR COALESCE({col_desc}::text, '') ILIKE %s
                ORDER BY descricao
                LIMIT 30
                """,
                (f"%{q_digits}%" if q_digits else "%__sem_numero__", f"%{q}%"),
            )
            rows = cur.fetchall() or []

            for r in rows:
                codigo = _row_get(r, "codigo", 0, "") or ""
                descricao = _row_get(r, "descricao", 1, "") or ""
                if codigo or descricao:
                    items.append({
                        "codigo": codigo,
                        "descricao": descricao,
                        "label": f"{codigo} - {descricao}".strip(" -"),
                    })

            if items:
                break

        # 2) Fallback: CBOs cadastrados em usuários
        if not items and has_table(conn, "usuarios") and has_column(conn, "usuarios", "cbo"):
            nome_expr = "COALESCE(nome, '')" if has_column(conn, "usuarios", "nome") else "''"

            cur.execute(
                f"""
                SELECT DISTINCT
                    COALESCE(cbo::text, '') AS codigo,
                    {nome_expr} AS descricao
                FROM usuarios
                WHERE COALESCE(cbo::text, '') <> ''
                  AND (
                    REGEXP_REPLACE(COALESCE(cbo::text, ''), '\\D', '', 'g') ILIKE %s
                    OR {nome_expr} ILIKE %s
                  )
                ORDER BY codigo
                LIMIT 30
                """,
                (f"%{q_digits}%" if q_digits else "%__sem_numero__", f"%{q}%"),
            )

            rows = cur.fetchall() or []
            for r in rows:
                codigo = _row_get(r, "codigo", 0, "") or ""
                descricao = _row_get(r, "descricao", 1, "") or ""
                items.append({
                    "codigo": codigo,
                    "descricao": descricao,
                    "label": f"{codigo} - {descricao}".strip(" -"),
                })

    return jsonify(ok=True, items=items)


@atendimentos_bp.route("/api/sugestoes_pacientes")
def sugestoes_pacientes():
    termo = (request.args.get("termo", "") or "").strip()

    if len(termo) < 2:
        return jsonify([])

    with conectar_db() as conn:
        if not has_table(conn, "pacientes"):
            return jsonify([])

        cols = table_columns(conn, "pacientes")

        col_pront = "prontuario" if "prontuario" in cols else "''"
        col_stat = "status" if "status" in cols else "''"
        col_mod = "mod" if "mod" in cols else "''"
        col_nasc = "nascimento" if "nascimento" in cols else ("data_nascimento" if "data_nascimento" in cols else "''")
        col_cid = "cid" if "cid" in cols else "''"

        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT
                id,
                COALESCE(nome, '') AS nome,
                COALESCE({col_pront}, '') AS prontuario,
                COALESCE({col_stat}, '') AS status,
                COALESCE({col_mod}, '') AS mod,
                COALESCE({col_nasc}, '') AS nascimento,
                COALESCE({col_cid}, '') AS cid
            FROM pacientes
            WHERE nome ILIKE %s
            ORDER BY nome
            LIMIT 10
            """,
            (f"%{termo}%",),
        )
        rows = cur.fetchall() or []

    return jsonify([
        {
            "id": _row_get(r, "id", 0),
            "nome": _row_get(r, "nome", 1, "") or "",
            "prontuario": _row_get(r, "prontuario", 2, "") or "",
            "status": _row_get(r, "status", 3, "") or "",
            "mod": _row_get(r, "mod", 4, "") or "",
            "nascimento": str(_row_get(r, "nascimento", 5, "") or ""),
            "cid": _row_get(r, "cid", 6, "") or "-",
        }
        for r in rows
    ])


@atendimentos_bp.route("/api/paciente")
def api_paciente():
    pid = (request.args.get("id") or "").strip()

    if not pid:
        return jsonify({"ok": False, "error": "Parâmetro 'id' é obrigatório."}), 400

    with conectar_db() as conn:
        if not has_table(conn, "pacientes"):
            return jsonify({"ok": True, "found": False}), 404

        cols = table_columns(conn, "pacientes")

        col_pront = "prontuario" if "prontuario" in cols else "''"
        col_stat = "status" if "status" in cols else "''"
        col_mod = "mod" if "mod" in cols else "''"
        col_nasc = "nascimento" if "nascimento" in cols else ("data_nascimento" if "data_nascimento" in cols else "''")
        col_cid = "cid" if "cid" in cols else "''"

        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT
                id,
                COALESCE(nome, '') AS nome,
                COALESCE({col_pront}, '') AS prontuario,
                COALESCE({col_stat}, '') AS status,
                COALESCE({col_mod}, '') AS mod,
                COALESCE({col_nasc}, '') AS nascimento,
                COALESCE({col_cid}, '') AS cid
            FROM pacientes
            WHERE id = %s
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
        "id": _row_get(row, "id", 0),
        "nome": _row_get(row, "nome", 1, "") or "",
        "prontuario": _row_get(row, "prontuario", 2, "") or "",
        "status": _row_get(row, "status", 3, "") or "",
        "mod": _row_get(row, "mod", 4, "") or "",
        "nascimento": str(_row_get(row, "nascimento", 5, "") or ""),
        "cid": _row_get(row, "cid", 6, "") or "-",
    })


@atendimentos_bp.route("/salvar", methods=["POST"], endpoint="salvar_atendimento")
def salvar_atendimento_view():
    is_fetch = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    conn = conectar_db()
    cursor = conn.cursor()

    try:
        ensure_atendimentos_schema(conn)
        ensure_atendimento_procedimentos_schema(conn)
        ensure_fila_table(conn)
        ensure_evolucoes_ocultas_schema(conn)

        profissional_id = resolve_logged_profissional_id(conn)

        if not profissional_id:
            msg = "Não foi possível identificar o profissional logado. Faça login novamente."
            if is_fetch:
                return jsonify({"ok": False, "error": msg}), 401
            flash(msg)
            return redirect(url_for("atendimentos.pagina_atendimento"))

        _, prof_nome, prof_cns, prof_cbo = resolve_prof_dados(conn, profissional_id)
        prof_cbo = (prof_cbo or "").strip()

        if not prof_cbo:
            msg = "O profissional logado não possui CBO cadastrado."
            if is_fetch:
                return jsonify({"ok": False, "error": msg}), 400
            flash(msg)
            return redirect(url_for("atendimentos.pagina_atendimento"))

        paciente_id = (request.form.get("nomePaciente") or "").strip()
        data_atendimento = (request.form.get("dataAtendimento") or date.today().isoformat()).strip()
        status_atend = (request.form.get("status_justificativa") or "Realizado").strip()
        justificativa = (request.form.get("justificativa") or "").strip()
        evolucao = (request.form.get("evolucao") or "").strip()

        evolucao_oculta = (request.form.get("evolucao_oculta") or "").strip()
        evolucao_oculta_visibilidade = (
            request.form.get("evolucao_oculta_visibilidade") or "somente_eu"
        ).strip()
        evolucao_oculta_cbos = (request.form.get("evolucao_oculta_cbos") or "").strip()

        if evolucao_oculta_visibilidade not in ("somente_eu", "cbos"):
            evolucao_oculta_visibilidade = "somente_eu"

        if evolucao_oculta_visibilidade != "cbos":
            evolucao_oculta_cbos = ""

        fila_id_raw = (request.form.get("fila_id") or "").strip()
        fila_id = int(fila_id_raw) if fila_id_raw.isdigit() else None

        combo_plano_id_raw = (request.form.get("combo_plano_id") or "").strip()
        combo_plano_id = int(combo_plano_id_raw) if combo_plano_id_raw.isdigit() else None

        contabiliza_sessao_raw = (request.form.get("contabiliza_sessao") or "").strip().lower()
        contabiliza_sessao = 1 if contabiliza_sessao_raw in ("1", "true", "on", "sim", "yes") else 0

        enviar_sem_procedimento_raw = (request.form.get("enviar_sem_procedimento") or "").strip().lower()
        enviar_sem_procedimento = 1 if enviar_sem_procedimento_raw in ("1", "true", "on", "sim", "yes") else 0

        if not paciente_id:
            msg = "Paciente não informado."
            if is_fetch:
                return jsonify({"ok": False, "error": msg}), 400
            flash(msg)
            return redirect(url_for("atendimentos.pagina_atendimento"))

        procedimentos, codigos = normalize_procs_from_form(request.form)

        cursor.execute(
            """
            SELECT
                COALESCE(nome, '') AS nome,
                COALESCE(prontuario, '') AS prontuario,
                COALESCE(mod, '') AS mod,
                COALESCE(status, '') AS status
            FROM pacientes
            WHERE id = %s
            LIMIT 1
            """,
            (paciente_id,),
        )
        paciente = cursor.fetchone()

        if not paciente:
            msg = "Paciente não encontrado."
            if is_fetch:
                return jsonify({"ok": False, "error": msg}), 404
            flash(msg)
            return redirect(url_for("atendimentos.pagina_atendimento"))

        nome = _row_get(paciente, "nome", 0, "") or ""
        prontuario = _row_get(paciente, "prontuario", 1, "") or ""
        mod = _row_get(paciente, "mod", 2, "") or ""
        status_paciente = _row_get(paciente, "status", 3, "") or ""

        if combo_plano_id:
            combo_info = buscar_combo_ativo_paciente(conn, paciente_id)

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

            cursor.execute(
                """
                SELECT 1
                FROM atendimentos
                WHERE paciente_id = %s
                  AND data_atendimento = %s
                  AND combo_plano_id = %s
                  AND COALESCE(contabiliza_sessao, 1) = 1
                LIMIT 1
                """,
                (paciente_id, data_atendimento, combo_plano_id),
            )

            if contabiliza_sessao and cursor.fetchone():
                msg = "Já existe atendimento deste combo contabilizado para este paciente nesta data."
                if is_fetch:
                    return jsonify({"ok": False, "error": msg}), 409
                flash(msg)
                return redirect(url_for("atendimentos.pagina_atendimento"))

        pac_cids = get_paciente_cids(conn, paciente_id)
        competencia_vigente = get_procedimentos_competencia_vigente(conn)
        permitidos = listar_procedimentos_compativeis_db(conn, prof_cbo, pac_cids)

        permitidos_cod = {
            (x.get("codigo") or "").strip()
            for x in permitidos
            if (x.get("codigo") or "").strip()
        }

        permitidos_desc = {
            (x.get("descricao") or "").strip().lower()
            for x in permitidos
            if (x.get("descricao") or "").strip()
        }

        if not procedimentos:
            if not enviar_sem_procedimento:
                msg = "Nenhum procedimento foi selecionado para este atendimento. Deseja salvar mesmo assim?"
                if is_fetch:
                    return jsonify({
                        "ok": False,
                        "requires_confirmation": True,
                        "error": msg,
                        "competencia": competencia_vigente or "",
                        "cbo": prof_cbo or "",
                        "paciente_cids": pac_cids,
                    }), 409
                flash(msg)
                return redirect(url_for("atendimentos.pagina_atendimento"))
        else:
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
                comp_txt = competencia_vigente or "—"

                msg = (
                    "Procedimento(s) incompatível(is) com a regra CBO/CID vigente: "
                    + ", ".join(invalidos)
                    + f" | Competência: {comp_txt} | CBO: {prof_cbo or '—'} | CID(s): {cids_txt}"
                )

                if is_fetch:
                    return jsonify({
                        "ok": False,
                        "error": msg,
                        "competencia": comp_txt,
                        "cbo": prof_cbo or "",
                        "paciente_cids": pac_cids,
                        "invalidos": invalidos,
                    }), 400

                flash(msg)
                return redirect(url_for("atendimentos.pagina_atendimento"))

        cursor.execute(
            """
            INSERT INTO atendimentos (
                paciente_id,
                data_atendimento,
                status,
                justificativa,
                evolucao,
                nome,
                prontuario,
                mod,
                status_paciente,
                profissional_id,
                nome_profissional,
                cns_profissional,
                cbo_profissional,
                combo_plano_id,
                contabiliza_sessao,
                created_at,
                atualizado_em
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            RETURNING id
            """,
            (
                paciente_id,
                data_atendimento,
                status_atend,
                justificativa,
                evolucao,
                nome,
                prontuario,
                mod,
                status_paciente,
                profissional_id,
                prof_nome,
                prof_cns,
                prof_cbo,
                combo_plano_id,
                1 if combo_plano_id and contabiliza_sessao else 0,
            ),
        )

        atendimento_id = _row_get(cursor.fetchone(), "id", 0)

        if procedimentos:
            for proc, cod in zip(procedimentos, codigos):
                cursor.execute(
                    """
                    INSERT INTO atendimento_procedimentos (
                        atendimento_id,
                        procedimento,
                        codigo_sigtap,
                        created_at
                    )
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                    """,
                    (
                        atendimento_id,
                        (proc or "").strip(),
                        (cod or "").strip() or None,
                    ),
                )

        if evolucao_oculta:
            cursor.execute(
                """
                INSERT INTO atendimento_evolucoes_ocultas (
                    atendimento_id,
                    paciente_id,
                    profissional_id,
                    profissional_nome,
                    profissional_cbo,
                    evolucao_oculta,
                    visibilidade,
                    cbos_autorizados,
                    created_at,
                    atualizado_em
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                )
                """,
                (
                    atendimento_id,
                    paciente_id,
                    profissional_id,
                    prof_nome,
                    prof_cbo,
                    evolucao_oculta,
                    evolucao_oculta_visibilidade,
                    evolucao_oculta_cbos,
                ),
            )

        if fila_id:
            cursor.execute(
                """
                UPDATE fila_atendimentos
                   SET status = 'finalizado',
                       obs = CASE
                               WHEN COALESCE(obs, '') = '' THEN 'ATENDIDO'
                               ELSE obs
                             END
                 WHERE id = %s
                """,
                (fila_id,),
            )

        conn.commit()

        if combo_plano_id:
            recalcular_saldo_combo(conn, combo_plano_id)

        if is_fetch:
            return jsonify({
                "ok": True,
                "message": "Atendimento salvo com sucesso.",
                "atendimento_id": atendimento_id,
                "redirect": url_for("atendimentos.lista_atendimentos"),
                "combo_plano_id": combo_plano_id,
                "contabiliza_sessao": 1 if combo_plano_id and contabiliza_sessao else 0,
                "competencia": competencia_vigente,
                "cbo": prof_cbo,
                "paciente_cids": pac_cids,
                "salvo_sem_procedimento": not bool(procedimentos),
                "evolucao_oculta_salva": bool(evolucao_oculta),
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

def ensure_chamadas_pacientes_schema(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chamadas_pacientes (
            id SERIAL PRIMARY KEY,
            paciente_id INTEGER,
            paciente_nome TEXT NOT NULL,
            profissional_nome TEXT,
            setor TEXT,
            status TEXT DEFAULT 'chamando',
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_chamadas_pacientes_criado_em
        ON chamadas_pacientes (criado_em)
    """)
    conn.commit()


@atendimentos_bp.route("/chama-na-tela/tv")
def chama_na_tela_tv():
    with conectar_db() as conn:
        ensure_chamadas_pacientes_schema(conn)

    return render_template("chama_na_tela_tv.html")


@atendimentos_bp.route("/chama-na-tela/chamar", methods=["POST"])
def chamar_paciente_na_tela():
    data = request.get_json(silent=True) or request.form

    paciente_id = data.get("paciente_id") or None
    paciente_nome = (data.get("paciente_nome") or "").strip()
    profissional_nome = (data.get("profissional_nome") or "").strip()
    setor = (data.get("setor") or "Recepção").strip()

    if not paciente_nome:
        return jsonify(ok=False, erro="Nome do paciente não informado."), 400

    with conectar_db() as conn:
        ensure_chamadas_pacientes_schema(conn)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO chamadas_pacientes (
                paciente_id,
                paciente_nome,
                profissional_nome,
                setor,
                status,
                criado_em
            )
            VALUES (%s, %s, %s, %s, 'chamando', CURRENT_TIMESTAMP)
            RETURNING id
            """,
            (
                paciente_id,
                paciente_nome,
                profissional_nome,
                setor,
            ),
        )
        chamada_id = _row_get(cur.fetchone(), "id", 0)
        conn.commit()

    return jsonify(
        ok=True,
        chamada_id=chamada_id,
        mensagem=f"{paciente_nome} chamado na tela."
    )


@atendimentos_bp.route("/chama-na-tela/api/ultima")
def ultima_chamada_na_tela():
    with conectar_db() as conn:
        ensure_chamadas_pacientes_schema(conn)
        cur = conn.cursor()
        cur.execute("""
            SELECT
                id,
                paciente_id,
                paciente_nome,
                profissional_nome,
                setor,
                status,
                criado_em
            FROM chamadas_pacientes
            ORDER BY id DESC
            LIMIT 1
        """)
        row = cur.fetchone()

    if not row:
        return jsonify(ok=True, chamada=None)

    chamada = {
        "id": _row_get(row, "id", 0),
        "paciente_id": _row_get(row, "paciente_id", 1),
        "paciente_nome": _row_get(row, "paciente_nome", 2, ""),
        "profissional_nome": _row_get(row, "profissional_nome", 3, ""),
        "setor": _row_get(row, "setor", 4, ""),
        "status": _row_get(row, "status", 5, ""),
        "criado_em": str(_row_get(row, "criado_em", 6, "")),
    }

    return jsonify(ok=True, chamada=chamada)

@atendimentos_bp.route("/chama-na-tela/api/recentes")
def chamadas_recentes_na_tela():
    with conectar_db() as conn:
        ensure_chamadas_pacientes_schema(conn)
        cur = conn.cursor()
        cur.execute("""
            SELECT
                id,
                paciente_id,
                paciente_nome,
                profissional_nome,
                setor,
                status,
                criado_em
            FROM chamadas_pacientes
            ORDER BY id DESC
            LIMIT 4
        """)
        rows = cur.fetchall() or []

    chamadas = []
    for r in rows:
        chamadas.append({
            "id": _row_get(r, "id", 0),
            "paciente_id": _row_get(r, "paciente_id", 1),
            "paciente_nome": _row_get(r, "paciente_nome", 2, ""),
            "profissional_nome": _row_get(r, "profissional_nome", 3, ""),
            "cbo": _row_get(r, "setor", 4, ""),  # por enquanto usando setor como CBO/modalidade
            "status": _row_get(r, "status", 5, ""),
            "criado_em": str(_row_get(r, "criado_em", 6, "")),
        })

    return jsonify(ok=True, chamadas=chamadas)

@atendimentos_bp.route("/chama-na-tela/api/fila")
def fila_chamadas_na_tela():
    after_id = request.args.get("after_id", "0")

    try:
        after_id = int(after_id)
    except ValueError:
        after_id = 0

    with conectar_db() as conn:
        ensure_chamadas_pacientes_schema(conn)
        cur = conn.cursor()
        cur.execute("""
            SELECT
                id,
                paciente_id,
                paciente_nome,
                profissional_nome,
                setor,
                status,
                criado_em
            FROM chamadas_pacientes
            WHERE id > %s
            ORDER BY id ASC
            LIMIT 10
        """, (after_id,))
        rows = cur.fetchall() or []

    chamadas = []
    for r in rows:
        chamadas.append({
            "id": _row_get(r, "id", 0),
            "paciente_id": _row_get(r, "paciente_id", 1),
            "paciente_nome": _row_get(r, "paciente_nome", 2, ""),
            "profissional_nome": _row_get(r, "profissional_nome", 3, ""),
            "cbo": _row_get(r, "setor", 4, ""),
            "setor": _row_get(r, "setor", 4, ""),
            "status": _row_get(r, "status", 5, ""),
            "criado_em": str(_row_get(r, "criado_em", 6, "")),
        })

    return jsonify(ok=True, chamadas=chamadas)