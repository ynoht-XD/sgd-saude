import os
import re
import psycopg
from psycopg.rows import dict_row

from datetime import date, datetime, time
from flask import current_app, render_template, request, jsonify, session, abort

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
# LOGS
# ============================================================

try:
    from log import registrar_log, log_erro, log_edicao, log_visualizacao
except Exception:
    def registrar_log(*args, **kwargs): pass
    def log_erro(*args, **kwargs): pass
    def log_edicao(*args, **kwargs): pass
    def log_visualizacao(*args, **kwargs): pass


# ============================================================
# MÓDULOS / PERMISSÕES
# ============================================================

try:
    from admin.modulos import require_permission
except Exception:
    def require_permission(modulo_codigo: str, acao: str = "ver"):
        def decorator(view):
            return view
        return decorator


MODULO_AGENDA = "agenda"


# ============================================================
# HELPERS
# ============================================================

def only_digits(v):
    return re.sub(r"\D", "", str(v or ""))


def get_clinica_id(default=1):
    return int(session.get("clinica_id") or default)


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
        "MASTER",
        "ROOT",
        "SUPERADMIN",
    }


def serializar(v):
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    return v


def serializar_row(row):
    if row is None:
        return None
    return {k: serializar(v) for k, v in dict(row).items()}


_column_cache = {}


