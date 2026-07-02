# -*- coding: utf-8 -*-
from __future__ import annotations

import re
import traceback
from typing import Any, Optional

from flask import (
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

try:
    from auth import login_required
except ImportError:
    def login_required(f):
        return f

from db import conectar_db

try:
    from logs import registrar_log
except ImportError:
    def registrar_log(*args, **kwargs):
        return None

from . import export_bp


# =============================================================================
# HELPERS
# =============================================================================

_DIGITS_RE = re.compile(r"\D+")


def _only_digits(s: Any) -> Optional[str]:
    if s is None:
        return None
    v = _DIGITS_RE.sub("", str(s))
    return v or None


def _clean(s: Any) -> Optional[str]:
    if s is None:
        return None
    v = str(s).strip()
    return v if v else None


def tratar_data(valor: Any):
    v = (str(valor).strip() if valor is not None else "")
    return v or None


def to_int_or_none(x: Any) -> Optional[int]:
    if x is None or str(x).strip() == "":
        return None
    try:
        return int(str(x).strip())
    except Exception:
        return None


def normalizar_sexo(valor: Any) -> Optional[str]:
    if valor is None:
        return None

    s = str(valor).strip().upper()

    if not s:
        return None

    if s == "M" or s.startswith("MASC"):
        return "M"

    if s == "F" or s.startswith("FEM"):
        return "F"

    return s[:1]


def _form_text(name: str):
    return _clean(request.form.get(name))


def _form_digits(name: str):
    return _only_digits(request.form.get(name))


def _form_date(name: str):
    return tratar_data(request.form.get(name))


def _form_int(name: str):
    return to_int_or_none(request.form.get(name))


def _get_existing_columns(table_name: str = "apac", schema: str = "public") -> set[str]:
    conn = conectar_db()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = %s
               AND table_name = %s
            """,
            (schema, table_name),
        )

        return {row["column_name"] for row in cur.fetchall()}

    finally:
        cur.close()
        conn.close()


def _filter_existing_columns(campos: dict, table_name: str = "apac") -> dict:
    existentes = _get_existing_columns(table_name)
    return {
        k: v for k, v in campos.items()
        if k in existentes and v is not None
    }




def ensure_apac_table():
    conn = conectar_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS public.apac (
                id SERIAL PRIMARY KEY,

                paciente_id INTEGER,
                clinica_id INTEGER,

                numero_apac TEXT,
                competencia TEXT,
                procedimento TEXT,
                codigo_procedimento TEXT,
                quantidade INTEGER,
                cnes TEXT,
                data_inicial DATE,
                data_final DATE,
                tipo_apac TEXT,
                nacionalidade TEXT,
                servico TEXT,
                classificacao TEXT,
                carater_atendimento TEXT,

                prontuario TEXT,
                nome_paciente TEXT,
                nome TEXT,
                cns TEXT,
                cpf TEXT,
                data_nascimento DATE,
                nascimento DATE,
                idade INTEGER,
                sexo TEXT,
                status TEXT,

                mod TEXT,
                admissao DATE,
                nis TEXT,
                raca TEXT,
                religiao TEXT,
                rg TEXT,
                orgao_rg TEXT,
                estado_civil TEXT,

                logradouro TEXT,
                rua TEXT,
                endereco TEXT,
                codigo_logradouro TEXT,
                cod_logradouro TEXT,
                numero_casa TEXT,
                numero TEXT,
                complemento TEXT,
                bairro TEXT,
                municipio TEXT,
                cidade TEXT,
                uf TEXT,
                cep TEXT,
                codigo_ibge TEXT,

                mae TEXT,
                nome_mae TEXT,
                cpf_mae TEXT,
                rg_mae TEXT,
                rg_ssp_mae TEXT,
                nis_mae TEXT,

                pai TEXT,
                nome_pai TEXT,
                cpf_pai TEXT,
                rg_pai TEXT,
                rg_ssp_pai TEXT,

                telefone1 TEXT,
                telefone2 TEXT,
                telefone3 TEXT,
                telefone TEXT,
                email TEXT,

                responsavel TEXT,
                cpf_responsavel TEXT,
                rg_responsavel TEXT,
                orgao_rg_responsavel TEXT,

                laudos_json TEXT,
                comorbidades_json TEXT,
                cid TEXT,
                cid2 TEXT,
                alergias TEXT,
                aviso TEXT,
                obs_geral TEXT,
                descricao_diagnostico TEXT,

                terapeuta TEXT,
                cbo TEXT,
                cbo_nome TEXT,
                cbo_executante TEXT,
                cns_executante TEXT,

                cns_solicitante TEXT,
                nome_solicitante TEXT,
                data_solicitacao DATE,

                cns_autorizador TEXT,
                nome_autorizador TEXT,
                data_autorizacao DATE,
                orgao_emissor TEXT,

                nota_fiscal TEXT,
                data_nota_fiscal DATE,
                data_entrada_nf DATE,
                competencia_nota TEXT,
                protocolo_nota TEXT,
                obs_nota TEXT,

                data_pedido DATE,
                fornecedor TEXT,
                obs_pedido TEXT,
                data_entrega DATE,
                local_entrega TEXT,
                status_entrega TEXT,
                obs_entrega TEXT,

                motivo_saida TEXT,
                data_alta DATE,

                processado BOOLEAN NOT NULL DEFAULT FALSE,
                bpai BOOLEAN NOT NULL DEFAULT FALSE,
                sms_enviado BOOLEAN NOT NULL DEFAULT FALSE,

                criado_em TIMESTAMP NOT NULL DEFAULT NOW(),
                atualizado_em TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_apac_nome_paciente
            ON public.apac (nome_paciente);
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_apac_competencia
            ON public.apac (competencia);
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_apac_numero_apac
            ON public.apac (numero_apac);
        """)

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        cur.close()
        conn.close()





