# documentos/routes.py
"""Rotas dos documentos do atendimento. TODA consulta filtra por clinica_id (da sessao) e por atendimento_id."""
from __future__ import annotations

import json
import re
from datetime import date, datetime

from flask import abort, jsonify, render_template, request, session, url_for

from . import documentos_bp
from .cid import descricao_oficial
from .schema import ensure_documentos_schema, invalidar_schema
from .validacao import TIPOS, valida_documento
from atendimentos.helpers import _row_get, has_table, table_columns
from db import conectar_db

try:
    from admin.modulos import require_permission
except Exception:  # pragma: no cover
    def require_permission(modulo_codigo: str, acao: str = "ver"):
        def deco(fn):
            return fn
        return deco

try:
    from log import registrar_log, log_erro
except Exception:  # pragma: no cover
    def registrar_log(*a, **k): pass
    def log_erro(*a, **k): pass

MODULO = "atendimentos"   # mesma permissao do atendimento: quem acessa o atendimento emite documentos (decisao desta rodada)
STATUS_EMITIDO, STATUS_CANCELADO = "emitido", "cancelado"


# ============================================================================ contexto
def _clinica_id() -> int:
    try:
        return int(session.get("clinica_id"))
    except (TypeError, ValueError):
        abort(403)


def _usuario_id() -> int | None:
    for k in ("usuario_id", "user_id", "id"):
        try:
            return int(session[k])
        except (KeyError, TypeError, ValueError):
            continue
    return None


def _iso(v) -> str:
    if v is None:
        return ""
    try:
        return v.isoformat(timespec="seconds")
    except Exception:
        return str(v)


def _json_erro(msg: str, status: int = 400, **extra):
    return jsonify(ok=False, error=msg, erro=msg, **extra), status


def _like(q: str) -> str:
    """Escapa % _ \\ para busca ILIKE literal."""
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


