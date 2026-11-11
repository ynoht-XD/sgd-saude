"""SGD NFC: frequência assinada, via cartão ou designação da recepção.
A tabela permanece independente da frequência web existente.
"""
from __future__ import annotations
import base64, binascii, hashlib, io, secrets
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from flask import g, jsonify, request, session, render_template_string
from PIL import Image, UnidentifiedImageError
from db import conectar_db
from . import mobile_nfc_bp
from .auth import require_mobile_token, _one

TZ = ZoneInfo('America/Maceio')
MAX_PNG = 500_000

def db():
    conn = conectar_db(); conn.autocommit = False; return conn

def erro(m, status=400): return jsonify(ok=False, erro=m), status

def schema(cur):
    # frequencia_nfc.etiqueta_id tem FK para mobile_nfc_etiquetas: garante que ela exista
    # antes (num banco novo o painel/estacao podem ser o primeiro acesso, antes de /etiquetas).
    from .etiquetas import _schema as _schema_etiquetas
    _schema_etiquetas(cur)
    cur.execute('''CREATE TABLE IF NOT EXISTS public.frequencia_nfc (
        id BIGSERIAL PRIMARY KEY,
        clinica_id INTEGER NOT NULL REFERENCES public.clinicas(id),
        paciente_id INTEGER NOT NULL REFERENCES public.pacientes(id),
        etiqueta_id BIGINT REFERENCES public.mobile_nfc_etiquetas(id),
        designacao_id BIGINT,
        origem VARCHAR(16) NOT NULL DEFAULT 'NFC',
        registrado_por INTEGER NOT NULL REFERENCES public.usuarios(id),
        data_local DATE NOT NULL,
        registrada_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        assinatura_png BYTEA NOT NULL,
        assinatura_sha256 CHAR(64) NOT NULL,
        assinante_tipo VARCHAR(20) NOT NULL DEFAULT 'PACIENTE',
        assinante_nome VARCHAR(160),
        cancelada_em TIMESTAMPTZ,
        CONSTRAINT ck_frequencia_nfc_assinante CHECK (assinante_tipo IN ('PACIENTE','RESPONSAVEL'))
    )''')
    # Migração para tabelas criadas na primeira versão.
    cur.execute('ALTER TABLE public.frequencia_nfc ALTER COLUMN etiqueta_id DROP NOT NULL')
    cur.execute("ALTER TABLE public.frequencia_nfc ADD COLUMN IF NOT EXISTS designacao_id BIGINT")
    cur.execute("ALTER TABLE public.frequencia_nfc ADD COLUMN IF NOT EXISTS origem VARCHAR(16) NOT NULL DEFAULT 'NFC'")
    cur.execute('DROP INDEX IF EXISTS public.uq_frequencia_nfc_dia')
    cur.execute('ALTER TABLE public.frequencia_nfc ADD COLUMN IF NOT EXISTS cancelada_por INTEGER')
    cur.execute('ALTER TABLE public.frequencia_nfc ADD COLUMN IF NOT EXISTS cancelamento_motivo TEXT')
    cur.execute('ALTER TABLE public.frequencia_nfc ADD COLUMN IF NOT EXISTS excluida_em TIMESTAMPTZ')
    cur.execute('ALTER TABLE public.frequencia_nfc ADD COLUMN IF NOT EXISTS excluida_por INTEGER')
    cur.execute('ALTER TABLE public.frequencia_nfc ADD COLUMN IF NOT EXISTS exclusao_motivo TEXT')
    cur.execute('ALTER TABLE public.frequencia_nfc ADD COLUMN IF NOT EXISTS justificativa_retroativa TEXT')
    cur.execute('''CREATE TABLE IF NOT EXISTS public.frequencia_nfc_estacoes (
        id BIGSERIAL PRIMARY KEY, clinica_id INTEGER NOT NULL REFERENCES public.clinicas(id),
        usuario_id INTEGER NOT NULL REFERENCES public.usuarios(id),
        codigo_hash CHAR(64) NOT NULL UNIQUE,
        criada_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        expira_em TIMESTAMPTZ NOT NULL,
        ativa BOOLEAN NOT NULL DEFAULT TRUE
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS public.frequencia_nfc_designacoes (
        id BIGSERIAL PRIMARY KEY,
        estacao_id BIGINT NOT NULL REFERENCES public.frequencia_nfc_estacoes(id),
        clinica_id INTEGER NOT NULL REFERENCES public.clinicas(id),
        paciente_id INTEGER NOT NULL REFERENCES public.pacientes(id),
        designado_por INTEGER NOT NULL REFERENCES public.usuarios(id),
        criada_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        expira_em TIMESTAMPTZ NOT NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'PENDENTE',
        confirmada_em TIMESTAMPTZ
    )''')
    cur.execute('''CREATE INDEX IF NOT EXISTS idx_freq_nfc_designacoes_estacao
                   ON public.frequencia_nfc_designacoes(estacao_id,status,criada_em DESC)''')

