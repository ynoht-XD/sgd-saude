"""Controle administrativo de frequência NFC: histórico, designações e exportações.
Registrar em mobile_nfc/__init__.py: from . import controle_freq
Dependências de exportação: pip install reportlab XlsxWriter
"""
from __future__ import annotations
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo
from flask import jsonify, request, session, render_template, send_file, abort, g
from psycopg.errors import UniqueViolation
from db import conectar_db
from . import mobile_nfc_bp
from .frequencia_nfc import schema
import hashlib, base64
from .auth import require_mobile_token

TZ = ZoneInfo('America/Maceio')

def auth():
    try:
        uid, cid = int(session.get('usuario_id')), int(session.get('clinica_id'))
        if uid > 0 and cid > 0: return uid, cid
    except (TypeError, ValueError): pass
    return None

def deny():
    return jsonify(ok=False, erro='Acesso não autenticado no SGD.'), 401

def csrf_ok():
    import hmac
    esperado = str(session.get('csrf_freq_nfc') or '')
    enviado = str(request.headers.get('X-CSRF-Token') or '')
    # Sessao sem token (pagina do painel/recepcao nunca aberta) NUNCA vale: '' == '' nao pode passar.
    return bool(esperado) and hmac.compare_digest(esperado, enviado)

def connect():
    conn = conectar_db()
    conn.autocommit = False
    return conn

def one(cur):
    """Suporta cursores psycopg que retornam dict_row ou tuplas."""
    row = cur.fetchone()
    if row is None:
        return None
    if isinstance(row, Mapping):
        return dict(row)
    return dict(zip([c.name for c in cur.description], row))

def rows(cur):
    """Preserva os valores reais das colunas, nunca seus nomes."""
    result = cur.fetchall()
    if not result:
        return []
    if isinstance(result[0], Mapping):
        return [dict(row) for row in result]
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in result]

def period():
    today = datetime.now(TZ).date()
    try:
        start = date.fromisoformat(request.args.get('inicio') or str(today.replace(day=1)))
        end = date.fromisoformat(request.args.get('fim') or str(today))
    except ValueError: raise ValueError('Datas inválidas.')
    if start > end or (end-start).days > 366: raise ValueError('Informe um período de até 367 dias.')
    return start, end

def filters(cid):
    start, end = period()
    q = str(request.args.get('q') or '').strip()[:100]
    origin = str(request.args.get('origem') or '').upper()
    status = str(request.args.get('situacao') or 'ATIVAS').upper()
    if origin not in ('', 'NFC', 'RECEPCAO'): raise ValueError('Origem inválida.')
    if status not in ('ATIVAS', 'CANCELADAS', 'TODAS'): raise ValueError('Situação inválida.')
    where = ['f.clinica_id=%s', 'f.data_local BETWEEN %s AND %s']
    args = [cid, start, end]
    if q:
        where.append('(p.nome ILIKE %s OR p.prontuario ILIKE %s)')
        args.extend(['%'+q+'%', '%'+q+'%'])
    if origin:
        where.append('f.origem=%s'); args.append(origin)
    if status == 'ATIVAS': where.append('f.cancelada_em IS NULL AND f.excluida_em IS NULL')
    if status == 'CANCELADAS': where.append('f.cancelada_em IS NOT NULL AND f.excluida_em IS NULL')
    where.append('f.excluida_em IS NULL')
    return ' AND '.join(where), args, start, end

SELECT = '''SELECT f.id,f.data_local,f.registrada_em,f.origem,f.assinante_tipo,
                   f.assinante_nome,f.cancelada_em,f.designacao_id,f.cancelamento_motivo,
                   p.nome AS paciente,p.prontuario,p.nascimento,
                   u.nome AS profissional,
                   OCTET_LENGTH(f.assinatura_png) AS assinatura_bytes
            FROM public.frequencia_nfc f
            JOIN public.pacientes p ON p.id=f.paciente_id AND p.clinica_id=f.clinica_id
            LEFT JOIN public.usuarios u ON u.id=f.registrado_por'''

def serialize(data):
    for row in data:
        for k,v in list(row.items()):
            if isinstance(v,(date,datetime)): row[k]=v.isoformat()
    return data

@mobile_nfc_bp.get('/controle-frequencia-nfc')
def controle_pagina():
    if not auth(): return 'Faça login no SGD para acessar o controle NFC.', 401
    import secrets
    session.setdefault('csrf_freq_nfc', secrets.token_urlsafe(32))
    return render_template('controle_freq.html', csrf=session['csrf_freq_nfc'], pode_excluir=_is_admin(*auth()))