def table_has_column(table_name: str, column_name: str) -> bool:
    cache_key = f"{table_name}.{column_name}"

    if cache_key in _column_cache:
        return _column_cache[cache_key]

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = %s
                      AND column_name = %s
                );
                """,
                (table_name, column_name),
            )
            exists = bool(cur.fetchone()[0])

    _column_cache[cache_key] = exists
    return exists


def log_api_erro(e, descricao, entidade=None, entidade_id=None, detalhes=None):
    log_erro(
        MODULO_AGENDA,
        e,
        entidade=entidade,
        entidade_id=entidade_id,
        descricao=descricao,
        detalhes={
            "clinica_id": get_clinica_id(),
            "usuario_id": usuario_logado_id(),
            **(detalhes or {}),
        },
    )


# ============================================================
# SCHEMA
# ============================================================

def ensure_agenda_medica_schema():
    sql = """
    CREATE EXTENSION IF NOT EXISTS pgcrypto;

    CREATE TABLE IF NOT EXISTS agenda_medica_liberacoes (
        id SERIAL PRIMARY KEY,
        uid UUID NOT NULL DEFAULT gen_random_uuid(),

        clinica_id INTEGER NOT NULL DEFAULT 1,

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
        ADD COLUMN IF NOT EXISTS clinica_id INTEGER NOT NULL DEFAULT 1;

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

    ALTER TABLE agenda_medica_liberacoes
        ADD COLUMN IF NOT EXISTS criado_por_id INTEGER;

    ALTER TABLE agenda_medica_liberacoes
        ADD COLUMN IF NOT EXISTS criado_por_nome VARCHAR(255);

    ALTER TABLE agenda_medica_liberacoes
        ADD COLUMN IF NOT EXISTS criado_em TIMESTAMP NOT NULL DEFAULT NOW();

    ALTER TABLE agenda_medica_liberacoes
        ADD COLUMN IF NOT EXISTS atualizado_em TIMESTAMP;

    CREATE INDEX IF NOT EXISTS idx_agenda_medica_liberacoes_clinica
        ON agenda_medica_liberacoes(clinica_id);

    CREATE INDEX IF NOT EXISTS idx_agenda_medica_liberacoes_clinica_data
        ON agenda_medica_liberacoes(clinica_id, data_atendimento);

    CREATE INDEX IF NOT EXISTS idx_agenda_medica_liberacoes_cbo
        ON agenda_medica_liberacoes(clinica_id, cbo);

    CREATE TABLE IF NOT EXISTS agenda_medica_marcacoes (
        id SERIAL PRIMARY KEY,
        uid UUID NOT NULL DEFAULT gen_random_uuid(),

        clinica_id INTEGER NOT NULL DEFAULT 1,

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

    ALTER TABLE agenda_medica_marcacoes
        ADD COLUMN IF NOT EXISTS clinica_id INTEGER NOT NULL DEFAULT 1;

    ALTER TABLE agenda_medica_marcacoes
        ADD COLUMN IF NOT EXISTS justificativa TEXT;

    ALTER TABLE agenda_medica_marcacoes
        ADD COLUMN IF NOT EXISTS observacao TEXT;

    ALTER TABLE agenda_medica_marcacoes
        ADD COLUMN IF NOT EXISTS decidido_por_id INTEGER;

    ALTER TABLE agenda_medica_marcacoes
        ADD COLUMN IF NOT EXISTS decidido_por_nome VARCHAR(255);

    ALTER TABLE agenda_medica_marcacoes
        ADD COLUMN IF NOT EXISTS decidido_em TIMESTAMP;

    CREATE INDEX IF NOT EXISTS idx_agenda_medica_marcacoes_clinica
        ON agenda_medica_marcacoes(clinica_id);

    CREATE INDEX IF NOT EXISTS idx_agenda_medica_marcacoes_liberacao
        ON agenda_medica_marcacoes(clinica_id, liberacao_id);

    CREATE INDEX IF NOT EXISTS idx_agenda_medica_marcacoes_status
        ON agenda_medica_marcacoes(clinica_id, status);

    CREATE INDEX IF NOT EXISTS idx_agenda_medica_marcacoes_paciente
        ON agenda_medica_marcacoes(clinica_id, paciente_id);
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
@require_permission(MODULO_AGENDA, "ver")
def index():
    log_visualizacao(
        modulo=MODULO_AGENDA,
        entidade="agenda_medica",
        descricao="Abriu tela de coordenação da agenda médica.",
        detalhes={"clinica_id": get_clinica_id()},
    )
    return render_template("agenda_medica/coordenacao.html")


@agenda_medica_bp.route("/coordenacao")
@require_permission(MODULO_AGENDA, "ver")
def coordenacao():
    log_visualizacao(
        modulo=MODULO_AGENDA,
        entidade="agenda_medica",
        descricao="Abriu tela de coordenação da agenda médica.",
        detalhes={"clinica_id": get_clinica_id()},
    )
    return render_template("agenda_medica/coordenacao.html")


@agenda_medica_bp.route("/profissional")
@require_permission(MODULO_AGENDA, "ver")
def profissional():
    log_visualizacao(
        modulo=MODULO_AGENDA,
        entidade="agenda_medica",
        descricao="Abriu tela profissional da agenda médica.",
        detalhes={"clinica_id": get_clinica_id()},
    )
    return render_template("agenda_medica/profissional.html")


# ============================================================
# API CBO AUTOCOMPLETE
# ============================================================

@agenda_medica_bp.route("/api/cbos")
@require_permission(MODULO_AGENDA, "ver")
def buscar_cbos():
    try:
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
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, (termo, termo, f"{q}%", f"{q}%"))
                rows = cur.fetchall()

        return jsonify({
            "ok": True,
            "cbos": [serializar_row(r) for r in rows],
        })

    except Exception as e:
        log_api_erro(e, "Erro ao buscar CBOs na agenda médica.")
        return jsonify({"ok": False, "erro": str(e)}), 500


# ============================================================
# API LIBERAÇÕES / CARDS
# ============================================================

@agenda_medica_bp.route("/api/liberacoes/cards")
@require_permission(MODULO_AGENDA, "ver")
def listar_liberacoes_cards():
    try:
        clinica_id = get_clinica_id()

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
              AND l.clinica_id = %s
              AND {filtro_data}
        """

        sql = f"""
            SELECT
                l.id,
                l.clinica_id,
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
            LEFT JOIN agenda_medica_marcacoes m
                   ON m.liberacao_id = l.id
                  AND m.clinica_id = l.clinica_id
            WHERE l.ativo = TRUE
              AND l.clinica_id = %s
              AND {filtro_data}
            GROUP BY l.id
            ORDER BY {ordem}, l.id DESC
            LIMIT %s OFFSET %s
        """

        with get_conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql_count, (clinica_id,))
                total = cur.fetchone()["total"]

                cur.execute(sql, (clinica_id, per_page, offset))
                rows = cur.fetchall()

        return jsonify({
            "ok": True,
            "items": [serializar_row(r) for r in rows],
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": max((total + per_page - 1) // per_page, 1),
        })

    except Exception as e:
        log_api_erro(e, "Erro ao listar cards de liberações da agenda médica.")
        return jsonify({"ok": False, "erro": str(e)}), 500


@agenda_medica_bp.route("/api/liberacoes", methods=["POST"])
@require_permission(MODULO_AGENDA, "criar")
def criar_liberacao():
    try:
        clinica_id = get_clinica_id()
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
                clinica_id,
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    clinica_id,
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

        log_edicao(
            modulo=MODULO_AGENDA,
            entidade="agenda_medica_liberacoes",
            entidade_id=novo_id,
            descricao="Liberou agenda médica.",
            detalhes={
                "clinica_id": clinica_id,
                "cbo": cbo,
                "cbo_descricao": cbo_descricao,
                "data_atendimento": data_atendimento,
                "capacidade_total": capacidade_total,
            },
        )

        return jsonify({
            "ok": True,
            "id": novo_id,
            "mensagem": "Agenda liberada com sucesso.",
        })

    except Exception as e:
        log_api_erro(e, "Erro ao criar liberação da agenda médica.")
        return jsonify({"ok": False, "erro": str(e)}), 500


@agenda_medica_bp.route("/api/liberacoes/<int:liberacao_id>", methods=["GET"])
@require_permission(MODULO_AGENDA, "ver")
def obter_liberacao(liberacao_id):
    try:
        clinica_id = get_clinica_id()

        sql = """
            SELECT
                id,
                clinica_id,
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
              AND clinica_id = %s
        """

        with get_conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, (liberacao_id, clinica_id))
                row = cur.fetchone()

        if not row:
            return jsonify({"ok": False, "erro": "Agenda não encontrada."}), 404

        return jsonify({"ok": True, "agenda": serializar_row(row)})

    except Exception as e:
        log_api_erro(
            e,
            "Erro ao obter liberação da agenda médica.",
            entidade="agenda_medica_liberacoes",
            entidade_id=liberacao_id,
        )
        return jsonify({"ok": False, "erro": str(e)}), 500


@agenda_medica_bp.route("/api/liberacoes/<int:liberacao_id>", methods=["PUT"])
@require_permission(MODULO_AGENDA, "editar")
def editar_liberacao(liberacao_id):
    try:
        clinica_id = get_clinica_id()
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
                      AND clinica_id = %s
                    """,
                    (liberacao_id, clinica_id),
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
                      AND clinica_id = %s
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
                        clinica_id,
                    ),
                )

            conn.commit()

        log_edicao(
            modulo=MODULO_AGENDA,
            entidade="agenda_medica_liberacoes",
            entidade_id=liberacao_id,
            descricao="Atualizou liberação da agenda médica.",
            detalhes={
                "clinica_id": clinica_id,
                "cbo": cbo,
                "data_atendimento": data_atendimento,
                "capacidade_total": capacidade_total,
            },
        )

        return jsonify({"ok": True, "mensagem": "Agenda atualizada."})

    except Exception as e:
        log_api_erro(
            e,
            "Erro ao editar liberação da agenda médica.",
            entidade="agenda_medica_liberacoes",
            entidade_id=liberacao_id,
        )
        return jsonify({"ok": False, "erro": str(e)}), 500


