from __future__ import annotations

import os
from datetime import date

from flask import (
    Flask, render_template, session, request,
    redirect, url_for, g
)

# Blueprints principais
from agenda import agenda_bp
from cadastro import cadastro_bp
from atendimentos import atendimentos_bp
from pacientes import pacientes_bp
from export import export_bp
from admin import admin_bp
from auth import auth_bp
from rh import rh_bp
from financeiro import financeiro_bp
from digitador import digitador_bp
from auditivo import auditivo_bp
from registros import registros_bp
from pts import pts_bp
from meus_atendimentos import meus_atendimentos_bp
from procedimentos import procedimentos_bp
from avaliacoes import avaliacoes_bp
from agenda_medica import agenda_medica_bp
from clinica_config import clinica_config_bp
from logs import logs_bp

from db import conectar_db


app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "uma_chave_ultra_secreta_123")
app.config["TEMPLATES_AUTO_RELOAD"] = True


# ============================================================
# REGISTRO DOS BLUEPRINTS
# ============================================================

app.register_blueprint(agenda_bp, url_prefix="/agenda")
app.register_blueprint(cadastro_bp)
app.register_blueprint(atendimentos_bp)
app.register_blueprint(pacientes_bp)
app.register_blueprint(export_bp, url_prefix="/export")
app.register_blueprint(admin_bp, url_prefix="/admin")
app.register_blueprint(auth_bp, url_prefix="/auth")
app.register_blueprint(rh_bp)
app.register_blueprint(financeiro_bp)
app.register_blueprint(digitador_bp)
app.register_blueprint(auditivo_bp)
app.register_blueprint(registros_bp, url_prefix="/registros")
app.register_blueprint(procedimentos_bp)
app.register_blueprint(pts_bp)
app.register_blueprint(meus_atendimentos_bp)
app.register_blueprint(avaliacoes_bp)
app.register_blueprint(agenda_medica_bp)
app.register_blueprint(clinica_config_bp)
app.register_blueprint(logs_bp)

# ============================================================
# ENDPOINTS PÚBLICOS
# ============================================================

PUBLIC_ENDPOINTS = {
    "auth.login",
    "auth.logout",
    "static",
}


# ============================================================
# HELPERS POSTGRES / GERAIS
# ============================================================

def _val(row, key: str, index: int = 0, default=None):
    if not row:
        return default

    if isinstance(row, dict) or hasattr(row, "keys"):
        return dict(row).get(key, default)

    try:
        return row[index]
    except Exception:
        return default


def _dict_fetchall(cur):
    rows = cur.fetchall() or []

    if not rows:
        return []

    if isinstance(rows[0], dict) or hasattr(rows[0], "keys"):
        return [dict(r) for r in rows]

    cols = [c[0] for c in cur.description] if cur.description else []
    return [dict(zip(cols, row)) for row in rows]


def _dict_fetchone(cur):
    row = cur.fetchone()

    if not row:
        return None

    if isinstance(row, dict) or hasattr(row, "keys"):
        return dict(row)

    cols = [c[0] for c in cur.description] if cur.description else []
    return dict(zip(cols, row))


def _has_table(conn, name: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = %s
            LIMIT 1;
        """, (name,))
        return cur.fetchone() is not None
    finally:
        cur.close()


def _cols(conn, table: str) -> set[str]:
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
            ORDER BY ordinal_position;
        """, (table,))

        rows = cur.fetchall() or []

        return {
            _val(r, "column_name", 0)
            for r in rows
            if _val(r, "column_name", 0)
        }
    finally:
        cur.close()


def _first_existing(cols: set[str], options: list[str]) -> str | None:
    for c in options:
        if c in cols:
            return c
    return None


def _competencia_atual() -> str:
    return date.today().strftime("%Y-%m")


def _where_competencia_sql(col: str) -> str:
    return f"TO_CHAR({col}::timestamp, 'YYYY-MM') = %s"


def _today_iso() -> str:
    return date.today().isoformat()


def _today_dow_pt() -> str:
    return ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"][date.today().weekday()]


def _today_dow_dom() -> int:
    wd = date.today().weekday()
    return 0 if wd == 6 else wd + 1


def _session_user_id():
    return session.get("user_id") or session.get("usuario_id")


def _session_clinica_id(default: int | None = 1) -> int | None:
    val = session.get("clinica_id") or session.get("clinic_id") or default

    try:
        return int(val) if val is not None else None
    except Exception:
        return default


def _add_clinica_filter(conn, table: str, alias: str, where: list[str], params: list, clinica_id: int | None):
    if not clinica_id:
        return

    if not _has_table(conn, table):
        return

    cols = _cols(conn, table)

    if "clinica_id" in cols:
        where.append(f"{alias}.clinica_id = %s")
        params.append(int(clinica_id))


