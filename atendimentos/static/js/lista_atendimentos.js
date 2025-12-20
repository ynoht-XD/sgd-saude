// atendimentos/static/js/lista_atendimentos.js
(() => {
  // ============================================================
  //  FILA DE ATENDIMENTOS — Lista e Ações
  //  ✅ Datalist “inteligente” (3+ chars) para Paciente e Profissional
  //  ✅ PACIENTES: base no template (1x) e filtra em memória
  //  ✅ PROFISSIONAIS: busca no backend com ?q= (3+ chars) + debounce
  //  ✅ Workaround Chrome/Edge para datalist dinâmico
  // ============================================================

  // ===================== Endpoints =====================
  const API = {
    filaList:     "/atendimentos/api/fila",
    filaAdd:      "/atendimentos/api/fila/add",
    filaUpdate:   (id) => `/atendimentos/api/fila/${id}`,
    filaDelete:   (id) => `/atendimentos/api/fila/${id}`,
    filaClear:    "/atendimentos/api/fila/clear",
    filaSyncHoje: "/atendimentos/api/fila/sync_hoje",
    declaracao:   (id) => `/atendimentos/declaracao/${id}`,

    // ✅ autocomplete profissionais: exige ?q= (>=3 chars)
    profissionais: "/atendimentos/api/profissionais",
  };

  // ===================== Status semânticos =====================
  const STATUS = { ATENDENDO: "atendendo" };

  // ===================== Helpers básicos =====================
  const $  = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const DEBUG = true;
  const log = (...a) => DEBUG && console.log("🧪 FILA:", ...a);

  async function jfetch(url, opts = {}) {
    const res  = await fetch(url, opts);
    const ctyp = (res.headers.get("content-type") || "").toLowerCase();
    const js   = ctyp.includes("application/json");
    const data = js ? await res.json() : null;

    if (!res.ok) {
      const msg = (data && (data.error || data.message)) || `HTTP ${res.status}`;
      throw new Error(msg);
    }
    return data;
  }

  function toast(msg, type = "info") {
    if (type === "error") alert(msg);
  }

  function escapeHtml(s) {
    return (s || "").replace(/[&<>"']/g, (m) => ({
      "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
    }[m]));
  }

  function badgePrio(prio) {
    const p = (prio || "").toLowerCase();
    const label = p ? p.charAt(0).toUpperCase() + p.slice(1) : "";
    return `<span class="badge prio ${p}">${label}</span>`;
  }

  function pacienteCellHtml(item) {
    const icon = item.from_agenda
      ? `<span class="from-agenda" title="Vindo da agenda">📅</span>`
      : `<span class="from-agenda" hidden>📅</span>`;
    return `${icon}${escapeHtml(item.paciente_nome || "—")}`;
  }

  // ===================== DOM refs =====================
  const tbodyFila   = $("#tbodyFila");
  const emptyFila   = $("#emptyFila");
  const qtdFilaEl   = $("#qtdFila");

  const fBusca      = $("#fBusca");
  const fProf       = $("#fProf");
  const prioFilter  = $("#prioFilter");

  const formAdd               = $("#formAdd");
  const pacienteInput         = $("#pacienteInput");
  const pacienteIdHidden      = $("#pacienteId");
  const profInput             = $("#profInput");
  const profissionalIdHidden  = $("#profissionalId");
  const tipoSel               = $("#tipoAtendimento");
  const prioGroup             = $("#prioGroup");
  const obsEl                 = $("#obs");

  const btnImprimir   = $("#btnImprimir");
  const btnLimparFila = $("#btnLimparFila");

  const pacDatalist  = document.getElementById("listaPacientes");
  const profDatalist = document.getElementById("listaProfissionais");

  // ===================== Opções em memória =====================
  let PAC_OPTS  = [];

  // cache (labelLower -> id) para fallback (profissionais)
  const PROF_CACHE = new Map();

  // ============================================================
  // Captura opções do template (PACIENTES) e limpa datalist
  // ============================================================
  if (pacDatalist) {
    PAC_OPTS = Array.from(pacDatalist.options).map(op => ({
      value: op.value || "",
      id: op.getAttribute("data-id") || ""
    }));
    pacDatalist.innerHTML = "";
    log("PAC_OPTS (template):", PAC_OPTS.length);
  }

  // ============================================================
  // Datalist “inteligente” (3+ chars)
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
      inputEl.offsetHeight; // força reflow
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
  // Paciente autocomplete (template -> memória)
  // ============================================================
  pacienteInput?.addEventListener("input", () => {
    if (!pacDatalist) return;
    const shown = preencherDatalist(pacienteInput, pacDatalist, PAC_OPTS, 3, 30);
    if (shown > 0) wakeDatalist(pacienteInput, "listaPacientes");
  });

  pacienteInput?.addEventListener("change", () => {
    const parsed = parseDatalistValue(pacienteInput, "#listaPacientes");
    pacienteIdHidden.value = parsed.id ?? "";
    log("Paciente change:", { text: parsed.text, id: parsed.id, hidden: pacienteIdHidden.value });
  });

  // ============================================================
  // ✅ Profissional autocomplete (API por termo: ?q=)
  // ============================================================
  let profReqSeq = 0;
  let profDebounceTimer = null;

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

    // ignora resposta “antiga” (usuário digitou mais depois)
    if (mySeq !== profReqSeq) return [];

    return Array.isArray(data?.items) ? data.items : [];
  }

  function debounce(fn, ms) {
    return (...args) => {
      clearTimeout(profDebounceTimer);
      profDebounceTimer = setTimeout(() => fn(...args), ms);
    };
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

      log("Prof sugestões:", { term, items: items.length });
    } catch (e) {
      console.warn("Falha ao buscar profissionais:", e.message);
      clearProfSuggestions();
    }
  }, 220);

  profInput?.addEventListener("input", () => {
    profissionalIdHidden.value = ""; // digitou => invalida seleção
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

    // 1) tenta achar option no DOM
    const parsed = parseDatalistValue(profInput, "#listaProfissionais");
    if (parsed.id) id = parsed.id;

    // 2) fallback: cache
    if (!id && PROF_CACHE.has(lower)) id = PROF_CACHE.get(lower);

    profissionalIdHidden.value = id ? String(id) : "";

    log("Prof change:", { text: val, id, hidden: profissionalIdHidden.value });
  });

  // ===================== Estado / Render / Filtros =====================
  let allItems = [];
  let filterPrio = "";

  function renderFila(itemsRaw) {
    const items = applyFilters(itemsRaw);

    if (!items.length) {
      tbodyFila.innerHTML = "";
      if (emptyFila) emptyFila.hidden = false;
      if (qtdFilaEl) qtdFilaEl.textContent = "0";
      return;
    }

    if (emptyFila) emptyFila.hidden = true;
    if (qtdFilaEl) qtdFilaEl.textContent = String(items.length);

    const rows = items.map((it) => {
      const id      = it.id;
      const hora    = escapeHtml(it.hora || "");
      const prof    = escapeHtml(it.profissional_nome || "—");
      const tipo    = escapeHtml(it.tipo || "—");
      const obs     = escapeHtml(it.obs || "—");
      const status  = (it.status || (it.em_atendimento ? STATUS.ATENDENDO : "") || "").toLowerCase();

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

      const quickActionsHtml = `
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
      `;

      return `
        <tr data-id="${id}"
            data-prof="${it.profissional_id}"
            data-prio="${it.prioridade}"
            data-status="${status}">
          <td>${hora}</td>
          <td data-pid="${it.paciente_id}">${pacienteCellHtml(it)}</td>
          <td>${prof}</td>
          <td>${tipo}</td>
          <td>${badgePrio(it.prioridade)}</td>
          <td>${obs}</td>
          <td class="row-actions">
            ${quickActionsHtml}
            ${menuHtml}
          </td>
        </tr>
      `;
    }).join("");

    tbodyFila.innerHTML = rows;
  }

  function applyFilters(list) {
    const q      = (fBusca?.value || "").trim().toLowerCase();
    const profId = (fProf?.value || "").trim();
    const prio   = filterPrio;

    return list.filter(it => {
      if (profId && String(it.profissional_id) !== profId) return false;
      if (prio && String(it.prioridade || "").toLowerCase() !== prio) return false;

      if (q) {
        const hay = `${it.paciente_nome || ""} ${it.profissional_nome || ""} ${it.obs || ""}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
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

  fBusca?.addEventListener("input", () => renderFila(allItems));
  fProf?.addEventListener("change", () => renderFila(allItems));
  prioFilter?.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".pf-pill");
    if (!btn) return;
    $$(".pf-pill", prioFilter).forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    filterPrio = (btn.dataset.prio || "").toLowerCase();
    renderFila(allItems);
  });

  // ===================== Dropdown (portal robusto) =====================
  const __menuState = new WeakMap();
  let __justOpenedUntil = 0;

  function closeAllMenus(except = null){
    document.querySelectorAll(".menu-pop:not([hidden])").forEach(pop=>{
      if(pop === except) return;
      const st = __menuState.get(pop);
      if(st && st.anchor){
        pop.classList.remove("is-portal");
        pop.hidden = true;
        pop.style.left = pop.style.top = pop.style.minWidth = "";
        st.anchor.appendChild(pop);
        __menuState.delete(pop);
        const btn = st.anchor.querySelector("[data-menu-toggle]");
        if(btn) btn.setAttribute("aria-expanded","false");
      }else{
        pop.hidden = true;
        const btn = pop.closest(".menu")?.querySelector("[data-menu-toggle]");
        if(btn) btn.setAttribute("aria-expanded","false");
      }
    });
  }

  function openWithPortal(pop, btn){
    const anchor = btn.closest(".menu");
    __menuState.set(pop, { anchor });
    pop.hidden = false;
    pop.classList.add("is-portal");
    pop.style.minWidth = "180px";
    document.body.appendChild(pop);

    const br = btn.getBoundingClientRect();
    const pr = pop.getBoundingClientRect();

    const left = Math.max(8, Math.min(br.right - pr.width, window.innerWidth - pr.width - 8));
    const top  = Math.min(br.bottom + 8, window.innerHeight - pr.height - 8);

    pop.style.left = `${left}px`;
    pop.style.top  = `${top}px`;
    btn.setAttribute("aria-expanded","true");

    const tr = btn.closest("tr[data-id]");
    const id = tr ? Number(tr.dataset.id) : null;
    const decl = pop.querySelector('[data-acao="declaracao"]');
    if (decl && id) decl.setAttribute("href", API.declaracao(id));

    (pop.querySelector(".menu-item, a.menu-item") || pop).focus?.();
    __justOpenedUntil = performance.now() + 120;
  }

  function toggleMenu(pop, btn){
    const willOpen = pop.hidden;
    closeAllMenus(pop);
    if (willOpen) openWithPortal(pop, btn);
    else closeAllMenus();
  }

  document.addEventListener("click", (e)=>{
    const btn = e.target.closest("[data-menu-toggle]");
    if(!btn) return;
    e.preventDefault();
    e.stopPropagation();
    const pop = btn.closest(".menu")?.querySelector(".menu-pop");
    if(!pop) return;
    toggleMenu(pop, btn);
  });

  document.addEventListener("click", ()=>{
    if(performance.now() < __justOpenedUntil) return;
    closeAllMenus();
  });

  document.addEventListener("keydown", (e)=>{
    if(e.key === "Escape") closeAllMenus();
  });

  document.addEventListener("click", (e)=>{
    if(e.target.closest(".menu-pop")) e.stopPropagation();
  }, true);

  // ===================== Ações (delegation no tbody) =====================
  const $tbody = document.getElementById("tbodyFila");

  $tbody?.addEventListener("click", async (e)=>{
    const ac = e.target.closest("[data-acao]");
    if(!ac) return;

    closeAllMenus();

    const tr = ac.closest("tr[data-id]");
    const id = tr ? Number(tr.dataset.id) : null;
    if(!id) return;

    const acao = ac.dataset.acao;

    if(acao === "atender"){
      try {
        const pid  = tr.querySelector("[data-pid]")?.dataset.pid || "";
        const ptxt = tr.querySelector("[data-pid]")?.textContent.trim() || "";

        if (!pid) {
          alert("Paciente não identificado para este atendimento.");
          return;
        }

        try {
          await fetch(API.filaUpdate(id),{
            method:"PATCH",
            headers:{ "Content-Type":"application/json" },
            body: JSON.stringify({ status: STATUS.ATENDENDO })
          });
          tr.setAttribute("data-status", STATUS.ATENDENDO);
        } catch(err) {
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

    if(acao === "editar"){
      alert("⚙️ Edição ainda não implementada.");
      return;
    }

    if(acao === "falta"){
      try{
        await fetch(API.filaUpdate(id),{
          method:"PATCH",
          headers:{ "Content-Type":"application/json" },
          body:JSON.stringify({ prioridade:"amarelo", obs:"FALTA" })
        });
        await carregarFila();
      }catch{
        alert("Falha ao marcar falta.");
      }
      return;
    }

    if(acao === "remover"){
      if(!confirm("Remover este item da fila?")) return;
      try{
        await fetch(API.filaDelete(id),{ method:"DELETE" });
        await carregarFila();
      }catch{
        alert("Falha ao remover.");
      }
      return;
    }
  });

  // ===================== Adicionar manualmente =====================
  formAdd?.addEventListener("submit", async (ev) => {
    ev.preventDefault();

    // ----- paciente
    const pacId = (pacienteIdHidden.value || "").trim();
    let paciente_id = pacId ? Number(pacId) : null;
    let paciente_texto = null;

    if (!paciente_id) {
      const parsed = parseDatalistValue(pacienteInput, "#listaPacientes");
      paciente_id    = parsed.id ?? null;
      paciente_texto = parsed.id ? null : parsed.text;
    }

    // ----- profissional
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

  // ===================== Top actions =====================
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

  // ===================== Sincronização cross-aba (opcional) =====================
  window.addEventListener('storage', async (ev) => {
    if (!ev.key || !ev.key.startsWith('fila:removida:')) return;
    await carregarFila();
  });

  // ===================== Boot =====================
  (async function boot() {
    log("Sanity DOM:", {
      profInput: !!profInput,
      profissionalIdHidden: !!profissionalIdHidden,
      profDatalist: !!profDatalist,
      pacInput: !!pacienteInput,
      pacHidden: !!pacienteIdHidden,
      pacDatalist: !!pacDatalist,
    });

    // sincroniza fila
    await syncHoje();

    setInterval(async () => {
      await syncHoje();
    }, 60_000);
  })();
})();
