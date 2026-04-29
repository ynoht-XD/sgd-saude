import os
import re
import psycopg
from psycopg.rows import dict_row

from datetime import date, datetime, time
from flask import current_app, render_template, request, jsonify, session

from . import agenda_medica_bp


# ============================================================
# CONEXÃO
# ============================================================

try:
    from db import conectar_db
except Exception:
    conectar_db = None


def get_conn():
    if conectar_db:
        return conectar_db()

    database_url = current_app.config.get("DATABASE_URL") or os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "Nenhuma conexão configurada. Crie db.conectar_db() ou configure DATABASE_URL."
        )

    return psycopg.connect(database_url)


# ============================================================
# HELPERS
# ============================================================

def only_digits(v):
    return re.sub(r"\D", "", str(v or ""))


def usuario_logado_id():
    return (
        session.get("usuario_id")
        or session.get("user_id")
        or session.get("id_usuario")
        or session.get("id")
    )


def usuario_logado_nome():
    return (
        session.get("usuario_nome")
        or session.get("nome")
        or session.get("user_nome")
        or "Usuário"
    )


def usuario_logado_role():
    return str(
        session.get("role")
        or session.get("nivel")
        or session.get("perfil")
        or ""
    ).upper()


def is_coordenacao():
    return usuario_logado_role() in {
        "ADMIN",
        "COORDENADOR",
        "COORDENACAO",
        "COORDENAÇÃO",
        "COORD",
    }


def serializar(v):
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    return v


def serializar_row(row):
    return {k: serializar(v) for k, v in dict(row).items()}


# ============================================================
# SCHEMA
# ============================================================

