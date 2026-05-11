(() => {
  "use strict";

  const API = {
    filaList: "/atendimentos/api/fila",
    filaAdd: "/atendimentos/api/fila/add",
    filaUpdate: (id) => `/atendimentos/api/fila/${id}`,
    filaDelete: (id) => `/atendimentos/api/fila/${id}`,
    filaClear: "/atendimentos/api/fila/clear",
    filaSyncHoje: "/atendimentos/api/fila/sync_hoje",
    pacientes: "/atendimentos/api/pacientes",
    profissionais: "/atendimentos/api/profissionais",
    chamarTv: "/atendimentos/chama-na-tela/chamar",
  };

  const DEBUG = true;
  const PER_PAGE = 12;
  const MIN_SEARCH = 3;

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const log = (...args) => DEBUG && console.log("🧾 LISTA_ATENDIMENTOS:", ...args);

  const dom = {
    cards: $("#cardsFila"),
    empty: $("#emptyFila"),
    qtd: $("#qtdFila"),

    form: $("#formAdd"),
    pacienteInput: $("#pacienteInput"),
    pacienteId: $("#pacienteId"),
    pacienteList: $("#listaPacientes"),

    profInput: $("#profInput"),
    profissionalId: $("#profissionalId"),
    profList: $("#listaProfissionais"),

    tipo: $("#tipoAtendimento"),
    prioGroup: $("#prioGroup"),
    obs: $("#obs"),

    busca: $("#fBusca"),
    profFiltro: $("#fProf"),
    prioFilter: $("#prioFilter"),

    btnImprimir: $("#btnImprimir"),
    btnLimpar: $("#btnLimparFila"),

    pagination: $("#filaPagination"),
    prev: $("#filaPrev"),
    next: $("#filaNext"),
    pageInfo: $("#filaPageInfo"),
  };

  let allItems = [];
  let filteredItems = [];
  let currentPage = 1;
  let filtroPrio = "";

  let pacReqSeq = 0;
  let profReqSeq = 0;

  const PAC_CACHE = new Map();
  const PROF_CACHE = new Map();

  function csrfHeaders(extra = {}) {
    const token =
      document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") ||
      document.querySelector('input[name="csrf_token"]')?.value ||
      "";

    return token ? { ...extra, "X-CSRFToken": token } : extra;
  }

  async function jfetch(url, opts = {}) {
    const headers = csrfHeaders(opts.headers || {});

    const res = await fetch(url, {
      credentials: "same-origin",
      ...opts,
      headers,
    });

    const contentType = (res.headers.get("content-type") || "").toLowerCase();
    const data = contentType.includes("application/json") ? await res.json() : null;

    if (!res.ok || data?.ok === false) {
      throw new Error(data?.error || data?.erro || data?.message || `Erro HTTP ${res.status}`);
    }

    return data;
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (m) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[m]));
  }

  function normalizeText(value) {
    return String(value ?? "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .trim()
      .toLowerCase();
  }

  function safeId(value) {
    const s = String(value ?? "").trim();
    return /^\d+$/.test(s) ? s : "";
  }

  function debounce(fn, delay = 300) {
    let timer = null;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), delay);
    };
  }

  function getPayloadList(data) {
    if (Array.isArray(data)) return data;
    if (Array.isArray(data?.items)) return data.items;
    if (Array.isArray(data?.dados)) return data.dados;
    if (Array.isArray(data?.results)) return data.results;
    if (Array.isArray(data?.fila)) return data.fila;
    return [];
  }

  function toast(msg, type = "info") {
    if (type === "error") {
      alert(msg);
      return;
    }

    console.log(`[${type}] ${msg}`);
  }

  function isFromAgenda(item) {
    return (
      item?.from_agenda === true ||
      item?.from_agenda === 1 ||
      item?.origem === "agenda" ||
      !!item?.agenda_id
    );
  }

  function itemKey(item) {
    if (!item) return "";
    if (item.id) return `id:${item.id}`;
    if (item.agenda_id) return `agenda:${item.agenda_id}`;
    return "";
  }

  function removedStorageKey(item) {
    const key = itemKey(item);
    return key ? `fila_removida:${key}` : "";
  }

  function rememberRemoved(item) {
    const k = removedStorageKey(item);
    if (k) localStorage.setItem(k, String(Date.now()));
  }

  function wasLocallyRemoved(item) {
    const k = removedStorageKey(item);
    if (!k) return false;

    const raw = localStorage.getItem(k);
    if (!raw) return false;

    const age = Date.now() - Number(raw || 0);
    const maxAge = 12 * 60 * 60 * 1000;

    if (age > maxAge) {
      localStorage.removeItem(k);
      return false;
    }

    return true;
  }

  function isOpenItem(item) {
    const status = normalizeText(item?.status || "");

    return ![
      "finalizado",
      "atendido",
      "concluido",
      "concluído",
      "removido",
      "cancelado",
      "excluido",
      "excluído",
    ].includes(status);
  }

  function priorityLabel(prio) {
    const p = normalizeText(prio);

    return {
      verde: "Leve",
      amarelo: "Moderado",
      vermelho: "Urgente",
      laranja: "Alta",
    }[p] || (p ? p[0].toUpperCase() + p.slice(1) : "—");
  }

  function badgePrio(prio) {
    const p = normalizeText(prio || "verde");
    return `<span class="badge prio ${escapeHtml(p)}">${escapeHtml(priorityLabel(p))}</span>`;
  }

  function comboHtml(item) {
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

    const nome = combo.combo_nome || combo.nome_plano || combo.nome || "Combo/Plano";
    const restantes = Number(combo.sessoes_restantes ?? combo.restantes ?? 0);
    const zero = restantes <= 0;

    return `
      <div class="combo-box ${zero ? "is-zero" : ""}">
        <div class="combo-meta">
          <strong>${escapeHtml(nome)}</strong>
          <span>${zero ? "Sem saldo" : `${escapeHtml(restantes)} restante(s)`}</span>
        </div>
      </div>
    `;
  }

  function actionButtonsHtml(pacienteNome) {
    return `
      <div class="fila-card-head-actions">
        <button
          type="button"
          class="btn atender"
          data-acao="atender"
          aria-label="Atender ${escapeHtml(pacienteNome)}"
          title="Atender"
        >
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
            <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4Zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4Z" fill="currentColor"/>
          </svg>
        </button>

        <button
          type="button"
          class="btn remover"
          data-acao="remover"
          aria-label="Remover ${escapeHtml(pacienteNome)}"
          title="Remover"
        >
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
            <path d="M3 6h18M8 6V4h8v2m1 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6h14Z"
                  stroke="currentColor"
                  stroke-width="2"
                  fill="none"
                  stroke-linecap="round"
                  stroke-linejoin="round"/>
          </svg>
        </button>
      </div>
    `;
  }

  function cardHtml(item) {
    const id = safeId(item.id);
    const pacienteId = safeId(item.paciente_id);
    const agendaId = safeId(item.agenda_id);

    const pacienteNome = item.paciente_nome || item.nome_paciente || "—";
    const profissionalNome = item.profissional_nome || item.nome_profissional || "—";
    const hora = item.hora || item.horario || "—";
    const tipo = item.tipo || "Individual";
    const obs = item.obs || item.observacao || "—";
    const origem = item.origem || (isFromAgenda(item) ? "agenda" : "manual");

    const combo = item?.combo || null;
    const temCombo = !!(combo && combo.id);
    const comboRestantes = Number(combo?.sessoes_restantes ?? combo?.restantes ?? 0);
    const semSaldo = temCombo && comboRestantes <= 0;

    return `
      <article
        class="fila-card ${semSaldo ? "is-sem-saldo" : ""}"
        data-id="${escapeHtml(id)}"
        data-prof="${escapeHtml(item.profissional_id || "")}"
        data-prio="${escapeHtml(item.prioridade || "verde")}"
        data-origem="${escapeHtml(origem)}"
        data-agenda-id="${escapeHtml(agendaId)}"
        data-status="${escapeHtml(item.status || "")}"
        data-tem-combo="${temCombo ? "1" : "0"}"
        data-combo-restantes="${escapeHtml(comboRestantes)}"
      >
        <header class="fila-card-head">
          <div class="fila-card-time">
            <span class="fila-card-label">Hora</span>
            <strong>${escapeHtml(hora)}</strong>
          </div>

          <div class="fila-card-top-actions">
            ${isFromAgenda(item) ? `<span class="from-agenda" title="Vindo da agenda">📅</span>` : ""}
            ${badgePrio(item.prioridade)}
            ${actionButtonsHtml(pacienteNome)}
          </div>
        </header>

        <div class="fila-card-body">
          <section class="fila-card-group">
            <span class="fila-card-mini-label">Paciente</span>
            <div class="fila-card-main" data-pid="${escapeHtml(pacienteId)}">
              <strong>${escapeHtml(pacienteNome)}</strong>
              <span class="muted-mini">ID: ${escapeHtml(pacienteId || "—")}</span>
            </div>
          </section>

          <section class="fila-card-group">
            <span class="fila-card-mini-label">Combo</span>
            ${comboHtml(item)}
          </section>

          <section class="fila-card-group">
            <span class="fila-card-mini-label">Profissional</span>
            <div class="fila-card-main">
              <strong>${escapeHtml(profissionalNome)}</strong>
              ${
                item.profissional_cbo || item.cbo
                  ? `<span class="muted-mini">CBO: ${escapeHtml(item.profissional_cbo || item.cbo)}</span>`
                  : ""
              }
            </div>
          </section>

          <section class="fila-card-inline">
            <div class="fila-card-group">
              <span class="fila-card-mini-label">Tipo</span>
              <div class="fila-card-main">
                <strong>${escapeHtml(tipo)}</strong>
              </div>
            </div>

            <div class="fila-card-group">
              <span class="fila-card-mini-label">Observações</span>
              <div class="fila-card-main">
                <span class="obs-text">${escapeHtml(obs)}</span>
              </div>
            </div>
          </section>
        </div>

        <footer class="fila-card-actions">
          <button
            type="button"
            class="btn chamar-tv"
            data-acao="chamar-tv"
            data-paciente-id="${escapeHtml(pacienteId)}"
            data-paciente-nome="${escapeHtml(pacienteNome)}"
            data-profissional-nome="${escapeHtml(profissionalNome)}"
            data-setor="Recepção"
            aria-label="Chamar ${escapeHtml(pacienteNome)} na TV"
          >
            📢 Chamar na TV
          </button>
        </footer>
      </article>
    `;
  }

  function applyFilters(items) {
    const q = normalizeText(dom.busca?.value || "");
    const prof = normalizeText(dom.profFiltro?.value || "");
    const prio = normalizeText(filtroPrio);

    return items.filter((item) => {
      if (!isOpenItem(item)) return false;
      if (wasLocallyRemoved(item)) return false;

      if (prio && normalizeText(item.prioridade) !== prio) return false;

      if (prof) {
        const profHay = [
          item.profissional_id,
          item.profissional_nome,
          item.nome_profissional,
          item.cbo,
          item.profissional_cbo,
          item.funcao,
        ].map(normalizeText).join(" ");

        if (!profHay.includes(prof)) return false;
      }

      if (q) {
        const hay = [
          item.paciente_nome,
          item.nome_paciente,
          item.paciente_id,
          item.cpf,
          item.cns,
          item.prontuario,
          item.profissional_nome,
          item.nome_profissional,
          item.cbo,
          item.profissional_cbo,
          item.tipo,
          item.prioridade,
          item.obs,
          item.observacao,
          item.status,
          item?.combo?.combo_nome,
          item?.combo?.nome_plano,
          item?.combo?.nome,
        ].map(normalizeText).join(" ");

        if (!hay.includes(q)) return false;
      }

      return true;
    });
  }

  function updateCounter() {
    if (dom.qtd) dom.qtd.textContent = String(filteredItems.length);
  }

  function totalPages() {
    return Math.max(1, Math.ceil(filteredItems.length / PER_PAGE));
  }

  function pageItems() {
    const start = (currentPage - 1) * PER_PAGE;
    return filteredItems.slice(start, start + PER_PAGE);
  }

  function updatePagination() {
    const total = totalPages();

    if (currentPage > total) currentPage = total;
    if (currentPage < 1) currentPage = 1;

    if (dom.pageInfo) dom.pageInfo.textContent = `Página ${currentPage} de ${total}`;
    if (dom.prev) dom.prev.disabled = currentPage <= 1;
    if (dom.next) dom.next.disabled = currentPage >= total;

    if (dom.pagination) {
      dom.pagination.hidden = filteredItems.length === 0 || total <= 1;
    }
  }

  function renderCurrentPage() {
    if (!dom.cards) return;

    updatePagination();
    updateCounter();

    const items = pageItems();

    if (!items.length) {
      dom.cards.innerHTML = "";
      if (dom.empty) dom.empty.hidden = false;
      return;
    }

    if (dom.empty) dom.empty.hidden = true;
    dom.cards.innerHTML = items.map(cardHtml).join("");
  }

  function renderFila(resetPage = true) {
    filteredItems = applyFilters(allItems);

    if (resetPage) currentPage = 1;

    renderCurrentPage();
  }

  async function carregarFila() {
    const data = await jfetch(API.filaList);
    const items = getPayloadList(data);

    allItems = items
      .filter(isOpenItem)
      .filter((item) => !wasLocallyRemoved(item));

    renderFila(false);

    log("Fila carregada:", allItems.length);
  }

  async function syncHoje() {
    try {
      await jfetch(API.filaSyncHoje, { method: "POST" });
    } catch (err) {
      console.warn("Falha no sync da agenda:", err.message);
    }

    await carregarFila();
  }

  function clearDatalist(listEl, cache) {
    if (listEl) listEl.innerHTML = "";
    cache.clear();
  }

  function setDatalist(listEl, cache, items) {
    if (!listEl) return;

    listEl.innerHTML = "";
    cache.clear();

    for (const item of items) {
      const id = safeId(item.id);
      const nome = String(item.label || item.nome || item.text || "").trim();

      if (!id || !nome) continue;

      const opt = document.createElement("option");
      opt.value = nome;
      opt.dataset.id = id;

      listEl.appendChild(opt);
      cache.set(normalizeText(nome), id);
    }
  }

  function parseDatalist(inputEl, listEl) {
    const val = String(inputEl?.value || "").trim();

    if (!val || !listEl) return { id: "", label: val };

    const found = Array.from(listEl.options || []).find((op) => {
      return String(op.value || "").trim() === val;
    });

    return {
      id: safeId(found?.dataset?.id || ""),
      label: val,
    };
  }

  function forceOpenDatalist(inputEl, listId) {
    try {
      inputEl.setAttribute("list", "");
      inputEl.offsetHeight;
      inputEl.setAttribute("list", listId);
    } catch (_) {}
  }

  async function buscarPacientes(term) {
    const q = String(term || "").trim();
    if (q.length < MIN_SEARCH) return [];

    const seq = ++pacReqSeq;
    const data = await jfetch(`${API.pacientes}?q=${encodeURIComponent(q)}`);

    if (seq !== pacReqSeq) return [];
    return getPayloadList(data);
  }

  async function buscarProfissionais(term) {
    const q = String(term || "").trim();
    if (q.length < MIN_SEARCH) return [];

    const seq = ++profReqSeq;
    const data = await jfetch(`${API.profissionais}?q=${encodeURIComponent(q)}`);

    if (seq !== profReqSeq) return [];
    return getPayloadList(data);
  }

  const onPacienteInput = debounce(async () => {
    const val = String(dom.pacienteInput?.value || "").trim();

    if (dom.pacienteId) dom.pacienteId.value = "";

    if (val.length < MIN_SEARCH) {
      clearDatalist(dom.pacienteList, PAC_CACHE);
      return;
    }

    const cachedId = PAC_CACHE.get(normalizeText(val));
    if (cachedId && dom.pacienteId) {
      dom.pacienteId.value = cachedId;
      return;
    }

    try {
      const items = await buscarPacientes(val);
      setDatalist(dom.pacienteList, PAC_CACHE, items);
      if (items.length) forceOpenDatalist(dom.pacienteInput, "listaPacientes");
    } catch (err) {
      console.warn("Erro ao buscar pacientes:", err.message);
      clearDatalist(dom.pacienteList, PAC_CACHE);
    }
  }, 250);

  const onProfInput = debounce(async () => {
    const val = String(dom.profInput?.value || "").trim();

    if (dom.profissionalId) dom.profissionalId.value = "";

    if (val.length < MIN_SEARCH) {
      clearDatalist(dom.profList, PROF_CACHE);
      return;
    }

    const cachedId = PROF_CACHE.get(normalizeText(val));
    if (cachedId && dom.profissionalId) {
      dom.profissionalId.value = cachedId;
      return;
    }

    try {
      const items = await buscarProfissionais(val);
      setDatalist(dom.profList, PROF_CACHE, items);
      if (items.length) forceOpenDatalist(dom.profInput, "listaProfissionais");
    } catch (err) {
      console.warn("Erro ao buscar profissionais:", err.message);
      clearDatalist(dom.profList, PROF_CACHE);
    }
  }, 250);

  dom.pacienteInput?.addEventListener("input", onPacienteInput);

  dom.pacienteInput?.addEventListener("change", () => {
    const parsed = parseDatalist(dom.pacienteInput, dom.pacienteList);
    const cacheId = PAC_CACHE.get(normalizeText(parsed.label));
    if (dom.pacienteId) dom.pacienteId.value = safeId(parsed.id || cacheId);
  });

  dom.profInput?.addEventListener("input", onProfInput);

  dom.profInput?.addEventListener("change", () => {
    const parsed = parseDatalist(dom.profInput, dom.profList);
    const cacheId = PROF_CACHE.get(normalizeText(parsed.label));
    if (dom.profissionalId) dom.profissionalId.value = safeId(parsed.id || cacheId);
  });

  dom.busca?.addEventListener("input", debounce(() => renderFila(true), 150));
  dom.profFiltro?.addEventListener("change", () => renderFila(true));
  dom.profFiltro?.addEventListener("input", () => renderFila(true));

  dom.prioFilter?.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".pf-pill");
    if (!btn) return;

    $$(".pf-pill", dom.prioFilter).forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");

    filtroPrio = normalizeText(btn.dataset.prio || "");
    renderFila(true);
  });

  dom.prev?.addEventListener("click", () => {
    if (currentPage <= 1) return;
    currentPage--;
    renderCurrentPage();
  });

  dom.next?.addEventListener("click", () => {
    if (currentPage >= totalPages()) return;
    currentPage++;
    renderCurrentPage();
  });

  dom.cards?.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-acao]");
    if (!btn) return;

    const card = btn.closest(".fila-card");
    if (!card) return;

    const acao = btn.dataset.acao;
    const id = safeId(card.dataset.id);

    ev.preventDefault();

    if (acao === "chamar-tv") {
      const oldText = btn.innerHTML;

      const payload = {
        paciente_id: btn.dataset.pacienteId || "",
        paciente_nome: btn.dataset.pacienteNome || "",
        profissional_nome: btn.dataset.profissionalNome || "",
        setor: btn.dataset.setor || "Recepção",
      };

      if (!payload.paciente_nome) {
        alert("Paciente inválido para chamada.");
        return;
      }

      btn.disabled = true;
      btn.innerHTML = "Chamando...";

      try {
        await jfetch(API.chamarTv, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        btn.innerHTML = "✅ Chamado!";
        setTimeout(() => {
          btn.innerHTML = oldText;
          btn.disabled = false;
        }, 1500);
      } catch (err) {
        alert(err.message || "Falha ao chamar na TV.");
        btn.innerHTML = oldText;
        btn.disabled = false;
      }

      return;
    }

    if (!id) {
      alert("Item da fila sem ID. Verifique o retorno da API.");
      return;
    }

    if (acao === "atender") {
      const pacienteId = card.querySelector("[data-pid]")?.dataset.pid || "";
      const pacienteNome = card.querySelector("[data-pid] strong")?.textContent?.trim() || "";

      if (!pacienteId) {
        alert("Paciente não identificado para atendimento.");
        return;
      }

      try {
        await jfetch(API.filaUpdate(id), {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: "atendendo" }),
        });
      } catch (err) {
        console.warn("Não conseguiu marcar como atendendo:", err.message);
      }

      window.location.href =
        `/atendimentos/registrar?fila_id=${encodeURIComponent(id)}` +
        `&paciente_id=${encodeURIComponent(pacienteId)}` +
        `&paciente_nome=${encodeURIComponent(pacienteNome)}`;

      return;
    }

    if (acao === "remover") {
      if (!confirm("Remover este item da fila?")) return;

      const item = allItems.find((x) => String(x.id) === String(id)) || {
        id,
        agenda_id: card.dataset.agendaId,
      };

      try {
        await jfetch(API.filaDelete(id), {
          method: "DELETE",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            motivo: "Removido da lista de atendimentos.",
            origem: card.dataset.origem || "",
            agenda_id: card.dataset.agendaId || "",
          }),
        });
      } catch (err) {
        console.warn("DELETE falhou, aplicando remoção local:", err.message);
      }

      rememberRemoved(item);

      allItems = allItems.filter((x) => String(x.id) !== String(id));
      renderFila(false);

      return;
    }
  });

  dom.form?.addEventListener("submit", async (ev) => {
    ev.preventDefault();

    let pacienteId = safeId(dom.pacienteId?.value);
    let profissionalId = safeId(dom.profissionalId?.value);

    if (!pacienteId) {
      const parsed = parseDatalist(dom.pacienteInput, dom.pacienteList);
      pacienteId = safeId(parsed.id || PAC_CACHE.get(normalizeText(parsed.label)));
    }

    if (!profissionalId) {
      const parsed = parseDatalist(dom.profInput, dom.profList);
      profissionalId = safeId(parsed.id || PROF_CACHE.get(normalizeText(parsed.label)));
    }

    if (!pacienteId) {
      toast(`Digite pelo menos ${MIN_SEARCH} letras e selecione um paciente da lista.`, "error");
      return;
    }

    if (!profissionalId) {
      toast(`Digite pelo menos ${MIN_SEARCH} letras e selecione um profissional da lista.`, "error");
      return;
    }

    const payload = {
      paciente_id: pacienteId,
      profissional_id: profissionalId,
      tipo: dom.tipo?.value || "Individual",
      prioridade:
        dom.prioGroup?.querySelector('input[name="prioridade"]:checked')?.value || "verde",
      obs: dom.obs?.value || "",
    };

    try {
      await jfetch(API.filaAdd, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      dom.form.reset();

      if (dom.pacienteId) dom.pacienteId.value = "";
      if (dom.profissionalId) dom.profissionalId.value = "";

      clearDatalist(dom.pacienteList, PAC_CACHE);
      clearDatalist(dom.profList, PROF_CACHE);

      await carregarFila();
    } catch (err) {
      toast(err.message || "Falha ao adicionar paciente à fila.", "error");
    }
  });

  dom.btnImprimir?.addEventListener("click", () => window.print());

  dom.btnLimpar?.addEventListener("click", async () => {
    if (!confirm("Limpar completamente a fila?")) return;

    try {
      await jfetch(API.filaClear, { method: "POST" });
      allItems = [];
      renderFila(true);
    } catch (err) {
      toast(err.message || "Falha ao limpar fila.", "error");
    }
  });

  document.addEventListener("keydown", (ev) => {
    if (ev.ctrlKey && ev.key.toLowerCase() === "p") {
      ev.preventDefault();
      window.print();
    }
  });

  window.addEventListener("storage", (ev) => {
    if (ev.key && ev.key.startsWith("fila_removida:")) {
      carregarFila().catch(console.warn);
    }
  });

  async function boot() {
    log("DOM OK:", {
      cards: !!dom.cards,
      form: !!dom.form,
      pacienteInput: !!dom.pacienteInput,
      profInput: !!dom.profInput,
      busca: !!dom.busca,
      profFiltro: !!dom.profFiltro,
    });

    await syncHoje();

    setInterval(() => {
      syncHoje().catch((err) => console.warn("Erro no sync automático:", err.message));
    }, 60_000);
  }

  boot().catch((err) => {
    console.error("Erro ao iniciar lista de atendimentos:", err);
    toast("Erro ao carregar a lista de atendimentos.", "error");
  });
})();