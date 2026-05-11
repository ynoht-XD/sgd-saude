# -*- coding: utf-8 -*-
"""
config_clinica.py

Responsável por:
- Criar/garantir estrutura multi-clínica
- Criar tabela clinicas
- Criar tabela clinica_configuracoes
- Adicionar clinica_id em usuarios
- Definir clínica ID 1 como matriz administrativa
- Guardar dados Pix/cobrança da matriz
- Buscar, criar e atualizar dados gerais da clínica
- Resolver clinica_id atual respeitando MASTER
"""

from flask import session, request
from db import conectar_db


MATRIZ_CLINICA_ID = 1


# ============================================================
# HELPERS INTERNOS
# ============================================================

def row_to_dict(row, cursor=None):
    if not row:
        return None

    if isinstance(row, dict):
        return dict(row)

    if cursor and cursor.description:
        colunas = [desc[0] for desc in cursor.description]
        return dict(zip(colunas, row))

    return None


def normalizar_cnpj(cnpj):
    return "".join(ch for ch in str(cnpj or "") if ch.isdigit())


def normalizar_texto(valor):
    return (valor or "").strip()


def bool_valor(valor, default=True):
    if valor is None:
        return default

    if isinstance(valor, bool):
        return valor

    return str(valor).lower() in ("on", "true", "1", "sim", "yes")


def usuario_eh_master():
    return bool(
        session.get("is_master")
        or session.get("is_superuser")
        or session.get("master")
        or str(session.get("role", "")).upper() in ("MASTER", "ROOT", "SUPERADMIN")
    )


def get_clinica_id_atual(default=MATRIZ_CLINICA_ID):
    if usuario_eh_master():
        clinica_id = (
            request.args.get("clinica_id", type=int)
            or request.form.get("clinica_id", type=int)
            or session.get("clinica_id")
            or default
        )
        return int(clinica_id or default)

    return int(session.get("clinica_id") or default)


def eh_matriz(clinica_id):
    return int(clinica_id or 0) == MATRIZ_CLINICA_ID


# ============================================================
# SCHEMA PRINCIPAL MULTI-CLÍNICA
# ============================================================

def ensure_multi_clinica_schema():
    ensure_clinicas_table()
    ensure_usuarios_clinica_columns()
    ensure_clinica_configuracoes_table()
    ensure_clinica_padrao()


