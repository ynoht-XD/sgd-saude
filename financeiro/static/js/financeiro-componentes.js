/* financeiro-componentes.js — peças compartilhadas da área Comercial (Combos, Planos, Comercial).
 *
 * Extraído de comercial.js SEM mudar comportamento: o código abaixo é o mesmo que estava lá,
 * só reorganizado em funções puras (devolvem HTML/valores) e em duas fábricas que recebem os
 * elementos da página e callbacks. Nenhuma peça conhece "Combo" ou "Plano" em particular: o tipo
 * vem nos dados (item.tipo), então a mesma peça serve às duas páginas.
 *
 * Carregar ANTES de comercial.js. Expõe window.FinComp.
 *
 *   utilitários ........ escapeHtml, money, digits, boolValue, normalizeText, parseDateSafe,
 *                        formatDateBR, diffDays, toast, debounce, setLoading, requestJSON,
 *                        openDialog, closeDialog, togglePanel
 *   cartão de vínculo .. buildDatasResumo, getDataStatus, getConsumoClasse, percentualConsumo,
 *                        vinculoCardHtml(item), paginacaoHtml(pagina, total, porPagina)
 *   sem vínculo ........ semVinculoCardsHtml(items)
 *   busca de paciente .. pacienteResultadosHtml(items), criarSeletorPaciente({...})
 *   modal de edição .... criarModalVinculo({ els, aposSalvar, aposDesvincular, aposExcluir })
 *
 * CSRF: csrf.js (layout) já injeta o X-CSRFToken em todo fetch não-GET.
 * Os helpers de catalogos.js e beneficiarios.js continuam com cópias próprias (não tocados).
 */
