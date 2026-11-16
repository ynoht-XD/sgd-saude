/* Documentos do atendimento: formulario por tipo, CID/procedimento com autocomplete, lista, cancelamento.
 * O servidor e a validacao de verdade; aqui so ajudamos o preenchimento. Nenhum dado de paciente vai para console/log. */
(() => {
  "use strict";

  const page = document.getElementById("docPage");
  if (!page) return;

  // Lidos na hora do uso (getters): na tela de registrar o atendimento so tem id DEPOIS de salvar (ver SGDDocumentos.ativar no fim).
  const CFG = {
    get atendimentoId() { return page.dataset.atendimentoId || ""; },
    get dataAtendimento() { return page.dataset.dataAtendimento || ""; },
    get urlLista() { return page.dataset.urlLista; },
    get urlCriar() { return page.dataset.urlCriar; },
    get urlBase() { return page.dataset.urlBase; },
    get urlCid() { return page.dataset.urlCid; },
    get urlProc() { return page.dataset.urlProc; },
  };

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
  const debounce = (fn, ms = 250) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

  const dlg = $("#docDialog");
  const form = $("#docForm");
  const campos = $("#docCampos");
  const erros = $("#docErros");
  let tipoAtual = "";
  let cidSel = null;

  // ------------------------------------------------------------------ rede
  async function api(url, opts = {}) {
    const res = await fetch(url, { credentials: "same-origin", ...opts, headers: { "Content-Type": "application/json", ...(opts.headers || {}) } });
    const tipo = (res.headers.get("content-type") || "").toLowerCase();
    if (res.redirected || (res.ok && !tipo.includes("application/json"))) throw Object.assign(new Error("Sua sessão expirou. Entre novamente."), { status: 401 });
    const data = tipo.includes("application/json") ? await res.json() : null;
    if (res.status === 403) throw Object.assign(new Error("Você não tem permissão para esta ação."), { status: 403 });
    if (!res.ok || !data || data.ok === false) throw Object.assign(new Error(data?.error || `Erro ${res.status}.`), { status: res.status, erros: data?.erros });
    return data;
  }

  // ------------------------------------------------------------------ autocomplete generico
  function ligarBusca({ input, caixa, url, extra = "", vazio, aoEscolher }) {
    const buscar = debounce(async () => {
      const q = input.value.trim();
      if (q.length < 2) { caixa.hidden = true; return; }
      try {
        const data = await api(`${url}?q=${encodeURIComponent(q)}${extra}`);
        caixa.innerHTML = data.items.length
          ? data.items.map((it, i) => `<button type="button" data-i="${i}">${esc(it.label)}</button>`).join("")
          : `<small>${esc(vazio)}</small>`;
        caixa.hidden = false;
        $$("button", caixa).forEach((b) => b.addEventListener("click", () => { aoEscolher(data.items[Number(b.dataset.i)]); caixa.hidden = true; }));
      } catch (e) {
        caixa.innerHTML = `<small>${esc(e.message)}</small>`;
        caixa.hidden = false;
      }
    });
    input.addEventListener("input", buscar);
    input.addEventListener("blur", () => setTimeout(() => { caixa.hidden = true; }, 180));
  }

  // ------------------------------------------------------------------ CID (opcional) - comum a todos os tipos
  function cidHtml() {
    return `
      <div class="doc-campo">
        <span>CID-10 (opcional)</span>
        <div class="doc-sug-wrap">
          <input class="doc-cid-busca" id="cidBusca" type="text" autocomplete="off" placeholder="Código ou nome (ex.: F84 ou autismo)">
          <div class="doc-sug" id="cidSug" hidden></div>
        </div>
        <div id="cidSel"></div>
      </div>`;
  }

  function mostrarCid() {
    const box = $("#cidSel");
    if (!cidSel) { box.innerHTML = ""; return; }
    box.innerHTML = `<span class="doc-selecionado">${esc(cidSel.codigo)}${cidSel.descricao ? " — " + esc(cidSel.descricao) : ""}<button type="button" id="cidLimpar" aria-label="Remover CID">×</button></span>`;
    $("#cidLimpar").addEventListener("click", () => { cidSel = null; mostrarCid(); });
    $("#cidBusca").value = "";
  }

  function ligarCid() {
    ligarBusca({
      input: $("#cidBusca"), caixa: $("#cidSug"), url: CFG.urlCid,
      vazio: "Nenhum CID encontrado (a base pode não estar importada). O CID é opcional: você pode digitar o código.",
      aoEscolher: (it) => { cidSel = { codigo: it.codigo, descricao: it.descricao }; mostrarCid(); },
    });
    mostrarCid();
  }

  function coletaCid() {
    if (cidSel) return cidSel;
    const manual = ($("#cidBusca")?.value || "").trim();
    return manual ? { codigo: manual, descricao: "" } : null;
  }

  // ------------------------------------------------------------------ tipos
  const campo = (rotulo, html) => `<label class="doc-campo"><span>${rotulo}</span>${html}</label>`;
  const urgenciaHtml = () => campo("Urgência", `<select name="urgencia"><option value="eletivo">Eletivo</option><option value="prioritario">Prioritário</option><option value="urgente">Urgente</option></select>`);

  function linhaMedicamento() {
    return `
      <div class="doc-bloco" data-item>
        <div class="doc-bloco-topo"><strong>Medicamento</strong><button type="button" class="doc-mini perigo" data-remover>Remover</button></div>
        ${campo("Nome do medicamento *", `<input type="text" data-k="medicamento" maxlength="200">`)}
        <div class="doc-linha">
          ${campo("Dose", `<input type="text" data-k="dose" maxlength="100" placeholder="ex.: 500 mg">`)}
          ${campo("Via", `<input type="text" data-k="via" maxlength="60" placeholder="ex.: oral">`)}
          ${campo("Duração", `<input type="text" data-k="duracao" maxlength="100" placeholder="ex.: 7 dias">`)}
          ${campo("Quantidade", `<input type="text" data-k="quantidade" maxlength="60" placeholder="ex.: 1 caixa">`)}
        </div>
        ${campo("Posologia *", `<textarea data-k="posologia" rows="2" maxlength="500" placeholder="ex.: 1 comprimido a cada 8 horas"></textarea>`)}
        ${campo("Observação", `<input type="text" data-k="observacao" maxlength="300">`)}
      </div>`;
  }

  function linhaExame() {
    return `
      <div class="doc-bloco" data-item>
        <div class="doc-bloco-topo"><strong>Exame</strong><button type="button" class="doc-mini perigo" data-remover>Remover</button></div>
        <div class="doc-campo">
          <span>Exame * (busque no catálogo ou digite livremente)</span>
          <div class="doc-sug-wrap">
            <input type="text" data-k="descricao" maxlength="300" autocomplete="off" placeholder="Nome do exame ou código SIGTAP">
            <div class="doc-sug" hidden></div>
          </div>
          <input type="hidden" data-k="procedimento_codigo" value="">
          <p class="doc-dica" data-dica>Sem código: será impresso como texto livre.</p>
        </div>
        ${campo("Observação", `<input type="text" data-k="observacao" maxlength="300">`)}
      </div>`;
  }

  function ligarRepetidor(boxSel, criar, aoCriar) {
    const box = $(boxSel);
    const add = () => {
      box.insertAdjacentHTML("beforeend", criar());
      const item = box.lastElementChild;
      $("[data-remover]", item).addEventListener("click", () => { if ($$("[data-item]", box).length > 1) item.remove(); });
      if (aoCriar) aoCriar(item);
    };
    add();
    return add;
  }

  const TIPOS = {
    receita: {
      rotulo: "Receita",
      html: () => `<div id="itens"></div><button type="button" class="doc-btn sec" id="addItem">+ Adicionar medicamento</button>
                   ${campo("Orientações gerais", `<textarea name="orientacoes_gerais" rows="3" maxlength="2000"></textarea>`)}`,
      ligar: () => { const add = ligarRepetidor("#itens", linhaMedicamento); $("#addItem").addEventListener("click", add); },
      coleta: () => ({
        itens: $$("#itens [data-item]").map((it) => Object.fromEntries($$("[data-k]", it).map((e) => [e.dataset.k, e.value]))),
        orientacoes_gerais: $("[name=orientacoes_gerais]").value,
      }),
    },
    atestado: {
      rotulo: "Atestado",
      html: () => `
        <div class="doc-campo"><span class="doc-legenda">Tipo de atestado *</span>
          <div class="doc-radios">
            <label><input type="radio" name="modalidade" value="afastamento" checked> Afastamento</label>
            <label><input type="radio" name="modalidade" value="comparecimento"> Comparecimento</label>
          </div></div>
        <div id="blocoAfastamento" class="doc-linha">
          ${campo("Dias de afastamento *", `<input type="number" name="dias" min="1" max="365" value="1">`)}
          ${campo("A partir de", `<input type="date" name="data_inicio" value="${esc(CFG.dataAtendimento)}">`)}
        </div>
        <div id="blocoComparecimento" class="doc-linha" hidden>
          ${campo("Data", `<input type="date" name="data" value="${esc(CFG.dataAtendimento)}">`)}
          ${campo("Hora de início", `<input type="time" name="hora_inicio">`)}
          ${campo("Hora de término", `<input type="time" name="hora_fim">`)}
        </div>
        ${campo("Observação", `<textarea name="observacao" rows="2" maxlength="2000"></textarea>`)}
        <label class="doc-check"><input type="checkbox" name="incluir_cid"> Incluir o CID no atestado</label>`,
      ligar: () => {
        const alterna = () => {
          const af = $("[name=modalidade]:checked").value === "afastamento";
          $("#blocoAfastamento").hidden = !af; $("#blocoComparecimento").hidden = af;
        };
        $$("[name=modalidade]").forEach((r) => r.addEventListener("change", alterna));
      },
      coleta: () => {
        const m = $("[name=modalidade]:checked").value;
        const base = { modalidade: m, observacao: $("[name=observacao]").value, incluir_cid: $("[name=incluir_cid]").checked };
        return m === "afastamento"
          ? { ...base, dias: $("[name=dias]").value, data_inicio: $("[name=data_inicio]").value }
          : { ...base, data: $("[name=data]").value, hora_inicio: $("[name=hora_inicio]").value, hora_fim: $("[name=hora_fim]").value };
      },
    },
    declaracao: {
      rotulo: "Declaração",
      html: () => `${campo("Finalidade", `<input type="text" name="finalidade" maxlength="200" placeholder="ex.: Declaração de comparecimento / acompanhamento">`)}
                   ${campo("Texto da declaração *", `<textarea name="texto" rows="8" maxlength="5000" placeholder="Escreva o texto da declaração."></textarea>`)}`,
      ligar: () => {},
      coleta: () => ({ finalidade: $("[name=finalidade]").value, texto: $("[name=texto]").value }),
    },
    encaminhamento: {
      rotulo: "Encaminhamento",
      html: () => `${campo("Especialidade ou serviço de destino *", `<input type="text" name="especialidade_destino" maxlength="200" placeholder="ex.: Neuropediatria">`)}
                   ${campo("Profissional de destino", `<input type="text" name="profissional_destino" maxlength="200">`)}
                   ${urgenciaHtml()}
                   ${campo("Motivo do encaminhamento *", `<textarea name="motivo" rows="4" maxlength="2000"></textarea>`)}
                   ${campo("Resumo clínico", `<textarea name="resumo_clinico" rows="4" maxlength="3000"></textarea>`)}`,
      ligar: () => {},
      coleta: () => Object.fromEntries(["especialidade_destino", "profissional_destino", "urgencia", "motivo", "resumo_clinico"].map((k) => [k, $(`[name=${k}]`).value])),
    },
    solicitacao_exame: {
      rotulo: "Solicitação de exame",
      html: () => `<div id="itens"></div><button type="button" class="doc-btn sec" id="addItem">+ Adicionar exame</button>
                   ${urgenciaHtml()}
                   ${campo("Justificativa / indicação clínica", `<textarea name="justificativa" rows="3" maxlength="2000"></textarea>`)}
                   <p class="doc-dica">Somente texto: esta solicitação não aceita anexos.</p>`,
      ligar: () => {
        const preparar = (item) => {
          const desc = $("[data-k=descricao]", item), cod = $("[data-k=procedimento_codigo]", item), dica = $("[data-dica]", item), caixa = $(".doc-sug", item);
          ligarBusca({
            input: desc, caixa, url: CFG.urlProc, extra: "&grupo=02",
            vazio: "Nada encontrado no catálogo. Você pode digitar o exame livremente.",
            aoEscolher: (it) => { desc.value = it.descricao; cod.value = it.codigo; dica.textContent = `Código SIGTAP ${it.codigo}`; },
          });
          desc.addEventListener("input", () => { if (cod.value) { cod.value = ""; dica.textContent = "Sem código: será impresso como texto livre."; } });
        };
        const add = ligarRepetidor("#itens", linhaExame, preparar);
        $("#addItem").addEventListener("click", add);
      },
      coleta: () => ({
        exames: $$("#itens [data-item]").map((it) => Object.fromEntries($$("[data-k]", it).map((e) => [e.dataset.k, e.value]))),
        urgencia: $("[name=urgencia]").value,
        justificativa: $("[name=justificativa]").value,
      }),
    },
  };

  // ------------------------------------------------------------------ dialogo de emissao
  function mostrarErros(lista) {
    erros.hidden = !lista.length;
    erros.innerHTML = lista.length === 1 ? esc(lista[0]) : `<ul>${lista.map((e) => `<li>${esc(e)}</li>`).join("")}</ul>`;
  }

  function abrir(tipo) {
    tipoAtual = tipo; cidSel = null; mostrarErros([]);
    $("#docDialogTitulo").textContent = `Emitir ${TIPOS[tipo].rotulo.toLowerCase()}`;
    campos.innerHTML = cidHtml() + TIPOS[tipo].html();   // CID no topo: a lista de sugestoes abre para baixo, sobre os outros campos
    TIPOS[tipo].ligar();
    ligarCid();
    dlg.showModal();
    const primeiro = $("input:not([type=hidden]):not([type=radio]):not(.doc-cid-busca), textarea", campos);
    if (primeiro) primeiro.focus();
  }

  $$(".doc-tipo").forEach((b) => b.addEventListener("click", () => abrir(b.dataset.tipo)));
  $("#docFechar").addEventListener("click", () => dlg.close());
  $("#docCancelarForm").addEventListener("click", () => dlg.close());

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const btn = $("#docEmitir");
    btn.disabled = true; mostrarErros([]);
    try {
      const data = await api(CFG.urlCriar, { method: "POST", body: JSON.stringify({ tipo: tipoAtual, cid: coletaCid(), conteudo: TIPOS[tipoAtual].coleta() }) });
      dlg.close();
      await carregar(`Documento emitido: ${TIPOS[tipoAtual].rotulo} nº ${data.id}.`, data.id);
    } catch (e) {
      mostrarErros(e.erros && e.erros.length ? e.erros : [e.message || "Não foi possível emitir o documento."]);
    } finally {
      btn.disabled = false;
    }
  });

  // ------------------------------------------------------------------ lista
  const lista = $("#docLista");

  function fmtDataHora(iso) {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? "" : d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  }

  function itemHtml(d) {
    const cancelado = d.status === "cancelado";
    const meta = [d.resumo, d.cid_codigo ? `CID ${d.cid_codigo}` : "", `Emitido em ${fmtDataHora(d.emitido_em)}`, cancelado && d.cancelado_motivo ? `Motivo do cancelamento: ${d.cancelado_motivo}` : ""].filter(Boolean).join(" · ");
    const u = `${CFG.urlBase}/${d.id}/imprimir`;
    return `
      <article class="doc-item ${cancelado ? "cancelado" : ""}" data-id="${d.id}">
        <div class="doc-item-info">
          <div class="doc-item-tit">${esc(d.rotulo)} nº ${d.id}<span class="doc-selo ${cancelado ? "cancelado" : ""}">${cancelado ? "Cancelado" : "Emitido"}</span></div>
          <div class="doc-item-meta">${esc(meta)}</div>
        </div>
        <div class="doc-item-acoes">
          <a class="doc-mini" href="${u}" target="_blank" rel="noopener">Abrir</a>
          <a class="doc-mini" href="${u}?auto=1" target="_blank" rel="noopener">Imprimir</a>
          ${cancelado ? "" : `<button type="button" class="doc-mini perigo" data-cancelar="${d.id}" data-rotulo="${esc(d.rotulo)} nº ${d.id}">Cancelar</button>`}
        </div>
      </article>`;
  }

  async function carregar(aviso = "", destacarId = null) {
    try {
      const data = await api(CFG.urlLista);
      lista.innerHTML = (aviso ? `<p class="doc-selecionado" role="status">${esc(aviso)}</p>` : "") +
        (data.items.length ? data.items.map(itemHtml).join("") : `<p class="doc-vazio">Nenhum documento emitido neste atendimento.</p>`);
      $$("[data-cancelar]", lista).forEach((b) => b.addEventListener("click", () => abrirCancelamento(b.dataset.cancelar, b.dataset.rotulo)));
      if (destacarId) $(`[data-id="${destacarId}"]`, lista)?.scrollIntoView({ block: "nearest" });
    } catch (e) {
      lista.innerHTML = `<p class="doc-erros">${esc(e.message || "Não foi possível carregar os documentos.")}</p>`;
    }
  }

  // ------------------------------------------------------------------ cancelamento (soft-delete)
  const cdlg = $("#docCancelDialog");
  let cancelandoId = null;

  function abrirCancelamento(id, rotulo) {
    cancelandoId = id; $("#docCancelRotulo").textContent = rotulo; $("#docCancelMotivo").value = ""; $("#docCancelErro").hidden = true;
    cdlg.showModal();
  }

  $("#docCancelVoltar").addEventListener("click", () => cdlg.close());
  $("#docCancelForm").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const btn = $("#docCancelConfirmar"); btn.disabled = true;
    try {
      await api(`${CFG.urlBase}/${cancelandoId}/cancelar`, { method: "POST", body: JSON.stringify({ motivo: $("#docCancelMotivo").value }) });
      cdlg.close();
      await carregar("Documento cancelado.");
    } catch (e) {
      const el = $("#docCancelErro"); el.textContent = e.message || "Não foi possível cancelar."; el.hidden = false;
    } finally {
      btn.disabled = false;
    }
  });

  // Pagina propria de documentos: o atendimento ja existe, carrega a lista na hora.
  if (CFG.atendimentoId) carregar();

  // Tela de registrar atendimento: o painel e criado vazio e ativado depois de salvar (mesmas rotas, mesmo formulario).
  window.SGDDocumentos = {
    ativar({ atendimentoId, dataAtendimento = "" }) {
      const base = `/atendimentos/${encodeURIComponent(atendimentoId)}/documentos`;
      page.dataset.atendimentoId = String(atendimentoId);
      page.dataset.dataAtendimento = dataAtendimento;
      page.dataset.urlBase = base;
      page.dataset.urlCriar = base;
      page.dataset.urlLista = `${base}/api`;
      return carregar();
    },
  };
})();
