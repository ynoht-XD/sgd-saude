# atendimentos/chama_na_tela.py
from __future__ import annotations

from flask import Blueprint, render_template, request, jsonify, session, abort

try:
    from db import conectar_db
except ImportError:
    conectar_db = None

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


chama_tela_bp = Blueprint(
    "chama_tela",
    __name__,
    template_folder="templates",
    static_folder="static",
    url_prefix="/atendimentos/chama-na-tela"
)


# ============================================================
# HELPERS
# ============================================================

def get_conn():
    if conectar_db:
        return conectar_db()
    raise RuntimeError("Função conectar_db() não encontrada.")


def is_postgres_conn(conn):
    return conn.__class__.__module__.startswith("psycopg2")


def placeholder(conn):
    return "%s" if is_postgres_conn(conn) else "?"


def row_get(row, key, index=None, default=None):
    if row is None:
        return default

    if isinstance(row, dict):
        return row.get(key, default)

    if hasattr(row, "keys"):
        try:
            return row[key]
        except Exception:
            pass

    if index is not None:
        try:
            return row[index]
        except Exception:
            return default

    return default


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


def table_has_column(conn, table: str, column: str) -> bool:
    cur = conn.cursor()

    try:
        if is_postgres_conn(conn):
            cur.execute("""
                SELECT 1
                  FROM information_schema.columns
                 WHERE table_name = %s
                   AND column_name = %s
                 LIMIT 1
            """, (table, column))
            return cur.fetchone() is not None

        cur.execute(f"PRAGMA table_info({table})")
        cols = [r[1] for r in cur.fetchall() or []]
        return column in cols
    finally:
        cur.close()


# ============================================================
# SCHEMA
# ============================================================

def ensure_chamada_table():
    conn = get_conn()
    pg = is_postgres_conn(conn)
    cur = conn.cursor()

    try:
        if pg:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chamadas_pacientes (
                    id SERIAL PRIMARY KEY,
                    clinica_id INTEGER,
                    paciente_id INTEGER,
                    paciente_nome TEXT NOT NULL,
                    profissional_id INTEGER,
                    profissional_nome TEXT,
                    cbo TEXT,
                    setor TEXT,
                    status TEXT DEFAULT 'pendente',
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    exibido_em TIMESTAMP,
                    criado_por INTEGER
                );
            """)

            for col_sql in (
                "ALTER TABLE chamadas_pacientes ADD COLUMN IF NOT EXISTS clinica_id INTEGER;",
                "ALTER TABLE chamadas_pacientes ADD COLUMN IF NOT EXISTS profissional_id INTEGER;",
                "ALTER TABLE chamadas_pacientes ADD COLUMN IF NOT EXISTS cbo TEXT;",
                "ALTER TABLE chamadas_pacientes ADD COLUMN IF NOT EXISTS exibido_em TIMESTAMP;",
                "ALTER TABLE chamadas_pacientes ADD COLUMN IF NOT EXISTS criado_por INTEGER;",
            ):
                cur.execute(col_sql)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS tv_anuncios (
                    id SERIAL PRIMARY KEY,
                    clinica_id INTEGER,
                    titulo TEXT NOT NULL,
                    mensagem TEXT,
                    imagem_url TEXT,
                    video_url TEXT,
                    tipo TEXT DEFAULT 'texto',
                    ativo BOOLEAN DEFAULT TRUE,
                    ordem INTEGER DEFAULT 0,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    criado_por INTEGER
                );
            """)

            for col_sql in (
                "ALTER TABLE tv_anuncios ADD COLUMN IF NOT EXISTS clinica_id INTEGER;",
                "ALTER TABLE tv_anuncios ADD COLUMN IF NOT EXISTS titulo TEXT;",
                "ALTER TABLE tv_anuncios ADD COLUMN IF NOT EXISTS mensagem TEXT;",
                "ALTER TABLE tv_anuncios ADD COLUMN IF NOT EXISTS imagem_url TEXT;",
                "ALTER TABLE tv_anuncios ADD COLUMN IF NOT EXISTS video_url TEXT;",
                "ALTER TABLE tv_anuncios ADD COLUMN IF NOT EXISTS tipo TEXT DEFAULT 'texto';",
                "ALTER TABLE tv_anuncios ADD COLUMN IF NOT EXISTS ativo BOOLEAN DEFAULT TRUE;",
                "ALTER TABLE tv_anuncios ADD COLUMN IF NOT EXISTS ordem INTEGER DEFAULT 0;",
                "ALTER TABLE tv_anuncios ADD COLUMN IF NOT EXISTS criado_por INTEGER;",
            ):
                cur.execute(col_sql)

        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chamadas_pacientes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    clinica_id INTEGER,
                    paciente_id INTEGER,
                    paciente_nome TEXT NOT NULL,
                    profissional_id INTEGER,
                    profissional_nome TEXT,
                    cbo TEXT,
                    setor TEXT,
                    status TEXT DEFAULT 'pendente',
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    exibido_em TIMESTAMP,
                    criado_por INTEGER
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS tv_anuncios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    clinica_id INTEGER,
                    titulo TEXT NOT NULL,
                    mensagem TEXT,
                    imagem_url TEXT,
                    video_url TEXT,
                    tipo TEXT DEFAULT 'texto',
                    ativo INTEGER DEFAULT 1,
                    ordem INTEGER DEFAULT 0,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    criado_por INTEGER
                );
            """)

            for table, columns in {
                "chamadas_pacientes": {
                    "clinica_id": "INTEGER",
                    "profissional_id": "INTEGER",
                    "cbo": "TEXT",
                    "exibido_em": "TIMESTAMP",
                    "criado_por": "INTEGER",
                },
                "tv_anuncios": {
                    "clinica_id": "INTEGER",
                    "mensagem": "TEXT",
                    "imagem_url": "TEXT",
                    "video_url": "TEXT",
                    "tipo": "TEXT DEFAULT 'texto'",
                    "ativo": "INTEGER DEFAULT 1",
                    "ordem": "INTEGER DEFAULT 0",
                    "atualizado_em": "TIMESTAMP",
                    "criado_por": "INTEGER",
                }
            }.items():
                cur.execute(f"PRAGMA table_info({table})")
                existentes = [r[1] for r in cur.fetchall() or []]

                for col, tipo in columns.items():
                    if col not in existentes:
                        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {tipo};")

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_chamadas_pacientes_clinica_id
            ON chamadas_pacientes (clinica_id);
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_chamadas_pacientes_status
            ON chamadas_pacientes (status);
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_chamadas_pacientes_clinica_id_id
            ON chamadas_pacientes (clinica_id, id);
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_tv_anuncios_clinica_ativo
            ON tv_anuncios (clinica_id, ativo);
        """)

        conn.commit()

    finally:
        cur.close()
        conn.close()


