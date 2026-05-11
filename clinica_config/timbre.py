# -*- coding: utf-8 -*-
"""
timbre.py

Motor do timbre por clínica.

- Salva imagens por clinica_id
- Serve imagens por clinica_id
- Gera URLs com cache busting
- Mantém compatibilidade com /timbre
- Funciona local e Render com PostgreSQL
"""

from __future__ import annotations

import io
from datetime import datetime

from flask import (
    request,
    redirect,
    url_for,
    flash,
    current_app,
    jsonify,
    send_file,
    abort,
    render_template,
)

from werkzeug.utils import secure_filename

from . import clinica_config_bp
from db import conectar_db

from .config_clinica import (
    ensure_multi_clinica_schema,
    get_clinica_id_atual,
    buscar_ou_criar_configuracao_clinica,
    exigir_acesso_clinica,
)


ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
MAX_IMAGE_SIZE_MB = 5


IMAGE_FIELDS = {
    "logo": {
        "forms": ["logo", "timbre_logo"],
        "bin": "logo_bin",
        "mime": "logo_mime",
        "nome": "logo_nome",
        "path": "logo_path",
    },
    "cabecalho": {
        "forms": ["imagem_cabecalho", "timbre_cabecalho"],
        "bin": "cabecalho_img_bin",
        "mime": "cabecalho_img_mime",
        "nome": "cabecalho_img_nome",
        "path": "cabecalho_img_path",
    },
    "rodape1": {
        "forms": ["imagem_rodape", "timbre_rodape1"],
        "bin": "rodape_img_bin",
        "mime": "rodape_img_mime",
        "nome": "rodape_img_nome",
        "path": "rodape_img_path",
    },
    "rodape2": {
        "forms": ["rodape_img_2", "timbre_rodape2"],
        "bin": "rodape_img_2_bin",
        "mime": "rodape_img_2_mime",
        "nome": "rodape_img_2_nome",
        "path": "rodape_img_2_path",
    },
    "rodape3": {
        "forms": ["rodape_img_3", "timbre_rodape3"],
        "bin": "rodape_img_3_bin",
        "mime": "rodape_img_3_mime",
        "nome": "rodape_img_3_nome",
        "path": "rodape_img_3_path",
    },
}