def assinatura_png(payload):
    raw = str(payload.get('assinatura_png_base64') or '')
    if raw.startswith('data:image/png;base64,'): raw = raw.split(',', 1)[1]
    if len(raw) > 750_000: raise ValueError('Assinatura excede o limite de tamanho.')
    try:
        png = base64.b64decode(raw, validate=True)
        if not 100 <= len(png) <= MAX_PNG: raise ValueError('Assinatura vazia ou muito grande.')
        with Image.open(io.BytesIO(png)) as im:
            if im.format != 'PNG' or not 100 <= im.width <= 5000 or not 50 <= im.height <= 5000:
                raise ValueError('Dimensões da assinatura inválidas.')
            im.load()
    except (binascii.Error, UnidentifiedImageError, OSError) as exc:
        raise ValueError('Assinatura PNG inválida.') from exc
    return png

@mobile_nfc_bp.post('/frequencia/confirmar')
@require_mobile_token
def confirmar():
    payload = request.get_json(silent=True) or {}
    try: png = assinatura_png(payload)
    except ValueError as exc: return erro(str(exc))
    tipo = str(payload.get('assinante_tipo') or 'PACIENTE').upper()
    nome = str(payload.get('assinante_nome') or '').strip()
    if tipo not in ('PACIENTE','RESPONSAVEL'): return erro('Tipo de assinante inválido.')
    if tipo == 'RESPONSAVEL' and len(nome) < 3: return erro('Informe o nome do responsável.')
    if len(nome) > 160: return erro('Nome do assinante muito longo.')
    cid = int(g.mobile_nfc['clinica_id']); uid = int(g.mobile_nfc['usuario_id'])
    ticket_id = payload.get('designacao_id')
    ndef = str(payload.get('conteudo_ndef') or '')
    conn = db()
    try:
        with conn.cursor() as cur:
            schema(cur)
            if ticket_id is not None:
                try: ticket_id = int(ticket_id)
                except (ValueError, TypeError): return erro('Designação inválida.')
                cur.execute('''SELECT d.id,d.paciente_id,p.nome,p.prontuario
                               FROM public.frequencia_nfc_designacoes d
                               JOIN public.frequencia_nfc_estacoes e ON e.id=d.estacao_id
                               JOIN public.pacientes p ON p.id=d.paciente_id AND p.clinica_id=d.clinica_id
                               WHERE d.id=%s AND d.clinica_id=%s AND e.usuario_id=%s
                                 AND e.ativa AND e.expira_em>NOW() AND d.expira_em>NOW()
                                 AND d.status='PENDENTE' FOR UPDATE OF d''', (ticket_id,cid,uid))
                paciente = _one(cur)
                if not paciente: return erro('Designação expirada, cancelada ou já utilizada.',409)
                etiqueta_id = None; origem = 'RECEPCAO'
            else:
                if not ndef.startswith('SGDNFC1:') or not 40 <= len(ndef) <= 110:
                    return erro('Etiqueta NFC inválida.')
                digest = hashlib.sha256(ndef.encode('utf-8')).hexdigest()
                cur.execute('''SELECT p.id AS paciente_id,p.nome,p.prontuario,e.id AS etiqueta_id
                               FROM public.mobile_nfc_etiquetas e
                               JOIN public.pacientes p ON p.id=e.paciente_id AND p.clinica_id=e.clinica_id
                               WHERE e.token_hash=%s AND e.clinica_id=%s
                                 AND e.ativada_em IS NOT NULL AND e.revogada_em IS NULL''',(digest,cid))
                paciente = _one(cur)
                if not paciente: return erro('Etiqueta sem vínculo ativo nesta clínica.',404)
                etiqueta_id = paciente['etiqueta_id']; origem = 'NFC'
            hoje = datetime.now(TZ).date()
            cur.execute('''INSERT INTO public.frequencia_nfc
                (clinica_id,paciente_id,etiqueta_id,designacao_id,origem,registrado_por,data_local,
                 assinatura_png,assinatura_sha256,assinante_tipo,assinante_nome)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (clinica_id,paciente_id,data_local) WHERE cancelada_em IS NULL
                DO NOTHING RETURNING id''',
                (cid,paciente['paciente_id'],etiqueta_id,ticket_id,origem,uid,hoje,
                 png,hashlib.sha256(png).hexdigest(),tipo,nome or None))
            registro = _one(cur)
            if not registro: return erro('Paciente já possui frequência NFC registrada hoje.',409)
            if ticket_id is not None:
                cur.execute("UPDATE public.frequencia_nfc_designacoes SET status='CONFIRMADA',confirmada_em=NOW() WHERE id=%s",(ticket_id,))
        conn.commit()
        return jsonify(ok=True, frequencia_id=registro['id'],origem=origem,
                       paciente={'nome':paciente['nome'],'prontuario':paciente['prontuario']},
                       mensagem='Frequência registrada com assinatura.')
    except Exception:
        conn.rollback(); raise
    finally: conn.close()

