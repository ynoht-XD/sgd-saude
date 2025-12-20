// admin/static/js/admin.js
document.addEventListener('DOMContentLoaded', () => {
  // =========================
  // 1) Auto-fechar mensagens flash
  // =========================
  const flashes = document.querySelectorAll('.flash');
  flashes.forEach(f => {
    // fecha ao clicar
    f.addEventListener('click', () => f.remove());
    // fecha automático após 6s
    setTimeout(() => {
      try {
        f.style.transition = 'opacity .3s ease';
        f.style.opacity = '0';
        setTimeout(() => f.remove(), 350);
      } catch (_) {}
    }, 6000);
  });

  // =========================
  // 2) Máscara e sanitização de CPF no formulário de usuários
  //    - exibe máscara na digitação
  //    - na submissão, envia apenas dígitos
  // =========================
  const cpfInput = document.querySelector('input[name="cpf"]');
  if (cpfInput) {
    const onlyDigits = s => s.replace(/\D/g, '');
    const maskCpf = v => {
      v = onlyDigits(v).slice(0, 11);
      if (v.length <= 3) return v;
      if (v.length <= 6) return `${v.slice(0,3)}.${v.slice(3)}`;
      if (v.length <= 9) return `${v.slice(0,3)}.${v.slice(3,6)}.${v.slice(6)}`;
      return `${v.slice(0,3)}.${v.slice(3,6)}.${v.slice(6,9)}-${v.slice(9,11)}`;
    };

    // aplica máscara enquanto digita
    cpfInput.addEventListener('input', () => {
      const caret = cpfInput.selectionStart;
      cpfInput.value = maskCpf(cpfInput.value);
      // caret básico (não perfeito, mas ok para o caso)
      cpfInput.selectionStart = cpfInput.selectionEnd = caret;
    });

    // sanitiza no submit (envia só dígitos)
    const form = cpfInput.closest('form');
    if (form) {
      form.addEventListener('submit', () => {
        cpfInput.value = onlyDigits(cpfInput.value);
      });
    }
  }

  // =========================
  // 3) UX do formulário (evitar duplo envio / feedback btn)
  // =========================
  document.querySelectorAll('form').forEach(form => {
    form.addEventListener('submit', (e) => {
      const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
      if (submitBtn && !submitBtn.disabled) {
        submitBtn.dataset.originalText = submitBtn.innerText;
        submitBtn.innerText = 'Enviando...';
        submitBtn.disabled = true;
        // reabilita caso a navegação não ocorra (ex.: erro validação server-side)
        setTimeout(() => {
          if (document.visibilityState === 'visible') {
            submitBtn.disabled = false;
            submitBtn.innerText = submitBtn.dataset.originalText || 'Salvar';
          }
        }, 6000);
      }
    });
  });

  // =========================
  // 4) Contadores de seleção (multiselect CBOs e módulos)
  // =========================
  const updateCountBadge = (el) => {
    let badge = el.parentElement.querySelector('.count-badge');
    if (!badge) {
      badge = document.createElement('small');
      badge.className = 'count-badge';
      badge.style.marginLeft = '8px';
      badge.style.color = '#6b7280';
      el.parentElement.appendChild(badge);
    }
    const total = el.options.length;
    const selected = Array.from(el.options).filter(o => o.selected).length;
    badge.textContent = `(${selected}/${total} selecionado${selected === 1 ? '' : 's'})`;
  };

  // multiselects (ex.: CBOs)
  document.querySelectorAll('select[multiple]').forEach(select => {
    updateCountBadge(select);
    select.addEventListener('change', () => updateCountBadge(select));
  });

  // checkboxes de módulos
  const modulosContainer = document.querySelector('form[action$="/modulos"], form:has(input[name="modulos"])') || document.querySelector('form');
  const moduloCheckboxes = document.querySelectorAll('input[type="checkbox"][name="modulos"]');
  if (moduloCheckboxes.length) {
    const counter = document.createElement('small');
    counter.style.display = 'block';
    counter.style.margin = '8px 0 0 2px';
    counter.style.color = '#6b7280';
    const updateModuloCount = () => {
      const total = moduloCheckboxes.length;
      const checked = Array.from(moduloCheckboxes).filter(c => c.checked).length;
      counter.textContent = `Módulos habilitados: ${checked}/${total}`;
    };
    updateModuloCount();
    moduloCheckboxes.forEach(cb => cb.addEventListener('change', updateModuloCount));
    // tenta colocar no card principal (ou logo após o form)
    const card = document.querySelector('.card');
    (card || modulosContainer || document.body).appendChild(counter);
  }

  // =========================
  // 5) Ações com confirmação (ex.: desativar usuário)
  //    Use data-confirm="Mensagem?" no link/botão
  // =========================
  document.body.addEventListener('click', (e) => {
    const target = e.target.closest('[data-confirm]');
    if (target) {
      const msg = target.getAttribute('data-confirm') || 'Confirmar ação?';
      if (!confirm(msg)) {
        e.preventDefault();
        e.stopPropagation();
      }
    }
  });

  // =========================
  // 6) Backup via fetch (progressive enhancement)
  //    Se existir um form com id="backupForm", intercepta pra UX melhor.
  //    Caso contrário, deixa o submit normal.
  // =========================
  const backupForm = document.getElementById('backupForm') || document.querySelector('form[action$="/backup/run"]');
  if (backupForm) {
    backupForm.addEventListener('submit', async (e) => {
      // se quiser manter o comportamento padrão do servidor,
      // comente este bloco e deixe o submit seguir.
      e.preventDefault();
      const btn = backupForm.querySelector('button[type="submit"], input[type="submit"]');
      if (btn) {
        btn.disabled = true;
        btn.dataset.originalText = btn.innerText;
        btn.innerText = 'Iniciando backup...';
      }

      try {
        const resp = await fetch(backupForm.action, { method: 'POST' });
        // tenta atualizar a página para exibir flash do servidor
        if (resp.redirected) {
          window.location.href = resp.url;
          return;
        }
        // se não redirecionou, dá um feedback simples:
        alert('Backup solicitado. Verifique as notificações (flash) na página.');
      } catch (err) {
        console.error(err);
        alert('Falha ao iniciar backup. Tente novamente.');
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerText = btn.dataset.originalText || 'Gerar backup agora';
        }
      }
    });
  }
});
