(() => {
  const API = "/agenda-medica/api";

  const state = {
    agendas: [],
    filtradas: [],
    page: 1,
    perPage: 6,
    pacienteTimer: null,
    pacienteSelecionado: null,
  };

  const $ = (sel) => document.querySelector(sel);

  const els = {
    hoje: $("#amHoje"),

    formSolicitacao: $("#formSolicitacaoAgenda"),
    btnLimparSolicitacao: $("#btnLimparSolicitacao"),
    btnSolicitar: $("#btnSolicitar"),

    pacienteBusca: $("#pacienteBusca"),
    pacienteSugestoes: $("#pacienteSugestoes"),
    pacienteId: $("#pacienteId"),
    pacienteNome: $("#pacienteNome"),
    pacienteCpf: $("#pacienteCpf"),
    pacienteCns: $("#pacienteCns"),
    pacienteNascimento: $("#pacienteNascimento"),

    selectCbo: $("#selectCbo"),
    selectData: $("#selectData"),
    vagasInfo: $("#vagasInfo"),
    observacaoSolicitacao: $("#observacaoSolicitacao"),

    formFiltros: $("#formFiltrosProfissional"),
    filtroPaciente: $("#filtroPaciente"),
    filtroCbo: $("#filtroCbo"),
    filtroData: $("#filtroData"),
    filtroStatus: $("#filtroStatus"),
    btnLimparFiltros: $("#btnLimparFiltros"),

    grid: $("#gridAgendasLiberadas"),
    count: $("#countAgendas"),
    pageInfo: $("#pageAgendas"),
    prev: $("#prevAgendas"),
    next: $("#nextAgendas"),

    modal: $("#modalVisualizarAgenda"),
    modalTitulo: $("#modalAgendaTitulo"),
    modalSubtitulo: $("#modalAgendaSubtitulo"),
    btnFecharModal: $("#btnFecharModalAgenda"),

    totalAprovados: $("#totalAprovados"),
    totalPendentes: $("#totalPendentes"),
    totalRecusados: $("#totalRecusados"),

    listaAprovados: $("#listaAprovados"),
    listaPendentes: $("#listaPendentes"),
    listaRecusados: $("#listaRecusados"),
  };

  function toast(msg, tipo = "info") {
    if (window.Swal) {
      Swal.fire({
        toast: true,
        position: "top-end",
        icon: tipo === "erro" ? "error" : tipo === "ok" ? "success" : "info",
        title: msg,
        showConfirmButton: false,
        timer: 2200,
      });
      return;
    }

    alert(msg);
  }

  function formatDate(iso) {
    if (!iso) return "-";
    const [y, m, d] = String(iso).slice(0, 10).split("-");
    return `${d}/${m}/${y}`;
  }

  function onlyDigits(v) {
    return String(v || "").replace(/\D/g, "");
  }

  function normalizar(v) {
    return String(v || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase();
  }

  async function fetchJson(url, options = {}) {
    const res = await fetch(url, {
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      ...options,
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok || data.ok === false) {
      throw new Error(data.erro || data.mensagem || "Erro na requisição.");
    }

    return data;
  }

  function atualizarHoje() {
    if (!els.hoje) return;

    els.hoje.textContent = new Date().toLocaleDateString("pt-BR", {
      weekday: "long",
      day: "2-digit",
      month: "long",
    });
  }

  async function carregarAgendasBase() {
    if (!els.grid) return;

    els.grid.innerHTML = `<div class="am-empty">Carregando agendas liberadas...</div>`;

    try {
      const data = await fetchJson(`${API}/liberacoes/cards?tipo=futuras&page=1&per_page=200`);
      state.agendas = data.items || [];

      alimentarChoices();
      aplicarFiltros();
    } catch (err) {
      els.grid.innerHTML = `<div class="am-empty">${err.message}</div>`;
    }
  }

  function alimentarChoices() {
    alimentarChoiceCbo();
    alimentarChoiceDataFiltro();
    atualizarDatasDaSolicitacao();
  }

  function alimentarChoiceCbo() {
    const map = new Map();

    state.agendas.forEach((ag) => {
      if (!ag.cbo) return;
      map.set(ag.cbo, {
        cbo: ag.cbo,
        descricao: ag.cbo_descricao || "Sem descrição",
      });
    });

    const opts = [...map.values()]
      .sort((a, b) => a.descricao.localeCompare(b.descricao))
      .map((item) => `
        <option value="${item.cbo}">
          ${item.cbo} - ${item.descricao}
        </option>
      `)
      .join("");

    els.selectCbo.innerHTML = `
      <option value="">Selecione uma especialidade...</option>
      ${opts}
    `;
  }

  function alimentarChoiceDataFiltro() {
    const datas = [...new Set(state.agendas.map((ag) => ag.data_atendimento).filter(Boolean))]
      .sort();

    els.filtroData.innerHTML = `
      <option value="">Todas as datas liberadas</option>
      ${datas.map((d) => `<option value="${d}">${formatDate(d)}</option>`).join("")}
    `;
  }

  function atualizarDatasDaSolicitacao() {
    const cbo = els.selectCbo.value;

    const agendas = state.agendas
      .filter((ag) => !cbo || ag.cbo === cbo)
      .filter((ag) => Number(ag.vagas_restantes || 0) > 0)
      .sort((a, b) => String(a.data_atendimento).localeCompare(String(b.data_atendimento)));

    els.selectData.innerHTML = `
      <option value="">Selecione uma data...</option>
      ${agendas.map((ag) => `
        <option value="${ag.id}">
          ${formatDate(ag.data_atendimento)} — ${ag.vagas_restantes} vaga${Number(ag.vagas_restantes) === 1 ? "" : "s"}
        </option>
      `).join("")}
    `;

    atualizarVagasInfo();
  }

  function atualizarVagasInfo() {
    const id = Number(els.selectData.value || 0);
    const ag = state.agendas.find((item) => Number(item.id) === id);

    if (!ag) {
      els.vagasInfo.value = "-";
      return;
    }

    els.vagasInfo.value = `${ag.vagas_restantes} disponível(is) de ${ag.capacidade_total}`;
  }

  function aplicarFiltros() {
    const paciente = normalizar(els.filtroPaciente.value);
    const cbo = normalizar(els.filtroCbo.value);
    const data = els.filtroData.value;
    const status = els.filtroStatus.value;

    let lista = [...state.agendas];

    if (cbo) {
      lista = lista.filter((ag) => {
        const texto = normalizar(`${ag.cbo || ""} ${ag.cbo_descricao || ""}`);
        return texto.includes(cbo);
      });
    }

    if (data) {
      lista = lista.filter((ag) => String(ag.data_atendimento).slice(0, 10) === data);
    }

    if (status) {
      lista = lista.filter((ag) => {
        if (status === "PENDENTE") return Number(ag.pendentes || 0) > 0;
        if (status === "ACEITO") return Number(ag.aceitos || 0) > 0;
        if (status === "RECUSADO") return Number(ag.recusados || 0) > 0;
        if (status === "CANCELADO") return Number(ag.cancelados || 0) > 0;
        return true;
      });
    }

    if (paciente.length >= 3) {
      // filtro refinado por paciente será feito melhor quando o backend retornar agenda por paciente.
      // Por enquanto mantém os cards e o modal mostra os nomes.
    }

    state.filtradas = lista;
    state.page = 1;
    renderCards();
  }

  function renderCards() {
    const total = state.filtradas.length;
    const pages = Math.max(Math.ceil(total / state.perPage), 1);

    if (state.page > pages) state.page = pages;

    const start = (state.page - 1) * state.perPage;
    const items = state.filtradas.slice(start, start + state.perPage);

    els.count.textContent = `${total} registro${total === 1 ? "" : "s"}`;
    els.pageInfo.textContent = `Página ${state.page} de ${pages}`;

    if (!items.length) {
      els.grid.innerHTML = `<div class="am-empty">Nenhuma agenda liberada encontrada.</div>`;
      return;
    }

    els.grid.innerHTML = items.map(cardTemplate).join("");
  }

  function cardTemplate(item) {
    const total = Number(item.capacidade_total || 0);
    const ocupadas = Number(item.capacidade_ocupada || 0);
    const restantes = Number(item.vagas_restantes || 0);

    return `
      <article class="am-card" data-id="${item.id}">
        <div class="am-card-top">
          <div>
            <span class="am-date">${formatDate(item.data_atendimento)}</span>
            <h3>${item.cbo || ""} - ${item.cbo_descricao || "Sem descrição"}</h3>
            <p>${item.observacao || "Sem observação."}</p>
          </div>

          <span class="am-chip">${restantes} vaga${restantes === 1 ? "" : "s"}</span>
        </div>

        <div class="am-metrics">
          <div class="am-metric">
            <strong>${total}</strong>
            <span>Total</span>
          </div>
          <div class="am-metric">
            <strong>${ocupadas}</strong>
            <span>Usadas</span>
          </div>
          <div class="am-metric">
            <strong>${item.pendentes || 0}</strong>
            <span>Aguard.</span>
          </div>
          <div class="am-metric">
            <strong>${item.aceitos || 0}</strong>
            <span>Aprov.</span>
          </div>
        </div>

        <div class="am-card-actions">
          <button class="am-btn am-btn-primary" type="button" data-action="visualizar" data-id="${item.id}">
            Visualizar agenda
          </button>
        </div>
      </article>
    `;
  }

  async function buscarPacientes(q) {
    const data = await fetchJson(`${API}/pacientes?q=${encodeURIComponent(q)}`);
    return data.pacientes || [];
  }

  function renderPacientes(pacientes) {
    if (!els.pacienteSugestoes) return;

    if (!pacientes.length) {
      els.pacienteSugestoes.innerHTML = `
        <div class="am-suggestion">
          <strong>Nenhum paciente encontrado</strong>
          <span>Confira o cadastro do paciente.</span>
        </div>
      `;
      els.pacienteSugestoes.classList.add("open");
      return;
    }

    els.pacienteSugestoes.innerHTML = pacientes.map((p) => `
      <div class="am-suggestion"
           data-id="${p.id || ""}"
           data-nome="${String(p.nome || "").replaceAll('"', "&quot;")}"
           data-cpf="${p.cpf || ""}"
           data-cns="${p.cns || ""}"
           data-nascimento="${p.nascimento || ""}">
        <strong>${p.nome || ""}</strong>
        <span>CPF: ${p.cpf || "-"} • CNS: ${p.cns || "-"}</span>
      </div>
    `).join("");

    els.pacienteSugestoes.classList.add("open");
  }

  function fecharSugestoesPaciente() {
    els.pacienteSugestoes?.classList.remove("open");
    if (els.pacienteSugestoes) els.pacienteSugestoes.innerHTML = "";
  }

  function selecionarPaciente(item) {
    els.pacienteId.value = item.dataset.id || "";
    els.pacienteNome.value = item.dataset.nome || "";
    els.pacienteCpf.value = item.dataset.cpf || "";
    els.pacienteCns.value = item.dataset.cns || "";
    els.pacienteNascimento.value = item.dataset.nascimento || "";

    els.pacienteBusca.value = item.dataset.nome || "";

    state.pacienteSelecionado = {
      id: els.pacienteId.value,
      nome: els.pacienteNome.value,
      cpf: els.pacienteCpf.value,
      cns: els.pacienteCns.value,
      nascimento: els.pacienteNascimento.value,
    };

    fecharSugestoesPaciente();
  }

  async function solicitarAgenda(e) {
    e.preventDefault();

    if (!els.pacienteId.value || !els.pacienteNome.value) {
      toast("Selecione um paciente cadastrado.", "erro");
      return;
    }

    if (!els.selectCbo.value) {
      toast("Selecione uma especialidade.", "erro");
      return;
    }

    if (!els.selectData.value) {
      toast("Selecione uma data liberada.", "erro");
      return;
    }

    const payload = {
      liberacao_id: els.selectData.value,
      paciente_id: els.pacienteId.value,
      paciente_nome: els.pacienteNome.value,
      paciente_cpf: onlyDigits(els.pacienteCpf.value),
      paciente_cns: onlyDigits(els.pacienteCns.value),
      paciente_nascimento: els.pacienteNascimento.value || null,
      observacao: els.observacaoSolicitacao.value.trim(),
    };

    els.btnSolicitar.disabled = true;
    els.btnSolicitar.textContent = "Solicitando...";

    try {
      const data = await fetchJson(`${API}/marcacoes`, {
        method: "POST",
        body: JSON.stringify(payload),
      });

      toast(data.mensagem || "Solicitação enviada.", "ok");
      limparSolicitacao();
      await carregarAgendasBase();
    } catch (err) {
      toast(err.message, "erro");
    } finally {
      els.btnSolicitar.disabled = false;
      els.btnSolicitar.textContent = "Solicitar";
    }
  }

  function limparSolicitacao() {
    els.pacienteBusca.value = "";
    els.pacienteId.value = "";
    els.pacienteNome.value = "";
    els.pacienteCpf.value = "";
    els.pacienteCns.value = "";
    els.pacienteNascimento.value = "";

    els.selectCbo.value = "";
    atualizarDatasDaSolicitacao();

    els.observacaoSolicitacao.value = "";
    state.pacienteSelecionado = null;
  }

  async function visualizarAgenda(id) {
    const agenda = state.agendas.find((ag) => Number(ag.id) === Number(id));

    if (!agenda) return;

    els.modalTitulo.textContent = `${agenda.cbo} - ${agenda.cbo_descricao}`;
    els.modalSubtitulo.textContent =
      `${formatDate(agenda.data_atendimento)} • ${agenda.vagas_restantes} vaga${Number(agenda.vagas_restantes) === 1 ? "" : "s"} disponível(is)`;

    els.listaAprovados.innerHTML = `<div class="am-empty">Carregando...</div>`;
    els.listaPendentes.innerHTML = `<div class="am-empty">Carregando...</div>`;
    els.listaRecusados.innerHTML = `<div class="am-empty">Carregando...</div>`;

    abrirModal();

    try {
      const data = await fetchJson(`${API}/liberacoes/${id}/marcacoes`);
      const rows = data.marcacoes || [];

      const aprovados = rows.filter((r) => r.status === "ACEITO");
      const pendentes = rows.filter((r) => r.status === "PENDENTE");
      const recusados = rows.filter((r) => r.status === "RECUSADO" || r.status === "CANCELADO");

      els.totalAprovados.textContent = aprovados.length;
      els.totalPendentes.textContent = pendentes.length;
      els.totalRecusados.textContent = recusados.length;

      els.listaAprovados.innerHTML = listaTemplate(aprovados, "Nenhum aprovado ainda.");
      els.listaPendentes.innerHTML = listaTemplate(pendentes, "Nenhuma solicitação aguardando.");
      els.listaRecusados.innerHTML = listaTemplate(recusados, "Nenhum recusado.");
    } catch (err) {
      els.listaPendentes.innerHTML = `<div class="am-empty">${err.message}</div>`;
    }
  }

  function listaTemplate(rows, emptyMsg) {
    if (!rows.length) {
      return `<div class="am-empty">${emptyMsg}</div>`;
    }

    return rows.map((m) => {
      const status = String(m.status || "PENDENTE").toUpperCase();

      return `
        <article class="am-paciente">
          <div class="am-paciente-top">
            <div>
              <h3>${m.paciente_nome || "Paciente"}</h3>
              <p>
                Profissional: ${m.profissional_nome || "-"}<br>
                CPF: ${m.paciente_cpf || "-"} • CNS: ${m.paciente_cns || "-"}<br>
                Nascimento: ${m.paciente_nascimento ? formatDate(m.paciente_nascimento) : "-"}
              </p>
            </div>
            <span class="am-status ${status}">${status}</span>
          </div>

          ${m.observacao ? `<p><strong>Obs.:</strong> ${m.observacao}</p>` : ""}
          ${m.justificativa ? `<p><strong>Justificativa:</strong> ${m.justificativa}</p>` : ""}
        </article>
      `;
    }).join("");
  }

  function abrirModal() {
    if (typeof els.modal.showModal === "function") {
      els.modal.showModal();
    } else {
      els.modal.setAttribute("open", "open");
    }
  }

  function fecharModal() {
    if (typeof els.modal.close === "function") {
      els.modal.close();
    } else {
      els.modal.removeAttribute("open");
    }
  }

  function limparFiltros() {
    els.filtroPaciente.value = "";
    els.filtroCbo.value = "";
    els.filtroData.value = "";
    els.filtroStatus.value = "";

    aplicarFiltros();
  }

  function bindEvents() {
    els.pacienteBusca?.addEventListener("input", () => {
      const q = els.pacienteBusca.value.trim();

      els.pacienteId.value = "";
      els.pacienteNome.value = "";
      els.pacienteCpf.value = "";
      els.pacienteCns.value = "";
      els.pacienteNascimento.value = "";

      clearTimeout(state.pacienteTimer);

      if (q.length < 3) {
        fecharSugestoesPaciente();
        return;
      }

      state.pacienteTimer = setTimeout(async () => {
        try {
          const pacientes = await buscarPacientes(q);
          renderPacientes(pacientes);
        } catch (err) {
          console.error(err);
          renderPacientes([]);
        }
      }, 300);
    });

    els.pacienteSugestoes?.addEventListener("click", (e) => {
      const item = e.target.closest(".am-suggestion");
      if (!item) return;
      selecionarPaciente(item);
    });

    document.addEventListener("click", (e) => {
      if (!e.target.closest(".am-autocomplete-wrap")) {
        fecharSugestoesPaciente();
      }
    });

    els.selectCbo?.addEventListener("change", atualizarDatasDaSolicitacao);
    els.selectData?.addEventListener("change", atualizarVagasInfo);

    els.formSolicitacao?.addEventListener("submit", solicitarAgenda);
    els.btnLimparSolicitacao?.addEventListener("click", limparSolicitacao);

    els.formFiltros?.addEventListener("submit", (e) => {
      e.preventDefault();
      aplicarFiltros();
    });

    els.btnLimparFiltros?.addEventListener("click", limparFiltros);

    els.prev?.addEventListener("click", () => {
      if (state.page <= 1) return;
      state.page--;
      renderCards();
    });

    els.next?.addEventListener("click", () => {
      const pages = Math.max(Math.ceil(state.filtradas.length / state.perPage), 1);
      if (state.page >= pages) return;
      state.page++;
      renderCards();
    });

    document.addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-action]");
      if (!btn) return;

      if (btn.dataset.action === "visualizar") {
        await visualizarAgenda(btn.dataset.id);
      }
    });

    els.btnFecharModal?.addEventListener("click", fecharModal);
  }

  async function init() {
    atualizarHoje();
    bindEvents();
    await carregarAgendasBase();
  }

  document.addEventListener("DOMContentLoaded", init);
})();