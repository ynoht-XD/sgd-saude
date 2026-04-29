// sgd/atendimentos/static/js/atendimentos.js

const PROC_PADRAO = {
  codigo: "0301010048",
  descricao: "CONSULTA DE PROFISSIONAIS DE NIVEL SUPERIOR NA ATENÇÃO ESPECIALIZADA (EXCETO MÉDICO)",
  quantidade: 1,
};

let sugestoesCache = [];
let ultimoAtendimentoCache = null;

document.addEventListener("DOMContentLoaded", () => {
  console.log("📦 [atendimentos.js] carregado!");

  initComboCollapse();
  initComboToggle();
  initEvolucaoOculta();

  initPacienteFromURL();

  initProcedimentos();
  initModalSugestoes();
  initHistoricoProcedimentos();
  initVozEvolucao();
  initSalvar();
});

/* ==========================================================
   HELPERS
========================================================== */

function qs(sel, root = document) {
  return root.querySelector(sel);
}

function qsa(sel, root = document) {
  return Array.from(root.querySelectorAll(sel));
}

function getParam(name) {
  return new URLSearchParams(window.location.search).get(name) || "";
}

function escapeHTML(s) {
  return String(s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function normalize(s) {
  return String(s || "").trim().toLowerCase();
}

function fmtISOToBR(value) {
  if (!value) return "—";
  const iso = String(value).slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return value;
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

function calcIdade(iso) {
  if (!iso || !/^\d{4}-\d{2}-\d{2}/.test(iso)) return "—";

  const nasc = new Date(`${String(iso).slice(0, 10)}T00:00:00`);
  const hoje = new Date();

  let idade = hoje.getFullYear() - nasc.getFullYear();
  const m = hoje.getMonth() - nasc.getMonth();

  if (m < 0 || (m === 0 && hoje.getDate() < nasc.getDate())) idade--;

  return `${idade} ano(s)`;
}

function setText(id, value, fallback = "—") {
  const el = document.getElementById(id);
  if (el) el.textContent = value || fallback;
}

function setValue(id, value) {
  const el = document.getElementById(id);
  if (el) el.value = value ?? "";
}

function getPacienteId() {
  return (qs("#nomePaciente")?.value || getParam("paciente_id") || "").trim();
}

function getFilaId() {
  return (qs("#fila_id")?.value || getParam("fila_id") || "").trim();
}

function debounce(fn, delay = 180) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

/* ==========================================================
   FETCHERS
========================================================== */

async function fetchJSON(url, options = {}) {
  const resp = await fetch(url, options);
  const data = await resp.json().catch(() => null);

  if (!resp.ok) {
    throw new Error(data?.error || `Erro HTTP ${resp.status}`);
  }

  return data;
}

async function fetchPaciente(id) {
  if (!id) return null;
  const j = await fetchJSON(`/atendimentos/api/paciente?id=${encodeURIComponent(id)}`);
  return j?.ok && j?.found ? j : null;
}

async function fetchUltimo(id) {
  if (!id) return { ok: true, found: false };
  return fetchJSON(`/atendimentos/api/ultimo_atendimento?id=${encodeURIComponent(id)}`);
}

async function fetchCombo(id) {
  if (!id) return { ok: true, item: null };
  return fetchJSON(`/atendimentos/api/paciente/${encodeURIComponent(id)}/combo`);
}

async function fetchSugestoesProcedimentos(id) {
  if (!id) return { ok: true, items: [] };
  return fetchJSON(`/atendimentos/api/procedimentos_sugeridos?paciente_id=${encodeURIComponent(id)}`);
}

/* ==========================================================
   PACIENTE
========================================================== */

function preencherPaciente(dados) {
  if (!dados) return;

  setText("info-nome", dados.nome || "—");
  setText("info-prontuario", dados.prontuario || "—");
  setText("info-mod", dados.mod || "—");
  setText("info-nascimento", fmtISOToBR(dados.nascimento));
  setText("info-idade", calcIdade(dados.nascimento));
  setText("info-cid", dados.cid || "—");
}

function preencherUltimo(info) {
  const btn = qs("#btnVerUltimo");

  if (info?.ok && info?.found) {
    setText("ua-data", fmtISOToBR(info.data));
    setText("ua-profissional", info.profissional || "—");

    if (btn) {
      btn.dataset.id = info.id || "";
      btn.disabled = false;
    }
  } else {
    setText("ua-data", "—");
    setText("ua-profissional", "—");

    if (btn) {
      btn.dataset.id = "";
      btn.disabled = false;
    }
  }
}

async function carregarPacienteCompleto(id) {
  if (!id) {
    resetCombo();
    preencherUltimo({ ok: true, found: false });
    return;
  }

  try {
    const paciente = await fetchPaciente(id);
    if (paciente) preencherPaciente(paciente);

    const ultimo = await fetchUltimo(id);
    preencherUltimo(ultimo);

    const combo = await fetchCombo(id);
    preencherCombo(combo);

    await carregarSugestoesProcedimentos(false);

    document.dispatchEvent(new CustomEvent("paciente:selecionado", {
      detail: { pacienteId: id }
    }));
  } catch (e) {
    console.error(e);
  }
}

function initPacienteFromURL() {
  const pid = getParam("paciente_id");
  const nome = getParam("paciente_nome");

  if (pid) setValue("nomePaciente", pid);
  if (nome) setText("info-nome", nome);

  carregarPacienteCompleto(pid || getPacienteId());

  qs("#btnVerUltimo")?.addEventListener("click", async () => {
    const aid = qs("#btnVerUltimo")?.dataset.id;

    if (!aid) {
      alert("Nenhum atendimento encontrado para este paciente.");
      return;
    }

    try {
      const j = await fetchJSON(`/atendimentos/${aid}.json`);

      if (window.UCModal) {
        window.UCModal.fill(j);
        window.UCModal.open();
      } else {
        alert(`Último atendimento:\n\nData: ${fmtISOToBR(j.data_atendimento)}\nProfissional: ${j.profissional_nome || "—"}`);
      }
    } catch (e) {
      alert(e.message || "Erro ao abrir o atendimento.");
    }
  });
}

/* ==========================================================
   COMBO
========================================================== */

function initComboCollapse() {
  const btn = qs("#btnToggleComboPanel");
  const body = qs("#comboPanelBody");
  const status = qs("#comboCollapseStatus");

  if (!btn || !body) return;

  function setExpanded(expanded) {
    btn.setAttribute("aria-expanded", expanded ? "true" : "false");
    body.hidden = !expanded;
    body.classList.toggle("is-collapsed", !expanded);
    body.classList.toggle("is-expanded", expanded);

    const custom = btn.dataset.statusText || "";
    if (status) status.textContent = expanded ? "Aberto" : (custom || "Recolhido");
  }

  setExpanded(false);

  btn.addEventListener("click", () => {
    setExpanded(btn.getAttribute("aria-expanded") !== "true");
  });

  window.atdComboCollapse = {
    open: () => setExpanded(true),
    close: () => setExpanded(false),
    status: (txt) => {
      btn.dataset.statusText = txt || "Recolhido";
      if (btn.getAttribute("aria-expanded") !== "true" && status) {
        status.textContent = btn.dataset.statusText;
      }
    },
  };
}

function resetCombo() {
  qs("#comboCard")?.setAttribute("hidden", "");
  qs("#comboEmptyCard")?.removeAttribute("hidden");

  setValue("combo_plano_id", "");
  setValue("combo_plano_nome", "");

  setText("comboNome", "—");
  setText("comboContratadas", "0");
  setText("comboUsadas", "0");
  setText("comboRestantes", "0");

  const toggle = qs("#toggleUsarCombo");
  if (toggle) {
    toggle.checked = false;
    toggle.disabled = true;
  }

  window.atdComboCollapse?.status("Sem combo/plano ativo");
  window.atdComboCollapse?.close();
}

function atualizarTextoCombo() {
  const help = qs("#comboHelpText");
  const toggle = qs("#toggleUsarCombo");
  const restantes = Number(qs("#comboRestantes")?.textContent || 0);

  if (!help) return;

  if (!toggle || toggle.disabled) {
    help.textContent = "Sem combo/plano ativo vinculado para consumo automático de sessão.";
  } else if (restantes <= 0) {
    help.textContent = "Este combo/plano não possui sessões restantes.";
  } else if (toggle.checked) {
    help.textContent = "Ao salvar, 1 sessão será consumida deste combo/plano.";
  } else {
    help.textContent = "Este atendimento será salvo sem consumir sessão do combo/plano.";
  }
}

function preencherCombo(resp) {
  const item = resp?.item;

  if (!item?.id) {
    resetCombo();
    return;
  }

  qs("#comboCard")?.removeAttribute("hidden");
  qs("#comboEmptyCard")?.setAttribute("hidden", "");

  const nome = item.combo_nome || item.nome_plano || "Combo/Plano";
  const restantes = Number(item.sessoes_restantes || 0);

  setText("comboNome", nome);
  setText("comboTipoBadge", item.tipo === "plano" ? "Plano" : "Combo");
  setText("comboStatusBadge", item.status || "Ativo");
  setText("comboContratadas", String(item.sessoes_contratadas || 0));
  setText("comboUsadas", String(item.sessoes_usadas || 0));
  setText("comboRestantes", String(restantes));

  setValue("combo_plano_id", item.id);
  setValue("combo_plano_nome", nome);

  const toggle = qs("#toggleUsarCombo");
  if (toggle) {
    toggle.disabled = restantes <= 0;
    toggle.checked = restantes > 0;
  }

  window.atdComboCollapse?.status(`${restantes} sessão(ões) restantes`);
  window.atdComboCollapse?.close();
  atualizarTextoCombo();
}

function initComboToggle() {
  qs("#toggleUsarCombo")?.addEventListener("change", atualizarTextoCombo);
}

/* ==========================================================
   PROCEDIMENTOS + SUGESTÕES INLINE
========================================================== */

function isProcRowEmpty(row) {
  const proc = qs('input[name="procedimento[]"]', row)?.value || "";
  const cod = qs('input[name="codigoProcedimento[]"]', row)?.value || "";
  return !proc.trim() && !cod.trim();
}

function setProcRow(row, proc = {}) {
  if (!row) return;

  const inp = qs('input[name="procedimento[]"]', row);
  const cod = qs('input[name="codigoProcedimento[]"]', row);
  const qtd = qs('input[name="quantidadeProcedimento[]"]', row);

  if (inp) inp.value = proc.procedimento || proc.descricao || "";
  if (cod) cod.value = proc.codigo_sigtap || proc.codigo || "";
  if (qtd) qtd.value = proc.quantidade || 1;

  esconderSugestoesInline(row);
}

function criarLinhaProcedimento(proc = {}) {
  const row = document.createElement("div");
  row.className = "proc-row atd-proc-row";

  row.innerHTML = `
    <div class="proc-col proc-col--desc">
      <label class="sr-only">Procedimento</label>

      <div class="proc-input-inline">
        <input type="text"
               name="procedimento[]"
               class="input proc-input"
               placeholder="Digite o código ou nome do procedimento"
               autocomplete="off"
               value="${escapeHTML(proc.procedimento || proc.descricao || "")}">
      </div>

      <div class="proc-inline-suggestions" hidden></div>
    </div>

    <input type="hidden"
           name="codigoProcedimento[]"
           class="proc-codigo"
           value="${escapeHTML(proc.codigo_sigtap || proc.codigo || "")}">

    <div class="proc-col proc-col--qtd">
      <label class="sr-only">Quantidade</label>
      <input type="number"
             name="quantidadeProcedimento[]"
             class="input proc-qtd"
             min="1"
             value="${escapeHTML(proc.quantidade || 1)}">
    </div>

    <div class="proc-col proc-col--actions">
      <button type="button" class="btn btn--ghost btnRemoveProc">
        Remover
      </button>
    </div>
  `;

  return row;
}

function garantirProcedimentoPadrao() {
  const wrap = qs("#procedimentosWrap");
  if (!wrap) return;

  const rows = qsa(".proc-row", wrap);

  if (!rows.length) {
    wrap.appendChild(criarLinhaProcedimento(PROC_PADRAO));
    return;
  }

  if (isProcRowEmpty(rows[0])) {
    setProcRow(rows[0], PROC_PADRAO);
  }
}

function limparProcedimentos({ comPadrao = true } = {}) {
  const wrap = qs("#procedimentosWrap");
  if (!wrap) return;

  wrap.innerHTML = "";
  wrap.appendChild(criarLinhaProcedimento(comPadrao ? PROC_PADRAO : {}));
}

function adicionarProcedimento(proc = {}) {
  const wrap = qs("#procedimentosWrap");
  if (!wrap) return;

  const rows = qsa(".proc-row", wrap);

  if (rows.length === 1 && isProcRowEmpty(rows[0])) {
    setProcRow(rows[0], proc);
    return;
  }

  wrap.appendChild(criarLinhaProcedimento(proc));
}

function filtrarSugestoes(term) {
  const t = normalize(term);
  if (!t) return [];

  return sugestoesCache
    .filter((p) =>
      normalize(p.codigo).includes(t) ||
      normalize(p.descricao).includes(t)
    )
    .slice(0, 8);
}

function mostrarSugestoesInline(row, items) {
  const box = qs(".proc-inline-suggestions", row);
  if (!box) return;

  if (!items.length) {
    box.hidden = true;
    box.innerHTML = "";
    return;
  }

  box.innerHTML = items.map((p) => `
    <button type="button"
            class="proc-inline-item"
            data-codigo="${escapeHTML(p.codigo)}"
            data-descricao="${escapeHTML(p.descricao)}">
      <strong>${escapeHTML(p.codigo || "—")}</strong>
      <span>${escapeHTML(p.descricao || "")}</span>
    </button>
  `).join("");

  box.hidden = false;
}

function esconderSugestoesInline(row) {
  const box = qs(".proc-inline-suggestions", row);
  if (!box) return;
  box.hidden = true;
  box.innerHTML = "";
}

async function carregarSugestoesProcedimentos(showAlert = true) {
  const pacienteId = getPacienteId();

  if (!pacienteId) {
    if (showAlert) alert("Paciente não identificado.");
    return [];
  }

  const j = await fetchSugestoesProcedimentos(pacienteId);
  sugestoesCache = j?.items || [];

  const cids = (j?.paciente_cids || []).join(", ") || "—";
  const resumo = qs("#sugestoesProcResumo");

  if (resumo) {
    resumo.textContent = `CBO: ${j?.cbo || "—"} · CID(s): ${cids} · ${sugestoesCache.length} procedimento(s)`;
  }

  renderSugestoesModal(sugestoesCache);
  return sugestoesCache;
}

function initProcedimentos() {
  const wrap = qs("#procedimentosWrap");
  const btnAdd = qs("#btnAddProcedimento");

  if (!wrap) return;

  garantirProcedimentoPadrao();

  btnAdd?.addEventListener("click", () => adicionarProcedimento({}));

  wrap.addEventListener("input", debounce(async (e) => {
    const input = e.target.closest('input[name="procedimento[]"]');
    if (!input) return;

    const row = input.closest(".proc-row");
    const cod = qs('input[name="codigoProcedimento[]"]', row);

    if (cod) cod.value = "";

    if (!sugestoesCache.length) {
      await carregarSugestoesProcedimentos(false);
    }

    mostrarSugestoesInline(row, filtrarSugestoes(input.value));
  }, 160));

  wrap.addEventListener("focusin", async (e) => {
    const input = e.target.closest('input[name="procedimento[]"]');
    if (!input) return;

    if (!sugestoesCache.length) {
      await carregarSugestoesProcedimentos(false);
    }

    const row = input.closest(".proc-row");
    mostrarSugestoesInline(row, filtrarSugestoes(input.value));
  });

  wrap.addEventListener("click", (e) => {
    const sug = e.target.closest(".proc-inline-item");
    if (sug) {
      const row = sug.closest(".proc-row");
      setProcRow(row, {
        codigo: sug.dataset.codigo || "",
        descricao: sug.dataset.descricao || "",
        quantidade: 1,
      });
      return;
    }

    const btn = e.target.closest(".btnRemoveProc");
    if (!btn) return;

    const row = btn.closest(".proc-row");
    row?.remove();

    if (!qsa(".proc-row", wrap).length) {
      wrap.appendChild(criarLinhaProcedimento(PROC_PADRAO));
    }
  });

  document.addEventListener("click", (e) => {
    if (e.target.closest(".proc-row")) return;
    qsa(".proc-row", wrap).forEach(esconderSugestoesInline);
  });
}

/* ==========================================================
   MODAL SUGESTÕES
========================================================== */

function renderSugestoesModal(items) {
  const lista = qs("#listaSugestoesProc");
  const termo = normalize(qs("#buscaSugestaoProc")?.value || "");

  if (!lista) return;

  const filtrados = (items || []).filter((p) => {
    if (!termo) return true;
    return normalize(p.codigo).includes(termo) || normalize(p.descricao).includes(termo);
  });

  if (!filtrados.length) {
    lista.innerHTML = `<p class="atd-empty">Nenhum procedimento encontrado.</p>`;
    return;
  }

  lista.innerHTML = filtrados.map((p) => `
    <label class="atd-sugestao-proc">
      <input type="checkbox"
             data-codigo="${escapeHTML(p.codigo)}"
             data-descricao="${escapeHTML(p.descricao)}">
      <span>
        <strong>${escapeHTML(p.descricao)}</strong>
        <small>${escapeHTML(p.codigo)} · Competência ${escapeHTML(p.competencia || "—")}</small>
      </span>
    </label>
  `).join("");
}

function initModalSugestoes() {
  const modal = qs("#modalSugestoesProc");

  qs("#btnAbrirSugestoesProc")?.addEventListener("click", async () => {
    if (!modal) return;

    if (typeof modal.showModal === "function") modal.showModal();
    else modal.setAttribute("open", "");

    await carregarSugestoesProcedimentos();
  });

  qs("#btnFecharSugestoesProc")?.addEventListener("click", () => {
    if (typeof modal?.close === "function") modal.close();
    else modal?.removeAttribute("open");
  });

  qs("#buscaSugestaoProc")?.addEventListener("input", () => {
    renderSugestoesModal(sugestoesCache);
  });

  qs("#btnAdicionarSelecionadosProc")?.addEventListener("click", () => {
    const marcados = qsa("#listaSugestoesProc input:checked");

    if (!marcados.length) {
      alert("Selecione pelo menos um procedimento.");
      return;
    }

    marcados.forEach((ck) => {
      adicionarProcedimento({
        codigo: ck.dataset.codigo || "",
        descricao: ck.dataset.descricao || "",
        quantidade: 1,
      });
    });

    if (typeof modal?.close === "function") modal.close();
    else modal?.removeAttribute("open");
  });
}

/* ==========================================================
   HISTÓRICO
========================================================== */

function renderHistoricoProcedimentos(info) {
  const box = qs("#historicoProcedimentosBox");
  const lista = qs("#historicoProcedimentosLista");
  const hint = qs("#historicoProcedimentosHint");

  if (!box || !lista) return;

  const procs = info?.procedimentos || [];

  if (!procs.length) {
    box.hidden = true;
    lista.innerHTML = "";
    return;
  }

  box.hidden = false;
  if (hint) hint.textContent = `${procs.length} procedimento(s) encontrado(s) no último atendimento`;

  lista.innerHTML = procs.map((p) => `
    <button type="button"
            class="atd-chip atd-chip-proc"
            data-codigo="${escapeHTML(p.codigo_sigtap || "")}"
            data-procedimento="${escapeHTML(p.procedimento || "")}">
      ${escapeHTML(p.codigo_sigtap || "")} · ${escapeHTML(p.procedimento || "")}
    </button>
  `).join("");
}

function initHistoricoProcedimentos() {
  document.addEventListener("paciente:selecionado", async (ev) => {
    const pacienteId = ev.detail?.pacienteId;
    if (!pacienteId) return;

    try {
      ultimoAtendimentoCache = await fetchUltimo(pacienteId);
      renderHistoricoProcedimentos(ultimoAtendimentoCache);
    } catch (e) {
      console.warn(e);
    }
  });

  qs("#historicoProcedimentosLista")?.addEventListener("click", (e) => {
    const btn = e.target.closest(".atd-chip-proc");
    if (!btn) return;

    adicionarProcedimento({
      codigo: btn.dataset.codigo || "",
      descricao: btn.dataset.procedimento || "",
      quantidade: 1,
    });
  });

  qs("#btnUsarUltimosProcs")?.addEventListener("click", async () => {
    const pacienteId = getPacienteId();

    if (!pacienteId) {
      alert("Paciente não identificado.");
      return;
    }

    if (!ultimoAtendimentoCache) {
      ultimoAtendimentoCache = await fetchUltimo(pacienteId);
    }

    const procs = ultimoAtendimentoCache?.procedimentos || [];

    if (!procs.length) {
      alert("Nenhum procedimento anterior encontrado para este paciente.");
      return;
    }

    limparProcedimentos({ comPadrao: false });

    procs.forEach((p, idx) => {
      const item = {
        descricao: p.procedimento || "",
        codigo: p.codigo_sigtap || "",
        quantidade: 1,
      };

      if (idx === 0) setProcRow(qs(".proc-row"), item);
      else adicionarProcedimento(item);
    });
  });
}

/* ==========================================================
   VOZ
========================================================== */

function initVozEvolucao() {
  const btn = qs("#btnFalarEvolucao");
  const textarea = qs("#evolucao");
  const status = qs("#voiceStatus");

  if (!btn || !textarea) return;

  if (status) {
    status.hidden = true;
    status.style.display = "none";
  }

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!SpeechRecognition) {
    btn.disabled = true;
    btn.textContent = "🎙️ Indisponível";
    return;
  }

  const rec = new SpeechRecognition();
  rec.lang = "pt-BR";
  rec.continuous = true;
  rec.interimResults = true;

  let listening = false;
  let baseText = "";
  let finalTranscript = "";

  function setListening(on) {
    listening = on;
    btn.setAttribute("aria-pressed", on ? "true" : "false");
    btn.classList.toggle("is-listening", on);
    btn.textContent = on ? "🔴 Ouvindo" : "🎙️ Falar";

    if (status) {
      status.hidden = !on;
      status.style.display = on ? "inline-flex" : "none";
    }
  }

  rec.onstart = () => setListening(true);
  rec.onend = () => setListening(false);

  rec.onerror = (event) => {
    console.warn("Erro no reconhecimento de voz:", event.error);
    setListening(false);
  };

  rec.onresult = (event) => {
    let interimTranscript = "";

    for (let i = event.resultIndex; i < event.results.length; i++) {
      const transcript = event.results[i][0].transcript.trim();

      if (event.results[i].isFinal) {
        finalTranscript += `${transcript} `;
      } else {
        interimTranscript += ` ${transcript}`;
      }
    }

    textarea.value = [
      baseText.trim(),
      finalTranscript.trim(),
      interimTranscript.trim(),
    ].filter(Boolean).join(" ").replace(/\s+/g, " ").trim();
  };

  btn.addEventListener("click", () => {
    if (listening) {
      rec.stop();
      return;
    }

    baseText = textarea.value || "";
    finalTranscript = "";

    try {
      rec.start();
    } catch (e) {
      console.warn("Reconhecimento já iniciado ou indisponível:", e);
    }
  });
}

/* ==========================================================
   EVOLUÇÃO OCULTA
========================================================== */

function initEvolucaoOculta() {
  const btn = qs("#btnToggleEvolucaoOculta");
  const body = qs("#evolucaoOcultaBody");
  const boxCbos = qs("#boxCbosAutorizados");

  if (btn && body) {
    function setOpen(open) {
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      body.hidden = !open;
      body.classList.toggle("is-collapsed", !open);
      body.classList.toggle("is-expanded", open);
    }

    setOpen(false);

    btn.addEventListener("click", () => {
      setOpen(btn.getAttribute("aria-expanded") !== "true");
    });
  }

  qsa('input[name="evolucao_oculta_visibilidade"]').forEach((radio) => {
    radio.addEventListener("change", () => {
      const selected = qs('input[name="evolucao_oculta_visibilidade"]:checked')?.value;
      if (boxCbos) boxCbos.hidden = selected !== "cbos";
    });
  });
}

/* ==========================================================
   SALVAR
========================================================== */

function hasProcedimento() {
  return qsa('input[name="procedimento[]"]').some((el) => (el.value || "").trim());
}

function initSalvar() {
  const form = qs("#form-atendimento");
  if (!form || form.dataset.bound === "1") return;

  form.dataset.bound = "1";

  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const pacienteId = getPacienteId();

    if (!pacienteId) {
      alert("Paciente não informado. Volte pela fila ou selecione um paciente.");
      return;
    }

    setValue("nomePaciente", pacienteId);

    const btn = form.querySelector('[type="submit"]');
    if (btn) btn.disabled = true;

    try {
      garantirProcedimentoPadrao();

      const fd = new FormData(form);

      fd.set("nomePaciente", pacienteId);
      fd.set("fila_id", getFilaId());

      const comboId = qs("#combo_plano_id")?.value || "";
      const toggle = qs("#toggleUsarCombo");

      fd.set("combo_plano_id", comboId);
      fd.set(
        "contabiliza_sessao",
        comboId && toggle?.checked && !toggle?.disabled ? "1" : "0"
      );

      if (!hasProcedimento()) {
        const ok = confirm("Nenhum procedimento foi selecionado. Deseja salvar mesmo assim?");

        if (!ok) {
          if (btn) btn.disabled = false;
          return;
        }

        fd.set("enviar_sem_procedimento", "1");
      } else {
        fd.set("enviar_sem_procedimento", "0");
      }

      const resp = await fetch(form.action, {
        method: "POST",
        body: fd,
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });

      const data = await resp.json().catch(() => null);

      if (!resp.ok || !data?.ok) {
        throw new Error(data?.error || "Falha ao salvar atendimento.");
      }

      window.location.href = data.redirect || "/atendimentos/";
    } catch (err) {
      console.error(err);
      alert(err.message || "Erro ao salvar atendimento.");

      if (btn) btn.disabled = false;
    }
  });
}