(() => {
  "use strict";

  if (window.FinComp) return;

  // =========================================================
  // UTILITÁRIOS
  // =========================================================
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

  // =========================================================
  // DATAS / STATUS / CONSUMO DE UM VÍNCULO
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
  // CARTÃO DE VÍNCULO (Combo ou Plano: o tipo vem em item.tipo)
  // =========================================================
  function vinculoCardHtml(item) {
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
              ${item.tipo === "plano" && Number(item.max_beneficiarios || 1) > 1 ? `
              <button type="button" class="com-btn com-btn--ghost" data-action="gerenciar-beneficiarios"
                      data-id="${item.id}" data-max="${Number(item.max_beneficiarios)}"
                      data-nome="${escapeHtml(item.paciente_nome || "")}"
                      data-plano="${escapeHtml(nomeCombo)}">
                Gerenciar beneficiários
              </button>` : ""}
              <button type="button" class="com-btn com-btn--ghost" data-action="editar-vinculo" data-id="${item.id}">
                Editar
              </button>
            </div>
          </div>
        </article>
      `;
  }

  // Botões de paginação. Devolve a página já limitada ao total (quem chama grava no seu estado).
  function paginacaoHtml(paginaAtual, total, porPagina) {
    const totalPaginas = Math.max(1, Math.ceil(total / porPagina));

    if (paginaAtual > totalPaginas) {
      paginaAtual = totalPaginas;
    }

    const botoes = [];

    botoes.push(`
      <button type="button" class="com-btn com-btn--ghost" data-page-action="prev" ${paginaAtual === 1 ? "disabled" : ""}>
        ← Anterior
      </button>
    `);

    for (let i = 1; i <= totalPaginas; i++) {
      if (
        i === 1 ||
        i === totalPaginas ||
        Math.abs(i - paginaAtual) <= 1
      ) {
        botoes.push(`
          <button type="button" class="com-btn ${i === paginaAtual ? "com-btn--primary" : "com-btn--ghost"}" data-page="${i}">
            ${i}
          </button>
        `);
      } else if (
        (i === paginaAtual - 2 && i > 1) ||
        (i === paginaAtual + 2 && i < totalPaginas)
      ) {
        botoes.push(`<span class="com-pag-ellipsis" style="align-self:center;padding:0 4px;">…</span>`);
      }
    }

    botoes.push(`
      <button type="button" class="com-btn com-btn--ghost" data-page-action="next" ${paginaAtual === totalPaginas ? "disabled" : ""}>
        Próxima →
      </button>
    `);

    const html = `
      <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;width:100%;">
        ${botoes.join("")}
        <span style="margin-left:auto;color:#64748b;color:light-dark(#64748b,var(--muted));font-size:.9rem;">
          ${total} registro(s) · ${totalPaginas} página(s)
        </span>
      </div>
    `;

    return { paginaAtual, totalPaginas, html };
  }

  // =========================================================
  // PACIENTES SEM VÍNCULO
  // =========================================================
  function semVinculoCardsHtml(items) {
    return items.map(item => {
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
  // BUSCA / SELEÇÃO DE PACIENTE
  // =========================================================
  function pacienteResultadosHtml(items) {
    return items.map(item => {
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
  }

  /* Seletor de paciente (campo de busca + lista de resultados + caixa do selecionado).
   *   resultados ........ elemento onde a lista de resultados aparece
   *   caixaSelecionado .. elemento onde o paciente escolhido é mostrado
   *   campoId ........... <input hidden> que recebe o id do paciente escolhido
   *   vinculoExistente .. (pacienteId) => contrato já existente do paciente, ou undefined
   *   aoSelecionar ...... (paciente) => void   (a página guarda no seu estado)
   *   aoLimpar .......... () => void
   * O dataset vem do botão clicado (data-id, data-nome, ...), como antes.
   */
  function criarSeletorPaciente(cfg) {
    const { resultados, caixaSelecionado, campoId } = cfg;
    const vinculoExistente = cfg.vinculoExistente || (() => undefined);
    const aoSelecionar = cfg.aoSelecionar || (() => {});
    const aoLimpar = cfg.aoLimpar || (() => {});

    async function buscar(q) {
      const termo = String(q || "").trim();

      if (termo.length < 2) {
        if (resultados) {
          resultados.hidden = true;
          resultados.innerHTML = "";
        }
        return;
      }

      try {
        const data = await requestJSON(`/financeiro/api/pacientes/buscar?q=${encodeURIComponent(termo)}`);
        const items = Array.isArray(data.items) ? data.items : [];

        if (!items.length) {
          resultados.hidden = false;
          resultados.innerHTML = `<div class="com-empty">Nenhum paciente encontrado.</div>`;
          return;
        }

        resultados.hidden = false;
        resultados.innerHTML = pacienteResultadosHtml(items);
      } catch (err) {
        resultados.hidden = false;
        resultados.innerHTML = `<div class="com-empty">${escapeHtml(err.message || "Erro ao buscar pacientes.")}</div>`;
      }
    }

    function selecionar(dataset) {
      const paciente = {
        id: dataset.id || "",
        nome: dataset.nome || "",
        cpf: dataset.cpf || "",
        cns: dataset.cns || "",
        nascimento: dataset.nascimento || "",
        telefone: dataset.telefone || ""
      };

      aoSelecionar(paciente);

      if (campoId) {
        campoId.value = paciente.id || "";
      }

      const existente = vinculoExistente(paciente.id);

      caixaSelecionado.innerHTML = `
      <div class="com-patient-card">
        <strong>${escapeHtml(paciente.nome || "Sem nome")}</strong>
        <div class="com-patient-meta">
          ${paciente.cpf ? `CPF: ${escapeHtml(paciente.cpf)} · ` : ""}
          ${paciente.cns ? `CNS: ${escapeHtml(paciente.cns)} · ` : ""}
          ${paciente.telefone ? `Tel: ${escapeHtml(paciente.telefone)} · ` : ""}
          ${paciente.nascimento ? `Nasc.: ${escapeHtml(paciente.nascimento)}` : ""}
        </div>
        ${
          existente
            ? `<div class="com-patient-meta" style="color:#b45309;color:light-dark(#b45309,var(--warning-ink));font-weight:700;">
                Este paciente já possui vínculo cadastrado. Atualize/editando o registro existente.
              </div>`
            : ""
        }
      </div>
    `;

      resultados.hidden = true;
      resultados.innerHTML = "";

      if (existente) {
        toast("Este paciente já está cadastrado no comercial. Edite o vínculo existente.");
      }
    }

    function limpar() {
      aoLimpar();
      if (campoId) campoId.value = "";

      if (caixaSelecionado) {
        caixaSelecionado.innerHTML = `<div class="com-patient-empty">Nenhum paciente selecionado.</div>`;
      }
    }

    return { buscar, selecionar, limpar };
  }

  // =========================================================
  // MODAL "EDITAR VÍNCULO"
  // =========================================================
  /* Precisa dos elementos (mesmos nomes usados em comercial.js): modalVinculo, mvId,
   * mvPacienteNome, mvTipo, mvFieldCombo, mvComboId, mvFieldNomePlano, mvNomePlano,
   * mvSessoesContratadas, mvSessoesUsadas, mvSessoesRestantes, mvValorTotal,
   * mvFormaPagamento, mvStatus, mvDataInicio, mvDataFim, mvRecorrente,
   * mvRenovacaoAutomatica, mvObservacoes, mvBadgeTipo, mvBadgeConsumo, mvBadgeAlerta.
   * Callbacks (async, rodam dentro do mesmo try/catch de antes): aposSalvar,
   * aposDesvincular, aposExcluir — a página recarrega as listas que quiser.
   */
  function criarModalVinculo(cfg) {
    const els = cfg.els;
    const aposSalvar = cfg.aposSalvar || (async () => {});
    const aposDesvincular = cfg.aposDesvincular || (async () => {});
    const aposExcluir = cfg.aposExcluir || (async () => {});

    function sincronizarTipo() {
      const tipo = els.mvTipo?.value || "combo";
      const isCombo = tipo === "combo";

      if (els.mvFieldCombo) els.mvFieldCombo.hidden = !isCombo;
      if (els.mvFieldNomePlano) els.mvFieldNomePlano.hidden = isCombo;
    }

    function preencherResumo(item) {
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

    async function abrir(id) {
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

        sincronizarTipo();
        preencherResumo(item);
        openDialog(els.modalVinculo);
      } catch (err) {
        toast(err.message || "Não foi possível abrir o vínculo.");
      }
    }

    async function enviar(ev) {
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
        await aposSalvar();
      } catch (err) {
        toast(err.message || "Não foi possível atualizar o vínculo.");
      }
    }

    async function desvincular() {
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
        await aposDesvincular();
      } catch (err) {
        toast(err.message || "Não foi possível desvincular os atendimentos.");
      }
    }

    async function excluir() {
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
        await aposExcluir();
      } catch (err) {
        toast(err.message || "Não foi possível excluir o vínculo.");
      }
    }

    function fechar() {
      closeDialog(els.modalVinculo);
    }

    return { sincronizarTipo, abrir, enviar, desvincular, excluir, fechar };
  }

  window.FinComp = Object.freeze({
    escapeHtml, money, digits, boolValue, normalizeText, parseDateSafe, formatDateBR, diffDays,
    toast, debounce, setLoading, requestJSON, openDialog, closeDialog, togglePanel,
    buildDatasResumo, getDataStatus, getConsumoClasse, percentualConsumo,
    vinculoCardHtml, paginacaoHtml, semVinculoCardsHtml,
    pacienteResultadosHtml, criarSeletorPaciente, criarModalVinculo,
  });
})();