# =============================================================================
# APAC · CADASTRO
# =============================================================================

@export_bp.route("/apac/cadastro", methods=["GET"])
@login_required
def apac_cadastro():
    return render_template("apac_cadastro.html")


@export_bp.route("/apac/cadastro", methods=["POST"])
@login_required
def apac_salvar():
    conn = None
    cur = None

    try:
        nome_paciente = _form_text("nome_paciente") or _form_text("nome")

        if not nome_paciente:
            flash("Informe o nome do paciente.", "warning")
            return redirect(url_for("export.apac_cadastro"))

        # ---------------------------------------------------------------------
        # Campos principais da APAC + snapshot do paciente
        # ---------------------------------------------------------------------
        campos = {
            # Controle / vínculo paciente
            "paciente_id": _form_int("paciente_id") or _form_int("id"),
            "clinica_id": _form_int("clinica_id"),

            # APAC
            "numero_apac": _form_text("numero_apac"),
            "competencia": _form_text("competencia"),
            "procedimento": _form_text("procedimento"),
            "codigo_procedimento": _form_digits("codigo_procedimento") or _form_text("codigo_procedimento"),
            "quantidade": _form_int("quantidade"),
            "cnes": _form_digits("cnes") or _form_text("cnes"),
            "data_inicial": _form_date("data_inicial"),
            "data_final": _form_date("data_final"),
            "tipo_apac": _form_text("tipo_apac"),
            "nacionalidade": _form_text("nacionalidade"),
            "servico": _form_text("servico"),
            "classificacao": _form_text("classificacao"),
            "carater_atendimento": _form_text("carater_atendimento"),

            # Paciente
            "prontuario": _form_text("prontuario"),
            "nome_paciente": nome_paciente,
            "nome": nome_paciente,
            "cns": _form_digits("cns") or _form_digits("cns_paciente"),
            "cpf": _form_digits("cpf") or _form_digits("cpf_paciente"),
            "data_nascimento": _form_date("data_nascimento") or _form_date("nascimento"),
            "nascimento": _form_date("nascimento") or _form_date("data_nascimento"),
            "idade": _form_int("idade"),
            "sexo": normalizar_sexo(request.form.get("sexo")),
            "status": _form_text("status"),

            # Dados sociais/documentos
            "mod": _form_text("mod"),
            "admissao": _form_date("admissao"),
            "nis": _form_digits("nis"),
            "raca": _form_text("raca"),
            "religiao": _form_text("religiao"),
            "rg": _form_text("rg"),
            "orgao_rg": _form_text("orgao_rg"),
            "estado_civil": _form_text("estado_civil"),

            # Endereço
            "logradouro": _form_text("logradouro"),
            "rua": _form_text("rua") or _form_text("endereco") or _form_text("logradouro"),
            "endereco": _form_text("endereco") or _form_text("logradouro") or _form_text("rua"),
            "codigo_logradouro": _form_text("codigo_logradouro") or _form_text("cod_logradouro"),
            "cod_logradouro": _form_text("cod_logradouro") or _form_text("codigo_logradouro"),
            "numero_casa": _form_text("numero_casa") or _form_text("numero"),
            "numero": _form_text("numero") or _form_text("numero_casa"),
            "complemento": _form_text("complemento"),
            "bairro": _form_text("bairro"),
            "municipio": _form_text("municipio") or _form_text("cidade"),
            "cidade": _form_text("cidade") or _form_text("municipio"),
            "uf": _form_text("uf"),
            "cep": _form_digits("cep"),
            "codigo_ibge": _form_digits("codigo_ibge") or _form_digits("ibge"),

            # Família
            "mae": _form_text("mae") or _form_text("nome_mae"),
            "nome_mae": _form_text("nome_mae") or _form_text("mae"),
            "cpf_mae": _form_digits("cpf_mae"),
            "rg_mae": _form_text("rg_mae"),
            "rg_ssp_mae": _form_text("rg_ssp_mae"),
            "nis_mae": _form_digits("nis_mae"),

            "pai": _form_text("pai") or _form_text("nome_pai"),
            "nome_pai": _form_text("nome_pai") or _form_text("pai"),
            "cpf_pai": _form_digits("cpf_pai"),
            "rg_pai": _form_text("rg_pai"),
            "rg_ssp_pai": _form_text("rg_ssp_pai"),

            # Contato
            "telefone1": _form_text("telefone1") or _form_text("telefone"),
            "telefone2": _form_text("telefone2"),
            "telefone3": _form_text("telefone3"),
            "telefone": _form_text("telefone") or _form_text("telefone1"),
            "email": _form_text("email"),

            # Responsável
            "responsavel": _form_text("responsavel"),
            "cpf_responsavel": _form_digits("cpf_responsavel"),
            "rg_responsavel": _form_text("rg_responsavel"),
            "orgao_rg_responsavel": _form_text("orgao_rg_responsavel"),

            # Laudos / saúde
            "laudos_json": _form_text("laudos_json"),
            "comorbidades_json": _form_text("comorbidades_json"),
            "cid": _form_text("cid"),
            "cid2": _form_text("cid2") or _form_text("cid_secundario"),
            "alergias": _form_text("alergias"),
            "aviso": _form_text("aviso"),
            "obs_geral": _form_text("obs_geral"),
            "descricao_diagnostico": _form_text("descricao_diagnostico"),

            # Profissional / execução futura
            "terapeuta": _form_text("terapeuta"),
            "cbo": _form_text("cbo"),
            "cbo_nome": _form_text("cbo_nome"),
            "cbo_executante": _form_text("cbo_executante"),
            "cns_executante": _form_digits("cns_executante"),

            # Solicitante
            "cns_solicitante": _form_digits("cns_solicitante"),
            "nome_solicitante": _form_text("nome_solicitante"),
            "data_solicitacao": _form_date("data_solicitacao"),

            # Autorizador
            "cns_autorizador": _form_digits("cns_autorizador"),
            "nome_autorizador": _form_text("nome_autorizador"),
            "data_autorizacao": _form_date("data_autorizacao"),
            "orgao_emissor": _form_text("orgao_emissor") or _form_text("orgao_emissor_rg"),

            # Nota / faturamento futuro
            "nota_fiscal": _form_text("nota_fiscal"),
            "data_nota_fiscal": _form_date("data_nota_fiscal"),
            "data_entrada_nf": _form_date("data_entrada_nf"),
            "competencia_nota": _form_text("competencia_nota"),
            "protocolo_nota": _form_text("protocolo_nota"),
            "obs_nota": _form_text("obs_nota"),

            # Pedido / entrega futura
            "data_pedido": _form_date("data_pedido"),
            "fornecedor": _form_text("fornecedor"),
            "obs_pedido": _form_text("obs_pedido"),
            "data_entrega": _form_date("data_entrega"),
            "local_entrega": _form_text("local_entrega"),
            "status_entrega": _form_text("status_entrega"),
            "obs_entrega": _form_text("obs_entrega"),

            # Saída
            "motivo_saida": _form_text("motivo_saida"),
            "data_alta": _form_date("data_alta"),

            # Flags
            "processado": False,
            "bpai": False,
            "sms_enviado": False,
        }

        
        ensure_apac_table()
        # Só insere colunas que realmente existem em public.apac
        campos_validos = _filter_existing_columns(campos, "apac")

        if not campos_validos:
            flash("Nenhum campo compatível encontrado para salvar.", "warning")
            return redirect(url_for("export.apac_cadastro"))

        cols = ", ".join(campos_validos.keys())
        placeholders = ", ".join(["%s"] * len(campos_validos))
        valores = list(campos_validos.values())

        sql = f"""
            INSERT INTO public.apac ({cols})
            VALUES ({placeholders})
            RETURNING id;
        """

        conn = conectar_db()
        cur = conn.cursor()
        cur.execute(sql, valores)

        novo = cur.fetchone()
        novo_id = novo["id"]

        conn.commit()

        registrar_log(
            f"🧾 Criou APAC ID {novo_id}",
            session.get("usuario_logado")
        )

        flash(f"✅ APAC cadastrada com sucesso! ID {novo_id}", "success")
        return redirect(url_for("export.apac_view"))

    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass

        print("❌ Erro ao salvar APAC:", e)
        traceback.print_exc()

        flash("❌ Erro ao salvar a APAC no banco.", "danger")
        return redirect(url_for("export.apac_cadastro"))

    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass

        try:
            if conn:
                conn.close()
        except Exception:
            pass


