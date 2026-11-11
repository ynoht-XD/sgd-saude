"""API de etiquetas NFC do SGD. Pacientes exclusivamente de public.pacientes.

O token aleatório é escrito como NDEF TEXT no cartão pelo Android.
O banco conserva somente SHA-256 do token. UID não autentica.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from flask import g, jsonify, request
from db import conectar_db
from . import mobile_nfc_bp
from .auth import require_mobile_token, _one, _rows

TAG_RE = re.compile(r'^SGDNFC1:[A-Za-z0-9_-]{40,100}$')


def _db():
    conn = conectar_db()
    conn.autocommit = False
    return conn


def _schema(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.mobile_nfc_etiquetas (
            id BIGSERIAL PRIMARY KEY,
            clinica_id INTEGER NOT NULL REFERENCES public.clinicas(id),
            paciente_id INTEGER NOT NULL REFERENCES public.pacientes(id),
            token_hash CHAR(64) NOT NULL UNIQUE,
            criado_por INTEGER NOT NULL REFERENCES public.usuarios(id),
            criada_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ativada_em TIMESTAMPTZ,
            revogada_em TIMESTAMPTZ,
            revogada_por INTEGER REFERENCES public.usuarios(id)
        )
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_mobile_nfc_paciente_ativo
        ON public.mobile_nfc_etiquetas(clinica_id, paciente_id)
        WHERE revogada_em IS NULL
    """)


def _patient(cur, cid, pid):
    cur.execute("""SELECT id, nome, prontuario, CASE WHEN BTRIM(nascimento) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN SUBSTRING(BTRIM(nascimento),9,2)||'/'||SUBSTRING(BTRIM(nascimento),6,2)||'/'||SUBSTRING(BTRIM(nascimento),1,4) ELSE NULLIF(BTRIM(nascimento),'') END AS nascimento FROM public.pacientes
                   WHERE id=%s AND clinica_id=%s""", (pid, cid))
    return _one(cur)


def _response_error(message, code=400):
    return jsonify(ok=False, erro=message), code


@mobile_nfc_bp.get('/pacientes')
@require_mobile_token
def buscar_pacientes():
    termo = str(request.args.get('q') or '').strip()
    if len(termo) < 2 or len(termo) > 100:
        return _response_error('Informe ao menos 2 caracteres.', 400)
    cid = g.mobile_nfc['clinica_id']
    conn = _db()
    try:
        with conn.cursor() as cur:
            _schema(cur)
            cur.execute("""
                SELECT p.id, p.nome, p.prontuario, CASE WHEN BTRIM(p.nascimento) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN SUBSTRING(BTRIM(p.nascimento),9,2)||'/'||SUBSTRING(BTRIM(p.nascimento),6,2)||'/'||SUBSTRING(BTRIM(p.nascimento),1,4) ELSE NULLIF(BTRIM(p.nascimento),'') END AS nascimento,
                       EXISTS (SELECT 1 FROM public.mobile_nfc_etiquetas e
                               WHERE e.paciente_id=p.id AND e.clinica_id=p.clinica_id
                                 AND e.revogada_em IS NULL) AS possui_nfc
                FROM public.pacientes p
                WHERE p.clinica_id=%s
                  AND (p.prontuario=%s OR p.nome ILIKE %s)
                ORDER BY CASE WHEN p.prontuario=%s THEN 0 ELSE 1 END, p.nome
                LIMIT 25
            """, (cid, termo, '%' + termo + '%', termo))
            # A tabela de etiquetas é inicializada antes de executar a busca.
            items = _rows(cur)
        conn.commit()
        return jsonify(ok=True, pacientes=items)
    finally:
        conn.close()


