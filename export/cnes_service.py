# -*- coding: utf-8 -*-
"""
CNES Service · BPA-I

Valida profissional no CNES usando os endpoints JSON do próprio site:
1) /services/profissionais?cns=<CNS>
2) /services/profissionais/<ID>

Dependência:
    pip install requests
"""

import json
import re
from datetime import datetime, timedelta

try:
    import requests
except Exception:
    requests = None

try:
    from db import conectar_db
except Exception:
    conectar_db = None


CNES_BASE = "https://cnes.datasus.gov.br"
SERVICES_BASE = f"{CNES_BASE}/services"
CACHE_DIAS = 30


def digits(v):
    return re.sub(r"\D+", "", str(v or ""))


def clean(v):
    return str(v or "").strip()


def norm_cns(v):
    d = digits(v)
    return d.zfill(15)[-15:] if d else ""


def norm_cnes(v):
    d = digits(v)
    return d.zfill(7)[-7:] if d else ""


def norm_cbo(v):
    d = digits(v)
    return d.zfill(6)[-6:] if d else ""


def row_to_dict(row, cols=None):
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    try:
        return dict(row)
    except Exception:
        pass
    if cols:
        return dict(zip(cols, row))
    return {}


# ============================================================
# CACHE POSTGRES
# ============================================================

def garantir_tabela_cache():
    if conectar_db is None:
        return

    conn = conectar_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cnes_profissionais_cache (
            cns TEXT PRIMARY KEY,
            nome TEXT,
            dados_json TEXT,
            html TEXT,
            consultado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_cnes_cache_data
        ON cnes_profissionais_cache (consultado_em)
    """)

    conn.commit()
    cur.close()
    conn.close()


def buscar_cache(cns):
    if conectar_db is None:
        return None

    garantir_tabela_cache()

    conn = conectar_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT cns, nome, dados_json, consultado_em
        FROM cnes_profissionais_cache
        WHERE cns = %s
    """, (cns,))

    row = cur.fetchone()
    cols = [d[0] for d in cur.description] if cur.description else []

    cur.close()
    conn.close()

    item = row_to_dict(row, cols)
    if not item:
        return None

    consultado = item.get("consultado_em")

    if isinstance(consultado, str):
        try:
            consultado = datetime.fromisoformat(consultado)
        except Exception:
            consultado = None

    if consultado and datetime.now() - consultado > timedelta(days=CACHE_DIAS):
        return None

    try:
        dados = json.loads(item.get("dados_json") or "{}")
        dados["fonte"] = "cache"
        return dados
    except Exception:
        return None


