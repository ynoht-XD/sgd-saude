// meus_atendimentos/static/js/meus_atendimentos.js
document.addEventListener("DOMContentLoaded", () => {
  const page = document.querySelector(".page-meus-atendimentos");
  if (!page) return;

  const form = page.querySelector(".ma-filters-form");
  const modal = document.getElementById("modalMeuAtendimento");

  initAutoFilters(form);
  initModal(modal);
});

function initModal(modal) {
  if (!modal) return;

  const elPaciente = document.getElementById("maModalPaciente");
  const elSub = document.getElementById("maModalSub");
  const elData = document.getElementById("maModalData");
  const elIdade = document.getElementById("maModalIdade");
  const elProcedimento = document.getElementById("maModalProcedimento");
  const elEvolucao = document.getElementById("maModalEvolucao");

  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".ma-open-modal");
    if (!btn) return;

    const card = btn.closest(".ma-card");
    if (!card) return;

    elPaciente.textContent = card.dataset.paciente || "Paciente";
    elSub.textContent = `Atendimento #${card.dataset.id || "—"}`;
    elData.textContent = formatBR(card.dataset.data);
    elIdade.textContent = card.dataset.idade || "—";
    elProcedimento.textContent = card.dataset.procedimento || "—";
    elEvolucao.textContent = card.dataset.evolucao || "Sem evolução registrada.";

    if (typeof modal.showModal === "function") modal.showModal();
    else modal.setAttribute("open", "open");
  });

  document.addEventListener("click", (e) => {
    if (!e.target.closest("[data-close-modal]")) return;
    closeModal(modal);
  });

  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal(modal);
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal.open) closeModal(modal);
  });
}

function closeModal(modal) {
  if (typeof modal.close === "function") modal.close();
  else modal.removeAttribute("open");
}

function initAutoFilters(form) {
  if (!form) return;

  const fPaciente = form.querySelector("#f-q");
  const fIni = form.querySelector("#f-data-ini");
  const fFim = form.querySelector("#f-data-fim");
  const fIdMin = form.querySelector("#f-idade-min");
  const fIdMax = form.querySelector("#f-idade-max");
  const fCidade = form.querySelector("#f-cidade");
  const fCid = form.querySelector("#f-cid");

  if (fPaciente) {
    const debouncedSubmit = debounce(() => form.submit(), 450);

    fPaciente.addEventListener("input", () => {
      const v = (fPaciente.value || "").trim();
      if (v.length === 0) return debouncedSubmit();
      if (v.length < 3) return;
      debouncedSubmit();
    });

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

  [fIni, fFim, fIdMin, fIdMax, fCidade, fCid].forEach((el) => {
    if (!el) return;
    el.addEventListener("change", () => form.submit());
  });
}

function formatBR(value) {
  if (!value) return "—";

  const s = String(value).trim();
  const iso = s.slice(0, 10);

  if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) {
    const [y, m, d] = iso.split("-");
    return `${d}/${m}/${y}`;
  }

  return s || "—";
}

function debounce(fn, wait = 350) {
  let t = null;

  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), wait);
  };
}