@chama_tela_bp.before_app_request
def preparar_chamada():
    ensure_chamada_table()


# ============================================================
# BUSCAS
# ============================================================

def buscar_cbo_profissional(conn, profissional_id=None, profissional_nome=None, clinica_id=None):
    cur = conn.cursor()
    ph = placeholder(conn)

    try:
        if profissional_id:
            for tabela in ("usuarios", "profissionais"):
                try:
                    filtro_clinica = ""
                    params = [profissional_id]

                    if clinica_id and table_has_column(conn, tabela, "clinica_id"):
                        filtro_clinica = f" AND (clinica_id = {ph} OR clinica_id IS NULL)"
                        params.append(clinica_id)

                    cur.execute(
                        f"""
                        SELECT COALESCE(cbo, '') AS cbo
                          FROM {tabela}
                         WHERE id = {ph}
                           {filtro_clinica}
                         LIMIT 1
                        """,
                        tuple(params)
                    )

                    row = cur.fetchone()
                    cbo = row_get(row, "cbo", 0, "")
                    if cbo:
                        return str(cbo).strip()
                except Exception:
                    pass

        if profissional_nome:
            for tabela in ("usuarios", "profissionais"):
                try:
                    filtro_clinica = ""
                    params = [profissional_nome]

                    if clinica_id and table_has_column(conn, tabela, "clinica_id"):
                        filtro_clinica = f" AND (clinica_id = {ph} OR clinica_id IS NULL)"
                        params.append(clinica_id)

                    like_sql = f"nome ILIKE {ph}" if is_postgres_conn(conn) else f"LOWER(nome) LIKE LOWER({ph})"

                    cur.execute(
                        f"""
                        SELECT COALESCE(cbo, '') AS cbo
                          FROM {tabela}
                         WHERE {like_sql}
                           {filtro_clinica}
                         LIMIT 1
                        """,
                        tuple(params)
                    )

                    row = cur.fetchone()
                    cbo = row_get(row, "cbo", 0, "")
                    if cbo:
                        return str(cbo).strip()
                except Exception:
                    pass

        return ""

    finally:
        cur.close()