def _registrar_log_app(acao: str, modulo: str = "app", detalhes: str = "", sucesso: bool = True):
    try:
        conn = conectar_db()

        if not _has_table(conn, "logs"):
            conn.close()
            return

        cols = _cols(conn, "logs")
        cur = conn.cursor()

        campos = []
        valores = []
        params = []

        def add(campo, valor):
            if campo in cols:
                campos.append(campo)
                valores.append("%s")
                params.append(valor)

        add("usuario_id", _session_user_id())
        add("clinica_id", _session_clinica_id(None))
        add("modulo", modulo)
        add("acao", acao)
        add("detalhes", detalhes)
        add("sucesso", sucesso)

        if "created_at" in cols:
            campos.append("created_at")
            valores.append("CURRENT_TIMESTAMP")
        elif "criado_em" in cols:
            campos.append("criado_em")
            valores.append("CURRENT_TIMESTAMP")

        if campos:
            cur.execute(
                f"""
                INSERT INTO logs ({", ".join(campos)})
                VALUES ({", ".join(valores)})
                """,
                params,
            )
            conn.commit()

        cur.close()
        conn.close()

    except Exception as e:
        print("⚠️ Erro ao registrar log app:", e)


# ============================================================
# BEFORE REQUEST · LOGIN / CLÍNICA / MÓDULOS
# ============================================================

@app.before_request
def setup_request_context():
    ep = request.endpoint or ""

    if ep.startswith("auth.") or ep in PUBLIC_ENDPOINTS or ep.endswith(".static"):
        return

    if not _session_user_id():
        return redirect(url_for("auth.login", next=request.full_path or request.path))

    # Garante contexto mínimo de clínica.
    # Se teu login já coloca session["clinica_id"], isso só reaproveita.
    if not session.get("clinica_id"):
        session["clinica_id"] = 1

    g.usuario_id = _session_user_id()
    g.clinica_id = _session_clinica_id(1)

    # Prepara módulos, se disponível.
    try:
        from admin.modulos import preparar_modulos
        preparar_modulos()
    except Exception as e:
        print("⚠️ Não foi possível preparar módulos:", e)


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


# ============================================================
# HOME
# ============================================================

