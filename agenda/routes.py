from datetime import datetime, timedelta
import sqlite3, io, csv
from typing import Optional

from flask import render_template, request, jsonify, url_for, send_file
from . import agenda_bp
from db import conectar_db

# ============================================================
# UTILIDADES / CONSTANTES
# ============================================================

# Labels 0..6 no padrão do SQLite (%w): 0=Dom..6=Sáb
DOW_LABELS_PT = ["Domingo", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"]

# Usado no template da agenda
DOW_LABELS = [(str(i), nome) for i, nome in enumerate(DOW_LABELS_PT)]


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=? LIMIT 1;",
        (table,),
    )
    return cur.fetchone() is not None


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table});")
    return column in {row[1] for row in cur.fetchall()}


def _ensure_agendamentos_table(conn: sqlite3.Connection):
    """
    Garante a tabela agendamentos com o mínimo necessário
    para a agenda funcionar.

    Importante:
    - removemos a dependência funcional de 'recorrente'
    - removemos a dependência funcional de 'valor_sessao'
    - mantemos colunas antigas, se já existirem, para não quebrar banco legado
    """
    if _has_table(conn, "agendamentos"):
        return

    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS agendamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            paciente TEXT,
            profissional TEXT,
            profissional_cpf TEXT,

            inicio TEXT,
            fim TEXT,

            dia TEXT,
            observacao TEXT,

            status TEXT DEFAULT 'ativo',

            recorrente INTEGER DEFAULT 0,
            serie_uid TEXT,
            dow_dom INTEGER,

            valor_sessao REAL
        );
        """
    )
    conn.commit()


def _ensure_valor_col(conn: sqlite3.Connection):
    """
    Mantém compatibilidade com bancos antigos.
    A agenda não vai mais usar 'valor_sessao' como regra do fluxo,
    mas a coluna pode continuar existindo no banco sem problema.
    """
    if not _has_table(conn, "agendamentos"):
        return
    if not _has_column(conn, "agendamentos", "valor_sessao"):
        cur = conn.cursor()
        cur.execute("ALTER TABLE agendamentos ADD COLUMN valor_sessao REAL;")
        conn.commit()


def _ensure_dia_col(conn: sqlite3.Connection):
    """
    Garante a coluna 'dia' com o nome do dia da semana.
    Ex.: Segunda, Terça, Quarta...
    """
    if not _has_table(conn, "agendamentos"):
        return
    if not _has_column(conn, "agendamentos", "dia"):
        cur = conn.cursor()
        cur.execute("ALTER TABLE agendamentos ADD COLUMN dia TEXT;")
        conn.commit()


def ensure_schema_agenda(conn: sqlite3.Connection):
    """
    Ponto único para garantir schema da agenda.
    Seguro chamar várias vezes.
    """
    _ensure_agendamentos_table(conn)
    _ensure_valor_col(conn)
    _ensure_dia_col(conn)


def _parse_hhmm(s: str) -> Optional[tuple[int, int]]:
    """
    Converte HH:MM em tupla (hora, minuto).
    """
    try:
        hh, mm = s.strip().split(":")
        hh, mm = int(hh), int(mm)
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh, mm
    except Exception:
        pass
    return None


def _next_date_for_dow(ref: datetime, dow_dom: int) -> datetime:
    """
    Retorna a próxima data (>= hoje) que cai no DOW solicitado.
    SQLite %w: 0=Dom..6=Sáb.
    """
    today_w = (ref.weekday() + 1) % 7  # converte para 0=Dom..6=Sáb
    delta = (dow_dom - today_w) % 7
    return (ref + timedelta(days=delta)).replace(hour=0, minute=0, second=0, microsecond=0)


def _combine_date_time(day: datetime, hh: int, mm: int) -> datetime:
    return day.replace(hour=hh, minute=mm, second=0, microsecond=0)


def _usuario_by_cpf(conn: sqlite3.Connection, cpf: str):
    """
    Resolve usuário/profissional pelo CPF.
    Se tabela usuarios não existir, retorna None.
    """
    if not _has_table(conn, "usuarios"):
        return None

    cur = conn.cursor()
    cur.execute(
        """
        SELECT nome, cpf
          FROM usuarios
         WHERE TRIM(COALESCE(cpf,'')) = TRIM(?)
           AND COALESCE(is_active,1)=1
         LIMIT 1;
        """,
        (cpf,),
    )
    r = cur.fetchone()
    if not r:
        return None

    try:
        return {"nome": r["nome"], "cpf": r["cpf"]}
    except Exception:
        return {"nome": r[0], "cpf": r[1]}


def _to_dt(val):
    """
    Converte valores comuns do SQLite para datetime.
    """
    if val is None:
        return None
    if isinstance(val, datetime):
        return val

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(val), fmt)
        except Exception:
            continue

    try:
        return datetime.fromisoformat(str(val))
    except Exception:
        return None


# ============================================================
# /agenda (GET) - PÁGINA
# ============================================================

@agenda_bp.route("/", methods=["GET"], endpoint="visualizar_agenda")
def agenda_form():
    pacientes = []

    with conectar_db() as conn:
        ensure_schema_agenda(conn)

        cur = conn.cursor()
        try:
            cur.execute("SELECT id, nome FROM pacientes ORDER BY nome;")
            pacientes = [{"id": r[0], "nome": r[1]} for r in cur.fetchall()]
        except Exception:
            pacientes = []

    return render_template("agenda.html", pacientes=pacientes, dow_labels=DOW_LABELS)


# ============================================================
# /agenda (POST) - SALVAR AGENDAMENTO
# ============================================================

@agenda_bp.route("/", methods=["POST"], endpoint="agenda_salvar")
def agenda_salvar():
    """
    Salva APENAS UM agendamento por vez.

    Espera JSON:
      {
        "paciente_id": 123,                // ou "paciente_nome": "FULANO"
        "dia": "1",                        // 0=Dom..6=Sáb
        "hora_de": "08:00",
        "hora_ate": "08:30",               // opcional; se vazio, usa +30min
        "profissional_cpf": "000.000.000-00"
      }

    Mudança importante:
    - removemos 'qtd'
    - removemos a lógica de recorrência
    - removemos o papel comercial da agenda
    """
    data = request.get_json(silent=True) or {}

    pac_id = data.get("paciente_id")
    pac_nome = (data.get("paciente_nome") or "").strip()
    dia = (data.get("dia") or "").strip()
    hora_de = (data.get("hora_de") or "").strip()
    hora_ate = (data.get("hora_ate") or "").strip()
    prof_cpf = (data.get("profissional_cpf") or "").strip()
    observacao = (data.get("observacao") or "").strip()

    is_vago = pac_nome.upper() == "VAGO"

    # ------------------------------
    # VALIDAÇÕES
    # ------------------------------
    if not pac_id and not pac_nome and not is_vago:
        return jsonify({"error": "Informe o paciente."}), 400

    if not prof_cpf:
        return jsonify({"error": "Profissional é obrigatório."}), 400

    if not dia.isdigit() or not (0 <= int(dia) <= 6):
        return jsonify({"error": "Dia inválido. Use 0..6 (0=Dom..6=Sáb)."}), 400

    hhmm_de = _parse_hhmm(hora_de)
    if not hhmm_de:
        return jsonify({"error": "Horário inicial inválido. Use HH:MM."}), 400

    hhmm_ate = _parse_hhmm(hora_ate) if hora_ate else None

    with conectar_db() as conn:
        ensure_schema_agenda(conn)
        cur = conn.cursor()

        # ------------------------------
        # RESOLVE PACIENTE
        # ------------------------------
        pid = None
        nome = None

        if is_vago:
            pid = None
            nome = "VAGO"
        else:
            if pac_id:
                cur.execute("SELECT id, nome FROM pacientes WHERE id = ? LIMIT 1;", (pac_id,))
                r = cur.fetchone()
                if not r:
                    return jsonify({"error": "Paciente não encontrado (id)."}), 404
                pid, nome = int(r[0]), r[1]
            else:
                cur.execute(
                    """
                    SELECT id, nome
                      FROM pacientes
                     WHERE TRIM(UPPER(nome)) = TRIM(UPPER(?))
                     LIMIT 1;
                    """,
                    (pac_nome,),
                )
                r = cur.fetchone()
                if not r:
                    return jsonify({"error": "Paciente não encontrado (nome)."}), 404
                pid, nome = int(r[0]), r[1]

        # ------------------------------
        # RESOLVE PROFISSIONAL
        # ------------------------------
        u = _usuario_by_cpf(conn, prof_cpf)
        if not u:
            return jsonify({"error": "Profissional (CPF) não encontrado ou inativo."}), 400

        prof_nome = u["nome"]
        prof_cpf = u["cpf"]

        # ------------------------------
        # MONTA DATA/HORA DO AGENDAMENTO
        # ------------------------------
        dow = int(dia)
        today = datetime.now()
        base_day = _next_date_for_dow(today, dow)

        if hhmm_ate:
            dur_min = (hhmm_ate[0] - hhmm_de[0]) * 60 + (hhmm_ate[1] - hhmm_de[1])
            if dur_min <= 0:
                return jsonify({"error": "Horário final deve ser após o inicial."}), 400
        else:
            dur_min = 30

        ini_dt = _combine_date_time(base_day, hhmm_de[0], hhmm_de[1])
        fim_dt = ini_dt + timedelta(minutes=dur_min)
        dow_dom_val = ((ini_dt.weekday() + 1) % 7)

        try:
            dia_label = DOW_LABELS_PT[dow_dom_val]
        except Exception:
            dia_label = ""

        # ------------------------------
        # INSERE UM AGENDAMENTO
        # ------------------------------
        cur.execute(
            """
            INSERT INTO agendamentos
               (paciente,
                profissional,
                profissional_cpf,
                inicio,
                fim,
                dia,
                observacao,
                status,
                recorrente,
                serie_uid,
                dow_dom,
                valor_sessao)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'ativo', 0, NULL, ?, NULL);
            """,
            (
                nome,
                prof_nome,
                prof_cpf,
                ini_dt.strftime("%Y-%m-%d %H:%M:%S"),
                fim_dt.strftime("%Y-%m-%d %H:%M:%S"),
                dia_label,
                observacao or None,
                dow_dom_val,
            ),
        )
        created_id = cur.lastrowid
        conn.commit()

        redirect_url = None
        if pid is not None:
            try:
                redirect_url = url_for("pacientes.visualizar_paciente", id=pid)
            except Exception:
                redirect_url = None

    return jsonify(
        {
            "ok": True,
            "criado": created_id,
            "paciente": {"id": pid, "nome": nome},
            "redirect": redirect_url,
        }
    ), 201


# ============================================================
# API - PROFISSIONAIS
# ============================================================

@agenda_bp.get("/api/profissionais", endpoint="api_profissionais")
def api_profissionais():
    """
    Retorna profissionais ativos com CPF:
    [{nome, cpf}]
    """
    try:
        with conectar_db() as conn:
            ensure_schema_agenda(conn)

            cur = conn.cursor()
            cur.execute(
                """
                SELECT nome, cpf
                  FROM usuarios
                 WHERE TRIM(COALESCE(cpf,'')) <> ''
                   AND COALESCE(is_active,1)=1
                 ORDER BY nome;
                """
            )
            rows = cur.fetchall()

            out = []
            for r in rows:
                try:
                    out.append({"nome": r["nome"], "cpf": r["cpf"]})
                except Exception:
                    out.append({"nome": r[0], "cpf": r[1]})

        return jsonify(out)
    except Exception as e:
        return jsonify({"error": "Falha ao listar profissionais", "detail": str(e)}), 500


# ============================================================
# API - AGREGADOS DA AGENDA
# ============================================================

@agenda_bp.get("/api/agregados", endpoint="api_agregados")
def api_agregados():
    """
    Lista agregada da agenda, mas agora puxando a quantidade de sessões
    do módulo comercial/financeiro e NÃO da contagem de agendamentos.

    Regras:
    - qtd_agendamentos = quantidade de registros na agenda
    - qtd_sessoes = sessoes_contratadas do vínculo ativo no financeiro
    - sessoes_usadas = vindo do financeiro
    - sessoes_restantes = contratado - usadas
    """
    try:
        qp = request.args

        prof_param = (qp.get("profissional_cpf") or qp.get("profissional") or "").strip()
        dia_param = (qp.get("dia") or qp.get("dia_semana") or "").strip()
        hora_de = (qp.get("hora_de") or qp.get("hora_ini") or "").strip()
        hora_ate = (qp.get("hora_ate") or qp.get("hora_fim") or "").strip()
        paciente_q = (qp.get("paciente") or qp.get("paciente_nome") or "").strip()
        idade_min = (qp.get("idade_min") or qp.get("idadeDe") or "").strip()
        idade_max = (qp.get("idade_max") or qp.get("idadeAte") or "").strip()
        cid_q = (qp.get("cid") or qp.get("cid10") or "").strip()

        with conectar_db() as conn:
            ensure_schema_agenda(conn)
            cur = conn.cursor()

            # ------------------------------
            # MAPEIA COLUNAS DISPONÍVEIS
            # ------------------------------
            cur.execute("PRAGMA table_info(agendamentos);")
            cols_ag = {row[1] for row in cur.fetchall()}

            cur.execute("PRAGMA table_info(pacientes);")
            cols_pac = {row[1] for row in cur.fetchall()}

            has_financeiro = _has_table(conn, "financeiro_paciente_planos")
            has_dow = "dow_dom" in cols_ag
            has_prof_cpf = "profissional_cpf" in cols_ag
            has_pront = "prontuario" in cols_pac
            has_dia = "dia" in cols_ag

            nascimento_col = None
            if "nascimento" in cols_pac:
                nascimento_col = "p.nascimento"
            elif "data_nascimento" in cols_pac:
                nascimento_col = "p.data_nascimento"

            has_cid = "cid" in cols_pac

            dow_expr = "a.dow_dom" if has_dow else "CAST(strftime('%w', a.inicio) AS INTEGER)"

            # ------------------------------
            # FILTROS
            # ------------------------------
            where_clauses = [
                "TRIM(COALESCE(a.paciente,'')) <> ''",
                "TRIM(COALESCE(a.profissional,'')) <> ''",
            ]
            params: list = []

            if prof_param:
                if has_prof_cpf:
                    where_clauses.append("TRIM(COALESCE(a.profissional_cpf,'')) = TRIM(?)")
                    params.append(prof_param)
                else:
                    where_clauses.append("TRIM(UPPER(a.profissional)) = TRIM(UPPER(?))")
                    params.append(prof_param)

            if dia_param and dia_param.isdigit():
                dow_val = int(dia_param)
                where_clauses.append(f"{dow_expr} = ?")
                params.append(dow_val)

            if hora_de:
                where_clauses.append("strftime('%H:%M', a.inicio) >= ?")
                params.append(hora_de)

            if hora_ate:
                where_clauses.append("strftime('%H:%M', a.inicio) <= ?")
                params.append(hora_ate)

            if paciente_q:
                where_clauses.append("UPPER(a.paciente) LIKE '%' || UPPER(?) || '%'")
                params.append(paciente_q)

            if nascimento_col and (idade_min or idade_max):
                age_expr = f"CAST((julianday('now') - julianday({nascimento_col})) / 365.25 AS INTEGER)"
                if idade_min:
                    where_clauses.append(f"{age_expr} >= ?")
                    params.append(int(idade_min))
                if idade_max:
                    where_clauses.append(f"{age_expr} <= ?")
                    params.append(int(idade_max))

            if has_cid and cid_q:
                where_clauses.append("UPPER(COALESCE(p.cid,'')) LIKE '%' || UPPER(?) || '%'")
                params.append(cid_q)

            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

            # ------------------------------
            # CAMPOS EXTRAS
            # ------------------------------
            select_pront = ", MIN(p.prontuario) AS prontuario" if has_pront else ""
            select_dia = ", MIN(a.dia) AS dia_data" if has_dia else ""

            # Se existir financeiro, busca as sessões do vínculo ativo
            select_fin = ""
            join_fin = ""
            if has_financeiro:
                select_fin = """
                    , MAX(COALESCE(fp.sessoes_contratadas, 0)) AS qtd_sessoes
                    , MAX(COALESCE(fp.sessoes_usadas, 0)) AS sessoes_usadas
                    , MAX(COALESCE(fp.combo_nome, fp.nome_plano, '')) AS nome_combo
                    , MAX(COALESCE(fp.status, '')) AS status_comercial
                """
                join_fin = """
                    LEFT JOIN financeiro_paciente_planos fp
                           ON fp.paciente_id = p.id
                          AND COALESCE(fp.status, 'ativo') = 'ativo'
                """
            else:
                select_fin = """
                    , 0 AS qtd_sessoes
                    , 0 AS sessoes_usadas
                    , '' AS nome_combo
                    , '' AS status_comercial
                """
                join_fin = ""

            # ------------------------------
            # QUERY PRINCIPAL
            # ------------------------------
            sql = f"""
                SELECT
                    {dow_expr} AS dow,
                    strftime('%H:%M', a.inicio) AS hora_ini,
                    a.profissional,
                    a.paciente,
                    COUNT(*) AS qtd_agendamentos,
                    MIN(a.id) AS any_id,
                    MIN(p.id) AS paciente_id
                    {select_pront}
                    {select_dia}
                    {select_fin}
                FROM agendamentos a
                LEFT JOIN pacientes p
                       ON TRIM(UPPER(a.paciente)) = TRIM(UPPER(p.nome))
                {join_fin}
                WHERE {where_sql}
                GROUP BY {dow_expr}, strftime('%H:%M', a.inicio), a.profissional, a.paciente
                ORDER BY dow ASC, hora_ini ASC, a.profissional ASC, a.paciente ASC;
            """

            cur.execute(sql, params)
            rows = cur.fetchall()

            out = []
            for r in rows:
                try:
                    dow = r["dow"]
                    hora_ini = r["hora_ini"]
                    prof = r["profissional"]
                    pac = r["paciente"]
                    qtd_agendamentos = r["qtd_agendamentos"]
                    any_id = r["any_id"]
                    paciente_id = r["paciente_id"]
                    pront = r["prontuario"] if has_pront else None
                    dia_data = r["dia_data"] if has_dia else None
                    qtd_sessoes = r["qtd_sessoes"]
                    sessoes_usadas = r["sessoes_usadas"]
                    nome_combo = r["nome_combo"]
                    status_comercial = r["status_comercial"]
                except Exception:
                    continue

                try:
                    dia_label = DOW_LABELS_PT[int(dow)]
                except Exception:
                    dia_label = "—"

                qtd_sessoes = int(qtd_sessoes or 0)
                sessoes_usadas = int(sessoes_usadas or 0)
                sessoes_restantes = max(qtd_sessoes - sessoes_usadas, 0)

                out.append(
                    {
                        "dia": dia_label,
                        "dia_num": int(dow) if dow is not None else None,
                        "dia_label": dia_label,
                        "hora_ini": hora_ini or "—",
                        "profissional": prof or "—",
                        "paciente": pac or "—",
                        "paciente_id": int(paciente_id) if paciente_id is not None else None,
                        "prontuario": pront,
                        "qtd_agendamentos": int(qtd_agendamentos or 0),

                        # AQUI está a mudança principal:
                        "qtd": qtd_sessoes,  # mantém compatibilidade com o front antigo
                        "qtd_sessoes": qtd_sessoes,
                        "sessoes_usadas": sessoes_usadas,
                        "sessoes_restantes": sessoes_restantes,

                        "combo_nome": nome_combo or "",
                        "status_comercial": status_comercial or "",
                        "any_id": int(any_id or 0),
                        "dia_data": dia_data,
                    }
                )

        return jsonify(out)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Falha ao listar agregados", "detail": str(e)}), 500

# ============================================================
# EXPORT DOS AGREGADOS
# ============================================================

@agenda_bp.get("/api/agregados/export", endpoint="api_agregados_export")
def api_agregados_export():
    """
    Exporta a lista agregada em XLSX.
    Se openpyxl não estiver disponível, cai para CSV.
    """
    resp = api_agregados()

    if isinstance(resp, tuple):
        data, status = resp
        if status != 200:
            return resp
        items = data.get_json(force=True)
    else:
        items = resp.get_json(force=True)

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font

        wb = Workbook()
        ws = wb.active
        ws.title = "Agendamentos"

        headers = ["Dia", "Horário", "Profissional", "Paciente", "Qtd. registros"]
        ws.append(headers)

        for cell in ws[1]:
          cell.font = Font(bold=True)
          cell.alignment = Alignment(horizontal="center")

        for it in items:
            ws.append(
                [
                    it.get("dia_label", "—"),
                    it.get("hora_ini", "—"),
                    it.get("profissional", "—"),
                    it.get("paciente", "—"),
                    it.get("qtd", 0),
                ]
            )

        for col in ws.columns:
            max_len = 0
            col_letter = col[0].column_letter
            for cell in col:
                val = cell.value
                if val is None:
                    continue
                max_len = max(max_len, len(str(val)))
            ws.column_dimensions[col_letter].width = min(max_len + 2, 50)

        bio = io.BytesIO()
        wb.save(bio)
        bio.seek(0)

        fname = f"agendamentos_agregados_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        return send_file(
            bio,
            as_attachment=True,
            download_name=fname,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    except ImportError:
        sio = io.StringIO()
        writer = csv.writer(sio, delimiter=";")
        writer.writerow(["Dia", "Horário", "Profissional", "Paciente", "Qtd. registros"])

        for it in items:
            writer.writerow(
                [
                    it.get("dia_label", "—"),
                    it.get("hora_ini", "—"),
                    it.get("profissional", "—"),
                    it.get("paciente", "—"),
                    it.get("qtd", 0),
                ]
            )

        bio = io.BytesIO(sio.getvalue().encode("utf-8-sig"))
        fname = f"agendamentos_agregados_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        return send_file(bio, as_attachment=True, download_name=fname, mimetype="text/csv")


# ============================================================
# API - OBTER UM AGENDAMENTO
# ============================================================

@agenda_bp.get("/api/agendamentos/<int:ag_id>", endpoint="api_get_agendamento")
def api_get_agendamento(ag_id: int):
    """
    Retorna os dados de um agendamento para edição.
    """
    try:
        with conectar_db() as conn:
            ensure_schema_agenda(conn)
            cur = conn.cursor()

            cur.execute("PRAGMA table_info(agendamentos);")
            cols_ag = {row[1] for row in cur.fetchall()}
            has_prof_cpf = "profissional_cpf" in cols_ag
            has_valor = "valor_sessao" in cols_ag
            has_dow = "dow_dom" in cols_ag

            cur.execute(
                """
                SELECT id,
                       paciente,
                       profissional,
                       {prof_cpf_sel}
                       inicio,
                       fim,
                       {dow_sel}
                       {valor_sel}
                  FROM agendamentos
                 WHERE id = ?
                 LIMIT 1;
                """.format(
                    prof_cpf_sel="profissional_cpf," if has_prof_cpf else "'' AS profissional_cpf,",
                    dow_sel="dow_dom," if has_dow else "NULL AS dow_dom,",
                    valor_sel="valor_sessao" if has_valor else "NULL AS valor_sessao",
                ),
                (ag_id,),
            )
            row = cur.fetchone()

            if not row:
                return jsonify({"error": "Agendamento não encontrado."}), 404

            (
                _id,
                paciente,
                profissional,
                profissional_cpf,
                inicio_raw,
                fim_raw,
                dow_dom,
                valor_sessao,
            ) = row

            dt_ini = _to_dt(inicio_raw)
            dt_fim = _to_dt(fim_raw)

            hora_de = dt_ini.strftime("%H:%M") if dt_ini else None
            hora_ate = dt_fim.strftime("%H:%M") if dt_fim else None

            if dow_dom is not None:
                dia = int(dow_dom)
            elif dt_ini:
                dia = (dt_ini.weekday() + 1) % 7
            else:
                dia = None

            return jsonify(
                {
                    "id": int(_id),
                    "paciente": paciente,
                    "profissional": profissional,
                    "profissional_cpf": profissional_cpf,
                    "dia": dia,
                    "hora_de": hora_de,
                    "hora_ate": hora_ate,
                    "valor_sessao": float(valor_sessao) if valor_sessao is not None else None,
                }
            )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Falha ao carregar agendamento", "detail": str(e)}), 500


# ============================================================
# API - EDITAR AGENDAMENTO
# ============================================================

@agenda_bp.put("/api/agendamentos/<int:ag_id>", endpoint="api_editar_agendamento")
def api_editar_agendamento(ag_id: int):
    """
    Edita apenas UM agendamento.
    """
    data = request.get_json(silent=True) or {}

    dia_raw = (data.get("dia") or "").strip()
    hora_de = (data.get("hora_de") or "").strip()
    hora_ate = (data.get("hora_ate") or "").strip()
    novo_prof_cpf = (data.get("profissional_cpf") or "").strip()
    valor_sessao = data.get("valor_sessao", None)

    try:
        with conectar_db() as conn:
            ensure_schema_agenda(conn)
            cur = conn.cursor()

            cur.execute("PRAGMA table_info(agendamentos);")
            cols_ag = {row[1] for row in cur.fetchall()}
            has_dow = "dow_dom" in cols_ag
            has_prof_cpf = "profissional_cpf" in cols_ag
            has_valor = "valor_sessao" in cols_ag
            has_dia = "dia" in cols_ag

            cur.execute(
                """
                SELECT id,
                       paciente,
                       profissional,
                       {prof_cpf_sel}
                       inicio,
                       fim,
                       {dow_sel}
                       {valor_sel}
                  FROM agendamentos
                 WHERE id = ?
                 LIMIT 1;
                """.format(
                    prof_cpf_sel="profissional_cpf," if has_prof_cpf else "'' AS profissional_cpf,",
                    dow_sel="dow_dom," if has_dow else "NULL AS dow_dom,",
                    valor_sel="valor_sessao" if has_valor else "NULL AS valor_sessao",
                ),
                (ag_id,),
            )
            row = cur.fetchone()

            if not row:
                return jsonify({"error": "Agendamento não encontrado."}), 404

            (
                _id,
                paciente,
                profissional,
                profissional_cpf_atual,
                inicio_raw,
                fim_raw,
                dow_dom,
                valor_atual,
            ) = row

            dt_ini = _to_dt(inicio_raw)
            dt_fim = _to_dt(fim_raw)

            if not dt_ini:
                return jsonify({"error": "Não foi possível interpretar o horário inicial atual."}), 500

            dur_min_original = int((dt_fim - dt_ini).total_seconds() // 60) if dt_fim else 30

            novo_dia_semana = None
            if dia_raw:
                if not dia_raw.isdigit() or not (0 <= int(dia_raw) <= 6):
                    return jsonify({"error": "Valor de 'dia' inválido (use 0..6)."}), 400
                novo_dia_semana = int(dia_raw)

            if hora_de:
                hhmm_de = _parse_hhmm(hora_de)
                if not hhmm_de:
                    return jsonify({"error": "Horário inicial inválido. Use HH:MM."}), 400
                dt_ini_new = dt_ini.replace(hour=hhmm_de[0], minute=hhmm_de[1], second=0, microsecond=0)
            else:
                dt_ini_new = dt_ini

            if hora_ate:
                hhmm_ate = _parse_hhmm(hora_ate)
                if not hhmm_ate:
                    return jsonify({"error": "Horário final inválido. Use HH:MM."}), 400
                dt_fim_new = dt_ini_new.replace(hour=hhmm_ate[0], minute=hhmm_ate[1], second=0, microsecond=0)
                if dt_fim_new <= dt_ini_new:
                    return jsonify({"error": "Horário final deve ser após o inicial."}), 400
            else:
                dt_fim_new = dt_ini_new + timedelta(minutes=dur_min_original)

            if novo_dia_semana is not None:
                dow_atual_dom = (dt_ini_new.weekday() + 1) % 7
                delta_d = (novo_dia_semana - dow_atual_dom) % 7
                dt_ini_new = dt_ini_new + timedelta(days=delta_d)
                dt_fim_new = dt_fim_new + timedelta(days=delta_d)

            dow_dom_novo = (dt_ini_new.weekday() + 1) % 7

            novo_prof_nome = profissional
            novo_prof_cpf_resolvido = profissional_cpf_atual

            if novo_prof_cpf:
                u = _usuario_by_cpf(conn, novo_prof_cpf)
                if not u:
                    return jsonify({"error": "Profissional (CPF) não encontrado ou inativo."}), 400
                novo_prof_nome = u["nome"]
                novo_prof_cpf_resolvido = u["cpf"]

            val_float = None
            if has_valor and valor_sessao is not None:
                try:
                    val_float = float(valor_sessao)
                except Exception:
                    return jsonify({"error": "Valor da sessão inválido."}), 400

            set_parts = []
            params_up = []

            set_parts.append("inicio = ?")
            params_up.append(dt_ini_new.strftime("%Y-%m-%d %H:%M:%S"))

            set_parts.append("fim = ?")
            params_up.append(dt_fim_new.strftime("%Y-%m-%d %H:%M:%S"))

            if has_dia:
                try:
                    dia_label = DOW_LABELS_PT[dow_dom_novo]
                except Exception:
                    dia_label = ""
                set_parts.append("dia = ?")
                params_up.append(dia_label)

            if has_dow:
                set_parts.append("dow_dom = ?")
                params_up.append(dow_dom_novo)

            if has_valor and val_float is not None:
                set_parts.append("valor_sessao = ?")
                params_up.append(val_float)

            if has_prof_cpf and novo_prof_cpf_resolvido:
                set_parts.append("profissional_cpf = ?")
                params_up.append(novo_prof_cpf_resolvido)

            if novo_prof_nome and novo_prof_nome != profissional:
                set_parts.append("profissional = ?")
                params_up.append(novo_prof_nome)

            sql_up = f"UPDATE agendamentos SET {', '.join(set_parts)} WHERE id = ?;"
            params_up.append(ag_id)

            cur.execute(sql_up, params_up)
            conn.commit()

        return jsonify({"ok": True, "updated_id": ag_id})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Falha ao editar agendamento", "detail": str(e)}), 500


# ============================================================
# API - EXCLUIR AGENDAMENTO INDIVIDUAL
# ============================================================

@agenda_bp.delete("/api/agendamentos/<int:ag_id>", endpoint="api_excluir_agendamento")
def api_excluir_agendamento(ag_id: int):
    try:
        with conectar_db() as conn:
            ensure_schema_agenda(conn)
            cur = conn.cursor()

            cur.execute("DELETE FROM agendamentos WHERE id = ?;", (ag_id,))
            deleted = cur.rowcount or 0
            conn.commit()

        return jsonify({"ok": True, "deleted_id": ag_id, "deleted": deleted})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Falha ao excluir agendamento", "detail": str(e)}), 500


# ============================================================
# API - EXCLUIR GRUPO AGREGADO
# ============================================================

@agenda_bp.delete("/api/agregados", endpoint="api_excluir_grupo")
def api_excluir_grupo():
    """
    Exclui todos os agendamentos que compõem um grupo agregado.

    Query params:
      - dow (0..6)  [obrigatório]
      - hora_ini (HH:MM) [obrigatório]
      - profissional (nome exato) [obrigatório]
      - paciente (nome exato) [obrigatório]
    """
    try:
        dow = request.args.get("dow", "").strip()
        hora_ini = request.args.get("hora_ini", "").strip()
        prof = (request.args.get("profissional") or "").strip()
        pac = (request.args.get("paciente") or "").strip()

        if not (dow.isdigit() and 0 <= int(dow) <= 6):
            return jsonify({"error": "Parâmetro 'dow' inválido (0..6)."}), 400

        if len(hora_ini) != 5 or ":" not in hora_ini:
            return jsonify({"error": "Parâmetro 'hora_ini' deve ser HH:MM."}), 400

        if not prof or not pac:
            return jsonify({"error": "Parâmetros 'profissional' e 'paciente' são obrigatórios."}), 400

        with conectar_db() as conn:
            ensure_schema_agenda(conn)
            cur = conn.cursor()

            cur.execute("PRAGMA table_info(agendamentos);")
            cols = {row[1] for row in cur.fetchall()}
            has_dow = "dow_dom" in cols

            if has_dow:
                cur.execute(
                    """
                    DELETE FROM agendamentos
                     WHERE dow_dom = ?
                       AND TRIM(UPPER(profissional)) = TRIM(UPPER(?))
                       AND TRIM(UPPER(paciente)) = TRIM(UPPER(?))
                       AND strftime('%H:%M', inicio) = ?
                    """,
                    (int(dow), prof, pac, hora_ini),
                )
            else:
                cur.execute(
                    """
                    DELETE FROM agendamentos
                     WHERE CAST(strftime('%w', inicio) AS INTEGER) = ?
                       AND TRIM(UPPER(profissional)) = TRIM(UPPER(?))
                       AND TRIM(UPPER(paciente)) = TRIM(UPPER(?))
                       AND strftime('%H:%M', inicio) = ?
                    """,
                    (int(dow), prof, pac, hora_ini),
                )

            deleted = cur.rowcount or 0
            conn.commit()

        return jsonify({"ok": True, "deleted": deleted})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Falha ao excluir grupo", "detail": str(e)}), 500