def ensure_clinicas_table():
    conn = conectar_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS clinicas (
            id SERIAL PRIMARY KEY,
            nome VARCHAR(255) NOT NULL,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    alteracoes = [
        "ADD COLUMN IF NOT EXISTS nome_fantasia VARCHAR(255)",
        "ADD COLUMN IF NOT EXISTS razao_social VARCHAR(255)",
        "ADD COLUMN IF NOT EXISTS cnpj VARCHAR(30)",
        "ADD COLUMN IF NOT EXISTS cnpj_digits VARCHAR(20)",

        "ADD COLUMN IF NOT EXISTS telefone VARCHAR(40)",
        "ADD COLUMN IF NOT EXISTS whatsapp VARCHAR(40)",
        "ADD COLUMN IF NOT EXISTS email VARCHAR(255)",

        "ADD COLUMN IF NOT EXISTS cep VARCHAR(20)",
        "ADD COLUMN IF NOT EXISTS logradouro VARCHAR(255)",
        "ADD COLUMN IF NOT EXISTS numero VARCHAR(50)",
        "ADD COLUMN IF NOT EXISTS complemento VARCHAR(255)",
        "ADD COLUMN IF NOT EXISTS bairro VARCHAR(120)",
        "ADD COLUMN IF NOT EXISTS municipio VARCHAR(120)",
        "ADD COLUMN IF NOT EXISTS uf VARCHAR(2)",
        "ADD COLUMN IF NOT EXISTS endereco TEXT",

        "ADD COLUMN IF NOT EXISTS responsavel_nome VARCHAR(255)",
        "ADD COLUMN IF NOT EXISTS responsavel_cpf VARCHAR(30)",
        "ADD COLUMN IF NOT EXISTS responsavel_telefone VARCHAR(40)",
        "ADD COLUMN IF NOT EXISTS responsavel_email VARCHAR(255)",

        "ADD COLUMN IF NOT EXISTS cnes VARCHAR(50)",
        "ADD COLUMN IF NOT EXISTS tipo_clinica VARCHAR(120)",

        "ADD COLUMN IF NOT EXISTS ativa BOOLEAN DEFAULT TRUE",
        "ADD COLUMN IF NOT EXISTS is_matriz BOOLEAN DEFAULT FALSE",
        "ADD COLUMN IF NOT EXISTS observacoes TEXT",

        # Dados de cobrança/Pix — principalmente para a matriz administrativa
        "ADD COLUMN IF NOT EXISTS chave_pix VARCHAR(255)",
        "ADD COLUMN IF NOT EXISTS tipo_chave_pix VARCHAR(50)",
        "ADD COLUMN IF NOT EXISTS favorecido_pix VARCHAR(255)",
        "ADD COLUMN IF NOT EXISTS banco_pix VARCHAR(120)",
        "ADD COLUMN IF NOT EXISTS agencia_pix VARCHAR(50)",
        "ADD COLUMN IF NOT EXISTS conta_pix VARCHAR(80)",
        "ADD COLUMN IF NOT EXISTS documento_favorecido_pix VARCHAR(40)",
        "ADD COLUMN IF NOT EXISTS observacao_pagamento TEXT",

        # Futuro financeiro das clínicas clientes
        "ADD COLUMN IF NOT EXISTS valor_mensalidade NUMERIC(12,2)",
        "ADD COLUMN IF NOT EXISTS dia_vencimento INTEGER",
        "ADD COLUMN IF NOT EXISTS plano_contratado VARCHAR(120)",
        "ADD COLUMN IF NOT EXISTS status_pagamento VARCHAR(50) DEFAULT 'ativo'",

        "ADD COLUMN IF NOT EXISTS criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "ADD COLUMN IF NOT EXISTS atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    ]

    for alteracao in alteracoes:
        cur.execute(f"ALTER TABLE clinicas {alteracao};")

    cur.execute("""
        UPDATE clinicas
        SET cnpj_digits = regexp_replace(COALESCE(cnpj, ''), '[^0-9]', '', 'g')
        WHERE cnpj_digits IS NULL OR cnpj_digits = '';
    """)

    cur.execute("""
        UPDATE clinicas
        SET is_matriz = TRUE
        WHERE id = 1;
    """)

    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_clinicas_cnpj_digits_unique
        ON clinicas (cnpj_digits)
        WHERE cnpj_digits IS NOT NULL AND cnpj_digits <> '';
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_clinicas_ativa
        ON clinicas (ativa);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_clinicas_nome
        ON clinicas (nome);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_clinicas_is_matriz
        ON clinicas (is_matriz);
    """)

    conn.commit()
    cur.close()
    conn.close()


def ensure_usuarios_clinica_columns():
    conn = conectar_db()
    cur = conn.cursor()

    cur.execute("""
        ALTER TABLE usuarios
        ADD COLUMN IF NOT EXISTS clinica_id INTEGER DEFAULT 1;
    """)

    cur.execute("""
        ALTER TABLE usuarios
        ADD COLUMN IF NOT EXISTS is_master BOOLEAN DEFAULT FALSE;
    """)

    cur.execute("""
        ALTER TABLE usuarios
        ADD COLUMN IF NOT EXISTS is_superuser BOOLEAN DEFAULT FALSE;
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_usuarios_clinica_id
        ON usuarios (clinica_id);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_usuarios_master
        ON usuarios (is_master);
    """)

    conn.commit()
    cur.close()
    conn.close()


def ensure_clinica_configuracoes_table():
    conn = conectar_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS clinica_configuracoes (
            id SERIAL PRIMARY KEY,
            clinica_id INTEGER NOT NULL DEFAULT 1,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    alteracoes = [
        "ADD COLUMN IF NOT EXISTS clinica_id INTEGER NOT NULL DEFAULT 1",

        "ADD COLUMN IF NOT EXISTS nome_clinica VARCHAR(255)",
        "ADD COLUMN IF NOT EXISTS cnpj VARCHAR(30)",
        "ADD COLUMN IF NOT EXISTS telefone VARCHAR(40)",
        "ADD COLUMN IF NOT EXISTS email VARCHAR(255)",
        "ADD COLUMN IF NOT EXISTS endereco TEXT",

        "ADD COLUMN IF NOT EXISTS logo_path TEXT",
        "ADD COLUMN IF NOT EXISTS logo_bin BYTEA",
        "ADD COLUMN IF NOT EXISTS logo_mime VARCHAR(100)",
        "ADD COLUMN IF NOT EXISTS logo_nome VARCHAR(255)",

        "ADD COLUMN IF NOT EXISTS cabecalho_texto TEXT",
        "ADD COLUMN IF NOT EXISTS cabecalho_img_path TEXT",
        "ADD COLUMN IF NOT EXISTS cabecalho_img_bin BYTEA",
        "ADD COLUMN IF NOT EXISTS cabecalho_img_mime VARCHAR(100)",
        "ADD COLUMN IF NOT EXISTS cabecalho_img_nome VARCHAR(255)",
        "ADD COLUMN IF NOT EXISTS cabecalho_altura INTEGER DEFAULT 130",
        "ADD COLUMN IF NOT EXISTS cabecalho_mostrar_logo BOOLEAN DEFAULT TRUE",
        "ADD COLUMN IF NOT EXISTS cabecalho_alinhamento VARCHAR(20) DEFAULT 'centro'",

        "ADD COLUMN IF NOT EXISTS rodape_texto TEXT",
        "ADD COLUMN IF NOT EXISTS rodape_img_path TEXT",
        "ADD COLUMN IF NOT EXISTS rodape_img_bin BYTEA",
        "ADD COLUMN IF NOT EXISTS rodape_img_mime VARCHAR(100)",
        "ADD COLUMN IF NOT EXISTS rodape_img_nome VARCHAR(255)",
        "ADD COLUMN IF NOT EXISTS rodape_altura INTEGER DEFAULT 115",
        "ADD COLUMN IF NOT EXISTS rodape_alinhamento VARCHAR(20) DEFAULT 'esquerda'",

        "ADD COLUMN IF NOT EXISTS rodape_img_2_path TEXT",
        "ADD COLUMN IF NOT EXISTS rodape_img_2_bin BYTEA",
        "ADD COLUMN IF NOT EXISTS rodape_img_2_mime VARCHAR(100)",
        "ADD COLUMN IF NOT EXISTS rodape_img_2_nome VARCHAR(255)",

        "ADD COLUMN IF NOT EXISTS rodape_img_3_path TEXT",
        "ADD COLUMN IF NOT EXISTS rodape_img_3_bin BYTEA",
        "ADD COLUMN IF NOT EXISTS rodape_img_3_mime VARCHAR(100)",
        "ADD COLUMN IF NOT EXISTS rodape_img_3_nome VARCHAR(255)",

        "ADD COLUMN IF NOT EXISTS margem_superior INTEGER DEFAULT 20",
        "ADD COLUMN IF NOT EXISTS margem_inferior INTEGER DEFAULT 20",
        "ADD COLUMN IF NOT EXISTS margem_esquerda INTEGER DEFAULT 20",
        "ADD COLUMN IF NOT EXISTS margem_direita INTEGER DEFAULT 20",

        "ADD COLUMN IF NOT EXISTS mostrar_linha_cabecalho BOOLEAN DEFAULT FALSE",
        "ADD COLUMN IF NOT EXISTS mostrar_linha_rodape BOOLEAN DEFAULT FALSE",

        "ADD COLUMN IF NOT EXISTS cor_listra_topo VARCHAR(30) DEFAULT '#0f766e'",
        "ADD COLUMN IF NOT EXISTS criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "ADD COLUMN IF NOT EXISTS atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    ]

    for alteracao in alteracoes:
        cur.execute(f"ALTER TABLE clinica_configuracoes {alteracao};")

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_clinica_configuracoes_clinica_id
        ON clinica_configuracoes (clinica_id);
    """)

    conn.commit()
    cur.close()
    conn.close()


