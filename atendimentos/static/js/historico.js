// sgd/atendimentos/static/js/historico.js

document.addEventListener('DOMContentLoaded', () => {
  // Se vier por URL: ?paciente_id=123&paciente_nome=Fulano
  const params = new URLSearchParams(location.search);
  const pid = params.get('paciente_id') || '';
  const nome = params.get('paciente_nome') || '';

  // Pré-preenche lateral (reutiliza helpers do atendimentos.js):
  if (nome) {
    const spanNome = document.getElementById('infoNome');
    if (spanNome) spanNome.textContent = nome;
  }
  if (pid) {
    // Mostra lateral, busca último atendimento e demais infos básicas (reuso de funções)
    const infoBox = document.getElementById('dadosPaciente');
    if (infoBox) infoBox.style.display = 'block';

    // Reaproveita a mesma função do atendimentos.js se quiser (outra opção: duplicar lógica mínima aqui)
    try {
      // preencher "Último Atendimento" rapidamente
      fetch(`/atendimentos/api/ultimo_atendimento?id=${encodeURIComponent(pid)}`)
        .then(r => r.ok ? r.json() : null)
        .then(j => {
          if (!j) return;
          const toBR = (iso) => /^\d{4}-\d{2}-\d{2}$/.test(iso||'') ? iso.split('-').reverse().join('/') : (iso || '-');
          const spanUlt = document.getElementById('infoUltimaConsulta');
          const spanProf = document.getElementById('infoProfissional');
          if (spanUlt) spanUlt.textContent = j && j.ok && j.found ? toBR(j.data) : '-';
          if (spanProf) spanProf.textContent = j && j.ok && j.found ? (j.profissional || '-') : '-';

          // botão ver atendimento (último)
          const btnVer = document.querySelector('#blocoUltimoAtendimento .btn-outline');
          if (btnVer) {
            btnVer.onclick = async (ev) => {
              ev.preventDefault();
              if (!j || !j.ok || !j.found || !j.id) {
                alert('Nenhum atendimento encontrado.');
                return;
              }
              try {
                const r = await fetch(`/atendimentos/${j.id}.json`);
                if (!r.ok) throw new Error('Falha ao carregar atendimento');
                const data = await r.json();
                if (window.UCModal) {
                  window.UCModal.fill(data);
                  window.UCModal.open();
                } else {
                  window.open(`/atendimentos/${j.id}.json`, '_blank');
                }
              } catch (e) {
                console.error(e);
                alert('Não foi possível abrir o atendimento.');
              }
            };
          }
        });
    } catch {}
  }

  // Carregar histórico no container
  carregarHistorico(pid);

  // Filtro de busca
  const filtro = document.getElementById('histSearch');
  if (filtro) {
    filtro.addEventListener('input', () => filtrarHistorico(filtro.value.trim().toLowerCase()));
  }
});

let HIST_CACHE = [];

async function carregarHistorico(pacienteId) {
  const container = document.getElementById('histContainer');
  if (!container) return;

  if (!pacienteId) {
    container.insertAdjacentHTML('beforeend', `<div class="hist-row"><div class="hist-cell" style="grid-column:1 / -1">Selecione um paciente para ver o histórico.</div></div>`);
    return;
  }

  try {
    const r = await fetch(`/atendimentos/api/historico?paciente_id=${encodeURIComponent(pacienteId)}`);
    const j = await r.json();
    if (!j.ok) throw new Error(j.error || 'Erro ao carregar histórico');

    HIST_CACHE = j.items || [];
    renderHistorico(HIST_CACHE);
  } catch (e) {
    console.error(e);
    container.insertAdjacentHTML('beforeend', `<div class="hist-row"><div class="hist-cell" style="grid-column:1 / -1">Não foi possível carregar o histórico.</div></div>`);
  }
}

function renderHistorico(items) {
  const container = document.getElementById('histContainer');
  if (!container) return;

  // remove linhas existentes (menos o header)
  [...container.querySelectorAll('.hist-row:not(.header)')].forEach(el => el.remove());

  const toBR = (iso) => /^\d{4}-\d{2}-\d{2}$/.test(iso||'') ? iso.split('-').reverse().join('/') : (iso || '-');

  if (!items || items.length === 0) {
    container.insertAdjacentHTML('beforeend', `<div class="hist-row"><div class="hist-cell" style="grid-column:1 / -1">Sem atendimentos cadastrados.</div></div>`);
    return;
  }

  items.forEach(it => {
    const row = document.createElement('div');
    row.className = 'hist-row';
    row.innerHTML = `
      <div class="hist-cell" data-label="Data">${toBR(it.data_atendimento)}</div>
      <div class="hist-cell" data-label="Procedimento" title="${(it.procedimento||'').trim()}">${(it.procedimento||'').trim()}</div>
      <div class="hist-cell" data-label="Profissional" title="${it.profissional_nome||'—'}">${it.profissional_nome||'—'}</div>
      <div class="hist-cell" data-label="Status">${it.status||''}</div>
      <div class="hist-cell action">
        <button class="hist-btn" data-aid="${it.id}">Ver</button>
      </div>
    `;
    // click em "Ver" → abre modal
    row.querySelector('.hist-btn').addEventListener('click', async (ev) => {
      ev.preventDefault();
      const aid = ev.currentTarget.getAttribute('data-aid');
      try {
        const r = await fetch(`/atendimentos/${aid}.json`);
        if (!r.ok) throw new Error('Falha ao carregar atendimento');
        const data = await r.json();
        if (window.UCModal) {
          window.UCModal.fill(data);
          window.UCModal.open();
        } else {
          window.open(`/atendimentos/${aid}.json`, '_blank');
        }
      } catch (e) {
        console.error(e);
        alert('Não foi possível abrir o atendimento.');
      }
    });

    container.appendChild(row);
  });
}

function filtrarHistorico(q) {
  const arr = !q ? HIST_CACHE : HIST_CACHE.filter(it => {
    const p = (it.procedimento || '').toLowerCase();
    const pr = (it.profissional_nome || '').toLowerCase();
    return p.includes(q) || pr.includes(q);
  });
  renderHistorico(arr);
}