# =============================================================================
# APAC · API PESQUISA PACIENTES
# =============================================================================

@export_bp.route("/apac/api/consulta_pacientes", methods=["GET"])
@login_required
def apac_api_consulta_pacientes():
    termo = (request.args.get("nome") or "").strip()

    if len(termo) < 3:
        return jsonify([])

    conn = None
    cur = None

    try:
        conn = conectar_db()
        cur = conn.cursor()

        colunas_desejadas = [
            "id",
            "prontuario",
            "nome",
            "cns",
            "status",
            "nascimento",
            "idade",
            "sexo",
            "mod",
            "admissao",
            "cpf",
            "nis",
            "raca",
            "religiao",
            "logradouro",
            "codigo_logradouro",
            "numero_casa",
            "complemento",
            "bairro",
            "municipio",
            "cep",
            "codigo_ibge",
            "rg",
            "orgao_rg",
            "estado_civil",
            "mae",
            "cpf_mae",
            "rg_mae",
            "rg_ssp_mae",
            "nis_mae",
            "pai",
            "cpf_pai",
            "rg_pai",
            "rg_ssp_pai",
            "telefone1",
            "telefone2",
            "telefone3",
            "email",
            "responsavel",
            "cpf_responsavel",
            "rg_responsavel",
            "orgao_rg_responsavel",
            "laudos_json",
            "cid",
            "cid2",
            "rua",
            "numero",
            "cidade",
            "uf",
            "telefone",
            "nome_mae",
            "nome_pai",
            "end_prontuario",
            "alergias",
            "aviso",
            "comorbidades_json",
            "terapeuta",
            "cbo",
            "cbo_nome",
            "clinica_id",
        ]

        cur.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = 'pacientes'
            """
        )

        existentes = {row["column_name"] for row in cur.fetchall()}
        colunas = [c for c in colunas_desejadas if c in existentes]

        if not colunas:
            return jsonify([])

        select_cols = ", ".join(colunas)

        where_busca = []

        if "nome" in existentes:
            where_busca.append("LOWER(COALESCE(nome, '')) LIKE LOWER(%s)")

        if "nome_paciente" in existentes:
            where_busca.append("LOWER(COALESCE(nome_paciente, '')) LIKE LOWER(%s)")

        if "mae" in existentes:
            where_busca.append("LOWER(COALESCE(mae, '')) LIKE LOWER(%s)")

        if "nome_mae" in existentes:
            where_busca.append("LOWER(COALESCE(nome_mae, '')) LIKE LOWER(%s)")

        if "cpf" in existentes:
            where_busca.append("regexp_replace(COALESCE(cpf::text, ''), '\\D', '', 'g') LIKE %s")

        if "cns" in existentes:
            where_busca.append("regexp_replace(COALESCE(cns::text, ''), '\\D', '', 'g') LIKE %s")

        params = []
        like = f"%{termo}%"
        digits = _only_digits(termo) or termo

        for cond in where_busca:
            if "regexp_replace" in cond:
                params.append(f"%{digits}%")
            else:
                params.append(like)

        if not where_busca:
            return jsonify([])

        order_col = "nome" if "nome" in existentes else colunas[0]

        sql = f"""
            SELECT {select_cols}
              FROM public.pacientes
             WHERE {" OR ".join(where_busca)}
             ORDER BY {order_col}
             LIMIT 20
        """

        cur.execute(sql, params)
        rows = cur.fetchall()

        saida = []

        for row in rows:
            item = dict(row)

            # Aliases para o JS/HTML
            item["nome_paciente"] = item.get("nome") or item.get("nome_paciente") or ""
            item["data_nascimento"] = item.get("nascimento") or item.get("data_nascimento") or ""
            item["prontuario"] = item.get("prontuario") or item.get("end_prontuario") or ""
            item["mae"] = item.get("mae") or item.get("nome_mae") or ""
            item["pai"] = item.get("pai") or item.get("nome_pai") or ""
            item["endereco"] = (
                item.get("logradouro")
                or item.get("rua")
                or item.get("endereco")
                or item.get("end_prontuario")
                or ""
            )
            item["numero"] = item.get("numero") or item.get("numero_casa") or ""
            item["municipio"] = item.get("municipio") or item.get("cidade") or ""
            item["telefone"] = (
                item.get("telefone")
                or item.get("telefone1")
                or item.get("telefone2")
                or item.get("telefone3")
                or ""
            )

            # Datas em JSON
            for k, v in list(item.items()):
                if hasattr(v, "strftime"):
                    item[k] = v.strftime("%Y-%m-%d")

            saida.append(item)

        return jsonify(saida)

    except Exception as e:
        print("❌ Erro na pesquisa de pacientes para APAC:", e)
        traceback.print_exc()
        return jsonify([]), 200

    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass

        try:
            if conn:
                conn.close()
        except Exception:
            pass


# =============================================================================
# APAC · API PROCEDIMENTOS / SIGTAP
# Cenários:
# 1) Pesquisa por código ou descrição
# 2) Ao selecionar procedimento, retorna serviços/classificações compatíveis
# 3) Pesquisa por serviço mostra procedimentos compatíveis
# 4) Pesquisa por classificação mostra procedimentos compatíveis
# =============================================================================

def _descobrir_tabela_sigtap(cur):
    candidatas = [
        "procedimentos",
        "sigtap_procedimentos",
        "sigtap",
        "procedimentos_sigtap",
    ]

    for tabela in candidatas:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                  FROM information_schema.tables
                 WHERE table_schema = 'public'
                   AND table_name = %s
            ) AS existe
            """,
            (tabela,),
        )

        row = cur.fetchone()

        if row and row["existe"]:
            return tabela

    return None

