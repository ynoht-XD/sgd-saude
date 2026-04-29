/* admin/static/js/modulos.js */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", () => {
    initFeather();
    initCards();
    initStats();
    initCollapseCategorias();
    initTabs();
    initCboCollapse();
    initNivelSelects();
    initSwitches();
    initQuickActions();
    initSubmitProtection();
  });

  const qs = (s, r = document) => r.querySelector(s);
  const qsa = (s, r = document) => Array.from(r.querySelectorAll(s));

  function initFeather() {
    if (window.feather?.replace) window.feather.replace();
  }

  function parseName(name) {
    // nivel__agenda__ROLE__PROFISSIONAL
    const parts = String(name || "").split("__");
    if (parts.length !== 4 || parts[0] !== "nivel") return null;
    return {
      modulo: parts[1],
      tipo: parts[2],
      valor: parts[3],
    };
  }

  function setSelectValue(select, value, force = true) {
    if (!select) return;

    if (!force && select.dataset.manual === "1") return;

    select.value = String(value ?? "0");
    applyNivelClass(select);
  }

  function initCards() {
    qsa("[data-modulo-card]").forEach(updateCardState);
  }

  function updateCardState(card) {
    const ativo = qs(".js-modulo-ativo", card);
    if (!ativo) return;

    card.classList.toggle("is-active", ativo.checked);
    card.classList.toggle("is-disabled", !ativo.checked);
  }

  function updateStats() {
    const statAtivos = qs("#statAtivos");
    if (statAtivos) statAtivos.textContent = qsa(".js-modulo-ativo:checked").length;
  }

  function initStats() {
    updateStats();
  }

  function initSwitches() {
    qsa("[data-modulo-card]").forEach((card) => {
      const ativo = qs(".js-modulo-ativo", card);
      if (!ativo) return;

      ativo.addEventListener("change", () => {
        updateCardState(card);
        updateStats();
        pulseSaveFooter();
      });
    });
  }

  function initCollapseCategorias() {
    qsa("[data-collapse]").forEach((btn) => {
      const card = btn.closest(".categoria-card");
      btn.setAttribute("aria-expanded", "true");

      btn.addEventListener("click", () => {
        if (!card) return;
        card.classList.toggle("is-collapsed");
        btn.setAttribute("aria-expanded", !card.classList.contains("is-collapsed"));
      });
    });
  }

  function initTabs() {
    qsa(".access-tabs").forEach((tabsBox) => {
      const card = tabsBox.closest("[data-modulo-card]");
      const buttons = qsa(".access-tab", tabsBox);

      buttons.forEach((btn) => {
        btn.addEventListener("click", () => {
          const targetId = btn.dataset.tabTarget;
          if (!targetId || !card) return;

          buttons.forEach((b) => b.classList.remove("is-active"));
          btn.classList.add("is-active");

          qsa(".access-tab-panel", card).forEach((panel) => {
            panel.classList.toggle("is-active", panel.id === targetId);
          });
        });
      });
    });
  }

  function initCboCollapse() {
    qsa("[data-cbo-toggle]").forEach((btn) => {
      const group = btn.closest(".cbo-group");
      if (!group) return;

      group.classList.add("is-collapsed");
      btn.setAttribute("aria-expanded", "false");

      btn.addEventListener("click", () => {
        group.classList.toggle("is-collapsed");
        btn.setAttribute("aria-expanded", !group.classList.contains("is-collapsed"));
      });
    });
  }

  function initNivelSelects() {
    qsa(".nivel-select").forEach((select) => {
      applyNivelClass(select);

      const meta = parseName(select.name);

      // Guarda o valor original para sabermos o que foi exceção manual.
      select.dataset.original = select.value || "0";

      select.addEventListener("change", () => {
        applyNivelClass(select);
        markChanged(select);

        if (!meta) return;

        select.dataset.manual = "1";

        if (meta.tipo === "ROLE") {
          propagarRole(select, meta);
        }

        if (meta.tipo === "CBO") {
          propagarCbo(select, meta);
        }

        pulseSaveFooter();
      });
    });
  }

  function applyNivelClass(select) {
    select.classList.remove("nivel-0", "nivel-1", "nivel-2", "nivel-3");
    select.classList.add(`nivel-${String(select.value || "0")}`);
  }

  function propagarRole(roleSelect, meta) {
    const card = roleSelect.closest("[data-modulo-card]");
    if (!card) return;

    const nivel = roleSelect.value;
    const role = meta.valor;

    const pessoasDaRole = qsa(`select.nivel-select[name^="nivel__${meta.modulo}__USUARIO__"]`, card)
      .filter((sel) => {
        const row = sel.closest(".person-row");
        const roleText = (row?.dataset.role || row?.querySelector("small")?.textContent || "").toUpperCase();

        if (role === "RECEPCAO") return roleText.includes("RECEPCAO") || roleText.includes("RECEPÇÃO");
        return roleText.includes(role);
      });

    pessoasDaRole.forEach((sel) => {
      const original = sel.dataset.original || "0";
      const manual = sel.dataset.manual === "1";

      // Só propaga em quem não foi ajustado manualmente.
      // Assim: Profissionais podem ver, mas João específico pode ficar sem acesso.
      if (!manual || original === sel.value) {
        setSelectValue(sel, nivel, true);
        sel.dataset.inheritedFrom = `ROLE:${role}`;
      }
    });
  }

  function propagarCbo(cboSelect, meta) {
    const group = cboSelect.closest(".cbo-group");
    if (!group) return;

    const nivel = cboSelect.value;

    qsa(`select.nivel-select[name^="nivel__${meta.modulo}__USUARIO__"]`, group).forEach((sel) => {
      const manual = sel.dataset.manual === "1";

      if (!manual) {
        setSelectValue(sel, nivel, true);
        sel.dataset.inheritedFrom = `CBO:${meta.valor}`;
      }
    });
  }

  function markChanged(el) {
    const row = el.closest(".person-row, .access-group, .cbo-level-row, .mod-card");
    if (!row) return;

    row.classList.add("is-changed");
    setTimeout(() => row.classList.remove("is-changed"), 900);
  }

  function initQuickActions() {
    qs("#btnAtivarEssenciais")?.addEventListener("click", ativarEssenciais);
    qs("#btnDesativarTodos")?.addEventListener("click", desativarTodos);
    qs("#btnExpandirTudo")?.addEventListener("click", expandirTudo);
    qs("#btnRecolherTudo")?.addEventListener("click", recolherTudo);
  }

  function ativarEssenciais() {
    const essenciais = new Set([
      "dashboard", "agenda", "meus_atendimentos", "cadastro",
      "lista_atendimentos", "avaliacoes", "pacientes", "pts",
      "registros", "admin_painel", "admin_usuarios", "admin_modulos",
      "admin_cbo", "admin_cid", "admin_cep_ibge"
    ]);

    qsa("[data-modulo-card]").forEach((card) => {
      const ativo = qs(".js-modulo-ativo", card);
      if (!ativo) return;

      ativo.checked = essenciais.has(card.dataset.codigo);
      updateCardState(card);
    });

    updateStats();
    pulseSaveFooter();
  }

  function desativarTodos() {
    if (!confirm("Deseja desativar todos os módulos desta clínica?")) return;

    qsa(".js-modulo-ativo").forEach((input) => input.checked = false);
    qsa("[data-modulo-card]").forEach(updateCardState);

    updateStats();
    pulseSaveFooter();
  }

  function expandirTudo() {
    qsa(".categoria-card, .cbo-group").forEach((el) => el.classList.remove("is-collapsed"));
    qsa("[data-collapse], [data-cbo-toggle]").forEach((btn) => btn.setAttribute("aria-expanded", "true"));
  }

  function recolherTudo() {
    qsa(".categoria-card, .cbo-group").forEach((el) => el.classList.add("is-collapsed"));
    qsa("[data-collapse], [data-cbo-toggle]").forEach((btn) => btn.setAttribute("aria-expanded", "false"));
  }

  function initSubmitProtection() {
    const form = qs("#formModulos");
    if (!form) return;

    form.addEventListener("submit", (event) => {
      if (!qsa(".js-modulo-ativo:checked").length) {
        if (!confirm("Nenhum módulo está ativo para esta clínica. Deseja salvar mesmo assim?")) {
          event.preventDefault();
        }
      }
    });
  }

  function pulseSaveFooter() {
    const footer = qs(".save-footer");
    if (!footer) return;

    footer.classList.remove("is-pulsing");
    void footer.offsetWidth;
    footer.classList.add("is-pulsing");

    setTimeout(() => footer.classList.remove("is-pulsing"), 900);
  }
})();