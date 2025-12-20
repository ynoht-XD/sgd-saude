(function(){
  const qs  = (s, el=document) => el.querySelector(s);
  const qsa = (s, el=document) => Array.from(el.querySelectorAll(s));

  // ===== Autocomplete paciente =====
  const inputNome  = qs('#paciente_nome');
  const sugg       = qs('#sugestoes_paciente');

  function closeSugg(){ sugg.innerHTML=''; sugg.hidden = true; }
  function openSugg(){ sugg.hidden = false; }

  inputNome.addEventListener('input', async function(){
    const termo = this.value.trim();
    closeSugg();
    if (termo.length < 3) return;
    try{
      const url = `${(window.SGD_AUDITIVO?.urlBuscaPacientes||'/api/consulta_pacientes')}?nome=${encodeURIComponent(termo)}`;
      const r   = await fetch(url);
      const arr = await r.json();
      if (!Array.isArray(arr) || arr.length === 0) return;

      arr.slice(0,10).forEach(p => {
        const d = document.createElement('div');
        d.textContent = `${p.nome} ${p.data_nascimento ? '('+p.data_nascimento+')' : ''}`;
        d.addEventListener('click', () => fillFromPaciente(p));
        sugg.appendChild(d);
      });
      openSugg();
    }catch(e){ console.error('Busca pacientes falhou', e); }
  });
  document.addEventListener('click', (e) => { if (!sugg.contains(e.target) && e.target !== inputNome) closeSugg(); });

  function fillFromPaciente(p){
    inputNome.value = p.nome || '';

    // nascimento: aceita dd/mm/aaaa ou iso
    const vis  = qs('#nascimento_visivel');
    const hid  = qs('#nascimento');
    if (p.data_nascimento){
      const parts = p.data_nascimento.split('/');
      let dt = parts.length === 3 ? new Date(`${parts[2]}-${parts[1]}-${parts[0]}`) : new Date(p.data_nascimento);
      if (!isNaN(dt)){
        const d = String(dt.getDate()).padStart(2,'0');
        const m = String(dt.getMonth()+1).padStart(2,'0');
        const y = dt.getFullYear();
        vis.value = `${d}/${m}/${y}`;
        hid.value = `${y}-${m}-${d}`;
      }
    }
    qs('#prontuario').value = p.prontuario || '';
    qs('#cns').value        = p.cns || '';
    qs('#sexo').value       = p.sexo || '';

    closeSugg();
  }

  // ===== PTA e classificação =====
  const PTA_FREQS = [500,1000,2000];
  const ranges = [
    {max:25, label:'Normal'},
    {max:40, label:'Leve'},
    {max:55, label:'Moderado'},
    {max:70, label:'Moderado/Severo'},
    {max:90, label:'Severo'},
    {max:200, label:'Profundo'}
  ];
  function classify(db){
    for (const r of ranges){ if (db <= r.max) return r.label; }
    return '';
  }
  function parseNum(v){ const n = Number(v); return isNaN(n) ? null : n; }

  function calcPTA(side /* 'od' | 'oe' */){
    const vals = PTA_FREQS.map(f => parseNum(qs(`input[name="va_${side}_${f}"]`)?.value));
    const list = vals.filter(v => v !== null);
    if (!list.length){ qs(`#pta_${side}`).value=''; qs(`#class_${side}`).value=''; return; }
    const avg = Math.round(list.reduce((a,b)=>a+b,0)/list.length);
    qs(`#pta_${side}`).value = `${avg} dB HL`;
    qs(`#class_${side}`).value = classify(avg);
  }

  PTA_FREQS.forEach(f => {
    ['od','oe'].forEach(side => {
      const el = qs(`input[name="va_${side}_${f}"]`);
      if (el) el.addEventListener('input', () => calcPTA(side));
    });
  });

  // Copiar OD -> OE
  const btnCopiar = qs('#btnCopiarOD');
  if (btnCopiar){
    btnCopiar.addEventListener('click', () => {
      [250,500,1000,2000,3000,4000,6000,8000].forEach(f => {
        const src = qs(`input[name="va_od_${f}"]`);
        const dst = qs(`input[name="va_oe_${f}"]`);
        if (src && dst) dst.value = src.value;
      });
      [250,500,1000,2000,3000,4000].forEach(f => {
        const src = qs(`input[name="vo_od_${f}"]`);
        const dst = qs(`input[name="vo_oe_${f}"]`);
        if (src && dst) dst.value = src.value;
      });
      calcPTA('oe');
    });
  }

  // Limpar / Imprimir
  qs('#btnLimpar')?.addEventListener('click', () => {
    qs('#formExame').reset();
    ['od','oe'].forEach(s => { qs(`#pta_${s}`).value=''; qs(`#class_${s}`).value=''; });
  });
  qs('#btnImprimir')?.addEventListener('click', () => window.print());
})();
