// export/static/js/bpa.js
// ============================================================
// BPA-I · Front-end
// ============================================================

(() => {
  "use strict";

  const qs = (sel, root = document) => root.querySelector(sel);
  const qsa = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const digits = (s) => String(s || "").replace(/\D+/g, "");
  const onlyText = (s) => String(s || "").replace(/\s+/g, " ").trim();

  const formatBytes = (bytes = 0) => {
    const n = Number(bytes || 0);
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1024 / 1024).toFixed(2)} MB`;
  };

  const fileExt = (filename = "") => {
    const m = String(filename).toLowerCase().match(/\.[^.]+$/);
    return m ? m[0] : "";
  };

  const allowedExts = new Set([".xls", ".xlsx", ".csv"]);

  const toast = (msg, type = "info") => {
    let el = qs("#bpaToast");
    if (!el) {
      el = document.createElement("div");
      el.id = "bpaToast";
      el.className = "bpa-toast";
      document.body.appendChild(el);
    }

    el.textContent = msg;
    el.dataset.type = type;
    el.classList.add("show");

    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.remove("show"), 2800);
  };

  // ============================================================
  // CPF / COMPETÊNCIA
  // ============================================================

  const cpfIsValid = (cpf) => {
    cpf = digits(cpf);
    if (cpf.length !== 11) return false;
    if (/^(\d)\1{10}$/.test(cpf)) return false;

    const calcDV = (base) => {
      let sum = 0;
      for (let i = 0; i < base.length; i++) {
        sum += parseInt(base[i], 10) * (base.length + 1 - i);
      }
      const mod = sum % 11;
      return mod < 2 ? 0 : 11 - mod;
    };

    const dv1 = calcDV(cpf.slice(0, 9));
    const dv2 = calcDV(cpf.slice(0, 9) + dv1);
    return cpf.endsWith(`${dv1}${dv2}`);
  };

  const maskCPF = (value) => {
    const v = digits(value).slice(0, 11);
    if (v.length <= 3) return v;
    if (v.length <= 6) return `${v.slice(0, 3)}.${v.slice(3)}`;
    if (v.length <= 9) return `${v.slice(0, 3)}.${v.slice(3, 6)}.${v.slice(6)}`;
    return `${v.slice(0, 3)}.${v.slice(3, 6)}.${v.slice(6, 9)}-${v.slice(9, 11)}`;
  };

  const unmaskCPF = (value) => digits(value).slice(0, 11);

  const monthToCompetencia = (value) => {
    if (!value || !value.includes("-")) return "";
    const [yyyy, mm] = value.split("-");
    if (!yyyy || !mm) return "";
    return `${mm}/${yyyy}`;
  };

  const competenciaToMonth = (value) => {
    if (!value || !value.includes("/")) return "";
    const [mm, yyyy] = value.split("/");
    if (!yyyy || !mm) return "";
    return `${yyyy}-${mm}`;
  };

  // ============================================================
  // ELEMENTOS
  // ============================================================

  const form = qs("#bpaiForm");

  const cpfInput = qs("#cpf");
  const cpfHidden = qs("#cpfHidden");
  const compInput = qs("#competencia");
  const compHidden = qs("#competenciaHidden");
  const siglaInput = qs("#sigla");
  const orgaoInput = qs("#orgao");
  const fileInput = qs("#file");
  const fileInfo = qs("#fileInfo");
  const submitBtn = qs("#submitBtn");
  const errorBox = qs("#errorBox");
  const okBox = qs("#okBox");

  const fields = [cpfInput, compInput, siglaInput, orgaoInput, fileInput].filter(Boolean);

  // ============================================================
  // UI HELPERS
  // ============================================================

  const setMsg = (el, msg, show = true) => {
    if (!el) return;
    el.textContent = msg || "";
    el.style.display = show ? "block" : "none";
  };

  const setFieldState = (el, state) => {
    if (!el) return;

    el.classList.remove("is-valid", "is-invalid", "is-neutral");

    if (state === "valid") el.classList.add("is-valid");
    else if (state === "invalid") el.classList.add("is-invalid");
    else el.classList.add("is-neutral");
  };

  const markAllNeutral = () => {
    fields.forEach((field) => setFieldState(field, "neutral"));
  };

  const scrollToAuditIfExists = () => {
    const audit = qs(".auditoria-card");
    if (!audit) return;

    setTimeout(() => {
      audit.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 180);
  };

  const setButtonLoading = (loading) => {
    if (!submitBtn) return;

    if (loading) {
      submitBtn.dataset.originalText = submitBtn.textContent;
      submitBtn.textContent = "Processando auditoria...";
      submitBtn.disabled = true;
      submitBtn.classList.add("is-loading");
    } else {
      submitBtn.textContent = submitBtn.dataset.originalText || "Processar e auditar";
      submitBtn.classList.remove("is-loading");
    }
  };

  // ============================================================
  // FORM
  // ============================================================

  const validateFile = () => {
    const f = fileInput?.files?.[0];

    if (!f) {
      return { ok: false, message: "Nenhum arquivo selecionado." };
    }

    const ext = fileExt(f.name);

    if (!allowedExts.has(ext)) {
      return { ok: false, message: "Arquivo inválido. Use XLS, XLSX ou CSV." };
    }

    return { ok: true, message: `${f.name} • ${formatBytes(f.size)}` };
  };

  const getValidation = () => {
    const cpfOk = cpfIsValid(cpfInput?.value);
    const compOk = !!compInput?.value;
    const siglaOk = onlyText(siglaInput?.value).length > 0;
    const orgaoOk = onlyText(orgaoInput?.value).length > 0;
    const fileStatus = validateFile();

    return {
      cpfOk,
      compOk,
      siglaOk,
      orgaoOk,
      fileOk: fileStatus.ok,
      fileMessage: fileStatus.message,
      allOk: cpfOk && compOk && siglaOk && orgaoOk && fileStatus.ok,
    };
  };

  const touchValidity = ({ silent = false } = {}) => {
    setMsg(errorBox, "", false);
    setMsg(okBox, "", false);

    const v = getValidation();

    setFieldState(cpfInput, cpfInput?.value ? (v.cpfOk ? "valid" : "invalid") : "neutral");
    setFieldState(compInput, compInput?.value ? (v.compOk ? "valid" : "invalid") : "neutral");
    setFieldState(siglaInput, siglaInput?.value ? (v.siglaOk ? "valid" : "invalid") : "neutral");
    setFieldState(orgaoInput, orgaoInput?.value ? (v.orgaoOk ? "valid" : "invalid") : "neutral");
    setFieldState(fileInput, fileInput?.files?.length ? (v.fileOk ? "valid" : "invalid") : "neutral");

    if (fileInfo) fileInfo.textContent = v.fileMessage;
    if (submitBtn) submitBtn.disabled = !v.allOk;

    if (!silent && fileInput?.files?.length && !v.fileOk) {
      setMsg(errorBox, v.fileMessage, true);
    }

    return v;
  };

  const explainInvalid = () => {
    const v = getValidation();

    if (!v.cpfOk) return "CPF inválido. Confira os dígitos informados.";
    if (!v.compOk) return "Informe a competência.";
    if (!v.siglaOk) return "Informe a sigla do órgão.";
    if (!v.orgaoOk) return "Informe o órgão de origem.";
    if (!v.fileOk) return v.fileMessage || "Selecione uma planilha válida.";

    return "Corrija os campos destacados e tente novamente.";
  };

  const initForm = () => {
    if (!form) return;

    cpfInput?.addEventListener("input", () => {
      cpfInput.value = maskCPF(cpfInput.value);
      if (cpfHidden) cpfHidden.value = unmaskCPF(cpfInput.value);
      touchValidity({ silent: true });
    });

    cpfInput?.addEventListener("blur", () => touchValidity());

    siglaInput?.addEventListener("input", () => {
      siglaInput.value = onlyText(siglaInput.value).toUpperCase();
      touchValidity({ silent: true });
    });

    orgaoInput?.addEventListener("input", () => {
      orgaoInput.value = onlyText(orgaoInput.value);
      touchValidity({ silent: true });
    });

    compInput?.addEventListener("change", () => {
      if (compHidden) compHidden.value = monthToCompetencia(compInput.value);
      touchValidity({ silent: true });
    });

    fileInput?.addEventListener("change", () => touchValidity());

    form.addEventListener("submit", (e) => {
      const v = touchValidity();

      if (!v.allOk) {
        e.preventDefault();
        setMsg(errorBox, explainInvalid(), true);
        setMsg(okBox, "", false);
        return;
      }

      if (cpfHidden) cpfHidden.value = unmaskCPF(cpfInput.value);
      if (compHidden) compHidden.value = monthToCompetencia(compInput.value);

      setMsg(errorBox, "", false);
      setMsg(okBox, "Validado! Auditando a produção...", true);
      setButtonLoading(true);
    });
  };

  // ============================================================
  // AUDITORIA / PAGINAÇÃO CLIENT-SIDE
  // ============================================================

  let currentPage = 1;
  const perPage = 15;

  const getErroRows = () => qsa("#tabelaErros tbody tr");
  const getChecks = () => qsa(".erro-check");

  const getRowsByCurrentFilter = () => {
    const filtroErro = qs("#filtroErro");
    const tipo = filtroErro?.value || "TODOS";

    return getErroRows().filter((tr) => {
      return tipo === "TODOS" || tr.dataset.tipo === tipo;
    });
  };

  const getVisibleErroRows = () =>
    getErroRows().filter((tr) => tr.dataset.pageVisible === "1");

  const getSelectedChecks = () =>
    qsa(".erro-check:checked").filter((c) => {
      const tr = c.closest("tr");
      return tr && tr.dataset.pageVisible === "1";
    });

  const updateSelectionCounter = () => {
    const el = qs("#selectedCount");
    if (!el) return;
    el.textContent = String(getSelectedChecks().length);
  };

  const clearSelection = () => {
    getChecks().forEach((c) => {
      c.checked = false;
    });

    const checkMaster = qs("#checkMaster");
    if (checkMaster) checkMaster.checked = false;

    updateSelectionCounter();
  };

  const renderClientPagination = () => {
    const rows = getErroRows();
    const filteredRows = getRowsByCurrentFilter();
    const pagination = qs(".audit-pagination");

    if (!rows.length) return;

    const totalPages = Math.max(1, Math.ceil(filteredRows.length / perPage));

    if (currentPage > totalPages) currentPage = totalPages;
    if (currentPage < 1) currentPage = 1;

    rows.forEach((row) => {
      row.style.display = "none";
      row.dataset.pageVisible = "0";
    });

    const start = (currentPage - 1) * perPage;
    const end = start + perPage;

    filteredRows.slice(start, end).forEach((row) => {
      row.style.display = "";
      row.dataset.pageVisible = "1";
    });

    if (pagination) {
      pagination.innerHTML = `
        <span>Página ${currentPage} de ${totalPages} · ${filteredRows.length} problema(s)</span>
        <div class="row">
          <button type="button" class="ghost" ${currentPage <= 1 ? "disabled" : ""} id="pgPrev">Anterior</button>
          <button type="button" class="ghost" ${currentPage >= totalPages ? "disabled" : ""} id="pgNext">Próxima</button>
        </div>
      `;

      qs("#pgPrev")?.addEventListener("click", () => {
        currentPage -= 1;
        clearSelection();
        renderClientPagination();
      });

      qs("#pgNext")?.addEventListener("click", () => {
        currentPage += 1;
        clearSelection();
        renderClientPagination();
      });
    }

    clearSelection();
  };

  const selectVisibleErrors = () => {
    getVisibleErroRows().forEach((tr) => {
      const check = qs(".erro-check", tr);
      if (check) check.checked = true;
    });

    updateSelectionCounter();
  };

  const initAuditSelection = () => {
    const tabela = qs("#tabelaErros");
    if (!tabela) return;

    const checkMaster = qs("#checkMaster");

    checkMaster?.addEventListener("change", () => {
      getVisibleErroRows().forEach((tr) => {
        const check = qs(".erro-check", tr);
        if (check) check.checked = checkMaster.checked;
      });

      updateSelectionCounter();
    });

    qs("#btnSelectAllErrors")?.addEventListener("click", () => {
      selectVisibleErrors();
      toast("Linhas da página selecionadas.", "ok");
    });

    qs("#btnClearSelection")?.addEventListener("click", () => {
      clearSelection();
      toast("Seleção limpa.", "info");
    });

    getChecks().forEach((check) => {
      check.addEventListener("change", updateSelectionCounter);
    });

    renderClientPagination();
    updateSelectionCounter();
  };

  // ============================================================
  // AÇÕES / CONFIRMAÇÕES
  // ============================================================

  const initAuditForms = () => {
    const formSelecionados = qs("#formErrosSelecionados");
    const acaoErros = qs("#acaoErros");

    if (formSelecionados) {
      formSelecionados.addEventListener("submit", (e) => {
        const acao = acaoErros?.value || "excluir_selecionados";
        const qtdSelecionados = getSelectedChecks().length;

        if (acao === "excluir_selecionados" && qtdSelecionados === 0) {
          e.preventDefault();
          toast("Selecione pelo menos uma linha.", "warn");
          return;
        }

        if (acao === "excluir_todos_erros") {
          const ok = confirm("Excluir todas as linhas com erro bloqueante?");
          if (!ok) e.preventDefault();
          return;
        }

        if (acao === "excluir_todos_filtrados") {
          const ok = confirm("Excluir todas as linhas do filtro atual?");
          if (!ok) e.preventDefault();
          return;
        }

        if (acao === "excluir_selecionados") {
          const ok = confirm(`Excluir ${qtdSelecionados} linha(s) selecionada(s)?`);
          if (!ok) e.preventDefault();
        }
      });
    }

    qsa('form input[name="acao"][value="excluir_individual"]').forEach((input) => {
      const f = input.closest("form");
      if (!f) return;

      f.addEventListener("submit", (e) => {
        const ok = confirm("Excluir esta linha da geração do TXT?");
        if (!ok) e.preventDefault();
      });
    });

    qsa('form input[name="acao"][value="limpar_exclusoes"]').forEach((input) => {
      const f = input.closest("form");
      if (!f) return;

      f.addEventListener("submit", (e) => {
        const ok = confirm("Restaurar todas as linhas excluídas?");
        if (!ok) e.preventDefault();
      });
    });
  };

  const initFiltro = () => {
    const filtroErro = qs("#filtroErro");
    if (!filtroErro) return;

    filtroErro.addEventListener("change", (e) => {
      e.preventDefault();
      currentPage = 1;
      clearSelection();
      renderClientPagination();
    });
  };

  const initDownload = () => {
    qsa('form[action*="/bpa/download"]').forEach((f) => {
      f.addEventListener("submit", () => {
        toast("Gerando TXT...", "info");
      });
    });
  };

  const initPrintButtons = () => {
    qsa("[data-print-audit]").forEach((btn) => {
      btn.addEventListener("click", () => window.print());
    });
  };

  // ============================================================
  // INIT
  // ============================================================

  const init = () => {
    markAllNeutral();

    if (cpfInput?.value) {
      cpfInput.value = maskCPF(cpfInput.value);
      if (cpfHidden) cpfHidden.value = unmaskCPF(cpfInput.value);
    }

    if (compHidden?.value && !compInput?.value) {
      const monthValue = competenciaToMonth(compHidden.value);
      if (monthValue && compInput) compInput.value = monthValue;
    }

    if (compInput?.value && compHidden) {
      compHidden.value = monthToCompetencia(compInput.value);
    }

    initForm();
    touchValidity({ silent: true });

    initAuditSelection();
    initAuditForms();
    initFiltro();
    initDownload();
    initPrintButtons();

    scrollToAuditIfExists();
  };

  document.addEventListener("DOMContentLoaded", init);
})();