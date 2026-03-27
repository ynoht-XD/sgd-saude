# -*- coding: utf-8 -*-
"""
Rotas do módulo Export ➜ BPA-i
- GET  /export/bpa           → formulário (bpa.html)
- POST /export/bpa/convert   → recebe XLS/XLSX/CSV e devolve TXT no layout BPA-i
- GET  /export/bpa/modelo    → baixa planilha modelo com colunas esperadas
"""
import io
import re
import math
from datetime import datetime
from db import conectar_db
import pandas as pd
from flask import request, render_template, abort, send_file, flash, redirect, url_for
from flask import request, render_template, abort, send_file, redirect, url_for, flash
from db import conectar_db
import sqlite3
import csv
import io
from datetime import datetime
from . import export_bp  # blueprint

# ============== Config / Colunas esperadas ==============
REQUIRED_COLUMNS = [
    "prd-ident", "prd-cnes", "prd-cnsmed", "prd-cbo", "prd-dtaten", "prd-pa",
    "prd-cnspac", "prd-sexo", "prd-ibge", "prd-cid", "prd-idade", "prd-qt",
    "prd-caten", "prd-naut", "prd-org", "prd-nmpac", "prd-raca", "prd-etnia",
    "prd-nac", "prd-srv", "prd-clf", "prd-equipe-seq", "prd-equipe-area",
    "prd-cnpj", "prd-cep-pcnte", "prd-lograd-pcnte", "prd-end-pcnte",
    "prd-compl-pcnte", "prd-num-pcnte", "prd-bairro-pcnte", "prd-ddtel-pcnte",
    "prd-email-pcnte", "prd-ine", "prd-dtnasc",
]

ALLOWED_EXT = {".xls", ".xlsx", ".csv"}

# ======================= Helpers genéricos =======================
import re
import pandas as pd
from datetime import date, datetime
import unicodedata

def _is_nan_like(x) -> bool:
    try:
        if pd.isna(x):
            return True
    except Exception:
        pass
    if x is None:
        return True
    if isinstance(x, str) and x.strip().lower() in {"nan", "none", "null"}:
        return True
    return False

def _clean(x) -> str:
    if _is_nan_like(x):
        return ""
    return str(x).strip()

def _digits(s: str) -> str:
    return re.sub(r"\D+", "", s or "")

def _pad_left_zeros(val: str, width: int) -> str:
    v = _digits(val)
    return v.zfill(width)[:width]

def _pad_right(s: str, width: int) -> str:
    s = (s or "")
    return (s[:width]).ljust(width, " ")

def _upper(s: str) -> str:
    return (s or "").strip().upper()

def _competencia_to_yyyymm(competencia_mm_aaaa: str) -> str:
    s = _clean(competencia_mm_aaaa)
    m = re.match(r"^(\d{2})[\/-](\d{4})$", s)
    if not m:
        return "000000"
    mm, aaaa = m.group(1), m.group(2)
    return f"{aaaa}{mm}"

# -------------------------------
# PARSER DE DATA CONFIÁVEL
# -------------------------------
def _parse_to_date(x):
    """
    Converte x em datetime.date com detecção explícita:
    - ISO: YYYY-MM-DD ou YYYY-MM-DD HH:MM[:SS]
    - BR : DD/MM/YYYY ou DD-MM-YYYY
    - Dígitos: DDMMAAAA ou AAAAMMDD (ano >= 1900)
    Retorna None se inválido.
    """
    if _is_nan_like(x):
        return None

    if isinstance(x, date) and not isinstance(x, datetime):
        return x
    if isinstance(x, datetime):
        return x.date()

    s = _clean(x)

    # 1) ISO: YYYY-MM-DD [HH:MM[:SS]]
    m = re.match(r"^\s*(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?\s*$", s)
    if m:
        yyyy, mm, dd = m.group(1), m.group(2), m.group(3)
        try:
            return date(int(yyyy), int(mm), int(dd))
        except Exception:
            return None

    # 2) BR: DD/MM/YYYY ou DD-MM-YYYY
    m = re.match(r"^\s*(\d{2})[\/-](\d{2})[\/-](\d{4})\s*$", s)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        try:
            return date(int(yyyy), int(mm), int(dd))
        except Exception:
            return None

    # 3) Apenas dígitos (8)
    d = _digits(s)
    if len(d) == 8:
        # AAAAMMDD se prefixo parece ano
        if d[:4].isdigit() and int(d[:4]) >= 1900:
            yyyy, mm, dd = d[:4], d[4:6], d[6:8]
        # DDMMAAAA se sufixo parece ano
        elif d[4:].isdigit() and int(d[4:]) >= 1900:
            dd, mm, yyyy = d[:2], d[2:4], d[4:]
        else:
            return None
        try:
            return date(int(yyyy), int(mm), int(dd))
        except Exception:
            return None

    # 4) Fallback controlado: pandas com dayfirst=True
    try:
        ts = pd.to_datetime(s, dayfirst=True, errors="raise")
        if pd.isna(ts):
            return None
        return ts.date()
    except Exception:
        return None

