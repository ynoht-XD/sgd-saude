"""Importa a base CEP/IBGE direto do disco (sem upload HTTP).

Reaproveita `admin.bibliotecas.importar_cep_ibge_txt` (mesmo parser, mesma validacao e mesmos
lotes de 50.000 do importador da tela): o arquivo e aberto aqui e entregue no formato que o
importador espera (um objeto com `.stream`). Nada do codigo da tela/rota foi alterado.

ATENCAO: o importador substitui a tabela inteira (TRUNCATE + INSERT em lotes), como o da tela.
Rodar de novo com o mesmo arquivo deixa a tabela identica (nao duplica).

Uso (a partir de /opt/sgd-saude/app):
    python -m scripts.importar_cep_ibge                       # arquivo padrao em data_base/ibge/
    python -m scripts.importar_cep_ibge --arquivo AMOSTRA.txt --lote 50000

O destino vem do db.py (DATABASE_URL ou PG_*). Sem DATABASE_URL/PG_* o padrao do db.py e o banco
de PRODUCAO (porta 5434): por seguranca o script recusa essa porta sem a flag --producao.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from types import SimpleNamespace
from urllib.parse import urlparse

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

ARQUIVO_PADRAO = os.path.join(RAIZ, "data_base", "ibge", "cep_ibge_municipio_integracao_20260413_103100.txt")
PORTA_PRODUCAO = 5434


def _destino() -> tuple[str, int, str]:
    """host, porta e banco do destino (nunca imprime usuario/senha)."""
    from db import get_database_url
    u = urlparse(get_database_url())
    return u.hostname or "?", int(u.port or 5432), (u.path or "/").lstrip("/")


def _contar_linhas_de_dados(caminho: str) -> int:
    n = 0
    with open(caminho, "rb") as f:
        for _ in f:
            n += 1
    return max(n - 1, 0)  # menos o cabecalho


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Importa a base CEP/IBGE de um arquivo do disco.")
    ap.add_argument("--arquivo", default=ARQUIVO_PADRAO, help="TXT delimitado por ';' com cabecalho (padrao: arquivo em data_base/ibge/)")
    ap.add_argument("--lote", type=int, default=50000, help="linhas por lote/commit (padrao 50000, igual ao importador da tela)")
    ap.add_argument("--producao", action="store_true", help="confirma que o destino e o banco de producao (porta 5434)")
    args = ap.parse_args(argv)

    caminho = os.path.abspath(args.arquivo)
    if not os.path.isfile(caminho):
        print("ERRO: arquivo nao encontrado:", caminho)
        return 1

    host, porta, banco = _destino()
    print(f"Destino : {host}:{porta}/{banco}")
    print(f"Arquivo : {caminho} ({os.path.getsize(caminho):,} bytes)".replace(",", "."))
    if porta == PORTA_PRODUCAO and not args.producao:
        print("RECUSADO: o destino e o banco de PRODUCAO (porta 5434). Se for isso mesmo, rode com --producao.")
        return 3

    from admin.bibliotecas import importar_cep_ibge_txt
    from db import conectar_db

    esperadas = _contar_linhas_de_dados(caminho)
    print(f"Linhas de dados no arquivo: {esperadas}")

    t0 = time.time()
    with open(caminho, "rb") as f:
        processados, ignorados = importar_cep_ibge_txt(SimpleNamespace(stream=f, filename=os.path.basename(caminho)), chunk_size=args.lote)
    dur = time.time() - t0

    conn = conectar_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS n, COUNT(DISTINCT cep) AS ceps FROM cep_ibge")
        r = cur.fetchone()
        n, ceps = (r["n"], r["ceps"]) if isinstance(r, dict) else (r[0], r[1])
    finally:
        conn.close()

    print(f"Importadas: {processados} | ignoradas: {ignorados} | tempo: {dur:.1f} s")
    print(f"Tabela cep_ibge agora: {n} linhas, {ceps} CEPs distintos")
    ok = (processados + ignorados == esperadas) and (n == processados)
    print("CONFERENCIA:", "OK (importadas + ignoradas = linhas do arquivo; tabela = importadas)" if ok else "DIVERGENTE")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
