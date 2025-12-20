# sgd/rh/routes.py
from datetime import date, timedelta
from flask import render_template
from . import rh_bp

@rh_bp.route('/', methods=['GET'])
def rh_home():
    """
    Renderiza o dashboard inicial do RH (front only).
    Pode passar alguns dados mock para o template exibir cards/avisos.
    """
    ctx = {
        "hoje": date.today().isoformat(),
        "metricas": {
            "colaboradores_total": 27,
            "ativos": 25,
            "ferias_pendentes": 3,
            "asos_vencendo_60d": 4,
        },
        "avisos": [
            {"tipo": "ASO", "colaborador": "Maria Santos", "vence_em": (date.today()+timedelta(days=28)).isoformat()},
            {"tipo": "Treinamento", "colaborador": "João Lima", "curso": "NR-32", "vence_em": (date.today()+timedelta(days=15)).isoformat()},
            {"tipo": "Férias", "colaborador": "Ana Souza", "inicio": (date.today()+timedelta(days=35)).isoformat(), "dias": 30},
        ],
        "unidades": [
            {"id": 1, "nome": "UBS Centro"},
            {"id": 2, "nome": "Clínica Escola"},
            {"id": 3, "nome": "UPA Municipal"},
        ],
    }
    return render_template('rh.html', **ctx)
