// sgd/atendimentos/static/js/atendimentos.js
// ==========================================================
// Atendimento
// - Autocomplete de paciente
// - Resumo do paciente
// - Último atendimento
// - Combo/plano ativo + toggle para consumir sessão
// - Procedimentos sugeridos (CBO logado + CID paciente)
// - Salvar via fetch JSON
// - Remove da fila só se salvou de verdade
// ==========================================================

document.addEventListener("DOMContentLoaded", () => {
  console.log("📦 [atendimentos.js] carregado!");

  inicializarAutocompletePaciente();
  prefFillPacienteFromURL();
  inicializarProcedimentosSugestao();
  inicializarSalvarERedirecionar();
  inicializarComboToggleWatch();
});

/* ===========================================
   Helpers
   =========================================== */
function fmtISOToBR(iso) {
  if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return iso || "-";
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

function getQueryParam(name) {
  const params = new URLSearchParams(window.location.search);
  return params.get(name);
}

function debounce(fn, wait = 250) {
  let t = null;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), wait);
  };
}

function escapeHTML(s) {
  return String(s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function getFilaId() {
  const hid = document.getElementById("fila_id");
  const hiddenVal = (hid?.value || "").trim();
  if (hiddenVal) return hiddenVal;

  const qsVal = (getQueryParam("fila_id") || "").trim();
  if (qsVal) return qsVal;

  return "";
}

function calcIdadeFromISO(iso) {
  if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return "—";

  const hoje = new Date();
  const nasc = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(nasc.getTime())) return "—";

  let idade = hoje.getFullYear() - nasc.getFullYear();
  const m = hoje.getMonth() - nasc.getMonth();

  if (m < 0 || (m === 0 && hoje.getDate() < nasc.getDate())) {
    idade--;
  }

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

function setHidden(el, hidden) {
  if (!el) return;
  el.hidden = !!hidden;
}

function normalizeText(s) {
  return String(s || "").trim().toLowerCase();
}

/* ===========================================
   Fetchers
   =========================================== */
async function fetchDadosPaciente(id) {
  if (!id) return null;
  try {
    const resp = await fetch(`/atendimentos/api/paciente?id=${encodeURIComponent(id)}`);
    if (!resp.ok) return null;
    const j = await resp.json();
    if (!j.ok || !j.found) return null;
    return j;
  } catch (e) {
    console.error("❌ Erro ao carregar dados do paciente:", e);
    return null;
  }
}

async function fetchUltimoAtendimento(pacienteId) {
  if (!pacienteId) return { ok: true, found: false };
  try {
    const resp = await fetch(`/atendimentos/api/ultimo_atendimento?id=${encodeURIComponent(pacienteId)}`);
    if (!resp.ok) return { ok: false };
    const j = await resp.json();
    return j || { ok: false };
  } catch (e) {
    console.error("❌ Erro ao carregar último atendimento:", e);
    return { ok: false };
  }
}

async function fetchComboAtivo(pacienteId) {
  if (!pacienteId) return { ok: true, item: null };
  try {
    const resp = await fetch(`/atendimentos/api/paciente/${encodeURIComponent(pacienteId)}/combo`);
    if (!resp.ok) return { ok: false, item: null };
    const j = await resp.json();
    return j || { ok: false, item: null };
  } catch (e) {
    console.error("❌ Erro ao carregar combo ativo:", e);
    return { ok: false, item: null };
  }
}

async function fetchProcedimentosSugeridos(pacienteId) {
  if (!pacienteId) return { ok: true, items: [] };
  try {
    const resp = await fetch(`/atendimentos/api/procedimentos_sugeridos?paciente_id=${encodeURIComponent(pacienteId)}`);
    if (!resp.ok) return { ok: false, items: [] };
    const j = await resp.json();
    return j || { ok: false, items: [] };
  } catch (e) {
    console.error("❌ Erro ao carregar procedimentos sugeridos:", e);
    return { ok: false, items: [] };
  }
}

/* ===========================================
   Resumo do paciente
   =========================================== */
function preencherBlocoPaciente(dados) {
  if (!dados) return;

  setText("info-nome", dados.nome || "—");
  setText("info-prontuario", dados.prontuario || "—");
  setText("info-mod", dados.mod || "—");

  const nascFmt = /^\d{4}-\d{2}-\d{2}$/.test(dados.nascimento || "")
    ? fmtISOToBR(dados.nascimento)
    : (dados.nascimento || "—");

  setText("info-nascimento", nascFmt);
  setText("info-idade", calcIdadeFromISO(dados.nascimento));
  setText("info-cid", dados.cid || "-");
}

/* ===========================================
   Último atendimento
   =========================================== */
function preencherUltimoAtendimento(info) {
  const btnVer = document.getElementById("btnVerUltimo");
  if (!btnVer) return;

  let ultimoAtendimentoId = null;

  if (info && info.ok && info.found) {
    setText("ua-data", fmtISOToBR(info.data));
    setText("ua-profissional", info.profissional || "-");
    setText("ua-procedimento", info.procedimento || "-");
    setText("ua-codigo", info.codigo_sigtap || "-");
    ultimoAtendimentoId = info.id || null;
  } else {
    setText("ua-data", "—");
    setText("ua-profissional", "—");
    setText("ua-procedimento", "—");
    setText("ua-codigo", "—");
    ultimoAtendimentoId = null;
  }

  btnVer.onclick = async (ev) => {
    ev.preventDefault();
    if (!ultimoAtendimentoId) {
      alert("Nenhum atendimento encontrado para este paciente.");
      return;
    }

    try {
      const r = await fetch(`/atendimentos/${ultimoAtendimentoId}.json`);
      if (!r.ok) throw new Error("Falha ao carregar atendimento");
      const j = await r.json();

      if (window.UCModal) {
        window.UCModal.fill(j);
        window.UCModal.open();
      } else {
        window.open(`/atendimentos/${ultimoAtendimentoId}.json`, "_blank");
      }
    } catch (e) {
      console.error(e);
      alert("Não foi possível abrir o atendimento.");
    }
  };
}

/* ===========================================
   Combo / plano ativo
   =========================================== */
function resetComboCard() {
  const comboCard = document.getElementById("comboCard");
  const comboEmptyCard = document.getElementById("comboEmptyCard");
  const toggle = document.getElementById("toggleUsarCombo");

  setHidden(comboCard, true);
  setHidden(comboEmptyCard, false);

  setText("comboNome", "—");
  setText("comboContratadas", "0");
  setText("comboUsadas", "0");
  setText("comboRestantes", "0");
  setText("comboTipoBadge", "Combo");
  setText("comboStatusBadge", "Ativo");
  setValue("combo_plano_id", "");
  setValue("combo_plano_nome", "");

  const restantesCard = document.getElementById("comboRestantesCard");
  if (restantesCard) {
    restantesCard.classList.remove("is-zero");
  }

  if (toggle) {
    toggle.checked = false;
    toggle.disabled = true;
  }

  atualizarTextoToggleCombo();
}

function atualizarTextoToggleCombo() {
  const toggle = document.getElementById("toggleUsarCombo");
  const help = document.getElementById("comboHelpText");
  const restantes = Number(document.getElementById("comboRestantes")?.textContent || 0);

  if (!help) return;

  if (!toggle || toggle.disabled) {
    help.textContent = "Sem combo/plano ativo vinculado para consumo automático de sessão.";
    return;
  }

  if (restantes <= 0) {
    help.textContent = "Este combo/plano não possui sessões restantes. O consumo automático foi bloqueado.";
    return;
  }

  if (toggle.checked) {
    help.textContent = "Ao salvar o atendimento, 1 sessão será consumida deste combo/plano.";
  } else {
    help.textContent = "Este atendimento será salvo sem consumir sessão do combo/plano.";
  }
}

function preencherComboCard(resp) {
  const comboCard = document.getElementById("comboCard");
  const comboEmptyCard = document.getElementById("comboEmptyCard");
  const toggle = document.getElementById("toggleUsarCombo");
  const restantesCard = document.getElementById("comboRestantesCard");
  const statusBadge = document.getElementById("comboStatusBadge");

  const item = resp?.item || null;
  if (!item || !item.id) {
    resetComboCard();
    return;
  }

  setHidden(comboCard, false);
  setHidden(comboEmptyCard, true);

  const nome = item.combo_nome || item.nome_plano || "Combo/Plano";
  const tipo = item.tipo === "plano" ? "Plano" : "Combo";
  const status = item.status || "Ativo";
  const contratadas = Number(item.sessoes_contratadas || 0);
  const usadas = Number(item.sessoes_usadas || 0);
  const restantes = Number(item.sessoes_restantes || 0);

  setText("comboNome", nome);
  setText("comboContratadas", String(contratadas));
  setText("comboUsadas", String(usadas));
  setText("comboRestantes", String(restantes));
  setText("comboTipoBadge", tipo);
  setText("comboStatusBadge", status);

  setValue("combo_plano_id", item.id);
  setValue("combo_plano_nome", nome);

  if (statusBadge) {
    statusBadge.className = "atd-badge atd-badge--soft";
    if (normalizeText(status) === "encerrado" || restantes <= 0) {
      statusBadge.classList.add("is-zero");
    }
  }

  if (restantesCard) {
    restantesCard.classList.toggle("is-zero", restantes <= 0);
  }

  if (toggle) {
    toggle.disabled = restantes <= 0;
    toggle.checked = restantes > 0; // ligado por padrão se houver saldo
  }

  atualizarTextoToggleCombo();
}

function inicializarComboToggleWatch() {
  const toggle = document.getElementById("toggleUsarCombo");
  if (!toggle) return;

  toggle.addEventListener("change", () => {
    atualizarTextoToggleCombo();
  });
}

/* ===========================================
   Autocomplete paciente
   =========================================== */
function inicializarAutocompletePaciente() {
  const input = document.getElementById("nomePaciente");
  const lista = document.getElementById("listaPacientes");
  const campoHidden = document.getElementById("nomePacienteId");

  if (!input || !lista || !campoHidden) {
    console.warn("⚠️ Campos de paciente/autocomplete não encontrados.");
    return;
  }

  let lastFetchCtl = null;

  function clearList() {
    lista.innerHTML = "";
    lista.style.display = "none";
    lista.hidden = true;
  }

  function renderSugestao(p) {
    const li = document.createElement("li");
    li.textContent = p.nome;
    li.dataset.id = p.id;
    li.tabIndex = 0;

    li.addEventListener("click", () => selectPaciente(p));
    li.addEventListener("keydown", (e) => {
      if (e.key === "Enter") selectPaciente(p);
    });

    return li;
  }

  async function aplicarCargaCompletaPaciente(pacienteId) {
    document.dispatchEvent(
      new CustomEvent("paciente:selecionado", { detail: { pacienteId } })
    );
  }

  async function selectPaciente(paciente) {
    input.value = paciente.nome || "";
    campoHidden.value = paciente.id || "";
    clearList();

    preencherBlocoPaciente(paciente);

    if (paciente.id) {
      const dados = await fetchDadosPaciente(paciente.id);
      if (dados) preencherBlocoPaciente(dados);

      const infoUlt = await fetchUltimoAtendimento(paciente.id);
      preencherUltimoAtendimento(infoUlt);

      const comboResp = await fetchComboAtivo(paciente.id);
      preencherComboCard(comboResp);

      await aplicarCargaCompletaPaciente(paciente.id);
    } else {
      resetComboCard();
      preencherUltimoAtendimento({ ok: true, found: false });
    }
  }

  input.addEventListener(
    "input",
    debounce(async () => {
      const termo = input.value.trim();
      campoHidden.value = "";
      clearList();

      if (termo.length < 2) {
        resetComboCard();
        return;
      }

      if (lastFetchCtl) lastFetchCtl.abort();
      lastFetchCtl = new AbortController();

      try {
        const res = await fetch(
          `/atendimentos/api/sugestoes_pacientes?termo=${encodeURIComponent(termo)}`,
          { signal: lastFetchCtl.signal }
        );

        if (!res.ok) throw new Error("HTTP " + res.status);

        const sugestoes = await res.json();
        if (!Array.isArray(sugestoes) || sugestoes.length === 0) {
          clearList();
          return;
        }

        sugestoes.forEach((p) => lista.appendChild(renderSugestao(p)));
        lista.hidden = false;
        lista.style.display = "block";
      } catch (err) {
        if (err.name !== "AbortError") {
          console.error("❌ Erro ao buscar sugestões:", err);
        }
      }
    }, 220)
  );

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && lista.children.length > 0) {
      e.preventDefault();
      const first = lista.querySelector("li");
      if (!first) return;
      const p = { id: first.dataset.id, nome: first.textContent };
      selectPaciente(p);
    }
  });

  document.addEventListener("click", (e) => {
    if (!lista.contains(e.target) && e.target !== input) {
      clearList();
    }
  });
}

