from __future__ import annotations

from datetime import date

from flask import jsonify, render_template, request, session, abort

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

try:
    from admin.modulos import require_permission
except Exception:
    def require_permission(modulo_codigo: str, acao: str = "ver"):
        def deco(fn):
            return fn
        return deco

try:
    from log import registrar_log, log_erro
except Exception:
    def registrar_log(*args, **kwargs): pass
    def log_erro(*args, **kwargs): pass


# ============================================================
# CONTEXTO / SEGURANÇA
# ============================================================

def _clinica_id_atual() -> int:
    clinica_id = session.get("clinica_id")
    if not clinica_id:
        abort(403)

    try:
        return int(clinica_id)
    except Exception:
        abort(403)


def _usuario_id_atual():
    return session.get("usuario_id") or session.get("user_id") or session.get("id")


def _filtro_clinica_sql(conn, tabela: str, alias: str = "") -> str:
    """
    Retorna filtro seguro por clínica.
    Compatível com tabelas legadas sem clinica_id.
    """
    if not has_column(conn, tabela, "clinica_id"):
        return ""

    prefix = f"{alias}." if alias else ""
    return f" AND ({prefix}clinica_id = %s OR {prefix}clinica_id IS NULL) "


def _params_clinica(conn, tabela: str, clinica_id: int) -> list:
    if has_column(conn, tabela, "clinica_id"):
        return [clinica_id]
    return []


# ============================================================
# API · ÚLTIMO ATENDIMENTO DO PACIENTE
# ============================================================

@atendimentos_bp.route("/api/ultimo_atendimento")
@require_permission("historico_atendimentos", "ver")
def api_ultimo_atendimento():
    clinica_id = _clinica_id_atual()
    paciente_id = (request.args.get("id") or "").strip()

    if not paciente_id:
        return jsonify({
            "ok": False,
            "error": "Parâmetro 'id' do paciente é obrigatório."
        }), 400

    try:
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

            filtro_clinica_atend = _filtro_clinica_sql(conn, "atendimentos", "a")
            params = [paciente_id] + _params_clinica(conn, "atendimentos", clinica_id)

            cur.execute(
                f"""
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
                FROM atendimentos a
                WHERE paciente_id = %s
                  {filtro_clinica_atend}
                ORDER BY
                    data_atendimento DESC NULLS LAST,
                    id DESC
                LIMIT 1
                """,
                params,
            )

            row = cur.fetchone()

            if not row:
                registrar_log(
                    modulo="historico_atendimentos",
                    acao="consultar",
                    entidade="atendimentos",
                    descricao="Consultou último atendimento sem resultado.",
                    detalhes={
                        "clinica_id": clinica_id,
                        "paciente_id": paciente_id,
                    },
                )

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

        registrar_log(
            modulo="historico_atendimentos",
            acao="consultar",
            entidade="atendimentos",
            entidade_id=atendimento_id,
            descricao="Consultou último atendimento do paciente.",
            detalhes={
                "clinica_id": clinica_id,
                "paciente_id": paciente_id,
                "atendimento_id": atendimento_id,
            },
        )

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

    except Exception as e:
        log_erro(
            "historico_atendimentos",
            e,
            entidade="atendimentos",
            descricao="Erro ao consultar último atendimento.",
            detalhes={
                "clinica_id": clinica_id,
                "paciente_id": paciente_id,
            },
        )
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# API · JSON COMPLETO DE UM ATENDIMENTO
# ============================================================

