// ============================================================
// AVALIAÇÕES · JS GLOBAL
// Arquivo: sgd/avaliacoes/static/js/avaliacoes.js
// ------------------------------------------------------------
// Responsável por:
// - Autocomplete de pacientes (3+ letras)
// - Referência por id / nome / prontuário
// - Garantir consistência dos dados enviados
// - UX limpa e profissional (SGD style)
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

function qsa(sel, root = document) {
  return Array.from(root.querySelectorAll(sel));
}

/* ============================================================
   AUTOCOMPLETE DE PACIENTE
   ============================================================ */

function initPacienteAutocomplete() {
  const inputNome = qs('input[name="paciente_nome"]');
  if (!inputNome) return;

  const form = inputNome.closest("form");
  if (!form) return;

  // Campos ocultos (criamos se não existirem)
  const inputId =
    qs('input[name="paciente_id"]', form) ||
    createHidden(form, "paciente_id");

  const inputPront =
    qs('input[name="paciente_prontuario"]', form) ||
    createHidden(form, "paciente_prontuario");

  // Marca quando um paciente foi realmente selecionado da lista
  let selecionado = false;

  /* ----------------------------
     Wrapper visual
     ---------------------------- */
  const wrapper = document.createElement("div");
  wrapper.style.position = "relative";

  inputNome.parentNode.insertBefore(wrapper, inputNome);
  wrapper.appendChild(inputNome);

  /* ----------------------------
     Lista de resultados
     ---------------------------- */
  const list = document.createElement("div");
  list.className = "paciente-autocomplete";
  Object.assign(list.style, {
    position: "absolute",
    top: "100%",
    left: 0,
    right: 0,
    zIndex: 30,
    background: "#fff",
    border: "1px solid #e5e7eb",
    borderRadius: "12px",
    boxShadow: "0 10px 30px rgba(2,6,23,.12)",
    marginTop: "4px",
    display: "none",
    overflow: "hidden",
  });
  wrapper.appendChild(list);

  /* ----------------------------
     Busca remota (debounced)
     ---------------------------- */
  const buscar = debounce(async () => {
    const q = inputNome.value.trim();

    // Se apagou ou menos de 3 letras → limpa vínculo
    if (q.length < 3) {
      limparVinculo();
      hideList();
      return;
    }

    try {
      const resp = await fetch(
        `/avaliacoes/api/pacientes?q=${encodeURIComponent(q)}`
      );
      const data = await resp.json();

      renderLista(list, data.items, (item) => {
        inputNome.value = item.nome;
        inputId.value = item.id;
        inputPront.value = item.prontuario || "";
        selecionado = true;
        hideList();
      });
    } catch (e) {
      console.error("❌ Erro ao buscar pacientes:", e);
    }
  }, 350);

  inputNome.addEventListener("input", () => {
    // Se o usuário editar depois de selecionar → invalida vínculo
    if (selecionado) {
      limparVinculo();
    }
    buscar();
  });

  /* ----------------------------
     Fecha ao clicar fora
     ---------------------------- */
  document.addEventListener("click", (e) => {
    if (!wrapper.contains(e.target)) {
      hideList();
    }
  });

  /* ----------------------------
     Helpers locais
     ---------------------------- */
  function limparVinculo() {
    inputId.value = "";
    inputPront.value = "";
    selecionado = false;
  }

  function hideList() {
    list.style.display = "none";
    list.innerHTML = "";
  }
}

/* ============================================================
   RENDER DA LISTA
   ============================================================ */

function renderLista(container, items, onSelect) {
  container.innerHTML = "";

  if (!items || items.length === 0) {
    container.innerHTML = `
      <div style="padding:10px 12px;color:#64748b;font-weight:700">
        Nenhum paciente encontrado
      </div>
    `;
    container.style.display = "block";
    return;
  }

  items.forEach((item) => {
    const row = document.createElement("div");
    row.style.padding = "10px 12px";
    row.style.cursor = "pointer";
    row.style.display = "flex";
    row.style.flexDirection = "column";
    row.style.gap = "2px";

    row.innerHTML = `
      <strong>${item.nome}</strong>
      <small style="color:#64748b">
        Prontuário: ${item.prontuario || "-"}
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

/* ============================================================
   UTILS
   ============================================================ */

function createHidden(form, name) {
  const i = document.createElement("input");
  i.type = "hidden";
  i.name = name;
  form.appendChild(i);
  return i;
}
