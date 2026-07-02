from __future__ import annotations

import io
import json
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import HexColor

from db import conectar_db


# ============================================================
# HELPERS
# ============================================================

def _safe(v, default="-"):
    if v is None:
        return default
    v = str(v).strip()
    return v if v else default


def _safe_int(v, default=0):
    try:
        return int(v)
    except Exception:
        return default


def _bin(v):
    if not v:
        return None
    if isinstance(v, memoryview):
        return v.tobytes()
    if isinstance(v, bytearray):
        return bytes(v)
    if isinstance(v, bytes):
        return v
    return None


def _wrap(texto, limite=90):
    texto = _safe(texto, "")
    if not texto:
        return ["-"]

    linhas = []
    for bloco in texto.splitlines():
        palavras = bloco.split()
        atual = ""

        for p in palavras:
            teste = f"{atual} {p}".strip()
            if len(teste) <= limite:
                atual = teste
            else:
                if atual:
                    linhas.append(atual)
                atual = p

        if atual:
            linhas.append(atual)

    return linhas or ["-"]


def _row_to_dict(row, cur):
    if not row:
        return {}
    if isinstance(row, dict) or hasattr(row, "keys"):
        return dict(row)

    cols = [d[0] for d in cur.description]
    return {cols[i]: row[i] for i in range(len(cols))}


def _data_br(v):
    if not v:
        return "-"

    if isinstance(v, datetime):
        return v.strftime("%d/%m/%Y %H:%M")

    txt = str(v).strip()

    try:
        if "T" in txt:
            return datetime.fromisoformat(txt.replace("Z", "")).strftime("%d/%m/%Y %H:%M")

        if len(txt) >= 10 and txt[4] == "-" and txt[7] == "-":
            dt = datetime.fromisoformat(txt[:19])
            return dt.strftime("%d/%m/%Y %H:%M") if len(txt) > 10 else dt.strftime("%d/%m/%Y")
    except Exception:
        pass

    return txt


def _sim_nao(valor):
    if valor in (True, "true", "1", "on", "sim", "Sim", "SIM", "yes", "S"):
        return "Sim"
    return "-"


def buscar_config_timbre(clinica_id):
    if not clinica_id:
        return {}

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

        return _row_to_dict(cur.fetchone(), cur)

    except Exception:
        return {}

    finally:
        cur.close()
        conn.close()


def desenhar_imagem(pdf, dados, x, y, w, h):
    img_bin = _bin(dados)
    if not img_bin:
        return False

    try:
        img = ImageReader(io.BytesIO(img_bin))
        pdf.drawImage(
            img,
            x,
            y,
            width=w,
            height=h,
            preserveAspectRatio=True,
            anchor="c",
            mask="auto",
        )
        return True
    except Exception as e:
        print(f"[PDF TIMBRE] Erro ao desenhar imagem: {e}")
        return False


# ============================================================
# PDF
# ============================================================