def ensure_clinica_padrao():
    conn = conectar_db()
    cur = conn.cursor()

    cur.execute("SELECT id FROM clinicas WHERE id = 1 LIMIT 1;")
    row = cur.fetchone()

    if not row:
        cur.execute("""
            INSERT INTO clinicas (
                id,
                nome,
                nome_fantasia,
                razao_social,
                ativa,
                is_matriz,
                criado_em,
                atualizado_em
            )
            VALUES (
                1,
                'Minha Empresa',
                'Minha Empresa',
                'Minha Empresa',
                TRUE,
                TRUE,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT (id) DO NOTHING;
        """)

        cur.execute("""
            SELECT setval(
                pg_get_serial_sequence('clinicas', 'id'),
                COALESCE((SELECT MAX(id) FROM clinicas), 1),
                TRUE
            );
        """)

    cur.execute("""
        UPDATE clinicas
        SET is_matriz = TRUE,
            ativa = TRUE
        WHERE id = 1;
    """)

    cur.execute("""
        UPDATE usuarios
        SET clinica_id = 1
        WHERE clinica_id IS NULL;
    """)

    conn.commit()
    cur.close()
    conn.close()


# ============================================================
# CRUD DE CLÍNICAS
# ============================================================

def listar_clinicas(apenas_ativas=False):
    ensure_multi_clinica_schema()

    conn = conectar_db()
    cur = conn.cursor()

    if apenas_ativas:
        cur.execute("""
            SELECT *
            FROM clinicas
            WHERE ativa = TRUE
            ORDER BY is_matriz DESC, nome ASC;
        """)
    else:
        cur.execute("""
            SELECT *
            FROM clinicas
            ORDER BY is_matriz DESC, ativa DESC, nome ASC;
        """)

    rows = cur.fetchall()
    clinicas = [row_to_dict(row, cur) for row in rows]

    cur.close()
    conn.close()

    return clinicas


