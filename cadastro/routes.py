from __future__ import annotations

import json
import re
from datetime import date
from urllib.parse import quote_plus

from flask import request, render_template, jsonify, redirect, url_for, session, abort

from . import cadastro_bp
from db import conectar_db

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
# Helpers de contexto
# =============================================================================

def _clinica_id_atual() -> int:
    clinica_id = session.get("clinica_id")
    if not clinica_id:
        abort(403)
    return int(clinica_id)


def _usuario_id_atual():
    return session.get("usuario_id") or session.get("user_id")


# =============================================================================
# Helpers de normalização
# =============================================================================

_UPPER_FIELDS = {
    "nome", "status", "raca", "religiao",
    "logradouro", "codigo_logradouro", "complemento", "bairro", "municipio",
    "orgao_rg", "orgao_rg_responsavel", "estado_civil",
    "mae", "pai", "responsavel",
}

_ALLOWED_MODS = {"FIS", "INT", "AUD", "EQUO", "MED", "VISU", "EXAM", "SEM MOD"}

_MOD_MAP = {
    "FIS": "FIS", "FISIOTERAPIA": "FIS", "FISIOTERAPIA (FIS)": "FIS",
    "INT": "INT", "INTELECTUAL": "INT", "DEFICIENCIA INTELECTUAL": "INT", "DEFICIÊNCIA INTELECTUAL": "INT",
    "AUD": "AUD", "AUDITIVA": "AUD", "DEFICIENCIA AUDITIVA": "AUD", "DEFICIÊNCIA AUDITIVA": "AUD",
    "EQUO": "EQUO", "EQUOTERAPIA": "EQUO",
    "MED": "MED", "MEDICO": "MED", "MÉDICO": "MED",
    "VISU": "VISU", "VISUAL": "VISU", "DEFICIENCIA VISUAL": "VISU", "DEFICIÊNCIA VISUAL": "VISU",
    "EXAM": "EXAM", "EXAME": "EXAM", "EXAMES": "EXAM",
    "SEM MOD": "SEM MOD", "SEM MODALIDADE": "SEM MOD", "SEM": "SEM MOD",
    "": "SEM MOD", None: "SEM MOD",
}


def only_digits(v: str | None) -> str:
    return re.sub(r"\D+", "", v or "")


def _to_upper(x):
    if x is None:
        return ""
    return str(x).strip().upper()


def _normalize_prontuario(v: str | None) -> str:
    s = (v or "").strip()
    if not s:
        return ""
    up = s.upper().strip()
    if up.startswith("SGD-"):
        return s[4:].strip()
    if up.startswith("SGD"):
        return s[3:].strip()
    return s


def _normalize_mod(v: str | None) -> str:
    raw = (v or "").strip()
    key = raw.upper()
    norm = _MOD_MAP.get(key)
    if norm:
        return norm
    if key in _ALLOWED_MODS:
        return key
    return "SEM MOD"


def _normalize_admissao(v: str | None) -> str:
    s = (v or "").strip()
    return s if s else date.today().isoformat()


def _parse_laudos_list(raw) -> list[dict]:
    if raw is None:
        return []

    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except Exception:
            return []
    else:
        parsed = raw

    if not isinstance(parsed, list):
        return []

    normalizados = []
    vistos = set()

    for item in parsed:
        if isinstance(item, dict):
            codigo = str(item.get("codigo") or item.get("cid") or "").strip().upper()
            descricao = str(item.get("descricao") or item.get("nome") or "").strip().upper()
        elif isinstance(item, str):
            codigo = item.strip().upper()
            descricao = ""
        else:
            continue

        if not codigo and not descricao:
            continue

        chave = (codigo, descricao)
        if chave in vistos:
            continue
        vistos.add(chave)

        normalizados.append({"codigo": codigo, "descricao": descricao})

    return normalizados


def _parse_laudos_payload(raw) -> str:
    return json.dumps(_parse_laudos_list(raw), ensure_ascii=False)


def _coletar_laudos_form(form) -> str:
    bruto_json = (form.get("laudos_json") or form.get("laudos_cids_json") or "").strip()
    if bruto_json:
        return _parse_laudos_payload(bruto_json)

    codigos = form.getlist("laudos_cid[]") or form.getlist("laudos_cid")
    descricoes = form.getlist("laudos_desc[]") or form.getlist("laudos_desc")

    itens = []
    total = max(len(codigos), len(descricoes))

    for i in range(total):
        codigo = str(codigos[i] if i < len(codigos) else "").strip().upper()
        descricao = str(descricoes[i] if i < len(descricoes) else "").strip().upper()
        if not codigo and not descricao:
            continue
        itens.append({"codigo": codigo, "descricao": descricao})

    return _parse_laudos_payload(itens)