def chamada_to_dict(row):
    return {
        "id": row_get(row, "id", 0),
        "clinica_id": row_get(row, "clinica_id", 1),
        "paciente_id": row_get(row, "paciente_id", 2),
        "paciente_nome": row_get(row, "paciente_nome", 3, ""),
        "profissional_id": row_get(row, "profissional_id", 4),
        "profissional_nome": row_get(row, "profissional_nome", 5, ""),
        "cbo": row_get(row, "cbo", 6, ""),
        "setor": row_get(row, "setor", 7, ""),
        "status": row_get(row, "status", 8, ""),
        "criado_em": str(row_get(row, "criado_em", 9, "")),
        "exibido_em": str(row_get(row, "exibido_em", 10, "") or ""),
    }


def anuncio_to_dict(row):
    return {
        "id": row_get(row, "id", 0),
        "clinica_id": row_get(row, "clinica_id", 1),
        "titulo": row_get(row, "titulo", 2, ""),
        "mensagem": row_get(row, "mensagem", 3, ""),
        "imagem_url": row_get(row, "imagem_url", 4, ""),
        "video_url": row_get(row, "video_url", 5, ""),
        "tipo": row_get(row, "tipo", 6, "texto"),
        "ativo": bool(row_get(row, "ativo", 7, True)),
        "ordem": row_get(row, "ordem", 8, 0),
    }


# ============================================================
# PÁGINA TV
# ============================================================

@chama_tela_bp.route("/tv")
@require_permission("chama_na_tela", "ver")
def tv_recepcao():
    clinica_id = _clinica_id_atual()

    registrar_log(
        modulo="chama_na_tela",
        acao="visualizar",
        entidade="tv",
        descricao="Abriu tela de chamada na TV.",
        detalhes={"clinica_id": clinica_id},
    )

    return render_template(
        "chama_na_tela_tv.html",
        clinica_id=clinica_id,
        clinica_nome=session.get("clinica_nome"),
    )


# ============================================================
# CHAMAR PACIENTE
# ============================================================

@chama_tela_bp.route("/chamar", methods=["POST"])
@require_permission("chama_na_tela", "editar")
def chamar_paciente():
    clinica_id = _clinica_id_atual()
    data = request.get_json(silent=True) or request.form

    paciente_id = data.get("paciente_id") or data.get("id")
    paciente_nome = (data.get("paciente_nome") or data.get("nome") or "").strip()

    profissional_id = data.get("profissional_id") or data.get("prof_id")
    profissional_nome = (data.get("profissional_nome") or data.get("profissional") or "").strip()

    cbo = (
        data.get("cbo")
        or data.get("profissional_cbo")
        or data.get("modalidade")
        or ""
    )
    cbo = str(cbo).strip()

    setor = (data.get("setor") or data.get("local") or "Recepção").strip()

    if not paciente_nome:
        return jsonify(ok=False, erro="Nome do paciente não informado."), 400

    try:
        conn = get_conn()
        ph = placeholder(conn)

        if not cbo:
            cbo = buscar_cbo_profissional(
                conn,
                profissional_id=profissional_id,
                profissional_nome=profissional_nome,
                clinica_id=clinica_id,
            )

        cur = conn.cursor()

        cur.execute(
            f"""
            INSERT INTO chamadas_pacientes (
                clinica_id,
                paciente_id,
                paciente_nome,
                profissional_id,
                profissional_nome,
                cbo,
                setor,
                status,
                criado_em,
                criado_por
            )
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, CURRENT_TIMESTAMP, {ph})
            """,
            (
                clinica_id,
                paciente_id,
                paciente_nome,
                profissional_id,
                profissional_nome,
                cbo,
                setor,
                "pendente",
                _usuario_id_atual(),
            )
        )

        conn.commit()
        cur.close()
        conn.close()

        registrar_log(
            modulo="chama_na_tela",
            acao="criar",
            entidade="chamadas_pacientes",
            descricao="Paciente enviado para chamada na TV.",
            detalhes={
                "clinica_id": clinica_id,
                "paciente_id": paciente_id,
                "paciente_nome": paciente_nome,
                "profissional_id": profissional_id,
                "profissional_nome": profissional_nome,
                "cbo": cbo,
                "setor": setor,
            },
        )

        return jsonify(
            ok=True,
            mensagem=f"{paciente_nome} entrou na fila de chamada.",
            paciente_nome=paciente_nome,
            profissional_nome=profissional_nome,
            cbo=cbo,
        )

    except Exception as e:
        log_erro(
            "chama_na_tela",
            e,
            entidade="chamadas_pacientes",
            descricao="Erro ao chamar paciente na TV.",
            detalhes={
                "clinica_id": clinica_id,
                "paciente_id": paciente_id,
                "paciente_nome": paciente_nome,
                "profissional_id": profissional_id,
            },
        )
        return jsonify(ok=False, erro=str(e)), 500


