// sgd/atendimentos/static/js/atendimentos.js

// Procedimento padrao: vem do SERVIDOR (por CBO do profissional logado, so se for compativel); null = a linha comeca vazia.
let procPadrao = null;
let procSeq = 1;   // ids unicos para ligar <label for> as linhas de procedimento

let sugestoesCache = [];
let ultimoAtendimentoCache = null;
let cidsAtivos = [];   // condicoes ativas/cronicas do paciente (paciente_cids_ativos)

document.addEventListener("DOMContentLoaded", () => {
  console.log("📦 [atendimentos.js] carregado!");

  initComboCollapse();
  initComboToggle();
  initEvolucaoOculta();

  initPacienteFromURL();

  initProcedimentos();
  initModalSugestoes();
  initHistoricoProcedimentos();
  initVozEvolucao();
  initCidAtendimento();
  initCidAtivo();
  initSalvar();
});

/* ==========================================================
   MENSAGENS E CONFIRMACAO (substituem alert() e confirm() nativos)
========================================================== */

function toast(msg, tipo = "info") {
  let box = qs("#atdToasts");
  if (!box) {
    box = document.createElement("div");
    box.id = "atdToasts";
    box.className = "atd-toasts";
    box.setAttribute("role", "status");
    box.setAttribute("aria-live", "polite");
    document.body.appendChild(box);
  }

  const el = document.createElement("div");
  el.className = `atd-toast atd-toast--${tipo}`;
  el.textContent = msg;
  el.addEventListener("click", () => el.remove());
  box.appendChild(el);

  while (box.children.length > 3) box.firstElementChild.remove();

  setTimeout(() => el.remove(), tipo === "error" ? 7000 : 4000);
}

/* Pergunta Sim/Nao dentro da pagina. Devolve Promise<boolean>; Esc ou "Voltar" = false. */
function perguntar(mensagem, { titulo = "Confirmar", sim = "Confirmar", nao = "Voltar" } = {}) {
  const dlg = qs("#atdConfirmDialog");
  if (!dlg || typeof dlg.showModal !== "function") return Promise.resolve(window.confirm(mensagem));   // so se o <dialog> nao existir

  qs("#atdConfirmTitulo", dlg).textContent = titulo;
  qs("#atdConfirmTexto", dlg).textContent = mensagem;
  qs("#atdConfirmSim", dlg).textContent = sim;
  qs("#atdConfirmNao", dlg).textContent = nao;

  return new Promise((resolve) => {
    const fim = (valor) => {
      dlg.removeEventListener("cancel", aoEsc);
      qs("#atdConfirmSim", dlg).onclick = null;
      qs("#atdConfirmNao", dlg).onclick = null;
      if (dlg.open) dlg.close();
      resolve(valor);
    };
    const aoEsc = (ev) => { ev.preventDefault(); fim(false); };

    dlg.addEventListener("cancel", aoEsc);
    qs("#atdConfirmSim", dlg).onclick = () => fim(true);
    qs("#atdConfirmNao", dlg).onclick = () => fim(false);
    dlg.showModal();
    qs("#atdConfirmSim", dlg).focus();
  });
}

/* Botao de voz: icone SVG (em vez de emoji) + texto */
const ICONE_MIC = '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M12 15a3 3 0 0 0 3-3V7a3 3 0 0 0-6 0v5a3 3 0 0 0 3 3Zm6-3a6 6 0 0 1-12 0m6 6v3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const ICONE_REC = '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><circle cx="12" cy="12" r="6" fill="currentColor"/></svg>';

function rotuloVoz(btn, estado) {
  const mapa = { falar: [ICONE_MIC, "Falar"], ouvindo: [ICONE_REC, "Ouvindo"], indisponivel: [ICONE_MIC, "Indisponível"] };
  const [icone, texto] = mapa[estado] || mapa.falar;
  btn.innerHTML = `${icone}<span>${texto}</span>`;
}

/* ==========================================================
   HELPERS
========================================================== */

function qs(sel, root = document) {
  return root.querySelector(sel);
}

function qsa(sel, root = document) {
  return Array.from(root.querySelectorAll(sel));
}

function getParam(name) {
  return new URLSearchParams(window.location.search).get(name) || "";
}

