# -*- coding: utf-8 -*-
"""
Auditoria BPA-I
- Duplicidades
- Validação procedimento/CBO/CID/serviço/classificação
- Validação CNES profissional/estabelecimento como AVISO
- Rankings gerais e por pessoa
- Baixa frequência estimada por paciente
- Suporte a exclusão de linhas por índice
"""

import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime

import pandas as pd

try:
    from db import conectar_db
except Exception:
    conectar_db = None

try:
    from .cnes_service import validar_profissionais_linhas_cnes
except Exception:
    validar_profissionais_linhas_cnes = None


_CACHE_REGRAS_PROCEDIMENTOS = None
_CACHE_OCUPACOES = None


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


def clean(v):
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass
    return str(v).strip()


def digits(v):
    s = clean(v)

    if re.match(r"^\d+\.0+$", s):
        s = s.split(".")[0]

    if re.match(r"^\d+(\.\d+)?e\+?\d+$", s.lower()):
        try:
            s = str(int(float(s)))
        except Exception:
            pass

    return re.sub(r"\D+", "", s)


def norm_text(v):
    s = clean(v)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip().upper()


def norm_codigo(v, width=None):
    d = digits(v)
    if width and d:
        return d.zfill(width)[-width:]
    return d


def norm_cid(v):
    return re.sub(r"[^A-Z0-9]", "", norm_text(v))


def split_lista(v):
    s = clean(v)
    if not s:
        return []
    return [x.strip() for x in s.split(",") if x.strip()]


def parse_data(v):
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()

    s = clean(v)
    if not s:
        return None

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y%m%d", "%d%m%Y"):
        try:
            return datetime.strptime(s[:10] if "-" in s else s, fmt).date()
        except Exception:
            pass

    try:
        dt = pd.to_datetime(s, dayfirst=True, errors="coerce")
        if pd.isna(dt):
            return None
        return dt.date()
    except Exception:
        return None


def limpar_cache_auditoria():
    global _CACHE_REGRAS_PROCEDIMENTOS, _CACHE_OCUPACOES
    _CACHE_REGRAS_PROCEDIMENTOS = None
    _CACHE_OCUPACOES = None


