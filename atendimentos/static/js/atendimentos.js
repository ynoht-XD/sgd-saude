// sgd/atendimentos/static/js/atendimentos.js
// ✅ Procedimentos sugeridos via DB (CBO logado + CID paciente)
// ✅ Autocomplete paciente + cards + último atendimento
// ✅ Dropdown custom de procedimentos (CSS real)
// ✅ FIX: ao salvar -> remove da fila (se tiver fila_id) e redireciona /atendimentos

document.addEventListener("DOMContentLoaded", () => {
  console.log("📦 [atendimentos.js] carregado!");

  inicializarAutocompletePaciente();
  prefFillPacienteFromURL();
  inicializarProcedimentosSugestao(); // ⭐ dropdown custom
  inicializarSalvarERedirecionar();   // ⭐ FIX salvar + remover fila + redirect
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

function getFilaId() {
  // prioridade: hidden do form (mais confiável)
  const hid = document.getElementById("fila_id");
  const v1 = (hid?.value || "").trim();
  if (v1) return v1;

  // fallback: querystring
  const v2 = (getQueryParam("fila_id") || "").trim();
  return v2 || "";
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
   Preencher cards (paciente + último atendimento)
   =========================================== */
function preencherBlocoPaciente(dados) {
  if (!dados) return;

  const spanNome = document.getElementById("info-nome");
  const spanProntuario = document.getElementById("info-prontuario");
  const spanStatus = document.getElementById("info-status");
  const spanMod = document.getElementById("info-mod");
  const spanNascimento = document.getElementById("info-nascimento");
  const spanCid = document.getElementById("info-cid");

  if (spanNome) spanNome.textContent = dados.nome || "";
  if (spanProntuario) spanProntuario.textContent = dados.prontuario || "";
  if (spanStatus) spanStatus.textContent = dados.status || "";
  if (spanMod) spanMod.textContent = dados.mod || "";

  if (spanNascimento) {
    const nasc = dados.nascimento;
    spanNascimento.textContent = /^\d{4}-\d{2}-\d{2}$/.test(nasc || "") ? fmtISOToBR(nasc) : (nasc || "");
  }

  if (spanCid) spanCid.textContent = dados.cid || "-";
}

function preencherUltimoAtendimento(info) {
  const spanData = document.getElementById("ua-data");
  const spanProf = document.getElementById("ua-profissional");
  const btnVer = document.getElementById("btnVerUltimo");

  if (!spanData || !spanProf || !btnVer) return;

  let ultimoAtendimentoId = null;

  if (info && info.ok && info.found) {
    spanData.textContent = fmtISOToBR(info.data);
    spanProf.textContent = info.profissional || "-";
    ultimoAtendimentoId = info.id || null;
  } else {
    spanData.textContent = "—";
    spanProf.textContent = "—";
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
   Autocomplete Paciente
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

  async function aplicarProcedimentosSugeridos(pacienteId) {
    document.dispatchEvent(new CustomEvent("paciente:selecionado", { detail: { pacienteId } }));
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

      await aplicarProcedimentosSugeridos(paciente.id);
    }
  }

  input.addEventListener(
    "input",
    debounce(async () => {
      const termo = input.value.trim();
      campoHidden.value = "";
      clearList();

      if (termo.length < 2) return;

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
        if (err.name !== "AbortError") console.error("❌ Erro ao buscar sugestões:", err);
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
    if (!lista.contains(e.target) && e.target !== input) clearList();
  });
}

/* ===========================================
   Prefill vindo da fila
   =========================================== */
function prefFillPacienteFromURL() {
  const pid = getQueryParam("paciente_id") || "";
  const nome = getQueryParam("paciente_nome") || "";

  if (!pid && !nome) return;

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

      document.dispatchEvent(new CustomEvent("paciente:selecionado", { detail: { pacienteId: pid } }));
    }
  })();
}

/* ===========================================
   ⭐ Dropdown de Procedimentos sugeridos (custom)
   =========================================== */
function inicializarProcedimentosSugestao() {
  const wrap = document.getElementById("procedimentosWrap");
  const btnAdd = document.getElementById("btnAddProcedimento");
  const campoPacienteId = document.getElementById("nomePacienteId");

  if (!wrap) return;

  const cache = new Map();
  let currentPacienteId = "";
  let activeDropdown = null;

  function setHint(text) {
    const el = document.getElementById("hint-procs");
    if (el) el.textContent = text || "";
  }

  async function loadProcedimentos(pacienteId) {
    currentPacienteId = pacienteId || "";

    if (!pacienteId) {
      setHint("");
      return { ok: true, items: [] };
    }
    if (cache.has(pacienteId)) return cache.get(pacienteId);

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
    setHint(`Sugestões filtradas por CBO ${j.cbo || "—"} e CID(s) ${cids}`);
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
      .filter((x) => normalize(x.descricao).includes(t) || normalize(x.codigo).includes(t))
      .slice(0, 80);
  }

  function escapeHTML(s) {
    return String(s || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
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
    const inpCod  = row.querySelector('input[name="codigoProcedimento[]"]');
    if (!inpProc || !inpCod) return;

    inpProc.removeAttribute("list"); // mata datalist nativo

    const host = ensureHost(inpProc);

    let state = {
      open: false,
      dd: null,
      filtered: [],
      activeIndex: 0,
      itemsBase: [],
    };

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
        inpCod.value  = (p.codigo || "").trim();
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

    inpProc.addEventListener("focus", async () => open(inpProc.value || ""));
    inpProc.addEventListener("input", async () => open(inpProc.value || ""));

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
          inpCod.value  = (pick.codigo || "").trim();
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

  btnAdd?.addEventListener("click", () => setTimeout(() => bindAllRows(), 0));

  wrap.addEventListener("click", (e) => {
    const btn = e.target.closest(".btnRemoveProc");
    if (!btn) return;
    setTimeout(() => bindAllRows(), 0);
  });

  bindAllRows();

  const initialPid = (campoPacienteId?.value || "").trim();
  if (initialPid) loadProcedimentos(initialPid);
}

/* ===========================================
   ⭐ FIX: Salvar atendimento -> remover da fila -> redirect
   =========================================== */
function inicializarSalvarERedirecionar() {
  const form = document.getElementById("form-atendimento") || document.getElementById("formAtendimento");
  if (!form) return;

  const btnSubmit = form.querySelector('[type="submit"]');

  // evita bind duplicado caso o script seja incluído 2x
  if (form.dataset.bindSave === "1") return;
  form.dataset.bindSave = "1";

  form.addEventListener("submit", async (ev) => {
    // Fazemos via fetch para controlar a remoção da fila antes do redirect
    ev.preventDefault();

    if (btnSubmit) btnSubmit.disabled = true;

    try {
      const fd = new FormData(form);

      // garante fila_id no POST também (caso backend use)
      const filaId = getFilaId();
      if (filaId && !fd.get("fila_id")) fd.set("fila_id", filaId);

      const resp = await fetch(form.action || window.location.pathname, {
        method: "POST",
        body: fd,
      });

      if (!resp.ok) {
        // tenta extrair mensagem
        let msg = "Falha ao salvar o atendimento.";
        try {
          const ct = resp.headers.get("content-type") || "";
          if (ct.includes("application/json")) {
            const j = await resp.json();
            msg = j?.message || j?.error || msg;
          } else {
            const t = await resp.text();
            if (t && t.length < 300) msg = t;
          }
        } catch (_) {}
        throw new Error(msg);
      }

      // ✅ remove da fila (se existir fila_id)
      if (filaId) {
        try {
          await fetch(`/atendimentos/api/fila/${encodeURIComponent(filaId)}`, { method: "DELETE" });
          try { localStorage.setItem(`fila:removida:${filaId}`, String(Date.now())); } catch (_) {}
        } catch (e) {
          console.warn("⚠️ Não foi possível remover da fila:", e);
        }
      }

      // ✅ redirect final
      window.location.href = "/atendimentos";
    } catch (err) {
      console.error(err);
      alert(err.message || "Erro ao finalizar atendimento.");
      if (btnSubmit) btnSubmit.disabled = false;
    }
  });
}