def _split_multi(codigos, descricoes):
    """
    Aceita:
    - string com | ; , quebra de linha
    - array/list do Postgres
    - string tipo {001,002}
    - descrição única ou múltipla
    """
    import json
    import re

    def normalizar_lista(valor):
        if valor is None:
            return []

        if isinstance(valor, (list, tuple)):
            return [str(x).strip() for x in valor if str(x).strip()]

        txt = str(valor).strip()

        if not txt:
            return []

        # tenta JSON
        try:
            parsed = json.loads(txt)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except Exception:
            pass

        # remove chaves de array postgres: {001,002}
        txt = txt.strip("{}[]")

        # separadores comuns
        partes = re.split(r"\s*\|\s*|\s*;\s*|\s*,\s*|\r?\n", txt)

        return [p.strip() for p in partes if p.strip()]

    cods = normalizar_lista(codigos)
    descs = normalizar_lista(descricoes)

    saida = []

    for i, cod in enumerate(cods):
        desc = descs[i] if i < len(descs) else ""

        saida.append({
            "codigo": cod,
            "descricao": desc,
            "label": f"{cod} - {desc}" if desc else cod,
        })

    return saida




@export_bp.route("/apac/api/procedimentos", methods=["GET"])
@login_required
def apac_api_procedimentos():
    q = (request.args.get("q") or "").strip()
    servico = (_only_digits(request.args.get("servico")) or "").strip()
    classificacao = (_only_digits(request.args.get("classificacao")) or "").strip()
    competencia = (request.args.get("competencia") or "").strip()

    if len(q) < 3 and not servico and not classificacao:
        return jsonify([])

    conn = None
    cur = None

    try:
        conn = conectar_db()
        cur = conn.cursor()

        tabela = "procedimentos"

        cur.execute("""
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = %s
        """, (tabela,))

        existentes = {row["column_name"] for row in cur.fetchall()}

        if "codigo" not in existentes or "descricao" not in existentes:
            return jsonify([])

        desejadas = [
            "id",
            "codigo",
            "descricao",
            "competencia",
            "complexidade",
            "servicos_codigos",
            "servicos_descricoes",
            "classificacoes_codigos",
            "classificacoes_descricoes",
            "cbos_codigos",
            "cbos_descricoes",
            "cids_codigos",
            "cids_descricoes",
            "qtd_cbos",
            "qtd_cids",
            "qtd_servicos",
            "valor_sa",
            "valor_sh",
            "valor_sp",
            "valor_total",
            "co_financiamento",
            "no_financiamento",
            "co_rubrica",
            "no_rubrica",
        ]

        colunas = [c for c in desejadas if c in existentes]
        select_cols = ", ".join(colunas)

        where = []
        params = []

        if q and len(q) >= 3:
            q_digits = _only_digits(q)

            if q_digits:
                where.append("""
                    (
                        regexp_replace(COALESCE(codigo::text, ''), '\\D', '', 'g') LIKE %s
                        OR LOWER(COALESCE(descricao, '')) LIKE LOWER(%s)
                    )
                """)
                params.extend([f"%{q_digits}%", f"%{q}%"])
            else:
                where.append("LOWER(COALESCE(descricao, '')) LIKE LOWER(%s)")
                params.append(f"%{q}%")

        if servico and "servicos_codigos" in existentes:
            where.append("""
                regexp_replace(COALESCE(servicos_codigos::text, ''), '\\D', '', 'g') LIKE %s
            """)
            params.append(f"%{servico}%")

        if classificacao and "classificacoes_codigos" in existentes:
            where.append("""
                regexp_replace(COALESCE(classificacoes_codigos::text, ''), '\\D', '', 'g') LIKE %s
            """)
            params.append(f"%{classificacao}%")

        if competencia and "competencia" in existentes:
            where.append("COALESCE(competencia::text, '') = %s")
            params.append(competencia)

        if not where:
            return jsonify([])

        sql = f"""
            SELECT {select_cols}
              FROM public.{tabela}
             WHERE {" AND ".join(where)}
             ORDER BY descricao
             LIMIT 30
        """

        cur.execute(sql, params)
        rows = cur.fetchall()

        saida = []

        for row in rows:
            item = dict(row)

            item["servicos"] = _split_multi(
                item.get("servicos_codigos"),
                item.get("servicos_descricoes"),
            )

            item["classificacoes"] = _split_multi(
                item.get("classificacoes_codigos"),
                item.get("classificacoes_descricoes"),
            )

            item["cbos"] = _split_multi(
                item.get("cbos_codigos"),
                item.get("cbos_descricoes"),
            )

            item["cids"] = _split_multi(
                item.get("cids_codigos"),
                item.get("cids_descricoes"),
            )

            for k, v in list(item.items()):
                if hasattr(v, "strftime"):
                    item[k] = v.strftime("%Y-%m-%d")

            saida.append(item)

        return jsonify(saida)

    except Exception as e:
        print("❌ Erro na API de procedimentos APAC:", e)
        traceback.print_exc()
        return jsonify([]), 200

    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass

        try:
            if conn:
                conn.close()
        except Exception:
            pass

