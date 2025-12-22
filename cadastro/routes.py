# cadastro/routes.py
from __future__ import annotations

import sqlite3
from datetime import date
from urllib.parse import quote_plus

from flask import request, render_template, jsonify, redirect, url_for

from . import cadastro_bp
from db import conectar_db


# =============================================================================
# Helpers de normalização
# =============================================================================

_UPPER_FIELDS = {
    "nome", "status", "cid", "cid2", "raca",
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
# MIGRATION / SCHEMA: PACIENTES
# =============================================================================

def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=? LIMIT 1;", (table,))
    return cur.fetchone() is not None


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return {r[1] for r in cur.fetchall()}


def _add_col(conn: sqlite3.Connection, table: str, col: str, ddl: str) -> None:
    cols = _table_columns(conn, table)
    if col in cols:
        return
    cur = conn.cursor()
    cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl};")
    conn.commit()


def ensure_pacientes_schema(conn: sqlite3.Connection) -> None:
    """
    Garante que a tabela pacientes exista e tenha TODAS as colunas usadas no INSERT.
    Idempotente (seguro rodar sempre).
    """
    cur = conn.cursor()

    # base mínima (se não existir)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS pacientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prontuario TEXT,
            nome TEXT,
            cns TEXT,
            status TEXT,
            nascimento TEXT,
            idade TEXT,
            sexo TEXT,
            mod TEXT,
            cid TEXT,
            cid2 TEXT,
            admissao TEXT,
            cpf TEXT
        )
        """
    )
    conn.commit()

    # garante colunas do teu INSERT (todas)
    _add_col(conn, "pacientes", "nis", "TEXT")
    _add_col(conn, "pacientes", "raca", "TEXT")
    _add_col(conn, "pacientes", "logradouro", "TEXT")
    _add_col(conn, "pacientes", "codigo_logradouro", "TEXT")
    _add_col(conn, "pacientes", "numero_casa", "TEXT")
    _add_col(conn, "pacientes", "complemento", "TEXT")
    _add_col(conn, "pacientes", "bairro", "TEXT")
    _add_col(conn, "pacientes", "municipio", "TEXT")
    _add_col(conn, "pacientes", "cep", "TEXT")

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

    # índices úteis
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pacientes_nome ON pacientes(nome);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pacientes_cpf  ON pacientes(cpf);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pacientes_prontuario ON pacientes(prontuario);")
    conn.commit()


# =============================================================================
# Rotas
# =============================================================================

@cadastro_bp.route("/cadastro", methods=["GET"])
def cadastrar_paciente():
    hoje = date.today().isoformat()
    return render_template("cadastro.html", admissao_sugestao=hoje)


@cadastro_bp.route("/cadastro", methods=["POST"])
def salvar_paciente():
    is_json = request.is_json
    dados_raw = request.get_json(silent=True) if is_json else request.form.to_dict(flat=True)
    dados = _upperize_payload(dados_raw or {})

    try:
        with conectar_db() as conn:
            # ✅ garante schema antes do insert
            ensure_pacientes_schema(conn)

            cursor = conn.cursor()
            print("📦 Dados recebidos (normalizados):", dados)

            cursor.execute(
                """
                INSERT INTO pacientes (
                    prontuario, nome, cns, status, nascimento, idade, sexo, mod,
                    cid, cid2, nis, raca, admissao,
                    logradouro, codigo_logradouro, numero_casa, complemento, bairro, municipio, cep,
                    cpf, rg, orgao_rg, estado_civil,
                    mae, cpf_mae, rg_mae, rg_ssp_mae, nis_mae,
                    pai, cpf_pai, rg_pai, rg_ssp_pai,
                    telefone1, telefone2, telefone3, email,
                    responsavel, cpf_responsavel, rg_responsavel, orgao_rg_responsavel
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dados.get("prontuario"),
                    dados.get("nome"),
                    dados.get("cns"),
                    dados.get("status"),
                    dados.get("nascimento"),
                    dados.get("idade"),
                    dados.get("sexo"),
                    dados.get("mod"),
                    dados.get("cid"),
                    dados.get("cid2"),
                    dados.get("nis"),
                    dados.get("raca"),
                    dados.get("admissao"),
                    dados.get("logradouro"),
                    dados.get("codigo_logradouro"),
                    dados.get("numero_casa"),
                    dados.get("complemento"),
                    dados.get("bairro"),
                    dados.get("municipio"),
                    dados.get("cep"),
                    dados.get("cpf"),
                    dados.get("rg"),
                    dados.get("orgao_rg"),
                    dados.get("estado_civil"),
                    dados.get("mae"),
                    dados.get("cpf_mae"),
                    dados.get("rg_mae"),
                    dados.get("rg_ssp_mae"),
                    dados.get("nis_mae"),
                    dados.get("pai"),
                    dados.get("cpf_pai"),
                    dados.get("rg_pai"),
                    dados.get("rg_ssp_pai"),
                    dados.get("telefone1"),
                    dados.get("telefone2"),
                    dados.get("telefone3"),
                    dados.get("email"),
                    dados.get("responsavel"),
                    dados.get("cpf_responsavel"),
                    dados.get("rg_responsavel"),
                    dados.get("orgao_rg_responsavel"),
                ),
            )

            last_id = cursor.lastrowid
            conn.commit()

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
        import traceback
        traceback.print_exc()
        if is_json:
            return jsonify({"status": "erro", "mensagem": str(e)}), 500
        return jsonify({"status": "erro", "mensagem": str(e)}), 500