# ============================================================================ consultas de apoio
def _atendimento(conn, atendimento_id: int, clinica_id: int) -> dict | None:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, paciente_id, data_atendimento, nome, status, profissional_id, nome_profissional
          FROM atendimentos
         WHERE id = %s AND clinica_id = %s
         LIMIT 1
        """,
        (atendimento_id, clinica_id),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "id": _row_get(row, "id", 0),
        "paciente_id": _row_get(row, "paciente_id", 1),
        "data_atendimento": _row_get(row, "data_atendimento", 2),
        "nome": _row_get(row, "nome", 3, "") or "",
        "status": _row_get(row, "status", 4, "") or "",
        "profissional_id": _row_get(row, "profissional_id", 5),
        "nome_profissional": _row_get(row, "nome_profissional", 6, "") or "",
    }


def _paciente_snapshot(conn, atend: dict, clinica_id: int) -> dict:
    snap = {"id": atend["paciente_id"], "nome": atend["nome"], "nascimento": "", "cpf": "", "cns": "", "prontuario": ""}
    if not atend.get("paciente_id") or not has_table(conn, "pacientes"):
        return snap
    cols = table_columns(conn, "pacientes")
    sel = [c for c in ("nome", "nascimento", "cpf", "cns", "prontuario") if c in cols]
    if not sel:
        return snap
    filtro = " AND clinica_id = %s" if "clinica_id" in cols else ""
    params = [atend["paciente_id"]] + ([clinica_id] if filtro else [])
    cur = conn.cursor()
    cur.execute(f"SELECT {', '.join(sel)} FROM pacientes WHERE id = %s{filtro} LIMIT 1", params)
    row = cur.fetchone()
    if row:
        for i, c in enumerate(sel):
            v = _row_get(row, c, i, "")
            snap[c] = str(v).strip() if v is not None else ""
    return snap


def _profissional_snapshot(conn, usuario_id: int | None, clinica_id: int) -> dict:
    snap = {"id": usuario_id, "nome": "", "conselho": "", "registro": "", "uf": "", "cbo": "", "cbo_descricao": ""}
    if not usuario_id or not has_table(conn, "usuarios"):
        return snap
    cols = table_columns(conn, "usuarios")
    mapa = {"nome": "nome", "conselho": "conselho", "registro_conselho": "registro", "uf_conselho": "uf", "cbo": "cbo", "cbo_descricao": "cbo_descricao"}
    sel = [c for c in mapa if c in cols]
    if not sel:
        return snap
    filtro = " AND clinica_id = %s" if "clinica_id" in cols else ""
    params = [usuario_id] + ([clinica_id] if filtro else [])
    cur = conn.cursor()
    cur.execute(f"SELECT {', '.join(sel)} FROM usuarios WHERE id = %s{filtro} LIMIT 1", params)
    row = cur.fetchone()
    if row:
        for i, c in enumerate(sel):
            v = _row_get(row, c, i, "")
            snap[mapa[c]] = str(v).strip() if v is not None else ""
    return snap


def _confere_exames(conn, conteudo: dict) -> list[str]:
    """Exame com codigo SIGTAP: confere no catalogo e usa a descricao OFICIAL. Sem codigo = texto livre (nao bloqueia)."""
    erros: list[str] = []
    com_codigo = [e for e in conteudo.get("exames", []) if e.get("procedimento_codigo")]
    if not com_codigo:
        return erros
    if not has_table(conn, "procedimentos"):
        return ["Catálogo de procedimentos indisponível: informe o exame sem código (texto livre)."]
    cur = conn.cursor()
    for i, e in enumerate(conteudo["exames"], 1):
        if not e.get("procedimento_codigo"):
            continue
        cur.execute(
            "SELECT descricao FROM procedimentos WHERE codigo = %s ORDER BY competencia DESC NULLS LAST LIMIT 1",
            (e["procedimento_codigo"],),
        )
        row = cur.fetchone()
        if not row:
            erros.append(f"Exame {i}: o procedimento {e['procedimento_codigo']} não existe no catálogo.")
        else:
            e["descricao"] = (_row_get(row, "descricao", 0, "") or e["descricao"]).strip() or e["descricao"]
    return erros


def _resumo(tipo: str, c: dict) -> str:
    """Texto curto para a lista."""
    if tipo == "receita":
        nomes = [i.get("medicamento", "") for i in c.get("itens", [])]
        return ", ".join(nomes[:3]) + (f" e mais {len(nomes) - 3}" if len(nomes) > 3 else "")
    if tipo == "atestado":
        if c.get("modalidade") == "afastamento":
            return f"Afastamento de {c.get('dias')} dia(s)"
        return "Comparecimento"
    if tipo == "declaracao":
        return c.get("finalidade") or (c.get("texto", "")[:80])
    if tipo == "encaminhamento":
        return f"Para {c.get('especialidade_destino', '')}"
    if tipo == "solicitacao_exame":
        nomes = [e.get("descricao", "") for e in c.get("exames", [])]
        return ", ".join(nomes[:3]) + (f" e mais {len(nomes) - 3}" if len(nomes) > 3 else "")
    return ""


def _linha_para_dict(row, completo: bool = False) -> dict:
    g = lambda k, i, d="": _row_get(row, k, i, d)
    tipo = g("tipo", 4)
    conteudo = g("conteudo", 6, {}) or {}
    if isinstance(conteudo, str):
        conteudo = json.loads(conteudo or "{}")
    d = {
        "id": g("id", 0), "atendimento_id": g("atendimento_id", 1), "paciente_id": g("paciente_id", 2), "status": g("status", 3),
        "tipo": tipo, "rotulo": TIPOS.get(tipo, {}).get("rotulo", tipo), "titulo": g("titulo", 5),
        "cid_codigo": g("cid_codigo", 7), "cid_descricao": g("cid_descricao", 8),
        "emitido_em": _iso(g("emitido_em", 9, None)), "cancelado_em": _iso(g("cancelado_em", 10, None)),
        "cancelado_motivo": g("cancelado_motivo", 11), "resumo": _resumo(tipo, conteudo),
    }
    if completo:
        ps, fs = g("paciente_snapshot", 12, {}) or {}, g("profissional_snapshot", 13, {}) or {}
        d["conteudo"] = conteudo
        d["paciente"] = json.loads(ps) if isinstance(ps, str) else ps
        d["profissional"] = json.loads(fs) if isinstance(fs, str) else fs
    return d


COLS_DOC = ("id, atendimento_id, paciente_id, status, tipo, titulo, conteudo, cid_codigo, cid_descricao, "
            "emitido_em, cancelado_em, cancelado_motivo, paciente_snapshot, profissional_snapshot")


def _doc(conn, atendimento_id: int, doc_id: int, clinica_id: int):
    cur = conn.cursor()
    cur.execute(
        f"SELECT {COLS_DOC} FROM documentos_atendimento WHERE id = %s AND atendimento_id = %s AND clinica_id = %s LIMIT 1",
        (doc_id, atendimento_id, clinica_id),
    )
    return cur.fetchone()


# ============================================================================ buscas (autocomplete)
@documentos_bp.get("/api/cid10/buscar")
@require_permission(MODULO, "ver")
def buscar_cid10():
    """CID e OPCIONAL na emissao: base nao importada / tabela inexistente = lista vazia (nao e erro)."""
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify(ok=True, items=[])
    try:
        with conectar_db() as conn:
            if not has_table(conn, "cid_catalogo"):
                return jsonify(ok=True, items=[])
            cur = conn.cursor()
            cur.execute(
                """
                SELECT co_cid, no_cid
                  FROM cid_catalogo
                 WHERE co_cid ILIKE %s ESCAPE '\\' OR COALESCE(no_cid, '') ILIKE %s ESCAPE '\\'
                 ORDER BY (REPLACE(UPPER(co_cid), '.', '') = REPLACE(UPPER(%s), '.', '')) DESC,
                          (co_cid ILIKE %s ESCAPE '\\') DESC, co_cid
                 LIMIT 20
                """,
                (_like(q), _like(q), q, _like(q)[1:]),   # [1:] = prefixo: "q%"
            )
            rows = cur.fetchall() or []
        itens = [{"codigo": _row_get(r, "co_cid", 0, ""), "descricao": _row_get(r, "no_cid", 1, "") or ""} for r in rows]
        for it in itens:
            it["label"] = f"{it['codigo']} - {it['descricao']}"
        return jsonify(ok=True, items=itens)
    except Exception as e:
        log_erro(MODULO, e, entidade="cid_catalogo", descricao="Erro ao buscar CID para documento.", detalhes={})
        return _json_erro("Não foi possível buscar o CID agora.", 500, items=[])


@documentos_bp.get("/api/procedimentos/buscar")
@require_permission(MODULO, "ver")
def buscar_procedimentos():
    """Catalogo SIGTAP (tabela `procedimentos`, a mesma do modulo de procedimentos): ultima competencia de cada codigo.
    `grupo` (ex.: 02 = diagnostico) filtra pelo prefixo do codigo."""
    q = (request.args.get("q") or "").strip()
    grupo = re.sub(r"\D", "", request.args.get("grupo") or "")[:2]
    if len(q) < 2:
        return jsonify(ok=True, items=[])
    try:
        with conectar_db() as conn:
            if not has_table(conn, "procedimentos"):
                return jsonify(ok=True, items=[])
            cur = conn.cursor()
            cur.execute(
                """
                SELECT codigo, descricao FROM (
                    SELECT DISTINCT ON (codigo) codigo, descricao, competencia
                      FROM procedimentos
                     WHERE COALESCE(codigo, '') <> ''
                       AND (codigo ILIKE %s ESCAPE '\\' OR COALESCE(descricao, '') ILIKE %s ESCAPE '\\')
                       AND (%s = '' OR codigo LIKE %s)
                     ORDER BY codigo, competencia DESC NULLS LAST
                ) t
                ORDER BY (codigo = %s) DESC, descricao
                LIMIT 20
                """,
                (_like(q), _like(q), grupo, grupo + "%", q),
            )
            rows = cur.fetchall() or []
        itens = [{"codigo": _row_get(r, "codigo", 0, ""), "descricao": _row_get(r, "descricao", 1, "") or ""} for r in rows]
        for it in itens:
            it["label"] = f"{it['codigo']} - {it['descricao']}"
        return jsonify(ok=True, items=itens)
    except Exception as e:
        log_erro(MODULO, e, entidade="procedimentos", descricao="Erro ao buscar procedimento para documento.", detalhes={})
        return _json_erro("Não foi possível buscar procedimentos agora.", 500, items=[])


# ============================================================================ pagina do atendimento
@documentos_bp.get("/atendimentos/<int:atendimento_id>/documentos")
@require_permission(MODULO, "ver")
def pagina_documentos(atendimento_id: int):
    clinica_id = _clinica_id()
    try:
        with conectar_db() as conn:
            ensure_documentos_schema(conn)
            atend = _atendimento(conn, atendimento_id, clinica_id)
            if not atend:
                abort(404)
            paciente = _paciente_snapshot(conn, atend, clinica_id)
    except Exception as e:
        if getattr(e, "code", None) in (404, 403):
            raise
        invalidar_schema()
        log_erro(MODULO, e, entidade="documentos_atendimento", descricao="Erro ao abrir documentos do atendimento.", detalhes={"atendimento_id": atendimento_id})
        return "Não foi possível abrir os documentos deste atendimento agora.", 500

    return render_template(
        "documentos_atendimento.html",
        atendimento=atend, paciente=paciente, data_atendimento=_iso(atend["data_atendimento"])[:10],
        tipos=[{"valor": k, "rotulo": v["rotulo"]} for k, v in TIPOS.items()],
        pode_editar=True,
    )


@documentos_bp.get("/atendimentos/<int:atendimento_id>/documentos/api")
@require_permission(MODULO, "ver")
def listar_documentos(atendimento_id: int):
    clinica_id = _clinica_id()
    try:
        with conectar_db() as conn:
            ensure_documentos_schema(conn)
            if not _atendimento(conn, atendimento_id, clinica_id):
                return _json_erro("Atendimento não encontrado.", 404)
            cur = conn.cursor()
            cur.execute(
                f"SELECT {COLS_DOC} FROM documentos_atendimento WHERE atendimento_id = %s AND clinica_id = %s ORDER BY emitido_em DESC, id DESC",
                (atendimento_id, clinica_id),
            )
            itens = [_linha_para_dict(r) for r in (cur.fetchall() or [])]
        return jsonify(ok=True, items=itens)
    except Exception as e:
        invalidar_schema()
        log_erro(MODULO, e, entidade="documentos_atendimento", descricao="Erro ao listar documentos.", detalhes={"atendimento_id": atendimento_id})
        return _json_erro("Não foi possível listar os documentos agora.", 500)


@documentos_bp.post("/atendimentos/<int:atendimento_id>/documentos")
@require_permission(MODULO, "editar")
def criar_documento(atendimento_id: int):
    clinica_id, usuario_id = _clinica_id(), _usuario_id()
    payload = request.get_json(silent=True)
    try:
        with conectar_db() as conn:
            ensure_documentos_schema(conn)
            atend = _atendimento(conn, atendimento_id, clinica_id)
            if not atend:
                return _json_erro("Atendimento não encontrado.", 404)

            ctx = {"data_atendimento": _iso(atend["data_atendimento"])[:10] or date.today().isoformat()}
            doc, erros = valida_documento(payload, ctx)
            if doc is None:
                return _json_erro(erros[0], 400, erros=erros)

            # CID: se o catalogo conhece o codigo, a descricao oficial vence a do navegador
            cid = doc["cid"]
            if cid:
                oficial = descricao_oficial(conn, cid["codigo"])
                if oficial:
                    cid["descricao"] = oficial
            if doc["tipo"] == "solicitacao_exame":
                erros = _confere_exames(conn, doc["conteudo"])
                if erros:
                    return _json_erro(erros[0], 400, erros=erros)

            paciente = _paciente_snapshot(conn, atend, clinica_id)
            profissional = _profissional_snapshot(conn, usuario_id, clinica_id)
            if not profissional["nome"]:
                return _json_erro("Não foi possível identificar o profissional que está emitindo. Faça login novamente.", 400)

            titulo = TIPOS[doc["tipo"]]["titulo"]
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO documentos_atendimento
                    (clinica_id, atendimento_id, paciente_id, profissional_id, tipo, titulo, conteudo,
                     cid_codigo, cid_descricao, paciente_snapshot, profissional_snapshot, status, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
                RETURNING id, emitido_em
                """,
                (clinica_id, atendimento_id, atend["paciente_id"], usuario_id, doc["tipo"], titulo,
                 json.dumps(doc["conteudo"], ensure_ascii=False), cid["codigo"] if cid else None, cid["descricao"] if cid else None,
                 json.dumps(paciente, ensure_ascii=False), json.dumps(profissional, ensure_ascii=False), STATUS_EMITIDO, usuario_id),
            )
            row = cur.fetchone()
            conn.commit()
            doc_id = _row_get(row, "id", 0)

        # log SEM dados do paciente: so ids e tipo
        registrar_log(modulo=MODULO, acao="criar", entidade="documentos_atendimento", entidade_id=doc_id,
                      descricao="Emitiu documento do atendimento.",
                      detalhes={"clinica_id": clinica_id, "atendimento_id": atendimento_id, "tipo": doc["tipo"]})
        return jsonify(ok=True, id=doc_id, tipo=doc["tipo"],
                       imprimir=url_for("documentos.imprimir_documento", atendimento_id=atendimento_id, doc_id=doc_id))
    except Exception as e:
        invalidar_schema()
        log_erro(MODULO, e, entidade="documentos_atendimento", descricao="Erro ao emitir documento.", detalhes={"atendimento_id": atendimento_id})
        return _json_erro("Não foi possível emitir o documento agora. Tente novamente.", 500)