@mobile_nfc_bp.get('/controle-frequencia-nfc/api/historico')
def controle_historico():
    a=auth()
    if not a: return deny()
    try:
        where,args,start,end=filters(a[1]); page=max(1,min(10000,int(request.args.get('pagina') or 1)))
    except (ValueError,TypeError) as exc: return jsonify(ok=False,erro=str(exc)),400
    conn=connect()
    try:
        with conn.cursor() as cur:
            schema(cur)
            cur.execute('SELECT COUNT(*) AS total,COUNT(*) FILTER (WHERE f.origem=\'NFC\') AS nfc,COUNT(*) FILTER (WHERE f.origem=\'RECEPCAO\') AS recepcao,COUNT(*) FILTER (WHERE f.cancelada_em IS NOT NULL) AS canceladas FROM public.frequencia_nfc f JOIN public.pacientes p ON p.id=f.paciente_id AND p.clinica_id=f.clinica_id WHERE '+where,args)
            stats=one(cur)
            cur.execute(SELECT+' WHERE '+where+' ORDER BY f.registrada_em DESC,f.id DESC LIMIT 30 OFFSET %s',args+[(page-1)*30])
            items=rows(cur)
        conn.commit()
        return jsonify(ok=True,registros=serialize(items),indicadores=stats,pagina=page,inicio=str(start),fim=str(end))
    except Exception:
        conn.rollback(); raise
    finally: conn.close()

@mobile_nfc_bp.get('/controle-frequencia-nfc/api/designacoes')
def controle_designacoes():
    a=auth()
    if not a: return deny()
    conn=connect()
    try:
        with conn.cursor() as cur:
            schema(cur)
            cur.execute('''SELECT d.id,d.status,d.criada_em,d.expira_em,d.confirmada_em,
                                  p.nome AS paciente,p.prontuario,e.id AS estacao_id,
                                  u.nome AS designado_por
                           FROM public.frequencia_nfc_designacoes d
                           JOIN public.pacientes p ON p.id=d.paciente_id AND p.clinica_id=d.clinica_id
                           JOIN public.frequencia_nfc_estacoes e ON e.id=d.estacao_id
                           LEFT JOIN public.usuarios u ON u.id=d.designado_por
                           WHERE d.clinica_id=%s ORDER BY d.criada_em DESC LIMIT 50''',(a[1],))
            items=rows(cur)
            cur.execute('''SELECT e.id,e.usuario_id,u.nome AS operador,e.criada_em,e.expira_em
                           FROM public.frequencia_nfc_estacoes e
                           LEFT JOIN public.usuarios u ON u.id=e.usuario_id
                           WHERE e.clinica_id=%s AND e.ativa AND e.expira_em>NOW()
                           ORDER BY e.id DESC''',(a[1],))
            stations=rows(cur)
        conn.commit()
        return jsonify(ok=True,designacoes=serialize(items),estacoes=serialize(stations))
    except Exception: conn.rollback(); raise
    finally: conn.close()

@mobile_nfc_bp.post('/controle-frequencia-nfc/api/designar')
def controle_designar():
    a=auth()
    if not a: return deny()
    if not csrf_ok(): return jsonify(ok=False,erro='Token de proteção inválido. Recarregue a página.'),403
    body=request.get_json(silent=True) or {}
    try: pid=int(body.get('paciente_id')); station=int(body.get('estacao_id'))
    except (TypeError,ValueError): return jsonify(ok=False,erro='Paciente e estação obrigatórios.'),400
    conn=connect()
    try:
        with conn.cursor() as cur:
            schema(cur)
            cur.execute('SELECT id FROM public.pacientes WHERE id=%s AND clinica_id=%s',(pid,a[1]))
            if not one(cur): return jsonify(ok=False,erro='Paciente não pertence à clínica.'),404
            cur.execute('''SELECT id FROM public.frequencia_nfc_estacoes
                           WHERE id=%s AND clinica_id=%s AND ativa AND expira_em>NOW() FOR UPDATE''',(station,a[1]))
            if not one(cur): return jsonify(ok=False,erro='Estação não está ativa.'),409
            cur.execute("UPDATE public.frequencia_nfc_designacoes SET status='CANCELADA' WHERE estacao_id=%s AND clinica_id=%s AND status='PENDENTE'",(station,a[1]))
            cur.execute('''INSERT INTO public.frequencia_nfc_designacoes
                           (estacao_id,clinica_id,paciente_id,designado_por,expira_em)
                           VALUES (%s,%s,%s,%s,NOW()+INTERVAL '5 minutes') RETURNING id''',(station,a[1],pid,a[0]))
            result=one(cur)
        conn.commit()
        return jsonify(ok=True,designacao_id=result['id'])
    except Exception: conn.rollback(); raise
    finally: conn.close()