// ====== EXTRA FINAL ======

// CANCELAR
function initCancelar() {
  const btn = qs("#btnCancelarAtendimento");
  if (!btn) return;

  btn.addEventListener("click", () => {
    if (confirm("Deseja cancelar o atendimento?")) {
      window.location.href = "/atendimentos/";
    }
  });
}

// ==========================================================
// CBO AUTORIZADOS (AUTOCOMPLETE BONITO)
// ==========================================================

function initCboAutocomplete() {
  const input = qs("#cboSearchOculto");
  const boxSug = qs("#cboSugestoesOcultas");
  const listaSel = qs("#cbosSelecionadosOcultos");
  const hidden = qs("#evolucao_oculta_cbos");

  if (!input || !boxSug || !listaSel || !hidden) return;

  let selecionados = [];

  function renderSelecionados() {
    listaSel.innerHTML = selecionados.map(cbo => `
      <div class="atd-cbo-chip" data-codigo="${cbo.codigo}">
        <span>${cbo.codigo} - ${cbo.descricao}</span>
        <button type="button" class="remove-cbo">×</button>
      </div>
    `).join("");

    hidden.value = selecionados.map(c => c.codigo).join(",");
  }

  async function buscarCbos(term) {
    if (!term || term.length < 2) {
      boxSug.hidden = true;
      return;
    }

    try {
      const resp = await fetch(`/atendimentos/api/cbos_sugestoes?q=${encodeURIComponent(term)}`);
      const data = await resp.json();

      if (!data.ok) return;

      const items = data.items || [];

      if (!items.length) {
        boxSug.hidden = true;
        return;
      }

      boxSug.innerHTML = items.map(i => `
        <div class="atd-cbo-item"
             data-codigo="${i.codigo}"
             data-descricao="${i.descricao}">
          <strong>${i.codigo}</strong>
          <span>${i.descricao}</span>
        </div>
      `).join("");

      boxSug.hidden = false;

    } catch (e) {
      console.error("Erro ao buscar CBO:", e);
    }
  }

  input.addEventListener("input", debounce(e => {
    buscarCbos(e.target.value);
  }, 200));

  boxSug.addEventListener("click", e => {
    const item = e.target.closest(".atd-cbo-item");
    if (!item) return;

    const codigo = item.dataset.codigo;
    const descricao = item.dataset.descricao;

    if (selecionados.find(c => c.codigo === codigo)) return;

    selecionados.push({ codigo, descricao });
    renderSelecionados();

    input.value = "";
    boxSug.hidden = true;
  });

  listaSel.addEventListener("click", e => {
    if (!e.target.classList.contains("remove-cbo")) return;

    const chip = e.target.closest(".atd-cbo-chip");
    const codigo = chip.dataset.codigo;

    selecionados = selecionados.filter(c => c.codigo !== codigo);
    renderSelecionados();
  });

  document.addEventListener("click", e => {
    if (!e.target.closest(".atd-cbo-search-wrap")) {
      boxSug.hidden = true;
    }
  });
}

