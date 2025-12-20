// ===========================================================
// RH — Front interactions (preview)
// Path: sgd/rh/static/js/rh.js
// ===========================================================
(() => {
  // ===== Helpers =====
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const on = (el, ev, fn) => el && el.addEventListener(ev, fn);
  const onlyDigits = (s) => (s || '').replace(/\D+/g, '');
  const debounce = (fn, ms = 200) => { let t; return (...a)=>{ clearTimeout(t); t=setTimeout(()=>fn(...a), ms); }; };
  const escapeHtml = (s) => String(s).replace(/[&<>"']/g,(m)=>({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[m]));
  const download = (filename, text, mime="text/csv;charset=utf-8") => {
    const blob = new Blob([text], {type:mime});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename; a.style.display='none';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(()=>URL.revokeObjectURL(a.href), 1000);
  };

  // Masks
  function maskCPF(v) {
    v = onlyDigits(v).slice(0, 11);
    if (v.length > 9) return v.replace(/(\d{3})(\d{3})(\d{3})(\d{0,2})/,'$1.$2.$3-$4');
    if (v.length > 6) return v.replace(/(\d{3})(\d{3})(\d{0,3})/,'$1.$2.$3');
    if (v.length > 3) return v.replace(/(\d{3})(\d{0,3})/,'$1.$2');
    return v;
  }
  function maskTel(v){
    v = onlyDigits(v).slice(0,11);
    if (v.length > 10) return v.replace(/(\d{2})(\d{5})(\d{0,4})/, '($1) $2-$3');
    if (v.length > 6) return v.replace(/(\d{2})(\d{4})(\d{0,4})/, '($1) $2-$3');
    if (v.length > 2) return v.replace(/(\d{2})(\d{0,5})/, '($1) $2');
    return v;
  }

  // ===== Elements =====
  const btnNovo = $('#btnNovoColab');
  const btnRelatorios = $('#btnRelatorios');
  const btnEscalas = $('#btnEscalas');
  const btnFerias = $('#btnFerias');

  const tableColab = $('#tColab');
  const tbodyColab = $('#tColab tbody');
  const emptyColab = $('#emptyColab');

  const qColab = $('#qColab');
  const uColab = $('#uColab');
  const vincColab = $('#vincColab');
  const statusColab = $('#statusColab');
  const fColab = $('#fColab');
  const btnLimparFiltros = $('#btnLimparFiltros');
  const btnExportColab = $('#btnExportColab');

  // Tabs
  const tabsWrap = $('#tabsVenc');
  const panels = $$('.tab-panel');

  // Outras tabelas (mock – visual)
  const tASO = $('#tASO tbody'), emptyASO = $('#emptyASO');
  const tTreino = $('#tTreino tbody'), emptyTreino = $('#emptyTreino');
  const tEPI = $('#tEPI tbody'), emptyEPI = $('#emptyEPI');
  const tEscalas = $('#tEscalas tbody'), emptyEscalas = $('#emptyEscalas');
  const tFerias = $('#tFerias tbody'), emptyFerias = $('#emptyFerias');

  // Modal Colaborador
  const modal = $('#modalColab');
  const formColab = $('#formColab');
  const tituloModal = $('#tituloModalColab');

  // Campos do modal (mínimos)
  const iNome = formColab?.querySelector('input[name="nome"]');
  const iEmail = formColab?.querySelector('input[name="email"]');
  const iCPF = formColab?.querySelector('input[name="cpf"]');
  const iTelefone = formColab?.querySelector('input[name="telefone"]');
  const iVinculo = formColab?.querySelector('select[name="vinculo"]');
  const iUnidade = formColab?.querySelector('select[name="unidade"]');
  const iCargo = formColab?.querySelector('input[name="cargo"]');
  const iCBO = formColab?.querySelector('input[name="cbo"]');
  const iAdmissao = formColab?.querySelector('input[name="dt_admissao"]');
  const iStatus = formColab?.querySelector('select[name="status"]');

  // ===== Data (mock) =====
  const UNIT_MAP = (() => {
    const map = {};
    uColab?.querySelectorAll('option').forEach(opt=>{
      const v = (opt.value||'').trim();
      if (v) map[v] = opt.textContent.trim();
    });
    return map;
  })();

  let COLAB = [
    { id: 1, nome:'Ana Souza', cpf:'123.456.789-00', vinculo:'CLT', cargo:'Enfermeira', cbo:'223505', unidade:'1', status:'ATIVO' },
    { id: 2, nome:'João Lima', cpf:'987.654.321-00', vinculo:'PJ', cargo:'Fisioterapeuta', cbo:'223605', unidade:'2', status:'ATIVO' },
    { id: 3, nome:'Maria Santos', cpf:'111.222.333-44', vinculo:'CLT', cargo:'Recepcionista', cbo:'422105', unidade:'1', status:'ATIVO' },
    { id: 4, nome:'Carlos Pereira', cpf:'222.333.444-55', vinculo:'RESIDENTE', cargo:'Médico Residente', cbo:'225125', unidade:'3', status:'ATIVO' },
    { id: 5, nome:'Paula Nogueira', cpf:'333.444.555-66', vinculo:'ESTAGIARIO', cargo:'Téc. Enfermagem', cbo:'322205', unidade:'2', status:'INATIVO' },
    { id: 6, nome:'Rafael Costa', cpf:'444.555.666-77', vinculo:'CLT', cargo:'Psicólogo', cbo:'251510', unidade:'1', status:'ATIVO' },
  ];
  let EDIT_ID = null; // nulo = novo

  const ASO = [
    { colab:'Ana Souza', tipo:'Periódico', data:'2025-07-05', validade:'2026-07-05', status:'OK' },
    { colab:'João Lima', tipo:'Periódico', data:'2024-09-01', validade:'2025-09-01', status:'ATENÇÃO' },
    { colab:'Paula Nogueira', tipo:'Admissional', data:'2023-05-20', validade:'2024-05-20', status:'VENCIDO' },
  ];
  const TREINO = [
    { colab:'Carlos Pereira', treino:'NR-32', concl:'2025-01-10', ate:'2027-01-10', status:'OK' },
    { colab:'Maria Santos', treino:'Atendimento Humanizado', concl:'2024-10-15', ate:'2026-10-15', status:'OK' },
    { colab:'Rafael Costa', treino:'BLS', concl:'2023-11-02', ate:'2025-11-02', status:'ATENÇÃO' },
  ];
  const EPI = [
    { colab:'Ana Souza', epi:'Luvas Nitrílicas', ca:'12345', entregue:'2025-03-01', validade:'2026-03-01' },
    { colab:'João Lima', epi:'Máscara PFF2', ca:'67890', entregue:'2025-08-10', validade:'2025-12-10' },
  ];
  const ESCALAS = [
    { colab:'Ana Souza', unidade:'1', data:'2025-08-25', inicio:'08:00', fim:'14:00' },
    { colab:'João Lima', unidade:'2', data:'2025-08-26', inicio:'13:00', fim:'19:00' },
  ];
  const FERIAS = [
    { colab:'Maria Santos', tipo:'Férias', inicio:'2025-09-05', fim:'2025-10-04', dias:30 },
    { colab:'Rafael Costa', tipo:'Licença', inicio:'2025-09-12', fim:'2025-09-26', dias:14 },
  ];

  // ===== Render =====
  function unidadeNome(id){ return UNIT_MAP[id] || '—'; }
  function badgeStatus(s){
    if (s==='ATIVO') return '<span class="badge ok">Ativo</span>';
    if (s==='INATIVO') return '<span class="badge err">Inativo</span>';
    return '<span class="badge">'+escapeHtml(s||'—')+'</span>';
  }
  function statusCor(s){
    const k = String(s||'').toUpperCase();
    if (k==='OK') return '<span class="badge ok">OK</span>';
    if (k==='ATENÇÃO' || k==='ATENCAO') return '<span class="badge warn">Atenção</span>';
    if (k==='VENCIDO') return '<span class="badge err">Vencido</span>';
    return '<span class="badge">'+escapeHtml(k)+'</span>';
  }

  function renderColabTable(list){
    tbodyColab.innerHTML = '';
    list.forEach(c=>{
      const tr = document.createElement('tr');
      tr.setAttribute('data-id', c.id);
      tr.setAttribute('data-unidade', c.unidade||'');
      tr.setAttribute('data-vinculo', (c.vinculo||'').toUpperCase());
      tr.setAttribute('data-status', (c.status||'').toUpperCase());
      tr.innerHTML = `
        <td>${escapeHtml(c.nome)}</td>
        <td>${escapeHtml(c.cpf)}</td>
        <td>${escapeHtml(c.vinculo)}</td>
        <td>${escapeHtml(c.cargo||'—')}${c.cbo?` / ${escapeHtml(c.cbo)}`:''}</td>
        <td>${escapeHtml(unidadeNome(c.unidade))}</td>
        <td>${badgeStatus(c.status)}</td>
        <td class="row-actions">
          <button class="btn xs" data-action="view">Ver</button>
          <button class="btn xs" data-action="edit">Editar</button>
          <button class="btn xs danger" data-action="toggle">${c.status==='ATIVO'?'Inativar':'Ativar'}</button>
        </td>
      `;
      tbodyColab.appendChild(tr);
    });
    emptyColab.style.display = list.length ? 'none' : '';
  }

  function renderASO(){
    tASO.innerHTML = '';
    ASO.forEach(r=>{
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${escapeHtml(r.colab)}</td>
        <td>${escapeHtml(r.tipo)}</td>
        <td>${escapeHtml(r.data)}</td>
        <td>${escapeHtml(r.validade)}</td>
        <td>${statusCor(r.status)}</td>
        <td><button class="btn xs">Ver</button></td>
      `;
      tASO.appendChild(tr);
    });
    if (emptyASO) emptyASO.style.display = ASO.length ? 'none' : '';
  }
  function renderTreino(){
    tTreino.innerHTML = '';
    TREINO.forEach(r=>{
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${escapeHtml(r.colab)}</td>
        <td>${escapeHtml(r.treino)}</td>
        <td>${escapeHtml(r.concl)}</td>
        <td>${escapeHtml(r.ate)}</td>
        <td>${statusCor(r.status)}</td>
        <td><button class="btn xs">Ver</button></td>
      `;
      tTreino.appendChild(tr);
    });
    if (emptyTreino) emptyTreino.style.display = TREINO.length ? 'none' : '';
  }
  function renderEPI(){
    tEPI.innerHTML = '';
    EPI.forEach(r=>{
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${escapeHtml(r.colab)}</td>
        <td>${escapeHtml(r.epi)}</td>
        <td>${escapeHtml(r.ca)}</td>
        <td>${escapeHtml(r.entregue)}</td>
        <td>${escapeHtml(r.validade)}</td>
        <td><button class="btn xs">Ver</button></td>
      `;
      tEPI.appendChild(tr);
    });
    if (emptyEPI) emptyEPI.style.display = EPI.length ? 'none' : '';
  }
  function renderEscalas(){
    tEscalas.innerHTML = '';
    ESCALAS.forEach(r=>{
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${escapeHtml(r.colab)}</td>
        <td>${escapeHtml(unidadeNome(r.unidade))}</td>
        <td>${escapeHtml(r.data)}</td>
        <td>${escapeHtml(r.inicio)}</td>
        <td>${escapeHtml(r.fim)}</td>
      `;
      tEscalas.appendChild(tr);
    });
    if (emptyEscalas) emptyEscalas.style.display = ESCALAS.length ? 'none' : '';
  }
  function renderFerias(){
    tFerias.innerHTML = '';
    FERIAS.forEach(r=>{
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${escapeHtml(r.colab)}</td>
        <td>${escapeHtml(r.tipo)}</td>
        <td>${escapeHtml(r.inicio)}</td>
        <td>${escapeHtml(r.fim)}</td>
        <td>${escapeHtml(String(r.dias))}</td>
      `;
      tFerias.appendChild(tr);
    });
    if (emptyFerias) emptyFerias.style.display = FERIAS.length ? 'none' : '';
  }

  // ===== Filters (Colaboradores) =====
  function applyColabFilters() {
    const q = (qColab?.value || '').toLowerCase().trim();
    const uni = (uColab?.value || '').trim();
    const vinc = (vincColab?.value || '').toUpperCase().trim();
    const st = (statusColab?.value || '').toUpperCase().trim();

    const filtered = COLAB.filter(c=>{
      const matchQ = !q || [c.nome, c.cpf, c.cargo, c.cbo].some(v => (v||'').toLowerCase().includes(q));
      const matchU = !uni || (c.unidade === uni);
      const matchV = !vinc || (String(c.vinculo||'').toUpperCase() === vinc);
      const matchS = !st || (String(c.status||'').toUpperCase() === st);
      return matchQ && matchU && matchV && matchS;
    });
    renderColabTable(filtered);
  }

  // ===== Export CSV (Colaboradores) =====
  function exportColabCSV(){
    const rows = [['Nome','CPF','Vínculo','Cargo/CBO','Unidade','Status']];
    $$('#tColab tbody tr').forEach(tr=>{
      if (tr.style.display === 'none') return; // respeita filtro
      const tds = tr.querySelectorAll('td');
      const nome = tds[0]?.textContent.trim() || '';
      const cpf = tds[1]?.textContent.trim() || '';
      const vinc = tds[2]?.textContent.trim() || '';
      const cargoCBO = tds[3]?.textContent.replace(/\s+/g,' ').trim() || '';
      const unidade = tds[4]?.textContent.trim() || '';
      const status = tds[5]?.textContent.trim() || '';
      rows.push([nome, cpf, vinc, cargoCBO, unidade, status]);
    });
    const csv = rows.map(r=>r.map(x=>`"${String(x).replace(/"/g,'""')}"`).join(',')).join('\n');
    download(`colaboradores_${new Date().toISOString().slice(0,10)}.csv`, csv);
  }

  // ===== Modal =====
  function openModal(title='Novo colaborador'){
    if (tituloModal) tituloModal.textContent = title;
    if (modal?.showModal) modal.showModal(); else modal?.classList.add('open');
  }
  function closeModal(){
    if (modal?.close) modal.close(); else modal?.classList.remove('open');
    EDIT_ID = null;
    formColab?.reset();
  }

  // preencher modal para edição
  function fillModal(c){
    iNome.value = c.nome || '';
    iEmail.value = c.email || '';
    iCPF.value = c.cpf || '';
    iTelefone.value = c.telefone || '';
    iVinculo.value = c.vinculo || '';
    iUnidade.value = c.unidade || '';
    iCargo.value = c.cargo || '';
    iCBO.value = c.cbo || '';
    iAdmissao.value = c.dt_admissao || '';
    iStatus.value = c.status || 'ATIVO';
  }

  // ===== Events =====
  on(btnNovo, 'click', ()=>{ EDIT_ID=null; formColab?.reset(); openModal('Novo colaborador'); });
  $$('.modal [data-modal-close]').forEach(b=>on(b,'click', closeModal));

  // atalhos
  document.addEventListener('keydown', (e)=>{
    if (e.key==='Escape' && modal?.open) closeModal();
    if ((e.ctrlKey||e.metaKey) && e.key.toLowerCase()==='n'){
      e.preventDefault(); EDIT_ID=null; formColab?.reset(); openModal('Novo colaborador');
    }
  });

  // máscaras
  on(iCPF, 'input', e=> e.target.value = maskCPF(e.target.value));
  on(iTelefone, 'input', e=> e.target.value = maskTel(e.target.value));

  // submit
  on(formColab, 'submit', (e)=>{
    e.preventDefault();
    const nome = iNome?.value.trim();
    const cpf = iCPF?.value.trim();
    const vinc = iVinculo?.value.trim();
    if (!nome) return alert('Informe o Nome.');
    if (!cpf || onlyDigits(cpf).length !== 11) return alert('CPF inválido.');
    if (!vinc) return alert('Selecione o Vínculo.');

    const novo = {
      id: EDIT_ID ?? (Math.max(0,...COLAB.map(x=>x.id))+1),
      nome,
      cpf,
      vinculo: vinc.toUpperCase(),
      cargo: iCargo?.value.trim() || '',
      cbo: iCBO?.value.trim() || '',
      unidade: iUnidade?.value || '',
      status: iStatus?.value || 'ATIVO',
      email: iEmail?.value || '',
      telefone: iTelefone?.value || '',
      dt_admissao: iAdmissao?.value || ''
    };

    if (EDIT_ID){
      COLAB = COLAB.map(c=> c.id===EDIT_ID ? {...c, ...novo} : c);
    } else {
      COLAB.push(novo);
    }
    closeModal();
    applyColabFilters();
    alert('Colaborador salvo (preview).');
  });

  // ações na tabela
  on(tableColab, 'click', (e)=>{
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const tr = btn.closest('tr'); if(!tr) return;
    const id = Number(tr.getAttribute('data-id'));
    const action = btn.getAttribute('data-action');
    const colab = COLAB.find(c=>c.id===id);
    if (!colab) return;

    if (action==='view'){
      alert(`Colaborador\n\nNome: ${colab.nome}\nCPF: ${colab.cpf}\nVínculo: ${colab.vinculo}\nUnidade: ${unidadeNome(colab.unidade)}`);
      return;
    }
    if (action==='edit'){
      EDIT_ID = id; fillModal(colab); openModal('Editar colaborador'); return;
    }
    if (action==='toggle'){
      const novoStatus = colab.status==='ATIVO' ? 'INATIVO' : 'ATIVO';
      if (confirm(`Confirmar alterar status para ${novoStatus}?`)){
        colab.status = novoStatus;
        applyColabFilters();
      }
      return;
    }
  });

  // filtros
  on(fColab, 'submit', (e)=>{ e.preventDefault(); applyColabFilters(); });
  on(qColab, 'input', debounce(applyColabFilters, 150));
  on(uColab, 'change', applyColabFilters);
  on(vincColab, 'change', applyColabFilters);
  on(statusColab, 'change', applyColabFilters);
  on(btnLimparFiltros, 'click', ()=>{
    qColab.value=''; uColab.value=''; vincColab.value=''; statusColab.value='';
    applyColabFilters();
  });
  on(btnExportColab, 'click', exportColabCSV);

  // tabs
  on(tabsWrap, 'click', (e)=>{
    const btn = e.target.closest('.tab');
    if (!btn) return;
    const tab = btn.getAttribute('data-tab');
    tabsWrap.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active', t===btn));
    panels.forEach(p=> p.classList.toggle('active', p.getAttribute('data-panel')===tab));
  });

  // botões topo
  on(btnRelatorios, 'click', ()=> window.print());
  on(btnEscalas, 'click', ()=> { $('#tEscalas')?.scrollIntoView({behavior:'smooth', block:'start'}); });
  on(btnFerias, 'click', ()=> { $('#tFerias')?.scrollIntoView({behavior:'smooth', block:'start'}); });

  // ===== Init =====
  renderColabTable(COLAB);
  renderASO(); renderTreino(); renderEPI(); renderEscalas(); renderFerias();
  applyColabFilters();
})();
