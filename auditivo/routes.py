# auditivo/routes.py
from flask import render_template
from . import auditivo_bp

@auditivo_bp.get("/exames")
def exames_auditivos():
    # Apenas renderiza o front. Depois conectamos o POST.
    return render_template("exames_auditivos.html")
