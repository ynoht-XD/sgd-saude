from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import g, jsonify, request
from werkzeug.security import check_password_hash

from db import conectar_db
from . import mobile_nfc_bp

TOKEN_HOURS = 12


def _digits(value):
    return re.sub(r"\D", "", str(value or ""))


def _rows(cur):
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row)) if not isinstance(row, dict) else dict(row) for row in cur.fetchall()]


def _one(cur):
    row = cur.fetchone()
    if row is None:
        return None
    return dict(zip([d[0] for d in cur.description], row)) if not isinstance(row, dict) else dict(row)


def _db():
    conn = conectar_db()
    conn.autocommit = False
    return conn


def _init_schema(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS public.mobile_nfc_tokens (
                id BIGSERIAL PRIMARY KEY,
                token_hash CHAR(64) NOT NULL UNIQUE,
                usuario_id INTEGER NOT NULL REFERENCES public.usuarios(id),
                clinica_id INTEGER NOT NULL REFERENCES public.clinicas(id),
                criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                expira_em TIMESTAMPTZ NOT NULL,
                revogado_em TIMESTAMPTZ,
                ultimo_uso_em TIMESTAMPTZ
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_mobile_nfc_tokens_usuario_clinica
            ON public.mobile_nfc_tokens (usuario_id, clinica_id)
        """)
    conn.commit()


def _user_is_master(user):
    return bool(user.get("is_master") or user.get("is_superuser") or
                str(user.get("role") or "").upper() in {"MASTER", "ROOT", "SUPERADMIN"})


def _valid_password(user, password):
    hashes = [user.get("password_hash"), user.get("senha_hash")]
    return any(h and check_password_hash(h, password) for h in hashes)


def _active_users(conn, cpf):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT u.id, u.nome, u.role, u.clinica_id, u.is_master,
                   u.is_superuser, u.password_hash, u.senha_hash,
                   c.nome AS clinica_nome
              FROM public.usuarios u
              JOIN public.clinicas c ON c.id = u.clinica_id
             WHERE (u.cpf_digits = %s OR
                    regexp_replace(coalesce(u.cpf, ''), '[^0-9]', '', 'g') = %s)
               AND u.is_active IS TRUE
               AND c.ativo IS TRUE AND c.ativa IS TRUE
             ORDER BY u.clinica_id, u.id
        """, (cpf, cpf))
        return _rows(cur)


def _bearer_token():
    auth = request.headers.get("Authorization", "")
    parts = auth.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token if 32 <= len(token) <= 256 else None


def require_mobile_token(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = _bearer_token()
        if not token:
            return jsonify(ok=False, erro="Token de acesso ausente."), 401
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        conn = _db()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT t.id AS token_id, t.usuario_id, t.clinica_id,
                           u.nome AS usuario_nome, u.role, u.is_master, u.is_superuser,
                           c.nome AS clinica_nome
                      FROM public.mobile_nfc_tokens t
                      JOIN public.usuarios u ON u.id = t.usuario_id
                      JOIN public.clinicas c ON c.id = t.clinica_id
                     WHERE t.token_hash = %s
                       AND t.revogado_em IS NULL
                       AND t.expira_em > NOW()
                       AND u.is_active IS TRUE
                       AND u.clinica_id = t.clinica_id
                       AND c.ativo IS TRUE AND c.ativa IS TRUE
                """, (digest,))
                row = _one(cur)
                if not row or _user_is_master(row):
                    return jsonify(ok=False, erro="Sessão inválida ou expirada."), 401
                g.mobile_nfc = row
                cur.execute("""
                    UPDATE public.mobile_nfc_tokens
                       SET ultimo_uso_em = NOW()
                     WHERE id = %s
                """, (row["token_id"],))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return fn(*args, **kwargs)
    return wrapper


@mobile_nfc_bp.get("/status")
def mobile_status():
    return jsonify(ok=True, sistema="SGD Saúde NFC", modulo="mobile_nfc",
                   mensagem="API NFC conectada com sucesso")


@mobile_nfc_bp.post("/login")
def mobile_login():
    data = request.get_json(silent=True) or {}
    cpf = _digits(data.get("cpf"))
    password = str(data.get("senha") or "")
    clinic_requested = data.get("clinica_id")
    if len(cpf) != 11 or not password or len(password) > 1024:
        return jsonify(ok=False, erro="CPF ou senha inválidos."), 401

    conn = _db()
    try:
        _init_schema(conn)
        users = _active_users(conn, cpf)
        verified = [u for u in users if _valid_password(u, password) and not _user_is_master(u)]
        if not verified:
            return jsonify(ok=False, erro="CPF ou senha inválidos."), 401

        # Não aceitar múltiplos usuários válidos na mesma clínica sem resolução explícita.
        by_clinic = {}
        for user in verified:
            by_clinic.setdefault(user["clinica_id"], []).append(user)

        if clinic_requested is None:
            if len(by_clinic) > 1:
                return jsonify(ok=True, requer_clinica=True,
                               clinicas=[{"id": cid, "nome": entries[0]["clinica_nome"]}
                                        for cid, entries in by_clinic.items()])
            clinic_id = next(iter(by_clinic))
        else:
            try:
                clinic_id = int(clinic_requested)
            except (TypeError, ValueError):
                return jsonify(ok=False, erro="Clínica inválida."), 400

        candidates = by_clinic.get(clinic_id, [])
        if len(candidates) != 1:
            return jsonify(ok=False, erro="Clínica não autorizada ou vínculo ambíguo."), 403
        user = candidates[0]

        token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        expires = datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO public.mobile_nfc_tokens
                    (token_hash, usuario_id, clinica_id, expira_em)
                VALUES (%s, %s, %s, %s)
            """, (token_hash, user["id"], clinic_id, expires))
            cur.execute("""
                UPDATE public.usuarios
                   SET last_login_at = CURRENT_TIMESTAMP
                 WHERE id = %s
            """, (user["id"],))
        conn.commit()
        response = jsonify(ok=True, requer_clinica=False, token=token,
                           tipo_token="Bearer", expira_em=expires.isoformat(),
                           usuario={"id": user["id"], "nome": user["nome"],
                                    "role": user["role"]},
                           clinica={"id": clinic_id, "nome": user["clinica_nome"]})
        response.headers["Cache-Control"] = "no-store"
        return response
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@mobile_nfc_bp.get("/me")
@require_mobile_token
def mobile_me():
    u = g.mobile_nfc
    return jsonify(ok=True,
                   usuario={"id": u["usuario_id"], "nome": u["usuario_nome"],
                            "role": u["role"]},
                   clinica={"id": u["clinica_id"], "nome": u["clinica_nome"]})


@mobile_nfc_bp.post("/logout")
@require_mobile_token
def mobile_logout():
    conn = _db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE public.mobile_nfc_tokens
                   SET revogado_em = NOW()
                 WHERE id = %s AND revogado_em IS NULL
            """, (g.mobile_nfc["token_id"],))
        conn.commit()
        return jsonify(ok=True, mensagem="Sessão encerrada.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
