(() => {
  "use strict";

  // =========================================================
  // HELPERS
  // =========================================================
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const state = {
    recebimentos: [],
    lancamentos: [],
    resumo: {},
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

  function normalizeText(v) {
    return String(v || "").trim().toLowerCase();
  }

  function formatDateBR(value) {
    if (!value) return "—";
    try {
      const d = new Date(`${String(value).slice(0, 10)}T00:00:00`);
      if (Number.isNaN(d.getTime())) return String(value);
      return d.toLocaleDateString("pt-BR");
    } catch {
      return String(value);
    }
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

  function setLoading(btn, isLoading, loadingText = "Carregando...") {
    if (!btn) return;
    if (isLoading) {
      btn.dataset.originalText = btn.textContent;
      btn.disabled = true;
      btn.textContent = loadingText;
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

  // =========================================================
  // ELEMENTOS
  // =========================================================
  const els = {
    // filtros globais
    fDataIni: $("#fDataIni"),
    fDataFim: $("#fDataFim"),
    fCompetencia: $("#fCompetencia"),
    fTipoLanc: $("#fTipoLanc"),
    fStatusLanc: $("#fStatusLanc"),
    fBuscaLanc: $("#fBuscaLanc"),
    btnAplicarFinanceiro: $("#btnAplicarFinanceiro"),
    btnLimparFinanceiro: $("#btnLimparFinanceiro"),

    // KPIs
    kpiSaldo: $("#kpiSaldo"),
    kpiEntradas: $("#kpiEntradas"),
    kpiSaidas: $("#kpiSaidas"),
    kpiPendentes: $("#kpiPendentes"),

    // recebimentos
    fRecebBusca: $("#fRecebBusca"),
    fRecebStatus: $("#fRecebStatus"),
    fRecebTipo: $("#fRecebTipo"),
    btnAtualizarRecebimentos: $("#btnAtualizarRecebimentos"),
    finCardsRecebimentos: $("#finCardsRecebimentos"),

    // lançamento manual
    formLancamentoManual: $("#formLancamentoManual"),
    lancTipo: $("#lancTipo"),
    lancCategoria: $("#lancCategoria"),
    lancDescricao: $("#lancDescricao"),
    lancValor: $("#lancValor"),
    lancForma: $("#lancForma"),
    lancStatus: $("#lancStatus"),
    lancVencimento: $("#lancVencimento"),
    lancCompetencia: $("#lancCompetencia"),
    lancObservacoes: $("#lancObservacoes"),
    btnSalvarLancamento: $("#btnSalvarLancamento"),
    btnLimparLancamento: $("#btnLimparLancamento"),

    // cards de lançamentos
    btnAtualizarLancamentos: $("#btnAtualizarLancamentos"),
    finCardsLancamentos: $("#finCardsLancamentos"),

    // fechamento
    sumEntradasPagas: $("#sumEntradasPagas"),
    sumSaidasPagas: $("#sumSaidasPagas"),
    sumEntradasPendentes: $("#sumEntradasPendentes"),
    sumSaldoProjetado: $("#sumSaldoProjetado"),
    finResumoCategorias: $("#finResumoCategorias"),
    finResumoDias: $("#finResumoDias"),

    // modal lançamento
    modalLancamento: $("#modalLancamento"),
    formModalLancamento: $("#formModalLancamento"),
    mlId: $("#mlId"),
    mlTipo: $("#mlTipo"),
    mlCategoria: $("#mlCategoria"),
    mlDescricao: $("#mlDescricao"),
    mlValor: $("#mlValor"),
    mlFormaPagamento: $("#mlFormaPagamento"),
    mlStatus: $("#mlStatus"),
    mlVencimento: $("#mlVencimento"),
    mlDataPagamento: $("#mlDataPagamento"),
    mlCompetencia: $("#mlCompetencia"),
    mlObservacoes: $("#mlObservacoes"),
    btnExcluirLancamentoModal: $("#btnExcluirLancamentoModal"),
    btnFecharLancamentoModal: $("#btnFecharLancamentoModal"),
  };

  // =========================================================
  // QUERY PARAMS
  // =========================================================
  function getGlobalFilterParams() {
    const params = new URLSearchParams();

    const data_ini = els.fDataIni?.value || "";
    const data_fim = els.fDataFim?.value || "";
    const competencia = els.fCompetencia?.value || "";
    const tipo = els.fTipoLanc?.value || "";
    const status = els.fStatusLanc?.value || "";
    const q = els.fBuscaLanc?.value?.trim() || "";

    if (data_ini) params.set("data_ini", data_ini);
    if (data_fim) params.set("data_fim", data_fim);
    if (competencia) params.set("competencia", competencia);
    if (tipo) params.set("tipo", tipo);
    if (status) params.set("status", status);
    if (q) params.set("q", q);

    return params;
  }

  function getRecebimentosFilterParams() {
    const params = new URLSearchParams();

    const q = els.fRecebBusca?.value?.trim() || "";
    const status = els.fRecebStatus?.value || "";
    const tipo = els.fRecebTipo?.value || "";

    if (q) params.set("q", q);
    if (status) params.set("status", status);
    if (tipo) params.set("tipo", tipo);

    return params;
  }

  // =========================================================
  // KPIS / RESUMO
  // =========================================================
  async function loadResumo() {
    const params = getGlobalFilterParams();
    const data = await requestJSON(`/financeiro/api/resumo?${params.toString()}`);
    state.resumo = data.resumo || {};

    const saldo = Number(state.resumo.saldo_caixa || data.saldo_caixa || 0);
    const entradas = Number(state.resumo.entradas || data.entradas || 0);
    const saidas = Number(state.resumo.saidas || data.saidas || 0);
    const pendentes = Number(state.resumo.pendentes || data.pendentes || 0);

    if (els.kpiSaldo) els.kpiSaldo.textContent = money(saldo);
    if (els.kpiEntradas) els.kpiEntradas.textContent = money(entradas);
    if (els.kpiSaidas) els.kpiSaidas.textContent = money(saidas);
    if (els.kpiPendentes) els.kpiPendentes.textContent = money(pendentes);

    if (els.sumEntradasPagas) {
      els.sumEntradasPagas.textContent = money(state.resumo.entradas_pagas || entradas);
    }
    if (els.sumSaidasPagas) {
      els.sumSaidasPagas.textContent = money(state.resumo.saidas_pagas || saidas);
    }
    if (els.sumEntradasPendentes) {
      els.sumEntradasPendentes.textContent = money(state.resumo.entradas_pendentes || pendentes);
    }
    if (els.sumSaldoProjetado) {
      els.sumSaldoProjetado.textContent = money(state.resumo.saldo_projetado || saldo);
    }
  }

  async function loadFechamento() {
    const params = getGlobalFilterParams();
    const data = await requestJSON(`/financeiro/api/fechamento?${params.toString()}`);

    const categorias = Array.isArray(data.por_categoria) ? data.por_categoria : [];
    const dias = Array.isArray(data.por_dia) ? data.por_dia : [];

    renderResumoCategorias(categorias);
    renderResumoDias(dias);
  }

  function renderResumoCategorias(items) {
    if (!els.finResumoCategorias) return;

    if (!items.length) {
      els.finResumoCategorias.innerHTML = `<div class="fin-empty-inline">Sem dados.</div>`;
      return;
    }

    els.finResumoCategorias.innerHTML = items.map(item => `
      <div class="fin-list-row">
        <div class="fin-list-row__left">
          <strong>${escapeHtml(item.categoria || "sem_categoria")}</strong>
          <span>${escapeHtml(item.tipo || "—")} · ${escapeHtml(item.status || "—")} · ${Number(item.qtd || 0)} registro(s)</span>
        </div>
        <div class="fin-list-row__right">${money(item.total)}</div>
      </div>
    `).join("");
  }

  function renderResumoDias(items) {
    if (!els.finResumoDias) return;

    if (!items.length) {
      els.finResumoDias.innerHTML = `<div class="fin-empty-inline">Sem dados.</div>`;
      return;
    }

    els.finResumoDias.innerHTML = items.map(item => `
      <div class="fin-list-row">
        <div class="fin-list-row__left">
          <strong>${escapeHtml(formatDateBR(item.dia))}</strong>
          <span>Entradas: ${money(item.entradas)} · Saídas: ${money(item.saidas)}</span>
        </div>
        <div class="fin-list-row__right">${money(Number(item.entradas || 0) - Number(item.saidas || 0))}</div>
      </div>
    `).join("");
  }

  // =========================================================
  // RECEBIMENTOS
  // =========================================================
  async function loadRecebimentos() {
    const params = getRecebimentosFilterParams();
    const data = await requestJSON(`/financeiro/api/pacientes-planos?${params.toString()}`);
    state.recebimentos = Array.isArray(data.items) ? data.items : [];
    renderRecebimentos();
  }

  function renderRecebimentos() {
    if (!els.finCardsRecebimentos) return;

    if (!state.recebimentos.length) {
      els.finCardsRecebimentos.innerHTML = `
        <div class="fin-empty">
          <strong>Nenhum recebimento carregado.</strong>
          <span>Os vínculos do comercial aparecerão aqui.</span>
        </div>
      `;
      return;
    }

    els.finCardsRecebimentos.innerHTML = state.recebimentos.map(item => {
      const tipo = normalizeText(item.tipo);
      const status = normalizeText(item.status);
      const nomeVinculo = item.combo_nome || item.nome_plano || "Sem vínculo";
      const contratadas = Number(item.sessoes_contratadas || 0);
      const usadas = Number(item.sessoes_usadas || 0);
      const restantes = Number(item.sessoes_restantes || Math.max(contratadas - usadas, 0));

      return `
        <article class="fin-item-card">
          <div class="fin-item-head">
            <div class="fin-item-title">
              <strong>${escapeHtml(item.paciente_nome || "Sem paciente")}</strong>
              <div class="fin-item-sub">${escapeHtml(nomeVinculo)}</div>
            </div>

            <div class="fin-badges">
              <span class="fin-badge ${tipo === "combo" ? "fin-badge--entrada" : "fin-badge--soft"}">
                ${escapeHtml(item.tipo || "—")}
              </span>
              <span class="fin-badge ${
                status === "ativo"
                  ? "fin-badge--pago"
                  : status === "encerrado"
                    ? "fin-badge--pendente"
                    : "fin-badge--soft"
              }">
                ${escapeHtml(item.status || "—")}
              </span>
            </div>
          </div>

          <div class="fin-item-meta">
            <div class="fin-meta-box">
              <span class="fin-meta-box__label">Valor total</span>
              <div class="fin-meta-box__value fin-money">${money(item.valor_total)}</div>
            </div>

            <div class="fin-meta-box">
              <span class="fin-meta-box__label">Forma pagamento</span>
              <div class="fin-meta-box__value">${escapeHtml(item.forma_pagamento || "—")}</div>
            </div>

            <div class="fin-meta-box">
              <span class="fin-meta-box__label">Sessões</span>
              <div class="fin-meta-box__value">
                ${contratadas} contratada(s) · ${usadas} usada(s) · ${restantes} restante(s)
              </div>
            </div>
          </div>

          ${
            item.observacoes
              ? `<div class="fin-item-sub">${escapeHtml(item.observacoes)}</div>`
              : ""
          }
        </article>
      `;
    }).join("");
  }

  // =========================================================
  // LANÇAMENTOS
  // =========================================================
  async function loadLancamentos() {
    const params = getGlobalFilterParams();
    const data = await requestJSON(`/financeiro/api/lancamentos?${params.toString()}`);
    state.lancamentos = Array.isArray(data.items) ? data.items : [];
    renderLancamentos();
  }

  function getLancamentoBadgeTipo(tipo) {
    return normalizeText(tipo) === "saida" ? "fin-badge--saida" : "fin-badge--entrada";
  }

  function getLancamentoBadgeStatus(status) {
    const s = normalizeText(status);
    if (s === "pago") return "fin-badge--pago";
    if (s === "pendente") return "fin-badge--pendente";
    if (s === "parcial") return "fin-badge--parcial";
    return "fin-badge--soft";
  }

  function renderLancamentos() {
    if (!els.finCardsLancamentos) return;

    if (!state.lancamentos.length) {
      els.finCardsLancamentos.innerHTML = `
        <div class="fin-empty">
          <strong>Nenhum lançamento carregado.</strong>
          <span>As movimentações aparecerão aqui.</span>
        </div>
      `;
      return;
    }

    els.finCardsLancamentos.innerHTML = state.lancamentos.map(item => {
      const tipo = normalizeText(item.tipo);
      const cardClass = tipo === "saida" ? "is-saida" : "is-entrada";

      return `
        <article class="fin-item-card ${cardClass}" data-lanc-id="${item.id}">
          <div class="fin-item-head">
            <div class="fin-item-title">
              <strong>${escapeHtml(item.descricao || "Sem descrição")}</strong>
              <div class="fin-item-sub">
                ${escapeHtml(item.categoria || "sem categoria")}
                ${item.origem ? ` · ${escapeHtml(item.origem)}` : ""}
              </div>
            </div>

            <div class="fin-badges">
              <span class="fin-badge ${getLancamentoBadgeTipo(item.tipo)}">${escapeHtml(item.tipo || "—")}</span>
              <span class="fin-badge ${getLancamentoBadgeStatus(item.status)}">${escapeHtml(item.status || "—")}</span>
            </div>
          </div>

          <div class="fin-item-meta">
            <div class="fin-meta-box">
              <span class="fin-meta-box__label">Valor</span>
              <div class="fin-meta-box__value fin-money ${tipo === "saida" ? "is-saida" : ""}">
                ${money(item.valor)}
              </div>
            </div>

            <div class="fin-meta-box">
              <span class="fin-meta-box__label">Forma pagamento</span>
              <div class="fin-meta-box__value">${escapeHtml(item.forma_pagamento || "—")}</div>
            </div>

            <div class="fin-meta-box">
              <span class="fin-meta-box__label">Vencimento</span>
              <div class="fin-meta-box__value">${formatDateBR(item.vencimento)}</div>
            </div>

            <div class="fin-meta-box">
              <span class="fin-meta-box__label">Data pagamento</span>
              <div class="fin-meta-box__value">${formatDateBR(item.data_pagamento)}</div>
            </div>
          </div>

          ${
            item.observacoes
              ? `<div class="fin-item-sub">${escapeHtml(item.observacoes)}</div>`
              : ""
          }

          <div class="fin-actions">
            ${
              normalizeText(item.status) !== "pago"
                ? `<button type="button" class="fin-btn fin-btn--primary" data-action="baixar-lancamento" data-id="${item.id}">
                    Baixar
                  </button>`
                : ""
            }
            <button type="button" class="fin-btn fin-btn--ghost" data-action="editar-lancamento" data-id="${item.id}">
              Editar
            </button>
          </div>
        </article>
      `;
    }).join("");
  }

  // =========================================================
  // FORM MANUAL
  // =========================================================
  function resetFormLancamento() {
    els.formLancamentoManual?.reset();

    const hoje = new Date().toISOString().slice(0, 10);
    const competencia = hoje.slice(0, 7);

    if (els.lancStatus) els.lancStatus.value = "pago";
    if (els.lancTipo) els.lancTipo.value = "entrada";
    if (els.lancVencimento) els.lancVencimento.value = hoje;
    if (els.lancCompetencia) els.lancCompetencia.value = competencia;
  }

  async function submitLancamentoManual(ev) {
    ev.preventDefault();

    const payload = {
      tipo: els.lancTipo.value,
      categoria: els.lancCategoria.value.trim(),
      descricao: els.lancDescricao.value.trim(),
      valor: Number(els.lancValor.value || 0),
      forma_pagamento: els.lancForma.value,
      status: els.lancStatus.value,
      vencimento: els.lancVencimento.value,
      competencia: els.lancCompetencia.value,
      observacoes: els.lancObservacoes.value.trim(),
    };

    if (!payload.descricao) {
      toast("Informe a descrição do lançamento.");
      return;
    }

    if (!(payload.valor > 0)) {
      toast("Informe um valor maior que zero.");
      return;
    }

    setLoading(els.btnSalvarLancamento, true, "Salvando...");

    try {
      await requestJSON("/financeiro/api/lancamentos", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      toast("Lançamento cadastrado com sucesso.");
      resetFormLancamento();
      await refreshAllFinanceiro();
    } catch (err) {
      toast(err.message || "Não foi possível salvar o lançamento.");
    } finally {
      setLoading(els.btnSalvarLancamento, false);
    }
  }

  // =========================================================
  // MODAL LANÇAMENTO
  // =========================================================
  async function openModalLancamento(id) {
    try {
      const data = await requestJSON(`/financeiro/api/lancamentos/${id}`);
      const item = data.item;
      if (!item) return;

      els.mlId.value = item.id || "";
      els.mlTipo.value = item.tipo || "entrada";
      els.mlCategoria.value = item.categoria || "";
      els.mlDescricao.value = item.descricao || "";
      els.mlValor.value = Number(item.valor || 0);
      els.mlFormaPagamento.value = item.forma_pagamento || "";
      els.mlStatus.value = item.status || "pendente";
      els.mlVencimento.value = item.vencimento ? String(item.vencimento).slice(0, 10) : "";
      els.mlDataPagamento.value = item.data_pagamento ? String(item.data_pagamento).slice(0, 10) : "";
      els.mlCompetencia.value = item.competencia || "";
      els.mlObservacoes.value = item.observacoes || "";

      openDialog(els.modalLancamento);
    } catch (err) {
      toast(err.message || "Não foi possível abrir o lançamento.");
    }
  }

  async function submitModalLancamento(ev) {
    ev.preventDefault();

    const id = els.mlId.value.trim();
    if (!id) return;

    const payload = {
      tipo: els.mlTipo.value,
      categoria: els.mlCategoria.value.trim(),
      descricao: els.mlDescricao.value.trim(),
      valor: Number(els.mlValor.value || 0),
      forma_pagamento: els.mlFormaPagamento.value,
      status: els.mlStatus.value,
      vencimento: els.mlVencimento.value,
      data_pagamento: els.mlDataPagamento.value,
      competencia: els.mlCompetencia.value,
      observacoes: els.mlObservacoes.value.trim(),
    };

    try {
      await requestJSON(`/financeiro/api/lancamentos/${id}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });

      toast("Lançamento atualizado com sucesso.");
      closeDialog(els.modalLancamento);
      await refreshAllFinanceiro();
    } catch (err) {
      toast(err.message || "Não foi possível atualizar o lançamento.");
    }
  }

  async function excluirLancamentoModal() {
    const id = els.mlId.value.trim();
    if (!id) return;

    const confirmed = window.confirm("Deseja realmente excluir este lançamento?");
    if (!confirmed) return;

    try {
      await requestJSON(`/financeiro/api/lancamentos/${id}`, {
        method: "DELETE"
      });

      toast("Lançamento removido com sucesso.");
      closeDialog(els.modalLancamento);
      await refreshAllFinanceiro();
    } catch (err) {
      toast(err.message || "Não foi possível excluir o lançamento.");
    }
  }

  async function baixarLancamento(id) {
    const confirmed = window.confirm("Deseja baixar este lançamento como pago?");
    if (!confirmed) return;

    const hoje = new Date().toISOString().slice(0, 10);

    try {
      await requestJSON(`/financeiro/api/lancamentos/${id}/baixar`, {
        method: "POST",
        body: JSON.stringify({
          data_pagamento: hoje,
        }),
      });

      toast("Lançamento baixado com sucesso.");
      await refreshAllFinanceiro();
    } catch (err) {
      toast(err.message || "Não foi possível baixar o lançamento.");
    }
  }

  // =========================================================
  // REFRESH GERAL
  // =========================================================
  async function refreshAllFinanceiro() {
    await Promise.all([
      loadResumo(),
      loadRecebimentos(),
      loadLancamentos(),
      loadFechamento(),
    ]);
  }

  function limparFiltrosFinanceiro() {
    if (els.fDataIni) els.fDataIni.value = "";
    if (els.fDataFim) els.fDataFim.value = "";
    if (els.fCompetencia) els.fCompetencia.value = "";
    if (els.fTipoLanc) els.fTipoLanc.value = "";
    if (els.fStatusLanc) els.fStatusLanc.value = "";
    if (els.fBuscaLanc) els.fBuscaLanc.value = "";

    if (els.fRecebBusca) els.fRecebBusca.value = "";
    if (els.fRecebStatus) els.fRecebStatus.value = "";
    if (els.fRecebTipo) els.fRecebTipo.value = "";
  }

  // =========================================================
  // EVENTS
  // =========================================================
  function bindEvents() {
    // filtros globais
    els.btnAplicarFinanceiro?.addEventListener("click", () => {
      refreshAllFinanceiro().catch(err => toast(err.message));
    });

    els.btnLimparFinanceiro?.addEventListener("click", () => {
      limparFiltrosFinanceiro();
      refreshAllFinanceiro().catch(err => toast(err.message));
    });

    els.fBuscaLanc?.addEventListener("input", debounce(() => {
      loadLancamentos().catch(err => toast(err.message));
    }, 250));

    els.fTipoLanc?.addEventListener("change", () => {
      loadLancamentos().catch(err => toast(err.message));
      loadResumo().catch(err => toast(err.message));
      loadFechamento().catch(err => toast(err.message));
    });

    els.fStatusLanc?.addEventListener("change", () => {
      loadLancamentos().catch(err => toast(err.message));
      loadResumo().catch(err => toast(err.message));
    });

    // recebimentos
    els.btnAtualizarRecebimentos?.addEventListener("click", () => {
      loadRecebimentos().catch(err => toast(err.message));
    });

    els.fRecebBusca?.addEventListener("input", debounce(() => {
      loadRecebimentos().catch(err => toast(err.message));
    }, 250));

    els.fRecebStatus?.addEventListener("change", () => {
      loadRecebimentos().catch(err => toast(err.message));
    });

    els.fRecebTipo?.addEventListener("change", () => {
      loadRecebimentos().catch(err => toast(err.message));
    });

    // lançamento manual
    els.formLancamentoManual?.addEventListener("submit", submitLancamentoManual);
    els.btnLimparLancamento?.addEventListener("click", resetFormLancamento);

    // cards de lançamentos
    els.btnAtualizarLancamentos?.addEventListener("click", () => {
      loadLancamentos().catch(err => toast(err.message));
    });

    els.finCardsLancamentos?.addEventListener("click", (ev) => {
      const btnEditar = ev.target.closest("[data-action='editar-lancamento']");
      if (btnEditar) {
        openModalLancamento(btnEditar.dataset.id);
        return;
      }

      const btnBaixar = ev.target.closest("[data-action='baixar-lancamento']");
      if (btnBaixar) {
        baixarLancamento(btnBaixar.dataset.id);
      }
    });

    // modal
    els.formModalLancamento?.addEventListener("submit", submitModalLancamento);
    els.btnExcluirLancamentoModal?.addEventListener("click", excluirLancamentoModal);
    els.btnFecharLancamentoModal?.addEventListener("click", () => closeDialog(els.modalLancamento));
  }

  // =========================================================
  // INIT
  // =========================================================
  async function init() {
    bindEvents();
    resetFormLancamento();

    try {
      await refreshAllFinanceiro();
    } catch (err) {
      toast(err.message || "Erro ao carregar a tela financeira.");
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();