def ensure_agenda_medica_schema():
    sql = """
    CREATE EXTENSION IF NOT EXISTS pgcrypto;

    CREATE TABLE IF NOT EXISTS agenda_medica_liberacoes (
        id SERIAL PRIMARY KEY,
        uid UUID NOT NULL DEFAULT gen_random_uuid(),

        cbo VARCHAR(20),
        cbo_descricao TEXT,

        data_atendimento DATE NOT NULL,

        vagas_normais INTEGER NOT NULL DEFAULT 0,
        vagas_encaixe INTEGER NOT NULL DEFAULT 0,
        capacidade_total INTEGER NOT NULL DEFAULT 0,
        capacidade_ocupada INTEGER NOT NULL DEFAULT 0,

        observacao TEXT,
        ativo BOOLEAN NOT NULL DEFAULT TRUE,

        criado_por_id INTEGER,
        criado_por_nome VARCHAR(255),
        criado_em TIMESTAMP NOT NULL DEFAULT NOW(),

        atualizado_em TIMESTAMP
    );

    ALTER TABLE agenda_medica_liberacoes
        ADD COLUMN IF NOT EXISTS cbo VARCHAR(20);

    ALTER TABLE agenda_medica_liberacoes
        ADD COLUMN IF NOT EXISTS cbo_descricao TEXT;

    ALTER TABLE agenda_medica_liberacoes
        ADD COLUMN IF NOT EXISTS vagas_normais INTEGER NOT NULL DEFAULT 0;

    ALTER TABLE agenda_medica_liberacoes
        ADD COLUMN IF NOT EXISTS vagas_encaixe INTEGER NOT NULL DEFAULT 0;

    ALTER TABLE agenda_medica_liberacoes
        ADD COLUMN IF NOT EXISTS capacidade_total INTEGER NOT NULL DEFAULT 0;

    ALTER TABLE agenda_medica_liberacoes
        ADD COLUMN IF NOT EXISTS capacidade_ocupada INTEGER NOT NULL DEFAULT 0;

    ALTER TABLE agenda_medica_liberacoes
        ADD COLUMN IF NOT EXISTS observacao TEXT;

    ALTER TABLE agenda_medica_liberacoes
        ADD COLUMN IF NOT EXISTS ativo BOOLEAN NOT NULL DEFAULT TRUE;

    CREATE INDEX IF NOT EXISTS idx_agenda_medica_liberacoes_data
        ON agenda_medica_liberacoes(data_atendimento);

    CREATE INDEX IF NOT EXISTS idx_agenda_medica_liberacoes_cbo
        ON agenda_medica_liberacoes(cbo);

    CREATE TABLE IF NOT EXISTS agenda_medica_marcacoes (
        id SERIAL PRIMARY KEY,
        uid UUID NOT NULL DEFAULT gen_random_uuid(),

        liberacao_id INTEGER NOT NULL
            REFERENCES agenda_medica_liberacoes(id)
            ON DELETE CASCADE,

        paciente_id INTEGER,
        paciente_nome VARCHAR(255) NOT NULL,
        paciente_cpf VARCHAR(20),
        paciente_cns VARCHAR(30),
        paciente_nascimento DATE,

        profissional_id INTEGER,
        profissional_nome VARCHAR(255),

        status VARCHAR(30) NOT NULL DEFAULT 'PENDENTE',

        justificativa TEXT,
        observacao TEXT,

        criado_em TIMESTAMP NOT NULL DEFAULT NOW(),
        atualizado_em TIMESTAMP,

        decidido_por_id INTEGER,
        decidido_por_nome VARCHAR(255),
        decidido_em TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_agenda_medica_marcacoes_liberacao
        ON agenda_medica_marcacoes(liberacao_id);

    CREATE INDEX IF NOT EXISTS idx_agenda_medica_marcacoes_status
        ON agenda_medica_marcacoes(status);
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()


_schema_ok = False


@agenda_medica_bp.before_request
def before_request_agenda_medica():
    global _schema_ok

    if _schema_ok:
        return

    ensure_agenda_medica_schema()
    _schema_ok = True


# ============================================================
# PÁGINAS
# ============================================================

@agenda_medica_bp.route("/")
def index():
    return render_template("agenda_medica/coordenacao.html")


@agenda_medica_bp.route("/coordenacao")
def coordenacao():
    return render_template("agenda_medica/coordenacao.html")


# ============================================================
# API CBO AUTOCOMPLETE
# ============================================================

@agenda_medica_bp.route("/api/cbos")
def buscar_cbos():
    q = (request.args.get("q") or "").strip()

    if len(q) < 3:
        return jsonify({"ok": True, "cbos": []})

    termo = f"%{q}%"

    sql = """
        SELECT
            co_ocupacao AS codigo,
            no_ocupacao AS descricao
        FROM ocupacoes
        WHERE co_ocupacao ILIKE %s
           OR no_ocupacao ILIKE %s
        ORDER BY
            CASE
                WHEN co_ocupacao ILIKE %s THEN 0
                WHEN no_ocupacao ILIKE %s THEN 1
                ELSE 2
            END,
            no_ocupacao ASC
        LIMIT 20
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (termo, termo, f"{q}%", f"{q}%"))
            cols = [desc[0] for desc in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]

    return jsonify({
        "ok": True,
        "cbos": [serializar_row(r) for r in rows],
    })


# ============================================================
# API LIBERAÇÕES / CARDS
# ============================================================

