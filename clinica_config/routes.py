# -*- coding: utf-8 -*-
"""
routes.py

Responsável por:
- Página principal de configuração da clínica
- CRUD básico de clínicas
- Seleção de clínica pelo MASTER
- APIs gerais de clínicas
- Redirecionamento para timbre

O timbre agora fica separado em:
- timbre.py
- timbre.html
"""

from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    session,
    current_app,
    abort,
)

from . import clinica_config_bp

from .config_clinica import (
    ensure_multi_clinica_schema,
    get_clinica_id_atual,
    usuario_eh_master,
    usuario_pode_acessar_clinica,
    exigir_acesso_clinica,
    listar_clinicas,
    buscar_clinica,
    buscar_clinica_atual,
    salvar_clinica,
    desativar_clinica,
    ativar_clinica,
    buscar_ou_criar_configuracao_clinica,
)


# IMPORTANTE:
# mantém o timbre.py registrado no blueprint.
# Sem isso, as rotas /timbre, /api/timbre e /timbre/imagem/<campo>
# podem não ser carregadas dependendo do __init__.py.
try:
    from . import timbre  # noqa: F401
except Exception:
    pass


# ============================================================
# HELPERS DE FORM
# ============================================================

def clean_text(name, default=""):
    return (request.form.get(name) or default).strip()


def bool_form(name, default=False):
    valor = request.form.get(name)

    if valor is None:
        return bool(default)

    return str(valor).lower() in ("on", "true", "1", "sim", "yes")


def montar_dados_clinica_form():
    """
    Monta dict com dados gerais da clínica vindos do formulário.
    """
    return {
        "nome": clean_text("nome") or clean_text("nome_clinica"),
        "nome_clinica": clean_text("nome_clinica") or clean_text("nome"),

        "nome_fantasia": clean_text("nome_fantasia"),
        "razao_social": clean_text("razao_social"),

        "cnpj": clean_text("cnpj"),

        "telefone": clean_text("telefone"),
        "whatsapp": clean_text("whatsapp"),
        "email": clean_text("email"),

        "cep": clean_text("cep"),
        "logradouro": clean_text("logradouro"),
        "numero": clean_text("numero"),
        "complemento": clean_text("complemento"),
        "bairro": clean_text("bairro"),
        "municipio": clean_text("municipio"),
        "uf": clean_text("uf"),

        "endereco": clean_text("endereco"),

        "responsavel_nome": clean_text("responsavel_nome"),
        "responsavel_cpf": clean_text("responsavel_cpf"),
        "responsavel_telefone": clean_text("responsavel_telefone"),
        "responsavel_email": clean_text("responsavel_email"),

        "cnes": clean_text("cnes"),
        "tipo_clinica": clean_text("tipo_clinica"),

        "ativa": bool_form("ativa", True),

        "observacoes": clean_text("observacoes"),
    }


# ============================================================
# ENTRADA PRINCIPAL
# ============================================================

@clinica_config_bp.before_request
def before_clinica_config():
    """
    Garante estrutura sempre que entrar nesse módulo.
    """
    ensure_multi_clinica_schema()


@clinica_config_bp.route("/", methods=["GET", "POST"])
def index():
    """
    Página principal das configurações gerais da clínica.

    Aqui NÃO fica mais timbre.
    Timbre agora é:
        /clinica-config/timbre
    """

    try:
        clinica_id = get_clinica_id_atual()

        exigir_acesso_clinica(clinica_id)

        if request.method == "POST":
            dados = montar_dados_clinica_form()

            salvar_clinica(
                dados=dados,
                clinica_id=clinica_id,
            )

            flash(
                "Dados gerais da clínica salvos com sucesso.",
                "success",
            )

            return redirect(
                url_for(
                    "clinica_config.index",
                    clinica_id=clinica_id,
                )
            )

        clinica = buscar_clinica(clinica_id)

        config = buscar_ou_criar_configuracao_clinica(clinica_id)

        clinicas = listar_clinicas() if usuario_eh_master() else []

        return render_template(
            "clinica_config.html",
            clinica=clinica,
            config=config,
            clinicas=clinicas,
            clinica_id=clinica_id,
            is_master=usuario_eh_master(),
        )

    except PermissionError as e:
        flash(str(e), "error")
        return redirect(url_for("index"))

    except Exception as e:
        current_app.logger.exception(
            "Erro ao abrir configurações da clínica"
        )
        flash(
            f"Erro ao abrir configurações da clínica: {e}",
            "error",
        )
        return redirect(url_for("index"))


