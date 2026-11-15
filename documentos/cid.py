# documentos/cid.py
"""Acesso ao catalogo de CID-10 (`cid_catalogo`), compartilhado por documentos e atendimentos.

A BUSCA (autocomplete) e UMA so: GET /api/cid10/buscar (documentos/routes.py). Aqui ficam so as conferencias de servidor.
Regra: CID e OPCIONAL; formato invalido sempre e erro; codigo fora do catalogo so e erro quando o catalogo JA FOI importado
(tabela com linhas). Catalogo ausente/vazio nunca bloqueia.
"""
from __future__ import annotations

from atendimentos.helpers import _row_get, has_table

from .validacao import normaliza_cid


def catalogo_tem_dados(conn) -> bool:
    if not has_table(conn, "cid_catalogo"):
        return False
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM cid_catalogo LIMIT 1")
    return cur.fetchone() is not None


def buscar_no_catalogo(conn, codigo: str) -> tuple[str, str] | None:
    """(co_cid, no_cid) do catalogo (compara sem o ponto: F84.0 == F840); None se nao ha tabela ou o codigo nao existe."""
    if not has_table(conn, "cid_catalogo"):
        return None
    cur = conn.cursor()
    cur.execute(
        "SELECT co_cid, no_cid FROM cid_catalogo WHERE REPLACE(co_cid, '.', '') = REPLACE(%s, '.', '') LIMIT 1",
        (codigo,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return ((_row_get(row, "co_cid", 0, "") or "").strip(), (_row_get(row, "no_cid", 1, "") or "").strip())


def descricao_oficial(conn, codigo: str) -> str | None:
    achado = buscar_no_catalogo(conn, codigo)
    return (achado[1] or None) if achado else None


def valida_cid_atendimento(conn, bruto) -> tuple[str | None, str | None]:
    """CID digitado no atendimento -> (codigo_para_gravar | None, erro | None).
    Vazio = (None, None). Se o catalogo foi importado, o codigo tem de existir nele e e gravado como o catalogo o escreve."""
    codigo_in = str(bruto or "").strip()
    if not codigo_in:
        return None, None

    cid, erros = normaliza_cid({"codigo": codigo_in})
    if erros or not cid:
        return None, (erros[0] if erros else "CID inválido.")

    codigo = cid["codigo"]
    if catalogo_tem_dados(conn):
        achado = buscar_no_catalogo(conn, codigo)
        if not achado:
            return None, f"CID {codigo} não encontrado no catálogo de CID-10. Escolha um da lista de sugestões."
        codigo = achado[0] or codigo
    return codigo[:10], None