@agenda_medica_bp.route("/api/liberacoes/<int:liberacao_id>", methods=["DELETE"])
@require_permission(MODULO_AGENDA, "editar")
def excluir_liberacao(liberacao_id):
    try:
        clinica_id = get_clinica_id()

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE agenda_medica_liberacoes
                    SET ativo = FALSE,
                        atualizado_em = NOW()
                    WHERE id = %s
                      AND clinica_id = %s
                    """,
                    (liberacao_id, clinica_id),
                )

                if cur.rowcount == 0:
                    conn.rollback()
                    return jsonify({"ok": False, "erro": "Agenda não encontrada."}), 404

            conn.commit()

        log_edicao(
            modulo=MODULO_AGENDA,
            entidade="agenda_medica_liberacoes",
            entidade_id=liberacao_id,
            descricao="Excluiu/inativou liberação da agenda médica.",
            detalhes={"clinica_id": clinica_id},
        )

        return jsonify({"ok": True, "mensagem": "Agenda excluída."})

    except Exception as e:
        log_api_erro(
            e,
            "Erro ao excluir liberação da agenda médica.",
            entidade="agenda_medica_liberacoes",
            entidade_id=liberacao_id,
        )
        return jsonify({"ok": False, "erro": str(e)}), 500


# ============================================================
# API MARCAÇÕES DA AGENDA
# ============================================================

@agenda_medica_bp.route("/api/liberacoes/<int:liberacao_id>/marcacoes")
@require_permission(MODULO_AGENDA, "ver")
def marcacoes_da_liberacao(liberacao_id):
    try:
        clinica_id = get_clinica_id()

        sql = """
            SELECT
                m.id,
                m.clinica_id,
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
            JOIN agenda_medica_liberacoes l
              ON l.id = m.liberacao_id
             AND l.clinica_id = m.clinica_id
            WHERE m.liberacao_id = %s
              AND m.clinica_id = %s
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
                cur.execute(sql, (liberacao_id, clinica_id))
                rows = cur.fetchall()

        return jsonify({
            "ok": True,
            "marcacoes": [serializar_row(r) for r in rows],
        })

    except Exception as e:
        log_api_erro(
            e,
            "Erro ao listar marcações da liberação.",
            entidade="agenda_medica_liberacoes",
            entidade_id=liberacao_id,
        )
        return jsonify({"ok": False, "erro": str(e)}), 500


