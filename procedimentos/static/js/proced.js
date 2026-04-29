(() => {
  "use strict";

  const byId = (id) => document.getElementById(id);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const inputArquivo = byId("arquivo");
  const fileName = byId("file-name");
  const filtrosAtivos = byId("filtros-ativos");

  const modal = byId("proced-modal");
  const modalTitle = byId("proced-modal-title");
  const modalBody = byId("proced-modal-body");
  const modalClose = byId("proced-modal-close");

  const detalheModal = byId("proced-detalhe-modal");
  const detalheClose = byId("proced-detalhe-close");

  const detTitulo = byId("proced-detalhe-titulo");
  const detSubtitulo = byId("proced-detalhe-subtitulo");

  const detCodigo = byId("det-codigo");
  const detBadges = byId("det-badges");
  const detNome = byId("det-nome");

  const detComplexidade = byId("det-complexidade");
  const detCompetencia = byId("det-competencia");

  const detValorSh = byId("det-valor-sh");
  const detValorSa = byId("det-valor-sa");
  const detValorSp = byId("det-valor-sp");
  const detValorTotal = byId("det-valor-total");

  const detCoFinanciamento = byId("det-co-financiamento");
  const detNoFinanciamento = byId("det-no-financiamento");
  const detCoRubrica = byId("det-co-rubrica");
  const detNoRubrica = byId("det-no-rubrica");

  const detQtdCids = byId("det-qtd-cids");
  const detQtdCbos = byId("det-qtd-cbos");
  const detQtdServicos = byId("det-qtd-servicos");

  const detCidsCodigos = byId("det-cids-codigos");
  const detCidsDescricoes = byId("det-cids-descricoes");

  const detCbosCodigos = byId("det-cbos-codigos");
  const detCbosDescricoes = byId("det-cbos-descricoes");

  const detServicosCodigos = byId("det-servicos-codigos");
  const detServicosDescricoes = byId("det-servicos-descricoes");

  const detClassificacoesCodigos = byId("det-classificacoes-codigos");
  const detClassificacoesDescricoes = byId("det-classificacoes-descricoes");

  function safeText(value, fallback = "—") {
    const txt = String(value ?? "").trim();
    return txt && txt !== "undefined" && txt !== "null" ? txt : fallback;
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

  function renderChips(value, chipClass = "") {
    const items = splitItems(value);

    if (!items.length) {
      return `<span class="proced-empty-inline">Nenhum item encontrado.</span>`;
    }

    return items
      .map((item) => `<span class="chip ${chipClass}">${escapeHtml(item)}</span>`)
      .join("");
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
    } catch (_) {
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
    } catch (_) {
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

  function getQueryParams() {
    const params = new URLSearchParams(window.location.search);

    return {
      q: safeText(params.get("q"), ""),
      cid: safeText(params.get("cid"), ""),
      cbo: safeText(params.get("cbo"), ""),
      complexidade: safeText(params.get("complexidade"), ""),
    };
  }

  function atualizarResumoFiltros() {
    if (!filtrosAtivos) return;

    const params = getQueryParams();
    const parts = [];

    if (params.q) parts.push(`Texto: ${params.q}`);
    if (params.cid) parts.push(`CID(s): ${params.cid}`);
    if (params.cbo) parts.push(`CBO(s): ${params.cbo}`);
    if (params.complexidade) parts.push(`Complexidade: ${params.complexidade}`);

    filtrosAtivos.textContent = parts.length ? parts.join(" • ") : "Nenhum";
  }

  function openModal(title, content) {
    if (!modal || !modalTitle || !modalBody) return;

    modalTitle.textContent = safeText(title, "Detalhes");
    modalBody.innerHTML = `<div class="proced-modal-list">${renderChips(content)}</div>`;

    openDialog(modal);
  }

  function bindMoreButtons() {
    $$("[data-modal-title][data-modal-content]").forEach((btn) => {
      btn.addEventListener("click", () => {
        openModal(
          btn.getAttribute("data-modal-title"),
          btn.getAttribute("data-modal-content")
        );
      });
    });
  }

  function preencherCabecalhoDetalhe(payload) {
    setText(detTitulo, "Procedimento completo");
    setText(
      detSubtitulo,
      payload.codigo !== "—"
        ? `Código ${payload.codigo} · ${payload.competencia}`
        : "Visualização detalhada do procedimento"
    );

    setText(detCodigo, payload.codigo);
    setText(detNome, payload.nome);
    setText(detComplexidade, payload.complexidade);
    setText(detCompetencia, payload.competencia);

    setText(detCoFinanciamento, payload.coFinanciamento);
    setText(detNoFinanciamento, payload.noFinanciamento);
    setText(detCoRubrica, payload.coRubrica);
    setText(detNoRubrica, payload.noRubrica);
  }

  function preencherValores(payload) {
    setText(detValorSh, moeda(payload.valorSh), "R$ 0,00");
    setText(detValorSa, moeda(payload.valorSa), "R$ 0,00");
    setText(detValorSp, moeda(payload.valorSp), "R$ 0,00");
    setText(detValorTotal, moeda(payload.valorTotal), "R$ 0,00");
  }

  function preencherBadgesDetalhe(payload) {
    if (!detBadges) return;

    const badges = [];

    badges.push(`
      <span class="badge badge-total">
        ${escapeHtml(moeda(payload.valorTotal))}
      </span>
    `);

    if (payload.complexidade !== "—") {
      badges.push(`
        <span class="badge ${getBadgeClassByComplexidade(payload.complexidade)}">
          ${escapeHtml(payload.complexidade)}
        </span>
      `);
    }

    if (payload.competencia !== "—") {
      badges.push(`
        <span class="badge badge-neutral">
          Competência ${escapeHtml(payload.competencia)}
        </span>
      `);
    }

    if (payload.coFinanciamento !== "—" || payload.noFinanciamento !== "—") {
      badges.push(`
        <span class="badge badge-fin">
          ${escapeHtml([payload.coFinanciamento, payload.noFinanciamento].filter(v => v !== "—").join(" · "))}
        </span>
      `);
    }

    detBadges.innerHTML = badges.join("");
  }

  function preencherRelacionamentos(payload) {
    setText(detQtdCids, payload.qtdCids, "0");
    setText(detQtdCbos, payload.qtdCbos, "0");
    setText(detQtdServicos, payload.qtdServicos, "0");

    setHtml(detCidsCodigos, renderPares(payload.cidsCodigos, payload.cidsDescricoes, "vinculo-cid"));
    setHtml(detCidsDescricoes, renderChips(payload.cidsDescricoes, "chip-cid"));

    setHtml(detCbosCodigos, renderPares(payload.cbosCodigos, payload.cbosDescricoes, "vinculo-cbo"));
    setHtml(detCbosDescricoes, renderChips(payload.cbosDescricoes, "chip-cbo"));

    setHtml(detServicosCodigos, renderPares(payload.servicosCodigos, payload.servicosDescricoes, "vinculo-serv"));
    setHtml(detServicosDescricoes, renderChips(payload.servicosDescricoes, "chip-serv"));

    setHtml(
      detClassificacoesCodigos,
      renderPares(payload.classificacoesCodigos, payload.classificacoesDescricoes, "vinculo-class")
    );
    setHtml(detClassificacoesDescricoes, renderChips(payload.classificacoesDescricoes, "chip-class"));
  }

  function preencherDetalhe(btn) {
    const payload = {
      codigo: getData(btn, "procedCodigo"),
      nome: getData(btn, "procedNome"),
      complexidade: getData(btn, "procedComplexidade"),
      competencia: getData(btn, "procedCompetencia"),

      valorSh: getData(btn, "procedValorSh", "0"),
      valorSa: getData(btn, "procedValorSa", "0"),
      valorSp: getData(btn, "procedValorSp", "0"),
      valorTotal: getData(btn, "procedValorTotal", "0"),

      coFinanciamento: getData(btn, "procedCoFinanciamento"),
      noFinanciamento: getData(btn, "procedNoFinanciamento"),

      coRubrica: getData(btn, "procedCoRubrica"),
      noRubrica: getData(btn, "procedNoRubrica"),

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

    preencherCabecalhoDetalhe(payload);
    preencherValores(payload);
    preencherBadgesDetalhe(payload);
    preencherRelacionamentos(payload);
  }

  function bindDetalheButtons() {
    $$(".btn-ver-procedimento").forEach((btn) => {
      btn.addEventListener("click", () => {
        preencherDetalhe(btn);
        openDialog(detalheModal);
      });
    });
  }

  function bindFileInput() {
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

  function init() {
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