@app.route("/")
def index():
    comp = _competencia_atual()
    hoje_iso = _today_iso()
    hoje_dia = _today_dow_pt()
    hoje_dow_dom = _today_dow_dom()

    clinica_id = _session_clinica_id(1)

    conn = conectar_db()
    cur = conn.cursor()

    ativos = 0
    espera = 0
    procedimentos_comp = 0
    atend_por_prof = []
    agendados_hoje = []

    try:
        # ------------------------------
        # 1) PACIENTES: ATIVOS e ESPERA
        # ------------------------------
        pacientes_table = (
            "pacientes"
            if _has_table(conn, "pacientes")
            else ("pacinetes" if _has_table(conn, "pacinetes") else None)
        )

        if pacientes_table:
            pc = _cols(conn, pacientes_table)
            col_status = _first_existing(pc, ["status", "situacao", "situacao_status"])

            if col_status:
                where = [
                    f"UPPER(TRIM(COALESCE({col_status}, ''))) IN ('ATIVO', 'ATIVOS')"
                ]
                params = []

                _add_clinica_filter(conn, pacientes_table, pacientes_table, where, params, clinica_id)

                cur.execute(
                    f"""
                    SELECT COUNT(*) AS total
                    FROM {pacientes_table}
                    WHERE {" AND ".join(where)}
                    """,
                    params,
                )
                ativos = int(_val(cur.fetchone(), "total", 0, 0) or 0)

                where = [
                    f"UPPER(TRIM(COALESCE({col_status}, ''))) LIKE 'ESPERA%%'"
                ]
                params = []

                _add_clinica_filter(conn, pacientes_table, pacientes_table, where, params, clinica_id)

                cur.execute(
                    f"""
                    SELECT COUNT(*) AS total
                    FROM {pacientes_table}
                    WHERE {" AND ".join(where)}
                    """,
                    params,
                )
                espera = int(_val(cur.fetchone(), "total", 0, 0) or 0)

        # ------------------------------------------
        # 2) PROCEDIMENTOS REALIZADOS NA COMPETÊNCIA
        # ------------------------------------------
        has_atend = _has_table(conn, "atendimentos")
        has_aproc = (
            _has_table(conn, "atendimento_procedimentos")
            or _has_table(conn, "atendimento_procedimento")
        )

        aproc_table = (
            "atendimento_procedimentos"
            if _has_table(conn, "atendimento_procedimentos")
            else "atendimento_procedimento"
        )

        if has_atend:
            ac = _cols(conn, "atendimentos")
            col_data_at = _first_existing(ac, ["data_atendimento", "criado_em", "created_at", "data"])

            if has_aproc and col_data_at:
                where = [_where_competencia_sql(f"a.{col_data_at}")]
                params = [comp]
                _add_clinica_filter(conn, "atendimentos", "a", where, params, clinica_id)

                cur.execute(
                    f"""
                    SELECT COUNT(*) AS total
                    FROM {aproc_table} ap
                    JOIN atendimentos a ON a.id = ap.atendimento_id
                    WHERE {" AND ".join(where)}
                    """,
                    params,
                )
                procedimentos_comp = int(_val(cur.fetchone(), "total", 0, 0) or 0)

            if procedimentos_comp == 0 and col_data_at:
                where = [_where_competencia_sql(f"a.{col_data_at}")]
                params = [comp]
                _add_clinica_filter(conn, "atendimentos", "a", where, params, clinica_id)

                cur.execute(
                    f"""
                    SELECT COUNT(*) AS total
                    FROM atendimentos a
                    WHERE {" AND ".join(where)}
                    """,
                    params,
                )
                procedimentos_comp = int(_val(cur.fetchone(), "total", 0, 0) or 0)

        # ------------------------------------------
        # 3) ATENDIMENTOS POR PROFISSIONAL
        # ------------------------------------------
        if has_atend and _has_table(conn, "usuarios"):
            ac = _cols(conn, "atendimentos")
            uc = _cols(conn, "usuarios")

            col_data_at = _first_existing(ac, ["data_atendimento", "criado_em", "created_at", "data"])
            has_prof_id = "profissional_id" in ac
            has_nome_prof_atend = "nome_profissional" in ac
            has_u_nome = "nome" in uc

            if col_data_at:
                join_usuarios = ""
                profissional_expr = "'—'"

                if has_prof_id and has_u_nome:
                    if "profissional_id" in uc:
                        join_usuarios = """
                            LEFT JOIN usuarios u
                                ON u.id = a.profissional_id
                                OR u.profissional_id = a.profissional_id
                        """
                    else:
                        join_usuarios = """
                            LEFT JOIN usuarios u
                                ON u.id = a.profissional_id
                        """

                    if has_nome_prof_atend:
                        profissional_expr = "COALESCE(u.nome, NULLIF(TRIM(COALESCE(a.nome_profissional, '')), ''), '—')"
                    else:
                        profissional_expr = "COALESCE(u.nome, '—')"

                elif has_nome_prof_atend:
                    profissional_expr = "COALESCE(NULLIF(TRIM(a.nome_profissional), ''), '—')"

                where = [_where_competencia_sql(f"a.{col_data_at}")]
                params = [comp]
                _add_clinica_filter(conn, "atendimentos", "a", where, params, clinica_id)

                cur.execute(
                    f"""
                    SELECT
                        {profissional_expr} AS profissional,
                        COUNT(*) AS qtd
                    FROM atendimentos a
                    {join_usuarios}
                    WHERE {" AND ".join(where)}
                    GROUP BY profissional
                    ORDER BY qtd DESC, profissional ASC
                    LIMIT 50
                    """,
                    params,
                )

                atend_por_prof = [
                    {
                        "profissional": _val(r, "profissional", 0, "—"),
                        "qtd": int(_val(r, "qtd", 1, 0) or 0),
                    }
                    for r in cur.fetchall()
                ]

        # ------------------------------------------
        # 4) AGENDADOS DE HOJE
        # ------------------------------------------
        if _has_table(conn, "agendamentos"):
            gc = _cols(conn, "agendamentos")

            has_inicio = "inicio" in gc
            has_status = "status" in gc
            has_prof_cpf = "profissional_cpf" in gc
            has_dia_txt = "dia" in gc
            has_dow_dom = "dow_dom" in gc

            day_parts = []
            params = []

            if has_inicio:
                day_parts.append("DATE(a.inicio::timestamp) = %s")
                params.append(hoje_iso)

            if has_dia_txt:
                day_parts.append("LOWER(TRIM(COALESCE(a.dia, ''))) = %s")
                params.append(hoje_dia)

            if has_dow_dom:
                day_parts.append("a.dow_dom = %s")
                params.append(hoje_dow_dom)

            where = [f"({' OR '.join(day_parts)})" if day_parts else "FALSE"]

            if has_status:
                where.append("(a.status IS NULL OR LOWER(TRIM(a.status)) = 'ativo')")

            _add_clinica_filter(conn, "agendamentos", "a", where, params, clinica_id)

            join_usuarios = ""
            select_prof_nome = "TRIM(COALESCE(a.profissional, '')) AS profissional_nome"

            if _has_table(conn, "usuarios") and has_prof_cpf:
                join_usuarios = """
                    LEFT JOIN usuarios u
                        ON u.cpf_digits = REGEXP_REPLACE(COALESCE(a.profissional_cpf, ''), '[^0-9]', '', 'g')
                """
                select_prof_nome = "COALESCE(u.nome, TRIM(COALESCE(a.profissional, ''))) AS profissional_nome"

            cur.execute(
                f"""
                SELECT DISTINCT
                       a.id,
                       TRIM(COALESCE(a.paciente, '')) AS paciente,
                       {select_prof_nome},
                       TRIM(COALESCE(a.profissional, '')) AS profissional_raw,
                       TRIM(COALESCE(a.profissional_cpf, '')) AS profissional_cpf,
                       TO_CHAR(a.inicio::timestamp, 'HH24:MI') AS hora_ini,
                       TO_CHAR(a.fim::timestamp, 'HH24:MI') AS hora_fim,
                       TRIM(COALESCE(a.observacao, '')) AS observacao,
                       TRIM(COALESCE(a.status, '')) AS status
                FROM agendamentos a
                {join_usuarios}
                WHERE {" AND ".join(where)}
                ORDER BY hora_ini ASC, profissional_nome ASC, paciente ASC
                LIMIT 200
                """,
                tuple(params),
            )

            agendados_hoje = [
                {
                    "id": _val(r, "id", 0),
                    "paciente": _val(r, "paciente", 1, ""),
                    "profissional_nome": _val(r, "profissional_nome", 2, ""),
                    "profissional_raw": _val(r, "profissional_raw", 3, ""),
                    "profissional_cpf": _val(r, "profissional_cpf", 4, ""),
                    "hora_ini": _val(r, "hora_ini", 5, "") or "",
                    "hora_fim": _val(r, "hora_fim", 6, "") or "",
                    "observacao": _val(r, "observacao", 7, ""),
                    "status": _val(r, "status", 8, ""),
                }
                for r in cur.fetchall()
            ]

        _registrar_log_app(
            acao="VISUALIZAR_DASHBOARD",
            modulo="dashboard",
            detalhes=f"Dashboard visualizado. clinica_id={clinica_id}",
        )

    except Exception as e:
        _registrar_log_app(
            acao="ERRO_DASHBOARD",
            modulo="dashboard",
            detalhes=str(e),
            sucesso=False,
        )
        raise

    finally:
        cur.close()
        conn.close()

    return render_template(
        "index.html",
        competencia=comp,
        hoje_iso=hoje_iso,
        hoje_dia=hoje_dia,
        clinica_id=clinica_id,
        kpi_ativos=ativos,
        kpi_espera=espera,
        kpi_procedimentos=procedimentos_comp,
        atend_por_prof=atend_por_prof,
        agendados_hoje=agendados_hoje,
    )