@export_bp.route("/apac/api/procedimento/<codigo>", methods=["GET"])
@login_required
def apac_api_procedimento_detalhe(codigo):
    codigo_limpo = _only_digits(codigo)

    if not codigo_limpo:
        return jsonify({"ok": False}), 404

    conn = None
    cur = None

    try:
        conn = conectar_db()
        cur = conn.cursor()

        tabela = _descobrir_tabela_sigtap(cur)

        if not tabela:
            return jsonify({"ok": False}), 404

        cur.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = %s
            """,
            (tabela,),
        )

        existentes = {row["column_name"] for row in cur.fetchall()}

        desejadas = [
            "id",
            "codigo",
            "descricao",
            "competencia",
            "complexidade",
            "servicos_codigos",
            "servicos_descricoes",
            "classificacoes_codigos",
            "classificacoes_descricoes",
            "cbos_codigos",
            "cbos_descricoes",
            "cids_codigos",
            "cids_descricoes",
            "valor_total",
        ]

        colunas = [c for c in desejadas if c in existentes]
        select_cols = ", ".join(colunas)

        cur.execute(
            f"""
            SELECT {select_cols}
              FROM public.{tabela}
             WHERE regexp_replace(COALESCE(codigo::text, ''), '\\D', '', 'g') = %s
             LIMIT 1
            """,
            (codigo_limpo,),
        )

        row = cur.fetchone()

        if not row:
            return jsonify({"ok": False}), 404

        item = dict(row)

        item["ok"] = True
        item["servicos"] = _split_multi(
            item.get("servicos_codigos"),
            item.get("servicos_descricoes"),
        )

        item["classificacoes"] = _split_multi(
            item.get("classificacoes_codigos"),
            item.get("classificacoes_descricoes"),
        )

        item["cbos"] = _split_multi(
            item.get("cbos_codigos"),
            item.get("cbos_descricoes"),
        )

        item["cids"] = _split_multi(
            item.get("cids_codigos"),
            item.get("cids_descricoes"),
        )

        return jsonify(item)

    except Exception as e:
        print("❌ Erro ao detalhar procedimento APAC:", e)
        traceback.print_exc()
        return jsonify({"ok": False}), 200

    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass

        try:
            if conn:
                conn.close()
        except Exception:
            pass


# =============================================================================
# APAC · API PROFISSIONAIS
# Solicitação / Autorização
# =============================================================================

def _descobrir_tabela_usuarios(cur):
    candidatas = [
        "usuarios",
        "users",
        "usuario",
    ]

    for tabela in candidatas:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                  FROM information_schema.tables
                 WHERE table_schema = 'public'
                   AND table_name = %s
            ) AS existe
            """,
            (tabela,),
        )

        row = cur.fetchone()
        if row and row["existe"]:
            return tabela

    return None