def allowed_file(filename: str | None) -> bool:
    return bool(
        filename
        and "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def bool_form(name: str) -> bool:
    return request.form.get(name) in ("on", "true", "1", "sim", "yes")


def int_form(name: str, default: int) -> int:
    try:
        return int(request.form.get(name) or default)
    except Exception:
        return default


def clean_text(name: str, default: str = "") -> str:
    return (request.form.get(name) or default).strip()


def row_to_dict(row, cursor=None):
    if not row:
        return None

    if isinstance(row, dict):
        return dict(row)

    if hasattr(row, "keys"):
        return dict(row)

    if cursor and cursor.description:
        colunas = [desc[0] for desc in cursor.description]
        return dict(zip(colunas, row))

    return None


def normalizar_binario_imagem(dados):
    if not dados:
        return None

    if isinstance(dados, memoryview):
        return dados.tobytes()

    if isinstance(dados, bytearray):
        return bytes(dados)

    if isinstance(dados, bytes):
        return dados

    return None


def resolver_clinica_id_request() -> int:
    clinica_id = (
        request.args.get("clinica_id", type=int)
        or request.form.get("clinica_id", type=int)
        or get_clinica_id_atual()
    )

    if not clinica_id:
        abort(403)

    return int(clinica_id)


def ler_imagem_upload_por_campos(campos: list[str]):
    arquivo = None

    for campo in campos:
        arquivo = request.files.get(campo)
        if arquivo and arquivo.filename:
            break

    if not arquivo or not arquivo.filename:
        return None

    if not allowed_file(arquivo.filename):
        raise ValueError("Formato inválido. Use PNG, JPG, JPEG ou WEBP.")

    dados = arquivo.read()

    if not dados:
        return None

    limite = MAX_IMAGE_SIZE_MB * 1024 * 1024

    if len(dados) > limite:
        raise ValueError(
            f"A imagem {arquivo.filename} ultrapassa {MAX_IMAGE_SIZE_MB}MB."
        )

    return {
        "bytes": bytes(dados),
        "mime": arquivo.mimetype or "application/octet-stream",
        "nome": secure_filename(arquivo.filename),
    }


def montar_dados_timbre_form():
    return {
        "cabecalho_texto": clean_text("cabecalho_texto"),
        "cabecalho_altura": int_form("cabecalho_altura", 130),
        "cabecalho_mostrar_logo": bool_form("cabecalho_mostrar_logo"),
        "cabecalho_alinhamento": clean_text("cabecalho_alinhamento", "centro"),

        "rodape_texto": clean_text("rodape_texto"),
        "rodape_altura": int_form("rodape_altura", 115),
        "rodape_alinhamento": clean_text("rodape_alinhamento", "esquerda"),

        "margem_superior": int_form("margem_superior", 20),
        "margem_inferior": int_form("margem_inferior", 20),
        "margem_esquerda": int_form("margem_esquerda", 20),
        "margem_direita": int_form("margem_direita", 20),

        "mostrar_linha_cabecalho": bool_form("mostrar_linha_cabecalho"),
        "mostrar_linha_rodape": bool_form("mostrar_linha_rodape"),

        "cor_listra_topo": clean_text("cor_listra_topo", "#0f766e"),
    }


def montar_imagens_timbre_form():
    imagens = {}

    for key, meta in IMAGE_FIELDS.items():
        img = ler_imagem_upload_por_campos(meta["forms"])
        if img:
            imagens[key] = img

    return imagens


def _versao_cache(config: dict) -> str:
    versao = config.get("atualizado_em")

    if versao:
        try:
            return str(int(versao.timestamp()))
        except Exception:
            return str(versao).replace(" ", "_").replace(":", "-")

    return "1"


def buscar_timbre(clinica_id=None):
    ensure_multi_clinica_schema()

    clinica_id = int(clinica_id or get_clinica_id_atual() or 0)

    if not clinica_id:
        abort(403)

    exigir_acesso_clinica(clinica_id)
    buscar_ou_criar_configuracao_clinica(clinica_id)

    conn = conectar_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT *
            FROM clinica_configuracoes
            WHERE clinica_id = %s
            ORDER BY id DESC
            LIMIT 1
        """, (clinica_id,))

        row = cur.fetchone()
        config = row_to_dict(row, cur) or {}
    finally:
        cur.close()
        conn.close()

    versao = _versao_cache(config)

    for key, meta in IMAGE_FIELDS.items():
        config[meta["path"]] = url_for(
            "clinica_config.imagem_timbre",
            campo=key,
            clinica_id=clinica_id,
            v=versao,
        )

    config["clinica_id"] = clinica_id
    return config


def salvar_timbre(dados, imagens, clinica_id=None):
    ensure_multi_clinica_schema()

    clinica_id = int(clinica_id or get_clinica_id_atual() or 0)

    if not clinica_id:
        abort(403)

    exigir_acesso_clinica(clinica_id)
    buscar_ou_criar_configuracao_clinica(clinica_id)

    conn = conectar_db()
    cur = conn.cursor()

    params_imagens = {}

    for key, meta in IMAGE_FIELDS.items():
        img = imagens.get(key)

        params_imagens[meta["bin"]] = img["bytes"] if img else None
        params_imagens[meta["mime"]] = img["mime"] if img else None
        params_imagens[meta["nome"]] = img["nome"] if img else None

    try:
        cur.execute("""
            UPDATE clinica_configuracoes
            SET
                cabecalho_texto = %s,
                cabecalho_altura = %s,
                cabecalho_mostrar_logo = %s,
                cabecalho_alinhamento = %s,

                rodape_texto = %s,
                rodape_altura = %s,
                rodape_alinhamento = %s,

                margem_superior = %s,
                margem_inferior = %s,
                margem_esquerda = %s,
                margem_direita = %s,

                mostrar_linha_cabecalho = %s,
                mostrar_linha_rodape = %s,

                cor_listra_topo = %s,

                logo_bin = COALESCE(%s, logo_bin),
                logo_mime = COALESCE(%s, logo_mime),
                logo_nome = COALESCE(%s, logo_nome),

                cabecalho_img_bin = COALESCE(%s, cabecalho_img_bin),
                cabecalho_img_mime = COALESCE(%s, cabecalho_img_mime),
                cabecalho_img_nome = COALESCE(%s, cabecalho_img_nome),

                rodape_img_bin = COALESCE(%s, rodape_img_bin),
                rodape_img_mime = COALESCE(%s, rodape_img_mime),
                rodape_img_nome = COALESCE(%s, rodape_img_nome),

                rodape_img_2_bin = COALESCE(%s, rodape_img_2_bin),
                rodape_img_2_mime = COALESCE(%s, rodape_img_2_mime),
                rodape_img_2_nome = COALESCE(%s, rodape_img_2_nome),

                rodape_img_3_bin = COALESCE(%s, rodape_img_3_bin),
                rodape_img_3_mime = COALESCE(%s, rodape_img_3_mime),
                rodape_img_3_nome = COALESCE(%s, rodape_img_3_nome),

                atualizado_em = CURRENT_TIMESTAMP
            WHERE clinica_id = %s
        """, (
            dados["cabecalho_texto"],
            dados["cabecalho_altura"],
            dados["cabecalho_mostrar_logo"],
            dados["cabecalho_alinhamento"],

            dados["rodape_texto"],
            dados["rodape_altura"],
            dados["rodape_alinhamento"],

            dados["margem_superior"],
            dados["margem_inferior"],
            dados["margem_esquerda"],
            dados["margem_direita"],

            dados["mostrar_linha_cabecalho"],
            dados["mostrar_linha_rodape"],

            dados["cor_listra_topo"],

            params_imagens["logo_bin"],
            params_imagens["logo_mime"],
            params_imagens["logo_nome"],

            params_imagens["cabecalho_img_bin"],
            params_imagens["cabecalho_img_mime"],
            params_imagens["cabecalho_img_nome"],

            params_imagens["rodape_img_bin"],
            params_imagens["rodape_img_mime"],
            params_imagens["rodape_img_nome"],

            params_imagens["rodape_img_2_bin"],
            params_imagens["rodape_img_2_mime"],
            params_imagens["rodape_img_2_nome"],

            params_imagens["rodape_img_3_bin"],
            params_imagens["rodape_img_3_mime"],
            params_imagens["rodape_img_3_nome"],

            clinica_id,
        ))

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        cur.close()
        conn.close()


def salvar_timbre_da_request(clinica_id=None):
    clinica_id = int(clinica_id or resolver_clinica_id_request())

    dados = montar_dados_timbre_form()
    imagens = montar_imagens_timbre_form()

    salvar_timbre(
        dados=dados,
        imagens=imagens,
        clinica_id=clinica_id,
    )

    return True


@clinica_config_bp.route("/timbre", methods=["GET", "POST"])
def timbre():
    clinica_id = resolver_clinica_id_request()
    exigir_acesso_clinica(clinica_id)

    if request.method == "POST":
        try:
            salvar_timbre_da_request(clinica_id)
            flash("Timbre atualizado com sucesso.", "success")

            return redirect(
                url_for(
                    "clinica_config.timbre",
                    clinica_id=clinica_id,
                )
            )

        except ValueError as e:
            flash(str(e), "error")

        except Exception as e:
            current_app.logger.exception("Erro ao salvar timbre")
            flash(f"Erro ao salvar timbre: {e}", "error")

    config = buscar_timbre(clinica_id)

    conn = conectar_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT *
            FROM clinicas
            WHERE id = %s
            LIMIT 1
        """, (clinica_id,))

        row = cur.fetchone()
        clinica = row_to_dict(row, cur) or {"id": clinica_id, "nome": "Clínica"}

    finally:
        cur.close()
        conn.close()

    return render_template(
        "timbre.html",
        clinica=clinica,
        clinica_id=clinica_id,
        config=config,
    )