@atendimentos_bp.route("/<int:aid>.json", methods=["GET"])
@require_permission("historico_atendimentos", "ver")
def ver_atendimento_json(aid: int):
    clinica_id = _clinica_id_atual()

    try:
        with conectar_db() as conn:
            ensure_atendimentos_schema(conn)
            ensure_atendimento_procedimentos_schema(conn)

            if not has_table(conn, "atendimentos"):
                return jsonify({
                    "ok": False,
                    "error": "Tabela de atendimentos não encontrada."
                }), 404

            cur = conn.cursor()

            filtro_clinica_atend = _filtro_clinica_sql(conn, "atendimentos", "a")
            params = [aid] + _params_clinica(conn, "atendimentos", clinica_id)

            cur.execute(
                f"""
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
                    combo_plano_id,
                    COALESCE(cid_codigo, '') AS cid_codigo
                FROM atendimentos a
                WHERE id = %s
                  {filtro_clinica_atend}
                LIMIT 1
                """,
                params,
            )

            row = cur.fetchone()

            if not row:
                return jsonify({
                    "ok": False,
                    "error": "Atendimento não encontrado nesta clínica."
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
            cid_codigo = _row_get(row, "cid_codigo", 12, "") or ""

            prontuario = ""

            if paciente_id and has_table(conn, "pacientes") and has_column(conn, "pacientes", "prontuario"):
                filtro_clinica_pac = _filtro_clinica_sql(conn, "pacientes", "p")
                params_pac = [paciente_id] + _params_clinica(conn, "pacientes", clinica_id)

                cur.execute(
                    f"""
                    SELECT COALESCE(prontuario, '') AS prontuario
                    FROM pacientes p
                    WHERE id = %s
                      {filtro_clinica_pac}
                    LIMIT 1
                    """,
                    params_pac,
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

        registrar_log(
            modulo="historico_atendimentos",
            acao="visualizar",
            entidade="atendimentos",
            entidade_id=atendimento_id,
            descricao="Visualizou JSON completo de atendimento.",
            detalhes={
                "clinica_id": clinica_id,
                "atendimento_id": atendimento_id,
                "paciente_id": paciente_id,
            },
        )

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
            "cid_codigo": cid_codigo,
            "procedimento": primeiro_proc,
            "codigo_sigtap": primeiro_cod,
            "procedimentos": procs,
            "combo_plano_id": combo_plano_id,
            "combo": combo,
        })

    except Exception as e:
        log_erro(
            "historico_atendimentos",
            e,
            entidade="atendimentos",
            entidade_id=aid,
            descricao="Erro ao visualizar JSON completo de atendimento.",
            detalhes={
                "clinica_id": clinica_id,
                "atendimento_id": aid,
            },
        )
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# PÁGINA · HISTÓRICO
# ============================================================

@atendimentos_bp.route("/historico", methods=["GET"])
@require_permission("historico_atendimentos", "ver")
def historico_page():
    clinica_id = _clinica_id_atual()

    paciente_id = request.args.get("paciente_id")
    paciente_nome = request.args.get("paciente_nome", "")

    registrar_log(
        modulo="historico_atendimentos",
        acao="visualizar",
        entidade="atendimentos",
        descricao="Abriu página de histórico de atendimentos.",
        detalhes={
            "clinica_id": clinica_id,
            "paciente_id": paciente_id,
            "paciente_nome": paciente_nome,
        },
    )

    return render_template(
        "historico_atendimentos.html",
        data_hoje=date.today().isoformat(),
        paciente_id=paciente_id,
        paciente_nome=paciente_nome,
        clinica_id=clinica_id,
        clinica_nome=session.get("clinica_nome"),
    )


# ============================================================
# API · HISTÓRICO DO PACIENTE
# ============================================================

def _paciente_do_historico(conn, paciente_id: str, clinica_id: int) -> dict | None:
    """Dados de identificacao do paciente para o cabecalho do historico (mesmo modulo/permissao e mesmo isolamento por clinica)."""
    if not has_table(conn, "pacientes"):
        return None

    from .helpers import table_columns
    cols = table_columns(conn, "pacientes")
    sel = lambda c: f"COALESCE({c}::text, '')" if c in cols else "''"
    nasc = "nascimento" if "nascimento" in cols else ("data_nascimento" if "data_nascimento" in cols else None)
    filtro = _filtro_clinica_sql(conn, "pacientes", "p")
    params = [paciente_id] + _params_clinica(conn, "pacientes", clinica_id)

    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT id,
               COALESCE(nome, '') AS nome,
               {sel("prontuario")} AS prontuario,
               {sel(nasc) if nasc else "''"} AS nascimento,
               {sel("mod")} AS modalidade,
               {sel("status")} AS status,
               {sel("cid")} AS cid,
               {sel("cpf")} AS cpf,
               {sel("cns")} AS cns
          FROM pacientes p
         WHERE id = %s
           {filtro}
         LIMIT 1
        """,
        params,
    )
    r = cur.fetchone()
    if not r:
        return None

    return {
        "id": _row_get(r, "id", 0),
        "nome": _row_get(r, "nome", 1, "") or "",
        "prontuario": _row_get(r, "prontuario", 2, "") or "",
        "nascimento": (_row_get(r, "nascimento", 3, "") or "")[:10],
        "modalidade": _row_get(r, "modalidade", 4, "") or "",
        "status": _row_get(r, "status", 5, "") or "",
        "cid": _row_get(r, "cid", 6, "") or "",
        "cpf": _row_get(r, "cpf", 7, "") or "",
        "cns": _row_get(r, "cns", 8, "") or "",
    }


@atendimentos_bp.route("/api/historico")
@require_permission("historico_atendimentos", "ver")
def api_historico():
    """Historico do paciente: UM item por atendimento (os procedimentos vem numa lista) + dados do paciente.

    Antes a consulta fazia LEFT JOIN com os procedimentos e devolvia uma linha por procedimento: um atendimento com 3 procedimentos
    aparecia 3 vezes no historico."""
    clinica_id = _clinica_id_atual()
    paciente_id = (request.args.get("paciente_id") or "").strip()

    if not paciente_id.isdigit():
        return jsonify({
            "ok": False,
            "error": "Parâmetro 'paciente_id' é obrigatório."
        }), 400

    try:
        with conectar_db() as conn:
            ensure_atendimentos_schema(conn)
            ensure_atendimento_procedimentos_schema(conn)

            if not has_table(conn, "atendimentos"):
                return jsonify({"ok": True, "items": [], "paciente": None})

            paciente = _paciente_do_historico(conn, paciente_id, clinica_id)
            cur = conn.cursor()

            filtro_clinica_atend = _filtro_clinica_sql(conn, "atendimentos", "a")
            params = [paciente_id] + _params_clinica(conn, "atendimentos", clinica_id)

            cur.execute(
                f"""
                SELECT
                    a.id AS atendimento_id,
                    a.data_atendimento AS data_atendimento,
                    COALESCE(a.status, '') AS status,
                    COALESCE(a.justificativa, '') AS justificativa,
                    COALESCE(a.evolucao, '') AS evolucao,
                    COALESCE(a.anexo_atestado, '') AS anexo_atestado,
                    COALESCE(a.nome_profissional, '') AS nome_profissional,
                    COALESCE(a.cns_profissional, '') AS cns_profissional,
                    COALESCE(a.cbo_profissional, '') AS cbo_profissional,
                    a.combo_plano_id,
                    COALESCE(a.cid_codigo, '') AS cid_codigo
                FROM atendimentos a
                WHERE a.paciente_id = %s
                  {filtro_clinica_atend}
                ORDER BY
                    a.data_atendimento DESC NULLS LAST,
                    a.id DESC
                LIMIT 400
                """,
                params,
            )

            rows = cur.fetchall() or []
            ids = [_row_get(r, "atendimento_id", 0) for r in rows]

            procs_por_atend: dict = {}
            if ids and has_table(conn, "atendimento_procedimentos"):
                cur.execute(
                    """
                    SELECT atendimento_id,
                           COALESCE(procedimento, '') AS procedimento,
                           COALESCE(codigo_sigtap, '') AS codigo_sigtap
                      FROM atendimento_procedimentos
                     WHERE atendimento_id = ANY(%s)
                     ORDER BY atendimento_id, id
                    """,
                    (ids,),
                )
                for pr in (cur.fetchall() or []):
                    procs_por_atend.setdefault(_row_get(pr, "atendimento_id", 0), []).append({
                        "procedimento": _row_get(pr, "procedimento", 1, "") or "",
                        "codigo_sigtap": _row_get(pr, "codigo_sigtap", 2, "") or "",
                    })

        registrar_log(
            modulo="historico_atendimentos",
            acao="consultar",
            entidade="atendimentos",
            descricao="Consultou histórico do paciente.",
            detalhes={
                "clinica_id": clinica_id,
                "paciente_id": paciente_id,
                "total": len(rows),
            },
        )

        itens = []
        for r in rows:
            aid = _row_get(r, "atendimento_id", 0)
            procs = procs_por_atend.get(aid, [])
            itens.append({
                "atendimento_id": aid,
                "data_atendimento": str(_row_get(r, "data_atendimento", 1) or "")[:10],
                "status": _row_get(r, "status", 2, "") or "",
                "justificativa": _row_get(r, "justificativa", 3, "") or "",
                "evolucao": _row_get(r, "evolucao", 4, "") or "",
                "anexo_atestado": _row_get(r, "anexo_atestado", 5, "") or "",
                "profissional": _row_get(r, "nome_profissional", 6, "") or "—",
                "profissional_cns": _row_get(r, "cns_profissional", 7, "") or "",
                "profissional_cbo": _row_get(r, "cbo_profissional", 8, "") or "",
                "combo_plano_id": _row_get(r, "combo_plano_id", 9),
                "cid_codigo": _row_get(r, "cid_codigo", 10, "") or "",
                "procedimentos": procs,
                # compat: o primeiro procedimento nos campos antigos
                "procedimento": procs[0]["procedimento"] if procs else "",
                "codigo_sigtap": procs[0]["codigo_sigtap"] if procs else "",
            })

        return jsonify({"ok": True, "paciente": paciente, "items": itens})

    except Exception as e:
        log_erro(
            "historico_atendimentos",
            e,
            entidade="atendimentos",
            descricao="Erro ao consultar histórico do paciente.",
            detalhes={
                "clinica_id": clinica_id,
                "paciente_id": paciente_id,
            },
        )
        return jsonify({"ok": False, "error": "Não foi possível carregar o histórico agora."}), 500

