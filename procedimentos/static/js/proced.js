(() => {
  "use strict";

  const DEBUG = true;

  const log = (...args) => {
    if (DEBUG) console.log("🧪 [proced.js]", ...args);
  };

  const warn = (...args) => {
    if (DEBUG) console.warn("⚠️ [proced.js]", ...args);
  };

  const byId = (id) => document.getElementById(id);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  function safeText(value, fallback = "—") {
    const txt = String(value ?? "").trim();
    return txt && txt !== "undefined" && txt !== "null" && txt !== "None" ? txt : fallback;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function moeda(value) {
    let txt = String(value ?? "0").trim();

    if (!txt || txt === "—") txt = "0";

    txt = txt
      .replace("R$", "")
      .replace(/\s/g, "")
      .replace(/\./g, "")
      .replace(",", ".");

    const n = Number(txt);

    return Number.isFinite(n)
      ? n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })
      : "R$ 0,00";
  }

  function splitItems(value) {
    const raw = safeText(value, "");
    if (!raw || raw === "—") return [];

    return raw
      .split(/[,;\n|]+/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function setText(el, value, fallback = "—") {
    if (!el) return;
    el.textContent = safeText(value, fallback);
  }

  function setHtml(el, html) {
    if (!el) return;
    el.innerHTML = html && String(html).trim()
      ? html
      : `<span class="proced-empty-inline">Sem conteúdo.</span>`;
  }

  function getData(btn, key, fallback = "—") {
    if (!btn || !btn.dataset) return fallback;
    return safeText(btn.dataset[key], fallback);
  }

  function openDialog(dialog) {
    if (!dialog) return;

    try {
      if (typeof dialog.showModal === "function") {
        if (!dialog.open) dialog.showModal();
      } else {
        dialog.setAttribute("open", "open");
      }
    } catch (err) {
      warn("Falha no showModal, usando fallback:", err);
      dialog.setAttribute("open", "open");
    }
  }

  function closeDialog(dialog) {
    if (!dialog) return;

    try {
      if (typeof dialog.close === "function" && dialog.open) {
        dialog.close();
      } else {
        dialog.removeAttribute("open");
      }
    } catch (err) {
      warn("Falha ao fechar modal, usando fallback:", err);
      dialog.removeAttribute("open");
    }
  }

  function bindBackdropClose(dialog) {
    if (!dialog) return;

    dialog.addEventListener("click", (e) => {
      const box = dialog.querySelector(".proced-modal__dialog");
      if (!box) return;

      const rect = box.getBoundingClientRect();

      const inside =
        e.clientX >= rect.left &&
        e.clientX <= rect.right &&
        e.clientY >= rect.top &&
        e.clientY <= rect.bottom;

      if (!inside) closeDialog(dialog);
    });
  }

  function getBadgeClassByComplexidade(text) {
    const value = safeText(text, "").toLowerCase();

    if (value.includes("alta")) return "badge-red";
    if (value.includes("média") || value.includes("media")) return "badge-yellow";
    if (value.includes("baixa")) return "badge-green";

    return "badge-neutral";
  }

  function renderChips(value, chipClass = "") {
    const items = splitItems(value);

    if (!items.length) {
      return `<span class="proced-empty-inline">Nenhum item encontrado.</span>`;
    }

    return items
      .map((item) => `<span class="chip ${chipClass}">${escapeHtml(item)}</span>`)
      .join("");
  }

  function zipCodigoDescricao(codigos, descricoes) {
    const codes = splitItems(codigos);
    const descs = splitItems(descricoes);
    const max = Math.max(codes.length, descs.length);

    const pares = [];

    for (let i = 0; i < max; i++) {
      pares.push({
        codigo: codes[i] || "—",
        descricao: descs[i] || "Descrição não informada",
      });
    }

    return pares;
  }

  function renderPares(codigos, descricoes, chipClass = "") {
    const pares = zipCodigoDescricao(codigos, descricoes);

    if (!pares.length) {
      return `<span class="proced-empty-inline">Nenhum vínculo encontrado.</span>`;
    }

    return pares
      .map((item) => `
        <article class="proced-vinculo-card ${chipClass}">
          <strong>${escapeHtml(item.codigo)}</strong>
          <span>${escapeHtml(item.descricao)}</span>
        </article>
      `)
      .join("");
  }

  function atualizarResumoFiltros() {
    const filtrosAtivos = byId("filtros-ativos");
    if (!filtrosAtivos) return;

    const params = new URLSearchParams(window.location.search);
    const parts = [];

    const q = safeText(params.get("q"), "");
    const cid = safeText(params.get("cid"), "");
    const cbo = safeText(params.get("cbo"), "");
    const complexidade = safeText(params.get("complexidade"), "");

    if (q) parts.push(`Texto: ${q}`);
    if (cid) parts.push(`CID(s): ${cid}`);
    if (cbo) parts.push(`CBO(s): ${cbo}`);
    if (complexidade) parts.push(`Complexidade: ${complexidade}`);

    filtrosAtivos.textContent = parts.length ? parts.join(" • ") : "Nenhum";
  }

  function openModal(title, content) {
    const modal = byId("proced-modal");
    const modalTitle = byId("proced-modal-title");
    const modalBody = byId("proced-modal-body");

    if (!modal || !modalTitle || !modalBody) {
      warn("Modal geral não encontrado.");
      return;
    }

    modalTitle.textContent = safeText(title, "Detalhes");
    modalBody.innerHTML = `<div class="proced-modal-list">${renderChips(content)}</div>`;

    openDialog(modal);
  }

  function bindMoreButtons() {
    const buttons = $$("[data-modal-title][data-modal-content]");
    log("Botões de chips encontrados:", buttons.length);

    buttons.forEach((btn) => {
      btn.addEventListener("click", () => {
        openModal(
          btn.getAttribute("data-modal-title"),
          btn.getAttribute("data-modal-content")
        );
      });
    });
  }

  function preencherCabecalhoDetalhe(payload) {
    setText(byId("proced-detalhe-titulo"), "Procedimento completo");

    const subtitulo = payload.codigo
      ? `Código ${payload.codigo} · ${payload.competencia || "sem competência"}`
      : "Visualização detalhada do procedimento";

    setText(byId("proced-detalhe-subtitulo"), subtitulo);

    setText(byId("det-codigo"), payload.codigo);
    setText(byId("det-nome"), payload.nome);
    setText(byId("det-complexidade"), payload.complexidade);
    setText(byId("det-competencia"), payload.competencia);

    setText(byId("det-co-financiamento"), payload.coFinanciamento);
    setText(byId("det-no-financiamento"), payload.noFinanciamento);
    setText(byId("det-co-rubrica"), payload.coRubrica);
    setText(byId("det-no-rubrica"), payload.noRubrica);
  }

  function preencherValores(payload) {
    setText(byId("det-valor-sh"), moeda(payload.valorSh), "R$ 0,00");
    setText(byId("det-valor-sa"), moeda(payload.valorSa), "R$ 0,00");
    setText(byId("det-valor-sp"), moeda(payload.valorSp), "R$ 0,00");
    setText(byId("det-valor-total"), moeda(payload.valorTotal), "R$ 0,00");
  }

  function preencherBadgesDetalhe(payload) {
    const detBadges = byId("det-badges");
    if (!detBadges) return;

    const badges = [];

    badges.push(`
      <span class="badge badge-total">
        ${escapeHtml(moeda(payload.valorTotal))}
      </span>
    `);

    if (payload.complexidade) {
      badges.push(`
        <span class="badge ${getBadgeClassByComplexidade(payload.complexidade)}">
          ${escapeHtml(payload.complexidade)}
        </span>
      `);
    }

    if (payload.competencia) {
      badges.push(`
        <span class="badge badge-neutral">
          Competência ${escapeHtml(payload.competencia)}
        </span>
      `);
    }

    if (payload.coFinanciamento || payload.noFinanciamento) {
      badges.push(`
        <span class="badge badge-fin">
          ${escapeHtml([payload.coFinanciamento, payload.noFinanciamento].filter(Boolean).join(" · "))}
        </span>
      `);
    }

    detBadges.innerHTML = badges.join("");
  }

  function preencherRelacionamentos(payload) {
    setText(byId("det-qtd-cids"), payload.qtdCids || "0", "0");
    setText(byId("det-qtd-cbos"), payload.qtdCbos || "0", "0");
    setText(byId("det-qtd-servicos"), payload.qtdServicos || "0", "0");

    setHtml(byId("det-cids-codigos"), renderPares(payload.cidsCodigos, payload.cidsDescricoes, "vinculo-cid"));
    setHtml(byId("det-cids-descricoes"), renderChips(payload.cidsDescricoes, "chip-cid"));

    setHtml(byId("det-cbos-codigos"), renderPares(payload.cbosCodigos, payload.cbosDescricoes, "vinculo-cbo"));
    setHtml(byId("det-cbos-descricoes"), renderChips(payload.cbosDescricoes, "chip-cbo"));

    setHtml(byId("det-servicos-codigos"), renderPares(payload.servicosCodigos, payload.servicosDescricoes, "vinculo-serv"));
    setHtml(byId("det-servicos-descricoes"), renderChips(payload.servicosDescricoes, "chip-serv"));

    setHtml(
      byId("det-classificacoes-codigos"),
      renderPares(payload.classificacoesCodigos, payload.classificacoesDescricoes, "vinculo-class")
    );
    setHtml(byId("det-classificacoes-descricoes"), renderChips(payload.classificacoesDescricoes, "chip-class"));
  }

  function preencherDetalhe(btn) {
    const payload = {
      id: getData(btn, "procedId", ""),
      codigo: getData(btn, "procedCodigo", ""),
      nome: getData(btn, "procedNome", ""),
      complexidade: getData(btn, "procedComplexidade", ""),
      competencia: getData(btn, "procedCompetencia", ""),

      valorSh: getData(btn, "procedValorSh", "0"),
      valorSa: getData(btn, "procedValorSa", "0"),
      valorSp: getData(btn, "procedValorSp", "0"),
      valorTotal: getData(btn, "procedValorTotal", "0"),

      coFinanciamento: getData(btn, "procedCoFinanciamento", ""),
      noFinanciamento: getData(btn, "procedNoFinanciamento", ""),

      coRubrica: getData(btn, "procedCoRubrica", ""),
      noRubrica: getData(btn, "procedNoRubrica", ""),

      qtdCids: getData(btn, "procedQtdCids", "0"),
      qtdCbos: getData(btn, "procedQtdCbos", "0"),
      qtdServicos: getData(btn, "procedQtdServicos", "0"),

      cidsCodigos: getData(btn, "procedCidsCodigos", ""),
      cidsDescricoes: getData(btn, "procedCidsDescricoes", ""),

      cbosCodigos: getData(btn, "procedCbosCodigos", ""),
      cbosDescricoes: getData(btn, "procedCbosDescricoes", ""),

      servicosCodigos: getData(btn, "procedServicosCodigos", ""),
      servicosDescricoes: getData(btn, "procedServicosDescricoes", ""),

      classificacoesCodigos: getData(btn, "procedClassificacoesCodigos", ""),
      classificacoesDescricoes: getData(btn, "procedClassificacoesDescricoes", ""),
    };

    log("Payload do procedimento:", payload);

    preencherCabecalhoDetalhe(payload);
    preencherValores(payload);
    preencherBadgesDetalhe(payload);
    preencherRelacionamentos(payload);
  }

  function bindDetalheButtons() {
    const detalheModal = byId("proced-detalhe-modal");
    const buttons = $$(".btn-ver-procedimento");

    log("Cards encontrados:", $$(".proced-item-card").length);
    log("Botões Ver procedimento encontrados:", buttons.length);

    if (!detalheModal) {
      warn("Modal de detalhe não encontrado: #proced-detalhe-modal");
    }

    buttons.forEach((btn) => {
      btn.addEventListener("click", () => {
        preencherDetalhe(btn);
        openDialog(detalheModal);
      });
    });
  }

  function bindFileInput() {
    const inputArquivo = byId("arquivo");
    const fileName = byId("file-name");

    if (!inputArquivo || !fileName) return;

    inputArquivo.addEventListener("change", () => {
      const file = inputArquivo.files && inputArquivo.files[0];
      fileName.textContent = file ? file.name : "Nenhum arquivo selecionado";
    });
  }

  function bindAutoTrimCampos() {
    ["q", "cid", "cbo"].forEach((id) => {
      const el = byId(id);
      if (!el) return;

      el.addEventListener("blur", () => {
        el.value = safeText(el.value, "")
          .replace(/\s*,\s*/g, ", ")
          .replace(/\s{2,}/g, " ");
      });
    });
  }

  function bindModalEvents() {
    const modal = byId("proced-modal");
    const modalClose = byId("proced-modal-close");

    const detalheModal = byId("proced-detalhe-modal");
    const detalheClose = byId("proced-detalhe-close");

    if (modalClose) {
      modalClose.addEventListener("click", () => closeDialog(modal));
    }

    if (detalheClose) {
      detalheClose.addEventListener("click", () => closeDialog(detalheModal));
    }

    bindBackdropClose(modal);
    bindBackdropClose(detalheModal);

    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;

      if (detalheModal && detalheModal.open) {
        closeDialog(detalheModal);
        return;
      }

      if (modal && modal.open) {
        closeDialog(modal);
      }
    });
  }

  function diagnosticoInicial() {
    log("JS carregado.");
    log("URL:", window.location.href);
    log("Grid:", document.querySelector(".proced-cards-grid"));
    log("Cards:", $$(".proced-item-card").length);
    log("Empty:", document.querySelector(".proced-empty"));
    log("Resumo resultados:", document.querySelector(".summary-pill strong")?.textContent?.trim());

    if (!document.querySelector(".proced-cards-grid") && document.querySelector(".proced-empty")) {
      warn("O HTML renderizou estado vazio. Então o problema está no backend/listagem: variável dados veio vazia.");
    }

    if (document.querySelector(".proced-cards-grid") && $$(".proced-item-card").length === 0) {
      warn("Existe grid, mas não existem cards dentro. Verifique o loop Jinja.");
    }
  }

  function init() {
    diagnosticoInicial();
    bindFileInput();
    bindMoreButtons();
    bindDetalheButtons();
    bindModalEvents();
    bindAutoTrimCampos();
    atualizarResumoFiltros();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();