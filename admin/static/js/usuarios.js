// admin/static/js/usuarios.js
(() => {
  "use strict";

  // ===== Helpers =====
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const on = (el, ev, fn) => el && el.addEventListener(ev, fn);
  const onlyDigits = (s) => (s || "").replace(/\D+/g, "");
  const debounce = (fn, ms = 200) => {
    let t;
    return (...a) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...a), ms);
    };
  };

  // ===== Elements =====
  const btnNovo = $("#btnNovoUsuario");
  const btnNiveis = $("#btnGerenciarNiveis");
  const dialog = $("#modalUsuario");
  const formUsuario = $("#formUsuario");
  const tituloModal = $("#tituloModalUsuario");
  const drawer = $("#drawerNiveis");
  const table = $("#tUsuarios");
  const cardsWrap = $(".usuarios-cards");
  const filtrosForm = $("#filtrosUsuarios");

  // Inputs do modal principal
  const iIdHid = $("#u_id_hidden");
  const iNome = $("#u_nome");
  const iEmail = $("#u_email");
  const iCPF = $("#u_cpf");
  const iCNS = $("#u_cns");
  const iNasc = $("#u_nascimento");
  const iSexo = $("#u_sexo");
  const iConselho = $("#u_conselho");
  const iRegConselho = $("#u_registro_conselho");
  const iUFConselho = $("#u_uf_conselho");

  // CBO
  const iCBO = $("#u_cbo"); // hidden com valor real
  const iCBOBusca = $("#u_cbo_busca"); // input visível
  const iCBOSugestoes = $("#u_cbo_sugestoes");
  const iCBOHint = $("#u_cbo_hint");

  const iTel = $("#u_telefone");
  const iRole = $("#u_role");
  const iStatus = $("#u_status");
  const iCEP = $("#u_cep");
  const iLogradouro = $("#u_logradouro");
  const iNumero = $("#u_numero");
  const iCompl = $("#u_complemento");
  const iBairro = $("#u_bairro");
  const iMunicipio = $("#u_municipio");
  const iUF = $("#u_uf");

  // Grupo de senhas
  const gSenhas = $("#u_senhas_group");
  const iSenha = $("#u_senha");
  const iSenha2 = $("#u_senha2");

  // Modal de senha
  const dialogSenha = $("#modalSenha");
  const formSenha = $("#formSenha");
  const iIdSenha = $("#u_id_senha");
  const sSenha = $("#s_senha");
  const sSenha2 = $("#s_senha2");

  // Drawer níveis
  const formNivel = $("#formNivel");
  const listaNiveis = $("#listaNiveis");

  // Permissões
  const permGrid = $("#permGrid");
  const permHidden = $("#permHidden");

  const ALL_PERMS = [
    "cadastro", "pacientes", "atendimentos", "agenda",
    "export_bpai", "export_apac", "export_ciha",
    "financeiro", "rh"
  ];

  const ROLE_DEFAULTS = {
    RECEPCAO: new Set(["cadastro", "agenda", "atendimentos"]),
    PROFISSIONAL: new Set(["pacientes", "agenda", "atendimentos"]),
    ADMIN: new Set(ALL_PERMS),
  };

  // CBO autocomplete state
  let cboSelecionado = null;
  let cboDebounce = null;

  // ===== Base /admin estável para rotas =====
  function baseAdmin() {
    const a = document.createElement("a");
    a.href = $("#tUsuarios")?.baseURI || window.location.href;
    const m = a.pathname.match(/^(.*)\/usuarios/);
    return (m && m[1]) || "/admin";
  }

  // ===== Permissões =====
  function setPerms(selectionSet) {
    if (!permGrid) return;
    $$(".perm-pill", permGrid).forEach((btn) => {
      const key = btn.getAttribute("data-perm");
      const isOn = selectionSet.has(key);
      btn.classList.toggle("on", isOn);
      btn.classList.toggle("active", isOn);
      btn.setAttribute("aria-pressed", isOn ? "true" : "false");
    });
    syncHiddenPerms();
  }

  function getSelectedPerms() {
    if (!permGrid) return [];
    return $$(".perm-pill.on, .perm-pill.active", permGrid).map((b) => b.getAttribute("data-perm"));
  }

  function syncHiddenPerms() {
    if (!permHidden) return;
    permHidden.innerHTML = "";

    $$(".perm-pill[aria-pressed='true'], .perm-pill.on, .perm-pill.active", permGrid || document).forEach((p) => {
      const key = p.dataset.perm;
      if (!key) return;

      const inp = document.createElement("input");
      inp.type = "hidden";
      inp.name = "perm_" + key;
      inp.value = "1";
      permHidden.appendChild(inp);
    });
  }

  function applyRoleDefaults() {
    const role = iRole?.value || "";
    const def = ROLE_DEFAULTS[role] || new Set();
    setPerms(def);
  }

  // ===== Modal principal =====
  function openDialog(el) {
    if (!el) return;
    try {
      el.showModal();
    } catch {
      el.setAttribute("open", "");
      el.classList.add("open");
      el.style.display = "grid";
      el.style.placeItems = "center";
    }
  }

  function closeDialog(el) {
    if (!el) return;
    try {
      el.close();
    } catch {
      el.removeAttribute("open");
      el.classList.remove("open");
      el.style.display = "";
      el.style.placeItems = "";
    }
  }

  function resetCboField() {
    cboSelecionado = null;
    if (iCBO) iCBO.value = "";
    if (iCBOBusca) iCBOBusca.value = "";
    hideCboSuggestions();
    setCboHint("Digite pelo menos 2 caracteres.");
  }

  function clearForm() {
    const inputs = [
      iIdHid, iNome, iEmail, iCPF, iCNS, iNasc, iSexo, iConselho, iRegConselho, iUFConselho,
      iTel, iRole, iStatus, iCEP, iLogradouro, iNumero, iCompl, iBairro, iMunicipio, iUF
    ];

    inputs.forEach((inp) => {
      if (!inp) return;
      if (inp.tagName === "SELECT") {
        inp.selectedIndex = 0;
      } else {
        inp.value = "";
      }
    });

    resetCboField();

    if (iStatus) iStatus.value = "1";

    if (permGrid) {
      $$(".perm-pill", permGrid).forEach((btn) => {
        btn.classList.remove("on", "active");
        btn.setAttribute("aria-pressed", "false");
      });
    }
    if (permHidden) permHidden.innerHTML = "";

    if (iSenha) iSenha.value = "";
    if (iSenha2) iSenha2.value = "";
  }

  function showPasswords(show) {
    if (!gSenhas) return;
    gSenhas.style.display = show ? "" : "none";

    if (iSenha) iSenha.toggleAttribute("required", show);
    if (iSenha2) iSenha2.toggleAttribute("required", show);

    if (!show) {
      if (iSenha) iSenha.value = "";
      if (iSenha2) iSenha2.value = "";
    }
  }

  function openCreate() {
    clearForm();
    if (tituloModal) tituloModal.textContent = "Novo usuário";
    showPasswords(true);

    if (formUsuario) {
      formUsuario.setAttribute(
        "action",
        formUsuario.dataset.actionCreate || formUsuario.action || `${baseAdmin()}/usuarios/novo`
      );
    }

    applyRoleDefaults();
    openDialog(dialog);
  }

  // ===== CBO autocomplete =====
  function setCboHint(text) {
    if (iCBOHint) iCBOHint.textContent = text;
  }

  function hideCboSuggestions() {
    if (!iCBOSugestoes) return;
    iCBOSugestoes.innerHTML = "";
    iCBOSugestoes.hidden = true;
  }

  function fillCboSelected(codigo, descricao) {
    const c = String(codigo || "").trim();
    const d = String(descricao || "").trim();

    cboSelecionado = { codigo: c, descricao: d };

    if (iCBO) iCBO.value = c;
    if (iCBOBusca) iCBOBusca.value = [c, d].filter(Boolean).join(" — ");

    setCboHint(d ? `Selecionado: ${d}` : "CBO selecionado.");
    hideCboSuggestions();
  }

  function showCboSuggestions(items) {
    if (!iCBOSugestoes) return;

    if (!items.length) {
      iCBOSugestoes.innerHTML = `<div class="autocomplete-empty">Nenhum CBO encontrado.</div>`;
      iCBOSugestoes.hidden = false;
      return;
    }

    iCBOSugestoes.innerHTML = items.map((item) => `
      <button
        type="button"
        class="autocomplete-item"
        data-codigo="${String(item.codigo || "").replace(/"/g, "&quot;")}"
        data-descricao="${String(item.descricao || "").replace(/"/g, "&quot;")}"
      >
        <strong>${item.codigo || ""}</strong>
        <span>${item.descricao || ""}</span>
      </button>
    `).join("");

    iCBOSugestoes.hidden = false;
  }

  async function fetchCboSuggestions(q) {
    const termo = String(q || "").trim();

    if (termo.length < 2) {
      hideCboSuggestions();
      setCboHint("Digite pelo menos 2 caracteres.");
      return;
    }

    try {
      const response = await fetch(`${baseAdmin()}/api/cbos-catalogo/buscar?q=${encodeURIComponent(termo)}`, {
        credentials: "same-origin",
      });

      const data = await response.json();

      if (!response.ok || !data.ok) {
        showCboSuggestions([]);
        setCboHint("Não foi possível buscar o CBO.");
        return;
      }

      showCboSuggestions(data.items || []);
      setCboHint(`${(data.items || []).length} sugestão(ões) encontrada(s).`);
    } catch (error) {
      console.error("Erro ao buscar CBO:", error);
      showCboSuggestions([]);
      setCboHint("Erro ao buscar CBO.");
    }
  }

  // ===== Editar usuário =====
  async function openEdit(uid) {
    clearForm();

    if (tituloModal) tituloModal.textContent = "Editar usuário";
    showPasswords(false);

    const fromRow = () => {
      const tr = table?.querySelector(`tr[data-id="${uid}"]`);
      if (!tr) return false;

      const txt = (i) => (tr.children[i]?.textContent || "").trim();

      if (iIdHid) iIdHid.value = uid;
      if (iNome) iNome.value = txt(0);
      if (iCPF) iCPF.value = txt(1);
      if (iEmail) iEmail.value = txt(2);

      const nivelTxt = (txt(3) || "").toUpperCase().replace(/\s+/g, "_");
      if (iRole) iRole.value = nivelTxt;

      const cboTxt = txt(4) || "";
      const match = cboTxt.match(/^(\d+)/);
      if (match) {
        if (iCBO) iCBO.value = match[1];
        if (iCBOBusca) iCBOBusca.value = cboTxt;
      }

      const isActive = (tr.children[5]?.textContent || "").includes("Ativo");
      if (iStatus) iStatus.value = isActive ? "1" : "0";

      applyRoleDefaults();
      return true;
    };

    fromRow();

    try {
      const res = await fetch(`${baseAdmin()}/usuarios/${uid}.json`, { credentials: "same-origin" });
      if (!res.ok) throw new Error("Falha ao carregar JSON do usuário.");

      const u = await res.json();

      if (iIdHid) iIdHid.value = u.id || uid;
      if (iNome) iNome.value = u.nome || "";
      if (iEmail) iEmail.value = u.email || "";
      if (iCPF) iCPF.value = u.cpf || "";
      if (iCNS) iCNS.value = (u.cns || "").slice(0, 15);
      if (iNasc) iNasc.value = u.nascimento || "";
      if (iSexo) iSexo.value = u.sexo || "";
      if (iConselho) iConselho.value = u.conselho || "";
      if (iRegConselho) iRegConselho.value = u.registro_conselho || "";
      if (iUFConselho) iUFConselho.value = u.uf_conselho || "";
      if (iTel) iTel.value = u.telefone || "";
      if (iCEP) iCEP.value = u.cep || "";
      if (iLogradouro) iLogradouro.value = u.logradouro || "";
      if (iNumero) iNumero.value = u.numero || "";
      if (iCompl) iCompl.value = u.complemento || "";
      if (iBairro) iBairro.value = u.bairro || "";
      if (iMunicipio) iMunicipio.value = u.municipio || "";
      if (iUF) iUF.value = u.uf || "";
      if (iRole) iRole.value = u.role || (iRole.value || "");
      if (iStatus) iStatus.value = String(u.is_active ?? Number(iStatus.value || 1));

      if (iCBO) iCBO.value = u.cbo || "";
      if (iCBOBusca) iCBOBusca.value = u.cbo_label || u.cbo || "";

      try {
        const arr = JSON.parse(u.permissoes_json || "[]");
        if (Array.isArray(arr) && arr.length) {
          setPerms(new Set(arr));
        }
      } catch {
        // ignore
      }
    } catch {
      // fallback já preenchido pela linha
    }

    if (formUsuario) {
      formUsuario.setAttribute("action", `${baseAdmin()}/usuarios/${uid}/editar`);
    }

    openDialog(dialog);
  }

  // ===== Fechamentos =====
  function closeModalMain() {
    closeDialog(dialog);
  }

  function openDrawer() {
    drawer?.classList.add("open");
  }

  function closeDrawer() {
    drawer?.classList.remove("open");
  }

  // ===== Bind básico =====
  $$(".modal [data-modal-close]").forEach((btn) =>
    on(btn, "click", () => closeDialog(btn.closest("dialog") || dialog))
  );

  on(btnNiveis, "click", openDrawer);
  $$(".drawer [data-drawer-close]").forEach((btn) => on(btn, "click", closeDrawer));
  on(btnNovo, "click", openCreate);

  // ===== Máscaras =====
  function maskCPF(v) {
    v = onlyDigits(v).slice(0, 11);
    if (v.length > 9) return v.replace(/(\d{3})(\d{3})(\d{3})(\d{0,2})/, "$1.$2.$3-$4");
    if (v.length > 6) return v.replace(/(\d{3})(\d{3})(\d{0,3})/, "$1.$2.$3");
    if (v.length > 3) return v.replace(/(\d{3})(\d{0,3})/, "$1.$2");
    return v;
  }

  function maskTel(v) {
    v = onlyDigits(v).slice(0, 11);
    if (v.length > 10) return v.replace(/(\d{2})(\d{5})(\d{0,4})/, "($1) $2-$3");
    if (v.length > 6) return v.replace(/(\d{2})(\d{4})(\d{0,4})/, "($1) $2-$3");
    if (v.length > 2) return v.replace(/(\d{2})(\d{0,5})/, "($1) $2");
    return v;
  }

  function maskCEP(v) {
    v = onlyDigits(v).slice(0, 8);
    if (v.length > 5) return v.replace(/(\d{5})(\d{0,3})/, "$1-$2");
    return v;
  }

  on(iCPF, "input", (e) => e.target.value = maskCPF(e.target.value));
  on(iTel, "input", (e) => e.target.value = maskTel(e.target.value));
  on(iCEP, "input", (e) => e.target.value = maskCEP(e.target.value));
  on(iCNS, "input", (e) => e.target.value = onlyDigits(e.target.value).slice(0, 15));

  // ===== CBO events =====
  if (iCBOBusca) {
    on(iCBOBusca, "input", () => {
      const termo = iCBOBusca.value;

      cboSelecionado = null;
      if (iCBO) iCBO.value = "";

      clearTimeout(cboDebounce);
      cboDebounce = setTimeout(() => {
        fetchCboSuggestions(termo);
      }, 180);
    });

    on(iCBOBusca, "keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();

        const primeiroItem = iCBOSugestoes?.querySelector(".autocomplete-item");
        if (primeiroItem) {
          fillCboSelected(
            primeiroItem.dataset.codigo || "",
            primeiroItem.dataset.descricao || ""
          );
        }
      }
    });

    on(iCBOBusca, "blur", () => {
      setTimeout(() => hideCboSuggestions(), 220);
    });
  }

  if (iCBOSugestoes) {
    on(iCBOSugestoes, "mousedown", (e) => {
      const btn = e.target.closest(".autocomplete-item");
      if (!btn) return;

      e.preventDefault();

      fillCboSelected(
        btn.dataset.codigo || "",
        btn.dataset.descricao || ""
      );
    });
  }

  document.addEventListener("click", (e) => {
    const clicouNoCampo = e.target.closest(".cbo-field");
    if (!clicouNoCampo) {
      hideCboSuggestions();
    }
  });

  // ===== Validação =====
  function validate() {
    const errors = [];

    if (!iNome?.value.trim()) errors.push("Informe o Nome.");

    const cpfDigits = onlyDigits(iCPF?.value);
    if (!cpfDigits || cpfDigits.length !== 11) errors.push("CPF inválido.");

    if (iEmail?.value && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(iEmail.value)) {
      errors.push("E-mail inválido.");
    }

    if (!iRole?.value) errors.push("Selecione um nível.");

    if (iCBOBusca?.value && !iCBO?.value) {
      errors.push("Selecione um CBO válido na lista de sugestões.");
    }

    if (gSenhas?.style.display !== "none") {
      if (!iSenha?.value || iSenha.value.length < 6) {
        errors.push("Senha mínima de 6 caracteres.");
      }
      if (iSenha?.value !== iSenha2?.value) {
        errors.push("A confirmação da senha não confere.");
      }
    }

    if (errors.length) {
      alert("Corrija os campos:\n• " + errors.join("\n• "));
      return false;
    }

    return true;
  }

  function normalizeBeforeSubmit() {
    if (iCPF) iCPF.value = onlyDigits(iCPF.value);
    if (iCEP) iCEP.value = onlyDigits(iCEP.value);
    if (iTel) iTel.value = onlyDigits(iTel.value);
    if (iCNS) iCNS.value = onlyDigits(iCNS.value);
    if (iCBO) iCBO.value = onlyDigits(iCBO.value).slice(0, 6);
    syncHiddenPerms();
  }

  on(formUsuario, "submit", (e) => {
    if (!validate()) {
      e.preventDefault();
      return;
    }
    normalizeBeforeSubmit();
  });

  // ===== Ações na tabela =====
  on(table, "click", (e) => {
    const btn = e.target.closest("[data-action]");
    if (!btn) return;

    const tr = btn.closest("tr");
    const id = tr?.getAttribute("data-id");
    const action = btn.getAttribute("data-action");

    if (action === "edit") {
      if (id) openEdit(id);
      return;
    }

    if (action === "password" && dialogSenha && formSenha) {
      if (!id) return;

      if (iIdSenha) iIdSenha.value = id;
      formSenha.setAttribute("action", `${baseAdmin()}/usuarios/${id}/senha`);
      if (sSenha) sSenha.value = "";
      if (sSenha2) sSenha2.value = "";
      openDialog(dialogSenha);
    }
  });

  // ===== Ações nos cards mobile =====
  on(cardsWrap, "click", (e) => {
    const btn = e.target.closest("[data-action]");
    if (!btn) return;

    const card = e.target.closest("[data-id]");
    const id = card?.getAttribute("data-id");
    const action = btn.getAttribute("data-action");

    if (action === "edit") {
      if (id) openEdit(id);
      return;
    }

    if (action === "password" && dialogSenha && formSenha) {
      if (!id) return;

      if (iIdSenha) iIdSenha.value = id;
      formSenha.setAttribute("action", `${baseAdmin()}/usuarios/${id}/senha`);
      if (sSenha) sSenha.value = "";
      if (sSenha2) sSenha2.value = "";
      openDialog(dialogSenha);
    }
  });

  // ===== Modal de senha =====
  function validateSenha() {
    const errs = [];
    if (!sSenha?.value || sSenha.value.length < 6) errs.push("Senha mínima de 6 caracteres.");
    if (sSenha?.value !== sSenha2?.value) errs.push("A confirmação da senha não confere.");

    if (errs.length) {
      alert("Corrija os campos:\n• " + errs.join("\n• "));
      return false;
    }
    return true;
  }

  on(formSenha, "submit", (e) => {
    if (!validateSenha()) {
      e.preventDefault();
    }
  });

  // ===== Toggle olho senha =====
  $$(".eye-btn").forEach((btn) => {
    const sel = btn.getAttribute("data-toggle-pass");
    const input = $(sel);
    on(btn, "click", () => {
      if (input) input.type = input.type === "password" ? "text" : "password";
    });
  });

  // ===== Filtros client-side =====
  on(filtrosForm, "submit", (e) => {
    e.preventDefault();
    applyFilters();
  });

  on($("#f_busca"), "input", debounce(applyFilters, 150));
  on($("#f_nivel"), "change", applyFilters);
  on($("#f_status"), "change", applyFilters);

  function applyFilters() {
    const q = ($("#f_busca")?.value || "").trim().toLowerCase();
    const nivel = $("#f_nivel")?.value || "";
    const status = $("#f_status")?.value || "";

    // tabela
    $$("tbody tr", table || document).forEach((tr) => {
      const nome = tr.children[0]?.textContent.toLowerCase() || "";
      const cpf = tr.children[1]?.textContent.toLowerCase() || "";
      const email = tr.children[2]?.textContent.toLowerCase() || "";
      const nivelTxt = tr.children[3]?.textContent || "";
      const cboTxt = tr.children[4]?.textContent.toLowerCase() || "";
      const ativo = tr.children[5]?.textContent.includes("Ativo") ? "ativo" : "inativo";

      const matchQ = !q || nome.includes(q) || cpf.includes(q) || email.includes(q) || cboTxt.includes(q);
      const matchNivel = !nivel || nivelTxt.toUpperCase().includes(nivel.toUpperCase());
      const matchStatus = !status || status === ativo;

      tr.style.display = (matchQ && matchNivel && matchStatus) ? "" : "none";
    });

    // cards
    $$("[data-id]", cardsWrap || document).forEach((card) => {
      if (card.tagName === "TR") return;

      const nome = $(".usuario-card-head h3", card)?.textContent.toLowerCase() || "";
      const email = $(".usuario-card-sub", card)?.textContent.toLowerCase() || "";
      const metas = $$(".usuario-meta-value", card).map((el) => el.textContent.toLowerCase());

      const cpf = metas[0] || "";
      const nivelTxt = metas[1] || "";
      const cboTxt = metas[2] || "";
      const ativo = ($(".badge", card)?.textContent || "").includes("Ativo") ? "ativo" : "inativo";

      const matchQ = !q || nome.includes(q) || cpf.includes(q) || email.includes(q) || cboTxt.includes(q);
      const matchNivel = !nivel || nivelTxt.toUpperCase().includes(nivel.toUpperCase());
      const matchStatus = !status || status === ativo;

      card.style.display = (matchQ && matchNivel && matchStatus) ? "" : "none";
    });
  }

  // ===== Drawer de níveis =====
  on(formNivel, "submit", () => {
    // backend já cuida
  });

  on(listaNiveis, "click", (e) => {
    const btn = e.target.closest("[data-edit-nivel],[data-delete-nivel]");
    if (!btn) return;

    const li = btn.closest("li");

    if (btn.hasAttribute("data-delete-nivel")) {
      e.preventDefault();
      if (confirm("Excluir este nível? (preview visual)")) li?.remove();
      return;
    }

    if (btn.hasAttribute("data-edit-nivel")) {
      e.preventDefault();
      const nomeTxt = li?.querySelector("strong")?.textContent.trim() || "";
      const slugTxt = li?.getAttribute("data-slug") || "";
      const lvlNome = $("#lvl_nome");
      const lvlSlug = $("#lvl_slug");

      if (lvlNome) lvlNome.value = nomeTxt;
      if (lvlSlug) lvlSlug.value = slugTxt;

      alert("Edite os campos e envie para salvar (preview).");
    }
  });

  // ===== Keyboard sugar =====
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (dialog?.open) closeModalMain();
      else if (dialogSenha?.open) closeDialog(dialogSenha);
      else if (drawer?.classList.contains("open")) closeDrawer();
    }

    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "n") {
      e.preventDefault();
      openCreate();
    }
  });

  // ===== Init =====
  if (formUsuario && !formUsuario.dataset.actionCreate) {
    formUsuario.dataset.actionCreate =
      formUsuario.getAttribute("action") || `${baseAdmin()}/usuarios/novo`;
  }

  if (permGrid) {
    on(permGrid, "click", (e) => {
      const btn = e.target.closest(".perm-pill");
      if (!btn) return;

      const isOn = btn.getAttribute("aria-pressed") === "true";
      btn.setAttribute("aria-pressed", isOn ? "false" : "true");
      btn.classList.toggle("on", !isOn);
      btn.classList.toggle("active", !isOn);
      syncHiddenPerms();
    });
  }

  applyFilters();
})();