def _upperize_payload(dados: dict) -> dict:
    out = {}

    for k, v in (dados or {}).items():
        if k in _UPPER_FIELDS:
            out[k] = _to_upper(v)
        elif k == "email":
            out[k] = (v or "").strip().lower()
        elif k == "sexo":
            out[k] = (v or "").strip().upper()[:1]
        else:
            out[k] = (v or "").strip() if isinstance(v, str) else v

    out["prontuario"] = _normalize_prontuario(out.get("prontuario"))
    out["mod"] = _normalize_mod(out.get("mod"))
    out["admissao"] = _normalize_admissao(out.get("admissao"))
    out["cep"] = only_digits(out.get("cep"))[:8]
    out["codigo_ibge"] = only_digits(out.get("codigo_ibge"))
    out["cpf"] = only_digits(out.get("cpf"))[:11]
    out["cns"] = only_digits(out.get("cns"))
    out["laudos_json"] = _parse_laudos_payload(out.get("laudos_json"))

    return out


def _build_redirect_url(dados: dict, last_id: int) -> str:
    base = url_for("pacientes.listar_pacientes")
    nome = (dados.get("nome") or "").strip()
    pront = (dados.get("prontuario") or "").strip()
    cpf = (dados.get("cpf") or "").strip()

    if nome:
        return f"{base}?nome={quote_plus(nome)}"
    if pront:
        return f"{base}?prontuario={quote_plus(pront)}"
    if cpf:
        return f"{base}?cpf={quote_plus(cpf)}"

    try:
        return url_for("pacientes.visualizar_paciente", id=last_id)
    except Exception:
        return base


# =============================================================================
# Helpers PostgreSQL
# =============================================================================

def _conn():
    conn = conectar_db()
    try:
        from psycopg.rows import dict_row
        conn.row_factory = dict_row
    except Exception:
        pass
    return conn


def _fetchone_dict(cur):
    row = cur.fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    try:
        return dict(row)
    except Exception:
        cols = [c[0] for c in cur.description] if cur.description else []
        return dict(zip(cols, row))


def _fetchall_dicts(cur):
    rows = cur.fetchall() or []
    out = []
    cols = [c[0] for c in cur.description] if cur.description else []

    for row in rows:
        if isinstance(row, dict):
            out.append(dict(row))
        else:
            try:
                out.append(dict(row))
            except Exception:
                out.append(dict(zip(cols, row)))

    return out


def _has_table(conn, table: str) -> bool:
    cur = conn.cursor()
    cur.execute("""
        SELECT 1
          FROM information_schema.tables
         WHERE table_schema = 'public'
           AND table_name = %s
         LIMIT 1;
    """, (table,))
    return cur.fetchone() is not None


def _table_columns(conn, table: str) -> set[str]:
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = %s
         ORDER BY ordinal_position;
    """, (table,))
    return {r["column_name"] for r in _fetchall_dicts(cur)}


def _add_col(conn, table: str, col: str, ddl: str) -> None:
    cur = conn.cursor()
    cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {ddl};")
    conn.commit()


# =============================================================================
# Migration / Schema
# =============================================================================

def ensure_paciente_laudos_schema(conn) -> None:
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS paciente_laudos (
            id SERIAL PRIMARY KEY,
            clinica_id INTEGER,
            paciente_id INTEGER NOT NULL,
            cid_codigo TEXT NOT NULL,
            cid_descricao TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cur.execute("ALTER TABLE paciente_laudos ADD COLUMN IF NOT EXISTS clinica_id INTEGER;")

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_paciente_laudos_clinica
        ON paciente_laudos(clinica_id);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_paciente_laudos_paciente_id
        ON paciente_laudos(paciente_id);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_paciente_laudos_clinica_paciente
        ON paciente_laudos(clinica_id, paciente_id);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_paciente_laudos_cid_codigo
        ON paciente_laudos(cid_codigo);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_paciente_laudos_cid_desc
        ON paciente_laudos(cid_descricao);
    """)

    conn.commit()