@mobile_nfc_bp.post('/controle-frequencia-nfc/api/designacoes/<int:did>/cancelar')
def controle_cancelar(did):
    a=auth()
    if not a: return deny()
    if not csrf_ok(): return jsonify(ok=False,erro='Token de proteção inválido.'),403
    conn=connect()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE public.frequencia_nfc_designacoes SET status='CANCELADA' WHERE id=%s AND clinica_id=%s AND status='PENDENTE' RETURNING id",(did,a[1]))
            result=one(cur)
        conn.commit()
        return jsonify(ok=bool(result),erro=None if result else 'Designação não está pendente.')
    except Exception: conn.rollback(); raise
    finally: conn.close()

@mobile_nfc_bp.get('/controle-frequencia-nfc/api/pacientes')
def controle_pacientes():
    a=auth()
    if not a: return deny()
    q=str(request.args.get('q') or '').strip()[:100]
    if len(q)<3: return jsonify(ok=False,erro='Digite ao menos três caracteres.'),400
    conn=connect()
    try:
        with conn.cursor() as cur:
            cur.execute('''SELECT id,nome,prontuario,nascimento FROM public.pacientes
                           WHERE clinica_id=%s AND (nome ILIKE %s OR prontuario ILIKE %s)
                           ORDER BY CASE WHEN prontuario=%s THEN 0 ELSE 1 END,nome LIMIT 30''',(a[1],'%'+q+'%','%'+q+'%',q))
            data=rows(cur)
        return jsonify(ok=True,pacientes=serialize(data))
    finally: conn.close()

@mobile_nfc_bp.get('/controle-frequencia-nfc/api/assinatura/<int:fid>')
def controle_assinatura(fid):
    a=auth()
    if not a: return deny()
    conn=connect()
    try:
        with conn.cursor() as cur:
            cur.execute('''SELECT assinatura_png FROM public.frequencia_nfc
                           WHERE id=%s AND clinica_id=%s AND excluida_em IS NULL''',(fid,a[1]))
            item=one(cur)
        if not item: abort(404)
        resp=send_file(BytesIO(bytes(item['assinatura_png'])),mimetype='image/png',download_name=f'assinatura_{fid}.png',as_attachment=False)
        resp.headers['Cache-Control']='no-store, private'
        resp.headers['X-Content-Type-Options']='nosniff'
        return resp
    finally: conn.close()

