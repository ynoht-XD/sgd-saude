# sgd/financeiro/routes.py
from datetime import date, timedelta
from flask import render_template, jsonify, request
from . import financeiro_bp

@financeiro_bp.route("/", methods=["GET"])
def financeiro_home():
    """Renderiza o dashboard inicial do Financeiro (front only)."""
    hoje = date.today()

    ctx = {
        "data_ref": hoje.isoformat(),
        "kpis": {
            "saldo_caixa": 125_430.72,
            "receber_30d": 87_900.00,
            "pagar_30d": 64_350.35,
            "inadimplencia": 4.2,   # %
        },
        # mock para cartões/quadros rápidos
        "contas": [
            {"apelido": "Banco A - Corrente", "saldo": 82_100.55},
            {"apelido": "Banco B - Aplicação", "saldo": 38_250.17},
            {"apelido": "Caixa físico", "saldo": 5_080.00},
        ],
        "avisos": [
            {"tipo": "NFSe", "msg": "2 RPS pendentes de emissão", "acao": "Ver RPS"},
            {"tipo": "Conciliação", "msg": "11 lançamentos não conciliados", "acao": "Conciliar"},
            {"tipo": "Aging", "msg": "R$ 12.450,00 em atraso > 30 dias", "acao": "Cobrança"},
        ],
        # listas para possível render/JS
        "centros_custo": [
            {"id": 1, "nome": "UBS Centro"},
            {"id": 2, "nome": "Clínica Escola"},
            {"id": 3, "nome": "UPA Municipal"},
        ],
    }
    return render_template("financeiro.html", **ctx)

# --- (opcional) endpoints mock para o front consumir depois ---

@financeiro_bp.route("/api/fluxo-caixa", methods=["GET"])
def api_fluxo_caixa():
    """Retorna pontos de fluxo de caixa projetado (mock)."""
    base = date.today()
    pontos = []
    saldo = 120_000.0
    for i in range(0, 14):
        d = base + timedelta(days=i)
        # entradas/saídas fictícias
        entradas = 8_000.0 if i in (2, 5, 9) else 2_000.0
        saidas = 3_500.0 if i in (1, 4, 8, 12) else 1_000.0
        saldo += entradas - saidas
        pontos.append({
            "data": d.isoformat(),
            "entradas": round(entradas, 2),
            "saidas": round(saidas, 2),
            "saldo": round(saldo, 2),
        })
    return jsonify(pontos)

@financeiro_bp.route("/api/receber", methods=["GET"])
def api_receber():
    """Lista títulos a receber (mock)."""
    itens = [
        {"id": 101, "emissao": "2025-08-05", "venc": "2025-08-25", "pagador": "Convênio Alfa", "paciente": "João Silva", "valor": 420.00, "status": "EM_ABERTO", "centro_custo": 1},
        {"id": 102, "emissao": "2025-08-02", "venc": "2025-08-20", "pagador": "Particular", "paciente": "Ana Souza", "valor": 180.00, "status": "PAGO", "centro_custo": 2},
        {"id": 103, "emissao": "2025-07-28", "venc": "2025-08-10", "pagador": "Convênio Beta", "paciente": "Carlos Pereira", "valor": 310.00, "status": "EM_ATRASO", "centro_custo": 1},
    ]
    return jsonify(itens)

@financeiro_bp.route("/api/pagar", methods=["GET"])
def api_pagar():
    """Lista títulos a pagar (mock)."""
    itens = [
        {"id": 201, "emissao": "2025-08-01", "venc": "2025-08-25", "fornecedor": "Fornecedor X", "descricao": "Materiais clínicos", "valor": 2_430.90, "status": "EM_ABERTO", "centro_custo": 1},
        {"id": 202, "emissao": "2025-08-03", "venc": "2025-08-18", "fornecedor": "Energia", "descricao": "Conta de luz", "valor": 1_180.30, "status": "PROGRAMADO", "centro_custo": 3},
        {"id": 203, "emissao": "2025-07-29", "venc": "2025-08-12", "fornecedor": "Serviços TI", "descricao": "Suporte mensal", "valor": 890.00, "status": "PAGO", "centro_custo": 2},
    ]
    return jsonify(itens)