@export_bp.route("/apac/api/profissionais", methods=["GET"])
@login_required
def apac_api_profissionais():
    termo = (request.args.get("q") or request.args.get("nome") or "").strip()

    if len(termo) < 3:
        return jsonify([])

    conn = None
    cur = None

    try:
        conn = conectar_db()
        cur = conn.cursor()

        tabela = _descobrir_tabela_usuarios(cur)

        if not tabela:
            return jsonify([])

        cur.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = %s
            """,
            (tabela,),
        )

        existentes = {row["column_name"] for row in cur.fetchall()}

        desejadas = [
            "id",
            "nome",
            "profissional_id",
            "registro_conselho",
            "uf_conselho",
            "telefone",
            "sexo",
            "nascimento",
            "logradouro",
            "numero",
            "municipio",
            "uf",
            "role",
            "perfil_id",
            "is_active",
            "is_master",
            "is_superuser",
            "permissoes_json",
        ]

        colunas = [c for c in desejadas if c in existentes]

        if not colunas or "nome" not in existentes:
            return jsonify([])

        select_cols = ", ".join(colunas)

        where = ["LOWER(COALESCE(nome, '')) LIKE LOWER(%s)"]
        params = [f"%{termo}%"]

        termo_digits = _only_digits(termo)

        if termo_digits:
            if "profissional_id" in existentes:
                where.append("COALESCE(profissional_id::text, '') LIKE %s")
                params.append(f"%{termo_digits}%")

            if "registro_conselho" in existentes:
                where.append("regexp_replace(COALESCE(registro_conselho::text, ''), '\\D', '', 'g') LIKE %s")
                params.append(f"%{termo_digits}%")

            if "telefone" in existentes:
                where.append("regexp_replace(COALESCE(telefone::text, ''), '\\D', '', 'g') LIKE %s")
                params.append(f"%{termo_digits}%")

        if "is_active" in existentes:
            filtro_ativo = "AND COALESCE(is_active, TRUE) = TRUE"
        else:
            filtro_ativo = ""

        sql = f"""
            SELECT {select_cols}
              FROM public.{tabela}
             WHERE ({' OR '.join(where)})
             {filtro_ativo}
             ORDER BY nome
             LIMIT 20
        """

        cur.execute(sql, params)
        rows = cur.fetchall()

        saida = []

        for row in rows:
            item = dict(row)

            item["label"] = item.get("nome") or ""
            item["cns"] = item.get("profissional_id") or ""
            item["conselho"] = item.get("registro_conselho") or ""
            item["uf_conselho"] = item.get("uf_conselho") or ""

            for k, v in list(item.items()):
                if hasattr(v, "strftime"):
                    item[k] = v.strftime("%Y-%m-%d")

            saida.append(item)

        return jsonify(saida)

    except Exception as e:
        print("❌ Erro na API de profissionais APAC:", e)
        traceback.print_exc()
        return jsonify([]), 200

    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass

        try:
            if conn:
                conn.close()
        except Exception:
            pass