def buscar_clinica(clinica_id):
    ensure_multi_clinica_schema()

    conn = conectar_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM clinicas
        WHERE id = %s
        LIMIT 1;
    """, (clinica_id,))

    row = cur.fetchone()
    clinica = row_to_dict(row, cur)

    cur.close()
    conn.close()

    return clinica


def buscar_clinica_atual():
    clinica_id = get_clinica_id_atual()
    return buscar_clinica(clinica_id)


def montar_payload_clinica(dados):
    cnpj = normalizar_texto(dados.get("cnpj"))
    cnpj_digits = normalizar_cnpj(cnpj)

    return {
        "nome": normalizar_texto(dados.get("nome") or dados.get("nome_clinica")),
        "nome_fantasia": normalizar_texto(dados.get("nome_fantasia")),
        "razao_social": normalizar_texto(dados.get("razao_social")),
        "cnpj": cnpj,
        "cnpj_digits": cnpj_digits,

        "telefone": normalizar_texto(dados.get("telefone")),
        "whatsapp": normalizar_texto(dados.get("whatsapp")),
        "email": normalizar_texto(dados.get("email")),

        "cep": normalizar_texto(dados.get("cep")),
        "logradouro": normalizar_texto(dados.get("logradouro")),
        "numero": normalizar_texto(dados.get("numero")),
        "complemento": normalizar_texto(dados.get("complemento")),
        "bairro": normalizar_texto(dados.get("bairro")),
        "municipio": normalizar_texto(dados.get("municipio")),
        "uf": normalizar_texto(dados.get("uf"))[:2].upper(),
        "endereco": normalizar_texto(dados.get("endereco")),

        "responsavel_nome": normalizar_texto(dados.get("responsavel_nome")),
        "responsavel_cpf": normalizar_texto(dados.get("responsavel_cpf")),
        "responsavel_telefone": normalizar_texto(dados.get("responsavel_telefone")),
        "responsavel_email": normalizar_texto(dados.get("responsavel_email")),

        "cnes": normalizar_texto(dados.get("cnes")),
        "tipo_clinica": normalizar_texto(dados.get("tipo_clinica")),
        "ativa": bool_valor(dados.get("ativa"), True),
        "observacoes": normalizar_texto(dados.get("observacoes")),

        "chave_pix": normalizar_texto(dados.get("chave_pix")),
        "tipo_chave_pix": normalizar_texto(dados.get("tipo_chave_pix")),
        "favorecido_pix": normalizar_texto(dados.get("favorecido_pix")),
        "banco_pix": normalizar_texto(dados.get("banco_pix")),
        "agencia_pix": normalizar_texto(dados.get("agencia_pix")),
        "conta_pix": normalizar_texto(dados.get("conta_pix")),
        "documento_favorecido_pix": normalizar_texto(dados.get("documento_favorecido_pix")),
        "observacao_pagamento": normalizar_texto(dados.get("observacao_pagamento")),

        "valor_mensalidade": dados.get("valor_mensalidade") or None,
        "dia_vencimento": dados.get("dia_vencimento") or None,
        "plano_contratado": normalizar_texto(dados.get("plano_contratado")),
        "status_pagamento": normalizar_texto(dados.get("status_pagamento") or "ativo"),
    }


def criar_clinica(dados):
    ensure_multi_clinica_schema()

    payload = montar_payload_clinica(dados)

    if not payload["nome"]:
        raise ValueError("Informe o nome da clínica.")

    conn = conectar_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO clinicas (
            nome, nome_fantasia, razao_social,
            cnpj, cnpj_digits,
            telefone, whatsapp, email,
            cep, logradouro, numero, complemento, bairro, municipio, uf, endereco,
            responsavel_nome, responsavel_cpf, responsavel_telefone, responsavel_email,
            cnes, tipo_clinica,
            ativa, is_matriz, observacoes,
            chave_pix, tipo_chave_pix, favorecido_pix, banco_pix,
            agencia_pix, conta_pix, documento_favorecido_pix, observacao_pagamento,
            valor_mensalidade, dia_vencimento, plano_contratado, status_pagamento,
            criado_em, atualizado_em
        )
        VALUES (
            %s, %s, %s,
            %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s,
            %s, FALSE, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        RETURNING id;
    """, (
        payload["nome"],
        payload["nome_fantasia"],
        payload["razao_social"],
        payload["cnpj"],
        payload["cnpj_digits"],

        payload["telefone"],
        payload["whatsapp"],
        payload["email"],

        payload["cep"],
        payload["logradouro"],
        payload["numero"],
        payload["complemento"],
        payload["bairro"],
        payload["municipio"],
        payload["uf"],
        payload["endereco"],

        payload["responsavel_nome"],
        payload["responsavel_cpf"],
        payload["responsavel_telefone"],
        payload["responsavel_email"],

        payload["cnes"],
        payload["tipo_clinica"],

        payload["ativa"],
        payload["observacoes"],

        payload["chave_pix"],
        payload["tipo_chave_pix"],
        payload["favorecido_pix"],
        payload["banco_pix"],
        payload["agencia_pix"],
        payload["conta_pix"],
        payload["documento_favorecido_pix"],
        payload["observacao_pagamento"],

        payload["valor_mensalidade"],
        payload["dia_vencimento"],
        payload["plano_contratado"],
        payload["status_pagamento"],
    ))

    row = cur.fetchone()

    if isinstance(row, dict):
        nova_id = row.get("id")
    else:
        nova_id = row[0]

    conn.commit()
    cur.close()
    conn.close()

    return nova_id