# ============================================================
# CONTEXT PROCESSOR · MÓDULOS / CLÍNICA
# ============================================================

@app.context_processor
def inject_permissions():
    def can_modulo(modulo_codigo, acao="ver"):
        try:
            from admin.modulos import usuario_tem_permissao, usuario_eh_master

            if usuario_eh_master():
                return True

            usuario_id = _session_user_id()
            clinica_id = _session_clinica_id(1)

            if not usuario_id or not clinica_id:
                return False

            return usuario_tem_permissao(
                usuario_id=int(usuario_id),
                clinica_id=int(clinica_id),
                modulo_codigo=modulo_codigo,
                acao=acao,
            )

        except Exception as e:
            print("⚠️ Erro no can_modulo:", e)
            return False

    return {
        "can_modulo": can_modulo,
        "clinica_id_atual": _session_clinica_id(1),
        "usuario_id_atual": _session_user_id(),
    }


# ============================================================
# HANDLERS DE ERROS
# ============================================================

@app.errorhandler(403)
def forbidden(e):
    _registrar_log_app(
        acao="ERRO_403",
        modulo="app",
        detalhes=f"endpoint={request.endpoint}; path={request.path}",
        sucesso=False,
    )
    return "Acesso negado (403). Faça login com um usuário autorizado para acessar esta área.", 403


@app.errorhandler(404)
def not_found(e):
    return "Página não encontrada (404).", 404


@app.errorhandler(500)
def internal_error(e):
    _registrar_log_app(
        acao="ERRO_500",
        modulo="app",
        detalhes=f"endpoint={request.endpoint}; path={request.path}; erro={e}",
        sucesso=False,
    )
    return "Erro interno no servidor (500).", 500


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    app.run(debug=True, port=5001)