@clinica_config_bp.route("/timbre/imagem/<campo>")
def imagem_timbre(campo):
    ensure_multi_clinica_schema()

    clinica_id = resolver_clinica_id_request()
    exigir_acesso_clinica(clinica_id)

    if campo not in IMAGE_FIELDS:
        abort(404)

    meta = IMAGE_FIELDS[campo]

    conn = conectar_db()
    cur = conn.cursor()

    try:
        cur.execute(f"""
            SELECT
                {meta["bin"]} AS img_bin,
                {meta["mime"]} AS img_mime,
                {meta["nome"]} AS img_nome
            FROM clinica_configuracoes
            WHERE clinica_id = %s
            ORDER BY id DESC
            LIMIT 1
        """, (clinica_id,))

        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not row:
        abort(404)

    if isinstance(row, dict) or hasattr(row, "keys"):
        row_dict = dict(row)
        dados = row_dict.get("img_bin")
        mime = row_dict.get("img_mime")
        nome = row_dict.get("img_nome")
    else:
        dados, mime, nome = row

    dados = normalizar_binario_imagem(dados)

    if not dados:
        abort(404)

    return send_file(
        io.BytesIO(dados),
        mimetype=mime or "application/octet-stream",
        download_name=nome or f"{campo}.png",
        max_age=0,
        conditional=True,
    )