/* ===========================================
   Prefill paciente vindo da fila
   =========================================== */
function prefFillPacienteFromURL() {
  const pid = getQueryParam("paciente_id") || "";
  const nome = getQueryParam("paciente_nome") || "";

  if (!pid && !nome) {
    resetComboCard();
    preencherUltimoAtendimento({ ok: true, found: false });
    return;
  }

  const input = document.getElementById("nomePaciente");
  const campoHidden = document.getElementById("nomePacienteId");

  if (input && nome) input.value = nome;
  if (campoHidden && pid) campoHidden.value = pid;

  preencherBlocoPaciente({ id: pid, nome });

  (async () => {
    if (pid) {
      const dados = await fetchDadosPaciente(pid);
      if (dados) preencherBlocoPaciente(dados);

      const infoUlt = await fetchUltimoAtendimento(pid);
      preencherUltimoAtendimento(infoUlt);

      const comboResp = await fetchComboAtivo(pid);
      preencherComboCard(comboResp);

      document.dispatchEvent(
        new CustomEvent("paciente:selecionado", { detail: { pacienteId: pid } })
      );
    } else {
      resetComboCard();
      preencherUltimoAtendimento({ ok: true, found: false });
    }
  })();
}

/* ===========================================
   Procedimentos sugeridos (dropdown custom)
   =========================================== */
