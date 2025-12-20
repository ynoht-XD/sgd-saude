document.addEventListener('DOMContentLoaded', () => {
  // Auto-fechar flashes
  document.querySelectorAll('.flash').forEach(el => {
    setTimeout(() => {
      el.style.transition = 'opacity .25s ease';
      el.style.opacity = '0';
      setTimeout(() => el.remove(), 280);
    }, 5000);
  });

  // Máscara leve para CPF (envia só dígitos)
  const cpf = document.querySelector('input[name="cpf"]');
  if (cpf) {
    const only = s => s.replace(/\D/g, '').slice(0, 11);
    const mask = v => {
      v = only(v);
      if (v.length <= 3) return v;
      if (v.length <= 6) return `${v.slice(0,3)}.${v.slice(3)}`;
      if (v.length <= 9) return `${v.slice(0,3)}.${v.slice(3,6)}.${v.slice(6)}`;
      return `${v.slice(0,3)}.${v.slice(3,6)}.${v.slice(6,9)}-${v.slice(9,11)}`;
    };
    cpf.addEventListener('input', () => cpf.value = mask(cpf.value));
    cpf.form && cpf.form.addEventListener('submit', () => cpf.value = only(cpf.value));
  }

  // Toggle visibilidade da senha (olhinho)
  document.querySelectorAll('.eye-btn').forEach(btn => {
    const sel = btn.getAttribute('data-target');
    const input = document.querySelector(sel);
    if (!input) return;

    const setMode = (show) => {
      input.type = show ? 'text' : 'password';
      btn.classList.toggle('showing', !!show);
      btn.setAttribute('aria-label', show ? 'Ocultar senha' : 'Mostrar senha');
      btn.setAttribute('title', show ? 'Ocultar senha' : 'Mostrar senha');
    };

    btn.addEventListener('click', () => {
      const showing = btn.classList.contains('showing');
      setMode(!showing);
    });

    // estado inicial
    setMode(false);
  });
});
