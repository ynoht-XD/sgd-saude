from __future__ import annotations

from datetime import date, datetime
from flask import (
    render_template,
    request,
    jsonify,
    redirect,
    url_for,
    flash,
    session,
    abort,
)

from . import atendimentos_bp
from db import conectar_db

from .helpers import (
    _row_get,
    has_table,
    has_column,
    table_columns,
    ensure_fila_table,
    ensure_atendimentos_schema,
    resolve_paciente,
    resolve_prof_id_by_nome_ou_cpf,
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


# =============================================================================
# CONTEXTO
# =============================================================================

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


def _fetchall_dicts(cur):
    rows = cur.fetchall() or []
    cols = [c[0] for c in cur.description] if cur.description else []
    out = []

    for r in rows:
        if isinstance(r, dict):
            out.append(dict(r))
        else:
            out.append({cols[i]: r[i] for i in range(min(len(cols), len(r)))})

    return out


def _fetchone_dict(cur):
    row = cur.fetchone()
    if not row:
        return None

    if isinstance(row, dict):
        return dict(row)

    cols = [c[0] for c in cur.description] if cur.description else []
    return {cols[i]: row[i] for i in range(min(len(cols), len(row)))}


# =============================================================================
# SCHEMA
# =============================================================================

def ensure_lista_atendimentos_schema(conn):
    ensure_fila_table(conn)
    ensure_atendimentos_schema(conn)

    cur = conn.cursor()

    cur.execute("""
        ALTER TABLE fila_atendimentos
        ADD COLUMN IF NOT EXISTS clinica_id INTEGER;
    """)

    cur.execute("""
        ALTER TABLE fila_atendimentos
        ADD COLUMN IF NOT EXISTS removido_em TIMESTAMP;
    """)

    cur.execute("""
        ALTER TABLE fila_atendimentos
        ADD COLUMN IF NOT EXISTS removido_por INTEGER;
    """)

    cur.execute("""
        ALTER TABLE fila_atendimentos
        ADD COLUMN IF NOT EXISTS motivo_remocao TEXT;
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_fila_clinica_status
        ON fila_atendimentos(clinica_id, status);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_fila_clinica_created
        ON fila_atendimentos(clinica_id, created_at);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_fila_clinica_paciente
        ON fila_atendimentos(clinica_id, paciente_id);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_fila_clinica_profissional
        ON fila_atendimentos(clinica_id, profissional_id);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_fila_clinica_agenda
        ON fila_atendimentos(clinica_id, agenda_id);
    """)

    conn.commit()


# =============================================================================
# HELPERS
# =============================================================================

def _hora_atual_hhmm() -> str:
    return datetime.now().strftime("%H:%M")


def _safe_status_aberto_sql(alias: str = "f"):
    return f"""
    (
        {alias}.status IS NULL
        OR TRIM({alias}.status) = ''
        OR LOWER(TRIM({alias}.status)) IN ('aguardando', 'pendente', 'chamado', 'em_atendimento', 'ativo')
    )
    """


def _buscar_fila_item(conn, fila_id: int, clinica_id: int):
    cur = conn.cursor()
    cur.execute("""
        SELECT *
          FROM fila_atendimentos
         WHERE id = %s
           AND clinica_id = %s
         LIMIT 1;
    """, (fila_id, clinica_id))
    return _fetchone_dict(cur)


def _listar_fila(conn, clinica_id: int, apenas_hoje: bool = True) -> list[dict]:
    ensure_lista_atendimentos_schema(conn)
    cur = conn.cursor()

    filtro_data = "AND DATE(f.created_at) = CURRENT_DATE" if apenas_hoje else ""

    cur.execute(f"""
        SELECT
            f.id,
            f.clinica_id,
            f.hora,
            f.paciente_id,
            COALESCE(f.paciente_nome, p.nome, '') AS paciente_nome,
            f.profissional_id,
            COALESCE(u.nome, '') AS profissional_nome,
            COALESCE(u.cbo, '') AS profissional_cbo,
            f.tipo,
            f.prioridade,
            f.obs,
            f.origem,
            f.agenda_id,
            COALESCE(f.status, '') AS status,
            f.created_at,
            f.removido_em,
            f.motivo_remocao,
            COALESCE(p.prontuario, '') AS prontuario,
            COALESCE(p.cpf, '') AS cpf,
            COALESCE(p.cns, '') AS cns,
            COALESCE(p.mod, '') AS mod,
            COALESCE(p.status, '') AS status_paciente
        FROM fila_atendimentos f
        LEFT JOIN pacientes p
               ON p.id = f.paciente_id
              AND (
                    p.clinica_id = f.clinica_id
                    OR p.clinica_id IS NULL
                  )
        LEFT JOIN usuarios u
               ON u.id = f.profissional_id
              AND (
                    u.clinica_id = f.clinica_id
                    OR u.clinica_id IS NULL
                  )
        WHERE f.clinica_id = %s
          {filtro_data}
          AND {_safe_status_aberto_sql("f")}
        ORDER BY
            CASE LOWER(COALESCE(f.prioridade, 'verde'))
                WHEN 'vermelho' THEN 1
                WHEN 'laranja' THEN 2
                WHEN 'amarelo' THEN 3
                WHEN 'verde' THEN 4
                ELSE 5
            END,
            f.hora ASC,
            f.id ASC;
    """, (clinica_id,))

    return _fetchall_dicts(cur)


def _resolver_paciente_profissional(conn, data):
    paciente_id = (data.get("paciente_id") or data.get("paciente") or "").strip()
    paciente_texto = (data.get("paciente_nome") or data.get("nome_paciente") or "").strip()

    profissional_id_raw = (data.get("profissional_id") or "").strip()
    profissional_nome = (data.get("profissional_nome") or data.get("profissional") or "").strip()
    profissional_cpf = (data.get("profissional_cpf") or "").strip()

    paciente = resolve_paciente(conn, paciente_id, paciente_texto)

    prof_id = None
    if profissional_id_raw.isdigit():
        prof_id = int(profissional_id_raw)
    else:
        prof_id = resolve_prof_id_by_nome_ou_cpf(conn, profissional_nome, profissional_cpf)

    return paciente, prof_id


# =============================================================================
# SINCRONIZAÇÃO SEGURA AGENDA → FILA
# =============================================================================

def sync_today_agenda_to_fila_seguro(conn, clinica_id: int) -> None:
    """
    Sincroniza a agenda de hoje com a fila.

    Regra importante:
    Se um agendamento já gerou uma fila alguma vez, mesmo removida,
    ele NÃO será recriado ao recarregar a página.
    """
    if not has_table(conn, "agendamentos"):
        return

    if not has_table(conn, "pacientes"):
        return

    ensure_lista_atendimentos_schema(conn)

    ag_cols = table_columns(conn, "agendamentos")
    cur = conn.cursor()

    has_ag_clinica = "clinica_id" in ag_cols
    has_paciente_id = "paciente_id" in ag_cols
    has_profissional_id = "profissional_id" in ag_cols
    has_profissional_cpf = "profissional_cpf" in ag_cols

    paciente_id_expr = "a.paciente_id" if has_paciente_id else "NULL::integer"
    profissional_id_expr = "a.profissional_id" if has_profissional_id else "NULL::integer"
    profissional_cpf_expr = "COALESCE(a.profissional_cpf, '')" if has_profissional_cpf else "''"

    filtro_clinica = "AND a.clinica_id = %s" if has_ag_clinica else ""
    params = [clinica_id] if has_ag_clinica else []

    cur.execute(f"""
        SELECT
            a.id AS agenda_id,
            {paciente_id_expr} AS paciente_id,
            COALESCE(a.paciente, '') AS paciente_nome,
            {profissional_id_expr} AS profissional_id,
            COALESCE(a.profissional, '') AS profissional_nome,
            {profissional_cpf_expr} AS profissional_cpf,
            TO_CHAR(a.inicio, 'HH24:MI') AS hora
        FROM agendamentos a
        WHERE DATE(a.inicio) = CURRENT_DATE
          {filtro_clinica}
          AND COALESCE(a.status, 'ativo') NOT IN ('cancelado', 'removido', 'excluido')
        ORDER BY a.inicio ASC, a.id ASC;
    """, params)

    agendamentos = _fetchall_dicts(cur)

    for ag in agendamentos:
        agenda_id = ag.get("agenda_id")
        paciente_id = ag.get("paciente_id")
        paciente_nome = (ag.get("paciente_nome") or "").strip()
        profissional_id = ag.get("profissional_id")
        profissional_nome = (ag.get("profissional_nome") or "").strip()
        profissional_cpf = (ag.get("profissional_cpf") or "").strip()
        hora = (ag.get("hora") or "").strip()

        if not hora or not paciente_nome:
            continue

        # 1) Se este agenda_id já gerou fila alguma vez, não recria.
        cur.execute("""
            SELECT 1
              FROM fila_atendimentos
             WHERE clinica_id = %s
               AND agenda_id = %s
             LIMIT 1;
        """, (clinica_id, agenda_id))

        if cur.fetchone():
            continue

        # 2) Resolve paciente caso a agenda não tenha paciente_id.
        if not paciente_id:
            paciente = resolve_paciente(conn, None, paciente_nome)
            if not paciente:
                continue
            paciente_id = paciente.get("id")
            paciente_nome = paciente.get("nome") or paciente_nome

        # 3) Resolve profissional caso a agenda não tenha profissional_id.
        if not profissional_id:
            profissional_id = resolve_prof_id_by_nome_ou_cpf(
                conn,
                profissional_nome,
                profissional_cpf,
            )

        if not profissional_id:
            continue

        # 4) Se já foi atendido hoje, não joga na fila.
        cur.execute("""
            SELECT 1
              FROM atendimentos
             WHERE clinica_id = %s
               AND paciente_id = %s
               AND data_atendimento = CURRENT_DATE
             LIMIT 1;
        """, (clinica_id, paciente_id))

        if cur.fetchone():
            continue

        # 5) Fallback extra: se já existe uma fila do mesmo paciente/prof/hora hoje,
        # mesmo sem agenda_id, não duplica.
        cur.execute("""
            SELECT 1
              FROM fila_atendimentos
             WHERE clinica_id = %s
               AND paciente_id = %s
               AND profissional_id = %s
               AND hora = %s
               AND DATE(created_at) = CURRENT_DATE
             LIMIT 1;
        """, (clinica_id, paciente_id, profissional_id, hora))

        if cur.fetchone():
            continue

        cur.execute("""
            INSERT INTO fila_atendimentos (
                clinica_id,
                hora,
                paciente_id,
                paciente_nome,
                profissional_id,
                tipo,
                prioridade,
                obs,
                origem,
                agenda_id,
                status,
                created_at
            )
            VALUES (
                %s, %s, %s, %s, %s,
                'Individual',
                'verde',
                '',
                'agenda',
                %s,
                'aguardando',
                CURRENT_TIMESTAMP
            );
        """, (
            clinica_id,
            hora,
            paciente_id,
            paciente_nome,
            profissional_id,
            agenda_id,
        ))

    conn.commit()


# =============================================================================
# PÁGINA PRINCIPAL
# =============================================================================

@atendimentos_bp.route("/", methods=["GET"], endpoint="lista_atendimentos")
@atendimentos_bp.route("/lista", methods=["GET"])
@require_permission("lista_atendimentos", "ver")
def lista_atendimentos():
    clinica_id = _clinica_id_atual()

    try:
        with conectar_db() as conn:
            ensure_lista_atendimentos_schema(conn)
            sync_today_agenda_to_fila_seguro(conn, clinica_id)
            fila = _listar_fila(conn, clinica_id, apenas_hoje=True)

        registrar_log(
            modulo="lista_atendimentos",
            acao="visualizar",
            entidade="fila_atendimentos",
            descricao="Visualizou lista de atendimentos.",
            detalhes={
                "clinica_id": clinica_id,
                "total": len(fila),
            },
        )

        return render_template(
            "lista_atendimentos.html",
            fila=fila,
            itens=fila,
            atendimentos=fila,
            data_hoje=date.today().isoformat(),
            clinica_id=clinica_id,
            clinica_nome=session.get("clinica_nome"),
        )

    except Exception as e:
        log_erro(
            "lista_atendimentos",
            e,
            entidade="fila_atendimentos",
            descricao="Erro ao abrir lista de atendimentos.",
            detalhes={"clinica_id": clinica_id},
        )
        return f"Erro ao abrir lista de atendimentos: {e}", 500


# =============================================================================
# API LISTAR
# =============================================================================

@atendimentos_bp.get("/api/fila", endpoint="api_lista_fila")
@require_permission("lista_atendimentos", "ver")
def api_lista_fila():
    clinica_id = _clinica_id_atual()

    try:
        with conectar_db() as conn:
            ensure_lista_atendimentos_schema(conn)
            sync_today_agenda_to_fila_seguro(conn, clinica_id)
            fila = _listar_fila(conn, clinica_id, apenas_hoje=True)

        return jsonify({"ok": True, "items": fila, "total": len(fila)})

    except Exception as e:
        log_erro(
            "lista_atendimentos",
            e,
            entidade="fila_atendimentos",
            descricao="Erro ao listar fila via API.",
            detalhes={"clinica_id": clinica_id},
        )
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================================
# API SUGESTÕES · PACIENTES
# =============================================================================

@atendimentos_bp.get("/api/pacientes")
@atendimentos_bp.get("/api/sugestoes_pacientes_lista")
@atendimentos_bp.get("/api/lista/pacientes")
@require_permission("lista_atendimentos", "ver")
def api_sugestoes_pacientes_lista():
    clinica_id = _clinica_id_atual()
    q = (
        request.args.get("q")
        or request.args.get("termo")
        or request.args.get("busca")
        or ""
    ).strip()

    if len(q) < 2:
        return jsonify([])

    try:
        with conectar_db() as conn:
            if not has_table(conn, "pacientes"):
                return jsonify([])

            cols = table_columns(conn, "pacientes")
            filtro_clinica = "AND clinica_id = %s" if "clinica_id" in cols else ""

            col_cpf = "cpf" if "cpf" in cols else "''"
            col_cns = "cns" if "cns" in cols else "''"
            col_pront = "prontuario" if "prontuario" in cols else "''"
            col_tel = "COALESCE(telefone, telefone1, '')" if "telefone" in cols and "telefone1" in cols else (
                "COALESCE(telefone, '')" if "telefone" in cols else (
                    "COALESCE(telefone1, '')" if "telefone1" in cols else "''"
                )
            )

            params = []
            if filtro_clinica:
                params.append(clinica_id)

            like = f"%{q}%"
            params.extend([like, like, like, like])

            cur = conn.cursor()
            cur.execute(f"""
                SELECT
                    id,
                    COALESCE(nome, '') AS nome,
                    COALESCE({col_cpf}, '') AS cpf,
                    COALESCE({col_cns}, '') AS cns,
                    COALESCE({col_pront}, '') AS prontuario,
                    {col_tel} AS telefone
                FROM pacientes
                WHERE 1=1
                  {filtro_clinica}
                  AND (
                        nome ILIKE %s
                        OR COALESCE({col_cpf}, '') ILIKE %s
                        OR COALESCE({col_cns}, '') ILIKE %s
                        OR COALESCE({col_pront}, '') ILIKE %s
                  )
                ORDER BY nome
                LIMIT 20;
            """, params)

            rows = _fetchall_dicts(cur)

        return jsonify([
            {
                "id": r.get("id"),
                "nome": r.get("nome") or "",
                "cpf": r.get("cpf") or "",
                "cns": r.get("cns") or "",
                "prontuario": r.get("prontuario") or "",
                "telefone": r.get("telefone") or "",
                "label": f"{r.get('nome') or ''} · Pront: {r.get('prontuario') or '—'}",
            }
            for r in rows
        ])

    except Exception as e:
        log_erro(
            "lista_atendimentos",
            e,
            entidade="pacientes",
            descricao="Erro ao buscar sugestões de pacientes na lista.",
            detalhes={"clinica_id": clinica_id, "q": q},
        )
        return jsonify([]), 500


# =============================================================================
# API SUGESTÕES · PROFISSIONAIS
# =============================================================================

@atendimentos_bp.get("/api/profissionais")
@atendimentos_bp.get("/api/sugestoes_profissionais")
@atendimentos_bp.get("/api/lista/profissionais")
@require_permission("lista_atendimentos", "ver")
def api_sugestoes_profissionais_lista():
    clinica_id = _clinica_id_atual()
    q = (
        request.args.get("q")
        or request.args.get("termo")
        or request.args.get("busca")
        or ""
    ).strip()

    if len(q) < 2:
        return jsonify([])

    try:
        with conectar_db() as conn:
            if not has_table(conn, "usuarios"):
                return jsonify([])

            cols = table_columns(conn, "usuarios")

            nome_expr = "COALESCE(nome, '')" if "nome" in cols else "''"
            cpf_expr = "COALESCE(cpf, '')" if "cpf" in cols else "''"
            cbo_expr = "COALESCE(cbo, '')" if "cbo" in cols else "''"

            conds = []
            params = []

            if "clinica_id" in cols:
                conds.append("clinica_id = %s")
                params.append(clinica_id)

            if "is_active" in cols:
                conds.append("(is_active IS TRUE OR is_active IS NULL)")

            if "role" in cols:
                conds.append("UPPER(COALESCE(role, '')) IN ('PROFISSIONAL', 'ADMIN', 'RECEPCAO', 'RECEPÇÃO')")

            where_extra = "AND " + " AND ".join(conds) if conds else ""

            like = f"%{q}%"
            params.extend([like, like, like])

            cur = conn.cursor()
            cur.execute(f"""
                SELECT
                    id,
                    {nome_expr} AS nome,
                    {cpf_expr} AS cpf,
                    {cbo_expr} AS cbo
                FROM usuarios
                WHERE 1=1
                  {where_extra}
                  AND (
                        {nome_expr} ILIKE %s
                        OR {cpf_expr} ILIKE %s
                        OR {cbo_expr} ILIKE %s
                  )
                ORDER BY nome
                LIMIT 20;
            """, params)

            rows = _fetchall_dicts(cur)

        return jsonify([
            {
                "id": r.get("id"),
                "nome": r.get("nome") or "",
                "cpf": r.get("cpf") or "",
                "cbo": r.get("cbo") or "",
                "label": f"{r.get('nome') or ''} · CBO: {r.get('cbo') or '—'}",
            }
            for r in rows
        ])

    except Exception as e:
        log_erro(
            "lista_atendimentos",
            e,
            entidade="usuarios",
            descricao="Erro ao buscar sugestões de profissionais na lista.",
            detalhes={"clinica_id": clinica_id, "q": q},
        )
        return jsonify([]), 500


# =============================================================================
# ADICIONAR NA FILA
# =============================================================================

@atendimentos_bp.route("/adicionar", methods=["POST"], endpoint="adicionar_atendimento")
@require_permission("lista_atendimentos", "editar")
def adicionar_atendimento():
    clinica_id = _clinica_id_atual()
    is_json = request.is_json
    data = request.get_json(silent=True) if is_json else request.form

    try:
        with conectar_db() as conn:
            ensure_lista_atendimentos_schema(conn)

            paciente, profissional_id = _resolver_paciente_profissional(conn, data)

            if not paciente:
                msg = "Paciente não encontrado nesta clínica."
                if is_json:
                    return jsonify({"ok": False, "error": msg}), 404
                flash(msg, "error")
                return redirect(url_for("atendimentos.lista_atendimentos"))

            if not profissional_id:
                msg = "Profissional não encontrado."
                if is_json:
                    return jsonify({"ok": False, "error": msg}), 404
                flash(msg, "error")
                return redirect(url_for("atendimentos.lista_atendimentos"))

            hora = (data.get("hora") or _hora_atual_hhmm()).strip()
            tipo = (data.get("tipo") or "Individual").strip()
            prioridade = (data.get("prioridade") or "verde").strip()
            obs = (data.get("obs") or data.get("observacao") or "").strip()

            cur = conn.cursor()
            cur.execute("""
                INSERT INTO fila_atendimentos (
                    clinica_id,
                    hora,
                    paciente_id,
                    paciente_nome,
                    profissional_id,
                    tipo,
                    prioridade,
                    obs,
                    origem,
                    status,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'manual', 'aguardando', CURRENT_TIMESTAMP)
                RETURNING id;
            """, (
                clinica_id,
                hora,
                paciente.get("id"),
                paciente.get("nome"),
                profissional_id,
                tipo,
                prioridade,
                obs,
            ))

            fila_id = _row_get(cur.fetchone(), "id", 0)
            conn.commit()

        registrar_log(
            modulo="lista_atendimentos",
            acao="criar",
            entidade="fila_atendimentos",
            entidade_id=fila_id,
            descricao="Adicionou paciente à lista de atendimentos.",
            detalhes={
                "clinica_id": clinica_id,
                "fila_id": fila_id,
                "paciente_id": paciente.get("id"),
                "paciente_nome": paciente.get("nome"),
                "profissional_id": profissional_id,
                "origem": "manual",
            },
        )

        if is_json:
            return jsonify({"ok": True, "id": fila_id})

        flash("Paciente adicionado à lista.", "success")
        return redirect(url_for("atendimentos.lista_atendimentos"))

    except Exception as e:
        log_erro(
            "lista_atendimentos",
            e,
            entidade="fila_atendimentos",
            descricao="Erro ao adicionar paciente à lista.",
            detalhes={"clinica_id": clinica_id, "payload": dict(data)},
        )

        if is_json:
            return jsonify({"ok": False, "error": str(e)}), 500

        flash(f"Erro ao adicionar paciente: {e}", "error")
        return redirect(url_for("atendimentos.lista_atendimentos"))


# =============================================================================
# REMOVER DA FILA
# =============================================================================

@atendimentos_bp.route("/remover/<int:fila_id>", methods=["POST", "DELETE"], endpoint="remover_atendimento_fila")
@atendimentos_bp.route("/fila/<int:fila_id>/remover", methods=["POST", "DELETE"])
@require_permission("lista_atendimentos", "editar")
def remover_atendimento_fila(fila_id: int):
    clinica_id = _clinica_id_atual()
    is_json = request.method == "DELETE" or request.headers.get("X-Requested-With") == "XMLHttpRequest"

    if request.is_json:
        payload = request.get_json(silent=True) or {}
        motivo = (payload.get("motivo") or "").strip()
    else:
        motivo = (request.form.get("motivo") or "").strip()

    if not motivo:
        motivo = "Removido da lista de atendimentos."

    try:
        with conectar_db() as conn:
            ensure_lista_atendimentos_schema(conn)

            item = _buscar_fila_item(conn, fila_id, clinica_id)

            if not item:
                msg = "Item da fila não encontrado nesta clínica."
                if is_json:
                    return jsonify({"ok": False, "error": msg}), 404
                flash(msg, "error")
                return redirect(url_for("atendimentos.lista_atendimentos"))

            cur = conn.cursor()
            cur.execute("""
                UPDATE fila_atendimentos
                   SET status = 'removido',
                       motivo_remocao = %s,
                       removido_em = CURRENT_TIMESTAMP,
                       removido_por = %s,
                       obs = CASE
                               WHEN COALESCE(obs, '') = '' THEN %s
                               ELSE obs || ' | ' || %s
                             END
                 WHERE id = %s
                   AND clinica_id = %s;
            """, (
                motivo,
                _usuario_id_atual(),
                motivo,
                motivo,
                fila_id,
                clinica_id,
            ))

            updated = cur.rowcount or 0
            conn.commit()

        registrar_log(
            modulo="lista_atendimentos",
            acao="remover",
            entidade="fila_atendimentos",
            entidade_id=fila_id,
            descricao="Removeu paciente da lista de atendimentos.",
            detalhes={
                "clinica_id": clinica_id,
                "fila_id": fila_id,
                "paciente_id": item.get("paciente_id"),
                "paciente_nome": item.get("paciente_nome"),
                "profissional_id": item.get("profissional_id"),
                "origem": item.get("origem"),
                "agenda_id": item.get("agenda_id"),
                "motivo": motivo,
                "updated": updated,
            },
        )

        if is_json:
            return jsonify({"ok": True, "removed": updated, "id": fila_id})

        flash("Paciente removido da lista.", "success")
        return redirect(url_for("atendimentos.lista_atendimentos"))

    except Exception as e:
        log_erro(
            "lista_atendimentos",
            e,
            entidade="fila_atendimentos",
            entidade_id=fila_id,
            descricao="Erro ao remover paciente da lista.",
            detalhes={"clinica_id": clinica_id, "motivo": motivo},
        )

        if is_json:
            return jsonify({"ok": False, "error": str(e)}), 500

        flash(f"Erro ao remover paciente da lista: {e}", "error")
        return redirect(url_for("atendimentos.lista_atendimentos"))


# =============================================================================
# MARCAR COMO CHAMADO / EM ATENDIMENTO
# =============================================================================

@atendimentos_bp.route("/fila/<int:fila_id>/status", methods=["POST"], endpoint="alterar_status_fila")
@require_permission("lista_atendimentos", "editar")
def alterar_status_fila(fila_id: int):
    clinica_id = _clinica_id_atual()
    is_json = request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest"

    payload = request.get_json(silent=True) if request.is_json else request.form
    novo_status = (payload.get("status") or "").strip().lower()

    permitidos = {"aguardando", "chamado", "em_atendimento", "removido", "finalizado"}

    if novo_status not in permitidos:
        return jsonify({"ok": False, "error": "Status inválido."}), 400

    try:
        with conectar_db() as conn:
            ensure_lista_atendimentos_schema(conn)

            item = _buscar_fila_item(conn, fila_id, clinica_id)

            if not item:
                return jsonify({"ok": False, "error": "Item não encontrado nesta clínica."}), 404

            cur = conn.cursor()
            cur.execute("""
                UPDATE fila_atendimentos
                   SET status = %s
                 WHERE id = %s
                   AND clinica_id = %s;
            """, (novo_status, fila_id, clinica_id))
            conn.commit()

        registrar_log(
            modulo="lista_atendimentos",
            acao="editar",
            entidade="fila_atendimentos",
            entidade_id=fila_id,
            descricao="Alterou status da fila de atendimento.",
            detalhes={
                "clinica_id": clinica_id,
                "fila_id": fila_id,
                "status_anterior": item.get("status"),
                "status_novo": novo_status,
            },
        )

        if is_json:
            return jsonify({"ok": True, "status": novo_status})

        return redirect(url_for("atendimentos.lista_atendimentos"))

    except Exception as e:
        log_erro(
            "lista_atendimentos",
            e,
            entidade="fila_atendimentos",
            entidade_id=fila_id,
            descricao="Erro ao alterar status da fila.",
            detalhes={"clinica_id": clinica_id, "status": novo_status},
        )
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================================
# IMPRESSÃO
# =============================================================================

@atendimentos_bp.route("/imprimir", methods=["GET"], endpoint="imprimir_lista_atendimentos")
@require_permission("lista_atendimentos", "ver")
def imprimir_lista_atendimentos():
    clinica_id = _clinica_id_atual()

    try:
        with conectar_db() as conn:
            ensure_lista_atendimentos_schema(conn)
            fila = _listar_fila(conn, clinica_id, apenas_hoje=True)

        registrar_log(
            modulo="lista_atendimentos",
            acao="visualizar",
            entidade="fila_atendimentos",
            descricao="Abriu impressão da lista de atendimentos.",
            detalhes={
                "clinica_id": clinica_id,
                "total": len(fila),
            },
        )

        return render_template(
            "imprimir_lista_atendimentos.html",
            fila=fila,
            itens=fila,
            atendimentos=fila,
            data_hoje=date.today().isoformat(),
            clinica_id=clinica_id,
            clinica_nome=session.get("clinica_nome"),
        )

    except Exception as e:
        log_erro(
            "lista_atendimentos",
            e,
            entidade="fila_atendimentos",
            descricao="Erro ao imprimir lista de atendimentos.",
            detalhes={"clinica_id": clinica_id},
        )
        return f"Erro ao imprimir lista: {e}", 500


@atendimentos_bp.post("/api/fila/add")
@require_permission("lista_atendimentos", "editar")
def api_fila_add_alias():
    return adicionar_atendimento()


@atendimentos_bp.route("/api/fila/<int:fila_id>", methods=["PATCH", "DELETE"])
@require_permission("lista_atendimentos", "editar")
def api_fila_item_alias(fila_id: int):
    if request.method == "DELETE":
        return remover_atendimento_fila(fila_id)

    clinica_id = _clinica_id_atual()
    payload = request.get_json(silent=True) or {}
    novo_status = (payload.get("status") or "").strip().lower()

    mapa_status = {
        "atendendo": "em_atendimento",
        "em atendimento": "em_atendimento",
        "em_atendimento": "em_atendimento",
        "finalizado": "finalizado",
        "atendido": "finalizado",
        "aguardando": "aguardando",
        "chamado": "chamado",
        "removido": "removido",
    }

    novo_status = mapa_status.get(novo_status, novo_status)

    if novo_status:
        with conectar_db() as conn:
            ensure_lista_atendimentos_schema(conn)

            cur = conn.cursor()
            cur.execute("""
                UPDATE fila_atendimentos
                   SET status = %s
                 WHERE id = %s
                   AND clinica_id = %s;
            """, (novo_status, fila_id, clinica_id))
            conn.commit()

        return jsonify({"ok": True, "id": fila_id, "status": novo_status})

    return jsonify({"ok": False, "error": "Nenhum status informado."}), 400


@atendimentos_bp.post("/api/fila/sync_hoje")
@require_permission("lista_atendimentos", "ver")
def api_fila_sync_hoje():
    clinica_id = _clinica_id_atual()

    try:
        with conectar_db() as conn:
            ensure_lista_atendimentos_schema(conn)
            sync_today_agenda_to_fila_seguro(conn, clinica_id)

        return jsonify({"ok": True})
    except Exception as e:
        log_erro(
            "lista_atendimentos",
            e,
            entidade="fila_atendimentos",
            descricao="Erro ao sincronizar agenda de hoje com a fila.",
            detalhes={"clinica_id": clinica_id},
        )
        return jsonify({"ok": False, "error": str(e)}), 500