function inicializarProcedimentosSugestao() {
  const wrap = document.getElementById("procedimentosWrap");
  const btnAdd = document.getElementById("btnAddProcedimento");
  const campoPacienteId = document.getElementById("nomePacienteId");

  if (!wrap) return;

  const cache = new Map();
  let currentPacienteId = "";
  let activeDropdown = null;

  function loadHintContainer() {
    let hint = document.getElementById("hint-procs");
    if (!hint) {
      hint = document.createElement("p");
      hint.id = "hint-procs";
      hint.className = "atd-section-sub";
      const head = document.querySelector(".atd-section-head > div");
      if (head) head.appendChild(hint);
    }
    return hint;
  }

  function setHint(text) {
    const el = loadHintContainer();
    if (el) el.textContent = text || "";
  }

  async function loadProcedimentos(pacienteId) {
    currentPacienteId = pacienteId || "";

    if (!pacienteId) {
      setHint("Procedimentos opcionais. Se desejar, escolha conforme as sugestões disponíveis para o paciente.");
      return { ok: true, items: [] };
    }

    if (cache.has(pacienteId)) {
      return cache.get(pacienteId);
    }

    setHint("Carregando procedimentos compatíveis…");

    const j = await fetchProcedimentosSugeridos(pacienteId);
    if (!j || !j.ok) {
      setHint("Não foi possível carregar procedimentos sugeridos.");
      const empty = { ok: false, items: [] };
      cache.set(pacienteId, empty);
      return empty;
    }

    cache.set(pacienteId, j);
    const cids = (j.paciente_cids || []).join(", ") || "—";
    setHint(`Sugestões filtradas por CBO ${j.cbo || "—"} e CID(s) ${cids}.`);
    return j;
  }

  function closeDropdown(dd) {
    if (!dd) return;
    dd.remove();
    if (activeDropdown === dd) activeDropdown = null;
  }

  function closeAnyDropdown() {
    if (activeDropdown) closeDropdown(activeDropdown);
  }

  function ensureHost(inpProc) {
    let host = inpProc.closest(".proc-host");
    if (host) return host;

    const parent = inpProc.parentElement;
    host = document.createElement("div");
    host.className = "proc-host";
    host.style.position = "relative";

    parent.insertBefore(host, inpProc);
    host.appendChild(inpProc);

    return host;
  }

  function mkDropdown(host) {
    closeAnyDropdown();

    const dd = document.createElement("div");
    dd.className = "proc-sug-list";
    dd.setAttribute("role", "listbox");
    host.appendChild(dd);

    activeDropdown = dd;
    return dd;
  }

  function normalize(str) {
    return (str || "").toString().trim().toLowerCase();
  }

  function filterItems(items, term) {
    const t = normalize(term);
    if (!t) return items.slice(0, 80);

    return items
      .filter((x) =>
        normalize(x.descricao).includes(t) || normalize(x.codigo).includes(t)
      )
      .slice(0, 80);
  }

  function renderDropdown(dd, items, onPick) {
    dd.innerHTML = "";

    if (!items || items.length === 0) {
      const empty = document.createElement("div");
      empty.className = "proc-sug-empty";
      empty.textContent = "Nenhum procedimento compatível encontrado.";
      dd.appendChild(empty);
      return;
    }

    items.forEach((p, idx) => {
      const it = document.createElement("div");
      it.className = "proc-sug-item";
      it.setAttribute("role", "option");
      it.dataset.idx = String(idx);

      it.innerHTML = `
        <div class="proc-sug-desc">${escapeHTML(p.descricao || "")}</div>
        <div class="proc-sug-code">${escapeHTML(p.codigo || "")}</div>
      `;

      it.addEventListener("mousedown", (e) => {
        e.preventDefault();
        onPick(p);
      });

      dd.appendChild(it);
    });
  }

  function setActiveItem(dd, idx) {
    const items = Array.from(dd.querySelectorAll(".proc-sug-item"));
    items.forEach((el) => el.classList.remove("is-active"));

    const el = items[idx];
    if (el) {
      el.classList.add("is-active");
      el.scrollIntoView({ block: "nearest" });
    }
  }

  function bindRow(row) {
    if (!row) return;

    const inpProc = row.querySelector('input[name="procedimento[]"]');
    const inpCod = row.querySelector('input[name="codigoProcedimento[]"]');
    if (!inpProc || !inpCod) return;

    inpProc.removeAttribute("list");

    const host = ensureHost(inpProc);

    let state = {
      open: false,
      dd: null,
      filtered: [],
      activeIndex: 0,
      itemsBase: [],
    };

    if (inpProc.dataset.boundProc === "1") return;
    inpProc.dataset.boundProc = "1";

    async function open(term = "") {
      const pid = (currentPacienteId || campoPacienteId?.value || "").trim();
      const bag = await loadProcedimentos(pid);
      state.itemsBase = bag?.items || [];
      state.filtered = filterItems(state.itemsBase, term);
      state.activeIndex = 0;

      if (!state.dd) state.dd = mkDropdown(host);
      state.open = true;

      renderDropdown(state.dd, state.filtered, (p) => {
        inpProc.value = (p.descricao || "").trim();
        inpCod.value = (p.codigo || "").trim();
        closeDropdown(state.dd);
        state.dd = null;
        state.open = false;
      });

      setActiveItem(state.dd, state.activeIndex);
    }

    function close() {
      if (state.dd) closeDropdown(state.dd);
      state.dd = null;
      state.open = false;
    }

    inpProc.addEventListener("focus", async () => {
      await open(inpProc.value || "");
    });

    inpProc.addEventListener(
      "input",
      debounce(async () => {
        await open(inpProc.value || "");
      }, 120)
    );

    inpProc.addEventListener("keydown", (e) => {
      if (!state.open || !state.dd) return;

      const max = (state.filtered?.length || 0) - 1;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        state.activeIndex = Math.min(max, state.activeIndex + 1);
        setActiveItem(state.dd, state.activeIndex);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        state.activeIndex = Math.max(0, state.activeIndex - 1);
        setActiveItem(state.dd, state.activeIndex);
      } else if (e.key === "Enter") {
        e.preventDefault();
        const pick = state.filtered[state.activeIndex];
        if (pick) {
          inpProc.value = (pick.descricao || "").trim();
          inpCod.value = (pick.codigo || "").trim();
        }
        close();
      } else if (e.key === "Escape") {
        e.preventDefault();
        close();
      }
    });

    document.addEventListener("mousedown", (ev) => {
      if (!state.open) return;
      if (!host.contains(ev.target)) close();
    });
  }

  function bindAllRows() {
    wrap.querySelectorAll(".proc-row").forEach((row) => bindRow(row));
  }

  document.addEventListener("paciente:selecionado", async (ev) => {
    const pacienteId = ev?.detail?.pacienteId || "";
    await loadProcedimentos(pacienteId);
    bindAllRows();
  });

  btnAdd?.addEventListener("click", () => {
    setTimeout(() => bindAllRows(), 0);
  });

  wrap.addEventListener("click", (e) => {
    const btn = e.target.closest(".btnRemoveProc");
    if (!btn) return;
    setTimeout(() => bindAllRows(), 0);
  });

  bindAllRows();

  const initialPid = (campoPacienteId?.value || "").trim();
  if (initialPid) loadProcedimentos(initialPid);
  else {
    setHint("Procedimentos opcionais. Se desejar, escolha conforme as sugestões disponíveis para o paciente.");
  }
}

