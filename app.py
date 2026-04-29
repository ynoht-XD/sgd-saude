from __future__ import annotations

from datetime import date

from flask import Flask, render_template, session, request, redirect, url_for

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

from db import conectar_db

app = Flask(__name__)
app.secret_key = "uma_chave_ultra_secreta_123"
app.config["TEMPLATES_AUTO_RELOAD"] = True


# ============================================================
#  REGISTRO DOS BLUEPRINTS
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


# ============================================================
#  ENDPOINTS PÚBLICOS
# ============================================================

PUBLIC_ENDPOINTS = {
    "auth.login",
    "auth.logout",
    "static",
}


@app.before_request
def require_login_globally():
    ep = request.endpoint or ""

    if ep.startswith("auth.") or ep in PUBLIC_ENDPOINTS or ep.endswith(".static"):
        return

    if not session.get("user_id"):
        return redirect(url_for("auth.login", next=request.path))


# ============================================================
#  HELPERS POSTGRES
# ============================================================

def _val(row, key: str, index: int = 0, default=None):
    """
    Compatibilidade:
    - psycopg com dict_row retorna dict
    - cursor comum retorna tuple/list
    """
    if not row:
        return default

    if isinstance(row, dict):
        return row.get(key, default)

    try:
        return row[index]
    except Exception:
        return default


def _dict_fetchall(cur):
    rows = cur.fetchall() or []

    if not rows:
        return []

    if isinstance(rows[0], dict):
        return [dict(r) for r in rows]

    cols = [c[0] for c in cur.description] if cur.description else []
    return [dict(zip(cols, row)) for row in rows]


def _dict_fetchone(cur):
    row = cur.fetchone()

    if not row:
        return None

    if isinstance(row, dict):
        return dict(row)

    cols = [c[0] for c in cur.description] if cur.description else []
    return dict(zip(cols, row))


def _has_table(conn, name: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 1 AS existe
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = %s
        LIMIT 1;
        """,
        (name,),
    )

    row = cur.fetchone()
    cur.close()

    return row is not None


def _cols(conn, table: str) -> set[str]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
        ORDER BY ordinal_position;
        """,
        (table,),
    )

    rows = cur.fetchall() or []
    cur.close()

    return {
        _val(r, "column_name", 0)
        for r in rows
        if _val(r, "column_name", 0)
    }


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


# ============================================================
#  HOME
# ============================================================

@app.route("/")
def index():
    comp = _competencia_atual()
    hoje_iso = _today_iso()
    hoje_dia = _today_dow_pt()
    hoje_dow_dom = _today_dow_dom()

    conn = conectar_db()
    cur = conn.cursor()

    try:
        # ------------------------------
        # 1) PACIENTES: ATIVOS e ESPERA
        # ------------------------------
        pacientes_table = (
            "pacientes"
            if _has_table(conn, "pacientes")
            else ("pacinetes" if _has_table(conn, "pacinetes") else None)
        )

        ativos = 0
        espera = 0

        if pacientes_table:
            pc = _cols(conn, pacientes_table)
            col_status = _first_existing(pc, ["status", "situacao", "situacao_status"])

            if col_status:
                cur.execute(
                    f"""
                    SELECT COUNT(*) AS total
                    FROM {pacientes_table}
                    WHERE UPPER(TRIM(COALESCE({col_status}, ''))) IN ('ATIVO', 'ATIVOS')
                    """
                )
                ativos = int(_val(cur.fetchone(), "total", 0, 0) or 0)

                cur.execute(
                    f"""
                    SELECT COUNT(*) AS total
                    FROM {pacientes_table}
                    WHERE UPPER(TRIM(COALESCE({col_status}, ''))) LIKE 'ESPERA%%'
                    """
                )
                espera = int(_val(cur.fetchone(), "total", 0, 0) or 0)

        # ------------------------------------------
        # 2) PROCEDIMENTOS REALIZADOS NA COMPETÊNCIA
        # ------------------------------------------
        procedimentos_comp = 0
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
                cur.execute(
                    f"""
                    SELECT COUNT(*) AS total
                    FROM {aproc_table} ap
                    JOIN atendimentos a ON a.id = ap.atendimento_id
                    WHERE {_where_competencia_sql(f"a.{col_data_at}")}
                    """,
                    (comp,),
                )
                procedimentos_comp = int(_val(cur.fetchone(), "total", 0, 0) or 0)

            if procedimentos_comp == 0 and col_data_at:
                cur.execute(
                    f"""
                    SELECT COUNT(*) AS total
                    FROM atendimentos a
                    WHERE {_where_competencia_sql(f"a.{col_data_at}")}
                    """,
                    (comp,),
                )
                procedimentos_comp = int(_val(cur.fetchone(), "total", 0, 0) or 0)

        # ------------------------------------------
        # 3) ATENDIMENTOS POR PROFISSIONAL
        # ------------------------------------------
        atend_por_prof = []

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

                cur.execute(
                    f"""
                    SELECT
                        {profissional_expr} AS profissional,
                        COUNT(*) AS qtd
                    FROM atendimentos a
                    {join_usuarios}
                    WHERE {_where_competencia_sql(f"a.{col_data_at}")}
                    GROUP BY profissional
                    ORDER BY qtd DESC, profissional ASC
                    LIMIT 50
                    """,
                    (comp,),
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
        agendados_hoje = []

        if _has_table(conn, "agendamentos"):
            gc = _cols(conn, "agendamentos")

            has_inicio = "inicio" in gc
            has_status = "status" in gc
            has_prof_cpf = "profissional_cpf" in gc
            has_dia_txt = "dia" in gc
            has_dow_dom = "dow_dom" in gc

            where_parts = []
            params = []

            if has_inicio:
                where_parts.append("DATE(a.inicio::timestamp) = %s")
                params.append(hoje_iso)

            if has_dia_txt:
                where_parts.append("LOWER(TRIM(COALESCE(a.dia, ''))) = %s")
                params.append(hoje_dia)

            if has_dow_dom:
                where_parts.append("a.dow_dom = %s")
                params.append(hoje_dow_dom)

            status_sql = ""
            if has_status:
                status_sql = " AND (a.status IS NULL OR LOWER(TRIM(a.status)) = 'ativo') "

            where_sql = " OR ".join([f"({w})" for w in where_parts]) if where_parts else "FALSE"

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
                WHERE ({where_sql})
                {status_sql}
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

    finally:
        cur.close()
        conn.close()

    return render_template(
        "index.html",
        competencia=comp,
        hoje_iso=hoje_iso,
        hoje_dia=hoje_dia,
        kpi_ativos=ativos,
        kpi_espera=espera,
        kpi_procedimentos=procedimentos_comp,
        atend_por_prof=atend_por_prof,
        agendados_hoje=agendados_hoje,
    )


# ============================================================
#  HANDLERS DE ERROS
# ============================================================

@app.errorhandler(403)
def forbidden(_e):
    return "Acesso negado (403). Faça login com um usuário autorizado para acessar esta área.", 403


@app.errorhandler(404)
def not_found(_e):
    return "Página não encontrada (404).", 404


@app.context_processor
def inject_permissions():
    def can_modulo(modulo_codigo, acao="ver"):
        try:
            from admin.modulos import usuario_tem_permissao, usuario_eh_master

            if usuario_eh_master():
                return True

            usuario_id = session.get("user_id") or session.get("usuario_id")
            clinica_id = session.get("clinica_id") or 1

            if not usuario_id:
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

    return {"can_modulo": can_modulo}


# ============================================================
#  MAIN
# ============================================================

if __name__ == "__main__":
    app.run(debug=True, port=5001)