def ensure_pacientes_schema(conn) -> None:
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pacientes (
            id SERIAL PRIMARY KEY
        );
    """)
    conn.commit()

    _add_col(conn, "pacientes", "clinica_id", "INTEGER")

    _add_col(conn, "pacientes", "prontuario", "TEXT")
    _add_col(conn, "pacientes", "nome", "TEXT")
    _add_col(conn, "pacientes", "cns", "TEXT")
    _add_col(conn, "pacientes", "status", "TEXT")
    _add_col(conn, "pacientes", "nascimento", "TEXT")
    _add_col(conn, "pacientes", "idade", "TEXT")
    _add_col(conn, "pacientes", "sexo", "TEXT")
    _add_col(conn, "pacientes", "mod", "TEXT")
    _add_col(conn, "pacientes", "admissao", "TEXT")
    _add_col(conn, "pacientes", "cpf", "TEXT")

    _add_col(conn, "pacientes", "nis", "TEXT")
    _add_col(conn, "pacientes", "raca", "TEXT")
    _add_col(conn, "pacientes", "religiao", "TEXT")

    _add_col(conn, "pacientes", "logradouro", "TEXT")
    _add_col(conn, "pacientes", "codigo_logradouro", "TEXT")
    _add_col(conn, "pacientes", "numero_casa", "TEXT")
    _add_col(conn, "pacientes", "complemento", "TEXT")
    _add_col(conn, "pacientes", "bairro", "TEXT")
    _add_col(conn, "pacientes", "municipio", "TEXT")
    _add_col(conn, "pacientes", "cep", "TEXT")
    _add_col(conn, "pacientes", "codigo_ibge", "TEXT")

    _add_col(conn, "pacientes", "rg", "TEXT")
    _add_col(conn, "pacientes", "orgao_rg", "TEXT")
    _add_col(conn, "pacientes", "estado_civil", "TEXT")

    _add_col(conn, "pacientes", "mae", "TEXT")
    _add_col(conn, "pacientes", "cpf_mae", "TEXT")
    _add_col(conn, "pacientes", "rg_mae", "TEXT")
    _add_col(conn, "pacientes", "rg_ssp_mae", "TEXT")
    _add_col(conn, "pacientes", "nis_mae", "TEXT")

    _add_col(conn, "pacientes", "pai", "TEXT")
    _add_col(conn, "pacientes", "cpf_pai", "TEXT")
    _add_col(conn, "pacientes", "rg_pai", "TEXT")
    _add_col(conn, "pacientes", "rg_ssp_pai", "TEXT")

    _add_col(conn, "pacientes", "telefone1", "TEXT")
    _add_col(conn, "pacientes", "telefone2", "TEXT")
    _add_col(conn, "pacientes", "telefone3", "TEXT")
    _add_col(conn, "pacientes", "email", "TEXT")

    _add_col(conn, "pacientes", "responsavel", "TEXT")
    _add_col(conn, "pacientes", "cpf_responsavel", "TEXT")
    _add_col(conn, "pacientes", "rg_responsavel", "TEXT")
    _add_col(conn, "pacientes", "orgao_rg_responsavel", "TEXT")

    _add_col(conn, "pacientes", "laudos_json", "TEXT")
    _add_col(conn, "pacientes", "cid", "TEXT")
    _add_col(conn, "pacientes", "cid2", "TEXT")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_pacientes_clinica_id ON pacientes(clinica_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pacientes_clinica_nome ON pacientes(clinica_id, nome);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pacientes_clinica_cpf ON pacientes(clinica_id, cpf);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pacientes_clinica_prontuario ON pacientes(clinica_id, prontuario);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pacientes_nome ON pacientes(nome);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pacientes_cpf ON pacientes(cpf);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pacientes_prontuario ON pacientes(prontuario);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pacientes_cep ON pacientes(cep);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pacientes_codigo_ibge ON pacientes(codigo_ibge);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pacientes_cid ON pacientes(cid);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pacientes_cid2 ON pacientes(cid2);")
    conn.commit()

    ensure_paciente_laudos_schema(conn)


def _insert_paciente_safe(conn, dados: dict) -> int:
    cols_exist = _table_columns(conn, "pacientes")

    desired_cols = [
        "clinica_id",
        "prontuario", "nome", "cns", "status", "nascimento", "idade", "sexo", "mod",
        "nis", "raca", "religiao", "admissao",
        "logradouro", "codigo_logradouro", "numero_casa", "complemento",
        "bairro", "municipio", "cep", "codigo_ibge",
        "cpf", "rg", "orgao_rg", "estado_civil",
        "mae", "cpf_mae", "rg_mae", "rg_ssp_mae", "nis_mae",
        "pai", "cpf_pai", "rg_pai", "rg_ssp_pai",
        "telefone1", "telefone2", "telefone3", "email",
        "responsavel", "cpf_responsavel", "rg_responsavel", "orgao_rg_responsavel",
        "laudos_json", "cid", "cid2",
    ]

    cols = [c for c in desired_cols if c in cols_exist]

    if not cols:
        raise RuntimeError("Tabela 'pacientes' sem colunas compatíveis para INSERT.")

    placeholders = ", ".join(["%s"] * len(cols))
    col_sql = ", ".join(cols)

    sql = f"INSERT INTO pacientes ({col_sql}) VALUES ({placeholders}) RETURNING id"
    vals = [dados.get(c) for c in cols]

    cur = conn.cursor()
    cur.execute(sql, vals)
    row = cur.fetchone()

    return int(row[0] if not isinstance(row, dict) else row["id"])


def _sync_paciente_laudos(conn, paciente_id: int, laudos_json: str, clinica_id: int) -> None:
    laudos = _parse_laudos_list(laudos_json)

    cur = conn.cursor()
    cur.execute(
        "DELETE FROM paciente_laudos WHERE paciente_id = %s AND clinica_id = %s;",
        (paciente_id, clinica_id),
    )

    if laudos:
        cur.executemany("""
            INSERT INTO paciente_laudos (
                clinica_id,
                paciente_id,
                cid_codigo,
                cid_descricao
            )
            VALUES (%s, %s, %s, %s);
        """, [
            (
                clinica_id,
                paciente_id,
                item.get("codigo", ""),
                item.get("descricao", ""),
            )
            for item in laudos
            if (item.get("codigo") or "").strip() or (item.get("descricao") or "").strip()
        ])


# =============================================================================
# APIs auxiliares
# =============================================================================

@cadastro_bp.route("/api/cep/buscar")
@require_permission("cadastro", "ver")
def buscar_cep():
    cep = only_digits(request.args.get("cep"))[:8]

    if len(cep) != 8:
        return jsonify({"ok": False, "mensagem": "CEP inválido."}), 400

    try:
        with _conn() as conn:
            ensure_pacientes_schema(conn)

            cur = conn.cursor()
            cur.execute("""
                SELECT cep, ibge, municipio, coduf, codmunicip
                  FROM cep_ibge
                 WHERE REGEXP_REPLACE(COALESCE(cep, ''), '[^0-9]', '', 'g') = %s
                 LIMIT 1;
            """, (cep,))
            row = _fetchone_dict(cur)

        if not row:
            return jsonify({"ok": False, "mensagem": "CEP não encontrado."}), 404

        registrar_log(
            modulo="cadastro",
            acao="buscar_cep",
            entidade="cep_ibge",
            descricao="Buscou CEP no cadastro.",
            detalhes={"cep": cep, "encontrado": True},
        )

        return jsonify({
            "ok": True,
            "item": {
                "cep": row["cep"] or "",
                "ibge": row["ibge"] or "",
                "municipio": row["municipio"] or "",
                "coduf": row["coduf"] or "",
                "codmunicip": row["codmunicip"] or "",
            }
        })

    except Exception as e:
        log_erro("cadastro", e, entidade="cep_ibge", descricao="Erro ao buscar CEP.", detalhes={"cep": cep})
        return jsonify({"ok": False, "mensagem": str(e)}), 500


@cadastro_bp.route("/api/cids/buscar")
@require_permission("cadastro", "ver")
def buscar_cids():
    q = (request.args.get("q") or "").strip()

    if len(q) < 2:
        return jsonify({"ok": True, "items": []})

    q_up = q.upper()

    try:
        with _conn() as conn:
            ensure_pacientes_schema(conn)

            cur = conn.cursor()
            cur.execute("""
                SELECT co_cid, no_cid
                  FROM cid_catalogo
                 WHERE co_cid ILIKE %s
                    OR UPPER(COALESCE(no_cid, '')) ILIKE %s
                 ORDER BY
                    CASE WHEN co_cid = %s THEN 0 ELSE 1 END,
                    co_cid ASC
                 LIMIT 20;
            """, (f"%{q_up}%", f"%{q_up}%", q_up))
            rows = _fetchall_dicts(cur)

        items = [
            {
                "codigo": r["co_cid"] or "",
                "descricao": r["no_cid"] or "",
                "label": f"{r['co_cid']} - {r['no_cid']}",
            }
            for r in rows
        ]

        registrar_log(
            modulo="cadastro",
            acao="buscar_cid",
            entidade="cid_catalogo",
            descricao="Buscou CID no cadastro.",
            detalhes={"q": q, "total": len(items)},
        )

        return jsonify({"ok": True, "items": items})

    except Exception as e:
        log_erro("cadastro", e, entidade="cid_catalogo", descricao="Erro ao buscar CID.", detalhes={"q": q})
        return jsonify({"ok": False, "mensagem": str(e)}), 500


# =============================================================================
# Rotas principais
# =============================================================================

@cadastro_bp.route("/cadastro", methods=["GET"])
@require_permission("cadastro", "ver")
def cadastrar_paciente():
    hoje = date.today().isoformat()

    registrar_log(
        modulo="cadastro",
        acao="visualizar",
        entidade="pacientes",
        descricao="Abriu tela de cadastro de paciente.",
        detalhes={"clinica_id": session.get("clinica_id")},
    )

    return render_template(
        "cadastro.html",
        admissao_sugestao=hoje,
        clinica_id=session.get("clinica_id"),
        clinica_nome=session.get("clinica_nome"),
    )


@cadastro_bp.route("/cadastro", methods=["POST"])
@require_permission("cadastro", "editar")
def salvar_paciente():
    is_json = request.is_json
    clinica_id = _clinica_id_atual()

    dados_raw = request.get_json(silent=True) if is_json else request.form.to_dict(flat=True)
    dados = _upperize_payload(dados_raw or {})
    dados["clinica_id"] = clinica_id

    if is_json:
        dados["laudos_json"] = _parse_laudos_payload((dados_raw or {}).get("laudos_json"))
    else:
        dados["laudos_json"] = _coletar_laudos_form(request.form)

    try:
        with _conn() as conn:
            try:
                conn.rollback()
            except Exception:
                pass

            ensure_pacientes_schema(conn)

            cep = only_digits(dados.get("cep"))[:8]

            if cep and _has_table(conn, "cep_ibge"):
                cur = conn.cursor()
                cur.execute("""
                    SELECT ibge, municipio
                      FROM cep_ibge
                     WHERE REGEXP_REPLACE(COALESCE(cep, ''), '[^0-9]', '', 'g') = %s
                     LIMIT 1;
                """, (cep,))
                row_cep = _fetchone_dict(cur)

                if row_cep:
                    if not (dados.get("municipio") or "").strip():
                        dados["municipio"] = (row_cep["municipio"] or "").strip().upper()
                    if not (dados.get("codigo_ibge") or "").strip():
                        dados["codigo_ibge"] = only_digits(row_cep["ibge"])

            laudos_lista = _parse_laudos_list(dados.get("laudos_json"))
            dados["cid"] = laudos_lista[0]["codigo"] if len(laudos_lista) > 0 else ""
            dados["cid2"] = laudos_lista[1]["codigo"] if len(laudos_lista) > 1 else ""

            last_id = _insert_paciente_safe(conn, dados)
            _sync_paciente_laudos(conn, last_id, dados.get("laudos_json"), clinica_id)

            conn.commit()

        registrar_log(
            modulo="cadastro",
            acao="criar",
            entidade="pacientes",
            entidade_id=last_id,
            descricao="Paciente cadastrado.",
            detalhes={
                "clinica_id": clinica_id,
                "paciente_id": last_id,
                "nome": dados.get("nome"),
                "cpf": dados.get("cpf"),
                "cns": dados.get("cns"),
                "prontuario": dados.get("prontuario"),
                "mod": dados.get("mod"),
                "cid": dados.get("cid"),
                "cid2": dados.get("cid2"),
            },
        )

        redirect_url = _build_redirect_url(dados, last_id)

        if is_json:
            return jsonify({
                "status": "sucesso",
                "mensagem": "Paciente cadastrado com sucesso",
                "id": last_id,
                "redirect": redirect_url,
            }), 201

        return redirect(redirect_url, code=303)

    except Exception as e:
        log_erro(
            "cadastro",
            e,
            entidade="pacientes",
            descricao="Erro ao cadastrar paciente.",
            detalhes={
                "clinica_id": clinica_id,
                "nome": dados.get("nome"),
                "cpf": dados.get("cpf"),
                "cns": dados.get("cns"),
            },
        )

        if is_json:
            return jsonify({"status": "erro", "mensagem": str(e)}), 500

        return jsonify({"status": "erro", "mensagem": str(e)}), 500