from flask import render_template
from . import digitador_bp

@digitador_bp.route("/apac", methods=["GET", "POST"])
def apac():
    return render_template("apac.html")

@digitador_bp.route("/bpai", methods=["GET", "POST"])
def bpai():
    return render_template("bpai.html")  # stub inicial

@digitador_bp.route("/ciha", methods=["GET", "POST"])
def ciha():
    return render_template("ciha.html")  # stub inicial
