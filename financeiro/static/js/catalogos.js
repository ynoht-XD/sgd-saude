/* catalogos.js — Planos, Atendimentos avulsos e Avaliações (Comercial).
 *
 * Mesmo molde da seção de Combos (comercial.js): botões "+ Cadastrar" e "Gerenciar",
 * formulário de cadastro, lista de cartões com campos abertos para edição,
 * "Salvar alterações", filtros de busca/status. Diferenças pedidas:
 *   - filtro por profissional;
 *   - ativar/desativar por botão (PATCH .../status); não existe exclusão (a API não tem DELETE).
 *
 * A validação do front só repete as mensagens que a própria API devolve
 * (financeiro/planos_catalogo.py e financeiro/catalogos_atendimento.py), na mesma ordem.
 * A API continua sendo a autoridade: qualquer erro dela aparece do mesmo jeito.
 * CSRF: csrf.js (layout) já injeta o X-CSRFToken em todo fetch não-GET.
 */
(() => {
  "use strict";

  // =========================================================
  // HELPERS (mesmos de comercial.js, que não os exporta)
  // =========================================================
  const escapeHtml = (value) =>
    String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");

  const toast = (msg) => window.alert(msg);

  const debounce = (fn, delay = 250) => {
    let timer = null;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), delay);
    };
  };

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
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    };

    const res = await fetch(url, config);
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

  function togglePanel(panel, button, forceState = null) {
    if (!panel || !button) return;
    const shouldOpen = forceState !== null ? forceState : panel.hidden;
    panel.hidden = !shouldOpen;
    button.setAttribute("aria-expanded", String(shouldOpen));
  }

  // Interpreta como a API (_to_float/_to_int): vazio => padrão; lixo => 0.
  function numero(raw, padrao, inteiro) {
    const s = String(raw ?? "").trim();
    if (s === "") return padrao;
    const n = Number(s.replace(",", "."));
    if (!Number.isFinite(n)) return 0;
    return inteiro ? Math.trunc(n) : n;
  }

  // =========================================================
  // DEFINIÇÃO DOS CATÁLOGOS (campos reais de cada API)
  // =========================================================
  const PERIODOS = [["semana", "Por semana"], ["mes", "Por mês"]];

  const CATALOGOS = {
    planos: {
      base: "/financeiro/api/planos",
      singular: "plano",
      plural: "planos",
      Singular: "Plano",
      cadastrado: "cadastrado",
      ajuda: "Escolha o profissional e informe mensalidade, duração e consultas por período. Para plano familiar, aumente o máximo de beneficiários.",
      titulo: "nome",
      campos: [
        { name: "profissional_id", label: "Profissional", tipo: "prof", span: "lg" },
        { name: "nome", label: "Nome do plano", tipo: "text", span: "lg", placeholder: "Ex: Plano mensal 1x por semana" },
        { name: "valor_mensalidade", label: "Mensalidade (R$)", tipo: "number", span: "md", min: 0, step: "0.01", padrao: 0, placeholder: "0,00" },
        { name: "duracao_meses", label: "Duração (meses)", tipo: "number", span: "md", min: 1, step: "1", padrao: 1, inteiro: true },
        { name: "sessoes_por_periodo", label: "Consultas por período", tipo: "number", span: "md", min: 1, step: "1", padrao: 1, inteiro: true },
        { name: "periodo", label: "Período", tipo: "select", span: "md", opcoes: PERIODOS, padrao: "semana" },
        { name: "max_beneficiarios", label: "Máx. beneficiários", tipo: "number", span: "md", min: 1, step: "1", padrao: 1, inteiro: true, dica: "1 = individual · mais de 1 = plano familiar" },
        { name: "descricao", label: "Observações", tipo: "textarea", span: "full", placeholder: "Observações do plano" },
      ],
      // Mesmas mensagens e mesma ordem de planos_catalogo._ler_payload
      validar(v) {
        if (!v.nome) return "Informe o nome do plano.";
        if (v.valor_mensalidade < 0) return "Valor da mensalidade inválido.";
        if (v.duracao_meses <= 0) return "Informe a duração do plano em meses (maior que zero).";
        if (v.sessoes_por_periodo <= 0) return "Informe quantas consultas por período (maior que zero).";
        if (!["semana", "mes"].includes(v.periodo)) return "Período inválido. Use 'semana' ou 'mes'.";
        if (v.max_beneficiarios <= 0) return "Máximo de beneficiários deve ser pelo menos 1.";
        if (!(v.profissional_id > 0)) return "Informe o profissional do plano (profissional_id).";
        return null;
      },
      badges: (it) => (Number(it.max_beneficiarios) > 1 ? [`<span class="com-badge com-badge--info">Familiar · até ${Number(it.max_beneficiarios)}</span>`] : []),
    },

    avulsos: {
      base: "/financeiro/api/avulsos",
      singular: "atendimento avulso",
      plural: "atendimentos avulsos",
      Singular: "Atendimento avulso",
      cadastrado: "cadastrado",
      ajuda: "Valor padrão de uma sessão avulsa do profissional (fora de combo ou plano). Ele é só a sugestão: o lançamento guarda o valor cobrado.",
      titulo: "descricao",
      campos: [
        { name: "profissional_id", label: "Profissional", tipo: "prof", span: "lg" },
        { name: "descricao", label: "Descrição", tipo: "text", span: "lg", placeholder: "Ex: Sessão avulsa de fisioterapia" },
        { name: "valor_padrao", label: "Valor padrão (R$)", tipo: "number", span: "md", min: 0, step: "0.01", padrao: 0, placeholder: "0,00" },
        { name: "duracao_prevista_min", label: "Duração prevista (min)", tipo: "number", span: "md", min: 1, step: "1", padrao: null, inteiro: true, opcional: true },
      ],
      // Mesmas mensagens e mesma ordem de catalogos_atendimento._ler_payload
      validar(v) {
        if (!v.descricao) return "Informe a descrição (atendimento avulso).";
        if (v.valor_padrao < 0) return "Valor inválido.";
        if (v.duracao_prevista_min !== null && v.duracao_prevista_min <= 0) return "Duração prevista deve ser maior que zero (em minutos).";
        if (!(v.profissional_id > 0)) return "Informe o profissional (profissional_id).";
        return null;
      },
      badges: () => [],
    },

    avaliacoes: {
      base: "/financeiro/api/avaliacoes",
      singular: "avaliação",
      plural: "avaliações",
      Singular: "Avaliação",
      cadastrado: "cadastrada",
      ajuda: "Valor da avaliação do profissional. Ele é só a sugestão: o lançamento guarda o valor cobrado.",
      titulo: "descricao",
      campos: [
        { name: "profissional_id", label: "Profissional", tipo: "prof", span: "lg" },
        { name: "descricao", label: "Descrição", tipo: "text", span: "lg", placeholder: "Ex: Avaliação inicial fonoaudiologia" },
        { name: "valor", label: "Valor (R$)", tipo: "number", span: "md", min: 0, step: "0.01", padrao: 0, placeholder: "0,00" },
        { name: "duracao_prevista_min", label: "Duração prevista (min)", tipo: "number", span: "md", min: 1, step: "1", padrao: null, inteiro: true, opcional: true },
      ],
      validar(v) {
        if (!v.descricao) return "Informe a descrição (avaliação).";
        if (v.valor < 0) return "Valor inválido.";
        if (v.duracao_prevista_min !== null && v.duracao_prevista_min <= 0) return "Duração prevista deve ser maior que zero (em minutos).";
        if (!(v.profissional_id > 0)) return "Informe o profissional (profissional_id).";
        return null;
      },
      badges: () => [],
    },
  };

  // =========================================================
  // PROFISSIONAIS (uma consulta só, compartilhada pelos 3 catálogos)
  // =========================================================
  const estado = { profissionais: [], profissionaisCarregados: false };

  async function carregarProfissionais() {
    const data = await requestJSON("/financeiro/api/profissionais");
    estado.profissionais = Array.isArray(data.items) ? data.items : [];
    estado.profissionaisCarregados = true;
  }

  function nomeProf(p) {
    return p.cbo ? `${p.nome} · CBO ${p.cbo}` : p.nome;
  }

  // <option>s agrupados: profissionais primeiro; id fora da lista (inativo/removido) vira opção própria.
  function opcoesProf({ selecionado = "", vazio = null } = {}) {
    const sel = String(selecionado ?? "");
    const profs = estado.profissionais.filter((p) => p.profissional);
    const outros = estado.profissionais.filter((p) => !p.profissional);
    const opt = (p) => `<option value="${p.id}" ${String(p.id) === sel ? "selected" : ""}>${escapeHtml(nomeProf(p))}</option>`;

    let html = vazio !== null ? `<option value="">${escapeHtml(vazio)}</option>` : "";
    if (profs.length) html += `<optgroup label="Profissionais">${profs.map(opt).join("")}</optgroup>`;
    if (outros.length) html += `<optgroup label="Outros usuários">${outros.map(opt).join("")}</optgroup>`;

    if (sel && !estado.profissionais.some((p) => String(p.id) === sel)) {
      html += `<option value="${escapeHtml(sel)}" selected>Profissional #${escapeHtml(sel)} (inativo ou removido)</option>`;
    }

    return html;
  }

  // =========================================================
  // RENDER DE CAMPOS
  // =========================================================
  function inputHtml(c, valor, extraAttrs = "", classe = "com-input") {
    const v = valor === null || valor === undefined ? "" : valor;

    if (c.tipo === "prof") {
      return `<select class="com-select" data-cat-field="${c.name}" ${extraAttrs}>${opcoesProf({ selecionado: v, vazio: "Selecione..." })}</select>`;
    }

    if (c.tipo === "select") {
      const opts = c.opcoes.map(([val, txt]) => `<option value="${val}" ${String(val) === String(v) ? "selected" : ""}>${escapeHtml(txt)}</option>`).join("");
      return `<select class="com-select" data-cat-field="${c.name}" ${extraAttrs}>${opts}</select>`;
    }

    if (c.tipo === "textarea") {
      return `<textarea class="com-textarea" data-cat-field="${c.name}" rows="3" placeholder="${escapeHtml(c.placeholder || "")}" ${extraAttrs}>${escapeHtml(v)}</textarea>`;
    }

    const attrs = c.tipo === "number" ? `type="number" ${c.min !== undefined ? `min="${c.min}"` : ""} ${c.step ? `step="${c.step}"` : ""}` : `type="text"`;
    return `<input class="${classe}" data-cat-field="${c.name}" ${attrs} value="${escapeHtml(v)}" placeholder="${escapeHtml(c.placeholder || "")}" ${extraAttrs}>`;
  }

  function renderFormulario(root, cfg) {
    const box = root.querySelector('[data-cat-role="campos"]');
    if (!box) return;

    box.innerHTML = cfg.campos.map((c) => `
      <div class="com-field com-field--${c.span}">
        <label class="com-label">${escapeHtml(c.label)}</label>
        ${inputHtml(c, c.padrao ?? "")}
        ${c.dica ? `<small>${escapeHtml(c.dica)}</small>` : ""}
      </div>
    `).join("");

    const ajuda = root.querySelector('[data-cat-role="ajuda-cadastro"]');
    if (ajuda) ajuda.textContent = cfg.ajuda;
  }

  function lerFormulario(root, cfg) {
    const v = {};

    for (const c of cfg.campos) {
      const el = root.querySelector(`[data-cat-role="form"] [data-cat-field="${c.name}"]`);
      const raw = el ? el.value : "";

      if (c.tipo === "number") {
        const n = numero(raw, c.padrao ?? 0, !!c.inteiro);
        v[c.name] = c.opcional && String(raw).trim() === "" ? null : n;
      } else if (c.tipo === "prof") {
        v[c.name] = numero(raw, 0, true);
      } else if (c.tipo === "select") {
        v[c.name] = String(raw || c.padrao || "").trim().toLowerCase();
      } else {
        v[c.name] = String(raw).trim();
      }
    }

    v.ativo = !!root.querySelector('[data-cat-role="form"] [data-cat-field="ativo"]')?.checked;
    return v;
  }

  // =========================================================
  // CARTÕES (gestão)
  // =========================================================
  function cartaoHtml(cfg, it) {
    const tituloCampo = cfg.campos.find((c) => c.name === cfg.titulo);
    const ativo = Number(it.ativo) === 1;
    const demais = cfg.campos.filter((c) => c.name !== cfg.titulo && c.tipo !== "textarea");
    const areas = cfg.campos.filter((c) => c.tipo === "textarea");

    return `
      <article class="combo-card" data-cat-id="${it.id}">
        <div class="combo-top">
          <div class="com-field" style="width:100%;gap:6px;">
            <label class="com-label">${escapeHtml(tituloCampo.label)}</label>
            ${inputHtml(tituloCampo, it[tituloCampo.name], "", "com-input")}
          </div>
          <div class="com-badges" data-cat-role="badges">${badgesHtml(cfg, it)}</div>
        </div>

        <div class="com-form-grid" style="grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;">
          ${demais.map((c) => `
            <div class="com-field" ${c.tipo === "prof" ? 'style="grid-column:1 / -1;"' : ""}>
              <label class="com-label">${escapeHtml(c.label)}</label>
              ${inputHtml(c, it[c.name])}
            </div>`).join("")}
        </div>

        ${areas.map((c) => `
          <div class="com-field">
            <label class="com-label">${escapeHtml(c.label)}</label>
            ${inputHtml(c, it[c.name])}
          </div>`).join("")}

        <div class="com-actions" style="justify-content:flex-end;">
          <button type="button" class="com-btn ${ativo ? "com-btn--ghost" : "com-btn--primary"}" data-cat-action="status" data-id="${it.id}">
            ${ativo ? "Desativar" : "Ativar"}
          </button>
        </div>
      </article>`;
  }

  function badgesHtml(cfg, it) {
    const ativo = Number(it.ativo) === 1;
    return [
      `<span class="com-badge ${ativo ? "com-badge--active" : "com-badge--inactive"}">${ativo ? "Ativo" : "Inativo"}</span>`,
      ...cfg.badges(it),
    ].join("");
  }

  // Lê o cartão e devolve só o que mudou, no formato do PUT.
  // Campo em branco: a API mantém o valor atual (exceto duração prevista, que limpa).
  function lerCartao(cfg, card, original) {
    const mudou = {};
    const efetivo = { ...original };

    for (const c of cfg.campos) {
      const el = card.querySelector(`[data-cat-field="${c.name}"]`);
      if (!el) continue;

      const raw = el.value;
      const vazio = String(raw).trim() === "";
      let novo;

      if (c.tipo === "number") {
        if (vazio) {
          if (!c.opcional) continue;
          novo = null;
        } else {
          novo = numero(raw, 0, !!c.inteiro);
        }
      } else if (c.tipo === "prof") {
        if (vazio) continue;
        novo = numero(raw, 0, true);
      } else if (c.tipo === "select") {
        if (vazio) continue;
        novo = String(raw).trim().toLowerCase();
      } else {
        if (vazio) continue;
        novo = String(raw).trim();
      }

      const antigo = original[c.name] === undefined ? null : original[c.name];
      const igual = c.tipo === "number" || c.tipo === "prof"
        ? (antigo === null || antigo === "" ? null : Number(antigo)) === novo
        : String(antigo ?? "").trim() === String(novo ?? "").trim();

      efetivo[c.name] = novo;
      if (!igual) mudou[c.name] = novo;
    }

    // valores efetivos já normalizados para o validador
    const v = {};
    for (const c of cfg.campos) {
      const bruto = efetivo[c.name];
      if (c.tipo === "number" || c.tipo === "prof") v[c.name] = bruto === null || bruto === "" || bruto === undefined ? null : Number(bruto);
      else v[c.name] = String(bruto ?? "").trim();
    }
    if (v.profissional_id === null) v.profissional_id = 0;
    for (const c of cfg.campos) {
      if (c.tipo === "number" && v[c.name] === null && !c.opcional) v[c.name] = c.padrao ?? 0;
    }

    return { mudou, efetivo: v };
  }

  // =========================================================
  // CONTROLADOR DE UM CATÁLOGO
  // =========================================================
  function iniciarCatalogo(chave) {
    const cfg = CATALOGOS[chave];
    const root = document.getElementById(`catPainel-${chave}`);
    if (!cfg || !root) return null;

    const q = (role) => root.querySelector(`[data-cat-role="${role}"]`);
    const acao = (nome) => root.querySelector(`[data-cat-action="${nome}"]`);

    const st = { itens: [] };
    const painelCadastro = q("painel-cadastro");
    const painelGestao = q("painel-gestao");
    const lista = q("lista");
    const form = q("form");

    renderFormulario(root, cfg);

    function atualizarSelectsProf() {
      const atual = form.querySelector('[data-cat-field="profissional_id"]');
      if (atual) atual.innerHTML = opcoesProf({ selecionado: atual.value, vazio: "Selecione..." });

      const filtro = q("filtro-prof");
      if (filtro) filtro.innerHTML = opcoesProf({ selecionado: filtro.value, vazio: "Todos os profissionais" });
    }

    function resetFormulario() {
      form.reset();
      renderFormulario(root, cfg);
      atualizarSelectsProf();
      const sw = form.querySelector('[data-cat-field="ativo"]');
      if (sw) sw.checked = true;
    }

    async function carregar() {
      const params = new URLSearchParams();
      const busca = q("filtro-busca")?.value?.trim() || "";
      const ativo = q("filtro-ativo")?.value || "";
      const prof = q("filtro-prof")?.value || "";

      if (busca) params.set("q", busca);
      if (ativo !== "") params.set("ativo", ativo);
      if (prof) params.set("profissional_id", prof);

      const data = await requestJSON(`${cfg.base}?${params.toString()}`);
      st.itens = Array.isArray(data.items) ? data.items : [];
      renderizar();
    }

    function renderizar() {
      if (!st.itens.length) {
        lista.innerHTML = `
          <div class="com-empty">
            <strong>Nenhum ${escapeHtml(cfg.singular)} encontrado.</strong>
            <span>Cadastre um novo item ou ajuste os filtros da pesquisa.</span>
          </div>`;
        return;
      }

      lista.innerHTML = st.itens.map((it) => cartaoHtml(cfg, it)).join("");
    }

    const cartao = (id) => lista.querySelector(`[data-cat-id="${id}"]`);
    const item = (id) => st.itens.find((x) => String(x.id) === String(id));

    async function enviarCadastro(ev) {
      ev.preventDefault();

      const valores = lerFormulario(root, cfg);
      const erro = cfg.validar(valores);

      if (erro) {
        toast(erro);
        return;
      }

      const btn = q("salvar");
      setLoading(btn, true);

      try {
        await requestJSON(cfg.base, { method: "POST", body: JSON.stringify(valores) });

        toast(`${cfg.Singular} ${cfg.cadastrado} com sucesso.`);
        resetFormulario();
        togglePanel(painelCadastro, acao("toggle-cadastro"), false);
        if (!painelGestao.hidden) await carregar();
      } catch (err) {
        toast(err.message || `Não foi possível salvar o ${cfg.singular}.`);
      } finally {
        setLoading(btn, false);
      }
    }

    async function salvarAlteracoes() {
      const btn = acao("salvar-tudo");
      const pendentes = [];

      for (const it of st.itens) {
        const card = cartao(it.id);
        if (!card) continue;

        const { mudou, efetivo } = lerCartao(cfg, card, it);
        if (!Object.keys(mudou).length) continue;

        const erro = cfg.validar(efetivo);
        if (erro) {
          toast(`${it[cfg.titulo] || "#" + it.id}: ${erro}`);
          return;
        }

        pendentes.push({ it, mudou });
      }

      if (!pendentes.length) {
        toast("Nenhuma alteração para salvar.");
        return;
      }

      setLoading(btn, true, "Salvando...");

      try {
        for (const { it, mudou } of pendentes) {
          try {
            const data = await requestJSON(`${cfg.base}/${it.id}`, { method: "PUT", body: JSON.stringify(mudou) });
            Object.assign(it, data.item || mudou);
          } catch (err) {
            throw new Error(`${it[cfg.titulo] || "#" + it.id}: ${err.message}`);
          }
        }

        toast("Alterações salvas com sucesso.");
        await carregar();
      } catch (err) {
        toast(err.message || "Erro ao salvar alterações.");
      } finally {
        setLoading(btn, false);
      }
    }

    async function alternarStatus(id, botao) {
      const it = item(id);
      if (!it) return;

      const novo = Number(it.ativo) === 1 ? 0 : 1;
      botao.disabled = true;

      try {
        const data = await requestJSON(`${cfg.base}/${id}/status`, { method: "PATCH", body: JSON.stringify({ ativo: novo }) });
        it.ativo = data.item ? data.item.ativo : novo;

        // atualiza só selo e botão: edições não salvas nos campos do cartão são preservadas
        const card = cartao(id);
        card.querySelector('[data-cat-role="badges"]').innerHTML = badgesHtml(cfg, it);
        const ativo = Number(it.ativo) === 1;
        botao.textContent = ativo ? "Desativar" : "Ativar";
        botao.classList.toggle("com-btn--ghost", ativo);
        botao.classList.toggle("com-btn--primary", !ativo);
      } catch (err) {
        toast(err.message || "Não foi possível alterar o status.");
      } finally {
        botao.disabled = false;
      }
    }

    // ---- eventos
    acao("toggle-cadastro").addEventListener("click", () => togglePanel(painelCadastro, acao("toggle-cadastro")));

    acao("toggle-gestao").addEventListener("click", async () => {
      togglePanel(painelGestao, acao("toggle-gestao"));
      if (!painelGestao.hidden) {
        try { await carregar(); } catch (err) { toast(err.message); }
      }
    });

    acao("fechar-cadastro").addEventListener("click", () => togglePanel(painelCadastro, acao("toggle-cadastro"), false));
    acao("fechar-gestao").addEventListener("click", () => togglePanel(painelGestao, acao("toggle-gestao"), false));
    acao("limpar").addEventListener("click", resetFormulario);
    acao("atualizar").addEventListener("click", () => carregar().catch((err) => toast(err.message)));
    acao("salvar-tudo").addEventListener("click", salvarAlteracoes);

    form.addEventListener("submit", enviarCadastro);

    const recarregar = () => carregar().catch((err) => toast(err.message));
    q("filtro-busca").addEventListener("input", debounce(recarregar, 250));
    q("filtro-ativo").addEventListener("change", recarregar);
    q("filtro-prof").addEventListener("change", recarregar);

    lista.addEventListener("click", (ev) => {
      const btn = ev.target.closest('[data-cat-action="status"]');
      if (btn) alternarStatus(btn.dataset.id, btn);
    });

    return { atualizarSelectsProf, carregar };
  }

  // =========================================================
  // ABAS + INIT
  // =========================================================
  function iniciarAbas() {
    const tabs = Array.from(document.querySelectorAll("[data-cat-tab]"));

    function mostrar(chave) {
      for (const t of tabs) {
        const ativo = t.dataset.catTab === chave;
        t.classList.toggle("is-active", ativo);
        t.setAttribute("aria-selected", String(ativo));
      }

      for (const k of Object.keys(CATALOGOS)) {
        const painel = document.getElementById(`catPainel-${k}`);
        if (painel) painel.hidden = k !== chave;
      }
    }

    tabs.forEach((t) => t.addEventListener("click", () => mostrar(t.dataset.catTab)));
    mostrar("planos");
  }

  async function init() {
    if (!document.getElementById("secaoCatalogos")) return;

    const ctrl = Object.keys(CATALOGOS).map(iniciarCatalogo).filter(Boolean);
    iniciarAbas();

    try {
      await carregarProfissionais();
    } catch (err) {
      toast(err.message || "Não foi possível carregar a lista de profissionais.");
    }

    ctrl.forEach((c) => c.atualizarSelectsProf());
  }

  document.addEventListener("DOMContentLoaded", init);
})();
