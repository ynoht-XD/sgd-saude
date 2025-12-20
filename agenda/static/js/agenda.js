// agenda/static/js/agenda.js
(() => {
  // ================== helpers ==================
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const meta = (name) => document.querySelector(`meta[name="${name}"]`)?.content || "";

  const ENDPOINT_SAVE         = meta("agenda-save-endpoint");
  const ENDPOINT_SUGGEST      = meta("pacientes-suggest-endpoint");
  const ENDPOINT_PROS         = meta("profissionais-endpoint");
  const ENDPOINT_AGREG        = meta("agregados-endpoint");
  const ENDPOINT_EXPORT       = meta("agregados-export-endpoint");

  const ENDPOINT_AGEND_BASE   = "/agenda/api/agendamentos"; // PUT/DELETE por ID
  const ENDPOINT_DELETE_GROUP = "/agenda/api/agregados";    // DELETE por grupo (dow+hora+prof+pac)

  // CPF do profissional logado vindo do template
  const CURRENT_PROF_CPF = meta("current-prof-cpf") || "";
  const onlyDigits = (v) => (v || "").replace(/\D/g, "");

  console.debug("[agenda] META current-prof-cpf:", CURRENT_PROF_CPF);

  const debounce = (fn, ms = 250) => {
    let t;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn.apply(null, args), ms);
    };
  };

  const DIA_LABEL = (d) => {
    const M = ["Domingo","Segunda","Terça","Quarta","Quinta","Sexta","Sábado"];
    const i = Number(d);
    return Number.isInteger(i) && i >= 0 && i <= 6 ? M[i] : "—";
  };

  // ================== elementos do formulário (cadastro) ==================
  const elPacienteBusca = $("#paciente_busca");
  const elPacienteNome  = $("#paciente_nome");
  const elSug           = $("#sugestoes");
  const elMsg           = $("#msg");

  const elProf          = $("#profissional_select");
  const elDia           = $("#dia");
  const elHoraDe        = $("#hora_de");
  const elHoraAte       = $("#hora_ate");
  const elQtd           = $("#qtd");
  const elValor         = $("#valor");
  const elBtnSalvar     = $("#btnSalvar");
  const elBtnSalvarVago = $("#btnSalvarVago");

  // ================== elementos do modal de edição ==================
  const dlgEdit           = $("#modal-agenda-editar");
  const formEdit          = $("#form-agenda-editar");
  const elEditId          = $("#ag_edit_id");
  const elEditPaciente    = $("#ag_edit_paciente");
  const elEditProf        = $("#ag_edit_profissional");
  const elEditDia         = $("#ag_edit_dia");
  const elEditHoraDe      = $("#ag_edit_hora_de");
  const elEditHoraAte     = $("#ag_edit_hora_ate");
  const elEditQtd         = $("#ag_edit_qtd");
  const elEditValor       = $("#ag_edit_valor");
  const elEditMsg         = $("#ag_edit_msg");
  const elBtnSalvarEdicao = $("#btnAgendaSalvarEdicao");

  // ================== elementos dos filtros/lista ==================
  const elFProf     = $("#f_profissional");
  const elFDia      = $("#f_dia");
  const elFHoraDe   = $("#f_hora_de");
  const elFHoraAte  = $("#f_hora_ate");
  const elFPaciente = $("#f_paciente");
  const elFIdadeMin = $("#f_idade_min");
  const elFIdadeMax = $("#f_idade_max");
  const elFCid      = $("#f_cid");

  const elBtnAplicar   = $("#btnAplicarFiltros");
  const elBtnLimpar    = $("#btnLimparFiltros");
  const elFiltrosMsg   = $("#filtros_msg");

  // lista em cards
  const elCardsList    = $("#agCardsList");
  const elHelper       = $("#agregadosHelper");
  const elBtnRecarregar= $("#btnRecarregar");
  const elAgCount      = $("#agCount"); // pode não existir — protegemos abaixo

  // paginação
  const elPageInfo  = $("#pageInfo");
  const elBtnFirst  = $("#btnFirst");
  const elBtnPrev   = $("#btnPrev");
  const elBtnNext   = $("#btnNext");
  const elBtnLast   = $("#btnLast");
  const elPageInput = $("#pageInput");

  const cardList  = elCardsList?.closest(".card");
  const PAGE_SIZE = Number(cardList?.dataset?.pagesize || 20);

  let cacheItems  = [];
  let currentPage = 1;
  let totalPages  = 1;

  // ================== helpers modal ==================
  function openModal(mod) {
    const el = typeof mod === "string" ? document.getElementById(mod) : mod;
    if (!el) return;
    el.classList.add("is-open");
  }

  function closeModal(mod) {
    const el = typeof mod === "string" ? document.getElementById(mod) : mod;
    if (!el) return;
    el.classList.remove("is-open");
  }

  // ================== carregar profissionais ==================
  async function loadProfissionais() {
    try {
      const res = await fetch(ENDPOINT_PROS);
      const data = await res.json();

      console.debug("[agenda] /api/profissionais retornou:", data);

      const fillSelect = (select, addTodos = false) => {
        if (!select) return;
        const keepFirst = addTodos
          ? `<option value="">Todos</option>`
          : `<option value="">Selecione…</option>`;

        select.innerHTML = keepFirst + data.map(p => {
          const nome = p.nome || p.NOME || "";
          const cpf  = p.cpf  || p.CPF  || p.cpf_digits || "";
          return `<option value="${cpf}">${nome}</option>`;
        }).join("");
      };

      fillSelect(elProf, false);
      fillSelect(elFProf, true);
      fillSelect(elEditProf, false);

      // ===== auto-seleção do profissional logado =====
      const cpfMetaDigits = onlyDigits(CURRENT_PROF_CPF);

      const autoSelectByCpf = (select, label) => {
        if (!select || !cpfMetaDigits) return;
        const opts = Array.from(select.options || []);
        const match = opts.find(o => onlyDigits(o.value) === cpfMetaDigits);

        if (match && match.value !== "") {
          select.value = match.value;
          console.info(`[agenda] ${label} pré-selecionado:`, match.textContent, "| value:", match.value);
        } else {
          console.warn(
            `[agenda] NÃO consegui pré-selecionar ${label}.`,
            "cpfMetaDigits =", cpfMetaDigits,
            "options =", opts.map(o => ({ text: o.textContent, value: o.value }))
          );
        }
      };

      // cadastral (form de criação)
      autoSelectByCpf(elProf, "profissional (cadastro)");
      // filtros
      autoSelectByCpf(elFProf, "filtro profissional");

      // (opcional) edição: só faz sentido ao abrir modal, então deixamos para lá

    } catch (e) {
      console.error("profissionais failed", e);
    }
  }

  // ================== autocomplete paciente ==================
  function hideSuggest() {
    if (!elSug) return;
    elSug.classList.add("hidden");
    elSug.innerHTML = "";
  }

  function renderSuggest(list) {
    if (!elSug) return;
    if (!list || !list.length) {
      hideSuggest();
      return;
    }
    const html = `
      <div class="suggest-list">
        ${list.map(it => {
          const nome  = (it.nome || "").toString();
          const idade = it.idade != null ? `${it.idade} anos` : "idade —";
          const cpf   = it.cpf ? `${it.cpf}` : "CPF —";
          return `
            <div class="suggest-item" data-nome="${encodeURIComponent(nome)}">
              <span class="title">${nome}</span>
              <span class="sub">${idade} • ${cpf}${it.prontuario ? ` • Pront.: ${it.prontuario}` : ""}</span>
            </div>
          `;
        }).join("")}
      </div>
    `;
    elSug.innerHTML = html;
    elSug.classList.remove("hidden");

    $$(".suggest-item", elSug).forEach(item => {
      item.addEventListener("click", () => {
        const nome = decodeURIComponent(item.dataset.nome || "");
        if (elPacienteBusca) elPacienteBusca.value = nome;
        if (elPacienteNome)  elPacienteNome.value  = nome;
        hideSuggest();
      });
    });
  }

  const onPacienteInput = debounce(async () => {
    if (!elPacienteBusca) return;
    const q = (elPacienteBusca.value || "").trim();
    if (elPacienteNome) elPacienteNome.value = ""; // reseta até escolher
    if (q.length < 3) {
      hideSuggest();
      return;
    }
    try {
      const url = new URL(ENDPOINT_SUGGEST, location.origin);
      url.searchParams.set("q", q);
      const res = await fetch(url.toString());
      const data = await res.json();
      renderSuggest(data);
    } catch (e) {
      console.error("sugestões pacientes failed", e);
      hideSuggest();
    }
  }, 300);

  // ================== salvar agendamento (novo / vago) ==================
  async function salvarAgendamento(isVago = false) {
    if (!elMsg) return;
    elMsg.textContent = "";

    let paciente_nome = (elPacienteNome?.value || elPacienteBusca?.value || "").trim();
    if (isVago) {
      paciente_nome = "VAGO";
    }

    const profissional_cpf = (elProf?.value || "").trim();
    const dia      = (elDia?.value || "").trim();
    const hora_de  = (elHoraDe?.value || "").trim();
    const hora_ate = (elHoraAte?.value || "").trim();
    const qtd      = Number(elQtd?.value || 1);
    const valor_sessao = (elValor && elValor.value !== "" ? Number(elValor.value) : null);

    if (!paciente_nome && !isVago) {
      elMsg.textContent = "Informe o paciente (use a busca).";
      elPacienteBusca?.focus();
      return;
    }
    if (!profissional_cpf) {
      elMsg.textContent = "Selecione o profissional.";
      elProf?.focus();
      return;
    }
    if (!hora_de) {
      elMsg.textContent = "Informe o horário inicial.";
      elHoraDe?.focus();
      return;
    }

    const payload = {
      paciente_nome,
      profissional_cpf,
      dia,
      hora_de,
      hora_ate: hora_ate || undefined,
      qtd,
      valor_sessao
    };

    const btn = isVago ? elBtnSalvarVago : elBtnSalvar;
    if (btn) btn.disabled = true;

    try {
      const res = await fetch(ENDPOINT_SAVE, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();

      if (!res.ok || data.error) {
        elMsg.textContent = data.error || "Erro ao salvar.";
        return;
      }

      const n = (data.criados && data.criados.length) ? data.criados.length : qtd;
      const labelPac = isVago ? "horário VAGO" : paciente_nome;
      elMsg.textContent = `✅ ${n} sessão(ões) criada(s) para ${labelPac}.`;
      if (!isVago && data.redirect) {
        const a = document.createElement("a");
        a.href = data.redirect;
        a.textContent = " Ver prontuário";
        a.style.marginLeft = "6px";
        a.target = "_blank";
        elMsg.appendChild(a);
      }
      await recarregarAgregados(false);
    } catch (e) {
      console.error(e);
      elMsg.textContent = "Erro de rede ao salvar.";
    } finally {
      if (btn) btn.disabled = false;
      setTimeout(() => { if (elMsg.textContent.startsWith("✅")) elMsg.textContent = ""; }, 5000);
    }
  }

  // ================== filtros / agregados ==================
  function buildAgregadosURL(base = ENDPOINT_AGREG) {
    const url = new URL(base, location.origin);

    const profVal   = (elFProf?.value || "").trim();
    const diaVal    = (elFDia?.value || "").trim();
    const hDeVal    = (elFHoraDe?.value || "").trim();
    const hAteVal   = (elFHoraAte?.value || "").trim();
    const pacVal    = (elFPaciente?.value || "").trim();
    const idadeMin  = (elFIdadeMin?.value || "").trim();
    const idadeMax  = (elFIdadeMax?.value || "").trim();
    const cidVal    = (elFCid?.value || "").trim();

    if (profVal) {
      url.searchParams.set("profissional_cpf", profVal);
      url.searchParams.set("profissional", profVal);
    }
    if (diaVal) {
      url.searchParams.set("dia", diaVal);
      url.searchParams.set("dia_semana", diaVal);
    }
    if (hDeVal) {
      url.searchParams.set("hora_de", hDeVal);
      url.searchParams.set("hora_ini", hDeVal);
    }
    if (hAteVal) {
      url.searchParams.set("hora_ate", hAteVal);
      url.searchParams.set("hora_fim", hAteVal);
    }
    if (pacVal) {
      url.searchParams.set("paciente", pacVal);
      url.searchParams.set("paciente_nome", pacVal);
    }
    if (idadeMin) {
      url.searchParams.set("idade_min", idadeMin);
      url.searchParams.set("idadeDe", idadeMin);
    }
    if (idadeMax) {
      url.searchParams.set("idade_max", idadeMax);
      url.searchParams.set("idadeAte", idadeMax);
    }
    if (cidVal) {
      url.searchParams.set("cid", cidVal);
      url.searchParams.set("cid10", cidVal);
    }

    console.debug("[agenda] URL agregados:", url.toString());
    return url.toString();
  }

  function buildExportURL() {
    return buildAgregadosURL(ENDPOINT_EXPORT);
  }

  // ======== renderização em CARDS ========
  function renderCardsPage(items, page, pageSize) {
    if (!elCardsList) return;

    elCardsList.innerHTML = "";
    if (!items.length) {
      if (elHelper) elHelper.textContent = "Nenhum registro encontrado.";
      return;
    }
    if (elHelper) elHelper.textContent = "";

    const start = (page - 1) * pageSize;
    const slice = items.slice(start, start + pageSize);

    const cardsHtml = slice.map((it, i) => {
      const idxCache = start + i;

      const diaLabel = it.dia_label
        || (it.dia_num != null ? DIA_LABEL(it.dia_num) : DIA_LABEL(it.dia));

      const hora     = it.hora_ini || "—";
      const prof     = it.profissional || "—";
      const pac      = it.paciente || "—";
      const qtd      = it.qtd != null ? it.qtd : "—";
      const pront    = it.prontuario || it.paciente_prontuario || "";

      const prontBtn = it.paciente_id ? `
        <a class="icon-btn" href="/visualizar/${it.paciente_id}" title="Ver prontuário" target="_blank" aria-label="Ver prontuário">
          <svg viewBox="0 0 24 24"><path d="M3 5h18v14H3zM7 5v14"/></svg>
        </a>
      ` : `
        <button class="icon-btn" title="Prontuário indisponível" disabled aria-disabled="true">
          <svg viewBox="0 0 24 24"><path d="M3 5h18v14H3zM7 5v14"/></svg>
        </button>
      `;

      const editBtn = `
        <button
          class="icon-btn btn-edit"
          title="Editar agendamentos deste grupo"
          aria-label="Editar"
          data-id="${it.any_id || ""}"
          data-idx="${idxCache}"
        >
          <svg viewBox="0 0 24 24">
            <path d="M12 20h9"/><path d="M16.5 3.5l4 4L7 21l-4 1 1-4z"/>
          </svg>
        </button>
      `;

      const dowNum = (it.dia_num != null ? it.dia_num : it.dia);

      const delBtn = `
        <button
          class="icon-btn danger btn-del"
          title="Excluir todas as sessões deste grupo"
          aria-label="Excluir grupo"
          data-dow="${dowNum}"
          data-hora="${it.hora_ini}"
          data-prof="${encodeURIComponent(it.profissional || "")}"
          data-pac="${encodeURIComponent(it.paciente || "")}"
        >
          <svg viewBox="0 0 24 24">
            <path d="M3 6h18"/><path d="M8 6l1-2h6l1 2"/><path d="M6 6v14h12V6"/>
          </svg>
        </button>
      `;

      return `
        <article class="ag-card" data-cache-index="${idxCache}">
          <header class="ag-card-head">
            <div class="ag-card-paciente">${pac}</div>
            <div class="ag-card-dia">${diaLabel} • ${hora}</div>
          </header>
          <div class="ag-card-body">
            <div class="ag-card-line">
              <span class="label">Prontuário</span>
              <span class="value">${pront || "—"}</span>
            </div>
            <div class="ag-card-line">
              <span class="label">Qtd. sessões</span>
              <span class="value">${qtd}</span>
            </div>
            <div class="ag-card-line">
              <span class="label">Profissional</span>
              <span class="value">${prof}</span>
            </div>
          </div>
          <footer class="ag-card-actions">
            ${prontBtn}
            ${editBtn}
            ${delBtn}
          </footer>
        </article>
      `;
    }).join("");

    elCardsList.innerHTML = cardsHtml;
  }

  function updatePagerUI() {
    if (!elPageInfo || !elPageInput) return;
    elPageInfo.textContent = `Página ${currentPage} de ${totalPages}`;
    elPageInput.value = String(currentPage);
    if (elBtnFirst) elBtnFirst.disabled = currentPage <= 1;
    if (elBtnPrev)  elBtnPrev.disabled  = currentPage <= 1;
    if (elBtnNext)  elBtnNext.disabled  = currentPage >= totalPages;
    if (elBtnLast)  elBtnLast.disabled  = currentPage >= totalPages;
  }

  async function recarregarAgregados(resetToFirstPage = true) {
    try {
      if (elHelper) elHelper.textContent = "Carregando…";
      const url = buildAgregadosURL();
      const res = await fetch(url);
      const data = await res.json();
      cacheItems  = Array.isArray(data) ? data : [];
      totalPages  = Math.max(1, Math.ceil(cacheItems.length / PAGE_SIZE));
      currentPage = resetToFirstPage ? 1 : Math.min(currentPage, totalPages);

      renderCardsPage(cacheItems, currentPage, PAGE_SIZE);
      updatePagerUI();

      if (elAgCount) elAgCount.textContent = `(${cacheItems.length})`;
      if (elHelper) elHelper.textContent = cacheItems.length ? "" : "Nenhum registro encontrado.";
    } catch (e) {
      console.error(e);
      if (elHelper) elHelper.textContent = "Falha ao carregar.";
      if (elAgCount) elAgCount.textContent = "(0)";
    }
  }

  function applyFiltersMsg() {
    if (!elFiltrosMsg) return;
    const parts = [];
    if (elFProf?.value) parts.push("Profissional");
    if (elFDia?.value) parts.push("Dia");
    if (elFHoraDe?.value || elFHoraAte?.value) parts.push("Horário");
    if (elFPaciente?.value) parts.push("Paciente");
    if (elFIdadeMin?.value || elFIdadeMax?.value) parts.push("Idade");
    if (elFCid?.value) parts.push("CID");
    elFiltrosMsg.textContent = parts.length ? `Filtros ativos: ${parts.join(", ")}` : "";
  }

  function clearFilters() {
    if (elFProf)     elFProf.value = "";
    if (elFDia)      elFDia.value = "";
    if (elFHoraDe)   elFHoraDe.value = "";
    if (elFHoraAte)  elFHoraAte.value = "";
    if (elFPaciente) elFPaciente.value = "";
    if (elFIdadeMin) elFIdadeMin.value = "";
    if (elFIdadeMax) elFIdadeMax.value = "";
    if (elFCid)      elFCid.value = "";
    if (elFiltrosMsg) elFiltrosMsg.textContent = "";
  }

  // ================== modal de edição: preencher & salvar ==================
  function preencherModalEdicao(item) {
    if (!dlgEdit) return;
    if (elEditMsg) elEditMsg.textContent = "";

    if (elEditId)       elEditId.value       = item.any_id || "";
    if (elEditPaciente) elEditPaciente.value = item.paciente || "VAGO";

    if (elEditDia) {
      let diaVal = "";
      if (item.dia_num !== undefined && item.dia_num !== null) {
        diaVal = String(item.dia_num);
      } else if (item.dia !== undefined && item.dia !== null && /^\d+$/.test(String(item.dia))) {
        diaVal = String(item.dia);
      }
      elEditDia.value = diaVal;
    }

    if (elEditHoraDe)  elEditHoraDe.value  = item.hora_ini || "";
    if (elEditHoraAte) elEditHoraAte.value = item.hora_fim || item.hora_ate || "";

    if (elEditQtd)   elEditQtd.value   = item.qtd != null ? String(item.qtd) : "1";
    if (elEditValor) elEditValor.value = item.valor_sessao != null ? String(item.valor_sessao) : "";

    if (elEditProf) {
      const profCpf = item.profissional_cpf || item.profissional_cpf_digits || "";
      if (profCpf) {
        elEditProf.value = profCpf;
      } else if (item.profissional) {
        const opts = Array.from(elEditProf.options || []);
        const match = opts.find(o =>
          (o.textContent || "").trim().toUpperCase() === item.profissional.trim().toUpperCase()
        );
        if (match) elEditProf.value = match.value;
      }
    }

    openModal(dlgEdit);
  }

  async function salvarEdicaoGrupo(ev) {
    if (ev) ev.preventDefault();
    if (!elEditId || !dlgEdit) return;

    const id = (elEditId.value || "").trim();
    if (!id) {
      if (elEditMsg) elEditMsg.textContent = "ID do agendamento não encontrado.";
      return;
    }

    const dia       = (elEditDia?.value || "").trim();
    const hora_de   = (elEditHoraDe?.value || "").trim();
    const hora_ate  = (elEditHoraAte?.value || "").trim();
    const qtd       = Number(elEditQtd?.value || 1);
    const valor_raw = (elEditValor?.value || "").trim();
    const valor_sessao = valor_raw ? Number(valor_raw) : null;
    const paciente_nome    = (elEditPaciente?.value || "").trim();
    const profissional_cpf = (elEditProf?.value || "").trim();

    if (!hora_de) {
      if (elEditMsg) elEditMsg.textContent = "Informe o horário inicial.";
      elEditHoraDe?.focus();
      return;
    }

    const payload = {
      dia,
      hora_de,
      hora_ate: hora_ate || undefined,
      qtd,
      valor_sessao,
      paciente_nome,
      profissional_cpf: profissional_cpf || undefined
    };

    if (elEditMsg) {
      elEditMsg.textContent = "Salvando alterações…";
      elEditMsg.style.color = "#64748b";
    }
    if (elBtnSalvarEdicao) elBtnSalvarEdicao.disabled = true;

    try {
      const res = await fetch(`${ENDPOINT_AGEND_BASE}/${encodeURIComponent(id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();

      if (!res.ok || data.error) {
        if (elEditMsg) {
          elEditMsg.textContent = data.error || "Falha ao editar agendamento.";
          elEditMsg.style.color = "#dc2626";
        }
        if (elBtnSalvarEdicao) elBtnSalvarEdicao.disabled = false;
        return;
      }

      if (elEditMsg) {
        elEditMsg.textContent = "✅ Agendamento atualizado com sucesso.";
        elEditMsg.style.color = "#16a34a";
      }
      await recarregarAgregados(false);
      setTimeout(() => closeModal(dlgEdit), 400);
    } catch (e) {
      console.error(e);
      if (elEditMsg) {
        elEditMsg.textContent = "Erro de rede ao editar.";
        elEditMsg.style.color = "#dc2626";
      }
    } finally {
      if (elBtnSalvarEdicao) elBtnSalvarEdicao.disabled = false;
    }
  }

  // ================== eventos ==================
  document.addEventListener("click", (e) => {
    if (elSug && !elSug.contains(e.target) && e.target !== elPacienteBusca) {
      hideSuggest();
    }

    const closeTarget = e.target.closest('[data-close="modal-agenda-editar"]');
    if (closeTarget && dlgEdit) {
      closeModal(dlgEdit);
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && dlgEdit?.classList.contains("is-open")) {
      closeModal(dlgEdit);
    }
  });

  if (elPacienteBusca) {
    elPacienteBusca.addEventListener("input", onPacienteInput);
    elPacienteBusca.addEventListener("focus", onPacienteInput);
  }

  if (elBtnSalvar) {
    elBtnSalvar.addEventListener("click", (e) => {
      e.preventDefault();
      salvarAgendamento(false);
    });
  }

  if (elBtnSalvarVago) {
    elBtnSalvarVago.addEventListener("click", (e) => {
      e.preventDefault();
      salvarAgendamento(true);
    });
  }

  // filtros
  if (elBtnAplicar) {
    elBtnAplicar.addEventListener("click", async () => {
      applyFiltersMsg();
      await recarregarAgregados(true);
    });
  }
  if (elBtnLimpar) {
    elBtnLimpar.addEventListener("click", async () => {
      clearFilters();
      await recarregarAgregados(true);
    });
  }
  if (elBtnRecarregar) {
    elBtnRecarregar.addEventListener("click", async () => {
      await recarregarAgregados(false);
    });
  }

  // paginação
  if (elBtnFirst) {
    elBtnFirst.addEventListener("click", () => {
      if (currentPage > 1) {
        currentPage = 1;
        renderCardsPage(cacheItems, currentPage, PAGE_SIZE);
        updatePagerUI();
      }
    });
  }
  if (elBtnPrev) {
    elBtnPrev.addEventListener("click", () => {
      if (currentPage > 1) {
        currentPage -= 1;
        renderCardsPage(cacheItems, currentPage, PAGE_SIZE);
        updatePagerUI();
      }
    });
  }
  if (elBtnNext) {
    elBtnNext.addEventListener("click", () => {
      if (currentPage < totalPages) {
        currentPage += 1;
        renderCardsPage(cacheItems, currentPage, PAGE_SIZE);
        updatePagerUI();
      }
    });
  }
  if (elBtnLast) {
    elBtnLast.addEventListener("click", () => {
      if (currentPage < totalPages) {
        currentPage = totalPages;
        renderCardsPage(cacheItems, currentPage, PAGE_SIZE);
        updatePagerUI();
      }
    });
  }
  if (elPageInput) {
    elPageInput.addEventListener("change", () => {
      const v = Math.max(1, Math.min(totalPages, Number(elPageInput.value || 1)));
      currentPage = v;
      renderCardsPage(cacheItems, currentPage, PAGE_SIZE);
      updatePagerUI();
    });
  }

  // exportar
  const elBtnExport = document.getElementById("btnExport");
  elBtnExport?.addEventListener("click", () => {
    const url = buildExportURL();
    window.location.href = url;
  });

  // ================== ações nos CARDS (editar + excluir grupo) ==================
  if (elCardsList) {
    elCardsList.addEventListener("click", async (ev) => {
      const delBtn  = ev.target.closest(".btn-del");
      const editBtn = ev.target.closest(".btn-edit");

      // ---- EXCLUIR GRUPO ----
      if (delBtn) {
        const dow  = delBtn.getAttribute("data-dow");
        const hora = delBtn.getAttribute("data-hora");
        const prof = decodeURIComponent(delBtn.getAttribute("data-prof") || "");
        const pac  = decodeURIComponent(delBtn.getAttribute("data-pac")  || "");

        const ok = confirm(
          `Excluir TODAS as sessões deste grupo?\n\n${DIA_LABEL(dow)} • ${hora}\nProfissional: ${prof}\nPaciente: ${pac}`
        );
        if (!ok) return;

        delBtn.disabled = true;

        try {
          const url = new URL(ENDPOINT_DELETE_GROUP, location.origin);
          url.searchParams.set("dow", dow);
          url.searchParams.set("hora_ini", hora);
          url.searchParams.set("profissional", prof);
          url.searchParams.set("paciente", pac);

          const res  = await fetch(url.toString(), { method: "DELETE" });
          const data = await res.json();

          if (!res.ok || data.error) {
            alert(data.error || "Falha ao excluir grupo.");
            delBtn.disabled = false;
            return;
          }
          await recarregarAgregados(false);
        } catch (e) {
          console.error(e);
          alert("Erro de rede ao excluir grupo.");
          delBtn.disabled = false;
        }
        return;
      }

      // ---- EDITAR GRUPO (abrir modal) ----
      if (editBtn) {
        const idx = Number(editBtn.getAttribute("data-idx") || "-1");
        const item = cacheItems[idx];
        if (!item) {
          alert("Não foi possível localizar o registro para editar.");
          return;
        }
        if (!item.any_id) {
          alert("ID não encontrado para edição.");
          return;
        }
        preencherModalEdicao(item);
      }
    });
  }

  // submit do modal de edição
  if (formEdit && elBtnSalvarEdicao) {
    formEdit.addEventListener("submit", salvarEdicaoGrupo);
  }

  // ================== boot ==================
  (async function boot() {
    await loadProfissionais();   // aqui ele já tenta pré-selecionar pelo CPF
    applyFiltersMsg();
    await recarregarAgregados(true); // já vai chamar api/agregados com ?profissional=...
  })();
})();
