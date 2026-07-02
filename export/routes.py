# -*- coding: utf-8 -*-
"""
Rotas do módulo Export ➜ BPA-i

- GET  /export/bpa
- POST /export/bpa/convert
- POST /export/bpa/auditoria
- POST /export/bpa/download
- GET  /export/bpa/modelo
"""

import io
import os
import re
import math
import uuid
import pickle
import tempfile
import unicodedata
from datetime import date, datetime

import pandas as pd
from flask import (
    abort, flash, redirect, render_template, request,
    send_file, url_for, session
)

from . import export_bp
from .auditoria import auditar_dataframe_bpa
from .apac import *
from .apac_cadastro import *
from .apac_exporta import *


from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)









# ============== Config / Colunas esperadas ==============
REQUIRED_COLUMNS = [
    "prd-ident", "prd-cnes", "prd-cnsmed", "prd-cbo", "prd-dtaten", "prd-pa",
    "prd-cnspac", "prd-cpfpac", "prd-sexo", "prd-ibge", "prd-cid", "prd-idade", "prd-qt",
    "prd-caten", "prd-naut", "prd-org", "prd-nmpac", "prd-raca", "prd-etnia",
    "prd-nac", "prd-srv", "prd-clf", "prd-equipe-seq", "prd-equipe-area",
    "prd-cnpj", "prd-cep-pcnte", "prd-lograd-pcnte", "prd-end-pcnte",
    "prd-compl-pcnte", "prd-num-pcnte", "prd-bairro-pcnte", "prd-ddtel-pcnte",
    "prd-email-pcnte", "prd-ine", "prd-dtnasc",
]

ALLOWED_EXT = {".xls", ".xlsx", ".csv"}


# ======================= Helpers genéricos =======================
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


