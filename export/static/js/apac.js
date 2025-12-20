// export/static/js/apac.js
(() => {
  // ===== Helpers =====
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const on = (el, ev, fn) => el && el.addEventListener(ev, fn);

  const isISODate = (s) => /^\d{4}-\d{2}-\d{2}$/.test(s || "");
  const isBRDate  = (s) => /^\d{2}\/\d{2}\/\d{4}$/.test(s || "");

  const toISO = (s) => {
    if (!s) return "";
    s = String(s).trim();
    if (isISODate(s)) return s;
    if (isBRDate(s)) {
      const [dd, mm, yyyy] = s.split("/");
      return `${yyyy}-${mm}-${dd}`;
    }
    // tenta normalizar sem separador (ddmmyyyy)
    const digits = s.replace(/\D+/g, "");
    if (digits.length === 8) {
      const dd = digits.slice(0, 2);
      const mm = digits.slice(2, 4);
      const yyyy = digits.slice(4);
      return `${yyyy}-${mm}-${dd}`;
    }
    return s;
  };

  // ===== Elements =====
  const modal = $("#modal-edicao-apac");
  const editButtons = $$(".btn-editar");
  const closeBtns = $$("#modal-edicao-apac [data-close], #modal-edicao-apac .js-close, #modal-edicao-apac .icon-btn");
  const modalForm = $("#modal-edicao-apac form") || $("#form-edicao-apac");

  // Campos conhecidos no modal (name=...)
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
    "nome_paciente",
    "cns_paciente",
    "cpf_paciente",
    "data_nascimento",
    "nome_mae",
    "sexo",
    "raca",
    "endereco",
    "numero",
    "bairro",
    "cep",
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
    "obs_entrega",
    "status_entrega",
    "cbo_executante",
    "cns_executante",
    "servico",
    "classificacao",
  ];

  const DATE_FIELDS = new Set([
    "data_inicial",
    "data_final",
    "data_nota_fiscal",
    "data_entrada_nf",
    "data_pedido",
    "data_entrega",
    "data_nascimento",
  ]);

  function setFieldValue(name, value) {
    const el = modal?.querySelector(`[name="${name}"]`);
    if (!el) return;
    let v = value ?? "";

    // normaliza datas para inputs type=date
    if (DATE_FIELDS.has(name)) {
      v = toISO(v);
    }

    if (el.tagName === "SELECT" || el.tagName === "TEXTAREA") {
      el.value = v;
    } else {
      el.value = v;
    }
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

  // Fecha modal em botões dedicados
  closeBtns.forEach((btn) => on(btn, "click", closeModal));

  // Fecha modal clicando fora do card
  on(modal, "click", (e) => {
    if (e.target === modal) closeModal();
  });

  // ESC fecha modal
  on(document, "keydown", (e) => {
    if (e.key === "Escape" && modal && modal.style.display === "flex") {
      closeModal();
    }
  });

  function fillModalFromButton(btn) {
    // Preenche todos os campos por data-atributos
    FIELD_NAMES.forEach((name) => setFieldValue(name, btn.dataset[name] || ""));

    // Campo id (fallbacks)
    const idFromBtn = btn.dataset.id || btn.getAttribute("data-id");
    const idHidden = modal.querySelector("#id_apac_editar") || modal.querySelector('[name="id_apac"]');
    if (idFromBtn && idHidden) idHidden.value = idFromBtn;

    // Ajustes UX (foco no primeiro campo editável)
    const firstEditable = modal.querySelector('input:not([readonly]), select, textarea');
    if (firstEditable) setTimeout(() => firstEditable.focus(), 60);
  }

  // Clicar "Editar" abre o modal e popula
  editButtons.forEach((btn) => {
    on(btn, "click", () => {
      fillModalFromButton(btn);
      openModal();
    });
  });

  // Submissão do modal — normaliza datas antes de enviar
  on(modalForm, "submit", () => {
    DATE_FIELDS.forEach((name) => {
      const el = modalForm.querySelector(`[name="${name}"]`);
      if (el && el.value) el.value = toISO(el.value);
    });
  });

  // ===== (Opcional) manter filtros na URL ao exportar =====
  // Se colocar class="js-keep-query" nos links de export, mantém os filtros atuais.
  $$(".js-keep-query").forEach((a) => {
    on(a, "click", (e) => {
      const qs = window.location.search;
      if (!qs) return; // nada a fazer
      try {
        const url = new URL(a.href, window.location.origin);
        // Transfere todos os params atuais para o link
        const current = new URLSearchParams(window.location.search);
        current.forEach((val, key) => url.searchParams.set(key, val));
        a.href = url.toString();
      } catch {
        // deixa seguir do jeito que está
      }
    });
  });

  // ===== Clique na linha → abrir modal (conveniência) =====
  // Depende de haver um botão .btn-editar dentro da linha.
  $$(".apac-table tbody tr").forEach((tr) => {
    on(tr, "dblclick", () => {
      const btn = tr.querySelector(".btn-editar");
      if (btn) {
        fillModalFromButton(btn);
        openModal();
      }
    });
  });

})();
