(() => {
  "use strict";

  // =========================================================
  // HELPERS
  // =========================================================
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const state = {
    combos: [],
    vinculos: [],
    vinculosFiltrados: [],
    pacientesSemVinculo: [],
    pacienteSelecionado: null,
    paginaAtual: 1,
    itensPorPagina: 12,
    modoControle: "vinculos",
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function money(v) {
    const num = Number(v || 0);
    return num.toLocaleString("pt-BR", {
      style: "currency",
      currency: "BRL"
    });
  }

  function digits(v) {
    return String(v || "").replace(/\D+/g, "");
  }

  function boolValue(el) {
    return !!(el && el.checked);
  }

  function normalizeText(v) {
    return String(v || "").trim().toLowerCase();
  }

  function parseDateSafe(value) {
    if (!value) return null;
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  function formatDateBR(value) {
    const d = parseDateSafe(value);
    if (!d) return "";
    return d.toLocaleDateString("pt-BR");
  }

  function diffDays(fromDate, toDate) {
    const oneDay = 1000 * 60 * 60 * 24;
    const a = new Date(fromDate.getFullYear(), fromDate.getMonth(), fromDate.getDate());
    const b = new Date(toDate.getFullYear(), toDate.getMonth(), toDate.getDate());
    return Math.round((b - a) / oneDay);
  }

  function toast(msg) {
    window.alert(msg);
  }

  function debounce(fn, delay = 250) {
    let timer = null;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), delay);
    };
  }

  function setLoading(btn, isLoading, textLoading = "Salvando...") {
    if (!btn) return;
    if (isLoading) {
      btn.dataset.originalText = btn.textContent;
      btn.disabled = true;
      btn.textContent = textLoading;
    } else {
      btn.disabled = false;
      btn.textContent = btn.dataset.originalText || btn.textContent;
    }
  }

  async function requestJSON(url, options = {}) {
    const config = {
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {})
      },
      ...options
    };

    const res = await fetch(url, config);
    let data = null;

    try {
      data = await res.json();
    } catch {
      data = null;
    }

    if (!res.ok || !data || data.ok === false) {
      const erro = data?.erro || `Erro na requisição (${res.status}).`;
      throw new Error(erro);
    }

    return data;
  }

  function openDialog(dialog) {
    if (!dialog) return;
    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    } else {
      dialog.classList.add("open");
    }
  }

  function closeDialog(dialog) {
    if (!dialog) return;
    if (typeof dialog.close === "function") {
      dialog.close();
    } else {
      dialog.classList.remove("open");
    }
  }

  function togglePanel(panel, button, forceState = null) {
    if (!panel || !button) return;
    const shouldOpen = forceState !== null ? forceState : panel.hidden;
    panel.hidden = !shouldOpen;
    button.setAttribute("aria-expanded", String(shouldOpen));
  }

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
  // DATAS / STATUS
  // =========================================================
  function buildDatasResumo(item) {
    const datasResumo = item.datas_resumo || "";
    const diaSemana = item.dia_semana || "";
    const dataInicio = item.data_inicio || "";
    const dataFim = item.data_fim || "";

    if (datasResumo && String(datasResumo).trim()) {
      return String(datasResumo).trim();
    }

    if (dataInicio && dataFim) {
      return `${formatDateBR(dataInicio)} até ${formatDateBR(dataFim)}`;
    }

    if (dataInicio && !dataFim) {
      return `Início: ${formatDateBR(dataInicio)}`;
    }

    if (!dataInicio && dataFim) {
      return `Até ${formatDateBR(dataFim)}`;
    }

    if (diaSemana && String(diaSemana).trim()) {
      return `Recorrente · ${diaSemana}`;
    }

    return "Sem datas definidas";
  }

  function getDataStatus(item) {
    const indeterminado = !!item.indeterminado;
    const dia = item.dia_semana || "";
    const dataFim = parseDateSafe(item.data_fim);

    if (indeterminado || dia) {
      return { classe: "", label: "" };
    }

    if (!dataFim) {
      return { classe: "", label: "" };
    }

    const hoje = new Date();
    const dias = diffDays(hoje, dataFim);

    if (dias < 0) {
      return { classe: "is-expired", label: "Encerrado" };
    }

    if (dias <= 7) {
      return { classe: "is-warning", label: "Encerrando" };
    }

    return { classe: "", label: "" };
  }

  function getConsumoClasse(item) {
    if (normalizeText(item.status) === "encerrado" || Number(item.acabou)) {
      return "is-encerrado";
    }
    if (Number(item.perto_de_acabar)) {
      return "is-warning";
    }
    return "";
  }

  function percentualConsumo(item) {
    const pct = Number(item.percentual_usado || 0);
    if (pct < 0) return 0;
    if (pct > 100) return 100;
    return pct;
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
  async function buscarPacientes(q) {
    const termo = String(q || "").trim();

    if (termo.length < 2) {
      if (els.pacienteResultados) {
        els.pacienteResultados.hidden = true;
        els.pacienteResultados.innerHTML = "";
      }
      return;
    }

    try {
      const data = await requestJSON(`/financeiro/api/pacientes/buscar?q=${encodeURIComponent(termo)}`);
      const items = Array.isArray(data.items) ? data.items : [];

      if (!items.length) {
        els.pacienteResultados.hidden = false;
        els.pacienteResultados.innerHTML = `<div class="com-empty">Nenhum paciente encontrado.</div>`;
        return;
      }

      els.pacienteResultados.hidden = false;
      els.pacienteResultados.innerHTML = items.map(item => {
        const cpf = digits(item.cpf || "");
        const cns = digits(item.cns || "");

        return `
          <button type="button"
                  class="com-search-item"
                  data-action="select-paciente"
                  data-id="${item.id}"
                  data-nome="${escapeHtml(item.nome || "")}"
                  data-cpf="${escapeHtml(cpf)}"
                  data-cns="${escapeHtml(cns)}"
                  data-nascimento="${escapeHtml(item.nascimento || "")}"
                  data-telefone="${escapeHtml(item.telefone || "")}">
            <strong>${escapeHtml(item.nome || "Sem nome")}</strong>
            <span>
              ${cpf ? `CPF: ${escapeHtml(cpf)} · ` : ""}
              ${cns ? `CNS: ${escapeHtml(cns)} · ` : ""}
              ${item.telefone ? `Tel: ${escapeHtml(item.telefone)}` : "Sem telefone"}
            </span>
          </button>
        `;
      }).join("");
    } catch (err) {
      els.pacienteResultados.hidden = false;
      els.pacienteResultados.innerHTML = `<div class="com-empty">${escapeHtml(err.message || "Erro ao buscar pacientes.")}</div>`;
    }
  }

  function getExistingVinculoByPaciente(pacienteId) {
    return state.vinculos.find(v => String(v.paciente_id || "") === String(pacienteId || ""));
  }

  function selectPacienteFromDataset(dataset) {
    const paciente = {
      id: dataset.id || "",
      nome: dataset.nome || "",
      cpf: dataset.cpf || "",
      cns: dataset.cns || "",
      nascimento: dataset.nascimento || "",
      telefone: dataset.telefone || ""
    };

    state.pacienteSelecionado = paciente;

    if (els.pacienteId) {
      els.pacienteId.value = paciente.id || "";
    }

    const vinculoExistente = getExistingVinculoByPaciente(paciente.id);

    els.pacienteSelecionadoBox.innerHTML = `
      <div class="com-patient-card">
        <strong>${escapeHtml(paciente.nome || "Sem nome")}</strong>
        <div class="com-patient-meta">
          ${paciente.cpf ? `CPF: ${escapeHtml(paciente.cpf)} · ` : ""}
          ${paciente.cns ? `CNS: ${escapeHtml(paciente.cns)} · ` : ""}
          ${paciente.telefone ? `Tel: ${escapeHtml(paciente.telefone)} · ` : ""}
          ${paciente.nascimento ? `Nasc.: ${escapeHtml(paciente.nascimento)}` : ""}
        </div>
        ${
          vinculoExistente
            ? `<div class="com-patient-meta" style="color:#b45309;font-weight:700;">
                Este paciente já possui vínculo cadastrado. Atualize/editando o registro existente.
              </div>`
            : ""
        }
      </div>
    `;

    els.pacienteResultados.hidden = true;
    els.pacienteResultados.innerHTML = "";

    if (vinculoExistente) {
      toast("Este paciente já está cadastrado no comercial. Edite o vínculo existente.");
    }
  }

  function clearPacienteSelecionado() {
    state.pacienteSelecionado = null;
    if (els.pacienteId) els.pacienteId.value = "";

    if (els.pacienteSelecionadoBox) {
      els.pacienteSelecionadoBox.innerHTML = `<div class="com-patient-empty">Nenhum paciente selecionado.</div>`;
    }
  }

  // =========================================================
  // FORM VÍNCULO
  // =========================================================
  function syncTipoVinculoForm() {
    const tipo = els.tipoVinculo?.value || "combo";
    const isCombo = tipo === "combo";

    if (els.fieldComboSelect) els.fieldComboSelect.hidden = !isCombo;
    if (els.fieldNomePlano) els.fieldNomePlano.hidden = isCombo;
  }

  function syncTipoVinculoModal() {
    const tipo = els.mvTipo?.value || "combo";
    const isCombo = tipo === "combo";

    if (els.mvFieldCombo) els.mvFieldCombo.hidden = !isCombo;
    if (els.mvFieldNomePlano) els.mvFieldNomePlano.hidden = isCombo;
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
      nome_plano: tipo === "plano" ? (els.nomePlano.value || "").trim() : "",
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

    if (payload.tipo === "plano" && !payload.nome_plano) {
      toast("Informe o nome do plano.");
      return;
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
    const totalPaginas = Math.max(1, Math.ceil(total / state.itensPorPagina));

    if (state.paginaAtual > totalPaginas) {
      state.paginaAtual = totalPaginas;
    }

    const botoes = [];

    botoes.push(`
      <button type="button" class="com-btn com-btn--ghost" data-page-action="prev" ${state.paginaAtual === 1 ? "disabled" : ""}>
        ← Anterior
      </button>
    `);

    for (let i = 1; i <= totalPaginas; i++) {
      if (
        i === 1 ||
        i === totalPaginas ||
        Math.abs(i - state.paginaAtual) <= 1
      ) {
        botoes.push(`
          <button type="button" class="com-btn ${i === state.paginaAtual ? "com-btn--primary" : "com-btn--ghost"}" data-page="${i}">
            ${i}
          </button>
        `);
      } else if (
        (i === state.paginaAtual - 2 && i > 1) ||
        (i === state.paginaAtual + 2 && i < totalPaginas)
      ) {
        botoes.push(`<span class="com-pag-ellipsis" style="align-self:center;padding:0 4px;">…</span>`);
      }
    }

    botoes.push(`
      <button type="button" class="com-btn com-btn--ghost" data-page-action="next" ${state.paginaAtual === totalPaginas ? "disabled" : ""}>
        Próxima →
      </button>
    `);

    wrap.innerHTML = `
      <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;width:100%;">
        ${botoes.join("")}
        <span style="margin-left:auto;color:#64748b;font-size:.9rem;">
          ${total} registro(s) · ${totalPaginas} página(s)
        </span>
      </div>
    `;

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

    els.cardsVinculos.innerHTML = items.map(item => {
      const nomeCombo = item.combo_nome || item.nome_plano || "Sem combo/plano";
      const contratadas = Number(item.sessoes_contratadas || 0);
      const usadas = Number(item.sessoes_usadas || 0);
      const restantes = Number(item.sessoes_restantes || 0);
      const resumoDatas = buildDatasResumo(item);
      const dataStatus = getDataStatus(item);
      const classeConsumo = getConsumoClasse(item);
      const progresso = percentualConsumo(item);
      const tipoLabel = item.tipo === "combo" ? "Combo" : "Plano";

      return `
        <article class="com-vinculo-card ${classeConsumo} ${dataStatus.classe}" data-vinculo-id="${item.id}">
          <div class="com-vinculo-top">
            <div class="com-vinculo-ident">
              <h3>${escapeHtml(item.paciente_nome || "Sem nome")}</h3>
              <div class="com-vinculo-sub">
                ${escapeHtml(item.paciente_cpf || item.paciente_cns || "Sem CPF/CNS")}
              </div>
            </div>

            <div class="com-vinculo-meta">
              <span class="com-badge ${item.tipo === "combo" ? "com-badge--combo" : "com-badge--plan"}">${tipoLabel}</span>
              <span class="com-badge com-badge--status">${escapeHtml(item.status || "ativo")}</span>
              ${Number(item.perto_de_acabar) ? `<span class="com-badge com-badge--warn">Perto de acabar</span>` : ""}
              ${Number(item.acabou) ? `<span class="com-badge com-badge--danger">Sem saldo</span>` : ""}
              ${dataStatus.label ? `<span class="com-badge ${dataStatus.classe === "is-expired" ? "com-badge--danger" : "com-badge--warn"}">${dataStatus.label}</span>` : ""}
            </div>
          </div>

          <div class="com-vinculo-grid">
            <div class="com-mini">
              <span>Vínculo</span>
              <strong>${escapeHtml(nomeCombo)}</strong>
            </div>

            <div class="com-mini">
              <span>Valor</span>
              <strong>${money(item.valor_total)}</strong>
            </div>

            <div class="com-mini ${Number(item.perto_de_acabar) ? "com-mini--warn" : ""}">
              <span>Usadas</span>
              <strong>${usadas}</strong>
            </div>

            <div class="com-mini ${Number(item.acabou) ? "com-mini--danger" : Number(item.perto_de_acabar) ? "com-mini--warn" : ""}">
              <span>Restantes</span>
              <strong>${restantes}</strong>
            </div>
          </div>

          <div class="com-consumo">
            <div class="com-consumo-head">
              <span class="com-consumo-title">Consumo de sessões</span>
              <span class="com-consumo-numbers">${usadas} / ${contratadas || 0}</span>
            </div>
            <div class="com-progress">
              <i style="width:${progresso}%;"></i>
            </div>
          </div>

          <div class="com-vinculo-footer">
            <div class="com-vinculo-datas">
              <strong>Datas / recorrência</strong>
              <span>${escapeHtml(resumoDatas)}</span>
              ${item.observacoes ? `<span>${escapeHtml(item.observacoes)}</span>` : ""}
            </div>

            <div class="com-vinculo-actions">
              <button type="button" class="com-btn com-btn--ghost" data-action="editar-vinculo" data-id="${item.id}">
                Editar
              </button>
            </div>
          </div>
        </article>
      `;
    }).join("");

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

    els.cardsSemVinculo.innerHTML = items.map(item => {
      const cpf = digits(item.cpf || "");
      const cns = digits(item.cns || "");

      return `
        <article class="com-sem-vinculo-card" data-paciente-id="${item.id}">
          <div class="com-sem-vinculo-top">
            <div>
              <h3>${escapeHtml(item.nome || "Sem nome")}</h3>
              <p>
                ${cpf ? `CPF: ${escapeHtml(cpf)} · ` : ""}
                ${cns ? `CNS: ${escapeHtml(cns)} · ` : ""}
                ${item.telefone ? `Tel: ${escapeHtml(item.telefone)} · ` : ""}
                ${item.nascimento ? `Nasc.: ${escapeHtml(item.nascimento)}` : ""}
              </p>
            </div>

            <div class="com-badges">
              <span class="com-badge com-badge--soft">Sem vínculo</span>
            </div>
          </div>

          <div class="com-sem-vinculo-actions">
            <button
              type="button"
              class="com-btn com-btn--primary"
              data-action="usar-paciente-sem-vinculo"
              data-id="${item.id}"
              data-nome="${escapeHtml(item.nome || "")}"
              data-cpf="${escapeHtml(cpf)}"
              data-cns="${escapeHtml(cns)}"
              data-nascimento="${escapeHtml(item.nascimento || "")}"
              data-telefone="${escapeHtml(item.telefone || "")}">
              Vincular agora
            </button>
          </div>
        </article>
      `;
    }).join("");
  }

  // =========================================================
  // MODAL VÍNCULO
  // =========================================================
  function fillModalResumo(item) {
    const contratadas = Number(item.sessoes_contratadas || 0);
    const usadas = Number(item.sessoes_usadas || 0);
    const restantes = Number(item.sessoes_restantes ?? Math.max(contratadas - usadas, 0));
    const tipoLabel = item.tipo === "combo" ? "Combo" : "Plano";

    if (els.mvBadgeTipo) {
      els.mvBadgeTipo.textContent = tipoLabel;
      els.mvBadgeTipo.className = `com-badge ${item.tipo === "combo" ? "com-badge--combo" : "com-badge--plan"}`;
    }

    if (els.mvBadgeConsumo) {
      els.mvBadgeConsumo.textContent = `${usadas} / ${contratadas}`;
    }

    if (els.mvBadgeAlerta) {
      const show = !!Number(item.perto_de_acabar);
      els.mvBadgeAlerta.hidden = !show;
      els.mvBadgeAlerta.textContent = show ? "Perto de acabar" : "Perto de acabar";
    }

    if (els.mvSessoesRestantes) {
      els.mvSessoesRestantes.value = restantes;
    }
  }

  async function openVinculoModal(id) {
    try {
      const data = await requestJSON(`/financeiro/api/pacientes-planos/${id}`);
      const item = data.item;
      if (!item) return;

      els.mvId.value = item.id || "";
      els.mvPacienteNome.textContent = item.paciente_nome || "—";
      els.mvTipo.value = item.tipo || "combo";
      if (els.mvComboId) els.mvComboId.value = item.combo_id || "";
      if (els.mvNomePlano) els.mvNomePlano.value = item.nome_plano || "";
      els.mvSessoesContratadas.value = Number(item.sessoes_contratadas || 0);
      els.mvSessoesUsadas.value = Number(item.sessoes_usadas || 0);
      els.mvValorTotal.value = Number(item.valor_total || 0);
      els.mvFormaPagamento.value = item.forma_pagamento || "";
      els.mvStatus.value = item.status || "ativo";
      els.mvDataInicio.value = item.data_inicio || "";
      els.mvDataFim.value = item.data_fim || "";
      els.mvRecorrente.checked = !!Number(item.recorrente);
      els.mvRenovacaoAutomatica.checked = !!Number(item.renovacao_automatica);
      els.mvObservacoes.value = item.observacoes || "";

      syncTipoVinculoModal();
      fillModalResumo(item);
      openDialog(els.modalVinculo);
    } catch (err) {
      toast(err.message || "Não foi possível abrir o vínculo.");
    }
  }

  async function submitVinculoModal(ev) {
    ev.preventDefault();

    const id = els.mvId.value.trim();
    if (!id) return;

    const tipo = els.mvTipo.value;

    const payload = {
      tipo,
      combo_id: tipo === "combo" && els.mvComboId.value ? Number(els.mvComboId.value) : null,
      nome_plano: tipo === "plano" ? (els.mvNomePlano.value || "").trim() : "",
      sessoes_contratadas: Number(els.mvSessoesContratadas.value || 0),
      valor_total: Number(els.mvValorTotal.value || 0),
      forma_pagamento: els.mvFormaPagamento.value,
      status: els.mvStatus.value,
      data_inicio: els.mvDataInicio.value || "",
      data_fim: els.mvDataFim.value || "",
      recorrente: boolValue(els.mvRecorrente),
      renovacao_automatica: boolValue(els.mvRenovacaoAutomatica),
      observacoes: els.mvObservacoes.value.trim(),
    };

    if (payload.tipo === "combo" && !payload.combo_id) {
      toast("Selecione um combo.");
      return;
    }

    if (payload.tipo === "plano" && !payload.nome_plano) {
      toast("Informe o nome do plano.");
      return;
    }

    try {
      await requestJSON(`/financeiro/api/pacientes-planos/${id}`, {
        method: "PUT",
        body: JSON.stringify(payload)
      });

      toast("Vínculo atualizado com sucesso.");
      closeDialog(els.modalVinculo);
      await loadVinculos();
      await loadPacientesSemVinculo();
    } catch (err) {
      toast(err.message || "Não foi possível atualizar o vínculo.");
    }
  }

  async function desvincularAtendimentosModal() {
    const id = els.mvId.value.trim();
    if (!id) return;

    const confirmed = window.confirm("Deseja desvincular os atendimentos deste combo/plano?");
    if (!confirmed) return;

    try {
      await requestJSON(`/financeiro/api/pacientes-planos/${id}/desvincular-atendimentos`, {
        method: "POST"
      });

      toast("Atendimentos desvinculados com sucesso.");
      closeDialog(els.modalVinculo);
      await loadVinculos();
    } catch (err) {
      toast(err.message || "Não foi possível desvincular os atendimentos.");
    }
  }

  async function deleteVinculoModal() {
    const id = els.mvId.value.trim();
    if (!id) return;

    const confirmed = window.confirm("Deseja realmente excluir este vínculo?");
    if (!confirmed) return;

    try {
      await requestJSON(`/financeiro/api/pacientes-planos/${id}`, {
        method: "DELETE"
      });

      toast("Vínculo removido com sucesso.");
      closeDialog(els.modalVinculo);
      await loadVinculos();
      await loadPacientesSemVinculo();
    } catch (err) {
      toast(err.message || "Não foi possível excluir o vínculo.");
    }
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