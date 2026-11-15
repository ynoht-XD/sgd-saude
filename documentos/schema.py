# documentos/schema.py
"""Schema da tabela `documentos_atendimento`.

A MESMA definicao esta em docs/migracao-documentos-atendimento.sql (para revisao/aprovacao antes de rodar em producao).
`ensure_documentos_schema` e idempotente (CREATE ... IF NOT EXISTS) e roda uma vez por processo, como os demais
`ensure_*` do projeto. Nao altera nenhuma tabela existente: so cria a nova tabela e seus indices.
"""
from __future__ import annotations

SQL_TABELA = """
CREATE TABLE IF NOT EXISTS documentos_atendimento (
    id                    SERIAL PRIMARY KEY,
    clinica_id            INTEGER NOT NULL,
    atendimento_id        INTEGER NOT NULL,
    paciente_id           INTEGER NOT NULL,
    profissional_id       INTEGER,
    tipo                  TEXT NOT NULL,
    titulo                TEXT,
    conteudo              JSONB NOT NULL DEFAULT '{}'::jsonb,
    cid_codigo            TEXT,
    cid_descricao         TEXT,
    paciente_snapshot     JSONB NOT NULL DEFAULT '{}'::jsonb,
    profissional_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    status                TEXT NOT NULL DEFAULT 'emitido',
    emitido_em            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    cancelado_em          TIMESTAMP,
    cancelado_por         INTEGER,
    cancelado_motivo      TEXT,
    created_by            INTEGER,
    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_documentos_atendimento_status CHECK (status IN ('emitido', 'cancelado'))
)
"""

SQL_INDICES = (
    "CREATE INDEX IF NOT EXISTS idx_docatend_clinica_atendimento ON documentos_atendimento (clinica_id, atendimento_id)",
    "CREATE INDEX IF NOT EXISTS idx_docatend_clinica_paciente ON documentos_atendimento (clinica_id, paciente_id, emitido_em DESC)",
    "CREATE INDEX IF NOT EXISTS idx_docatend_clinica_tipo ON documentos_atendimento (clinica_id, tipo)",
)

_SCHEMA_PRONTO = False


def ensure_documentos_schema(conn) -> None:
    global _SCHEMA_PRONTO
    if _SCHEMA_PRONTO:
        return

    cur = conn.cursor()
    cur.execute(SQL_TABELA)
    for sql in SQL_INDICES:
        cur.execute(sql)
    conn.commit()
    _SCHEMA_PRONTO = True


def invalidar_schema() -> None:
    """Chamado em erro: se a tabela sumiu (restore de backup), a proxima requisicao recria."""
    global _SCHEMA_PRONTO
    _SCHEMA_PRONTO = False