@mobile_nfc_bp.post('/estacao/criar')
@require_mobile_token
def criar_estacao():
    cid=int(g.mobile_nfc['clinica_id']); uid=int(g.mobile_nfc['usuario_id'])
    codigo=f'{secrets.randbelow(1000000):06d}'
    digest=hashlib.sha256(codigo.encode()).hexdigest()
    conn=db()
    try:
        with conn.cursor() as cur:
            schema(cur)
            cur.execute('''UPDATE public.frequencia_nfc_estacoes SET ativa=FALSE
                           WHERE clinica_id=%s AND usuario_id=%s AND ativa''',(cid,uid))
            cur.execute('''INSERT INTO public.frequencia_nfc_estacoes
                           (clinica_id,usuario_id,codigo_hash,expira_em)
                           VALUES (%s,%s,%s,NOW()+INTERVAL '8 hours') RETURNING id''',(cid,uid,digest))
            est=_one(cur)
        conn.commit()
        return jsonify(ok=True,estacao_id=est['id'],codigo=codigo,expira_em_minutos=480)
    except Exception: conn.rollback(); raise
    finally: conn.close()

@mobile_nfc_bp.get('/estacao/pendente')
@require_mobile_token
def pendente():
    cid=int(g.mobile_nfc['clinica_id']); uid=int(g.mobile_nfc['usuario_id'])
    conn=db()
    try:
        with conn.cursor() as cur:
            schema(cur)
            cur.execute('''SELECT d.id AS designacao_id,p.nome,p.prontuario,p.nascimento
                           FROM public.frequencia_nfc_designacoes d
                           JOIN public.frequencia_nfc_estacoes e ON e.id=d.estacao_id
                           JOIN public.pacientes p ON p.id=d.paciente_id
                           WHERE e.usuario_id=%s AND d.clinica_id=%s AND e.ativa
                             AND e.expira_em>NOW() AND d.expira_em>NOW() AND d.status='PENDENTE'
                           ORDER BY d.criada_em DESC LIMIT 1''',(uid,cid))
            item=_one(cur)
        conn.commit()
        return jsonify(ok=True,designacao=item)
    except Exception: conn.rollback(); raise
    finally: conn.close()

@mobile_nfc_bp.post('/estacao/recusar')
@require_mobile_token
def recusar():
    data=request.get_json(silent=True) or {}
    try: did=int(data.get('designacao_id'))
    except (TypeError,ValueError): return erro('Designação inválida.')
    cid=int(g.mobile_nfc['clinica_id']); uid=int(g.mobile_nfc['usuario_id'])
    conn=db()
    try:
        with conn.cursor() as cur:
            cur.execute('''UPDATE public.frequencia_nfc_designacoes d SET status='RECUSADA'
                           FROM public.frequencia_nfc_estacoes e
                           WHERE d.estacao_id=e.id AND d.id=%s AND d.clinica_id=%s
                             AND e.usuario_id=%s AND d.status='PENDENTE' RETURNING d.id''',(did,cid,uid))
            ok=_one(cur)
        conn.commit()
        return jsonify(ok=bool(ok))
    except Exception: conn.rollback(); raise
    finally: conn.close()

