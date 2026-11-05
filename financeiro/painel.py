# financeiro/painel.py
"""Painel financeiro consolidado (Grupo F): só leitura.

    GET /financeiro/api/painel?competencia=AAAA-MM
    GET /financeiro/api/inadimplencia[?limit=N]

Reúne os catálogos (combos, planos, avulsos, avaliações) e os lançamentos. Não escreve
em nenhuma tabela. Todas as consultas passam por _add_clinica_where (fail-closed).

Datas: vencimento/competencia/data_* são TEXT no projeto (criado_em é TIMESTAMP). A
comparação com "hoje" é feita em Python sobre o valor ISO (AAAA-MM-DD); vencimento que
não for uma data ISO válida nunca é tratado como vencido e é contado à parte
(`sem_vencimento_valido`), em vez de entrar numa comparação de texto errada.

Status: "em aberto" = tudo que não é 'pago' nem 'cancelado' (pendente, parcial...).
Não existe valor parcialmente pago no banco: um 'parcial' conta pelo valor cheio.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from flask import request

from . import financeiro_bp
from . import financas
from admin.modulos import require_permission

from .financas import (
    ensure_financeiro_schema,
    _conn,
    _execute,
    _fetchall_dict,
    _fetchone_dict,
    _to_int,
    _table_exists,
    _add_clinica_where,
    _ok,
    _fail,
)

_RE_COMPETENCIA = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
ORIGENS = ("combo", "plano", "avulso", "avaliacao", "outras")


def _dec(v) -> Decimal:
    try:
        return Decimal(str(v)) if v not in (None, "") else Decimal("0")
    except Exception:
        return Decimal("0")


def _r2(d: Decimal) -> float:
    return float(round(d, 2))


def _iso(v):
    """'AAAA-MM-DD[...]' -> date; qualquer outra coisa -> None."""
    s = str(v or "").strip()[:10]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _hoje() -> date:
    return date.fromisoformat(financas._today_iso())


def _cond(conn, tabela: str, alias: str):
    """('alias.clinica_id = ?', [id]) -- fail-closed, para usar em ON de JOIN."""
    w, p = [], []
    _add_clinica_where(conn, tabela, alias, w, p)
    return w[0], p


def _contar(conn, tabela: str, extra: str = "1=1", params=None) -> int:
    where = [extra]
    prm = list(params or [])
    _add_clinica_where(conn, tabela, tabela, where, prm)
    cur = _execute(conn, f"SELECT COUNT(*) AS total FROM {tabela} WHERE {' AND '.join(where)}", prm)
    return _to_int((_fetchone_dict(cur) or {}).get("total"), 0)


def _nomes(conn, tabela: str, ids: list, coluna_nome: str = "nome") -> dict:
    """{id: nome} para uma lista de ids, sempre filtrado pela clínica."""
    ids = sorted({int(i) for i in ids if i is not None})
    out = {}

    if not ids or not _table_exists(conn, tabela):
        return out

    for i in range(0, len(ids), 500):
        parte = ids[i:i + 500]
        where = [f"t.id IN ({', '.join(['?'] * len(parte))})"]
        params = list(parte)
        _add_clinica_where(conn, tabela, "t", where, params)

        cur = _execute(conn, f"SELECT t.id, t.{coluna_nome} AS nome FROM {tabela} t WHERE {' AND '.join(where)}", params)

        for r in _fetchall_dict(cur):
            out[int(r["id"])] = r.get("nome")

    return out


# =====================================================================
# PAINEL
# =====================================================================

@financeiro_bp.get("/api/painel")
@require_permission("financeiro", "ver")
def api_painel():
    ensure_financeiro_schema()

    competencia = (request.args.get("competencia") or financas._competencia_padrao()).strip()

    if not _RE_COMPETENCIA.match(competencia):
        return _fail("Competência inválida. Use AAAA-MM.")

    conn = _conn()

    try:
        hoje = _hoje()

        # --- lançamentos da competência, já com origem (combo/plano) e dono no catálogo ---
        c_pp, p_pp = _cond(conn, "financeiro_paciente_planos", "pp")
        c_pl, p_pl = _cond(conn, "financeiro_planos", "fpl")
        c_cb, p_cb = _cond(conn, "financeiro_combos", "fc")

        where = ["l.competencia = ?"]
        p_where = [competencia]
        _add_clinica_where(conn, "financeiro_lancamentos", "l", where, p_where)

        cur = _execute(conn, f"""
            SELECT
                l.tipo,
                l.status,
                l.valor,
                l.vencimento,
                l.origem,
                pp.tipo AS contrato_tipo,
                COALESCE(fpl.profissional_id, fc.profissional_id) AS profissional_id
            FROM financeiro_lancamentos l
            LEFT JOIN financeiro_paciente_planos pp ON pp.id = l.plano_id AND {c_pp}
            LEFT JOIN financeiro_planos fpl ON fpl.id = pp.plano_catalogo_id AND {c_pl}
            LEFT JOIN financeiro_combos fc ON fc.id = pp.combo_id AND {c_cb}
            WHERE {" AND ".join(where)}
        """, [*p_pp, *p_pl, *p_cb, *p_where])

        linhas = _fetchall_dict(cur)

        zero = Decimal("0")
        rec = {"prevista": zero, "recebida": zero, "em_aberto": zero, "vencida": zero}
        qtd_vencidas = 0
        sem_venc = 0
        desp = {"previstas": zero, "pagas": zero, "em_aberto": zero}
        por_origem = {o: {"previsto": zero, "recebido": zero, "em_aberto": zero, "qtd": 0} for o in ORIGENS}
        por_prof = {}

        for ln in linhas:
            status = (ln.get("status") or "").strip().lower()

            if status == "cancelado":
                continue

            valor = _dec(ln.get("valor"))
            paga = status == "pago"

            if (ln.get("tipo") or "").lower() == "saida":
                desp["previstas"] += valor
                if paga:
                    desp["pagas"] += valor
                else:
                    desp["em_aberto"] += valor
                continue

            if (ln.get("tipo") or "").lower() != "entrada":
                continue

            rec["prevista"] += valor
            if paga:
                rec["recebida"] += valor
            else:
                rec["em_aberto"] += valor
                venc = _iso(ln.get("vencimento"))
                if venc is None:
                    sem_venc += 1
                elif venc < hoje:
                    rec["vencida"] += valor
                    qtd_vencidas += 1

            origem = (ln.get("origem") or "").strip().lower()
            if origem == "plano":
                classe = "combo" if ln.get("contrato_tipo") == "combo" else "plano"
            elif origem in ("avulso", "avaliacao"):
                classe = origem
            else:
                classe = "outras"

            o = por_origem[classe]
            o["previsto"] += valor
            o["qtd"] += 1
            o["recebido" if paga else "em_aberto"] += valor

            pid = ln.get("profissional_id")
            pid = int(pid) if pid is not None else None
            pf = por_prof.setdefault(pid, {"previsto": zero, "recebido": zero, "em_aberto": zero})
            pf["previsto"] += valor
            pf["recebido" if paga else "em_aberto"] += valor

        nomes_prof = _nomes(conn, "usuarios", [k for k in por_prof if k is not None])

        # --- catálogos e contratos ---
        planos_cat = {"individual": 0, "familiar": 0}
        cur = _execute(conn, *_sql_planos_cat(conn))
        for r in _fetchall_dict(cur):
            planos_cat["familiar" if _to_int(r.get("max_beneficiarios"), 1) > 1 else "individual"] += _to_int(r.get("total"), 0)
        planos_cat["total"] = planos_cat["individual"] + planos_cat["familiar"]

        contratos = {"combo": 0, "plano_individual": 0, "plano_familiar": 0}
        w_ct = ["status = 'ativo'"]
        p_ct = []
        _add_clinica_where(conn, "financeiro_paciente_planos", "financeiro_paciente_planos", w_ct, p_ct)
        cur = _execute(conn, f"""
            SELECT tipo, COALESCE(max_beneficiarios, 1) AS max_beneficiarios, COUNT(*) AS total
            FROM financeiro_paciente_planos
            WHERE {" AND ".join(w_ct)}
            GROUP BY tipo, COALESCE(max_beneficiarios, 1)
        """, p_ct)
        for r in _fetchall_dict(cur):
            n = _to_int(r.get("total"), 0)
            if r.get("tipo") == "combo":
                contratos["combo"] += n
            elif _to_int(r.get("max_beneficiarios"), 1) > 1:
                contratos["plano_familiar"] += n
            else:
                contratos["plano_individual"] += n
        contratos["total"] = contratos["combo"] + contratos["plano_individual"] + contratos["plano_familiar"]

        # avaliações realizadas (clínicas) no mês: tabela avaliacoes, só leitura
        avaliacoes_realizadas = 0
        if _table_exists(conn, "avaliacoes"):
            w_av = ["SUBSTR(CAST(avaliacoes.criado_em AS TEXT), 1, 7) = ?"]
            p_av = [competencia]
            _add_clinica_where(conn, "avaliacoes", "avaliacoes", w_av, p_av)
            cur = _execute(conn, f"SELECT COUNT(*) AS total FROM avaliacoes WHERE {' AND '.join(w_av)}", p_av)
            avaliacoes_realizadas = _to_int((_fetchone_dict(cur) or {}).get("total"), 0)

        painel = {
            "competencia": competencia,
            "hoje": hoje.isoformat(),
            "receita": {
                "prevista": _r2(rec["prevista"]),
                "recebida": _r2(rec["recebida"]),
                "em_aberto": _r2(rec["em_aberto"]),
                "vencida": _r2(rec["vencida"]),
                "qtd_vencidas": qtd_vencidas,
                "sem_vencimento_valido": sem_venc,
            },
            "despesas": {k: _r2(v) for k, v in desp.items()},
            "saldo": {
                "realizado": _r2(rec["recebida"] - desp["pagas"]),
                "previsto": _r2(rec["prevista"] - desp["previstas"]),
            },
            "contagens": {
                "combos_ativos": _contar(conn, "financeiro_combos", "ativo = 1"),
                "planos_catalogo_ativos": planos_cat,
                "contratos_ativos": contratos,
                "avulsos_ativos": _contar(conn, "financeiro_avulsos", "ativo = 1"),
                "avaliacoes_catalogo_ativas": _contar(conn, "financeiro_avaliacoes", "ativo = 1"),
                "avaliacoes_realizadas": avaliacoes_realizadas,
            },
            "receita_por_origem": {
                o: {"previsto": _r2(v["previsto"]), "recebido": _r2(v["recebido"]),
                    "em_aberto": _r2(v["em_aberto"]), "qtd": v["qtd"]}
                for o, v in por_origem.items()
            },
            "receita_por_profissional": sorted(
                [
                    {
                        "profissional_id": k,
                        "profissional_nome": nomes_prof.get(k) if k is not None else None,
                        "previsto": _r2(v["previsto"]),
                        "recebido": _r2(v["recebido"]),
                        "em_aberto": _r2(v["em_aberto"]),
                    }
                    for k, v in por_prof.items()
                ],
                key=lambda x: (-x["previsto"], x["profissional_id"] is None),
            ),
            "observacoes": [
                "Valores sem lançamentos cancelados. 'Em aberto' = pendente/parcial (sem valor parcial no banco).",
                "Receita vencida = vencimento anterior a hoje e não paga, dentro da competência (a lista completa está em /api/inadimplencia).",
                "Profissional: lançamentos ainda não gravam profissional_id; a receita é atribuída ao dono ATUAL do combo/plano no catálogo. Lançamentos manuais e sem dono ficam em profissional_id nulo.",
                "'avaliacoes_realizadas' conta a tabela clínica avaliacoes (criado_em no mês), não lançamentos.",
            ],
        }

        return _ok(painel=painel)

    except Exception as e:
        return _fail(f"Erro ao montar painel: {e}", 500)

    finally:
        conn.close()


def _sql_planos_cat(conn):
    where = ["ativo = 1"]
    params = []
    _add_clinica_where(conn, "financeiro_planos", "financeiro_planos", where, params)
    return (
        f"""
        SELECT max_beneficiarios, COUNT(*) AS total
        FROM financeiro_planos
        WHERE {" AND ".join(where)}
        GROUP BY max_beneficiarios
        """,
        params,
    )


# =====================================================================
# INADIMPLÊNCIA
# =====================================================================

@financeiro_bp.get("/api/inadimplencia")
@require_permission("financeiro", "ver")
def api_inadimplencia():
    ensure_financeiro_schema()

    limite = min(max(_to_int(request.args.get("limit"), 200), 1), 1000)

    conn = _conn()

    try:
        hoje = _hoje()

        c_pp, p_pp = _cond(conn, "financeiro_paciente_planos", "pp")

        where = ["l.tipo = 'entrada'", "COALESCE(l.status, '') NOT IN ('pago', 'cancelado')"]
        p_where = []
        _add_clinica_where(conn, "financeiro_lancamentos", "l", where, p_where)

        cur = _execute(conn, f"""
            SELECT
                l.id, l.paciente_id, l.plano_id, l.cliente_nome, l.descricao,
                l.valor, l.status, l.vencimento,
                pp.tipo AS contrato_tipo,
                COALESCE(pp.combo_nome, pp.nome_plano) AS contrato_nome
            FROM financeiro_lancamentos l
            LEFT JOIN financeiro_paciente_planos pp ON pp.id = l.plano_id AND {c_pp}
            WHERE {" AND ".join(where)}
        """, [*p_pp, *p_where])

        grupos = {}
        sem_venc = 0

        for ln in _fetchall_dict(cur):
            venc = _iso(ln.get("vencimento"))

            if venc is None:
                sem_venc += 1
                continue

            pid = ln.get("paciente_id")
            chave = ("p", int(pid)) if pid is not None else ("n", (ln.get("cliente_nome") or "").strip().lower())
            g = grupos.setdefault(chave, {
                "paciente_id": int(pid) if pid is not None else None,
                "cliente_nome": ln.get("cliente_nome"),
                "vencidos": [],
                "a_vencer": [],
            })

            (g["vencidos"] if venc < hoje else g["a_vencer"]).append((venc, ln))

        nomes = _nomes(conn, "pacientes", [g["paciente_id"] for g in grupos.values()])

        itens = []

        for g in grupos.values():
            if not g["vencidos"]:
                continue

            venc_datas = [v for v, _ in g["vencidos"]]
            desde = min(venc_datas)
            futuros = [v for v, _ in g["a_vencer"]]

            por_contrato = {}
            for v, ln in g["vencidos"]:
                cid = ln.get("plano_id")
                c = por_contrato.setdefault(cid, {
                    "contrato_id": cid,
                    "tipo": ln.get("contrato_tipo"),
                    "nome": ln.get("contrato_nome"),
                    "valor_vencido": Decimal("0"),
                    "qtd": 0,
                    "vencido_desde": v,
                })
                c["valor_vencido"] += _dec(ln.get("valor"))
                c["qtd"] += 1
                c["vencido_desde"] = min(c["vencido_desde"], v)

            nome = nomes.get(g["paciente_id"]) if g["paciente_id"] is not None else None

            itens.append({
                "paciente_id": g["paciente_id"],
                "paciente_nome": nome or g["cliente_nome"],
                "valor_vencido": _r2(sum((_dec(ln.get("valor")) for _, ln in g["vencidos"]), Decimal("0"))),
                "qtd_vencidos": len(g["vencidos"]),
                "vencido_desde": desde.isoformat(),
                "dias_atraso_max": (hoje - desde).days,
                "proximo_vencimento": min(futuros).isoformat() if futuros else None,
                "valor_a_vencer": _r2(sum((_dec(ln.get("valor")) for _, ln in g["a_vencer"]), Decimal("0"))),
                "contratos": [
                    {**c, "valor_vencido": _r2(c["valor_vencido"]), "vencido_desde": c["vencido_desde"].isoformat()}
                    for c in sorted(por_contrato.values(), key=lambda c: c["vencido_desde"])
                ],
                "lancamentos": [
                    {
                        "id": ln["id"],
                        "descricao": ln.get("descricao"),
                        "valor": _r2(_dec(ln.get("valor"))),
                        "vencimento": v.isoformat(),
                        "status": ln.get("status"),
                        "contrato_id": ln.get("plano_id"),
                    }
                    for v, ln in sorted(g["vencidos"], key=lambda t: t[0])
                ],
            })

        itens.sort(key=lambda i: (-i["valor_vencido"], i["vencido_desde"]))
        total = _r2(sum((_dec(i["valor_vencido"]) for i in itens), Decimal("0")))

        return _ok(
            hoje=hoje.isoformat(),
            total_vencido=total,
            qtd_pacientes=len(itens),
            sem_vencimento_valido=sem_venc,
            truncado=len(itens) > limite,
            items=itens[:limite],
            observacoes=[
                "Só receitas (tipo 'entrada') não pagas e não canceladas com vencimento anterior a hoje.",
                "'proximo_vencimento' = menor vencimento ainda não vencido e não pago do mesmo paciente (nulo se não houver).",
                "Lançamentos sem vencimento em formato AAAA-MM-DD não entram (ver sem_vencimento_valido).",
            ],
        )

    except Exception as e:
        return _fail(f"Erro ao montar inadimplência: {e}", 500)

    finally:
        conn.close()