def _txt_safe(s: str, upper: bool = False) -> str:
    s = _clean(s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))

    if upper:
        s = s.upper()

    s = re.sub(r"[\r\n\t]+", " ", s)
    s = re.sub(r"[^A-Za-z0-9 @._\-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    return s


def _upper(s: str) -> str:
    return (s or "").strip().upper()


def _competencia_to_yyyymm(competencia_mm_aaaa: str) -> str:
    s = _clean(competencia_mm_aaaa)
    m = re.match(r"^(\d{2})[\/-](\d{4})$", s)
    if not m:
        return "000000"
    mm, aaaa = m.group(1), m.group(2)
    return f"{aaaa}{mm}"


def _parse_to_date(x):
    if _is_nan_like(x):
        return None

    if isinstance(x, date) and not isinstance(x, datetime):
        return x

    if isinstance(x, datetime):
        return x.date()

    s = _clean(x)

    m = re.match(r"^\s*(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?\s*$", s)
    if m:
        yyyy, mm, dd = m.group(1), m.group(2), m.group(3)
        try:
            return date(int(yyyy), int(mm), int(dd))
        except Exception:
            return None

    m = re.match(r"^\s*(\d{2})[\/-](\d{2})[\/-](\d{4})\s*$", s)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        try:
            return date(int(yyyy), int(mm), int(dd))
        except Exception:
            return None

    d = _digits(s)
    if len(d) == 8:
        if int(d[:4]) >= 1900:
            yyyy, mm, dd = d[:4], d[4:6], d[6:8]
        elif int(d[4:]) >= 1900:
            dd, mm, yyyy = d[:2], d[2:4], d[4:]
        else:
            return None

        try:
            return date(int(yyyy), int(mm), int(dd))
        except Exception:
            return None

    try:
        ts = pd.to_datetime(s, dayfirst=True, errors="raise")
        if pd.isna(ts):
            return None
        return ts.date()
    except Exception:
        return None


def _date_to_yyyymmdd(x) -> str:
    dt = _parse_to_date(x)
    return dt.strftime("%Y%m%d") if dt else ""


def _normalize_header(col: str) -> str:
    col = (col or "").strip().lower()
    col = col.replace("_", "-")
    col = re.sub(r"[\s]+", " ", col)
    col = re.sub(r"[-]{2,}", "-", col)
    return col


def _ext(filename: str) -> str:
    m = re.search(r"\.[^.]+$", filename or "", flags=re.I)
    return (m.group(0) if m else "").lower()


# ======================= Cabeçalho BPA-i =======================
def build_bpai_header(orgao: str, sigla: str, cpf_ou_cnpj: str, competencia_mm_aaaa: str, num_registros: int) -> str:
    prefixo = "01#BPA#"
    yyyymm = _competencia_to_yyyymm(competencia_mm_aaaa)
    nregs6 = str(max(0, int(num_registros))).zfill(6)
    folhas = max(1, math.ceil(num_registros / 99)) if num_registros > 0 else 0
    folhas6 = str(folhas).zfill(6)
    controle = "1111"
    orgao30 = _pad_right(_upper(_clean(orgao)), 30)
    sigla6 = _pad_right(_upper(_clean(sigla)), 6)
    cgc_cpf14 = _pad_left_zeros(cpf_ou_cnpj, 14)
    frase_estatica = "SECRETARIAS DE SAUDE MUNICIPAL DA CIDADE"
    indicador_municipio = "M"
    versao10 = _pad_right("1.0.0", 10)
    fim = "LF"

    return (
        prefixo + yyyymm + nregs6 + folhas6 + controle +
        orgao30 + sigla6 + cgc_cpf14 + frase_estatica +
        indicador_municipio + versao10 + fim
    )


# ======================= Corpo BPA-i =======================
def resolver_cns_paciente(row: pd.Series) -> str:
    cns_raw = _digits(_clean(row.get("prd-cnspac", "")))
    if cns_raw:
        return cns_raw.zfill(15)[:15]
    return " " * 15


def resolver_cpf_paciente_final(row: pd.Series) -> str:
    cpf_raw = _digits(_clean(row.get("prd-cpfpac", "")))[:11]
    if cpf_raw:
        return cpf_raw.ljust(11, " ")
    return " " * 11


def build_body_line(row: pd.Series, competencia_yyyymm: str, folha: int, linha: int) -> str:
    tipo = "03"
    cnes7 = _pad_left_zeros(_clean(row.get("prd-cnes", "")), 7)
    comp6 = competencia_yyyymm[:6] if competencia_yyyymm else "000000"
    cns_prof15 = _pad_left_zeros(_clean(row.get("prd-cnsmed", "")), 15)
    cbo6 = _pad_left_zeros(_clean(row.get("prd-cbo", "")), 6)
    dt8 = _date_to_yyyymmdd(row.get("prd-dtaten", "")) or "00000000"

    folha3 = str(int(folha)).zfill(3)
    linha2 = str(int(linha)).zfill(2)
    pa10 = _pad_left_zeros(_clean(row.get("prd-pa", "")), 10)

    cns_pac15 = resolver_cns_paciente(row)
    cpf_pac11 = resolver_cpf_paciente_final(row)

    sx_val = _upper(_clean(row.get("prd-sexo", "")))
    sx1 = sx_val[:1] if sx_val else " "
    ibge6 = _pad_left_zeros(_clean(row.get("prd-ibge", "")), 6)
    cid4 = _pad_right(_upper(_clean(row.get("prd-cid", ""))), 4)
    idade3 = _pad_left_zeros(_clean(row.get("prd-idade", "")), 3)
    qt6 = _pad_left_zeros(_clean(row.get("prd-qt", "")), 6)
    caten2 = _pad_left_zeros(_clean(row.get("prd-caten", "")), 2)
    naut13 = " " * 13

    org_val = _txt_safe(row.get("prd-org", ""), upper=True) or "BPA"
    org3 = _pad_right(org_val, 3)[:3]
    nmpac30 = _pad_right(_txt_safe(row.get("prd-nmpac", ""), upper=True), 30)
    dtnasc8 = _date_to_yyyymmdd(row.get("prd-dtnasc", "")) or "00000000"

    raca2 = _pad_left_zeros(_clean(row.get("prd-raca", "")), 2)
    etnia4 = " " * 4
    nac3 = _pad_left_zeros(_clean(row.get("prd-nac", "")), 3)

    srv3 = _pad_left_zeros(_clean(row.get("prd-srv", "")), 3)
    clf3 = _pad_left_zeros(_clean(row.get("prd-clf", "")), 3)
    equipe_area_cnpj_26 = " " * 26
    cep8 = _pad_left_zeros(_clean(row.get("prd-cep-pcnte", "")), 8)
    lograd3 = _pad_left_zeros(_clean(row.get("prd-lograd-pcnte", "")), 3)
    end30 = _pad_right(_txt_safe(row.get("prd-end-pcnte", ""), upper=True), 30)
    compl10 = _pad_right(_txt_safe(row.get("prd-compl-pcnte", ""), upper=True), 10)
    num5 = _pad_right(_txt_safe(row.get("prd-num-pcnte", ""), upper=True), 5)
    bairro30 = _pad_right(_txt_safe(row.get("prd-bairro-pcnte", ""), upper=True), 30)
    tel11 = _pad_right(_clean(row.get("prd-ddtel-pcnte", "")), 11)
    email40 = _pad_right(_txt_safe(row.get("prd-email-pcnte", ""), upper=False).lower(), 40)
    ine10 = _pad_right(_clean(row.get("prd-ine", "")), 10)

    return (
        f"{tipo}{cnes7}{comp6}{cns_prof15}{cbo6}{dt8}"
        f"{folha3}{linha2}"
        f"{pa10}{cns_pac15}{sx1}{ibge6}{cid4}{idade3}{qt6}{caten2}"
        f"{naut13}{org3}{nmpac30}"
        f"{dtnasc8}{raca2}{etnia4}{nac3}{srv3}{clf3}"
        f"{equipe_area_cnpj_26}{cep8}"
        f"{lograd3}{end30}{compl10}{num5}{bairro30}{tel11}"
        f"{email40}{ine10}{cpf_pac11}"
    )


def dataframe_to_txt_body(df: pd.DataFrame, competencia_yyyymm: str) -> str:
    lines = []
    folha = 1
    linha = 1
    prev_cns = None

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

    return "\r\n".join(lines)


# ======================= Carregamento da planilha =======================
def _load_dataframe(upload_file) -> pd.DataFrame:
    filename = upload_file.filename or ""
    ext = _ext(filename)

    if ext not in ALLOWED_EXT:
        abort(400, f"Extensão não suportada: {ext or 'desconhecida'}. Use XLS, XLSX ou CSV.")

    try:
        if ext == ".csv":
            df = pd.read_csv(upload_file, dtype=str, keep_default_na=False)
        else:
            df = pd.read_excel(upload_file, dtype=str, engine=None)
    except Exception as e:
        abort(400, f"Erro ao ler planilha: {e}")

    norm_map = {c: _normalize_header(c) for c in df.columns}
    df.columns = [norm_map[c] for c in df.columns]

    needed_now = {
        "prd-cnes", "prd-cnsmed", "prd-cbo", "prd-dtaten",
        "prd-pa", "prd-cnspac", "prd-cpfpac", "prd-sexo", "prd-ibge",
        "prd-cid", "prd-idade", "prd-qt", "prd-caten",
        "prd-org", "prd-nmpac", "prd-raca", "prd-nac",
        "prd-srv", "prd-clf", "prd-cep-pcnte", "prd-dtnasc",
        "prd-lograd-pcnte", "prd-end-pcnte", "prd-compl-pcnte",
        "prd-num-pcnte", "prd-bairro-pcnte", "prd-ddtel-pcnte",
        "prd-email-pcnte", "prd-ine",
    }
    needed_now = {_normalize_header(c) for c in needed_now}

    have = set(df.columns)
    missing_now = [c for c in sorted(needed_now) if c not in have]

    if missing_now:
        abort(400, f"Planilha faltando colunas obrigatórias: {', '.join(missing_now)}")

    return df


# ============================================================
# BPA-I · CACHE TEMPORÁRIO
# ============================================================
def _bpa_cache_dir():
    path = os.path.join(tempfile.gettempdir(), "sgd_bpai_cache")
    os.makedirs(path, exist_ok=True)
    return path


def _bpa_cache_path(token):
    return os.path.join(_bpa_cache_dir(), f"{token}.pkl")


def _salvar_bpa_cache(df, form_data, filename):
    token = uuid.uuid4().hex

    payload = {
        "df": df,
        "form_data": form_data,
        "filename": filename,
        "excluir_idxs": [],
        "auditoria": None
    }

    with open(_bpa_cache_path(token), "wb") as f:
        pickle.dump(payload, f)

    session["bpa_token"] = token

    return token, payload


def _carregar_bpa_cache(token=None):
    token = token or session.get("bpa_token")

    if not token:
        abort(400, "Auditoria não encontrada. Envie a planilha novamente.")

    path = _bpa_cache_path(token)

    if not os.path.exists(path):
        abort(400, "Auditoria expirada. Envie a planilha novamente.")

    with open(path, "rb") as f:
        payload = pickle.load(f)

    return token, payload


def _salvar_payload_bpa(token, payload):
    with open(_bpa_cache_path(token), "wb") as f:
        pickle.dump(payload, f)


def _int_list(values):
    out = []

    for v in values or []:
        try:
            out.append(int(v))
        except Exception:
            pass

    return out


def _gerar_txt_bpa_do_payload(payload):
    df = payload["df"]
    excluir_idxs = set(payload.get("excluir_idxs", []))

    df_final = df.drop(index=list(excluir_idxs), errors="ignore").copy()

    form_data = payload["form_data"]
    competencia_form = form_data.get("competencia", "")
    competencia_yyyymm = _competencia_to_yyyymm(competencia_form)

    header_line = build_bpai_header(
        orgao=form_data.get("orgao", ""),
        sigla=form_data.get("sigla", ""),
        cpf_ou_cnpj=form_data.get("cpf", ""),
        competencia_mm_aaaa=competencia_form,
        num_registros=len(df_final),
    )

    body_text = dataframe_to_txt_body(df_final, competencia_yyyymm)
    final_text = header_line + ("\r\n" if body_text else "") + body_text

    original = payload.get("filename") or "bpa"
    base = re.sub(r"\.[^.]+$", "", original)
    out_name = f"{base}.txt"

    return final_text, out_name


def _render_bpa_com_auditoria(
    payload,
    token,
    filtro_tipo_erro="TODOS",
    pagina_erros=1,
    erros_por_pagina=25,
    gerar_preview_txt=True,
):
    auditoria = payload.get("auditoria")

    if not auditoria:
        auditoria = auditar_dataframe_bpa(
            payload["df"],
            excluir_idxs=payload.get("excluir_idxs", []),
            filtro_tipo_erro=filtro_tipo_erro,
            pagina_erros=pagina_erros,
            erros_por_pagina=erros_por_pagina,
            validar_cnes=False,
        )

        payload["auditoria"] = auditoria
        _salvar_payload_bpa(token, payload)

    txt_gerado = True
    txt_nome = None
    txt_preview = None
    txt_tamanho_bytes = None

    if gerar_preview_txt:
        final_text, txt_nome = _gerar_txt_bpa_do_payload(payload)
        txt_preview = final_text[:3000]
        txt_tamanho_bytes = len(final_text.encode("latin-1", errors="replace"))

    return render_template(
        "bpa.html",
        auditoria=auditoria,
        form_data=payload["form_data"],
        bpa_token=token,
        filtro_tipo_erro=filtro_tipo_erro or "TODOS",
        pagina_erros=int(pagina_erros or 1),
        erros_por_pagina=int(erros_por_pagina or 25),
        txt_gerado=txt_gerado,
        txt_nome=txt_nome,
        txt_preview=txt_preview,
        txt_tamanho_bytes=txt_tamanho_bytes,
    )





# ======================= Rotas BPA-i =======================
@export_bp.get("/bpa")
def bpa_form():
    return render_template("bpa.html")


@export_bp.get("/bpa/modelo")
def bpa_modelo():
    cols = [_normalize_header(c) for c in REQUIRED_COLUMNS]
    exemplo = {c: "" for c in cols}
    exemplo.update({
        "prd-cnes": "6097367",
        "prd-cnsmed": "123456789012345",
        "prd-cbo": "225125",
        "prd-dtaten": datetime.today().strftime("%d/%m/%Y"),
        "prd-pa": "0301010030",
        "prd-cnspac": "898001160134286",
        "prd-cpfpac": "12345678901",
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
    if "file" not in request.files:
        abort(400, "Arquivo não enviado.")

    f = request.files["file"]

    if not f or f.filename == "":
        abort(400, "Arquivo inválido.")

    try:
        df = _load_dataframe(f)
    except Exception as e:
        abort(400, f"Falha ao processar o arquivo: {e}")

    form_data = {
        "cpf": request.form.get("cpf", ""),
        "competencia": request.form.get("competencia", ""),
        "orgao": request.form.get("orgao", ""),
        "sigla": request.form.get("sigla", ""),
    }

    # --------------------------------------------------
    # Salva o BPA temporariamente
    # --------------------------------------------------
    token, payload = _salvar_bpa_cache(
        df,
        form_data,
        f.filename or "bpa.xlsx"
    )



    # --------------------------------------------------
    # Gera auditoria inicial
    # --------------------------------------------------
    payload["auditoria"] = auditar_dataframe_bpa(
        df,
        validar_cnes=False,
        pagina_erros=1,
        erros_por_pagina=999999
    )

    # --------------------------------------------------
    # Atualiza cache com auditoria pronta
    # --------------------------------------------------
    _salvar_payload_bpa(token, payload)

    # --------------------------------------------------
    # Renderiza a tela
    # --------------------------------------------------
    return _render_bpa_com_auditoria(
        payload=payload,
        token=token,
        filtro_tipo_erro="TODOS",
        pagina_erros=1,
        erros_por_pagina=25,
    )








@export_bp.post("/bpa/validar-cnes")
def bpa_validar_cnes():
    token = request.form.get("bpa_token") or session.get("bpa_token")
    token, payload = _carregar_bpa_cache(token)

    auditoria = auditar_dataframe_bpa(
        payload["df"],
        excluir_idxs=payload.get("excluir_idxs", []),
        validar_cnes=True,
        pagina_erros=1,
        erros_por_pagina=999999,
    )

    payload["auditoria"] = auditoria
    _salvar_payload_bpa(token, payload)

    return _render_bpa_com_auditoria(
        payload=payload,
        token=token,
        filtro_tipo_erro="TODOS",
        pagina_erros=1,
        erros_por_pagina=15,
    )







@export_bp.post("/bpa/auditoria")
def bpa_auditoria_acao():
    """
    Ações da auditoria BPA-I.

    Corrige:
    - auditoria_atual agora existe de verdade.
    - CNES fica ativado.
    - Exclusão individual, selecionados e todos com erro funcionam.
    - Adiciona opção futura: excluir_todos_filtrados.
    """

    token = request.form.get("bpa_token") or session.get("bpa_token")
    token, payload = _carregar_bpa_cache(token)

    acao = request.form.get("acao", "filtrar")

    filtro_tipo_erro = request.form.get("filtro_tipo_erro") or "TODOS"
    pagina_erros = int(request.form.get("pagina_erros") or 1)
    erros_por_pagina = int(request.form.get("erros_por_pagina") or 25)

    excluir_atual = set(payload.get("excluir_idxs", []))

    # Auditoria atual ANTES da ação.
    # Usada principalmente para:
    # - excluir todos com erro
    # - excluir todos filtrados
    auditoria_atual = auditar_dataframe_bpa(
        payload["df"],
        excluir_idxs=list(excluir_atual),
        filtro_tipo_erro=filtro_tipo_erro,
        pagina_erros=pagina_erros,
        erros_por_pagina=erros_por_pagina,
        validar_cnes=True,
    )

    if acao == "excluir_individual":
        idx = request.form.get("idx")

        if idx and str(idx).isdigit():
            excluir_atual.add(int(idx))

        pagina_erros = 1

    elif acao == "excluir_selecionados":
        selecionados = _int_list(request.form.getlist("selecionados"))

        if selecionados:
            excluir_atual.update(selecionados)

        pagina_erros = 1

    elif acao == "excluir_todos_erros":
        # Exclui todas as linhas com erro bloqueante.
        # Avisos CNES não entram aqui se gravidade = aviso.
        idxs_erro = auditoria_atual.get("exportacao", {}).get("idxs_com_erro", [])
        excluir_atual.update(idxs_erro)

        pagina_erros = 1

    elif acao == "excluir_todos_filtrados":
        # Exclui todos os itens do filtro atual.
        # Exemplo: filtro DUPLICIDADE -> exclui todas as duplicidades.
        for problema in auditoria_atual.get("problemas_filtrados", []):
            idx = problema.get("idx")

            if isinstance(idx, int) and idx >= 0:
                excluir_atual.add(idx)

        pagina_erros = 1

    elif acao == "limpar_exclusoes":
        excluir_atual = set()
        pagina_erros = 1

    elif acao == "filtrar":
        pagina_erros = 1

    elif acao == "paginar":
        # Mantém página enviada pelo formulário.
        pass

    payload["excluir_idxs"] = sorted(excluir_atual)

    # Como as exclusões mudaram, invalida auditoria cacheada se existir.
    payload["auditoria"] = None

    _salvar_payload_bpa(token, payload)

    return _render_bpa_com_auditoria(
        payload=payload,
        token=token,
        filtro_tipo_erro=filtro_tipo_erro,
        pagina_erros=pagina_erros,
        erros_por_pagina=erros_por_pagina,
    )





@export_bp.post("/bpa/download")
def bpa_download():
    token = request.form.get("bpa_token") or session.get("bpa_token")
    token, payload = _carregar_bpa_cache(token)

    auditoria = payload.get("auditoria")

    if auditoria and auditoria.get("resumo", {}).get("tem_problemas"):
        flash(
            f"Atenção: foram encontradas "
            f"{auditoria['resumo']['total_problemas']} inconsistências. "
            f"O TXT foi gerado mesmo assim.",
            "warning"
        )

    final_text, out_name = _gerar_txt_bpa_do_payload(payload)

    return send_file(
        io.BytesIO(final_text.encode("latin-1", errors="replace")),
        mimetype="text/plain; charset=latin-1",
        as_attachment=True,
        download_name=out_name
    )




@export_bp.post("/bpa/resumo-pdf")
def bpa_resumo_pdf():
    token = request.form.get("bpa_token") or session.get("bpa_token")
    token, payload = _carregar_bpa_cache(token)

    auditoria = payload.get("auditoria")

    if not auditoria:
        auditoria = auditar_dataframe_bpa(
            payload["df"],
            excluir_idxs=payload.get("excluir_idxs", []),
            validar_cnes=False,
            pagina_erros=1,
            erros_por_pagina=999999,
        )
        payload["auditoria"] = auditoria
        _salvar_payload_bpa(token, payload)

    pdf_bytes = _gerar_pdf_resumo_bpa(payload, auditoria)

    original = payload.get("filename") or "bpa"
    base = re.sub(r"\.[^.]+$", "", original)

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"resumo_auditoria_{base}.pdf"
    )








def _gerar_pdf_resumo_bpa(payload, auditoria):
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=1.2 * cm,
        leftMargin=1.2 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
    )

    styles = getSampleStyleSheet()
    story = []

    resumo = auditoria.get("resumo", {})
    rankings = auditoria.get("rankings", {})
    problemas = auditoria.get("problemas", [])
    baixa = auditoria.get("baixa_frequencia", {})
    cnesp = auditoria.get("cnes_profissionais", {})

    story.append(Paragraph("Resumo da Auditoria BPA-i", styles["Title"]))
    story.append(Paragraph(f"Arquivo: {payload.get('filename', '-')}", styles["Normal"]))
    story.append(Paragraph(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles["Normal"]))
    story.append(Spacer(1, 12))

    dados_resumo = [
        ["Indicador", "Quantidade"],
        ["Linhas originais", resumo.get("total_linhas_original", 0)],
        ["Linhas consideradas", resumo.get("total_linhas", 0)],
        ["Linhas excluídas", resumo.get("linhas_excluidas", 0)],
        ["Linhas válidas", resumo.get("validas", 0)],
        ["Problemas", resumo.get("total_problemas", 0)],
        ["Erros", resumo.get("total_erros", 0)],
        ["Avisos", resumo.get("total_avisos", 0)],
        ["Duplicidades", resumo.get("duplicidades", 0)],
        ["Inconsistências", resumo.get("inconsistencias", 0)],
        ["Pacientes únicos", resumo.get("pacientes_unicos", 0)],
        ["Profissionais únicos", resumo.get("profissionais_unicos", 0)],
        ["Procedimentos diferentes", resumo.get("procedimentos_diferentes", 0)],
        ["CIDs diferentes", resumo.get("cids_diferentes", 0)],
    ]

    story.append(_pdf_table(dados_resumo, [9 * cm, 5 * cm]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Top procedimentos", styles["Heading2"]))
    story.append(_pdf_table(
        [["Procedimento", "Quantidade"]] +
        [[x.get("chave", "-"), x.get("quantidade", 0)] for x in rankings.get("procedimentos", [])[:20]],
        [9 * cm, 4 * cm]
    ))

    story.append(Spacer(1, 12))
    story.append(Paragraph("Top CIDs", styles["Heading2"]))
    story.append(_pdf_table(
        [["CID", "Quantidade"]] +
        [[x.get("chave", "-"), x.get("quantidade", 0)] for x in rankings.get("cids", [])[:20]],
        [9 * cm, 4 * cm]
    ))

    story.append(PageBreak())

    story.append(Paragraph("Problemas encontrados", styles["Heading2"]))
    dados_problemas = [["Linha", "Tipo", "Paciente", "Procedimento", "CID", "Serviço/Class.", "Mensagem"]]

    for p in problemas[:150]:
        dados_problemas.append([
            p.get("linha_excel", "-"),
            p.get("tipo", "-"),
            p.get("paciente", "-")[:35],
            p.get("procedimento", "-"),
            p.get("cid", "-"),
            f"{p.get('servico', '-')}/{p.get('classificacao', '-')}",
            p.get("mensagem", "-")[:80],
        ])

    story.append(_pdf_table(
        dados_problemas,
        [1.5 * cm, 5 * cm, 6 * cm, 3 * cm, 2 * cm, 3 * cm, 10 * cm],
        font_size=7
    ))

    story.append(PageBreak())

    story.append(Paragraph("Validação CNES dos profissionais", styles["Heading2"]))

    if cnesp and cnesp.get("ativo"):
        dados_cnes = [["CNS", "CNES", "CBO", "Linhas", "Status", "Mensagem"]]

        for item in cnesp.get("itens", [])[:120]:
            dados_cnes.append([
                item.get("cns", "-"),
                item.get("cnes", "-"),
                item.get("cbo", "-"),
                item.get("qtd_linhas", 0),
                item.get("status", "-"),
                item.get("mensagem", "-")[:90],
            ])

        story.append(_pdf_table(
            dados_cnes,
            [4 * cm, 2.5 * cm, 2.5 * cm, 2 * cm, 3 * cm, 13 * cm],
            font_size=7
        ))
    else:
        story.append(Paragraph("Validação CNES não executada.", styles["Normal"]))

    story.append(Spacer(1, 12))
    story.append(Paragraph("Baixa frequência estimada", styles["Heading2"]))

    dados_freq = [["Paciente", "Dias diferentes", "Meta", "Déficit", "CBOs"]]

    for item in baixa.get("pacientes_abaixo", [])[:120]:
        dados_freq.append([
            item.get("paciente", "-")[:45],
            item.get("dias_diferentes", 0),
            item.get("meta_minima", 4),
            item.get("deficit", 0),
            item.get("cbos_txt", "-")[:80],
        ])

    story.append(_pdf_table(
        dados_freq,
        [8 * cm, 3 * cm, 2 * cm, 2 * cm, 12 * cm],
        font_size=7
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


def _pdf_table(data, col_widths=None, font_size=8):
    table = Table(data, colWidths=col_widths, repeatRows=1)

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5edf7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111827")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    return table