@agenda_medica_bp.route("/api/liberacoes/cards")
def listar_liberacoes_cards():
    tipo = request.args.get("tipo", "futuras")
    page = max(int(request.args.get("page", 1) or 1), 1)
    per_page = min(max(int(request.args.get("per_page", 6) or 6), 1), 30)
    offset = (page - 1) * per_page

    if tipo == "passadas":
        filtro_data = "l.data_atendimento < CURRENT_DATE"
        ordem = "l.data_atendimento DESC"
    else:
        filtro_data = "l.data_atendimento >= CURRENT_DATE"
        ordem = "l.data_atendimento ASC"

    sql_count = f"""
        SELECT COUNT(*) AS total
        FROM agenda_medica_liberacoes l
        WHERE l.ativo = TRUE
          AND {filtro_data}
    """

    sql = f"""
        SELECT
            l.id,
            l.cbo,
            l.cbo_descricao,
            l.data_atendimento,
            l.vagas_normais,
            l.vagas_encaixe,
            l.capacidade_total,
            l.capacidade_ocupada,
            GREATEST(l.capacidade_total - l.capacidade_ocupada, 0) AS vagas_restantes,
            l.observacao,
            l.criado_por_nome,
            l.criado_em,

            COUNT(m.id) AS total_marcacoes,
            COUNT(m.id) FILTER (WHERE m.status = 'PENDENTE') AS pendentes,
            COUNT(m.id) FILTER (WHERE m.status = 'ACEITO') AS aceitos,
            COUNT(m.id) FILTER (WHERE m.status = 'RECUSADO') AS recusados,
            COUNT(m.id) FILTER (WHERE m.status = 'CANCELADO') AS cancelados

        FROM agenda_medica_liberacoes l
        LEFT JOIN agenda_medica_marcacoes m ON m.liberacao_id = l.id
        WHERE l.ativo = TRUE
          AND {filtro_data}
        GROUP BY l.id
        ORDER BY {ordem}, l.id DESC
        LIMIT %s OFFSET %s
    """

    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql_count)
            total = cur.fetchone()["total"]

            cur.execute(sql, (per_page, offset))
            rows = cur.fetchall()

    return jsonify({
        "ok": True,
        "items": [serializar_row(r) for r in rows],
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": max((total + per_page - 1) // per_page, 1),
    })


@agenda_medica_bp.route("/api/liberacoes", methods=["POST"])
def criar_liberacao():
    data = request.get_json(silent=True) or {}

    cbo = only_digits(data.get("cbo"))
    cbo_descricao = (data.get("cbo_descricao") or "").strip()
    data_atendimento = data.get("data_atendimento")

    vagas_normais = int(data.get("vagas_normais") or 0)
    vagas_encaixe = int(data.get("vagas_encaixe") or 0)
    capacidade_total = vagas_normais + vagas_encaixe

    observacao = (data.get("observacao") or "").strip()

    if not cbo or not cbo_descricao:
        return jsonify({"ok": False, "erro": "Selecione um CBO válido."}), 400

    if not data_atendimento:
        return jsonify({"ok": False, "erro": "Informe a data da agenda."}), 400

    if capacidade_total <= 0:
        return jsonify({"ok": False, "erro": "Informe ao menos 1 vaga."}), 400

    sql = """
        INSERT INTO agenda_medica_liberacoes (
            cbo,
            cbo_descricao,
            data_atendimento,
            vagas_normais,
            vagas_encaixe,
            capacidade_total,
            observacao,
            criado_por_id,
            criado_por_nome
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (
                cbo,
                cbo_descricao,
                data_atendimento,
                vagas_normais,
                vagas_encaixe,
                capacidade_total,
                observacao,
                usuario_logado_id(),
                usuario_logado_nome(),
            ))
            novo_id = cur.fetchone()[0]
        conn.commit()

    return jsonify({
        "ok": True,
        "id": novo_id,
        "mensagem": "Agenda liberada com sucesso.",
    })


@agenda_medica_bp.route("/api/liberacoes/<int:liberacao_id>", methods=["GET"])
def obter_liberacao(liberacao_id):
    sql = """
        SELECT
            id,
            cbo,
            cbo_descricao,
            data_atendimento,
            vagas_normais,
            vagas_encaixe,
            capacidade_total,
            capacidade_ocupada,
            GREATEST(capacidade_total - capacidade_ocupada, 0) AS vagas_restantes,
            observacao
        FROM agenda_medica_liberacoes
        WHERE id = %s
    """

    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (liberacao_id,))
            row = cur.fetchone()

    if not row:
        return jsonify({"ok": False, "erro": "Agenda não encontrada."}), 404

    return jsonify({"ok": True, "agenda": serializar_row(row)})


@agenda_medica_bp.route("/api/liberacoes/<int:liberacao_id>", methods=["PUT"])
def editar_liberacao(liberacao_id):
    data = request.get_json(silent=True) or {}

    cbo = only_digits(data.get("cbo"))
    cbo_descricao = (data.get("cbo_descricao") or "").strip()
    data_atendimento = data.get("data_atendimento")

    vagas_normais = int(data.get("vagas_normais") or 0)
    vagas_encaixe = int(data.get("vagas_encaixe") or 0)
    capacidade_total = vagas_normais + vagas_encaixe

    observacao = (data.get("observacao") or "").strip()

    if not cbo or not cbo_descricao:
        return jsonify({"ok": False, "erro": "Selecione um CBO válido."}), 400

    if not data_atendimento:
        return jsonify({"ok": False, "erro": "Informe a data da agenda."}), 400

    if capacidade_total <= 0:
        return jsonify({"ok": False, "erro": "Informe ao menos 1 vaga."}), 400

    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT capacidade_ocupada
                FROM agenda_medica_liberacoes
                WHERE id = %s
                """,
                (liberacao_id,),
            )
            atual = cur.fetchone()

            if not atual:
                conn.rollback()
                return jsonify({"ok": False, "erro": "Agenda não encontrada."}), 404

            if capacidade_total < atual["capacidade_ocupada"]:
                conn.rollback()
                return jsonify({
                    "ok": False,
                    "erro": "A nova quantidade de vagas não pode ser menor que as marcações já feitas.",
                }), 400

            cur.execute(
                """
                UPDATE agenda_medica_liberacoes
                SET cbo = %s,
                    cbo_descricao = %s,
                    data_atendimento = %s,
                    vagas_normais = %s,
                    vagas_encaixe = %s,
                    capacidade_total = %s,
                    observacao = %s,
                    atualizado_em = NOW()
                WHERE id = %s
                """,
                (
                    cbo,
                    cbo_descricao,
                    data_atendimento,
                    vagas_normais,
                    vagas_encaixe,
                    capacidade_total,
                    observacao,
                    liberacao_id,
                ),
            )

        conn.commit()

    return jsonify({"ok": True, "mensagem": "Agenda atualizada."})