def atualizar_clinica(clinica_id, dados):
    ensure_multi_clinica_schema()

    payload = montar_payload_clinica(dados)

    if not payload["nome"]:
        raise ValueError("Informe o nome da clínica.")

    conn = conectar_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE clinicas
        SET
            nome = %s,
            nome_fantasia = %s,
            razao_social = %s,
            cnpj = %s,
            cnpj_digits = %s,

            telefone = %s,
            whatsapp = %s,
            email = %s,

            cep = %s,
            logradouro = %s,
            numero = %s,
            complemento = %s,
            bairro = %s,
            municipio = %s,
            uf = %s,
            endereco = %s,

            responsavel_nome = %s,
            responsavel_cpf = %s,
            responsavel_telefone = %s,
            responsavel_email = %s,

            cnes = %s,
            tipo_clinica = %s,
            ativa = %s,
            is_matriz = CASE WHEN id = 1 THEN TRUE ELSE is_matriz END,
            observacoes = %s,

            chave_pix = %s,
            tipo_chave_pix = %s,
            favorecido_pix = %s,
            banco_pix = %s,
            agencia_pix = %s,
            conta_pix = %s,
            documento_favorecido_pix = %s,
            observacao_pagamento = %s,

            valor_mensalidade = %s,
            dia_vencimento = %s,
            plano_contratado = %s,
            status_pagamento = %s,

            atualizado_em = CURRENT_TIMESTAMP
        WHERE id = %s;
    """, (
        payload["nome"],
        payload["nome_fantasia"],
        payload["razao_social"],
        payload["cnpj"],
        payload["cnpj_digits"],

        payload["telefone"],
        payload["whatsapp"],
        payload["email"],

        payload["cep"],
        payload["logradouro"],
        payload["numero"],
        payload["complemento"],
        payload["bairro"],
        payload["municipio"],
        payload["uf"],
        payload["endereco"],

        payload["responsavel_nome"],
        payload["responsavel_cpf"],
        payload["responsavel_telefone"],
        payload["responsavel_email"],

        payload["cnes"],
        payload["tipo_clinica"],
        payload["ativa"] if not eh_matriz(clinica_id) else True,
        payload["observacoes"],

        payload["chave_pix"],
        payload["tipo_chave_pix"],
        payload["favorecido_pix"],
        payload["banco_pix"],
        payload["agencia_pix"],
        payload["conta_pix"],
        payload["documento_favorecido_pix"],
        payload["observacao_pagamento"],

        payload["valor_mensalidade"],
        payload["dia_vencimento"],
        payload["plano_contratado"],
        payload["status_pagamento"],

        clinica_id,
    ))

    conn.commit()
    cur.close()
    conn.close()


def salvar_clinica(dados, clinica_id=None):
    ensure_multi_clinica_schema()

    if clinica_id:
        atualizar_clinica(clinica_id, dados)
        return clinica_id

    return criar_clinica(dados)


def desativar_clinica(clinica_id):
    ensure_multi_clinica_schema()

    if eh_matriz(clinica_id):
        raise ValueError("A matriz administrativa não pode ser desativada.")

    conn = conectar_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE clinicas
        SET ativa = FALSE,
            atualizado_em = CURRENT_TIMESTAMP
        WHERE id = %s;
    """, (clinica_id,))

    conn.commit()
    cur.close()
    conn.close()


