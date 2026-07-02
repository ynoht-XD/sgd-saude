// export/static/js/apac.js
(() => {
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const on = (el, ev, fn) => el && el.addEventListener(ev, fn);

  const modal = $("#modal-edicao-apac");
  const modalForm = $("#modal-edicao-apac form") || $("#form-edicao-apac");

  const DATE_FIELDS = new Set([
    "data_inicial",
    "data_final",
    "data_nascimento",
    "data_nota_fiscal",
    "data_entrada_nf",
    "data_pedido",
    "data_entrega",
    "data_solicitacao",
    "data_autorizacao",
  ]);

  const FIELD_NAMES = [
    "id_apac",
    "numero_apac",
    "competencia",
    "procedimento",
    "codigo_procedimento",
    "quantidade",
    "cnes",
    "data_inicial",
    "data_final",
    "tipo_apac",
    "nacionalidade",
    "tipo_apac",
    "nacionalidade",
    "carater_atendimento",
    "nome_paciente",
    "nome_paciente",
    "cns_paciente",
    "cpf_paciente",
    "data_nascimento",
    "nome_mae",
    "responsavel",
    "sexo",
    "raca",
    "endereco",
    "numero",
    "bairro",
    "cep",
    "cid",
    "cid2",
    "descricao_diagnostico",
    "obs_geral",
    "nome_solicitante",
    "cns_solicitante",
    "data_solicitacao",
    "nome_autorizador",
    "cns_autorizador",
    "data_autorizacao",
    "orgao_emissor",
    "status",
    "nota_fiscal",
    "data_nota_fiscal",
    "data_entrada_nf",
    "competencia_nota",
    "protocolo_nota",
    "obs_nota",
    "data_pedido",
    "fornecedor",
    "obs_pedido",
    "data_entrega",
    "local_entrega",
    "status_entrega",
    "obs_entrega",
    "cbo_executante",
    "cns_executante",
    "servico",
    "classificacao",
  ];

  function toISO(value) {
    if (!value) return "";

    const s = String(value).trim();

    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;

    if (/^\d{2}\/\d{2}\/\d{4}$/.test(s)) {
      const [dd, mm, yyyy] = s.split("/");
      return `${yyyy}-${mm}-${dd}`;
    }

    const digits = s.replace(/\D+/g, "");

    if (digits.length === 8) {
      const dd = digits.slice(0, 2);
      const mm = digits.slice(2, 4);
      const yyyy = digits.slice(4);
      return `${yyyy}-${mm}-${dd}`;
    }

    return s;
  }

  function debounce(fn, wait = 600) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), wait);
    };
  }

  async function postJson(url, payload) {
    const resp = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }

    return await resp.json();
  }

  function markSaving(el) {
    const card = el.closest(".apac-card");
    if (card) card.classList.add("saving");
  }

  function markSaved(el) {
    const card = el.closest(".apac-card");
    if (!card) return;

    card.classList.remove("saving");
    card.classList.add("saved");

    setTimeout(() => card.classList.remove("saved"), 900);
  }

  function markError(el) {
    const card = el.closest(".apac-card");
    if (!card) return;

    card.classList.remove("saving");
    card.classList.add("save-error");

    setTimeout(() => card.classList.remove("save-error"), 1300);
  }

  // ============================================================
  // Modal edição
  // ============================================================

  function setFieldValue(name, value) {
    if (!modal) return;

    const el = modal.querySelector(`[name="${name}"]`);
    if (!el) return;

    let v = value ?? "";

    if (DATE_FIELDS.has(name)) {
      v = toISO(v);
    }

    el.value = v;
  }

  function openModal() {
    if (!modal) return;
    modal.style.display = "flex";
    document.body.style.overflow = "hidden";
  }

  function closeModal() {
    if (!modal) return;
    modal.style.display = "none";
    document.body.style.overflow = "";
  }

  function fillModalFromButton(btn) {
    FIELD_NAMES.forEach((name) => {
      setFieldValue(name, btn.dataset[name] || "");
    });

    const idHidden =
      modal.querySelector("#id_apac_editar") ||
      modal.querySelector('[name="id_apac"]');

    if (idHidden) {
      idHidden.value = btn.dataset.id || "";
    }

    setTimeout(() => {
      const first = modal.querySelector("input:not([readonly]), select, textarea");
      if (first) first.focus();
    }, 80);
  }

  $$(".btn-editar").forEach((btn) => {
    on(btn, "click", () => {
      fillModalFromButton(btn);
      openModal();
    });
  });

  $$("#modal-edicao-apac .icon-btn, #modal-edicao-apac [data-close], #modal-edicao-apac .js-close")
    .forEach((btn) => on(btn, "click", closeModal));

  on(modal, "click", (e) => {
    if (e.target === modal) closeModal();
  });

  on(document, "keydown", (e) => {
    if (e.key === "Escape") closeModal();
  });

  on(modalForm, "submit", () => {
    DATE_FIELDS.forEach((name) => {
      const el = modalForm.querySelector(`[name="${name}"]`);
      if (el && el.value) {
        el.value = toISO(el.value);
      }
    });
  });

  $$(".apac-card").forEach((card) => {
    on(card, "dblclick", (e) => {
      if (e.target.closest("button, a, form, input, textarea, label")) return;

      const btn = card.querySelector(".btn-editar");
      if (btn) {
        fillModalFromButton(btn);
        openModal();
      }
    });
  });

  // ============================================================
  // Autosave checks: processado / sms_enviado / bpai
  // Espera rota POST /export/apac/autosave
  // payload: { id, campo, valor }
  // ============================================================

  $$(".js-toggle").forEach((check) => {
    on(check, "change", async () => {
      const id = check.dataset.id;
      const campo = check.dataset.campo;
      const valor = check.checked;

      if (!id || !campo) return;

      try {
        markSaving(check);

        await postJson("/export/apac/autosave", {
          id,
          campo,
          valor,
        });

        markSaved(check);
      } catch (err) {
        console.error("Erro ao salvar check:", err);
        check.checked = !valor;
        markError(check);
      }
    });
  });

  // ============================================================
  // Autosave observações
  // Espera rota POST /export/apac/autosave
  // payload: { id, campo: "obs_geral", valor }
  // ============================================================

  const salvarObs = debounce(async (textarea) => {
    const id = textarea.dataset.id;
    const valor = textarea.value || "";

    if (!id) return;

    try {
      markSaving(textarea);

      await postJson("/export/apac/autosave", {
        id,
        campo: "obs_geral",
        valor,
      });

      markSaved(textarea);
    } catch (err) {
      console.error("Erro ao salvar observação:", err);
      markError(textarea);
    }
  }, 700);

  $$(".js-obs").forEach((textarea) => {
    on(textarea, "input", () => salvarObs(textarea));
    on(textarea, "blur", () => salvarObs(textarea));
  });
})();