def gerar_pdf_avaliacao(avaliacao: dict, tipo_label: str, dados: dict | None = None):
    dados = dados or {}
    timbre = buscar_config_timbre(avaliacao.get("clinica_id"))

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)

    largura, altura = A4

    cor_listra = timbre.get("cor_listra_topo") or "#0f766e"

    margem_esq = _safe_int(timbre.get("margem_esquerda"), 20)
    margem_dir = _safe_int(timbre.get("margem_direita"), 20)
    margem_sup = _safe_int(timbre.get("margem_superior"), 20)
    margem_inf = _safe_int(timbre.get("margem_inferior"), 20)

    margem_x = max(35, margem_esq + 20)
    margem_direita = max(35, margem_dir + 20)

    cab_altura = _safe_int(timbre.get("cabecalho_altura"), 120)
    rod_altura = _safe_int(timbre.get("rodape_altura"), 90)

    area_escrita_largura = largura - margem_x - margem_direita
    y = altura - 40

    rodape_limite = max(95, rod_altura + margem_inf + 35)

    # --------------------------------------------------------
    # ESTRUTURA DE PÁGINA
    # --------------------------------------------------------

    def cor_rgb():
        try:
            return HexColor(cor_listra)
        except Exception:
            return HexColor("#0f766e")








    def rodape():
        rod_y = margem_inf + 12

        # Ajustado conforme você identificou:
        # - logo_bin fica como marca d'água central
        # - rodape_img_bin fica junto com as imagens da direita
        marca_dagua_centro = timbre.get("logo_bin")
        logo_marca = None
        img_dir_1 = timbre.get("rodape_img_bin")
        img_dir_2 = timbre.get("rodape_img_2_bin")
        img_dir_3 = timbre.get("rodape_img_3_bin")
        rod_texto = timbre.get("rodape_texto")

        # 1) Marca d’água grande no centro da página com 30% de opacidade
        if _bin(marca_dagua_centro):
            try:
                pdf.saveState()
                pdf.setFillAlpha(0.30)
                pdf.setStrokeAlpha(0.30)

                marca_w = 400
                marca_h = 400
                marca_x = (largura - marca_w) / 2
                marca_y = (altura - marca_h) / 2

                desenhar_imagem(
                    pdf,
                    marca_dagua_centro,
                    marca_x,
                    marca_y,
                    marca_w,
                    marca_h
                )

                pdf.restoreState()
            except Exception:
                try:
                    pdf.restoreState()
                except Exception:
                    pass

        # 2) Linha do rodapé
        if timbre.get("mostrar_linha_rodape"):
            pdf.setStrokeColorRGB(0.82, 0.86, 0.90)
            pdf.line(
                margem_x,
                rod_y + rod_altura + 8,
                largura - margem_direita,
                rod_y + rod_altura + 8
            )

        # 3) Texto do rodapé à esquerda
        texto_x = margem_x

        if rod_texto:
            pdf.setFont("Helvetica", 8)
            pdf.setFillColorRGB(0.10, 0.14, 0.18)

            linhas = _wrap(rod_texto, 62)
            ty = rod_y + rod_altura - 40

            for linha in linhas[:7]:
                pdf.drawString(texto_x + 10, ty, linha)
                ty -= 10

            pdf.setFillColorRGB(0, 0, 0)

        # 4) Imagens à direita
        imagens_direita = [
            img for img in [img_dir_1, img_dir_2, img_dir_3]
            if _bin(img)
        ]

        if imagens_direita:
            qtd = len(imagens_direita)
            gap = 8
            img_w = 72
            img_h = min(rod_altura - 12, 58)

            total_w = (img_w * qtd) + (gap * (qtd - 1))
            start_x = largura - margem_direita - total_w
            img_y = rod_y + ((rod_altura - img_h) / 2)

            for i, img in enumerate(imagens_direita):
                x = start_x + (i * (img_w + gap))
                desenhar_imagem(
                    pdf,
                    img,
                    x,
                    img_y,
                    img_w,
                    img_h
                )




    def cabecalho():
        nonlocal y

        pdf.setFillColor(cor_rgb())
        pdf.rect(0, altura - 12, largura, 12, fill=1, stroke=0)
        pdf.setFillColorRGB(0, 0, 0)

        cab_img = timbre.get("cabecalho_img_bin")
        logo = timbre.get("logo_bin")

        cab_y = altura - cab_altura - margem_sup

        if _bin(cab_img):
            desenhar_imagem(
                pdf,
                cab_img,
                margem_x,
                cab_y,
                area_escrita_largura,
                cab_altura,
            )
            y = cab_y - 22

        else:
            texto_x = margem_x
            topo_y = altura - margem_sup - 28

            if _bin(logo) and timbre.get("cabecalho_mostrar_logo", True):
                desenhar_imagem(
                    pdf,
                    logo,
                    margem_x,
                    topo_y - 45,
                    68,
                    52,
                )
                texto_x = margem_x + 82

            pdf.setFont("Helvetica-Bold", 13)
            pdf.drawString(texto_x, topo_y, "SGD · AVALIAÇÕES MULTIPROFISSIONAIS")

            cab_texto = timbre.get("cabecalho_texto")
            if cab_texto:
                pdf.setFont("Helvetica", 8.5)
                ty = topo_y - 13
                for linha in _wrap(cab_texto, 86):
                    pdf.drawString(texto_x, ty, linha)
                    ty -= 10

            y = altura - margem_sup - 92

        pdf.setFont("Helvetica", 8.5)
        pdf.drawRightString(
            largura - margem_direita,
            y + 20,
            f"Avaliação Nº {_safe(avaliacao.get('id'))}",
        )

        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(margem_x, y, tipo_label.upper())
        y -= 10

        if timbre.get("mostrar_linha_cabecalho"):
            pdf.setStrokeColorRGB(0.82, 0.86, 0.90)
            pdf.line(margem_x, y, largura - margem_direita, y)

        y -= 18

    def nova_pagina():
        nonlocal y
        pdf.showPage()
        cabecalho()
        rodape()

    def check_space(espaco=55):
        if y < rodape_limite + espaco:
            nova_pagina()

    # --------------------------------------------------------
    # DESENHO DE CAMPOS
    # --------------------------------------------------------

    def secao(titulo):
        nonlocal y
        check_space(40)

        pdf.setFillColorRGB(0.94, 0.97, 0.96)
        pdf.roundRect(
            margem_x,
            y - 18,
            area_escrita_largura,
            23,
            5,
            fill=1,
            stroke=0,
        )

        pdf.setFillColorRGB(0, 0, 0)
        pdf.setFont("Helvetica-Bold", 9.5)
        pdf.drawString(margem_x + 8, y - 12, titulo.upper())

        y -= 32

    def campo(label, valor, col=1, full=False):
        nonlocal y

        valor = _safe(valor)
        col_gap = 10
        col_w = (area_escrita_largura - col_gap) / 2

        if full or col == 1:
            x = margem_x
            w = area_escrita_largura
        else:
            x = margem_x if col == 2 else margem_x + col_w + col_gap
            w = col_w

        linhas = _wrap(valor, 44 if w < area_escrita_largura else 92)
        altura_box = max(34, 24 + (len(linhas) * 10))

        check_space(altura_box + 8)

        pdf.setStrokeColorRGB(0.88, 0.90, 0.93)
        pdf.roundRect(x, y - altura_box, w, altura_box, 6, fill=0, stroke=1)

        pdf.setFont("Helvetica-Bold", 7.5)
        pdf.setFillColorRGB(0.30, 0.35, 0.42)
        pdf.drawString(x + 7, y - 11, label.upper())

        pdf.setFont("Helvetica", 8.5)
        pdf.setFillColorRGB(0, 0, 0)

        ty = y - 23
        for linha in linhas:
            pdf.drawString(x + 7, ty, linha)
            ty -= 10

        return altura_box

    def campos_lado_a_lado(campos):
        nonlocal y

        linha = []

        for item in campos:
            if len(item) == 2:
                label, valor = item
                full = False
            else:
                label, valor, full = item

            if full:
                if linha:
                    _desenhar_linha_dupla(linha)
                    linha = []

                h = campo(label, valor, full=True)
                y -= h + 8
            else:
                linha.append((label, valor))
                if len(linha) == 2:
                    _desenhar_linha_dupla(linha)
                    linha = []

        if linha:
            _desenhar_linha_dupla(linha)

    def _desenhar_linha_dupla(linha):
        nonlocal y

        col_gap = 10
        col_w = (area_escrita_largura - col_gap) / 2

        dados_linha = []
        altura_max = 34

        for label, valor in linha:
            linhas = _wrap(valor, 44)
            h = max(34, 24 + (len(linhas) * 10))
            altura_max = max(altura_max, h)
            dados_linha.append((label, valor, linhas, h))

        check_space(altura_max + 8)

        for idx, (label, valor, linhas, h) in enumerate(dados_linha):
            x = margem_x + idx * (col_w + col_gap)

            pdf.setStrokeColorRGB(0.88, 0.90, 0.93)
            pdf.roundRect(x, y - altura_max, col_w, altura_max, 6, fill=0, stroke=1)

            pdf.setFont("Helvetica-Bold", 7.5)
            pdf.setFillColorRGB(0.30, 0.35, 0.42)
            pdf.drawString(x + 7, y - 11, label.upper())

            pdf.setFont("Helvetica", 8.5)
            pdf.setFillColorRGB(0, 0, 0)

            ty = y - 23
            for linha_txt in linhas:
                pdf.drawString(x + 7, ty, linha_txt)
                ty -= 10

        y -= altura_max + 8

    def lista_checks(titulo, itens, colunas=3):
        nonlocal y
        secao(titulo)

        ativos = [(label, _sim_nao(dados.get(chave))) for label, chave in itens]
        texto = "   |   ".join([f"{label}: {valor}" for label, valor in ativos])

        h = campo("Itens avaliados", texto, full=True)
        y -= h + 8

    def tabela_json(titulo, raw, colunas):
        nonlocal y
        secao(titulo)

        try:
            linhas = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            linhas = []

        if not linhas:
            h = campo(titulo, "-", full=True)
            y -= h + 8
            return

        for i, item in enumerate(linhas, 1):
            texto = " | ".join([f"{label}: {item.get(chave, '-')}" for label, chave in colunas])
            h = campo(f"Registro {i}", texto, full=True)
            y -= h + 8

    # --------------------------------------------------------
    # SEÇÕES
    # --------------------------------------------------------

    def meta():
        secao("Identificação do Registro")
        campos_lado_a_lado([
            ("Paciente", avaliacao.get("paciente_nome")),
            ("Prontuário", avaliacao.get("paciente_prontuario")),
            ("CPF", avaliacao.get("paciente_cpf")),
            ("Registrado em", _data_br(avaliacao.get("criado_em"))),
            ("Profissional", avaliacao.get("usuario_nome")),
            ("CBO", avaliacao.get("usuario_cbo")),
        ])

    def pdf_fisioterapia():
        secao("Identificação")
        campos_lado_a_lado([
            ("Data da Avaliação", _data_br(dados.get("data_avaliacao"))),
            ("Data de Nascimento", _data_br(dados.get("data_nascimento"))),
            ("Idade", dados.get("idade")),
            ("Sexo", dados.get("sexo")),
            ("Telefone", dados.get("telefone")),
            ("Profissão/Ocupação", dados.get("profissao_ocupacao")),
            ("Endereço", dados.get("endereco"), True),
        ])

        secao("Anamnese Fisioterapêutica")
        campos_lado_a_lado([
            ("Queixa Principal", dados.get("queixa_principal"), True),
            ("História da Doença Atual", dados.get("historia_doenca_atual"), True),
            ("Medicamentos em Uso", dados.get("medicamentos_uso"), True),
            ("Objetivo do Paciente", dados.get("objetivo_paciente"), True),
        ])

        lista_checks("Antecedentes Pessoais", [
            ("Hipertensão", "antecedente_hipertensao"),
            ("Diabetes", "antecedente_diabetes"),
            ("Cardiopatias", "antecedente_cardiopatias"),
            ("Osteoporose", "antecedente_osteoporose"),
            ("Artrose", "antecedente_artrose"),
            ("Artrite", "antecedente_artrite"),
            ("Cirurgias", "antecedente_cirurgias"),
            ("Fraturas", "antecedente_fraturas"),
        ])

        campos_lado_a_lado([
            ("Outros antecedentes", dados.get("antecedentes_outros"), True),
        ])

        secao("Hábitos de Vida")
        campos_lado_a_lado([
            ("Atividade Física", dados.get("atividade_fisica")),
            ("Sono", dados.get("sono")),
            ("Tabagismo", dados.get("tabagismo")),
            ("Etilismo", dados.get("etilismo")),
        ])

        secao("Dor")
        campos_lado_a_lado([
            ("EVA", f"{dados.get('eva_dor', '0')}/10"),
            ("Local", dados.get("dor_local")),
            ("Tipo", dados.get("dor_tipo")),
            ("Irradiação", dados.get("dor_irradiacao")),
        ])

        lista_checks("Inspeção", [
            ("Postura", "inspecao_postura"),
            ("Marcha", "inspecao_marcha"),
            ("Edema", "inspecao_edema"),
            ("Atrofia Muscular", "inspecao_atrofia_muscular"),
            ("Hipertrofia", "inspecao_hipertrofia"),
            ("Cicatriz", "inspecao_cicatriz"),
            ("Deformidade", "inspecao_deformidade"),
            ("Alteração Temp.", "inspecao_alteracao_temperatura"),
        ])

        campos_lado_a_lado([
            ("Observações da Inspeção", dados.get("inspecao_observacoes"), True),
            ("Palpação", dados.get("palpacao"), True),
        ])

        tabela_json("Amplitude de Movimento - ADM", dados.get("adm_json"), [
            ("Segmento", "segmento"),
            ("Ativa", "ativa"),
            ("Passiva", "passiva"),
            ("Dor", "dor"),
            ("Limitação", "limitacao"),
        ])

        tabela_json("Força Muscular - Escala de Oxford", dados.get("forca_muscular_json"), [
            ("Segmento", "segmento"),
            ("Direito", "direito"),
            ("Esquerdo", "esquerdo"),
        ])

        secao("Sensibilidade e Funcionalidade")
        campos_lado_a_lado([
            ("Sensibilidade", dados.get("sensibilidade")),
            ("Marcha", dados.get("marcha")),
            ("Equilíbrio", dados.get("equilibrio")),
            ("Coordenação", dados.get("coordenacao")),
            ("Observações Sensibilidade", dados.get("sensibilidade_observacoes"), True),
        ])

        lista_checks("Atividades de Vida Diária - AVDs", [
            ("Sentar", "avd_sentar"),
            ("Levantar", "avd_levantar"),
            ("Agachar", "avd_agachar"),
            ("Subir escadas", "avd_subir_escadas"),
            ("Descer escadas", "avd_descer_escadas"),
            ("Vestir-se", "avd_vestir_se"),
            ("Banho", "avd_banho"),
            ("Trabalho", "avd_trabalho"),
            ("Esporte", "avd_esporte"),
        ])

        secao("Testes, Diagnóstico e Plano Terapêutico")
        campos_lado_a_lado([
            ("Testes Especiais", dados.get("testes_especiais"), True),
            ("Diagnóstico Cinético-Funcional", dados.get("diagnostico_cinetico_funcional"), True),
            ("Objetivos Terapêuticos", dados.get("objetivos_terapeuticos"), True),
            ("Frequência Semanal", dados.get("frequencia_semanal")),
            ("Número de Sessões", dados.get("numero_sessoes")),
            ("Reavaliação Prevista", _data_br(dados.get("reavaliacao_prevista"))),
            ("Prioridade", dados.get("prioridade")),
            ("Recursos Fisioterapêuticos", dados.get("recursos_fisioterapeuticos"), True),
            ("Condutas", dados.get("condutas"), True),
            ("Observações", dados.get("observacoes"), True),
        ])

    def pdf_generico():
        secao("Dados da Avaliação")

        for chave, valor in dados.items():
            if valor not in (None, "", "0"):
                h = campo(chave.replace("_", " ").title(), valor, full=True)
                y_local = h
                del y_local

    # --------------------------------------------------------
    # EXECUÇÃO
    # --------------------------------------------------------

    pdf.setTitle(f"Avaliacao_{_safe(avaliacao.get('id'))}")

    cabecalho()
    rodape()
    meta()

    if avaliacao.get("tipo") == "fisioterapia":
        pdf_fisioterapia()
    else:
        pdf_generico()

    rodape()
    pdf.save()
    buffer.seek(0)

    return buffer