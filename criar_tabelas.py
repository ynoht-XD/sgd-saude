import sqlite3
import os

# 🔹 Caminho único do banco (com extensão .db na pasta correta)
os.makedirs("data_base", exist_ok=True)
CAMINHO_DB = os.path.join("data_base", "sgd_db.db")


def _conn():
    conn = sqlite3.connect(CAMINHO_DB)
    # garantir enforcement de FKs quando existirem
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


# 🔸 Criação da tabela PACIENTES (já existente)
def criar_tabela_pacientes():
    conn = _conn()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pacientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prontuario TEXT,
        nome TEXT,
        cns TEXT,
        status TEXT,
        nascimento TEXT,
        idade INTEGER,
        sexo TEXT,
        mod TEXT,
        cid TEXT,
        cid2 TEXT,
        nis TEXT,
        raca TEXT,
        admissao TEXT,

        logradouro TEXT,
        codigo_logradouro TEXT,
        numero_casa TEXT,
        complemento TEXT,
        bairro TEXT,
        municipio TEXT,
        cep TEXT,

        cpf TEXT,
        rg TEXT,
        orgao_rg TEXT,
        estado_civil TEXT,

        mae TEXT,
        cpf_mae TEXT,
        rg_mae TEXT,
        rg_ssp_mae TEXT,
        nis_mae TEXT,

        pai TEXT,
        cpf_pai TEXT,
        rg_pai TEXT,
        rg_ssp_pai TEXT,

        telefone1 TEXT,
        telefone2 TEXT,
        telefone3 TEXT,
        email TEXT,

        responsavel TEXT,
        cpf_responsavel TEXT,
        rg_responsavel TEXT,
        orgao_rg_responsavel TEXT
    )
    """)

    conn.commit()
    conn.close()
    print("✅ Tabela 'pacientes' criada/ok.")


# 🔸 Usuários (login por CPF), CBOs e relação N:N
def criar_tabelas_usuarios_cbos():
    conn = _conn()
    c = conn.cursor()

    # Usuários
    c.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        nome              TEXT NOT NULL,
        cpf               TEXT NOT NULL UNIQUE,            -- login
        email             TEXT,
        role              TEXT NOT NULL CHECK(role IN ('ADMIN','RECEPCAO','PROFISSIONAL')),
        profissional_id   INTEGER,                         -- opcional (sem FK aqui)
        password_hash     TEXT NOT NULL,
        must_change_pass  INTEGER NOT NULL DEFAULT 1,
        is_active         INTEGER NOT NULL DEFAULT 1,
        failed_attempts   INTEGER NOT NULL DEFAULT 0,
        locked_until      TEXT,
        last_login_at     TEXT,
        created_at        TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_role ON usuarios(role);")
    c.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_active ON usuarios(is_active);")

    # Catálogo de CBOs
    c.execute("""
    CREATE TABLE IF NOT EXISTS cbos (
        codigo    TEXT PRIMARY KEY,                        -- ex.: '223605'
        descricao TEXT NOT NULL
    )
    """)

    # Ligação N:N usuário x CBO
    c.execute("""
    CREATE TABLE IF NOT EXISTS usuario_cbo (
        usuario_id INTEGER NOT NULL,
        cbo_codigo TEXT    NOT NULL,
        PRIMARY KEY (usuario_id, cbo_codigo),
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
        FOREIGN KEY (cbo_codigo) REFERENCES cbos(codigo) ON DELETE RESTRICT
    )
    """)

    conn.commit()
    conn.close()
    print("✅ Tabelas 'usuarios', 'cbos' e 'usuario_cbo' criadas/ok.")


# 🔸 Fila de Atendimentos (triagem/recepção)
def criar_tabela_fila_atendimentos():
    conn = _conn()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS fila_atendimentos (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        data_ref        TEXT NOT NULL DEFAULT (date('now')),   -- AAAA-MM-DD
        ticket          TEXT,                                   -- ex.: A001
        paciente_id     INTEGER NOT NULL,
        servico         TEXT,                                   -- ou servico_id no futuro
        prioridade      INTEGER NOT NULL DEFAULT 3 CHECK (prioridade IN (1,2,3)), -- 1 alta, 2 média, 3 normal
        status          TEXT NOT NULL DEFAULT 'aguardando'
                           CHECK (status IN ('aguardando','chamado','em_atendimento','finalizado','cancelado','falta')),
        observacoes     TEXT,
        criado_em       TEXT NOT NULL DEFAULT (datetime('now')),
        chamado_em      TEXT,
        iniciado_em     TEXT,
        finalizado_em   TEXT,
        profissional_id INTEGER,                                -- quem atendeu (opcional)
        atendimento_id  INTEGER,                                -- referência ao registro em atendimentos
        UNIQUE (data_ref, ticket),
        FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE
    )
    """)

    c.execute("CREATE INDEX IF NOT EXISTS idx_fila_status ON fila_atendimentos(status);")
    c.execute("CREATE INDEX IF NOT EXISTS idx_fila_data ON fila_atendimentos(data_ref);")
    c.execute("CREATE INDEX IF NOT EXISTS idx_fila_criado ON fila_atendimentos(criado_em);")

    conn.commit()
    conn.close()
    print("✅ Tabela 'fila_atendimentos' criada/ok.")


