// ============================================================
// AVALIAÇÕES · JS GLOBAL
// Arquivo: sgd/avaliacoes/static/js/avaliacoes.js
// ============================================================

document.addEventListener("DOMContentLoaded", () => {
  console.log("📋 [avaliacoes.js] carregado");
  initPacienteAutocomplete();
});

/* ============================================================
   HELPERS
   ============================================================ */

function debounce(fn, wait = 300) {
  let t;

  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn.apply(null, args), wait);
  };
}

function qs(sel, root = document) {
  return root.querySelector(sel);
}

function normalizeText(v) {
  return String(v || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function onlyDigits(v) {
  return String(v || "").replace(/\D+/g, "");
}

function createHidden(form, name) {
  const i = document.createElement("input");
  i.type = "hidden";
  i.name = name;
  form.appendChild(i);
  return i;
}

function escapeHTML(v) {
  return String(v || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

/* ============================================================
   AUTOCOMPLETE DE PACIENTE
   ============================================================ */

function initPacienteAutocomplete() {
  const inputNome = qs('input[name="paciente_nome"]');
  if (!inputNome) return;

  const form = inputNome.closest("form");
  if (!form) return;

  const inputId =
    qs('input[name="paciente_id"]', form) ||
    createHidden(form, "paciente_id");

  const inputPront =
    qs('input[name="paciente_prontuario"]', form) ||
    createHidden(form, "paciente_prontuario");

  const inputCpf =
    qs('input[name="paciente_cpf"]', form) ||
    createHidden(form, "paciente_cpf");

  let selecionado = false;
  let selectedName = "";
  let requestSeq = 0;
  let controller = null;

  const wrapper = document.createElement("div");
  wrapper.className = "avaliacao-autocomplete-wrap";
  wrapper.style.position = "relative";
  wrapper.style.zIndex = "50";

  inputNome.parentNode.insertBefore(wrapper, inputNome);
  wrapper.appendChild(inputNome);

  const list = document.createElement("div");
  list.className = "paciente-autocomplete";
  Object.assign(list.style, {
    position: "absolute",
    top: "calc(100% + 6px)",
    left: 0,
    right: 0,
    zIndex: 99999,
    background: "#fff",
    border: "1px solid #e5e7eb",
    borderRadius: "14px",
    boxShadow: "0 18px 44px rgba(2,6,23,.18)",
    display: "none",
    overflow: "hidden",
    maxHeight: "280px",
    overflowY: "auto",
  });

  wrapper.appendChild(list);

  const buscar = debounce(async () => {
    const q = inputNome.value.trim();
    const qNorm = normalizeText(q);
    const qDigits = onlyDigits(q);

    if (q.length < 3) {
      limparVinculo();
      hideList();
      return;
    }

    const seq = ++requestSeq;

    if (controller) {
      controller.abort();
    }

    controller = new AbortController();

    showLoading();

    try {
      const resp = await fetch(
        `/avaliacoes/api/pacientes?q=${encodeURIComponent(q)}`,
        {
          headers: { Accept: "application/json" },
          signal: controller.signal,
        }
      );

      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }

      const data = await resp.json();

      if (seq !== requestSeq) return;

      const items = Array.isArray(data.items) ? data.items : [];

      const filtrados = items.filter((item) => {
        const nome = normalizeText(item.nome);
        const prontuario = normalizeText(item.prontuario);
        const cpf = onlyDigits(item.cpf);

        const matchTexto =
          nome.includes(qNorm) ||
          prontuario.includes(qNorm);

        const matchNumero =
          qDigits.length >= 3 &&
          (cpf.includes(qDigits) || onlyDigits(item.prontuario).includes(qDigits));

        return matchTexto || matchNumero;
      });

      renderLista(list, filtrados, q, (item) => {
        inputNome.value = item.nome || "";
        inputId.value = item.id || "";
        inputPront.value = item.prontuario || "";
        inputCpf.value = item.cpf || "";

        selecionado = true;
        selectedName = inputNome.value.trim();

        hideList();
      });

    } catch (e) {
      if (e.name === "AbortError") return;

      console.error("❌ Erro ao buscar pacientes:", e);
      hideList();
    }
  }, 350);

  inputNome.addEventListener("input", () => {
    const atual = inputNome.value.trim();

    if (selecionado && normalizeText(atual) !== normalizeText(selectedName)) {
      limparVinculo(false);
    }

    buscar();
  });

  inputNome.addEventListener("focus", () => {
    if (inputNome.value.trim().length >= 3 && !selecionado) {
      buscar();
    }
  });

  inputNome.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      hideList();
    }
  });

  form.addEventListener("submit", (e) => {
    if (!inputId.value) {
      e.preventDefault();
      inputNome.focus();
      showMessage("Selecione um paciente da lista antes de salvar.");
    }
  });

  document.addEventListener("click", (e) => {
    if (!wrapper.contains(e.target)) {
      hideList();
    }
  });

  function limparVinculo(clearName = true) {
    if (clearName) selectedName = "";

    inputId.value = "";
    inputPront.value = "";
    inputCpf.value = "";

    selecionado = false;
  }

  function hideList() {
    list.style.display = "none";
    list.innerHTML = "";
    wrapper.classList.remove("autocomplete-open");
  }

  function showLoading() {
    list.innerHTML = `
      <div style="padding:11px 13px;color:#64748b;font-weight:800">
        Buscando paciente...
      </div>
    `;
    list.style.display = "block";
    wrapper.classList.add("autocomplete-open");
  }

  function showMessage(msg) {
    list.innerHTML = `
      <div style="padding:11px 13px;color:#991b1b;background:#fee2e2;font-weight:800">
        ${escapeHTML(msg)}
      </div>
    `;
    list.style.display = "block";
    wrapper.classList.add("autocomplete-open");
  }
}

/* ============================================================
   RENDER DA LISTA
   ============================================================ */

function renderLista(container, items, termo, onSelect) {
  container.innerHTML = "";

  if (!items || items.length === 0) {
    container.innerHTML = `
      <div style="padding:11px 13px;color:#64748b;font-weight:800">
        Nenhum paciente encontrado para “${escapeHTML(termo)}”
      </div>
    `;
    container.style.display = "block";
    return;
  }

  items.forEach((item) => {
    const row = document.createElement("button");
    row.type = "button";

    Object.assign(row.style, {
      width: "100%",
      padding: "11px 13px",
      cursor: "pointer",
      display: "flex",
      flexDirection: "column",
      alignItems: "flex-start",
      gap: "3px",
      border: "0",
      borderBottom: "1px solid #f1f5f9",
      background: "#fff",
      textAlign: "left",
    });

    row.innerHTML = `
      <strong style="color:#0f172a">${escapeHTML(item.nome || "Sem nome")}</strong>
      <small style="color:#64748b;font-weight:700">
        Prontuário: ${escapeHTML(item.prontuario || "-")}
      </small>
    `;

    row.addEventListener("mouseenter", () => {
      row.style.background = "#eef2ff";
    });

    row.addEventListener("mouseleave", () => {
      row.style.background = "#fff";
    });

    row.addEventListener("click", () => onSelect(item));

    container.appendChild(row);
  });

  container.style.display = "block";
}