# -------------------------------
# FORMATADORES DE DATA
# -------------------------------
def _date_to_yyyymmdd(x) -> str:
    """Retorna AAAAMMDD, sem ambiguidades."""
    dt = _parse_to_date(x)
    return dt.strftime("%Y%m%d") if dt else ""

def _date_to_ddmmaaaa(x) -> str:
    """Retorna DDMMAAAA (formato exigido no BPA-I)."""
    dt = _parse_to_date(x)
    return dt.strftime("%d%m%Y") if dt else ""

# -------------------------------
# NORMALIZAÇÃO DE CABEÇALHO
# -------------------------------
def _normalize_header(col: str) -> str:
    """
    Normaliza cabeçalhos para comparação:
      - strip + lower
      - troca '_' por '-'
      - colapsa múltiplos espaços/traços/underscores
    """
    col = (col or "").strip().lower()
    col = col.replace("_", "-")
    col = re.sub(r"[\s]+", " ", col)
    col = re.sub(r"[-]{2,}", "-", col)
    return col

def _ext(filename: str) -> str:
    m = re.search(r"\.[^.]+$", filename or "", flags=re.I)
    return (m.group(0) if m else "").lower()

# ===============================
# (Opcional) HELPERS POR BYTES
# Use no export FIXED-WIDTH p/ evitar desalinhamento por UTF-8/acentos
# ===============================
def _ascii_fold(s: str) -> str:
    """Remove acentos (NFKD) para 7-bit ASCII seguro (opcional)."""
    s = s or ""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))

def _pad_right_bytes(s: str, width: int, encoding="latin-1") -> bytes:
    """
    Alfanumérico: right-pad com espaço até 'width' BYTES (trunca em bytes).
    Prefira encoding single-byte (latin-1/cp1252) no arquivo final.
    """
    s = s or ""
    b = s.encode(encoding, errors="replace")
    if len(b) > width:
        b = b[:width]
    else:
        b = b + b" " * (width - len(b))
    return b

def _pad_left_zeros_bytes(val: str, width: int) -> bytes:
    """Numérico: apenas dígitos, zfill, e retorna ASCII puro com width BYTES."""
    v = _digits(val)
    v = v.zfill(width)[:width]
    return v.encode("ascii", errors="strict")

# ======================= Cabeçalho BPA-i =======================
def build_bpai_header(orgao: str, sigla: str, cpf_ou_cnpj: str, competencia_mm_aaaa: str, num_registros: int) -> str:
    prefixo = "01#BPA#"
    yyyymm = _competencia_to_yyyymm(competencia_mm_aaaa)
    nregs6 = str(max(0, int(num_registros))).zfill(6)
    folhas = max(1, math.ceil(num_registros / 99)) if num_registros > 0 else 0
    folhas6 = str(folhas).zfill(6)
    controle = "1111"
    orgao30 = _pad_right(_upper(_clean(orgao)), 30)
    sigla6  = _pad_right(_upper(_clean(sigla)), 6)
    cgc_cpf14 = _pad_left_zeros(cpf_ou_cnpj, 14)
    frase_estatica = "SECRETARIAS DE SAUDE MUNICIPAL DA CIDADE"
    indicador_municipio = "M"
    versao10 = _pad_right("1.0.0", 10)
    fim = "LF"  # mantido conforme sua especificação

    return (
        prefixo + yyyymm + nregs6 + folhas6 + controle +
        orgao30 + sigla6 + cgc_cpf14 + frase_estatica +
        indicador_municipio + versao10 + fim
    )