@mobile_nfc_bp.get('/controle-frequencia-nfc/exportar/<tipo>')
def controle_exportar(tipo):
    a=auth()
    if not a: return deny()
    if tipo not in ('pdf','xlsx'): abort(404)
    try: where,args,start,end=filters(a[1])
    except ValueError as exc: return jsonify(ok=False,erro=str(exc)),400
    conn=connect()
    try:
        with conn.cursor() as cur:
            schema(cur)
            cur.execute(SELECT.replace(' FROM public.frequencia_nfc f', (',f.assinatura_png AS imagem_png' if tipo=='pdf' else '')+' FROM public.frequencia_nfc f')+' WHERE '+where+' ORDER BY f.registrada_em DESC,f.id DESC LIMIT '+('2000' if tipo=='pdf' else '25000'),args)
            data=rows(cur)
        conn.commit()
    except Exception: conn.rollback(); raise
    finally: conn.close()
    output=BytesIO()
    headers=['ID','Paciente','Prontuário','Nascimento','Data','Registrada em','Origem','Situação','Profissional','Assinante','Nome do assinante','Bytes assinatura']
    def fields(r):
        return [r['id'],r['paciente'],r['prontuario'],str(r['nascimento'] or ''),str(r['data_local']),str(r['registrada_em']),r['origem'],'CANCELADA' if r['cancelada_em'] else 'ATIVA',r['profissional'] or '',r['assinante_tipo'],r['assinante_nome'] or '',r['assinatura_bytes']]
    if tipo=='xlsx':
        import xlsxwriter
        wb=xlsxwriter.Workbook(output,{'in_memory':True})
        ws=wb.add_worksheet('Frequências NFC')
        title=wb.add_format({'bold':True,'font_color':'white','bg_color':'#15385B','font_size':14})
        head=wb.add_format({'bold':True,'bg_color':'#DDEAF7','border':1,'text_wrap':True})
        ws.merge_range(0,0,0,len(headers)-1,'SGD Saúde | Frequências NFC',title)
        ws.write(1,0,f'Período: {start:%d/%m/%Y} a {end:%d/%m/%Y} | Registros: {len(data)}')
        for col,h in enumerate(headers): ws.write(3,col,h,head)
        for row,r in enumerate(data,4):
            for col,value in enumerate(fields(r)): ws.write(row,col,value)
        ws.autofilter(3,0,max(4,len(data)+3),len(headers)-1)
        ws.freeze_panes(4,0)
        ws.set_column('A:A',9);ws.set_column('B:B',37);ws.set_column('C:D',17)
        ws.set_column('E:F',23);ws.set_column('G:L',20)
        wb.close()
        output.seek(0)
        return send_file(output,mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',as_attachment=True,download_name='frequencia_nfc.xlsx')
    from reportlab.platypus import SimpleDocTemplate,Paragraph,LongTable,TableStyle,Spacer,Image as RLImage,KeepTogether
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.pagesizes import landscape,A4
    from reportlab.lib.units import mm
    from xml.sax.saxutils import escape
    doc=SimpleDocTemplate(output,pagesize=landscape(A4),leftMargin=12*mm,rightMargin=12*mm,topMargin=12*mm,bottomMargin=12*mm)
    styles=getSampleStyleSheet()
    story=[Paragraph('SGD Saúde | Controle de frequência NFC',styles['Title']),Paragraph(f'Período: {start:%d/%m/%Y} a {end:%d/%m/%Y} | {len(data)} registros',styles['Normal']),Spacer(1,8)]
    th=['ID','Paciente','Pront.','Data','Origem','Situação','Profissional','Assinatura']
    cells=[th]
    for r in data:
        vals=[r['id'],r['paciente'],r['prontuario'],r['data_local'],r['origem'],'Cancelada' if r['cancelada_em'] else 'Ativa',r['profissional'] or '']
        row=[Paragraph(escape(str(v or '')),styles['BodyText']) for v in vals]
        try:
            image=RLImage(BytesIO(bytes(r['imagem_png'])),width=43*mm,height=19*mm,kind='proportional')
            row.append(image)
        except Exception:
            row.append(Paragraph('Indisponível',styles['BodyText']))
        cells.append(row)
    t=LongTable(cells,colWidths=[11*mm,51*mm,21*mm,23*mm,21*mm,22*mm,54*mm,55*mm],repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#DDEAF7')),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#CBD5E1')),('VALIGN',(0,0),(-1,-1),'TOP'),('FONTSIZE',(0,0),(-1,0),9),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
    story.append(t);doc.build(story);output.seek(0)
    return send_file(output,mimetype='application/pdf',as_attachment=True,download_name='frequencia_nfc.pdf')


# Eventos temporários de assinatura. A imagem parcial não é a assinatura legal:
# o documento definitivo é apenas a assinatura salva em frequencia_nfc.
def live_schema(cur):
    cur.execute('''CREATE TABLE IF NOT EXISTS public.frequencia_nfc_live (
        clinica_id INTEGER NOT NULL, chave VARCHAR(90) NOT NULL,
        paciente_id INTEGER, status VARCHAR(20) NOT NULL DEFAULT 'IDENTIFICADO',
        imagem_png BYTEA, versao BIGINT NOT NULL DEFAULT 0,
        atualizada_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (clinica_id,chave)
    )''')

def live_key(body):
    did=body.get('designacao_id')
    if did is not None:
        try:
            n=int(did)
            if n>0: return 'D:'+str(n)
        except (ValueError,TypeError): pass
        return None
    value=str(body.get('conteudo_ndef') or '')
    if value.startswith('SGDNFC1:') and 40<=len(value)<=110:
        return 'N:'+hashlib.sha256(value.encode()).hexdigest()
    return None

@mobile_nfc_bp.post('/controle-frequencia-nfc/mobile/evento')
@require_mobile_token
def mobile_live_event():
    body=request.get_json(silent=True) or {}
    key=live_key(body)
    if not key: return jsonify(ok=False,erro='Identificação inválida.'),400
    status=str(body.get('status') or '').upper()
    if status not in ('IDENTIFICADO','ESCREVENDO','SALVA','CANCELADA'):
        return jsonify(ok=False,erro='Estado inválido.'),400
    image=None
    if status=='ESCREVENDO':
        raw=str(body.get('imagem') or '')
        if len(raw)>220000: return jsonify(ok=False,erro='Prévia muito grande.'),413
        try:
            image=base64.b64decode(raw,validate=True)
            if not image.startswith(b'\x89PNG\r\n\x1a\n') or len(image)>160000: raise ValueError()
        except Exception: return jsonify(ok=False,erro='Imagem inválida.'),400
    cid=int(g.mobile_nfc['clinica_id']); uid=int(g.mobile_nfc['usuario_id'])
    conn=connect()
    try:
        with conn.cursor() as cur:
            live_schema(cur)
            if key.startswith('D:'):
                cur.execute('''SELECT d.paciente_id FROM public.frequencia_nfc_designacoes d
                    JOIN public.frequencia_nfc_estacoes e ON e.id=d.estacao_id
                    WHERE d.id=%s AND d.clinica_id=%s AND e.usuario_id=%s
                    AND e.ativa AND e.expira_em>NOW()''',(int(key[2:]),cid,uid))
            else:
                cur.execute('''SELECT e.paciente_id FROM public.mobile_nfc_etiquetas e
                    WHERE e.token_hash=%s AND e.clinica_id=%s AND e.ativada_em IS NOT NULL
                    AND e.revogada_em IS NULL''',(key[2:],cid))
            found=one(cur)
            if not found: return jsonify(ok=False,erro='Paciente ou estação não reconhecidos.'),404
            cur.execute('SELECT status FROM public.frequencia_nfc_live WHERE clinica_id=%s AND chave=%s FOR UPDATE',(cid,key))
            previous=one(cur)
            # Esta tabela é só a pré-visualização ao vivo; a proteção contra duplicidade está em
            # frequencia_nfc (uq_frequencia_nfc_dia). Um NOVO TOQUE (IDENTIFICADO) sempre reinicia a
            # linha, mesmo depois de CONFIRMADA/CANCELADA (antes ela ficava travada para sempre).
            # Prévias tardias (ESCREVENDO/SALVA/CANCELADA) de uma sessão já encerrada continuam
            # ignoradas, para o celular não "ressuscitar" no painel uma assinatura recém-cancelada.
            if previous and previous['status'] in ('CONFIRMADA','CANCELADA') and status!='IDENTIFICADO':
                return jsonify(ok=True,finalizado=True)
            if status=='CANCELADA' and key.startswith('D:'):
                cur.execute("UPDATE public.frequencia_nfc_designacoes SET status='CANCELADA' WHERE id=%s AND clinica_id=%s AND status='PENDENTE'",(int(key[2:]),cid))
            cur.execute('''INSERT INTO public.frequencia_nfc_live
                (clinica_id,chave,paciente_id,status,imagem_png,versao,atualizada_em)
                VALUES (%s,%s,%s,%s,%s,1,NOW())
                ON CONFLICT (clinica_id,chave) DO UPDATE SET
                status=EXCLUDED.status,
                imagem_png=CASE WHEN EXCLUDED.status='ESCREVENDO' THEN EXCLUDED.imagem_png ELSE NULL END,
                versao=frequencia_nfc_live.versao+1,atualizada_em=NOW()''',
                (cid,key,found['paciente_id'],status,image))
        conn.commit()
        return jsonify(ok=True)
    except Exception: conn.rollback(); raise
    finally: conn.close()

@mobile_nfc_bp.get('/controle-frequencia-nfc/api/evento-nfc')
def controle_evento_nfc():
    a=auth()
    if not a: return deny()
    conn=connect()
    try:
        with conn.cursor() as cur:
            live_schema(cur)
            cur.execute('''SELECT l.chave,l.atualizada_em,p.nome,p.prontuario,p.nascimento
                FROM public.frequencia_nfc_live l
                JOIN public.pacientes p ON p.id=l.paciente_id AND p.clinica_id=l.clinica_id
                WHERE l.clinica_id=%s AND l.chave LIKE 'N:%%'
                AND l.status IN ('IDENTIFICADO','ESCREVENDO')
                AND l.atualizada_em>NOW()-INTERVAL '2 minutes'
                ORDER BY l.atualizada_em DESC LIMIT 1''',(a[1],))
            r=one(cur)
        conn.commit()
        if not r: return jsonify(ok=True,evento=None)
        # Um evento pode reaparecer após refresh: a chave+timestamp o identifica.
        ident=int(r['atualizada_em'].timestamp()*1000)
        after=int(request.args.get('depois') or 0)
        return jsonify(ok=True,evento={'id':ident,'chave':r['chave'],
            'paciente':{'nome':r['nome'],'prontuario':r['prontuario'],'nascimento':str(r['nascimento'] or '')}} if ident>after else None)
    except Exception: conn.rollback(); raise
    finally: conn.close()

@mobile_nfc_bp.get('/controle-frequencia-nfc/api/assinatura-ao-vivo')
def controle_live_preview():
    a=auth()
    if not a: return deny()
    did=request.args.get('designacao_id')
    key='D:'+str(int(did)) if did and did.isdigit() else str(request.args.get('nfc_chave') or '')
    if not ((key.startswith('D:') and key[2:].isdigit()) or (key.startswith('N:') and len(key)==66)):
        return jsonify(ok=False,erro='Identificação inválida.'),400
    conn=connect()
    try:
        with conn.cursor() as cur:
            live_schema(cur)
            cur.execute('''SELECT status,versao,imagem_png FROM public.frequencia_nfc_live
                WHERE clinica_id=%s AND chave=%s AND atualizada_em>NOW()-INTERVAL '10 minutes' ''',(a[1],key))
            r=one(cur)
        conn.commit()
        if not r: return jsonify(ok=True,status='AGUARDANDO',imagem=None,versao=0)
        return jsonify(ok=True,status=r['status'],versao=r['versao'],
            imagem=base64.b64encode(bytes(r['imagem_png'])).decode() if r['imagem_png'] else None)
    except Exception: conn.rollback(); raise
    finally: conn.close()


@mobile_nfc_bp.post('/controle-frequencia-nfc/api/validar-assinatura')
def controle_validar_assinatura():
    '''A recepção, autenticada no SGD, valida a imagem temporária e grava a frequência.'''
    a=auth()
    if not a: return deny()
    if not csrf_ok(): return jsonify(ok=False,erro='Token de proteção inválido.'),403
    from .frequencia_nfc import assinatura_png
    body=request.get_json(silent=True) or {}
    key=live_key(body) if body.get('designacao_id') is not None else str(body.get('nfc_chave') or '')
    if not ((key.startswith('D:') and key[2:].isdigit()) or
            (key.startswith('N:') and len(key)==66 and all(c in '0123456789abcdef' for c in key[2:]))):
        return jsonify(ok=False,erro='Identificação inválida.'),400
    from datetime import date
    try:
        selected_date=date.fromisoformat(str(body.get('data_local') or datetime.now(TZ).date().isoformat()))
    except ValueError:
        return jsonify(ok=False,erro='Selecione uma data válida para a frequência.'),400
    if selected_date > datetime.now(TZ).date():
        return jsonify(ok=False,erro='Não é permitido registrar frequência futura.'),400
    justification=str(body.get('justificativa_retroativa') or '').strip()
    if selected_date < datetime.now(TZ).date() and len(justification)<5:
        return jsonify(ok=False,erro='Informe uma justificativa para o registro retroativo.'),400
    conn=connect()
    try:
        with conn.cursor() as cur:
            schema(cur);live_schema(cur)
            cur.execute('''SELECT paciente_id,status,imagem_png,atualizada_em FROM public.frequencia_nfc_live
                WHERE clinica_id=%s AND chave=%s FOR UPDATE''',(a[1],key))
            live=one(cur)
            if not live or live['status']!='ESCREVENDO' or not live['imagem_png']:
                return jsonify(ok=False,erro='Assinatura ainda não recebida ou indisponível.'),409
            if live['atualizada_em'] < datetime.now(live['atualizada_em'].tzinfo)-timedelta(minutes=5):
                return jsonify(ok=False,erro='Assinatura expirada. Solicite novamente.'),409
            png=assinatura_png({'assinatura_png_base64':base64.b64encode(bytes(live['imagem_png'])).decode('ascii')})
            pid=int(live['paciente_id']);did=None;eid=None;origin='NFC'
            if key.startswith('D:'):
                did=int(key[2:]);origin='RECEPCAO'
                cur.execute('''SELECT d.paciente_id FROM public.frequencia_nfc_designacoes d
                    JOIN public.frequencia_nfc_estacoes e ON e.id=d.estacao_id
                    WHERE d.id=%s AND d.clinica_id=%s AND d.status='PENDENTE'
                    AND d.expira_em>NOW() AND e.ativa AND e.expira_em>NOW() FOR UPDATE OF d''',(did,a[1]))
                d=one(cur)
                if not d or int(d['paciente_id'])!=pid:
                    return jsonify(ok=False,erro='Designação expirada ou inválida.'),409
            else:
                cur.execute('''SELECT id FROM public.mobile_nfc_etiquetas WHERE token_hash=%s
                    AND paciente_id=%s AND clinica_id=%s AND ativada_em IS NOT NULL
                    AND revogada_em IS NULL''',(key[2:],pid,a[1]))
                tag=one(cur)
                if not tag:return jsonify(ok=False,erro='Cartão NFC não está mais ativo.'),409
                eid=tag['id']
            cur.execute('''SELECT COUNT(*) AS total FROM public.frequencia_nfc
                 WHERE clinica_id=%s AND paciente_id=%s AND data_local=%s
                 AND cancelada_em IS NULL AND excluida_em IS NULL''',(a[1],pid,selected_date))
            duplicate=one(cur)['total']
            if duplicate and not body.get('confirmar_duplicidade'):
                return jsonify(ok=False,duplicidade=True,total=int(duplicate),
                    erro='Já existe frequência nessa data. Confirme se deseja registrar outra.'),409
            cur.execute('''INSERT INTO public.frequencia_nfc
                (clinica_id,paciente_id,etiqueta_id,designacao_id,origem,registrado_por,data_local,
                 assinatura_png,assinatura_sha256,assinante_tipo,justificativa_retroativa)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'PACIENTE',%s) RETURNING id''',
                (a[1],pid,eid,did,origin,a[0],selected_date,png,hashlib.sha256(png).hexdigest(),justification or None))
            result=one(cur)
            if did:
                cur.execute("UPDATE public.frequencia_nfc_designacoes SET status='CONFIRMADA',confirmada_em=NOW() WHERE id=%s AND clinica_id=%s",(did,a[1]))
            cur.execute('''UPDATE public.frequencia_nfc_live SET status='CONFIRMADA',imagem_png=NULL,
                versao=versao+1,atualizada_em=NOW() WHERE clinica_id=%s AND chave=%s''',(a[1],key))
        conn.commit()
        return jsonify(ok=True,frequencia_id=result['id'],origem=origin)
    except ValueError as exc:
        conn.rollback();return jsonify(ok=False,erro=str(exc)),400
    except UniqueViolation:
        # uq_frequencia_nfc_dia: já existe frequência ativa do paciente nesta data (inclui corrida entre dois registros).
        conn.rollback();return jsonify(ok=False,erro='Já existe frequência ativa deste paciente nessa data. Cancele a existente para registrar outra.'),409
    except Exception:
        conn.rollback();raise
    finally:conn.close()

@mobile_nfc_bp.get('/controle-frequencia-nfc/mobile/status')
@require_mobile_token
def mobile_live_status():
    body={'designacao_id':request.args.get('designacao_id')} if request.args.get('designacao_id') else {'conteudo_ndef':request.args.get('conteudo_ndef')}
    key=live_key(body)
    if not key:return jsonify(ok=False,erro='Identificação inválida.'),400
    cid=int(g.mobile_nfc['clinica_id']);uid=int(g.mobile_nfc['usuario_id'])
    conn=connect()
    try:
        with conn.cursor() as cur:
            live_schema(cur)
            if key.startswith('D:'):
                cur.execute('''SELECT 1 FROM public.frequencia_nfc_designacoes d
                    JOIN public.frequencia_nfc_estacoes e ON e.id=d.estacao_id
                    WHERE d.id=%s AND d.clinica_id=%s AND e.usuario_id=%s''',(int(key[2:]),cid,uid))
            else:
                cur.execute('''SELECT 1 FROM public.mobile_nfc_etiquetas WHERE token_hash=%s
                    AND clinica_id=%s AND ativada_em IS NOT NULL AND revogada_em IS NULL''',(key[2:],cid))
            if not one(cur):return jsonify(ok=False,erro='Acesso não autorizado.'),403
            cur.execute('SELECT status FROM public.frequencia_nfc_live WHERE clinica_id=%s AND chave=%s',(cid,key))
            r=one(cur)
        conn.commit()
        return jsonify(ok=True,status=r['status'] if r else 'AGUARDANDO')
    except Exception:conn.rollback();raise
    finally:conn.close()

@mobile_nfc_bp.post('/controle-frequencia-nfc/api/cancelar-assinatura')
def controle_cancelar_assinatura():
    a=auth()
    if not a:return deny()
    if not csrf_ok():return jsonify(ok=False,erro='Token de proteção inválido.'),403
    body=request.get_json(silent=True) or {}
    key=live_key(body) if body.get('designacao_id') is not None else str(body.get('nfc_chave') or '')
    if not ((key.startswith('D:') and key[2:].isdigit()) or (key.startswith('N:') and len(key)==66 and all(x in '0123456789abcdef' for x in key[2:]))):
        return jsonify(ok=False,erro='Assinatura inválida.'),400
    conn=connect()
    try:
        with conn.cursor() as cur:
            live_schema(cur)
            cur.execute("UPDATE public.frequencia_nfc_live SET status='CANCELADA',imagem_png=NULL,versao=versao+1,atualizada_em=NOW() WHERE clinica_id=%s AND chave=%s AND status NOT IN ('CONFIRMADA','CANCELADA') RETURNING chave",(a[1],key))
            changed=one(cur)
            if changed and key.startswith('D:'):
                cur.execute("UPDATE public.frequencia_nfc_designacoes SET status='CANCELADA' WHERE id=%s AND clinica_id=%s AND status='PENDENTE'",(int(key[2:]),a[1]))
        conn.commit()
        return jsonify(ok=bool(changed),erro=None if changed else 'Assinatura não está em andamento.')
    except Exception:conn.rollback();raise
    finally:conn.close()

def _is_admin(uid,cid):
    conn=connect()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT role FROM public.usuarios WHERE id=%s',(uid,))
            r=one(cur)
            return bool(r and str(r.get('role') or '').upper() in ('ADMIN','MASTER','SUPERADMIN'))
    finally:conn.close()

@mobile_nfc_bp.post('/controle-frequencia-nfc/api/registros/<int:fid>/cancelar')
def controle_cancelar_registro(fid):
    a=auth()
    if not a:return deny()
    if not csrf_ok():return jsonify(ok=False,erro='Token de proteção inválido.'),403
    reason=str((request.get_json(silent=True) or {}).get('motivo') or '').strip()
    if len(reason)<5:return jsonify(ok=False,erro='Informe o motivo do cancelamento (mínimo 5 caracteres).'),400
    conn=connect()
    try:
        with conn.cursor() as cur:
            schema(cur)
            cur.execute('''UPDATE public.frequencia_nfc SET cancelada_em=NOW(),cancelada_por=%s,cancelamento_motivo=%s
                WHERE id=%s AND clinica_id=%s AND cancelada_em IS NULL AND excluida_em IS NULL RETURNING id''',(a[0],reason,fid,a[1]))
            r=one(cur)
        conn.commit()
        return jsonify(ok=bool(r),erro=None if r else 'Registro não encontrado ou já cancelado.')
    except Exception:conn.rollback();raise
    finally:conn.close()

@mobile_nfc_bp.post('/controle-frequencia-nfc/api/registros/<int:fid>/excluir')
def controle_excluir_registro(fid):
    a=auth()
    if not a:return deny()
    if not csrf_ok():return jsonify(ok=False,erro='Token de proteção inválido.'),403
    if not _is_admin(*a):return jsonify(ok=False,erro='Exclusão restrita a administradores.'),403
    reason=str((request.get_json(silent=True) or {}).get('motivo') or '').strip()
    if len(reason)<5:return jsonify(ok=False,erro='Informe o motivo da exclusão.'),400
    conn=connect()
    try:
        with conn.cursor() as cur:
            schema(cur)
            cur.execute('''UPDATE public.frequencia_nfc SET excluida_em=NOW(),excluida_por=%s,exclusao_motivo=%s
                WHERE id=%s AND clinica_id=%s AND excluida_em IS NULL RETURNING id''',(a[0],reason,fid,a[1]))
            r=one(cur)
        conn.commit()
        return jsonify(ok=bool(r),erro=None if r else 'Registro indisponível.')
    except Exception:conn.rollback();raise
    finally:conn.close()
