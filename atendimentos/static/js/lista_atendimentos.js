(() => {
  "use strict";

  // ============================================================
  // FILA DE ATENDIMENTOS — CARDS + PAGINAÇÃO
  // ============================================================

  // ===================== Endpoints =====================
  const API = {
    filaList: "/atendimentos/api/fila",
    filaAdd: "/atendimentos/api/fila/add",
    filaUpdate: (id) => `/atendimentos/api/fila/${id}`,
    filaDelete: (id) => `/atendimentos/api/fila/${id}`,
    filaClear: "/atendimentos/api/fila/clear",
    filaSyncHoje: "/atendimentos/api/fila/sync_hoje",
    declaracao: (id) => `/atendimentos/declaracao/${id}`,
    profissionais: "/atendimentos/api/profissionais",
  };

  const STATUS = {
    ATENDENDO: "atendendo",
    FINALIZADO: "finalizado",
  };

  const PAGINACAO = {
    ITENS_POR_PAGINA: 12, // 3 colunas x 4 linhas
  };

  // ===================== Helpers =====================
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const DEBUG = true;
  const log = (...a) => DEBUG && console.log("🧪 FILA:", ...a);

  async function jfetch(url, opts = {}) {
    const res = await fetch(url, opts);
    const ctyp = (res.headers.get("content-type") || "").toLowerCase();
    const isJson = ctyp.includes("application/json");
    const data = isJson ? await res.json() : null;

    if (!res.ok) {
      const msg = (data && (data.error || data.message || data.erro)) || `HTTP ${res.status}`;
      throw new Error(msg);
    }
    return data;
  }

  function toast(msg, type = "info") {
    if (type === "error") {
      alert(msg);
      return;
    }
    console.log(`[${type}]`, msg);
  }

  function escapeHtml(s) {
    return String(s || "").replace(/[&<>"']/g, (m) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[m]));
  }

  function digits(s) {
    return String(s || "").replace(/\D+/g, "");
  }

  function normalizeText(s) {
    return String(s || "").trim().toLowerCase();
  }

  function debounce(fn, ms) {
    let timer = null;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), ms);
    };
  }

  function badgePrio(prio) {
    const p = normalizeText(prio);
    const labelMap = {
      verde: "Leve",
      amarelo: "Moderado",
      vermelho: "Urgente",
    };
    return `<span class="badge prio ${p}">${labelMap[p] || (p ? p[0].toUpperCase() + p.slice(1) : "—")}</span>`;
  }

  function comboCardHtml(item) {
    const combo = item?.combo || null;

    if (!combo || !combo.id) {
      return `
        <div class="combo-box">
          <div class="combo-meta">
            <strong>Sem combo</strong>
          </div>
        </div>
      `;
    }

    const nome = combo.combo_nome || combo.nome_plano || "Combo/Plano";
    const restantes = Number(combo.sessoes_restantes || 0);
    const zero = restantes <= 0;

    return `
      <div class="combo-box ${zero ? "is-zero" : ""}">
        <div class="combo-meta">
          <strong>${escapeHtml(nome)}</strong>
          <span>${zero ? "Sem saldo" : `${restantes} restante(s)`}</span>
        </div>
      </div>
    `;
  }

  function pacienteCardHtml(item) {
    const icon = item.from_agenda
      ? `<span class="from-agenda" title="Vindo da agenda">📅</span>`
      : "";

    return `
      <div class="fila-card-main" data-pid="${escapeHtml(item.paciente_id || "")}">
        <div style="display:flex;align-items:center;gap:8px;min-width:0;">
          ${icon}
          <strong>${escapeHtml(item.paciente_nome || "—")}</strong>
        </div>
        <span class="muted-mini">ID: ${escapeHtml(item.paciente_id || "—")}</span>
      </div>
    `;
  }

  // ===================== DOM =====================
  const cardsFila = $("#cardsFila");
  const emptyFila = $("#emptyFila");
  const qtdFilaEl = $("#qtdFila");

  const fBusca = $("#fBusca");
  const fProf = $("#fProf");
  const prioFilter = $("#prioFilter");

  const formAdd = $("#formAdd");
  const pacienteInput = $("#pacienteInput");
  const pacienteIdHidden = $("#pacienteId");
  const profInput = $("#profInput");
  const profissionalIdHidden = $("#profissionalId");
  const tipoSel = $("#tipoAtendimento");
  const prioGroup = $("#prioGroup");
  const obsEl = $("#obs");

  const btnImprimir = $("#btnImprimir");
  const btnLimparFila = $("#btnLimparFila");

  const filaPagination = $("#filaPagination");
  const filaPrev = $("#filaPrev");
  const filaNext = $("#filaNext");
  const filaPageInfo = $("#filaPageInfo");

  const pacDatalist = document.getElementById("listaPacientes");
  const profDatalist = document.getElementById("listaProfissionais");

  // ===================== Estado =====================
  let allItems = [];
  let filteredItems = [];
  let filterPrio = "";
  let paginaAtual = 1;

  let PAC_OPTS = [];
  const PROF_CACHE = new Map();

  // ============================================================
  // Captura opções do template (PACIENTES)
  // ============================================================
  if (pacDatalist) {
    PAC_OPTS = Array.from(pacDatalist.options).map(op => ({
      value: op.value || "",
      id: op.getAttribute("data-id") || ""
    }));
    pacDatalist.innerHTML = "";
    log("PAC_OPTS:", PAC_OPTS.length);
  }

  // ============================================================
  // Datalist inteligente
  // ============================================================
  function preencherDatalist(inputEl, datalistEl, sourceList, minLen = 3, limit = 30) {
    const term = (inputEl.value || "").trim().toLowerCase();

    if (term.length < minLen) {
      datalistEl.innerHTML = "";
      return 0;
    }

    const filtrados = sourceList
      .filter(op => (op.value || "").toLowerCase().includes(term))
      .slice(0, limit);

    datalistEl.innerHTML = "";
    for (const op of filtrados) {
      const el = document.createElement("option");
      el.value = op.value;
      if (op.id != null && op.id !== "") el.setAttribute("data-id", String(op.id));
      datalistEl.appendChild(el);
    }
    return filtrados.length;
  }

  function wakeDatalist(inputEl, datalistId) {
    try {
      inputEl.setAttribute("list", "");
      inputEl.offsetHeight;
      inputEl.setAttribute("list", datalistId);
    } catch (_) {}
  }

  function parseDatalistValue(inputEl, datalistSel) {
    const val = (inputEl.value || "").trim();
    const opts = $$(datalistSel + " option");
    let id = null;

    for (const op of opts) {
      if ((op.value || "").trim() === val) {
        const raw = op.getAttribute("data-id");
        if (raw != null && raw !== "") id = Number(raw);
        break;
      }
    }
    return { id, text: val };
  }

  // ============================================================
  // Paciente autocomplete
  // ============================================================
  pacienteInput?.addEventListener("input", () => {
    if (!pacDatalist) return;
    const shown = preencherDatalist(pacienteInput, pacDatalist, PAC_OPTS, 3, 30);
    if (shown > 0) wakeDatalist(pacienteInput, "listaPacientes");
  });

  pacienteInput?.addEventListener("change", () => {
    const parsed = parseDatalistValue(pacienteInput, "#listaPacientes");
    pacienteIdHidden.value = parsed.id ?? "";
    log("Paciente:", parsed);
  });

  // ============================================================
  // Profissional autocomplete
  // ============================================================
  let profReqSeq = 0;

  function clearProfSuggestions() {
    if (profDatalist) profDatalist.innerHTML = "";
    PROF_CACHE.clear();
  }

  function setProfSuggestions(items) {
    if (!profDatalist) return;

    profDatalist.innerHTML = "";
    PROF_CACHE.clear();

    for (const it of items) {
      const label = String(it.label || it.nome || "").trim();
      const id = it.id;

      if (!label || id == null) continue;

      const opt = document.createElement("option");
      opt.value = label;
      opt.setAttribute("data-id", String(id));
      profDatalist.appendChild(opt);

      PROF_CACHE.set(label.toLowerCase(), Number(id));
    }
  }

  async function fetchProfissionais(term) {
    const q = (term || "").trim();
    if (q.length < 3) return [];

    const mySeq = ++profReqSeq;
    const url = `${API.profissionais}?q=${encodeURIComponent(q)}`;
    const data = await jfetch(url);

    if (mySeq !== profReqSeq) return [];
    return Array.isArray(data?.items) ? data.items : [];
  }

  const onProfInput = debounce(async () => {
    if (!profInput || !profDatalist) return;

    const term = (profInput.value || "").trim();
    if (term.length < 3) {
      clearProfSuggestions();
      profissionalIdHidden.value = "";
      return;
    }

    try {
      const items = await fetchProfissionais(term);
      setProfSuggestions(items);

      if (items.length > 0) wakeDatalist(profInput, "listaProfissionais");
      log("Profissionais:", items.length);
    } catch (e) {
      console.warn("Falha ao buscar profissionais:", e.message);
      clearProfSuggestions();
    }
  }, 220);

  profInput?.addEventListener("input", () => {
    profissionalIdHidden.value = "";
    onProfInput();
  });

  profInput?.addEventListener("focus", () => {
    const term = (profInput.value || "").trim();
    if (term.length >= 3) onProfInput();
  });

  profInput?.addEventListener("change", () => {
    const val = (profInput.value || "").trim();
    const lower = val.toLowerCase();

    let id = null;
    const parsed = parseDatalistValue(profInput, "#listaProfissionais");
    if (parsed.id) id = parsed.id;
    if (!id && PROF_CACHE.has(lower)) id = PROF_CACHE.get(lower);

    profissionalIdHidden.value = id ? String(id) : "";
    log("Profissional:", { text: val, id });
  });

  // ============================================================
  // Filtros
  // ============================================================
  function applyFilters(list) {
    const q = normalizeText(fBusca?.value || "");
    const profId = (fProf?.value || "").trim();
    const prio = normalizeText(filterPrio);

    return list.filter(it => {
      if (profId && String(it.profissional_id) !== profId) return false;
      if (prio && normalizeText(it.prioridade) !== prio) return false;

      if (q) {
        const comboNome = it?.combo?.combo_nome || it?.combo?.nome_plano || "";
        const comboRestantes = String(it?.combo?.sessoes_restantes ?? "");
        const hay = [
          it.paciente_nome,
          it.profissional_nome,
          it.obs,
          comboNome,
          comboRestantes,
          it.tipo
        ].map(normalizeText).join(" ");

        if (!hay.includes(q)) return false;
      }

      return true;
    });
  }

  function updateCounter(total) {
    if (qtdFilaEl) qtdFilaEl.textContent = String(total);
  }

  // ============================================================
  // Paginação
  // ============================================================
  function totalPaginas() {
    return Math.max(1, Math.ceil(filteredItems.length / PAGINACAO.ITENS_POR_PAGINA));
  }

  function getPaginaItems() {
    const ini = (paginaAtual - 1) * PAGINACAO.ITENS_POR_PAGINA;
    const fim = ini + PAGINACAO.ITENS_POR_PAGINA;
    return filteredItems.slice(ini, fim);
  }

  function updatePaginationUI() {
    const total = totalPaginas();

    if (filaPageInfo) {
      filaPageInfo.textContent = `Página ${paginaAtual} de ${total}`;
    }

    if (filaPrev) filaPrev.disabled = paginaAtual <= 1;
    if (filaNext) filaNext.disabled = paginaAtual >= total;

    if (filaPagination) {
      filaPagination.hidden = filteredItems.length === 0 || total <= 1;
    }
  }

  function resetPaginaSePreciso() {
    const total = totalPaginas();
    if (paginaAtual > total) paginaAtual = total;
    if (paginaAtual < 1) paginaAtual = 1;
  }

  // ============================================================
  // Render dos cards
  // ============================================================
  function cardHtml(it) {
    const id = it.id;
    const hora = escapeHtml(it.hora || "");
    const tipo = escapeHtml(it.tipo || "—");
    const obs = escapeHtml(it.obs || "—");
    const status = normalizeText(it.status || (it.em_atendimento ? STATUS.ATENDENDO : ""));

    const combo = it?.combo || null;
    const temCombo = !!(combo && combo.id);
    const comboRestantes = Number(combo?.sessoes_restantes || 0);
    const semSaldo = temCombo && comboRestantes <= 0;

    const menuHtml = `
      <div class="menu">
        <button class="btn icon only" data-menu-toggle aria-haspopup="true" aria-expanded="false" title="Opções" type="button">
          <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M3 6h18M3 12h18M3 18h18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
        </button>

        <div class="menu-pop" hidden role="menu">
          <button class="menu-item" data-acao="atender" role="menuitem">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm0 2c-3 0-8 1.5-8 4v2h16v-2c0-2.5-5-4-8-4Z" fill="currentColor"/>
            </svg>
            <span>Atender</span>
          </button>

          <button class="menu-item" data-acao="editar" role="menuitem">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path d="M3 17.25V21h3.75l11-11.04-3.75-3.75L3 17.25ZM20.71 7.04a1 1 0 0 0 0-1.42l-2.34-2.34a1 1 0 0 0-1.42 0l-1.83 1.83 3.75 3.75 1.84-1.82Z" fill="currentColor"/>
            </svg>
            <span>Editar…</span>
          </button>

          <a class="menu-item" data-acao="declaracao" target="_blank" rel="noopener" role="menuitem">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path d="M13 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-7-6Z" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
              <polyline points="13 3 13 9 19 9" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <span>Gerar declaração</span>
          </a>

          <button class="menu-item" data-acao="falta" role="menuitem">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" fill="none"/>
              <line x1="8" y1="12" x2="16" y2="12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
            <span>Marcar falta</span>
          </button>

          <button class="menu-item danger" data-acao="remover" role="menuitem">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path d="M3 6h18M8 6V4h8v2m1 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6h14Z"
                    stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <span>Remover</span>
          </button>
        </div>
      </div>
    `;

    return `
      <article class="fila-card ${semSaldo ? "is-sem-saldo" : ""}"
               data-id="${id}"
               data-prof="${escapeHtml(it.profissional_id || "")}"
               data-prio="${escapeHtml(it.prioridade || "")}"
               data-status="${escapeHtml(status)}"
               data-tem-combo="${temCombo ? 1 : 0}"
               data-combo-restantes="${comboRestantes}">
        <header class="fila-card-head">
          <div class="fila-card-time">
            <span class="fila-card-label">Hora</span>
            <strong>${hora}</strong>
          </div>

          <div class="fila-card-top-actions">
            ${it.from_agenda ? `<span class="from-agenda" title="Vindo da agenda">📅</span>` : ""}
            ${badgePrio(it.prioridade)}
          </div>
        </header>

        <div class="fila-card-body">
          <section class="fila-card-group">
            <span class="fila-card-mini-label">Paciente</span>
            ${pacienteCardHtml(it)}
          </section>

          <section class="fila-card-group">
            <span class="fila-card-mini-label">Combo</span>
            ${comboCardHtml(it)}
          </section>

          <section class="fila-card-group">
            <span class="fila-card-mini-label">Profissional</span>
            <div class="fila-card-main">
              <strong>${escapeHtml(it.profissional_nome || "—")}</strong>
            </div>
          </section>

          <section class="fila-card-inline">
            <div class="fila-card-group">
              <span class="fila-card-mini-label">Tipo</span>
              <div class="fila-card-main">
                <strong>${tipo}</strong>
              </div>
            </div>

            <div class="fila-card-group">
              <span class="fila-card-mini-label">Observações</span>
              <div class="fila-card-main">
                <span class="obs-text">${obs}</span>
              </div>
            </div>
          </section>
        </div>

        <footer class="fila-card-actions">
          <button class="btn atender" title="Atender" data-acao="atender" aria-label="Atender" type="button">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm0 2c-3 0-8 1.5-8 4v2h16v-2c0-2.5-5-4-8-4Z" fill="currentColor"/>
            </svg>
          </button>

          <button class="btn remover" title="Excluir" data-acao="remover" aria-label="Excluir" type="button">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path d="M3 6h18M8 6V4h8v2m1 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6h14Z"
                    stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>

          ${menuHtml}
        </footer>
      </article>
    `;
  }

  function renderFila(itemsRaw) {
    filteredItems = applyFilters(itemsRaw);
    paginaAtual = 1;
    renderPaginaAtual();
  }

  function renderPaginaAtual() {
    resetPaginaSePreciso();
    const pageItems = getPaginaItems();
    updateCounter(filteredItems.length);
    updatePaginationUI();

    if (!cardsFila) return;

    if (!pageItems.length) {
      cardsFila.innerHTML = "";
      if (emptyFila) emptyFila.hidden = false;
      return;
    }

    if (emptyFila) emptyFila.hidden = true;
    cardsFila.innerHTML = pageItems.map(cardHtml).join("");
  }

  async function carregarFila() {
    const data = await jfetch(API.filaList);
    allItems = Array.isArray(data) ? data : [];
    renderFila(allItems);
  }

  async function syncHoje() {
    try {
      await jfetch(API.filaSyncHoje, { method: "POST" });
      await carregarFila();
    } catch (e) {
      console.warn("syncHoje falhou:", e.message);
    }
  }

  // ============================================================
  // Eventos de filtro / paginação
  // ============================================================
  fBusca?.addEventListener("input", () => renderFila(allItems));
  fProf?.addEventListener("change", () => renderFila(allItems));

  prioFilter?.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".pf-pill");
    if (!btn) return;

    $$(".pf-pill", prioFilter).forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    filterPrio = normalizeText(btn.dataset.prio || "");
    renderFila(allItems);
  });

  filaPrev?.addEventListener("click", () => {
    if (paginaAtual > 1) {
      paginaAtual--;
      renderPaginaAtual();
      cardsFila?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });

  filaNext?.addEventListener("click", () => {
    if (paginaAtual < totalPaginas()) {
      paginaAtual++;
      renderPaginaAtual();
      cardsFila?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });

  // ============================================================
  // Dropdown menu portal
  // ============================================================
  const __menuState = new WeakMap();
  let __justOpenedUntil = 0;

  function closeAllMenus(except = null) {
    document.querySelectorAll(".menu-pop:not([hidden])").forEach(pop => {
      if (pop === except) return;
      const st = __menuState.get(pop);

      if (st && st.anchor) {
        pop.classList.remove("is-portal");
        pop.hidden = true;
        pop.style.left = pop.style.top = pop.style.minWidth = "";
        st.anchor.appendChild(pop);
        __menuState.delete(pop);

        const btn = st.anchor.querySelector("[data-menu-toggle]");
        if (btn) btn.setAttribute("aria-expanded", "false");
      } else {
        pop.hidden = true;
        const btn = pop.closest(".menu")?.querySelector("[data-menu-toggle]");
        if (btn) btn.setAttribute("aria-expanded", "false");
      }
    });
  }

  function openWithPortal(pop, btn) {
    const anchor = btn.closest(".menu");
    __menuState.set(pop, { anchor });
    pop.hidden = false;
    pop.classList.add("is-portal");
    pop.style.minWidth = "210px";
    document.body.appendChild(pop);

    const br = btn.getBoundingClientRect();
    const pr = pop.getBoundingClientRect();

    const left = Math.max(8, Math.min(br.right - pr.width, window.innerWidth - pr.width - 8));
    const top = Math.min(br.bottom + 8, window.innerHeight - pr.height - 8);

    pop.style.left = `${left}px`;
    pop.style.top = `${top}px`;
    btn.setAttribute("aria-expanded", "true");

    const card = btn.closest(".fila-card[data-id]");
    const id = card ? Number(card.dataset.id) : null;
    const decl = pop.querySelector('[data-acao="declaracao"]');
    if (decl && id) decl.setAttribute("href", API.declaracao(id));

    (pop.querySelector(".menu-item, a.menu-item") || pop).focus?.();
    __justOpenedUntil = performance.now() + 120;
  }

  function toggleMenu(pop, btn) {
    const willOpen = pop.hidden;
    closeAllMenus(pop);
    if (willOpen) openWithPortal(pop, btn);
    else closeAllMenus();
  }

  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-menu-toggle]");
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();

    const pop = btn.closest(".menu")?.querySelector(".menu-pop");
    if (!pop) return;
    toggleMenu(pop, btn);
  });

  document.addEventListener("click", () => {
    if (performance.now() < __justOpenedUntil) return;
    closeAllMenus();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeAllMenus();
  });

  document.addEventListener("click", (e) => {
    if (e.target.closest(".menu-pop")) e.stopPropagation();
  }, true);

  // ============================================================
  // Ações dos cards
  // ============================================================
  cardsFila?.addEventListener("click", async (e) => {
    const ac = e.target.closest("[data-acao]");
    if (!ac) return;

    closeAllMenus();

    const card = ac.closest(".fila-card[data-id]");
    const id = card ? Number(card.dataset.id) : null;
    if (!id) return;

    const acao = ac.dataset.acao;

    if (acao === "atender") {
      try {
        const pid = card.querySelector("[data-pid]")?.dataset.pid || "";
        const ptxt = card.querySelector("[data-pid] strong")?.textContent.trim() || "";

        if (!pid) {
          alert("Paciente não identificado para este atendimento.");
          return;
        }

        try {
          await fetch(API.filaUpdate(id), {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status: STATUS.ATENDENDO })
          });
          card.setAttribute("data-status", STATUS.ATENDENDO);
        } catch (err) {
          console.warn("Não foi possível marcar como 'atendendo':", err?.message);
        }

        const url =
          `/atendimentos/registrar?fila_id=${encodeURIComponent(id)}` +
          `&paciente_id=${encodeURIComponent(pid)}` +
          `&paciente_nome=${encodeURIComponent(ptxt)}`;

        window.location.href = url;
      } catch (err) {
        console.error("Erro ao redirecionar:", err);
        alert("Não foi possível iniciar o atendimento.");
      }
      return;
    }

    if (acao === "editar") {
      alert("⚙️ Edição ainda não implementada.");
      return;
    }

    if (acao === "falta") {
      try {
        await fetch(API.filaUpdate(id), {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prioridade: "amarelo", obs: "FALTA" })
        });
        await carregarFila();
      } catch {
        alert("Falha ao marcar falta.");
      }
      return;
    }

    if (acao === "remover") {
      if (!confirm("Remover este item da fila?")) return;
      try {
        await fetch(API.filaDelete(id), { method: "DELETE" });
        await carregarFila();
      } catch {
        alert("Falha ao remover.");
      }
    }
  });

  // ============================================================
  // Adicionar manualmente
  // ============================================================
  formAdd?.addEventListener("submit", async (ev) => {
    ev.preventDefault();

    const pacId = (pacienteIdHidden.value || "").trim();
    let paciente_id = pacId ? Number(pacId) : null;
    let paciente_texto = null;

    if (!paciente_id) {
      const parsed = parseDatalistValue(pacienteInput, "#listaPacientes");
      paciente_id = parsed.id ?? null;
      paciente_texto = parsed.id ? null : parsed.text;
    }

    const profId = (profissionalIdHidden.value || "").trim();
    let profissional_id = profId ? Number(profId) : null;

    if (!profissional_id) {
      const label = (profInput.value || "").trim().toLowerCase();
      if (PROF_CACHE.has(label)) profissional_id = PROF_CACHE.get(label);

      if (!profissional_id) {
        toast("Selecione um profissional válido (use a lista).", "error");
        return;
      }
    }

    const tipo = (tipoSel?.value || "Individual").trim();
    const prioSel = prioGroup?.querySelector('input[name="prioridade"]:checked');
    const prioridade = (prioSel?.value || "verde").trim();
    const obs = (obsEl?.value || "").trim();

    try {
      await jfetch(API.filaAdd, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          paciente_id,
          paciente_texto,
          profissional_id,
          tipo,
          prioridade,
          obs
        })
      });

      pacienteInput.value = "";
      pacienteIdHidden.value = "";
      profInput.value = "";
      profissionalIdHidden.value = "";
      obsEl.value = "";
      clearProfSuggestions();

      await carregarFila();
    } catch (e) {
      toast(e.message || "Falha ao adicionar.", "error");
    }
  });

  // ============================================================
  // Ações do topo
  // ============================================================
  btnImprimir?.addEventListener("click", () => window.print());

  btnLimparFila?.addEventListener("click", async () => {
    if (!confirm("Limpar completamente a fila?")) return;
    try {
      await jfetch(API.filaClear, { method: "POST" });
      await carregarFila();
    } catch (e) {
      toast(e.message || "Falha ao limpar a fila.", "error");
    }
  });

  // ============================================================
  // Atalhos
  // ============================================================
  document.addEventListener("keydown", (ev) => {
    if (ev.ctrlKey && ev.key.toLowerCase() === "p") {
      ev.preventDefault();
      window.print();
    }
  });

  // ============================================================
  // Sync cross-tab
  // ============================================================
  window.addEventListener("storage", async (ev) => {
    if (!ev.key || !ev.key.startsWith("fila:removida:")) return;
    await carregarFila();
  });

  // ============================================================
  // Boot
  // ============================================================
  (async function boot() {
    log("Sanity DOM:", {
      cardsFila: !!cardsFila,
      filaPrev: !!filaPrev,
      filaNext: !!filaNext,
      filaPageInfo: !!filaPageInfo,
      profInput: !!profInput,
      pacienteInput: !!pacienteInput,
    });

    await syncHoje();

    setInterval(async () => {
      await syncHoje();
    }, 60_000);
  })();
})();