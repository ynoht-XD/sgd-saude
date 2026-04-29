# admin/bibliotecas.py
from __future__ import annotations

import io
import csv
from openpyxl import load_workbook
from flask import (
    render_template, request, redirect, url_for, flash
)

from . import admin_bp, admin_required
from db import conectar_db


# ============================================================
# SCHEMA POSTGRES
# ============================================================



def ensure_bibliotecas_postgres():
    conn = conectar_db()
    try:
        cur = conn.cursor()

        # =========================
        # CBO
        # =========================
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ocupacoes (
                id SERIAL PRIMARY KEY,
                co_ocupacao VARCHAR(10) UNIQUE,
                no_ocupacao TEXT
            );
        """)

        # =========================
        # CID
        # =========================
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cid_catalogo (
                id SERIAL PRIMARY KEY,
                co_cid VARCHAR(10) UNIQUE,
                no_cid TEXT
            );
        """)

        # =========================
        # CEP / IBGE
        # =========================
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cep_ibge (
                id SERIAL PRIMARY KEY,
                cep VARCHAR(10),
                ibge VARCHAR(20),
                municipio TEXT,
                coduf VARCHAR(5),
                codmunicip VARCHAR(10),
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # INDEXES
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ocupacoes_nome ON ocupacoes(no_ocupacao);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cid_nome ON cid_catalogo(no_cid);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cep ON cep_ibge(cep);")

        conn.commit()
    finally:
        conn.close()


# ============================================================
# HELPERS
# ============================================================

def _header_map(headers):
    mapa = {}
    for idx, h in enumerate(headers):
        chave = str(h or "").strip().lower()
        if chave:
            mapa[chave] = idx
    return mapa


# ============================================================
# IMPORTAÇÃO CBO
# ============================================================

def importar_cbo_xlsx(file_storage):
    ensure_bibliotecas_postgres()

    wb = load_workbook(file_storage, read_only=True, data_only=True)
    ws = wb.active

    rows = ws.iter_rows(values_only=True)
    headers = next(rows, None)

    if not headers:
        raise ValueError("Arquivo vazio")

    hmap = _header_map(headers)

    if "co_ocupacao" not in hmap or "no_ocupacao" not in hmap:
        raise ValueError("Colunas obrigatórias: co_ocupacao, no_ocupacao")

    conn = conectar_db()
    try:
        cur = conn.cursor()

        processados = 0
        ignorados = 0

        for row in rows:
            codigo_raw = row[hmap["co_ocupacao"]]
            nome = str(row[hmap["no_ocupacao"]] or "").strip()

            codigo = str(codigo_raw or "").strip()

            if codigo.endswith(".0"):
                codigo = codigo[:-2]

            codigo = "".join(ch for ch in codigo if ch.isdigit()).zfill(6)

            if not codigo or not nome:
                ignorados += 1
                continue

            cur.execute("""
                INSERT INTO ocupacoes (co_ocupacao, no_ocupacao)
                VALUES (%s, %s)
                ON CONFLICT (co_ocupacao)
                DO UPDATE SET no_ocupacao = EXCLUDED.no_ocupacao
            """, (codigo, nome))

            processados += 1

        conn.commit()
        return processados, ignorados

    finally:
        conn.close()


# ============================================================
# IMPORTAÇÃO CID
# ============================================================

# ============================================================
# IMPORTAÇÃO CID
# ============================================================

def importar_cid_xlsx(file_storage):
    ensure_bibliotecas_postgres()

    wb = load_workbook(file_storage, read_only=True, data_only=True)
    ws = wb.active

    rows = ws.iter_rows(values_only=True)
    headers = next(rows, None)

    if not headers:
        raise ValueError("Arquivo vazio.")

    hmap = _header_map(headers)

    col_codigo = (
        hmap.get("co_cid")
        or hmap.get("codigo")
        or hmap.get("código")
        or hmap.get("cid")
    )

    col_nome = (
        hmap.get("no_cid")
        or hmap.get("descricao")
        or hmap.get("descrição")
        or hmap.get("nome")
    )

    if col_codigo is None or col_nome is None:
        raise ValueError("Colunas obrigatórias: co_cid e no_cid.")

    conn = conectar_db()
    try:
        cur = conn.cursor()

        processados = 0
        ignorados = 0

        for row in rows:
            codigo = str(row[col_codigo] or "").strip().upper()
            nome = str(row[col_nome] or "").strip()

            codigo = codigo.replace(".", "").replace("-", "").strip()

            if not codigo or not nome:
                ignorados += 1
                continue

            cur.execute("""
                INSERT INTO cid_catalogo (co_cid, no_cid)
                VALUES (%s, %s)
                ON CONFLICT (co_cid)
                DO UPDATE SET no_cid = EXCLUDED.no_cid;
            """, (codigo, nome))

            processados += 1

        conn.commit()
        return processados, ignorados

    finally:
        conn.close()

# ============================================================
# IMPORTAÇÃO CEP / IBGE
# ============================================================

def importar_cep_ibge_txt(file_storage, chunk_size=10000):
    ensure_bibliotecas_postgres()

    conn = conectar_db()
    processados = 0
    ignorados = 0

    try:
        cur = conn.cursor()

        stream = io.TextIOWrapper(file_storage.stream, encoding="utf-8-sig")
        reader = csv.DictReader(stream, delimiter=";")

        lote = []

        for row in reader:
            cep = str(row.get("CEP") or "").strip()
            ibge = str(row.get("IBGE") or "").strip()
            municipio = str(row.get("MUNICIPIO") or "").strip()
            coduf = str(row.get("CODUF") or "").strip()
            codmunicip = str(row.get("CODMUNIC") or "").strip()
            criado_em = str(row.get("CRIADO_EM") or "").strip() or None

            if not cep or not ibge or not municipio:
                ignorados += 1
                continue

            lote.append((
                cep,
                ibge,
                municipio,
                coduf,
                codmunicip,
                criado_em,
            ))

            if len(lote) >= chunk_size:
                cur.executemany("""
                    INSERT INTO cep_ibge
                    (cep, ibge, municipio, coduf, codmunicip, criado_em)
                    VALUES (%s, %s, %s, %s, %s, COALESCE(%s::timestamp, CURRENT_TIMESTAMP));
                """, lote)

                processados += len(lote)
                lote.clear()

        if lote:
            cur.executemany("""
                INSERT INTO cep_ibge
                (cep, ibge, municipio, coduf, codmunicip, criado_em)
                VALUES (%s, %s, %s, %s, %s, COALESCE(%s::timestamp, CURRENT_TIMESTAMP));
            """, lote)

            processados += len(lote)

        conn.commit()
        return processados, ignorados

    finally:
        conn.close()



# ============================================================
# ROTAS
# ============================================================
@admin_bp.route("/cbo", methods=["GET", "POST"])
@admin_required
def biblioteca_cbo():
    ensure_bibliotecas_postgres()

    if request.method == "POST":
        arquivo = request.files.get("arquivo")

        if not arquivo or arquivo.filename == "":
            flash("Selecione um arquivo XLSX.", "error")
            return redirect(url_for("admin.biblioteca_cbo"))

        try:
            p, i = importar_cbo_xlsx(arquivo)
            flash(f"CBO importado com sucesso: {p} registros. Ignorados: {i}.", "success")
        except Exception as e:
            flash(f"Erro ao importar CBO: {e}", "error")

        return redirect(url_for("admin.biblioteca_cbo"))

    q = (request.args.get("q") or "").strip()
    itens = []

    conn = conectar_db()
    try:
        cur = conn.cursor()

        if q:
            like = f"%{q}%"
            cur.execute("""
                SELECT
                    co_ocupacao AS codigo,
                    no_ocupacao AS descricao
                FROM ocupacoes
                WHERE co_ocupacao ILIKE %s
                   OR no_ocupacao ILIKE %s
                ORDER BY co_ocupacao
                LIMIT 500;
            """, (like, like))
        else:
            cur.execute("""
                SELECT
                    co_ocupacao AS codigo,
                    no_ocupacao AS descricao
                FROM ocupacoes
                ORDER BY co_ocupacao
                LIMIT 500;
            """)

        rows = cur.fetchall()

        for row in rows:
            itens.append({
                "codigo": row[0],
                "descricao": row[1],
            })

    except Exception as e:
        conn.rollback()
        flash(f"Erro ao carregar CBOs: {e}", "error")

    finally:
        conn.close()

    return render_template(
        "cbo.html",
        titulo="Biblioteca CBO",
        q=q,
        itens=itens,
    )

# ============================================================
# ROTA CID
# ============================================================

@admin_bp.route("/cid", methods=["GET", "POST"])
@admin_required
def biblioteca_cid():
    ensure_bibliotecas_postgres()

    if request.method == "POST":
        arquivo = request.files.get("arquivo")

        if not arquivo or arquivo.filename == "":
            flash("Selecione um arquivo XLSX.", "error")
            return redirect(url_for("admin.biblioteca_cid"))

        try:
            p, i = importar_cid_xlsx(arquivo)
            flash(f"CID importado com sucesso: {p} registros. Ignorados: {i}.", "success")
        except Exception as e:
            flash(f"Erro ao importar CID: {e}", "error")

        return redirect(url_for("admin.biblioteca_cid"))

    q = (request.args.get("q") or "").strip()
    pagina = request.args.get("pagina", 1, type=int)

    por_pagina = 50
    pagina = max(pagina, 1)
    offset = (pagina - 1) * por_pagina

    itens = []
    total = 0

    conn = conectar_db()
    try:
        cur = conn.cursor()

        if q:
            like = f"%{q}%"

            cur.execute("""
                SELECT COUNT(*)
                FROM cid_catalogo
                WHERE co_cid ILIKE %s
                   OR no_cid ILIKE %s;
            """, (like, like))

            total = cur.fetchone()[0]

            cur.execute("""
                SELECT
                    co_cid AS codigo,
                    no_cid AS descricao
                FROM cid_catalogo
                WHERE co_cid ILIKE %s
                   OR no_cid ILIKE %s
                ORDER BY co_cid
                LIMIT %s OFFSET %s;
            """, (like, like, por_pagina, offset))

        else:
            cur.execute("""
                SELECT COUNT(*)
                FROM cid_catalogo;
            """)

            total = cur.fetchone()[0]

            cur.execute("""
                SELECT
                    co_cid AS codigo,
                    no_cid AS descricao
                FROM cid_catalogo
                ORDER BY co_cid
                LIMIT %s OFFSET %s;
            """, (por_pagina, offset))

        rows = cur.fetchall()

        for row in rows:
            itens.append({
                "codigo": row[0],
                "descricao": row[1],
            })

    except Exception as e:
        conn.rollback()
        flash(f"Erro ao carregar CIDs: {e}", "error")

    finally:
        conn.close()

    total_paginas = max((total + por_pagina - 1) // por_pagina, 1)

    if pagina > total_paginas:
        pagina = total_paginas

    return render_template(
        "cid.html",
        titulo="Biblioteca CID",
        q=q,
        itens=itens,
        pagina=pagina,
        total_paginas=total_paginas,
        total=total,
        por_pagina=por_pagina,
    )


@admin_bp.route("/cep-ibge", methods=["GET", "POST"])
@admin_required
def biblioteca_cep_ibge():
    ensure_bibliotecas_postgres()

    if request.method == "POST":
        arquivo = request.files.get("arquivo")

        if not arquivo or arquivo.filename == "":
            flash("Selecione um arquivo TXT separado por ponto e vírgula.", "error")
            return redirect(url_for("admin.biblioteca_cep_ibge"))

        try:
            p, i = importar_cep_ibge_txt(arquivo)
            flash(f"CEP/IBGE importado com sucesso: {p} registros. Ignorados: {i}.", "success")
        except Exception as e:
            flash(f"Erro ao importar CEP/IBGE: {e}", "error")

        return redirect(url_for("admin.biblioteca_cep_ibge"))

    q = (request.args.get("q") or "").strip()
    pagina = request.args.get("pagina", 1, type=int)

    por_pagina = 50
    pagina = max(pagina, 1)
    offset = (pagina - 1) * por_pagina

    itens = []
    total = 0

    conn = conectar_db()
    try:
        cur = conn.cursor()

        if q:
            like = f"%{q}%"

            cur.execute("""
                SELECT COUNT(*)
                FROM cep_ibge
                WHERE cep ILIKE %s
                   OR ibge ILIKE %s
                   OR municipio ILIKE %s
                   OR coduf ILIKE %s
                   OR codmunicip ILIKE %s;
            """, (like, like, like, like, like))

            total = cur.fetchone()[0]

            cur.execute("""
                SELECT
                    cep,
                    ibge,
                    municipio,
                    coduf,
                    codmunicip,
                    criado_em
                FROM cep_ibge
                WHERE cep ILIKE %s
                   OR ibge ILIKE %s
                   OR municipio ILIKE %s
                   OR coduf ILIKE %s
                   OR codmunicip ILIKE %s
                ORDER BY municipio, cep
                LIMIT %s OFFSET %s;
            """, (like, like, like, like, like, por_pagina, offset))

        else:
            cur.execute("SELECT COUNT(*) FROM cep_ibge;")
            total = cur.fetchone()[0]

            cur.execute("""
                SELECT
                    cep,
                    ibge,
                    municipio,
                    coduf,
                    codmunicip,
                    criado_em
                FROM cep_ibge
                ORDER BY municipio, cep
                LIMIT %s OFFSET %s;
            """, (por_pagina, offset))

        rows = cur.fetchall()

        for row in rows:
            itens.append({
                "cep": row[0],
                "ibge": row[1],
                "municipio": row[2],
                "coduf": row[3],
                "codmunicip": row[4],
                "criado_em": row[5],
            })

    except Exception as e:
        conn.rollback()
        flash(f"Erro ao carregar CEP/IBGE: {e}", "error")

    finally:
        conn.close()

    total_paginas = max((total + por_pagina - 1) // por_pagina, 1)

    if pagina > total_paginas:
        pagina = total_paginas

    return render_template(
        "cep_ibge.html",
        titulo="Biblioteca CEP/IBGE",
        q=q,
        itens=itens,
        pagina=pagina,
        total_paginas=total_paginas,
        total=total,
        por_pagina=por_pagina,
    )
    