@documentos_bp.get("/atendimentos/<int:atendimento_id>/documentos/<int:doc_id>")
@require_permission(MODULO, "ver")
def ver_documento(atendimento_id: int, doc_id: int):
    clinica_id = _clinica_id()
    try:
        with conectar_db() as conn:
            ensure_documentos_schema(conn)
            row = _doc(conn, atendimento_id, doc_id, clinica_id)
        if not row:
            return _json_erro("Documento não encontrado.", 404)
        return jsonify(ok=True, documento=_linha_para_dict(row, completo=True))
    except Exception as e:
        invalidar_schema()
        log_erro(MODULO, e, entidade="documentos_atendimento", descricao="Erro ao ver documento.", detalhes={"atendimento_id": atendimento_id, "doc_id": doc_id})
        return _json_erro("Não foi possível abrir o documento agora.", 500)


def _fmt_data(s: str) -> str:
    try:
        return date.fromisoformat((s or "")[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return s or ""


def _fmt_datahora(s: str) -> str:
    try:
        return datetime.fromisoformat(s).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return s or ""


@documentos_bp.get("/atendimentos/<int:atendimento_id>/documentos/<int:doc_id>/imprimir")
@require_permission(MODULO, "ver")
def imprimir_documento(atendimento_id: int, doc_id: int):
    """Pagina HTML simples para impressao pelo navegador (@media print). Sem PDF e sem timbre nesta rodada."""
    clinica_id = _clinica_id()
    try:
        with conectar_db() as conn:
            ensure_documentos_schema(conn)
            row = _doc(conn, atendimento_id, doc_id, clinica_id)
    except Exception as e:
        invalidar_schema()
        log_erro(MODULO, e, entidade="documentos_atendimento", descricao="Erro ao imprimir documento.", detalhes={"atendimento_id": atendimento_id, "doc_id": doc_id})
        return "Não foi possível abrir o documento agora.", 500
    if not row:
        abort(404)

    d = _linha_para_dict(row, completo=True)
    registrar_log(modulo=MODULO, acao="imprimir", entidade="documentos_atendimento", entidade_id=doc_id,
                  descricao="Abriu documento para impressão.", detalhes={"clinica_id": clinica_id, "atendimento_id": atendimento_id, "tipo": d["tipo"]})
    return render_template(
        "documento_imprimir.html", d=d, clinica_nome=session.get("clinica_nome") or "",
        emitido_fmt=_fmt_datahora(d["emitido_em"]), cancelado_fmt=_fmt_datahora(d["cancelado_em"]), fmt_data=_fmt_data,
        auto_imprimir=request.args.get("auto") == "1",
    )


@documentos_bp.post("/atendimentos/<int:atendimento_id>/documentos/<int:doc_id>/cancelar")
@require_permission(MODULO, "editar")
def cancelar_documento(atendimento_id: int, doc_id: int):
    """Soft-delete: o registro NUNCA e apagado (documento medico), so muda para 'cancelado'."""
    clinica_id, usuario_id = _clinica_id(), _usuario_id()
    data = request.get_json(silent=True) or {}
    motivo = str(data.get("motivo") or "").strip()
    if len(motivo) > 500:
        return _json_erro("Motivo: no máximo 500 caracteres.", 400)
    try:
        with conectar_db() as conn:
            ensure_documentos_schema(conn)
            row = _doc(conn, atendimento_id, doc_id, clinica_id)
            if not row:
                return _json_erro("Documento não encontrado.", 404)
            if _row_get(row, "status", 3) == STATUS_CANCELADO:
                return _json_erro("Este documento já está cancelado.", 409)
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE documentos_atendimento
                   SET status = 'cancelado', cancelado_em = CURRENT_TIMESTAMP, cancelado_por = %s,
                       cancelado_motivo = %s, updated_at = CURRENT_TIMESTAMP
                 WHERE id = %s AND atendimento_id = %s AND clinica_id = %s AND status = 'emitido'
                """,
                (usuario_id, motivo or None, doc_id, atendimento_id, clinica_id),
            )
            alterou = cur.rowcount
            conn.commit()
        if not alterou:
            return _json_erro("Este documento já está cancelado.", 409)
        registrar_log(modulo=MODULO, acao="cancelar", entidade="documentos_atendimento", entidade_id=doc_id,
                      descricao="Cancelou documento do atendimento.",
                      detalhes={"clinica_id": clinica_id, "atendimento_id": atendimento_id, "com_motivo": bool(motivo)})
        return jsonify(ok=True, id=doc_id, status=STATUS_CANCELADO)
    except Exception as e:
        invalidar_schema()
        log_erro(MODULO, e, entidade="documentos_atendimento", descricao="Erro ao cancelar documento.", detalhes={"atendimento_id": atendimento_id, "doc_id": doc_id})
        return _json_erro("Não foi possível cancelar o documento agora.", 500)