// ==========================================================
// MELHORIA VOZ (ANTI DUPLICAÇÃO)
// ==========================================================

function initVozEvolucaoMelhorado() {
  const btn = qs("#btnFalarEvolucao");
  const textarea = qs("#evolucao");
  const status = qs("#voiceStatus");

  if (!btn || !textarea) return;

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!SpeechRecognition) return;

  const rec = new SpeechRecognition();
  rec.lang = "pt-BR";
  rec.continuous = true;
  rec.interimResults = false; // 🔥 REMOVE DUPLICAÇÃO

  let listening = false;

  function toggle(on) {
    listening = on;
    btn.textContent = on ? "🔴 Ouvindo" : "🎙️ Falar";
    btn.classList.toggle("is-listening", on);

    if (status) {
      status.hidden = !on;
    }
  }

  rec.onstart = () => toggle(true);
  rec.onend = () => toggle(false);

  rec.onresult = (e) => {
    let text = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      text += e.results[i][0].transcript + " ";
    }

    textarea.value += " " + text.trim();
  };

  btn.addEventListener("click", () => {
    if (listening) rec.stop();
    else rec.start();
  });
}

// ==========================================================
// INICIALIZAÇÃO FINAL
// ==========================================================

document.addEventListener("DOMContentLoaded", () => {
  initCancelar();
  initCboAutocomplete();
  initVozEvolucaoMelhorado();
});