from flask import render_template, request, redirect, url_for, flash, jsonify, send_file
import math
import re
from io import BytesIO
import unicodedata

import pandas as pd

from db import conectar_db
from . import procedimentos_bp


# =========================================================
# CONEXÃO
# =========================================================
def get_conn():
    return conectar_db()


# =========================================================
# HELPERS
# =========================================================
def normalize_text(v):
    return str(v or "").strip()


def only_digits(v):
    return re.sub(r"\D+", "", str(v or ""))


def safe_like(v):
    return f"%{normalize_text(v)}%"


def normalize_col(c):
    c = str(c or "").strip().lower()
    c = unicodedata.normalize("NFKD", c)
    c = "".join(ch for ch in c if not unicodedata.combining(ch))
    c = re.sub(r"[^a-z0-9]+", "_", c)
    return c.strip("_")


def get_col(row, *names):
    for name in names:
        key = normalize_col(name)

        try:
            val = row.get(key)
            if val is not None and str(val).strip() != "":
                return val
        except Exception:
            pass

        try:
            val = row.get(name)
            if val is not None and str(val).strip() != "":
                return val
        except Exception:
            pass

    return ""


def row_to_dict(row, cols=None):
    if row is None:
        return None

    if isinstance(row, dict):
        return dict(row)

    if hasattr(row, "keys"):
        return {k: row[k] for k in row.keys()}

    if cols:
        return dict(zip(cols, row))

    try:
        return dict(row)
    except Exception:
        return {}


def fetchone_value(row):
    if not row:
        return 0

    if isinstance(row, dict):
        return list(row.values())[0]

    if hasattr(row, "keys"):
        keys = list(row.keys())
        return row[keys[0]] if keys else 0

    return row[0]


def to_float(v):
    try:
        txt = str(v or "").strip()

        if not txt:
            return 0.0

        txt = txt.replace("R$", "").replace(" ", "")

        if "," in txt and "." in txt:
            txt = txt.replace(".", "").replace(",", ".")
        else:
            txt = txt.replace(",", ".")

        return float(txt)
    except Exception:
        return 0.0


def to_int(v):
    try:
        txt = only_digits(v)
        return int(txt) if txt else 0
    except Exception:
        return 0


def montar_where(args):
    q = normalize_text(args.get("q"))
    codigo = normalize_text(args.get("codigo"))
    descricao = normalize_text(args.get("descricao"))
    complexidade = normalize_text(args.get("complexidade"))
    competencia = normalize_text(args.get("competencia"))
    cid = normalize_text(args.get("cid"))
    cbo = normalize_text(args.get("cbo"))
    servico = normalize_text(args.get("servico"))
    financiamento = normalize_text(args.get("financiamento"))
    rubrica = normalize_text(args.get("rubrica"))

    where = ["1=1"]
    params = []

    if q:
        where.append("""
            (
                codigo ILIKE %s OR
                descricao ILIKE %s OR
                cids_codigos ILIKE %s OR
                cids_descricoes ILIKE %s OR
                cbos_codigos ILIKE %s OR
                cbos_descricoes ILIKE %s OR
                servicos_codigos ILIKE %s OR
                servicos_descricoes ILIKE %s OR
                classificacoes_codigos ILIKE %s OR
                classificacoes_descricoes ILIKE %s
            )
        """)
        params.extend([safe_like(q)] * 10)

    if codigo:
        where.append("codigo ILIKE %s")
        params.append(safe_like(codigo))

    if descricao:
        where.append("descricao ILIKE %s")
        params.append(safe_like(descricao))

    if complexidade:
        where.append("complexidade ILIKE %s")
        params.append(safe_like(complexidade))

    if competencia:
        where.append("competencia ILIKE %s")
        params.append(safe_like(competencia))

    if cid:
        where.append("(cids_codigos ILIKE %s OR cids_descricoes ILIKE %s)")
        params.extend([safe_like(cid), safe_like(cid)])

    if cbo:
        where.append("(cbos_codigos ILIKE %s OR cbos_descricoes ILIKE %s)")
        params.extend([safe_like(cbo), safe_like(cbo)])

    if servico:
        where.append("""
            (
                servicos_codigos ILIKE %s OR
                servicos_descricoes ILIKE %s OR
                classificacoes_codigos ILIKE %s OR
                classificacoes_descricoes ILIKE %s
            )
        """)
        params.extend([safe_like(servico)] * 4)

    if financiamento:
        where.append("(co_financiamento ILIKE %s OR no_financiamento ILIKE %s)")
        params.extend([safe_like(financiamento), safe_like(financiamento)])

    if rubrica:
        where.append("(co_rubrica ILIKE %s OR no_rubrica ILIKE %s)")
        params.extend([safe_like(rubrica), safe_like(rubrica)])

    filtros = {
        "q": q,
        "codigo": codigo,
        "descricao": descricao,
        "complexidade": complexidade,
        "competencia": competencia,
        "cid": cid,
        "cbo": cbo,
        "servico": servico,
        "financiamento": financiamento,
        "rubrica": rubrica,
    }

    return " AND ".join(where), params, filtros