@clinica_config_bp.route("/api/timbre")
def api_timbre():
    clinica_id = resolver_clinica_id_request()
    exigir_acesso_clinica(clinica_id)

    return jsonify(buscar_timbre(clinica_id))


@clinica_config_bp.route("/timbre/preview", methods=["POST"])
def preview_timbre():
    clinica_id = resolver_clinica_id_request()
    exigir_acesso_clinica(clinica_id)

    config_atual = buscar_timbre(clinica_id)

    preview = {
        "clinica_id": clinica_id,

        "logo_path": config_atual.get("logo_path"),
        "cabecalho_img_path": config_atual.get("cabecalho_img_path"),
        "rodape_img_path": config_atual.get("rodape_img_path"),
        "rodape_img_2_path": config_atual.get("rodape_img_2_path"),
        "rodape_img_3_path": config_atual.get("rodape_img_3_path"),

        "cabecalho_texto": clean_text("cabecalho_texto"),
        "cabecalho_altura": int_form("cabecalho_altura", 130),
        "cabecalho_mostrar_logo": bool_form("cabecalho_mostrar_logo"),
        "cabecalho_alinhamento": clean_text("cabecalho_alinhamento", "centro"),

        "rodape_texto": clean_text("rodape_texto"),
        "rodape_altura": int_form("rodape_altura", 115),
        "rodape_alinhamento": clean_text("rodape_alinhamento", "esquerda"),

        "margem_superior": int_form("margem_superior", 20),
        "margem_inferior": int_form("margem_inferior", 20),
        "margem_esquerda": int_form("margem_esquerda", 20),
        "margem_direita": int_form("margem_direita", 20),

        "mostrar_linha_cabecalho": bool_form("mostrar_linha_cabecalho"),
        "mostrar_linha_rodape": bool_form("mostrar_linha_rodape"),
        "cor_listra_topo": clean_text("cor_listra_topo", "#0f766e"),

        "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }

    return jsonify(preview)