@mobile_nfc_bp.post('/etiquetas/preparar')
@require_mobile_token
def preparar_etiqueta():
    """Reserva token. Android deve gravar NDEF e então chamar /ativar."""
    data = request.get_json(silent=True) or {}
    try:
        pid = int(data.get('paciente_id'))
    except (TypeError, ValueError):
        return _response_error('Paciente inválido.')
    cid = g.mobile_nfc['clinica_id']
    uid = g.mobile_nfc['usuario_id']
    conn = _db()
    try:
        with conn.cursor() as cur:
            _schema(cur)
            paciente = _patient(cur, cid, pid)
            if not paciente:
                return _response_error('Paciente não encontrado nesta clínica.', 404)
            cur.execute("""SELECT id FROM public.mobile_nfc_etiquetas
                           WHERE clinica_id=%s AND paciente_id=%s AND revogada_em IS NULL
                           FOR UPDATE""", (cid, pid))
            if _one(cur):
                return _response_error('Paciente já possui etiqueta ativa. Revogue antes de substituir.', 409)
            token = 'SGDNFC1:' + secrets.token_urlsafe(36)
            digest = hashlib.sha256(token.encode('ascii')).hexdigest()
            cur.execute("""INSERT INTO public.mobile_nfc_etiquetas
                           (clinica_id,paciente_id,token_hash,criado_por)
                           VALUES (%s,%s,%s,%s) RETURNING id""", (cid,pid,digest,uid))
            eid = _one(cur)['id']
        conn.commit()
        response = jsonify(ok=True, etiqueta_id=eid, conteudo_ndef=token, paciente=paciente)
        response.headers['Cache-Control'] = 'no-store'
        return response
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@mobile_nfc_bp.post('/etiquetas/<int:etiqueta_id>/ativar')
@require_mobile_token
def ativar_etiqueta(etiqueta_id):
    """Chamar somente após escrita E LEITURA de verificação no Android."""
    cid = g.mobile_nfc['clinica_id']
    data = request.get_json(silent=True) or {}
    token = str(data.get('conteudo_ndef') or '')
    if not TAG_RE.fullmatch(token):
        return _response_error('Conteúdo NFC inválido.')
    digest = hashlib.sha256(token.encode('ascii')).hexdigest()
    conn = _db()
    try:
        with conn.cursor() as cur:
            cur.execute("""UPDATE public.mobile_nfc_etiquetas
                           SET ativada_em=NOW()
                           WHERE id=%s AND clinica_id=%s AND token_hash=%s
                             AND revogada_em IS NULL AND ativada_em IS NULL
                           RETURNING id""", (etiqueta_id,cid,digest))
            if not _one(cur):
                return _response_error('Etiqueta inexistente, revogada ou já ativada.', 409)
        conn.commit()
        return jsonify(ok=True, mensagem='Etiqueta vinculada e ativada.')
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@mobile_nfc_bp.post('/etiquetas/identificar')
@require_mobile_token
def identificar_etiqueta():
    data = request.get_json(silent=True) or {}
    token = str(data.get('conteudo_ndef') or '')
    if not TAG_RE.fullmatch(token):
        return _response_error('Etiqueta não reconhecida.', 404)
    digest = hashlib.sha256(token.encode('ascii')).hexdigest()
    cid = g.mobile_nfc['clinica_id']
    conn = _db()
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT p.id, p.nome, p.prontuario, CASE WHEN BTRIM(p.nascimento) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN SUBSTRING(BTRIM(p.nascimento),9,2)||'/'||SUBSTRING(BTRIM(p.nascimento),6,2)||'/'||SUBSTRING(BTRIM(p.nascimento),1,4) ELSE NULLIF(BTRIM(p.nascimento),'') END AS nascimento, e.id AS etiqueta_id
                           FROM public.mobile_nfc_etiquetas e
                           JOIN public.pacientes p ON p.id=e.paciente_id AND p.clinica_id=e.clinica_id
                           WHERE e.token_hash=%s AND e.clinica_id=%s
                             AND e.ativada_em IS NOT NULL AND e.revogada_em IS NULL""", (digest,cid))
            paciente = _one(cur)
        if not paciente:
            return _response_error('Etiqueta sem vínculo ativo nesta clínica.', 404)
        response = jsonify(ok=True, paciente=paciente)
        response.headers['Cache-Control'] = 'no-store'
        return response
    finally:
        conn.close()


@mobile_nfc_bp.post('/etiquetas/<int:etiqueta_id>/revogar')
@require_mobile_token
def revogar_etiqueta(etiqueta_id):
    cid = g.mobile_nfc['clinica_id']
    uid = g.mobile_nfc['usuario_id']
    conn = _db()
    try:
        with conn.cursor() as cur:
            cur.execute("""UPDATE public.mobile_nfc_etiquetas
                           SET revogada_em=NOW(), revogada_por=%s
                           WHERE id=%s AND clinica_id=%s AND revogada_em IS NULL
                           RETURNING id""", (uid,etiqueta_id,cid))
            if not _one(cur):
                return _response_error('Vínculo não encontrado ou já revogado.', 404)
        conn.commit()
        return jsonify(ok=True, mensagem='Vínculo revogado.')
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