def salvar_cache(cns, dados, html=""):
    if conectar_db is None:
        return

    garantir_tabela_cache()

    nome = dados.get("nome", "")
    dados_json = json.dumps(dados, ensure_ascii=False)

    conn = conectar_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO cnes_profissionais_cache (cns, nome, dados_json, html, consultado_em)
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (cns)
        DO UPDATE SET
            nome = EXCLUDED.nome,
            dados_json = EXCLUDED.dados_json,
            html = EXCLUDED.html,
            consultado_em = CURRENT_TIMESTAMP
    """, (cns, nome, dados_json, html))

    conn.commit()
    cur.close()
    conn.close()


# ============================================================
# CNES JSON
# ============================================================

def get_json_cnes(path):
    if requests is None:
        raise RuntimeError("Biblioteca requests não instalada. Rode: pip install requests")

    url = path if str(path).startswith("http") else f"{SERVICES_BASE}/{str(path).lstrip('/')}"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Referer": f"{CNES_BASE}/pages/profissionais/consulta.jsp",
    }

    resp = requests.get(url, headers=headers, timeout=25)
    resp.raise_for_status()

    return resp.json()


def buscar_profissional_por_cns(cns):
    cns = norm_cns(cns)
    if not cns:
        return None

    data = get_json_cnes(f"profissionais?cns={cns}")

    if isinstance(data, list):
        return data[0] if data else None

    if isinstance(data, dict):
        if data.get("content") and isinstance(data["content"], list):
            return data["content"][0] if data["content"] else None
        return data

    return None


def buscar_vinculos_ativos_por_id(prof_id):
    if not prof_id:
        return None

    return get_json_cnes(f"profissionais/{prof_id}")


def normalizar_vinculos_json(dto, cns_fallback=""):
    if not dto:
        return {
            "ok": False,
            "cns": norm_cns(cns_fallback),
            "nome": "",
            "lotacoes": [],
            "erro": "DTO vazio retornado pelo CNES.",
            "fonte": "cnes-json",
        }

    lotacoes = []

    for vinc in dto.get("vinculos", []) or []:
        cbo = norm_cbo(vinc.get("cbo"))
        cnes = norm_cnes(vinc.get("cnes"))

        if not cnes:
            continue

        lotacoes.append({
            "ibge": clean(vinc.get("coMun") or vinc.get("coMunicipio")),
            "uf": clean(vinc.get("estado") or vinc.get("sigla")),
            "municipio": clean(vinc.get("noMun") or vinc.get("noMunicipio")),
            "cbo": cbo,
            "cbo_descricao": clean(vinc.get("dsCbo")),
            "cnes": cnes,
            "cnpj": digits(vinc.get("cnpj")),
            "estabelecimento": clean(vinc.get("noFant")),
            "natureza": f"{clean(vinc.get('natJur'))} - {clean(vinc.get('dsNatJur'))}".strip(" -"),
            "gestao": clean(vinc.get("tpGestao")),
            "sus": "SIM" if clean(vinc.get("tpSusNaoSus")).upper() == "S" else "NÃO",
            "situacao": "ATIVO",
            "vinculacao": clean(vinc.get("vinculacao")),
            "vinculo": clean(vinc.get("vinculo")),
            "sub_vinculo": clean(vinc.get("subVinculo")),
            "ch_outros": vinc.get("chOutros", 0),
            "ch_amb": vinc.get("chAmb", 0),
            "ch_hosp": vinc.get("chHosp", 0),
        })

    return {
        "ok": True,
        "cns": norm_cns(dto.get("cns") or cns_fallback),
        "nome": clean(dto.get("nome")),
        "sexo": clean(dto.get("sexo")),
        "lotacoes": lotacoes,
        "erro": "",
        "fonte": "cnes-json",
        "consultado_em": datetime.now().isoformat(timespec="seconds"),
    }


def consultar_profissional_cnes(cns, usar_cache=True):
    cns = norm_cns(cns)

    if not cns:
        return {
            "ok": False,
            "cns": "",
            "nome": "",
            "lotacoes": [],
            "erro": "CNS profissional vazio ou inválido.",
            "fonte": "local",
        }

    if usar_cache:
        cached = buscar_cache(cns)
        if cached:
            return cached

    try:
        prof = buscar_profissional_por_cns(cns)

        if not prof:
            dados = {
                "ok": False,
                "cns": cns,
                "nome": "",
                "lotacoes": [],
                "erro": "Profissional não encontrado pelo CNS no CNES.",
                "fonte": "cnes-json",
            }
            salvar_cache(cns, dados)
            return dados

        prof_id = (
            prof.get("id")
            or prof.get("coProfissionalSus")
            or prof.get("coSeqProfissional")
            or prof.get("codigo")
            or prof.get("coSeq")
        )

        if not prof_id:
            dados = {
                "ok": False,
                "cns": cns,
                "nome": clean(prof.get("nome")),
                "lotacoes": [],
                "erro": "Profissional encontrado, mas sem ID interno para consultar vínculos.",
                "fonte": "cnes-json",
                "profissional_raw": prof,
            }
            salvar_cache(cns, dados)
            return dados

        dto = buscar_vinculos_ativos_por_id(prof_id)
        dados = normalizar_vinculos_json(dto, cns_fallback=cns)

        if not dados.get("nome"):
            dados["nome"] = clean(prof.get("nome"))

        dados["prof_id"] = prof_id
        salvar_cache(cns, dados)

        return dados

    except Exception as e:
        return {
            "ok": False,
            "cns": cns,
            "nome": "",
            "lotacoes": [],
            "erro": str(e),
            "fonte": "erro",
        }


# ============================================================
# VALIDAÇÃO
# ============================================================

def validar_profissional_no_cnes(cns_prof, cnes_estabelecimento, cbo=None, usar_cache=True):
    cns = norm_cns(cns_prof)
    cnes = norm_cnes(cnes_estabelecimento)
    cbo = norm_cbo(cbo)

    dados = consultar_profissional_cnes(cns, usar_cache=usar_cache)

    if not dados.get("ok"):
        return {
            "ok": False,
            "tipo": "CNES_CONSULTA_FALHOU",
            "mensagem": f"Não foi possível validar o profissional CNS {cns} no CNES.",
            "detalhe": dados.get("erro", ""),
            "dados": dados,
        }

    for lot in dados.get("lotacoes", []):
        lot_cnes = norm_cnes(lot.get("cnes"))
        lot_cbo = norm_cbo(lot.get("cbo"))

        cnes_ok = lot_cnes == cnes

        # Se o CBO veio no CNES, exige bater.
        # Se não veio, valida pelo CNES.
        cbo_ok = True
        if cbo and lot_cbo:
            cbo_ok = lot_cbo == cbo

        if cnes_ok and cbo_ok:
            return {
                "ok": True,
                "tipo": "PROFISSIONAL_LOTADO_CNES",
                "mensagem": f"Profissional {cns} encontrado no CNES {cnes}.",
                "detalhe": f"CBO CNES: {lot_cbo or 'não informado'} | CBO BPA: {cbo or 'não informado'}",
                "lotacao": lot,
                "dados": dados,
            }

    return {
        "ok": False,
        "tipo": "PROFISSIONAL_NAO_LOTADO_CNES",
        "mensagem": f"Profissional CNS {cns} não encontrado como vínculo ativo no CNES {cnes}.",
        "detalhe": f"CBO analisado: {cbo or 'não informado'}",
        "dados": dados,
    }


def validar_profissionais_linhas_cnes(linhas, usar_cache=True):
    problemas = []
    chaves = {}

    for item in linhas:
        cns = norm_cns(item.get("cns_prof"))
        cnes = norm_cnes(item.get("cnes") or item.get("prd-cnes"))
        cbo = norm_cbo(item.get("cbo"))

        if not cns or not cnes:
            continue

        chave = (cns, cnes, cbo)
        chaves.setdefault(chave, []).append(item)

    for (cns, cnes, cbo), itens in chaves.items():
        resultado = validar_profissional_no_cnes(cns, cnes, cbo, usar_cache=usar_cache)

        if resultado.get("ok"):
            continue

        for item in itens:
            problemas.append({
                "linha_excel": item.get("linha_excel"),
                "idx": item.get("idx"),
                "tipo": resultado.get("tipo", "CNES_PROFISSIONAL_INVALIDO"),
                "gravidade": "aviso",
                "mensagem": resultado.get("mensagem"),
                "paciente": item.get("paciente"),
                "data": item.get("data_br"),
                "procedimento": item.get("procedimento"),
                "cid": item.get("cid"),
                "servico": item.get("servico"),
                "classificacao": item.get("classificacao"),
                "sugestao": "Verifique a ficha do profissional no CNES e confirme vínculo ativo no estabelecimento.",
                "selecionavel": False,
            })

    return problemas