# ============================================================
# APIs DE CHAMADAS
# ============================================================

@chama_tela_bp.route("/api/ultima")
@require_permission("chama_na_tela", "ver")
def api_ultima_chamada():
    clinica_id = _clinica_id_atual()

    try:
        conn = get_conn()
        ph = placeholder(conn)
        cur = conn.cursor()

        cur.execute(
            f"""
            SELECT
                id,
                clinica_id,
                paciente_id,
                paciente_nome,
                profissional_id,
                profissional_nome,
                cbo,
                setor,
                status,
                criado_em,
                exibido_em
            FROM chamadas_pacientes
            WHERE clinica_id = {ph}
            ORDER BY id DESC
            LIMIT 1
            """,
            (clinica_id,)
        )

        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            return jsonify(ok=True, chamada=None)

        return jsonify(ok=True, chamada=chamada_to_dict(row))

    except Exception as e:
        log_erro("chama_na_tela", e, entidade="chamadas_pacientes", descricao="Erro ao buscar última chamada.", detalhes={"clinica_id": clinica_id})
        return jsonify(ok=False, erro=str(e)), 500


@chama_tela_bp.route("/api/recentes")
@require_permission("chama_na_tela", "ver")
def api_chamadas_recentes():
    clinica_id = _clinica_id_atual()

    try:
        conn = get_conn()
        ph = placeholder(conn)
        cur = conn.cursor()

        cur.execute(
            f"""
            SELECT
                id,
                clinica_id,
                paciente_id,
                paciente_nome,
                profissional_id,
                profissional_nome,
                cbo,
                setor,
                status,
                criado_em,
                exibido_em
            FROM chamadas_pacientes
            WHERE clinica_id = {ph}
            ORDER BY id DESC
            LIMIT 4
            """,
            (clinica_id,)
        )

        rows = cur.fetchall() or []
        cur.close()
        conn.close()

        return jsonify(ok=True, chamadas=[chamada_to_dict(r) for r in rows])

    except Exception as e:
        log_erro("chama_na_tela", e, entidade="chamadas_pacientes", descricao="Erro ao buscar chamadas recentes.", detalhes={"clinica_id": clinica_id})
        return jsonify(ok=False, erro=str(e)), 500


@chama_tela_bp.route("/api/fila")
@require_permission("chama_na_tela", "ver")
def api_fila_chamadas():
    clinica_id = _clinica_id_atual()

    after_id_raw = request.args.get("after_id") or "0"

    try:
        after_id = int(after_id_raw)
    except ValueError:
        after_id = 0

    try:
        conn = get_conn()
        ph = placeholder(conn)
        cur = conn.cursor()

        cur.execute(
            f"""
            SELECT
                id,
                clinica_id,
                paciente_id,
                paciente_nome,
                profissional_id,
                profissional_nome,
                cbo,
                setor,
                status,
                criado_em,
                exibido_em
            FROM chamadas_pacientes
            WHERE clinica_id = {ph}
              AND id > {ph}
            ORDER BY id ASC
            LIMIT 10
            """,
            (clinica_id, after_id)
        )

        rows = cur.fetchall() or []
        cur.close()
        conn.close()

        return jsonify(ok=True, chamadas=[chamada_to_dict(r) for r in rows])

    except Exception as e:
        log_erro("chama_na_tela", e, entidade="chamadas_pacientes", descricao="Erro ao buscar fila de chamadas.", detalhes={"clinica_id": clinica_id, "after_id": after_id})
        return jsonify(ok=False, erro=str(e)), 500