def carregar_regras_procedimentos(force_reload=False):
    global _CACHE_REGRAS_PROCEDIMENTOS

    if _CACHE_REGRAS_PROCEDIMENTOS is not None and not force_reload:
        return _CACHE_REGRAS_PROCEDIMENTOS

    regras = {}

    if conectar_db is None:
        print("❌ conectar_db não foi importado.")
        _CACHE_REGRAS_PROCEDIMENTOS = regras
        return regras

    conn = None
    cur = None

    try:
        conn = conectar_db()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                codigo,
                descricao,
                cids_codigos,
                cbos_codigos,
                servicos_codigos,
                classificacoes_codigos
            FROM procedimentos
            WHERE codigo IS NOT NULL
              AND TRIM(codigo) <> ''
        """)

        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description] if cur.description else []

        for row in rows:
            item = row_to_dict(row, cols)

            codigo = norm_codigo(item.get("codigo"), 10)
            if not codigo:
                continue

            cids = [norm_cid(x) for x in split_lista(item.get("cids_codigos"))]
            cbos = [norm_codigo(x, 6) for x in split_lista(item.get("cbos_codigos"))]
            servicos = [norm_codigo(x, 3) for x in split_lista(item.get("servicos_codigos"))]
            classificacoes = [norm_codigo(x, 3) for x in split_lista(item.get("classificacoes_codigos"))]

            pares = set()
            for srv, clf in zip(servicos, classificacoes):
                if srv and clf:
                    pares.add((srv, clf))

            regras[codigo] = {
                "codigo": codigo,
                "descricao": clean(item.get("descricao")),
                "cids": set(cids),
                "cbos": set(cbos),
                "servicos": set(servicos),
                "classificacoes": set(classificacoes),
                "pares_servico_classificacao": pares,
            }

        _CACHE_REGRAS_PROCEDIMENTOS = regras
        print("✅ Procedimentos carregados:", len(regras))
        return regras

    except Exception as e:
        print("❌ Erro ao carregar procedimentos:", repr(e))
        _CACHE_REGRAS_PROCEDIMENTOS = regras
        return regras

    finally:
        try:
            if cur:
                cur.close()
            if conn:
                conn.close()
        except Exception:
            pass


def carregar_ocupacoes(force_reload=False):
    global _CACHE_OCUPACOES

    if _CACHE_OCUPACOES is not None and not force_reload:
        return _CACHE_OCUPACOES

    mapa = {}

    if conectar_db is None:
        _CACHE_OCUPACOES = mapa
        return mapa

    conn = None
    cur = None

    try:
        conn = conectar_db()
        cur = conn.cursor()

        cur.execute("""
            SELECT co_ocupacao, no_ocupacao
            FROM ocupacoes
        """)

        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description] if cur.description else []

        for row in rows:
            item = row_to_dict(row, cols)
            cbo = norm_codigo(item.get("co_ocupacao"), 6)
            nome = clean(item.get("no_ocupacao"))

            if cbo:
                mapa[cbo] = nome

        _CACHE_OCUPACOES = mapa
        return mapa

    except Exception as e:
        print("⚠️ Erro ao carregar ocupações:", repr(e))
        _CACHE_OCUPACOES = mapa
        return mapa

    finally:
        try:
            if cur:
                cur.close()
            if conn:
                conn.close()
        except Exception:
            pass


def montar_linha_base(row, idx):
    data = parse_data(row.get("prd-dtaten"))

    paciente_key = (
        norm_codigo(row.get("prd-cnspac"), 15)
        or norm_codigo(row.get("prd-cpfpac"), 11)
        or norm_text(row.get("prd-nmpac"))
    )

    return {
        "idx": int(idx),
        "linha_excel": int(idx) + 2,
        "cnes": norm_codigo(row.get("prd-cnes"), 7),
        "paciente": norm_text(row.get("prd-nmpac")),
        "paciente_key": paciente_key,
        "cns_prof": norm_codigo(row.get("prd-cnsmed"), 15),
        "cbo": norm_codigo(row.get("prd-cbo"), 6),
        "data": data.isoformat() if data else "",
        "data_br": data.strftime("%d/%m/%Y") if data else "",
        "procedimento": norm_codigo(row.get("prd-pa"), 10),
        "cid": norm_cid(row.get("prd-cid")),
        "servico": norm_codigo(row.get("prd-srv"), 3),
        "classificacao": norm_codigo(row.get("prd-clf"), 3),
        "quantidade": int(norm_codigo(row.get("prd-qt")) or 1),
    }


def aplicar_exclusoes_linhas(linhas, excluir_idxs=None):
    excluir_idxs = set(int(x) for x in (excluir_idxs or []) if str(x).isdigit())
    return [l for l in linhas if l["idx"] not in excluir_idxs]


def detectar_duplicidades(linhas):
    problemas = []
    contador = defaultdict(list)

    for item in linhas:
        chave = (
            item["cns_prof"],
            item["paciente_key"],
            item["data"],
            item["procedimento"],
            item["cid"],
            item["servico"],
            item["classificacao"],
        )
        contador[chave].append(item)

    for _, itens in contador.items():
        if len(itens) > 1:
            for item in itens[1:]:
                problemas.append({
                    "linha_excel": item["linha_excel"],
                    "idx": item["idx"],
                    "tipo": "DUPLICIDADE",
                    "gravidade": "erro",
                    "mensagem": "Registro duplicado: mesmo profissional, paciente, data, procedimento, CID, serviço e classificação.",
                    "paciente": item["paciente"],
                    "data": item["data_br"],
                    "procedimento": item["procedimento"],
                    "cid": item["cid"],
                    "servico": item["servico"],
                    "classificacao": item["classificacao"],
                    "sugestao": "Excluir uma das linhas duplicadas antes de gerar o TXT.",
                    "selecionavel": True,
                })

    return problemas


def validar_regras_sigtap(linhas, regras):
    problemas = []

    for item in linhas:
        proc = norm_codigo(item.get("procedimento"), 10)
        item["procedimento"] = proc

        regra = regras.get(proc)

        if not regra:
            problemas.append({
                "linha_excel": item["linha_excel"],
                "idx": item["idx"],
                "tipo": "PROCEDIMENTO_NAO_ENCONTRADO",
                "gravidade": "erro",
                "mensagem": f"Procedimento {proc} não encontrado na tabela procedimentos.",
                "paciente": item["paciente"],
                "data": item["data_br"],
                "procedimento": proc,
                "cid": item["cid"],
                "servico": item["servico"],
                "classificacao": item["classificacao"],
                "sugestao": "Verifique se a tabela procedimentos foi importada corretamente.",
                "selecionavel": True,
            })
            continue

        checks = [
            ("CBO_INVALIDO", regra["cbos"] and item["cbo"] and item["cbo"] not in regra["cbos"], f"CBO {item['cbo']} não permitido para o procedimento {proc}.", "Corrigir o CBO ou conferir se o procedimento informado é o correto."),
            ("CID_INVALIDO", regra["cids"] and item["cid"] and item["cid"] not in regra["cids"], f"CID {item['cid']} não permitido para o procedimento {proc}.", "Corrigir o CID ou conferir se o procedimento informado é compatível."),
            ("SERVICO_INVALIDO", regra["servicos"] and item["servico"] and item["servico"] not in regra["servicos"], f"Serviço {item['servico']} não permitido para o procedimento {proc}.", "Corrigir o serviço informado."),
            ("CLASSIFICACAO_INVALIDA", regra["classificacoes"] and item["classificacao"] and item["classificacao"] not in regra["classificacoes"], f"Classificação {item['classificacao']} não permitida para o procedimento {proc}.", "Corrigir a classificação informada."),
        ]

        for tipo, condicao, mensagem, sugestao in checks:
            if condicao:
                problemas.append({
                    "linha_excel": item["linha_excel"],
                    "idx": item["idx"],
                    "tipo": tipo,
                    "gravidade": "erro",
                    "mensagem": mensagem,
                    "paciente": item["paciente"],
                    "data": item["data_br"],
                    "procedimento": proc,
                    "cid": item["cid"],
                    "servico": item["servico"],
                    "classificacao": item["classificacao"],
                    "sugestao": sugestao,
                    "selecionavel": True,
                })

        par = (item["servico"], item["classificacao"])

        if regra["pares_servico_classificacao"] and item["servico"] and item["classificacao"]:
            if par not in regra["pares_servico_classificacao"]:
                problemas.append({
                    "linha_excel": item["linha_excel"],
                    "idx": item["idx"],
                    "tipo": "SERVICO_CLASSIFICACAO_INVALIDO",
                    "gravidade": "erro",
                    "mensagem": f"O par serviço {item['servico']} + classificação {item['classificacao']} não está permitido para o procedimento {proc}.",
                    "paciente": item["paciente"],
                    "data": item["data_br"],
                    "procedimento": proc,
                    "cid": item["cid"],
                    "servico": item["servico"],
                    "classificacao": item["classificacao"],
                    "sugestao": "Corrigir serviço/classificação conforme a tabela SIGTAP.",
                    "selecionavel": True,
                })

    return problemas


def validar_cnes_profissionais(linhas, validar_cnes=False):
    if not validar_cnes:
        return []

    if validar_profissionais_linhas_cnes is None:
        return [{
            "linha_excel": "-",
            "idx": -1,
            "tipo": "CNES_VALIDACAO_INDISPONIVEL",
            "gravidade": "aviso",
            "mensagem": "Validação CNES indisponível. Verifique o arquivo cnes_service.py e a dependência requests.",
            "paciente": "-",
            "data": "-",
            "procedimento": "-",
            "cid": "-",
            "servico": "-",
            "classificacao": "-",
            "sugestao": "Instale requests e confirme se cnes_service.py está no módulo export.",
            "selecionavel": False,
        }]

    try:
        return validar_profissionais_linhas_cnes(linhas, usar_cache=True)
    except Exception as e:
        return [{
            "linha_excel": "-",
            "idx": -1,
            "tipo": "CNES_ERRO_VALIDACAO",
            "gravidade": "aviso",
            "mensagem": f"Erro ao validar profissionais no CNES: {e}",
            "paciente": "-",
            "data": "-",
            "procedimento": "-",
            "cid": "-",
            "servico": "-",
            "classificacao": "-",
            "sugestao": "Tente novamente ou valide manualmente no CNES.",
            "selecionavel": False,
        }]


def filtrar_problemas(problemas, tipo=None):
    if not tipo or tipo in {"TODOS", "ALL"}:
        return problemas
    return [p for p in problemas if p.get("tipo") == tipo]


def paginar_lista(lista, pagina=1, por_pagina=25):
    pagina = max(1, int(pagina or 1))
    por_pagina = max(1, int(por_pagina or 25))

    total = len(lista)
    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
    pagina = min(pagina, total_paginas)

    ini = (pagina - 1) * por_pagina
    fim = ini + por_pagina

    return {
        "itens": lista[ini:fim],
        "pagina": pagina,
        "por_pagina": por_pagina,
        "total": total,
        "total_paginas": total_paginas,
        "tem_anterior": pagina > 1,
        "tem_proxima": pagina < total_paginas,
        "pagina_anterior": pagina - 1 if pagina > 1 else 1,
        "pagina_proxima": pagina + 1 if pagina < total_paginas else total_paginas,
    }


def gerar_rankings(linhas):
    por_procedimento = Counter()
    por_cid = Counter()
    por_profissional = Counter()
    por_paciente = Counter()
    por_dia = Counter()
    por_procedimento_cid = Counter()
    por_servico_classificacao = Counter()

    pessoa_proc = defaultdict(Counter)
    pessoa_cid = defaultdict(Counter)
    pessoa_dias = defaultdict(set)

    pacientes_unicos = set()
    profissionais_unicos = set()

    for item in linhas:
        qt = item["quantidade"] or 1
        paciente = item["paciente"] or "SEM NOME"
        paciente_key = item["paciente_key"] or paciente

        por_procedimento[item["procedimento"]] += qt
        por_cid[item["cid"] or "SEM CID"] += qt
        por_profissional[item["cns_prof"] or "SEM CNS PROF"] += qt
        por_paciente[paciente] += qt
        por_dia[item["data_br"] or "SEM DATA"] += qt
        por_procedimento_cid[(item["procedimento"], item["cid"] or "SEM CID")] += qt
        por_servico_classificacao[(item["servico"], item["classificacao"])] += qt

        pessoa_proc[(paciente_key, paciente)][item["procedimento"]] += qt
        pessoa_cid[(paciente_key, paciente)][item["cid"] or "SEM CID"] += qt

        if item["data"]:
            pessoa_dias[(paciente_key, paciente)].add(item["data"])

        if paciente_key:
            pacientes_unicos.add(paciente_key)

        if item["cns_prof"]:
            profissionais_unicos.add(item["cns_prof"])

    def top(counter, limit=50):
        return [{"chave": k, "quantidade": v} for k, v in counter.most_common(limit)]

    por_pessoa = []

    for (paciente_key, paciente), counter_proc in pessoa_proc.items():
        total = sum(counter_proc.values())
        proc_top = counter_proc.most_common(5)
        cid_top = pessoa_cid[(paciente_key, paciente)].most_common(5)

        por_pessoa.append({
            "paciente_key": paciente_key,
            "paciente": paciente,
            "quantidade_total": total,
            "dias_diferentes": len(pessoa_dias[(paciente_key, paciente)]),
            "procedimentos_txt": ", ".join([f"{k} ({v})" for k, v in proc_top]),
            "cids_txt": ", ".join([f"{k} ({v})" for k, v in cid_top]),
        })

    por_pessoa.sort(key=lambda x: x["quantidade_total"], reverse=True)

    return {
        "procedimentos": top(por_procedimento),
        "cids": top(por_cid),
        "profissionais": top(por_profissional),
        "pacientes": top(por_paciente),
        "dias": top(por_dia, 31),
        "procedimento_cid": [
            {"procedimento": k[0], "cid": k[1], "quantidade": v}
            for k, v in por_procedimento_cid.most_common(50)
        ],
        "servico_classificacao": [
            {"servico": k[0], "classificacao": k[1], "quantidade": v}
            for k, v in por_servico_classificacao.most_common(50)
        ],
        "por_pessoa": por_pessoa,
        "pacientes_unicos": len(pacientes_unicos),
        "profissionais_unicos": len(profissionais_unicos),
    }


def baixa_frequencia_estimada(linhas, minimo_dias=4):
    ocupacoes = carregar_ocupacoes()

    mapa_dias = defaultdict(set)
    mapa_cbos = defaultdict(set)
    mapa_cns = defaultdict(set)
    dados_paciente = {}

    for item in linhas:
        paciente_key = item.get("paciente_key")
        data = item.get("data")

        if not paciente_key or not data:
            continue

        mapa_dias[paciente_key].add(data)

        cbo = norm_codigo(item.get("cbo"), 6)
        cns_prof = norm_codigo(item.get("cns_prof"), 15)

        if cbo:
            mapa_cbos[paciente_key].add(cbo)

        if cns_prof:
            mapa_cns[paciente_key].add(cns_prof)

        dados_paciente[paciente_key] = {
            "paciente": item.get("paciente") or "SEM NOME",
            "paciente_key": paciente_key,
        }

    abaixo = []

    for paciente_key, dias in mapa_dias.items():
        qtd_dias = len(dias)

        if qtd_dias < minimo_dias:
            cbos = sorted(mapa_cbos[paciente_key])
            cns_profissionais = sorted(mapa_cns[paciente_key])

            cbos_descritos = []
            for cbo in cbos:
                nome_ocupacao = ocupacoes.get(cbo, "")
                cbos_descritos.append(f"{cbo} - {nome_ocupacao}" if nome_ocupacao else cbo)

            info = dados_paciente[paciente_key]

            abaixo.append({
                "paciente": info["paciente"],
                "paciente_key": paciente_key,
                "dias_diferentes": qtd_dias,
                "dias_realizados": sorted(dias),
                "dias_realizados_txt": ", ".join(sorted(dias)),
                "meta_minima": minimo_dias,
                "deficit": minimo_dias - qtd_dias,
                "percentual": round((qtd_dias / minimo_dias) * 100, 1),
                "cbos": cbos,
                "cbos_txt": ", ".join(cbos_descritos),
                "cns_profissionais": sorted(mapa_cns[paciente_key]),
                "cns_profissionais_txt": ", ".join(sorted(mapa_cns[paciente_key])),
            })

    abaixo.sort(key=lambda x: (x["dias_diferentes"], x["paciente"]))

    return {
        "minimo_dias": minimo_dias,
        "pacientes_abaixo": abaixo,
    }


def auditar_dataframe_bpa(
    df: pd.DataFrame,
    carregar_regras=True,
    excluir_idxs=None,
    filtro_tipo_erro=None,
    pagina_erros=1,
    erros_por_pagina=25,
    validar_cnes=False,
):
    linhas_originais = [montar_linha_base(row, idx) for idx, row in df.iterrows()]
    linhas = aplicar_exclusoes_linhas(linhas_originais, excluir_idxs)

    regras = carregar_regras_procedimentos() if carregar_regras else {}

    problemas = []

    if carregar_regras and not regras:
        problemas.append({
            "linha_excel": "-",
            "idx": -1,
            "tipo": "BASE_PROCEDIMENTOS_VAZIA",
            "gravidade": "erro",
            "mensagem": "Nenhuma regra foi carregada da tabela procedimentos.",
            "paciente": "-",
            "data": "-",
            "procedimento": "-",
            "cid": "-",
            "servico": "-",
            "classificacao": "-",
            "sugestao": "Verifique conexão com o banco, nome da tabela procedimentos e se há registros importados.",
            "selecionavel": False,
        })
    else:
        problemas.extend(detectar_duplicidades(linhas))
        problemas.extend(validar_regras_sigtap(linhas, regras))

    problemas.extend(validar_cnes_profissionais(linhas, validar_cnes=validar_cnes))

    idx_com_erro = {
        p["idx"]
        for p in problemas
        if p.get("gravidade") == "erro"
        and isinstance(p.get("idx"), int)
        and p.get("idx") >= 0
    }

    total_avisos = sum(1 for p in problemas if p.get("gravidade") == "aviso")
    total_erros = sum(1 for p in problemas if p.get("gravidade") == "erro")

    tipos_erro = sorted({p["tipo"] for p in problemas})
    problemas_filtrados = filtrar_problemas(problemas, filtro_tipo_erro)
    problemas_paginados = paginar_lista(problemas_filtrados, pagina_erros, erros_por_pagina)

    rankings = gerar_rankings(linhas)
    baixa_freq = baixa_frequencia_estimada(linhas, minimo_dias=4)

    resumo = {
        "total_linhas_original": len(linhas_originais),
        "total_linhas": len(linhas),
        "linhas_excluidas": len(linhas_originais) - len(linhas),
        "validas": max(0, len(linhas) - len(idx_com_erro)),
        "linhas_com_erro": len(idx_com_erro),
        "total_problemas": len(problemas),
        "total_erros": total_erros,
        "total_avisos": total_avisos,
        "duplicidades": sum(1 for p in problemas if p["tipo"] == "DUPLICIDADE"),
        "inconsistencias": sum(
            1 for p in problemas
            if p["tipo"] != "DUPLICIDADE" and p.get("gravidade") == "erro"
        ),
        "avisos_cnes": sum(
            1 for p in problemas
            if str(p["tipo"]).startswith("CNES") or "CNES" in str(p["tipo"])
        ),
        "pacientes_unicos": rankings["pacientes_unicos"],
        "profissionais_unicos": rankings["profissionais_unicos"],
        "procedimentos_diferentes": len({x["procedimento"] for x in linhas if x["procedimento"]}),
        "cids_diferentes": len({x["cid"] for x in linhas if x["cid"]}),
        "pode_gerar_txt": True,
        "tem_problemas": len(problemas) > 0,
        "tem_erros": total_erros > 0,
        "tem_avisos": total_avisos > 0,
        "validacao_cnes_ativa": bool(validar_cnes),
    }

    exportacao = {
        "idxs_com_erro": sorted(idx_com_erro),
        "idxs_excluidos": sorted(set(excluir_idxs or [])),
        "idxs_aprovados": [l["idx"] for l in linhas if l["idx"] not in idx_com_erro],
    }

    cnes_profissionais = gerar_resumo_cnes_profissionais(
        linhas,
        validar_cnes=validar_cnes
)

    return {
        "resumo": resumo,
        "problemas": problemas,
        "problemas_filtrados": problemas_filtrados,
        "problemas_paginados": problemas_paginados,
        "tipos_erro": tipos_erro,
        "rankings": rankings,
        "baixa_frequencia": baixa_freq,
        "linhas": linhas,
        "linhas_originais": linhas_originais,
        "exportacao": exportacao,
        "cnes_profissionais": cnes_profissionais,
    }



def gerar_resumo_cnes_profissionais(linhas, validar_cnes=False):
    if not validar_cnes:
        return {
            "ativo": False,
            "total_analisados": 0,
            "encontrados": 0,
            "com_alerta": 0,
            "itens": [],
        }

    if validar_profissionais_linhas_cnes is None:
        return {
            "ativo": True,
            "total_analisados": 0,
            "encontrados": 0,
            "com_alerta": 1,
            "itens": [{
                "cns": "-",
                "cnes": "-",
                "cbo": "-",
                "status": "VALIDAÇÃO INDISPONÍVEL",
                "mensagem": "cnes_service.py não foi carregado.",
                "qtd_linhas": 0,
            }],
        }

    grupos = {}

    for item in linhas:
        chave = (
            item.get("cns_prof", ""),
            item.get("cnes", ""),
            item.get("cbo", ""),
        )

        if not chave[0] or not chave[1]:
            continue

        grupos.setdefault(chave, []).append(item)

    itens = []

    try:
        from .cnes_service import validar_profissional_no_cnes
    except Exception:
        try:
            from cnes_service import validar_profissional_no_cnes
        except Exception:
            validar_profissional_no_cnes = None

    if validar_profissional_no_cnes is None:
        return {
            "ativo": True,
            "total_analisados": len(grupos),
            "encontrados": 0,
            "com_alerta": len(grupos),
            "itens": [],
        }

    for (cns, cnes, cbo), regs in grupos.items():
        r = validar_profissional_no_cnes(cns, cnes, cbo, usar_cache=True)

        itens.append({
            "cns": cns,
            "cnes": cnes,
            "cbo": cbo,
            "qtd_linhas": len(regs),
            "status": "ENCONTRADO" if r.get("ok") else "ALERTA",
            "mensagem": r.get("mensagem", ""),
            "detalhe": r.get("detalhe", ""),
        })

    encontrados = sum(1 for x in itens if x["status"] == "ENCONTRADO")
    com_alerta = sum(1 for x in itens if x["status"] != "ENCONTRADO")

    return {
        "ativo": True,
        "total_analisados": len(itens),
        "encontrados": encontrados,
        "com_alerta": com_alerta,
        "itens": itens,
    }