function escapeHTML(s) {
  return String(s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function normalize(s) {
  return String(s || "").trim().toLowerCase();
}

function fmtISOToBR(value) {
  if (!value) return "—";
  const iso = String(value).slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return value;
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

function calcIdade(iso) {
  if (!iso || !/^\d{4}-\d{2}-\d{2}/.test(iso)) return "—";

  const nasc = new Date(`${String(iso).slice(0, 10)}T00:00:00`);
  const hoje = new Date();

  let idade = hoje.getFullYear() - nasc.getFullYear();
  const m = hoje.getMonth() - nasc.getMonth();

  if (m < 0 || (m === 0 && hoje.getDate() < nasc.getDate())) idade--;

  return `${idade} ano(s)`;
}

function setText(id, value, fallback = "—") {
  const el = document.getElementById(id);
  if (el) el.textContent = value || fallback;
}

function setValue(id, value) {
  const el = document.getElementById(id);
  if (el) el.value = value ?? "";
}

function getPacienteId() {
  return (qs("#nomePaciente")?.value || getParam("paciente_id") || "").trim();
}

function getFilaId() {
  return (qs("#fila_id")?.value || getParam("fila_id") || "").trim();
}

function debounce(fn, delay = 180) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

/* ==========================================================
   FETCHERS
========================================================== */

async function fetchJSON(url, options = {}) {
  const resp = await fetch(url, options);
  const data = await resp.json().catch(() => null);

  if (!resp.ok) {
    throw new Error(data?.error || `Erro HTTP ${resp.status}`);
  }

  return data;
}

async function fetchPaciente(id) {
  if (!id) return null;
  const j = await fetchJSON(`/atendimentos/api/paciente?id=${encodeURIComponent(id)}`);
  return j?.ok && j?.found ? j : null;
}

async function fetchUltimo(id) {
  if (!id) return { ok: true, found: false };
  return fetchJSON(`/atendimentos/api/ultimo_atendimento?id=${encodeURIComponent(id)}`);
}

async function fetchCombo(id) {
  if (!id) return { ok: true, item: null };
  return fetchJSON(`/atendimentos/api/paciente/${encodeURIComponent(id)}/combo`);
}

async function fetchSugestoesProcedimentos(id) {
  if (!id) return { ok: true, items: [] };
  const cid = cidAtendimentoAtual();   // CID pontual deste atendimento (junto com o cadastro e as condicoes ativas, define o que e compativel)
  return fetchJSON(`/atendimentos/api/procedimentos_sugeridos?paciente_id=${encodeURIComponent(id)}${cid ? `&cid=${encodeURIComponent(cid)}` : ""}`);
}

/* ==========================================================
   PACIENTE
========================================================== */

const apenasDigitos = (v) => String(v ?? "").replace(/\D/g, "");

/* CPF 000.000.000-00 e CNS 000 0000 0000 0000; se nao tem o tamanho esperado, mostra como veio ("—" se vazio) */
function fmtCPF(v) {
  const d = apenasDigitos(v);
  return d.length === 11 ? d.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4") : (String(v ?? "").trim() || "—");
}

function fmtCNS(v) {
  const d = apenasDigitos(v);
  return d.length === 15 ? d.replace(/(\d{3})(\d{4})(\d{4})(\d{4})/, "$1 $2 $3 $4") : (String(v ?? "").trim() || "—");
}

function preencherPaciente(dados) {
  if (!dados) return;

  setText("info-cpf", fmtCPF(dados.cpf));
  setText("info-cns", fmtCNS(dados.cns));

  setText("info-nome", dados.nome || "—");
  setText("info-prontuario", dados.prontuario || "—");
  setText("info-mod", dados.mod || "—");
  setText("info-nascimento", fmtISOToBR(dados.nascimento));
  setText("info-idade", calcIdade(dados.nascimento));
  setText("info-cid", dados.cid || "—");
}

function preencherUltimo(info) {
  const btn = qs("#btnVerUltimo");

  if (info?.ok && info?.found) {
    setText("ua-data", fmtISOToBR(info.data));
    setText("ua-profissional", info.profissional || "—");

    if (btn) {
      btn.dataset.id = info.id || "";
      btn.disabled = false;
      btn.title = "Abrir o último atendimento deste paciente";
    }
  } else {
    setText("ua-data", "—");
    setText("ua-profissional", "—");

    if (btn) {
      btn.dataset.id = "";
      btn.disabled = true;
      btn.title = "Este paciente ainda não tem atendimento anterior";
    }
  }
}

async function carregarPacienteCompleto(id) {
  if (!id) {
    resetCombo();
    preencherUltimo({ ok: true, found: false });
    return;
  }

  // Tudo em PARALELO e cada pedido trata o proprio resultado ao chegar. Antes eram 5 chamadas em serie e a caixa
  // "Ultimos procedimentos" so aparecia depois da mais lenta (a lista de sugestoes, que carrega o catalogo inteiro).
  // Agora ela aparece assim que o "ultimo atendimento" chega; um pedido que falha nao derruba os outros.
  ultimoAtendimentoCache = null;

  const tarefas = [
    fetchPaciente(id).then((paciente) => { if (paciente) preencherPaciente(paciente); }),
    fetchUltimo(id).then((ultimo) => {
      ultimoAtendimentoCache = ultimo;
      preencherUltimo(ultimo);
      renderHistoricoProcedimentos(ultimo);
    }),
    fetchCombo(id).then((combo) => preencherCombo(combo)),
    carregarCidsAtivos(id),
    carregarSugestoesProcedimentos(false),
  ];

  const resultados = await Promise.allSettled(tarefas);
  resultados.forEach((r) => { if (r.status === "rejected") console.error(r.reason); });

  document.dispatchEvent(new CustomEvent("paciente:selecionado", {
    detail: { pacienteId: id }
  }));
}

function initPacienteFromURL() {
  const pid = getParam("paciente_id");
  const nome = getParam("paciente_nome");

  if (pid) setValue("nomePaciente", pid);
  if (nome) setText("info-nome", nome);

  carregarPacienteCompleto(pid || getPacienteId());

  qs("#btnVerUltimo")?.addEventListener("click", async () => {
    const aid = qs("#btnVerUltimo")?.dataset.id;

    if (!aid) {
      toast("Nenhum atendimento anterior encontrado para este paciente.");
      return;
    }

    try {
      const j = await fetchJSON(`/atendimentos/${aid}.json`);

      // a modal "Ultimo atendimento" ja vem incluida na pagina (ultima_consulta.html)
      if (window.UCModal) {
        window.UCModal.fill(j);
        window.UCModal.open();
      } else {
        toast(`Último atendimento: ${fmtISOToBR(j.data_atendimento)} · ${j.profissional_nome || "—"}`);
      }
    } catch (e) {
      toast(e.message || "Erro ao abrir o atendimento.", "error");
    }
  });
}

/* ==========================================================
   COMBO
========================================================== */

function initComboCollapse() {
  const btn = qs("#btnToggleComboPanel");
  const body = qs("#comboPanelBody");
  const status = qs("#comboCollapseStatus");

  if (!btn || !body) return;

  function setExpanded(expanded) {
    btn.setAttribute("aria-expanded", expanded ? "true" : "false");
    body.hidden = !expanded;
    body.classList.toggle("is-collapsed", !expanded);
    body.classList.toggle("is-expanded", expanded);

    const custom = btn.dataset.statusText || "";
    if (status) status.textContent = expanded ? "Aberto" : (custom || "Recolhido");
  }

  setExpanded(false);

  btn.addEventListener("click", () => {
    setExpanded(btn.getAttribute("aria-expanded") !== "true");
  });

  window.atdComboCollapse = {
    open: () => setExpanded(true),
    close: () => setExpanded(false),
    status: (txt) => {
      btn.dataset.statusText = txt || "Recolhido";
      if (btn.getAttribute("aria-expanded") !== "true" && status) {
        status.textContent = btn.dataset.statusText;
      }
    },
  };
}

function resetCombo() {
  qs("#comboCard")?.setAttribute("hidden", "");
  qs("#comboEmptyCard")?.removeAttribute("hidden");

  setValue("combo_plano_id", "");
  setValue("combo_plano_nome", "");

  setText("comboNome", "—");
  setText("comboContratadas", "0");
  setText("comboUsadas", "0");
  setText("comboRestantes", "0");

  const toggle = qs("#toggleUsarCombo");
  if (toggle) {
    toggle.checked = false;
    toggle.disabled = true;
  }

  window.atdComboCollapse?.status("Sem combo/plano ativo");
  window.atdComboCollapse?.close();
}

function atualizarTextoCombo() {
  const help = qs("#comboHelpText");
  const toggle = qs("#toggleUsarCombo");
  const restantes = Number(qs("#comboRestantes")?.textContent || 0);

  if (!help) return;

  if (!toggle || toggle.disabled) {
    help.textContent = "Sem combo/plano ativo vinculado para consumo automático de sessão.";
  } else if (restantes <= 0) {
    help.textContent = "Este combo/plano não possui sessões restantes.";
  } else if (toggle.checked) {
    help.textContent = "Ao salvar, 1 sessão será consumida deste combo/plano.";
  } else {
    help.textContent = "Este atendimento será salvo sem consumir sessão do combo/plano.";
  }
}

function preencherCombo(resp) {
  const item = resp?.item;

  if (!item?.id) {
    resetCombo();
    return;
  }

  qs("#comboCard")?.removeAttribute("hidden");
  qs("#comboEmptyCard")?.setAttribute("hidden", "");

  const nome = item.combo_nome || item.nome_plano || "Combo/Plano";
  const restantes = Number(item.sessoes_restantes || 0);

  setText("comboNome", nome);
  setText("comboTipoBadge", item.tipo === "plano" ? "Plano" : "Combo");
  setText("comboStatusBadge", item.status || "Ativo");
  setText("comboContratadas", String(item.sessoes_contratadas || 0));
  setText("comboUsadas", String(item.sessoes_usadas || 0));
  setText("comboRestantes", String(restantes));

  setValue("combo_plano_id", item.id);
  setValue("combo_plano_nome", nome);

  const toggle = qs("#toggleUsarCombo");
  if (toggle) {
    toggle.disabled = restantes <= 0;
    toggle.checked = restantes > 0;
  }

  window.atdComboCollapse?.status(`${restantes} sessão(ões) restantes`);
  window.atdComboCollapse?.close();
  atualizarTextoCombo();
}

function initComboToggle() {
  qs("#toggleUsarCombo")?.addEventListener("change", atualizarTextoCombo);
}

/* ==========================================================
   PROCEDIMENTOS + SUGESTÕES INLINE
========================================================== */

function isProcRowEmpty(row) {
  const proc = qs('input[name="procedimento[]"]', row)?.value || "";
  const cod = qs('input[name="codigoProcedimento[]"]', row)?.value || "";
  return !proc.trim() && !cod.trim();
}

function setProcRow(row, proc = {}) {
  if (!row) return;

  const inp = qs('input[name="procedimento[]"]', row);
  const cod = qs('input[name="codigoProcedimento[]"]', row);
  const qtd = qs('input[name="quantidadeProcedimento[]"]', row);

  if (inp) inp.value = proc.procedimento || proc.descricao || "";
  if (cod) cod.value = proc.codigo_sigtap || proc.codigo || "";
  if (qtd) qtd.value = proc.quantidade || 1;

  esconderSugestoesInline(row);
}

function criarLinhaProcedimento(proc = {}) {
  const row = document.createElement("div");
  row.className = "proc-row atd-proc-row";

  const n = ++procSeq;

  row.innerHTML = `
    <div class="proc-col proc-col--desc">
      <label class="sr-only" for="procInput${n}">Procedimento</label>

      <div class="proc-input-inline">
        <input type="text"
               id="procInput${n}"
               name="procedimento[]"
               class="input proc-input"
               placeholder="Digite o código ou nome do procedimento"
               autocomplete="off"
               value="${escapeHTML(proc.procedimento || proc.descricao || "")}">
      </div>

      <div class="proc-inline-suggestions" hidden></div>
    </div>

    <input type="hidden"
           name="codigoProcedimento[]"
           class="proc-codigo"
           value="${escapeHTML(proc.codigo_sigtap || proc.codigo || "")}">

    <div class="proc-col proc-col--qtd">
      <label class="sr-only" for="procQtd${n}">Quantidade</label>
      <input type="number"
             id="procQtd${n}"
             name="quantidadeProcedimento[]"
             class="input proc-qtd"
             min="1"
             value="${escapeHTML(proc.quantidade || 1)}">
    </div>

    <div class="proc-col proc-col--actions">
      <button type="button" class="atd-btn atd-btn--danger-quiet atd-btn--sm btnRemoveProc">
        Remover
      </button>
    </div>
  `;

  return row;
}

/* Padrao por CBO (vem do servidor em /api/procedimentos_sugeridos, campo `padrao`; null = nada a pre-preencher).
   Aplica UMA vez, so se a primeira linha ainda estiver vazia. Nunca e reaplicado ao salvar: assim, quem apaga o
   procedimento recebe o aviso "Nenhum procedimento selecionado" em vez de o campo ser preenchido de novo. */
function aplicarProcedimentoPadrao() {
  const wrap = qs("#procedimentosWrap");
  if (!wrap || !procPadrao || wrap.dataset.padraoAplicado === "1") return;

  const rows = qsa(".proc-row", wrap);

  if (rows.length === 1 && isProcRowEmpty(rows[0])) {
    setProcRow(rows[0], procPadrao);
    wrap.dataset.padraoAplicado = "1";
  }
}

function limparProcedimentos() {
  const wrap = qs("#procedimentosWrap");
  if (!wrap) return;

  wrap.innerHTML = "";
  wrap.appendChild(criarLinhaProcedimento({}));
}

function adicionarProcedimento(proc = {}) {
  const wrap = qs("#procedimentosWrap");
  if (!wrap) return;

  const rows = qsa(".proc-row", wrap);

  if (rows.length === 1 && isProcRowEmpty(rows[0])) {
    setProcRow(rows[0], proc);
    return;
  }

  wrap.appendChild(criarLinhaProcedimento(proc));
}

function filtrarSugestoes(term) {
  const t = normalize(term);
  if (!t) return [];

  return sugestoesCache
    .filter((p) =>
      normalize(p.codigo).includes(t) ||
      normalize(p.descricao).includes(t)
    )
    .slice(0, 8);
}

function mostrarSugestoesInline(row, items) {
  const box = qs(".proc-inline-suggestions", row);
  if (!box) return;

  if (!items.length) {
    box.hidden = true;
    box.innerHTML = "";
    return;
  }

  box.innerHTML = items.map((p) => `
    <button type="button"
            class="proc-inline-item"
            data-codigo="${escapeHTML(p.codigo)}"
            data-descricao="${escapeHTML(p.descricao)}">
      <strong>${escapeHTML(p.codigo || "—")}</strong>
      <span>${escapeHTML(p.descricao || "")}</span>
    </button>
  `).join("");

  box.hidden = false;
}

function esconderSugestoesInline(row) {
  const box = qs(".proc-inline-suggestions", row);
  if (!box) return;
  box.hidden = true;
  box.innerHTML = "";
}

async function carregarSugestoesProcedimentos(showAlert = true) {
  const pacienteId = getPacienteId();

  if (!pacienteId) {
    if (showAlert) toast("Paciente não identificado.", "error");
    return [];
  }

  const j = await fetchSugestoesProcedimentos(pacienteId);
  sugestoesCache = j?.items || [];
  procPadrao = j?.padrao || null;
  aplicarProcedimentoPadrao();

  const cids = (j?.paciente_cids || []).join(", ") || "—";
  const resumo = qs("#sugestoesProcResumo");

  if (resumo) {
    resumo.textContent = `CBO: ${j?.cbo || "—"} · CID(s): ${cids} · ${sugestoesCache.length} procedimento(s)`;
  }

  renderSugestoesModal(sugestoesCache);
  return sugestoesCache;
}

function initProcedimentos() {
  const wrap = qs("#procedimentosWrap");
  const btnAdd = qs("#btnAddProcedimento");

  if (!wrap) return;

  btnAdd?.addEventListener("click", () => adicionarProcedimento({}));

  wrap.addEventListener("input", debounce(async (e) => {
    const input = e.target.closest('input[name="procedimento[]"]');
    if (!input) return;

    const row = input.closest(".proc-row");
    const cod = qs('input[name="codigoProcedimento[]"]', row);

    if (cod) cod.value = "";

    if (!sugestoesCache.length) {
      await carregarSugestoesProcedimentos(false);
    }

    mostrarSugestoesInline(row, filtrarSugestoes(input.value));
  }, 160));

  wrap.addEventListener("focusin", async (e) => {
    const input = e.target.closest('input[name="procedimento[]"]');
    if (!input) return;

    if (!sugestoesCache.length) {
      await carregarSugestoesProcedimentos(false);
    }

    const row = input.closest(".proc-row");
    mostrarSugestoesInline(row, filtrarSugestoes(input.value));
  });

  wrap.addEventListener("click", (e) => {
    const sug = e.target.closest(".proc-inline-item");
    if (sug) {
      const row = sug.closest(".proc-row");
      setProcRow(row, {
        codigo: sug.dataset.codigo || "",
        descricao: sug.dataset.descricao || "",
        quantidade: 1,
      });
      return;
    }

    const btn = e.target.closest(".btnRemoveProc");
    if (!btn) return;

    const row = btn.closest(".proc-row");
    row?.remove();

    if (!qsa(".proc-row", wrap).length) {
      wrap.appendChild(criarLinhaProcedimento({}));
    }
  });

  document.addEventListener("click", (e) => {
    if (e.target.closest(".proc-row")) return;
    qsa(".proc-row", wrap).forEach(esconderSugestoesInline);
  });
}

/* ==========================================================
   MODAL SUGESTÕES
========================================================== */

function renderSugestoesModal(items) {
  const lista = qs("#listaSugestoesProc");
  const termo = normalize(qs("#buscaSugestaoProc")?.value || "");

  if (!lista) return;

  const filtrados = (items || []).filter((p) => {
    if (!termo) return true;
    return normalize(p.codigo).includes(termo) || normalize(p.descricao).includes(termo);
  });

  if (!filtrados.length) {
    lista.innerHTML = `<p class="atd-empty">Nenhum procedimento encontrado.</p>`;
    return;
  }

  lista.innerHTML = filtrados.map((p) => `
    <label class="atd-sugestao-proc">
      <input type="checkbox"
             data-codigo="${escapeHTML(p.codigo)}"
             data-descricao="${escapeHTML(p.descricao)}">
      <span>
        <strong>${escapeHTML(p.descricao)}</strong>
        <small>${escapeHTML(p.codigo)} · Competência ${escapeHTML(p.competencia || "—")}</small>
      </span>
    </label>
  `).join("");
}

function initModalSugestoes() {
  const modal = qs("#modalSugestoesProc");

  qs("#btnAbrirSugestoesProc")?.addEventListener("click", async () => {
    if (!modal) return;

    if (typeof modal.showModal === "function") modal.showModal();
    else modal.setAttribute("open", "");

    await carregarSugestoesProcedimentos();
  });

  qs("#btnFecharSugestoesProc")?.addEventListener("click", () => {
    if (typeof modal?.close === "function") modal.close();
    else modal?.removeAttribute("open");
  });

  qs("#buscaSugestaoProc")?.addEventListener("input", () => {
    renderSugestoesModal(sugestoesCache);
  });

  qs("#btnAdicionarSelecionadosProc")?.addEventListener("click", () => {
    const marcados = qsa("#listaSugestoesProc input:checked");

    if (!marcados.length) {
      toast("Marque pelo menos um procedimento.", "error");
      return;
    }

    marcados.forEach((ck) => {
      adicionarProcedimento({
        codigo: ck.dataset.codigo || "",
        descricao: ck.dataset.descricao || "",
        quantidade: 1,
      });
    });

    if (typeof modal?.close === "function") modal.close();
    else modal?.removeAttribute("open");
  });
}

/* ==========================================================
   HISTÓRICO
========================================================== */

function renderHistoricoProcedimentos(info) {
  const box = qs("#historicoProcedimentosBox");
  const lista = qs("#historicoProcedimentosLista");
  const hint = qs("#historicoProcedimentosHint");

  if (!box || !lista) return;

  const procs = info?.procedimentos || [];

  if (!procs.length) {
    box.hidden = true;
    lista.innerHTML = "";
    return;
  }

  box.hidden = false;
  if (hint) hint.textContent = `${procs.length} procedimento(s) encontrado(s) no último atendimento`;

  lista.innerHTML = procs.map((p) => `
    <button type="button"
            class="atd-chip atd-chip-proc"
            data-codigo="${escapeHTML(p.codigo_sigtap || "")}"
            data-procedimento="${escapeHTML(p.procedimento || "")}">
      ${escapeHTML(p.codigo_sigtap || "")} · ${escapeHTML(p.procedimento || "")}
    </button>
  `).join("");
}

function initHistoricoProcedimentos() {
  // (a caixa ja foi desenhada por carregarPacienteCompleto assim que o "ultimo atendimento" chegou; aqui so cobre o
  //  caso de o evento vir de outro ponto sem o cache preenchido)
  document.addEventListener("paciente:selecionado", async (ev) => {
    const pacienteId = ev.detail?.pacienteId;
    if (!pacienteId || ultimoAtendimentoCache) return;

    try {
      ultimoAtendimentoCache = await fetchUltimo(pacienteId);
      renderHistoricoProcedimentos(ultimoAtendimentoCache);
    } catch (e) {
      console.warn(e);
    }
  });

  qs("#historicoProcedimentosLista")?.addEventListener("click", (e) => {
    const btn = e.target.closest(".atd-chip-proc");
    if (!btn) return;

    adicionarProcedimento({
      codigo: btn.dataset.codigo || "",
      descricao: btn.dataset.procedimento || "",
      quantidade: 1,
    });
  });

  qs("#btnUsarUltimosProcs")?.addEventListener("click", async () => {
    const pacienteId = getPacienteId();

    if (!pacienteId) {
      toast("Paciente não identificado.", "error");
      return;
    }

    if (!ultimoAtendimentoCache) {
      ultimoAtendimentoCache = await fetchUltimo(pacienteId);
    }

    const procs = ultimoAtendimentoCache?.procedimentos || [];

    if (!procs.length) {
      toast("Nenhum procedimento anterior encontrado para este paciente.");
      return;
    }

    limparProcedimentos();

    procs.forEach((p, idx) => {
      const item = {
        descricao: p.procedimento || "",
        codigo: p.codigo_sigtap || "",
        quantidade: 1,
      };

      if (idx === 0) setProcRow(qs(".proc-row"), item);
      else adicionarProcedimento(item);
    });
  });
}

/* ==========================================================
   VOZ
========================================================== */

function initVozEvolucao() {
  const btn = qs("#btnFalarEvolucao");
  const textarea = qs("#evolucao");
  const status = qs("#voiceStatus");

  if (!btn || !textarea) return;

  if (status) {
    status.hidden = true;
  }

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!SpeechRecognition) {
    btn.disabled = true;
    rotuloVoz(btn, "indisponivel");
    return;
  }

  const rec = new SpeechRecognition();
  rec.lang = "pt-BR";
  rec.continuous = true;
  rec.interimResults = true;

  let listening = false;
  let baseText = "";
  let finalTranscript = "";

  function setListening(on) {
    listening = on;
    btn.setAttribute("aria-pressed", on ? "true" : "false");
    btn.classList.toggle("is-listening", on);
    rotuloVoz(btn, on ? "ouvindo" : "falar");

    if (status) {
      status.hidden = !on;
    }
  }

  rec.onstart = () => setListening(true);
  rec.onend = () => setListening(false);

  rec.onerror = (event) => {
    console.warn("Erro no reconhecimento de voz:", event.error);
    setListening(false);
  };

  rec.onresult = (event) => {
    let interimTranscript = "";

    for (let i = event.resultIndex; i < event.results.length; i++) {
      const transcript = event.results[i][0].transcript.trim();

      if (event.results[i].isFinal) {
        finalTranscript += `${transcript} `;
      } else {
        interimTranscript += ` ${transcript}`;
      }
    }

    textarea.value = [
      baseText.trim(),
      finalTranscript.trim(),
      interimTranscript.trim(),
    ].filter(Boolean).join(" ").replace(/\s+/g, " ").trim();
  };

  btn.addEventListener("click", () => {
    if (listening) {
      rec.stop();
      return;
    }

    baseText = textarea.value || "";
    finalTranscript = "";

    try {
      rec.start();
    } catch (e) {
      console.warn("Reconhecimento já iniciado ou indisponível:", e);
    }
  });
}

/* ==========================================================
   EVOLUÇÃO OCULTA
========================================================== */

function initEvolucaoOculta() {
  const btn = qs("#btnToggleEvolucaoOculta");
  const body = qs("#evolucaoOcultaBody");
  const boxCbos = qs("#boxCbosAutorizados");

  if (btn && body) {
    function setOpen(open) {
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      body.hidden = !open;
      body.classList.toggle("is-collapsed", !open);
      body.classList.toggle("is-expanded", open);
    }

    setOpen(false);

    btn.addEventListener("click", () => {
      setOpen(btn.getAttribute("aria-expanded") !== "true");
    });
  }

  qsa('input[name="evolucao_oculta_visibilidade"]').forEach((radio) => {
    radio.addEventListener("change", () => {
      const selected = qs('input[name="evolucao_oculta_visibilidade"]:checked')?.value;
      if (boxCbos) boxCbos.hidden = selected !== "cbos";
    });
  });
}

/* ==========================================================
   SALVAR
========================================================== */

function hasProcedimento() {
  return qsa('input[name="procedimento[]"]').some((el) => (el.value || "").trim());
}

/* Retorno do "marcar como condicao ativa": o servidor responde cid_ativo = "criado" | "ja_ativo" | null */
function mensagemCidAtivo(data, cid) {
  if (!cid || !data?.cid_ativo) return "";
  return data.cid_ativo === "criado"
    ? `CID ${cid} marcado como condição ativa deste paciente.`
    : `CID ${cid} já era uma condição ativa deste paciente.`;
}

/* "Salvar e emitir documentos": o atendimento ja esta gravado; abre o painel de documentos NESTA tela (mesmas rotas da
   pagina de documentos) e trava o formulario para nao gravar o atendimento duas vezes. Devolve false se o painel nao existe. */
function abrirPainelDocumentos(form, data, avisoCid) {
  const painel = qs("#atdDocsPainel");
  if (!painel || !window.SGDDocumentos) return false;

  form.dataset.salvo = "1";
  form.inert = true;                                   // nada mais clicavel/focavel no formulario salvo
  qs(".atd-form-card")?.classList.add("is-salvo");     // esconde a barra de salvar e deixa o formulario so para consulta
  qsa('[type="submit"]', form).forEach((b) => { b.disabled = true; });

  setText("atdDocsSub", `Atendimento nº ${data.atendimento_id} salvo. Emita os documentos abaixo; ficam vinculados a ele.`);
  painel.hidden = false;
  window.SGDDocumentos.ativar({ atendimentoId: data.atendimento_id, dataAtendimento: qs('input[name="dataAtendimento"]')?.value || "" });

  toast(avisoCid ? `Atendimento salvo. ${avisoCid}` : "Atendimento salvo. Emita os documentos abaixo.", "ok");
  painel.scrollIntoView({ behavior: "smooth", block: "start" });
  qs(".doc-tipo", painel)?.focus({ preventScroll: true });
  return true;
}

function initSalvar() {
  const form = qs("#form-atendimento");
  if (!form || form.dataset.bound === "1") return;

  form.dataset.bound = "1";

  const btnEmitir = qs("#btnSalvarEmitirDocs");
  if (btnEmitir) {
    btnEmitir.addEventListener("click", () => {
      form.dataset.emitirDocs = "1";
      form.requestSubmit(qs("#btnSalvarAtendimento", form));
    });
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    // "Salvar e emitir documentos": mesmo salvamento; so muda o destino depois de salvar.
    // O botao NAO e de envio (type=button): assim o Enter num campo continua acionando o "Salvar atendimento".
    const emitirDocs = form.dataset.emitirDocs === "1";
    delete form.dataset.emitirDocs;

    const pacienteId = getPacienteId();

    if (!pacienteId) {
      toast("Paciente não informado. Volte pela fila ou selecione um paciente.", "error");
      return;
    }

    setValue("nomePaciente", pacienteId);

    if (!cidAtendimentoPronto()) return;

    if (form.dataset.salvo === "1") return;   // ja salvo: o painel de documentos esta aberto; nao grava de novo
    const cidSalvo = cidAtendimentoAtual();

    const btns = qsa('[type="submit"]', form);
    const btn = { set disabled(v) { btns.forEach((b) => { b.disabled = v; }); }, get disabled() { return btns.some((b) => b.disabled); } };
    btn.disabled = true;

    try {
      // (o procedimento padrao NAO e mais reaplicado aqui: se a pessoa apagou, vale o aviso logo abaixo)
      const fd = new FormData(form);

      fd.set("nomePaciente", pacienteId);
      fd.set("fila_id", getFilaId());

      const comboId = qs("#combo_plano_id")?.value || "";
      const toggle = qs("#toggleUsarCombo");

      fd.set("combo_plano_id", comboId);
      fd.set(
        "contabiliza_sessao",
        comboId && toggle?.checked && !toggle?.disabled ? "1" : "0"
      );

      if (!hasProcedimento()) {
        const ok = await perguntar(
          "Nenhum procedimento foi selecionado. Deseja salvar mesmo assim?",
          { titulo: "Salvar sem procedimento?", sim: "Salvar sem procedimento", nao: "Voltar e escolher" }
        );

        if (!ok) {
          btn.disabled = false;
          qs('input[name="procedimento[]"]')?.focus();
          return;
        }

        fd.set("enviar_sem_procedimento", "1");
      } else {
        fd.set("enviar_sem_procedimento", "0");
      }

      const enviar = () => fetch(form.action, {
        method: "POST",
        body: fd,
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });

      let resp = await enviar();
      let data = await resp.json().catch(() => null);

      // o servidor tambem pede confirmacao quando nao ha procedimento (rede de seguranca): pergunta e reenvia
      if (resp.status === 409 && data?.requires_confirmation) {
        const ok = await perguntar(data.error || "Nenhum procedimento foi selecionado. Deseja salvar mesmo assim?",
          { titulo: "Salvar sem procedimento?", sim: "Salvar sem procedimento", nao: "Voltar e escolher" });

        if (!ok) {
          btn.disabled = false;
          return;
        }

        fd.set("enviar_sem_procedimento", "1");
        resp = await enviar();
        data = await resp.json().catch(() => null);
      }

      if (!resp.ok || !data?.ok) {
        throw new Error(data?.error || "Falha ao salvar atendimento.");
      }

      const avisoCid = mensagemCidAtivo(data, cidSalvo);

      if (emitirDocs && data.atendimento_id) {
        if (abrirPainelDocumentos(form, data, avisoCid)) return;   // fica na MESMA tela
        window.location.href = `/atendimentos/${encodeURIComponent(data.atendimento_id)}/documentos`;   // so se o painel nao existir
        return;
      }

      // vai para a lista: guarda o aviso para ela mostrar (a pagina muda, um toast aqui sumiria)
      if (avisoCid) { try { sessionStorage.setItem("sgd_toast", JSON.stringify({ texto: avisoCid, tipo: "ok" })); } catch (_) { /* sem sessionStorage: segue sem o aviso */ } }
      window.location.href = data.redirect || "/atendimentos/";
    } catch (err) {
      console.error(err);
      toast(err.message || "Erro ao salvar atendimento.", "error");

      btn.disabled = false;
    }
  });
}

// ====== EXTRA FINAL ======

// CANCELAR
/* ==========================================================
   CID DO ATENDIMENTO (opcional)
   A busca usa o MESMO endpoint dos documentos: GET /api/cid10/buscar.
   O servidor e quem valida de verdade (formato e catalogo); aqui so ajudamos a escolher.
========================================================== */

const RE_CID_ATENDIMENTO = /^[A-Za-z]\d{2}(\.?[0-9A-Za-z]{1,4})?$/;

function initCidAtendimento() {
  const busca = qs("#cidAtendimentoBusca");
  const oculto = qs("#cidAtendimento");
  const caixa = qs("#cidAtendimentoSug");
  const msg = qs("#cidAtendimentoMsg");
  if (!busca || !oculto || !caixa) return;

  const url = busca.dataset.urlCid;
  let timer = null;
  let vezBusca = 0;   // identifica a busca mais recente; blur/edicao invalidam as anteriores

  const mostrarMsg = (texto, erro = false) => {
    msg.textContent = texto || "";
    msg.classList.toggle("is-erro", !!erro);
  };

  const escolher = (item) => {
    oculto.value = item.codigo;
    busca.value = `${item.codigo} — ${item.descricao}`;
    caixa.hidden = true;
    mostrarMsg("");
    aoMudarCidAtendimento();
  };

  busca.addEventListener("input", () => {
    oculto.value = "";               // editou o texto: a escolha anterior deixa de valer
    mostrarMsg("");
    aoMudarCidAtendimento();
    clearTimeout(timer);
    const q = busca.value.trim();
    if (q.length < 2) { caixa.hidden = true; atualizarCidAtivoBox(); return; }

    const minhaVez = ++vezBusca;
    timer = setTimeout(async () => {
      try {
        const resp = await fetch(`${url}?q=${encodeURIComponent(q)}`, { credentials: "same-origin" });
        const data = await resp.json();
        // resposta velha/fora de foco: se a pessoa ja digitou outra coisa ou saiu do campo, nao reabre a lista
        if (minhaVez !== vezBusca || document.activeElement !== busca) return;
        const itens = Array.isArray(data.items) ? data.items : [];

        caixa.innerHTML = itens.length
          ? itens.map((it, i) => `<button type="button" data-i="${i}">${escapeHtmlCid(it.label)}</button>`).join("")
          : `<small>Nenhum CID encontrado (a base pode não estar importada). O CID é opcional: se souber o código, digite-o.</small>`;
        caixa.hidden = false;
        atualizarCidAtivoBox();
        qsa("button", caixa).forEach((b) => b.addEventListener("click", () => escolher(itens[Number(b.dataset.i)])));
      } catch (e) {
        caixa.hidden = true;
        atualizarCidAtivoBox();
      }
    }, 250);
  });

  busca.addEventListener("blur", () => {
    vezBusca++; clearTimeout(timer);   // saiu do campo: nenhuma busca pendente pode reabrir a lista
    setTimeout(() => { caixa.hidden = true; atualizarCidAtivoBox(); }, 180);   // atraso: da tempo de clicar numa sugestao
  });
}

/* ==========================================================
   CID ATIVO/CRONICO DO PACIENTE
   O campo CID acima e PONTUAL (so deste atendimento). Aqui: ver as condicoes ativas do paciente, marcar o CID digitado como
   ativo (gravado junto com o atendimento) ou, se ele ja e ativo, marcar como resolvido na hora. O servidor decide tudo.
========================================================== */

const cidNorm = (c) => String(c || "").toUpperCase().replace(/[^A-Z0-9]/g, "");

/* CID atual do campo: o escolhido da lista ou um codigo digitado (ex.: F84.0). "" se nao ha. */
function cidAtendimentoAtual() {
  const oculto = qs("#cidAtendimento");
  const busca = qs("#cidAtendimentoBusca");
  if (oculto?.value) return oculto.value;
  const texto = (busca?.value || "").trim();
  return RE_CID_ATENDIMENTO.test(texto) ? texto.toUpperCase() : "";
}

let cidsAtivosFalhou = false;
let podeGerirCids = false;   // atendimentos:editar (o servidor decide e confere de novo em cada POST)

async function carregarCidsAtivos(pacienteId) {
  cidsAtivos = [];
  cidsAtivosFalhou = false;
  podeGerirCids = false;
  try {
    if (pacienteId) {
      const j = await fetchJSON(`/atendimentos/api/pacientes/${encodeURIComponent(pacienteId)}/cids_ativos`);
      cidsAtivos = Array.isArray(j?.items) ? j.items : [];
      podeGerirCids = !!j?.pode_gerir;
    }
  } catch (e) {
    cidsAtivosFalhou = true;
    console.error(e);
  }
  desenharCidsAtivos();
}

function desenharCidsAtivos() {
  // a faixa do paciente e fixa e mostra sempre: sem condicoes ativas aparece "Nenhuma"; se a consulta falhou, "indisponivel" (nunca "Nenhuma")
  setText("info-cids-ativos", cidsAtivosFalhou ? "indisponível" : (cidsAtivos.map((c) => c.cid_codigo).join(" · ") || "Nenhuma"));
  desenharListaCondicoes();
  atualizarCidAtivoBox();
}

/* Lista "Condicoes ativas do paciente": uma linha por condicao, cada uma com o proprio "Resolver" (so quem tem atendimentos:editar) */
function desenharListaCondicoes() {
  const bloco = qs("#blocoCondicoesAtivas");
  const ul = qs("#listaCondicoesAtivas");
  if (!bloco || !ul) return;

  bloco.hidden = !cidsAtivos.length;
  ul.innerHTML = cidsAtivos.map((c) => `
    <li class="atd-condicao" data-id="${escapeHtmlCid(c.id)}">
      <span class="atd-condicao-cid">${escapeHtmlCid(c.cid_codigo)}</span>
      <span class="atd-condicao-desc">${escapeHtmlCid(c.descricao || "")}</span>
      <span class="atd-condicao-desde">desde ${escapeHtmlCid(fmtISOToBR(c.data_inicio))}</span>
      ${podeGerirCids ? `<button type="button" class="atd-btn atd-btn--ghost atd-btn--sm" data-resolver="${escapeHtmlCid(c.id)}" aria-label="Resolver a condição ${escapeHtmlCid(c.cid_codigo)}">Resolver</button>` : ""}
    </li>`).join("");
}

function atualizarCidAtivoBox() {
  setText("info-cid-atendimento", cidAtendimentoAtual() || "—");   // faixa fixa do paciente: CID deste atendimento, ao vivo

  const box = qs("#cidAtivoBox");
  if (!box) return;

  const lblMarcar = qs("#cidAtivoMarcarLbl");
  const chk = qs("#cidMarcarAtivo");
  const ja = qs("#cidAtivoJa");
  const cid = cidAtendimentoAtual();
  // a lista de sugestoes fica POR CIMA: espera fechar. So conta se o campo ainda tem o foco (lista "solta" sem foco nao esconde a caixa)
  const sug = qs("#cidAtendimentoSug");
  const listaAberta = !!sug && !sug.hidden && document.activeElement === qs("#cidAtendimentoBusca");

  if (!cid || !getPacienteId() || listaAberta) {
    box.hidden = true; lblMarcar.hidden = true; ja.hidden = true;
    if (chk) chk.checked = false;
    return;
  }

  const ativa = cidsAtivos.find((c) => cidNorm(c.cid_codigo) === cidNorm(cid));
  box.hidden = false;

  if (ativa) {
    // ja e condicao ativa: nao oferece marcar de novo (sem duplicar); oferece encerrar aqui mesmo
    if (chk) chk.checked = false;
    lblMarcar.hidden = true;
    ja.hidden = false;
    qs("#cidAtivoJaTexto").textContent = `${ativa.cid_codigo} já é uma condição ativa deste paciente (desde ${fmtISOToBR(ativa.data_inicio)}).`;
    qs("#btnCidResolver").dataset.id = ativa.id;
  } else {
    ja.hidden = true;
    lblMarcar.hidden = false;
  }
}

let timerCidMudou = null;
function aoMudarCidAtendimento() {
  atualizarCidAtivoBox();
  // a regra de sugestao de procedimento combina o CID pontual com o cadastro e as condicoes ativas: recarrega a lista
  clearTimeout(timerCidMudou);
  timerCidMudou = setTimeout(() => { if (getPacienteId()) carregarSugestoesProcedimentos(false); }, 350);
}

/* Encerra (resolve) uma condicao ativa do paciente. Mesmo caminho para o botao da caixa do CID digitado e para os "Resolver" da lista. */
async function resolverCondicao(id, botao) {
  const ativa = cidsAtivos.find((c) => String(c.id) === String(id));
  if (!ativa) return;

  const ok = await perguntar(
    `${ativa.cid_codigo} deixa de ser uma condição ativa deste paciente (o histórico fica guardado). Confirmar?`,
    { titulo: "Marcar como resolvido?", sim: "Marcar como resolvido", nao: "Voltar" }
  );
  if (!ok) return;

  if (botao) botao.disabled = true;
  try {
    const resp = await fetch(`/atendimentos/api/cids_ativos/${encodeURIComponent(id)}/resolver`, {
      method: "POST",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    const data = await resp.json().catch(() => null);

    if (resp.status === 403) { toast("Você não tem permissão para encerrar condições do paciente.", "error"); return; }
    if (Array.isArray(data?.items)) cidsAtivos = data.items;
    if (!resp.ok || !data?.ok) { toast(data?.error || "Não foi possível encerrar a condição agora.", "error"); desenharCidsAtivos(); return; }

    toast(`Condição ${ativa.cid_codigo} marcada como resolvida.`, "ok");
    desenharCidsAtivos();
    aoMudarCidAtendimento();
  } catch (e) {
    console.error(e);
    toast("Não foi possível encerrar a condição agora.", "error");
  } finally {
    if (botao) botao.disabled = false;
  }
}

function initCidAtivo() {
  const btn = qs("#btnCidResolver");
  if (btn) btn.addEventListener("click", () => resolverCondicao(btn.dataset.id, btn));

  // lista "Condicoes ativas do paciente": um "Resolver" por condicao (delegado: a lista e redesenhada)
  qs("#listaCondicoesAtivas")?.addEventListener("click", (e) => {
    const b = e.target.closest("[data-resolver]");
    if (b) resolverCondicao(b.dataset.resolver, b);
  });
}

function escapeHtmlCid(v) {
  return String(v ?? "").replace(/[&<>"']/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
}

/* Antes de salvar: devolve true se o campo CID esta ok (vazio, escolhido da lista ou com cara de codigo). */
function cidAtendimentoPronto() {
  const busca = qs("#cidAtendimentoBusca");
  const oculto = qs("#cidAtendimento");
  const msg = qs("#cidAtendimentoMsg");
  if (!busca || !oculto) return true;

  const texto = busca.value.trim();
  if (!texto || oculto.value) return true;

  // digitou um codigo sem clicar na sugestao (ex.: base de CID ainda nao importada): o servidor confere
  if (RE_CID_ATENDIMENTO.test(texto)) {
    oculto.value = texto.toUpperCase();
    return true;
  }

  msg.textContent = "Escolha um CID da lista de sugestões, digite o código (ex.: F84.0) ou deixe o campo vazio.";
  msg.classList.add("is-erro");
  busca.focus();
  return false;
}

function initCancelar() {
  const btn = qs("#btnCancelarAtendimento");
  if (!btn) return;

  btn.addEventListener("click", async () => {
    const ok = await perguntar("O que foi preenchido neste atendimento será descartado.", {
      titulo: "Cancelar o atendimento?", sim: "Descartar e sair", nao: "Continuar editando",
    });

    if (ok) window.location.href = "/atendimentos/";
  });
}

// ==========================================================
// CBO AUTORIZADOS (AUTOCOMPLETE BONITO)
// ==========================================================

function initCboAutocomplete() {
  const input = qs("#cboSearchOculto");
  const boxSug = qs("#cboSugestoesOcultas");
  const listaSel = qs("#cbosSelecionadosOcultos");
  const hidden = qs("#evolucao_oculta_cbos");

  if (!input || !boxSug || !listaSel || !hidden) return;

  let selecionados = [];

  function renderSelecionados() {
    listaSel.innerHTML = selecionados.map(cbo => `
      <div class="atd-cbo-chip" data-codigo="${cbo.codigo}">
        <span>${cbo.codigo} - ${cbo.descricao}</span>
        <button type="button" class="remove-cbo">×</button>
      </div>
    `).join("");

    hidden.value = selecionados.map(c => c.codigo).join(",");
  }

  async function buscarCbos(term) {
    if (!term || term.length < 2) {
      boxSug.hidden = true;
      return;
    }

    try {
      const resp = await fetch(`/atendimentos/api/cbos_sugestoes?q=${encodeURIComponent(term)}`);
      const data = await resp.json();

      if (!data.ok) return;

      const items = data.items || [];

      if (!items.length) {
        boxSug.hidden = true;
        return;
      }

      boxSug.innerHTML = items.map(i => `
        <div class="atd-cbo-item"
             data-codigo="${i.codigo}"
             data-descricao="${i.descricao}">
          <strong>${i.codigo}</strong>
          <span>${i.descricao}</span>
        </div>
      `).join("");

      boxSug.hidden = false;

    } catch (e) {
      console.error("Erro ao buscar CBO:", e);
    }
  }

  input.addEventListener("input", debounce(e => {
    buscarCbos(e.target.value);
  }, 200));

  boxSug.addEventListener("click", e => {
    const item = e.target.closest(".atd-cbo-item");
    if (!item) return;

    const codigo = item.dataset.codigo;
    const descricao = item.dataset.descricao;

    if (selecionados.find(c => c.codigo === codigo)) return;

    selecionados.push({ codigo, descricao });
    renderSelecionados();

    input.value = "";
    boxSug.hidden = true;
  });

  listaSel.addEventListener("click", e => {
    if (!e.target.classList.contains("remove-cbo")) return;

    const chip = e.target.closest(".atd-cbo-chip");
    const codigo = chip.dataset.codigo;

    selecionados = selecionados.filter(c => c.codigo !== codigo);
    renderSelecionados();
  });

  document.addEventListener("click", e => {
    if (!e.target.closest(".atd-cbo-search-wrap")) {
      boxSug.hidden = true;
    }
  });
}

// ==========================================================
// MELHORIA VOZ (ANTI DUPLICAÇÃO)
// ==========================================================

function initVozEvolucaoMelhorado() {
  const btn = qs("#btnFalarEvolucao");
  const textarea = qs("#evolucao");
  const status = qs("#voiceStatus");

  if (!btn || !textarea) return;

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!SpeechRecognition) return;

  const rec = new SpeechRecognition();
  rec.lang = "pt-BR";
  rec.continuous = true;
  rec.interimResults = false; // 🔥 REMOVE DUPLICAÇÃO

  let listening = false;

  function toggle(on) {
    listening = on;
    rotuloVoz(btn, on ? "ouvindo" : "falar");
    btn.classList.toggle("is-listening", on);

    if (status) {
      status.hidden = !on;
    }
  }

  rec.onstart = () => toggle(true);
  rec.onend = () => toggle(false);

  rec.onresult = (e) => {
    let text = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      text += e.results[i][0].transcript + " ";
    }

    textarea.value += " " + text.trim();
  };

  btn.addEventListener("click", () => {
    if (listening) rec.stop();
    else rec.start();
  });
}

// ==========================================================
// INICIALIZAÇÃO FINAL
// ==========================================================

document.addEventListener("DOMContentLoaded", () => {
  initCancelar();
  initCboAutocomplete();
  initVozEvolucaoMelhorado();
});