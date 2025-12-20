// ===========================================================
// Financeiro — Front interactions (preview)
// Path: sgd/financeiro/static/js/financeiro.js
// ===========================================================
(() => {
  // ===== Helpers =====
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const on = (el, ev, fn) => el && el.addEventListener(ev, fn);
  const fmtBRL = (v) => (Number(v)||0).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
  const parseISO = (s) => s ? new Date(s+"T00:00:00") : null;
  const toISO = (d) => d instanceof Date ? d.toISOString().slice(0,10) : '';
  const debounce = (fn, ms=200)=>{ let t; return (...a)=>{ clearTimeout(t); t=setTimeout(()=>fn(...a), ms)} };
  const download = (filename, text, mime="text/csv;charset=utf-8") => {
    const blob = new Blob([text], {type:mime});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename; a.style.display='none';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(()=>URL.revokeObjectURL(a.href), 1000);
  };
  const badge = (status) => {
    const s = String(status||'').toUpperCase();
    if (s==='PAGO') return '<span class="badge ok">Pago</span>';
    if (s==='PROGRAMADO') return '<span class="badge info">Programado</span>';
    if (s==='EM_ATRASO') return '<span class="badge err">Em atraso</span>';
    if (s==='EM_ABERTO') return '<span class="badge warn">Em aberto</span>';
    return `<span class="badge">${s||'—'}</span>`;
  };

  // ===== Elements =====
  const btnNovoReceber = $('#btnNovoReceber');
  const btnNovoPagar = $('#btnNovoPagar');
  const btnConcilia = $('#btnConcilia');
  const btnEmitirNFSe = $('#btnEmitirNFSe');

  // Modais
  const dlgReceber = $('#modalReceber');
  const dlgPagar = $('#modalPagar');
  const dlgNFSe = $('#modalNFSe');
  const formReceber = $('#formReceber');
  const formPagar = $('#formPagar');
  const formNFSe = $('#formNFSe');

  // Fluxo de caixa
  const canvas = $('#chartFluxo');
  const btnExportFluxo = $('#btnExportFluxo');

  // Receber
  const fReceber = $('#fReceber');
  const qReceber = $('#qReceber');
  const stReceber = $('#stReceber');
  const ccReceber = $('#ccReceber');
  const dtDeReceber = $('#dtDeReceber');
  const dtAteReceber = $('#dtAteReceber');
  const btnLimparReceber = $('#btnLimparReceber');
  const btnReceberCSV = $('#btnReceberCSV');
  const tReceber = $('#tReceber tbody');
  const emptyReceber = $('#emptyReceber');

  // Pagar
  const fPagar = $('#fPagar');
  const qPagar = $('#qPagar');
  const stPagar = $('#stPagar');
  const ccPagar = $('#ccPagar');
  const dtDePagar = $('#dtDePagar');
  const dtAtePagar = $('#dtAtePagar');
  const btnLimparPagar = $('#btnLimparPagar');
  const btnPagarCSV = $('#btnPagarCSV');
  const tPagar = $('#tPagar tbody');
  const emptyPagar = $('#emptyPagar');

  // Conciliação
  const fileExtrato = $('#fileExtrato');
  const btnSugerirConc = $('#btnSugerirConc');
  const tExtrato = $('#tExtrato tbody');
  const emptyExtrato = $('#emptyExtrato');

  // ===== Data stores (front-only) =====
  let FLUXO = [];           // [{data, entradas, saidas, saldo}]
  let RECEBER = [];         // items de /api/receber
  let PAGAR = [];           // items de /api/pagar
  let EXTRATO = [];         // importado (csv/ofx)

  // ===== Dialog helpers =====
  function openDialog(dlg){ if (dlg?.showModal) dlg.showModal(); else dlg?.classList.add('open'); }
  function closeDialog(dlg){ if (dlg?.close) dlg.close(); else dlg?.classList.remove('open'); }
  $$('.modal [data-modal-close]').forEach(b=> on(b,'click', ()=> closeDialog(b.closest('dialog'))));
  document.addEventListener('keydown', (e)=>{ if (e.key==='Escape') $$('.modal').forEach(d=> d.open && d.close()); });

  on(btnNovoReceber,'click', ()=>{ formReceber?.reset(); openDialog(dlgReceber); });
  on(btnNovoPagar,'click', ()=>{ formPagar?.reset(); openDialog(dlgPagar); });
  on(btnEmitirNFSe,'click', ()=>{ formNFSe?.reset(); openDialog(dlgNFSe); });
  on(btnConcilia,'click', ()=>{ $('#tExtrato')?.scrollIntoView({behavior:'smooth', block:'start'}); });

  // ===== Fetch mocks =====
  async function loadFluxo(){
    const r = await fetch('/financeiro/api/fluxo-caixa');
    FLUXO = await r.json();
    drawFluxo(FLUXO);
  }
  async function loadReceber(){
    const r = await fetch('/financeiro/api/receber');
    RECEBER = await r.json();
    applyReceberFilters();
  }
  async function loadPagar(){
    const r = await fetch('/financeiro/api/pagar');
    PAGAR = await r.json();
    applyPagarFilters();
  }

  // ===== Canvas chart (saldo) =====
  function drawFluxo(points){
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height;
    ctx.clearRect(0,0,W,H);

    if (!points?.length) return;

    // Margens e escalas
    const m = {l:48, r:18, t:16, b:28};
    const xs = points.map(p=> parseISO(p.data).getTime());
    const ys = points.map(p=> p.saldo);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const padY = (maxY - minY) * 0.1 || 1;
    const y0 = minY - padY, y1 = maxY + padY;

    const xTo = (x)=> m.l + ( (x-minX)/(maxX-minX||1) ) * (W - m.l - m.r);
    const yTo = (y)=> H - m.b - ( (y - y0)/(y1 - y0) )*(H - m.t - m.b);

    // grade horizontal
    ctx.strokeStyle = '#e5e7eb'; ctx.lineWidth = 1;
    ctx.beginPath();
    for (let i=0;i<=4;i++){
      const y = m.t + i*(H - m.t - m.b)/4;
      ctx.moveTo(m.l, y); ctx.lineTo(W - m.r, y);
    }
    ctx.stroke();

    // eixo y labels
    ctx.fillStyle = '#374151'; ctx.font = '12px system-ui, -apple-system, Segoe UI, Roboto';
    ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    for (let i=0;i<=4;i++){
      const val = y1 - i*(y1-y0)/4;
      const y = yTo(val);
      ctx.fillText(fmtBRL(val), m.l - 6, y);
    }

    // linha saldo
    ctx.strokeStyle = '#2563eb'; ctx.lineWidth = 2;
    ctx.beginPath();
    points.forEach((p, idx)=>{
      const x = xTo(parseISO(p.data).getTime());
      const y = yTo(p.saldo);
      if (idx===0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
    });
    ctx.stroke();

    // pontos
    ctx.fillStyle = '#2563eb';
    points.forEach((p)=>{
      const x = xTo(parseISO(p.data).getTime());
      const y = yTo(p.saldo);
      ctx.beginPath(); ctx.arc(x,y,3,0,Math.PI*2); ctx.fill();
    });

    // eixo x (datas)
    ctx.fillStyle = '#374151'; ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    const step = Math.max(1, Math.floor(points.length/6));
    points.forEach((p, i)=>{
      if (i % step !== 0 && i !== points.length-1) return;
      const x = xTo(parseISO(p.data).getTime());
      ctx.fillText(p.data.slice(5).replace('-','/'), x, H - m.b + 6);
    });
  }

  on(btnExportFluxo, 'click', ()=>{
    if (!FLUXO.length) return alert('Sem dados para exportar.');
    const rows = [['Data','Entradas','Saídas','Saldo']].concat(
      FLUXO.map(p=>[p.data, String(p.entradas).replace('.',','), String(p.saidas).replace('.',','), String(p.saldo).replace('.',',')])
    );
    const csv = rows.map(r=>r.join(';')).join('\n');
    download(`fluxo_caixa_${toISO(new Date())}.csv`, csv);
  });

  // ===== Render tables =====
  function renderReceber(list){
    tReceber.innerHTML = '';
    list.forEach(it=>{
      const tr = document.createElement('tr');
      tr.setAttribute('data-id', it.id);
      tr.setAttribute('data-status', it.status);
      tr.innerHTML = `
        <td>${it.emissao || '—'}</td>
        <td>${it.venc || '—'}</td>
        <td>${it.pagador || '—'}</td>
        <td>${it.paciente || '—'}</td>
        <td class="num">${fmtBRL(it.valor)}</td>
        <td>${badge(it.status)}</td>
        <td class="row-actions">
          <button class="btn xs" data-action="view">Ver</button>
          <button class="btn xs" data-action="baixar">Baixa</button>
          <button class="btn xs danger" data-action="cancelar">Cancelar</button>
        </td>
      `;
      tReceber.appendChild(tr);
    });
    emptyReceber.style.display = list.length ? 'none' : '';
  }

  function renderPagar(list){
    tPagar.innerHTML = '';
    list.forEach(it=>{
      const tr = document.createElement('tr');
      tr.setAttribute('data-id', it.id);
      tr.setAttribute('data-status', it.status);
      tr.innerHTML = `
        <td>${it.emissao || '—'}</td>
        <td>${it.venc || '—'}</td>
        <td>${it.fornecedor || '—'}</td>
        <td>${it.descricao || '—'}</td>
        <td class="num">${fmtBRL(it.valor)}</td>
        <td>${badge(it.status)}</td>
        <td class="row-actions">
          <button class="btn xs" data-action="view">Ver</button>
          <button class="btn xs" data-action="pagar">Pagar</button>
          <button class="btn xs danger" data-action="cancelar">Cancelar</button>
        </td>
      `;
      tPagar.appendChild(tr);
    });
    emptyPagar.style.display = list.length ? 'none' : '';
  }

  // ===== Filters =====
  function inDateRange(dISO, deISO, ateISO){
    if (!dISO) return true;
    const d = parseISO(dISO);
    if (deISO && d < parseISO(deISO)) return false;
    if (ateISO && d > parseISO(ateISO)) return false;
    return true;
  }

  function applyReceberFilters(){
    const q = (qReceber?.value||'').toLowerCase().trim();
    const st = (stReceber?.value||'').toUpperCase();
    const cc = (ccReceber?.value||'').trim();
    const de = dtDeReceber?.value || '';
    const ate = dtAteReceber?.value || '';
    const filtered = RECEBER.filter(it=>{
      const texto = `${it.pagador||''} ${it.paciente||''}`.toLowerCase();
      const matchQ = !q || texto.includes(q);
      const matchS = !st || String(it.status||'').toUpperCase()===st;
      const matchCC = !cc || String(it.centro_custo||'')===cc;
      const matchDt = inDateRange(it.venc, de, ate);
      return matchQ && matchS && matchCC && matchDt;
    });
    renderReceber(filtered);
  }

  function applyPagarFilters(){
    const q = (qPagar?.value||'').toLowerCase().trim();
    const st = (stPagar?.value||'').toUpperCase();
    const cc = (ccPagar?.value||'').trim();
    const de = dtDePagar?.value || '';
    const ate = dtAtePagar?.value || '';
    const filtered = PAGAR.filter(it=>{
      const texto = `${it.fornecedor||''} ${it.descricao||''}`.toLowerCase();
      const matchQ = !q || texto.includes(q);
      const matchS = !st || String(it.status||'').toUpperCase()===st;
      const matchCC = !cc || String(it.centro_custo||'')===cc;
      const matchDt = inDateRange(it.venc, de, ate);
      return matchQ && matchS && matchCC && matchDt;
    });
    renderPagar(filtered);
  }

  on(fReceber,'submit', (e)=>{ e.preventDefault(); applyReceberFilters(); });
  on(qReceber,'input', debounce(applyReceberFilters, 150));
  on(stReceber,'change', applyReceberFilters);
  on(ccReceber,'change', applyReceberFilters);
  on(dtDeReceber,'change', applyReceberFilters);
  on(dtAteReceber,'change', applyReceberFilters);
  on(btnLimparReceber,'click', ()=>{ qReceber.value=''; stReceber.value=''; ccReceber.value=''; dtDeReceber.value=''; dtAteReceber.value=''; applyReceberFilters(); });

  on(fPagar,'submit', (e)=>{ e.preventDefault(); applyPagarFilters(); });
  on(qPagar,'input', debounce(applyPagarFilters, 150));
  on(stPagar,'change', applyPagarFilters);
  on(ccPagar,'change', applyPagarFilters);
  on(dtDePagar,'change', applyPagarFilters);
  on(dtAtePagar,'change', applyPagarFilters);
  on(btnLimparPagar,'click', ()=>{ qPagar.value=''; stPagar.value=''; ccPagar.value=''; dtDePagar.value=''; dtAtePagar.value=''; applyPagarFilters(); });

  // ===== Export CSV =====
  function exportTableCSV(tableId, filename){
    const rows = [];
    const tbl = $(tableId);
    const thead = tbl.querySelector('thead');
    const headers = [...thead.querySelectorAll('th')].map(th=> th.textContent.trim());
    rows.push(headers);
    $(`${tableId} tbody`).querySelectorAll('tr').forEach(tr=>{
      if (tr.style.display==='none') return; // respeita filtros, se aplicados via style
      const tds = tr.querySelectorAll('td');
      rows.push([...tds].slice(0, headers.length).map(td => `"${td.textContent.replace(/"/g,'""')}"`));
    });
    const csv = rows.map(r=>Array.isArray(r)? r.join(',') : r).join('\n');
    download(filename, csv);
  }
  on(btnReceberCSV,'click', ()=> exportTableCSV('#tReceber', `receber_${toISO(new Date())}.csv`) );
  on(btnPagarCSV,'click', ()=> exportTableCSV('#tPagar', `pagar_${toISO(new Date())}.csv`) );

  // ===== Row actions (Receber / Pagar) =====
  on($('#tReceber'), 'click', (e)=>{
    const btn = e.target.closest('[data-action]'); if (!btn) return;
    const tr = btn.closest('tr'); const id = Number(tr.getAttribute('data-id'));
    const it = RECEBER.find(x=> x.id===id); if (!it) return;
    const action = btn.getAttribute('data-action');
    if (action==='view'){
      alert(`Recebível #${id}\nPagador: ${it.pagador}\nPaciente: ${it.paciente}\nVenc.: ${it.venc}\nValor: ${fmtBRL(it.valor)}\nStatus: ${it.status}`);
    } else if (action==='baixar'){
      if (confirm('Confirmar baixa como PAGO?')){ it.status='PAGO'; applyReceberFilters(); }
    } else if (action==='cancelar'){
      if (confirm('Cancelar este título?')){ RECEBER = RECEBER.filter(x=>x.id!==id); applyReceberFilters(); }
    }
  });
  on($('#tPagar'), 'click', (e)=>{
    const btn = e.target.closest('[data-action]'); if (!btn) return;
    const tr = btn.closest('tr'); const id = Number(tr.getAttribute('data-id'));
    const it = PAGAR.find(x=> x.id===id); if (!it) return;
    const action = btn.getAttribute('data-action');
    if (action==='view'){
      alert(`Pagável #${id}\nFornecedor: ${it.fornecedor}\nDesc.: ${it.descricao}\nVenc.: ${it.venc}\nValor: ${fmtBRL(it.valor)}\nStatus: ${it.status}`);
    } else if (action==='pagar'){
      if (confirm('Marcar como PAGO?')){ it.status='PAGO'; applyPagarFilters(); }
    } else if (action==='cancelar'){
      if (confirm('Cancelar esta despesa?')){ PAGAR = PAGAR.filter(x=>x.id!==id); applyPagarFilters(); }
    }
  });

  // ===== Submit forms (add rows — preview) =====
  on(formReceber, 'submit', (e)=>{
    e.preventDefault();
    const fd = new FormData(formReceber);
    const novo = {
      id: (Math.max(0,...RECEBER.map(x=>x.id))+1) || 100,
      emissao: toISO(new Date()),
      venc: fd.get('venc') || toISO(new Date()),
      pagador: fd.get('pagador') || '',
      paciente: fd.get('paciente') || '',
      valor: parseFloat(fd.get('valor')||'0'),
      status: fd.get('status') || 'EM_ABERTO',
      centro_custo: fd.get('centro_custo') || ''
    };
    if (!novo.pagador || !novo.valor) return alert('Preencha Pagador e Valor.');
    RECEBER.push(novo);
    closeDialog(dlgReceber);
    applyReceberFilters();
    alert('Recebível salvo (preview).');
  });

  on(formPagar, 'submit', (e)=>{
    e.preventDefault();
    const fd = new FormData(formPagar);
    const novo = {
      id: (Math.max(0,...PAGAR.map(x=>x.id))+1) || 200,
      emissao: toISO(new Date()),
      venc: fd.get('venc') || toISO(new Date()),
      fornecedor: fd.get('fornecedor') || '',
      descricao: fd.get('descricao') || '',
      valor: parseFloat(fd.get('valor')||'0'),
      status: fd.get('status') || 'EM_ABERTO',
      centro_custo: fd.get('centro_custo') || ''
    };
    if (!novo.fornecedor || !novo.valor) return alert('Preencha Fornecedor e Valor.');
    PAGAR.push(novo);
    closeDialog(dlgPagar);
    applyPagarFilters();
    alert('Despesa salva (preview).');
  });

  on(formNFSe, 'submit', (e)=>{
    e.preventDefault();
    const fd = new FormData(formNFSe);
    const tomador = fd.get('tomador')||'';
    const valor = parseFloat(fd.get('valor')||'0');
    if (!tomador || !valor) return alert('Preencha Tomador e Valor.');
    closeDialog(dlgNFSe);
    alert('NFSe emitida (preview). Integração real entra na próxima fase.');
  });

  // ===== Conciliação — importar OFX/CSV e sugerir matches =====
  function renderExtrato(){
    tExtrato.innerHTML = '';
    EXTRATO.forEach((l, idx)=>{
      const tr = document.createElement('tr');
      tr.setAttribute('data-idx', idx);
      tr.innerHTML = `
        <td>${l.data || '—'}</td>
        <td>${l.historico || '—'}</td>
        <td>${l.documento || '—'}</td>
        <td class="num">${fmtBRL(l.valor)}</td>
        <td>${l.match || '—'}</td>
        <td class="row-actions">
          <button class="btn xs" data-action="conciliar">Conciliar</button>
          <button class="btn xs danger" data-action="ignorar">Ignorar</button>
        </td>
      `;
      tExtrato.appendChild(tr);
    });
    emptyExtrato.style.display = EXTRATO.length ? 'none' : '';
  }

  function parseCSV(text){
    const lines = text.split(/\r?\n/).filter(Boolean);
    // espera: data;historico;documento;valor
    const out = [];
    lines.slice(1).forEach(l=>{
      const cols = l.split(/[;,]/).map(c=>c.trim());
      if (cols.length < 4) return;
      const valor = parseFloat((cols[3]||'0').replace('.','').replace(',','.'));
      out.push({ data: cols[0], historico: cols[1], documento: cols[2], valor });
    });
    return out;
  }

  function parseOFX(text){
    // parse simples por tags — <STMTTRN><DTPOSTED>YYYYMMDD ... <TRNAMT>valor <MEMO>hist
    const out = [];
    const blocks = text.split(/<STMTTRN>/i).slice(1);
    blocks.forEach(b=>{
      const dt = (b.match(/<DTPOSTED>(\d{8})/i) || [])[1];
      const amt = (b.match(/<TRNAMT>(-?\d+[\.,]?\d*)/i) || [])[1];
      const memo = (b.match(/<MEMO>([^<]+)/i) || [])[1];
      const fitid = (b.match(/<FITID>([^<]+)/i) || [])[1];
      if (dt && amt){
        const data = `${dt.slice(0,4)}-${dt.slice(4,6)}-${dt.slice(6,8)}`;
        const valor = parseFloat(String(amt).replace(',','.'));
        out.push({ data, historico: memo||'', documento: fitid||'', valor });
      }
    });
    return out;
  }

  on(fileExtrato, 'change', async (e)=>{
    const f = e.target.files?.[0]; if (!f) return;
    const text = await f.text();
    let rows = [];
    if (f.name.toLowerCase().endsWith('.csv')) rows = parseCSV(text);
    else rows = parseOFX(text);
    EXTRATO = rows;
    renderExtrato();
    alert(`Importados ${rows.length} lançamentos (preview).`);
  });

  function sugerirMatches(){
    if (!EXTRATO.length){ alert('Importe um extrato primeiro.'); return; }
    const tolDias = 3;
    const dateDiff = (a,b)=> Math.abs((parseISO(a)-parseISO(b))/(1000*60*60*24));
    EXTRATO.forEach(l=>{
      // tenta Receber (valor positivo) e Pagar (valor negativo)
      let matchTxt = '';
      if (l.valor > 0){
        const m = RECEBER.find(r => r.status!=='PAGO' && Math.abs(r.valor - l.valor) < 0.01 && dateDiff(r.venc, l.data) <= tolDias);
        if (m) matchTxt = `Receber #${m.id}`;
      } else if (l.valor < 0){
        const alvo = Math.abs(l.valor);
        const m = PAGAR.find(p => p.status!=='PAGO' && Math.abs(p.valor - alvo) < 0.01 && dateDiff(p.venc, l.data) <= tolDias);
        if (m) matchTxt = `Pagar #${m.id}`;
      }
      l.match = matchTxt || '—';
    });
    renderExtrato();
    alert('Sugestões de conciliação geradas (preview).');
  }
  on(btnSugerirConc,'click', sugerirMatches);

  on($('#tExtrato'), 'click', (e)=>{
    const btn = e.target.closest('[data-action]'); if(!btn) return;
    const tr = btn.closest('tr'); const idx = Number(tr.getAttribute('data-idx'));
    const it = EXTRATO[idx]; if (!it) return;
    const action = btn.getAttribute('data-action');
    if (action==='conciliar'){
      if (!it.match || it.match==='—') { alert('Sem sugestão. Faça o match manual (futuro).'); return; }
      if (confirm(`Confirmar conciliação com ${it.match}?`)){
        // Marca pago/programado (preview)
        const m = it.match.split(' ');
        const tipo = m[0], id = Number(m[1]?.replace('#',''));
        if (tipo==='Receber'){
          const r = RECEBER.find(x=>x.id===id); if (r) r.status='PAGO';
          applyReceberFilters();
        } else if (tipo==='Pagar'){
          const p = PAGAR.find(x=>x.id===id); if (p) p.status='PAGO';
          applyPagarFilters();
        }
        it.match = 'Conciliado';
        renderExtrato();
      }
    } else if (action==='ignorar'){
      EXTRATO.splice(idx,1); renderExtrato();
    }
  });

  // ===== Init =====
  (async function init(){
    await Promise.all([loadFluxo(), loadReceber(), loadPagar()]);
  })();
})();
