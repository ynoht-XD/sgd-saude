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

app = Flask(__name__)
app.secret_key = 'uma_chave_ultra_secreta_123'
app.config['TEMPLATES_AUTO_RELOAD'] = True


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


# ============================================================
#  ENDPOINTS PÚBLICOS (sem login obrigatório)
# ============================================================

PUBLIC_ENDPOINTS = {
    "auth.login",
    "auth.logout",
    "static",   # /static global
}


@app.before_request
def require_login_globally():
    """
    Exige login para todas as rotas,
    exceto as públicas + auth + arquivos estáticos.
    """
    ep = request.endpoint or ""

    # libera:
    # - auth.*
    # - endpoints declarados em PUBLIC_ENDPOINTS
    # - qualquer endpoint .static
    if ep.startswith("auth.") or ep in PUBLIC_ENDPOINTS or ep.endswith(".static"):
        return

    # usuario não logado → envia pro login
    if not session.get("user_id"):
        return redirect(url_for("auth.login", next=request.path))


# ============================================================
#  HOME
# ============================================================
from datetime import date
import sqlite3
from flask import render_template

from db import conectar_db  # teu conector unificado

def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=? LIMIT 1;", (name,))
    return cur.fetchone() is not None

def _cols(conn: sqlite3.Connection, table: str) -> set[str]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table});")
    return {r[1] for r in cur.fetchall()}

def _first_existing(cols: set[str], options: list[str]) -> str | None:
    for c in options:
        if c in cols:
            return c
    return None

def _competencia_atual() -> str:
    return date.today().strftime("%Y-%m")

def _where_competencia_sql(col: str) -> str:
    return f"strftime('%Y-%m', {col}) = ?"

def _today_iso() -> str:
    return date.today().isoformat()

def _today_dow_pt() -> str:
    # segunda..domingo (pra bater com tua coluna agendamentos.dia, se ela guardar texto)
    return ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"][date.today().weekday()]

def _today_dow_dom() -> int:
    # dow_dom (0..6) com 0=domingo, 1=segunda, ..., 6=sábado
    # Python weekday(): 0=segunda..6=domingo
    wd = date.today().weekday()  # 0..6 (seg..dom)
    return 0 if wd == 6 else wd + 1

