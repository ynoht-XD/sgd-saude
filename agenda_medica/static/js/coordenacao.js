(() => {
  const API = "/agenda-medica/api";

  const state = {
    futuras: { page: 1, pages: 1 },
    passadas: { page: 1, pages: 1 },
    editandoId: null,
    cboTimer: null,
  };

  const $ = (sel) => document.querySelector(sel);

  const els = {
    hoje: $("#amHoje"),

    form: $("#formAgenda"),
    formTitulo: $("#formTitulo"),
    agendaId: $("#agendaId"),

    cboBusca: $("#cboBusca"),
    cboCodigo: $("#cboCodigo"),
    cboDescricao: $("#cboDescricao"),
    cboSugestoes: $("#cboSugestoes"),

    dataAtendimento: $("#dataAtendimento"),
    vagasNormais: $("#vagasNormais"),
    vagasEncaixe: $("#vagasEncaixe"),
    vagasTotal: $("#vagasTotal"),
    observacao: $("#observacao"),

    btnSalvar: $("#btnSalvar"),
    btnLimparForm: $("#btnLimparForm"),

    gridFuturas: $("#gridFuturas"),
    gridPassadas: $("#gridPassadas"),

    countFuturas: $("#countFuturas"),
    countPassadas: $("#countPassadas"),

    prevFuturas: $("#prevFuturas"),
    nextFuturas: $("#nextFuturas"),
    pageFuturas: $("#pageFuturas"),

    prevPassadas: $("#prevPassadas"),
    nextPassadas: $("#nextPassadas"),
    pagePassadas: $("#pagePassadas"),

    modal: $("#modalMarcacoes"),
    modalTitulo: $("#modalTitulo"),
    modalSubtitulo: $("#modalSubtitulo"),
    listaMarcacoes: $("#listaMarcacoes"),
    btnFecharModal: $("#btnFecharModal"),
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
    const [y, m, d] = iso.slice(0, 10).split("-");
    return `${d}/${m}/${y}`;
  }

  function statusLabel(status) {
    return String(status || "PENDENTE").toUpperCase();
  }

  function atualizarHoje() {
    const agora = new Date();
    els.hoje.textContent = agora.toLocaleDateString("pt-BR", {
      weekday: "long",
      day: "2-digit",
      month: "long",
    });
  }

  function atualizarTotal() {
    const normais = Number(els.vagasNormais.value || 0);
    const encaixe = Number(els.vagasEncaixe.value || 0);
    els.vagasTotal.value = normais + encaixe;
  }

  function limparForm() {
    state.editandoId = null;

    els.formTitulo.textContent = "Liberar agenda";
    els.btnSalvar.textContent = "Salvar agenda";

    els.agendaId.value = "";
    els.cboBusca.value = "";
    els.cboCodigo.value = "";
    els.cboDescricao.value = "";
    els.dataAtendimento.value = "";
    els.vagasNormais.value = 0;
    els.vagasEncaixe.value = 0;
    els.vagasTotal.value = 0;
    els.observacao.value = "";

    fecharSugestoes();
  }

  function fecharSugestoes() {
    els.cboSugestoes.classList.remove("open");
    els.cboSugestoes.innerHTML = "";
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

  async function buscarCbos(q) {
    const data = await fetchJson(`${API}/cbos?q=${encodeURIComponent(q)}`);
    return data.cbos || [];
  }

  function renderSugestoes(cbos) {
    if (!cbos.length) {
      els.cboSugestoes.innerHTML = `
        <div class="am-suggestion">
          <strong>Nenhum CBO encontrado</strong>
          <span>Confira se a biblioteca de CBO foi importada.</span>
        </div>
      `;
      els.cboSugestoes.classList.add("open");
      return;
    }

    els.cboSugestoes.innerHTML = cbos.map((cbo) => `
      <div class="am-suggestion"
           data-codigo="${cbo.codigo || ""}"
           data-descricao="${String(cbo.descricao || "").replaceAll('"', "&quot;")}">
        <strong>${cbo.codigo || ""}</strong>
        <span>${cbo.descricao || ""}</span>
      </div>
    `).join("");

    els.cboSugestoes.classList.add("open");
  }

  async function carregarCards(tipo) {
    const cfg = state[tipo];
    const grid = tipo === "futuras" ? els.gridFuturas : els.gridPassadas;
    const countEl = tipo === "futuras" ? els.countFuturas : els.countPassadas;
    const pageEl = tipo === "futuras" ? els.pageFuturas : els.pagePassadas;

    grid.innerHTML = `<div class="am-empty">Carregando agendas...</div>`;

    try {
      const data = await fetchJson(
        `${API}/liberacoes/cards?tipo=${tipo}&page=${cfg.page}&per_page=6`
      );

      cfg.page = data.page;
      cfg.pages = data.pages;

      countEl.textContent = `${data.total} registro${data.total === 1 ? "" : "s"}`;
      pageEl.textContent = `Página ${data.page} de ${data.pages}`;

      if (!data.items.length) {
        grid.innerHTML = `<div class="am-empty">Nenhuma agenda encontrada.</div>`;
        return;
      }

      grid.innerHTML = data.items.map(cardTemplate).join("");
    } catch (err) {
      grid.innerHTML = `<div class="am-empty">${err.message}</div>`;
    }
  }

  function cardTemplate(item) {
    const ocupadas = Number(item.capacidade_ocupada || 0);
    const total = Number(item.capacidade_total || 0);
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
            <span>Pend.</span>
          </div>
          <div class="am-metric">
            <strong>${item.aceitos || 0}</strong>
            <span>Aceitos</span>
          </div>
        </div>

        <div class="am-card-actions">
          <button class="am-btn am-btn-primary" data-action="ver" data-id="${item.id}">
            Ver
          </button>
          <button class="am-btn am-btn-light" data-action="editar" data-id="${item.id}">
            Editar
          </button>
          <button class="am-btn am-btn-danger" data-action="excluir" data-id="${item.id}">
            Excluir
          </button>
        </div>
      </article>
    `;
  }

  async function salvarAgenda(e) {
    e.preventDefault();

    atualizarTotal();

    const payload = {
      cbo: els.cboCodigo.value,
      cbo_descricao: els.cboDescricao.value,
      data_atendimento: els.dataAtendimento.value,
      vagas_normais: Number(els.vagasNormais.value || 0),
      vagas_encaixe: Number(els.vagasEncaixe.value || 0),
      observacao: els.observacao.value.trim(),
    };

    if (!payload.cbo || !payload.cbo_descricao) {
      toast("Selecione um CBO da lista.", "erro");
      return;
    }

    if (!payload.data_atendimento) {
      toast("Informe a data da agenda.", "erro");
      return;
    }

    if ((payload.vagas_normais + payload.vagas_encaixe) <= 0) {
      toast("Informe ao menos 1 vaga.", "erro");
      return;
    }

    const editando = Boolean(state.editandoId);
    const url = editando
      ? `${API}/liberacoes/${state.editandoId}`
      : `${API}/liberacoes`;

    const method = editando ? "PUT" : "POST";

    els.btnSalvar.disabled = true;
    els.btnSalvar.textContent = editando ? "Atualizando..." : "Salvando...";

    try {
      const data = await fetchJson(url, {
        method,
        body: JSON.stringify(payload),
      });

      toast(data.mensagem || "Salvo com sucesso.", "ok");
      limparForm();
      await recarregarTudo();
    } catch (err) {
      toast(err.message, "erro");
    } finally {
      els.btnSalvar.disabled = false;
      els.btnSalvar.textContent = state.editandoId ? "Atualizar agenda" : "Salvar agenda";
    }
  }

  async function editarAgenda(id) {
    try {
      const data = await fetchJson(`${API}/liberacoes/${id}`);
      const ag = data.agenda;

      state.editandoId = id;

      els.formTitulo.textContent = "Editar agenda";
      els.btnSalvar.textContent = "Atualizar agenda";

      els.agendaId.value = ag.id;
      els.cboCodigo.value = ag.cbo || "";
      els.cboDescricao.value = ag.cbo_descricao || "";
      els.cboBusca.value = `${ag.cbo || ""} - ${ag.cbo_descricao || ""}`;
      els.dataAtendimento.value = ag.data_atendimento || "";
      els.vagasNormais.value = ag.vagas_normais || 0;
      els.vagasEncaixe.value = ag.vagas_encaixe || 0;
      els.vagasTotal.value = ag.capacidade_total || 0;
      els.observacao.value = ag.observacao || "";

      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      toast(err.message, "erro");
    }
  }

  async function excluirAgenda(id) {
    const ok = confirm("Deseja excluir esta agenda? As marcações vinculadas ficarão ocultas junto com ela.");
    if (!ok) return;

    try {
      const data = await fetchJson(`${API}/liberacoes/${id}`, {
        method: "DELETE",
      });

      toast(data.mensagem || "Agenda excluída.", "ok");
      await recarregarTudo();
    } catch (err) {
      toast(err.message, "erro");
    }
  }

  async function verMarcacoes(id) {
    try {
      const agendaResp = await fetchJson(`${API}/liberacoes/${id}`);
      const agenda = agendaResp.agenda;

      els.modalTitulo.textContent = `${agenda.cbo} - ${agenda.cbo_descricao}`;
      els.modalSubtitulo.textContent = `${formatDate(agenda.data_atendimento)} • ${agenda.capacidade_ocupada}/${agenda.capacidade_total} vagas usadas`;

      els.listaMarcacoes.innerHTML = `<div class="am-empty">Carregando marcações...</div>`;

      if (typeof els.modal.showModal === "function") {
        els.modal.showModal();
      } else {
        els.modal.setAttribute("open", "open");
      }

      const data = await fetchJson(`${API}/liberacoes/${id}/marcacoes`);
      renderMarcacoes(data.marcacoes || []);
    } catch (err) {
      toast(err.message, "erro");
    }
  }

  function renderMarcacoes(marcacoes) {
    if (!marcacoes.length) {
      els.listaMarcacoes.innerHTML = `
        <div class="am-empty">
          Nenhum paciente foi marcado ainda. Agenda limpinha, igual mesa antes do café.
        </div>
      `;
      return;
    }

    els.listaMarcacoes.innerHTML = marcacoes.map((m) => {
      const status = statusLabel(m.status);
      const pendente = status === "PENDENTE";

      return `
        <article class="am-paciente" data-marcacao-id="${m.id}">
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

          ${pendente ? `
            <div class="am-card-actions">
              <button class="am-btn am-btn-success" data-action="aceitar" data-id="${m.id}">
                Aceitar
              </button>
              <button class="am-btn am-btn-danger" data-action="recusar" data-id="${m.id}">
                Recusar
              </button>
            </div>
          ` : ""}
        </article>
      `;
    }).join("");
  }

  async function aceitarMarcacao(id) {
    try {
      const data = await fetchJson(`${API}/marcacoes/${id}/aceitar`, {
        method: "POST",
        body: JSON.stringify({}),
      });

      toast(data.mensagem || "Marcação aceita.", "ok");

      const agendaId = document.querySelector(".am-card[data-id]")?.dataset?.id;
      await recarregarTudo();

      if (agendaId) {
        // mantém a tela atualizada; modal pode ser reaberto pelo usuário
      }
    } catch (err) {
      toast(err.message, "erro");
    }
  }

  async function recusarMarcacao(id) {
    const justificativa = prompt("Informe a justificativa da recusa:");
    if (justificativa === null) return;

    try {
      const data = await fetchJson(`${API}/marcacoes/${id}/recusar`, {
        method: "POST",
        body: JSON.stringify({ justificativa }),
      });

      toast(data.mensagem || "Marcação recusada.", "ok");
      els.modal.close?.();
      await recarregarTudo();
    } catch (err) {
      toast(err.message, "erro");
    }
  }

  async function recarregarTudo() {
    await Promise.all([
      carregarCards("futuras"),
      carregarCards("passadas"),
    ]);
  }

  function bindEvents() {
    els.vagasNormais.addEventListener("input", atualizarTotal);
    els.vagasEncaixe.addEventListener("input", atualizarTotal);

    els.form.addEventListener("submit", salvarAgenda);

    els.btnLimparForm.addEventListener("click", limparForm);

    els.cboBusca.addEventListener("input", () => {
      const q = els.cboBusca.value.trim();

      els.cboCodigo.value = "";
      els.cboDescricao.value = "";

      clearTimeout(state.cboTimer);

      if (q.length < 3) {
        fecharSugestoes();
        return;
      }

      state.cboTimer = setTimeout(async () => {
        try {
          const cbos = await buscarCbos(q);
          renderSugestoes(cbos);
        } catch (err) {
        console.error("Erro ao buscar CBO:", err);
        renderSugestoes([]);
        }
      }, 280);
    });

    els.cboSugestoes.addEventListener("click", (e) => {
      const item = e.target.closest(".am-suggestion");
      if (!item) return;

      const codigo = item.dataset.codigo || "";
      const descricao = item.dataset.descricao || "";

      if (!codigo || !descricao) return;

      els.cboCodigo.value = codigo;
      els.cboDescricao.value = descricao;
      els.cboBusca.value = `${codigo} - ${descricao}`;

      fecharSugestoes();
    });

    document.addEventListener("click", (e) => {
      if (!e.target.closest(".am-autocomplete-wrap")) {
        fecharSugestoes();
      }
    });

    document.addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-action]");
      if (!btn) return;

      const action = btn.dataset.action;
      const id = btn.dataset.id;

      if (action === "ver") await verMarcacoes(id);
      if (action === "editar") await editarAgenda(id);
      if (action === "excluir") await excluirAgenda(id);
      if (action === "aceitar") await aceitarMarcacao(id);
      if (action === "recusar") await recusarMarcacao(id);
    });

    els.prevFuturas.addEventListener("click", async () => {
      if (state.futuras.page <= 1) return;
      state.futuras.page--;
      await carregarCards("futuras");
    });

    els.nextFuturas.addEventListener("click", async () => {
      if (state.futuras.page >= state.futuras.pages) return;
      state.futuras.page++;
      await carregarCards("futuras");
    });

    els.prevPassadas.addEventListener("click", async () => {
      if (state.passadas.page <= 1) return;
      state.passadas.page--;
      await carregarCards("passadas");
    });

    els.nextPassadas.addEventListener("click", async () => {
      if (state.passadas.page >= state.passadas.pages) return;
      state.passadas.page++;
      await carregarCards("passadas");
    });

    els.btnFecharModal.addEventListener("click", () => {
      if (typeof els.modal.close === "function") {
        els.modal.close();
      } else {
        els.modal.removeAttribute("open");
      }
    });
  }

  async function init() {
    atualizarHoje();
    atualizarTotal();
    bindEvents();
    await recarregarTudo();
  }

  document.addEventListener("DOMContentLoaded", init);
})();