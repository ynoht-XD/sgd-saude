// ======================================================
// MEUS ATENDIMENTOS · JS (v2)
// Arquivo: meus_atendimentos.js
// - Auto filtros
// - Labels mobile
// - Details accordion
// - Numeração de linhas (considera paginação)
// ======================================================

document.addEventListener("DOMContentLoaded", () => {
  console.log("📦 [meus_atendimentos.js] carregado!");

  const page = document.querySelector(".page-meus-atendimentos");
  if (!page) return;

  const form = page.querySelector(".ma-filters-form");
  const table = page.querySelector(".ma-table");
  const btnLimpar = page.querySelector(".btn-ghost");

  // ---------------------------
  // 1) Mobile labels (data-label)
  // ---------------------------
  applyMobileLabels(table);

  // ---------------------------
  // 1.1) Numeração de linhas
  // ---------------------------
  applyRowNumbers(page, table);

  // ---------------------------
  // 2) Limpar filtros com UX boa
  // ---------------------------
  if (btnLimpar && form) {
    btnLimpar.addEventListener("click", (e) => {
      try {
        // se for link, deixa ir normalmente
        if (btnLimpar.tagName.toLowerCase() === "a") return;
      } catch (_) {}

      // fallback: se virar button
      e.preventDefault();
      clearForm(form);
      form.submit();
    });
  }

  // ---------------------------
  // 3) Auto-filtrar (opcional)
  //    - paciente: debounce
  //    - datas/idades/cidade/cid: submit direto
  // ---------------------------
  if (form) {
    const fPaciente = form.querySelector("#f-q");
    const fIni = form.querySelector("#f-data-ini");
    const fFim = form.querySelector("#f-data-fim");
    const fIdMin = form.querySelector("#f-idade-min");
    const fIdMax = form.querySelector("#f-idade-max");
    const fCidade = form.querySelector("#f-cidade");
    const fCid = form.querySelector("#f-cid");

    // Debounce só no search (evita submit a cada tecla)
    if (fPaciente) {
      const debouncedSubmit = debounce(() => form.submit(), 450);

      fPaciente.addEventListener("input", () => {
        const v = (fPaciente.value || "").trim();
        if (v.length === 0) return debouncedSubmit();
        if (v.length < 3) return; // mínimo razoável
        debouncedSubmit();
      });

      // Enter = submit imediato / Esc limpa
      fPaciente.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") {
          ev.preventDefault();
          form.submit();
        }
        if (ev.key === "Escape") {
          fPaciente.value = "";
          form.submit();
        }
      });
    }

    // Campos “mudança”: submit direto
    [fIni, fFim, fIdMin, fIdMax, fCidade, fCid].forEach((el) => {
      if (!el) return;
      el.addEventListener("change", () => form.submit());
    });
  }

  // ---------------------------
  // 4) Details: abre 1 por vez (opcional)
  // ---------------------------
  wireDetailsAccordion(page);
});

/* ======================================================
   Helpers
   ====================================================== */

function applyMobileLabels(table) {
  if (!table) return;

  const headers = Array.from(table.querySelectorAll("thead th")).map((th) =>
    (th.textContent || "").trim()
  );
  if (!headers.length) return;

  const rows = table.querySelectorAll("tbody tr");
  rows.forEach((tr) => {
    const tds = tr.querySelectorAll("td");
    tds.forEach((td, idx) => {
      if (!td.getAttribute("data-label") && headers[idx]) {
        td.setAttribute("data-label", headers[idx]);
      }
    });
  });
}

function applyRowNumbers(pageRoot, table) {
  if (!table || !pageRoot) return;

  // Pega info de paginação caso você tenha colocado no HTML:
  // <div class="ma-pager" data-page="2" data-per-page="20"></div>
  const pager = pageRoot.querySelector(".ma-pager");
  let page = 1;
  let perPage = 20;

  if (pager) {
    const p = parseInt(pager.getAttribute("data-page") || "1", 10);
    const pp = parseInt(pager.getAttribute("data-per-page") || "20", 10);
    if (!Number.isNaN(p) && p > 0) page = p;
    if (!Number.isNaN(pp) && pp > 0) perPage = pp;
  }

  const startIndex = (page - 1) * perPage;

  const tbody = table.querySelector("tbody");
  if (!tbody) return;

  const rows = Array.from(tbody.querySelectorAll("tr"));
  rows.forEach((tr, i) => {
    const n = startIndex + i + 1;

    // Se você já tiver uma célula de numeração:
    // <td class="ma-col-n"></td>
    let numCell = tr.querySelector("td.ma-col-n");

    // Se não tiver, cria e injeta como primeira coluna
    if (!numCell) {
      const firstTd = tr.querySelector("td");
      numCell = document.createElement("td");
      numCell.className = "ma-col-n";
      numCell.setAttribute("data-label", "#");
      if (firstTd) tr.insertBefore(numCell, firstTd);
      else tr.appendChild(numCell);
    }

    numCell.textContent = String(n);
  });

  // Também garante o <th>#</th> se não existir
  ensureNumberHeader(table);
}

function ensureNumberHeader(table) {
  const thead = table.querySelector("thead");
  if (!thead) return;

  const tr = thead.querySelector("tr");
  if (!tr) return;

  const already = tr.querySelector("th.ma-col-n");
  if (already) return;

  const th = document.createElement("th");
  th.className = "ma-col-n";
  th.textContent = "#";

  const firstTh = tr.querySelector("th");
  if (firstTh) tr.insertBefore(th, firstTh);
  else tr.appendChild(th);
}

function clearForm(form) {
  const inputs = form.querySelectorAll("input, select");
  inputs.forEach((el) => {
    const tag = (el.tagName || "").toLowerCase();
    if (tag === "select") {
      el.selectedIndex = 0;
      return;
    }

    const type = (el.getAttribute("type") || "").toLowerCase();
    if (type === "search" || type === "text" || type === "date" || type === "number") {
      el.value = "";
    }
  });
}

function debounce(fn, wait = 350) {
  let t = null;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), wait);
  };
}

function wireDetailsAccordion(root) {
  const allDetails = Array.from(root.querySelectorAll(".ma-evol-details"));
  if (!allDetails.length) return;

  allDetails.forEach((d) => {
    d.addEventListener("toggle", () => {
      if (!d.open) return;
      allDetails.forEach((other) => {
        if (other !== d) other.open = false;
      });
    });
  });
}