# ============================================================
# TIMBRE
# ============================================================

@clinica_config_bp.route("/papel-a4")
@clinica_config_bp.route("/papel")
def redirecionar_timbre():
    """
    Atalhos antigos/alternativos para a tela de timbre.
    """
    return redirect(url_for("clinica_config.timbre"))


# ============================================================
# CRUD DE CLÍNICAS - MASTER
# ============================================================

@clinica_config_bp.route("/clinicas", methods=["GET"])
def clinicas():
    """
    Lista clínicas.
    Apenas MASTER deve usar essa página.
    """

    if not usuario_eh_master():
        abort(403)

    lista = listar_clinicas()

    return render_template(
        "clinicas.html",
        clinicas=lista,
        is_master=True,
    )


@clinica_config_bp.route("/clinicas/nova", methods=["GET", "POST"])
def nova_clinica():
    """
    Cria nova clínica.
    Apenas MASTER.
    """

    if not usuario_eh_master():
        abort(403)

    if request.method == "POST":
        try:
            dados = montar_dados_clinica_form()

            nova_id = salvar_clinica(dados)

            flash(
                "Clínica criada com sucesso.",
                "success",
            )

            return redirect(
                url_for(
                    "clinica_config.index",
                    clinica_id=nova_id,
                )
            )

        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("clinica_config.nova_clinica"))

        except Exception as e:
            current_app.logger.exception("Erro ao criar clínica")
            flash(f"Erro ao criar clínica: {e}", "error")
            return redirect(url_for("clinica_config.nova_clinica"))

    return render_template(
        "clinica_form.html",
        clinica={},
        modo="nova",
        is_master=True,
    )


@clinica_config_bp.route("/clinicas/<int:clinica_id>/editar", methods=["GET", "POST"])
def editar_clinica(clinica_id):
    """
    Edita clínica existente.
    Apenas MASTER.
    """

    if not usuario_eh_master():
        abort(403)

    clinica = buscar_clinica(clinica_id)

    if not clinica:
        abort(404)

    if request.method == "POST":
        try:
            dados = montar_dados_clinica_form()

            salvar_clinica(
                dados=dados,
                clinica_id=clinica_id,
            )

            flash(
                "Clínica atualizada com sucesso.",
                "success",
            )

            return redirect(
                url_for(
                    "clinica_config.index",
                    clinica_id=clinica_id,
                )
            )

        except ValueError as e:
            flash(str(e), "error")
            return redirect(
                url_for(
                    "clinica_config.editar_clinica",
                    clinica_id=clinica_id,
                )
            )

        except Exception as e:
            current_app.logger.exception("Erro ao editar clínica")
            flash(f"Erro ao editar clínica: {e}", "error")
            return redirect(
                url_for(
                    "clinica_config.editar_clinica",
                    clinica_id=clinica_id,
                )
            )

    return render_template(
        "clinica_form.html",
        clinica=clinica,
        modo="editar",
        is_master=True,
    )


@clinica_config_bp.route("/clinicas/<int:clinica_id>/desativar", methods=["POST"])
def rota_desativar_clinica(clinica_id):
    """
    Desativa clínica.
    Apenas MASTER.
    """

    if not usuario_eh_master():
        abort(403)

    try:
        desativar_clinica(clinica_id)

        flash(
            "Clínica desativada com sucesso.",
            "success",
        )

    except ValueError as e:
        flash(str(e), "error")

    except Exception as e:
        current_app.logger.exception("Erro ao desativar clínica")
        flash(f"Erro ao desativar clínica: {e}", "error")

    return redirect(url_for("clinica_config.clinicas"))


@clinica_config_bp.route("/clinicas/<int:clinica_id>/ativar", methods=["POST"])
def rota_ativar_clinica(clinica_id):
    """
    Reativa clínica.
    Apenas MASTER.
    """

    if not usuario_eh_master():
        abort(403)

    try:
        ativar_clinica(clinica_id)

        flash(
            "Clínica ativada com sucesso.",
            "success",
        )

    except Exception as e:
        current_app.logger.exception("Erro ao ativar clínica")
        flash(f"Erro ao ativar clínica: {e}", "error")

    return redirect(url_for("clinica_config.clinicas"))