@chama_tela_bp.route("/api/marcar-exibida/<int:chamada_id>", methods=["POST"])
@require_permission("chama_na_tela", "editar")
def api_marcar_chamada_exibida(chamada_id):
    clinica_id = _clinica_id_atual()

    try:
        conn = get_conn()
        ph = placeholder(conn)
        cur = conn.cursor()

        cur.execute(
            f"""
            UPDATE chamadas_pacientes
               SET status = {ph},
                   exibido_em = CURRENT_TIMESTAMP
             WHERE id = {ph}
               AND clinica_id = {ph}
            """,
            ("exibida", chamada_id, clinica_id)
        )

        conn.commit()
        cur.close()
        conn.close()

        return jsonify(ok=True)

    except Exception as e:
        log_erro("chama_na_tela", e, entidade="chamadas_pacientes", entidade_id=chamada_id, descricao="Erro ao marcar chamada como exibida.", detalhes={"clinica_id": clinica_id})
        return jsonify(ok=False, erro=str(e)), 500


# ============================================================
# ANÚNCIOS PARA TV
# ============================================================

@chama_tela_bp.route("/api/anuncios")
@require_permission("chama_na_tela", "ver")
def api_anuncios():
    clinica_id = _clinica_id_atual()

    try:
        conn = get_conn()
        ph = placeholder(conn)
        cur = conn.cursor()

        cur.execute(
            f"""
            SELECT
                id,
                clinica_id,
                titulo,
                COALESCE(mensagem, '') AS mensagem,
                COALESCE(imagem_url, '') AS imagem_url,
                COALESCE(video_url, '') AS video_url,
                COALESCE(tipo, 'texto') AS tipo,
                ativo,
                COALESCE(ordem, 0) AS ordem
            FROM tv_anuncios
            WHERE clinica_id = {ph}
              AND ativo = {ph}
            ORDER BY ordem ASC, id ASC
            LIMIT 50
            """,
            (clinica_id, True if is_postgres_conn(conn) else 1)
        )

        rows = cur.fetchall() or []
        cur.close()
        conn.close()

        return jsonify(ok=True, anuncios=[anuncio_to_dict(r) for r in rows])

    except Exception as e:
        log_erro("chama_na_tela", e, entidade="tv_anuncios", descricao="Erro ao listar anúncios da TV.", detalhes={"clinica_id": clinica_id})
        return jsonify(ok=False, erro=str(e)), 500


@chama_tela_bp.route("/api/anuncios", methods=["POST"])
@require_permission("chama_na_tela", "editar")
def api_criar_anuncio():
    clinica_id = _clinica_id_atual()
    data = request.get_json(silent=True) or request.form

    titulo = (data.get("titulo") or "").strip()
    mensagem = (data.get("mensagem") or "").strip()
    imagem_url = (data.get("imagem_url") or "").strip()
    video_url = (data.get("video_url") or "").strip()
    tipo = (data.get("tipo") or "texto").strip()
    ordem = data.get("ordem") or 0

    if not titulo:
        return jsonify(ok=False, erro="Título do anúncio é obrigatório."), 400

    try:
        ordem = int(ordem)
    except Exception:
        ordem = 0

    try:
        conn = get_conn()
        ph = placeholder(conn)
        cur = conn.cursor()

        cur.execute(
            f"""
            INSERT INTO tv_anuncios (
                clinica_id,
                titulo,
                mensagem,
                imagem_url,
                video_url,
                tipo,
                ativo,
                ordem,
                criado_em,
                atualizado_em,
                criado_por
            )
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, {ph})
            """,
            (
                clinica_id,
                titulo,
                mensagem,
                imagem_url,
                video_url,
                tipo,
                True if is_postgres_conn(conn) else 1,
                ordem,
                _usuario_id_atual(),
            )
        )

        conn.commit()
        cur.close()
        conn.close()

        registrar_log(
            modulo="chama_na_tela",
            acao="criar",
            entidade="tv_anuncios",
            descricao="Criou anúncio para TV.",
            detalhes={
                "clinica_id": clinica_id,
                "titulo": titulo,
                "tipo": tipo,
            },
        )

        return jsonify(ok=True)

    except Exception as e:
        log_erro("chama_na_tela", e, entidade="tv_anuncios", descricao="Erro ao criar anúncio para TV.", detalhes={"clinica_id": clinica_id, "titulo": titulo})
        return jsonify(ok=False, erro=str(e)), 500