# ======================= Corpo BPA-i =======================
def build_body_line(row: pd.Series, competencia_yyyymm: str, folha: int, linha: int) -> str:
    tipo = "03"
    cnes7 = _pad_left_zeros(_clean(row.get("prd-cnes", "")), 7)
    comp6 = competencia_yyyymm[:6] if competencia_yyyymm else "000000"
    cns_prof15 = _pad_left_zeros(_clean(row.get("prd-cnsmed", "")), 15)
    cbo6  = _pad_left_zeros(_clean(row.get("prd-cbo", "")), 6)
    dt8 = _date_to_yyyymmdd(row.get("prd-dtaten", "")) or "00000000"

    folha3 = str(int(folha)).zfill(3)
    linha2 = str(int(linha)).zfill(2)
    pa10 = _pad_left_zeros(_clean(row.get("prd-pa", "")), 10)
    cns_pac15 = _pad_left_zeros(_clean(row.get("prd-cnspac", "")), 15)
    sx_val = _upper(_clean(row.get("prd-sexo", "")))
    sx1 = (sx_val[:1] if sx_val else " ")
    ibge6 = _pad_left_zeros(_clean(row.get("prd-ibge", "")), 6)
    cid_raw = _upper(_clean(row.get("prd-cid", "")))
    cid4 = _pad_right(cid_raw, 4)
    idade3 = _pad_left_zeros(_clean(row.get("prd-idade", "")), 3)
    qt6 = _pad_left_zeros(_clean(row.get("prd-qt", "")), 6)
    caten2 = _pad_left_zeros(_clean(row.get("prd-caten", "")), 2)
    naut13 = " " * 13  # nº autorização (em branco)
    org_val = _upper(_clean(row.get("prd-org", ""))) or "BPA"
    org3 = _pad_right(org_val, 3)[:3]
    nmpac30 = _pad_right(_upper(_clean(row.get("prd-nmpac", ""))), 30)
    dtnasc8 = _date_to_yyyymmdd(row.get("prd-dtnasc", "")) or "00000000"


    raca2 = _pad_left_zeros(_clean(row.get("prd-raca", "")), 2)
    etnia4 = " " * 4
    nac3 = _pad_left_zeros(_clean(row.get("prd-nac", "")), 3)
    srv3 = _pad_left_zeros(_clean(row.get("prd-srv", "")), 3)
    clf3 = _pad_left_zeros(_clean(row.get("prd-clf", "")), 3)
    equipe_area_cnpj_26 = " " * 26  # (equipes/cnpj omitidos nesta fase)
    cep8 = _pad_left_zeros(_clean(row.get("prd-cep-pcnte", "")), 8)
    lograd3 = _pad_left_zeros(_clean(row.get("prd-lograd-pcnte", "")), 3)
    end30 = _pad_right(_clean(row.get("prd-end-pcnte", "")), 30)
    compl10 = _pad_right(_clean(row.get("prd-compl-pcnte", "")), 10)
    num5 = _pad_right(_clean(row.get("prd-num-pcnte", "")), 5)
    bairro30 = _pad_right(_clean(row.get("prd-bairro-pcnte", "")), 30)
    tel11 = _pad_right(_clean(row.get("prd-ddtel-pcnte", "")), 11)
    email40 = _pad_right(_clean(row.get("prd-email-pcnte", "")).lower(), 40)
    ine10 = _pad_right(_clean(row.get("prd-ine", "")), 10)
    filler2 = "  "

    return (
        f"{tipo}{cnes7}{comp6}{cns_prof15}{cbo6}{dt8}"
        f"{folha3}{linha2}"
        f"{pa10}{cns_pac15}{sx1}{ibge6}{cid4}{idade3}{qt6}{caten2}"
        f"{naut13}{org3}{nmpac30}"
        f"{dtnasc8}{raca2}{etnia4}{nac3}{srv3}{clf3}"
        f"{equipe_area_cnpj_26}{cep8}"
        f"{lograd3}{end30}{compl10}{num5}{bairro30}{tel11}"
        f"{email40}{ine10}{filler2}"
    )

