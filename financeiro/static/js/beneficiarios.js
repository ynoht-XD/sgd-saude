(() => {
  "use strict";

  // =========================================================
  // Gerenciar beneficiários de um contrato (plano familiar)
  //
  // Painel (dialog) aberto pelo botão "Gerenciar beneficiários" do cartão
  // de vínculo (comercial.js). Usa só a API que já existe:
  //   GET    /financeiro/api/pacientes-planos/<id>/beneficiarios
  //   POST   /financeiro/api/pacientes-planos/<id>/beneficiarios   {paciente_id}
  //   DELETE /financeiro/api/pacientes-planos/<id>/beneficiarios/<paciente_id>
  //   GET    /financeiro/api/pacientes/buscar?q=
  // Todas as regras (limite, titular, contrato ativo) são da API; o front
  // só avisa o limite antes de tentar e mostra o erro que a API devolver.
  // =========================================================
  const BASE = "/financeiro/api";
  const EVENTO_ALTERADO = "financeiro:beneficiarios-alterados";

  const $ = (sel, root = document) => root.querySelector(sel);

  const dlg = $("#modalBeneficiarios");
  if (!dlg) return;

  const els = {
    titulo: $("#benefSubtitulo", dlg),
    vagas: $("#benefVagas", dlg),
    lista: $("#benefLista", dlg),
    aviso: $("#benefAviso", dlg),
    busca: $("#benefBusca", dlg),
    resultados: $("#benefResultados", dlg),
    selecionado: $("#benefSelecionado", dlg),
    adicionar: $("#benefAdicionar", dlg),
    fechar: $("#benefFechar", dlg),
    fecharX: $("#benefFecharX", dlg),
    addBox: $("#benefAddBox", dlg),
  };

  const state = {
    contratoId: null,
    max: 1,
    nomeTitular: "",
    itens: [],
    selecionado: null,
    seq: 0,
    ocupado: false,
  };

  const toast = (msg) => window.alert(msg);

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  const digits = (v) => String(v ?? "").replace(/\D+/g, "");

  function debounce(fn, delay = 250) {
    let timer = null;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), delay);
    };
  }

  async function requestJSON(url, options = {}) {
    const res = await fetch(url, {
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });

    let data = null;
    try {
      data = await res.json();
    } catch {
      data = null;
    }

    if (!res.ok || !data || data.ok === false) {
      throw new Error(data?.erro || `Erro na requisição (${res.status}).`);
    }

    return data;
  }

  function abrir() {
    if (typeof dlg.showModal === "function") {
      if (!dlg.open) dlg.showModal();
    } else {
      dlg.classList.add("open");
    }
  }

  function fechar() {
    if (typeof dlg.close === "function") {
      dlg.close();
    } else {
      dlg.classList.remove("open");
    }
  }

  function notificarAlteracao() {
    document.dispatchEvent(new CustomEvent(EVENTO_ALTERADO, { detail: { contratoId: state.contratoId } }));
  }

  function setAviso(texto) {
    els.aviso.textContent = texto || "";
  }

  // ---------------------------------------------------------
  // Render
  // ---------------------------------------------------------
  function render() {
    const ativos = state.itens.length;
    const cheio = ativos >= state.max;

    els.vagas.textContent = `${ativos} de ${state.max} vagas ocupadas (o titular ocupa uma vaga)`;

    const titular = state.itens.find((it) => it.eh_titular);
    const outros = state.itens.filter((it) => !it.eh_titular);

    const linhaTitular = `
      <li class="com-benef-item com-benef-item--titular" data-titular="1">
        <div class="com-benef-nome">
          <strong>${escapeHtml(titular?.paciente_nome || state.nomeTitular || "Titular")}</strong>
          <span>Responsável financeiro</span>
        </div>
        <span class="com-badge com-badge--plan">Titular</span>
      </li>
    `;

    const linhasOutros = outros.map((it) => `
      <li class="com-benef-item" data-paciente-id="${escapeHtml(it.paciente_id)}">
        <div class="com-benef-nome">
          <strong>${escapeHtml(it.paciente_nome || "Sem nome")}</strong>
          <span>Beneficiário</span>
        </div>
        <button type="button" class="com-btn com-btn--ghost"
                data-benef-action="desativar" data-paciente-id="${escapeHtml(it.paciente_id)}"
                data-nome="${escapeHtml(it.paciente_nome || "")}">
          Desativar
        </button>
      </li>
    `).join("");

    els.lista.innerHTML = linhaTitular + linhasOutros;

    // Limite: avisa e bloqueia antes de tentar (a API garante de qualquer forma).
    els.busca.disabled = cheio;
    els.addBox.classList.toggle("is-cheio", cheio);

    if (cheio) {
      limparBusca();
      els.selecionado.innerHTML = `<div class="com-patient-empty">Limite de beneficiários atingido (${state.max}). Desative um beneficiário para liberar uma vaga.</div>`;
    } else {
      renderSelecionado();
    }

    els.adicionar.disabled = cheio || !state.selecionado || state.ocupado;
  }

  function renderSelecionado() {
    const p = state.selecionado;

    if (!p) {
      els.selecionado.innerHTML = `<div class="com-patient-empty">Nenhum paciente selecionado.</div>`;
      return;
    }

    const cpf = digits(p.cpf);
    const cns = digits(p.cns);

    els.selecionado.innerHTML = `
      <div class="com-patient-card">
        <strong>${escapeHtml(p.nome || "Sem nome")}</strong>
        <div class="com-patient-meta">
          ${cpf ? `CPF: ${escapeHtml(cpf)}` : ""}${cpf && cns ? " · " : ""}${cns ? `CNS: ${escapeHtml(cns)}` : ""}
        </div>
      </div>
    `;
  }

  function limparBusca() {
    state.selecionado = null;
    state.seq += 1;
    els.busca.value = "";
    els.resultados.hidden = true;
    els.resultados.innerHTML = "";
  }

  // ---------------------------------------------------------
  // Dados
  // ---------------------------------------------------------
  async function carregar() {
    const data = await requestJSON(`${BASE}/pacientes-planos/${state.contratoId}/beneficiarios`);
    state.itens = Array.isArray(data.items) ? data.items : [];
    render();
  }

  async function abrirPara(btn) {
    state.contratoId = Number(btn.dataset.id);
    state.max = Math.max(1, Number(btn.dataset.max) || 1);
    state.nomeTitular = btn.dataset.nome || "";
    state.itens = [];
    state.selecionado = null;
    state.ocupado = false;

    els.titulo.textContent = btn.dataset.plano
      ? `${btn.dataset.plano} · titular: ${state.nomeTitular || "—"}`
      : `Titular: ${state.nomeTitular || "—"}`;

    limparBusca();
    setAviso("");
    els.lista.innerHTML = `<li class="com-empty">Carregando...</li>`;
    els.vagas.textContent = "";
    els.adicionar.disabled = true;

    abrir();

    try {
      await carregar();
    } catch (err) {
      els.lista.innerHTML = "";
      toast(err.message || "Não foi possível carregar os beneficiários.");
    }
  }

  async function buscar(q) {
    const termo = String(q || "").trim();
    const minha = ++state.seq;

    if (termo.length < 2) {
      els.resultados.hidden = true;
      els.resultados.innerHTML = "";
      return;
    }

    try {
      const data = await requestJSON(`${BASE}/pacientes/buscar?q=${encodeURIComponent(termo)}`);

      // resposta de uma digitação antiga: descarta
      if (minha !== state.seq) return;

      // quem já está no contrato não é candidato
      const jaNaLista = new Set(state.itens.map((it) => String(it.paciente_id)));
      const itens = (Array.isArray(data.items) ? data.items : []).filter((it) => !jaNaLista.has(String(it.id)));

      els.resultados.hidden = false;

      if (!itens.length) {
        els.resultados.innerHTML = `<div class="com-empty">Nenhum paciente encontrado.</div>`;
        return;
      }

      els.resultados.innerHTML = itens.map((it) => {
        const cpf = digits(it.cpf);
        const cns = digits(it.cns);

        return `
          <button type="button" class="com-search-item" data-benef-action="selecionar"
                  data-id="${escapeHtml(it.id)}" data-nome="${escapeHtml(it.nome || "")}"
                  data-cpf="${escapeHtml(cpf)}" data-cns="${escapeHtml(cns)}">
            <strong>${escapeHtml(it.nome || "Sem nome")}</strong>
            <span>${cpf ? `CPF: ${escapeHtml(cpf)}` : ""}${cpf && cns ? " · " : ""}${cns ? `CNS: ${escapeHtml(cns)}` : ""}${!cpf && !cns ? "Sem CPF/CNS" : ""}</span>
          </button>
        `;
      }).join("");
    } catch (err) {
      if (minha !== state.seq) return;
      els.resultados.hidden = false;
      els.resultados.innerHTML = `<div class="com-empty">${escapeHtml(err.message || "Erro ao buscar pacientes.")}</div>`;
    }
  }

  function selecionar(ds) {
    state.selecionado = { id: ds.id, nome: ds.nome, cpf: ds.cpf, cns: ds.cns };
    els.resultados.hidden = true;
    els.resultados.innerHTML = "";
    els.busca.value = ds.nome || "";
    renderSelecionado();
    els.adicionar.disabled = state.ocupado;
  }

  async function adicionarSelecionado() {
    if (!state.selecionado || state.ocupado) return;

    state.ocupado = true;
    els.adicionar.disabled = true;
    const textoOriginal = els.adicionar.textContent;
    els.adicionar.textContent = "Adicionando...";

    try {
      const data = await requestJSON(`${BASE}/pacientes-planos/${state.contratoId}/beneficiarios`, {
        method: "POST",
        body: JSON.stringify({ paciente_id: Number(state.selecionado.id) }),
      });

      state.itens = Array.isArray(data.items) ? data.items : state.itens;
      limparBusca();
      setAviso(data.mensagem || "Beneficiário adicionado.");
      notificarAlteracao();
    } catch (err) {
      setAviso("");
      toast(err.message || "Não foi possível adicionar o beneficiário.");
    } finally {
      state.ocupado = false;
      els.adicionar.textContent = textoOriginal;
      render();
    }
  }

  async function desativar(btn) {
    if (state.ocupado) return;

    state.ocupado = true;
    btn.disabled = true;

    try {
      const data = await requestJSON(
        `${BASE}/pacientes-planos/${state.contratoId}/beneficiarios/${encodeURIComponent(btn.dataset.pacienteId)}`,
        { method: "DELETE" }
      );

      state.itens = Array.isArray(data.items) ? data.items : state.itens;
      setAviso(data.mensagem || "Beneficiário removido.");
      notificarAlteracao();
    } catch (err) {
      setAviso("");
      toast(err.message || "Não foi possível desativar o beneficiário.");
    } finally {
      state.ocupado = false;
      render();
    }
  }

  // ---------------------------------------------------------
  // Eventos
  // ---------------------------------------------------------
  document.addEventListener("click", (ev) => {
    const abrirBtn = ev.target.closest("[data-action='gerenciar-beneficiarios']");
    if (abrirBtn) {
      abrirPara(abrirBtn);
    }
  });

  els.busca.addEventListener("input", () => {
    // digitar de novo invalida o paciente escolhido antes
    if (state.selecionado) {
      state.selecionado = null;
      renderSelecionado();
      els.adicionar.disabled = true;
    }
    buscarDebounced(els.busca.value);
  });

  const buscarDebounced = debounce(buscar, 250);

  els.resultados.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-benef-action='selecionar']");
    if (btn) selecionar(btn.dataset);
  });

  els.lista.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-benef-action='desativar']");
    if (btn) desativar(btn);
  });

  els.adicionar.addEventListener("click", adicionarSelecionado);
  els.fechar.addEventListener("click", fechar);
  els.fecharX.addEventListener("click", fechar);
})();