/* ===========================================
   Salvar -> remover da fila -> redirect
   =========================================== */
function inicializarSalvarERedirecionar() {
  const form = document.getElementById("form-atendimento") || document.getElementById("formAtendimento");
  if (!form) return;

  if (form.dataset.bindSave === "1") return;
  form.dataset.bindSave = "1";

  const btnSubmit = form.querySelector('[type="submit"]');
  const toggleCombo = document.getElementById("toggleUsarCombo");
  const comboPlanoId = document.getElementById("combo_plano_id");

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();

    if (btnSubmit) btnSubmit.disabled = true;

    try {
      const fd = new FormData(form);
      const filaId = getFilaId();

      if (filaId && !fd.get("fila_id")) {
        fd.set("fila_id", filaId);
      }

      // garante contabilização consistente
      if (comboPlanoId?.value) {
        fd.set("combo_plano_id", comboPlanoId.value);

        if (toggleCombo?.checked && !toggleCombo?.disabled) {
          fd.set("contabiliza_sessao", "1");
        } else {
          fd.set("contabiliza_sessao", "0");
        }
      } else {
        fd.set("combo_plano_id", "");
        fd.set("contabiliza_sessao", "0");
      }

      const resp = await fetch(form.action || window.location.pathname, {
        method: "POST",
        body: fd,
        headers: {
          "X-Requested-With": "XMLHttpRequest"
        }
      });

      const data = await resp.json().catch(() => null);

      if (!resp.ok || !data || data.ok !== true) {
        throw new Error(data?.error || "Falha ao salvar o atendimento.");
      }

      // remove da fila só se o save foi realmente ok
      if (filaId) {
        try {
          await fetch(`/atendimentos/api/fila/${encodeURIComponent(filaId)}`, {
            method: "DELETE"
          });
          try {
            localStorage.setItem(`fila:removida:${filaId}`, String(Date.now()));
          } catch (_) {}
        } catch (e) {
          console.warn("⚠️ Não foi possível remover da fila:", e);
        }
      }

      window.location.href = data.redirect || "/atendimentos/";
    } catch (err) {
      console.error(err);
      alert(err.message || "Erro ao finalizar atendimento.");
      if (btnSubmit) btnSubmit.disabled = false;
    }
  });
}