def dataframe_to_txt_body(df: pd.DataFrame, competencia_yyyymm: str) -> str:
    """
    Gera corpo em layout posicional, com paginação:
      - 99 linhas por folha (01..99);
      - ao trocar de profissional (CNS) no meio da folha, força salto de folha.
    """
    lines = []
    folha = 1
    linha = 1
    prev_cns = None

    # Garantir ordem previsível (por CNS e data)
    sort_cols = [c for c in ["prd-cnsmed", "prd-dtaten"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(by=sort_cols, kind="stable")

    for _, row in df.iterrows():
        cns_atual = _pad_left_zeros(_clean(row.get("prd-cnsmed", "")), 15)

        if prev_cns is not None and cns_atual != prev_cns and linha != 1:
            folha += 1
            linha = 1

        lines.append(build_body_line(row, competencia_yyyymm, folha, linha))

        if linha == 99:
            folha += 1
            linha = 1
        else:
            linha += 1

        prev_cns = cns_atual

    # CRLF por compatibilidade com validadores/Windows
    return "\r\n".join(lines)

# ======================= Carregamento da planilha =======================
def _load_dataframe(upload_file) -> pd.DataFrame:
    """
    Lê XLS/XLSX/CSV preservando zeros à esquerda (dtype=str).
    Normaliza cabeçalhos para o formato comparável às REQUIRED_COLUMNS.
    """
    filename = upload_file.filename or ""
    ext = _ext(filename)
    if ext not in ALLOWED_EXT:
        abort(400, f"Extensão não suportada: {ext or 'desconhecida'}. Use XLS, XLSX ou CSV.")

    try:
        if ext == ".csv":
            df = pd.read_csv(upload_file, dtype=str, keep_default_na=False)
        else:
            # engine=None deixa o pandas escolher, dtype=str preserva zeros à esquerda
            df = pd.read_excel(upload_file, dtype=str, engine=None)
    except Exception as e:
        abort(400, f"Erro ao ler planilha: {e}")

    # Normaliza cabeçalhos
    norm_map = {c: _normalize_header(c) for c in df.columns}
    df.columns = [norm_map[c] for c in df.columns]

    # Adaptação: aceitar '_' no arquivo e comparar com '-' requerido
    required_norm = [_normalize_header(c) for c in REQUIRED_COLUMNS]

    # Quais colunas temos?
    have = set(df.columns)
    missing = [c for c in required_norm if c not in have]

    # Para a primeira versão do conversor, exigimos o conjunto mínimo do body.
    needed_now = {
        "prd-cnes", "prd-cnsmed", "prd-cbo", "prd-dtaten",
        "prd-pa", "prd-cnspac", "prd-sexo", "prd-ibge",
        "prd-cid", "prd-idade", "prd-qt", "prd-caten",
        "prd-org", "prd-nmpac", "prd-raca", "prd-nac",
        "prd-srv", "prd-clf", "prd-cep-pcnte", "prd-dtnasc",
        "prd-lograd-pcnte", "prd-end-pcnte", "prd-compl-pcnte",
        "prd-num-pcnte", "prd-bairro-pcnte", "prd-ddtel-pcnte",
        "prd-email-pcnte", "prd-ine",
    }
    needed_now = {_normalize_header(c) for c in needed_now}
    missing_now = [c for c in sorted(needed_now) if c not in have]
    if missing_now:
        # apresenta nomes "bonitos" ao usuário
        raise_missing = ", ".join(missing_now)
        abort(400, f"Planilha faltando colunas obrigatórias: {raise_missing}")

    return df

# ======================= Rotas =======================
@export_bp.get("/bpa")
def bpa_form():
    # Template está em export/templates/bpa.html
    return render_template("bpa.html")

@export_bp.get("/bpa/modelo")
def bpa_modelo():
    """
    Gera e envia um modelo XLSX em memória com as colunas esperadas.
    """
    cols = [_normalize_header(c) for c in REQUIRED_COLUMNS]
    exemplo = {c: "" for c in cols}
    # alguns exemplos úteis
    exemplo.update({
        "prd-cnes": "6097367",
        "prd-cnsmed": "123456789012345",
        "prd-cbo": "225125",
        "prd-dtaten": datetime.today().strftime("%d/%m/%Y"),
        "prd-pa": "0301010030",
        "prd-cnspac": "898001160134286",
        "prd-sexo": "F",
        "prd-ibge": "270430",
        "prd-cid": "F839",
        "prd-idade": "034",
        "prd-qt": "001",
        "prd-caten": "01",
        "prd-org": "BPA",
        "prd-nmpac": "PACIENTE EXEMPLO",
        "prd-raca": "03",
        "prd-nac": "010",
        "prd-srv": "201",
        "prd-clf": "020",
        "prd-cep-pcnte": "57000000",
        "prd-dtnasc": "01/01/1990",
        "prd-lograd-pcnte": "081",
        "prd-end-pcnte": "RUA EXEMPLO",
        "prd-compl-pcnte": "CASA",
        "prd-num-pcnte": "123",
        "prd-bairro-pcnte": "CENTRO",
        "prd-ddtel-pcnte": "82999999999",
        "prd-email-pcnte": "exemplo@dominio.com",
        "prd-ine": "0000000000",
    })
    df = pd.DataFrame([exemplo], columns=cols)

    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="BPA-i")
    bio.seek(0)

    return send_file(
        bio,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="modelo_bpai.xlsx",
    )

@export_bp.post("/bpa/convert")
def bpa_convert():
    """
    Recebe planilha, valida, gera cabeçalho + corpo posicional e retorna TXT.
    """
    if "file" not in request.files:
        abort(400, "Arquivo não enviado.")
    f = request.files["file"]
    if not f or f.filename == "":
        abort(400, "Arquivo inválido.")

    try:
        df = _load_dataframe(f)
    except Exception as e:
        # abort já envia 400, mas se veio outra Exception mostramos amigável:
        abort(400, f"Falha ao processar o arquivo: {e}")

    # Dados do cabeçalho
    cpf_form = request.form.get("cpf", "")
    competencia_form = request.form.get("competencia", "")  # MM/AAAA
    orgao_form = request.form.get("orgao", "")
    sigla_form = request.form.get("sigla", "")

    competencia_yyyymm = _competencia_to_yyyymm(competencia_form)

    num_registros = len(df)
    header_line = build_bpai_header(
        orgao=orgao_form,
        sigla=sigla_form,
        cpf_ou_cnpj=cpf_form,
        competencia_mm_aaaa=competencia_form,
        num_registros=num_registros,
    )

    # Corpo
    body_text = dataframe_to_txt_body(df, competencia_yyyymm)

    # Resultado final (com CRLF entre header e body)
    final_text = header_line + ("\r\n" if body_text else "") + body_text
    content_bytes = final_text.encode("utf-8")

    # Nome do arquivo de saída
    original = f.filename or "bpa"
    base = re.sub(r"\.[^.]+$", "", original)
    out_name = f"{base}.txt"

    return send_file(
        io.BytesIO(content_bytes),
        mimetype="text/plain; charset=utf-8",
        as_attachment=True,
        download_name=out_name
    )


# -----------------------------
# APAC – Visualização/Export
# -----------------------------
@export_bp.get("/apac")
def apac_view():
    """
    Tela de visualização/gestão das APACs (filtros + tabela).
    Passe ao template as variáveis usadas no HTML para evitar 500 por variáveis ausentes.
    """
    # Filtros vindos por GET (default vazio)
    nome = request.args.get("nome", "")
    cep = request.args.get("cep", "")
    competencia = request.args.get("competencia", "")
    status = request.args.get("status", "")
    status_entrega = request.args.get("status_entrega", "")
    nota_fiscal = request.args.get("nota_fiscal", "")
    competencia_nota = request.args.get("competencia_nota", "")
    fornecedor = request.args.get("fornecedor", "")
    local_entrega = request.args.get("local_entrega", "")

    # Mock de dados (substituir por SELECT no seu banco)
    apacs = []
    # Exemplo (remova depois):
    # apacs = [{
    #     "id": 1, "prontuario": "12345", "nome_paciente": "Fulano",
    #     "numero_apac": "0001/2025", "competencia": "08/2025",
    #     "procedimento": "Aparelho AUD", "codigo_procedimento": "1234567",
    #     "quantidade": 1, "status": "Pago", "status_entrega": "Entregue",
    #     "cnes": "6097367", "data_inicial": "2025-08-01", "data_final": "2025-11-01",
    #     "tipo_apac": "1", "nacionalidade": "10", "cns": "123456789012345",
    #     "data_nascimento": "2010-05-20", "nome_mae": "Ciclana",
    #     "sexo": "M", "raca": "Parda", "endereco": "Rua A", "numero": "100",
    #     "bairro": "Centro", "cep": "00000-000",
    #     "nota_fiscal": "NF-99", "data_nota_fiscal": "2025-08-15",
    #     "data_entrada_nf": "2025-08-16", "competencia_nota": "08/2025",
    #     "protocolo_nota": "ABC123", "obs_nota": "", "data_pedido": "2025-08-10",
    #     "fornecedor": "Fornecedor X", "obs_pedido": "",
    #     "data_entrega": "2025-08-20", "local_entrega": "UBS Central",
    #     "obs_entrega": "", "cbo_executante": "223605",
    #     "cns_executante": "987654321098765", "servico": "", "classificacao": ""
    # }]

    return render_template(
        "apacs_visualizar.html",
        apacs=apacs,
        nome_filtro=nome,
        cep_filtro=cep,
        competencia_filtro=competencia,
        status_filtro=status,
        status_entrega_filtro=status_entrega,
        nota_fiscal_filtro=nota_fiscal,
        competencia_nota_filtro=competencia_nota,
        fornecedor_filtro=fornecedor,
        local_entrega_filtro=local_entrega,
    )

@export_bp.get("/apac/excel")
def apacs_excel():
    """Exporta APACs filtradas para Excel (stub)."""
    # gere o arquivo e retorne com send_file. Por enquanto, devolve um XLSX vazio.
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        pd.DataFrame([]).to_excel(writer, index=False, sheet_name="APACs")
    output.seek(0)
    return send_file(output, as_attachment=True, download_name="apacs.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@export_bp.get("/apac/txt")
def apacs_txt():
    """Exporta APACs filtradas para TXT (stub)."""
    competencia = request.args.get("competencia", "")
    conteudo = f"ARQUIVO APAC - COMPETENCIA {competencia}\r\n".encode("utf-8")
    return send_file(io.BytesIO(conteudo), as_attachment=True,
                     download_name=f"apacs_{competencia or 'MMYYYY'}.txt",
                     mimetype="text/plain; charset=utf-8")

@export_bp.post("/apac/duplicar")
def apac_duplicar():
    # pegue id e duplique no banco
    # id_apac = request.form.get("id_apac")
    flash("APAC duplicada (preview).", "success")
    return redirect(url_for("export.apac_view"))

@export_bp.post("/apac/excluir")
def apac_excluir():
    # id_apac = request.form.get("id_apac")
    flash("APAC excluída (preview).", "info")
    return redirect(url_for("export.apac_view"))

@export_bp.get("/apac/<int:apac_id>/pdf")
def apac_pdf(apac_id: int):
    """Gera PDF da APAC (stub)."""
    pdf_bytes = b"%PDF-1.4\n% ... pdf fake ..."
    return send_file(io.BytesIO(pdf_bytes), as_attachment=True,
                     download_name=f"apac_{apac_id}.pdf", mimetype="application/pdf")

@export_bp.post("/apac/atualizar")
def apac_atualizar():
    # Aqui você leria request.form e faria UPDATE no banco.
    # Ex.: id_apac = request.form.get("id_apac")
    from flask import flash, redirect, url_for
    flash("APAC atualizada (preview).", "success")
    return redirect(url_for("export.apac_view"))
