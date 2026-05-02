(() => {
  "use strict";

  const API = "/financeiro/api";

  const state = {
    competencia: "",
    tipo: "",
    categorias: {
      receitas: [],
      despesas: [],
      formas_pagamento: [],
      status: [],
    },
    lancamentos: [],
    combos: [],
    planos: [],
    pacienteSelecionado: null,
  };

  const $ = (sel, ctx = document) => ctx.querySelector(sel);
  const $$ = (sel, ctx = document) => Array.from(ctx.querySelectorAll(sel));

  const money = (v) =>
    Number(v || 0).toLocaleString("pt-BR", {
      style: "currency",
      currency: "BRL",
    });

  const todayISO = () => new Date().toISOString().slice(0, 10);
  const currentCompetencia = () => new Date().toISOString().slice(0, 7);

  const fmtDateBR = (value) => {
    if (!value) return "-";
    const d = String(value).slice(0, 10);
    const [y, m, day] = d.split("-");
    return y && m && day ? `${day}/${m}/${y}` : value;
  };

  async function api(path, options = {}) {
    const config = {
      headers: { "Content-Type": "application/json" },
      ...options,
    };

    const res = await fetch(`${API}${path}`, config);
    const data = await res.json().catch(() => ({}));

    if (!res.ok || data.ok === false) {
      throw new Error(data.erro || "Erro na requisição.");
    }

    return data;
  }

  function toast(msg, type = "ok") {
    console.log(`[${type}] ${msg}`);
    alert(msg);
  }

  function openModal(id) {
    const modal = document.getElementById(id);
    if (!modal) return;

    if (typeof modal.showModal === "function") modal.showModal();
    else modal.setAttribute("open", "open");
  }

  function closeModal(id) {
    const modal = document.getElementById(id);
    if (!modal) return;

    if (typeof modal.close === "function") modal.close();
    else modal.removeAttribute("open");
  }

  function fillSelect(select, items, placeholder = "Selecione") {
    if (!select) return;

    select.innerHTML = `<option value="">${placeholder}</option>`;

    items.forEach((item) => {
      const opt = document.createElement("option");
      opt.value = item;
      opt.textContent = item;
      select.appendChild(opt);
    });
  }

  function setCompetenciaAtual() {
    state.competencia = currentCompetencia();

    const filtro = $("#filtroCompetencia");
    if (filtro && !filtro.value) filtro.value = state.competencia;

    const lancCompetencia = $("#lancCompetencia");
    if (lancCompetencia) lancCompetencia.value = state.competencia;

    const txt = $("#txtCompetenciaAtual");
    if (txt) txt.textContent = `Competência ${state.competencia}`;
  }

  async function carregarCategorias() {
    const data = await api("/categorias");

    state.categorias = {
      receitas: data.receitas || [],
      despesas: data.despesas || [],
      formas_pagamento: data.formas_pagamento || [],
      status: data.status || [],
    };

    preencherCategoriasPorTipo();
    fillSelect($("#planoFormaPagamento"), state.categorias.formas_pagamento, "Selecione");
    fillSelect($("#lancFormaPagamento"), state.categorias.formas_pagamento, "Selecione");
  }

  function preencherCategoriasPorTipo() {
    const tipo = $("#lancTipo")?.value || "entrada";
    const categoriaLanc = $("#lancCategoria");
    const filtroCategoria = $("#filtroCategoria");

    const lista =
      tipo === "saida" ? state.categorias.despesas : state.categorias.receitas;

    fillSelect(categoriaLanc, lista, "Selecione");
    fillSelect(filtroCategoria, [...state.categorias.receitas, ...state.categorias.despesas], "Todas");
  }

  async function carregarResumo() {
    const comp = $("#filtroCompetencia")?.value || state.competencia;

    const data = await api(`/resumo?competencia=${encodeURIComponent(comp)}`);
    const r = data.resumo || {};

    $("#kpiEntradasPagas").textContent = money(r.entradas_pagas);
    $("#kpiSaidasPagas").textContent = money(r.saidas_pagas);
    $("#kpiSaldoPago").textContent = money(r.saldo_pago);

    const pendentes = Number(r.entradas_pendentes || 0) + Number(r.saidas_pendentes || 0);
    $("#kpiPendentes").textContent = money(pendentes);
  }

  async function carregarFechamento() {
    const comp = $("#filtroCompetencia")?.value || state.competencia;

    const data = await api(`/fechamento?competencia=${encodeURIComponent(comp)}`);
    const f = data.fechamento || {};

    $("#fechamentoSaldo").textContent = money(f.saldo);
    $("#fechamentoEntradas").textContent = money(f.entradas);
    $("#fechamentoSaidas").textContent = money(f.saidas);

    const box = $("#listaCategoriasFechamento");
    if (!box) return;

    const categorias = f.por_categoria || [];

    if (!categorias.length) {
      box.innerHTML = `<div class="empty-state">Nenhuma movimentação nesta competência.</div>`;
      return;
    }

    box.innerHTML = categorias
      .map((c) => {
        const tipo = c.tipo || "";
        return `
          <div class="fin-category-item ${tipo}">
            <div>
              <strong>${c.categoria || "Sem categoria"}</strong>
              <small>${tipo === "entrada" ? "Receita" : "Despesa"} · ${c.quantidade || 0} lançamento(s)</small>
            </div>
            <span class="valor">${money(c.total_pago)}</span>
          </div>
        `;
      })
      .join("");
  }

  function paramsLancamentos() {
    const params = new URLSearchParams();

    const competencia = $("#filtroCompetencia")?.value || state.competencia;
    const status = $("#filtroStatus")?.value || "";
    const categoria = $("#filtroCategoria")?.value || "";
    const q = $("#filtroBusca")?.value || "";

    if (competencia) params.set("competencia", competencia);
    if (state.tipo) params.set("tipo", state.tipo);
    if (status) params.set("status", status);
    if (categoria) params.set("categoria", categoria);
    if (q) params.set("q", q);

    params.set("per_page", "200");

    return params.toString();
  }

  async function carregarLancamentos() {
    const tbody = $("#tbodyLancamentos");
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="7" class="empty-cell">Carregando lançamentos...</td></tr>`;
    }

    const data = await api(`/lancamentos?${paramsLancamentos()}`);
    state.lancamentos = data.items || [];

    renderLancamentos();
  }

  function renderLancamentos() {
    const tbody = $("#tbodyLancamentos");
    if (!tbody) return;

    if (!state.lancamentos.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="empty-cell">Nenhum lançamento encontrado.</td></tr>`;
      return;
    }

    tbody.innerHTML = state.lancamentos
      .map((l) => {
        const tipo = l.tipo || "";
        const valorClass = tipo === "saida" ? "valor-saida" : "valor-entrada";

        return `
          <tr>
            <td>${fmtDateBR(l.data_movimento || l.data_pagamento || l.vencimento || l.criado_em)}</td>
            <td><span class="badge ${tipo}">${tipo === "saida" ? "Saída" : "Entrada"}</span></td>
            <td>
              <strong>${l.descricao || "-"}</strong><br>
              <small>${l.cliente_nome || l.fornecedor || l.documento || ""}</small>
            </td>
            <td>${l.categoria || "-"}</td>
            <td><span class="badge ${l.status || "pendente"}">${l.status || "pendente"}</span></td>
            <td class="text-right ${valorClass}">${money(l.valor)}</td>
            <td class="text-right">
              <div class="row-actions">
                ${
                  l.status !== "pago"
                    ? `<button data-action="pagar" data-id="${l.id}">Pagar</button>`
                    : ""
                }
                <button data-action="editar" data-id="${l.id}">Editar</button>
                <button data-action="excluir" data-id="${l.id}">Excluir</button>
              </div>
            </td>
          </tr>
        `;
      })
      .join("");
  }

  function limparFormLancamento() {
    $("#formLancamento")?.reset();

    $("#lancamentoId").value = "";
    $("#tituloModalLancamento").textContent = "Novo lançamento";
    $("#lancTipo").value = "entrada";
    $("#lancStatus").value = "pago";
    $("#lancDataMovimento").value = todayISO();
    $("#lancCompetencia").value = $("#filtroCompetencia")?.value || state.competencia;

    preencherCategoriasPorTipo();
  }

  function preencherFormLancamento(l) {
    $("#lancamentoId").value = l.id || "";
    $("#tituloModalLancamento").textContent = "Editar lançamento";

    $("#lancTipo").value = l.tipo || "entrada";
    preencherCategoriasPorTipo();

    $("#lancStatus").value = l.status || "pendente";
    $("#lancDataMovimento").value = String(l.data_movimento || l.data_pagamento || l.vencimento || todayISO()).slice(0, 10);
    $("#lancCompetencia").value = l.competencia || state.competencia;
    $("#lancCategoria").value = l.categoria || "";
    $("#lancSubcategoria").value = l.subcategoria || "";
    $("#lancDescricao").value = l.descricao || "";
    $("#lancValor").value = Number(l.valor || 0).toFixed(2);
    $("#lancFormaPagamento").value = l.forma_pagamento || "";
    $("#lancClienteNome").value = l.cliente_nome || "";
    $("#lancFornecedor").value = l.fornecedor || "";
    $("#lancDocumento").value = l.documento || "";
    $("#lancObservacoes").value = l.observacoes || "";
  }

  function payloadLancamento() {
    return {
      tipo: $("#lancTipo").value,
      status: $("#lancStatus").value,
      data_movimento: $("#lancDataMovimento").value,
      competencia: $("#lancCompetencia").value,
      categoria: $("#lancCategoria").value,
      subcategoria: $("#lancSubcategoria").value,
      descricao: $("#lancDescricao").value,
      valor: $("#lancValor").value,
      forma_pagamento: $("#lancFormaPagamento").value,
      cliente_nome: $("#lancClienteNome").value,
      fornecedor: $("#lancFornecedor").value,
      documento: $("#lancDocumento").value,
      observacoes: $("#lancObservacoes").value,
    };
  }

  async function salvarLancamento(ev) {
    ev.preventDefault();

    const id = $("#lancamentoId").value;
    const payload = payloadLancamento();

    try {
      if (id) {
        await api(`/lancamentos/${id}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
      } else {
        await api("/lancamentos", {
          method: "POST",
          body: JSON.stringify(payload),
        });
      }

      closeModal("modalLancamento");
      await refreshAll();
      toast("Lançamento salvo com sucesso.");
    } catch (err) {
      toast(err.message, "erro");
    }
  }

  async function pagarLancamento(id) {
    try {
      await api(`/lancamentos/${id}/pagar`, {
        method: "POST",
        body: JSON.stringify({
          data_pagamento: todayISO(),
        }),
      });

      await refreshAll();
      toast("Lançamento marcado como pago.");
    } catch (err) {
      toast(err.message, "erro");
    }
  }

  async function excluirLancamento(id) {
    if (!confirm("Excluir este lançamento?")) return;

    try {
      await api(`/lancamentos/${id}`, { method: "DELETE" });
      await refreshAll();
      toast("Lançamento excluído.");
    } catch (err) {
      toast(err.message, "erro");
    }
  }

  async function carregarCombos() {
    const data = await api("/combos?ativo=1");
    state.combos = data.items || [];

    const select = $("#planoComboId");
    if (!select) return;

    select.innerHTML = `<option value="">Selecione</option>`;

    state.combos.forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = `${c.nome} · ${c.sessoes || 0} sessões · ${money(c.preco)}`;
      opt.dataset.sessoes = c.sessoes || 0;
      opt.dataset.preco = c.preco || 0;
      select.appendChild(opt);
    });
  }

  async function carregarPlanos() {
    const data = await api("/pacientes-planos");
    state.planos = data.items || [];
    renderPlanos();
  }

  function renderPlanos() {
    const box = $("#listaPacientesPlanos");
    if (!box) return;

    if (!state.planos.length) {
      box.innerHTML = `<div class="empty-state">Nenhum vínculo cadastrado.</div>`;
      return;
    }

    box.innerHTML = state.planos
      .map((p) => {
        const nome = p.combo_nome || p.nome_plano || "Plano";
        const perc = Math.min(100, Number(p.percentual_usado || 0));

        return `
          <article class="plano-card">
            <h3>${p.paciente_nome || "-"}</h3>
            <p>${p.tipo === "combo" ? "Combo" : "Particular"} · ${nome}</p>

            <div class="plano-progress">
              <span style="width:${perc}%"></span>
            </div>

            <div class="plano-meta">
              <span>${p.sessoes_usadas || 0}/${p.sessoes_contratadas || 0} sessões</span>
              <strong>${money(p.valor_total)}</strong>
            </div>

            <div class="plano-meta">
              <span>Status: ${p.status || "ativo"}</span>
              <span>Restam: ${p.sessoes_restantes || 0}</span>
            </div>
          </article>
        `;
      })
      .join("");
  }

  function limparFormPlano() {
    $("#formPlano")?.reset();

    state.pacienteSelecionado = null;
    $("#planoPacienteId").value = "";
    $("#resultadoPacientesPlano").innerHTML = "";
    $("#planoDataInicio").value = todayISO();
    $("#planoStatus").value = "ativo";
    $("#planoTipo").value = "combo";
    $("#wrapComboPlano").style.display = "";
  }

  async function buscarPacientesPlano(q) {
    const box = $("#resultadoPacientesPlano");
    if (!box) return;

    if (!q || q.length < 2) {
      box.innerHTML = "";
      return;
    }

    try {
      const data = await api(`/pacientes/buscar?q=${encodeURIComponent(q)}&limit=8`);
      const items = data.items || [];

      if (!items.length) {
        box.innerHTML = `<div class="autocomplete-list"><div class="autocomplete-item">Nenhum paciente encontrado.</div></div>`;
        return;
      }

      box.innerHTML = `
        <div class="autocomplete-list">
          ${items
            .map(
              (p) => `
                <div class="autocomplete-item" data-paciente-id="${p.id}" data-paciente-nome="${p.nome}">
                  <strong>${p.nome}</strong>
                  <small>${p.cpf || p.cns || "Sem CPF/CNS"}</small>
                </div>
              `
            )
            .join("")}
        </div>
      `;
    } catch (err) {
      box.innerHTML = "";
    }
  }

  function payloadPlano() {
    return {
      paciente_id: $("#planoPacienteId").value,
      tipo: $("#planoTipo").value,
      combo_id: $("#planoComboId").value,
      nome_plano: $("#planoNome").value,
      sessoes_contratadas: $("#planoSessoes").value,
      valor_total: $("#planoValorTotal").value,
      data_inicio: $("#planoDataInicio").value,
      data_fim: $("#planoDataFim").value,
      forma_pagamento: $("#planoFormaPagamento").value,
      status: $("#planoStatus").value,
      observacoes: $("#planoObservacoes").value,
    };
  }

  async function salvarPlano(ev) {
    ev.preventDefault();

    try {
      await api("/pacientes-planos", {
        method: "POST",
        body: JSON.stringify(payloadPlano()),
      });

      closeModal("modalPlano");
      await refreshAll();
      toast("Vínculo salvo com sucesso.");
    } catch (err) {
      toast(err.message, "erro");
    }
  }

  async function refreshAll() {
    await Promise.all([
      carregarResumo(),
      carregarFechamento(),
      carregarLancamentos(),
      carregarPlanos(),
    ]);
  }

  function bindEvents() {
    $("#btnNovoLancamento")?.addEventListener("click", () => {
      limparFormLancamento();
      openModal("modalLancamento");
    });

    $("#btnNovoPlano")?.addEventListener("click", () => {
      limparFormPlano();
      openModal("modalPlano");
    });

    $$("[data-close-modal]").forEach((btn) => {
      btn.addEventListener("click", () => closeModal(btn.dataset.closeModal));
    });

    $("#formLancamento")?.addEventListener("submit", salvarLancamento);
    $("#formPlano")?.addEventListener("submit", salvarPlano);

    $("#lancTipo")?.addEventListener("change", preencherCategoriasPorTipo);

    $("#filtroCompetencia")?.addEventListener("change", async (ev) => {
      state.competencia = ev.target.value || currentCompetencia();

      const txt = $("#txtCompetenciaAtual");
      if (txt) txt.textContent = `Competência ${state.competencia}`;

      await refreshAll();
    });

    $("#filtroStatus")?.addEventListener("change", carregarLancamentos);
    $("#filtroCategoria")?.addEventListener("change", carregarLancamentos);

    $("#filtroBusca")?.addEventListener("input", debounce(carregarLancamentos, 350));

    $("#btnLimparFiltros")?.addEventListener("click", async () => {
      $("#filtroBusca").value = "";
      $("#filtroStatus").value = "";
      $("#filtroCategoria").value = "";
      state.tipo = "";

      $$(".fin-tabs button").forEach((b) => b.classList.remove("active"));
      $('.fin-tabs button[data-tipo=""]')?.classList.add("active");

      await carregarLancamentos();
    });

    $$(".fin-tabs button").forEach((btn) => {
      btn.addEventListener("click", async () => {
        $$(".fin-tabs button").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");

        state.tipo = btn.dataset.tipo || "";
        await carregarLancamentos();
      });
    });

    $("#tbodyLancamentos")?.addEventListener("click", async (ev) => {
      const btn = ev.target.closest("button[data-action]");
      if (!btn) return;

      const id = Number(btn.dataset.id);
      const action = btn.dataset.action;

      const item = state.lancamentos.find((l) => Number(l.id) === id);

      if (action === "editar" && item) {
        preencherFormLancamento(item);
        openModal("modalLancamento");
      }

      if (action === "pagar") {
        await pagarLancamento(id);
      }

      if (action === "excluir") {
        await excluirLancamento(id);
      }
    });

    $("#planoTipo")?.addEventListener("change", () => {
      const isCombo = $("#planoTipo").value === "combo";
      $("#wrapComboPlano").style.display = isCombo ? "" : "none";
    });

    $("#planoComboId")?.addEventListener("change", () => {
      const opt = $("#planoComboId").selectedOptions[0];
      if (!opt) return;

      $("#planoSessoes").value = opt.dataset.sessoes || 0;
      $("#planoValorTotal").value = opt.dataset.preco || 0;
    });

    $("#buscaPacientePlano")?.addEventListener(
      "input",
      debounce((ev) => buscarPacientesPlano(ev.target.value), 300)
    );

    $("#resultadoPacientesPlano")?.addEventListener("click", (ev) => {
      const item = ev.target.closest(".autocomplete-item[data-paciente-id]");
      if (!item) return;

      $("#planoPacienteId").value = item.dataset.pacienteId;
      $("#buscaPacientePlano").value = item.dataset.pacienteNome;
      $("#resultadoPacientesPlano").innerHTML = "";

      state.pacienteSelecionado = {
        id: item.dataset.pacienteId,
        nome: item.dataset.pacienteNome,
      };
    });
  }

  function debounce(fn, delay = 300) {
    let timer = null;

    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), delay);
    };
  }

  async function init() {
    try {
      setCompetenciaAtual();
      bindEvents();

      await carregarCategorias();
      await carregarCombos();
      await refreshAll();
    } catch (err) {
      console.error(err);
      toast(err.message || "Erro ao iniciar financeiro.", "erro");
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();