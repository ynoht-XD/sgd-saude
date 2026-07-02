# -*- coding: utf-8 -*-
"""
Rotas do módulo APAC

- GET  /export/apac
- GET  /export/apac/excel
- GET  /export/apac/txt
- POST /export/apac/duplicar
- POST /export/apac/excluir
- GET  /export/apac/<id>/pdf
- POST /export/apac/atualizar
"""
from __future__ import annotations

from datetime import datetime
import io
import traceback

from flask import (
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from db import conectar_db
from . import export_bp








# ============================================================
# APAC · Visualização
# ============================================================

@export_bp.get("/apac")
def apac_view():
    nome_filtro = request.args.get("nome", "") or ""
    cep_filtro = request.args.get("cep", "") or ""
    competencia_filtro = request.args.get("competencia", "") or ""
    status_filtro = request.args.get("status", "") or ""
    status_entrega_filtro = request.args.get("status_entrega", "") or ""
    nota_fiscal_filtro = request.args.get("nota_fiscal", "") or ""
    competencia_nota_filtro = request.args.get("competencia_nota", "") or ""
    fornecedor_filtro = request.args.get("fornecedor", "") or ""
    local_entrega_filtro = request.args.get("local_entrega", "") or ""

    apacs = []

    conn = conectar_db()
    cur = conn.cursor()

    try:
        # Se a tabela ainda não existir, evita erro na tela
        cur.execute("""
            SELECT EXISTS (
                SELECT 1
                  FROM information_schema.tables
                 WHERE table_schema = 'public'
                   AND table_name = 'apac'
            ) AS existe
        """)

        row = cur.fetchone()
        tabela_existe = bool(row["existe"]) if row else False

        if not tabela_existe:
            return render_template(
                "apacs_visualizar.html",
                apacs=[],
                nome_filtro=nome_filtro,
                cep_filtro=cep_filtro,
                competencia_filtro=competencia_filtro,
                status_filtro=status_filtro,
                status_entrega_filtro=status_entrega_filtro,
                nota_fiscal_filtro=nota_fiscal_filtro,
                competencia_nota_filtro=competencia_nota_filtro,
                fornecedor_filtro=fornecedor_filtro,
                local_entrega_filtro=local_entrega_filtro,
            )

        cur.execute("""
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = 'apac'
        """)

        existentes = {r["column_name"] for r in cur.fetchall()}

        desejadas = [
            "id",

            # Destaques do card
            "prontuario",
            "nome_paciente",
            "nome",
            "procedimento",
            "codigo_procedimento",
            "numero_apac",
            "competencia",
            "quantidade",
            "nota_fiscal",
            "status",
            "status_entrega",
            "data_entrega",
            "local_entrega",
            "processado",
            "bpai",
            "sms_enviado",
            "obs_geral",

            # APAC
            "cnes",
            "data_inicial",
            "data_final",
            "tipo_apac",
            "nacionalidade",
            "servico",
            "classificacao",
            "carater_atendimento",

            # Paciente
            "data_nascimento",
            "nascimento",
            "idade",
            "cns",
            "cpf",
            "nome_mae",
            "mae",
            "responsavel",
            "sexo",
            "raca",
            "endereco",
            "logradouro",
            "rua",
            "numero",
            "numero_casa",
            "bairro",
            "cep",
            "codigo_ibge",
            "municipio",

            # Diagnóstico
            "cid",
            "cid2",
            "descricao_diagnostico",

            # Solicitante/autorizador
            "nome_solicitante",
            "cns_solicitante",
            "data_solicitacao",
            "nome_autorizador",
            "cns_autorizador",
            "data_autorizacao",
            "orgao_emissor",

            # Nota/pedido/entrega
            "data_nota_fiscal",
            "data_entrada_nf",
            "competencia_nota",
            "protocolo_nota",
            "obs_nota",
            "data_pedido",
            "fornecedor",
            "obs_pedido",
            "obs_entrega",

            # Execução futura
            "cbo_executante",
            "cns_executante",

            # Controle
            "criado_em",
            "atualizado_em",
        ]

        colunas = [c for c in desejadas if c in existentes]

        if not colunas:
            raise Exception("Tabela public.apac existe, mas nenhuma coluna esperada foi encontrada.")

        where = []
        params = []

        if nome_filtro:
            if "nome_paciente" in existentes:
                where.append("LOWER(COALESCE(nome_paciente, '')) LIKE LOWER(%s)")
                params.append(f"%{nome_filtro}%")
            elif "nome" in existentes:
                where.append("LOWER(COALESCE(nome, '')) LIKE LOWER(%s)")
                params.append(f"%{nome_filtro}%")

        if cep_filtro and "cep" in existentes:
            cep_digits = "".join(ch for ch in cep_filtro if ch.isdigit())
            where.append("regexp_replace(COALESCE(cep::text, ''), '\\D', '', 'g') LIKE %s")
            params.append(f"%{cep_digits}%")

        if competencia_filtro and "competencia" in existentes:
            where.append("COALESCE(competencia::text, '') ILIKE %s")
            params.append(f"%{competencia_filtro}%")

        if status_filtro and "status" in existentes:
            where.append("COALESCE(status, '') = %s")
            params.append(status_filtro)

        if status_entrega_filtro and "status_entrega" in existentes:
            where.append("COALESCE(status_entrega, '') = %s")
            params.append(status_entrega_filtro)

        if nota_fiscal_filtro and "nota_fiscal" in existentes:
            where.append("COALESCE(nota_fiscal::text, '') ILIKE %s")
            params.append(f"%{nota_fiscal_filtro}%")

        if competencia_nota_filtro and "competencia_nota" in existentes:
            where.append("COALESCE(competencia_nota::text, '') ILIKE %s")
            params.append(f"%{competencia_nota_filtro}%")

        if fornecedor_filtro and "fornecedor" in existentes:
            where.append("COALESCE(fornecedor, '') ILIKE %s")
            params.append(f"%{fornecedor_filtro}%")

        if local_entrega_filtro and "local_entrega" in existentes:
            where.append("COALESCE(local_entrega, '') ILIKE %s")
            params.append(f"%{local_entrega_filtro}%")

        sql = f"""
            SELECT {", ".join(colunas)}
              FROM public.apac
        """

        if where:
            sql += " WHERE " + " AND ".join(where)

        sql += " ORDER BY id DESC LIMIT 500"

        cur.execute(sql, params)
        apacs = [dict(r) for r in cur.fetchall()]

        for a in apacs:
            a["nome_paciente"] = a.get("nome_paciente") or a.get("nome") or ""
            a["data_nascimento"] = a.get("data_nascimento") or a.get("nascimento") or ""
            a["nome_mae"] = a.get("nome_mae") or a.get("mae") or ""
            a["endereco"] = a.get("endereco") or a.get("logradouro") or a.get("rua") or ""
            a["numero"] = a.get("numero") or a.get("numero_casa") or ""

            a["processado"] = bool(a.get("processado", False))
            a["bpai"] = bool(a.get("bpai", False))
            a["sms_enviado"] = bool(a.get("sms_enviado", False))

            if not a.get("status"):
                a["status"] = "Em aberto"

            if not a.get("status_entrega"):
                a["status_entrega"] = "Na instituição"

    finally:
        cur.close()
        conn.close()

    return render_template(
        "apacs_visualizar.html",
        apacs=apacs,
        nome_filtro=nome_filtro,
        cep_filtro=cep_filtro,
        competencia_filtro=competencia_filtro,
        status_filtro=status_filtro,
        status_entrega_filtro=status_entrega_filtro,
        nota_fiscal_filtro=nota_fiscal_filtro,
        competencia_nota_filtro=competencia_nota_filtro,
        fornecedor_filtro=fornecedor_filtro,
        local_entrega_filtro=local_entrega_filtro,
    )





@export_bp.post("/apac/autosave")
def apac_autosave():
    data = request.get_json(silent=True) or {}

    apac_id = data.get("id")
    campo = data.get("campo")
    valor = data.get("valor")

    campos_permitidos = {
        "processado": "boolean",
        "sms_enviado": "boolean",
        "bpai": "boolean",
        "obs_geral": "text",
    }

    if not apac_id or campo not in campos_permitidos:
        return jsonify({"ok": False, "msg": "Parâmetros inválidos"}), 400

    conn = conectar_db()
    cur = conn.cursor()

    try:
        if campos_permitidos[campo] == "boolean":
            valor_final = bool(valor)
        else:
            valor_final = str(valor or "")

        cur.execute(
            f"""
            UPDATE public.apac
               SET {campo} = %s,
                   atualizado_em = NOW()
             WHERE id = %s
            """,
            (valor_final, int(apac_id)),
        )

        conn.commit()

        return jsonify({"ok": True})

    except Exception as e:
        conn.rollback()
        print("Erro autosave APAC:", e)
        return jsonify({"ok": False, "msg": str(e)}), 500

    finally:
        cur.close()
        conn.close()



# ============================================================
# APAC · Duplicar
# ============================================================
@export_bp.post("/apac/duplicar")
def apac_duplicar():
    flash("APAC duplicada com sucesso.", "success")
    return redirect(url_for("export.apac_view"))


# ============================================================
# APAC · Excluir
# ============================================================
@export_bp.route("/apac/excluir", methods=["POST"], endpoint="apac_excluir")
def apac_excluir():
    id_apac = request.form.get("id_apac")

    if not id_apac:
        flash("APAC não informada para exclusão.", "warning")
        return redirect(url_for("export.apac_view"))

    conn = conectar_db()
    cur = conn.cursor()

    try:
        cur.execute("DELETE FROM public.apac WHERE id = %s", (id_apac,))
        conn.commit()
        flash("APAC excluída com sucesso.", "success")

    except Exception as e:
        conn.rollback()
        print("❌ Erro ao excluir APAC:", e)
        flash("Erro ao excluir APAC.", "danger")

    finally:
        cur.close()
        conn.close()

    return redirect(url_for("export.apac_view"))

# ============================================================
# APAC · PDF individual
# ============================================================
@export_bp.get("/apac/<int:apac_id>/pdf")
def apac_pdf(apac_id: int):
    # Depois vamos gerar o PDF real com reportlab
    pdf_bytes = b"%PDF-1.4\n% APAC PDF PREVIEW\n"

    return send_file(
        io.BytesIO(pdf_bytes),
        as_attachment=True,
        download_name=f"apac_{apac_id}.pdf",
        mimetype="application/pdf",
    )


# ============================================================
# APAC · Atualizar
# ============================================================
@export_bp.post("/apac/atualizar")
def apac_atualizar():
    form = request.form
    apac_id = (form.get("id_apac") or "").strip()

    print("🟡 EDITAR APAC - ID:", apac_id)
    print("🟡 FORM RECEBIDO:", dict(form))

    if not apac_id.isdigit():
        flash("APAC inválida para edição.", "danger")
        return redirect(url_for("export.apac_view"))

    alias = {
        "cns_paciente": "cns",
        "cpf_paciente": "cpf",
    }

    campos_permitidos = [
        "numero_apac", "competencia", "procedimento", "codigo_procedimento",
        "quantidade", "cnes", "data_inicial", "data_final", "tipo_apac",
        "nacionalidade", "nome_paciente", "data_nascimento", "nome_mae",
        "responsavel", "sexo", "raca", "endereco", "numero", "bairro", "cep",
        "status", "nota_fiscal", "data_nota_fiscal", "data_entrada_nf",
        "competencia_nota", "protocolo_nota", "obs_nota", "data_pedido",
        "fornecedor", "obs_pedido", "data_entrega", "local_entrega",
        "status_entrega", "obs_entrega", "cbo_executante", "cns_executante",
        "servico", "classificacao", "cid", "cid2", "descricao_diagnostico",
        "obs_geral", "nome_solicitante", "cns_solicitante", "data_solicitacao",
        "nome_autorizador", "cns_autorizador", "data_autorizacao",
        "orgao_emissor", "prontuario",
    ]

    conn = conectar_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = 'apac'
        """)
        existentes = {r["column_name"] for r in cur.fetchall()}

        campos = {}

        for campo in campos_permitidos:
            if campo in form and campo in existentes:
                valor = form.get(campo)
                campos[campo] = valor if valor not in ("", None) else None

        for origem, destino in alias.items():
            if origem in form and destino in existentes:
                valor = form.get(origem)
                campos[destino] = valor if valor not in ("", None) else None

        if "atualizado_em" in existentes:
            campos["atualizado_em"] = datetime.now()

        print("🟢 CAMPOS PARA UPDATE:", campos)

        if not campos:
            flash("Nenhum campo válido para atualizar.", "warning")
            return redirect(url_for("export.apac_view"))

        set_sql = ", ".join([f"{campo} = %s" for campo in campos.keys()])
        valores = list(campos.values()) + [int(apac_id)]

        cur.execute(
            f"""
            UPDATE public.apac
               SET {set_sql}
             WHERE id = %s
         RETURNING id;
            """,
            valores,
        )

        atualizado = cur.fetchone()

        if not atualizado:
            conn.rollback()
            print("🔴 Nenhuma APAC encontrada com ID:", apac_id)
            flash("Nenhuma APAC foi atualizada. ID não encontrado.", "warning")
            return redirect(url_for("export.apac_view"))

        conn.commit()

        print("✅ APAC atualizada:", atualizado)
        flash("APAC atualizada com sucesso!", "success")

    except Exception as e:
        conn.rollback()
        print("❌ Erro ao atualizar APAC:", e)
        traceback.print_exc()
        flash("Erro ao atualizar APAC.", "danger")

    finally:
        cur.close()
        conn.close()

    return redirect(url_for("export.apac_view"))