# 🔸 Atendimentos (ajustado para ligar com fila e profissional)
def criar_tabela_atendimentos():
    conn = _conn()
    c = conn.cursor()

    # 🔥 segue sua lógica anterior de recriar nos testes
    c.execute("DROP TABLE IF EXISTS atendimentos")

    c.execute("""
    CREATE TABLE atendimentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paciente_id INTEGER NOT NULL,
        data_atendimento TEXT NOT NULL,
        procedimento TEXT,
        codigo_sigtap TEXT,
        status_justificativa TEXT CHECK(status_justificativa IN ('realizado', 'faltou')) NOT NULL DEFAULT 'realizado',
        justificativa TEXT,
        anexo_atestado TEXT,
        evolucao TEXT,

        -- campos já existentes para facilitar preenchimento
        nome TEXT,
        prontuario TEXT,
        mod TEXT,
        status TEXT,

        -- novos campos para integração com fila e profissional
        profissional_id INTEGER,            -- id do usuário/profissional que atendeu
        fila_id INTEGER,                    -- id em fila_atendimentos (quando vier de lá)

        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY (paciente_id) REFERENCES pacientes(id)
    )
    """)

    c.execute("CREATE INDEX IF NOT EXISTS idx_atendimentos_paciente ON atendimentos(paciente_id);")
    c.execute("CREATE INDEX IF NOT EXISTS idx_atendimentos_data ON atendimentos(data_atendimento);")

    conn.commit()
    conn.close()
    print("✅ Tabela 'atendimentos' criada/ok.")


# 🔸 Flags de Módulos (habilitar/desabilitar no painel)
def criar_tabela_feature_flags():
    conn = _conn()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS sistema_modulos (
        chave       TEXT PRIMARY KEY,                         -- ex.: 'fila_atendimentos'
        habilitado  INTEGER NOT NULL DEFAULT 0,               -- 0/1
        updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)

    # Índice auxiliar para consultas por habilitado
    c.execute("CREATE INDEX IF NOT EXISTS idx_modulos_habilitado ON sistema_modulos(habilitado);")

    conn.commit()
    conn.close()
    print("✅ Tabela 'sistema_modulos' criada/ok.")


# 🔸 Execução
if __name__ == '__main__':
    criar_tabela_pacientes()
    criar_tabelas_usuarios_cbos()
    criar_tabela_fila_atendimentos()
    criar_tabela_atendimentos()
    criar_tabela_feature_flags()
    print("🎉 Estrutura básica criada/atualizada com sucesso.")