@app.route("/")
def index():
    comp = _competencia_atual()
    hoje_iso = _today_iso()
    hoje_dia = _today_dow_pt()
    hoje_dow_dom = _today_dow_dom()

    conn = conectar_db()
    cur = conn.cursor()

    # ------------------------------
    # 1) PACIENTES: ATIVOS e ESPERA
    # ------------------------------
    pacientes_table = "pacientes" if _has_table(conn, "pacientes") else ("pacinetes" if _has_table(conn, "pacinetes") else None)

    ativos = 0
    espera = 0

    if pacientes_table:
        pc = _cols(conn, pacientes_table)
        col_status = _first_existing(pc, ["status", "situacao", "situacao_status"])
        if col_status:
            cur.execute(
                f"""
                SELECT COUNT(*)
                  FROM {pacientes_table}
                 WHERE UPPER(TRIM(COALESCE({col_status},''))) IN ('ATIVO','ATIVOS')
                """
            )
            ativos = int(cur.fetchone()[0] or 0)

            cur.execute(
                f"""
                SELECT COUNT(*)
                  FROM {pacientes_table}
                 WHERE UPPER(TRIM(COALESCE({col_status},''))) LIKE 'ESPERA%'
                """
            )
            espera = int(cur.fetchone()[0] or 0)

    # ------------------------------------------
    # 2) PROCEDIMENTOS REALIZADOS NA COMPETÊNCIA
    # ------------------------------------------
    procedimentos_comp = 0
    has_atend = _has_table(conn, "atendimentos")
    has_itens = _has_table(conn, "atendimentos_itens")

    if has_atend:
        ac = _cols(conn, "atendimentos")
        col_data_at = _first_existing(ac, ["data", "data_atendimento", "data_realizada", "criado_em", "created_at", "inicio"])

        if has_itens:
            ic = _cols(conn, "atendimentos_itens")
            col_fk = _first_existing(ic, ["atendimento_id", "atendimentos_id", "id_atendimento"])
            col_data_item = _first_existing(ic, ["data", "data_realizada", "criado_em", "created_at"])

            if col_fk and (col_data_item or col_data_at):
                if col_data_item:
                    where_comp = _where_competencia_sql(f"i.{col_data_item}")
                    cur.execute(
                        f"SELECT COUNT(*) FROM atendimentos_itens i WHERE {where_comp}",
                        (comp,)
                    )
                else:
                    where_comp = _where_competencia_sql(f"a.{col_data_at}")
                    cur.execute(
                        f"""
                        SELECT COUNT(*)
                          FROM atendimentos_itens i
                          JOIN atendimentos a ON a.id = i.{col_fk}
                         WHERE {where_comp}
                        """,
                        (comp,)
                    )
                procedimentos_comp = int(cur.fetchone()[0] or 0)

        if procedimentos_comp == 0 and col_data_at:
            where_comp = _where_competencia_sql(col_data_at)
            cur.execute(
                f"SELECT COUNT(*) FROM atendimentos WHERE {where_comp}",
                (comp,)
            )
            procedimentos_comp = int(cur.fetchone()[0] or 0)

    # ------------------------------------------
    # 2) PROCEDIMENTOS REALIZADOS NA COMPETÊNCIA
    #    (tabela: atendimento_procedimento)
    # ------------------------------------------
    procedimentos_comp = 0

    has_atend = _has_table(conn, "atendimentos")
    has_aproc = _has_table(conn, "atendimento_procedimento")

    if has_atend:
        ac = _cols(conn, "atendimentos")
        col_data_at = _first_existing(ac, ["data_atendimento", "criado_em"])

        if has_aproc and col_data_at:
            # 1 linha em atendimento_procedimento = 1 procedimento realizado
            cur.execute(
                f"""
                SELECT COUNT(*)
                FROM atendimento_procedimento ap
                JOIN atendimentos a ON a.id = ap.atendimento_id
                WHERE {_where_competencia_sql(f"a.{col_data_at}")}
                """,
                (comp,)
            )
            procedimentos_comp = int(cur.fetchone()[0] or 0)

        # fallback: se não tiver tabela de procedimentos por item
        if procedimentos_comp == 0 and col_data_at:
            cur.execute(
                f"""
                SELECT COUNT(*)
                FROM atendimentos a
                WHERE {_where_competencia_sql(f"a.{col_data_at}")}
                """,
                (comp,)
            )
            procedimentos_comp = int(cur.fetchone()[0] or 0)

    # ------------------------------------------
    # 3) ATENDIMENTOS POR PROFISSIONAL (NOME!)
    #    JOIN: atendimentos.profissional_id -> usuarios.id (ou usuarios.profissional_id)
    # ------------------------------------------
    atend_por_prof = []

    if has_atend and _has_table(conn, "usuarios"):
        ac = _cols(conn, "atendimentos")
        uc = _cols(conn, "usuarios")

        col_data_at = _first_existing(ac, ["data_atendimento", "criado_em"])
        has_prof_id = "profissional_id" in ac
        has_u_nome  = "nome" in uc

        if col_data_at and has_prof_id and has_u_nome:
            cur.execute(
                f"""
                SELECT
                    COALESCE(u.nome, NULLIF(TRIM(COALESCE(a.nome_profissional,'')), ''), '—') AS profissional,
                    COUNT(*) AS qtd
                FROM atendimentos a
            LEFT JOIN usuarios u
                    ON (u.id = a.profissional_id)
                    OR (u.profissional_id IS NOT NULL AND u.profissional_id = a.profissional_id)
                WHERE {_where_competencia_sql(f"a.{col_data_at}")}
                GROUP BY profissional
                ORDER BY qtd DESC, profissional ASC
                LIMIT 50
                """,
                (comp,)
            )
            atend_por_prof = [{"profissional": r[0], "qtd": int(r[1] or 0)} for r in cur.fetchall()]


    # ------------------------------------------
    # 4) AGENDADOS DE HOJE (com nome do prof via usuarios)
    #    Regras:
    #    - primeiro tenta por data: date(inicio)=hoje
    #    - se tua agenda usa "dia"/"dow_dom" (recorrência), também busca por isso
    # ------------------------------------------
    agendados_hoje = []

    if _has_table(conn, "agendamentos"):
        gc = _cols(conn, "agendamentos")

        # colunas essenciais
        has_inicio = "inicio" in gc
        has_status = "status" in gc
        has_prof_cpf = "profissional_cpf" in gc
        has_dia_txt = "dia" in gc
        has_dow_dom = "dow_dom" in gc

        # Vamos montar uma query que:
        # (A) pega agendamentos do dia por date(inicio)=?
        # (B) também inclui recorrentes fixados por "dia" OU "dow_dom" se existir
        # Evita duplicar usando DISTINCT por id.
        where_parts = []
        params = []

        if has_inicio:
            where_parts.append("date(a.inicio) = ?")
            params.append(hoje_iso)

        # se tiver "dia" textual (segunda, terça, ...)
        if has_dia_txt:
            where_parts.append("LOWER(TRIM(COALESCE(a.dia,''))) = ?")
            params.append(hoje_dia)

        # se tiver dow_dom (0..6, 0=domingo)
        if has_dow_dom:
            where_parts.append("a.dow_dom = ?")
            params.append(hoje_dow_dom)

        # status ativo (se existir)
        status_sql = ""
        if has_status:
            status_sql = " AND (a.status IS NULL OR LOWER(TRIM(a.status)) = 'ativo') "

        where_sql = " OR ".join([f"({w})" for w in where_parts]) if where_parts else "1=0"

        # join usuarios pra pegar nome
        join_usuarios = ""
        select_prof_nome = "TRIM(COALESCE(a.profissional,'')) AS profissional_nome"
        if _has_table(conn, "usuarios") and has_prof_cpf:
            join_usuarios = """
                LEFT JOIN usuarios u
                       ON u.cpf_digits = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(a.profissional_cpf,'.',''),'-',''),'/',''),' ',''), '(', '')
            """
            select_prof_nome = "COALESCE(u.nome, TRIM(COALESCE(a.profissional,''))) AS profissional_nome"

        cur.execute(
            f"""
            SELECT DISTINCT
                   a.id,
                   TRIM(COALESCE(a.paciente,'')) AS paciente,
                   {select_prof_nome},
                   TRIM(COALESCE(a.profissional,'')) AS profissional_raw,
                   TRIM(COALESCE(a.profissional_cpf,'')) AS profissional_cpf,
                   strftime('%H:%M', a.inicio) AS hora_ini,
                   strftime('%H:%M', a.fim)    AS hora_fim,
                   TRIM(COALESCE(a.observacao,'')) AS observacao,
                   TRIM(COALESCE(a.status,'')) AS status
              FROM agendamentos a
              {join_usuarios}
             WHERE ({where_sql})
             {status_sql}
             ORDER BY hora_ini ASC, profissional_nome ASC, paciente ASC
             LIMIT 200
            """,
            tuple(params)
        )

        agendados_hoje = [
            {
                "id": r[0],
                "paciente": r[1],
                "profissional_nome": r[2],
                "profissional_raw": r[3],
                "profissional_cpf": r[4],
                "hora_ini": r[5] or "",
                "hora_fim": r[6] or "",
                "observacao": r[7],
                "status": r[8],
            }
            for r in cur.fetchall()
        ]

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
        agendados_hoje=agendados_hoje
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


# ============================================================
#  MAIN
# ============================================================
if __name__ == '__main__':
    app.run(debug=True, port=5001)