@agenda_medica_bp.route("/api/marcacoes/<int:marcacao_id>/aceitar", methods=["POST"])
@require_permission(MODULO_AGENDA, "editar")
def aceitar_marcacao(marcacao_id):
    try:
        clinica_id = get_clinica_id()

        with get_conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, liberacao_id, paciente_nome, status
                    FROM agenda_medica_marcacoes
                    WHERE id = %s
                      AND clinica_id = %s
                    FOR UPDATE
                    """,
                    (marcacao_id, clinica_id),
                )
                marcacao = cur.fetchone()

                if not marcacao:
                    conn.rollback()
                    return jsonify({"ok": False, "erro": "Marcação não encontrada."}), 404

                if marcacao["status"] != "PENDENTE":
                    conn.rollback()
                    return jsonify({"ok": False, "erro": "Marcação já decidida."}), 400

                cur.execute(
                    """
                    UPDATE agenda_medica_marcacoes
                    SET status = 'ACEITO',
                        atualizado_em = NOW(),
                        decidido_por_id = %s,
                        decidido_por_nome = %s,
                        decidido_em = NOW()
                    WHERE id = %s
                      AND clinica_id = %s
                    """,
                    (
                        usuario_logado_id(),
                        usuario_logado_nome(),
                        marcacao_id,
                        clinica_id,
                    ),
                )

            conn.commit()

        log_edicao(
            modulo=MODULO_AGENDA,
            entidade="agenda_medica_marcacoes",
            entidade_id=marcacao_id,
            descricao="Aceitou marcação da agenda médica.",
            detalhes={
                "clinica_id": clinica_id,
                "paciente_nome": marcacao["paciente_nome"],
            },
        )

        return jsonify({"ok": True, "mensagem": "Marcação aceita."})

    except Exception as e:
        log_api_erro(
            e,
            "Erro ao aceitar marcação da agenda médica.",
            entidade="agenda_medica_marcacoes",
            entidade_id=marcacao_id,
        )
        return jsonify({"ok": False, "erro": str(e)}), 500


@agenda_medica_bp.route("/api/marcacoes/<int:marcacao_id>/recusar", methods=["POST"])
@require_permission(MODULO_AGENDA, "editar")
def recusar_marcacao(marcacao_id):
    try:
        clinica_id = get_clinica_id()
        data = request.get_json(silent=True) or {}
        justificativa = (data.get("justificativa") or "").strip()

        with get_conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, liberacao_id, paciente_nome, status
                    FROM agenda_medica_marcacoes
                    WHERE id = %s
                      AND clinica_id = %s
                    FOR UPDATE
                    """,
                    (marcacao_id, clinica_id),
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
                      AND clinica_id = %s
                    """,
                    (
                        justificativa,
                        usuario_logado_id(),
                        usuario_logado_nome(),
                        marcacao_id,
                        clinica_id,
                    ),
                )

                cur.execute(
                    """
                    UPDATE agenda_medica_liberacoes
                    SET capacidade_ocupada = GREATEST(capacidade_ocupada - 1, 0),
                        atualizado_em = NOW()
                    WHERE id = %s
                      AND clinica_id = %s
                    """,
                    (marcacao["liberacao_id"], clinica_id),
                )

            conn.commit()

        log_edicao(
            modulo=MODULO_AGENDA,
            entidade="agenda_medica_marcacoes",
            entidade_id=marcacao_id,
            descricao="Recusou marcação da agenda médica.",
            detalhes={
                "clinica_id": clinica_id,
                "paciente_nome": marcacao["paciente_nome"],
                "justificativa": justificativa,
            },
        )

        return jsonify({"ok": True, "mensagem": "Marcação recusada e vaga liberada."})

    except Exception as e:
        log_api_erro(
            e,
            "Erro ao recusar marcação da agenda médica.",
            entidade="agenda_medica_marcacoes",
            entidade_id=marcacao_id,
        )
        return jsonify({"ok": False, "erro": str(e)}), 500


# ============================================================
# API PACIENTES - AUTOCOMPLETE
# ============================================================

@agenda_medica_bp.route("/api/pacientes")
@require_permission(MODULO_AGENDA, "ver")
def buscar_pacientes():
    try:
        clinica_id = get_clinica_id()
        q = (request.args.get("q") or "").strip()

        if len(q) < 3:
            return jsonify({"ok": True, "pacientes": []})

        termo = f"%{q}%"
        digitos = only_digits(q)

        filtro_clinica = ""
        params = []

        if table_has_column("pacientes", "clinica_id"):
            filtro_clinica = "AND COALESCE(clinica_id, %s) = %s"
            params.extend([clinica_id, clinica_id])

        where = """
            (
                nome ILIKE %s
                OR cpf ILIKE %s
                OR cns ILIKE %s
        """

        params.extend([termo, termo, termo])

        if digitos:
            where += """
                OR regexp_replace(COALESCE(cpf, ''), '\\D', '', 'g') ILIKE %s
                OR regexp_replace(COALESCE(cns, ''), '\\D', '', 'g') ILIKE %s
            """
            params.extend([f"%{digitos}%", f"%{digitos}%"])

        where += ")"

        sql = f"""
            SELECT
                id,
                nome,
                cpf,
                cns,
                nascimento
            FROM pacientes
            WHERE {where}
              {filtro_clinica}
            ORDER BY nome ASC
            LIMIT 20
        """

        with get_conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

        registrar_log(
            modulo=MODULO_AGENDA,
            acao="pesquisar",
            entidade="pacientes",
            descricao="Pesquisou pacientes no autocomplete da agenda médica.",
            detalhes={
                "clinica_id": clinica_id,
                "termo": q,
                "total": len(rows),
            },
        )

        return jsonify({
            "ok": True,
            "pacientes": [serializar_row(r) for r in rows],
        })

    except Exception as e:
        log_api_erro(e, "Erro ao buscar pacientes na agenda médica.")
        return jsonify({"ok": False, "erro": str(e)}), 500


@agenda_medica_bp.route("/api/marcacoes", methods=["POST"])
@require_permission(MODULO_AGENDA, "criar")
def criar_marcacao():
    try:
        clinica_id = get_clinica_id()
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
                        clinica_id,
                        cbo,
                        cbo_descricao,
                        data_atendimento,
                        capacidade_total,
                        capacidade_ocupada,
                        ativo
                    FROM agenda_medica_liberacoes
                    WHERE id = %s
                      AND clinica_id = %s
                    FOR UPDATE
                    """,
                    (liberacao_id, clinica_id),
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
                    JOIN agenda_medica_liberacoes l
                      ON l.id = m.liberacao_id
                     AND l.clinica_id = m.clinica_id
                    WHERE l.clinica_id = %s
                      AND l.cbo = %s
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
                        clinica_id,
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
                        clinica_id,
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
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        clinica_id,
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
                      AND clinica_id = %s
                    """,
                    (liberacao_id, clinica_id),
                )

            conn.commit()

        log_edicao(
            modulo=MODULO_AGENDA,
            entidade="agenda_medica_marcacoes",
            entidade_id=marcacao_id,
            descricao="Criou solicitação de marcação na agenda médica.",
            detalhes={
                "clinica_id": clinica_id,
                "liberacao_id": liberacao_id,
                "paciente_id": paciente_id,
                "paciente_nome": paciente_nome,
                "cbo": liberacao["cbo"],
                "data_atendimento": serializar(liberacao["data_atendimento"]),
            },
        )

        return jsonify({
            "ok": True,
            "id": marcacao_id,
            "mensagem": "Solicitação enviada com sucesso.",
        })

    except Exception as e:
        log_api_erro(e, "Erro ao criar marcação na agenda médica.")
        return jsonify({"ok": False, "erro": str(e)}), 500