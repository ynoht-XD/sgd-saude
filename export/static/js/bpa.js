// export/static/js/bpa.js

// ===== Utils =====
const digits = s => (s || '').replace(/\D+/g, '');

const cpfIsValid = (cpf) => {
  cpf = digits(cpf);
  if (cpf.length !== 11 || /^(\d)\1{10}$/.test(cpf)) return false;

  const calcDV = (base) => {
    let sum = 0;
    for (let i = 0; i < base.length; i++) {
      sum += parseInt(base[i], 10) * (base.length + 1 - i);
    }
    const mod = sum % 11;
    return (mod < 2) ? 0 : 11 - mod;
  };

  const dv1 = calcDV(cpf.slice(0, 9));
  const dv2 = calcDV(cpf.slice(0, 9) + dv1);
  return cpf.endsWith(`${dv1}${dv2}`);
};

const maskCPF = (value) => {
  const v = digits(value).slice(0, 11);
  if (v.length <= 3) return v;
  if (v.length <= 6) return `${v.slice(0, 3)}.${v.slice(3)}`;
  if (v.length <= 9) return `${v.slice(0, 3)}.${v.slice(3, 6)}.${v.slice(6)}`;
  return `${v.slice(0, 3)}.${v.slice(3, 6)}.${v.slice(6, 9)}-${v.slice(9, 11)}`;
};

// ===== Elements =====
const form = document.getElementById('bpaiForm');
const cpfInput = document.getElementById('cpf');
const cpfHidden = document.getElementById('cpfHidden');
const compInput = document.getElementById('competencia');
const compHidden = document.getElementById('competenciaHidden');
const siglaInput = document.getElementById('sigla');
const orgaoInput = document.getElementById('orgao');
const fileInput = document.getElementById('file');
const fileInfo = document.getElementById('fileInfo');
const submitBtn = document.getElementById('submitBtn');
const errorBox = document.getElementById('errorBox');
const okBox = document.getElementById('okBox');

// ===== Listeners =====
cpfInput.addEventListener('input', () => {
  cpfInput.value = maskCPF(cpfInput.value);
  touchValidity();
});

siglaInput.addEventListener('input', () => {
  siglaInput.value = siglaInput.value.toUpperCase().trim();
  touchValidity();
});

orgaoInput.addEventListener('input', touchValidity);
compInput.addEventListener('change', touchValidity);

fileInput.addEventListener('change', () => {
  const f = fileInput.files?.[0];
  fileInfo.textContent = f
    ? `${f.name} • ${(f.size / 1024 / 1024).toFixed(2)} MB`
    : 'Nenhum arquivo selecionado.';
  touchValidity();
});

// ===== Validation =====
function touchValidity() {
  errorBox.style.display = 'none';
  okBox.style.display = 'none';

  const hasFile = fileInput.files && fileInput.files.length > 0;
  const cpfOk = cpfIsValid(cpfInput.value);
  const compOk = !!compInput.value;
  const siglaOk = siglaInput.value.trim().length > 0;
  const orgaoOk = orgaoInput.value.trim().length > 0;

  submitBtn.disabled = !(hasFile && cpfOk && compOk && siglaOk && orgaoOk);

  // feedback visual mínimo
  cpfInput.style.borderColor = cpfOk ? 'rgba(148,163,184,.35)' : 'rgba(239,68,68,.8)';
  compInput.style.borderColor = compOk ? 'rgba(148,163,184,.35)' : 'rgba(239,68,68,.8)';
  siglaInput.style.borderColor = siglaOk ? 'rgba(148,163,184,.35)' : 'rgba(239,68,68,.8)';
  orgaoInput.style.borderColor = orgaoOk ? 'rgba(148,163,184,.35)' : 'rgba(239,68,68,.8)';
  fileInput.style.borderColor = hasFile ? 'rgba(148,163,184,.35)' : 'rgba(239,68,68,.8)';
}

// ===== Submit Handler =====
form.addEventListener('submit', (e) => {
  if (submitBtn.disabled) {
    e.preventDefault();
    errorBox.style.display = 'block';
    return;
  }

  cpfHidden.value = digits(cpfInput.value);
  const [yyyy, mm] = compInput.value.split('-');
  compHidden.value = (mm && yyyy) ? `${mm}/${yyyy}` : '';

  okBox.style.display = 'block';
});

// Init
touchValidity();