@agenda_medica_bp.route("/api/liberacoes/<int:liberacao_id>", methods=["DELETE"])
def excluir_liberacao(liberacao_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE agenda_medica_liberacoes
                SET ativo = FALSE,
                    atualizado_em = NOW()
                WHERE id = %s
                """,
                (liberacao_id,),
            )
        conn.commit()

    return jsonify({"ok": True, "mensagem": "Agenda excluída."})


# ============================================================
# API MARCAÇÕES DA AGENDA
# ============================================================

@agenda_medica_bp.route("/api/liberacoes/<int:liberacao_id>/marcacoes")
def marcacoes_da_liberacao(liberacao_id):
    sql = """
        SELECT
            m.id,
            m.paciente_id,
            m.paciente_nome,
            m.paciente_cpf,
            m.paciente_cns,
            m.paciente_nascimento,
            m.profissional_id,
            m.profissional_nome,
            m.status,
            m.justificativa,
            m.observacao,
            m.criado_em,
            m.decidido_por_nome,
            m.decidido_em
        FROM agenda_medica_marcacoes m
        WHERE m.liberacao_id = %s
        ORDER BY
            CASE m.status
                WHEN 'PENDENTE' THEN 1
                WHEN 'ACEITO' THEN 2
                WHEN 'RECUSADO' THEN 3
                ELSE 4
            END,
            m.criado_em ASC
    """

    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (liberacao_id,))
            rows = cur.fetchall()

    return jsonify({
        "ok": True,
        "marcacoes": [serializar_row(r) for r in rows],
    })


@agenda_medica_bp.route("/api/marcacoes/<int:marcacao_id>/aceitar", methods=["POST"])
def aceitar_marcacao(marcacao_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE agenda_medica_marcacoes
                SET status = 'ACEITO',
                    atualizado_em = NOW(),
                    decidido_por_id = %s,
                    decidido_por_nome = %s,
                    decidido_em = NOW()
                WHERE id = %s
                  AND status = 'PENDENTE'
                """,
                (usuario_logado_id(), usuario_logado_nome(), marcacao_id),
            )

            if cur.rowcount == 0:
                conn.rollback()
                return jsonify({
                    "ok": False,
                    "erro": "Marcação não encontrada ou já decidida."
                }), 400

        conn.commit()

    return jsonify({"ok": True, "mensagem": "Marcação aceita."})


