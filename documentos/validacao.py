# documentos/validacao.py
"""Validacao e normalizacao do `conteudo` de cada tipo de documento.

Adicionar um tipo novo = registrar uma entrada em TIPOS (rotulo + funcao validadora). A tabela nao muda.
Cada validador recebe o dict bruto enviado pelo navegador e devolve (conteudo_normalizado, erros).
Nada aqui acessa o banco; a checagem contra o catalogo (CID / procedimentos) e feita nas rotas.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Callable

URGENCIAS = ("eletivo", "prioritario", "urgente")
MODALIDADES_ATESTADO = ("afastamento", "comparecimento")
MAX_ITENS = 30


# ----------------------------------------------------------------------------- utilidades
def _txt(v: Any, limite: int) -> str:
    """Texto aparado; devolve '' se nao for texto. O corte por tamanho e erro (nao trunca em silencio): ver _exige/_limite."""
    if v is None:
        return ""
    return str(v).strip()


def _limite(erros: list[str], rotulo: str, valor: str, maximo: int) -> str:
    if len(valor) > maximo:
        erros.append(f"{rotulo}: no máximo {maximo} caracteres (tem {len(valor)}).")
    return valor


def _exige(erros: list[str], rotulo: str, valor: str, maximo: int, minimo: int = 1) -> str:
    if len(valor) < minimo:
        erros.append(f"{rotulo}: obrigatório." if minimo <= 1 else f"{rotulo}: escreva pelo menos {minimo} caracteres.")
    elif len(valor) > maximo:
        erros.append(f"{rotulo}: no máximo {maximo} caracteres (tem {len(valor)}).")
    return valor


def _data(erros: list[str], rotulo: str, valor: Any, obrigatoria: bool = False) -> str:
    s = _txt(valor, 10)
    if not s:
        if obrigatoria:
            erros.append(f"{rotulo}: obrigatória.")
        return ""
    try:
        return date.fromisoformat(s).isoformat()
    except ValueError:
        erros.append(f"{rotulo}: data inválida (use AAAA-MM-DD).")
        return ""


def _hora(erros: list[str], rotulo: str, valor: Any) -> str:
    s = _txt(valor, 5)
    if not s:
        return ""
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", s):
        erros.append(f"{rotulo}: horário inválido (use HH:MM).")
        return ""
    return s


def _lista(erros: list[str], rotulo: str, valor: Any) -> list[dict]:
    if not isinstance(valor, list) or not valor:
        erros.append(f"{rotulo}: inclua pelo menos 1 item.")
        return []
    if len(valor) > MAX_ITENS:
        erros.append(f"{rotulo}: no máximo {MAX_ITENS} itens.")
        return []
    return [x if isinstance(x, dict) else {} for x in valor]


def _urgencia(erros: list[str], valor: Any) -> str:
    s = _txt(valor, 20).lower() or "eletivo"
    if s not in URGENCIAS:
        erros.append("Urgência inválida (use eletivo, prioritário ou urgente).")
        return "eletivo"
    return s


# ----------------------------------------------------------------------------- CID (opcional)
RE_CID = re.compile(r"^[A-Z]\d{2}(\.?[0-9A-Z]{1,4})?$")


def normaliza_cid(cid: Any) -> tuple[dict | None, list[str]]:
    """CID e OPCIONAL. Vazio -> (None, []). Formato invalido -> erro."""
    if not cid:
        return None, []
    if not isinstance(cid, dict):
        return None, ["CID inválido."]
    codigo = _txt(cid.get("codigo"), 10).upper().replace(" ", "")
    if not codigo:
        return None, []
    if not RE_CID.match(codigo):
        return None, [f"CID '{codigo}' em formato inválido (exemplo: F84.0 ou J00)."]
    descricao = _txt(cid.get("descricao"), 300)
    erros: list[str] = []
    _limite(erros, "Descrição do CID", descricao, 300)
    return {"codigo": codigo, "descricao": descricao}, erros


# ----------------------------------------------------------------------------- por tipo
def valida_receita(c: dict, ctx: dict) -> tuple[dict, list[str]]:
    erros: list[str] = []
    itens_out = []
    for i, it in enumerate(_lista(erros, "Medicamentos", c.get("itens")), 1):
        p = f"Medicamento {i}"
        med = _exige(erros, f"{p} (nome)", _txt(it.get("medicamento"), 200), 200)
        pos = _exige(erros, f"{p} (posologia)", _txt(it.get("posologia"), 500), 500)
        itens_out.append({
            "medicamento": med,
            "dose": _limite(erros, f"{p} (dose)", _txt(it.get("dose"), 100), 100),
            "via": _limite(erros, f"{p} (via)", _txt(it.get("via"), 60), 60),
            "posologia": pos,
            "duracao": _limite(erros, f"{p} (duração)", _txt(it.get("duracao"), 100), 100),
            "quantidade": _limite(erros, f"{p} (quantidade)", _txt(it.get("quantidade"), 60), 60),
            "observacao": _limite(erros, f"{p} (observação)", _txt(it.get("observacao"), 300), 300),
        })
    orient = _limite(erros, "Orientações gerais", _txt(c.get("orientacoes_gerais"), 2000), 2000)
    return {"itens": itens_out, "orientacoes_gerais": orient}, erros


def valida_atestado(c: dict, ctx: dict) -> tuple[dict, list[str]]:
    erros: list[str] = []
    modalidade = _txt(c.get("modalidade"), 20).lower()
    if modalidade not in MODALIDADES_ATESTADO:
        erros.append("Modalidade do atestado: escolha afastamento ou comparecimento.")
        modalidade = ""
    out: dict[str, Any] = {"modalidade": modalidade}

    if modalidade == "afastamento":
        try:
            dias = int(c.get("dias"))
        except (TypeError, ValueError):
            dias = 0
        if not 1 <= dias <= 365:
            erros.append("Dias de afastamento: informe um número entre 1 e 365.")
        out["dias"] = dias
        out["data_inicio"] = _data(erros, "Data de início do afastamento", c.get("data_inicio")) or ctx.get("data_atendimento", "")
    elif modalidade == "comparecimento":
        out["data"] = _data(erros, "Data do comparecimento", c.get("data")) or ctx.get("data_atendimento", "")
        hi, hf = _hora(erros, "Hora de início", c.get("hora_inicio")), _hora(erros, "Hora de término", c.get("hora_fim"))
        if hi and hf and hf <= hi:
            erros.append("Hora de término deve ser depois da hora de início.")
        out["hora_inicio"], out["hora_fim"] = hi, hf

    out["observacao"] = _limite(erros, "Observação", _txt(c.get("observacao"), 2000), 2000)
    incluir = bool(c.get("incluir_cid"))
    if incluir and not ctx.get("tem_cid"):
        erros.append("Para incluir o CID no atestado, informe o CID (ou desmarque a opção).")
    out["incluir_cid"] = incluir
    return out, erros


def valida_declaracao(c: dict, ctx: dict) -> tuple[dict, list[str]]:
    erros: list[str] = []
    finalidade = _limite(erros, "Finalidade", _txt(c.get("finalidade"), 200), 200)
    texto = _exige(erros, "Texto da declaração", _txt(c.get("texto"), 5000), 5000, minimo=10)
    return {"finalidade": finalidade, "texto": texto}, erros


def valida_encaminhamento(c: dict, ctx: dict) -> tuple[dict, list[str]]:
    erros: list[str] = []
    esp = _exige(erros, "Especialidade ou serviço de destino", _txt(c.get("especialidade_destino"), 200), 200)
    prof = _limite(erros, "Profissional de destino", _txt(c.get("profissional_destino"), 200), 200)
    motivo = _exige(erros, "Motivo do encaminhamento", _txt(c.get("motivo"), 2000), 2000, minimo=5)
    resumo = _limite(erros, "Resumo clínico", _txt(c.get("resumo_clinico"), 3000), 3000)
    return {"especialidade_destino": esp, "profissional_destino": prof, "motivo": motivo,
            "resumo_clinico": resumo, "urgencia": _urgencia(erros, c.get("urgencia"))}, erros


RE_SIGTAP = re.compile(r"^\d{10}$")


def valida_solicitacao_exame(c: dict, ctx: dict) -> tuple[dict, list[str]]:
    """Exames do catalogo (codigo SIGTAP de 10 digitos) OU texto livre (catalogo ainda nao importado nao bloqueia).
    NAO ha upload/anexo: so texto."""
    erros: list[str] = []
    exames = []
    for i, it in enumerate(_lista(erros, "Exames", c.get("exames")), 1):
        p = f"Exame {i}"
        codigo = re.sub(r"\D", "", _txt(it.get("procedimento_codigo"), 20))
        if codigo and not RE_SIGTAP.match(codigo):
            erros.append(f"{p}: código do procedimento deve ter 10 dígitos.")
        desc = _exige(erros, f"{p} (descrição)", _txt(it.get("descricao"), 300), 300)
        exames.append({"procedimento_codigo": codigo, "descricao": desc,
                       "observacao": _limite(erros, f"{p} (observação)", _txt(it.get("observacao"), 300), 300)})
    just = _limite(erros, "Justificativa / indicação clínica", _txt(c.get("justificativa"), 2000), 2000)
    return {"exames": exames, "justificativa": just, "urgencia": _urgencia(erros, c.get("urgencia"))}, erros


# ----------------------------------------------------------------------------- registro de tipos
# Para adicionar "orientacoes" ou "relatorio" no futuro: uma linha aqui + o validador + o bloco de impressao. Sem migracao.
TIPOS: dict[str, dict] = {
    "receita":           {"rotulo": "Receita",                 "titulo": "Receituário",                       "valida": valida_receita},
    "atestado":          {"rotulo": "Atestado",                "titulo": "Atestado",                          "valida": valida_atestado},
    "declaracao":        {"rotulo": "Declaração",              "titulo": "Declaração",                        "valida": valida_declaracao},
    "encaminhamento":    {"rotulo": "Encaminhamento",          "titulo": "Encaminhamento",                    "valida": valida_encaminhamento},
    "solicitacao_exame": {"rotulo": "Solicitação de exame",    "titulo": "Solicitação de exames",             "valida": valida_solicitacao_exame},
}


def valida_documento(payload: Any, ctx: dict) -> tuple[dict | None, list[str]]:
    """payload = {tipo, cid?, conteudo}. Devolve ({tipo, cid, conteudo}, []) ou (None, erros)."""
    if not isinstance(payload, dict):
        return None, ["Requisição inválida."]

    tipo = _txt(payload.get("tipo"), 40)
    if tipo not in TIPOS:
        return None, [f"Tipo de documento inválido: '{tipo}'."]

    conteudo_bruto = payload.get("conteudo")
    if not isinstance(conteudo_bruto, dict):
        return None, ["Conteúdo do documento ausente."]

    cid, erros_cid = normaliza_cid(payload.get("cid"))
    conteudo, erros = TIPOS[tipo]["valida"](conteudo_bruto, dict(ctx, tem_cid=bool(cid)))
    erros = erros_cid + erros
    if erros:
        return None, erros
    return {"tipo": tipo, "cid": cid, "conteudo": conteudo}, []
