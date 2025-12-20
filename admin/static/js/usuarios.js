// admin/static/js/usuarios.js
(() => {
  // ===== Helpers =====
  const $  = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const on = (el, ev, fn) => el && el.addEventListener(ev, fn);
  const onlyDigits = (s) => (s || '').replace(/\D+/g, '');
  const debounce = (fn, ms = 200) => { let t; return (...a)=>{clearTimeout(t); t=setTimeout(()=>fn(...a), ms);} };

  // ===== Elements =====
  const btnNovo     = $('#btnNovoUsuario');
  const btnNiveis   = $('#btnGerenciarNiveis');
  const dialog      = $('#modalUsuario');         // <dialog> CRIAR/EDITAR
  const formUsuario = $('#formUsuario');
  const tituloModal = $('#tituloModalUsuario');
  const drawer      = $('#drawerNiveis');
  const table       = $('#tUsuarios');
  const filtrosForm = $('#filtrosUsuarios');

  // Inputs do modal principal
  const iIdHid        = $('#u_id_hidden');
  const iNome         = $('#u_nome');
  const iEmail        = $('#u_email');
  const iCPF          = $('#u_cpf');
  const iCNS          = $('#u_cns');
  const iNasc         = $('#u_nascimento');
  const iSexo         = $('#u_sexo');
  const iConselho     = $('#u_conselho');
  const iRegConselho  = $('#u_registro_conselho');
  const iUFConselho   = $('#u_uf_conselho');
  const iCBO          = $('#u_cbo');
  const iTel          = $('#u_telefone');
  const iRole         = $('#u_role');
  const iStatus       = $('#u_status');
  const iCEP          = $('#u_cep');
  const iLogradouro   = $('#u_logradouro');
  const iNumero       = $('#u_numero');
  const iCompl        = $('#u_complemento');
  const iBairro       = $('#u_bairro');
  const iMunicipio    = $('#u_municipio');
  const iUF           = $('#u_uf');

  // Grupo de senhas (só em "Novo")
  const gSenhas   = $('#u_senhas_group');
  const iSenha    = $('#u_senha');
  const iSenha2   = $('#u_senha2');

  // Modal de senha (opcional; só usa se existir no HTML)
  const dialogSenha = $('#modalSenha');
  const formSenha   = $('#formSenha');
  const iIdSenha    = $('#u_id_senha');
  const sSenha      = $('#s_senha');
  const sSenha2     = $('#s_senha2');

  // Drawer níveis
  const formNivel   = $('#formNivel');
  const listaNiveis = $('#listaNiveis');

  // Permissões (pills)
  const permGrid   = $('#permGrid');
  const permHidden = $('#permHidden');

  const ALL_PERMS = [
    'cadastro','pacientes','atendimentos','agenda',
    'export_bpai','export_apac','export_ciha',
    'financeiro','rh'
  ];
  const ROLE_DEFAULTS = {
    'RECEPCAO'    : new Set(['cadastro','agenda','atendimentos']),
    'PROFISSIONAL': new Set(['pacientes','agenda','atendimentos']),
    'ADMIN'       : new Set(ALL_PERMS),
  };

  // ===== Base /admin estável para rotas =====
  function baseAdmin() {
    const a = document.createElement('a');
    a.href = $('#tUsuarios')?.baseURI || window.location.href;
    const m = a.pathname.match(/^(.*)\/usuarios/);
    return (m && m[1]) || '/admin';
  }

  // ===== Permissões: render/collect =====
  function setPerms(selectionSet) {
    if (!permGrid) return;
    $$('.perm-pill', permGrid).forEach(btn => {
      const key = btn.getAttribute('data-perm');
      const on = selectionSet.has(key);
      btn.classList.toggle('on', on);
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    syncHiddenPerms();
  }
  function getSelectedPerms() {
    return $$('.perm-pill.on', permGrid).map(b => b.getAttribute('data-perm'));
  }
  function syncHiddenPerms() {
    if (!permHidden) return;
    permHidden.innerHTML = '';
    $$('.perm-pill[aria-pressed="true"]', permGrid).forEach(p => {
      const key = p.dataset.perm;
      const inp = document.createElement('input');
      inp.type  = 'hidden';
      inp.name  = 'perm_' + key;   // compatível com backend atual
      inp.value = '1';
      permHidden.appendChild(inp);
    });
  }
  function applyRoleDefaults() {
    const role = iRole?.value || '';
    const def  = ROLE_DEFAULTS[role] || new Set();
    setPerms(def);
  }

  // ===== Modal principal: abrir/fechar (robusto) =====
  function openDialog(el) {
    if (!el) return;
    try {
      el.showModal(); // nativo
    } catch {
      // fallback agressivo
      el.setAttribute('open','');
      el.classList.add('open');
      el.style.display = 'grid';
      el.style.placeItems = 'center';
    }
  }
  function closeDialog(el) {
    if (!el) return;
    try { el.close(); }
    catch {
      el.removeAttribute('open');
      el.classList.remove('open');
      el.style.display = '';
      el.style.placeItems = '';
    }
  }

  function clearForm() {
  // limpa todos os inputs do modal
  const inputs = [
    iIdHid,iNome,iEmail,iCPF,iCNS,iNasc,iSexo,iConselho,iRegConselho,iUFConselho,
    iCBO,iTel,iRole,iStatus,iCEP,iLogradouro,iNumero,iCompl,iBairro,iMunicipio,iUF
  ];
  inputs.forEach(inp => { if (inp) inp.value = ''; });

  // status padrão ativo
  if (iStatus) iStatus.value = '1';

  // limpa pills de permissões
  if (permGrid) {
    $$('.perm-pill', permGrid).forEach(btn => {
      btn.classList.remove('on', 'active');
      btn.setAttribute('aria-pressed','false');
    });
  }
  if (permHidden) permHidden.innerHTML = '';

  // limpa senhas
  if (iSenha)  iSenha.value = '';
  if (iSenha2) iSenha2.value = '';
}


  // ===== Novo usuário =====
  function openCreate() {
    clearForm();
    if (tituloModal) tituloModal.textContent = 'Novo usuário';
    showPasswords(true);
    formUsuario?.setAttribute('action', formUsuario.dataset.actionCreate || formUsuario.action || `${baseAdmin()}/usuarios/novo`);
    applyRoleDefaults();
    openDialog(dialog);
  }

  // ===== Editar (com fallback para a linha da tabela) =====
  async function openEdit(uid) {
    clearForm();
    if (tituloModal) tituloModal.textContent = 'Editar usuário';
    showPasswords(false);

    // preenche com a linha da tabela (garantido)
    const fromRow = () => {
      const tr = table?.querySelector(`tr[data-id="${uid}"]`);
      if (!tr) return false;
      const txt = (i) => (tr.children[i]?.textContent || '').trim();
      if (iIdHid) iIdHid.value = uid;
      if (iNome)  iNome.value  = txt(0);
      if (iCPF)   iCPF.value   = txt(1);
      if (iEmail) iEmail.value = txt(2);
      const nivelTxt = (txt(3) || '').toUpperCase().replace(/\s+/g, '_');
      if (iRole)  iRole.value  = nivelTxt;
      const isActive = (tr.children[4]?.textContent || '').includes('Ativo');
      if (iStatus) iStatus.value = isActive ? '1' : '0';
      applyRoleDefaults();
      return true;
    };
    fromRow(); // já garante o preenchimento básico

    // se existir endpoint JSON, tenta refinar (campos extras)
    try {
      const res = await fetch(`${baseAdmin()}/usuarios/${uid}.json`, { credentials: 'same-origin' });
      if (!res.ok) throw new Error();
      const u = await res.json();

      if (iIdHid)       iIdHid.value       = u.id || uid;
      if (iNome)        iNome.value        = u.nome || '';
      if (iEmail)       iEmail.value       = u.email || '';
      if (iCPF)         iCPF.value         = (u.cpf || '');
      if (iCNS)         iCNS.value         = (u.cns || '').slice(0, 15);
      if (iNasc)        iNasc.value        = u.nascimento || '';
      if (iSexo)        iSexo.value        = u.sexo || '';
      if (iConselho)    iConselho.value    = u.conselho || '';
      if (iRegConselho) iRegConselho.value = u.registro_conselho || '';
      if (iUFConselho)  iUFConselho.value  = u.uf_conselho || '';
      if (iCBO)         iCBO.value         = u.cbo || '';
      if (iTel)         iTel.value         = (u.telefone || '');
      if (iCEP)         iCEP.value         = u.cep || '';
      if (iLogradouro)  iLogradouro.value  = u.logradouro || '';
      if (iNumero)      iNumero.value      = u.numero || '';
      if (iCompl)       iCompl.value       = u.complemento || '';
      if (iBairro)      iBairro.value      = u.bairro || '';
      if (iMunicipio)   iMunicipio.value   = u.municipio || '';
      if (iUF)          iUF.value          = u.uf || '';
      if (iRole)        iRole.value        = u.role || (iRole.value || '');
      if (iStatus)      iStatus.value      = String(u.is_active ?? Number(iStatus.value || 1));

      // permissões vindas do JSON (se houver)
      try {
        const arr = JSON.parse(u.permissoes_json || '[]');
        if (Array.isArray(arr) && arr.length) setPerms(new Set(arr));
      } catch {/* ignore */}
    } catch {/* se falhar o JSON, mantém dados da linha */}

    // action de editar e abre
    formUsuario?.setAttribute('action', `${baseAdmin()}/usuarios/${uid}/editar`);
    openDialog(dialog);
  }

  // ===== Mostrar / ocultar grupo de senhas =====
  function showPasswords(show) {
    if (!gSenhas) return;
    gSenhas.style.display = show ? '' : 'none';
    if (iSenha)  iSenha.toggleAttribute('required', show);
    if (iSenha2) iSenha2.toggleAttribute('required', show);
    if (!show) { if (iSenha) iSenha.value=''; if (iSenha2) iSenha2.value=''; }
  }

  // ===== Fechamentos =====
  function closeModalMain(){ closeDialog(dialog); }
  function openDrawer(){ drawer?.classList.add('open'); }
  function closeDrawer(){ drawer?.classList.remove('open'); }

  // ===== Bind de botões =====
  $$('.modal [data-modal-close]').forEach(btn => on(btn, 'click', () => closeDialog(btn.closest('dialog') || dialog)));
  on(btnNiveis, 'click', openDrawer);
  $$('.drawer [data-drawer-close]').forEach(btn => on(btn, 'click', closeDrawer));
  on(btnNovo, 'click', openCreate);

  // ===== Máscaras =====
  function maskCPF(v) {
    v = onlyDigits(v).slice(0, 11);
    if (v.length > 9)  return v.replace(/(\d{3})(\d{3})(\d{3})(\d{0,2})/, '$1.$2.$3-$4');
    if (v.length > 6)  return v.replace(/(\d{3})(\d{3})(\d{0,3})/, '$1.$2.$3');
    if (v.length > 3)  return v.replace(/(\d{3})(\d{0,3})/, '$1.$2');
    return v;
  }
  function maskTel(v) {
    v = onlyDigits(v).slice(0,11);
    if (v.length > 10) return v.replace(/(\d{2})(\d{5})(\d{0,4})/, '($1) $2-$3');
    if (v.length > 6)  return v.replace(/(\d{2})(\d{4})(\d{0,4})/, '($1) $2-$3');
    if (v.length > 2)  return v.replace(/(\d{2})(\d{0,5})/, '($1) $2');
    return v;
  }
  function maskCEP(v) {
    v = onlyDigits(v).slice(0,8);
    if (v.length > 5) return v.replace(/(\d{5})(\d{0,3})/, '$1-$2');
    return v;
  }
  on(iCPF, 'input', e => e.target.value = maskCPF(e.target.value));
  on(iTel, 'input', e => e.target.value = maskTel(e.target.value));
  on(iCEP, 'input', e => e.target.value = maskCEP(e.target.value));
  on(iCNS, 'input', e => e.target.value = onlyDigits(e.target.value).slice(0,15));

  // ===== Validação e normalização =====
  function validate() {
    const errors = [];
    if (!iNome?.value.trim()) errors.push('Informe o Nome.');
    const cpfDigits = onlyDigits(iCPF?.value);
    if (!cpfDigits || cpfDigits.length !== 11) errors.push('CPF inválido.');
    if (iEmail?.value && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(iEmail.value)) errors.push('E-mail inválido.');
    if (!iRole?.value) errors.push('Selecione um nível.');
    if (gSenhas?.style.display !== 'none') {
      if (!iSenha?.value || iSenha.value.length < 6) errors.push('Senha mínima de 6 caracteres.');
      if (iSenha?.value !== iSenha2?.value) errors.push('A confirmação da senha não confere.');
    }
    if (errors.length) { alert('Corrija os campos:\n• ' + errors.join('\n• ')); return false; }
    return true;
  }
  function normalizeBeforeSubmit() {
    if (iCPF) iCPF.value = onlyDigits(iCPF.value);
    if (iCEP) iCEP.value = onlyDigits(iCEP.value);
    if (iTel) iTel.value = onlyDigits(iTel.value);
    if (iCNS) iCNS.value = onlyDigits(iCNS.value);
    syncHiddenPerms();
  }

  on(formUsuario, 'submit', (e) => {
    if (!validate()) { e.preventDefault(); return; }
    normalizeBeforeSubmit();
  });

  // ===== Ações na tabela (Editar / Mudar senha) =====
  on(table, 'click', (e) => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const tr = btn.closest('tr');
    const id = tr?.getAttribute('data-id');
    const action = btn.getAttribute('data-action');

    if (action === 'edit') {
      if (id) openEdit(id);
      return;
    }

    if (action === 'password' && dialogSenha && formSenha) {
      if (!id) return;
      if (iIdSenha) iIdSenha.value = id;
      formSenha.setAttribute('action', `${baseAdmin()}/usuarios/${id}/senha`);
      if (sSenha) sSenha.value = '';
      if (sSenha2) sSenha2.value = '';
      openDialog(dialogSenha);
      return;
    }
  });

  // ===== Modal de senha (se existir) =====
  function validateSenha() {
    const errs = [];
    if (!sSenha?.value || sSenha.value.length < 6) errs.push('Senha mínima de 6 caracteres.');
    if (sSenha?.value !== sSenha2?.value) errs.push('A confirmação da senha não confere.');
    if (errs.length) { alert('Corrija os campos:\n• ' + errs.join('\n• ')); return false; }
    return true;
  }
  on(formSenha, 'submit', (e) => { if (!validateSenha()) { e.preventDefault(); } });

  // ===== Toggle olho senha (ambos modais) =====
  $$('.eye-btn').forEach(btn => {
    const sel = btn.getAttribute('data-toggle-pass');
    const input = $(sel);
    on(btn, 'click', () => { if (input) input.type = input.type === 'password' ? 'text' : 'password'; });
  });

  // ===== Filtros client-side =====
  on(filtrosForm, 'submit', (e) => { e.preventDefault(); applyFilters(); });
  on($('#f_busca'), 'input', debounce(applyFilters, 150));
  on($('#f_nivel'), 'change', applyFilters);
  on($('#f_status'), 'change', applyFilters);

  function applyFilters() {
    const q = ($('#f_busca')?.value || '').trim().toLowerCase();
    const nivel = $('#f_nivel')?.value || '';
    const status = $('#f_status')?.value || '';

    $$('tbody tr', table).forEach(tr => {
      const nome  = tr.children[0]?.textContent.toLowerCase() || '';
      const cpf   = tr.children[1]?.textContent.toLowerCase() || '';
      const email = tr.children[2]?.textContent.toLowerCase() || '';
      const nivelTxt = tr.children[3]?.textContent || '';
      const ativo = tr.children[4]?.textContent.includes('Ativo') ? 'ativo' : 'inativo';

      const matchQ      = !q || nome.includes(q) || cpf.includes(q) || email.includes(q);
      const matchNivel  = !nivel || nivelTxt.toUpperCase().includes(nivel.toUpperCase());
      const matchStatus = !status || status === ativo;

      tr.style.display = (matchQ && matchNivel && matchStatus) ? '' : 'none';
    });
  }

  // ===== Drawer de níveis (preview visual) =====
  on(formNivel, 'submit', (e) => {
    // deixa o POST seguir para o backend (preview)
  });
  on(listaNiveis, 'click', (e) => {
    const btn = e.target.closest('[data-edit-nivel],[data-delete-nivel]');
    if (!btn) return;
    const li = btn.closest('li');
    if (btn.hasAttribute('data-delete-nivel')) {
      e.preventDefault();
      if (confirm('Excluir este nível? (preview visual)')) li.remove();
      return;
    }
    if (btn.hasAttribute('data-edit-nivel')) {
      e.preventDefault();
      const nomeTxt = li.querySelector('strong')?.textContent.trim() || '';
      const slugTxt = li.getAttribute('data-slug') || '';
      $('#lvl_nome').value = nomeTxt;
      $('#lvl_slug').value = slugTxt;
      alert('Edite os campos e envie para salvar (preview).');
    }
  });

  // ===== Keyboard sugar =====
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      if (dialog?.open)            closeModalMain();
      else if (dialogSenha?.open)  closeDialog(dialogSenha);
      else if (drawer?.classList.contains('open')) closeDrawer();
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'n') {
      e.preventDefault(); openCreate();
    }
  });

  // ===== Init =====
  if (formUsuario && !formUsuario.dataset.actionCreate)
    formUsuario.dataset.actionCreate = formUsuario.getAttribute('action') || `${baseAdmin()}/usuarios/novo`;

  applyFilters();
})();