def ativar_clinica(clinica_id):
    ensure_multi_clinica_schema()

    conn = conectar_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE clinicas
        SET ativa = TRUE,
            atualizado_em = CURRENT_TIMESTAMP
        WHERE id = %s;
    """, (clinica_id,))

    conn.commit()
    cur.close()
    conn.close()


# ============================================================
# CONFIGURAÇÕES VISUAIS / TIMBRE
# ============================================================

def buscar_configuracao_clinica(clinica_id=None):
    ensure_multi_clinica_schema()

    clinica_id = clinica_id or get_clinica_id_atual()

    conn = conectar_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM clinica_configuracoes
        WHERE clinica_id = %s
        ORDER BY id DESC
        LIMIT 1;
    """, (clinica_id,))

    row = cur.fetchone()
    config = row_to_dict(row, cur)

    cur.close()
    conn.close()

    return config or {}


def criar_configuracao_padrao_clinica(clinica_id):
    ensure_multi_clinica_schema()

    clinica = buscar_clinica(clinica_id) or {}

    conn = conectar_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO clinica_configuracoes (
            clinica_id,
            nome_clinica,
            cnpj,
            telefone,
            email,
            endereco,
            cabecalho_texto,
            cabecalho_altura,
            cabecalho_mostrar_logo,
            cabecalho_alinhamento,
            rodape_texto,
            rodape_altura,
            rodape_alinhamento,
            margem_superior,
            margem_inferior,
            margem_esquerda,
            margem_direita,
            mostrar_linha_cabecalho,
            mostrar_linha_rodape,
            cor_listra_topo,
            criado_em,
            atualizado_em
        )
        VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, 130, TRUE, 'centro',
            %s, 115, 'esquerda',
            20, 20, 20, 20,
            FALSE, FALSE,
            '#0f766e',
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
        RETURNING id;
    """, (
        clinica_id,
        clinica.get("nome") or "Clínica",
        clinica.get("cnpj"),
        clinica.get("telefone"),
        clinica.get("email"),
        clinica.get("endereco"),
        clinica.get("nome") or "Clínica",
        clinica.get("nome") or "Clínica",
    ))

    row = cur.fetchone()

    if isinstance(row, dict):
        config_id = row.get("id")
    else:
        config_id = row[0]

    conn.commit()
    cur.close()
    conn.close()

    return config_id


def buscar_ou_criar_configuracao_clinica(clinica_id=None):
    clinica_id = clinica_id or get_clinica_id_atual()

    config = buscar_configuracao_clinica(clinica_id)
    if config:
        return config

    criar_configuracao_padrao_clinica(clinica_id)
    return buscar_configuracao_clinica(clinica_id)


# ============================================================
# SEGURANÇA / ESCOPO
# ============================================================

def usuario_pode_acessar_clinica(clinica_id):
    if usuario_eh_master():
        return True

    return int(session.get("clinica_id") or 0) == int(clinica_id or 0)


def exigir_acesso_clinica(clinica_id):
    if not usuario_pode_acessar_clinica(clinica_id):
        raise PermissionError("Você não tem permissão para acessar esta clínica.")

    return True


def filtro_sql_clinica(alias=None):
    if usuario_eh_master():
        return "1=1", []

    clinica_id = get_clinica_id_atual()
    prefixo = f"{alias}." if alias else ""

    return f"{prefixo}clinica_id = %s", [clinica_id]