# =========================================================
# SCHEMA
# =========================================================
def ensure_schema():
    conn = get_conn()

    try:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS procedimentos (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,

                codigo TEXT,
                descricao TEXT,
                complexidade TEXT,
                competencia TEXT,

                valor_sh NUMERIC(14, 2) DEFAULT 0,
                valor_sa NUMERIC(14, 2) DEFAULT 0,
                valor_sp NUMERIC(14, 2) DEFAULT 0,
                valor_total NUMERIC(14, 2) DEFAULT 0,

                co_financiamento TEXT,
                no_financiamento TEXT,
                co_rubrica TEXT,
                no_rubrica TEXT,

                qtd_cids INTEGER DEFAULT 0,
                cids_codigos TEXT,
                cids_descricoes TEXT,

                qtd_cbos INTEGER DEFAULT 0,
                cbos_codigos TEXT,
                cbos_descricoes TEXT,

                qtd_servicos INTEGER DEFAULT 0,
                servicos_codigos TEXT,
                servicos_descricoes TEXT,

                classificacoes_codigos TEXT,
                classificacoes_descricoes TEXT,

                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        alter_columns = {
            "codigo": "TEXT",
            "descricao": "TEXT",
            "complexidade": "TEXT",
            "competencia": "TEXT",
            "valor_sh": "NUMERIC(14, 2) DEFAULT 0",
            "valor_sa": "NUMERIC(14, 2) DEFAULT 0",
            "valor_sp": "NUMERIC(14, 2) DEFAULT 0",
            "valor_total": "NUMERIC(14, 2) DEFAULT 0",
            "co_financiamento": "TEXT",
            "no_financiamento": "TEXT",
            "co_rubrica": "TEXT",
            "no_rubrica": "TEXT",
            "qtd_cids": "INTEGER DEFAULT 0",
            "cids_codigos": "TEXT",
            "cids_descricoes": "TEXT",
            "qtd_cbos": "INTEGER DEFAULT 0",
            "cbos_codigos": "TEXT",
            "cbos_descricoes": "TEXT",
            "qtd_servicos": "INTEGER DEFAULT 0",
            "servicos_codigos": "TEXT",
            "servicos_descricoes": "TEXT",
            "classificacoes_codigos": "TEXT",
            "classificacoes_descricoes": "TEXT",
            "criado_em": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "atualizado_em": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        }

        for col, col_type in alter_columns.items():
            cur.execute(f"""
                ALTER TABLE procedimentos
                ADD COLUMN IF NOT EXISTS {col} {col_type}
            """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_procedimentos_codigo
            ON procedimentos (codigo)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_procedimentos_competencia
            ON procedimentos (competencia)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_procedimentos_complexidade
            ON procedimentos (complexidade)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_procedimentos_financiamento
            ON procedimentos (co_financiamento)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_procedimentos_rubrica
            ON procedimentos (co_rubrica)
        """)

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


# =========================================================
# LISTAGEM
# =========================================================
@procedimentos_bp.route("/")
def index():
    ensure_schema()

    pagina = max(1, request.args.get("pagina", 1, type=int))
    por_pagina = 12
    offset = (pagina - 1) * por_pagina

    where_sql, params, filtros = montar_where(request.args)

    conn = get_conn()

    try:
        cur = conn.cursor()

        cur.execute(f"""
            SELECT COUNT(*) AS total
            FROM procedimentos
            WHERE {where_sql}
        """, params)

        total = fetchone_value(cur.fetchone())
        total = int(total or 0)

        total_paginas = max(1, math.ceil(total / por_pagina))

        cur.execute(f"""
            SELECT
                id,
                codigo,
                descricao,
                complexidade,
                competencia,
                valor_sh,
                valor_sa,
                valor_sp,
                valor_total,
                co_financiamento,
                no_financiamento,
                co_rubrica,
                no_rubrica,
                qtd_cids,
                cids_codigos,
                cids_descricoes,
                qtd_cbos,
                cbos_codigos,
                cbos_descricoes,
                qtd_servicos,
                servicos_codigos,
                servicos_descricoes,
                classificacoes_codigos,
                classificacoes_descricoes
            FROM procedimentos
            WHERE {where_sql}
            ORDER BY codigo ASC NULLS LAST, descricao ASC NULLS LAST
            LIMIT %s OFFSET %s
        """, params + [por_pagina, offset])

        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        dados = [row_to_dict(row, cols) for row in rows]

        cur.execute("""
            SELECT DISTINCT complexidade
            FROM procedimentos
            WHERE complexidade IS NOT NULL AND TRIM(complexidade) <> ''
            ORDER BY complexidade
        """)

        cx_rows = cur.fetchall()
        cx_cols = [desc[0] for desc in cur.description]
        complexidades = [
            row_to_dict(row, cx_cols).get("complexidade")
            for row in cx_rows
            if row_to_dict(row, cx_cols).get("complexidade")
        ]

        print("====== DEBUG LISTAGEM PROCEDIMENTOS ======")
        print("Total:", total)
        print("Página:", pagina)
        print("Itens renderizados:", len(dados))
        if dados:
            print("Primeiro item:", dados[0])

        return render_template(
            "proced.html",
            dados=dados,
            filtros=filtros,
            pagina=pagina,
            por_pagina=por_pagina,
            total_paginas=total_paginas,
            total=total,
            complexidades=complexidades,
        )

    finally:
        conn.close()


# =========================================================
# API - DETALHE
# =========================================================
@procedimentos_bp.route("/api/<int:procedimento_id>")
def api_detalhe(procedimento_id):
    ensure_schema()

    conn = get_conn()

    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT
                id,
                codigo,
                descricao,
                complexidade,
                competencia,
                valor_sh,
                valor_sa,
                valor_sp,
                valor_total,
                co_financiamento,
                no_financiamento,
                co_rubrica,
                no_rubrica,
                qtd_cids,
                cids_codigos,
                cids_descricoes,
                qtd_cbos,
                cbos_codigos,
                cbos_descricoes,
                qtd_servicos,
                servicos_codigos,
                servicos_descricoes,
                classificacoes_codigos,
                classificacoes_descricoes
            FROM procedimentos
            WHERE id = %s
        """, (procedimento_id,))

        row = cur.fetchone()

        if not row:
            return jsonify({"ok": False, "erro": "Procedimento não encontrado"}), 404

        cols = [desc[0] for desc in cur.description]
        item = row_to_dict(row, cols)

        return jsonify({"ok": True, "procedimento": item})

    finally:
        conn.close()


# =========================================================
# IMPORTAÇÃO XLSX
# =========================================================
@procedimentos_bp.route("/importar", methods=["POST"])
def importar_xls():
    ensure_schema()

    file = request.files.get("arquivo")

    if not file or file.filename == "":
        flash("Arquivo não enviado.", "error")
        return redirect(url_for("procedimentos.index"))

    try:
        df = pd.read_excel(file, dtype=str).fillna("")
        df.columns = [normalize_col(c) for c in df.columns]

        print("====== DEBUG IMPORTAÇÃO PROCEDIMENTOS ======")
        print("Arquivo:", file.filename)
        print("Colunas detectadas:", list(df.columns))
        print("Total de linhas no Excel:", len(df))

        if len(df) > 0:
            print("Primeira linha:", df.iloc[0].to_dict())

    except Exception as e:
        flash(f"Erro ao ler arquivo: {e}", "error")
        return redirect(url_for("procedimentos.index"))

    conn = get_conn()

    try:
        cur = conn.cursor()
        cur.execute("TRUNCATE TABLE procedimentos RESTART IDENTITY;")

        total_linhas = 0
        total_importados = 0
        total_ignorados = 0

        for idx, row in df.iterrows():
            total_linhas += 1

            codigo = normalize_text(get_col(row, "codigo", "co_procedimento", "cod_procedimento"))
            descricao = normalize_text(get_col(row, "descricao", "no_procedimento", "procedimento"))

            if not codigo and not descricao:
                total_ignorados += 1
                print(f"[IGNORADO] Linha {idx + 2}: sem código e sem descrição")
                continue

            valor_sh = to_float(get_col(row, "valor_sh", "vl_sh"))
            valor_sa = to_float(get_col(row, "valor_sa", "vl_sa"))
            valor_sp = to_float(get_col(row, "valor_sp", "vl_sp"))

            valor_total_planilha = to_float(get_col(row, "valor_total", "vl_total"))
            valor_total = valor_total_planilha if valor_total_planilha > 0 else valor_sh + valor_sa + valor_sp

            cur.execute("""
                INSERT INTO procedimentos (
                    codigo,
                    descricao,
                    complexidade,
                    competencia,

                    valor_sh,
                    valor_sa,
                    valor_sp,
                    valor_total,

                    co_financiamento,
                    no_financiamento,
                    co_rubrica,
                    no_rubrica,

                    qtd_cids,
                    cids_codigos,
                    cids_descricoes,

                    qtd_cbos,
                    cbos_codigos,
                    cbos_descricoes,

                    qtd_servicos,
                    servicos_codigos,
                    servicos_descricoes,

                    classificacoes_codigos,
                    classificacoes_descricoes,

                    atualizado_em
                )
                VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    CURRENT_TIMESTAMP
                )
            """, (
                codigo,
                descricao,
                normalize_text(get_col(row, "complexidade", "tp_complexidade")),
                normalize_text(get_col(row, "competencia", "dt_competencia")),

                valor_sh,
                valor_sa,
                valor_sp,
                valor_total,

                normalize_text(get_col(row, "co_financiamento")),
                normalize_text(get_col(row, "no_financiamento")),
                normalize_text(get_col(row, "co_rubrica")),
                normalize_text(get_col(row, "no_rubrica")),

                to_int(get_col(row, "qtd_cids")),
                normalize_text(get_col(row, "cids_codigos")),
                normalize_text(get_col(row, "cids_descricoes")),

                to_int(get_col(row, "qtd_cbos")),
                normalize_text(get_col(row, "cbos_codigos")),
                normalize_text(get_col(row, "cbos_descricoes")),

                to_int(get_col(row, "qtd_servicos")),
                normalize_text(get_col(row, "servicos_codigos")),
                normalize_text(get_col(row, "servicos_descricoes")),

                normalize_text(get_col(row, "classificacoes_codigos")),
                normalize_text(get_col(row, "classificacoes_descricoes")),
            ))

            total_importados += 1

        cur.execute("""
            SELECT 
                COUNT(*) AS total,
                COUNT(NULLIF(TRIM(codigo), '')) AS com_codigo,
                COUNT(NULLIF(TRIM(descricao), '')) AS com_descricao
            FROM procedimentos
        """)

        resumo = row_to_dict(cur.fetchone(), [desc[0] for desc in cur.description])

        conn.commit()

        print("====== RESULTADO IMPORTAÇÃO ======")
        print("Linhas Excel:", total_linhas)
        print("Importados:", total_importados)
        print("Ignorados:", total_ignorados)
        print("Resumo banco:", resumo)

        flash(
            f"{total_importados} procedimentos importados. "
            f"{total_ignorados} linhas ignoradas.",
            "success"
        )

    except Exception as e:
        conn.rollback()
        print("ERRO NA IMPORTAÇÃO:", e)
        flash(f"Erro na importação: {e}", "error")

    finally:
        conn.close()

    return redirect(url_for("procedimentos.index"))


# =========================================================
# EXCLUSÃO
# =========================================================
@procedimentos_bp.route("/excluir/<int:procedimento_id>", methods=["POST"])
def excluir(procedimento_id):
    ensure_schema()

    conn = get_conn()

    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM procedimentos WHERE id = %s", (procedimento_id,))

        if cur.rowcount == 0:
            flash("Procedimento não encontrado.", "warning")
        else:
            flash("Procedimento excluído com sucesso.", "success")

        conn.commit()

    except Exception as e:
        conn.rollback()
        flash(f"Erro ao excluir procedimento: {e}", "error")

    finally:
        conn.close()

    return redirect(url_for("procedimentos.index"))


# =========================================================
# LIMPAR BASE
# =========================================================
@procedimentos_bp.route("/limpar", methods=["POST"])
def limpar():
    ensure_schema()

    conn = get_conn()

    try:
        cur = conn.cursor()
        cur.execute("TRUNCATE TABLE procedimentos RESTART IDENTITY;")
        conn.commit()

        flash("Base de procedimentos limpa com sucesso.", "success")

    except Exception as e:
        conn.rollback()
        flash(f"Erro ao limpar base: {e}", "error")

    finally:
        conn.close()

    return redirect(url_for("procedimentos.index"))


@procedimentos_bp.route("/limpar-banco", methods=["POST"])
def limpar_banco():
    return limpar()


# =========================================================
# EXPORTAÇÃO XLSX
# =========================================================
@procedimentos_bp.route("/exportar", methods=["GET"])
def exportar():
    ensure_schema()

    where_sql, params, _ = montar_where(request.args)

    conn = get_conn()

    try:
        cur = conn.cursor()

        cur.execute(f"""
            SELECT
                codigo,
                descricao,
                complexidade,
                competencia,
                valor_sh,
                valor_sa,
                valor_sp,
                valor_total,
                co_financiamento,
                no_financiamento,
                co_rubrica,
                no_rubrica,
                qtd_cids,
                cids_codigos,
                cids_descricoes,
                qtd_cbos,
                cbos_codigos,
                cbos_descricoes,
                qtd_servicos,
                servicos_codigos,
                servicos_descricoes,
                classificacoes_codigos,
                classificacoes_descricoes
            FROM procedimentos
            WHERE {where_sql}
            ORDER BY codigo ASC NULLS LAST, descricao ASC NULLS LAST
        """, params)

        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        dados = [row_to_dict(row, cols) for row in rows]

        df = pd.DataFrame(dados, columns=cols)

        mem = BytesIO()

        with pd.ExcelWriter(mem, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="procedimentos")

        mem.seek(0)

        return send_file(
            mem,
            as_attachment=True,
            download_name="procedimentos_filtrados.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    finally:
        conn.close()


# =========================================================
# PESQUISA EM LOTE
# =========================================================
@procedimentos_bp.route("/lote", methods=["GET", "POST"])
def lote():
    ensure_schema()

    resultados = []
    total_enviados = 0
    total_encontrados = 0

    if request.method == "POST":
        texto = request.form.get("codigos", "") or ""
        codigos = [
            normalize_text(c)
            for c in re.split(r"[\n,; ]+", texto)
            if normalize_text(c)
        ]

        total_enviados = len(codigos)

        if codigos:
            conn = get_conn()

            try:
                cur = conn.cursor()

                for codigo in codigos:
                    cur.execute("""
                        SELECT
                            id,
                            codigo,
                            descricao,
                            complexidade,
                            competencia,
                            valor_sh,
                            valor_sa,
                            valor_sp,
                            valor_total,
                            co_financiamento,
                            no_financiamento,
                            co_rubrica,
                            no_rubrica,
                            qtd_cids,
                            cids_codigos,
                            cids_descricoes,
                            qtd_cbos,
                            cbos_codigos,
                            cbos_descricoes,
                            qtd_servicos,
                            servicos_codigos,
                            servicos_descricoes,
                            classificacoes_codigos,
                            classificacoes_descricoes
                        FROM procedimentos
                        WHERE codigo = %s
                        LIMIT 1
                    """, (codigo,))

                    row = cur.fetchone()

                    if row:
                        cols = [desc[0] for desc in cur.description]
                        item = row_to_dict(row, cols)
                        item["encontrado"] = True
                        resultados.append(item)
                        total_encontrados += 1
                    else:
                        resultados.append({
                            "codigo": codigo,
                            "descricao": "Não encontrado",
                            "encontrado": False
                        })

            finally:
                conn.close()

    return render_template(
        "proced_lote.html",
        resultados=resultados,
        total_enviados=total_enviados,
        total_encontrados=total_encontrados
    )