# Página administrativa acessada no computador autenticado no SGD.
@mobile_nfc_bp.get('/recepcao')
def pagina_recepcao():
    if not session.get('usuario_id') or not session.get('clinica_id'):
        return 'Acesse primeiro o SGD com uma conta da recepção.',401
    return render_template_string('''<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<title>SGD | Enviar assinatura ao celular</title><style>
body{font:16px Arial;max-width:780px;margin:45px auto;padding:20px;color:#172b44}
input,button{padding:13px;border:1px solid #cbd5e1;border-radius:9px;font-size:16px}
input{width:95%;margin:7px 0}button{background:#1768be;color:white;cursor:pointer}
li{padding:12px;border-bottom:1px solid #eee;cursor:pointer}li:hover{background:#e9f2ff}
</style><h2>Enviar assinatura ao celular</h2>
<p>O celular mostra um código de 6 dígitos na aba Frequência. Informe-o abaixo.</p>
<label>Código do celular</label><input id="codigo" maxlength="6" placeholder="000000">
<label>Nome ou prontuário do paciente</label><input id="busca" placeholder="Pesquisar paciente">
<button onclick="pesquisar()">Pesquisar</button><ul id="lista"></ul><p id="aviso"></p>
<script>
const api=location.pathname.replace(/\\/recepcao$/, '');
async function req(path,body){const r=await fetch(api+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const j=await r.json();if(!r.ok)throw Error(j.erro||'HTTP '+r.status);return j;}
async function pesquisar(){const q=document.getElementById('busca').value;
try{const r=await fetch(api+'/recepcao/pacientes?q='+encodeURIComponent(q));const j=await r.json();if(!r.ok)throw Error(j.erro);document.getElementById('lista').innerHTML='';j.pacientes.forEach(p=>{const li=document.createElement('li');li.textContent=p.nome+' | '+(p.prontuario||'')+' | Nasc.: '+(p.nascimento||'—');li.onclick=()=>enviar(p.id,p.nome);document.getElementById('lista').append(li)})}catch(e){document.getElementById('aviso').textContent=e.message}}
async function enviar(id,nome){if(!confirm('Enviar '+nome+' para assinatura no celular?'))return;
try{const j=await req('/recepcao/designar',{codigo:document.getElementById('codigo').value,paciente_id:id});document.getElementById('aviso').textContent='Solicitação enviada ao celular. Designação nº '+j.designacao_id;}catch(e){document.getElementById('aviso').textContent=e.message}}
</script></html>''')

def recepcao_auth():
    uid=session.get('usuario_id'); cid=session.get('clinica_id')
    try: return int(uid),int(cid)
    except (ValueError,TypeError): return None

@mobile_nfc_bp.get('/recepcao/pacientes')
def recepcao_pacientes():
    auth=recepcao_auth()
    if not auth: return erro('Sessão SGD não autenticada.',401)
    q=str(request.args.get('q') or '').strip()
    if len(q)<2: return erro('Informe ao menos dois caracteres.')
    conn=db()
    try:
        with conn.cursor() as cur:
            cur.execute('''SELECT id,nome,prontuario,nascimento FROM public.pacientes
                           WHERE clinica_id=%s AND (nome ILIKE %s OR prontuario=%s)
                           ORDER BY nome LIMIT 25''',(auth[1],'%'+q+'%',q))
            cols=[d.name for d in cur.description]
            items=[dict(zip(cols,row)) for row in cur.fetchall()]
        return jsonify(ok=True,pacientes=items)
    finally: conn.close()

@mobile_nfc_bp.post('/recepcao/designar')
def designar():
    auth=recepcao_auth()
    if not auth: return erro('Sessão SGD não autenticada.',401)
    data=request.get_json(silent=True) or {}
    codigo=str(data.get('codigo') or '').strip()
    if len(codigo)!=6 or not codigo.isdigit(): return erro('Informe o código de seis dígitos do celular.')
    try: pid=int(data.get('paciente_id'))
    except (ValueError,TypeError): return erro('Paciente inválido.')
    digest=hashlib.sha256(codigo.encode()).hexdigest()
    conn=db()
    try:
        with conn.cursor() as cur:
            schema(cur)
            cur.execute('''SELECT id FROM public.frequencia_nfc_estacoes
                           WHERE codigo_hash=%s AND clinica_id=%s AND ativa AND expira_em>NOW()''',(digest,auth[1]))
            est=_one(cur)
            if not est: return erro('Código inexistente ou expirado para esta clínica.',404)
            cur.execute('SELECT id FROM public.pacientes WHERE id=%s AND clinica_id=%s',(pid,auth[1]))
            if not _one(cur): return erro('Paciente não pertence à clínica.',404)
            cur.execute('''UPDATE public.frequencia_nfc_designacoes SET status='CANCELADA'
                           WHERE estacao_id=%s AND status='PENDENTE' ''',(est['id'],))
            cur.execute('''INSERT INTO public.frequencia_nfc_designacoes
                           (estacao_id,clinica_id,paciente_id,designado_por,expira_em)
                           VALUES (%s,%s,%s,%s,NOW()+INTERVAL '5 minutes') RETURNING id''',
                        (est['id'],auth[1],pid,auth[0]))
            result=_one(cur)
        conn.commit()
        return jsonify(ok=True,designacao_id=result['id'])
    except Exception: conn.rollback(); raise
    finally: conn.close()