@agenda_medica_bp.route("/api/marcacoes/<int:marcacao_id>/recusar", methods=["POST"])
def recusar_marcacao(marcacao_id):
    data = request.get_json(silent=True) or {}
    justificativa = (data.get("justificativa") or "").strip()

    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, liberacao_id, status
                FROM agenda_medica_marcacoes
                WHERE id = %s
                FOR UPDATE
                """,
                (marcacao_id,),
            )
            marcacao = cur.fetchone()

            if not marcacao:
                conn.rollback()
                return jsonify({"ok": False, "erro": "Marcação não encontrada."}), 404

            if marcacao["status"] != "PENDENTE":
                conn.rollback()
                return jsonify({"ok": False, "erro": "Essa marcação já foi decidida."}), 400

            cur.execute(
                """
                UPDATE agenda_medica_marcacoes
                SET status = 'RECUSADO',
                    justificativa = %s,
                    atualizado_em = NOW(),
                    decidido_por_id = %s,
                    decidido_por_nome = %s,
                    decidido_em = NOW()
                WHERE id = %s
                """,
                (
                    justificativa,
                    usuario_logado_id(),
                    usuario_logado_nome(),
                    marcacao_id,
                ),
            )

            cur.execute(
                """
                UPDATE agenda_medica_liberacoes
                SET capacidade_ocupada = GREATEST(capacidade_ocupada - 1, 0),
                    atualizado_em = NOW()
                WHERE id = %s
                """,
                (marcacao["liberacao_id"],),
            )

        conn.commit()

    return jsonify({"ok": True, "mensagem": "Marcação recusada e vaga liberada."})

@agenda_medica_bp.route("/profissional")
def profissional():
    return render_template("agenda_medica/profissional.html")

# ============================================================
# API PACIENTES - AUTOCOMPLETE
# ============================================================

@agenda_medica_bp.route("/api/pacientes")
def buscar_pacientes():
    q = (request.args.get("q") or "").strip()

    if len(q) < 3:
        return jsonify({"ok": True, "pacientes": []})

    termo = f"%{q}%"
    digitos = only_digits(q)

    where = """
        nome ILIKE %s
        OR cpf ILIKE %s
        OR cns ILIKE %s
    """

    params = [termo, termo, termo]

    if digitos:
        where += """
            OR regexp_replace(COALESCE(cpf, ''), '\\D', '', 'g') ILIKE %s
            OR regexp_replace(COALESCE(cns, ''), '\\D', '', 'g') ILIKE %s
        """
        params.extend([f"%{digitos}%", f"%{digitos}%"])

    sql = f"""
        SELECT
            id,
            nome,
            cpf,
            cns,
            nascimento
        FROM pacientes
        WHERE {where}
        ORDER BY nome ASC
        LIMIT 20
    """

    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return jsonify({
        "ok": True,
        "pacientes": [serializar_row(r) for r in rows],
    })

@agenda_medica_bp.route("/api/marcacoes", methods=["POST"])
def criar_marcacao():
    data = request.get_json(silent=True) or {}

    liberacao_id = data.get("liberacao_id")
    paciente_id = data.get("paciente_id") or None
    paciente_nome = (data.get("paciente_nome") or "").strip()
    paciente_cpf = only_digits(data.get("paciente_cpf"))
    paciente_cns = only_digits(data.get("paciente_cns"))
    paciente_nascimento = data.get("paciente_nascimento") or None
    observacao = (data.get("observacao") or "").strip()

    if not liberacao_id:
        return jsonify({"ok": False, "erro": "Selecione uma data liberada."}), 400

    if not paciente_nome:
        return jsonify({"ok": False, "erro": "Selecione um paciente."}), 400

    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT 
                    id,
                    cbo,
                    cbo_descricao,
                    data_atendimento,
                    capacidade_total,
                    capacidade_ocupada,
                    ativo
                FROM agenda_medica_liberacoes
                WHERE id = %s
                FOR UPDATE
                """,
                (liberacao_id,),
            )
            liberacao = cur.fetchone()

            if not liberacao or not liberacao["ativo"]:
                conn.rollback()
                return jsonify({
                    "ok": False,
                    "erro": "Agenda não encontrada ou inativa."
                }), 404

            vagas_restantes = int(liberacao["capacidade_total"]) - int(liberacao["capacidade_ocupada"])

            if vagas_restantes <= 0:
                conn.rollback()
                return jsonify({
                    "ok": False,
                    "erro": "Não há vagas disponíveis para essa agenda."
                }), 409

            # ====================================================
            # BLOQUEIO DE DUPLICIDADE
            # Mesmo paciente + mesmo CBO/especialidade
            # Só bloqueia se já estiver PENDENTE ou ACEITO.
            # Se foi RECUSADO ou CANCELADO, permite solicitar de novo.
            # ====================================================
            cur.execute(
                """
                SELECT 
                    m.id,
                    m.status,
                    m.paciente_nome,
                    l.data_atendimento,
                    l.cbo,
                    l.cbo_descricao
                FROM agenda_medica_marcacoes m
                JOIN agenda_medica_liberacoes l ON l.id = m.liberacao_id
                WHERE l.cbo = %s
                AND m.status IN ('PENDENTE', 'ACEITO')
                AND (
                        (%s::integer IS NOT NULL AND m.paciente_id = %s::integer)
                    OR (%s <> '' AND regexp_replace(COALESCE(m.paciente_cpf, ''), '\\D', '', 'g') = %s)
                    OR (%s <> '' AND regexp_replace(COALESCE(m.paciente_cns, ''), '\\D', '', 'g') = %s)
                    OR (
                        lower(trim(m.paciente_nome)) = lower(trim(%s))
                        AND COALESCE(m.paciente_nascimento::text, '') = COALESCE(%s, '')
                        )
                )
                LIMIT 1
                """,
                (
                    liberacao["cbo"],
                    paciente_id, paciente_id,
                    paciente_cpf, paciente_cpf,
                    paciente_cns, paciente_cns,
                    paciente_nome,
                    paciente_nascimento,
                ),
            )
                        
            duplicada = cur.fetchone()

            if duplicada:
                conn.rollback()
                return jsonify({
                    "ok": False,
                    "erro": (
                        f"Este paciente já está na lista para "
                        f"{duplicada['cbo']} - {duplicada['cbo_descricao']} "
                        f"em {serializar(duplicada['data_atendimento'])}, "
                        f"com status {duplicada['status']}."
                    )
                }), 409

            cur.execute(
                """
                INSERT INTO agenda_medica_marcacoes (
                    liberacao_id,
                    paciente_id,
                    paciente_nome,
                    paciente_cpf,
                    paciente_cns,
                    paciente_nascimento,
                    profissional_id,
                    profissional_nome,
                    observacao
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    liberacao_id,
                    paciente_id,
                    paciente_nome,
                    paciente_cpf,
                    paciente_cns,
                    paciente_nascimento,
                    usuario_logado_id(),
                    usuario_logado_nome(),
                    observacao,
                ),
            )

            marcacao_id = cur.fetchone()["id"]

            cur.execute(
                """
                UPDATE agenda_medica_liberacoes
                SET capacidade_ocupada = capacidade_ocupada + 1,
                    atualizado_em = NOW()
                WHERE id = %s
                """,
                (liberacao_id,),
            )

        conn.commit()

    return jsonify({
        "ok": True,
        "id": marcacao_id,
        "mensagem": "Solicitação enviada com sucesso.",
    })