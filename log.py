# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import traceback
from flask import session, request

from db import conectar_db


def ensure_logs_table():
    conn = conectar_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS logs_sistema (
            id SERIAL PRIMARY KEY,
            clinica_id INTEGER,
            clinica_nome VARCHAR(255),
            usuario_id INTEGER,
            usuario_nome VARCHAR(255),
            usuario_cpf VARCHAR(30),
            usuario_role VARCHAR(80),
            modulo VARCHAR(120),
            acao VARCHAR(80),
            entidade VARCHAR(120),
            entidade_id VARCHAR(80),
            paciente_nome VARCHAR(255),
            descricao TEXT,
            detalhes_json JSONB,
            sucesso BOOLEAN DEFAULT TRUE,
            erro_tipo VARCHAR(255),
            erro_mensagem TEXT,
            erro_traceback TEXT,
            ip VARCHAR(80),
            user_agent TEXT,
            metodo VARCHAR(20),
            caminho TEXT,
            endpoint VARCHAR(255),
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cur.execute("""
        ALTER TABLE logs_sistema
        ADD COLUMN IF NOT EXISTS paciente_nome VARCHAR(255);
    """)

    indices = [
        "CREATE INDEX IF NOT EXISTS idx_logs_clinica_id ON logs_sistema (clinica_id);",
        "CREATE INDEX IF NOT EXISTS idx_logs_usuario_id ON logs_sistema (usuario_id);",
        "CREATE INDEX IF NOT EXISTS idx_logs_modulo ON logs_sistema (modulo);",
        "CREATE INDEX IF NOT EXISTS idx_logs_acao ON logs_sistema (acao);",
        "CREATE INDEX IF NOT EXISTS idx_logs_criado_em ON logs_sistema (criado_em);",
        "CREATE INDEX IF NOT EXISTS idx_logs_sucesso ON logs_sistema (sucesso);",
        "CREATE INDEX IF NOT EXISTS idx_logs_paciente_nome ON logs_sistema (paciente_nome);",
    ]

    for sql in indices:
        cur.execute(sql)

    conn.commit()
    cur.close()
    conn.close()


def _get_session_value(*keys, default=None):
    for key in keys:
        value = session.get(key)
        if value not in (None, ""):
            return value
    return default


def _json_safe(value):
    try:
        json.dumps(value, ensure_ascii=False, default=str)
        return value
    except Exception:
        return {"valor": str(value)}


def buscar_nome_paciente_por_id(paciente_id):
    if not paciente_id:
        return None

    try:
        conn = conectar_db()
        cur = conn.cursor()

        cur.execute("""
            SELECT nome
            FROM pacientes
            WHERE id = %s
            LIMIT 1;
        """, (paciente_id,))

        row = cur.fetchone()

        cur.close()
        conn.close()

        if row:
            return row.get("nome") if isinstance(row, dict) else row[0]

    except Exception as e:
        print("⚠️ Não foi possível buscar nome do paciente para log:", repr(e))

    return None


def contexto_atual():
    try:
        ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        if ip and "," in ip:
            ip = ip.split(",")[0].strip()

        return {
            "clinica_id": _get_session_value("clinica_id"),
            "clinica_nome": _get_session_value("clinica_nome"),
            "usuario_id": _get_session_value("usuario_id", "user_id"),
            "usuario_nome": _get_session_value("nome"),
            "usuario_cpf": _get_session_value("cpf", "cpf_digits"),
            "usuario_role": _get_session_value("role"),
            "ip": ip,
            "user_agent": request.headers.get("User-Agent"),
            "metodo": request.method,
            "caminho": request.path,
            "endpoint": request.endpoint,
        }

    except RuntimeError:
        return {
            "clinica_id": None,
            "clinica_nome": None,
            "usuario_id": None,
            "usuario_nome": None,
            "usuario_cpf": None,
            "usuario_role": None,
            "ip": None,
            "user_agent": None,
            "metodo": None,
            "caminho": None,
            "endpoint": None,
        }


def registrar_log(
    modulo: str,
    acao: str,
    descricao: str = "",
    entidade: str | None = None,
    entidade_id: str | int | None = None,
    detalhes: dict | list | str | None = None,
    sucesso: bool = True,
    erro: Exception | None = None,
    clinica_id: int | None = None,
    clinica_nome: str | None = None,
    usuario_id: int | None = None,
    usuario_nome: str | None = None,
    paciente_nome: str | None = None,
):
    try:
        ensure_logs_table()
        ctx = contexto_atual()

        erro_tipo = None
        erro_mensagem = None
        erro_tb = None

        if erro:
            sucesso = False
            erro_tipo = erro.__class__.__name__
            erro_mensagem = str(erro)
            erro_tb = traceback.format_exc()

        detalhes_json = detalhes

        if isinstance(detalhes, str):
            detalhes_json = {"texto": detalhes}

        detalhes_json = _json_safe(detalhes_json or {})

        paciente_nome_final = paciente_nome

        if not paciente_nome_final and isinstance(detalhes_json, dict):
            paciente_nome_final = (
                detalhes_json.get("paciente_nome")
                or detalhes_json.get("nome_paciente")
                or detalhes_json.get("nome")
            )

        if not paciente_nome_final and entidade and str(entidade).lower() in ("paciente", "pacientes"):
            paciente_nome_final = buscar_nome_paciente_por_id(entidade_id)

        conn = conectar_db()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO logs_sistema (
                clinica_id,
                clinica_nome,
                usuario_id,
                usuario_nome,
                usuario_cpf,
                usuario_role,
                modulo,
                acao,
                entidade,
                entidade_id,
                paciente_nome,
                descricao,
                detalhes_json,
                sucesso,
                erro_tipo,
                erro_mensagem,
                erro_traceback,
                ip,
                user_agent,
                metodo,
                caminho,
                endpoint,
                criado_em
            )
            VALUES (
                %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s::jsonb,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                CURRENT_TIMESTAMP
            );
        """, (
            clinica_id if clinica_id is not None else ctx.get("clinica_id"),
            clinica_nome if clinica_nome is not None else ctx.get("clinica_nome"),
            usuario_id if usuario_id is not None else ctx.get("usuario_id"),
            usuario_nome if usuario_nome is not None else ctx.get("usuario_nome"),
            ctx.get("usuario_cpf"),
            ctx.get("usuario_role"),
            modulo,
            acao,
            entidade,
            str(entidade_id) if entidade_id is not None else None,
            paciente_nome_final,
            descricao,
            json.dumps(detalhes_json, ensure_ascii=False, default=str),
            sucesso,
            erro_tipo,
            erro_mensagem,
            erro_tb,
            ctx.get("ip"),
            ctx.get("user_agent"),
            ctx.get("metodo"),
            ctx.get("caminho"),
            ctx.get("endpoint"),
        ))

        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        print("❌ ERRO AO REGISTRAR LOG:", repr(e))


def log_criacao(modulo, entidade=None, entidade_id=None, descricao="", detalhes=None):
    registrar_log(modulo, "criar", descricao or "Registro criado.", entidade, entidade_id, detalhes, True)


def log_edicao(modulo, entidade=None, entidade_id=None, descricao="", detalhes=None):
    registrar_log(modulo, "editar", descricao or "Registro editado.", entidade, entidade_id, detalhes, True)


def log_exclusao(modulo, entidade=None, entidade_id=None, descricao="", detalhes=None):
    registrar_log(modulo, "excluir", descricao or "Registro excluído.", entidade, entidade_id, detalhes, True)


def log_exportacao(modulo, entidade=None, descricao="", detalhes=None):
    registrar_log(
        modulo=modulo,
        acao="exportar",
        entidade=entidade,
        descricao=descricao or "Exportação realizada.",
        detalhes=detalhes,
        sucesso=True,
    )


def log_visualizacao(modulo, entidade=None, entidade_id=None, descricao="", detalhes=None):
    registrar_log(modulo, "visualizar", descricao or "Visualização realizada.", entidade, entidade_id, detalhes, True)


def log_login(usuario=None, descricao="Login realizado com sucesso."):
    detalhes = {}

    if usuario:
        detalhes = {
            "usuario_id": usuario.get("id"),
            "nome": usuario.get("nome"),
            "cpf": usuario.get("cpf"),
            "role": usuario.get("role"),
            "clinica_id": usuario.get("clinica_id"),
            "is_master": usuario.get("is_master"),
        }

    registrar_log(
        modulo="auth",
        acao="login",
        entidade="usuarios",
        entidade_id=usuario.get("id") if usuario else None,
        descricao=descricao,
        detalhes=detalhes,
        sucesso=True,
        clinica_id=usuario.get("clinica_id") if usuario else None,
        usuario_id=usuario.get("id") if usuario else None,
        usuario_nome=usuario.get("nome") if usuario else None,
    )


def log_logout(descricao="Logout realizado."):
    registrar_log(
        modulo="auth",
        acao="logout",
        entidade="usuarios",
        descricao=descricao,
        sucesso=True,
    )


def log_erro(modulo, erro, entidade=None, entidade_id=None, descricao="", detalhes=None):
    registrar_log(
        modulo=modulo,
        acao="erro",
        entidade=entidade,
        entidade_id=entidade_id,
        descricao=descricao or "Erro capturado no sistema.",
        detalhes=detalhes,
        sucesso=False,
        erro=erro,
    )


def log_paciente_criacao(paciente_id=None, paciente_nome=None, descricao="", detalhes=None):
    registrar_log(
        modulo="pacientes",
        acao="criar",
        entidade="pacientes",
        entidade_id=paciente_id,
        paciente_nome=paciente_nome,
        descricao=descricao or f"Paciente cadastrado: {paciente_nome or paciente_id}.",
        detalhes=detalhes,
        sucesso=True,
    )


def log_paciente_edicao(paciente_id=None, paciente_nome=None, descricao="", detalhes=None):
    registrar_log(
        modulo="pacientes",
        acao="editar",
        entidade="pacientes",
        entidade_id=paciente_id,
        paciente_nome=paciente_nome,
        descricao=descricao or f"Paciente editado: {paciente_nome or paciente_id}.",
        detalhes=detalhes,
        sucesso=True,
    )


def log_paciente_exportacao(paciente_id=None, paciente_nome=None, tipo_exportacao="exportação", descricao="", detalhes=None):
    registrar_log(
        modulo="pacientes",
        acao="exportar",
        entidade="pacientes",
        entidade_id=paciente_id,
        paciente_nome=paciente_nome,
        descricao=descricao or f"Exportação individual do paciente: {paciente_nome or paciente_id}.",
        detalhes={
            "tipo_exportacao": tipo_exportacao,
            **(detalhes or {}),
        },
        sucesso=True,
    )


def log_evolucao_exportacao_paciente(paciente_id=None, paciente_nome=None, descricao="", detalhes=None):
    registrar_log(
        modulo="evolucoes",
        acao="exportar",
        entidade="pacientes",
        entidade_id=paciente_id,
        paciente_nome=paciente_nome,
        descricao=descricao or f"Exportação de evolução do paciente: {paciente_nome or paciente_id}.",
        detalhes=detalhes,
        sucesso=True,
    )