# ============================================================
# TROCA DE CLÍNICA - MASTER
# ============================================================

@clinica_config_bp.route("/selecionar", methods=["POST"])
def selecionar_clinica():
    """
    MASTER escolhe qual clínica quer visualizar/configurar.
    """

    if not usuario_eh_master():
        abort(403)

    clinica_id = request.form.get("clinica_id", type=int)

    if not clinica_id:
        flash("Selecione uma clínica válida.", "error")
        return redirect(url_for("clinica_config.index"))

    clinica = buscar_clinica(clinica_id)

    if not clinica:
        flash("Clínica não encontrada.", "error")
        return redirect(url_for("clinica_config.index"))

    session["clinica_id"] = clinica_id

    flash(
        f"Clínica selecionada: {clinica.get('nome')}.",
        "success",
    )

    return redirect(
        url_for(
            "clinica_config.index",
            clinica_id=clinica_id,
        )
    )


# ============================================================
# APIs
# ============================================================

@clinica_config_bp.route("/api/clinicas", methods=["GET"])
def api_clinicas():
    """
    Lista clínicas em JSON.
    MASTER: todas.
    Usuário comum: apenas a sua.
    """

    if usuario_eh_master():
        return jsonify({
            "ok": True,
            "clinicas": listar_clinicas(),
        })

    clinica = buscar_clinica_atual()

    return jsonify({
        "ok": True,
        "clinicas": [clinica] if clinica else [],
    })


@clinica_config_bp.route("/api/clinica-atual", methods=["GET"])
def api_clinica_atual():
    """
    Retorna clínica atual.
    """

    clinica_id = get_clinica_id_atual()

    if not usuario_pode_acessar_clinica(clinica_id):
        return jsonify({
            "ok": False,
            "error": "Sem permissão para acessar esta clínica.",
        }), 403

    clinica = buscar_clinica(clinica_id)

    config = buscar_ou_criar_configuracao_clinica(clinica_id)

    return jsonify({
        "ok": True,
        "clinica_id": clinica_id,
        "clinica": clinica,
        "config": config,
        "is_master": usuario_eh_master(),
    })


@clinica_config_bp.route("/api/clinicas/<int:clinica_id>", methods=["GET"])
def api_clinica_por_id(clinica_id):
    """
    Busca clínica por ID.
    """

    if not usuario_pode_acessar_clinica(clinica_id):
        return jsonify({
            "ok": False,
            "error": "Sem permissão para acessar esta clínica.",
        }), 403

    clinica = buscar_clinica(clinica_id)

    if not clinica:
        return jsonify({
            "ok": False,
            "error": "Clínica não encontrada.",
        }), 404

    return jsonify({
        "ok": True,
        "clinica": clinica,
    })


@clinica_config_bp.route("/api/clinicas", methods=["POST"])
def api_criar_clinica():
    """
    Cria clínica via JSON.
    Apenas MASTER.
    """

    if not usuario_eh_master():
        return jsonify({
            "ok": False,
            "error": "Apenas MASTER pode criar clínicas.",
        }), 403

    try:
        dados = request.get_json(silent=True) or {}

        nova_id = salvar_clinica(dados)

        return jsonify({
            "ok": True,
            "clinica_id": nova_id,
            "message": "Clínica criada com sucesso.",
        })

    except ValueError as e:
        return jsonify({
            "ok": False,
            "error": str(e),
        }), 400

    except Exception as e:
        current_app.logger.exception("Erro na API ao criar clínica")
        return jsonify({
            "ok": False,
            "error": str(e),
        }), 500


@clinica_config_bp.route("/api/clinicas/<int:clinica_id>", methods=["PUT", "PATCH"])
def api_atualizar_clinica(clinica_id):
    """
    Atualiza clínica via JSON.
    MASTER pode alterar qualquer.
    Usuário comum só a própria, se permitido.
    """

    if not usuario_pode_acessar_clinica(clinica_id):
        return jsonify({
            "ok": False,
            "error": "Sem permissão para alterar esta clínica.",
        }), 403

    try:
        dados = request.get_json(silent=True) or {}

        salvar_clinica(
            dados=dados,
            clinica_id=clinica_id,
        )

        return jsonify({
            "ok": True,
            "message": "Clínica atualizada com sucesso.",
        })

    except ValueError as e:
        return jsonify({
            "ok": False,
            "error": str(e),
        }), 400

    except Exception as e:
        current_app.logger.exception("Erro na API ao atualizar clínica")
        return jsonify({
            "ok": False,
            "error": str(e),
        }), 500


