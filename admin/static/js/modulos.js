// admin/static/js/modulos.js
(() => {
  // ===== Helpers =====
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const debounce = (fn, ms = 200) => {
    let t;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...args), ms);
    };
  };

  // ===== Elements =====
  const grid = $('#modsGrid');
  if (!grid) return; // página errada

  const filtro = $('#filtro');
  const marcarTodos = $('#marcarTodos');
  const desmarcarTodos = $('#desmarcarTodos');
  const presetBasico = $('#presetBasico');
  const presetCompleto = $('#presetCompleto');
  const masterSwitch = $('#masterSwitch');
  const contadorSel = $('#contadorSel');

  const exportAll = $('#export_all');

  // ===== Core =====
  const getChecks = () => $$('input[type="checkbox"][name="modulos"]', grid);

  function updateCounter() {
    const all = getChecks();
    const total = all.filter(c => c.checked).length;

    if (contadorSel) {
      contadorSel.textContent = `${total} selecionado${total === 1 ? '' : 's'}`;
    }
    if (masterSwitch) {
      masterSwitch.checked = total === all.length && total > 0;
      masterSwitch.indeterminate = total > 0 && total < all.length;
    }
  }

  function setAll(checked) {
    getChecks().forEach(c => { c.checked = checked; });
    updateCounter();
  }

  // ===== Filtro com debounce =====
  if (filtro) {
    filtro.addEventListener('input', debounce(e => {
      const q = (e.target.value || '').trim().toLowerCase();
      Array.from(grid.children).forEach(card => {
        const hay = card.getAttribute('data-search') || '';
        card.style.display = hay.includes(q) ? '' : 'none';
      });
    }, 120));
  }

  // ===== Marcar / Desmarcar todos =====
  if (marcarTodos) marcarTodos.addEventListener('click', () => setAll(true));
  if (desmarcarTodos) desmarcarTodos.addEventListener('click', () => setAll(false));

  // ===== Presets =====
  if (presetBasico) {
    presetBasico.addEventListener('click', () => {
      const keys = new Set(['cadastro', 'atendimentos', 'pacientes']);
      getChecks().forEach(c => { c.checked = keys.has(c.value); });

      // Export off no básico
      if (exportAll) exportAll.checked = false;
      $$('.export-child', grid).forEach(el => { el.checked = false; });

      updateCounter();
    });
  }

  if (presetCompleto) {
    presetCompleto.addEventListener('click', () => {
      setAll(true);
    });
  }

  // ===== Master switch (liga/desliga todos) =====
  if (masterSwitch) {
    masterSwitch.addEventListener('change', (e) => {
      setAll(e.target.checked);
    });
  }

  // ===== Export: sincronização pai <-> filhos =====
  if (exportAll) {
    const exportChildren = $$('.export-child', grid);

    const syncChildren = (checked) => {
      exportChildren.forEach(el => { el.checked = checked; });
    };

    const refreshParentFromChildren = () => {
      const allOn = exportChildren.every(c => c.checked);
      const anyOn = exportChildren.some(c => c.checked);
      exportAll.checked = allOn;
      exportAll.indeterminate = anyOn && !allOn;
    };

    // Pai controla filhos
    exportAll.addEventListener('change', (e) => {
      syncChildren(e.target.checked);
      updateCounter();
    });

    // Filhos atualizam pai
    exportChildren.forEach(el => {
      el.addEventListener('change', () => {
        refreshParentFromChildren();
        updateCounter();
      });
    });

    // Estado inicial coerente
    refreshParentFromChildren();
  }

  // ===== Clique em qualquer checkbox deve atualizar contador =====
  grid.addEventListener('change', (e) => {
    if (e.target.matches('input[type="checkbox"][name="modulos"]')) {
      updateCounter();
    }
  });

  // ===== Init =====
  updateCounter();
})();
