(() => {
  "use strict";

  // =========================================================
  // HELPERS
  // =========================================================
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const state = {
    combos: [],
    planosCatalogo: [],
    autoPlano: false,
    vinculos: [],
    vinculosFiltrados: [],
    pacientesSemVinculo: [],
    pacienteSelecionado: null,
    paginaAtual: 1,
    itensPorPagina: 12,
    modoControle: "vinculos",
  };

  if (!window.FinComp) {
    throw new Error("financeiro-componentes.js não foi carregado antes de comercial.js.");
  }

  const {
    escapeHtml, money, boolValue, normalizeText,
    toast, debounce, setLoading, requestJSON, closeDialog, togglePanel,
    vinculoCardHtml, paginacaoHtml, semVinculoCardsHtml,
    criarSeletorPaciente, criarModalVinculo,
  } = window.FinComp;

  function setModeControle(mode) {
    state.modoControle = mode;

    if (els.abaVinculos) {
      const active = mode === "vinculos";
      els.abaVinculos.classList.toggle("is-active", active);
      els.abaVinculos.setAttribute("aria-selected", String(active));
    }

    if (els.abaSemVinculo) {
      const active = mode === "sem-vinculo";
      els.abaSemVinculo.classList.toggle("is-active", active);
      els.abaSemVinculo.setAttribute("aria-selected", String(active));
    }

    if (els.painelVinculos) els.painelVinculos.hidden = mode !== "vinculos";
    if (els.painelSemVinculo) els.painelSemVinculo.hidden = mode !== "sem-vinculo";
  }

  // =========================================================
  // ELEMENTOS
  // =========================================================
  const els = {
    // topo
    statCombos: $("#statCombos"),
    statPlanos: $("#statPlanos"),
    statVinculos: $("#statVinculos"),
    statPertoAcabar: $("#statPertoAcabar"),

    // toggles
    btnToggleCadastroCombo: $("#btnToggleCadastroCombo"),
    btnToggleGestaoCombos: $("#btnToggleGestaoCombos"),
    btnFecharCadastroCombo: $("#btnFecharCadastroCombo"),
    btnFecharGestaoCombos: $("#btnFecharGestaoCombos"),
    painelCadastroCombo: $("#painelCadastroCombo"),
    painelGestaoCombos: $("#painelGestaoCombos"),

    // combos
    formCombo: $("#formCombo"),
    comboId: $("#comboId"),
    comboNome: $("#comboNome"),
    comboSessoes: $("#comboSessoes"),
    comboPreco: $("#comboPreco"),
    comboDescricao: $("#comboDescricao"),
    comboAtivo: $("#comboAtivo"),
    btnSalvarCombo: $("#btnSalvarCombo"),
    btnLimparCombo: $("#btnLimparCombo"),
    filtroComboBusca: $("#filtroComboBusca"),
    filtroComboAtivo: $("#filtroComboAtivo"),
    btnAtualizarCombos: $("#btnAtualizarCombos"),
    btnSalvarGestaoCombos: $("#btnSalvarGestaoCombos"),
    listaCombos: $("#listaCombos"),

    // paciente
    pacienteBusca: $("#pacienteBusca"),
    pacienteResultados: $("#pacienteResultados"),
    pacienteSelecionadoBox: $("#pacienteSelecionadoBox"),
    pacienteId: $("#pacienteId"),

    // vínculo form
    formVinculo: $("#formVinculo"),
    vinculoId: $("#vinculoId"),
    tipoVinculo: $("#tipoVinculo"),
    comboSelect: $("#comboSelect"),
    fieldComboSelect: $("#fieldComboSelect"),
    fieldNomePlano: $("#fieldNomePlano"),
    nomePlano: $("#nomePlano"),
    fieldPlanoCatalogo: $("#fieldPlanoCatalogo"),
    planoCatalogoSelect: $("#planoCatalogoSelect"),
    planoResumo: $("#planoResumo"),
    sessoesContratadas: $("#sessoesContratadas"),
    valorTotal: $("#valorTotal"),
    formaPagamento: $("#formaPagamento"),
    dataInicioVinculo: $("#dataInicioVinculo"),
    dataFimVinculo: $("#dataFimVinculo"),
    vinculoRecorrente: $("#vinculoRecorrente"),
    vinculoRenovacao: $("#vinculoRenovacao"),
    observacoesVinculo: $("#observacoesVinculo"),
    btnSalvarVinculo: $("#btnSalvarVinculo"),
    btnLimparVinculo: $("#btnLimparVinculo"),

    // tabs / controle
    abaVinculos: $("#abaVinculos"),
    abaSemVinculo: $("#abaSemVinculo"),
    painelVinculos: $("#painelVinculos"),
    painelSemVinculo: $("#painelSemVinculo"),

    filtroVinculoBusca: $("#filtroVinculoBusca"),
    filtroVinculoTipo: $("#filtroVinculoTipo"),
    filtroVinculoStatus: $("#filtroVinculoStatus"),
    filtroPertoAcabar: $("#filtroPertoAcabar"),
    btnAtualizarVinculos: $("#btnAtualizarVinculos"),
    cardsVinculos: $("#cardsVinculos"),

    filtroSemVinculoBusca: $("#filtroSemVinculoBusca"),
    filtroSemVinculoAtendimento: $("#filtroSemVinculoAtendimento"),
    btnAtualizarSemVinculo: $("#btnAtualizarSemVinculo"),
    cardsSemVinculo: $("#cardsSemVinculo"),

    // modal vínculo
    modalVinculo: $("#modalVinculo"),
    formModalVinculo: $("#formModalVinculo"),
    mvId: $("#mvId"),
    mvPacienteNome: $("#mvPacienteNome"),
    mvTipo: $("#mvTipo"),
    mvFieldCombo: $("#mvFieldCombo"),
    mvComboId: $("#mvComboId"),
    mvFieldNomePlano: $("#mvFieldNomePlano"),
    mvNomePlano: $("#mvNomePlano"),
    mvSessoesContratadas: $("#mvSessoesContratadas"),
    mvSessoesUsadas: $("#mvSessoesUsadas"),
    mvSessoesRestantes: $("#mvSessoesRestantes"),
    mvValorTotal: $("#mvValorTotal"),
    mvFormaPagamento: $("#mvFormaPagamento"),
    mvStatus: $("#mvStatus"),
    mvDataInicio: $("#mvDataInicio"),
    mvDataFim: $("#mvDataFim"),
    mvRecorrente: $("#mvRecorrente"),
    mvRenovacaoAutomatica: $("#mvRenovacaoAutomatica"),
    mvObservacoes: $("#mvObservacoes"),
    mvBadgeTipo: $("#mvBadgeTipo"),
    mvBadgeConsumo: $("#mvBadgeConsumo"),
    mvBadgeAlerta: $("#mvBadgeAlerta"),
    btnDesvincularAtendimentosModal: $("#btnDesvincularAtendimentosModal"),
    btnExcluirVinculoModal: $("#btnExcluirVinculoModal"),
    btnFecharVinculoModal: $("#btnFecharVinculoModal"),
  };

  // =========================================================
  // COMPONENTES COMPARTILHADOS (financeiro-componentes.js)
  // =========================================================
  const seletorPaciente = criarSeletorPaciente({
    resultados: els.pacienteResultados,
    caixaSelecionado: els.pacienteSelecionadoBox,
    campoId: els.pacienteId,
    vinculoExistente: (pacienteId) => getExistingVinculoByPaciente(pacienteId),
    aoSelecionar: (paciente) => { state.pacienteSelecionado = paciente; },
    aoLimpar: () => { state.pacienteSelecionado = null; },
  });

  const modalVinculo = criarModalVinculo({
    els,
    aposSalvar: async () => {
      await loadVinculos();
      await loadPacientesSemVinculo();
    },
    aposDesvincular: async () => {
      await loadVinculos();
    },
    aposExcluir: async () => {
      await loadVinculos();
      await loadPacientesSemVinculo();
    },
  });

  // =========================================================
  // COMBOS
  // =========================================================
  async function loadCombos() {
    const q = els.filtroComboBusca?.value?.trim() || "";
    const ativo = els.filtroComboAtivo?.value || "";

    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (ativo !== "") params.set("ativo", ativo);

    const data = await requestJSON(`/financeiro/api/combos?${params.toString()}`);
    state.combos = Array.isArray(data.items) ? data.items : [];

    renderCombos();
    fillComboSelects();
    updateStats();
  }

  function fillComboSelects() {
    const options = [`<option value="">Selecione...</option>`]
      .concat(
        state.combos.map(c => `
          <option value="${c.id}" data-sessoes="${Number(c.sessoes || 0)}" data-preco="${Number(c.preco || 0)}">
            ${escapeHtml(c.nome)} · ${Number(c.sessoes || 0)} sessão(ões) · ${money(c.preco)}
          </option>
        `)
      )
      .join("");

    if (els.comboSelect) els.comboSelect.innerHTML = options;
    if (els.mvComboId) els.mvComboId.innerHTML = options;
  }

  function renderCombos() {
    if (!els.listaCombos) return;

    if (!state.combos.length) {
      els.listaCombos.innerHTML = `
        <div class="com-empty">
          <strong>Nenhum combo encontrado.</strong>
          <span>Cadastre um novo combo ou ajuste os filtros da pesquisa.</span>
        </div>
      `;
      return;
    }

    els.listaCombos.innerHTML = state.combos.map(combo => `
      <article class="combo-card" data-combo-id="${combo.id}">
        <div class="combo-top">
          <div class="com-field" style="width:100%;gap:6px;">
            <label class="com-label">Nome</label>
            <input class="com-input js-gestao-combo" data-field="nome" data-id="${combo.id}" value="${escapeHtml(combo.nome || "")}">
          </div>

          <div class="com-badges">
            <span class="com-badge ${Number(combo.ativo) ? "com-badge--active" : "com-badge--inactive"}">
              ${Number(combo.ativo) ? "Ativo" : "Inativo"}
            </span>
          </div>
        </div>

        <div class="com-form-grid" style="grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;">
          <div class="com-field">
            <label class="com-label">Sessões</label>
            <input class="com-input js-gestao-combo" data-field="sessoes" data-id="${combo.id}" type="number" min="1" step="1" value="${Number(combo.sessoes || 0)}">
          </div>

          <div class="com-field">
            <label class="com-label">Preço</label>
            <input class="com-input js-gestao-combo" data-field="preco" data-id="${combo.id}" type="number" min="0" step="0.01" value="${Number(combo.preco || 0)}">
          </div>
        </div>

        <div class="com-field">
          <label class="com-label">Observações</label>
          <textarea class="com-textarea js-gestao-combo" data-field="descricao" data-id="${combo.id}" rows="3">${escapeHtml(combo.descricao || "")}</textarea>
        </div>

        <div class="com-actions" style="justify-content:space-between;">
          <label class="com-switch">
            <input class="js-gestao-combo-checkbox" data-field="ativo" data-id="${combo.id}" type="checkbox" ${Number(combo.ativo) ? "checked" : ""}>
            <span class="com-switch-ui"></span>
            <span class="com-switch-text">Ativo</span>
          </label>

          <button type="button" class="com-btn com-btn--danger" data-action="excluir-combo" data-id="${combo.id}">
            Excluir
          </button>
        </div>
      </article>
    `).join("");
  }

  function collectComboCardData(comboId) {
    const card = els.listaCombos?.querySelector(`[data-combo-id="${comboId}"]`);
    if (!card) return null;

    return {
      nome: card.querySelector(`[data-field="nome"]`)?.value?.trim() || "",
      sessoes: Number(card.querySelector(`[data-field="sessoes"]`)?.value || 0),
      preco: Number(card.querySelector(`[data-field="preco"]`)?.value || 0),
      descricao: card.querySelector(`[data-field="descricao"]`)?.value?.trim() || "",
      ativo: !!card.querySelector(`[data-field="ativo"]`)?.checked,
    };
  }

  function resetComboForm() {
    els.formCombo?.reset();
    if (els.comboId) els.comboId.value = "";
    if (els.comboAtivo) els.comboAtivo.checked = true;
  }

  async function submitComboForm(ev) {
    ev.preventDefault();

    const payload = {
      nome: els.comboNome.value.trim(),
      sessoes: Number(els.comboSessoes.value || 0),
      preco: Number(els.comboPreco.value || 0),
      descricao: els.comboDescricao.value.trim(),
      ativo: boolValue(els.comboAtivo),
    };

    setLoading(els.btnSalvarCombo, true);

    try {
      await requestJSON("/financeiro/api/combos", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      toast("Combo cadastrado com sucesso.");
      resetComboForm();
      await loadCombos();
      togglePanel(els.painelCadastroCombo, els.btnToggleCadastroCombo, false);
    } catch (err) {
      toast(err.message || "Não foi possível salvar o combo.");
    } finally {
      setLoading(els.btnSalvarCombo, false);
    }
  }

  async function saveAllCombosInline() {
    const ids = [...new Set($$(".js-gestao-combo, .js-gestao-combo-checkbox", els.listaCombos).map(el => el.dataset.id))];

    if (!ids.length) {
      toast("Nenhum combo para salvar.");
      return;
    }

    setLoading(els.btnSalvarGestaoCombos, true, "Salvando...");

    try {
      for (const id of ids) {
        const payload = collectComboCardData(id);
        if (!payload) continue;

        await requestJSON(`/financeiro/api/combos/${id}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
      }

      toast("Alterações salvas com sucesso.");
      await loadCombos();
    } catch (err) {
      toast(err.message || "Erro ao salvar alterações dos combos.");
    } finally {
      setLoading(els.btnSalvarGestaoCombos, false);
    }
  }

  async function deleteCombo(comboId) {
    const confirmed = window.confirm("Deseja realmente excluir este combo?");
    if (!confirmed) return;

    try {
      await requestJSON(`/financeiro/api/combos/${comboId}`, {
        method: "DELETE"
      });
      toast("Combo excluído com sucesso.");
      await loadCombos();
    } catch (err) {
      toast(err.message || "Não foi possível excluir o combo.");
    }
  }

  // =========================================================
  // PACIENTES
  // =========================================================
  function buscarPacientes(q) {
    return seletorPaciente.buscar(q);
  }

  function getExistingVinculoByPaciente(pacienteId) {
    return state.vinculos.find(v => String(v.paciente_id || "") === String(pacienteId || ""));
  }

  function selectPacienteFromDataset(dataset) {
    seletorPaciente.selecionar(dataset);
  }

  function clearPacienteSelecionado() {
    seletorPaciente.limpar();
  }

  // =========================================================
  // FORM VÍNCULO
  // =========================================================
  function syncTipoVinculoForm() {
    const tipo = els.tipoVinculo?.value || "combo";
    const isCombo = tipo === "combo";

    if (els.fieldComboSelect) els.fieldComboSelect.hidden = !isCombo;
    // plano usa o seletor do catálogo; o nome livre não é mais usado na criação
    if (els.fieldNomePlano) els.fieldNomePlano.hidden = true;
    if (els.fieldPlanoCatalogo) els.fieldPlanoCatalogo.hidden = isCombo;

    if (isCombo) {
      limparPlanoCatalogoForm();
    } else if (!state.autoPlano) {
      // vindo de combo: os campos podem ter o autopreenchimento do combo; o plano recalcula os seus
      if (els.sessoesContratadas) els.sessoesContratadas.value = "";
      if (els.valorTotal) els.valorTotal.value = "";
      if (els.sessoesContratadas) els.sessoesContratadas.readOnly = true;
      loadPlanosCatalogo().catch(err => toast(err.message));
    }
  }

  // =========================================================
  // CONTRATO TIPO PLANO (catálogo)
  // =========================================================
  async function loadPlanosCatalogo() {
    const data = await requestJSON("/financeiro/api/planos?ativo=1");
    state.planosCatalogo = Array.isArray(data.items) ? data.items : [];

    if (!els.planoCatalogoSelect) return;

    const atual = els.planoCatalogoSelect.value;
    els.planoCatalogoSelect.innerHTML = [`<option value="">Selecione...</option>`]
      .concat(state.planosCatalogo.map(p => `
        <option value="${p.id}" ${String(p.id) === atual ? "selected" : ""}>
          ${escapeHtml(p.nome)} · ${money(p.valor_mensalidade)}/mês · ${Number(p.duracao_meses || 0)} mês(es)${Number(p.max_beneficiarios) > 1 ? " · familiar" : ""}
        </option>
      `))
      .join("");
  }

  // mesma conta do servidor (financas._calcular_sessoes_plano): semana = por_periodo x 4 x meses
  function sessoesDoPlano(p) {
    const por = Number(p.sessoes_por_periodo || 0);
    const meses = Number(p.duracao_meses || 0);
    if (por <= 0 || meses <= 0) return 0;
    return p.periodo === "semana" ? por * 4 * meses : por * meses;
  }

  function limparPlanoCatalogoForm() {
    if (els.planoCatalogoSelect) els.planoCatalogoSelect.value = "";
    if (els.planoResumo) {
      els.planoResumo.hidden = true;
      els.planoResumo.innerHTML = "";
    }
    if (els.sessoesContratadas) els.sessoesContratadas.readOnly = false;

    // desfaz só o que o próprio plano preencheu; o autopreenchimento do combo segue como antes
    if (state.autoPlano) {
      if (els.sessoesContratadas) els.sessoesContratadas.value = "";
      if (els.valorTotal) els.valorTotal.value = "";
      state.autoPlano = false;
    }
  }

  function applyPlanoCatalogoToForm() {
    const id = els.planoCatalogoSelect?.value;
    const plano = state.planosCatalogo.find(p => String(p.id) === String(id));

    if (!plano) {
      if (state.autoPlano) {
        els.sessoesContratadas.value = "";
        els.valorTotal.value = "";
        state.autoPlano = false;
      }
      els.planoResumo.hidden = true;
      els.planoResumo.innerHTML = "";
      return;
    }

    const sessoes = sessoesDoPlano(plano);
    const mensalidade = Number(plano.valor_mensalidade || 0);
    const meses = Number(plano.duracao_meses || 0);
    const total = mensalidade * meses;
    const maxBenef = Number(plano.max_beneficiarios || 1);
    const por = Number(plano.sessoes_por_periodo || 0);
    const periodoTxt = plano.periodo === "semana" ? "por semana" : "por mês";

    // sessões vêm do catálogo (o servidor recalcula e ignora o que for enviado); valor pode ser ajustado
    els.sessoesContratadas.value = sessoes;
    els.sessoesContratadas.readOnly = true;
    els.valorTotal.value = total;
    state.autoPlano = true;

    els.planoResumo.innerHTML = `
      <div class="com-patient-card" data-plano-resumo="1">
        <strong>${escapeHtml(plano.nome)}</strong>
        <div class="com-patient-meta">
          Mensalidade: <b>${money(mensalidade)}</b> ·
          Duração: <b>${meses} mês(es)</b> ·
          Consultas: <b>${por} ${periodoTxt}</b>
        </div>
        <div class="com-patient-meta">
          Total de sessões: <b>${sessoes}</b> ·
          Valor total do contrato: <b>${money(total)}</b>
        </div>
        <div class="com-patient-meta">
          ${maxBenef > 1
            ? `Plano familiar: até <b>${maxBenef}</b> beneficiários, contando o titular. O paciente selecionado entra como titular; os demais beneficiários são adicionados depois que o contrato existir.`
            : `Plano individual (1 beneficiário: o paciente selecionado).`}
        </div>
        <div class="com-patient-meta" style="color:#b45309;">
          Estes valores são copiados do catálogo agora (snapshot): alterar o plano no catálogo depois não muda este contrato.
        </div>
      </div>
    `;
    els.planoResumo.hidden = false;
  }

  function syncTipoVinculoModal() {
    modalVinculo.sincronizarTipo();
  }

  function applyComboDataToForm() {
    const opt = els.comboSelect?.selectedOptions?.[0];
    if (!opt || !opt.value) return;

    const sessoes = Number(opt.dataset.sessoes || 0);
    const preco = Number(opt.dataset.preco || 0);

    if (!Number(els.sessoesContratadas.value || 0)) {
      els.sessoesContratadas.value = sessoes || "";
    }

    if (!Number(els.valorTotal.value || 0)) {
      els.valorTotal.value = preco || "";
    }
  }

  function resetVinculoForm() {
    els.formVinculo?.reset();
    if (els.vinculoId) els.vinculoId.value = "";
    syncTipoVinculoForm();
    clearPacienteSelecionado();
  }

  async function submitVinculoForm(ev) {
    ev.preventDefault();

    const pacienteId = els.pacienteId?.value?.trim();
    if (!pacienteId) {
      toast("Selecione um paciente.");
      return;
    }

    const vinculoExistente = getExistingVinculoByPaciente(pacienteId);
    if (vinculoExistente) {
      toast(`"${state.pacienteSelecionado?.nome || "Paciente"}" já está cadastrado. Abra o card e edite o vínculo existente.`);
      return;
    }

    const tipo = els.tipoVinculo.value;

    const payload = {
      paciente_id: Number(pacienteId),
      tipo,
      combo_id: tipo === "combo" && els.comboSelect.value ? Number(els.comboSelect.value) : null,
      nome_plano: "",
      sessoes_contratadas: Number(els.sessoesContratadas.value || 0),
      valor_total: Number(els.valorTotal.value || 0),
      forma_pagamento: els.formaPagamento.value,
      data_inicio: els.dataInicioVinculo.value || "",
      data_fim: els.dataFimVinculo.value || "",
      recorrente: boolValue(els.vinculoRecorrente),
      renovacao_automatica: boolValue(els.vinculoRenovacao),
      observacoes: els.observacoesVinculo.value.trim(),
      status: "ativo"
    };

    if (payload.tipo === "combo" && !payload.combo_id) {
      toast("Selecione um combo.");
      return;
    }

    if (payload.tipo === "plano") {
      payload.plano_catalogo_id = els.planoCatalogoSelect?.value ? Number(els.planoCatalogoSelect.value) : null;

      if (!payload.plano_catalogo_id) {
        toast("Selecione um plano do catálogo (plano_catalogo_id).");
        return;
      }
    }

    setLoading(els.btnSalvarVinculo, true);

    try {
      await requestJSON("/financeiro/api/pacientes-planos", {
        method: "POST",
        body: JSON.stringify(payload)
      });

      toast("Vínculo salvo com sucesso.");
      resetVinculoForm();
      await loadVinculos();
      await loadPacientesSemVinculo();
    } catch (err) {
      toast(err.message || "Não foi possível salvar o vínculo.");
    } finally {
      setLoading(els.btnSalvarVinculo, false);
    }
  }

  // =========================================================
  // CONTROLE / VÍNCULOS
  // =========================================================
  async function loadVinculos() {
    const params = new URLSearchParams();
    const q = els.filtroVinculoBusca?.value?.trim() || "";
    const tipo = els.filtroVinculoTipo?.value || "";
    const status = els.filtroVinculoStatus?.value || "";
    const perto = boolValue(els.filtroPertoAcabar);

    if (q) params.set("q", q);
    if (tipo) params.set("tipo", tipo);
    if (status) params.set("status", status);
    if (perto) params.set("perto_de_acabar", "1");

    const data = await requestJSON(`/financeiro/api/pacientes-planos?${params.toString()}`);
    state.vinculos = Array.isArray(data.items) ? data.items : [];
    applyFiltroVinculos();
    updateStats();
  }

  function applyFiltroVinculos() {
    const q = normalizeText(els.filtroVinculoBusca?.value || "");
    const tipo = normalizeText(els.filtroVinculoTipo?.value || "");
    const status = normalizeText(els.filtroVinculoStatus?.value || "");
    const soPerto = boolValue(els.filtroPertoAcabar);

    state.vinculosFiltrados = state.vinculos.filter(item => {
      const texto = [
        item.paciente_nome,
        item.paciente_cpf,
        item.paciente_cns,
        item.combo_nome,
        item.nome_plano,
        item.tipo,
        item.observacoes,
      ].map(normalizeText).join(" ");

      const matchQ = !q || texto.includes(q);
      const matchTipo = !tipo || normalizeText(item.tipo) === tipo;
      const matchStatus = !status || normalizeText(item.status) === status;
      const matchPerto = !soPerto || !!Number(item.perto_de_acabar);

      return matchQ && matchTipo && matchStatus && matchPerto;
    });

    state.paginaAtual = 1;
    renderVinculosCards();
  }

  function getPaginaAtualItems() {
    const inicio = (state.paginaAtual - 1) * state.itensPorPagina;
    return state.vinculosFiltrados.slice(inicio, inicio + state.itensPorPagina);
  }

  function renderPaginacao() {
    if (!els.cardsVinculos) return;

    let wrap = $("#comPaginacao");
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.id = "comPaginacao";
      wrap.className = "com-actions";
      wrap.style.marginTop = "16px";
      els.cardsVinculos.insertAdjacentElement("afterend", wrap);
    }

    if (state.modoControle !== "vinculos") {
      wrap.innerHTML = "";
      return;
    }

    const total = state.vinculosFiltrados.length;
    const pag = paginacaoHtml(state.paginaAtual, total, state.itensPorPagina);
    state.paginaAtual = pag.paginaAtual;

    wrap.innerHTML = pag.html;

    wrap.onclick = (ev) => {
      const pageBtn = ev.target.closest("[data-page]");
      const actionBtn = ev.target.closest("[data-page-action]");

      if (pageBtn) {
        state.paginaAtual = Number(pageBtn.dataset.page);
        renderVinculosCards();
        return;
      }

      if (actionBtn) {
        const totalLocal = Math.max(1, Math.ceil(state.vinculosFiltrados.length / state.itensPorPagina));
        if (actionBtn.dataset.pageAction === "prev" && state.paginaAtual > 1) {
          state.paginaAtual -= 1;
        }
        if (actionBtn.dataset.pageAction === "next" && state.paginaAtual < totalLocal) {
          state.paginaAtual += 1;
        }
        renderVinculosCards();
      }
    };
  }

  function renderVinculosCards() {
    if (!els.cardsVinculos) return;

    const items = getPaginaAtualItems();

    if (!items.length) {
      els.cardsVinculos.innerHTML = `
        <div class="com-empty">
          <strong>Nenhum vínculo encontrado.</strong>
          <span>Os pacientes vinculados aparecerão aqui em formato de cards.</span>
        </div>
      `;
      renderPaginacao();
      return;
    }

    els.cardsVinculos.innerHTML = items.map(vinculoCardHtml).join("");

    renderPaginacao();
  }

  // =========================================================
  // PACIENTES SEM VÍNCULO
  // =========================================================
  async function loadPacientesSemVinculo() {
    const params = new URLSearchParams();
    const q = els.filtroSemVinculoBusca?.value?.trim() || "";
    const apenas = boolValue(els.filtroSemVinculoAtendimento);

    if (q) params.set("q", q);
    params.set("apenas_com_atendimento", apenas ? "1" : "0");

    const data = await requestJSON(`/financeiro/api/pacientes-sem-vinculo?${params.toString()}`);
    state.pacientesSemVinculo = Array.isArray(data.items) ? data.items : [];
    renderPacientesSemVinculo();
  }

  function renderPacientesSemVinculo() {
    if (!els.cardsSemVinculo) return;

    const items = state.pacientesSemVinculo;

    if (!items.length) {
      els.cardsSemVinculo.innerHTML = `
        <div class="com-empty">
          <strong>Nenhum paciente sem vínculo encontrado.</strong>
          <span>Quando houver pacientes fora do fluxo comercial, eles aparecerão aqui.</span>
        </div>
      `;
      return;
    }

    els.cardsSemVinculo.innerHTML = semVinculoCardsHtml(items);
  }

  // =========================================================
  // MODAL VÍNCULO
  // =========================================================
  function openVinculoModal(id) {
    return modalVinculo.abrir(id);
  }

  function submitVinculoModal(ev) {
    return modalVinculo.enviar(ev);
  }

  function desvincularAtendimentosModal() {
    return modalVinculo.desvincular();
  }

  function deleteVinculoModal() {
    return modalVinculo.excluir();
  }

  // =========================================================
  // STATS
  // =========================================================
  function updateStats() {
    if (els.statCombos) {
      els.statCombos.textContent = state.combos.filter(c => Number(c.ativo)).length;
    }

    if (els.statPlanos) {
      els.statPlanos.textContent = state.vinculos.filter(v => v.tipo === "plano" && normalizeText(v.status) === "ativo").length;
    }

    if (els.statVinculos) {
      els.statVinculos.textContent = state.vinculos.length;
    }

    if (els.statPertoAcabar) {
      els.statPertoAcabar.textContent = state.vinculos.filter(v => Number(v.perto_de_acabar)).length;
    }
  }

  // =========================================================
  // EVENTS
  // =========================================================
  function bindEvents() {
    // painéis
    els.btnToggleCadastroCombo?.addEventListener("click", () => {
      togglePanel(els.painelCadastroCombo, els.btnToggleCadastroCombo);
    });

    els.btnToggleGestaoCombos?.addEventListener("click", async () => {
      togglePanel(els.painelGestaoCombos, els.btnToggleGestaoCombos);
      if (!els.painelGestaoCombos.hidden) {
        await loadCombos();
      }
    });

    els.btnFecharCadastroCombo?.addEventListener("click", () => {
      togglePanel(els.painelCadastroCombo, els.btnToggleCadastroCombo, false);
    });

    els.btnFecharGestaoCombos?.addEventListener("click", () => {
      togglePanel(els.painelGestaoCombos, els.btnToggleGestaoCombos, false);
    });

    // abas controle
    els.abaVinculos?.addEventListener("click", () => setModeControle("vinculos"));
    els.abaSemVinculo?.addEventListener("click", () => setModeControle("sem-vinculo"));

    // combos
    els.formCombo?.addEventListener("submit", submitComboForm);
    els.btnLimparCombo?.addEventListener("click", resetComboForm);
    els.btnAtualizarCombos?.addEventListener("click", () => loadCombos().catch(err => toast(err.message)));
    els.filtroComboBusca?.addEventListener("input", debounce(() => loadCombos().catch(err => toast(err.message)), 250));
    els.filtroComboAtivo?.addEventListener("change", () => loadCombos().catch(err => toast(err.message)));
    els.btnSalvarGestaoCombos?.addEventListener("click", saveAllCombosInline);

    els.listaCombos?.addEventListener("click", (ev) => {
      const btnExcluir = ev.target.closest("[data-action='excluir-combo']");
      if (btnExcluir) {
        deleteCombo(btnExcluir.dataset.id);
      }
    });

    // busca paciente
    els.pacienteBusca?.addEventListener("input", debounce((ev) => {
      buscarPacientes(ev.target.value);
    }, 250));

    els.pacienteResultados?.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-action='select-paciente']");
      if (!btn) return;
      selectPacienteFromDataset(btn.dataset);
    });

    // form vínculo
    els.tipoVinculo?.addEventListener("change", syncTipoVinculoForm);
    els.comboSelect?.addEventListener("change", applyComboDataToForm);
    els.planoCatalogoSelect?.addEventListener("change", applyPlanoCatalogoToForm);
    els.formVinculo?.addEventListener("submit", submitVinculoForm);
    els.btnLimparVinculo?.addEventListener("click", resetVinculoForm);

    // filtros do controle
    els.btnAtualizarVinculos?.addEventListener("click", () => loadVinculos().catch(err => toast(err.message)));
    els.filtroVinculoBusca?.addEventListener("input", debounce(applyFiltroVinculos, 200));
    els.filtroVinculoTipo?.addEventListener("change", applyFiltroVinculos);
    els.filtroVinculoStatus?.addEventListener("change", applyFiltroVinculos);
    els.filtroPertoAcabar?.addEventListener("change", () => loadVinculos().catch(err => toast(err.message)));

    // pacientes sem vínculo
    els.btnAtualizarSemVinculo?.addEventListener("click", () => loadPacientesSemVinculo().catch(err => toast(err.message)));
    els.filtroSemVinculoBusca?.addEventListener("input", debounce(() => loadPacientesSemVinculo().catch(err => toast(err.message)), 250));
    els.filtroSemVinculoAtendimento?.addEventListener("change", () => loadPacientesSemVinculo().catch(err => toast(err.message)));

    els.cardsSemVinculo?.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-action='usar-paciente-sem-vinculo']");
      if (!btn) return;

      setModeControle("vinculos");
      selectPacienteFromDataset(btn.dataset);

      const topSection = els.formVinculo?.closest(".com-card");
      if (topSection) {
        topSection.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });

    // cards
    els.cardsVinculos?.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-action='editar-vinculo']");
      if (!btn) return;
      openVinculoModal(btn.dataset.id);
    });

    // modal
    els.mvTipo?.addEventListener("change", syncTipoVinculoModal);
    els.formModalVinculo?.addEventListener("submit", submitVinculoModal);
    els.btnDesvincularAtendimentosModal?.addEventListener("click", desvincularAtendimentosModal);
    els.btnExcluirVinculoModal?.addEventListener("click", deleteVinculoModal);
    els.btnFecharVinculoModal?.addEventListener("click", () => closeDialog(els.modalVinculo));

    // beneficiários (beneficiarios.js): quem entra/sai de um plano familiar muda a lista "sem vínculo"
    document.addEventListener("financeiro:beneficiarios-alterados", () => {
      loadPacientesSemVinculo().catch(err => toast(err.message));
    });

    // fechar busca ao clicar fora
    document.addEventListener("click", (ev) => {
      if (!ev.target.closest(".com-patient-search")) {
        if (els.pacienteResultados) {
          els.pacienteResultados.hidden = true;
        }
      }
    });
  }

  // =========================================================
  // INIT
  // =========================================================
  async function init() {
    bindEvents();
    syncTipoVinculoForm();
    syncTipoVinculoModal();
    setModeControle("vinculos");

    try {
      await Promise.all([
        loadCombos(),
        loadVinculos(),
        loadPacientesSemVinculo(),
      ]);
    } catch (err) {
      toast(err.message || "Erro ao carregar a tela comercial.");
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();