# ============================================================
# COMPATIBILIDADE COM ROTAS ANTIGAS
# ============================================================

@clinica_config_bp.route("/api/config", methods=["GET"])
def api_config_compat():
    """
    Compatibilidade com a rota antiga /api/config.

    Antes retornava configuração geral + timbre.
    Agora retorna clínica + config base.
    Para timbre visual usar:
        /clinica-config/api/timbre
    """

    clinica_id = request.args.get("clinica_id", type=int) or get_clinica_id_atual()

    if not usuario_pode_acessar_clinica(clinica_id):
        return jsonify({
            "ok": False,
            "error": "Sem permissão para acessar esta clínica.",
        }), 403

    clinica = buscar_clinica(clinica_id)
    config = buscar_ou_criar_configuracao_clinica(clinica_id)

    return jsonify({
        "ok": True,
        "clinica_id": clinica_id,
        "clinica": clinica,
        "config": config,
    })


@clinica_config_bp.route("/imagem/<campo>")
def imagem_antiga_redirect(campo):
    """
    Compatibilidade com rota antiga:
        /clinica-config/imagem/logo

    Agora redireciona para:
        /clinica-config/timbre/imagem/logo
    """

    clinica_id = request.args.get("clinica_id", type=int) or get_clinica_id_atual()

    return redirect(
        url_for(
            "clinica_config.imagem_timbre",
            campo=campo,
            clinica_id=clinica_id,
        )
    )


@clinica_config_bp.route("/preview", methods=["POST"])
def preview_antigo_redirect():
    """
    Compatibilidade com preview antigo.
    Agora o preview real está em:
        /clinica-config/timbre/preview
    """

    return redirect(url_for("clinica_config.preview_timbre"), code=307)


@clinica_config_bp.route("/selecionar-ambiente", methods=["GET", "POST"])
def selecionar_ambiente():
    """
    Painel pós-login do MASTER.
    Aqui ele escolhe em qual clínica vai trabalhar.
    Isso define session["clinica_id"] para o sistema inteiro.
    """

    if not usuario_eh_master():
        abort(403)

    ensure_multi_clinica_schema()

    if request.method == "POST":
        clinica_id = request.form.get("clinica_id", type=int)

        if not clinica_id:
            flash("Selecione uma clínica para continuar.", "error")
            return redirect(url_for("clinica_config.selecionar_ambiente"))

        clinica = buscar_clinica(clinica_id)

        if not clinica:
            flash("Clínica não encontrada.", "error")
            return redirect(url_for("clinica_config.selecionar_ambiente"))

        if not clinica.get("ativa"):
            flash("Essa clínica está inativa.", "error")
            return redirect(url_for("clinica_config.selecionar_ambiente"))

        session["clinica_id"] = clinica_id
        session["clinica_nome"] = clinica.get("nome")
        session["ambiente_definido"] = True

        current_app.logger.info(
            "MASTER entrou no ambiente da clínica %s - %s",
            clinica_id,
            clinica.get("nome")
        )

        flash(f"Ambiente selecionado: {clinica.get('nome')}", "success")

        return redirect(url_for("index"))

    clinicas = listar_clinicas(apenas_ativas=True)

    return render_template(
        "selecionar_ambiente.html",
        clinicas=clinicas,
    )

@clinica_config_bp.before_app_request
def exigir_ambiente_master():
    """
    Se for MASTER e ainda não escolheu clínica,
    manda para o painel de seleção de ambiente.
    """

    endpoint = request.endpoint or ""

    rotas_livres = (
        "auth.",
        "static",
        "clinica_config.selecionar_ambiente",
    )

    if endpoint.startswith(rotas_livres):
        return None

    if usuario_eh_master() and not session.get("clinica_id"):
        return redirect(url_for("clinica_config.selecionar_ambiente"))

    return None